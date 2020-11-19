# -*- coding: utf-8 -*-
"""Classes for calcs e wfls analysis."""
from __future__ import absolute_import
import numpy as np
from scipy.optimize import curve_fit
from matplotlib import pyplot as plt, style
import pandas as pd
import copy

try:
    from aiida.orm import Dict, Str, load_node, KpointsData, RemoteData
    from aiida.plugins import CalculationFactory, DataFactory
    from aiida_yambo.utils.common_helpers import *
except:
    pass
from aiida_yambo.utils.parallelism_finder import *
from aiida_yambo.utils.defaults.create_defaults import *
#we try to use netcdf
try:
    from netCDF4 import Dataset
except ImportError:
    _has_netcdf = False
else:
    _has_netcdf = True
################################################################################
################################################################################

def set_parallelism(instructions, inputs):

    resources = inputs.yres.yambo.metadata.options.resources
    structure = inputs.structure.get_ase()
    mesh = inputs.kpoints.get_kpoints_mesh()[0]
    kpoints = mesh[0]*mesh[1]*mesh[2]/2  #moreless... to fix

    occupied, ecut = periodical(structure)

    bands, qp, last_qp, runlevels = find_gw_info(inputs.yres.yambo)

    if 'BndsRnXp' in inputs.yres.yambo.parameters.get_dict().keys():
        yambo_bandsX = inputs.yres.yambo.parameters.get_dict()['BndsRnXp'][-1]
    else:
        yambo_bandsX = 0 
    
    if 'GbndRnge' in inputs.yres.yambo.parameters.get_dict().keys():
        yambo_bandsSc = inputs.yres.yambo.parameters.get_dict()['GbndRnge'][-1]
    else:
        yambo_bandsSc = 0

    bands = max(yambo_bandsX,yambo_bandsSc)

    if instructions['automatic'] and ('gw0' or 'HF_and_locXC' in runlevels):
        #standard
        new_parallelism, new_resources = find_parallelism_qp(resources['num_machines'], resources['num_mpiprocs_per_machine'], \
                                                        resources['num_cores_per_mpiproc'], bands, \
                                                        occupied, qp, kpoints,\
                                                        last_qp, namelist = {})
    
    elif instructions['semi-automatic'] and ('gw0' or 'HF_and_locXC' in runlevels):
        #parallel set for boundaries of params
        new_parallelism, new_resources = find_parallelism_qp(resources['num_machines'], resources['num_mpiprocs_per_machine'], \
                                                        resources['num_cores_per_mpiproc'], bands, \
                                                        occupied, qp, kpoints,\
                                                        last_qp, namelist = {})
    
    elif instructions['explicit']:
        #parallel set for each set of params
        new_parallelism = instructions['explicit']['parallelism']
        new_resources = instructions['explicit']['resources']
    
    elif instructions['function']:
        pass

    else:
        return {}, {}

    return new_parallelism, new_resources


#class calc_manager_aiida_yambo: 
def calc_manager_aiida_yambo(calc_info={}, wfl_settings={}):
    
    calc_dict = {}
    calc_dict.update(calc_info)
    calc_dict.update(wfl_settings)
    calc_dict['iter']  = 0
    calc_dict['success'] = False
    calc_dict['conv_thr'] = calc_dict.pop('conv_thr',0.1)
    calc_dict['max_iterations'] = calc_dict.pop('max_iterations',3)
    calc_dict['steps'] = calc_dict.pop('steps',3)
    calc_dict['conv_window'] = calc_dict.pop('conv_window',calc_dict['steps'])
    
    if calc_dict['type'] != '1D_convergence': 
        calc_dict['steps'] = len(calc_dict['space'])
    
    return calc_dict

