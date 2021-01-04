# Changelog

<!--next-version-placeholder-->

## v2.0.5 (2021-01-04)
### Fix
* Prevent semantic release from ruining manylinux builds ([`0cf11ec`](https://github.com/ssc-oscar/oscar.py/commit/0cf11ecf8e07928d62eebfda883997c64b349481))

## v2.0.4 (2021-01-04)
### Fix
* Apparently only Python2 needs *mu tag, Python3 should use *m one ([`3754db1`](https://github.com/ssc-oscar/oscar.py/commit/3754db15c043a5e4f181b6e788ba5259c7b1fbc2))
* Use wide unicode tags for wheels (cp27mu and cp36mu, as most Linux distributions use those) ([`afc609b`](https://github.com/ssc-oscar/oscar.py/commit/afc609b98012196ce7d7093a5a94b777642e83cf))

## v2.0.3 (2021-01-03)
### Fix
* Yet another ci debugging commit ([`4aa52f3`](https://github.com/ssc-oscar/oscar.py/commit/4aa52f36352494630870596ef4f1095064baf174))
* Remove non-manylinux binaries to fix release uploads ([`79ed5ee`](https://github.com/ssc-oscar/oscar.py/commit/79ed5ee28639e90ab82bb3865f578c3196b0a188))

### Documentation
* Readability fixes ([`7ee4f49`](https://github.com/ssc-oscar/oscar.py/commit/7ee4f490f8950f8fde4dd29f666daad283428e55))

## v2.0.2 (2021-01-03)
### Fix
* Prevent semantic-release from deleting built packages ([`ba7f468`](https://github.com/ssc-oscar/oscar.py/commit/ba7f46839213f88cf080f851c459c2d9c0b636bf))

## v2.0.1 (2021-01-03)
### Fix
* Version bump ([`6eef010`](https://github.com/ssc-oscar/oscar.py/commit/6eef010bae395f6c0a02901ec4998d142ff11d7f))

## v2.0.0 (2021-01-03)
### Feature
* Include statically linked libtokyocabinet support ([`97db8b4`](https://github.com/ssc-oscar/oscar.py/commit/97db8b4164e21ff299daf4aacffabd06d7a017ea))
* Py2 compatibility ([`cdd5af3`](https://github.com/ssc-oscar/oscar.py/commit/cdd5af3f0611f2aaffdafb9b56d682a080cb875b))
* Python3 support ([`941f123`](https://github.com/ssc-oscar/oscar.py/commit/941f123bd599201270c832ecd1ebd668968c4969))
* Automatic version and key length detection ([`899a74f`](https://github.com/ssc-oscar/oscar.py/commit/899a74ffb27343e58395abab9feb1d199d30ea50))
* Issue warnings on hosts other than da4 ([`c0ba613`](https://github.com/ssc-oscar/oscar.py/commit/c0ba613e589617702b9f8f666a150581120d0f02))

### Fix
* Update Py version requirements in setup.py ([`2e3a912`](https://github.com/ssc-oscar/oscar.py/commit/2e3a912daf20f3d7c30295e628c2f5690932e38a))
* Issues revealed by integration test ([`d8a4713`](https://github.com/ssc-oscar/oscar.py/commit/d8a471326a005da5e441f0dd0899e48286d542c2))
* Numerous regressions because of Py3 compatibility ([`c01722f`](https://github.com/ssc-oscar/oscar.py/commit/c01722f3b21aa272d9a0faac055bcd54107b2e95))
* Make `Commit` attributes Py3 compatible ([`f16f80c`](https://github.com/ssc-oscar/oscar.py/commit/f16f80c0b2fb155f068bde3c2df7f9e09fb8fa5e))
* Numerous Py2/3 compatibility issues ([`408cddc`](https://github.com/ssc-oscar/oscar.py/commit/408cddc25f9a177cd4ed0cadc31c448121c67e11))
* Lint checker warnings ([`9e04ed5`](https://github.com/ssc-oscar/oscar.py/commit/9e04ed5a312017554f39a3887ec534d724ed7cbd))
* Restore new table names for commits timeline table after merge conflict) ([`feb6e98`](https://github.com/ssc-oscar/oscar.py/commit/feb6e98a64746dbd6c77d349eb2bc766e03db38b))
* Cleanup after undergrads ([`2056d38`](https://github.com/ssc-oscar/oscar.py/commit/2056d38697d46c46e2e97bb4ac9a84d024e653d3))

### Breaking
* make trees non-recursive by default ([`ab5400a`](https://github.com/ssc-oscar/oscar.py/commit/ab5400a0624dbd7a0dddc8ae5d5f64ec6a223968))
* Python3 support ([`941f123`](https://github.com/ssc-oscar/oscar.py/commit/941f123bd599201270c832ecd1ebd668968c4969))

### Documentation
* Update contribution guide ([`cfd291c`](https://github.com/ssc-oscar/oscar.py/commit/cfd291c577cd416eeab19b213679fa5faef9382c))
* Minor improvements ([`7678165`](https://github.com/ssc-oscar/oscar.py/commit/7678165a11f170974b88d89a5f104e5a175c855b))
* Write contribution guideline ([`204b22f`](https://github.com/ssc-oscar/oscar.py/commit/204b22f87a6fbfe1d78a372f10444e1203cff999))
* Make docstring convention consistent (Google style) ([`c707f52`](https://github.com/ssc-oscar/oscar.py/commit/c707f52c060908f90b86b0f74881797b7a5a9262))
