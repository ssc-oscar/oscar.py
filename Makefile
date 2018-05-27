

.PHONY: deploy
deploy:
	scp oscar.py test.py Makefile $(SERVER):$(REMOTE_PATH)

.PHONY: test_local
test_local:
	python -m doctest oscar.py; python -m unittest test

.PHONY: test
test:
	$(MAKE) deploy
	ssh $(SERVER) 'cd $(REMOTE_PATH) && $(MAKE) test_local' | tee test.log

.PHONY: lint
lint:
	flake8 oscar.py

.PHONY: publish
publish:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) deploy
	twine upload dist/*

.PHONY: clean
clean:
	rm -rf oscar.egg-info
	rm -rf dist
	rm -rf build

.PHONY: install_dev
install_dev:
	apt-get install flake8
	pip install --user requests  # required by tests
	pip install --user tokyocabinet
