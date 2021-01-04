
# cython: language_level=3str, wraparound=False, boundscheck=False, nonecheck=False

import binascii
from cpython.version cimport PY_MAJOR_VERSION
from datetime import datetime, timedelta, tzinfo
import difflib
from functools import wraps
import glob
import hashlib
from libc.stdint cimport uint8_t, uint32_t, uint64_t
from libc.stdlib cimport free
from math import log
import os
import re
from threading import Lock
import time
from typing import Dict, Tuple
import warnings

# if throws "module 'lzf' has no attribute 'decompress'",
# `pip uninstall lzf && pip install python-lzf`
import lzf

__version__ = '2.0.4'
__author__ = 'marat@cmu.edu'
__license__ = 'GPL v3'

if PY_MAJOR_VERSION < 3:
    str_type = unicode
    bytes_type = str
else:
    str_type = str
    bytes_type = bytes


try:
    with open('/etc/hostname') as fh:
        HOSTNAME = fh.read().strip()
except IOError:
    raise ImportError('Oscar only support Linux hosts so far')

HOST = HOSTNAME.split('.', 1)[0]
DOMAIN = HOSTNAME[len(HOST):]
IS_TEST_ENV = 'OSCAR_TEST' in os.environ

# test environment has 'OSCAR_TEST' environment variable set
if not IS_TEST_ENV:
    if not DOMAIN.endswith(r'.eecs.utk.edu$'):
        raise ImportError('Oscar is only available on certain servers at UTK, '
                          'please modify to match your cluster configuration')

    if HOST not in ('da4', 'da5'):
        warnings.warn('Commit and tree direct content is only available on da4.'
                      ' Some functions might not work as expected.\n\n')

# Cython is generally smart enough to convert data[i] to int, but
# pyximport in Py2 fails to do so, requires to use ord explicitly
# TODO: get rid of this shame once Py2 support is dropped
cdef uint8_t nth_byte(bytes data, uint32_t i):
    if PY_MAJOR_VERSION < 3:
        return ord(data[i])
    return data[i]

def _latest_version(path_template):
    if '{ver}' not in path_template:
        return ''
    # Using * to allow for two-character versions
    glob_pattern = path_template.format(key=0, ver='*')
    filenames = glob.glob(glob_pattern)
    prefix, postfix = glob_pattern.split('*', 1)
    versions = [fname[len(prefix):-len(postfix)] for fname in filenames]
    return max(versions or [''], key=lambda ver: (len(ver), ver))


def _key_length(str path_template):
    # type: (str) -> int
    if '{key}' not in path_template:
        return 0
    glob_pattern = path_template.format(key='*', ver='*')
    filenames = glob.glob(glob_pattern)
    # key always comes the last, so rsplit is enough to account for two stars
    prefix, postfix = glob_pattern.rsplit('*', 1)
    # note that with wraparound=False we can't use negative indexes.
    # this caused hard to catch bugs before
    str_keys = [fname[len(prefix):len(fname)-len(postfix)] for fname in filenames]
    keys = [int(key) for key in str_keys if key]
    # Py2/3 compatible version
    return int(log(max(keys or [0]) + 1, 2))


# this dict is only for debugging purposes and it is not used anywhere
VERSIONS = {}  # type: Dict[str, str]


def _get_paths(dict raw_paths):
    # type: (Dict[str, Tuple[str, Dict[str, str]]]) -> Dict[str, Tuple[bytes, int]]
    """
    Compose path from
    Args:
        raw_paths (Dict[str, Tuple[str, Dict[str, str]]]): see example below

    Returns:
        (Dict[str, Tuple[str, int]]: map data type to a path template and a key
            length, e.g.:
            'author_commits' -> ('/da0_data/basemaps/a2cFullR.{key}.tch', 5)
    """
    paths = {}  # type: Dict[str, Tuple[bytes, int]]
    local_data_prefix = '/' + HOST + '_data'
    for category, (path_prefix, filenames) in raw_paths.items():
        cat_path_prefix = os.environ.get(category, path_prefix)
        cat_version = os.environ.get(category + '_VER') or _latest_version(
            os.path.join(cat_path_prefix, list(filenames.values())[0]))

        if cat_path_prefix.startswith(local_data_prefix):
            cat_path_prefix = '/data' + cat_path_prefix[len(local_data_prefix):]

        for ptype, fname in filenames.items():
            ppath = os.environ.get(
                '_'.join(['OSCAR', ptype.upper()]), cat_path_prefix)
            pver = os.environ.get(
                '_'.join(['OSCAR', ptype.upper(), 'VER']), cat_version)
            path_template = os.path.join(ppath, fname)
            # TODO: .format with pver and check keys only
            # this will allow to handle 2-char versions
            key_length = _key_length(path_template)
            if not key_length and not IS_TEST_ENV:
                warnings.warn("No keys found for path_template %s:\n%s" % (
                    ptype, path_template))
            VERSIONS[ptype] = pver
            paths[ptype] = (
                path_template.format(ver=pver, key='{key}'), key_length)
    return paths


