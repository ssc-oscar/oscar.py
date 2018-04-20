
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


def slice_shas(raw_data):
    for i in range(0, len(raw_data), 20):
        yield raw_data[i:i + 20]


def prefix(value, key_length):
    return ord(value[0]) & (2**key_length - 1)


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
        if len(sha) == 20:
            self.sha = sha
            self.bin_sha = sha.decode("hex")
        elif len(sha) == 40:
            self.sha = sha.encode("hex")
            self.bin_sha = sha
        else:
            raise ValueError("Invalid SHA1 hash: %s" % sha)

    def resolve_path(self, path, key_length=7):
        """Format given path with object type and key
        >>> go = GitObject('8528315640bac6eae17297270d4ee1892abf6add')
        >>> go.resolve_path("test")
        test
        >>> go.resolve_path("test_{key}", 7)
        'test_5'
        >>> go.resolve_path("/fast{blob}/All.sha1/{type}_{key}", 8)
        '/fast/All.sha1/None_133'
        >>> go.type = 'blob'
        >>> go.resolve_path("/fast{blob}/All.sha1/{type}_{key}", 8)
        '/fast1/All.sha1/blob_133'
        """
        return path.format(blob=1 if self.type == 'blob' else '',
                           type=self.type, key=prefix(self.bin_sha, key_length))

    @staticmethod
    def _read(path, key):
        """ Read the specified TokyCabinet by the specified key"""
        return TCH(path)[key]

    def read(self, path, key_length=7):
        return self._read(self.resolve_path(path, key_length), self.bin_sha)

    @classmethod
    def _map(cls, path, key):
        for bin_sha in slice_shas(cls._read(path, key)):
            yield cls(bin_sha)

    def map(self, path, key_length, cls):
        for bin_sha in slice_shas(self.read(path, key_length)):
            yield cls(bin_sha)

    def index_line(self):
        # get line number in index file
        return self.read('/fast{blob}/All.sha1/sha1.{type}_{key}.tch')

    def read_binary(self, offset, length):
        fh = BlobPool('/data/All.blobs/{type}_{key}.bin'.format(
            type=self.type, key=self.key(7)))
        fh.seek(offset)
        return decomp(fh.read(length))

    @property
    def data(self):
        # default implementation will only work for commits and trees
        if self.type is None:
            raise NotImplemented
        if self._data is None:
            self._data = decomp(self.read('/fast1/All.sha1c/{type}_{key}.tch'))
        return self._data

    def __str__(self):
        """
        >>> str(Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c'))
        tree d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d
        parent 66acf0a046a02b48e0b32052a17f1e240c2d7356
        author Pavel Puchkin <neoascetic@gmail.com> 1375321509 +1100
        committer Pavel Puchkin <neoascetic@gmail.com> 1375321597 +1100

        License changed :P

        """
        return self.data


class Blob(GitObject):
    type = 'blob'

    @property
    def data(self):
        if self._data is None:
            offset, length = unber(
                self.read('/data/All.sha1o/sha1.blob_{key}.tch'))
            self._data = self.read_binary(offset, length)
        return self._data

    @property
    def commits(self):
        bin_shas = self.read('/data/basemaps/b2cFullF.{key}.tch', 4)
        for bin_sha in slice_shas(bin_shas):
            yield Commit(bin_sha)

    @property
    def parents(self):
        """ Get parent trees
        :return: generator of Tree objects

        TODO: test
        TODO: ask Audris about inconsistency in name and key length
        """
        return self.map('/data/basemaps/b2pt.00-15.{key}.tch', 3, Tree)


