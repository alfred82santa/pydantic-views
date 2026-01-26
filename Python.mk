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
		flake8 

python-help:
	@echo "Python targets"
	@echo "-----------------------------------------------------------------------"
	@printf "%-22s %s\n" "python-help" "Show this help"
	@printf "%-22s %s\n" "requirements" "Install package requirements"
	@printf "%-22s %s\n" "beautify" "Reformat code (ruff fix + format)"
	@printf "%-22s %s\n" "lint" "Run ruff lint checks"
	@printf "%-22s %s\n" "tests" "Run tests with coverage"
	@printf "%-22s %s\n" "clean" "Remove build, cache, coverage artifacts"
	@printf "%-22s %s\n" "pull-request" "Run lint and tests"
	@printf "%-22s %s\n" "build" "Build the package"
	@printf "%-22s %s\n" "publish" "Publish to configured PyPI repo"

# Code recipes
requirements:
	${BUILDER_EXECUTABLE} sync --locked --all-extras --no-group docs

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
