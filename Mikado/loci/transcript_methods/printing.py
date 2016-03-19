"""
This module contains the methods related to creating the proper output lines for printing
GFFs/GTFs starting from the transcript class.
"""


from collections import Counter
import functools
from ...parsers.GTF import GtfLine
from ...parsers.GFF import GffLine
from ...parsers.bed12 import BED12
import intervaltree

__author__ = 'Luca Venturini'


def __create_cds_lines(transcript,
                       cds_run,
                       tid,
                       to_gtf=False, with_introns=False):

    """
    Private method to create the exon/UTR/CDS lines for printing
    out in GTF/GFF format.
    :param transcript: the transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript
    :param cds_run: the internal orf run we are preparing
    :param tid: name of the transcript
    :param to_gtf: boolean, indicates whether the lines should be GTF or GFF
    :param with_introns: boolean, if True introns will be added to the output
    we want GTF or GFF output
    :return:
    """

    exon_lines = []
    cds_begin = False
    counter = Counter()

    line_creator = functools.partial(__create_exon_line,
                                     transcript,
                                     **{"to_gtf": to_gtf,
                                        "tid": tid})

    if with_introns is True:
        cds_run = cds_run[:]
        for intron in transcript.introns:
            cds_run.append(("intron", intron))

    cds_run = sorted(cds_run, key=lambda segment: (segment[1][0],
                                                   segment[0].lower()))

    for segment in cds_run:
        try:
            exon_line, counter, cds_begin = line_creator(segment,
                                                         counter,
                                                         cds_begin)
        except IndexError:
            raise IndexError(cds_run)
        assert exon_line.start >= transcript.start, (transcript.start, segment, cds_run)
        assert exon_line.end <= transcript.end
        exon_lines.append(exon_line)

    # if to_gtf is False:
    #     exon_lines = [exon_line for exon_line in
    #                   __add_phase(transcript, exon_lines, first_phase=first_phase)]
    # else:
    #     exon_lines = [exon_line for exon_line in
    #                   __add_frame(transcript, exon_lines, first_phase=first_phase)]

    assert not any(True for x in exon_lines if x.feature == "CDS" and x.phase is None), [str(_) for _ in exon_lines]

    return [str(line) for line in exon_lines]


# pylint: disable=too-many-arguments
def __create_exon_line(transcript, segment, counter, cds_begin,
                       tid="", to_gtf=False):
    """
    Private method that creates an exon line for printing.
    :param transcript: the transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript

    :param segment: a segment of the form (feature, start, end)
    :type segment: list(str, intervaltree.Interval)

    :param counter: a Counter object that keeps track of how many exons,
    CDS, UTR segments we have already seen
    :type counter: Counter

    :param cds_begin: boolean flag that indicates whether the CDS has already begun
    :type cds_begin: bool

    :param tid: name of the transcript
    :param to_gtf: boolean flag

    :return: exon_line, counter, cds_begin
    :rtype: ((GtfLine | GffLine), Counter, bool)
    """

    if to_gtf is False:
        constructor = GffLine
        utr3_feature = "three_prime_UTR"
        utr5_feature = "five_prime_UTR"
    else:
        constructor = GtfLine
        utr3_feature = "3UTR"
        utr5_feature = "5UTR"

    assert segment[0] in ("UTR", "CDS", "exon", "intron"), segment

    phase = None
    if segment[0] == "UTR":
        if (cds_begin is True and transcript.strand == "-") or \
                (transcript.strand == "+" and cds_begin is False):
            feature = utr5_feature
            counter.update(["five"])
            index = counter["five"]
        else:
            feature = utr3_feature
            counter.update(["three"])
            index = counter["three"]
    elif segment[0] == "CDS":
        cds_begin = True
        counter.update(["CDS"])
        index = counter["CDS"]
        feature = "CDS"
        try:
            phase = segment[2]
        except IndexError:
            raise IndexError(segment)
    else:
        counter.update([segment[0]])
        index = counter[segment[0]]
        feature = segment[0]
    exon_line = constructor(None)

    for attr in ["chrom", "source", "strand"]:
        setattr(exon_line, attr, getattr(transcript, attr))

    exon_line.feature = feature
    exon_line.start, exon_line.end = segment[1][0], segment[1][1]
    exon_line.phase = phase

    exon_line.score = None
    if to_gtf is True:
        # noinspection PyPropertyAccess
        exon_line.gene = transcript.parent
        exon_line.transcript = tid
    else:
        exon_line.id = "{0}.{1}{2}".format(tid, feature, index)
        exon_line.parent = tid
    return exon_line, counter, cds_begin
# pylint: enable=too-many-arguments


