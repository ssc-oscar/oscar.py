# Python interface for OSCAR data


This is a convenience library to access OSCAR dataset. 
Since everything is stored in local files it won't work unless you have access 
to one of OSCAR servers.

**IMPORTANT:** all servers have access to each other's data through NFS, which is
subject to network delays and failures.
So, for faster access this module assumes you're working on **da4**, where all the
files are stored.

### Installation

    # pip is not available on OSCAR servers
    easy_install --user --upgrade oscar

### Reference

Please see <https://ssc-oscar.github.io/oscar.py> for the reference.


### How to contribute - read carefully

`master` is for releases only. Development happens on feature branches,
which stem from `dev` branch and merge back. Once in a while `dev` is merged
to master, producing a new release. This rule is mostly because of the server
layout preventing us from running unit tests automatically.

We use [conventional commits](https://www.conventionalcommits.org) message
convention. This means that you MUST prepend commit messages with one of:
- **fix:** in case the change fixes a problem without changing any interfaces.
    Example commit message: `fix: missing clickhouse-driver dependency (closes #123)`.
- **feat:** the change implements a new feature, without affecting existing
    interfaces. Example: `feat: implement author timeline`.
- **chore:** the change does not affect functionality, e.g. PEP8 fixes.
    E.g.: `chore: PEP8 fixes`
- **docs:**: similar to `chore:` but explicitly related to documentation.
    E.g.: `docs: add timeline usage examples`
- **refactor:** similar to `chore:`

In case of breaking changes (i.e. if any interfaces were changed, breaking 
backward compatibility), commit message should contain **BREAKING CHANGE**
in the footer.

Commit messages will be used to automatically bump version. `fix`, `chore`, `docs` 
will produce patch versions, `feat` will result in a minor version bump, and in
case of breaking changes the major version will be incremented.
As a consequence, **you must never change version number manually**.

Not following these procedures might take your pull request extra time to
review and in some cases will require rewriting the commit history.