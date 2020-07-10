from catkit import Gratoms
from catkit.gen.adsorption import Builder
from catkit.build import molecule
from catkit.gen.molecules import get_3D_positions

from rmgcat_to_sella.adsorbates import Adsorbates
from rmgcat_to_sella.graph_utils import node_test
from rmgcat_to_sella.main import WorkFlow

from ase.io import read, write
from ase.utils.structure_comparator import SymmetryEquivalenceCheck

import numpy as np
import yaml
import os
import shutil
from statistics import mean
from pathlib import Path
import networkx as nx
from spglib import get_symmetry


class TS():
    def __init__(self, facetpath, slab, ts_dir, yamlfile, repeats):
        ''' Initializing

        Parameters:
        ___________
        facetpath : str
            a path to the workflow's main dir
            e.g. 'Cu_111'
        slab : str
            a '.xyz' file name with the optimized slab
            e.g.
            'Cu_111_slab_opt.xyz'
        ts_dir : str
            a path to directory with TSs
            e.g. 'TS_estimate'
        yamlfile : str
            a name of the .yaml file with reaction list
        repeats: tuple
            specify reapeats in (x, y, z) direction,
            eg. (3, 3, 1)

        '''
        self.facetpath = facetpath
        self.slab = slab
        self.ts_dir = ts_dir
        self.yamlfile = yamlfile
        self.repeats = repeats

    def prepare_ts_estimate(self, scfactor, scfactor_surface,
                            rotAngle, pytemplate_xtb, species,
                            scaled1, scaled2):
        ''' Prepare TS estimates for subsequent xTB calculations

        Parameters:
        ___________
        scfator : float
            a scaling factor to scale a bond distance between
            atoms taking part in the reaction
            e.g. 1.4
        scfactor_surface : float
            a scaling factor to scale the target bond distance, i.e.
            the average distance between adsorbed atom and the nearest
            surface atom. Helpful e.g. when H is far away form the surface
            in TS, whereas for minima it is close to the surface
            e.g. 1.0
        rotAngle : float
            an angle (deg) of rotation  of the TS guess adduct on the surface
            e.g. 60
        pytemplate_xtb : python script
            a template file for penalty function minimization job
        species : list(str)
            a list of max 2 species that take part in the reaction
            e.g. ['O', 'H'] or ['CO2', 'H']
        scaled1 : bool
            specify whether use the optional scfactor_surface
            for the species 1 (sp1)
        scaled2 : bool
            specify whether use the optional scfactor_surface
            for the species 2 (sp2)
        '''

        ts_estimate_path = os.path.join(self.facetpath, self.ts_dir)
        if os.path.exists(ts_estimate_path):
            shutil.rmtree(ts_estimate_path)
            os.makedirs(ts_estimate_path)
        else:
            os.makedirs(ts_estimate_path)

        r_name_list, p_name_list, images = TS.prepare_react_list(self)
        rxn_name = TS.get_rxn_name(self)

        TS.TS_placer(self, scfactor, rotAngle,
                     rxn_name, r_name_list, p_name_list, images)

        # TS.filtered_out_equiv_ts_estimate(self, rxn_name)
        TS.set_up_penalty_xtb(self, pytemplate_xtb,
                              species, scaled1, scaled2, scfactor_surface)

    def get_max_rot_angle(self):
        ''' Get the maximum angle of rotation for a given slab that will
        generate all symmetrically distinct TS estimates.

        Returns:
        ________
        max_rot_angle : float
            a maximum angle of rotation of TS adducts on the given slab that
            would generate symmetrically dostinct configurations
            i.e. once the TS adduct is rotated by bigger angle than
            max_rot_angle, some of the generated structures will be
            symetrically equivalent to the others

        '''
        # convert slab to ASE's Atom object
        slab = read(self.slab)
        # get all symmetry operations
        symm = get_symmetry(slab)
        # count rotations operations
        nrot = len(symm['rotations'])
        # the angle of rotation is 360 devided by nrot/2 as thera are equal
        # number of symmetry operations around the z axis
        # (e.g. for Cu_111 therea are 6 z and 6 -z operations)
        max_rot_angle = 360/(nrot/2)
        return max_rot_angle

    def prepare_react_list(self):
        '''Convert yaml file to more useful format

        Returns
        _______
        r_name_list : list(str)
            a list with all reactants for the given reaction
        p_name_list : list(str)
            a list with all products for the given reaction
        images : list(Gratoms)
            a list of CatKit's Gratom object (both reactants and products)

        '''
        with open(self.yamlfile, 'r') as f:
            yamltxt = f.read()
        reactions = yaml.safe_load(yamltxt)
        speciesInd = []
        bonds = []
        unique_species = []
        unique_bonds = []
        images = []

        put_adsorbates = Adsorbates(
            self.facetpath, self.slab, self.repeats, self.yamlfile)

        for rxn in reactions:
            # transforming reactions data to gratom objects
            reactants, rbonds = put_adsorbates.rmgcat_to_gratoms(
                rxn['reactant'].split('\n'))
            products, pbonds = put_adsorbates.rmgcat_to_gratoms(
                rxn['product'].split('\n'))
            speciesInd += reactants + products
            bonds += rbonds + pbonds

        # TODO :to be debbuged later
        # for rp, uniquelist in ((reactants, r_unique), (products, p_unique)):
        #     for species in rp:
        #         symbols = str(species.symbols)
        #         symbols_list.append(symbols)
        #         speciesdir = os.path.join(
        #             self.facetpath, 'minima_unique', symbols)
        #         if symbols not in species_unique:
        #             species_unique[symbols] = get_all_species(
        #                 self, speciesdir)
        #         uniquelist.append(species_unique[symbols])

        # check if any products are the same as any reactants
        for species1, bond in zip(speciesInd, bonds):
            for species2 in unique_species:
                if nx.is_isomorphic(species1.graph, species2.graph, node_test):
                    break
            else:
                images.append(get_3D_positions(species1))
                unique_species.append(species1)
                unique_bonds.append(bond)

        r_name_list = [str(species.symbols) for species in reactants]
        p_name_list = [str(species.symbols) for species in products]

        # It is easier to estimate TS starting from reactant/product with
        # smaller numnber of species
        # if len(r_name_list) < len(p_name_list):
        #     print('Reactant structure will be used to estimate TS')
        #     rpDir = 'reactants'
        # else:
        #     print('Products will be used to estimate TS')
        #     rpDir = 'products'
        return r_name_list, p_name_list, images

    def get_rxn_name(self):
        ''' Get the reaction name

        Returns
        _______
        The name of the reaction in the following format:
        OH_H+O
        '''
        r_name_list, p_name_list, _ = TS.prepare_react_list(self)

        r_name = '+'.join([species for species in r_name_list])
        p_name = '+'.join([species for species in p_name_list])

        rxn_name = r_name + '_' + p_name
        return rxn_name

    def TS_placer(self, scfactor, rotAngle, rxn_name,
                  r_name_list, p_name_list, images):
        ''' Place adsorbates on the surface to estimate TS

        Parameters
        __________
        scfator : float
            a scaling factor to scale a bond distance between
            atoms taking part in the reaction
            e.g. 1.4
        rotAngle : float
            an angle (deg) of rotation  of the TS guess adduct on the surface
            e.g. 60
        rxn_name : str
            a reaction name
            e.g OH_O+H
        r_name_list : list(str)
            a list with all reactants for the given reaction
        p_name_list : list(str)
            a list with all products for the given reaction
        images : list(Gratoms)
            a list of CatKit's Gratom object (both reactants and products)

        '''
        ts_estimate_path = os.path.join(self.facetpath, self.ts_dir)
        slab = read(self.slab)
        slab.pbc = (True, True, False)
        # ADSORBATES
        # This part here is a bit hard coded, especially when dealing with
        # reactants with >= 3 atoms. The code works for couple of species
        # included in if else statement below. Probably will fail for other
        # species. This is becouse ase.build.molecule function numbers atoms
        # very diferently depending on the molecule specify.
        # To be resolved somehow.

        atom1 = 0  # atom1 should always have index 0, i.e. the first atom
        atom2 = 1
        # well, here is the problem becouse ase.build.molecule counts atoms
        # differently than my input in the yaml file. Probably the problem with
        # the way yamlfile is converted to species - to be resolved
        if len(r_name_list) <= len(p_name_list):
            TS_candidate = molecule(r_name_list[0])[0]
            # reactName = p_name
        else:
            # TS_candidate = molecule(p_name_list[0])[0]
            # images[2] keeps info about product. It's a Gratom object.
            # Cannot use catkit's molecule method becouse it generates
            # gemetry based on wierd order chemical formula string. Sometimes
            # it works to use molecule method but in general it is better to
            # use get_3D_positions() as it converts yaml info into 3d
            # position. In images I keep the oryginal order of elements with
            # connectivity info. In TS_candidate.get_chemical_formula()
            # elements are sorted and grouped
            TS_candidate = images[2]
            # reactName = r_name

        ''' Different cases '''
        if TS_candidate.get_chemical_formula() == 'CHO':
            atom2 = 2
            bondedThrough = [0]
        elif TS_candidate.get_chemical_formula() == 'COH':
            atom2 = 2
            bondedThrough = [0]
        elif TS_candidate.get_chemical_formula() == 'CHO2':
            # atom1 = 0
            # atom2 = 1
            bondedThrough = [2]  # connect through oxygen

        elif TS_candidate.get_chemical_formula() == 'C2H5O2':
            atom0 = 0
            atom1 = 1
            atom2 = 5
            bondedThrough = [6]  # connect through oxygen
        else:
            # atom2 = 1
            bondedThrough = [0]

        bondlen = TS_candidate.get_distance(atom1, atom2)
        # bondlen = TS_candidate.get_distance(atom1, atom2)
        # angle = TS_candidate.get_angle(0, 1, 5)

        # TS_candidate.set_distance(atom1, atom2, blen * scfactor, fix=0)

        '''Final ridgid rotations to orientate the TS_candidate on the surface'''
        if len(TS_candidate.get_tags()) < 3:
            TS_candidate.rotate(90, 'y')
            TS_candidate.set_distance(
                atom1, atom2, bondlen * scfactor, fix=0)
        elif len(TS_candidate.get_tags()) == 3:
            TS_candidate.rotate(90, 'z')
            TS_candidate.set_distance(
                atom1, atom2, bondlen * scfactor, fix=0)
        # else:
        elif TS_candidate.get_chemical_formula() == 'C2H5O2':
            # TS_candidate.rotate(60, 'y')
            TS_candidate.rotate(90, 'z')
            ''' Should work for H2CO*OCH3, i.e. COH3+HCOH '''
            TS_candidate.set_angle(atom2, atom1, atom0, -45,
                                   indices=[0, 1, 2, 3, 4], add=True)
            TS_candidate.set_distance(
                atom1, atom2, bondlen * scfactor, fix=1, indices=[0, 1, 2, 3, 4])
            # indices=[0, 1, 2, 3, 4]
        elif TS_candidate.get_chemical_formula() == 'CHO2':
            TS_candidate.rotate(90, 'z')
            TS_candidate.set_distance(
                atom1, atom2, bondlen * scfactor, fix=0)
        # double check this
        put_adsorbates = Adsorbates(
            self.facetpath, self.slab, self.repeats, self.yamlfile)
        slabedges, tags = put_adsorbates.get_edges(self)
        # double check this
        grslab = Gratoms(numbers=slab.numbers,
                         positions=slab.positions,
                         cell=slab.cell,
                         pbc=slab.pbc,
                         edges=slabedges)
        grslab.arrays['surface_atoms'] = tags

        # building adsorbtion structures
        ads_builder = Builder(grslab)

        max_angle = int(TS.get_max_rot_angle(self))

        angle = 0
        count = 0
        step_size = 5
        while angle <= max_angle:
            structs = ads_builder.add_adsorbate(
                TS_candidate, bondedThrough, -1, auto_construct=False)
            # change to True will make bondedThrough work.
            # Now it uses TS_candidate,rotate...
            # to generate adsorbed strucutres
            big_slab = slab * self.repeats
            nslab = len(slab)

            for i, struc in enumerate(structs):
                big_slab_ads = big_slab + struc[nslab:]
                write(os.path.join(ts_estimate_path, '{}'.format(
                    str(i + len(structs) * count).zfill(3)) + '_' + rxn_name + '.xyz'), big_slab_ads)

            TS_candidate.rotate(step_size, 'z')
            angle += step_size
            count += 1

        ''' Old version
        # # building adsorbtion structures
        # ads_builder = Builder(grslab)

        # possibleRotations = (360 / rotAngle) - 1
        # count = 0

        # while count <= possibleRotations:
        #     structs = ads_builder.add_adsorbate(
        #         TS_candidate, bondedThrough, -1, auto_construct=False)
        #     # change to True will make bondedThrough work.
        #     # Now it uses TS_candidate,rotate...
        #     # to generate adsorbed strucutres
        #     big_slab = slab * self.repeats
        #     nslab = len(slab)

        #     for i, struc in enumerate(structs):
        #         big_slab_ads = big_slab + struc[nslab:]
        #         write(os.path.join(ts_estimate_path, '{}'.format(
        #             str(i + len(structs) * count).zfill(3)) + '_' + rxn_name + '.xyz'), big_slab_ads)

        #     TS_candidate.rotate(rotAngle, 'z')
        #     count += 1
        '''

    def filtered_out_equiv_ts_estimate(self, rxn_name):
        '''Filtering out symmetry equivalent sites

        Parameters
        __________
        rxn_name : str
            a reaction name
            e.g. OH_O+H
        '''
        ts_estimate_path = os.path.join(self.facetpath, self.ts_dir)
        filtered_equivalen_sites = checkSymmBeforeXTB(ts_estimate_path)
        for eqsites in filtered_equivalen_sites:
            try:
                fileToRemove = os.path.join(
                    ts_estimate_path, eqsites + '_' + rxn_name + '.xyz')
                os.remove(fileToRemove)
            except OSError:
                print("Error while deleting file : ", fileToRemove)

        for prefix, noneqsites in enumerate(sorted(os.listdir(ts_estimate_path))):
            prefix = str(prefix).zfill(3)
            oldfname = os.path.join(ts_estimate_path, noneqsites)
            newfname = os.path.join(
                ts_estimate_path, prefix + noneqsites[3:])
            os.rename(oldfname, newfname)

    def set_up_penalty_xtb(self, pytemplate, species_list,
                           scaled1, scaled2, scfactor_surface):
        ''' Prepare calculations of the penalty function

        Parameters
        __________

        pytemplate : python script
            a template for the penalty function calculations
        species_list : list(str)
            a list of max 2 species that take part in the reaction
            e.g. ['O', 'H'] or ['CO2', 'H']
        scaled1 : bool
            specify whether use the optional scfactor_surface
            for the species 1 (sp1)
        scaled2 : bool
            specify whether use the optional scfactor_surface
            for the species 2 (sp2)
        scfactor_surface : float
            a scaling factor to scale the target bond distance, i.e.
            the average distance between adsorbed atom and the nearest
            surface atom. Helpful e.g. when H is far away form the surface
            in TS, whereas for minima it is close to the surface
            e.g. 1.0

        # TODO: Species3 is/should be optional '''
        ts_estimate_path = os.path.join(self.facetpath, self.ts_dir)

        # print(species3)
        path_to_minima = os.path.join(self.facetpath, 'minima')
        print(path_to_minima)
        avDist1 = TS.get_av_dist(self,
                                 path_to_minima, species_list[0],
                                 scfactor_surface, scaled1)
        avDist2 = TS.get_av_dist(self,
                                 path_to_minima, species_list[1],
                                 scfactor_surface, scaled2)
        '''the code belowe does not work in the loop, probably two differet path_to_minima variable needed to accouut for the possible scenario that one species was already calculated (other set of calculations - different reactions, whereas the second in calculated here for the first time) '''
        # checkMinimaPath = os.path.dirname(os.getcwd())
        # spList = [species1, species2]

        # for species in spList:
        #     is_it_calculated = CheckIfMinimasAlreadyCalculated(
        #         checkMinimaPath, species)
        #     if is_it_calculated is False:
        #         fPath = os.path.split(path)
        #         path_to_minima = os.path.join(fPath[0], 'minima')
        #     else:
        #         path_to_minima = is_it_calculated[1]

        # species_list = [species1, species2, species3]

        with open(pytemplate, 'r') as f:
            pytemplate = f.read()

        for geom in sorted(os.listdir(ts_estimate_path)):
            if geom.endswith('.xyz'):
                bonds = []
                geomPath = os.path.join(ts_estimate_path, geom)

                for species in species_list:
                    sp_index = get_index_adatom(species, geomPath)
                    Cu_index = get_index_surface_atom(species, geomPath)
                    # print(sp_index, Cu_index)
                    bonds.append((sp_index, Cu_index))

                # sp1_index = get_index_adatom(species1, geomPath)
                # sp2_index = get_index_adatom(species2, geomPath)
                # # sp3_index = get_index_adatom(species3, geomPath)
                # Cu_index1 = get_index_surface_atom(species1, geomPath)
                # Cu_index2 = get_index_surface_atom(species2, geomPath)
                # # Cu_index3 = get_index_surface_atom(species3, geomPath)

                prefix = geom.split('_')
                calcDir = os.path.join(ts_estimate_path, prefix[0])
                os.makedirs(calcDir, exist_ok=True)

                geomName = geom[:-4]

                # List of bonds we want O-Cu; H-Cu
                # bonds = ((sp1_index, Cu_index1),
                #          (sp2_index, Cu_index2))
                # print(type(bonds))
                avDists = (avDist1, avDist2)
                trajPath = os.path.join(geom[:-4] + '.traj')
                init_png = os.path.join(calcDir, geom[:-4] + '_initial.png')
                write(init_png, read(geomPath))
                fname = os.path.join(calcDir, geom[:-4] + '.py')
                with open(fname, 'w') as f:
                    f.write(pytemplate.format(geom=geom, bonds=bonds,
                                              avDists=avDists, trajPath=trajPath,
                                              repeats=self.repeats, prefix=prefix[0],
                                              geomName=geomName, slabopt=self.slab))
                f.close()
                shutil.move(geomPath, calcDir)
        f.close()

        try:
            rmpath = os.path.join(ts_estimate_path, 'initial_png')
            shutil.rmtree(rmpath)
        except FileNotFoundError:
            pass
            # print('No files to delete')

    def get_av_dist(self, path_to_minima, species, scfactor_surface,
                    scaled=False):
        ''' Get the average bond distance between adsorbate atom and
        the nearest surface atom for all symmetrically distinct minima
                    
        Parameters:
        ___________
        path_to_minima : str
            a path to minima
            e.g. 'Cu_111/minima'
        species : str
            a species symbol
            e.g. 'H' or 'CO'
        scfactor_surface : float
            a scaling factor to scale the target bond distance, i.e.
            the average distance between adsorbed atom and the nearest
            surface atom. Helpful e.g. when H is far away form the surface
            in TS, whereas for minima it is close to the surface
            e.g. 1.0
        scaled : bool
            specify whether to use the optional scfactor_surface
            for the given species
            default = False
        
        Returns:
        ________
        av_dist : float
            an average bond distance between the given species and the nearest
            surface atom for all symmetrically dictinct minima

        '''
        surface_atoms_indices = []
        adsorbate_atoms_indices = []
        all_dists = []
        TS.get_xyz_from_traj(self, path_to_minima, species)
        species_path = os.path.join(path_to_minima, species)
        # treat the special cases
        if species in ['CH3O', 'CH2O']:
            species = 'O'
        if len(species) > 1:
            species = species[:1]
        # get unique minima indices
        unique_minima_indices = TS.get_unique_minima_indicies_after_opt(self,
                                                                     path_to_minima,
                                                                     species)
        # go through all indices of *final.xyz file
        # e.g. 00_final.xyz, 01_final.xyz
        for index in unique_minima_indices:
            paths_to_uniq_minima_final_xyz = Path(
                species_path).glob('{}*final.xyz'.format(index))
            for unique_minimum_final_xyz in paths_to_uniq_minima_final_xyz:
                unique_minimum_atom = read(unique_minimum_final_xyz)
                # open the *final.xyz file as xyz_file
                with open(unique_minimum_final_xyz, 'r') as f:
                    xyz_file = f.readlines()
                    # find all Cu atoms and adsorbate atoms
                    for num, line in enumerate(xyz_file):
                        # For Cu(111) we can put ' 1 ' instead of 'Cu ' to
                        # limit calculations to surface Cu atoms only.
                        # For Cu(211) ASE is not generating tags like this,
                        # so full calculation have to be performed, i.e. all
                        # surface atoms
                        if 'Cu ' in line:
                            surface_atoms_indices.append(num - 2)
                        elif species in line and not 'Cu' in line:
                            # We need to have additional statement
                            # 'not 'Cu' in line'
                            # because for C it does not work without it'''
                            adsorbate_atoms_indices.append(num - 2)
                f.close()
                # find the shortest distance between the adsorbate
                # and the surface
                dist = float(min(unique_minimum_atom.get_distances(
                    adsorbate_atoms_indices[0], surface_atoms_indices)))
            all_dists.append(dist)
        # apply scaling factor if required
        if scaled:
            av_dist = mean(all_dists) * scfactor_surface
        else:
            av_dist = mean(all_dists)
        return av_dist

    def get_xyz_from_traj(self, path_to_minima, species):
        ''' Convert all ASE's traj files to .xyz files for a given species
        
        Parameters:
        ___________
        path_to_minima : str
            a path to minima
            e.g. 'Cu_111/minima'
        species : str
            a species symbol
            e.g. 'H' or 'CO'

        '''
        species_path = os.path.join(path_to_minima, species)
        for traj in sorted(os.listdir(species_path), key=str):
            if traj.endswith('.traj'):
                src_traj_path = os.path.join(species_path, traj)
                des_traj_path = os.path.join(
                    species_path, traj[:-5] + '_final.xyz')
                write(des_traj_path, read(src_traj_path))

    def get_unique_minima_indicies_after_opt(self, path_to_minima, species):
        ''' Get the indicies of the symmetrically distinct minima
        for a given species
        
        Parameters:
        ___________
        path_to_minima : str
            a path to minima
            e.g. 'Cu_111/minima'
        species : str
            a species symbol
            e.g. 'H' or 'CO'

        Returns:
        ________

        unique_minima_indices : list(str)
            a list with indecies of all unique minima for a given species
            e.g. ['01', '02', '04']
        
        '''
        good_minima = []
        result_list = []
        unique_minima_indices = []
        path_to_species = os.path.join(path_to_minima, species)
        trajlist = sorted(Path(path_to_species).glob('*final.xyz'), key=str)
        for traj in trajlist:
            minima = read(traj)
            minima.pbc = True
            comparator = SymmetryEquivalenceCheck()
            result = comparator.compare(minima, good_minima)
            result_list.append(result)
            if result is False:
                good_minima.append(minima)
        for prefix, result in enumerate(result_list):
            if result is False:
                unique_minima_indices.append(str(prefix).zfill(2))
        return unique_minima_indices

    def copy_minimas_prev_calculated(self, current_dir, species_list,
                                     minima_dir):
        ''' If minimas have been already calculated in different set of
         reactions, they are copied to the current workflow and used instead
         of calculating it again

        Parameters
        __________

        current_dir : str
            a path to the current directory
            e.g './Cu_111'
        species_list : list(str)
            a list of max 2 species that take part in the reaction
            e.g. ['O', 'H'] or ['CO2', 'H']
        minima_dir : str
            a path to minima directory
            e.g. Cu_111/minima

        '''
        for species in species_list:
            is_it_calculated = WorkFlow().check_if_minima_already_calculated(
                current_dir, species, self.facetpath)
            if is_it_calculated is False:
                pass
            else:
                try:
                    copyPath = is_it_calculated[1]
                    dstDir = os.path.join(minima_dir, species)
                    shutil.copytree(copyPath, dstDir)
                    dstDir = os.path.split(dstDir)[0]
                except FileExistsError:
                    dstDir = os.path.split(dstDir)[0]
                    print('All required files already exist.')
                    pass
                # is_it_calculated[1] is None when is_it_calculated[0] == False
                except IndexError:
                    pass

    def create_unique_TS(self):
        ''' Create unique TS files for calculations '''
        gd_ads_index = checkSymm(os.path.join(self.facetpath, self.ts_dir))
        for i, index in enumerate(gd_ads_index):
            uniqueTSdir = os.path.join(
                self.facetpath, self.ts_dir + '_unique', str(i).zfill(2))
            if os.path.isdir(uniqueTSdir):
                shutil.rmtree(uniqueTSdir)
                os.makedirs(uniqueTSdir, exist_ok=True)
            else:
                os.makedirs(uniqueTSdir, exist_ok=True)
            gpath = os.path.join(self.facetpath, self.ts_dir)
            for geom in os.listdir(gpath):
                geomDir = os.path.join(gpath, geom)
                if os.path.isdir(geomDir):
                    for traj in sorted(os.listdir(geomDir)):
                        if traj.startswith(gd_ads_index[i]) and traj.endswith('.traj'):
                            srcFile = os.path.join(geomDir, traj)
                            destFile = os.path.join(
                                uniqueTSdir, traj[:-5] + '_ts')
                            write(destFile + '.xyz', read(srcFile))
                            write(destFile + '.png', read(srcFile))
            #         shutil.copy2(os.path.join(path, geom), uniqueTSdir)
            for ts in os.listdir(uniqueTSdir):
                # if neb.endswith('.xyz'):
                TS_xyz_Dir = os.path.join(uniqueTSdir, ts)
                newTS_xyz_Dir = os.path.join(
                    uniqueTSdir, str(i).zfill(2) + ts[3:])
                # NEB_png_Dir = os.path.join(uniqueTSdir, str(
                #     i).zfill(3) + neb[2:][:-4] + '.png')
                os.rename(TS_xyz_Dir, newTS_xyz_Dir)
                # write(NEB_png_Dir, read(newNEB_xyz_Dir))

    def create_TS_unique_job_files(self, pytemplate,
                                   pseudopotentials, pseudo_dir):
        ''' Create job submission files'''
        unique_TS_candidate_path = os.path.join(
            self.facetpath, self.ts_dir + '_unique')
        with open(pytemplate, 'r') as f:
            pytemplate = f.read()

        for struc in os.listdir(unique_TS_candidate_path):
            TSdir = os.path.join(unique_TS_candidate_path, struc)
            if os.path.isdir(TSdir):
                TSpath = os.path.join(unique_TS_candidate_path, struc)
                for fl in os.listdir(TSpath):
                    if fl.endswith('.xyz'):
                        fname = os.path.join(
                            unique_TS_candidate_path, fl[:-4] + '.py')
                        with open(fname, 'w') as f:
                            f.write(pytemplate.format(TS=os.path.join(
                                struc, fl), rxn=fl[3:-7], prefix=fl[:2],
                                pseudopotentials=pseudopotentials,
                                pseudo_dir=pseudo_dir))
                        f.close()
        f.close()


