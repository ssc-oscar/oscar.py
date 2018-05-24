
from oscar import *

import unittest


class TestRelations(unittest.TestCase):
    """
    List of all relations and data file locations
    https://bitbucket.org/swsc/lookup/src/master/README.md
    author2commit
    author2file
    blob2commit - done
    commit2blob
    commit2project
    file2commit - done
    project2commit
    """

    def test_author_commit(self):
        pass

    def test_blob_commits_delete(self):
        """ Test blob2Cmt
        Test if a commit is contained in relations of all blobs it deleted
        """
        # this commit deletes MANIFEST.in
        # https://github.com/user2589/minicms/commit/SHA
        # Blob('7e2a34e2ec9bfdccfa01fff7762592d9458866eb')
        commit_sha = '2881cf0080f947beadbb7c240707de1b40af2747'
        commit = Commit(commit_sha)
        parent = commit.parents.next()

        # files that are in parent but not in commit
        # These are not present in blob.commits by some reason
        blobs = {parent.tree.files[fname] for fname in
                 set(parent.tree.files.keys()) - set(commit.tree.files.keys())}

        for sha in blobs:
            self.assertIn(
                commit_sha, Blob(sha).commit_shas,
                "Commit %s has blob %s deleted,"
                "but it is not listed in blob.commits" % (commit_sha, sha))

    def test_blob_commits_change(self):
        """ Test blob2Cmt
        Test if a commit is contained in relations of all blobs it changed
        """
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
                "Commit %s has blob %s changed,"
                "but it is not listed in blob.commits" % (commit_sha, sha))

    def test_blob_commits_add(self):
        """ Test blob2Cmt
        Test if a commit is contained in relations of all blobs it added
        """
        # this is the first commit in user2589_minicms
        # https://github.com/user2589/minicms/commit/SHA
        commit_sha = '1e971a073f40d74a1e72e07c682e1cba0bae159b'
        commit = Commit(commit_sha)

        blobs = set(commit.tree.files.values())

        for sha in blobs:
            self.assertIn(
                commit_sha, Blob(sha).commit_shas,
                "Commit %s has blob %s added for the first time, "
                "but it is not listed in blob.commits" % (commit_sha, sha))

    def test_blob_commits_all(self):
        """ Test blob2Cmt
        Test if all commit where a blob was modified are contained
        in the relation
        """
        # the first version of Readme.rst in user2589_minicms
        # it was there for only one commit, so:
        #     introduced in 2881cf0080f947beadbb7c240707de1b40af2747
        #     removed in 85787429380cb20b6a935e52c50f85f455790617
        # Feel free to change to any other blob from that project
        proj = 'user2589_minicms'
        blob_sha = 'c3bfa5467227e7188626e001652b85db57950a36'
        commits = {c.sha: c for c in
                   Commit.by_project(proj)}
        present = {sha: blob_sha in c.tree.files.values()
                   for sha, c in commits.items()}

        # commit is changing a blob if:
        #   all of parents have it and this commit doesn't
        #   neither of parents have it and commit does
        changed = {c.sha for sha, c in commits.items()
                   if ((c.parent_shas
                        and all(present[p] for p in c.parent_shas)
                        and not present[c.sha])
                       or (not any(present[p] for p in c.parent_shas)
                           and present[c.sha])
                       )}

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

    def test_file_commits(self):
        proj = 'user2589_minicms'
        fname = 'minicms/templatetags/minicms_tags.py'
        commits = {c.sha: c for c in
                   Commit.by_project(proj)}

        changed = set()
        for sha, c in commits.items():
            ptrees = [p.tree.files for p in c.parents] or [{}]
            if all(pt.get(fname) != c.tree.files.get(fname) for pt in ptrees):
                changed.add(sha)

        # only consider changes in this project
        relation = {c.sha for c in Commit.by_file(fname) if c.sha in commits}

        diff = relation - changed
        self.assertFalse(
            diff, "File2Cmt indicates file %s was changed in "
                  "commits %s, but it was not" % (fname, ",".join(diff)))

        diff = changed - relation
        self.assertFalse(
            diff, "File2Cmt indicates file %s was NOT changed in "
                  "commits %s, but it was" % (fname, ",".join(diff)))
