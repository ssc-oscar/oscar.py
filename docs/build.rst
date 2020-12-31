
As of 1.3 version, `oscar` is compiled from Cython, 
and thus requires few extra build steps.

Motivation
----------

The reason for this is that `libtokyocabinet` binding,
`python-tokyocabinet`, is a C extension that only supports 
Python 2 without any plans to implement Python3 compatibility.
Several options were considered:

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


About Cython
------------

Cython code is first transpiled into C code, which is then compiled into
a C Python extension (`.so` file on Linux systems). Generally, it does not
matter which letter of Python was used in the first step

There are `two main ways to compile <https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html>`_
Cython code, using `cythonize` and `pyximport`. The former one is done explicitly, 
e.g. to build binaries for distribution, while the latter one allows building
in place.