#!python3

# cython: language_level=3str
"""
Unit tests - only to check functions do what they are expected to do.
Please refrain from checking integrity of the dataset.
"""
from __future__ import unicode_literals

# Cython caches compiled files, so even if the main file did change but the
# test suite didn't, it won't recompile. More details in this SO answer:
# https://stackoverflow.com/questions/42259741/
import pyximport
pyximport.install(
    # build_dir='build',
    setup_args={"script_args": ["--force"]},
    inplace=True,
    language_level='3str'
)

from oscar import *
from unit_test_cy import *


class TestBasics(unittest.TestCase):
    def test_commit_tz(self):
        ctz = CommitTimezone(9, 30)
        self.assertEqual(repr(ctz), '<Timezone: 09:30>')

    def test_parse_commit_date(self):
        cdate = parse_commit_date(b'1337145807', b'+1130')
        # Things to consider:
        # - unix time is always UTC
        # - when datetime is rendered, it shows time in the specified timezone,
        #   at the given UTC time.
        # - if no timezone is specified, the server timezone is used
        # So, when the timezeon is specified, rendered time should be consistent
        self.assertEqual(cdate.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-16 16:53:27 +1130')
        cdate = parse_commit_date(b'1337145807', b'-1130')
        self.assertEqual(cdate.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-15 17:53:27 -1130')
        self.assertIsNone(parse_commit_date(b'3337145807', b'+1100'))


class TestHash(unittest.TestCase):
    # libtokyocabinet is not thread-safe; you cannot have two open instances of
    # the same DB. `unittest` runs multiple tests in threads, so if we use
    # `.setUp` and multiple tests, it will fail with "threading error".
    # Hence, monolitic test
    def test_hash(self):
        # setup
        # key 114 is from the commit used by TestCommit below, which present
        # in both test and production environment.
        # just a reminder, PATHS[data_type] is a (path, key_length) tuple
        db_path = PATHS['commit_random'][0].format(key=0).encode('ascii')
        self.db = Hash(db_path)

        # reading a single key
        k = b'test_key'
        self.assertEqual(self.db[k], b'\x00\x01\x02\x03')

        # reading all keys
        # create_fixtures.py adds more commits to this file to make it up to 1K
        keys = list(self.db)
        self.assertGreaterEqual(len(keys), 1000)


class TestBase(unittest.TestCase):
    # there is nothing testable at this class right now
    pass


class TestBlob(unittest.TestCase):
    # GitObject: all, instantiate from str/bytes
    def test_string_sha(self):
        self.assertEqual(Blob.string_sha(b'Hello world!'),
                         u'6769dd60bdf536a83c9353272157893043e9f7d0')

    def test_file_sha(self):
        self.assertEqual(Blob.file_sha('LICENSE'),
                         u'94a9ed024d3859793618152ea559a168bbcbb5e2')

    def test_len(self):
        sha = u'83d22195edc1473673f1bf35307aea6edf3c37e3'
        self.assertEqual(len(Blob(sha)), 42)

    def test_data(self):
        # blob has a different .data implementation
        sha = u'83d22195edc1473673f1bf35307aea6edf3c37e3'
        self.assertEqual(
            Blob(sha).data, b'*.egg-info/\ndist/\nbuild/\n*.pyc\n*.mo\n*.gz\n')


class TestTree(unittest.TestCase):
    def test_data(self):
        tree = Tree(u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertEqual(tree.data, (
            b'100755 .gitignore'
            b'\x00\x83\xd2!\x95\xed\xc1G6s\xf1\xbf50z\xean\xdf<7\xe3'
            b'100644 COPYING'
            b'\x00\xfd\xa9K\x84\x12/o6G<\xa3W7\x94\xa8\xf2\xc4\xf4\xa5\x8c'
            b'100644 MANIFEST.in'
            b'\x00\xb7$\x83\x15\x19\x90N+\xc2SsR;6\x8c]A\xdc6\x8e'
            b'100644 README.rst'
            b'\x00#JWS\x8f\x15\xd7/\x00`;\xf0\x86\xb4e\xb0\xf2\xcd\xa7\xb5'
            b'40000 minicms'
            b'\x00\x95H)\x88z\xf5\xd9\x07\x1a\xa9,Bq3\xca,\xdd\x08\x13\xcc'
            b'100644 setup.py'
            b'\x00F\xaa\xf0q\xf1\xb8Y\xc5\xbfE\'3\xc2X<p\xd9,\xd0\xc8'
        ))

    def test_files(self):
        tree = Tree(u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertIn(b'.gitignore', tree.files)
        self.assertNotIn(b'minicms', tree.files)  # folders are not included

    def test_in(self):
        tree = Tree(u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertIn(b'.gitignore', tree)
        self.assertNotIn(File(b'.keep'), tree)
        # setup.py blob
        self.assertIn(u'46aaf071f1b859c5bf452733c2583c70d92cd0c8', tree)
        self.assertIn(Blob(u'46aaf071f1b859c5bf452733c2583c70d92cd0c8'), tree)

    def test_len(self):
        tree = Tree(u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertEqual(len(tree), 5)

    def test_pprint(self):
        self.assertEqual(
            Tree(u'd4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d').str,
            u'100755 .gitignore 83d22195edc1473673f1bf35307aea6edf3c37e3\n'
            u'100644 COPYING fda94b84122f6f36473ca3573794a8f2c4f4a58c\n'
            u'100644 MANIFEST.in b724831519904e2bc25373523b368c5d41dc368e\n'
            u'100644 README.rst 234a57538f15d72f00603bf086b465b0f2cda7b5\n'
            u'40000 minicms 954829887af5d9071aa92c427133ca2cdd0813cc\n'
            u'100644 setup.py 46aaf071f1b859c5bf452733c2583c70d92cd0c8')


class TestCommit(unittest.TestCase):
    def test_init(self):
        sha = u'05cf84081b63cda822ee407e688269b494a642de'
        bin_sha = binascii.unhexlify(sha)
        self.assertEqual(GitObject(sha).sha, sha)
        self.assertEqual(GitObject(sha).bin_sha, bin_sha)
        self.assertRaises(ValueError, lambda: GitObject(u'05cf84081b63cda822'))

    def test_eq(self):
        sha = u'f2a7fcdc51450ab03cb364415f14e634fa69b62c'
        self.assertEqual(Commit(sha), Commit(sha))
        self.assertNotEqual(Commit(sha), Blob(sha))

    def test_data(self):
        data = Commit(u'f2a7fcdc51450ab03cb364415f14e634fa69b62c').data
        self.assertEqual(
            b'tree d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d\n'
            b'parent 66acf0a046a02b48e0b32052a17f1e240c2d7356\n'
            b'author Pavel Puchkin <neoascetic@gmail.com> 1375321509 +1100\n'
            b'committer Pavel Puchkin <neoascetic@gmail.com> 1375321597 +1100\n'
            b'\nLicense changed :P\n', data)

    def test_attrs(self):
        c = Commit(u'e38126dbca6572912013621d2aa9e6f7c50f36bc')
        self.assertTrue(c.author.startswith(b'Marat'))
        self.assertTrue(c.committer.startswith(b'Marat'))
        self.assertEqual(c.message, b'support no i18n')
        parent_sha = b'ab124ab4baa42cd9f554b7bb038e19d4e3647957'
        self.assertEqual(c.parent_shas, (binascii.unhexlify(parent_sha),))
        self.assertIsInstance(c.committed_at, datetime)
        self.assertIsInstance(c.authored_at, datetime)
        self.assertEqual(c.committed_at.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-19 01:14:08 +1100')
        self.assertEqual(c.authored_at.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-19 01:14:08 +1100')
        self.assertIsInstance(c.tree, Tree)
        self.assertEqual(c.tree.sha, u'6845f55f47ddfdbe4628a83fdaba35fa4ae3c894')
        self.assertRaises(AttributeError, lambda: c.arbitrary_attr)
        self.assertIsNone(c.signature)

        c = Commit(u'1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab')
        self.assertIsInstance(c.signature, bytes)
        self.assertGreater(len(c.signature), 450)  # 454 for this commit


class TestProject(unittest.TestCase):
    def test_url(self):
        self.assertEqual(Project(b'testuser_test_proj').url,
                         b'https://github.com/testuser/test_proj')
        self.assertEqual(Project(b'testuser_test_proj').url,
                         b'https://github.com/testuser/test_proj')
        self.assertEqual(Project(b'sourceforge.net_tes_tproj').url,
                         b'https://git.code.sf.net/p/tes_tproj')
        self.assertEqual(Project(b'drupal.com_testproj').url,
                         b'https://github.com/drupal.com/testproj')


class TestFile(unittest.TestCase):
    # this class consists of relations only - nothing to unit test
    pass


class TestAuthor(unittest.TestCase):
    # this class consists of relations only - nothing to unit test
    pass


if __name__ == "__main__":
    unittest.main()
