

version-help:
	@echo "Versioning targets"
	@echo "-----------------------------------------------------------------------"
	@printf "%-22s %s\n" "version-help" "Show this help"
	@printf "%-22s %s\n" "version" "Show current version"
	@printf "%-22s %s\n" "version-set.<version>" "Set new version and show it"

version:
	@${BUILDER_EXECUTABLE} version --short

version-set.%:
	@${BUILDER_EXECUTABLE} version $*
	@${MAKE} MAKEFLAGS=--no-print-directory version
