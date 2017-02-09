import os
import pandas as pd
from cobra.core import DictList
from collections import OrderedDict
from ssbio.core.object import Object
import ssbio.databases.kegg
import ssbio.databases.uniprot
from ssbio.sequence import SeqProp
from ssbio.databases.kegg import KEGGProp
from ssbio.databases.uniprot import UniProtProp
from ssbio.structure import StructProp
from ssbio.databases.pdb import PDBProp
from ssbio.structure.homology.itasser.itasserprop import ITASSERProp
import ssbio.sequence.utils.fasta
import ssbio.sequence.utils.alignment
import ssbio.utils
import requests
from ssbio.structure.utils.cleanpdb import CleanPDB
import ssbio.structure.properties.quality
import numpy as np
import logging
log = logging.getLogger(__name__)


class Protein(Object):
    """Basic definition of a protein"""

    _representative_sequence_attributes = ['gene', 'uniprot', 'kegg', 'pdbs',
                                           'sequence_path', 'metadata_path']
    _representative_structure_attributes = ['is_experimental', 'reference_seq_top_coverage', 'date', 'description',
                                            'resolution','taxonomy_name']

    def __init__(self, ident, description=None):
        Object.__init__(self, id=ident, description=description)
        self.sequences = DictList()
        self.structures = DictList()
        self.representative_sequence = None
        self.representative_structure = None

        # TODO: define this instead of doing op.join(gempro.sequence_dir, gene.id) for a lot of things
        # self.sequence_dir = seq_dir
        # self.structure_dir = struct_dir

    @property
    def num_structures(self):
        """Return the total number of structures"""
        return len(self.structures)

    @property
    def num_structures_experimental(self):
        """Return the total number of experimental structures"""
        return len(self.get_experimental_structures())

    @property
    def num_structures_homology(self):
        """Return the total number of homology models"""
        return len(self.get_homology_models())

    def get_experimental_structures(self):
        """Return a DictList of all experimental structures in self.structures"""
        return DictList(x for x in self.structures if x.is_experimental)

    def get_homology_models(self):
        """Return a DictList of all homology models in self.structures"""
        return DictList(x for x in self.structures if not x.is_experimental)

    def filter_sequences(self, seq_type):
        """Get a DictList of only specified types in the sequences attribute.

        Args:
            seq_type: Object type

        Returns:
            DictList: of Object type mappings only

        """
        return DictList(x for x in self.sequences if isinstance(x, seq_type))

    def load_kegg(self, kegg_id, kegg_organism_code=None, kegg_seq_file=None, kegg_metadata_file=None,
                  set_as_representative=False, download=False, outdir=None, force_rerun=False):
        """Load a KEGG ID, sequence, and metadata files into the sequences attribute.

        Args:
            kegg_id (str): KEGG ID
            kegg_organism_code (str): KEGG organism code to prepend to the kegg_id if not part of it already.
                Example: "eco:b1244", eco is the organism code
            kegg_seq_file (str): Path to KEGG FASTA file
            kegg_metadata_file (str): Path to KEGG metadata file (raw KEGG format)
            set_as_representative (bool): If this KEGG ID should be set as the representative sequence
            download (bool): If the KEGG sequence and metadata files should be downloaded if not provided
            outdir (str): Where the sequence and metadata files should be downloaded to
            force_rerun (bool): If ID should be reloaded and files redownloaded

        Returns:
            KEGGProp: object contained in the sequences attribute

        """
        if kegg_organism_code:
            kegg_id = kegg_organism_code + ':' + kegg_id

        # If we have already loaded the KEGG ID
        if self.sequences.has_id(kegg_id):
            # Remove it if we want to force rerun things
            if force_rerun:
                existing = self.sequences.get_by_id(kegg_id)
                self.sequences.remove(existing)
            # Otherwise just get that KEGG object
            else:
                log.debug('{}: KEGG ID already present in list of sequences'.format(kegg_id))
                kegg_prop = self.sequences.get_by_id(kegg_id)

        # Check again (instead of else) in case we removed it if force rerun
        if not self.sequences.has_id(kegg_id):
            kegg_prop = KEGGProp(kegg_id, kegg_seq_file, kegg_metadata_file)
            if download:
                kegg_prop.download_seq_file(outdir, force_rerun)
                kegg_prop.download_metadata_file(outdir, force_rerun)

            if kegg_prop.sequence_path:
                # Check if KEGG sequence matches a potentially set representative sequence
                # Do not add any info if a UniProt ID was already mapped though, we want to use that
                if self.representative_sequence:
                    if not self.representative_sequence.uniprot:
                        if kegg_prop.equal_to(self.representative_sequence):
                            # Update the representative sequence field with KEGG metadata
                            self.representative_sequence.update(kegg_prop.get_dict())
                        else:
                            # TODO: add option to use manual or kegg sequence if things do not match
                            log.warning('{}: representative sequence does not match mapped KEGG sequence.'.format(self.id))

            self.sequences.append(kegg_prop)

        if set_as_representative:
            self._representative_sequence_setter(kegg_prop)

        return self.sequences.get_by_id(kegg_id)

    def load_uniprot(self, uniprot_id, uniprot_seq_file=None, uniprot_metadata_file=None,
                     set_as_representative=False, download=False, outdir=None, force_rerun=False):
        """Load a UniProt ID and associated sequence/metadata files into the sequences attribute.

        Args:
            uniprot_id:
            uniprot_seq_file:
            uniprot_metadata_file:
            set_as_representative:
            download:
            outdir:
            force_rerun:

        Returns:

        """
        # If we have already loaded the KEGG ID
        if self.sequences.has_id(uniprot_id):
            # Remove it if we want to force rerun things
            if force_rerun:
                existing = self.sequences.get_by_id(uniprot_id)
                self.sequences.remove(existing)
            # Otherwise just get that KEGG object
            else:
                log.debug('{}: KEGG ID already present in list of sequences'.format(uniprot_id))
                uniprot_prop = self.sequences.get_by_id(uniprot_id)

        if not self.sequences.has_id(uniprot_id):
            uniprot_prop = UniProtProp(uniprot_id, uniprot_seq_file, uniprot_metadata_file)
            if download:
                uniprot_prop.download_seq_file(outdir, force_rerun)
                uniprot_prop.download_metadata_file(outdir, force_rerun)

            # Also check if UniProt sequence matches a potentially set representative sequence
            if self.representative_sequence:
                # Test equality
                if uniprot_prop.equal_to(self.representative_sequence):
                    # Update the representative sequence field with UniProt metadata
                    self.representative_sequence.update(uniprot_prop.get_dict())
                else:
                    # TODO: add option to use manual or uniprot sequence if things do not match
                    log.warning('{}: representative sequence does not match mapped UniProt sequence'.format(self.id))
            self.sequences.append(uniprot_prop)

        if set_as_representative:
            self._representative_sequence_setter(uniprot_prop)

        return self.sequences.get_by_id(uniprot_id)

    def load_manual_sequence_file(self, ident, seq_file, set_as_representative=False):
        """Load a manual sequence given as a FASTA file and optionally set it as the representative sequence.
            Also store it in the sequences attribute.

        Args:
            ident:
            seq_file:
            set_as_representative:

        """
        manual_sequence = SeqProp(ident=ident, sequence_file=seq_file)
        self.sequences.append(manual_sequence)

        if set_as_representative:
            self._representative_sequence_setter(manual_sequence)

        return self.sequences.get_by_id(ident)

    def load_manual_sequence_str(self, ident, seq_str, outdir=None, set_as_representative=False, force_rerun=False):
        """Load a manual sequence given as a string and optionally set it as the representative sequence.
            Also store it in the sequences attribute.

        Args:
            ident:
            seq_str:
            set_as_representative:

        """
        manual_sequence = SeqProp(ident=ident, seq_str=seq_str,
                                  write_fasta_file=True, outname=ident, outdir=outdir, force_rewrite=force_rerun)
        self.sequences.append(manual_sequence)

        if set_as_representative:
            self._representative_sequence_setter(manual_sequence)

        return self.sequences.get_by_id(ident)

    def _representative_sequence_setter(self, seq_prop):
        """Make a copy of a SeqProp object and store it as the representative. Only keep certain attributes"""
        self.representative_sequence = SeqProp(ident=seq_prop.id, sequence_file=seq_prop.sequence_path)
        self.representative_sequence.update(seq_prop.get_dict(), only_keys=self._representative_sequence_attributes)

    def set_representative_sequence(self):
        """Consolidate sequence that were loaded and set a single representative sequence."""

        if len(self.sequences) == 0:
            log.error('{}: no sequences mapped'.format(self.id))
            return self.representative_sequence

        kegg_mappings = self.filter_sequences(KEGGProp)
        if len(kegg_mappings) > 0:
            kegg_to_use = kegg_mappings[0]
            if len(kegg_mappings) > 1:
                log.warning('{}: multiple KEGG mappings found, using the first entry {}'.format(self.id, kegg_to_use.id))

        uniprot_mappings = self.filter_sequences(UniProtProp)

        # If a representative sequence has already been set, nothing needs to be done
        if self.representative_sequence:
            log.debug('{}: representative sequence already set'.format(self.id))

        # If there is a KEGG annotation and no UniProt annotations, set KEGG as representative
        elif len(kegg_mappings) > 0 and len(uniprot_mappings) == 0:
            self._representative_sequence_setter(kegg_to_use)
            log.debug('{}: representative sequence set from KEGG ID {}'.format(self.id, kegg_to_use.id))

        # If there are UniProt annotations and no KEGG annotations, set UniProt as representative
        elif len(kegg_mappings) == 0 and len(uniprot_mappings) > 0:
            # If there are multiple uniprots rank them by the sum of reviewed (bool) + num_pdbs
            # This way, UniProts with PDBs get ranked to the top, or if no PDBs, reviewed entries
            u_ranker = []
            for u in uniprot_mappings:
                u_ranker.append((u.id, u.ranking_score()))
            sorted_by_second = sorted(u_ranker, key=lambda tup: tup[1], reverse=True)
            best_u_id = sorted_by_second[0][0]

            best_u = uniprot_mappings.get_by_id(best_u_id)
            self._representative_sequence_setter(best_u)
            log.debug('{}: Representative sequence set from UniProt ID {}'.format(self.id, best_u_id))

        # If there are both UniProt and KEGG annotations...
        elif len(kegg_mappings) > 0 and len(uniprot_mappings) > 0:
            # Use KEGG if the mapped UniProt is unique, and it has PDBs
            if kegg_to_use.num_pdbs > 0 and not uniprot_mappings.has_id(kegg_to_use.uniprot):
                self._representative_sequence_setter(kegg_to_use)
                log.debug('{}: Representative sequence set from KEGG ID {}'.format(self.id, kegg_to_use.id))
            else:
                # If there are multiple uniprots rank them by the sum of reviewed (bool) + num_pdbs
                u_ranker = []
                for u in uniprot_mappings:
                    u_ranker.append((u.id, u.ranking_score()))
                sorted_by_second = sorted(u_ranker, key=lambda tup: tup[1], reverse=True)
                best_u_id = sorted_by_second[0][0]

                best_u = uniprot_mappings.get_by_id(best_u_id)
                self._representative_sequence_setter(best_u)
                log.debug('{}: Representative sequence set from UniProt ID {}'.format(self.id, best_u_id))

        return self.representative_sequence

    def align_sequences_to_representative(self, outdir=None, engine='needle', parse=True, force_rerun=False, **kwargs):
        """Align all sequences in the sequences attribute to the representative sequence.

        Stores the alignments the representative_sequence.sequence_alignments DictList

        Args:
            outfile:
            outdir:
            engine:
            parse: Store locations of mutations, insertions, and deletions in the alignment object (as an annotation)
            force_rerun:
            **kwargs: Other options for sequence alignment (gap penalties, etc) See:
                ssbio.sequence.utils.alignment.pairwise_sequence_alignment

        """
        for seq in self.sequences:
            aln_id = '{}_{}'.format(self.id, seq.id)
            outfile = '{}.needle'.format(aln_id)

            if self.representative_sequence.sequence_alignments.has_id(aln_id):
                log.debug('{}: alignment already completed'.format(seq.id))
                continue

            if not seq.seq_str:
                log.error('{}: no sequence stored, skipping alignment'.format(seq.id))
                continue

            # Don't need to compare sequence to itself
            if seq.id == self.representative_sequence.id:
                continue

            aln = ssbio.sequence.utils.alignment.pairwise_sequence_alignment(a_seq=self.representative_sequence.seq_str,
                                                                             a_seq_id=self.id,
                                                                             b_seq=seq.seq_str,
                                                                             b_seq_id=seq.id,
                                                                             engine=engine,
                                                                             outdir=outdir,
                                                                             outfile=outfile,
                                                                             force_rerun=force_rerun)
            # Add an identifier to the MultipleSeqAlignment object for storage in a DictList
            aln.id = aln_id
            aln.annotations['a_seq'] = self.representative_sequence.id
            aln.annotations['b_seq'] = seq.id

            if parse:
                aln_df = ssbio.sequence.utils.alignment.get_alignment_df(a_aln_seq=str(list(aln)[0].seq),
                                                                         b_aln_seq=str(list(aln)[1].seq))
                aln.annotations['mutations'] = ssbio.sequence.utils.alignment.get_mutations(aln_df)
                aln.annotations['deletions'] = ssbio.sequence.utils.alignment.get_deletions(aln_df)
                aln.annotations['insertions'] = ssbio.sequence.utils.alignment.get_insertions(aln_df)

            self.representative_sequence.sequence_alignments.append(aln)

    def load_pdb(self, pdb_id, mapped_chains=None, pdb_file=None, file_type=None, set_as_representative=False, force_rerun=False):
        """Load a PDB ID into the structures attribute.

        Args:
            pdb_id (str): PDB ID
            mapped_chains (str, list): Chain ID or list of IDs which you are interested in
            pdb_file (str): Path to PDB file
            file_type (str): Type of PDB file
            set_as_representative (bool): If this structure should be set as the representative structure
            parse (bool): If the structure's 3D coordinates and chains should be parsed

        Returns:
            PDBProp: The object that is now contained in the structures attribute

        """
        pdb_id = pdb_id.lower()

        if self.structures.has_id(pdb_id):
            if force_rerun:
                existing = self.structures.get_by_id(pdb_id)
                self.structures.remove(existing)
            else:
                log.debug('{}: PDB ID already present in list of structures'.format(pdb_id))
                pdb = self.structures.get_by_id(pdb_id)

                if mapped_chains:
                    pdb.add_mapped_chain_ids(mapped_chains)
                if pdb_file:
                    pdb.load_structure_file(pdb_file, file_type)

        if not self.structures.has_id(pdb_id):
            pdb = PDBProp(ident=pdb_id, chains=mapped_chains, structure_file=pdb_file, file_type=file_type, reference_seq=self.representative_sequence)
            if mapped_chains:
                pdb.add_mapped_chain_ids(mapped_chains)
            self.structures.append(pdb)

        if set_as_representative:
            self._representative_structure_setter(pdb)

        return self.structures.get_by_id(pdb_id)

    def load_itasser_folder(self, ident, itasser_folder, set_as_representative=False, create_dfs=False, force_rerun=False):
        """Load the results folder from I-TASSER, copy structure files over, and create summary dataframes.

        Args:
            ident: I-TASSER ID
            itasser_folder: Path to results folder
            set_as_representative: If this structure should be set as the representative structure
            create_dfs: If summary dataframes should be created
            parse: If the structure's 3D coordinates and chains should be parsed
            force_rerun:

        Returns:
            ITASSERProp: StructProp object stored in the structures list.

        """

        if self.structures.has_id(ident):
            if force_rerun:
                existing = self.structures.get_by_id(ident)
                self.structures.remove(existing)
            else:
                log.warning('{}: already present in list of structures'.format(ident))
                itasser = self.structures.get_by_id(ident)

        if not self.structures.has_id(ident):
            itasser = ITASSERProp(ident, itasser_folder, create_dfs=create_dfs, reference_seq=self.representative_sequence)
            self.structures.append(itasser)

        if set_as_representative:
            self._representative_structure_setter(itasser)

        return self.structures.get_by_id(ident)

    def load_generic_structure(self, ident, structure_file=None, set_as_representative=False, force_rerun=False):
        if self.structures.has_id(ident):
            if force_rerun:
                existing = self.structures.get_by_id(ident)
                self.structures.remove(existing)
            else:
                log.warning('{}: already present in list of structures'.format(ident))
                model = self.structures.get_by_id(ident)

        if not self.structures.has_id(ident):
            model = StructProp(ident=ident, structure_file=structure_file, reference_seq=self.representative_sequence,
                               is_experimental=False)
            self.structures.append(model)

        if set_as_representative:
            self._representative_structure_setter(model)

        return self.structures.get_by_id(ident)

    def _representative_structure_setter(self, struct_prop, keep_chain, new_id=None, clean=True,
                                         out_suffix='_clean', outdir=None):
        """Set the representative structure by 1) cleaning it and 2) copying over attributes of the original structure.

        The structure is copied because the chains stored may change, and cleaning it makes a new PDB file.

        Args:
            struct_prop (StructProp): StructProp object to set as representative
            keep_chain (str, list): List of chains to keep
            new_id (str): New ID to call this structure, for example 1abc-D to represent PDB 1abc, chain D
            clean (bool): If the PDB file should be cleaned (see ssbio.structure.utils.cleanpdb)
            out_suffix (str): Suffix to append to clean PDB file
            outdir (str): Path to output directory

        Returns:
            StructProp: representative structure

        """
        if not outdir:
            outdir = os.getcwd()

        if not new_id:
            new_id = struct_prop.id

        # If the structure is to be cleaned, and which chain to keep
        if clean:
            final_pdb = struct_prop.clean_structure(outdir=outdir, out_suffix=out_suffix, keep_chains=keep_chain)
        else:
            final_pdb = struct_prop.structure_path

        self.representative_structure = StructProp(ident=new_id, chains=keep_chain, mapped_chains=keep_chain,
                                                   structure_file=final_pdb, file_type='pdb',
                                                   reference_seq=self.representative_sequence,
                                                   representative_chain=keep_chain)

        self.representative_structure.update(struct_prop.get_dict_with_chain(chain=keep_chain),
                                             only_keys=self._representative_structure_attributes,
                                             overwrite=True)

        # STORE REPRESENTATIVE CHAIN RESNUMS in the representative sequence seqrecord letter_annotations
        # Get the alignment
        alnid = '{}_{}'.format(self.representative_sequence.id, self.representative_structure.id)
        aln = self.representative_structure.reference_seq.structure_alignments.get_by_id(alnid)
        # Get the mapping and store it in .seq_record.letter_annotations['repchain_resnums']
        aln_df = ssbio.sequence.utils.alignment.get_alignment_df(aln[0], aln[1])
        repchain_resnums = aln_df[pd.notnull(aln_df.id_a_pos)].id_b_pos.tolist()
        self.representative_sequence.seq_record.letter_annotations['repchain_resnums'] = repchain_resnums

        # Also need to parse the clean structure and save its sequence..
        self.representative_structure.parse_structure()

    def set_representative_structure(self, seq_outdir, struct_outdir, engine='needle', seq_ident_cutoff=0.5,
                                     always_use_homology=False,
                                     allow_missing_on_termini=0.2, allow_mutants=True, allow_deletions=False,
                                     allow_insertions=False, allow_unresolved=True, force_rerun=False):
        """Set a representative structure from a structure in self.structures

        Args:
            seq_outdir:
            struct_outdir:
            engine:
            seq_ident_cutoff:
            always_use_homology:
            allow_missing_on_termini:
            allow_mutants:
            allow_deletions:
            allow_insertions:
            allow_unresolved:
            force_rerun:

        Returns:

        """
        log.debug('{}: setting representative structure'.format(self.id))

        if len(self.structures) == 0:
            log.debug('{}: no structures available'.format(self.id))
            return None

        if not self.representative_sequence:
            log.error('{}: no representative sequence to compare structures to'.format(self.id))
            return None

        if self.representative_structure and not force_rerun:
            log.debug('{}: representative structure already set'.format(self.id))
            return self.representative_structure

        has_homology = False
        has_pdb = False
        use_homology = False
        use_pdb = False

        if self.num_structures_homology > 0:
            has_homology = True
        if self.num_structures_experimental > 0:
            has_pdb = True

        # If we mark to always use homology, use it if it exists
        if always_use_homology:
            if has_homology:
                use_homology = True
            elif has_pdb:
                use_pdb = True
        # If we don't always want to use homology, use PDB if it exists
        else:
            if has_homology and has_pdb:
                use_pdb = True
                use_homology = True
            elif has_homology and not has_pdb:
                use_homology = True
            elif has_pdb and not has_homology:
                use_pdb = True

        if use_pdb:
            # Put PDBs through QC/QA
            log.debug('{}: checking quality of experimental structures'.format(self.id))
            all_pdbs = self.get_experimental_structures()

            for pdb in all_pdbs:
                # Download the structure and parse it
                # This will add all chains to the mapped_chains attribute if there are none
                try:
                    pdb.download_structure_file(outdir=struct_outdir, force_rerun=force_rerun)
                    # TODO: add global flag of PDB file type and adjust for downloading the header here (and other places where pdb is downloaded)
                    # pdb.download_cif_header_file(outdir=struct_outdir)
                except requests.exceptions.HTTPError:
                    log.error('{}: structure file could not be downloaded'.format(pdb))
                    continue
                pdb.align_reference_seq_to_mapped_chains(outdir=seq_outdir, engine=engine, parse=False, force_rerun=force_rerun)
                best_chain = pdb.sequence_quality_checker(seq_ident_cutoff=seq_ident_cutoff,
                                                          allow_missing_on_termini=allow_missing_on_termini,
                                                          allow_mutants=allow_mutants, allow_deletions=allow_deletions,
                                                          allow_insertions=allow_insertions, allow_unresolved=allow_unresolved)

                if best_chain:
                    self._representative_structure_setter(struct_prop=pdb,
                                                          new_id='{}-{}'.format(pdb.id, best_chain.id),
                                                          clean=True,
                                                          out_suffix='-{}_clean'.format(best_chain.id),
                                                          keep_chain=best_chain.id,
                                                          outdir=struct_outdir)
                    log.debug('{}-{}: set as representative structure'.format(pdb.id, best_chain.id))
                    return self.representative_structure
            else:
                log.debug('{}: no experimental structures meet cutoffs'.format(self.id))

        # If we are to use homology, save its information in the representative structure field
        if use_homology:
            log.debug('{}: checking quality of homology models'.format(self.id))
            all_models = self.get_homology_models()

            # TODO: homology models are not ordered in any other way other than how they are loaded,
            # rethink this for multiple homology models
            for homology in all_models:
                if not homology.structure_path:
                    log.debug('{}: no homology structure file'.format(self.id))
                    continue

                homology.align_reference_seq_to_mapped_chains(outdir=seq_outdir, engine=engine, parse=False,
                                                              force_rerun=force_rerun)
                best_chain = homology.sequence_quality_checker(seq_ident_cutoff=seq_ident_cutoff,
                                                               allow_missing_on_termini=allow_missing_on_termini,
                                                               allow_mutants=allow_mutants,
                                                               allow_deletions=allow_deletions,
                                                               allow_insertions=allow_insertions,
                                                               allow_unresolved=allow_unresolved)

                if best_chain:
                    if not best_chain.id.strip():
                        best_chain_suffix = 'X'
                    else:
                        best_chain_suffix = best_chain.id
                    self._representative_structure_setter(struct_prop=homology,
                                                          new_id='{}-{}'.format(homology.id, best_chain_suffix),
                                                          clean=True,
                                                          out_suffix='-{}_clean'.format(best_chain_suffix),
                                                          keep_chain=best_chain.id,
                                                          outdir=struct_outdir)
                    log.debug('{}-{}: set as representative structure'.format(homology.id, best_chain_suffix))
                    return self.representative_structure

        else:
            log.warning('{}: no representative structure found'.format(self.id))
            return None

    def view_all_mutations(self, grouped=False, color='red', unique_colors=True, structure_opacity=0.5,
                           opacity_range=(0.8,1), scale_range=(1,5), gui=False):
        """Map all sequence alignment mutations to the structure.

        Args:
            grouped (bool): If groups of mutations should be colored and sized together
            color (str): Color of the mutations (overridden if unique_colors=True)
            unique_colors (bool): If each mutation/mutation group should be colored uniquely
            structure_opacity (float): Opacity of the protein structure cartoon representation
            opacity_range (tuple): Min/max opacity values (mutations that show up more will be opaque)
            scale_range (tuple): Min/max size values (mutations that show up more will be bigger)
            gui (bool): If the NGLview GUI should show up

        Returns:
            NGLviewer object

        """
        single, fingerprint = self.representative_sequence.sequence_mutation_summary()

        single_lens = {k: len(v) for k, v in single.items()}
        single_map_to_structure = {}
        for k, v in single_lens.items():
            resnum = int(k[1])
            resnum_to_structure = self.representative_structure.map_repseq_resnums_to_structure_resnums(resnum)
            if resnum not in resnum_to_structure:
                log.warning('{}: residue is not available in structure {}'.format(resnum, self.representative_structure.id))
                continue
            new_key = resnum_to_structure[resnum][1]
            single_map_to_structure[new_key] = v

        if not grouped:
            view = self.representative_structure.view_structure_and_highlight_residues(single_map_to_structure,
                                                                                       color=color, unique_colors=unique_colors,
                                                                                       structure_opacity=structure_opacity,
                                                                                       opacity_range=opacity_range,
                                                                                       scale_range=scale_range,
                                                                                       gui=gui)
            return view

        else:
            fingerprint_lens = {k: len(v) for k, v in fingerprint.items()}
            fingerprint_map_to_structure = {}
            for k, v in fingerprint_lens.items():
                k_list = [int(x[1]) for x in k]
                resnums_to_structure = self.representative_structure.map_repseq_resnums_to_structure_resnums(k_list)
                new_key = tuple(y[1] for y in resnums_to_structure.values())
                fingerprint_map_to_structure[new_key] = v

            view = self.representative_structure.view_structure_and_highlight_residues(fingerprint_map_to_structure,
                                                                                       color=color, unique_colors=unique_colors,
                                                                                       opacity_range=opacity_range,
                                                                                       scale_range=scale_range,
                                                                                       gui=gui)
            return view

    def summarize_protein(self):
        """Gather all possible attributes in the sequences and structures and summarize everything.

        Returns:
            dict:

        """
        d = OrderedDict()
        repseq = self.representative_sequence
        if not self.representative_structure:
            repstruct = StructProp(self.id)
            repchain = repstruct.representative_chain
        else:
            repstruct = self.representative_structure
            repchain = self.representative_structure.representative_chain
        single, fingerprint = g.protein.representative_sequence.sequence_mutation_summary()
        numstrains = len(self.sequences) - 1

        d['Gene ID'] = g.id
        d['Number of sequences'] = len(self.sequences)
        d['Number of structures (total)'] = self.num_structures
        d['Number of structures (experimental)'] = self.num_structures_experimental
        d['Number of structures (homology models)'] = self.num_structures_homology

        # d['------REPRESENTATIVE SEQUENCE PROPERTIES------')
        #     d['Sequence ID'] = repseq.id
        d['Sequence length'] = repseq.sequence_len
        d['Predicted number of transmembrane helices'] = repseq.seq_record.annotations['num_tm_helix-tmhmm']

        # d['------REPRESENTATIVE STRUCTURE PROPERTIES------')
        d['Structure ID'] = repstruct.id
        #     d['Structure representative chain'] = format(repchain.id)))
        d['Structure is experimental'] = repstruct.is_experimental
        # d['Structure origin'] = repstruct.taxonomy_name))
        # d['Structure description'] = repstruct.description))
        d['Structure coverage of sequence'] = str(repstruct.reference_seq_top_coverage) + '%'

        # d['------ALIGNMENTS SUMMARY------')
        #     d['Number of sequence alignments'] = len(repseq.sequence_alignments)))
        #     d['Number of structure alignments'] = len(repseq.structure_alignments)))

        singles = []
        for k, v in single.items():
            k = [str(x) for x in k]
            if len(v) / numstrains >= 0.01:
                singles.append(''.join(k))  # len(v) is the number of strains
        d['Mutations that show up in more than 10% of strains'] = ';'.join(singles)

        allfingerprints = []
        for k, v in fingerprint.items():
            if len(v) / numstrains >= 0.01:
                fingerprints = []
                for m in k:
                    y = [str(x) for x in m]
                    fingerprints.append(''.join(y))
                allfingerprints.append('-'.join(fingerprints))
        d['Mutation groups that show up in more than 10% of strains'] = ';'.join(allfingerprints)

        return d