# note to future self: Python2 uses str (bytes) for os.environ,
# Python3 uses str (unicode). Don't add Py2/3 compatibility prefixes here
PATHS = _get_paths({
    'OSCAR_ALL_BLOBS': ('/da4_data/All.blobs/', {
        'commit_sequential_idx': 'commit_{key}.idx',
        'commit_sequential_bin': 'commit_{key}.bin',
        'tree_sequential_idx': 'tree_{key}.idx',
        'tree_sequential_bin': 'tree_{key}.bin',
        'blob_data': 'blob_{key}.bin',
    }),
    'OSCAR_ALL_SHA1C': ('/fast/All.sha1c', {
        # critical - random access to trees and commits: only on da4 and da5
        # - performance is best when /fast is on SSD raid
        'commit_random': 'commit_{key}.tch',
        'tree_random': 'tree_{key}.tch',
    }),
    # all three are available on da[3-5]
    'OSCAR_ALL_SHA1O': ('/fast/All.sha1o', {
        'blob_offset': 'sha1.blob_{key}.tch',
        # Speed is a bit lower since the content is read from HDD raid
    }),
    'OSCAR_BASEMAPS': ('/da0_data/basemaps', {
        # relations - good to have but not critical
        'commit_projects': 'c2pFull{ver}.{key}.tch',
        'commit_children': 'c2ccFull{ver}.{key}.tch',
        'commit_time_author': 'c2taFull{ver}.{key}.tch',
        'commit_root': 'c2rFull{ver}.{key}.tch',
        'commit_head': 'c2hFull{ver}.{key}.tch',
        'commit_parent': 'c2pcFull{ver}.{key}.tch',
        'author_commits': 'a2cFull{ver}.{key}.tch',
        'author_projects': 'a2pFull{ver}.{key}.tch',
        'author_files': 'a2fFull{ver}.{key}.tch',
        'project_authors': 'p2aFull{ver}.{key}.tch',

        'commit_blobs': 'c2bFull{ver}.{key}.tch',
        'commit_files': 'c2fFull{ver}.{key}.tch',
        'project_commits': 'p2cFull{ver}.{key}.tch',
        'blob_commits': 'b2cFull{ver}.{key}.tch',
        # this actually points to the first time/author/commit only
        'blob_author': 'b2aFull{ver}.{key}.tch',
        'file_authors': 'f2aFull{ver}.{key}.tch',
        'file_commits': 'f2cFull{ver}.{key}.tch',
        'file_blobs': 'f2bFull{ver}.{key}.tch',
        'blob_files': 'b2fFull{ver}.{key}.tch',
    }),
})

# prefixes used by World of Code to identify source project platforms
# See Project.to_url() for more details
# Prefixes have been deprecated by replacing them with the string resembling
# actual URL
URL_PREFIXES = {
    b'bitbucket.org': b'bitbucket.org',
    b'gitlab.com': b'gitlab.com',
    b'android.googlesource.com': b'android.googlesource.com',
    b'bioconductor.org': b'bioconductor.org',
    b'drupal.com': b'git.drupal.org',
    b'git.eclipse.org': b'git.eclipse.org',
    b'git.kernel.org': b'git.kernel.org',
    b'git.postgresql.org': b'git.postgresql.org',
    b'git.savannah.gnu.org': b'git.savannah.gnu.org',
    b'git.zx2c4.com': b'git.zx2c4.com',
    b'gitlab.gnome.org': b'gitlab.gnome.org',
    b'kde.org': b'anongit.kde.org',
    b'repo.or.cz': b'repo.or.cz',
    b'salsa.debian.org': b'salsa.debian.org',
    b'sourceforge.net': b'git.code.sf.net/p'
}
IGNORED_AUTHORS = (
    b'GitHub Merge Button <merge-button@github.com>'
)

class ObjectNotFound(KeyError):
    pass


cdef unber(bytes buf):
    r""" Perl BER unpacking.
    BER is a way to pack several variable-length ints into one
    binary string. Here we do the reverse.
    Format definition: from http://perldoc.perl.org/functions/pack.html
        (see "w" template description)

    Args:
        buf (bytes): a binary string with packed values

    Returns:
         str: a list of unpacked values

    >>> unber(b'\x00\x83M')
    [0, 461]
    >>> unber(b'\x83M\x96\x14')
    [461, 2836]
    >>> unber(b'\x99a\x89\x12')
    [3297, 1170]
    """
    # PY: 262ns, Cy: 78ns
    cdef:
        list res = []
        # blob_offset sizes are getting close to 32-bit integer max
        uint64_t acc = 0
        uint8_t b

    for b in buf:
        acc = (acc << 7) + (b & 0x7f)
        if not b & 0x80:
            res.append(acc)
            acc = 0
    return res


