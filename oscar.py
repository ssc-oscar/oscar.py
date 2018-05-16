
import lzf
from tokyocabinet import hash

from functools import wraps
import warnings

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
    if not raw_data:
        return ""
    elif raw_data[0] == '\x00':
        return raw_data[1:]
    start, usize = lzf_length(raw_data)
    return lzf.decompress(raw_data[start:], usize)


def cached_property(func):
    """ Classic memoize with @property on top"""
    @wraps(func)
    def wrapper(self):
        if not hasattr(self, "_cache"):
            self._cache = {}
        key = func.__name__
        if key not in self._cache:
            self._cache[key] = func(self)
        return self._cache[key]
    return property(wrapper)


def slice20(raw_data):
    """ Convenience method to slice raw_data into 20-byte chunks
    >>> list(slice20("a"*20 + "b"*20))
    ['aaaaaaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbbbbbb']
    """
    for i in range(0, len(raw_data), 20):
        yield raw_data[i:i + 20]


def prefix(value, key_length):
    # type: (str, int) -> int
    """ Calculate 'filesystem sharding' prefix using bit magic
    >>> prefix('\xff', 7)
    127
    >>> prefix('\xff', 3)
    7
    """
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
        value = BlobPool('path_to.tch')[key]
    """
    pool = {}

    @staticmethod
    def __new__(cls, path):
        if path not in cls.pool:
            cls.pool[path] = open(path, 'rb')
        return cls.pool[path]


class GitObject(object):
    type = None

    @classmethod
    def all(cls):
        """ Iterate ALL objects of this type (all projects, all times) """
        for key in range(128):
            path = '/data/All.blobs/%s_%d' % (cls.type, key)
            datafile = open(path + '.bin')
            for line in open(path + '.idx'):
                chunks = line.strip().split(";")
                if cls.type == "blob":
                    offset, comp_length, full_length, sha = chunks[1:5]
                else:
                    offset, comp_length, sha = chunks[1:4]

                obj = cls(sha)
                obj._cache = {'data': decomp(datafile.read(int(comp_length)))}

                yield obj

    def __init__(self, sha):
        """
        :param sha: either a 40 char hex or a 20 bytes binary SHA1 hash
        >>> sha = '05cf84081b63cda822ee407e688269b494a642de'
        >>> GitObject(sha.decode('hex')).sha == sha
        True
        >>> GitObject(sha).bin_sha == sha.decode('hex')
        True
        """
        if len(sha) == 40:
            self.sha = sha
            self.bin_sha = sha.decode("hex")
        elif len(sha) == 20:
            self.sha = sha.encode("hex")
            self.bin_sha = sha
        else:
            raise ValueError("Invalid SHA1 hash: %s" % sha)

    def __eq__(self, other):
        return isinstance(other, type(self)) \
               and self.type == other.type \
               and self.sha == other.sha

    def resolve_path(self, path, key_length=7):
        """Format given path with object type and key
        >>> go = GitObject('8528315640bac6eae17297270d4ee1892abf6add')
        >>> go.resolve_path("test")
        'test'
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
        """ Resolve the path and read .tch"""
        return self._read(self.resolve_path(path, key_length), self.bin_sha)

    @classmethod
    def _map(cls, path, key):
        return tuple(cls(bin_sha) for bin_sha in slice20(cls._read(path, key)))

    def map(self, path, key_length, cls):
        return tuple(cls(bin_sha)
                     for bin_sha in slice20(self.read(path, key_length)))

    def index_line(self):
        # get line number in index file
        return self.read('/fast{blob}/All.sha1/sha1.{type}_{key}.tch')

    @cached_property
    def data(self):
        if self.type is None:
            raise NotImplemented
        # default implementation will only work for commits and trees
        return decomp(self.read('/fast1/All.sha1c/{type}_{key}.tch'))

    def __repr__(self):
        return "<%s: %s>" % ((self.type or 'GitObject').capitalize(), self.sha)

    def __str__(self):
        """
        >>> print(Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c'))
        tree d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d
        parent 66acf0a046a02b48e0b32052a17f1e240c2d7356
        author Pavel Puchkin <neoascetic@gmail.com> 1375321509 +1100
        committer Pavel Puchkin <neoascetic@gmail.com> 1375321597 +1100
        <BLANKLINE>
        License changed :P
        <BLANKLINE>
        """
        return self.data


