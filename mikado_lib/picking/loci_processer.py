from multiprocessing import Process
from multiprocessing.managers import AutoProxy
import logging
import logging.handlers as logging_handlers
import functools
from ..utilities import dbutils
from ..loci_objects.superlocus import Superlocus
from ..parsers.GFF import GffLine
import collections
import csv
import re
import sys

__author__ = 'Luca Venturini'


def merge_partial(filenames, handle):

    """This function merges the partial files created by the multiprocessing into a single
    sorted file."""

    current_lines = collections.defaultdict(list)
    filenames = set([open(_) for _ in filenames])
    while len(filenames) > 0:
        finished = set()
        for _ in filenames:
            try:
                line = next(_)
                _ = line.split("/")
                current_lines[int(_[0])].append("/".join(_[1:]))

            except StopIteration:
                _.close()
                finished.add(_)

        # assert len(current_lines) > 0 or len(finished) == len(filenames)
        # if len(current_lines) > 0:
        #     current = min(current_lines.keys())
        #     for line in current_lines[current]:
        #         print(line, file=handle, end='')
        #         current_lines[current].remove(line)
        #     del current_lines[current]
        for _ in finished:
            filenames.remove(_)

    while len(current_lines) > 0:
        current = min(current_lines.keys())
        for line in current_lines[current]:
            print(line, file=handle, end="")
        del current_lines[current]

    return


def print_gene(current_gene, gene_counter, handle, prefix):

    print(current_gene["gene"], file=handle)
    chrom = current_gene["gene"].chrom
    primaries = [_ for _ in current_gene["transcripts"] if
                 current_gene["transcripts"][_]["primary"] is True]
    assert len(primaries) == 1 or all([".orf" in _ for _ in primaries]), current_gene
    for primary in sorted(primaries):
        tid = "{0}.{1}G{2}.1".format(prefix, chrom, gene_counter)
        if ".orf" in primary:
            tid = "{0}{1}".format(tid,
                                  primary[primary.find(".orf"):])
        else:
            assert len(primaries) == 1
        current_transcript = current_gene["transcripts"][primary]["transcript"]
        current_transcript.parent = current_gene["gene"].id
        current_exons = current_gene["transcripts"][primary]["exons"]
        current_transcript.attributes["Alias"] = current_transcript.id[:]
        current_transcript.id = tid
        print(current_transcript, file=handle)
        for exon in current_exons:
            exon.parent = tid
            exon.id = re.sub(current_transcript.attributes["Alias"],
                             tid, exon.id)
            exon.name = re.sub(current_transcript.attributes["Alias"],
                               tid, exon.id)
            print(exon, file=handle)

    others = [_ for _ in current_gene["transcripts"] if _ not in primaries]

    others = sorted(others,
                    key=lambda _:
                    (current_gene["transcripts"][_]["transcript"].start,
                     current_gene["transcripts"][_]["transcript"].end))
    # transcript_counter = 1

    for other in others:
        name = re.sub("\.orf[0-9]+", "", other)
        current_transcript = current_gene["transcripts"][other]["transcript"]
        # Get the original transcript counter
        try:
            first = re.sub("{0}\.".format(current_transcript.parent[0]), "", other)
            transcript_counter = int(re.sub("\.orf[0-9]+", "", first))
        except ValueError:
            assert isinstance(current_transcript.parent, list),\
                type(current_transcript.parent)
            raise
        assert transcript_counter > 1

        tid = "{0}.{1}G{2}.{3}".format(prefix,
                                       chrom,
                                       gene_counter,
                                       transcript_counter)
        if ".orf" in other:
            tid = "{0}{1}".format(tid,
                                  other[other.find(".orf"):])

        current_transcript.parent = current_gene["gene"].id
        current_exons = current_gene["transcripts"][other]["exons"]
        current_transcript.attributes["Alias"] = current_transcript.id[:]
        current_transcript.id = tid
        print(current_transcript, file=handle)
        for exon in current_exons:
            exon.parent = tid
            exon.id = re.sub(current_transcript.attributes["Alias"],
                             tid, exon.id)
            exon.name = re.sub(current_transcript.attributes["Alias"],
                               tid, exon.id)
            print(exon, file=handle)
    print("###", file=handle)


