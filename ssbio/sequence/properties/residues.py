from Bio.SeqUtils.ProtParam import ProteinAnalysis
import ssbio.utils
import subprocess
import logging
log = logging.getLogger(__name__)


def sequence_properties(seq_str):
    """Utiize Biopython's ProteinAnalysis module to return general sequence properties of an amino acid string.

    Args:
        seq_str: String representation of a amino acid sequence

    Returns:
        dict: Dictionary of sequence properties. Some definitions include:
        instability_index: Any value above 40 means the protein is unstable (has a short half life).
        secondary_structure_fraction: Percentage of protein in helix, turn or sheet

    TODO:
        Finish definitions of dictionary

    """

    analysed_seq = ProteinAnalysis(seq_str)

    info_dict = {}
    info_dict['amino_acids_content'] = analysed_seq.count_amino_acids()
    info_dict['amino_acids_percent'] = analysed_seq.get_amino_acids_percent()
    info_dict['length'] = analysed_seq.length
    info_dict['monoisotopic'] = analysed_seq.monoisotopic
    info_dict['molecular_weight'] = analysed_seq.molecular_weight()
    info_dict['aromaticity'] = analysed_seq.aromaticity()
    info_dict['instability_index'] = analysed_seq.instability_index()
    info_dict['flexibility'] = analysed_seq.flexibility()
    info_dict['isoelectric_point'] = analysed_seq.isoelectric_point()
    info_dict['secondary_structure_fraction'] = analysed_seq.secondary_structure_fraction()

    return info_dict


def emboss_pepstats_on_file(infile, outfile='', outdir='', outext='.pepstats', force_rerun=False):
    # Check if pepstats is installed
    if not ssbio.utils.program_exists('pepstats'):
        raise OSError('EMBOSS package not installed.')

    # Create the output file name
    outfile = ssbio.utils.outfile_name_maker(infile=infile, outfile=outfile, outdir=outdir, outext=outext)

    # Check for force rerunning
    if ssbio.utils.force_rerun(flag=force_rerun, outfile=outfile):
        cmd = 'pepstats -sequence="{}" -outfile="{}"'.format(infile, outfile)
        command = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = command.communicate()
        log.debug('{}: Ran EMBOSS pepstats'.format(infile))
    else:
        log.debug('{}: pepstats already exists')

    return outfile



#
# AAdict = {
#
#
# 'LYS': 'positive',
# 'ARG': 'positive',
# 'HIS': 'positive',
#
# 'ASP': 'negative',
# 'GLU': 'negative',
#
# 'LEU': 'nonpolar',
# 'TRP': 'nonpolar',
# 'VAL': 'nonpolar',
# 'PHE': 'nonpolar',
# 'PRO': 'nonpolar',
# 'ILE': 'nonpolar',
# 'GLY': 'nonpolar',
# 'ALA': 'nonpolar',
# 'MET': 'nonpolar',
#
# 'ASN': 'polar',
# 'THR': 'polar',
# 'TYR': 'polar',
# 'MSE': 'polar',
# 'SEC': 'polar',
# 'SER': 'polar',
# 'GLN': 'polar',
# 'CYS': 'polar',
# }
#
#
# def residue_props(seq_str):
#     """Return a dictionary of residue properties indicating the percentage of the respective property for a sequence.
#
#     Properties are: Polar, nonpolar, negative, positive.
#
#     Args:
#         pdb_file: PDB or MMCIF structure file
#
#     Returns:
#         dict: Dictonary of percentage (float) of properties
#     """
#
#     props = {}
#     polar = 0
#     nonpolar = 0
#     positive = 0
#     negative = 0
#     total = 0
#
#     for j in seq_str:
#         if j.resname in AAdict:
#             if AAdict[j.resname] == 'nonpolar':
#                 nonpolar = nonpolar + 1
#             elif AAdict[j.resname] == 'polar':
#                 polar = polar + 1
#             elif AAdict[j.resname] == 'positive':
#                 positive = positive + 1
#             elif AAdict[j.resname] == 'negative':
#                 negative = negative + 1
#             total = total + 1
#
#     props['ssb_per_NP'] = float(nonpolar) / float(total)
#     props['ssb_per_P'] = float(polar) / float(total)
#     props['ssb_per_pos'] = float(positive) / float(total)
#     props['ssb_per_neg'] = float(negative) / float(total)
#
#     return props