################################## update_parameters - create parameters space #####################################
def updater(calc_dict, inp_to_update, parameters, parallelism_instructions, values_dict = {}):

    if not isinstance(calc_dict['var'],list):
        calc_dict['var'] = [calc_dict['var']]

    input_dict = inp_to_update.yres.yambo.parameters.get_dict()
    
    for var in calc_dict['var']:
        if var == 'kpoint_mesh' or var == 'kpoint_density':
            k_quantity = parameters[var].pop(0)
            k_quantity_shift = inp_to_update.scf.kpoints.get_kpoints_mesh()[1]
            inp_to_update.scf.kpoints = KpointsData()
            inp_to_update.scf.kpoints.set_cell_from_structure(inp_to_update.scf.pw.structure) #to count the PBC...
            if isinstance(k_quantity,tuple):
                inp_to_update.scf.kpoints.set_kpoints_mesh(k_quantity,k_quantity_shift) 
            else:
                inp_to_update.scf.kpoints.set_kpoints_mesh_from_density(1/k_quantity, force_parity=True)
            inp_to_update.nscf.kpoints = inp_to_update.scf.kpoints

            try:
                inp_to_update.parent_folder =  find_pw_parent(take_calc_from_remote(inp_to_update.parent_folder), calc_type=['scf']).outputs.remote_folder 
                #I need to start from the scf calc
            except:
                del inp_to_update.parent_folder #do all scf+nscf+y in case

            inp_to_update.yres.yambo.settings = update_dict(inp_to_update.yres.yambo.settings, 'COPY_SAVE', False) #no yambo here
            inp_to_update.yres.yambo.settings = update_dict(inp_to_update.yres.yambo.settings, 'COPY_DBS', False)  #no yambo here
            values_dict[var]=k_quantity
        else:
            
            input_dict[var] = parameters[var].pop(0)
            inp_to_update.yres.yambo.parameters = Dict(dict=input_dict)
            values_dict[var]=input_dict[var]
    
    if parallelism_instructions != {}:
        new_para, new_res = set_parallelism(parallelism_instructions, inp_to_update)

        inp_to_update.yres.yambo.parameters = update_dict(inp_to_update.yres.yambo.parameters, list(new_para.keys()), list(new_para.values()))
        inp_to_update.yres.yambo.metadata.options.resources = new_res

    return inp_to_update, values_dict

################################## parsers #####################################
def take_quantities(calc_dict, steps = 1, where = [], what = 'gap',backtrace=1):

    try:
        backtrace = calc_dict['steps'] 
        where = calc_dict['where']
        what = calc_dict['what']
    except:
        pass

    print('looking for {} in k-points {}'.format(what,where))

    quantities = np.zeros((len(where),backtrace,3))

    for j in range(len(where)):
        for i in range(1,backtrace+1):
            try: #YamboConvergence
                yambo_calc = load_node(calc_dict['wfl_pk']).caller.called[backtrace-i].called[0].called[0]
            except: #YamboWorkflow,YamboRestart of YamboCalculation
                yambo_calc = load_node(calc_dict['wfl_pk'])
                print('values provided are: [iteration, value in eV, workflow pk]')
            if yambo_calc.is_finished_ok:
                if what == 'gap':
                    _vb=find_table_ind(where[j][1], where[j][0],yambo_calc.outputs.array_ndb)
                    _cb=find_table_ind(where[j][3], where[j][2],yambo_calc.outputs.array_ndb)
                    quantities[j,i-1,1] = abs((yambo_calc.outputs.array_ndb.get_array('Eo')[_vb].real+
                                yambo_calc.outputs.array_ndb.get_array('E_minus_Eo')[_vb].real)-
                                (yambo_calc.outputs.array_ndb.get_array('Eo')[_cb].real+
                                yambo_calc.outputs.array_ndb.get_array('E_minus_Eo')[_cb].real))

                if what == 'single-levels':
                    _level=find_table_ind(where[j][1], where[j][0],yambo_calc.outputs.array_ndb)
                    quantities[j,i-1,1] = yambo_calc.outputs.array_ndb.get_array('Eo')[_level].real+ \
                                yambo_calc.outputs.array_ndb.get_array('E_minus_Eo')[_level].real

                quantities[j,i-1,1] = quantities[j,i-1,1]*27.2114 #conversion to eV
            else:
                quantities[j,i-1,1] = False
                
            quantities[j,i-1,0] = i  #number of the iteration times to be used in a fit
            quantities[j,i-1,2] = int(yambo_calc.pk) #CalcJobNode.pk responsible of the calculation

    return quantities

def start_from_converged(inputs, node,):
    inputs.yres.yambo.parameters = node.called[0].get_builder_restart().yambo['parameters']
    inputs.yres.yambo.metadata.options.resources = node.called[0].called[0].get_options()['resources']
    inputs.yres.yambo.metadata.options.max_wallclock_seconds = node.called[0].called[0].get_options()['max_wallclock_seconds']