# def gen_xyz_from_traj(avDistPath, species):
#     # if species == 'C':
#     #     species_path = os.path.join(avDistPath, species + 'O')
#     # else:
#     species_path = os.path.join(avDistPath, species)
#     for traj in sorted(os.listdir(species_path), key=str):
#         if traj.endswith('.traj'):
#             srcTrajPath = os.path.join(species_path, traj)
#             desTrajPath = os.path.join(species_path, traj[:-5] + '_final.xyz')
#             write(desTrajPath, read(srcTrajPath))


# def get_unique_minima_index_after_opt(facetpath, minima_dir):
#     good_minima = []
#     result_list = []
#     unique_minima_index = []
#     gpath = os.path.join(facetpath, minima_dir)
#     trajlist = sorted(Path(gpath).glob('*final.xyz'), key=str)
#     for traj in trajlist:
#         minima = read(traj)
#         minima.pbc = True
#         comparator = SymmetryEquivalenceCheck()
#         result = comparator.compare(minima, good_minima)
#         result_list.append(result)
#         if result is False:
#             good_minima.append(minima)
#     for num, res in enumerate(result_list):
#         if res is False:
#             unique_minima_index.append(str(num).zfill(2))
#     return unique_minima_index


# def get_av_dist(avDistPath, species, scfactor_surface, scaled=False):
#     surface_atoms_indices = []
#     adsorbate_atoms_indices = []
#     all_dists = []
#     gen_xyz_from_traj(avDistPath, species)
#     species_path = os.path.join(avDistPath, species)
#     if species in ['CH3O', 'CH2O']:
#         species = 'O'
#     if len(species) > 1:
#         species = species[:1]
#     # get unique minima indices
#     unique_minima_indices = get_unique_minima_index_after_opt(
#         'Cu_111', os.path.join('minima', species))
#     # go through all indices of *final.xyz file
#     # e.g. 00_final.xyz, 01_final.xyz
#     for index in unique_minima_indices:
#         paths_to_uniq_minima_final_xyz = Path(
#             species_path).glob('{}*final.xyz'.format(index))
#         for unique_minimum_final_xyz in paths_to_uniq_minima_final_xyz:
#             unique_minimum_atom = read(unique_minimum_final_xyz)
#             # open the *final.xyz file as xyz_file
#             with open(unique_minimum_final_xyz, 'r') as f:
#                 xyz_file = f.readlines()
#                 # find all Cu atoms and adsorbate atoms
#                 for num, line in enumerate(xyz_file):
#                     # For Cu(111) we can put ' 1 ' instead of 'Cu ' to limit
#                     # calculations to surface Cu atoms only. For Cu(211) ase is
#                     # not generating tags like this, so full calculation have
#                     # to be performed, i.e. all surface atoms'''
#                     if 'Cu ' in line:
#                         surface_atoms_indices.append(num - 2)
#                     elif species in line and not 'Cu' in line:
#                         # We need to have additional statement
#                         # 'not 'Cu' in line'
#                         # because for C it does not work without it'''
#                         adsorbate_atoms_indices.append(num - 2)
#             f.close()
#             # find the shortest distance between the adsorbate and the surface
#             dist = float(min(unique_minimum_atom.get_distances(
#                 adsorbate_atoms_indices[0], surface_atoms_indices)))
#         all_dists.append(dist)
#     # apply scaling factor if required
#     if scaled:
#         av_dist = mean(all_dists) * scfactor_surface
#     else:
#         av_dist = mean(all_dists)
#     return av_dist


