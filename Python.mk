# Author: Alfred

PACKAGE_COVERAGE=$(PACKAGE_DIR)

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

BUILDER_EXECUTABLE?=uv
BUILDER_RUN?=${BUILDER_EXECUTABLE} run


# Recipes ************************************************************************************
.PHONY: python-help requirements beautify lint tests clean pull-request publish  \
		flake sort-imports

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
	${BUILDER_EXECUTABLE} install --no-interaction --no-ansi --all-extras --without=docs

beautify:
	${BUILDER_RUN} ruff check --fix .
	${BUILDER_RUN} ruff format .

lint:
	@echo "Running ruff tests..."
	${BUILDER_RUN} ruff check .

tests:
	@echo "Running tests..."
	@${BUILDER_RUN} pytest -v -s --cov-report term-missing --cov-report xml --cov-fail-under=${COVER_MIN_PERCENTAGE} --cov=${PACKAGE_COVERAGE} --exitfirst

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
	${BUILDER_EXECUTABLE} build

publish: #build
	${BUILDER_EXECUTABLE} publish ${_PYPI_PUBLISH_ARGS} --username="${PYPI_REPO_USERNAME}" --password="${PYPI_REPO_PASSWORD}"