cdef (int, int) lzf_length(bytes raw_data):
    # type: (bytes) -> (int, int)
    r""" Get length of uncompressed data from a header of Compress::LZF
    output. Check Compress::LZF sources for the definition of this bit magic
        (namely, LZF.xs, decompress_sv)
        https://metacpan.org/source/MLEHMANN/Compress-LZF-3.8/LZF.xs

    Args:
        raw_data (bytes): data compressed with Perl Compress::LZF

    Returns:
         Tuple[int, int]: (header_size, uncompressed_content_length) in bytes

    >>> lzf_length(b'\xc4\x9b')
    (2, 283)
    >>> lzf_length(b'\xc3\xa4')
    (2, 228)
    >>> lzf_length(b'\xc3\x8a')
    (2, 202)
    >>> lzf_length(b'\xca\x87')
    (2, 647)
    >>> lzf_length(b'\xe1\xaf\xa9')
    (3, 7145)
    >>> lzf_length(b'\xe0\xa7\x9c')
    (3, 2524)
    """
    # PY:725us, Cy:194usec
    cdef:
        # compressed size, header length, uncompressed size
        uint32_t csize=len(raw_data), start=1, usize
        # first byte, mask, buffer iterator placeholder
        uint8_t lower=nth_byte(raw_data, 0), mask=0x80, b

    while mask and csize > start and (lower & mask):
        mask >>= 1 + (mask == 0x80)
        start += 1
    if not mask or csize < start:
        raise ValueError('LZF compressed data header is corrupted')
    usize = lower & (mask - 1)
    for b in raw_data[1:start]:
        usize = (usize << 6) + (b & 0x3f)
    if not usize:
        raise ValueError('LZF compressed data header is corrupted')
    return start, usize


def decomp(bytes raw_data):
    # type: (bytes) -> bytes
    """ lzf wrapper to handle perl tweaks in Compress::LZF
    This function extracts uncompressed size header
    and then does usual lzf decompression.

    Args:
        raw_data (bytes): data compressed with Perl Compress::LZF

    Returns:
        str: unpacked data
    """
    if not raw_data:
        return b''
    if nth_byte(raw_data, 0) == 0:
        return raw_data[1:]
    start, usize = lzf_length(raw_data)
    # while it is tempting to include liblzf and link statically, there is
    # zero advantage comparing to just using python-lzf
    return lzf.decompress(raw_data[start:], usize)


cdef uint32_t fnvhash(bytes data):
    """
    Returns the 32 bit FNV-1a hash value for the given data.
    >>> hex(fnvhash('foo'))
    '0xa9f37ed7'
    """
    # PY: 5.8usec Cy: 66.8ns
    cdef:
        uint32_t hval = 0x811c9dc5
        uint8_t b
    for b in data:
        hval ^= b
        hval *= 0x01000193
    return hval


def cached_property(func):
    """ Classic memoize with @property on top"""
    @wraps(func)
    def wrapper(self):
        key = '_' + func.__name__
        if not hasattr(self, key):
            setattr(self, key, func(self))
        return getattr(self, key)
    return property(wrapper)


def slice20(bytes raw_data):
    """ Slice raw_data into 20-byte chunks and hex encode each of them
    It returns tuple in order to be cacheable
    """
    if raw_data is None:
        return ()
    return tuple(raw_data[i:i + 20] for i in range(0, len(raw_data), 20))


class CommitTimezone(tzinfo):
    # TODO: replace with datetime.timezone once Py2 support is ended
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


def parse_commit_date(bytes timestamp, bytes tz):
    """ Parse date string of authored_at/commited_at

    git log time is in the original timezone
        gitpython - same as git log (also, it has the correct timezone)
    unix timestamps (used internally by commit objects) are in UTC
        datetime.fromtimestamp without a timezone will convert it to host tz
    github api is in UTC (this is what trailing 'Z' means)

    Args:
        timestamp (str): Commit.authored_at or Commit.commited_at,
            e.g. '1337145807 +1100'
        tz (str): timezone
    Returns:
        Optional[datetime.datetime]: UTC datetime

    >>> parse_commit_date(b'1337145807', b'+1130')
    datetime.datetime(2012, 5, 16, 16, 23, 27, tzinfo=<Timezone: 11:30>)
    >>> parse_commit_date(b'3337145807', b'+1100') is None
    True
    """
    cdef:
        int sign = -1 if tz.startswith(b'-') else 1
        uint32_t ts
        int hours, minutes
        uint8_t tz_len = len(tz)
    try:
        ts = int(timestamp)
        hours = sign * int(tz[tz_len-4:tz_len-2])
        minutes = sign * int(tz[tz_len-2:])
        dt = datetime.fromtimestamp(ts, CommitTimezone(hours, minutes))
    except (ValueError, OverflowError):
        # i.e. if timestamp or timezone is invalid
        return None

    # timestamp is in the future
    if ts > time.time():
        return None

    return dt

cdef extern from 'Python.h':
    object PyBytes_FromStringAndSize(char *s, Py_ssize_t len)


cdef extern from 'tchdb.h':
    ctypedef struct TCHDB:  # type of structure for a hash database
        pass

    cdef enum:  # enumeration for open modes
        HDBOREADER = 1 << 0,  # open as a reader
        HDBONOLCK = 1 << 4,  # open without locking

    const char *tchdberrmsg(int ecode)
    TCHDB *tchdbnew()
    int tchdbecode(TCHDB *hdb)
    bint tchdbopen(TCHDB *hdb, const char *path, int omode)
    bint tchdbclose(TCHDB *hdb)
    void *tchdbget(TCHDB *hdb, const void *kbuf, int ksiz, int *sp)
    bint tchdbiterinit(TCHDB *hdb)
    void *tchdbiternext(TCHDB *hdb, int *sp)


