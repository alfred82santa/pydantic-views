
include Config.mk

.EXPORT_ALL_VARIABLES:

help:
	@echo "Recipes for ${PACKAGE_NAME} package"
	@echo
	@echo "General options"
	@echo "-----------------------------------------------------------------------"
	@echo "help:                    This help"
	@echo
	@make --quiet python-help
	@echo
	@echo
	@make --quiet HELP_PREFIX="docs." docs.help


include Python.mk
include Version.mk


docs.%:
	@${POETRY_RUN} ${MAKE} -C docs/ HELP_PREFIX="docs." $(*)
