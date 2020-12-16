
PYTHON = python3

.PHONY: build
build:
	$(PYTHON) setup.py build_ext --inplace


.PHONY: test
test:
	$(MAKE) build
	PYTHONPATH=. $(PYTHON) tests/unit_test.py
	PYTHONPATH=. $(PYTHON) tests/integration_test.py

.PHONY: clean
clean:
	rm -rf $(PACKAGE).egg-info dist build docs/build
	find -name "*.pyxbldc" -delete
	find -name "*.so" -delete
	find -name "*.pyo" -delete
	find -name "*.pyc" -delete
	find -name __pycache__ -delete
