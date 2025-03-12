# Author: Alfred

PACKAGE_COVERAGE=$(PACKAGE_DIR)

ISORT_PARAMS?=

# Minimum coverage
COVER_MIN_PERCENTAGE=95

PYPI_REPO?=
PYPI_REPO_USERNAME?=
PYPI_REPO_PASSWORD?=

ifneq (${PYPI_REPO},)
_PYPI_PUBLISH_ARGS=--repository=${PYPI_REPO}
else
_PYPI_PUBLISH_ARGS=
endif

POETRY_EXECUTABLE?=poetry
POETRY_RUN?=${POETRY_EXECUTABLE} run


# Recipes ************************************************************************************
.PHONY: python-help requirements black beautify-imports beautify lint tests clean pull-request  publish  \
		flake autopep sort-imports

python-help:
	@echo "Python options"
	@echo "-----------------------------------------------------------------------"
	@echo "python-help:             This help"
	@echo "requirements:            Install package requirements"
	@echo "black:                   Reformat code using Black"
	@echo "beautify-imports:        Reformat and sort imports"
	@echo "beautify:                Reformat code (beautify-imports + black)"
	@echo "lint:                    Check code format"
	@echo "tests:                   Run tests with coverage"
	@echo "clean:                   Clean compiled files"
	@echo "pull-request:            Helper to run when a pull request is made"
	@echo "sort-imports:            Sort imports"
	@echo "build-doc-html:          Build documentation HTML files"

# Code recipes
requirements:
	${POETRY_EXECUTABLE} install --no-interaction --no-ansi --all-extras --without=docs

black:
	${POETRY_RUN} ruff format .

beautify-imports:
	${POETRY_RUN} autoflake --remove-all-unused-imports -j 4 --in-place --remove-duplicate-keys -r ${PACKAGE_DIR} ${PACKAGE_TESTS_DIR}
	${POETRY_RUN} isort ${ISORT_PARAMS} ${PACKAGE_DIR}
	${POETRY_RUN} isort ${ISORT_PARAMS} ${PACKAGE_TESTS_DIR}
	${POETRY_RUN} isort ${ISORT_PARAMS} ${PACKAGE_DOCS_SRC_DIR}
	${POETRY_RUN} absolufy-imports --never $(shell find ${PACKAGE_DIR}  -not -path "*__pycache__*" | grep .py$)
	${POETRY_RUN} absolufy-imports --never $(shell find ${PACKAGE_TESTS_DIR}  -not -path "*__pycache__*" | grep .py$)

beautify: beautify-imports black

lint:
	@echo "Running flake8 tests..."
	${POETRY_RUN} ruff check .
	${POETRY_RUN} flake8 .
	${POETRY_RUN} isort -c ${ISORT_PARAMS} .

tests:
	@echo "Running tests..."
	@# echo "NO TESTS"
	@${POETRY_RUN} pytest -v -s --cov-report term-missing --cov-report xml --cov-fail-under=${COVER_MIN_PERCENTAGE} --cov=${PACKAGE_COVERAGE} --exitfirst

clean:
	@echo "Cleaning compiled files..."
	find . | grep -E "(__pycache__|\.pyc|\.pyo)$ " | xargs rm -rf
	@echo "Cleaning distribution files..."
	rm -rf dist
	@echo "Cleaning build files..."
	rm -rf build
	@echo "Cleaning egg info files..."
	rm -rf ${PACKAGE_NAME}.egg-info
	@echo "Cleaning coverage files..."
	rm -f .coverage


pull-request: lint tests

build:
	${POETRY_EXECUTABLE} build

publish: #build
	${POETRY_EXECUTABLE} publish ${_PYPI_PUBLISH_ARGS} --username="${PYPI_REPO_USERNAME}" --password="${PYPI_REPO_PASSWORD}"
