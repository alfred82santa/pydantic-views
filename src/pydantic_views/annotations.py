"""
Helpers to annotate Pydantic fields with access modes used by pydantic-views builders.

These annotations tell the builders whether a field should be exposed for read, write,
creation-only flows, or hidden entirely.
"""

from enum import Enum, auto
from typing import Annotated, ClassVar, TypeVar

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


class AccessTag:
    """Tag annotation. It is used to mark fields with custom tags that can be used in builders."""

    __slots__ = ("name",)
    __instances: ClassVar[dict[str, "AccessTag"]] = {}

    def __new__(cls, name: str) -> "AccessTag":
        if name in cls.__instances:
            return cls.__instances[name]
        instance = super().__new__(cls)
        cls.__instances[name] = instance
        return instance

    def __init__(self, name: str) -> None:
        if hasattr(self, "name"):
            return
        self.name = name

    def __repr__(self) -> str:
        return f"AccessTag({self.name})"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.name == other
        if not isinstance(other, AccessTag):  # pragma: no cover
            return NotImplemented
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __setattr__(self, name: str, value: object) -> None:
        if not hasattr(self, "name") and name == "name":
            super().__setattr__(name, value)
            return
        raise TypeError("AccessTag is immutable")
