#!/usr/bin/env runaiida
# -*- coding: utf-8 -*-
import sys
import os
from aiida.orm import DataFactory, CalculationFactory
from aiida.common.example_helpers import test_and_get_code
from aiida.orm.data.base import List
from aiida.orm import Code
from aiida.orm import DataFactory
import pymatgen
from aiida.work.run import submit
from aiida_yambo.calculations.gw import YamboCalculation
from aiida_quantumespresso.calculations.pw import PwCalculation
from aiida.orm.data.upf import UpfData, get_pseudos_from_structure


#codename = 'pw_6.1@fidis' #'pw_6.2_2Dcode@marconi_knl' 


#code = Code.get_from_string(codename)

StructureData = DataFactory('structure')

a = 5.367 * pymatgen.core.units.bohr_to_ang
structure_pmg = pymatgen.Structure(
            lattice=[[-a, 0, a], [0, a, a], [-a, a, 0]],
            species=['Ga', 'As'],
            coords=[[0] * 3, [0.25] * 3]
        )
structure = StructureData()
structure.set_pymatgen_structure(structure_pmg)

 
ParameterData = DataFactory('parameter')
    
parameters = ParameterData(dict={
              'CONTROL': {
                  'calculation': 'scf',
                  'restart_mode': 'from_scratch',
                  'wf_collect': True,
                  'verbosity' :'high',
                  },
              'SYSTEM': {
                  'ecutwfc': 20.,
                  },
              'ELECTRONS': {
                  'conv_thr': 1.e-8,
                  'electron_maxstep ': 50,
                  'mixing_mode': 'plain',
                  'mixing_beta' : 0.7,
                  }})

KpointsData = DataFactory('array.kpoints')
kpoints = KpointsData() 
kpoints.set_kpoints_mesh([4,4,4])
    
inputs = {}
inputs['structure'] = structure
inputs['kpoints'] = kpoints
inputs['parameters'] = parameters
inputs['pseudo'] = get_pseudos_from_structure(structure, 'SSSP_efficiency_v0.95' )
inputs['_options'] = {'max_wallclock_seconds':30*60, 
                      'resources':{
                                  "num_machines": 1,
                                  "num_mpiprocs_per_machine":64},
                       'custom_scheduler_commands':u"#PBS -A Pra15_3963",
                                  }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='SCF calculation.')
    parser.add_argument('--code', type=str, dest='codename', required=True,
                        help='The pw codename to use')
    #parser.add_argument('--pseudo', type=str, dest='pseudo', required=True,
    #                    help='The pesudo  to use')
    #parser.add_argument('--structure', type=int, dest='structure', required=True,
    #                    help='The structure  to use')
    #parser.add_argument('--parent', type=int, dest='parent', required=True,
    #                    help='The parent  to use')
    args = parser.parse_args()
    code = Code.get_from_string(args.codename)
    inputs['code'] = code
    process = PwCalculation.process()
    running = submit(process, **inputs)
    print "Created calculation; with pid={}".format(running.pid)

