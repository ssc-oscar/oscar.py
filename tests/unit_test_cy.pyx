
# cython: language_level=3str
"""
Unit tests - only to check functions do what they are expected to do.
Please refrain from checking integrity of the dataset.
"""

import unittest

cimport oscar

class TestUtils(unittest.TestCase):
    # ignored, as they're executed on import anyway:
    #     _latest_version
    #     _key_length
    #     _get_paths

    def test_unber(self):
        self.assertEqual(oscar.unber(b'\x00\x83M'), [0, 461])
        self.assertEqual(oscar.unber(b'\x83M\x96\x14'), [461, 2836])
        self.assertEqual(oscar.unber(b'\x99a\x89\x12'), [3297, 1170])
        # test number exceeding 32-bit signed int
        self.assertEqual(oscar.unber(
            b'\x84\xb0\xfb\x82\xd93*'), [150581849267, 42])

    def test_lzf_length(self):
        self.assertEqual(oscar.lzf_length(b'\xc4\x9b'), (2, 283))
        self.assertEqual(oscar.lzf_length(b'\xc3\xa4'), (2, 228))
        self.assertEqual(oscar.lzf_length(b'\xc3\x8a'), (2, 202))
        self.assertEqual(oscar.lzf_length(b'\xca\x87'), (2, 647))
        self.assertEqual(oscar.lzf_length(b'\xe1\xaf\xa9'), (3, 7145))
        self.assertEqual(oscar.lzf_length(b'\xe0\xa7\x9c'), (3, 2524))
        # test extra bytes don't affect the result
        self.assertEqual(oscar.lzf_length(b'\xc4\xa6\x1f100644'), (2, 294))

    def test_decomp(self):
        # TODO: test decomp()
        pass

    def test_fnvhash(self):
        self.assertEqual(hex(oscar.fnvhash(b'foo')), '0xa9f37ed7')
