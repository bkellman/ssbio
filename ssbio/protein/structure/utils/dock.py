import os
import re
import sys
import os.path as op
import logging

from ssbio.core.object import Object
import ssbio.utils

from pkg_resources import resource_filename
amb = resource_filename('ssbio.etc', 'vdw_AMBER_parm99.defn')
f1 = resource_filename('ssbio.etc', 'flex.defn')
f2 = resource_filename('ssbio.etc', 'flex_drive.tbl')

log = logging.getLogger(__name__)


class DOCK(Object):

    """Class to prepare a structure file for docking with DOCK6.

    Attributes:

    """

    def __init__(self, structure_id, pdb_file, root_dir=None):
        """Initialize a DOCK6 project.

        Args:

        """
        Object.__init__(self, id=structure_id, description='DOCK6 preparation')
        self._root_dir = None
        self.structure_path = pdb_file

        if root_dir:
            self.root_dir = root_dir
        else:
            self.root_dir = self.structure_dir

    @property
    def root_dir(self):
        """str: Directory where DOCK project folder is located"""
        return self._root_dir

    @root_dir.setter
    def root_dir(self, path):
        if not path:
            raise ValueError('No path specified')

        if not op.exists(path):
            raise ValueError('{}: folder does not exist'.format(path))

        if self._root_dir:
            log.debug('Changing root directory of DOCK project for "{}" from {} to {}'.format(self.id, self.root_dir, path))

            if not op.exists(op.join(path, self.id)):
                raise IOError('DOCK project "{}" does not exist in folder {}'.format(self.id, path))

        self._root_dir = path

        for d in [self.dock_dir]:
            ssbio.utils.make_dir(d)

    @property
    def dock_dir(self):
        """str: DOCK folder"""
        if self.root_dir:
            return op.join(self.root_dir, self.id + '_DOCK')
        else:
            log.warning('Root directory not set')
            return None

    @property
    def structure_dir(self):
        if not self._structure_dir:
            raise OSError('No structure folder set')
        return self._structure_dir

    @structure_dir.setter
    def structure_dir(self, path):
        if path and not op.exists(path):
            raise OSError('{}: folder does not exist'.format(path))

        self._structure_dir = path

    @property
    def structure_path(self):
        if not self.structure_file:
            raise OSError('Metadata file not loaded')

        path = op.join(self.structure_dir, self.structure_file)
        if not op.exists(path):
            raise OSError('{}: file does not exist'.format(path))
        return path

    @structure_path.setter
    def structure_path(self, path):
        """Provide pointers to the paths of the structure file

        Args:
            path: Path to structure file

        """
        if not path:
            self.structure_dir = None
            self.structure_file = None

        else:
            if not op.exists(path):
                raise OSError('{}: file does not exist!'.format(path))

            if not op.dirname(path):
                self.structure_dir = '.'
            else:
                self.structure_dir = op.dirname(path)
            self.structure_file = op.basename(path)

    def dockprep(self, force_rerun=False):
        """Prepare a PDB file for docking by first converting it to mol2 format

        Returns:
            str: Path to prepped structure file

        """
        prep_mol2 = op.join(self.dock_dir, '{}_prep.mol2'.format(self.id))
        prep_py = op.join(self.dock_dir, "prep.py")

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=prep_mol2):
            with open(prep_py, "w") as f:
                f.write('import chimera\n')
                f.write('from DockPrep import prep\n')
                f.write('models = chimera.openModels.list(modelTypes=[chimera.Molecule])\n')
                f.write('prep(models)\n')
                f.write('from WriteMol2 import writeMol2\n')
                f.write('writeMol2(models, "{}")\n'.format(prep_mol2))

            cmd = 'chimera --nogui {} {}'.format(self.structure_path, prep_py)
            os.system(cmd)
            os.remove(prep_py)
            os.remove('{}c'.format(prep_py))

        return prep_mol2

    def protein_only_and_noH(self, prep_mol2, keep_ligands=None, force_rerun=False):
        """Isolate the receptor by stripping everything except protein and specified ligands

        Args:
            prep_mol2 (str): Path to mol2 file
            keep_ligands (str, list): Ligand(s) to keep in PDB file

        Returns:
            str: Path to prepped structure file

        """
        receptor_mol2 = op.join(self.dock_dir, '{}_receptor.mol2'.format(self.id))
        receptor_noh = op.join(self.dock_dir, '{}_receptor_noH.pdb'.format(self.id))

        prly_com = op.join(self.dock_dir, "prly.com")

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=receptor_noh):
            with open(prly_com, "w") as f:
                f.write('open {}\n'.format(prep_mol2))

                keep_str = 'delete ~protein'
                if keep_ligands:
                    keep_ligands = ssbio.utils.force_list(keep_ligands)
                    for res in keep_ligands:
                        keep_str += ' & ~:{} '.format(res)
                keep_str = keep_str.strip() + '\n'
                f.write(keep_str)

                f.write('write format mol2 0 {}\n'.format(receptor_mol2))
                f.write('delete element.H\n')
                f.write('write format pdb 0 {}\n'.format(receptor_noh))

            cmd = 'chimera --nogui {}'.format(prly_com)
            os.system(cmd)
            os.remove(prly_com)

        return receptor_mol2, receptor_noh

    def dms_maker(self, receptor_noh, force_rerun=False):
        """Create surface representation (dms file) of receptor

        Args:
            receptor_noh:

        Returns:

        """
        dms = op.join(self.dock_dir, '{}_receptor.dms'.format(self.id))

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=dms):
            cmd = 'dms {} -n -w 1.4 -o {}'.format(receptor_noh, dms)
            os.system(cmd)

        return dms

    def sphgen(self, dms, force_rerun=False):
        """Create sphere representation (sph file) of receptor from the surface representation

        Args:
            dms:
            prefix:

        Returns:

        """
        sph = op.join(self.dock_dir, '{}_receptor.sph'.format(self.id))
        insph = op.join(self.dock_dir, 'INSPH')

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=sph):
            with open(insph, "w") as f:
                f.write("{}\n".format(dms))
                f.write("R\n")
                f.write("X\n")
                f.write("0.0\n")
                f.write("4.0\n")
                f.write("1.4\n")
                f.write("{}\n".format(sph))

            os.chdir(self.dock_dir)
            cmd = "sphgen_cpp"
            os.system(cmd)
            os.remove(insph)

        return sph

    def binding_site_mol2(self, receptor_noH, residues, force_rerun=False):
        """Create mol2 of only binding site residues from the receptor

        This function will take in a .pdb file (preferably the _receptor_noH.pdb file)
        and a string of residues (ex: 144,170,199) and delete all other residues in the
        .pdb file. It then saves the coordinates of the selected residues as a .mol2 file.
        This is necessary for Chimera to select spheres within the radius of the binding
        site.

        Args:
            receptor_noH:
            residues:

        Returns:

        """

        prefix = self.id + '_' + 'binding_residues'
        mol2maker = op.join(self.dock_dir, '{}_make_mol2.py'.format(prefix))
        outfile = op.join(self.dock_dir, '{}.mol2'.format(prefix))

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=outfile):
            with open(mol2maker, 'w') as mol2_maker:
                mol2_maker.write('#! /usr/bin/env python\n')
                mol2_maker.write('from chimera import runCommand\n')
                mol2_maker.write('runCommand("open {}")\n'.format(receptor_noH))
                mol2_maker.write('runCommand("delete ~:{}")\n'.format(residues))
                mol2_maker.write('runCommand("write format mol2 resnum 0 {}")\n'.format(outfile))
                mol2_maker.write('runCommand("close all")')

            cmd = 'chimera --nogui {}'.format(mol2maker)
            os.system(cmd)
            os.remove(mol2maker)
            os.remove('{}c'.format(mol2maker))

        return outfile

    def sphere_selector_using_residues(self, sph_file, res_mol2, radius, force_rerun=False):
        """Select spheres based on binding site residues

        Args:
            sph_file:
            res_mol2:
            radius:

        Returns:

        """
        selsph = op.join(self.dock_dir, '{}_selsph_binding.sph'.format(self.id))

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=selsph):
            cmd = "sphere_selector {} {} {}".format(sph_file, res_mol2, radius)
            rename = "mv selected_spheres.sph {}".format(selsph)

            os.system(cmd)
            os.system(rename)

        return selsph

    def split_sph(self, sph_file, force_rerun=False):
        selsph = op.join(self.dock_dir, '{}_selsph.sph'.format(self.id))

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=selsph):
            with open(sph_file, "r") as f:
                text = f.read()
                f.seek(0)
                lines = f.readlines()
                paragraphs = re.split("cluster    ...  number of spheres in cluster   ...\n", text)

                with open(selsph, "w") as f2:
                    f2.write(lines[1])
                    f2.write(paragraphs[1])

        return selsph

    def showbox(self, selsph, force_rerun=False):
        boxfile = op.join(self.dock_dir, "{}_box.pdb".format(self.id))
        boxscript = op.join(self.dock_dir, "{}_box.in".format(self.id))

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=boxfile):
            with open(boxscript, "w") as f:
                f.write("Y\n")
                f.write("0\n")
                f.write("{}\n".format(selsph))
                f.write("1\n")
                f.write("{}".format(boxfile))

            cmd = "showbox < {}".format(boxscript)
            os.system(cmd)

        return boxfile

    def grid(self, receptor_file, box_file, amb_file=None, force_rerun=False):
        gridscript = op.join(self.dock_dir, "{}_grid.in".format(self.id))
        out_name = op.join(self.dock_dir, "{}_grid.out".format(self.id))

        if amb_file:
            amb = amb_file

        if ssbio.utils.force_rerun(flag=force_rerun, outfile=out_name):
            with open(gridscript, "w") as f:
                grid_text = """compute_grids                  yes
            grid_spacing                   0.3
            output_molecule                no
            contact_score                  yes
            contact_cutoff_distance        4.5
        
            energy_score                   yes
            energy_cutoff_distance         9999
        
            atom_model                     all
            attractive_exponent            6
            repulsive_exponent             12
            distance_dielectric            yes
            dielectric_factor              4
        
            bump_filter                    yes
            bump_overlap                   0.75
        
            receptor_file                  {}
            box_file                       {}
            vdw_definition_file            {}
            score_grid_prefix              {}_grid
            """.format(receptor_file, box_file, amb, self.id)

                f.write(grid_text)

            cmd = "grid -i {} -o {}".format(gridscript, out_name)
            os.system(cmd)

        return out_name

    def do_dock6_rigid(self, ligand_path, sph_path, grid_path, amber, flex1, flex2, force_rerun=False):
        ligand_name = os.path.basename(args.ligand).split('.')[0]
        in_name = op.join(self.dock_dir, "{}_{}_dock.in".format(self.id, ligand_name))
        out_name = op.join(self.dock_dir, "{}_{}_dock.out".format (self.id, ligand_name))

        with open(in_name, "w") as f:
            dock_text = """ligand_atom_file                                             {}
        limit_max_ligands                                            no
        skip_molecule                                                no
        read_mol_solvation                                           no
        calculate_rmsd                                               no
        use_database_filter                                          no
        orient_ligand                                                yes
        automated_matching                                           yes
        receptor_site_file                                           {}
        max_orientations                                             1000
        critical_points                                              no
        chemical_matching                                            no
        use_ligand_spheres                                           no
        use_internal_energy                                          yes
        internal_energy_rep_exp                                      12
        flexible_ligand                                              no
        bump_filter                                                  no
        score_molecules                                              yes
        contact_score_primary                                        no
        contact_score_secondary                                      no
        grid_score_primary                                           yes
        grid_score_secondary                                         no
        grid_score_rep_rad_scale                                     1
        grid_score_vdw_scale                                         1
        grid_score_es_scale                                          1
        grid_score_grid_prefix                                       {}
        multigrid_score_secondary                                    no
        dock3.5_score_secondary                                      no
        continuous_score_secondary                                   no
        descriptor_score_secondary                                   no
        gbsa_zou_score_secondary                                     no
        gbsa_hawkins_score_secondary                                 no
        SASA_descriptor_score_secondary                              no
        amber_score_secondary                                        no
        minimize_ligand                                              yes
        simplex_max_iterations                                       1000
        simplex_tors_premin_iterations                               0
        simplex_max_cycles                                           1
        simplex_score_converge                                       0.1
        simplex_cycle_converge                                       1.0
        simplex_trans_step                                           1.0
        simplex_rot_step                                             0.1
        simplex_tors_step                                            10.0
        simplex_random_seed                                          0
        simplex_restraint_min                                        yes
        simplex_coefficient_restraint                                10.0
        atom_model                                                   all
        vdw_defn_file                                                {}
        flex_defn_file                                               {}
        flex_drive_file                                              {}
        ligand_outfile_prefix                                        {}_{}_rigid
        write_orientations                                           yes
        num_scored_conformers                                        20
        rank_ligands                                                 no
        """.format(ligand_path, sph_path, grid_path.split('.')[0], amber, flex1, flex2, self.id, ligand_name)

            f.write(dock_text)

        cmd = "dock6 -i {} -o {}".format(in_name, out_name)
        os.system(cmd)

    def do_dock6_flexible(self, ligand_path, sph_path, grid_path, amber, flex1, flex2, force_rerun=False):
        ligand_name = os.path.basename(ligand_path).split('.')[0]
        in_name = op.join(self.dock_dir, "{}_{}_flexdock.in".format(self.id, ligand_name))
        out_name = op.join(self.dock_dir, "{}_{}_flexdock.out".format(self.id, ligand_name))

        with open(in_name, "w") as f:
            dock_text = """ligand_atom_file                                             {}
        limit_max_ligands                                            no
        skip_molecule                                                no
        read_mol_solvation                                           no
        calculate_rmsd                                               no
        use_database_filter                                          no
        orient_ligand                                                yes
        automated_matching                                           yes
        receptor_site_file                                           {}
        max_orientations                                             1000
        critical_points                                              no
        chemical_matching                                            no
        use_ligand_spheres                                           no
        use_internal_energy                                          yes
        internal_energy_rep_exp                                      12
        flexible_ligand                                              yes
        user_specified_anchor                                        no
        limit_max_anchors                                            no
        min_anchor_size                                              5
        pruning_use_clustering                                       yes
        pruning_max_orients                                          100
        pruning_clustering_cutoff                                    100
        pruning_conformer_score_cutoff                               100
        use_clash_overlap                                            no
        write_growth_tree                                            no
        bump_filter                                                  yes
        bump_grid_prefix                                             {}
        score_molecules                                              yes
        contact_score_primary                                        no
        contact_score_secondary                                      no
        grid_score_primary                                           yes
        grid_score_secondary                                         no
        grid_score_rep_rad_scale                                     1
        grid_score_vdw_scale                                         1
        grid_score_es_scale                                          1
        grid_score_grid_prefix                                       {}
        multigrid_score_secondary                                    no
        dock3.5_score_secondary                                      no
        continuous_score_secondary                                   no
        descriptor_score_secondary                                   no
        gbsa_zou_score_secondary                                     no
        gbsa_hawkins_score_secondary                                 no
        SASA_descriptor_score_secondary                              no
        amber_score_secondary                                        no
        minimize_ligand                                              yes
        minimize_anchor                                              yes
        minimize_flexible_growth                                     yes
        use_advanced_simplex_parameters                              no
        simplex_max_cycles                                           1
        simplex_score_converge                                       0.1
        simplex_cycle_converge                                       1.0
        simplex_trans_step                                           1.0
        simplex_rot_step                                             0.1
        simplex_tors_step                                            10.0
        simplex_anchor_max_iterations                                500
        simplex_grow_max_iterations                                  500
        simplex_grow_tors_premin_iterations                          0
        simplex_random_seed                                          0
        simplex_restraint_min                                        yes
        simplex_coefficient_restraint                                10.0
        atom_model                                                   all
        vdw_defn_file                                                {}
        flex_defn_file                                               {}
        flex_drive_file                                              {}
        ligand_outfile_prefix                                        {}_{}_flexible
        write_orientations                                           no
        num_scored_conformers                                        20
        rank_ligands                                                 no
        """.format(ligand_path, sph_path, grid_path.split('.')[0], grid_path.split('.')[0], amber, flex1, flex2,
                   self.id, ligand_name)

            f.write(dock_text)

        cmd = "dock6 -i {} -o {} -v".format(in_name, out_name)
        os.system(cmd)

    def do_dock6_amberscore(self, ligand_path, sph_path, grid_path, amber, flex1, flex2, force_rerun=False):
        ligand_name = os.path.basename(args.ligand).split('.')[0]
        in_name = "{}_{}_amberscore.in" % (prefix, ligand_name)
        out_name = "{}_{}_amberscore.out" % (prefix, ligand_name)

        with open("{}" % in_name, "w") as f:
            dock_text = """ligand_atom_file                                             {}.amber_score.mol2
        limit_max_ligands                                            no
        skip_molecule                                                no
        read_mol_solvation                                           no
        calculate_rmsd                                               no
        use_database_filter                                          no
        orient_ligand                                                no
        use_internal_energy                                          no
        flexible_ligand                                              no
        bump_filter                                                  no
        score_molecules                                              yes
        contact_score_primary                                        no
        contact_score_secondary                                      no
        grid_score_primary                                           no
        grid_score_secondary                                         no
        multigrid_score_primary                                      no
        multigrid_score_secondary                                    no
        dock3.5_score_primary                                        no
        dock3.5_score_secondary                                      no
        continuous_score_primary                                     no
        continuous_score_secondary                                   no
        descriptor_score_primary                                     no
        descriptor_score_secondary                                   no
        gbsa_zou_score_primary                                       no
        gbsa_zou_score_secondary                                     no
        gbsa_hawkins_score_primary                                   no
        gbsa_hawkins_score_secondary                                 no
        SASA_descriptor_score_primary                                no
        SASA_descriptor_score_secondary                              no
        amber_score_primary                                          yes
        amber_score_secondary                                        no
        amber_score_receptor_file_prefix                             {}
        amber_score_movable_region                                   ligand
        amber_score_minimization_rmsgrad                             0.01
        amber_score_before_md_minimization_cycles                    100
        amber_score_md_steps                                         3000
        amber_score_after_md_minimization_cycles                     100
        amber_score_gb_model                                         5
        amber_score_nonbonded_cutoff                                 18.0
        amber_score_temperature                                      300.0
        amber_score_abort_on_unprepped_ligand                        yes
        ligand_outfile_prefix                                        output
        write_orientations                                           no
        num_scored_conformers                                        1
        rank_ligands                                                 no
        """.format()

            f.write(dock_text)

        cmd = "dock6 -i {} -o {} -v" % (in_name, out_name)
        os.system(cmd)