def merge_loci(filenames, handle, prefix=""):

    current_lines = collections.defaultdict(list)
    filenames = set([open(_) for _ in filenames])
    while len(filenames) > 0:
        finished = set()
        for _ in filenames:
            try:
                line = next(_)
                _ = line.split("/")
                current_lines[int(_[0])].append(GffLine("/".join(_[1:])))

            except StopIteration:
                _.close()
                finished.add(_)

        for _ in finished:
            filenames.remove(_)

    gene_counter = 0
    current_chrom = None
    while len(current_lines) > 0:
        current = min(current_lines.keys())
        current_gene = dict()
        for line in current_lines[current]:
            if line.header is True:
                if "###" not in line._line and line._line != "NA":
                    print(line, file=handle)
                continue
            if current_chrom is not None and current_chrom != line.chrom:
                gene_counter = 0
            if line.is_gene:
                if current_gene != dict():
                    # Print out
                    print_gene(current_gene, gene_counter, handle, prefix)
                    current_gene = dict()
                    pass
                current_gene["transcripts"] = dict()
                gene_counter += 1
                line.id = "{0}.{1}G{2}".format(prefix, line.chrom, gene_counter)
                current_gene["gene"] = line
                # current_gene = line.id
            elif line.is_transcript:
                assert current_gene is not None
                # line.parent = current_gene
                current_gene["transcripts"][line.id] = dict()
                current_gene["transcripts"][line.id]["transcript"] = line
                current_gene["transcripts"][line.id]["exons"] = []
                if line.attributes["primary"].lower() in ("true", "false"):
                    primary = eval(line.attributes["primary"])
                else:
                    raise ValueError("Invalid value for \"primary\" field: {0}".format(
                        line.attributes["primary"]
                    ))

                current_gene["transcripts"][line.id]["primary"] = primary
            elif line.is_exon:
                for parent in line.parent:
                    assert parent in current_gene["transcripts"]
                    current_gene["transcripts"][parent]["exons"].append(line)
            else:
                print(line, file=handle)
                continue
        if current_gene != dict():
            print_gene(current_gene, gene_counter, handle, prefix)

        del current_lines[current]

    return


def remove_fragments(stranded_loci, json_conf, logger):

    """This method checks which loci are possible fragments, according to the
    parameters provided in the configuration file, and tags/remove them according
    to the configuration specification.

    :param stranded_loci: a list of the loci to consider for fragment removal
    :type stranded_loci: list[Superlocus]

    :param json_conf: the configuration dictionary
    :type json_conf: dict

    :param logger: the logger
    :type logger: logging.Logger

    """

    loci_to_check = {True: set(), False: set()}
    for stranded_locus in stranded_loci:
        for _, locus_instance in stranded_locus.loci.items():
            locus_instance.logger = logger
            loci_to_check[locus_instance.monoexonic].add(locus_instance)

    mcdl = json_conf["pick"]["run_options"]["fragments_maximal_cds"]
    bool_remove_fragments = json_conf["pick"]["run_options"]["remove_overlapping_fragments"]
    for stranded_locus in stranded_loci:
        to_remove = set()
        for locus_id, locus_instance in stranded_locus.loci.items():
            if locus_instance in loci_to_check[True]:
                logger.debug("Checking if %s is a fragment", locus_instance.id)

                for other_locus in loci_to_check[False]:
                    if other_locus.other_is_fragment(locus_instance,
                                                     minimal_cds_length=mcdl) is True:
                        if bool_remove_fragments is False:
                            # Just mark it as a fragment
                            stranded_locus.loci[locus_id].is_fragment = True
                        else:
                            to_remove.add(locus_id)
                            # del stranded_locus.loci[locus_id]
                        break
        for locus_id in to_remove:
            del stranded_locus.loci[locus_id]
        yield stranded_locus


