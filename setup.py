
import re
from setuptools import setup

head = open('oscar.py').read(2048)
pattern = r"""__%s__\s*=\s*['"]([^'"]*)['"]"""
kwargs = {keyword: re.search(pattern % keyword, head).group(1)
          for keyword in ('version', 'author', 'license')}

# options reference: https://docs.python.org/2/distutils/
# see also: https://packaging.python.org/tutorials/distributing-packages/
setup(
    name="oscar",
    description="A Python interface to OSCAR data",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    classifiers=[  # full list: https://pypi.org/classifiers/
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 2.7',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: POSIX :: Linux',
        'Topic :: Scientific/Engineering'
    ],
    python_requires='~=2.7',
    py_modules=['oscar'],
    author_email='marat@cmu.edu',
    url='https://github.com/ssc-oscar/oscar.py',
    install_requires=['python-lzf', 'tokyocabinet', 'pygit2', 'fnvhash'],
    test_suite='test.TestStatus',
    **kwargs
)