def get_bond_dist(ads_atom, geom):
    ''' Specify adsorbate atom symbol and bond distance with the closest surface metal atom will be calculated '''
    surface_atom = []
    adsorbate_atom = []
    struc = read(geom)
    if len(ads_atom) > 1:
        ads_atom = ads_atom[:-1]
    # if ads_atom == 'C':
    #     ads_atom == 'CO'
    with open(geom, 'r') as f:
        xyz_geom_file = f.readlines()
        for num, line in enumerate(xyz_geom_file):
            if ' 1 ' in line:
                # reading each line and adding only the one with tags = 1
                # (surface atoms). It is necessary to subtract 2 as indices in
                # atom object starts with 0 and we also have to take into
                # account that the first line in xyz file contains non xyz
                # information
                surface_atom.append(num - 2)
            elif ads_atom in line:
                if not "Cu" in line:
                    adsorbate_atom.append(num - 2)
    f.close()

    if len(adsorbate_atom) > 1:
        dist_Cu_adsorbate = min(struc.get_distances(
            adsorbate_atom[0], surface_atom))
        return dist_Cu_adsorbate
    else:
        dist_Cu_adsorbate = min(
            struc.get_distances(adsorbate_atom, surface_atom))
        return dist_Cu_adsorbate


def get_index_adatom(ads_atom, geom):
    ''' Specify adsorbate atom symbol and its index will be returned '''
    adsorbate_atom = []
    if len(ads_atom) > 1:
        ads_atom = ads_atom[:1]
    with open(geom, 'r') as f:
        xyz_geom_file = f.readlines()
        for num, line in enumerate(xyz_geom_file):
            if ads_atom in line:
                if not 'Cu' in line:
                    adsorbate_atom.append(num - 2)
    f.close()
    return adsorbate_atom[0]


