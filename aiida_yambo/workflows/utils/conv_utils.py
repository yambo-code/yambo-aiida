# -*- coding: utf-8 -*-
"""Helper functions."""
from __future__ import absolute_import
import numpy as np
from scipy.optimize import curve_fit
from matplotlib import pyplot as plt, style
from collections.abc import Mapping

from aiida.orm import Dict, Str, load_node
from aiida.plugins import CalculationFactory, DataFactory

from aiida_quantumespresso.utils.pseudopotential import validate_and_prepare_pseudos_inputs
from aiida_quantumespresso.workflows.pw.base import PwBaseWorkChain
from aiida_quantumespresso.utils.mapping import prepare_process_inputs

'''
convergence functions for gw(for now) convergences.
'''

def convergence_evaluation(calcs_info):

    gap = np.zeros((calcs_info['steps'],2))
    for i in range(1,calcs_info['steps']+1):
        yambo_calc = load_node(calcs_info['wfl_pk']).caller.called[calcs_info['steps']-i].called[0].called[0]
        gap[i-1,1] = abs((yambo_calc.outputs.array_qp.get_array('Eo')[0]+
                    yambo_calc.outputs.array_qp.get_array('E_minus_Eo')[0])-
                   (yambo_calc.outputs.array_qp.get_array('Eo')[1]+
                    yambo_calc.outputs.array_qp.get_array('E_minus_Eo')[1]))

        gap[i-1,0] = i*calcs_info['delta']

    conv = True

    for i in range(calcs_info['conv_window']):
        if abs(gap[-1,1]-gap[-(i+1),1]) > calcs_info['conv_thr']: #backcheck
            conv = False

    '''
    def func(x, a, b,c):
        return a + b/(x-c) #non +...

    popt, pcov = curve_fit(func, gap[:,0], gap[:,1]) #guess
    #print('parameters are = ',popt)


    if abs(gap[-1,1]-popt[0]) > calcs_info['conv_thr']: #backcheck
            conv = False
    '''
    return conv, gap #,popt

    ## plot con tutti i valori della variabile, anche quelli della finestra precedente
    #fig, ax = plt.subplots()
    #plt.xlabel(var)
    #plt.ylabel('Gap (eV)')
    #plt.title('600 bands')
    #ax.plot([0,20],[r,r])
    #ax.plot(np.linspace(1,20,100),func(np.linspace(1,20,100),*popt),'-',label='Fit')
    #ax.plot(gaps_1[:,0],gaps_1[:,1],'*-',label='calculated')
    #legend = ax.legend(loc='best', shadow=True)

'''
def final_plot(conv_workflow):
'''