if __name__ == '__main__':

    import glob
    import argparse
    import shlex

    # load inputs from command line
    p = argparse.ArgumentParser(
            description='Run the DOCK steps on a folder of structure files. To run in the background, execute using nohup: nohup dock.py $BASENAME $NUMFRAMES /path/to/structures/ /path/to/parameters/ --ligand /path/to/ligand.mol2 --cofactors $COFACTORS --residues $RESIDUES > /path/to/logs/$LOGNAME &')
    p.add_argument('basename', help='base filename that you used to name your files')
    p.add_argument('numframes', help='total number of frames from your trajectory', type=int)
    p.add_argument('folder', help='path to folder with your structure files')
    p.add_argument('params', help='path to folder with parameter files')
    p.add_argument('--ligand', help='path to file of your ligand that you want to dock')
    p.add_argument('--cofactors',
                   help='comma-separated string of cofactors that you want to keep while docking (e.g. SAM,DNC,WAT)')
    p.add_argument('--residues', help='comma-separated string of the binding residues')
    p.add_argument('--radius', help='radius around binding residues to dock to (default 9 A)', type=int, default=9)
    p.add_argument('--redock', help='run DOCK again for the specified ligand, even if docking files exist',
                   default=False)
    args = p.parse_args()

    # file paths for docking parameters
    amb = os.path.join(args.params, 'vdw_AMBER_parm99.defn')
    f1 = os.path.join(args.params, 'flex.defn')
    f2 = os.path.join(args.params, 'flex_drive.tbl')

    print(args)
    # loading current files
    os.chdir(args.folder)
    # pdbs = glob.glob('{}-*.pdb'.format(args.basename))
    current_files = os.listdir(os.getcwd())

    # ligand name
    if args.ligand:
        ligandname = os.path.basename(args.ligand)

    # cofactors
    if args.cofactors:
        cofactors_list = shlex.split(args.cofactors)
    else:
        cofactors_list = []

    print('***************PARAMETERS***************')
    print('FULL LIST: {0}'.format(vars(args)))
    if args.ligand:
        print('LIGAND: {0}'.format(ligandname))
    if args.cofactors:
        print('COFACTORS: {0}'.format(cofactors_list))
    if args.residues:
        print('BINDING RESIDUES: {0}'.format(args.residues))
        print('RADIUS: {0}'.format(args.radius))

    counter = 1
    for frame in range(1, args.numframes + 1):
        # just a simple counter
        print(str(counter) + '/' + str(args.numframes))
        counter += 1

        # file_prefix = '{0}-{1:03d}'.format(args.basename, frame)
        file_prefix = '{0}'.format(args.basename)
        print(file_prefix)

        # DOCKPREP
        # example: 3bwm-440_prep.mol2
        pdb = '{0}.pdb'.format(file_prefix)
        prepped_check = '{}_prep.mol2'.format(file_prefix)
        if prepped_check in current_files:
            print('***DOCKPREP PREVIOUSLY RUN***')
            prepped_file = prepped_check
        else:
            print('RUNNING: DOCKPREP')
            prepped_file = dockprep(pdb, file_prefix)

        # ISOLATE RECEPTOR
        # example: 3bwm-440_receptor.mol2, 3bwm-440_receptor_noH.pdb
        receptor_check = '{}_receptor.mol2'.format(file_prefix)
        receptor_noH_check = '{}_receptor_noH.pdb'.format(file_prefix)
        if receptor_check in current_files and receptor_noH_check in current_files:
            print('***RECEPTOR FILES PREVIOUSLY GENERATED***')
            receptor, receptor_noH = receptor_check, receptor_noH_check
        else:
            print('RUNNING: ISOLATE RECEPTOR')
            receptor, receptor_noH = protein_only_and_noH(prepped_file, cofactors_list, file_prefix)

        # DMS
        # example: 3bwm-440_receptor.dms
        dms_check = '{}_receptor.dms'.format(file_prefix)
        if dms_check in current_files:
            print('***SURFACE PREVIOUSLY GENERATED***')
            dms = dms_check
        else:
            print('RUNNING: DMS')
            dms = dms_maker(receptor_noH, file_prefix)

        # SPHGEN
        # example: 3bwm-440_receptor.sph
        sph_check = '{}_receptor.sph'.format(file_prefix)
        if sph_check in current_files:
            print('***SPHERES PREVIOUSLY GENERATED***')
            sph = sph_check
        else:
            print('RUNNING: SPHGEN')
            sph = sphgen(dms, file_prefix)

        # SPHERE_SELECTOR
        # first choose binding site and save it as separate .mol2
        # example: 3BWY-418_binding_residues.mol2
        binding_site_mol2_file_check = '{}_binding_residues.mol2'.format(file_prefix)
        if binding_site_mol2_file_check in current_files:
            print('***BINDING SITE RESIDUES ALREADY DEFINED***')
            binding_site_mol2_file = binding_site_mol2_file_check
        else:
            print('RUNNING: BINDING SITE MOL2')
            binding_site_mol2_file = binding_site_mol2(receptor_noH, args.residues, file_prefix)

        # then select the spheres based on these binding residues
        # example: 3bwm-440_selected_spheres_using_binding_residues.sph
        sel_sph_check = '{}_selected_spheres_using_binding_residues.sph'.format(file_prefix)
        if sel_sph_check in current_files:
            print('***SPHERES ALREADY SELECTED***')
            sel_sph = sel_sph_check
        else:
            print('RUNNING: SPHERE_SELECTOR')
            sel_sph = sphere_selector_using_residues(sph, binding_site_mol2_file, args.radius, file_prefix)

        # SHOWBOX
        # example: 3bwm-440_box.pdb
        box_check = '{}_box.pdb'.format(file_prefix)
        if box_check in current_files:
            print('***BOX PREVIOUSLY MADE***')
            box = box_check
        else:
            print('RUNNING: SHOWBOX')
            box = showbox(sel_sph, file_prefix)

        # GRID
        # example: 3bwm-440_grid.out
        gr_check = '{}_grid.out'.format(file_prefix)
        if gr_check in current_files:
            print('***GRID PREVIOUSLY CALCULATED***')
            gr = gr_check
        else:
            print('RUNNING: GRID')
            gr = grid(receptor, box, amb, file_prefix)

        # DOCK
        if args.ligand:
            dock6_flexible_check = '{}_{}_flexible_scored.mol2'.format((file_prefix, ligandname.split('.')[0]))
            if dock6_flexible_check in current_files and not args.redock:
                print('***DOCK PREVIOUSLY RUN***')
            else:
                print('RUNNING: DOCK')
                do_dock6_flexible(args.ligand, sel_sph, gr, amb, f1, f2, file_prefix)

    print('***DOCKING COMPLETE***')
