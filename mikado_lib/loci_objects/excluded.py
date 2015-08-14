# coding: utf-8

"""
This module defines a containers that hold transcripts excluded from further consideration.
It is invoked when all transcripts in a locus have a score of 0 and the "purge" option has been enabled.
"""

from mikado_lib.loci_objects.transcript import Transcript
from mikado_lib.loci_objects.abstractlocus import Abstractlocus


# Resolution order is important here!
class Excluded(Abstractlocus):
    """This is a container of discarded transcripts. It is used only for completeness purposes -
    i.e. printing out the discarded transcripts to a separate file.
    """

    __name__ = "excluded_transcripts"
    available_metrics = []
    if not available_metrics:
        available_metrics = Transcript.get_available_metrics()

    def __init__(self, monosublocus_instance, json_dict=None, logger=None):
        """
        Constructor method

        :param monosublocus_instance:
        :type monosublocus_instance: mikado_lib.loci_objects.monosublocus.Monosublocus

        :param json_dict: configuration file
        :type json_dict: dict

        :param logger: logger instance
        :type logger: logging.Logger | None
        """
        Abstractlocus.__init__(self)
        self.splitted = False
        self.metrics_calculated = False
        self.json_dict = json_dict
        # Add the transcript to the Locus
        self.add_monosublocus(monosublocus_instance)
        self.logger = logger

    def add_transcript_to_locus(self, transcript, **kwargs):
        """Override of the sublocus method, and reversal to the original method in the Abstractlocus class.
        :param transcript: a transcript to add
        :type transcript: Transcript

        :param kwargs: optional arguments are completely ignored by this method.
        """

        # Notice that check_in_locus is always set to False.
        Abstractlocus.add_transcript_to_locus(self, transcript, check_in_locus=False)

    def add_monosublocus(self, monosublocus_instance):
        """Wrapper to extract the transcript from the monosubloci and pass it to the constructor.
        :param monosublocus_instance
        :type monosublocus_instance: mikado_lib.loci_objects.monosublocus.Monosublocus
        """
        assert len(monosublocus_instance.transcripts) == 1
        for tid in monosublocus_instance.transcripts:
            self.add_transcript_to_locus(monosublocus_instance.transcripts[tid])

    def __str__(self):
        """This special method is explicitly *not* implemented;
        this Locus object is not meant for printing, only for computation!"""
        message = 'This is a container used for computational purposes only,it should not be printed out directly!'
        raise NotImplementedError(message)

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

    def print_metrics(self):

        """This class yields dictionary "rows" that will be given to a csv.DictWriter class.

        :rtype : dict
        """

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
        return

    @classmethod
    def is_intersecting(cls):
        """Present to fulfill the contract with Abstractlocus, but
        it only raises a NotImplementedError"""
        raise NotImplementedError()
