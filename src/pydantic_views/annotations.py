from enum import Enum, auto
from typing import Annotated, TypeVar

T = TypeVar("T")


class AccessMode(Enum):
    READ_AND_WRITE = auto()
    READ_ONLY = auto()
    WRITE_ONLY = auto()
    READ_ONLY_ON_CREATION = auto()
    WRITE_ONLY_ON_CREATION = auto()
    HIDDEN = auto()


class FieldAccess:
    __slots__ = ("_mode",)

    def __init__(self, mode: AccessMode = AccessMode.READ_AND_WRITE):
        self._mode = mode

    @property
    def mode(self) -> AccessMode:
        return self._mode


RW = FieldAccess(AccessMode.READ_AND_WRITE)
RO = FieldAccess(AccessMode.READ_ONLY)
WO = FieldAccess(AccessMode.WRITE_ONLY)
ROOC = FieldAccess(AccessMode.READ_ONLY_ON_CREATION)
WOOC = FieldAccess(AccessMode.WRITE_ONLY_ON_CREATION)
HIDDEN = FieldAccess(AccessMode.HIDDEN)


ReadAndWrite = Annotated[T, RW]
ReadOnly = Annotated[T, RO]
WriteOnly = Annotated[T, WO]
ReadOnlyOnCreation = Annotated[T, ROOC]
WriteOnlyOnCreation = Annotated[T, WOOC]
Hidden = Annotated[T, HIDDEN]
