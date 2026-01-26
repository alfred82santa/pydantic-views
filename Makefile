
include Config.mk

.EXPORT_ALL_VARIABLES:

.PHONY: help python-help

help:
	@echo "Targets for ${PACKAGE_NAME} package"
	@echo "-----------------------------------------------------------------------"
	@printf "%-22s %s\n" "help" "Show this help"
	@echo
	@make --quiet python-help
	@echo
	@make --quiet version-help
	@echo
	@make --quiet HELP_PREFIX="docs." docs.help


include Python.mk
include Version.mk


docs.%:
	@${BUILDER_RUN} ${MAKE} -C docs/ HELP_PREFIX="docs." $(*)