class Blob(GitObject):
    type = 'blob'

    @cached_property
    def data(self):
        offset, length = unber(
            self.read('/data/All.sha1o/sha1.blob_{key}.tch'))
        fh = BlobPool(self.resolve_path('/data/All.blobs/{type}_{key}.bin'))
        fh.seek(offset)
        return decomp(fh.read(length))

    @property
    def commits(self):
        # type: () -> tuple
        """ Get commits where this blob has been added or removed/changed

        # TODO: claimed to return only commits modifying the blob; check and update
        # Known to be inaccurate - tests fail
        >>> cs = list(Blob("7e2a34e2ec9bfdccfa01fff7762592d9458866eb").commits
        >>> len(cs) >= 4
        True
        >>> "1e971a073f40d74a1e72e07c682e1cba0bae159b" in {c.sha for c in cs}
        True
        >>> "8fb99ec51bccc6ea4828c6ea08cd0976b53e6edc" in {c.sha for c in cs}
        True
        >>> cs = list(Blob("e0ac96cefe3d230553931c54a79fa164a8fa11da").commits
        >>> len(cs) >= 4
        True
        >>> "1e971a073f40d74a1e72e07c682e1cba0bae159b" in {c.sha for c in cs}
        True
        >>> "8fb99ec51bccc6ea4828c6ea08cd0976b53e6edc" in {c.sha for c in cs}
        True
        """
        bin_shas = self.read('/data/basemaps/b2cFullF.{key}.tch', 4)
        for bin_sha in slice20(bin_shas):
            yield Commit(bin_sha)

    @property
    def parents(self):
        """ Get parent trees
        :return: tuple of Tree objects

        # >>> c = Commit("1e971a073f40d74a1e72e07c682e1cba0bae159b")
        # >>> all(c.tree.sha in {pt.sha for pt in blob.parents}
        # ...     for blob in c._blobs)
        # True
        """
        warnings.warn(
            "This relation is not maintained anymore and known to be "
            "inaccurate. Please don't use it", DeprecationWarning)
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
        data = self.data
        i = 0
        while i < len(data):
            # mode
            start = i
            while i < len(data) and data[i] != " ":
                i += 1
            mode = data[start:i]
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

    def traverse(self):
        """ Recursively traverse commit files structures
        :return: generator of (mode, filename, blob/tree sha)
        >>> c = Commit("1e971a073f40d74a1e72e07c682e1cba0bae159b")
        >>> len(list(c.tree.traverse()))
        8
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> len(list(c.tree.traverse()))
        36
        """
        for mode, fname, sha in self:
            yield mode, fname, sha
            # trees are always 40000:
            # https://stackoverflow.com/questions/1071241
            if mode == "40000":
                for mode2, fname2, sha2 in Tree(sha).traverse():
                    yield mode2, fname + '/' + fname2, sha2

    def full(self):
        """ Subtree pretty print
        :return: multiline string, where each line contains mode, name and sha,
            with subtrees expanded
        """
        files = sorted(self.traverse(), key=lambda x: x[1])
        return "\n".join(" ".join(line) for line in files)

    @cached_property
    def parents(self):
        """ Get parent trees
        :return: generator of Tree objects

        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> trees = {fname: sha
        ...          for mode, fname, sha in c.tree.traverse() if mode=="40000"}
        >>> all(trees[fname.rsplit("/", 1)[0]] in
        ...         {p.sha for p in Tree(sha).parents}
        ...     for fname, sha in trees.items() if "/" in fname)
        True
        """
        try:
            return tuple(
                self.map('/data/basemaps/t2pt0-127.{key}.tch', 3, Tree))
        except KeyError:
            return tuple()

    def __str__(self):
        """
        >>> print(Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d"))
        100755 .gitignore 83d22195edc1473673f1bf35307aea6edf3c37e3
        100644 COPYING fda94b84122f6f36473ca3573794a8f2c4f4a58c
        100644 MANIFEST.in b724831519904e2bc25373523b368c5d41dc368e
        100644 README.rst 234a57538f15d72f00603bf086b465b0f2cda7b5
        40000 minicms 954829887af5d9071aa92c427133ca2cdd0813cc
        100644 setup.py 46aaf071f1b859c5bf452733c2583c70d92cd0c8
        >>> print(Tree("954829887af5d9071aa92c427133ca2cdd0813cc"))
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

    @cached_property
    def files(self):
        return {fname: sha
                for mode, fname, sha in self.traverse() if mode != "40000"}

    @cached_property
    def blobs(self):
        """ Get a tuple of all blobs from the tree and its subtrees
        :return: tuple of Blobs

        >>> len(Tree('d20520ef8c1537a42628b72d481b8174c0a1de84').blobs)
        7
        """
        return tuple(Blob(sha) for sha in self.files.values())


class Commit(GitObject):
    """ A git commit object """

    type = 'commit'

    @classmethod
    def by_author(cls, author):
        """ Get all commits authored by <author>

        :param author: str, commit author string, "name <email>".
            E.g.: 'gsadaram <gsadaram@cisco.com>'
        :return: generator of commits
        >>> cs = list(Commit.by_author('Marat <valiev.m@gmail.com>'))
        >>> len(cs) > 100
        True
        >>> all(isinstance(c, Commit) for c in cs)
        True
        >>> author = 'user2589 <valiev.m@gmail.com>'
        >>> orig = {c.sha for c in Commit.by_project('user2589_karta')
        ...               if c.author==author}
        >>> mapp = {c.sha for c in Commit.by_author(author)}
        >>> orig.issubset(mapp)
        True
        """
        return cls._map('/data/basemaps/Auth2Cmt.tch', author)

    @classmethod
    def by_file(cls, file_path):
        """ Get all commits *modifying* the given file
        :param file_path: a full path, e.g.: 'public_html/images/cms/my.gif'
        :return: generator of commits

        # TODO: claimed to return only commits modifying the file; check and update
        >>> proj = 'user2589_minicms'
        >>> cs = {c.sha: {fname: sha
        ...               for mode, fname, sha in c.tree.traverse()
        ...               if mode != "40000"}
        ...       for c in Commit.by_project(proj)}
        >>> fname = 'minicms/templatetags/minicms_tags.py'
        >>> s = set()
        >>> for sha, files in cs.items():
        ...     for parent in Commit(sha).parents:
        ...         if cs[parent.sha].get(fname) != files.get(fname):
        ...             s.add(sha)
        >>> s2 = {c.sha for c in Commit.by_file(fname)}
        >>> fname = 'minicms/admin.py'
        >>> orig = {c.sha for
        ...         if ' %s ' % fname in c.tree.full()}
        >>> cs = list(Commit.by_file(fname))
        >>> len(cs) > 40
        True
        >>> all(isinstance(c, Commit) for c in cs)
        True
        >>> mapp = {c.sha for c in cs}
        >>> orig.issubset(mapp)
        True
        >>> fname = 'minicms/templatetags/minicms_tags.py'
        >>> orig = {c.sha for c in Commit.by_project(proj)
        ...         if ' %s ' % fname in c.tree.full()}
        >>> mapp = {c.sha for c in Commit.by_file(fname)}
        >>> orig.issubset(mapp)
        True

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

        >>> cs = list(Commit.by_project('user2589_minicms'))
        >>> len(cs) > 65
        True
        >>> all(isinstance(c, Commit) for c in cs)
        True
        >>> import requests
        >>> gh = requests.get('https://api.github.com/repos/user2589/minicms/'
        ...                   'commits?per_page=100').json()
        >>> sha_gh = {c['sha'] for c in gh}
        >>> merge = "GitHub Merge Button <merge-button@github.com>"
        >>> all(c.sha  in sha_gh or c.author == merge for c in cs)
        True
        >>> shas = {c.sha for c in cs}
        >>> all(all(p.sha in shas for p in c.parents) for c in cs)
        True
        """
        return cls._map('/data/basemaps/Prj2CmtG.%d.tch' % prefix(project, 3),
                        project)

    def __getattr__(self, attr):
        """ Mimic special properties:
            tree:           root Tree of the commit
            parents:        tuple of parent commits
            message:        str, first line of the commit message
            full_message:   str, full commit message
            author:         str, Name <email>
            authored_at:    str, unix_epoch timezone
            committer:      str, Name <email>
            committed_at:   str, unix_epoch timezone
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> c.author.startswith('Marat')
        True
        >>> c.authored_at
        '1337350448 +1100'
        >>> c.tree.sha
        '6845f55f47ddfdbe4628a83fdaba35fa4ae3c894'
        >>> len(c.parents)
        1
        >>> c.parents[0].sha
        'ab124ab4baa42cd9f554b7bb038e19d4e3647957'
        >>> c.committed_at
        '1337350448 +1100'
        """
        if attr not in ('tree', 'parents', 'message', 'full_message',
                        'author', 'committer', 'authored_at', 'committed_at'):
            raise AttributeError

        self.header, self.full_message = self.data.split("\n\n", 1)
        self.message = self.full_message.split("\n", 1)[0]
        parents = []
        for line in self.header.split("\n"):
            key, value = line.strip().split(" ", 1)
            if key == "tree":
                self.tree = Tree(value)
            elif key == "parent":  # multiple parents possible
                parents.append(Commit(value))
            elif key == "author":
                chunks = value.rsplit(" ", 2)
                self.author = chunks[0]
                self.authored_at = " ".join(chunks[1:])
            elif key == "committer":
                chunks = value.rsplit(" ", 2)
                self.committer = chunks[0]
                self.committed_at = " ".join(chunks[1:])
        self.parents = tuple(parents)

        return getattr(self, attr)

    @cached_property
    def projects(self):
        # type: () -> list
        """Projects including this commit
        >>> proj = 'user2589_minicms'
        >>> all(proj in c.projects for c in Commit.by_project(proj))
        True
        >>> proj = 'user2589_karta'
        >>> all(proj in c.projects for c in Commit.by_project(proj))
        True
        """
        return decomp(
            self.read('/data/basemaps/Cmt2PrjG.{key}.tch', 3)).split(";")

    @cached_property
    def children(self):
        # type: () -> tuple
        """ Commit children
        :return: tuple of children Commit objects
        >>> cs = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b').children
        >>> '9bd02434b834979bb69d0b752a403228f2e385e8' in {c.sha for c in cs}
        True
        >>> isinstance(cs[0], Commit)
        True
        >>> len(Commit("a443e1e76c39c7b1ad6f38967a75df667b9fed57").children) > 1
        True
        >>> len(Commit("4199110871d5dcb3a79dfc19a16eb630c9218962").children) > 3
        True
        >>> cs = Commit.by_project('user2589_minicms')
        >>> all(all(c.sha in {ch.sha for ch in p.children} for p in c.parents)
        ...     for c in cs)
        True
        """
        return self.map('/data/basemaps/Cmt2Chld.tch', 1, Commit)

    @cached_property
    def blobs(self):
        # type: () -> tuple
        """ Commit blobs retrieved from cached relation
        much faster
        :return: tuple of children Blob objects

        # TODO: known to be inaccurate - tests fail
        >>> c = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
        >>> len(c.blobs) == len(c._blobs)
        True
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> len(c.blobs) == len(c._blobs)
        True
        """
        warnings.warn(
            "This relation is known to miss every first file in all trees. "
            "Consider using Commit._blobs as a slower but more accurate "
            "alternative", DeprecationWarning)
        return self.map('/data/basemaps/c2bFullF.{key}.tch', 4, Blob)


class Tag(GitObject):
    type = 'tag'

    @property
    def data(self):
        raise NotImplementedError
