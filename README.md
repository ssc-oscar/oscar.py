# Python interface for OSCAR data

> [!NOTE]
> New projects may want to use the [python-woc](https://github.com/ssc-oscar/python-woc) package instead. It's fast, easy to install, and provides a more complete interface to the data.

This is a convenience library to access World of Code data
(WoC; it was referred internally as oscar while development, hence the name). 
Since everything is stored in local files it won't work unless you have access 
to one of the WoC servers.

### Installation

Normally it is preinstalled on WoC servers. To install manually, 
e.g. to a virtual environment not using system packages, just use:

```shell
python3 setup.py build_ext
python3 setup.py install --user
```

Installing from sources requires extra tools to compile (cython, 
manylinux docker image etc), but still possible. Refer to the 
[Build page](https://ssc-oscar.github.io/oscar.py) in the reference.

### Reference

Please see <https://ssc-oscar.github.io/oscar.py> for the full reference.

