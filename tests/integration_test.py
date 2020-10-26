#!python3
"""
Unit tests - only to check functions do what they are expected to do.
Please avoid checking the integrity of the dataset.
"""

import unittest

from oscar import *


class TestBlob(unittest.TestCase):
    def test_commits_shas(self):
        # setup.py from minicms - used in at least couple commits
        blob = Blob('46aaf071f1b859c5bf452733c2583c70d92cd0c8')
        self.assertGreater(len(blob.commit_shas), 1)
        self.assertIsInstance(blob.commit_shas[0], (str, bytes))


class TestTree(unittest.TestCase):
    # there are no relations in this class, everything is covered by unit tests
    pass


class TestCommit(unittest.TestCase):
    def test_projects(self):
        # a commit in numpy from Oct 2009 - present in over 3k projects
        c = Commit('4fb4c64cae2ce1ba16082d918e94e845fa2c87f3')
        self.assertGreater(len(c.project_names), 3000)
        self.assertIsInstance(c.project_names[0], (str, bytes))
        self.assertTrue(any(pname.endswith(b'numpy')
                            for pname in c.project_names))

    def test_children(self):
        #  minicms commit with two children
        c = Commit('a443e1e76c39c7b1ad6f38967a75df667b9fed57')
        self.assertGreater(len(c.child_shas), 1)
        self.assertIsInstance(c.child_shas[0], (str, bytes))

    def test_changed_files(self):
        c = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
        # 3 files changed, 1 deleted
        self.assertGreater(len(c.changed_file_names), 2)
        self.assertIsInstance(c.changed_file_names[0], (str, bytes))


class TestProject(unittest.TestCase):
    def test_commits(self):
        p = Project(b'user2589_minicms')
        self.assertGreater(len(p.commit_shas), 30)
        self.assertIsInstance(p.commit_shas[0], (str, bytes))

    def test_commits_fp(self):
        p = Project(b'user2589_minicms')
        commits = set(c.bin_sha for c in p.commits_fp)
        self.assertGreater(len(commits), 2)
        self.assertLessEqual(len(commits), len(p.commit_shas))
        self.assertTrue(commits.issubset(p.commit_shas))

    def test_in(self):
        p = Project(b'user2589_minicms')
        c = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c')
        self.assertIn(c, p)
        self.assertIn(c.sha, p)
        self.assertIn(c.bin_sha, p)

    def test_head(self):
        self.assertEqual(
            Project(b'user2589_minicms').head,
            Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c'))
        self.assertEqual(
            Project('RoseTHERESA_SimpleCMS').head,
            Commit('a47afa002ccfd3e23920f323b172f78c5c970250'))

    def test_tail(self):
        self.assertEqual(
            Project(b'user2589_minicms').tail,
            binascii.unhexlify('1e971a073f40d74a1e72e07c682e1cba0bae159b'))

    def test_authors(self):
        p = Project(b'user2589_minicms')
        self.assertGreater(len(p.author_names), 1)
        self.assertIsInstance(p.author_names[0], (str, bytes))


class TestFile(unittest.TestCase):
    def test_authors(self):
        f = File(b'minicms/templates/minicms/tags/breadcrumbs.html')
        self.assertGreater(len(f.author_names), 1)
        self.assertIsInstance(f.author_names[0], (str, bytes))

    def test_commits(self):
        f = File(b'minicms/templates/minicms/tags/breadcrumbs.html')
        self.assertGreater(len(f.commit_shas), 1)
        self.assertIsInstance(f.commit_shas[0], (str, bytes))


class TestAuthor(unittest.TestCase):
    def test_commits(self):
        a = Author(b'user2589 <user2589@users.noreply.github.com>')
        self.assertGreater(len(a.commit_shas), 40)
        self.assertIsInstance(a.commit_shas[0], (str, bytes))

    def test_files(self):
        a = Author(b'user2589 <user2589@users.noreply.github.com>')
        self.assertGreater(len(a.file_names), 10)
        self.assertIsInstance(a.file_names[0], (str, bytes))

    def test_projects(self):
        a = Author(b'user2589 <user2589@users.noreply.github.com>')
        self.assertGreater(len(a.project_names), 10)
        self.assertIsInstance(a.project_names[0], (str, bytes))


if __name__ == "__main__":
    unittest.main()
