
from setuptools import setup

# options reference: https://docs.python.org/2/distutils/
# see also: https://packaging.python.org/tutorials/distributing-packages/
setup(
    name="oscar",
    version="0.0.1",
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
    author='Marat',
    author_email='marat@cmu.edu',
    url='https://github.com/user2589/oscar.py',
    install_requires=[r.strip() for r in open('requirements.txt') if r.strip()]
    # TODO: run unit tests
)
