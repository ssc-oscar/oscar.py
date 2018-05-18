# Python interface for OSCAR data


This is a convenience library to access OSCAR dataset files.

### Installation

    easy_install --user --upgrade oscar

# Git objects

This package provides interfaces to git objects: Commit, Tree, Blog and Tag.

All git objects have `sha` property, which represents SHA1 object hash as a hex string,
and `bin_sha`, its binary counterpart.
All objects can be instantiated using their hashes, either a 40-char hex string or 20-bytes binary.

Example.:

    >>> c = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
    >>> c.sha
    '1e971a073f40d74a1e72e07c682e1cba0bae159b'
    >>> c.bin_sha
    '\x1e\x97\x1a\x07?@\xd7J\x1er\xe0|h.\x1c\xba\x0b\xae\x15\x9b'

Another shared property is `data`, a binary representation of a git object.
It is not expected to be used directly, but who knows what your research will take.


# Commit

Represents Git commit. It has following properties:

- _tree_ - a `Tree` object referring to the root tree of this commit (see below)
- _parents_ - a tuple of parent `Commit` objects. 
    Note that there might be any number of parents, from zero (initial commit)
    to many. At least three parent commits were spotted in the wild.
    
- _message_ - the first line of the commit message.
    Most of commits have only one line message and also the first line is
    what you will see by default on GitHub. 
    However, messages can be arbitrary long.
    Messages of squashed commits are just a concatenation of source commit messages.
    
- _full_message_ - full message, including the first line
- _author_ - name and email, e.g. `'John Doe <johndoe@yahoo.com>'`
- _committer_ - similar to author
- _authored_at_ - unix timestamp with a timezone as a sting, e.g. `'1336361613 +1100'`
- _committed_at_ - similar to _authored_at_

All commit properties are lazy, i.e. they will be instantiated on the first access.
However, the properties above will be instantiated at once if you access any of them.

- _projects_ - list of project urls this commit belongs to
- _children_ - list of projects having this commit as a parent

Example:

    >>> commit = Commit('1e971a073f40d74a1e72e07c682e1cba0bae159b')
    >>> commit.message
    'Initial commit'
    >>> commit.children
    (<Commit: 9bd02434b834979bb69d0b752a403228f2e385e8>,)
    >>> commit.projects
    ['user2589_minicms']
    

Commits can be queried by author, by project and by file name.
Example:

    >>> Commit.by_author('user2589 <valiev.m@gmail.com>')
    (<Commit: 016ae4e8f82a88c7e136be26ec2e56ca37e8f0c4>,
    ... a rather long list of commits omitted ..
     <Commit: fe7caac022031851d76f41216a2b3f44d52586a4>)

Note that `Commit.by_file` returns only commits adding/changing/removing the file.

    >>> Commit.by_file('minicms/templatetags/minicms_tags.py')
    (<Commit: ba3659e841cb145050f4a36edb760be41e639d68>,
    ... 5 commits omitted ..
     <Commit: d11431c3ef74770ac570a82b2fd9b19a690a4adc>)



# Tree

Trees represent folders. Every commit has a root tree:

    >>> commit.tree
    <Tree: d20520ef8c1537a42628b72d481b8174c0a1de84>

Trees are iterable. Every element is a 3-string tuple: 
mode, filename, blob/tree sha:

    >>> tree = Tree('a3a0624d9de2f153e4614863cc6ed2f086942b51')
    >>> list(tree)
    [('100755', '.gitignore', '9825f4f761657f2a8cc1352f2a5cd50a442fb624'),
     ('100644', 'MANIFEST.in', '96bc275bee57ddbe38acbd46776d907bc10f279f'),
     ('100644', 'README.rst', '7e2fa0485a64f0890f5f6ca7f8971bbd92dd9a87'),
     ('40000', 'minicms', '68223fc8336bc3c56e18cbe463d3713bb0d414ce'),
     ('100644', 'setup.py', 'a7550c30e0cb443ec79af189fc738ccf56ef3ed4')]