def get_index_surface_atom(ads_atom, geom):
    ''' Specify adsorbate atom symbol and index of the neares metal atom will be returned '''
    surface_atom = []
    adsorbate_atom = []
    if len(ads_atom) > 1:
        ads_atom = ads_atom[:1]
    # print(ads_atom)
    struc = read(geom)
    with open(geom, 'r') as f:
        xyz_geom_file = f.readlines()
        for num, line in enumerate(xyz_geom_file):
            if 'Cu ' in line:
                surface_atom.append(num - 2)
            elif ads_atom in line:
                if not 'Cu' in line:
                    adsorbate_atom.append(num - 2)
    f.close()

    all_dist_surface_adsorbate = struc.get_distances(
        adsorbate_atom[0], surface_atom)
    min_dist_surface_adsorbate = min(
        struc.get_distances(adsorbate_atom[0], surface_atom))
    # get index of the surface atom for which distance to adsorbate is the
    # lowest
    index = np.where(all_dist_surface_adsorbate == min_dist_surface_adsorbate)

    return surface_atom[index[0][0]]


def checkSymm(path):
    good_adsorbate = []
    result_list = []
    geomlist = sorted(Path(path).glob('**/*.traj'))
    for geom in geomlist:
        adsorbed = read(geom)
        adsorbed.pbc = True
        comparator = SymmetryEquivalenceCheck()
        result = comparator.compare(adsorbed, good_adsorbate)
        result_list.append(result)
        if result is False:
            good_adsorbate.append(adsorbed)
    unique_index = []
    for num, res in enumerate(result_list):
        if res is False:
            unique_index.append(str(num).zfill(3))
    return unique_index


