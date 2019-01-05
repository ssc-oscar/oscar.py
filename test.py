
import requests

from collections import defaultdict
import doctest
import logging
import os
import unittest

from oscar import *


class TestStatus(unittest.TestCase):
    """Check what data/relations are available"""
    def test_status(self):
        # this test never fails. Instead, it logs status to stderr
        levels = {
            1: logging.warning,
            2: logging.error,
            3: logging.critical,
        }

        def check(path, level):
            if not os.path.isfile(path):
                levels[level]("Does not exist: %s", path)

        kwargs = {'type': 'commit', 'key': 0}
        # key lenght: 7 bit, with few exceptions
        check(PATHS['all_random'].format(**kwargs), 3)
        check(PATHS['blob_data'].format(**kwargs), 1)
        check(PATHS['all_sequential'].format(**kwargs) + '.idx', 1)
        check(PATHS['commit_index_line'].format(**kwargs), 1)

        kwargs['type'] = 'tree'
        check(PATHS['all_random'].format(**kwargs), 3)
        check(PATHS['blob_data'].format(**kwargs), 1)
        check(PATHS['all_sequential'].format(**kwargs) + '.idx', 1)
        check(PATHS['tree_index_line'].format(**kwargs), 1)

        kwargs = {'type': 'blob', 'key': 0}
        check(PATHS['blob_data'].format(**kwargs), 3)
        check(PATHS['blob_offset'].format(**kwargs), 3)
        check(PATHS['blob_index_line'].format(**kwargs), 1)

        # type-agnostic
        # key length: 4 bit
        check(PATHS['blob_commits'].format(**kwargs), 2)
        check(PATHS['commit_blobs'].format(**kwargs), 2)
        # key length: 3 bit
        check(PATHS['commit_projects'].format(**kwargs), 2)
        check(PATHS['project_commits'].format(**kwargs), 2)
        check(PATHS['file_commits'].format(**kwargs), 2)
        check(PATHS['commit_children'].format(**kwargs), 2)
        # key length: 0
        check(PATHS['author_commits'].format(**kwargs), 2)

        kwargs = {'type': 'tag', 'key': 0}
        check(PATHS['tag_index_line'].format(**kwargs), 1)


def check_status():
    return unittest.TestLoader().loadTestsFromTestCase(TestStatus)


