
# cython: language_level=3str
"""
Unit tests - only to check functions do what they are expected to do.
Please refrain from checking integrity of the dataset.
"""
from __future__ import unicode_literals

import pyximport
# Cython caches compiled files, so even if the main file did change but the
# test suite didn't, it won't recompile. More details in this SO answer:
# https://stackoverflow.com/questions/42259741/
pyximport.install(setup_args={"script_args": ["--force"]}, language_level='3str')

from oscar import *
from .unit_test_cy import *


class TestBasics(unittest.TestCase):
    def test_commit_tz(self):
        ctz = CommitTimezone(9, 30)
        self.assertEqual(repr(ctz), '<Timezone: 09:30>')

    def test_parse_commit_date(self):
        cdate = parse_commit_date(b'1337145807', b'+1100')
        self.assertEqual(cdate.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-16 16:23:27 +1100')
        self.assertIsNone(parse_commit_date(b'3337145807', b'+1100'))


class TestHash(unittest.TestCase):
    # libtokyocabinet is not thread-safe; you cannot have two open instances of
    # the same DB. `unittest` runs multiple tests in threads, so if we use
    # `.setUp` and multiple tests, it will fail with "threading error".
    # Hence, monolitic test
    def test_hash(self):
        # setup
        self.db = Hash(b'/fast/All.sha1/sha1.commit_0.tch')

        # reading a single key
        k = b'\x80\xb4\xca\x99\xf8`Y\x03\xd8\xack\xd9!\xeb\xed\xfd\xfe\xcd\xd6`'
        self.assertEqual(self.db[k], b'\x00')

        # reading all keys
        # TODO: re-enable once done debugging
        keys = list(self.db)
        self.assertGreaterEqual(len(keys), 14620535)


class TestBase(unittest.TestCase):
    # there is nothing testable at this class right now
    pass


class TestCommit(unittest.TestCase):
    def test_init(self):
        sha = '05cf84081b63cda822ee407e688269b494a642de'
        bin_sha = b'\x05\xcf\x84\x08\x1b\x63\xcd\xa8\x22\xee' \
                  b'\x40\x7e\x68\x82\x69\xb4\x94\xa6\x42\xde'
        self.assertEqual(GitObject(sha).sha, sha)
        self.assertEqual(GitObject(sha).bin_sha, bin_sha)
        self.assertRaises(ValueError, lambda: GitObject('05cf84081b63cda822ee'))

    def test_eq(self):
        sha = 'f2a7fcdc51450ab03cb364415f14e634fa69b62c'
        self.assertEqual(Commit(sha), Commit(sha))
        self.assertNotEqual(Commit(sha), Blob(sha))

    def test_data(self):
        data = Commit('f2a7fcdc51450ab03cb364415f14e634fa69b62c').data
        self.assertEqual(
            b'tree d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d\n'
            b'parent 66acf0a046a02b48e0b32052a17f1e240c2d7356\n'
            b'author Pavel Puchkin <neoascetic@gmail.com> 1375321509 +1100\n'
            b'committer Pavel Puchkin <neoascetic@gmail.com> 1375321597 +1100\n'
            b'\nLicense changed :P\n', data)

    def test_attrs(self):
        c = Commit('e38126dbca6572912013621d2aa9e6f7c50f36bc')
        self.assertTrue(c.author.startswith('Marat'))
        self.assertTrue(c.committer.startswith('Marat'))
        self.assertEqual(c.message, b'support no i18n')
        parent_sha = b'ab124ab4baa42cd9f554b7bb038e19d4e3647957'
        self.assertEqual(c.parent_shas, (binascii.unhexlify(parent_sha),))
        self.assertEqual(c.committed_at.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-18 03:14:08 -1100')
        self.assertEqual(c.authored_at.strftime('%Y-%m-%d %H:%M:%S %z'),
                         '2012-05-18 03:14:08 -1100')
        self.assertIsInstance(c.tree, Tree)
        self.assertEqual(c.tree.sha, '6845f55f47ddfdbe4628a83fdaba35fa4ae3c894')
        self.assertRaises(AttributeError, lambda: c.arbitrary_attr)
        self.assertIsNone(c.signature)

        c = Commit('1cc6f4418dcc09f64dcbb0410fec76ceaa5034ab')
        self.assertIsInstance(c.signature, bytes)
        self.assertGreater(len(c.signature), 450)  # 454 for this commit


class TestBlob(unittest.TestCase):
    # GitObject: all, instantiate from str/bytes
    def test_string_sha(self):
        self.assertEqual(Blob.string_sha(b'Hello world!'),
                         '6769dd60bdf536a83c9353272157893043e9f7d0')

    def test_file_sha(self):
        self.assertEqual(Blob.file_sha('LICENSE'),
                         '94a9ed024d3859793618152ea559a168bbcbb5e2')

    def test_len(self):
        sha = '83d22195edc1473673f1bf35307aea6edf3c37e3'
        self.assertEqual(len(Blob(sha)), 42)

    def test_data(self):
        # blob has a different .data implementation
        sha = '83d22195edc1473673f1bf35307aea6edf3c37e3'
        self.assertEqual(
            Blob(sha).data, b'*.egg-info/\ndist/\nbuild/\n*.pyc\n*.mo\n*.gz\n')


class TestTree(unittest.TestCase):
    def test_data(self):
        tree = Tree("d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d")
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
        tree = Tree('d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertIn(b'.gitignore', tree.files)
        self.assertNotIn(b'minicms', tree.files)  # folders are not included

    def test_in(self):
        tree = Tree('d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertIn(b'.gitignore', tree)
        self.assertNotIn(File(b'.keep'), tree)
        self.assertIn('46aaf071f1b859c5bf452733c2583c70d92cd0c8', tree)
        self.assertIn(Blob('46aaf071f1b859c5bf452733c2583c70d92cd0c8'), tree)

    def test_len(self):
        tree = Tree('d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d')
        self.assertEqual(len(tree), 16)
        
    def test_pprint(self):
        self.assertEqual(
            Tree('d4ddbae978c9ec2dc3b7b3497c2086ecf7be7d9d').str,
            '100755 .gitignore 83d22195edc1473673f1bf35307aea6edf3c37e3\n'
            '100644 COPYING fda94b84122f6f36473ca3573794a8f2c4f4a58c\n'
            '100644 MANIFEST.in b724831519904e2bc25373523b368c5d41dc368e\n'
            '100644 README.rst 234a57538f15d72f00603bf086b465b0f2cda7b5\n'
            '40000 minicms 954829887af5d9071aa92c427133ca2cdd0813cc\n'
            '100644 setup.py 46aaf071f1b859c5bf452733c2583c70d92cd0c8')

#
# class TestRelations(unittest.TestCase):
#     """
#     List of all relations and data file locations
#     https://bitbucket.org/swsc/lookup/src/master/README.md
#
#     author2commit   - done
#     author2project  - done
#     author2file     - done // Fail
#     blob2commit     - done // 2x  Fails
#     cmt_time_author - needs testing
#     cmt_head	    - needs testing
#     commit2blob     - done // Fail
#     commit2project  - done
#     commit2children - done
#     file2commit     - done
#     project2commit  - done
#     project_url	    - done
#     """
#
#     def test_project_url(self):
#         proj = 'CS340-19_MoonMan'
#         url = Project(proj).toURL()
#         request = requests.get(url)
#         self.assertEqual(
#             request.status_code,  200,
#             "%s can supposedly be found at %s, but website is not a legitimate "
#             "URL" % (proj, url))
#
#     def test_author_torvald(self):
#         pass
#
#     def test_commit_head(self):
#         commit = 'e38126dbca6572912013621d2aa9e6f7c50f36bc'
#         head, depth = Commit_info(commit).head
#         # WTF?
#         self.assertIs(
#             tuple(Commit(commit).parent_shas), False,
#             "c2hFullO lists %s as the head commit, but %s has parent shas"
#             "" % (head, head))
#
#     def test_commit_time_author(self):
#         commit = 'e38126dbca6572912013621d2aa9e6f7c50f36bc'
#         time, author = Commit_info(commit).time_author
#         self.assertEqual(
#             author, Commit(commit).author,
#             "c2taFullO lists commit author as %s, but the author listed in "
#             "Cmt2Auth is %s" % (author, Commit(commit).author))
#
#     def test_author_projects(self):
#         """ Test dpg.py for list author names for a project, and whether other
#         projects for those same authors can be listed. """
#         proj = 'CS340-19_students'
#         print("List of " + proj + " authors:")
#         print("--------------------------------------")
#         for author in Project(proj).author_names:
#             print(author)
#             print("|-> also worked on these projects: "),
#             for p_name in Author(author.encode('utf-8')).project_names:
#                 if p_name == proj:
#                     continue
#                 print(p_name),
#             print("\n")
#
#     def test_author_commit(self):
#         """ Test if all commits made by an author are listed in Auth2Cmt """
#         proj = 'user2589_minicms'
#         authors = ('Marat <valiev.m@gmail.com>',
#                    'user2589 <valiev.m@gmail.com>')
#         commits = {c.sha: c for c in Project(proj).commits}
#
#         for author in authors:
#             relation = {c.sha: c for c in Author(author).commits}
#             for sha, c in relation.items():
#                 self.assertEqual(
#                     c.author, author,
#                     "Author2Cmt lists commit %s as authored by %s, but it is "
#                     "%s" % (sha, author, c.author))
#
#             relation = {sha for sha in relation if sha in commits}
#             cs = {sha for sha, c in commits.items() if c.author == author}
#             diff = relation - cs
#             self.assertFalse(
#                 diff, "Author2Cmt lists commits %s as authored by %s, but"
#                       "they are not" % (",".join(diff), author))
#             diff = cs - relation
#             self.assertFalse(
#                 diff, "Author2Cmt does not list commits %s as authored by %s,"
#                       "but they are" % (",".join(diff), author))
#
#     def test_blob_commits_change(self):
#         """ Test if all commits modifying a blob are listed in Blob2Cmt """
#         # this commit changes a bunch of files
#         # https://github.com/user2589/minicms/commit/SHA
#         commit_sha = 'ba3659e841cb145050f4a36edb760be41e639d68'
#         commit = Commit(commit_sha)
#         parent = commit.parents.next()
#
#         blobs = {sha for fname, sha in commit.tree.files.items()
#                  if parent.tree.files.get(fname) != sha}
#
#         for sha in blobs:
#             self.assertIn(
#                 commit_sha, Blob(sha).commit_shas,
#                 "Blob2Cmt doesn't list commit %s for blob %s,"
#                 "but it but it was changed in this commit" % (commit_sha, sha))
#
#     def test_blob_commits_add(self):
#         """ Test if all commits adding a blob are listed in Blob2Cmt """
#         # this is the first commit in user2589_minicms
#         # https://github.com/user2589/minicms/commit/SHA
#         commit_sha = '1e971a073f40d74a1e72e07c682e1cba0bae159b'
#         commit = Commit(commit_sha)
#
#         blobs = set(commit.tree.files.values())
#
#         for sha in blobs:
#             self.assertIn(
#                 commit_sha, Blob(sha).commit_shas,
#                 "Blob2Cmt doesn't list commit %s for blob %s,"
#                 "but it was added in this commit" % (commit_sha, sha))
#
#     def test_blob_commits_all(self):
#         """ Test if all commit modifiying a blob are listed in blob2Cmt """
#         # the first version of Readme.rst in user2589_minicms
#         # it was there for only one commit, so:
#         #     introduced in 2881cf0080f947beadbb7c240707de1b40af2747
#         #     removed in 85787429380cb20b6a935e52c50f85f455790617
#         # Feel free to change to any other blob from that project
#         proj = 'user2589_minicms'
#         blob_sha = 'c3bfa5467227e7188626e001652b85db57950a36'
#         commits = {c.sha: c for c in Project(proj).commits}
#         present = {sha: blob_sha in c.tree.files.values()
#                    for sha, c in commits.items()}
#
#         # commit is changing a blob if:
#         #   all of parents have it and this commit doesn't
#         #   neither of parents have it and commit does
#         changed = {c.sha for sha, c in commits.items()
#                    if not any(present[p] for p in c.parent_shas)
#                    and present[c.sha]}
#
#         # just in case this blob is not unique to the project,
#         # e.g. a license file, filter first
#         relation = {sha for sha in Blob(blob_sha).commit_shas
#                     }.intersection(commits.keys())
#
#         diff = relation - changed
#         self.assertFalse(
#             diff, "Blob2Cmt indicates blob %s was changed in "
#                   "commits %s, but it was not" % (blob_sha, ",".join(diff)))
#
#         diff = changed - relation
#         self.assertFalse(
#             diff, "Blob2Cmt indicates blob %s was NOT changed in "
#                   "commits %s, but it was" % (blob_sha, ",".join(diff)))
#
#     def test_commit_blobs(self):
#         """ Test if all blobs modified in a commit are listed in c2bFull """
#         for sha in ('1e971a073f40d74a1e72e07c682e1cba0bae159b',
#                     'e38126dbca6572912013621d2aa9e6f7c50f36bc'):
#             c = Commit(sha)
#             relation = set(c.blob_shas_rel)
#             blobs = set(c.blob_shas)
#             diff = relation - blobs
#             self.assertFalse(
#                 diff, "c2bFull: blobs %s are in the relation but they "
#                       "are not in the commit %s" % (",".join(diff), sha))
#             diff = blobs - relation
#             self.assertFalse(
#                 diff, "c2bFull: blobs %s are in the commit %s but they are "
#                       "not reported by the relation" % (",".join(diff), sha))
#
#     def test_commit_projects(self):
#         """ Test if all projects having a commit are listed in Cmt2Prj """
#         for proj in ('user2589_minicms', 'user2589_karta'):
#             for c in Project(proj).commits:
#                 self.assertIn(
#                     proj, c.project_names,
#                     "Cmt2Prj asserts commit %s doesn't belong to project %s, "
#                     "but it does" % (c.sha, proj))
#
#     def test_commit_children(self):
#         project = 'user2589_minicms'
#         commits = {c.sha: c for c in Project(project).commits}
#         children = defaultdict(set)
#         for sha, c in commits.items():
#             for parent_sha in c.parent_shas:
#                 children[parent_sha].add(c.sha)
#
#         for sha, c in commits.items():
#             # filter out commits outside of the project, just in case
#             relation = {sha for sha in c.child_shas if sha in commits}
#
#             diff = relation - children[sha]
#             self.assertFalse(
#                 diff, "Cmt2Chld lists commits %s as children of commit %s, but"
#                       "they are not" % (",".join(diff), sha))
#
#             diff = children[sha] - relation
#             self.assertFalse(
#                 diff, "Cmt2Chld doesn't list commits %s as children of commit "
#                       "%s, but they are" % (",".join(diff), sha))
#
#     def test_commit_files(self):
#         project = 'user2589_minicms'
#         commits = {c.sha: c for c in Project(project).commits}
#         children = defaultdict(set)
#
#         for sha, c in commits.items():
#             for parent_sha in c.parent_shas:
#                 children[parent_sha].add(c.sha)
#
#         for sha, c in commits.items():
#             # filter out commits outside of the project, just in case
#             relation = set(c.changed_file_names)
#
#         # TODO: complete this test
#
#     def test_file_commits(self):
#         """ Test if all commits modifying a file are listed in File2Cmt """
#         proj = 'user2589_minicms'
#         fname = 'minicms/templatetags/minicms_tags.py'
#         commits = {c.sha: c for c in Project(proj).commits}
#
#         changed = set()
#         for sha, c in commits.items():
#             # this relation only follows the first parent for diff :(
#             pt_files = c.parent_shas and c.parents.next().tree.files or {}
#             if pt_files.get(fname) != c.tree.files.get(fname):
#                 changed.add(sha)
#
#         # only consider changes in this project
#         relation = {sha for sha in File(fname).commit_shas if sha in commits}
#
#         diff = relation - changed
#         self.assertFalse(
#             diff, "File2Cmt indicates file %s was changed in "
#                   "commits %s, but it was not" % (fname, ",".join(diff)))
#
#         diff = changed - relation
#         self.assertFalse(
#             diff, "File2Cmt indicates file %s was NOT changed in "
#                   "commits %s, but it was" % (fname, ",".join(diff)))
#
#     def test_file_commits_delete(self):
#         fname = "minicms/static/minicms/markdown.css"
#         # deleted by this commit
#         sha = '1837bfa6553a9f272c5dcc1f6259ba17357cf8ed'
#         self.assertIn(sha, File(fname).commit_shas,
#                       "File %s was deleted by commit %s but was not listed "
#                       "as changing it." % (fname, sha))
#
#     def test_project_commits(self):
#         """ Test if all commits in a project are listed in Prj2Cmt """
#         # select something long abandoned and with <100 commits
#         project = 'user2589_minicms'
#         relation = {c.sha for c in Project(project).commits}
#         url = "https://api.github.com/repos/%s/commits?" \
#               "per_page=100" % project.replace("_", "/")
#         github = {c['sha'] for c in requests.get(url).json()}
#
#         diff = relation - github
#         self.assertFalse(
#             diff, "Prj2Cmt lists commits %s in project %s but they're not on "
#                   "github" % (",".join(diff), project))
#
#         diff = github - relation
#         self.assertFalse(
#             diff, "Prj2Cmt doesn't list commits %s in project %s but they're "
#                   "on github" % (",".join(diff), project))


if __name__ == "__main__":
    unittest.main()
