
import lzf
from tokyocabinet import hash as tch

from functools import wraps
import warnings

INVALID = "compressed data corrupted (invalid length)"


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
        raise ValueError(INVALID)
    lower = ord(raw_data[0])
    csize = len(raw_data)
    start = 1
    mask = 0x80
    while mask and csize > start and (lower & mask):
        mask >>= 1 + (mask == 0x80)
        start += 1
    if not mask or csize < start:
        raise ValueError(INVALID)
    usize = lower & (mask - 1)
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


# Pool of open TokyoCabinet databases to save few milliseconds on opening
_TCH_POOL = {}


def _get_tch(path):
    if not path.endswith('.tch'):
        path += '.tch'
    if path not in _TCH_POOL:
        _TCH_POOL[path] = tch.Hash()
        _TCH_POOL[path].open(path, tch.HDBOREADER)
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

    def __eq__(self, other):
        return isinstance(other, type(self)) \
               and self.type == other.type \
               and self.key == other.key

    def __str__(self):
        return self.key

    @classmethod
    def all(cls):
        raise NotImplementedError


class GitObject(_Base):

    @classmethod
    def all(cls, ignored_prefix=''):
        """ Iterate ALL objects of this type (all projects, all times) """
        for key in range(128):
            path = '/data/All.blobs/%s_%d' % (cls.type, key)
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
        return self.read('/fast{blob}/All.sha1/sha1.{type}_{key}.tch')

    @cached_property
    def data(self):
        if self.type not in ('commit', 'tree'):
            raise NotImplementedError
        # default implementation will only work for commits and trees
        return decomp(self.read('/fast1/All.sha1c/{type}_{key}.tch'))

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
        try:
            offset, length = unber(
                self.read('/data/All.sha1o/sha1.blob_{key}.tch'))
        except ValueError:  # empty read -> value not found
            raise KeyError('Blob data not found (bad sha?)')
        # no caching here because it will make the code non-thread-safe
        fh = open(self.resolve_path('/data/All.blobs/{type}_{key}.bin'), 'rb')
        fh.seek(offset)
        return decomp(fh.read(length))

    @cached_property
    def commit_shas(self):
        """ SHAs of Commits in which this blob have been
        introduced/modified/removed
        """
        return slice20(self.read('/data/basemaps/b2cFullF.{key}.tch', 4))

    @property
    def commits(self):
        """ Commits where this blob has been added/removed/changed """
        return (Commit(bin_sha) for bin_sha in self.commit_shas)


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

    def __len__(self):
        return len(self.files)

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
    def parent_tree_shas(self):
        return slice20(self.read('/data/basemaps/t2pt0-127.{key}.tch', 3))

    @property
    def parent_trees(self):
        """ Get parent trees
        :return: generator of Tree objects

        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> trees = {fname: sha
        ...          for mode, fname, sha in c.tree.traverse() if mode=="40000"}
        >>> all(trees[fname.rsplit("/", 1)[0]] in
        ...         {p.sha for p in Tree(sha).parent_trees}
        ...     for fname, sha in trees.items() if "/" in fname)
        True
        """
        return (Tree(sha) for sha in self.parent_tree_shas)

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

    @property
    def blobs(self):
        """ Get a tuple of all blobs from the tree and its subtrees
        :return: tuple of Blobs

        >>> len(tuple(Tree('d20520ef8c1537a42628b72d481b8174c0a1de84').blobs))
        7
        """
        return (Blob(sha) for sha in self.files.values())


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
        return (cls(sha) for sha in
                slice20(read_tch('/data/basemaps/Auth2Cmt.tch', author)))

    @classmethod
    def by_file(cls, file_path):
        """ Get all commits *modifying* the given file
        :param file_path: a full path, e.g.: 'public_html/images/cms/my.gif'
        :return: generator of commits
        """
        if not file_path.endswith("\n"):
            file_path += "\n"
        tch_path = '/data/basemaps/f2cFullF.%d.tch' % prefix(file_path, 3)
        data = read_tch(tch_path, file_path)
        return (cls(sha) for sha in slice20(data))

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
        tch_path = '/data/basemaps/Prj2CmtG.%d.tch' % prefix(project, 3)
        data = read_tch(tch_path, project)
        return (cls(bin_sha) for bin_sha in slice20(data))

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
        """ A generator of parent commits
        If you only need hashes (and not Commit objects),
        use .parent_sha instead
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> tuple(c.parents)
        (<Commit: ab124ab4baa42cd9f554b7bb038e19d4e3647957>,)
        """
        return (Commit(sha) for sha in self.parent_shas)

    @cached_property
    def project_names(self):
        # type: () -> tuple
        """Projects including this commit
        >>> c = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
        >>> isinstance(c.project_names, tuple)
        True
        >>> len(c.project_names) > 0
        True
        >>> 'user2589_minicms' in c.project_names
        True
        """
        data = decomp(self.read('/data/basemaps/Cmt2PrjG.{key}.tch', 3))
        return tuple((data and data.split(";")) or [])

    @property
    def projects(self):
        return (Project(uri) for uri in self.project_names)

    @cached_property
    def child_shas(self):
        """ Children commit binary sha hashes
        :return: a tuple of children commit sha (20-byte binary string)

        >>> c = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
        >>> cs = c.child_shas
        >>> len(cs) > 0  # actually, 1
        True
        >>> isinstance(c.child_shas, tuple)
        True
        >>> '9bd02434b834979bb69d0b752a403228f2e385e8' in cs
        True
        """
        # key_length will be ignored
        return slice20(self.read('/data/basemaps/Cmt2Chld.tch', 1))

    @property
    def children(self):
        """ Commit children
        :return: a generator of children Commit objects
        >>> c = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
        >>> isinstance(tuple(c.children)[0], Commit)
        True
        >>> c = Commit("a443e1e76c39c7b1ad6f38967a75df667b9fed57")
        >>> len(tuple(c.children)) > 1
        True
        >>> c = Commit("4199110871d5dcb3a79dfc19a16eb630c9218962")
        >>> len(tuple(c.children)) > 3
        True
        >>> cs = Commit.by_project('user2589_minicms')
        >>> all(all(c.sha in {ch.sha for ch in p.children} for p in c.parents)
        ...     for c in cs)
        True
        """
        return (Commit(bin_sha) for bin_sha in self.child_shas)

    @cached_property
    def blob_shas(self):
        return slice20(self.read('/data/basemaps/c2bFullF.{key}.tch', 4))

    @property
    def blobs(self):
        """ Commit blobs retrieved from cached relation
        much faster
        :return: tuple of children Blob objects

        >>> c = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
        >>> len(tuple(c.blobs)) == len(tuple(c.tree.blobs))
        True
        >>> c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        >>> len(tuple(c.blobs)) == len(tuple(c.tree.blobs))
        True
        """
        warnings.warn(
            "This relation is known to miss every first file in all trees. "
            "Consider using Commit.tree.blobs as a slower but more accurate "
            "alternative", DeprecationWarning)
        return (Blob(bin_sha) for bin_sha in self.blob_shas)


