
Starting version 1.3, `oscar` is compiled from Cython, a language closely
resembling Python but with optional strong typing to improve performance.
Building Cython packages requires few extra build steps, as explained below.

In addition, automation in this project relies on few assumptions which you are
expected to follow. Below you can find their brief description and the motivation
behind.


How to contribute
-----------------

All the development is done on feature branches, which are then merged to `master`
via pull requests. Every pull request triggers unit testing, every merge triggers
a release.

To generate release notes, we use `conventional commits <https://www.conventionalcommits.org>`_,
a convention to commit messages. In a nutshell, it means commit messages should
be prefixed with one of:

- **fix:** in case the change fixes a problem without changing any interfaces.
    Example commit message: `fix: missing clickhouse-driver dependency (closes #123)`.
- **feat:** the change implements a new feature, without affecting existing
    interfaces. Example: `feat: implement author timeline`.
- other prefixes, e.g. `chore:`, `refactor:`, `docs:`, `test:`, `ci:`, etc.
    - these will not be included in release notes and will not trigger a new
    release without new features or fixes added, unless contain breaking changes
    (see below).

In case of breaking changes (i.e. if any interfaces were changed, breaking
backward compatibility), commit message should include an exclamation mark before
the semicolon, or contain **BREAKING CHANGE** in the footer, e.g.:

    `feat!: drop support for deprectated parameters`

`fix`, `chore`, `docs` commits will produce patch versions, `feat` will result
in a minor version bump, and in case of breaking changes the major version will
be incremented. As a consequence, **you must never change version number manually**.

Not following these procedures might take your pull request extra time to
review and in some cases will require rewriting the commit history.


About Cython
------------

The reason to use Cython was primarily Python 3 support. WoC data is stored
in tokyocabinet (.tch) files, without native Python support.
`libtokyocabinet` binding, `python-tokyocabinet`, is a C extension supporting
Python 2 only, and lack of development activity suggests updating it for Py 3
is hardly considered. So, our options to interface `libtokyocabinet` were:

- cffi (C Foreign Functions Interface) - perhaps, the simplest option,
  but it does not support conditional definitions (`#IFDEF`), that are
  actively used in tokyocabinet headers
- C extension, adapting existing `python-tokyocabinet` code for Python 3.
  It is rather hard to support and even harder to debug; a single
  attempt was scrapped after making a silently failing extension.
- SWIG, a Google project to generate C/C++ library bindings
  for pretty much any language. Since this library provides 1:1 interface
  to the library methods, Python clients had to be aware of the returned
  C structures used by libtokyocabinet, which was very inconvenient.
- Cython, a weird mix of Python and C. It allows writing Python interfaces,
  while simultaneously using C functions. This makes it the ideal option
  for our purposes, providing a Python tch file handler holding working
  with libtokyocabinet C structures under the hood.

Cython came a clear winner in this comparison, also helping to speed up
some utility functions along the way (e.g. `fnvhash`, a pure Python version
of which was previously used).

Compiling and packaging
----------------------

To compile oscar locally, run:
`python setup.py build_ext --inplace`. To explicitly specify python version,
replace `pyhon`, with the appropriate version, e.g. `python2`.
There shorter alias for this command, `make build`, will always use the default
Python.

If you are building for several Python versions in a row without changing the
code (e.g. to check if it compiles at all), make sure you clean up first by
running `make clean`.
Compilation is cached when possible, and will be omitted if the input hasn't
changed - the compiler is not aware that the resulting `.so` file exposes
different interfaces. You will get a lot of angry messages about missing
interfaces and symbols when import with the same Python version which "compiled"
this `.so` just a second ago in this case.

Packaging is slightly more complicated than just compiling since oscar needs to
support at least Python 2.7 and 3.6 simultaneously, meaning we need to package
multiple binaries. Fortunately, `PEP 513 <https://www.python.org/dev/peps/pep-0513/>`_
offers support for such packages. Building is done via `manylinux <https://github.com/pypa/manylinux>`_,
a special Docker image, and is automated via GitHub action.

To build package locally,

1. clone the corresponding GitHub action repository,
  `git clone git@github.com:RalfG/python-wheels-manylinux-build.git`,
2. check out the desired tag if necessary, e.g. `git checkout v0.3.3`
3. build Docker image: `docker build -t manylinux2010 .`
4. run the image: `make build_manylinux`


Testing
-------

Every push to oscar repository is automatically tested; on top, you might want
to test locally before making a commit to avoid awkward followup fixes and a
bunch of angry emails from GitHub actions bot telling how you broke the build.
Unit tests are tedious to write, but will save a lot of your time in the long run.
First thing to know about  unit tests, please DO write them - future you will be
grateful. Second, there are a couple things about testing Cython code against a
remote dataset.

To run tests locally, `make test_local`.
WoC files are only available on UTK servers only, so to make local testing
possible, there is a small subset of the data in `tests/fixtures`. Changing
oscar paths to point at these fixtures requires setting some environment
variables, stored in `tests/local_test.env`.
To tests locally,

1. set environment variables, `source tests/local_test.env`
2. clean up previously compiled binaries to avoid Py2/3 compatibility issues:
  `make clean`
3. run the test script: `PYTHONPATH=. python tests/unit_test.py`. Don't forget to
  replace `python` with a specific version if testing against non-default Python)

`make test_local` is a shortcut for this, except it will always use the default
Python and thus doesn't need to clean.

Unit tests for Cython functions (i.e., defined with `cdef`) are stored in a
separate `.pyx` file, which is imported from the regular `.py` test suite.
Cython code can only be accessed from Cython files, which cannot executed as a
Python script. Thus, we have to store them separately - see `tests/unit_test.py`
and `tests/unit_test_cy.pyx` as an example of how it is organized.

To avoid manual compilation with `cythonize`, Cython tests are compiled with
`pyximport`, an in-place JIT compiler. Thus, at the beginning of every test suite,
install `pyximport`:

.. code-block:: python
    import pyximport
    pyximport.install(
        # build_dir='build',
        setup_args={"script_args": ["--force"]},
        inplace=True,
        language_level='3str'
    )

To tell `pyximport` where to find sources and libraries for the main module,
there is a special file `oscar.pyxbld`. It is important to keep it consistent
with the `Extension` parameters in `setup.py`. If you can `make build` but unit
tests fail to compile it, this is the first place to check.

Cython functions being tested should be exposed in `oscar.pxd` -
a Cython equivalent of a header file. If tests cannot find some function that is
defined in oscar, check it is included there. Hopefully, the list of tested
functions will grow bigger with your help.

Finally, unit and integration tests can also be run on real data. On one of UTK
servers (preferably, `da4`), clone the repository and run `make test`. If the
result is different from your local run, perhaps it's time to update fixtures
and/or tests.