cdef class Hash:
    """Object representing a Tokyocabinet Hash table"""
    cdef TCHDB* _db
    cdef bytes filename

    def __cinit__(self, char *path, nolock=True):
        cdef int mode = HDBOREADER
        if nolock:
            mode |= HDBONOLCK
        self._db = tchdbnew()
        self.filename = path
        if self._db is NULL:
            raise MemoryError()
        cdef bint result = tchdbopen(self._db, path, mode)
        if not result:
            raise IOError('Failed to open .tch file "%s": ' % self.filename
                          + self._error())

    def _error(self):
        cdef int code = tchdbecode(self._db)
        cdef bytes msg = tchdberrmsg(code)
        return msg.decode('ascii')

    def __iter__(self):
        cdef:
            bint result = tchdbiterinit(self._db)
            char *buf
            int sp
            bytes key
        if not result:
            raise IOError('Failed to iterate .tch file "%s": ' % self.filename
                          + self._error())
        while True:
            buf = <char *>tchdbiternext(self._db, &sp)
            if buf is NULL:
                break
            key = PyBytes_FromStringAndSize(buf, sp)
            free(buf)
            yield key

    cdef bytes read(self, bytes key):
        cdef:
            char *k = key
            char *buf
            int sp
            int ksize=len(key)
        buf = <char *>tchdbget(self._db, k, ksize, &sp)
        if buf is NULL:
            raise ObjectNotFound()
        cdef bytes value = PyBytes_FromStringAndSize(buf, sp)
        free(buf)
        return value

    def __getitem__(self, bytes key):
        return self.read(key)

    def __del__(self):
        cdef bint result = tchdbclose(self._db)
        if not result:
            raise IOError('Failed to close .tch "%s": ' % self.filename
                          + self._error())

    def __dealloc__(self):
        free(self._db)


# Pool of open TokyoCabinet databases to save few milliseconds on opening
cdef dict _TCH_POOL = {}  # type: Dict[str, Hash]
TCH_LOCK = Lock()

def _get_tch(char *path):
    """ Cache Hash() objects """
    if path in _TCH_POOL:
        return _TCH_POOL[path]
    try:
        TCH_LOCK.acquire()
        # in multithreading environment this can cause race condition,
        # so we need a lock
        if path not in _TCH_POOL:
            _TCH_POOL[path] = Hash(path)
    finally:
        TCH_LOCK.release()
    return _TCH_POOL[path]


class _Base(object):
    type = 'oscar_base'  # type: str
    key = None  # type: bytes
    # fnv keys are used for non-git objects, such as files, projects and authors
    use_fnv_keys = True  # type: bool
    _keys_registry_dtype = None  # type: str

    def __init__(self, key):
        self.key = key

    def __repr__(self):
        return '<%s: %s>' % (self.type.capitalize(), self)

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return isinstance(other, type(self)) \
            and self.type == other.type \
            and self.key == other.key

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return (binascii.hexlify(self.key).decode('ascii')
                if isinstance(self.key, bytes_type) else self.key)

    def resolve_path(self, dtype):
        """ Get path to a file using data type and object key (for sharding)
        """
        path, prefix_length = PATHS[dtype]

        cdef uint8_t p
        if self.use_fnv_keys:
            p = fnvhash(self.key)
        else:
            p = nth_byte(self.key, 0)
        cdef uint8_t prefix = p & (2**prefix_length - 1)
        return path.format(key=prefix)

    def read_tch(self, dtype):
        """ Resolve the path and read .tch"""
        path = self.resolve_path(dtype).encode('ascii')
        try:
            return _get_tch(path)[self.key]
        except KeyError:
            return None

    @classmethod
    def all_keys(cls):
        """ Iterate keys of all objects of the given type
        This might be useful to get a list of all projects, or a list of
        all file names.

        Yields:
            bytes: objects key
        """
        if not cls._keys_registry_dtype:
            raise NotImplemented

        base_path, prefix_length = PATHS[cls._keys_registry_dtype]
        for file_prefix in range(2 ** prefix_length):
            for key in _get_tch(base_path.format(key=file_prefix)):
                yield key

    @classmethod
    def all(cls):
        for key in cls.all_keys():
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
                offset, comp_length, sha = chunks[1:4]
                if len(chunks) > 4:  # cls.type == "blob":
                    # usually, it's true for blobs;
                    # however, some blobs follow common pattern
                    sha = chunks[5]

                obj = cls(sha)
                obj.data = decomp(datafile.read(int(comp_length)))

                yield obj
            datafile.close()

    def __init__(self, sha):
        if isinstance(sha, str_type) and len(sha) == 40:
            self.sha = sha
            self.bin_sha = binascii.unhexlify(sha)
        elif isinstance(sha, bytes_type) and len(sha) == 20:
            self.bin_sha = sha
            self.sha = binascii.hexlify(sha).decode('ascii')
        else:
            raise ValueError('Invalid SHA1 hash: %s' % sha)
        super(GitObject, self).__init__(self.bin_sha)

    @cached_property
    def data(self):
        # type: () -> bytes
        if self.type not in ('commit', 'tree'):
            raise NotImplementedError
        # default implementation will only work for commits and trees
        return decomp(self.read_tch(self.type + '_random'))

    @classmethod
    def string_sha(cls, data):
        # type: (bytes) -> str
        """Manually compute blob sha from its content passed as `data`.
        The main use case for this method is to identify source of a file.

        Blob SHA is computed from a string:
        "blob <file content length as str><null byte><file content>"

        # https://gist.github.com/masak/2415865
        Commit SHAs are computed in a similar way
        "commit <commit length as str><null byte><commit content>"

        note that commit content includes committed/authored date

        Args:
            data (bytes): content of the GitObject to get hash for

        Returns:
            str: 40-byte hex SHA1 hash
        """
        sha1 = hashlib.sha1()
        sha1.update(b'%s %d\x00' % (cls.type.encode('ascii'), len(data)))
        sha1.update(data)
        return sha1.hexdigest()

    @classmethod
    def file_sha(cls, path):
        buffsize = 1024 ** 2
        size = os.stat(path).st_size
        with open(path, 'rb') as fh:
            sha1 = hashlib.sha1()
            sha1.update(b'%s %d\x00' % (cls.type.encode('ascii'), size))
            while True:
                data = fh.read(min(size, buffsize))
                if not data:
                    return sha1.hexdigest()
                sha1.update(data)


