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

Please see <https://ssc-oscar.github.io/oscar.py>
for the reference.


### Deployment

Don't forget to tag the release with new tag (e.g., v1.2.1 for version 1.2.1) if the version is updated

Also 
```
git push --tags
```
By default tags are not pushed and travis build will fail (unable to find release tag)

Submit a fix: blabla or feat: blabla PR for travis to deploy it to pypi
