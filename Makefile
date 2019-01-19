

.PHONY: deploy
deploy:
	scp oscar.py test.py setup.py Makefile $(SERVER):$(REMOTE_PATH)

.PHONY: status
status:
	python -m unittest test.TestStatus

.PHONY: test_local
test_local:
	python -m doctest $(TESTROOT)
	python -m unittest test

.PHONY: test
test:
	$(MAKE) deploy
	ssh $(SERVER) 'cd $(REMOTE_PATH) && $(MAKE) test_local' 2>&1 | tee test.log

.PHONY: publish
publish:
	test $$(git config user.name) || git config user.name "semantic-release (via TravisCI)"
	test $$(git config user.email) || git config user.email "semantic-release@travis"
	semantic-release publish

.PHONY: clean
clean:
	rm -rf $(PACKAGE).egg-info dist build docs/build
	find -name "*.pyo" -delete
	find -name "*.pyc" -delete
	find -name __pycache__ -delete

.PHONY: html
html:
	sphinx-build -M html "docs" "docs/build"

.PHONY: install
install:
	sudo apt-get update && sudo apt-get install libtokyocabinet-dev
	pip install -r requirements.txt

.PHONY: install_dev
install_dev:
	$(MAKE) install
	pip install sphinx sphinx-autobuild
	pip install requests  # required by tests
	# documentation builder
