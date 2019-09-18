import lzf
# da4 doesn't have libgit2-dev to install pygit2 yet
# import pygit2
from tokyocabinet import hash as tch

from datetime import datetime, timedelta, tzinfo
import difflib
from functools import wraps
import hashlib
import os
import time
import warnings
import fnvhash


__version__ = '1.2.2'
__author__ = "Marat (@cmu.edu)"
__license__ = "GPL v3"

PATHS = {
    # data_type: (path, prefix_bit_length)
    # prefix length means that the data are split into 2**n files,
    # e.g. key is in 0..31 for prefix length of 5 bit.

    # The most critical: raw data for the initial storage, use in sweeps, 100TB da4+ backup
    'commit_sequential_idx': ('/data/All.blobs/commit_{key}.idx', 7),
    'commit_sequential_bin': ('/data/All.blobs/commit_{key}.bin', 7),
    'tree_sequential_idx': ('/data/All.blobs/blob_{key}.idx', 7),
    'tree_sequential_bin': ('/data/All.blobs/blob_{key}.bin', 7),

    # critical - random access to trees and commits on da3 and da4, 10TB
    'commit_random': ('/fast/All.sha1c/commit_{key}.tch', 7),
    'tree_random': ('/fast/All.sha1c/tree_{key}.tch', 7),

    'blob_offset': ('/fast/All.sha1o/sha1.blob_{key}.tch', 7),
    'blob_data': ('/data/All.blobs/blob_{key}.bin', 7),
    # the rest of x_data is currently unused:
    # 'commit_data': ('/data/All.blobs/commit_{key}.bin',  # 7)
    # 'tree_data': ('/data/All.blobs/tree_{key}.bin', 7)
    # 'tag_data': ('/data/All.blobs/tag_{key}.bin', 7)

    # relations - good to have but not critical
    'commit_projects': ('/da0_data/basemaps/c2pFullP.{key}.tch', 5),
    'commit_children': ('/da0_data/basemaps/c2ccFullP.{key}.tch', 5),
    'commit_blobs': ('/da0_data/basemaps/c2bFullP.{key}.tch', 5),
    'commit_files': ('/da0_data/basemaps/c2fFullP.{key}.tch', 5),
    'project_commits': ('/da0_data/basemaps/p2cFullP.{key}.tch', 5),
    'author_commits': ('/da0_data/basemaps/a2cFullP.{key}.tch', 5),
    'author_projects': ('/da0_data/basemaps/a2pFullP.{key}.tch', 5),
    'author_trpath':('/da0_data/basemaps/a2trpO.tch', 5),
    'blob_commits': ('/da0_data/basemaps/b2cFullP.{key}.tch', 5),
    'blob_authors': ('/da0_data/basemaps/b2aFullP.{key}.tch', 5),
    'file_commits': ('/da0_data/basemaps/f2cFullP.{key}.tch', 5),

    ####  dictionary entries added after 5/12/19  #####
    'file_blobs': ('/da0_data/basemaps/f2bFullP.{key}.tch', 5),
    'commit_time_author': ('/da0_data/basemaps/c2taFullP.{key}.tch', 5),
    'project_authors': ('/da0_data/basemaps/p2aFullP.{key}.tch', 5),
    'blob_files': ('/da0_data/basemaps/b2fFullP.{key}.tch', 5),
    'commit_head': ('/da0_data/basemaps/c2hFullO.{key}.tch', 5),

    # another way to get commit parents, currently unused
    # 'commit_parents': ('/da0_data/basemaps/c2pcK.{key}.tch', 7)

    # SHA1 cache, on da3 and d4  668G
    'blob_index_line': ('/fast/All.sha1/sha1.blob_{key}.tch', 7),
    'tree_index_line': ('/fast/All.sha1/sha1.tree_{key}.tch', 7),
    'commit_index_line': ('/fast/All.sha1/sha1.commit_{key}.tch', 7),
    'tag_index_line': ('/fast/All.sha1/sha1.tag_{key}.tch', 7)
}


