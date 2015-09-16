# coding: utf-8

"""
This class defines the results of the Assigner.compare method.
"""


class ResultStorer:
    """This class stores the results in pre-defined slots, to reduce memory usage."""

    __slots__ = ["ref_id", "ref_gene", "ccode",
                 "tid", "gid",
                 "n_prec", "n_recall", "n_f1",
                 "j_prec", "j_recall", "j_f1",
                 "e_prec", "e_recall", "e_f1",
                 "distance"]

    def __init__(self, *args):

        """
        :param args: a list/tuple
        :type args: list | tuple

        """

        if len(args) != len(self.__slots__):
            err_msg = "Result_storer expected {0} but only received {1}".format(
                len(self.__slots__), len(args))
            raise ValueError(err_msg)

        self.ref_id, self.ref_gene, self.ccode, self.tid, self.gid, \
            self.n_prec, self.n_recall, self.n_f1,\
            self.j_prec, self.j_recall, self.j_f1, \
            self.e_prec, self.e_recall, self.e_f1, \
            self.distance = args

        for index, key in enumerate(self.__slots__):
            if index < 3:
                if isinstance(getattr(self, self.__slots__[index]), str):
                    setattr(self, key, tuple([getattr(self, self.__slots__[index])]))
            elif 4 < index < len(self.__slots__):
                if isinstance(getattr(self, self.__slots__[index]), (float, int)):
                    setattr(self, key, tuple([getattr(self, self.__slots__[index])]))

    def _asdict(self):

        """
        :return: a dictionary containing the items of the class
        :rtype : dict
        """
        result_dict = dict().fromkeys(self.__slots__)

        for attr in self.__slots__[:3]:
            try:
                result_dict[attr] = ",".join(list(getattr(self, attr)))
            except TypeError as exc:
                raise TypeError("{0}; {1}".format(exc, getattr(self, attr)))
        for attr in self.__slots__[3:5]:
            result_dict[attr] = getattr(self, attr)
        for attr in self.__slots__[5:-1]:
            result_dict[attr] = ",".join("{0:,.2f}".format(x) for x in getattr(self, attr))
        result_dict["distance"] = self.distance[0]  # Last attribute
        return result_dict

    def as_dict(self):
        """
        Wrapper for the protected method _asdict
        :return: dictionary
        """

        return self._asdict()

    def __str__(self):

        result_dict = self._asdict()
        line = []
        for key in self.__slots__:
            line.append(str(result_dict[key]))
        return "\t".join(line)

    def __repr__(self):

        represent = "result( "
        for key in self.__slots__:
            represent += "{0}={1}, ".format(key, getattr(self, key))
        represent += ")"
        return represent

    def __getitem__(self, item):
        if item in self.__slots__:
            return getattr(self, item)
        else:
            raise KeyError(item)