def analyse_locus(slocus: Superlocus,
                  counter: int,
                  json_conf: dict,
                  printer_queue: [AutoProxy, None],
                  logging_queue: AutoProxy,
                  engine=None,
                  data_dict=None) -> [Superlocus]:

    """
    :param slocus: a superlocus instance
    :type slocus: mikado_lib.loci_objects.superlocus.Superlocus

    :param counter: an integer which is used to create the proper name for the locus.
    :type counter: int

    :param json_conf: the configuration dictionary
    :type json_conf: dict

    :param logging_queue: the logging queue
    :type logging_queue: multiprocessing.managers.AutoProxy

    :param printer_queue: the printing queue
    :type printer_queue: multiprocessing.managers.AutoProxy

    :param engine: an optional engine to connect to the database.
    :type data_dict: sqlalchemy.engine.engine

    :param data_dict: a dictionary of preloaded data
    :type data_dict: (None|dict)

    This function takes as input a "superlocus" instance and the pipeline configuration.
    It also accepts as optional keywords a dictionary with the CDS information
    (derived from a Bed12Parser) and a "lock" used for avoiding writing collisions
    during multithreading.
    The function splits the superlocus into its strand components and calls the relevant methods
    to define the loci.
    When it is finished, it transmits the superloci to the printer function.
    """

    # Define the logger
    if slocus is None:
        # printer_dict[counter] = []
        if printer_queue:
            while printer_queue.qsize() >= json_conf["pick"]["run_options"]["threads"] * 10:
                continue
            # printer_queue.put_nowait(([], counter))
            return
        else:
            return []

    handler = logging_handlers.QueueHandler(logging_queue)
    logger = logging.getLogger("{0}:{1}-{2}".format(
        slocus.chrom, slocus.start, slocus.end))
    logger.addHandler(handler)

    # We need to set this to the lowest possible level,
    # otherwise we overwrite the global configuration
    logger.setLevel(json_conf["log_settings"]["log_level"])
    logger.propagate = False
    logger.debug("Started with %s, counter %d",
                 slocus.id, counter)
    if slocus.stranded is True:
        logger.warn("%s is stranded already! Resetting",
                    slocus.id)
        slocus.stranded = False

    slocus.logger = logger
    slocus.source = json_conf["pick"]["output_format"]["source"]

    try:
        slocus.load_all_transcript_data(engine=engine,
                                        data_dict=data_dict)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        logger.error("Error while loading data for %s", slocus.id)
        logger.exception(exc)
    logger.debug("Loading transcript data for %s", slocus.id)

    # Load the CDS information if necessary
    if slocus.initialized is False:
        # This happens when all transcripts have been removed from the locus,
        # due to errors that have been hopefully logged
        logger.warning(
            "%s had all transcripts failing checks, ignoring it",
            slocus.id)
        # printer_dict[counter] = []
        if printer_queue:
            while printer_queue.qsize >= json_conf["pick"]["run_options"]["threads"] * 10:
                continue
            # printer_queue.put_nowait(([], counter))
            return
        else:
            return []

    # Split the superlocus in the stranded components
    logger.debug("Splitting by strand")
    stranded_loci = sorted(list(slocus.split_strands()))
    # Define the loci
    logger.debug("Divided into %d loci", len(stranded_loci))

    for stranded_locus in stranded_loci:
        try:
            stranded_locus.define_loci()
        except KeyboardInterrupt:
            raise
        except OSError:
            raise
        except Exception as exc:
            logger.exception(exc)
            logger.error("Removing failed locus %s", stranded_locus.name)
            stranded_loci.remove(stranded_locus)
        logger.debug("Defined loci for %s:%f-%f, strand: %s",
                     stranded_locus.chrom,
                     stranded_locus.start,
                     stranded_locus.end,
                     stranded_locus.strand)

    # Remove overlapping fragments.
    loci_to_check = {True: set(), False: set()}
    for stranded_locus in stranded_loci:
        for _, locus_instance in stranded_locus.loci.items():
            locus_instance.logger = logger
            loci_to_check[locus_instance.monoexonic].add(locus_instance)

    # Check if any locus is a fragment, if so, tag/remove it
    stranded_loci = sorted(list(remove_fragments(stranded_loci, json_conf, logger)))
    try:
        logger.debug("Size of the loci to send: {0}, for {1} loci".format(
            sys.getsizeof(stranded_loci),
            len(stranded_loci)))
    except Exception as err:
        logger.error(err)
        pass
    # printer_dict[counter] = stranded_loci
    if printer_queue:
        while printer_queue.qsize() >= json_conf["pick"]["run_options"]["threads"] * 10:
            continue
        # printer_queue.put_nowait((stranded_loci, counter))
        # printer_queue.put((stranded_loci, counter))
        logger.debug("Finished with %s, counter %d", slocus.id, counter)
        logger.removeHandler(handler)
        handler.close()
        return
    else:
        logger.debug("Finished with %s, counter %d", slocus.id, counter)
        logger.removeHandler(handler)
        handler.close()
        return stranded_loci


