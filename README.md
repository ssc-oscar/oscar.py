# Python interface for OSCAR data


This is a convenience library to access OSCAR dataset. 
Since everything is stored in local files it won't work unless you have access 
to one of OSCAR servers.

**IMPORTANT:** all servers have access to each other's data through NFS, which is
subject to network delays and failures.
So, for faster access this module assumes you're working on **da4**, where all the
files are stored.

### Installation

    easy_install --user --upgrade oscar

### Reference

Please see <https://ssc-oscar.github.io/oscar.py>
for the reference.