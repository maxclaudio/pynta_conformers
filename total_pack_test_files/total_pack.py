import sys
import os
sys.path.insert(0,os.path.join(os.getcwd(),'ml_pynta/pynta'))
from pynta.main import Pynta
import ast
import json
import time
from ase.visualize import view

start_time = time.time()

# Reading in vasp stuff

#with open('vasp_slab_params.txt') as f:
#    slab_params = f.read()
#with open('vasp_bulk_params.txt') as f:
#    bulk_params = f.read()
#with open('vasp_gas_params.txt') as f:
#    gas_params = f.read()
#vasp_slab_params = ast.literal_eval(slab_params)
#vasp_gas_params = ast.literal_eval(gas_params)
#vasp_bulk_params = ast.literal_eval(bulk_params)


path_to_ML_model = '/global/homes/c/claudio/pynta_conformers/graph.pb'
pyn = Pynta(path=os.getcwd(),
                rxns_file=os.getcwd()+'/rxn.yaml',
                surface_type="fcc111",software="DP", vacuum=10, metal="Ag",socket=False,queue=True,njobs_queue=22,
                repeats=(3,3,4), a=3.8905015, slab_path='/global/homes/c/claudio/pynta_conformers/slab.xyz',label="CHOH-conf-exploration",num_jobs=22,frozen_layers=2,
                software_kwargs={'model':path_to_ML_model},
                software_kwargs_gas={'model':path_to_ML_model},
                lattice_opt_software_kwargs={'model':path_to_ML_model})
#pyn.generate_slab()
#pyn.execute(generate_initial_ad_guesses=True, calculate_adsorbates=False, calculate_transition_states=False, launch=False)
pyn.execute()
pyn.analyze_slab()
pyn.generate_mol_dict()
pyn.generate_initial_adsorbate_guesses(skip_structs=False)

#for struct in pyn.adsorbate_structures:
#    view(struct)
#    exit()

end = time.time()
print("--- %s seconds ---" % (time.time() - start_time))