class Tag(GitObject):
    type = 'tag'


class Project(_Base):
    type = 'project'

    @classmethod
    def all(cls, name_prefix=''):
        """ Get all project URIs, starting with an optional prefix
        This method is heavy so it is moved to integration tests
        """
        for key_prefix in range(8):
            tch_path = '/data/basemaps/Prj2CmtG.%d.tch' % key_prefix
            for uri in tch_keys(tch_path, name_prefix):
                yield cls(uri)

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits in the project
        >>> commits = Project('user2589_minicms').commit_shas
        >>> len(commits) > 60
        True
        >>> isinstance(commits, tuple)
        True
        >>> isinstance(commits[0], str)
        True
        >>> len(commits[0] == 40)
        True
        """
        tch_path = '/data/basemaps/Prj2CmtG.%d.tch' % prefix(self.key, 3)
        return slice20(read_tch(tch_path, self.key))

    @property
    def commits(self):
        for sha in self.commit_shas:
            c = Commit(sha)
            if c.author != 'GitHub Merge Button <merge-button@github.com>':
                yield c

    @cached_property
    def head(self):
        commits = {c.sha: c for c in self.commits}
        parents = set().union(*(c.parent_shas for c in commits.values()))
        heads = set(commits.keys()) - parents
        assert len(heads) == 1, "Unexpected number of heads"
        return tuple(heads)[0]

    @property
    def commits_fp(self):
        """ Get a subset of commits following only first parent, to mimic
        https://git-scm.com/docs/git-log#git-log---first-parent
        """
        commit = self.head
        while True:
            yield commit
            if not commit.parent_shas:
                return
            commit = Commit(commit.parent_shas[0])


class File(_Base):
    type = 'file'

    @classmethod
    def all(cls, fname_prefix=''):
        """ Get all file names, starting with an optional prefix
        This method is heavy so it is moved to integration tests
        """
        for key_prefix in range(8):
            tch_path = '/data/basemaps/f2cFullF.%d.tch' % key_prefix
            for fname in tch_keys(tch_path, fname_prefix):
                yield cls(fname)

    @cached_property
    def commit_shas(self):
        """ SHA1 of all commits authored by the Author
        >>> commits = File('minicms/templatetags/minicms_tags.py').commit_shas
        >>> len(commits) > 0
        True
        >>> isinstance(commits, tuple)
        True
        >>> isinstance(commits[0], str)
        True
        >>> len(commits[0] == 40)
        True
        """
        file_path = self.key
        if not file_path.endswith("\n"):
            file_path += "\n"
        tch_path = '/data/basemaps/f2cFullF.%d.tch' % prefix(file_path, 3)
        return slice20(read_tch(tch_path, file_path))

    @property
    def commits(self):
        """ A commits authored by the Author
        >>> commits = tuple(Author('user2589 <valiev.m@gmail.com>').commits)
        >>> len(commits) > 50
        True
        >>> isinstance(commits[0], Commit)
        True
        """
        return (Commit(sha) for sha in self.commit_shas)


class Author(_Base):
    type = 'author'

    @classmethod
    def all(cls, name_prefix=''):
        """ Get all author names, starting with an optional prefix
        This method is heavy so it is moved to integration tests
        """
        for name in tch_keys('/data/basemaps/Auth2Cmt.tch', name_prefix):
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
        >>> len(commits[0] == 40)
        True
        """
        return slice20(read_tch('/data/basemaps/Auth2Cmt.tch', self.key))

    @property
    def commits(self):
        """ A commits authored by the Author
        >>> commits = tuple(Author('user2589 <valiev.m@gmail.com>').commits)
        >>> len(commits) > 50
        True
        >>> isinstance(commits[0], Commit)
        True
        """
        return (Commit(sha) for sha in self.commit_shas)

    @cached_property
    def file_names(self):
        """ All filenames changed by the Author
        >>> fnames = Author('user2589 <valiev.m@gmail.com>').file_names
        >>> len(fnames) > 50
        True
        >>> isinstance(fnames, tuple)
        True
        >>> isinstance(fnames[0], str)
        True
        """
        data = decomp(read_tch('/data/basemaps/Auth2File.tch', self.key))
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
