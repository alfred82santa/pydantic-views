

version:
	@poetry version --short

version-set.%:
	@poetry version $*
	@${MAKE} MAKEFLAGS=--no-print-directory version