class Blob(GitObject):
    type = 'blob'

    def __len__(self):
        _, length = self.position
        return length

    @cached_property
    def position(self):
        # type: () -> (int, int)
        """ Get offset and length of the blob data in the storage """
        value = self.read_tch('blob_offset')
        if value is None:  # empty read -> value not found
            raise ObjectNotFound('Blob data not found (bad sha?)')
        return unber(value)

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
        # unfortunately, Py2 cython doesn't know how to instantiate bytes from
        # memoryviews. TODO: reuse libgit2 git_tree__parse_raw
        data = self.data

        i = 0
        while i < len(data):
            # mode
            start = i
            while i < len(data) and nth_byte(data, i) != 32:  # 32 is space
                i += 1
            mode = data[start:i]
            i += 1
            # file name
            start = i
            while i < len(data) and <char> nth_byte(data, i) != 0:
                i += 1
            fname = data[start:i]
            # sha
            start = i + 1
            i += 21
            yield mode, fname, data[start:i]

    def __len__(self):
        return len(self.files)

    def __contains__(self, item):
        if isinstance(item, File):
            return item.key in self.files
        elif isinstance(item, Blob):
            return item.bin_sha in self.blob_shas
        elif isinstance(item, str_type) and len(item) == 40:
            item = binascii.unhexlify(item)
        elif not isinstance(item, bytes_type):
            return False

        return item in self.blob_shas or item in self.files

    def traverse(self):
        """ Recursively traverse the tree
        This will generate 3-tuples of the same format as direct tree
        iteration, but will recursively include subtrees content.

        Yields:
            Tuple[bytes, bytes, bytes]: (mode, filename, blob/tree sha)

        >>> c = Commit(u'1e971a073f40d74a1e72e07c682e1cba0bae159b')
        >>> len(list(c.tree.traverse()))
        8
        >>> c = Commit(u'e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> len(list(c.tree.traverse()))
        36
        """
        for mode, fname, sha in self:
            yield mode, fname, sha
            # trees are always 40000:
            # https://stackoverflow.com/questions/1071241
            if mode == b'40000':
                for mode2, fname2, sha2 in Tree(sha).traverse():
                    yield mode2, fname + b'/' + fname2, sha2

    @cached_property
    def str(self):
        """
        >>> print(Tree('954829887af5d9071aa92c427133ca2cdd0813cc'))
        100644 __init__.py ff1f7925b77129b31938e76b5661f0a2c4500556
        100644 admin.py d05d461b48a8a5b5a9d1ea62b3815e089f3eb79b
        100644 models.py d1d952ee766d616eae5bfbd040c684007a424364
        40000 templates 7ff5e4c9bd3ce6ab500b754831d231022b58f689
        40000 templatetags e5e994b0be2c9ce6af6f753275e7d8c29ccf75ce
        100644 urls.py e9cb0c23a7f6683911305efff91dcabadb938794
        100644 utils.py 2cfbd298f18a75d1f0f51c2f6a1f2fcdf41a9559
        100644 views.py 973a78a1fe9e69d4d3b25c92b3889f7e91142439
        """
        return b'\n'.join(b' '.join((mode, fname, binascii.hexlify(sha)))
                          for mode, fname, sha in self).decode('ascii')

    @cached_property
    def files(self):
        """ A dict of all files and their content/blob sha under this tree.
        It includes recursive files (i.e. files in subdirectories).
        It does NOT include subdirectories themselves.
        """
        return {fname: sha for mode, fname, sha in self if mode != b'40000'}

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
    encoding = 'utf8'

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
        >>> c.author.startswith(b'Marat')
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
        # using libgit2 commit_parse would be a bit faster, but would require
        # to face internal git structures with manual memory management.
        # The probability of introducing bugs and memory leaks isn't worth it

        attrs = ('tree', 'parent_shas', 'message', 'full_message', 'author',
                 'committer', 'authored_at', 'committed_at', 'signature')
        if attr not in attrs:
            raise AttributeError(
                '\'%s\'has no attribute \'%s\'' % (self.__class__.__name__, attr))

        for a in attrs:
            setattr(self, a, None)
        self._parse()
        return getattr(self, attr)

    # def _parse2(self):
    #     # TODO: port to Cython
    #     # Py: 22.6usec, Cy:
    #     cdef:
    #         const unsigned char[:] data = self.data
    #         uint32_t data_len = len(self.data)
    #         uint32_t start, end, sol, eol = 101
    #         list parent_shas = []
    #         bytes timestamp, timezone
    #     # fields come in this exact order:
    #     # tree, parent, author, committer, [gpgsig], [encoding]
    #     if data[0:5] != b'tree ': raise ValueError('Malformed commit')
    #     self.tree = Tree(binascii.unhexlify(data[5:5+40]))
    #
    #     if data[45:45+8] != b'\nparent ': raise ValueError('Malformed commit')
    #     parent_shas.append(binascii.unhexlify(data[53:53+40]))
    #
    #     if data[93:93+8] != b'\nauthor ': raise ValueError('Malformed commit')
    #     # eol is initialized at 101 already
    #     while data[eol] != b'\n': eol += 1
    #     end = eol - 1
    #     start = end
    #     while data[start] != b' ': start -= 1
    #     timezone = data[start+1:end]
    #     end = start-1
    #     start = end
    #     while data[start] != b' ': start -= 1
    #     timestamp = data[start+1:end]
    #     self.authored_at = parse_commit_date(timestamp, timezone)
    #     self.author = bytes(data[101:start-1])
    #
    #     sol = eol
    #     eol += 1
    #     if data[sol:sol+11] != b'\ncommitter ': raise ValueError('Malformed commit')
    #     while data[eol] != b'\n': eol += 1
    #     end = eol - 1
    #     start = end
    #     while data[start] != b' ': start -= 1
    #     timezone = data[start+1:end]
    #     end = start-1
    #     start = end
    #     while data[start] != b' ': start -= 1
    #     timestamp = data[start+1:end]
    #     self.committed_at = parse_commit_date(timestamp, timezone)
    #     self.committer = bytes(data[101:start-1])
    #
    #
    #     for field, field_len in ((b'tree', 5), (b'parent', 7)):
    #     for field, field_len in ((b'author', 7), (b'committer', 10)):
    #
    #
    #     self.header = bytes(data[0:i])
    #     start = i
    #     self.header, self.full_message = self.data.split(b'\n\n', 1)
    #     self.message = self.full_message.split(b'\n', 1)[0]
    #     cdef list parent_shas = []
    #     cdef bytes signature = None
    #     cdef bint reading_signature = False
    #     for line in self.header.split(b'\n'):
    #         if reading_signature:
    #             # examples:
    #             #   1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab
    #             #   cbbc685c45bdff4da5ea0984f1dd3a73486b4556
    #             signature += line
    #             if line.strip() == b'-----END PGP SIGNATURE-----':
    #                 self.signature = signature
    #                 reading_signature = False
    #             continue
    #
    #         if line.startswith(b' '):  # mergetag object, not supported (yet?)
    #             # example: c1313c68c7f784efaf700fbfb771065840fc260a
    #             continue
    #
    #         line = line.strip()
    #         if not line:  # sometimes there is an empty line after gpgsig
    #             continue
    #         try:
    #             key, value = line.split(b' ', 1)
    #         except ValueError:
    #             raise ValueError('Unexpected header in commit ' + self.sha)
    #         # fields come in this exact order:
    #         # tree, parent, author, committer, [gpgsig], [encoding]
    #         if key == b'tree':
    #             # value is bytes holding hex values -> need to decode
    #             self.tree = Tree(binascii.unhexlify(value))
    #         elif key == b'parent':  # multiple parents possible
    #             parent_shas.append(binascii.unhexlify(value))
    #         elif key == b'author':
    #             # author name can have arbitrary number of spaces while
    #             # timestamp is guaranteed to have one, so rsplit
    #             self.author, timestamp, timezone = value.rsplit(b' ', 2)
    #             self.authored_at = parse_commit_date(timestamp, timezone)
    #         elif key == b'committer':
    #             # same logic as author
    #             self.committer, timestamp, timezone = value.rsplit(b' ', 2)
    #             self.committed_at = parse_commit_date(timestamp, timezone)
    #         elif key == b'gpgsig':
    #             signature = value
    #             reading_signature = True
    #         elif key == b'encoding':
    #             self.encoding = value.decode('ascii')
    #     self.parent_shas = tuple(parent_shas)

    def _parse(self):
        self.header, self.full_message = self.data.split(b'\n\n', 1)
        self.message = self.full_message.split(b'\n', 1)[0]
        cdef list parent_shas = []
        cdef bytes signature = None
        cdef bint reading_signature = False
        for line in self.header.split(b'\n'):
            if reading_signature:
                # examples:
                #   1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab
                #   cbbc685c45bdff4da5ea0984f1dd3a73486b4556
                signature += line
                if line.strip() == b'-----END PGP SIGNATURE-----':
                    self.signature = signature
                    reading_signature = False
                continue

            if line.startswith(b' '):  # mergetag object, not supported (yet?)
                # example: c1313c68c7f784efaf700fbfb771065840fc260a
                continue

            line = line.strip()
            if not line:  # sometimes there is an empty line after gpgsig
                continue
            try:
                key, value = line.split(b' ', 1)
            except ValueError:
                raise ValueError('Unexpected header in commit ' + self.sha)
            # fields come in this exact order:
            # tree, parent, author, committer, [gpgsig], [encoding]
            if key == b'tree':
                # value is bytes holding hex values -> need to decode
                self.tree = Tree(binascii.unhexlify(value))
            elif key == b'parent':  # multiple parents possible
                parent_shas.append(binascii.unhexlify(value))
            elif key == b'author':
                # author name can have arbitrary number of spaces while
                # timestamp is guaranteed to have one, so rsplit
                self.author, timestamp, timezone = value.rsplit(b' ', 2)
                self.authored_at = parse_commit_date(timestamp, timezone)
            elif key == b'committer':
                # same logic as author
                self.committer, timestamp, timezone = value.rsplit(b' ', 2)
                self.committed_at = parse_commit_date(timestamp, timezone)
            elif key == b'gpgsig':
                signature = value
                reading_signature = True
            elif key == b'encoding':
                self.encoding = value.decode('ascii')
        self.parent_shas = tuple(parent_shas)

    def __sub__(self, parent, threshold=0.5):
        """ Compare two Commits.

        Args:
            parent (Commit): another commit to compare to.
                Expected order is `diff = child_commit - parent_commit`

        Yields:
            Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
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
                yield fname, fname, old_files[fname], new_files[fname]

        added_paths = new_paths - old_paths
        deleted_paths = old_paths - new_paths

        if threshold >= 1:  # i.e. only exact matches are considered
            for fname in added_paths:
                yield None, fname, None, new_files[fname]
            for fname in deleted_paths:
                yield fname, None, old_files[fname], None
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
                    yield deleted_fname, added_fname, deleted_blob, added_blob
                    del(deleted_blobs[deleted_fname])
                    matched = True
                    break
            if not matched:  # this is a new file
                yield None, added_fname, None, added_blob

        for deleted_fname, deleted_blob in deleted_blobs.items():
            yield deleted_fname, None, deleted_blob, None

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
        return tuple(project_name for project_name in data.split(b';')
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
        return tuple((data and data.split(b';')) or [])

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
        # still true as of Sep 2020
        warnings.warn(
            'This relation is known to miss every first file in all trees. '
            'Consider using Commit.tree.blobs as a slower but more accurate '
            'alternative', DeprecationWarning)
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
                     for file_name in (data and data.split(";")) or []
                     if file_name and file_name != 'EMPTY')


class Tag(GitObject):
    """ Tag doesn't have any functionality associated.
    You can't really do anything useful with it yet
    """
    type = 'tag'


class Project(_Base):
    """
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
        if isinstance(uri, str_type):
            uri = uri.encode('ascii')
        self.uri = uri
        super(Project, self).__init__(uri)

    def __iter__(self):
        """ Generator of all commits in the project.
        Order of commits is not guaranteed

        >>> commits = tuple(Project(b'user2589_minicms'))
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
            if author not in IGNORED_AUTHORS:
                yield c

    def __contains__(self, item):
        if isinstance(item, Commit):
            key = item.key
        elif isinstance(item, bytes_type) and len(item) == 20:
            key = item
        elif isinstance(item, str_type) and len(item) == 40:
            key = binascii.unhexlify(item)
        else:
            return False
        return key in self.commit_shas

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits in the project

        >>> Project(b'user2589_django-currencies').commit_shas
        ...         # doctest: +NORMALIZE_WHITESPACE
        ('2dbcd43f077f2b5511cc107d63a0b9539a6aa2a7',
         '7572fc070c44f85e2a540f9a5a05a95d1dd2662d')
        """
        return slice20(self.read_tch('project_commits'))

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
                      key=lambda c: c.authored_at or DAY_Z)[len(commits)-1]

    @cached_property
    def tail(self):
        """ Get the first commit SHA by following first parents

        >>> Project(b'user2589_minicms').tail
        '1e971a073f40d74a1e72e07c682e1cba0bae159b'
        """
        commits = {c.bin_sha: c for c in self.commits}
        pts = set(c.parent_shas[0] for c in commits.values() if c.parent_shas)
        for bin_sha, c in commits.items():
            if bin_sha in pts and not c.parent_shas:
                return bin_sha

    @property
    def commits_fp(self):
        """ Get a commit chain by following only the first parent, to mimic
        https://git-scm.com/docs/git-log#git-log---first-parent .
        Thus, you only get a small subset of the full commit tree:

        >>> p = Project(b'user2589_minicms')
        >>> set(c.sha for c in p.commits_fp).issubset(p.commit_shas)
        True

        In scenarios where branches are not important, it can save a lot
        of computing.

        Yields:
            Commit: binary commit shas, following first parent only,
                from the latest to the earliest.
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
        result = []
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

    @cached_property
    def url(self):
        """ Get the URL for a given project URI
        >>> Project('CS340-19_lectures').url
        'http://github.com/CS340-19/lectures'
        """
        prefix, body = self.uri.split(b'_', 1)
        if prefix == b'sourceforge.net':
            platform = URL_PREFIXES[prefix]
        elif prefix in URL_PREFIXES and b'_' in body:
            platform = URL_PREFIXES[prefix]
            body = body.replace(b'_', b'/', 1)
        else:
            platform = b'github.com'
            body = self.uri.replace(b'_', b'/', 1)
        return b'/'.join((b'https:/', platform, body))

    @cached_property
    def author_names(self):
        data = decomp(self.read_tch('project_authors'))
        return tuple(author_name
                     for author_name in (data and data.split(b';')) or []
                     if author_name and author_name != 'EMPTY')


class File(_Base):
    """
    Files are initialized with a path, starting from a commit root tree:

        >>> File(b'.gitignore')  # doctest: +SKIP
        >>> File(b'docs/Index.rst')  # doctest: +SKIP
    """
    type = 'file'
    _keys_registry_dtype = 'file_commits'

    def __init__(self, path):
        if isinstance(path, str_type):
            path = path.encode('utf8')
        self.path = path
        super(File, self).__init__(path)

    @cached_property
    def author_names(self):
        data = decomp(self.read_tch('file_authors'))
        return tuple(author for author in (data and data.split(b';'))
                     if author not in IGNORED_AUTHORS)

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
        return slice20(self.read_tch('file_commits'))

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
            if author not in IGNORED_AUTHORS:
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
        if isinstance(full_email, str_type):
            full_email = full_email.encode('utf8')
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
        return slice20(self.read_tch('author_commits'))

    @property
    def commits(self):
        """ A generator of all Commit objects authored by the Author

        >>> commits = tuple(
        ...     Author('user2589 <user2589@users.noreply.github.com>').commits)
        >>> len(commits) > 40
        True
        >>> isinstance(commits[0], Commit)
        True
        """
        return (Commit(sha) for sha in self.commit_shas)

    @cached_property
    def file_names(self):
        data = decomp(self.read_tch('author_files'))
        return tuple(fname for fname in (data and data.split(b';')))

    @cached_property
    def project_names(self):
        """ URIs of projects where author has committed to
        A generator of all Commit objects authored by the Author
        """
        data = decomp(self.read_tch('author_projects'))
        return tuple(project_name
                     for project_name in (data and data.split(b';'))
                     if project_name and project_name != b'EMPTY')

    # This relation went MIA as of Sep 6 2020
    # @cached_property
    # def torvald(self):
    #     data = decomp(self.read_tch('author_trpath'))
    #     return tuple(path for path in (data and data.split(";")))

# temporary data for local test
# TODO: remove once commit parse
#
# c = Commit("1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab")
# c._data = b'tree 0a2def6627be9bf2f3c7c2a84eb1e2feb0e7c03e\n' \
#           b'parent d55f5fb86e5892dd1673a9c6cf5e3fdff8c5d93b\n' \
#           b'author AlecGoldstein123 <34690976+AlecGoldstein123@users.noreply.github.com> 1513882101 -0500\n' \
#           b'committer GitHub <noreply@github.com> 1513882101 -0500\n' \
#           b'gpgsig -----BEGIN PGP SIGNATURE-----\n' \
#           b' \n' \
#           b' wsBcBAABCAAQBQJaPAH1CRBK7hj4Ov3rIwAAdHIIACYBs+bTOv7clJSYr9NT0gbX\n' \
#           b' zb4XeJJADvDISZUJChwebEENDue5+GX+dX03ILptRizVVnASwNZR30DENeJNcOpw\n' \
#           b' WqXKho+AV0H0C91x8CIbICnDjdgGdcyKFBCWQ8lBV6BjiRwGXFKJU6dyt480lzs8\n' \
#           b' Eu2PqpTg59Xr/msd4vTrQofSoRwu8kW8KXBWou6G1f9KVCoOXWvhRmiLngFupyPV\n' \
#           b' 0jbNLOe6IQ37xrvvSULCiBmemeYfAJSUywMPIPFyUpzZc2+jKDOcxJeKrRxzmQM0\n' \
#           b' XKeHQIqKSQOVPB/SB7i2Pnxf/UBObaa4kiFoDGHp5IjolgMC+4pFuF2mOE5pbcQ=\n' \
#           b' =cWKt\n' \
#           b' -----END PGP SIGNATURE-----\n' \
#           b' \n\n' \
#           b'Add files via upload'
