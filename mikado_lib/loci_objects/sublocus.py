# coding: utf-8

"""
The Sublocus class is the first to be invoked during the Mikado pick analysis. Each of these containers
holds transcripts which either are monoexonic and overlapping, or multiexonic and with at least an intron
in common.
"""

from mikado_lib.loci_objects.excluded import Excluded
from mikado_lib.loci_objects.abstractlocus import Abstractlocus
from mikado_lib.loci_objects.monosublocus import Monosublocus
from mikado_lib.loci_objects.transcript import Transcript
from mikado_lib.parsers.GFF import GffLine


class Sublocus(Abstractlocus):
    """
    The sublocus class is created either by the superlocus class during
    the subloci definition, or directly using a G(T|F)line-like object.
    It is used to define the monosubloci.
    """

    __name__ = "sublocus"
    available_metrics = Transcript.get_available_metrics()

    # ############### Class special methods ##############

    def __init__(self, span, json_dict=None, logger=None):

        """
        :param span: an instance which describes a genomic interval
        :type span: Transcript | Abstractlocus

        :param json_dict: a configuration dictionary
        :type json_dict: dict

        :param logger: a logger instance from the logging library
        :type logger: logging.Logger | None

        This class takes as input a "span" feature - e.g. a GffLine or a transcript_instance.
        The span instance should therefore have such attributes as chrom, strand, start, end, attributes.
        """

        self.counter = 0  # simple tag for avoiding collisions in the GFF output
        self.__splitted = False
        super().__init__()
        self.logger = logger
        self.json_dict = json_dict
        self.fixedSize = True if span.feature == "sublocus" else False
        if span.__name__ == "transcript":
            span.finalize()
        self.purge = self.json_dict["run_options"]["purge"]
        self.source = self.json_dict["source"]

        self.excluded = None
        self.splitted = False
        self.metrics_calculated = False  # Flag to indicate that we have not calculated the metrics for the transcripts
        self.scores_calculated = False  # Flag to indicate that we have not calculated the scores for the transcripts
        setattr(self, "monoexonic", getattr(span, "monoexonic", None))
        if json_dict is None or type(json_dict) is not dict:
            raise ValueError("I am missing the configuration for prioritizing transcripts!")
        self.locus_verified_introns = set()

        # This part is necessary to import modules
        if "modules" in self.json_dict:
            import importlib
            for mod in self.json_dict["modules"]:
                globals()[mod] = importlib.import_module(mod)

        if type(span) is Transcript:
            self.add_transcript_to_locus(span)
        else:
            self.parent = getattr(span, "parent")
            self.chrom = getattr(span, "chrom")
            self.start = getattr(span, "start")
            self.end = getattr(span, "end")
            self.strand = getattr(span, "strand")
            self.attributes = getattr(span, "attributes")

        self.monosubloci = []
        self.logger.debug("Initialized {0}".format(self.id))
        self.scores = dict()

    def __str__(self, print_cds=True):

        lines = []

        self_line = GffLine('')
        self.feature = self.__name__
        for attr in ["chrom", 'feature', 'source', 'start', 'end', 'strand']:
            setattr(self_line, attr, getattr(self, attr))
        self_line.phase, self_line.score = None, None
        self_line.id = "{0}_{1}".format(self.source, self.id)
        self_line.name = self.name
        self_line.parent = self.parent
        self_line.attributes["multiexonic"] = (not self.monoexonic)
        lines.append(str(self_line))

        for tid in sorted(self.transcripts, key=lambda ttid: self.transcripts[ttid]):
            self.transcripts[tid].source = self.source
            self.transcripts[tid].parent = self_line.id
            lines.append(self.transcripts[tid].__str__(print_cds=print_cds).rstrip())

        return "\n".join(lines)

    # ########## Class instance methods #####################

    def add_transcript_to_locus(self, transcript: Transcript, **kwargs):

        """
        :param transcript: the transcript which might be putatively added to the Locus.
        :type transcript: Transcript

        :param kwargs: eventual keyword arguments are ignored.

        This is an override of the original method, as at the sublocus stage
        we need to accomplish a couple of things more:
        - check that transcripts added to the sublocus are either all monoexonic or all multiexonic
        - change the id of the transcripts to  
        """

        if len(self.transcripts) > 0:

            self.logger.debug("Adding {0} to {1}".format(transcript.id, self.id))
        else:
            self.logger.debug("Initializing sublocus with {0} at {1}{2}:{3}-{4}".format(transcript.id,
                                                                                        transcript.chrom,
                                                                                        transcript.strand,
                                                                                        transcript.start,
                                                                                        transcript.end))

        if transcript is None:
            return
        if self.initialized is False:
            self.monoexonic = transcript.monoexonic
        elif self.monoexonic != transcript.monoexonic:
            raise ValueError(
                "Sublocus and transcript are not compatible!\n{0}\t{1}\t{2}\t{3}\t{4}\n{5}".format(self.chrom,
                                                                                                   self.start,
                                                                                                   self.end,
                                                                                                   self.strand,
                                                                                                   self.monoexonic,
                                                                                                   Transcript))

        super().add_transcript_to_locus(transcript)
        # add the verified introns from the outside
        self.locus_verified_introns = set.union(self.locus_verified_introns, transcript.verified_introns)
        self.logger.debug("Added {0} to {1}".format(transcript.id, self.id))
        # Update the id

    def define_monosubloci(self, purge=False, excluded=None):
        """
        :param purge: a flag which indicates whether loci whose best transcript has a score of 0 should
        be excluded (True) or retained (False)
        :type purge: bool

        :param excluded: the excluded Locus to which transcripts from purged loci will be added to
        :type excluded: None
        :type excluded: mikado_lib.loci_objects.excluded.Excluded

        This function retrieves the best non-overlapping transcripts inside the sublocus, according to the score
        calculated by calculate_scores (explicitly called inside the method).
        The "excluded" keyword must contain either None or a MonosublocusHolder object. It is used to contain
        transcripts that must self.blast_hits = []be excluded from the Locus due to unmet requirements.
        """

        self.monosubloci = []
        self.excluded = excluded
        self.logger.debug("Launching calculate scores for {0}".format(self.id))
        self.calculate_scores()

        self.logger.debug("Defining monosubloci for {0}".format(self.id))

        transcript_graph = self.define_graph(self.transcripts, inters=self.is_intersecting)

        while len(transcript_graph) > 0:
            cliques, communities = self.find_communities(transcript_graph)
            to_remove = set()
            for msbl in communities:
                msbl = dict((x, self.transcripts[x]) for x in msbl)
                selected_tid = self.choose_best(msbl)
                selected_transcript = self.transcripts[selected_tid]
                to_remove.add(selected_tid)
                for clique in cliques:
                    if selected_tid in cliques:
                        to_remove.update(clique)
                if purge is False or selected_transcript.score > 0:
                    new_locus = Monosublocus(selected_transcript, logger=self.logger)
                    self.monosubloci.append(new_locus)
            if len(to_remove) < 1:
                message = "No transcripts to remove from the pool for {0}\n".format(self.id)
                message += "Transcripts remaining: {0}".format(communities)
                exc = ValueError(message)
                self.logger.exception(exc)
                raise exc
            self.logger.debug("Removing {0} from transcripts for {1}".format(len(to_remove), self.id))
            transcript_graph.remove_nodes_from(to_remove)
        self.logger.debug("Defined monosubloci for {0}".format(self.id))
        self.splitted = True
        self.logger.debug("Defined monosubloci for {0}".format(self.id))
        return

    def calculate_metrics(self, tid: str):
        """
        :param tid: the name of the transcript to be analysed
        :type tid: str

        This function will calculate the metrics for a transcript which are relative in nature
        i.e. that depend on the other transcripts in the sublocus. Examples include the fraction
        of introns or exons in the sublocus, or the number/fraction of retained introns.  
        """

        self.logger.debug("Calculating metrics for {0}".format(tid))
        transcript_instance = self.transcripts[tid]
        self.transcripts[tid].finalize()  # The transcript must be finalized before we can calculate the score.

        self.transcripts[tid].exon_fraction = len(set.intersection(self.exons, self.transcripts[tid].exons)) / len(
            self.exons)

        if len(self.introns) > 0:
            transcript_instance.intron_fraction = len(
                set.intersection(transcript_instance.introns, self.introns)) / len(self.introns)
        else:
            transcript_instance.intron_fraction = 0
        if len(self.selected_cds_introns) > 0:
            transcript_instance.selected_cds_intron_fraction = len(
                set.intersection(transcript_instance.selected_cds_introns, set(self.selected_cds_introns))) / len(
                self.selected_cds_introns)
        else:
            transcript_instance.selected_cds_intron_fraction = 0

        if len(self.combined_cds_introns) > 0:
            transcript_instance.combined_cds_intron_fraction = len(
                set.intersection(set(transcript_instance.combined_cds_introns), set(self.combined_cds_introns))) / len(
                self.combined_cds_introns)
        else:
            transcript_instance.combined_cds_intron_fraction = 0

        self.find_retained_introns(transcript_instance)
        transcript_instance.retained_fraction = sum(
            e[1] - e[0] + 1 for e in transcript_instance.retained_introns) / transcript_instance.cdna_length
        if len(self.locus_verified_introns) > 0:
            transcript_instance.proportion_verified_introns_inlocus = len(
                set.intersection(transcript_instance.verified_introns, self.locus_verified_introns)) / len(
                self.locus_verified_introns)
        else:
            transcript_instance.proportion_verified_introns_inlocus = 0
        self.transcripts[tid] = transcript_instance
        self.logger.debug("Calculated metrics for {0}".format(tid))

    def find_retained_introns(self, transcript):

        """This method checks the number of exons that are possibly retained introns for a given transcript.
        To perform this operation, it checks for each non-CDS exon whether it exists a sublocus intron that
        is *completely* contained within a transcript exon. Such non-CDS exons must be *after* the
        CDS start; a retained intron should contain a premature stop codon, not a delayed start. 
        CDS exons are ignored because their retention might be perfectly valid.
        The results are stored inside the transcript instance, in the "retained_introns" tuple.

        :param transcript: a Transcript instance
        :type transcript: Transcript
        """

        transcript.retained_introns = []

        if transcript.strand == "+":
            filtering = filter(lambda e: e not in transcript.non_overlapping_cds and
                               e[0] >= transcript.combined_cds_start,
                               transcript.exons
                               )
        else:
            filtering = filter(lambda e: e not in transcript.non_overlapping_cds and
                               e[1] <= transcript.combined_cds_start,
                               transcript.exons
                               )
        for exon in filtering:
            # Check that the overlap is at least as long as the minimum between the exon and the intron.
            if any(filter(
                    lambda junction: self.overlap(exon, junction) >= junction[1] - junction[0],
                    self.combined_cds_introns
            )) is True:
                transcript.retained_introns.append(exon)
        transcript.retained_introns = tuple(transcript.retained_introns)

    def load_scores(self, scores):
        """
        :param scores: an external dictionary with scores
        :type scores: dict

        Simple mock function to load scores for the transcripts from an external dictionary.
        """

        for tid in self.transcripts:
            if tid in scores:
                self.transcripts[tid].score = scores[tid]
            else:
                self.transcripts[tid].score = 0

    def calculate_scores(self):
        """
        Function to calculate a score for each transcript, given the metrics derived
        with the calculate_metrics method and the scoring scheme provided in the JSON configuration.
        If any requirements have been specified, all transcripts which do not pass them
        will be assigned a score of 0 and subsequently ignored.
        Scores are rounded to the nearest integer.
        """

        if self.scores_calculated is True:
            return

        self.get_metrics()
        not_passing = set()
        if not hasattr(self, "logger"):
            self.logger = None
            self.logger.setLevel("DEBUG")
        self.logger.debug("Calculating scores for {0}".format(self.id))
        if "requirements" in self.json_dict:
            self.json_dict["requirements"]["compiled"] = compile(self.json_dict["requirements"]["expression"], "<json>",
                                                                 "eval")
            previous_not_passing = set()
            while True:
                not_passing = set()
                for tid in filter(lambda t: t not in previous_not_passing, self.transcripts):
                    evaluated = dict()
                    for key in self.json_dict["requirements"]["parameters"]:
                        value = getattr(self.transcripts[tid],
                                        self.json_dict["requirements"]["parameters"][key]["name"])
                        evaluated[key] = self.evaluate(value, self.json_dict["requirements"]["parameters"][key])
                    if eval(self.json_dict["requirements"]["compiled"]) is False:
                        not_passing.add(tid)
                if len(not_passing) == 0:
                    break

                for tid in not_passing:
                    self.transcripts[tid].score = 0
                    if self.purge is True:
                        self.metrics_calculated = False
                        if self.excluded is None:
                            excluded = Monosublocus(self.transcripts[tid], logger=self.logger)
                            self.excluded = Excluded(excluded)
                        else:
                            self.excluded.add_transcript_to_locus(self.transcripts[tid])
                        self.remove_transcript_from_locus(tid)
                if len(self.transcripts) == 0:
                    return
                else:
                    # Recalculate the metrics
                    self.get_metrics()

                previous_not_passing = not_passing.copy()
            not_passing = previous_not_passing.copy()
            del previous_not_passing

        if len(self.transcripts) == 0:
            self.logger.warning("No transcripts pass the muster for {0}".format(self.id))
            return
        self.scores = dict()
        for tid in self.transcripts:
            self.scores[tid] = dict()
        for param in self.json_dict["scoring"]:
            rescaling = self.json_dict["scoring"][param]["rescaling"]
            metrics = [getattr(self.transcripts[tid], param) for tid in self.transcripts]
            if rescaling == "target":
                target = self.json_dict["scoring"][param]["value"]
                denominator = max(abs(x - target) for x in metrics)
            else:
                target = None
                denominator = (max(metrics) - min(metrics))
            if denominator == 0:
                denominator = 1

            for tid in self.transcripts:
                tid_metric = getattr(self.transcripts[tid], param)
                check = True
                score = 0
                if "filter" in self.json_dict["scoring"][param]:
                    check = self.evaluate(tid_metric, self.json_dict["scoring"][param]["filter"])
                if check is False:
                    score = 0
                else:
                    if rescaling == "max":
                        score = abs((tid_metric - min(metrics)) / denominator)
                    elif rescaling == "min":
                        score = abs(1 - (tid_metric - min(metrics)) / denominator)
                    elif rescaling == "target":
                        score = 1 - abs(tid_metric - target) / denominator
                score *= self.json_dict["scoring"][param]["multiplier"]
                self.scores[tid][param] = score

        for tid in self.transcripts:
            if tid in not_passing:
                self.transcripts[tid].score = 0
            else:
                self.transcripts[tid].score = sum(self.scores[tid].values())

        self.scores_calculated = True

    def print_metrics(self):

        """This method yields dictionary "rows" that will be given to a csv.DictWriter class."""

        # Check that rower is an instance of the csv.DictWriter class
        self.calculate_scores()

        # The rower is an instance of the DictWriter class from the standard CSV module

        for tid in sorted(self.transcripts.keys(), key=lambda ttid: self.transcripts[ttid]):
            row = {}
            for key in self.available_metrics:
                if key.lower() in ("id", "tid"):
                    row[key] = tid
                elif key.lower() == "parent":
                    row[key] = self.id
                else:
                    row[key] = getattr(self.transcripts[tid], key, "NA")
                if type(row[key]) is float:
                    row[key] = round(row[key], 2)
                elif row[key] is None or row[key] == "":
                    row[key] = "NA"
            yield row
        if self.excluded is not None:
            for row in self.excluded.print_metrics():
                yield row

        return

    def print_scores(self):
        """This method yields dictionary rows that are given to a csv.DictWriter class."""
        self.calculate_scores()
        score_keys = sorted(list(self.json_dict["scoring"].keys()))
        keys = ["tid", "parent", "score"] + score_keys

        for tid in self.scores:
            row = dict().fromkeys(keys)
            row["tid"] = tid
            row["parent"] = self.id
            row["score"] = round(self.transcripts[tid].score, 2)
            for key in score_keys:
                row[key] = round(self.scores[tid][key], 2)
            yield row

    def get_metrics(self):

        """Quick wrapper to calculate the metrics for all the transcripts."""

        if self.metrics_calculated is True:
            return

        for tid in self.transcripts:
            self.calculate_metrics(tid)

        self.metrics_calculated = True
        return

    # ############## Class methods ################

    @classmethod
    def is_intersecting(cls, transcript, other):
        """
        :param transcript: the first transcript to check
        :type transcript: Transcript

        :param other: the second transcript to check
        :type other: Transcript

        Implementation of the is_intersecting method. Here at the level of the sublocus,
        the intersection is seen as overlap between exons. 
        """

        if transcript.id == other.id:
            # We do not want intersection with oneself
            return False
        for exon in transcript.exons:
            if any(
                    filter(
                        # Check that at least one couple of exons are overlapping
                        lambda oexon: cls.overlap(exon, oexon) >= 0,
                        other.exons
                    )
            ) is True:
                return True

        return False

    @property
    def splitted(self):
        """The splitted flag indicates whether a sublocus has already been processed to produce the necessary monosubloci.
        It must be set as a boolean flag (hence why it is coded as a property)

        :rtype bool
        """
        return self.__splitted

    @splitted.setter
    def splitted(self, verified):
        """
        :param verified: boolean flag to set.
        :type verified: bool
        """

        if type(verified) != bool:
            raise TypeError()
        self.__splitted = verified

    @property
    def id(self):
        """
        :return: The name of the Locus.
        :rtype str
        """
        if self.monoexonic is True:
            addendum = "mono"
        else:
            addendum = "multi"
        if self.counter > 0:
            addendum = "{0}.{1}".format(addendum, self.counter)

        return "{0}.{1}".format(super().id, addendum)