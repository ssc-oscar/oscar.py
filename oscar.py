
import lzf
from tokyocabinet import hash as tch

from datetime import datetime, timedelta, tzinfo
from functools import wraps
import warnings

__version__ = "0.1.2"
__author__ = "Marat (@cmu.edu)"

PATHS = {
    # not critical - almost never used
    'all_sequential': '/data/All.blobs/{type}_{key}',  # cmt, tree
    'index_line': '/fast{blob}/All.sha1/sha1.{type}_{key}.tch',
    # critical - contain actual objects
    'all_random': '/fast1/All.sha1c/{type}_{key}.tch',  # cmt, tree
    'blob_offset': '/data/All.sha1o/sha1.blob_{key}.tch',
    'blob_data': '/data/All.blobs/{type}_{key}.bin',
    # relations - good to have but not critical
    'blob_commits': '/data/basemaps/b2cFullF.{key}.tch',
    'tree_parents': '/data/basemaps/t2pt0-127.{key}.tch',
    'commit_projects': '/data/basemaps/Cmt2PrjH.{key}.tch',
    'commit_children': '/data/basemaps/Cmt2Chld.tch',
    'commit_blobs': '/data/basemaps/c2bFullF.{key}.tch',
    'project_commits': '/data/basemaps/Prj2CmtH.{key}.tch',
    'file_commits': '/data/basemaps/f2cFullF.{key}.tch',
    'author_commits': '/data/basemaps/Auth2CmtH.tch',
    'author_files': '/data/basemaps/Auth2File.tch',
}


def unber(s):
    # type: (str) -> list
    r""" Perl BER unpacking
    Format definition: from http://perldoc.perl.org/functions/pack.html
        (see "w" template description)

    BER is a way to pack several variable-length ints into one
    binary string. Here we do the reverse

    :param s: a binary string with packed values
    :return: a list of unpacked values

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
    r""" Get length of uncompressed data from a header of Compress::LZF
    output. Check Compress::LZF sources for the definition of this bit magic
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
        raise ValueError("LZF compressed data are missing header")
    lower = ord(raw_data[0])
    csize = len(raw_data)
    start = 1
    mask = 0x80
    while mask and csize > start and (lower & mask):
        mask >>= 1 + (mask == 0x80)
        start += 1
    if not mask or csize < start:
        raise ValueError("LZF compressed data header is corrupted")
    usize = lower & (mask - 1)
    for i in range(1, start):
        usize = (usize << 6) + (ord(raw_data[i]) & 0x3f)
    if not usize:
        raise ValueError("LZF compressed data header is corrupted")
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
        key = "_" + func.__name__
        if not hasattr(self, key):
            setattr(self, key, func(self))
        return getattr(self, key)
    return property(wrapper)


def slice20(raw_data):
    """ Slice raw_data into 20-byte chunks and hex encode each of them
    """
    return tuple(raw_data[i:i + 20].encode('hex')
                 for i in range(0, len(raw_data), 20))


def prefix(value, key_length):
    # type: (str, int) -> int
    """ Calculate 'filesystem sharding' prefix using bit magic
    >>> prefix('\xff', 7)
    127
    >>> prefix('\xff', 3)
    7
    """
    return ord(value[0]) & (2**key_length - 1)


ZERO_TD = timedelta(0)


