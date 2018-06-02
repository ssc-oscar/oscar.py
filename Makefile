
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
SPHINXPROJ    = oscar
SOURCEDIR     = docs
BUILDDIR      = docs/build

.PHONY: deploy
deploy:
	scp oscar.py test.py Makefile $(SERVER):$(REMOTE_PATH)

.PHONY: test_local
test_local:
	python -m doctest oscar.py; python -m unittest test

.PHONY: test
test:
	$(MAKE) deploy
	ssh $(SERVER) 'cd $(REMOTE_PATH) && $(MAKE) test_local' 2>&1 | tee test.log

.PHONY: lint
lint:
	flake8 oscar.py

.PHONY: publish
publish:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) deploy
	python setup.py sdist bdist_wheel
	twine upload dist/*

.PHONY: clean
clean:
	rm -rf oscar.egg-info dist build docs/build

.PHONY: html
html:
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: install_dev
install_dev:
	sudo apt-get install libtokyocabinet-dev
	pip install --user flake8
	pip install --user requests  # required by tests
	pip install --user -r requirements.txt
	# documentation builder
	pip install --user  sphinx sphinx-autobuild

.PHONY: install_dev
install_dev:
	sudo apt-get install libtokyocabinet-dev
	pip install --user flake8
	pip install --user requests  # required by tests
	pip install --user -r requirements.txt
	# documentation builder
	pip install --user  sphinx sphinx-autobuild

.PHONY: travis_env
travis_env:
	sudo apt-get update && sudo apt-get install libtokyocabinet-dev
	pip install -r requirements.txt
	pip install sphinx sphinx-autobuild
