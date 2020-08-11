import collections
from ...parsers.bam_parser import BamParser
from ...exceptions import InvalidTranscript


def parse_prediction_bam(args, queue_logger, transmit_wrapper, constructor):

    transcript = None
    done = 0
    lastdone = 1
    __found_with_orf = set()
    name_counter = collections.Counter()  # This is needed for BAMs
    invalids = set()
    coord_list = None
    if args.prediction.__annot_type__ == BamParser.__annot_type__:
        for row in args.prediction:
            if row.is_unmapped is True:
                continue
            done, lastdone, coord_list, __found_with_orf = transmit_wrapper(transcript=transcript,
                                                                done=done,
                                                                            coord_list=coord_list,
                                                                lastdone=lastdone,
                                                                __found_with_orf=__found_with_orf)
            try:
                transcript = constructor(row, accept_undefined_multi=True, trust_orf=True)
            except (InvalidTranscript, AssertionError, TypeError, ValueError):
                queue_logger.warning("Row %s is invalid, skipping.", row)
                transcript = None
                invalids.add(row.id)
                continue
            if name_counter.get(row.query_name):
                name = "{}_{}".format(row.query_name, name_counter.get(row.query_name))
            else:
                name = row.query_name
            transcript.id = transcript.name = transcript.alias = name
            transcript.parent = transcript.attributes["gene_id"] = "{0}.gene".format(name)
    done, lastdone, coord_list, __found_with_orf = transmit_wrapper(
        transcript=transcript,
        done=done,
        coord_list=coord_list,
        lastdone=lastdone,
        __found_with_orf=__found_with_orf)

    return done, lastdone, coord_list