''' The code below is rather useless - double check it '''


def checkSymmBeforeXTB(path):
    good_adsorbate = []
    result_list = []
    geomlist = sorted(Path(path).glob('*.xyz'))
    for geom in geomlist:
        adsorbed = read(geom)
        adsorbed.pbc = True
        comparator = SymmetryEquivalenceCheck()
        result = comparator.compare(adsorbed, good_adsorbate)
        result_list.append(result)
        if result is False:
            good_adsorbate.append(adsorbed)
    notunique_index = []
    for num, res in enumerate(result_list):
        if res is True:
            ''' Better to have all symmetry equivalent site here in a list. The workflow will remove them in getTSestimate function keeping all symmetry distinct sites '''
            notunique_index.append(str(num).zfill(3))
    return notunique_index


def create_all_TS(facetpath):
    all_TS_candidate_path = os.path.join(facetpath, 'TS_candidate')
    os.makedirs(all_TS_candidate_path, exist_ok=True)
    gpath = os.path.join(facetpath, 'TS_estimate')
    for geom in os.listdir(gpath):
        geomDir = os.path.join(gpath, geom)
        if os.path.isdir(geomDir):
            for traj in sorted(os.listdir(geomDir)):
                if traj.endswith('.traj'):
                    # print(str(num/2).zfill(3))
                    xyz_dir_path = os.path.join(
                        all_TS_candidate_path, traj[:3])
                    os.makedirs(xyz_dir_path, exist_ok=True)
                    srcFile = os.path.join(geomDir, traj)
                    destFile = os.path.join(xyz_dir_path, traj[:-5])
                    write(destFile + '.xyz', read(srcFile))
                    write(destFile + '_initial.png', read(srcFile))


