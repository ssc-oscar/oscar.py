
from libc.stdint cimport uint32_t

cdef unber(bytes buf)
cdef (int, int) lzf_length(bytes raw_data)
cdef uint32_t fnvhash(bytes data)
