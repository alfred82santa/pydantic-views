"""
Helpers to annotate Pydantic fields with access modes used by pydantic-views builders.

These annotations tell the builders whether a field should be exposed for read, write,
creation-only flows, or hidden entirely.
"""

from enum import Enum, auto
from typing import Annotated, TypeVar

T = TypeVar("T")


class AccessMode(Enum):
    """Access rules that determine if and when a field is exposed in generated views."""

    #: Read and write mark.
    READ_AND_WRITE = auto()

    #: Read only mark.
    READ_ONLY = auto()

    #: Write only mark.
    WRITE_ONLY = auto()

    #: Read only on creation mark.
    READ_ONLY_ON_CREATION = auto()

    #: Write only on creation mark.
    WRITE_ONLY_ON_CREATION = auto()

    #: Hidden mark.
    HIDDEN = auto()


#: Read and write field annotation. Field could be read and written always.
ReadAndWrite = Annotated[T, AccessMode.READ_AND_WRITE]

#: Read only field annotation. Field could be read always but never written.
ReadOnly = Annotated[T, AccessMode.READ_ONLY]

#: Write only field annotation. Field could be written always but never read.
WriteOnly = Annotated[T, AccessMode.WRITE_ONLY]

#: Read only on creation field annotation. Field could be read only after creation, and never again.
ReadOnlyOnCreation = Annotated[T, AccessMode.READ_ONLY_ON_CREATION]

#: Write only on creation field annotation. Field could be written only after creation, and never again.
WriteOnlyOnCreation = Annotated[T, AccessMode.WRITE_ONLY_ON_CREATION]

#: Hidden field annotation. Field could not be read or written.
Hidden = Annotated[T, AccessMode.HIDDEN]
