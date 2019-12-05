# Some simple testing tasks (sorry, UNIX only).

FLAGS=


flake: checkrst
	flake8 aiomonitor tests examples setup.py

test: flake
	py.test -s -v $(FLAGS) ./tests/

vtest:
	py.test -s -v $(FLAGS) ./tests/

checkrst:
	python setup.py check --restructuredtext

testloop:
	while true ; do \
        py.test -s -v $(FLAGS) ./tests/ ; \
    done

cov cover coverage: flake mypy checkrst
	py.test -s -v --cov-report term --cov-report html --cov aiomonitor ./tests
	@echo "open file://`pwd`/htmlcov/index.html"

mypy:
	if ! python --version | grep -q 'Python 3\.5\.'; then \
	    mypy aiomonitor --ignore-missing-imports --disallow-untyped-calls --disallow-incomplete-defs --strict; \
	fi

ci: flake mypy
	py.test -s -v  --cov-report term --cov aiomonitor ./tests

clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -f `find . -type f -name '@*' `
	rm -f `find . -type f -name '#*#' `
	rm -f `find . -type f -name '*.orig' `
	rm -f `find . -type f -name '*.rej' `
	rm -f .coverage
	rm -rf coverage
	rm -rf build
	rm -rf htmlcov
	rm -rf dist
	rm -rf node_modules

doc:
	make -C docs html
	@echo "open file://`pwd`/docs/_build/html/index.html"

.PHONY: all flake test vtest cov clean doc ci
