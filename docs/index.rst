.. oscar documentation master file, created by
   sphinx-quickstart on Mon May 28 14:28:44 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Reference
===========

.. toctree::
   :maxdepth: 2

   contribute


This module provides interface to the objects:

- :py:class:`.Project` - represents a repository
- :py:class:`.Commit` - represents a commit in a repository
- :py:class:`.Tree` - represents a directory and its content. Each `Commit` has a root tree.
- :py:class:`.File` - represents a file path, including all parent directories/trees
- :py:class:`.Blob` - Binary Large OBject, represents a file content.
- :py:class:`.Author` - represents a combination of author name and email.

`Commit`, `Tree` and `Blob` are a straightforward representation of
objects used by Git internally.
It will be helpful to read `Chapter 2 <https://git-scm.com/book/en/v2/Git-Internals-Git-Objects>`_
of `Pro Git book <https://git-scm.com/book/en/v2/>`_ (free and Open Source)
for better understanding of these objects.

Common methods
--------------
.. py:module:: oscar

All objects have a unique key.
For git objects (`Commit`, `Tree`, `Blob`)
it is the object SHA hash;
for `Project` it is the project URI;
for `File` it is the filename;
for `Author` it is the author name and email.
Objects of the same type and having the same key will be considered equivalent:

    >>> sha = 'f2a7fcdc51450ab03cb364415f14e634fa69b62c'
    >>> Commit(sha) == Commit(sha)
    True

It is possible to iterate all objects of a given type using `.all()`

.. automethod:: _Base.all

    E.g. to iterate all repositories of user2589 on github:

    >>> for project in Project.all():
    ...     print project.uri

GitObject methods
-----------------

These methods are shared by `Commit`, `Tree`, `Blob`.

All git objects are instantiated by a 40-byte hex string SHA or a 20-byte binary SHA.
In most cases you will use hex form, the latter way is needed only fore relatively
rare cases you need to interface with binary data.

    >>> Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
    >>> Commit(b'\xf2\xa7\xfc\xdcQE\n\xb0<\xb3dA_\x14\xe64\xfai\xb6,')

Whatever form of SHA was used to instantiate the object, it will have properties:

- `sha` - 40-byte hex string
- `bin_sha` - 20 bytes binary string

All git objects, when coerced to `str`, will return their internal representation.
It is mostly important for `Blob` to access the file content.


Class reference
---------------

.. autoclass:: Project
    :members: commit_shas, commits, head, tail, commits_fp

.. autoclass:: Commit
    :members: parents, project_names, projects, child_shas, children, blob_shas, blobs

.. autoclass:: Tree
    :members: traverse, files, blob_shas, blobs

.. autoclass:: File
    :members: commit_shas, commits

.. autoclass:: Blob
    :members: data, commit_shas, commits

.. autoclass:: Author
    :members: commit_shas, commits