class Tree(GitObject):
    type = 'tree'

    def __iter__(self):
        """ Unpack binary tree structures, yielding 3-tuples of
        (mode (ASCII decimal), filename, sha (40 bytes hex))

        Format description:  https://stackoverflow.com/questions/14790681/
            mode   (ASCII encoded decimal)
            SPACE (\0x20)
            filename
            NULL (\x00)
            20-byte binary hash
        >>> len(list(Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d")))
        6
        >>> all(len(line) == 3
        ...     for line in Tree("954829887af5d9071aa92c427133ca2cdd0813cc"))
        True
        """
        data = str(self)
        i = 0
        while i < len(data):
            # mode
            start = i
            while i < len(data) and data[i] != " ":
                i += 1
            mode = int(data[start:i])
            i += 1
            # file name
            start = i
            while i < len(data) and data[i] != "\x00":
                i += 1
            fname = data[start:i]
            # sha
            start = i + 1
            i += 21
            yield mode, fname, data[start:i].encode('hex')

    @property
    def parents(self):
        """ Get parent trees
        :return: generator of Tree objects

        TODO: test
        TODO: ask Audris about inconsistency in name and key length
        """
        return self.map('/data/basemaps/t2pt0-127.{key}.tch', 3, Tree)

    def __str__(self):
        """
        >>> str(Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d"))
        100755 .gitignore 83d22195edc1473673f1bf35307aea6edf3c37e3
        100644 COPYING fda94b84122f6f36473ca3573794a8f2c4f4a58c
        100644 MANIFEST.in b724831519904e2bc25373523b368c5d41dc368e
        100644 README.rst 234a57538f15d72f00603bf086b465b0f2cda7b5
        40000 minicms 954829887af5d9071aa92c427133ca2cdd0813cc
        100644 setup.py 46aaf071f1b859c5bf452733c2583c70d92cd0c8
        >>> str(Tree("954829887af5d9071aa92c427133ca2cdd0813cc"))
        100644 __init__.py ff1f7925b77129b31938e76b5661f0a2c4500556
        100644 admin.py d05d461b48a8a5b5a9d1ea62b3815e089f3eb79b
        100644 models.py d1d952ee766d616eae5bfbd040c684007a424364
        40000 templates 7ff5e4c9bd3ce6ab500b754831d231022b58f689
        40000 templatetags e5e994b0be2c9ce6af6f753275e7d8c29ccf75ce
        100644 urls.py e9cb0c23a7f6683911305efff91dcabadb938794
        100644 utils.py 2cfbd298f18a75d1f0f51c2f6a1f2fcdf41a9559
        100644 views.py 973a78a1fe9e69d4d3b25c92b3889f7e91142439
        """
        return "\n".join(" ".join(line) for line in self)


class Commit(GitObject):
    type = 'commit'

    @classmethod
    def by_author(cls, author):
        """ Get all commits authored by <author>

        :param author: str, commit author string, "name <email>".
            E.g.: 'gsadaram <gsadaram@cisco.com>'
        :return: generator of commits
        """
        return cls._map('/data/basemaps/Auth2Cmt.tch', author)

    @classmethod
    def by_file(cls, file_path):
        """ Get all commits with this filename
        :param file_path: a full path, e.g.: 'public_html/images/cms/my.gif'
        :return: generator of commits
        """
        if not file_path.endswith("\n"):
            file_path += "\n"
        return cls._map('/data/basemaps/f2cFullF.%d.tch' % prefix(file_path, 3),
                        file_path)

    @classmethod
    def by_project(cls, project):
        """ Get all commits for the specified project
        :param project: project id <user>_<repo>, e.g. user2589_oscar.py
        :return: generator of commits
        """
        return cls._map('/data/basemaps/Prj2CmtG.%d.tch' % prefix(project, 3),
                        project)

    # TODO: author, committer, times, tree

    def children(self):
        # TODO: test
        return self.map('/data/basemaps/Cmt2Chld.tch.tch', 1, Commit)

    def blobs(self):
        # TODO: test
        return self.map('/data/basemaps/c2bFullF.{0..15}.tch', 4, Blob)


class Tag(GitObject):
    type = 'tag'

    @property
    def data(self):
        raise NotImplemented