class CommitTimezone(tzinfo):
    # a lightweight version of pytz._FixedOffset
    def __init__(self, hours, minutes):
        self.offset = timedelta(hours=hours, minutes=minutes)

    def utcoffset(self, dt):
        return self.offset

    def tzname(self, dt):
        return 'fixed'

    def dst(self, dt):
        # daylight saving time - no info
        return ZERO_TD

    def __repr__(self):
        h, m = divmod(self.offset.seconds // 60, 60)
        return "<Timezone: %02d:%02d>" % (h, m)


def parse_commit_date(timestamp):
    """ Parse date string of authored_at/commited_at

    git log time is in the original timezone
        gitpython - same as git log (also, it has the correct timezone)
    unix timestamps (used internally by commit objects) are in UTC
        datetime.fromtimestamp without a timezone will convert it to host tz
    github api is in UTC (this is what trailing 'Z' means)

    :param timestamp: Commit.authored_at or Commit.commited_at,
        e.g. '1337145807 +1100'
    :type timestamp: str
    :return: UTC datetime
    :rtype: datetime.datetime

    >>> parse_commit_date('1337145807 +1100')
    datetime.datetime(2012, 5, 16, 16, 23, 27, tzinfo=<Timezone: 11:00>)
    """
    ts, tz = timestamp.split()
    sign = -1 if tz.startswith('-') else 1
    hours, minutes = sign*int(tz[-4:-2]), sign*int(tz[-2])
    # comparison doesn't work correctly for timezone aware dates
    # so, resorting to naive UTC implementation below
    return datetime.fromtimestamp(int(ts), CommitTimezone(hours, minutes))


# Pool of open TokyoCabinet databases to save few milliseconds on opening
_TCH_POOL = {}


def _get_tch(path):
    if not path.endswith('.tch'):
        path += '.tch'
    if path not in _TCH_POOL:
        _TCH_POOL[path] = tch.Hash()
        _TCH_POOL[path].open(path, tch.HDBOREADER)
        # _TCH_POOL[path].setmutex()
    return _TCH_POOL[path]


def read_tch(path, key):
    """ Read a value from a Tokyo Cabinet file by the specified key
    Main purpose of this method is to cached open .tch handlers
    in _TCH_POOL to speedup reads
    """

    try:
        return _get_tch(path)[key]
    except KeyError:
        return ''


def tch_keys(path, key_prefix=''):
    return _get_tch(path).fwmkeys(key_prefix)


class _Base(object):
    type = None
    key = None

    def __init__(self, key):
        """
        :param key: unique identifier for an object of this type
        """
        self.key = key

    def __repr__(self):
        return "<%s: %s>" % ((self.type or 'OscarBase').capitalize(), self.key)

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        """
        >>> sha = 'f2a7fcdc51450ab03cb364415f14e634fa69b62c'
        >>> Commit(sha) == Commit(sha)
        True
        >>> Commit(sha) == Blob(sha)
        False
        """
        return isinstance(other, type(self)) \
            and self.type == other.type \
            and self.key == other.key

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return self.key

    @classmethod
    def all(cls, key_prefix=''):
        """ Iterate all objects of the given type

        This might be useful to get a list of all projects, or a list of
        all file names.
        """
        raise NotImplementedError


class GitObject(_Base):

    @classmethod
    def all(cls, ignored_prefix=''):
        """ Iterate ALL objects of this type (all projects, all times) """
        for key in range(128):
            path = PATHS['all_sequential'].format(type=cls.type, key=key)
            datafile = open(path + '.bin')
            for line in open(path + '.idx'):
                chunks = line.strip().split(";")
                if len(chunks) > 4:  # cls.type == "blob":
                    # usually, it's true for blobs;
                    # however, some blobs follow common pattern
                    offset, comp_length, full_length, sha = chunks[1:5]
                else:
                    offset, comp_length, sha = chunks[1:4]

                obj = cls(sha)
                obj._data = decomp(datafile.read(int(comp_length)))

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
        super(GitObject, self).__init__(sha)

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
        return path.format(
            blob=1 if self.type == 'blob' else '',
            type=self.type, key=prefix(self.bin_sha, key_length))

    def read(self, path, key_length=7):
        """ Resolve the path and read .tch"""
        return read_tch(self.resolve_path(path, key_length), self.bin_sha)

    def index_line(self):
        # get a line number in the index file
        return self.read(PATHS['index_line'])

    @cached_property
    def data(self):
        if self.type not in ('commit', 'tree'):
            raise NotImplementedError
        # default implementation will only work for commits and trees
        return decomp(self.read(PATHS['all_random']))

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

    def __len__(self):
        return len(self.data)

    @cached_property
    def data(self):
        """ Content of the blob """
        try:
            offset, length = unber(
                self.read(PATHS['blob_offset']))
        except ValueError:  # empty read -> value not found
            raise KeyError('Blob data not found (bad sha?)')
        # no caching here to stay thread-safe
        fh = open(self.resolve_path(PATHS['blob_data']), 'rb')
        fh.seek(offset)
        return decomp(fh.read(length))

    @cached_property
    def commit_shas(self):
        """ SHAs of Commits in which this blob have been
        introduced or modified.

        **NOTE: commits removing this blob are not included**
        """
        return slice20(self.read(PATHS['blob_commits'], 4))

    @property
    def commits(self):
        """ Commits where this blob has been added or changed

        **NOTE: commits removing this blob are not included**
        """
        return (Commit(bin_sha) for bin_sha in self.commit_shas)


class Tree(GitObject):
    """ A representation of git tree object, basically - a directory.

    Trees are iterable. Each element of the iteration is a 3-tuple:
    `(mode, filename, sha)`

    - `mode` is an ASCII decimal **string** similar to file mode
        in Unix systems. Subtrees always have mode "40000"
    - `filename` is a string filename, not including directories
    - `sha` is a 40 bytes hex string representing file content Blob SHA

    .. Note:: iteration is not recursive.
        For a recursive walk, use Tree.traverse() or Tree.files

    Both files and blobs can be checked for membership,
    either by their id (filename or SHA) or a corresponding object:

        >>> tree = Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d")
        >>> '.gitignore' in tree
        True
        >>> File('.keep') in tree
        False
        >>> '83d22195edc1473673f1bf35307aea6edf3c37e3' in tree
        True
        >>> Blob('83d22195edc1473673f1bf35307aea6edf3c37e3') in tree
        True

    `len(tree)` returns the number of files under the tree, including files in
    subtrees but not the subtrees themselves:

        >>> len(Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d"))
        16

    """
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

    def __len__(self):
        return len(self.files)

    def __contains__(self, item):
        if isinstance(item, File):
            return item.key in self.files
        elif isinstance(item, Blob):
            return item.sha in self.blob_shas
        elif not isinstance(item, str):
            return False

        return item in self.blob_shas or item in self.files

    def traverse(self):
        """ Recursively traverse the tree
        This will generate 3-tuples of the same format as direct tree
        iteration, but will recursively include subtrees content.

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

    @property
    def full(self):
        """ Formatted tree content, including recursive files and subtrees
        It is intended for debug purposes only.

        :return: multiline string, where each line contains mode, name and sha,
            with subtrees expanded
        """
        files = sorted(self.traverse(), key=lambda x: x[1])
        return "\n".join(" ".join(line) for line in files)

    @cached_property
    def parent_tree_shas(self):
        """ Tuple of SHA hashes of parent trees
        i.e. trees including this one as a subdirectory.
        """
        return slice20(self.read(PATHS['tree_parents'], 3))

    @property
    def parent_trees(self):
        """ Get parent trees
        :return: generator of parent Tree objects
        """
        return (Tree(sha) for sha in self.parent_tree_shas)

    def __str__(self):
        """
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
        """ A dict of all files and their content/blob sha under this tree.
        It includes recursive files (i.e. files in subdirectories).
        It does not include subdirectories themselves.
        """
        return {fname: sha
                for mode, fname, sha in self.traverse() if mode != "40000"}

    @property
    def blob_shas(self):
        """A tuple of all file content shas, including files in subdirectories
        """
        return tuple(self.files.values())

    @property
    def blobs(self):
        """ A generator of Blob objects with file content.
        It does include files in subdirectories.

        >>> tuple(Tree('d20520ef8c1537a42628b72d481b8174c0a1de84').blobs
        ...       )  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
        (<Blob: 2bdf5d686c6cd488b706be5c99c3bb1e166cf2f6>, ...,
         <Blob: c006bef767d08b41633b380058a171b7786b71ab>)
        """
        return (Blob(sha) for sha in self.files.values())


class Commit(GitObject):
    """ A git commit object.

    Commits have some special properties.
    Most of object properties provided by this project are lazy, i.e. they are
    computed when you access them for the first time.
    The following `Commit` properties will be instantiated all at once on the
    first access to *any* of them.

    - :data:`tree`:           root `Tree` of the commit
    - :data:`parent_shas`:    tuple of parent commit sha hashes
    - :data:`message`:        str, first line of the commit message
    - :data:`full_message`:   str, full commit message
    - :data:`author`:         str, Name <email>
    - :data:`authored_at`:    str, unix_epoch+timezone
    - :data:`committer`:      str, Name <email>
    - :data:`committed_at`:   str, unix_epoch+timezone
    """
    type = 'commit'

    def __getattr__(self, attr):
        """ Mimic special properties:
            tree:           root Tree of the commit
            parent_shas:    tuple of parent commit sha hashes
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
        >>> len(c.parent_shas)
        1
        >>> c.parent_shas[0]
        'ab124ab4baa42cd9f554b7bb038e19d4e3647957'
        >>> c.committed_at
        '1337350448 +1100'
        """
        if attr not in ('tree', 'parent_shas', 'message', 'full_message',
                        'author', 'committer', 'authored_at', 'committed_at'):
            raise AttributeError

        self.header, self.full_message = self.data.split("\n\n", 1)
        self.message = self.full_message.split("\n", 1)[0]
        parent_shas = []
        for line in self.header.split("\n"):
            key, value = line.strip().split(" ", 1)
            if key == "tree":
                self.tree = Tree(value)
            elif key == "parent":  # multiple parents possible
                parent_shas.append(value)
            elif key == "author":
                chunks = value.rsplit(" ", 2)
                self.author = chunks[0]
                self.authored_at = " ".join(chunks[1:])
            elif key == "committer":
                chunks = value.rsplit(" ", 2)
                self.committer = chunks[0]
                self.committed_at = " ".join(chunks[1:])
        self.parent_shas = tuple(parent_shas)

        return getattr(self, attr)

    @property
    def parents(self):
        """ A generator of parent commits.
        If you only need hashes (and not `Commit` objects),
        use `.parent_sha` instead

        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> tuple(c.parents)
        (<Commit: ab124ab4baa42cd9f554b7bb038e19d4e3647957>,)
        """
        return (Commit(sha) for sha in self.parent_shas)

    @cached_property
    def project_names(self):
        # type: () -> tuple
        """ URIs of projects including this commit.
        This property can be used to find all forks of a project
        by its first commit.

        >>> c = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
        >>> isinstance(c.project_names, tuple)
        True
        >>> len(c.project_names) > 0
        True
        >>> 'user2589_minicms' in c.project_names
        True
        """
        data = decomp(self.read(PATHS['commit_projects'], 3))
        return tuple((data and data.split(";")) or [])

    @property
    def projects(self):
        """ A generator of `Project` s, in which this commit is included.
        """
        return (Project(uri) for uri in self.project_names)

    @cached_property
    def child_shas(self):
        """ Children commit binary sha hashes.
        Basically, this is a reverse parent_shas

        >>> Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b').child_shas
        ('9bd02434b834979bb69d0b752a403228f2e385e8',)
        """
        # key_length will be ignored if =1
        return slice20(self.read(PATHS['commit_children'], 1))

    @property
    def children(self):
        """ A generator of children `Commit` objects

        >>> tuple(Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b').children)
        (<Commit: 9bd02434b834979bb69d0b752a403228f2e385e8>,)
        """
        return (Commit(sha) for sha in self.child_shas)

    @cached_property
    def blob_shas(self):
        """ SHA hashes of all blobs in the commit

        >>> Commit('af0048f4aac8f4760bf9b816e01524d7fb20a3fc').blob_shas  # doctest: +NORMALIZE_WHITESPACE
        ('b2f49ffef1c8d7ce83a004b34035f917713e2766',
         'c92011c5ccc32a9248bd929a6e56f846ac5b8072',
         'bf3c2d2df2ef710f995b590ac3e2c851b592c871')
        """
        return self.tree.blob_shas

    @property
    def blob_shas_rel(self):
        """
        This relation is known to miss every first file in all trees.
        Consider using Commit.tree.blobs as a slower but more accurate
        alternative.

        When this relation passes the test, please replace blob_sha with it
        It should be faster but as of now it is not accurate
        """
        warnings.warn(
            "This relation is known to miss every first file in all trees. "
            "Consider using Commit.tree.blobs as a slower but more accurate "
            "alternative", DeprecationWarning)
        return slice20(self.read(PATHS['commit_blobs'], 4))

    @property
    def blobs(self):
        """ A generator of `Blob` objects included in this commit

        >>> tuple(Commit('af0048f4aac8f4760bf9b816e01524d7fb20a3fc').blobs)  # doctest: +NORMALIZE_WHITESPACE
        (<Blob: b2f49ffef1c8d7ce83a004b34035f917713e2766>,
         <Blob: c92011c5ccc32a9248bd929a6e56f846ac5b8072>,
         <Blob: bf3c2d2df2ef710f995b590ac3e2c851b592c871>)
        """
        return (Blob(bin_sha) for bin_sha in self.blob_shas)


class Tag(GitObject):
    """ Tag doesn't have any functionality associated.
    You can't really do anything useful with it yet
    """
    type = 'tag'


class Project(_Base):
    """
    Projects are initialized with a URI:
        - Github: `{user}_{repo}`, e.g. `user2589_minicms`
        - Gitlab: `gl_{user}_{repo}`
        - Bitbucket: `bb_{user}_{repo}`
        - Bioconductor: `bc_{user}_{repo}`

    Projects are iterable:

        >>> for commit in Project('user2589_minicms'):  # doctest: +SKIP
        ...     print(commit.sha)

    Commits can be checked for membership in a project, either by their SHA
    hash or by a Commit object itself:

        >>> sha = 'e38126dbca6572912013621d2aa9e6f7c50f36bc'
        >>> sha in Project('user2589_minicms')
        True
        >>> Commit(sha) in Project('user2589_minicms')
        True
    """
    type = 'project'

    def __init__(self, uri):
        self.uri = uri
        super(Project, self).__init__(uri)

    def __iter__(self):
        """ Generator of all commits in the project.
        Order of commits is not guaranteed

        >>> commits = tuple(Project('user2589_minicms'))
        >>> len(commits) > 60
        True
        >>> isinstance(commits[0], Commit)
        True
        """
        for sha in self.commit_shas:
            c = Commit(sha)
            if c.author != 'GitHub Merge Button <merge-button@github.com>':
                yield c

    def __contains__(self, item):
        if isinstance(item, Commit):
            key = item.key
        elif isinstance(item, str):
            if len(item) == 20:
                key = item.encode('hex')
            elif len(item) == 40:
                key = item
            else:
                return False
        else:
            return False
        return key in self.commit_shas

    @classmethod
    def all(cls, name_prefix=''):
        """ Get all project URIs, with URI starting with an optional prefix

        Args:
            name_prefix (str): optional URI prefix
        Returns:
            a generator of `Project` objects
        """
        for key_prefix in range(8):
            tch_path = PATHS['project_commits'].format(key=key_prefix)
            for uri in tch_keys(tch_path, name_prefix):
                yield cls(uri)

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits in the project

        >>> Project('user2589_django-currencies').commit_shas # doctest: +NORMALIZE_WHITESPACE
        ('2dbcd43f077f2b5511cc107d63a0b9539a6aa2a7',
         '7572fc070c44f85e2a540f9a5a05a95d1dd2662d')
        """
        tch_path = PATHS['project_commits'].format(key=prefix(self.key, 3))
        return slice20(read_tch(tch_path, self.key))

    @property
    def commits(self):
        """ A generator of all Commit objects in the project.
        It has the same effect as iterating a `Project` instance itself.

        >>> tuple(Project('user2589_django-currencies').commits) # doctest: +NORMALIZE_WHITESPACE
        (<Commit: 2dbcd43f077f2b5511cc107d63a0b9539a6aa2a7>,
         <Commit: 7572fc070c44f85e2a540f9a5a05a95d1dd2662d>)
        """
        return (c for c in self)

    @cached_property
    def head(self):
        """ Get the last commit SHA, i.e. the repository HEAD

        >>> Project('user2589_minicms').head
        'f2a7fcdc51450ab03cb364415f14e634fa69b62c'
        """
        commits = {c.sha: c for c in self.commits}
        parents = set().union(*(c.parent_shas for c in commits.values()))
        heads = set(commits.keys()) - parents
        assert len(heads) == 1, "Unexpected number of heads"
        return tuple(heads)[0]

    @cached_property
    def tail(self):
        """ Get the first commit SHA by following first parents

        >>> Project('user2589_minicms').tail
        '1e971a073f40d74a1e72e07c682e1cba0bae159b'
        """
        commits = {c.sha: c for c in self.commits}
        pts = set(c.parent_shas[0] for c in commits.values() if c.parent_shas)
        for sha, c in commits.items():
            if sha in pts and not c.parent_shas:
                return sha

    @property
    def commits_fp(self):
        """ Get a commit chain by following only the first parent, to mimic
        https://git-scm.com/docs/git-log#git-log---first-parent .
        Thus, you only get a small subset of the full commit tree:

        >>> p = Project('user2589_minicms')
        >>> set(c.sha for c in p.commits_fp).issubset(p.commit_shas)
        True

        In scenarios where branches are not important, it can save a lot
        of computing.
        """
        commit = Commit(self.head)
        while commit:
            yield commit
            commit = commit.parent_shas and commit.parents.next()


class File(_Base):
    """
    Files are initialized with a path, starting from a commit root tree:

        >>> File('.gitignore')  # doctest: +SKIP
        >>> File('docs/Index.rst')  # doctest: +SKIP
    """
    type = 'file'

    def __init__(self, path):
        self.path = path
        super(File, self).__init__(path)

    @classmethod
    def all(cls, fname_prefix=''):
        """ Get all file names, starting with an optional prefix
        This method is heavy so it is moved to integration tests
        """
        for key_prefix in range(8):
            tch_path = PATHS['file_commits'].format(key=key_prefix)
            for fname in tch_keys(tch_path, fname_prefix):
                yield cls(fname)

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits changing this file

        **NOTE: this relation considers only diff with the first parent,
        which substantially limits its application**

        >>> commits = File('minicms/templatetags/minicms_tags.py').commit_shas
        >>> len(commits) > 0
        True
        >>> isinstance(commits, tuple)
        True
        >>> isinstance(commits[0], str)
        True
        >>> len(commits[0]) == 40
        True
        """
        file_path = self.key
        if not file_path.endswith("\n"):
            file_path += "\n"
        tch_path = PATHS['file_commits'].format(key=prefix(file_path, 3))
        return slice20(read_tch(tch_path, file_path))

    @property
    def commits(self):
        """ All commits changing the file

        **NOTE: this relation considers only diff with the first parent,
        which substantially limits its application**

        >>> cs = tuple(File('minicms/templatetags/minicms_tags.py').commits)
        >>> len(cs) > 0
        True
        >>> isinstance(cs[0], Commit)
        True
        """
        return (Commit(sha) for sha in self.commit_shas)


class Author(_Base):
    """
    Authors are initialized with a combination of name and email, as they
    appear in git configuration.

        >>> Author('John Doe <john.doe@aol.com>')  # doctest: +SKIP

    At this point we don't have a relation to map all aliases of the same
    author, so keep in mind this object represents an alias, not a person.
    """
    type = 'author'

    def __init__(self, full_email):
        self.full_email = full_email
        super(Author, self).__init__(full_email)

    @classmethod
    def all(cls, name_prefix=''):
        """ Get all author names, starting with an optional prefix
        This method is heavy so it is moved to integration tests
        """
        for name in tch_keys(PATHS['author_commits'], name_prefix):
            yield cls(name)

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits authored by the Author

        >>> commits = Author('user2589 <valiev.m@gmail.com>').commit_shas
        >>> len(commits) > 50
        True
        >>> isinstance(commits, tuple)
        True
        >>> isinstance(commits[0], str)
        True
        >>> len(commits[0]) == 40
        True
        """
        return slice20(read_tch(PATHS['author_commits'], self.key))

    @property
    def commits(self):
        """ A generator of all Commit objects authored by the Author

        >>> commits = tuple(Author('user2589 <valiev.m@gmail.com>').commits)
        >>> len(commits) > 50
        True
        >>> isinstance(commits[0], Commit)
        True
        """
        return (Commit(sha) for sha in self.commit_shas)

    @cached_property
    def file_names(self):
        """ All file names the Author has changed

        >>> fnames = Author('user2589 <valiev.m@gmail.com>').file_names
        >>> len(fnames) > 50
        True
        >>> isinstance(fnames, tuple)
        True
        >>> isinstance(fnames[0], str)
        True
        """
        data = decomp(read_tch(PATHS['author_files'], self.key))
        return tuple((data and data.split(";")) or [])

    @property
    def files(self):
        """ All File objects changed by the Author

        >>> fnames = tuple(Author('user2589 <valiev.m@gmail.com>').files)
        >>> len(fnames) > 50
        True
        >>> isinstance(fnames[0], File)
        True
        """
        return (File(fname) for fname in self.file_names)