Note that subfolders are also trees. You can recognize them by mode "40000"

To recursively iterate a tree, use `traverse()`:

    >>> list(tree.traverse())
    [('100755', '.gitignore', '9825f4f761657f2a8cc1352f2a5cd50a442fb624'),
     ('100644', 'MANIFEST.in', '96bc275bee57ddbe38acbd46776d907bc10f279f'),
     ('100644', 'README.rst', '7e2fa0485a64f0890f5f6ca7f8971bbd92dd9a87'),
     ('40000', 'minicms', '68223fc8336bc3c56e18cbe463d3713bb0d414ce'),
     ... some output omitted ...
     ('100644', 'minicms/views.py', '1e397174b6a04fdc4831ce809fb17dde2bd7a295'),
     ('100644', 'setup.py', 'a7550c30e0cb443ec79af189fc738ccf56ef3ed4')]

`full()` will return this list as a string - it's helpful for debugging

    >>> print tree.full()
    100755 .gitignore 9825f4f761657f2a8cc1352f2a5cd50a442fb624
    100644 MANIFEST.in 96bc275bee57ddbe38acbd46776d907bc10f279f
    100644 README.rst 7e2fa0485a64f0890f5f6ca7f8971bbd92dd9a87
    40000 minicms 68223fc8336bc3c56e18cbe463d3713bb0d414ce
     ... a bunch of omitted files...
    100644 minicms/views.py 1e397174b6a04fdc4831ce809fb17dde2bd7a295
    100644 setup.py a7550c30e0cb443ec79af189fc738ccf56ef3ed4


Note that `traverse()` includes subtrees. If you want files only, `files` 
will return a dictionary of `{filename: blob_sha}`

    >>> tree.files
    {'.gitignore': '9825f4f761657f2a8cc1352f2a5cd50a442fb624',
     'MANIFEST.in': '96bc275bee57ddbe38acbd46776d907bc10f279f',
     'README.rst': '7e2fa0485a64f0890f5f6ca7f8971bbd92dd9a87',
     ... some output omitted ...
     'minicms/utils.py': '10ce01a41e4abb4da59a634a22bd0bb51c332ee9',
     'minicms/views.py': '1e397174b6a04fdc4831ce809fb17dde2bd7a295',
     'setup.py': 'a7550c30e0cb443ec79af189fc738ccf56ef3ed4'}

If you just want blobs without file names, there is a shortcut:
    
    >>> tree.blobs
    (<Blob: e69de29bb2d1d6434b8b29ae775ad8c2e48c5391>,
     <Blob: fed6a5206e25905978fc9f0ff61fee5cdada74f1>,
     ... some output omitted ...
     <Blob: 1e397174b6a04fdc4831ce809fb17dde2bd7a295>)

Parent trees, i.e. trees including this one:

    >>> Tree('bd0930554fd24ee1c5b47125c1a206c2ac30621b').parents
    (<Tree: 68223fc8336bc3c56e18cbe463d3713bb0d414ce>,
     <Tree: e7826353f91d9ff5511027443624b455d32c96ed>)
     
Note that some (root) trees don't have parents
    
    >>> tree.parents
    ()

# Blob

Blobs represent file content. Blob is not exactly a file, since several trees 
might refer the same blob under different file names.

String representation of a blob is a file content:

    >>> blob = tree.blobs[-1]
    >>> print blob
    # encoding: utf-8
    from django.conf import settings
    from django import http
    from django.shortcuts import render_to_response
    from django.template import RequestContext
     ... some output omitted ...
    
It is possible to access commits changing a blob with `blob.commits`, 
but this relation is not reliable. Please use with care.

Although blobs have property `parents`, which used to point at parent trees,
it is not maintained and will throw a `DeprecationWarning`


# Tag

This is the most useless object so far. 
It doesn't provide any functionality except validation that this tag exists