class TestRelations(unittest.TestCase):
    """
    List of all relations and data file locations
    https://bitbucket.org/swsc/lookup/src/master/README.md

    author2commit   - done
    author2file     - done // Fail
    blob2commit     - done // 2x  Fails
    commit2blob     - done // Fail
    commit2project  - done
    commit2children - done
    file2commit     - done
    project2commit  - done
    """

    def test_author_commit(self):
        """ Test if all commits made by an author are listed in Auth2Cmt """
        proj = 'user2589_minicms'
        authors = ('Marat <valiev.m@gmail.com>',
                   'user2589 <valiev.m@gmail.com>')
        commits = {c.sha: c for c in Project(proj).commits}

        for author in authors:
            relation = {c.sha: c for c in Author(author).commits}
            for sha, c in relation.items():
                self.assertEqual(
                    c.author, author,
                    "Author2Cmt lists commit %s as authored by %s, but it is "
                    "%s" % (sha, author, c.author))

            relation = {sha for sha in relation if sha in commits}
            cs = {sha for sha, c in commits.items() if c.author == author}
            diff = relation - cs
            self.assertFalse(
                diff, "Author2Cmt lists commits %s as authored by %s, but"
                      "they are not" % (",".join(diff), author))
            diff = cs - relation
            self.assertFalse(
                diff, "Author2Cmt does not list commits %s as authored by %s,"
                      "but they are" % (",".join(diff), author))

    def test_blob_commits_change(self):
        """ Test if all commits modifying a blob are listed in Blob2Cmt """
        # this commit changes a bunch of files
        # https://github.com/user2589/minicms/commit/SHA
        commit_sha = 'ba3659e841cb145050f4a36edb760be41e639d68'
        commit = Commit(commit_sha)
        parent = commit.parents.next()

        blobs = {sha for fname, sha in commit.tree.files.items()
                 if parent.tree.files.get(fname) != sha}

        for sha in blobs:
            self.assertIn(
                commit_sha, Blob(sha).commit_shas,
                "Blob2Cmt doesn't list commit %s for blob %s,"
                "but it but it was changed in this commit" % (commit_sha, sha))

    def test_blob_commits_add(self):
        """ Test if all commits adding a blob are listed in Blob2Cmt """
        # this is the first commit in user2589_minicms
        # https://github.com/user2589/minicms/commit/SHA
        commit_sha = '1e971a073f40d74a1e72e07c682e1cba0bae159b'
        commit = Commit(commit_sha)

        blobs = set(commit.tree.files.values())

        for sha in blobs:
            self.assertIn(
                commit_sha, Blob(sha).commit_shas,
                "Blob2Cmt doesn't list commit %s for blob %s,"
                "but it but it was added in this commit" % (commit_sha, sha))

    def test_blob_commits_all(self):
        """ Test if all commit modifiying a blob are listed in blob2Cmt """
        # the first version of Readme.rst in user2589_minicms
        # it was there for only one commit, so:
        #     introduced in 2881cf0080f947beadbb7c240707de1b40af2747
        #     removed in 85787429380cb20b6a935e52c50f85f455790617
        # Feel free to change to any other blob from that project
        proj = 'user2589_minicms'
        blob_sha = 'c3bfa5467227e7188626e001652b85db57950a36'
        commits = {c.sha: c for c in Project(proj).commits}
        present = {sha: blob_sha in c.tree.files.values()
                   for sha, c in commits.items()}

        # commit is changing a blob if:
        #   all of parents have it and this commit doesn't
        #   neither of parents have it and commit does
        changed = {c.sha for sha, c in commits.items()
                   if not any(present[p] for p in c.parent_shas)
                   and present[c.sha]}

        # just in case this blob is not unique to the project,
        # e.g. a license file, filter first
        relation = {sha for sha in Blob(blob_sha).commit_shas
                    }.intersection(commits.keys())

        diff = relation - changed
        self.assertFalse(
            diff, "Blob2Cmt indicates blob %s was changed in "
                  "commits %s, but it was not" % (blob_sha, ",".join(diff)))

        diff = changed - relation
        self.assertFalse(
            diff, "Blob2Cmt indicates blob %s was NOT changed in "
                  "commits %s, but it was" % (blob_sha, ",".join(diff)))

    def test_commit_blobs(self):
        """ Test if all blobs modified in a commit are listed in c2bFull """
        for sha in ('1e971a073f40d74a1e72e07c682e1cba0bae159b',
                    'e38126dbca6572912013621d2aa9e6f7c50f36bc'):
            c = Commit(sha)
            relation = set(c.blob_shas_rel)
            blobs = set(c.blob_shas)
            diff = relation - blobs
            self.assertFalse(
                diff, "c2bFull: blobs %s are in the relation but they "
                      "are not in the commit %s" % (",".join(diff), sha))
            diff = blobs - relation
            self.assertFalse(
                diff, "c2bFull: blobs %s are in the commit %s but they are "
                      "not reported by the relation" % (",".join(diff), sha))

    def test_commit_projects(self):
        """ Test if all projects having a commit are listed in Cmt2Prj """
        for proj in ('user2589_minicms', 'user2589_karta'):
            for c in Project(proj).commits:
                self.assertIn(
                    proj, c.project_names,
                    "Cmt2Prj asserts commit %s doesn't belong to project %s, "
                    "but it does" % (c.sha, proj))

    def test_commit_children(self):
        project = 'user2589_minicms'
        commits = {c.sha: c for c in Project(project).commits}
        children = defaultdict(set)
        for sha, c in commits.items():
            for parent_sha in c.parent_shas:
                children[parent_sha].add(c.sha)

        for sha, c in commits.items():
            # filter out commits outside of the project, just in case
            relation = {sha for sha in c.child_shas if sha in commits}

            diff = relation - children[sha]
            self.assertFalse(
                diff, "Cmt2Chld lists commits %s as children of commit %s, but"
                      "they are not" % (",".join(diff), sha))

            diff = children[sha] - relation
            self.assertFalse(
                diff, "Cmt2Chld doesn't list commits %s as children of commit "
                      "%s, but they are" % (",".join(diff), sha))

    def test_file_commits(self):
        """ Test if all commits modifying a file are listed in File2Cmt """
        proj = 'user2589_minicms'
        fname = 'minicms/templatetags/minicms_tags.py'
        commits = {c.sha: c for c in Project(proj).commits}

        changed = set()
        for sha, c in commits.items():
            # this relation only follows the first parent for diff :(
            pt_files = c.parent_shas and c.parents.next().tree.files or {}
            if pt_files.get(fname) != c.tree.files.get(fname):
                changed.add(sha)

        # only consider changes in this project
        relation = {sha for sha in File(fname).commit_shas if sha in commits}

        diff = relation - changed
        self.assertFalse(
            diff, "File2Cmt indicates file %s was changed in "
                  "commits %s, but it was not" % (fname, ",".join(diff)))

        diff = changed - relation
        self.assertFalse(
            diff, "File2Cmt indicates file %s was NOT changed in "
                  "commits %s, but it was" % (fname, ",".join(diff)))

    def test_file_commits_delete(self):
        fname = "minicms/static/minicms/markdown.css"
        # deleted by this commit
        sha = '1837bfa6553a9f272c5dcc1f6259ba17357cf8ed'
        self.assertIn(sha, File(fname).commit_shas,
                      "File %s was deleted by commit %s but was not listed "
                      "as changing it." % (fname, sha))

    def test_project_commits(self):
        """ Test if all commits in a project are listed in Prj2Cmt """
        # select something long abandoned and with <100 commits
        project = 'user2589_minicms'
        relation = {c.sha for c in Project(project).commits}
        url = "https://api.github.com/repos/%s/commits?" \
              "per_page=100" % project.replace("_", "/")
        github = {c['sha'] for c in requests.get(url).json()}

        diff = relation - github
        self.assertFalse(
            diff, "Prj2Cmt lists commits %s in project %s but they're not on "
                  "github" % (",".join(diff), project))

        diff = github - relation
        self.assertFalse(
            diff, "Prj2Cmt doesn't list commits %s in project %s but they're "
                  "on github" % (",".join(diff), project))


if __name__ == "__main__":
    import oscar
    doctest.testmod(oscar)
    unittest.main()
