
PYTHON = python3

.PHONY: build
build:
	$(PYTHON) setup.py build_ext --inplace

.PHONY: test
test:
	$(MAKE) build
	PYTHONPATH=. $(PYTHON) tests/unit_test.py
	PYTHONPATH=. $(PYTHON) tests/integration_test.py

.PHONY: test_local
test_local:
	source tests/local_test.env; PYTHONPATH=. $(PYTHON) tests/unit_test.py

.PHONY: clean
clean:
	rm -rf oscar.egg-info dist build docs/build ~/.pyxbld/* *.c tests/*.c *.so tests/*.so
	find -name "*.pyxbldc" -delete
	find -name "*.pyo" -delete
	find -name "*.pyc" -delete
	find -name __pycache__ -delete
