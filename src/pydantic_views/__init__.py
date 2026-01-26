"""
Public package surface for pydantic-views.

This module re-exports the main classes, builders, and annotations so users can import
from :mod:`pydantic_views` directly.
"""

from .annotations import (
    AccessMode,
    Hidden,
    ReadAndWrite,
    ReadOnly,
    ReadOnlyOnCreation,
    WriteOnly,
    WriteOnlyOnCreation,
)
from .builder import (
    Builder,
    BuilderCreate,
    BuilderCreateResult,
    BuilderLoad,
    BuilderUpdate,
    ensure_model_views,
)
from .manager import Manager
from .view import RootView, View

__all__ = [
    "AccessMode",
    "ReadOnly",
    "ReadAndWrite",
    "ReadOnlyOnCreation",
    "WriteOnly",
    "WriteOnlyOnCreation",
    "Hidden",
    "Builder",
    "BuilderCreate",
    "BuilderCreateResult",
    "BuilderUpdate",
    "BuilderLoad",
    "ensure_model_views",
    "Manager",
    "View",
    "RootView",
]
