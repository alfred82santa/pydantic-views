

version:
	@${BUILDER_EXECUTABLE} version --short

version-set.%:
	@${BUILDER_EXECUTABLE} version $*
	@${MAKE} MAKEFLAGS=--no-print-directory version