class LociProcesser(Process):

    """This process class takes care of getting from the queue the loci,
    analyse them, and print them to the output files."""

    def __init__(self,
                 json_conf,
                 data_dict,
                 output_files,
                 locus_queue,
                 logging_queue,
                 identifier
                 ):

        # current_counter, gene_counter, current_chrom = shared_values
        super(LociProcesser, self).__init__()
        self.logging_queue = logging_queue
        self.__identifier = identifier  # Property directly unsettable
        self.name = "LociProcesser-{0}".format(self.identifier)
        self.json_conf = json_conf
        self.handler = logging_handlers.QueueHandler(self.logging_queue)
        self.logger = logging.getLogger(self.name)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(self.json_conf["log_settings"]["log_level"])
        self.logger.propagate = False

        self.__data_dict = data_dict
        self.locus_queue = locus_queue
        # self.lock = lock
        self.__output_files = output_files
        self.locus_metrics, self.locus_scores, self.locus_out = [None] * 3
        self.sub_metrics, self.sub_scores, self.sub_out = [None] * 3
        self.monolocus_out = None
        self._handles = []
        self._create_handles(self.__output_files)
        self.__gene_counter = 0
        assert self.locus_out is not None
        self.logger.debug("Starting Process %s", self.name)

        self.logger.debug("Starting the pool for {0}".format(self.name))
        try:
            if self.json_conf["pick"]["run_options"]["preload"] is False:
                self.engine = dbutils.connect(self.json_conf, self.logger)
            else:
                self.engine = None
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise
        except Exception as exc:
            self.logger.exception(exc)
            return
        self.analyse_locus = functools.partial(analyse_locus,
                                               printer_queue=None,
                                               json_conf=self.json_conf,
                                               data_dict=self.__data_dict,
                                               engine=self.engine,
                                               logging_queue=self.logging_queue)

    @property
    def identifier(self):
        return self.__identifier

    def __getstate__(self):

        state = self.__dict__.copy()
        for h in state["_handles"]:
            h.close()

        state["_handles"] = []

        for name in ["locus_metrics", "locus_scores", "locus_out",
                     "sub_metrics", "sub_scores", "sub_out", "monolocus_out"]:
            state[name] = None
        state["engine"] = None
        state["analyse_locus"] = None
        del state["handler"]
        del state["logger"]
        return state

    def __setstate__(self, state):

        self.__dict__.update(state)
        self.handler = logging_handlers.QueueHandler(self.logging_queue)
        self.logger = logging.getLogger(self.name)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(self.json_conf["log_settings"]["log_level"])
        self.logger.propagate = False

        self._create_handles(self.__output_files)
        if self.json_conf["pick"]["run_options"]["preload"] is False:
            self.engine = dbutils.connect(self.json_conf, self.logger)
        else:
            self.engine = None
        self.analyse_locus = functools.partial(analyse_locus,
                                               printer_queue=None,
                                               json_conf=self.json_conf,
                                               data_dict=self.__data_dict,
                                               engine=self.engine,
                                               logging_queue=self.logging_queue)

    def _create_handles(self, handles):

        (locus_metrics_file,
         locus_scores_file,
         locus_out_file) = ["{0}-{1}".format(_, self.identifier) for _ in handles[0]]
        locus_metrics_file = open(locus_metrics_file, "w")
        locus_scores_file = open(locus_scores_file, "w")

        score_keys = ["tid", "parent", "score"]
        score_keys += sorted(list(self.json_conf["scoring"].keys()))
        # Define mandatory output files

        self.locus_metrics = csv.DictWriter(
            locus_metrics_file,
            Superlocus.available_metrics,
            delimiter="\t")

        self.locus_scores = csv.DictWriter(locus_scores_file, score_keys, delimiter="\t")

        self.locus_metrics.handle = locus_metrics_file
        self.locus_metrics.flush = self.locus_metrics.handle.flush
        self.locus_metrics.close = self.locus_metrics.handle.close
        self.locus_scores.handle = locus_scores_file
        self.locus_scores.flush = self.locus_scores.handle.flush
        self.locus_scores.close = self.locus_scores.handle.close

        self.locus_out = open(locus_out_file, 'w')
        self._handles.extend((self.locus_out, self.locus_metrics, self.locus_out))

        (sub_metrics_file,
         sub_scores_file,
         sub_out_file) = ["{0}-{1}".format(_, self.identifier) for _ in handles[1]]
        if sub_metrics_file:
            sub_metrics_file = open(sub_metrics_file, "w")
            sub_scores_file = open(sub_scores_file, "w")
            self.sub_metrics = csv.DictWriter(
                sub_metrics_file,
                Superlocus.available_metrics,
                delimiter="\t")
            self.sub_metrics.handle = sub_metrics_file
            self.sub_metrics.flush = self.sub_metrics.handle.flush
            self.sub_metrics.close = self.sub_metrics.handle.close
            self.sub_scores = csv.DictWriter(
                sub_scores_file, score_keys, delimiter="\t")
            self.sub_scores.handle = sub_scores_file
            self.sub_scores.flush = self.sub_scores.handle.flush
            self.sub_scores.close = self.sub_scores.handle.close
            self.sub_out = open(sub_out_file, "w")
            self._handles.extend([self.sub_metrics, self.sub_scores, self.sub_out])
        monolocus_out_file = "{0}-{1}".format(handles[2], self.identifier)
        if monolocus_out_file:
            self.monolocus_out = open(monolocus_out_file, "w")
            self._handles.append(self.monolocus_out)

        return

    def run(self):
        """Start polling the queue, analyse the loci, and send them to the printer process."""
        self.logger.debug("Starting to parse data for {0}".format(self.name))
        exit_received = False
        current_chrom = None
        while True:
            if exit_received is False:
                slocus, counter = self.locus_queue.get()
                if slocus == "EXIT":
                    self.logger.debug("EXIT received for %s", self.name)
                    self.locus_queue.put((slocus, counter))
                    exit_received = True
                    if self.engine is not None:
                        self.engine.dispose()
                    self.locus_out.close()
                    self.locus_scores.close()
                    self.locus_metrics.close()
                    if self.sub_metrics is not None:
                        self.sub_metrics.close()
                        self.sub_scores.close()
                        self.sub_out.close()
                    if self.monolocus_out is not None:
                        self.monolocus_out.close()

                    return
                else:
                    if slocus is not None:
                        if current_chrom != slocus.chrom:
                            self.__gene_counter = 0
                            current_chrom = slocus.chrom
                        stranded_loci = self.analyse_locus(slocus, counter)
                    else:
                        stranded_loci = []
                    for stranded_locus in stranded_loci:
                        self._print_locus(stranded_locus, counter)

    def _print_locus(self, stranded_locus, counter):

        """
        Private method that handles a single superlocus for printing.
        It also detects and flags/discard fragmentary loci.
        :param stranded_locus: the stranded locus to analyse
        :return:
        """

        if self.sub_out != '':  # Skip this section if no sub_out is defined
            sub_lines = stranded_locus.__str__(
                level="subloci",
                print_cds=not self.json_conf["pick"]["run_options"]["exclude_cds"])
            if sub_lines != '':
                sub_lines = "\n".join(
                    ["{0}/{1}".format(counter, line) for line in sub_lines.split("\n")])
                print(sub_lines, file=self.sub_out)
                # sub_out.flush()
            sub_metrics_rows = [x for x in stranded_locus.print_subloci_metrics()
                                if x != {} and "tid" in x]
            sub_scores_rows = [x for x in stranded_locus.print_subloci_scores()
                               if x != {} and "tid" in x]
            for row in sub_metrics_rows:
                row["tid"] = "{0}/{1}".format(counter, row["tid"])
                self.sub_metrics.writerow(row)
                # sub_metrics.flush()
            for row in sub_scores_rows:
                row["tid"] = "{0}/{1}".format(counter, row["tid"])
                self.sub_scores.writerow(row)
                # sub_scores.flush()
        if self.monolocus_out != '':
            mono_lines = stranded_locus.__str__(
                level="monosubloci",
                print_cds=not self.json_conf["pick"]["run_options"]["exclude_cds"])
            if mono_lines != '':
                mono_lines = "\n".join(
                    ["{0}/{1}".format(counter, line) for line in mono_lines.split("\n")])
                print(mono_lines, file=self.monolocus_out)
                # mono_out.flush()
        locus_metrics_rows = [x for x in stranded_locus.print_monoholder_metrics()
                              if x != {} and "tid" in x]
        locus_scores_rows = [x for x in stranded_locus.print_monoholder_scores()]

        assert len(locus_metrics_rows) == len(locus_scores_rows)

        for locus in stranded_locus.loci:
            fragment_test = (
                self.json_conf["pick"]["run_options"]["remove_overlapping_fragments"]
                is True and stranded_locus.loci[locus].is_fragment is True)

            if fragment_test is True:
                continue
            self.__gene_counter += 1
            new_id = "{0}.{1}G{2}".format(
                self.json_conf["pick"]["output_format"]["id_prefix"],
                stranded_locus.chrom, self.__gene_counter)
            stranded_locus.loci[locus].id = new_id

        locus_lines = stranded_locus.__str__(
            print_cds=not self.json_conf["pick"]["run_options"]["exclude_cds"])
        for row in locus_metrics_rows:
            row["tid"] = "{0}/{1}".format(counter, row["tid"])
            self.locus_metrics.writerow(row)
            # locus_metrics.flush()
        for row in locus_scores_rows:
            row["tid"] = "{0}/{1}".format(counter, row["tid"])
            self.locus_scores.writerow(row)
            # self.locus_scores.flush()

        if locus_lines != '':
            locus_lines = "\n".join(
                    ["{0}/{1}".format(counter, line) for line in locus_lines.split("\n")])
            print(locus_lines, file=self.locus_out)
            # locus_out.flush()
