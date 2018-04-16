
import lzf
import tokyocabinet


def decomp(raw_data):
    # the 
    INVALID = "compressed data corrupted (invalid length)"
    if not raw_data:
        raise ValueError(INVALID)
    l = ord(raw_data[0])
    csize = len(raw_data)
    start = 1
    mask = 0x80
    while mask and csize > start and (l & mask):
        mask >>= 1 + (mask == 0x80)
        start += 1
    if not mask or csize <= start:
        raise ValueError(INVALID)
    usize = l & (mask - 1)
    for i in range(1, start):
        usize = (usize << 6) + (ord(raw_data[i]) & 0x3f)
    if not usize:
        raise ValueError(INVALID)
    return lzf.decompress(raw_data[start:], usize)

