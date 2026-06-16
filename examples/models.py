"""
Complex example models and their views, used to exercise the pydantic-views mypy plugin.

Most views use the *explicit keyword* form (``view_name=..., access_modes=(...), ...``) so that mypy
can analyse them; ``AccountLoad`` instead uses the ``preset=LoadPreset`` form, which the plugin
resolves to the same keywords. The keyword values mirror the standard builder presets:

================  ================================================================  ==========================
View              access_modes                                                      extra flags
================  ================================================================  ==========================
Create            READ_AND_WRITE, WRITE_ONLY, WRITE_ONLY_ON_CREATION                hide_default_null=True
CreateResult      READ_AND_WRITE, READ_ONLY, READ_ONLY_ON_CREATION                  include_computed_fields=True
Update            READ_AND_WRITE, WRITE_ONLY                                        all_optional=True
Load              READ_AND_WRITE, READ_ONLY                                         include_computed_fields=True
================  ================================================================  ==========================
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from annotated_types import Gt
from pydantic import BaseModel, Field, computed_field

from pydantic_views import (
    AccessMode,
    Hidden,
    LoadPreset,
    ReadOnly,
    ReadOnlyOnCreation,
    View,
    WriteOnly,
    WriteOnlyOnCreation,
)


class Address(BaseModel):
    """A nested model referenced by ``User``."""

    street: str
    number: int
    zip_code: ReadOnly[str]
    notes: WriteOnly[str | None] = None


class Role(BaseModel):
    name: str
    level: Annotated[int, AccessMode.READ_ONLY, Gt(0)]


class User(BaseModel):
    """A model that exercises every access mode plus computed and complex fields."""

    # Read/write everywhere (unmarked).
    name: str
    kind: Literal["person", "bot"] = "person"

    # Read-only: shown when loading, hidden from create/update inputs.
    id: ReadOnly[int]
    created_at: ReadOnly[datetime]

    # Server-generated secret: provided once on creation, returned in the create result.
    api_key: ReadOnlyOnCreation[str]

    # Write-only: accepted as input, never read back.
    password: WriteOnly[str]

    # Write-only on creation: set at creation time only.
    invite_code: WriteOnlyOnCreation[str | None] = None

    # Combined modes with a preserved validator.
    score: Annotated[int, AccessMode.READ_ONLY, AccessMode.WRITE_ONLY_ON_CREATION, Gt(5)] = 10

    # Never exposed.
    internal_flags: Hidden[int] = 0

    # Complex / nested fields.
    primary_address: Address
    addresses: list[Address] = Field(default_factory=list)
    roles: dict[str, Role] = Field(default_factory=dict)

    @computed_field
    def display_name(self) -> str:
        return f"{self.name} ({self.kind})"


class UserCreate(
    View[User],
    view_name="Create",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.WRITE_ONLY,
        AccessMode.WRITE_ONLY_ON_CREATION,
    ),
    hide_default_null=True,
):
    pass


class UserCreateResult(
    View[User],
    view_name="CreateResult",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.READ_ONLY,
        AccessMode.READ_ONLY_ON_CREATION,
    ),
    include_computed_fields=True,
):
    pass


class UserUpdate(
    View[User],
    view_name="Update",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.WRITE_ONLY,
    ),
    all_optional=True,
):
    pass


class UserLoad(
    View[User],
    view_name="Load",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.READ_ONLY,
    ),
    include_computed_fields=True,
):
    pass


class UserPatch(
    View[User],
    view_name="Patch",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.WRITE_ONLY,
    ),
    all_optional=True,
    all_nullable=True,
):
    """A JSON-merge-patch style view: every writable field is optional *and* nullable."""

    pass


class UserSignup(
    View[User],
    view_name="Signup",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.WRITE_ONLY,
        AccessMode.WRITE_ONLY_ON_CREATION,
    ),
    hide_default_null=True,
):
    """A create-style view that also declares its own fields, just for this view.

    These are plain Pydantic fields living only on the view (not on ``User``); the mypy plugin keeps
    them alongside the fields derived from the source model, exactly as the runtime view does.
    """

    accept_terms: bool
    referral_code: str | None = None


class Account(BaseModel):
    """A small, nesting-free model used to demonstrate view-only fields cleanly."""

    id: ReadOnly[int]
    username: str
    password: WriteOnly[str]


class AccountCreate(
    View[Account],
    view_name="Create",
    access_modes=(
        AccessMode.READ_AND_WRITE,
        AccessMode.WRITE_ONLY,
        AccessMode.WRITE_ONLY_ON_CREATION,
    ),
):
    """Create input that also carries two fields living only on the view."""

    accept_terms: bool
    captcha: str | None = None


class AccountLoad(View[Account], preset=LoadPreset):
    """Load view declared via the ``preset=`` form instead of explicit keywords.

    ``LoadPreset`` expands to ``view_name="Load"`` plus the read access modes, so the mypy plugin
    keeps exactly the readable fields (``id``, ``username``) and drops write-only ``password`` —
    identical to the explicit-keyword views above.
    """
