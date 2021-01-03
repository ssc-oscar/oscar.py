
# cython: language_level=3str
from libc.stdint cimport uint32_t

# we need this header file for unit tests.
cdef unber(bytes buf)
cdef (int, int) lzf_length(bytes raw_data)
cdef uint32_t fnvhash(bytes data)