class ObjectNotFound(KeyError):
    pass


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
    if raw_data is None:
        return ()

    return tuple(raw_data[i:i + 20].encode('hex')
                 for i in range(0, len(raw_data), 20))

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
        return timedelta(0)

    def __repr__(self):
        h, m = divmod(self.offset.seconds // 60, 60)
        return "<Timezone: %02d:%02d>" % (h, m)


DAY_Z = datetime.fromtimestamp(0, CommitTimezone(0, 0))


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
    :rtype: datetime.datetime or None

    >>> parse_commit_date('1337145807 +1100')
    datetime.datetime(2012, 5, 16, 16, 23, 27, tzinfo=<Timezone: 11:00>)
    >>> parse_commit_date('3337145807 +1100') is None
    True
    """
    ts, tz = timestamp.split()
    sign = -1 if tz.startswith('-') else 1
    try:
        ts = int(ts)
        hours, minutes = sign * int(tz[-4:-2]), sign * int(tz[-2])
        dt = datetime.fromtimestamp(ts, CommitTimezone(hours, minutes))
    except ValueError:
        # i.e. if timestamp or timezone is invalid
        return None

    # timestamp is in the future
    if ts > time.time():
        return None

    return dt


# Pool of open TokyoCabinet databases to save few milliseconds on opening
_TCH_POOL = {}


def _get_tch(path):
    if not path.endswith('.tch'):
        path += '.tch'
    if path not in _TCH_POOL:
        _TCH_POOL[path] = tch.Hash()
        _TCH_POOL[path].open(path, tch.HDBOREADER | tch.HDBONOLCK)
        # _TCH_POOL[path].setmutex()
    return _TCH_POOL[path]


def read_tch(path, key, silent=False):
    """ Read a value from a Tokyo Cabinet file by the specified key
    Main purpose of this method is to cached open .tch handlers
    in _TCH_POOL to speedup reads
    """

    try:
        return _get_tch(path)[key]
    except:
      return None
        #raise IOError("Tokyocabinet file " + path + " not found")
    #except KeyError:
     #   if silent:
     #       return ''
     #   raise ObjectNotFound(path + " " + key)

def tch_keys(path, key_prefix=''):
    return _get_tch(path).fwmkeys(key_prefix)


def resolve_path(dtype, object_key, use_fnv=False):
    # type: (str, str, bool) -> str
    """ Get path to a file using data type and object key (for sharding) """
    path, prefix_length = PATHS[dtype]

    p = fnvhash.fnv1a_32(object_key) if use_fnv else ord(object_key[0])
    prefix = p & (2**prefix_length - 1)
    return path.format(key=prefix)


class _Base(object):
    type = None
    key = None
    # fnv keys are used for non-git objects, such as files, projects and authors
    use_fnv_keys = True
    _keys_registry_dtype = None

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

    def resolve_path(self, dtype):
        return resolve_path(dtype, self.key, self.use_fnv_keys)

    def read_tch(self, dtype, silent=True):
        """ Resolve the path and read .tch"""
        return read_tch(self.resolve_path(dtype), self.key, silent)

    @classmethod
    def all(cls):
        """ Iterate all objects of the given type

        This might be useful to get a list of all projects, or a list of
        all file names.

        Returns:
            a generator of `Project` objects
        """
        if not cls._keys_registry_dtype:
            raise NotImplemented

        base_path, prefix_length = PATHS[cls._keys_registry_dtype]
        for file_prefix in range(2 ** prefix_length):
            tch_path = base_path.format(key=file_prefix)
            for key in tch_keys(tch_path):
                yield cls(key)


class GitObject(_Base):
    use_fnv_keys = False

    @classmethod
    def all(cls):
        """ Iterate ALL objects of this type (all projects, all times) """
        base_idx_path, prefix_length = PATHS[cls.type + '_sequential_idx']
        base_bin_path, prefix_length = PATHS[cls.type + '_sequential_bin']
        for key in range(2**prefix_length):
            idx_path = base_idx_path.format(key=key)
            bin_path = base_bin_path.format(key=key)
            datafile = open(bin_path)
            for line in open(idx_path):
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
            datafile.close()

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
        self.key = self.sha
        super(GitObject, self).__init__(sha)

    def resolve_path(self, dtype):
        # overriding to use bin_sha instead of the key (which is sha)
        return resolve_path(dtype, self.bin_sha, self.use_fnv_keys)

    def read_tch(self, dtype, silent=True):
        """ Resolve the path and read .tch"""
        return read_tch(self.resolve_path(dtype), self.bin_sha, silent)

    @cached_property
    def data(self):
        if self.type not in ('commit', 'tree'):
            raise NotImplementedError
        # default implementation will only work for commits and trees
        return decomp(self.read_tch(self.type + '_random', silent=False))

    @classmethod
    def string_sha(cls, data):
        """Manually compute blob sha from its content passed as `data`.

        The main use case for this method is to identify source of a file.

        Blob SHA is computed from a string:
        "blob <file content length as str><null byte><file content>"

        # https://gist.github.com/masak/2415865
        Commit SHAs are computed in a similar way
        "commit <commit length as str><null byte><commit content>"

        note that commit content includes committed/authored date

        Args:
            data (str): content of the GitObject to get hash for

        Returns:
            str: 40-byte hex SHA1 hash
        """
        sha1 = hashlib.sha1()
        sha1.update("%s %d\x00" % (cls.type, len(data)))
        sha1.update(data)
        return sha1.hexdigest()

    @classmethod
    def file_sha(cls, path):
        buffsize = 1024 ** 2
        size = os.stat(path).st_size
        fh = open(path, 'rb')
        sha1 = hashlib.sha1()
        sha1.update("%s %d\x00" % (cls.type, size))
        while size > 0:
            data = fh.read(min(size, buffsize))
            if not data:
                return sha1.hexdigest()
            sha1.update(data)

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
        _, length = self.position
        return length

    @classmethod
    def string_sha(cls, data):
        """
        >>> Blob.string_sha('Hello world!')
        '6769dd60bdf536a83c9353272157893043e9f7d0'
        """
        # return pygit2.hash(data)
        return super(Blob, cls).string_sha(data)

    @classmethod
    def file_sha(cls, path):
        """Manually compute blob sha from a file content.

        Similar to string_sha
        >>> Blob.file_sha('LICENSE')
        '94a9ed024d3859793618152ea559a168bbcbb5e2'
        """
        # return pygit2.hashfile(path)
        return super(Blob, cls).file_sha(path)

    @cached_property
    def position(self):
        """ Get offset and length of the blob data in the storage """
        try:
            offset, length = unber(self.read_tch('blob_offset'))
        except ValueError:  # empty read -> value not found
            raise ObjectNotFound('Blob data not found (bad sha?)')
        return offset, length

    @cached_property
    def data(self):
        """ Content of the blob """
        offset, length = self.position
        # no caching here to stay thread-safe
        with open(self.resolve_path('blob_data'), 'rb') as fh:
            fh.seek(offset)
            return decomp(fh.read(length))

    @cached_property
    def commit_shas(self):
        """ SHAs of Commits in which this blob have been
        introduced or modified.

        **NOTE: commits removing this blob are not included**
        """
        return slice20(self.read_tch('blob_commits'))

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
        It does NOT include subdirectories themselves.
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
        return (Blob(sha) for sha in self.blob_shas)


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
            authored_at:    timezone-aware datetime or None (if invalid)
            committer:      str, Name <email>
            committed_at:   timezone-aware datetime or None (if invalid)
            signature:      str or None, PGP signature

        Commit: https://github.com/user2589/minicms/commit/e38126db
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> c.author.startswith('Marat')
        True
        >>> c.authored_at
        datetime.datetime(2012, 5, 19, 1, 14, 8, tzinfo=<Timezone: 11:00>)
        >>> c.tree.sha
        '6845f55f47ddfdbe4628a83fdaba35fa4ae3c894'
        >>> len(c.parent_shas)
        1
        >>> c.parent_shas[0]
        'ab124ab4baa42cd9f554b7bb038e19d4e3647957'
        >>> c.committed_at
        datetime.datetime(2012, 5, 19, 1, 14, 8, tzinfo=<Timezone: 11:00>)
        """
        attrs = ('tree', 'parent_shas', 'message', 'full_message', 'author',
                 'committer', 'authored_at', 'committed_at', 'signature')
        if attr not in attrs:
            raise AttributeError

        for a in attrs:
            setattr(self, a, None)

        self.header, self.full_message = self.data.split("\n\n", 1)
        self.message = self.full_message.split("\n", 1)[0]
        parent_shas = []
        signature = None
        reading_signature = False
        for line in self.header.split("\n"):
            if reading_signature:
                # examples:
                #   1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab
                #   cbbc685c45bdff4da5ea0984f1dd3a73486b4556
                signature += line
                if line.strip() == "-----END PGP SIGNATURE-----":
                    self.signature = signature
                    reading_signature = False
                continue

            if line.startswith(" "):  # mergetag object, not supported (yet?)
                # example: c1313c68c7f784efaf700fbfb771065840fc260a
                continue

            line = line.strip()
            if not line:  # sometimes there is an empty line after gpgsig
                continue
            try:
                key, value = line.split(" ", 1)
            except ValueError:
                raise ValueError("Unexpected header in commit " + self.sha)

            if key == "tree":
                self.tree = Tree(value)
            elif key == "parent":  # multiple parents possible
                parent_shas.append(value)
            elif key == "author":
                # author name can have arbitrary number of spaces while
                # timestamp is guaranteed to have one, so rsplit
                chunks = value.rsplit(" ", 2)
                self.author = chunks[0]
                self.authored_at = parse_commit_date(" ".join(chunks[1:]))
            elif key == "committer":
                # same logic as author
                chunks = value.rsplit(" ", 2)
                self.committer = chunks[0]
                self.committed_at = parse_commit_date(" ".join(chunks[1:]))
            elif key == 'gpgsig':
                signature = value
                reading_signature = True
        self.parent_shas = tuple(parent_shas)

        return getattr(self, attr)

    def __sub__(self, parent, threshold=0.5):
        """ Compare two Commits.

        Args:
            parent (Commit): another commit to compare to.
                Expected order is `diff = child_commit - parent_commit`

        Returns:
            Generator[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]]:
                4-tuples: `(old_path, new_path, old_sha, new_sha)`

            Examples:
            - a new file 'setup.py' was created:
                `(None, 'setup.py', None, 'file_sha')`
            - an existing 'setup.py' was deleted:
                `('setup.py', None, 'old_file_sha', None)`
            - setup.py.old was renamed to setup.py, content unchanged:
                `('setup.py.old', 'setup.py', 'file_sha', 'file_sha')`
            - setup.py was edited:
                `('setup.py', 'setup.py', 'old_file_sha', 'new_file_sha')`
            - setup.py.old was edited and renamed to setup.py:
                `('setup.py.old', 'setup.py', 'old_file_sha', 'new_file_sha')`

        Detecting the last one is computationally expensive. You can adjust this
        behaviour by passing the `threshold` parameter, which is 0.5 by default.
        It means that if roughly 50% of the file content is the same,
        it is considered a match. `threshold=1` means that only exact
        matches are considered, effectively disabling this comparison.
        If threshold is set to 0, any pair of deleted and added file will be
        considered renamed and edited; this last case doesn't make much sense so
        don't set it too low.
        """
        if parent.sha not in self.parent_shas:
            warnings.warn("Comparing non-adjacent commits might be "
                          "computationally expensive. Proceed with caution.")

        # filename: (blob sha before, blob sha after)
        new_files = self.tree.files
        new_paths = set(new_files.keys())
        old_files = parent.tree.files
        old_paths = set(old_files.keys())

        # unchanged_paths
        for fname in new_paths.intersection(old_paths):
            if new_files[fname] != old_files[fname]:
                # i.e. the Blob sha is the same
                yield (fname, fname, old_files[fname], new_files[fname])

        added_paths = new_paths - old_paths
        deleted_paths = old_paths - new_paths

        if threshold >= 1:  # i.e. only exact matches are considered
            for fname in added_paths:
                yield (None, fname, None, new_files[fname])
            for fname in deleted_paths:
                yield (fname, None, old_files[fname], None)
            return

        # search for matches
        sm = difflib.SequenceMatcher()
        added_blobs = {f: Blob(new_files[f]) for f in added_paths}
        deleted_blobs = {f: Blob(old_files[f]) for f in deleted_paths}
        # for each added blob, try to find a match in deleted blobs
        #   if there is a match, signal a rename and remove from deleted
        #   if there is no match, signal a new file
        # unused deleted blobs are indeed deleted
        for added_fname, added_blob in added_blobs.items():
            sm.set_seq1(added_blob)
            matched = False
            for deleted_fname, deleted_blob in deleted_blobs.items():
                sm.set_seq2(deleted_blob)
                # use quick checks first (lower bound by length diff)
                if sm.real_quick_ratio() > threshold \
                        and sm.quick_ratio() > threshold \
                        and sm.ratio() > threshold:
                    yield (deleted_fname, added_fname, deleted_blob, added_blob)
                    del(deleted_blobs[deleted_fname])
                    matched = True
                    break
            if not matched:  # this is a new file
                yield (None, added_fname, None, added_blob)

        for deleted_fname, deleted_blob in deleted_blobs.items():
            yield (deleted_fname, None, deleted_blob, None)

    @property
    def parents(self):
        """ A generator of parent commits.
        If you only need hashes (and not `Commit` objects),
        use `.parent_sha` instead

        Commit: https://github.com/user2589/minicms/commit/e38126db
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

        Commit: https://github.com/user2589/minicms/commit/f2a7fcdc
        >>> c = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
        >>> isinstance(c.project_names, tuple)
        True
        >>> len(c.project_names) > 0
        True
        >>> 'user2589_minicms' in c.project_names
        True
        """
        data = decomp(self.read_tch('commit_projects'))
        return tuple(project_name
                     for project_name in (data and data.split(";")) or []
                     if project_name and project_name != 'EMPTY')

    @property
    def projects(self):
        """ A generator of `Project` s, in which this commit is included.
        """
        return (Project(uri) for uri in self.project_names)

    @cached_property
    def child_shas(self):
        """ Children commit binary sha hashes.
        Basically, this is a reverse parent_shas

        Commit: https://github.com/user2589/minicms/commit/1e971a07
        >>> Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b').child_shas
        ('9bd02434b834979bb69d0b752a403228f2e385e8',)
        """
        return slice20(self.read_tch('commit_children'))

    @property
    def children(self):
        """ A generator of children `Commit` objects

        Commit: https://github.com/user2589/minicms/commit/1e971a07
        >>> tuple(Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b').children)
        (<Commit: 9bd02434b834979bb69d0b752a403228f2e385e8>,)
        """
        return (Commit(sha) for sha in self.child_shas)

    @cached_property
    def blob_shas(self):
        """ SHA hashes of all blobs in the commit

        >>> Commit('af0048f4aac8f4760bf9b816e01524d7fb20a3fc').blob_shas
        ...        # doctest: +NORMALIZE_WHITESPACE
        ('b2f49ffef1c8d7ce83a004b34035f917713e2766',
         'c92011c5ccc32a9248bd929a6e56f846ac5b8072',
         'bf3c2d2df2ef710f995b590ac3e2c851b592c871')
        """
        return self.tree.blob_shas

    @cached_property
    def changed_file_names(self):
        data = decomp(self.read_tch('commit_files'))
        return tuple((data and data.split(";")) or [])

    def files_changed(self):
        return (File(filename) for filename in self.changed_file_names)

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
        return slice20(self.read_tch('commit_blobs'))

    @property
    def blobs(self):
        """ A generator of `Blob` objects included in this commit

        >>> tuple(Commit('af0048f4aac8f4760bf9b816e01524d7fb20a3fc').blobs)
        ...              # doctest: +NORMALIZE_WHITESPACE
        (<Blob: b2f49ffef1c8d7ce83a004b34035f917713e2766>,
         <Blob: c92011c5ccc32a9248bd929a6e56f846ac5b8072>,
         <Blob: bf3c2d2df2ef710f995b590ac3e2c851b592c871>)
        """
        return (Blob(bin_sha) for bin_sha in self.blob_shas)

    @cached_property
    def files(self):
        data = decomp(self.read_tch('commit_files'))
        return tuple(file_name 
        for file_name in (data and data.split(";")) or [] if file_name and file_name != 'EMPTY')

class Commit_info(GitObject):
    @cached_property
    def time_author(self):
        data = self.read_tch('commit_time_author')
        return tuple(time_author 
        for time_author in (data and data.split(";")))

    @cached_property
    def head(self):
      data = slice20(self.read_tch('commit_head'))
      return data 

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
        - Bioconductor: `bioconductor.org_{user}_{repo}`
        - kde: `kde.org_{user}_{repo}`
        - drupal: `drupal.org_{user}_{repo}` 
        - Googlesouce: `android.googlesource.com_{repo}_{user}`
        - Linux kernel: `git.kernel.org_{user}_{repo}`
        - PostgreSQL: `git.postgresql.org_{user}_{repo}`
        - GNU Savannah: `git.savannah.gnu.org_{user}_{repo}`
        - ZX2C4: `git.zx2c4.com_{user}_{repo}`
        - GNOME: `gitlab.gnome.org_{user}_{repo}`
        - repo.or.cz: `repo.or.cz_{user}_{repo}`
        - Salsa: `salsa.debian.org_{user}_{repo}`
        - SourceForge: `sourceforge.net_{user}_{repo}`
  
    Projects are iterable:

        >>> for commit in Project('user2589_minicms'):  # doctest: +SKIP
        ...     print(commit.sha)

    Commits can be checked for membership in a project, either by their SHA
    hash or by a Commit object itself:

        Commit: https://github.com/user2589/minicms/commit/e38126db
        >>> sha = 'e38126dbca6572912013621d2aa9e6f7c50f36bc'
        >>> sha in Project('user2589_minicms')
        True
        >>> Commit(sha) in Project('user2589_minicms')
        True
    """

    type = 'project'
    _keys_registry_dtype = 'project_commits'

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
            try:
                c = Commit(sha)
                author = c.author
            except ObjectNotFound:
                continue
            if author != 'GitHub Merge Button <merge-button@github.com>':
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

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits in the project

        >>> Project('user2589_django-currencies').commit_shas
        ...         # doctest: +NORMALIZE_WHITESPACE
        ('2dbcd43f077f2b5511cc107d63a0b9539a6aa2a7',
         '7572fc070c44f85e2a540f9a5a05a95d1dd2662d')
        """
        tch_path = self.resolve_path('project_commits')
        return slice20(read_tch(tch_path, self.key, silent=True))

    @property
    def commits(self):
        """ A generator of all Commit objects in the project.
        It has the same effect as iterating a `Project` instance itself,
        with some additional validation of commit dates.

        >>> tuple(Project('user2589_django-currencies').commits)
        ...       # doctest: +NORMALIZE_WHITESPACE
        (<Commit: 2dbcd43f077f2b5511cc107d63a0b9539a6aa2a7>,
         <Commit: 7572fc070c44f85e2a540f9a5a05a95d1dd2662d>)
        """
        commits = tuple(c for c in self)
        tails = tuple(c for c in commits
                      if not c.parent_shas and c.authored_at is not None)
        if tails:
            min_date = min(c.authored_at for c in tails)
        else:  # i.e. if all tails have invalid date
            min_date = DAY_Z

        for c in commits:
            if c.authored_at and c.authored_at < min_date:
                c.authored_at = None
            yield c

    @cached_property
    def head(self):
        """ Get the HEAD commit of the repository

        >>> Project('user2589_minicms').head
        <Commit: f2a7fcdc51450ab03cb364415f14e634fa69b62c>
        >>> Project('RoseTHERESA_SimpleCMS').head
        <Commit: a47afa002ccfd3e23920f323b172f78c5c970250>
        """
        # Sometimes (very rarely) commit dates are wrong, so the latest commit
        # is not actually the head. The magic below is to account for this
        commits = {c.sha: c for c in self.commits}
        parents = set().union(*(c.parent_shas for c in commits.values()))
        heads = set(commits.keys()) - parents

        # it is possible that there is more than one head.
        # E.g. it happens when HEAD is moved manually (git reset)
        # and continued with a separate chain of commits.
        # in this case, let's just use the latest one
        # actually, storing refs would make it much simpler
        return sorted((commits[sha] for sha in heads),
                      key=lambda c: c.authored_at or DAY_Z)[-1]

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

        Note: commits will come in order from the latest to the earliest.
        """
        # Simplified version of self.head():
        #   - slightly less precise,
        #   - 20% faster
        #
        # out of 500 randomly sampled projects, 493 had the same head.
        # In the remaining 7:
        #     2 had the same commit chain length,
        #     3 had one more commit
        #     1 had two more commits
        #     1 had three more commits
        # Execution time:
        #   simplified version (argmax): ~153 seconds
        #   self.head(): ~190 seconds

        # at this point we know all commits are in the dataset
        # (validated in __iter___)
        commits = {c.sha: c for c in self.commits}
        commit = max(commits.values(), key=lambda c: c.authored_at or DAY_Z)
        while commit:
            try:  # here there is no guarantee commit is in the dataset
                first_parent = commit.parent_shas and commit.parent_shas[0]
            except ObjectNotFound:
                break

            yield commit

            if not first_parent:
                break

            commit = commits.get(first_parent, Commit(first_parent))

    def toURL(self):
      '''
      Get the URL for a given project URI
      >>> Project('CS340-19_lectures').toURL()
      'http://github.com/CS340-19/lectures'
      '''
      p_name = self.uri
      found = False
      toUrlMap = {
        "bb": "bitbucket.org", "gl": "gitlab.org",
        "android.googlesource.com": "android.googlesource.com",
        "bioconductor.org": "bioconductor.org",
        "drupal.com": "git.drupal.org", "git.eclipse.org": "git.eclipse.org",
        "git.kernel.org": "git.kernel.org",
        "git.postgresql.org": "git.postgresql.org" ,
        "git.savannah.gnu.org": "git.savannah.gnu.org",
        "git.zx2c4.com": "git.zx2c4.com" ,
        "gitlab.gnome.org": "gitlab.gnome.org",
        "kde.org": "anongit.kde.org",
        "repo.or.cz": "repo.or.cz",
        "salsa.debian.org": "salsa.debian.org",
        "sourceforge.net": "git.code.sf.net/p"}

      for URL in toUrlMap.keys():
        URL_ = URL + "_"
        if p_name.startswith(URL_) and (p_name.count('_') >= 2 or URL == "sourceforge.net"):
          replacement = toUrlMap[URL] + "/"
          p_name = p_name.replace(URL_, replacement)
          found = True
          break

      if not found: 
        p_name = "github.com/" + p_name
 
      p_name = p_name.replace('_', '/', 1)
      return "https://" + p_name  
    
    @cached_property
    def author_names(self):
        data = decomp(self.read_tch('project_authors'))
        return tuple(author_name 
        for author_name in (data and data.split(";")) or [] if author_name and author_name != 'EMPTY')


class File(_Base):
    """
    Files are initialized with a path, starting from a commit root tree:

        >>> File('.gitignore')  # doctest: +SKIP
        >>> File('docs/Index.rst')  # doctest: +SKIP
    """
    type = 'file'
    _keys_registry_dtype = 'file_commits'

    def __init__(self, path):
        self.path = path
        super(File, self).__init__(path)

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
        #if not file_path.endswith("\n"):
        #    file_path += "\n"
        tch_path = resolve_path('file_commits', file_path, self.use_fnv_keys)
        return slice20(read_tch(tch_path, file_path, silent=True))

    @property
    def commits(self):
        """ All commits changing the file

        .. note: this relation considers only diff with the first parent,
            which substantially limits its application

        >>> cs = tuple(File('minicms/templatetags/minicms_tags.py').commits)
        >>> len(cs) > 0
        True
        >>> isinstance(cs[0], Commit)
        True
        """
        for sha in self.commit_shas:
            c = Commit(sha)
            try:
                author = c.author
            except ObjectNotFound:
                continue
            if author != 'GitHub Merge Button <merge-button@github.com>':
                yield c

    def __str__(self):
        return super(File, self).__str__().rstrip("\n\r")


class Author(_Base):
    """
    Authors are initialized with a combination of name and email, as they
    appear in git configuration.

        >>> Author('John Doe <john.doe@aol.com>')  # doctest: +SKIP

    At this point we don't have a relation to map all aliases of the same
    author, so keep in mind this object represents an alias, not a person.
    """
    type = 'author'
    _keys_registry_dtype = 'author_commits'

    def __init__(self, full_email):
        self.full_email = full_email
        super(Author, self).__init__(full_email)

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
        return slice20(self.read_tch('author_commits', silent=True))

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
    def project_names(self):
        """ URIs of projects where author has committed to 
A generator of all Commit objects authored by the Author
        """
        data = decomp(self.read_tch('author_projects'))
        return tuple(project_name
          for project_name in (data and data.split(";")) or [] if project_name and project_name != 'EMPTY')
    
    @cached_property
    def torvald(self):
      data = decomp(self.read_tch('author_trpath'))
      return tuple(path for path in (data and data.split(";")))
