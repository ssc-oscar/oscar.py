
from setuptools import setup

# options reference: https://docs.python.org/2/distutils/
# see also: https://packaging.python.org/tutorials/distributing-packages/
setup(
    # whenever you're updating the next three lines
    # please also update oscar.py
    name="oscar",
    version="1.0.0",
    author='Marat (@cmu.edu)',

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
    license="GPL v3.0",
    author_email='marat@cmu.edu',
    url='https://github.com/ssc-oscar/oscar.py',
    install_requires=['python-lzf', 'tokyocabinet'],
    test_suite='test.TestStatus'
)
