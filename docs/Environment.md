
Some quick notes on environment setup

## Import paths:

To install executables locally (e.g. pip), add to ~/.bashrc:

    if [ -d "$HOME/.local/bin" ] ; then
        export PATH=~/.local/bin:$PATH
    fi

If you want to install Perl modules locally, add to the same file:

    if [ -d "$HOME/.local/lib64/perl5" ] ; then
        export PERL5LIB=$HOME/.local/lib64/perl5
    fi


## Python

Install development version of the package:

Install pip:

    easy_install --user pip
    pip install --upgrade pip

Clone the repo and install dependencies:

    git clone git@github.com:user2589/oscar.py.git
    cd oscar.py
    pip install --user --upgrade -r requirements.txt

Note that OSCAR servers are running RHEL and have different big/little endian than
most conventional Linux distributions.
Pakcages compiled on Debian-based systems are known not to work with OSCAR
Tokyo Cabinet files.

## Perl

Package Tokyocabinet is not on CPAN, so install manually:

    # mkdir src && cd src
    wget http://fallabs.com/tokyocabinet/tokyocabinet-1.4.48.tar.gz
    tar -zxvf tokyocabinet-1.4.48.tar.gz
    cd tokyocabinet-1.4.48
    perl Makefile.PL PREFIX=~/.local
    make
    # make test
    make install
    # install CPAN
    # cpan install Compress::LZF