def create_all_TS_job_files(facetpath, pytemplate):
    all_TS_candidate_path = os.path.join(facetpath, 'TS_candidate')
    with open(pytemplate, 'r') as f:
        pytemplate = f.read()

    for struc in os.listdir(all_TS_candidate_path):
        TSdir = os.path.join(all_TS_candidate_path, struc)
        if os.path.isdir(TSdir):
            TSpath = os.path.join(all_TS_candidate_path, struc)
            for file in os.listdir(TSpath):
                if file.endswith('.xyz'):
                    fname = os.path.join(
                        all_TS_candidate_path, f'{struc}_{file[:-4][4:]}_relax.py')
                    with open(fname, 'w') as f:
                        f.write(pytemplate.format(TS=os.path.join(
                            struc, file), rxn=file[:-4][4:], prefix=file[:3]))
                    f.close()
    f.close()


# def create_TS_unique_job_files(facetpath, TSdir, pytemplate):
#     unique_TS_candidate_path = os.path.join(facetpath, TSdir + '_unique')
#     with open(pytemplate, 'r') as f:
#         pytemplate = f.read()

#     for struc in os.listdir(unique_TS_candidate_path):
#         TSdir = os.path.join(unique_TS_candidate_path, struc)
#         if os.path.isdir(TSdir):
#             TSpath = os.path.join(unique_TS_candidate_path, struc)
#             for fl in os.listdir(TSpath):
#                 if fl.endswith('.xyz'):
#                     fname = os.path.join(
#                         unique_TS_candidate_path, fl[:-4] + '.py')
#                     with open(fname, 'w') as f:
#                         f.write(pytemplate.format(TS=os.path.join(
#                             struc, fl), rxn=fl[3:-7], prefix=fl[:2]))
#                     f.close()
#     f.close()


