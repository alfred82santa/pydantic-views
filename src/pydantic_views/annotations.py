from enum import Enum, auto
from typing import Annotated, TypeAlias, TypeVar

T = TypeVar("T")


class AccessMode(Enum):
    """
    Field access mode.
    """

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


#: Read and write field annotation. Field could be read and writen always.
ReadAndWrite: TypeAlias = Annotated[T, AccessMode.READ_AND_WRITE]

#: Read only field annotation. Field could be read always but never writen.
ReadOnly = Annotated[T, AccessMode.READ_ONLY]

#: Write only field annotation. Field could be writen always but never read.
WriteOnly = Annotated[T, AccessMode.WRITE_ONLY]

#: Read only on creation field annotation. Field could be read only after creation, and never again.
ReadOnlyOnCreation = Annotated[T, AccessMode.READ_ONLY_ON_CREATION]

#: Write only on creation field annotation. Field could be writen only after creation, and never again.
WriteOnlyOnCreation = Annotated[T, AccessMode.WRITE_ONLY_ON_CREATION]

#: Hidden field annotation. Field could not be read or writen.
Hidden = Annotated[T, AccessMode.HIDDEN]
