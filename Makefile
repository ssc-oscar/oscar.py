SHELL := /bin/bash

.PHONY: build
build:
	python setup.py build_ext --inplace

# test ground for github action, requires building local image from
# https://github.com/RalfG/python-wheels-manylinux-build
.PHONY: build_manylinux
build_manylinux:
	docker run --rm -e PLAT=manylinux2010_x86_64 -v `pwd`:/github/workspace/ manylinux2010 "cp27-cp27m cp36-cp36m" "cython setuptools>=18.0" "bzip2-devel zlib-devel"

.PHONY: test
test:
	$(MAKE) build
	PYTHONPATH=. python tests/unit_test.py
	PYTHONPATH=. python tests/integration_test.py

.PHONY: test_local
test_local:
	bash -c "source tests/local_test.env; PYTHONPATH=. python tests/unit_test.py"

.PHONY: clean
clean:
	rm -rf oscar.egg-info dist build docs/build ~/.pyxbld/* *.c tests/*.c *.so tests/*.so
	find -name "*.pyxbldc" -delete
	find -name "*.pyo" -delete
	find -name "*.pyc" -delete
	find -name __pycache__ -delete