# def set_up_penalty_xtb(path, pytemplate, repeats, slab, species_list, scfactor_surface, scaled1, scaled2):
#     '''Species3 is/should be optional '''
#     # print(species3)
#     fPath = os.path.split(path)
#     path_to_minima = os.path.join(fPath[0], 'minima')
#     avDist1 = get_av_dist(path_to_minima, species_list[0], scfactor_surface, scaled1)
#     avDist2 = get_av_dist(path_to_minima, species_list[1], scfactor_surface, scaled2)
#     '''the code belowe does not work in the loop, probably two differet path_to_minima variable needed to accouut for the poscible scenaario that one species was already calculated (other set of calculations - different reactions, whereas the second in calculated here for the first time) '''
#     # checkMinimaPath = os.path.dirname(os.getcwd())
#     # spList = [species1, species2]

#     # for species in spList:
#     #     is_it_calculated = CheckIfMinimasAlreadyCalculated(
#     #         checkMinimaPath, species)
#     #     if is_it_calculated is False:
#     #         fPath = os.path.split(path)
#     #         path_to_minima = os.path.join(fPath[0], 'minima')
#     #     else:
#     #         path_to_minima = is_it_calculated[1]

#     # species_list = [species1, species2, species3]

#     with open(pytemplate, 'r') as f:
#         pytemplate = f.read()

