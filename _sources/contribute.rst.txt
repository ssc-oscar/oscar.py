
How to contribute
=================


`master` is for releases only. Development happens on feature branches,
which stem from `dev` branch and merge back. Once in a while `dev` is merged
to master, producing a new release. This rule is mostly because of the server
layout preventing us from running unit tests automatically.

We use `conventional commits <https://www.conventionalcommits.org>`_ message
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
in the footer, or have an exclamation mark after prefix, e.g.:

    `feat!: drop support for deprectated parameters`

Commit messages will be used to automatically bump version. `fix`, `chore`, `docs`
will produce patch versions, `feat` will result in a minor version bump, and in
case of breaking changes the major version will be incremented.
As a consequence, **you must never change version number manually**.

Not following these procedures might take your pull request extra time to
review and in some cases will require rewriting the commit history.