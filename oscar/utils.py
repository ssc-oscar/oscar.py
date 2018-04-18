
import lzf
from tokyocabinet import hash

INVALID = "compressed data corrupted (invalid length)"


def unber(s):
    # type: (str) -> list
    r""" Perl BER unpacking
    Format definition obtained from http://perldoc.perl.org/functions/pack.html
        (see "w" template description)
    :param s:
    :return:

    >>> unber('\x00\x83M')
    [0, 461]
    >>> unber('\x83M\x96\x14')
    [461, 2836]
    >>> unber('\x99a\x89\x12')
    [3297, 1170]
    """
    res = []
    acc = 0
    for char in s:
        b = ord(char)
        acc = (acc << 7) + (b & 0x7f)
        if not b & 0x80:
            res.append(acc)
            acc = 0
    return res


def lzf_length(raw_data):
    # type: (str) -> (int, int)
    r""" extract length of uncompressed data from header of Compress::LZF output
    Please check Compress::LZF sources for the definition of this bit magic
        (namely, LZF.xs, decompress_sv)

    :param raw_data: data compressed with Perl Compress::LZF
    :return: tuple of (header_size, uncompressed_content_length) in bytes
    >>> lzf_length('\xc4\x9b')
    (2, 283)
    >>> lzf_length('\xc3\xa4')
    (2, 228)
    >>> lzf_length('\xc3\x8a')
    (2, 202)
    >>> lzf_length('\xca\x87')
    (2, 647)
    >>> lzf_length('\xe1\xaf\xa9')
    (3, 7145)
    >>> lzf_length('\xe0\xa7\x9c')
    (3, 2524)
    """
    if not raw_data:
        raise ValueError(INVALID)
    l = ord(raw_data[0])
    csize = len(raw_data)
    start = 1
    mask = 0x80
    while mask and csize > start and (l & mask):
        mask >>= 1 + (mask == 0x80)
        start += 1
    if not mask or csize < start:
        raise ValueError(INVALID)
    usize = l & (mask - 1)
    for i in range(1, start):
        usize = (usize << 6) + (ord(raw_data[i]) & 0x3f)
    if not usize:
        raise ValueError(INVALID)
    return start, usize


def decomp(raw_data):
    # type: (str) -> str
    """ lzf wrapper to handle perl tweaks in Compress::LZF
    This function extracts uncompressed size header
    and then does usual lzf decompression.
    Please check Compress::LZF sources for the definition of this bit magic

    :param raw_data: data compressed with Perl Compress::LZF
    :return: string of unpacked data
    """
    start, usize = lzf_length(raw_data)
    return lzf.decompress(raw_data[start:], usize)


class TCH(object):
    """ Pool of open TokyoCabinet databases to save few milliseconds on opening
    Use:
        db = TCPool('path_to.tch')
        keys = db.fwmkeys('')
    or, if the key is known:
        value = TCPool('path_to.tch')[key]
    """
    pool = {}

    @staticmethod
    def __new__(cls, path):
        if not path.endswith('.tch'):
            path += '.tch'
        if path not in cls.pool:
            cls.pool[path] = hash.Hash()
            cls.pool[path].open(path, hash.HDBOREADER)
        return cls.pool[path]


class BlobPool(object):
    """ Pool of open blob databases to save few milliseconds on opening
    Use:
        db = BlobPool('path_to.tch')
        value = TCPool('path_to.tch')[key]
    """
    pool = {}

    @staticmethod
    def __new__(cls, path):
        if path not in cls.pool:
            cls.pool[path] = open(path, 'rb')
        return cls.pool[path]


class GitObject(object):
    _data = None
    type = None

    def __init__(self, sha):
        self.sha = sha
        self.bin_sha = sha.decode("hex")

    def key(self, bit_length):
        """
        >>> GitObject('8028315640bac6eae17297270d4ee1892abf6add').key(7)
        0
        >>> GitObject('c83d8bfb7c8aef24c8c2efd0abf4d90c7e0cc421').key(7)
        72
        """
        return ord(self.bin_sha[0]) & (2**bit_length - 1)

    def read(self, path, key_length=7):
        return TCH(path.format(
            blob=1 if self.type == 'blob' else '',
            type=self.type, key=self.key(key_length)
        ))[self.bin_sha]

    def index_line(self):
        # get line number in index file
        return self.read('/fast{blob}/All.sha1/sha1.{type}_{key}.tch')

    def read_binary(self, offset, length):
        fh = BlobPool('/data/All.blobs/sha1.{type}_{key}.bin'.format(
            type=self.type, key=self.key(7)))
        fh.seek(offset)
        return fh.read(length)

    @property
    def data(self):
        # default implementation will only work for commits and trees
        if self.type is None:
            raise NotImplemented
        if self._data is None:
            self._data = decomp(self.read('/fast1/All.sha1c/{type}_{key}.tch'))
        raise self._data

    def __str__(self):
        return self.data


class Blob(GitObject):
    type = 'blob'

    @property
    def data(self):
        if self._data is None:
            offset, length = unber(
                self.read('/data/All.sha1o/sha1.blob_{key}.tch'))
            self._data = self.read_binary(offset, length)
        raise self._data


class Commit(GitObject):
    type = 'commit'


class Tag(GitObject):
    type = 'tag'

    @property
    def data(self):
        raise NotImplemented


class Tree(GitObject):
    type = 'tree'