def create_lines_cds(transcript, to_gtf=False, with_introns=False):

    """
    Method to create the GTF/GFF lines for printing in the presence of CDS information.
    WARNING: at the moment, the phase support is disabled.
    :param transcript: the transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript

    :param to_gtf: boolean, it indicates whether the output is GTF (True) or GFF3 (False)

    :param first_phase: number it indicates the phase of the first CDS exon. It defaults to 0.
    :param with_introns: boolean, if set to True, introns will be printed as well.
    :return:
    """

    if to_gtf is False:
        constructor = GffLine
    else:
        constructor = GtfLine

    lines = []
    transcript_counter = 0

    parent_line = constructor(None)
    if transcript.is_coding is False:
        lines = create_lines_no_cds(transcript, to_gtf=to_gtf)
    else:
        for index, cds_run in enumerate(transcript.internal_orfs):
            if transcript.number_internal_orfs > 1:
                transcript_counter += 1
                tid = "{0}.orf{1}".format(transcript.id, transcript_counter)

                if index == transcript.selected_internal_orf_index:
                    transcript.attributes["maximal"] = True
                else:
                    transcript.attributes["maximal"] = False
            else:
                tid = transcript.id
            cds_run = transcript.internal_orfs[index]

            for attr in ["chrom", "source", "feature", "start", "end",
                         "score", "strand", "attributes", "parent"]:
                setattr(parent_line, attr, getattr(transcript, attr))

            parent_line.phase = '.'

            parent_line.id = tid
            parent_line.name = transcript.id

            exon_lines = __create_cds_lines(transcript,
                                            cds_run,
                                            tid,
                                            to_gtf=to_gtf,
                                            with_introns=with_introns)

            lines.append(str(parent_line))
            lines.extend(exon_lines)
    return lines


def create_lines_bed(transcript):

    """
    Method to create a BED12 object for printing
    :param transcript: Mikado.py.loci.transcript.Transcript
    :return:
    """

    bed12 = BED12()
    bed12.transcriptomic = False
    bed12.header = False
    bed12.chrom = transcript.chrom
    bed12.start = transcript.start
    bed12.end = transcript.end
    bed12.name = transcript.id
    bed12.score = transcript.score
    bed12.strand = transcript.strand
    if transcript.is_coding:
        bed12.thick_start = transcript.combined_cds[0][0]
        bed12.thick_end = transcript.combined_cds[-1][1]
    else:
        bed12.thick_start = bed12.thick_end = bed12.start
    bed12.block_count = transcript.exon_num
    bed12.block_sizes = [exon.end - exon.begin + 1 for exon in transcript.exons]
    bed12.block_starts = [0]
    for pos, intron in enumerate(transcript.introns):
        bed12.block_starts.append(bed12.block_sizes[pos] + intron.end - intron.begin + 1)
    return str(bed12)


def __add_phase(transcript, exon_lines, first_phase=0):

    """
    Private method to add the phase to a transcript. The phase is defined as
    the reverse of the modulo 3 of the number of bases from the start.
    Or:

    (3 - (len(cds so far) % 3)) % 3

    Or (more verbose):

    modulo = len(cds so far) % 3
    if modulo == 0:
       phase = 0
    elif modulo == 1:
       phase = 2
    else:
       phase = 1

    :param transcript: the transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript

    :param exon_lines:
    :return:
    """

    # We start by 0 if no CDS loaded, else
    # we use the first phase

    previous = (3 - (first_phase % 3)) % 3

    new_lines = []
    for line in sorted(exon_lines, reverse=(transcript.strand == "-")):
        if line.feature == "CDS":
            phase = (3 - (previous % 3)) % 3
            line.phase = phase
            previous += len(line)
        new_lines.append(line)
    return sorted(new_lines)


def __add_frame(transcript, exon_lines, first_phase=0):

    """
    Private method to add the frame to a transcript. The frame is defined as
    the modulo 3 of the number of bases from the start.
    Or:

    len(cds so far) % 3

    In this library, the frame (correct definition for the field in GTF)
    is aliased as "phase".

    :param transcript: the transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript

    :param exon_lines:
    :return:
    """

    # We start by 0 if no CDS loaded, else
    # we use the first phase

    previous = first_phase % 3

    new_lines = []
    for line in sorted(exon_lines, reverse=(transcript.strand == "-")):
        if line.feature == "CDS":
            frame = previous % 3
            line.frame = frame
            previous += len(line)
        new_lines.append(line)
    return sorted(new_lines)


def create_lines_no_cds(transcript,
                        to_gtf=False):

    """
    Method to create the GTF/GFF lines for printing in the absence of CDS information.

    :param transcript: the Transcript instance
    :type transcript: mikado_lib.loci_objects.transcript.Transcript

    :param to_gtf: boolean, it indicates whether the output is GTF (True) or GFF3 (False)
    :type to_gtf: bool
    """

    if to_gtf is True:
        constructor = GtfLine
    else:
        constructor = GffLine

    parent_line = constructor(None)

    for attr in ["chrom", "source", "feature", "start", "end",
                 "score", "strand", "attributes", "parent"]:
        setattr(parent_line, attr, getattr(transcript, attr))

    parent_line.phase = '.'
    parent_line.id = transcript.id

    parent_line.name = transcript.name

    lines = [str(parent_line)]
    exon_lines = []

    exon_count = 0
    for exon in transcript.exons:
        exon_count += 1
        exon_line = constructor(None)
        for attr in ["chrom", "source", "strand", "attributes"]:
            setattr(exon_line, attr, getattr(transcript, attr))
        exon_line.feature = "exon"
        exon_line.start, exon_line.end = exon[0], exon[1]
        assert exon_line.start >= transcript.start
        assert exon_line.end <= transcript.end
        exon_line.score = None
        exon_line.phase = None

        exon_line.id = "{0}.{1}{2}".format(transcript.id, "exon", exon_count)
        exon_line.parent = transcript.id
        exon_line.name = transcript.name
        exon_lines.append(str(exon_line))

    lines.extend(exon_lines)
    return lines