#     for geom in sorted(os.listdir(path)):
#         if geom.endswith('.xyz'):
#             bonds = []
#             geomPath = os.path.join(path, geom)

#             for species in species_list:
#                 sp_index = get_index_adatom(species, geomPath)
#                 Cu_index = get_index_surface_atom(species, geomPath)
#                 # print(sp_index, Cu_index)
#                 bonds.append((sp_index, Cu_index))

#             # sp1_index = get_index_adatom(species1, geomPath)
#             # sp2_index = get_index_adatom(species2, geomPath)
#             # # sp3_index = get_index_adatom(species3, geomPath)
#             # Cu_index1 = get_index_surface_atom(species1, geomPath)
#             # Cu_index2 = get_index_surface_atom(species2, geomPath)
#             # # Cu_index3 = get_index_surface_atom(species3, geomPath)

#             prefix = geom.split('_')
#             calcDir = os.path.join(path, prefix[0])
#             os.makedirs(calcDir, exist_ok=True)

#             geomName = geom[:-4]

#             # List of bonds we want O-Cu; H-Cu
#             # bonds = ((sp1_index, Cu_index1),
#             #          (sp2_index, Cu_index2))
#             # print(type(bonds))
#             avDists = (avDist1, avDist2)
#             trajPath = os.path.join(geom[:-4] + '.traj')
#             init_png = os.path.join(calcDir, geom[:-4] + '_initial.png')
#             write(init_png, read(geomPath))
#             fname = os.path.join(calcDir, geom[:-4] + '.py')
#             with open(fname, 'w') as f:
#                 f.write(pytemplate.format(geom=geom, bonds=bonds,
#                                           avDists=avDists, trajPath=trajPath,
#                                           repeats=repeats, prefix=prefix[0],
#                                           geomName=geomName, slabopt=slab))
#             f.close()
#             shutil.move(geomPath, calcDir)
#     f.close()

#     try:
#         rmpath = os.path.join(path, 'initial_png')
#         shutil.rmtree(rmpath)
#     except FileNotFoundError:
#         pass
#         # print('No files to delete')


# # def create_unique_TS(facetpath, TSdir):
# #     # checkSymmPath = os.path.join(path, 'TS_estimate')

# #     # gd_ads_index = checkSymm(facetpath, TSdir)
# #     # new checksym with globbing
# #     gd_ads_index = checkSymm(os.path.join(facetpath, TSdir))
# #     for i, index in enumerate(gd_ads_index):
# #         uniqueTSdir = os.path.join(
# #             facetpath, TSdir + '_unique', str(i).zfill(2))
# #         if os.path.isdir(uniqueTSdir):
# #             shutil.rmtree(uniqueTSdir)
# #             os.makedirs(uniqueTSdir, exist_ok=True)
# #         else:
# #             os.makedirs(uniqueTSdir, exist_ok=True)
# #         gpath = os.path.join(facetpath, TSdir)
# #         for geom in os.listdir(gpath):
# #             geomDir = os.path.join(gpath, geom)
# #             if os.path.isdir(geomDir):
# #                 for traj in sorted(os.listdir(geomDir)):
# #                     if traj.startswith(gd_ads_index[i]) and traj.endswith('.traj'):
# #                         srcFile = os.path.join(geomDir, traj)
# #                         destFile = os.path.join(uniqueTSdir, traj[:-5] + '_ts')
# #                         write(destFile + '.xyz', read(srcFile))
# #                         write(destFile + '.png', read(srcFile))
# #         #         shutil.copy2(os.path.join(path, geom), uniqueTSdir)
# #         for ts in os.listdir(uniqueTSdir):
# #             # if neb.endswith('.xyz'):
# #             TS_xyz_Dir = os.path.join(uniqueTSdir, ts)
# #             newTS_xyz_Dir = os.path.join(
# #                 uniqueTSdir, str(i).zfill(2) + ts[3:])
# #             # NEB_png_Dir = os.path.join(uniqueTSdir, str(
# #             #     i).zfill(3) + neb[2:][:-4] + '.png')
# #             os.rename(TS_xyz_Dir, newTS_xyz_Dir)
# #             # write(NEB_png_Dir, read(newNEB_xyz_Dir))
