
.PHONY: build
build:
	python3 setup.py build_ext --inplace


.PHONY: test
test:
	$(MAKE) build
	PYTHONPATH=. python3 tests/unit_test.py
	PYTHONPATH=. python3 tests/integration_test.py

.PHONY: clean
clean:
	rm -rf $(PACKAGE).egg-info dist build docs/build
	find -name "*.pyo" -delete
	find -name "*.pyc" -delete
	find -name __pycache__ -delete
