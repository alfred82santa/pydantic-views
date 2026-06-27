"""
Positive type-checking assertions for the pydantic-views mypy plugin.

This module must type-check **cleanly**::

    mypy --config-file examples/mypy.ini examples/check_views.py

It exercises that each view exposes exactly the fields the runtime builder produces, with the right
optionality and types — including nested models, whose fields use the generated nested views
(``AddressLoad``, ``RoleLoad``, …) just like at runtime.
"""

from __future__ import annotations

from typing import reveal_type

from .models import AccountCreate, AccountLoad, UserLoad, UserUpdate

# --- Update: every kept field is optional, write-only `password` is accepted --------------------
UserUpdate()
UserUpdate(name="new-name")
UserUpdate(name="new-name", password="secret")  # noqa: S106


# --- A view that declares its own fields: they coexist with the source-model fields -------------
# `username`/`password` come from Account; `accept_terms`/`captcha` are declared on the view itself.
account = AccountCreate(username="ada", password="secret", accept_terms=True)  # noqa: S106
reveal_type(account.username)  # N: Revealed type is "builtins.str"
reveal_type(account.accept_terms)  # view-only field -> bool
reveal_type(account.captcha)  # view-only optional field -> str | None


# --- preset= form: `AccountLoad` uses `preset=LoadPreset` instead of explicit keywords ---------
# The plugin resolves the preset to the same keywords, so the readable fields are kept...
account_loaded = AccountLoad.model_validate({})
reveal_type(account_loaded.id)  # N: Revealed type is "builtins.int"
reveal_type(account_loaded.username)  # N: Revealed type is "builtins.str"


# --- Load: build the realistic way (nested views are generated, not importable) -----------------
loaded = UserLoad.model_validate({})

reveal_type(loaded.id)  # N: Revealed type is "builtins.int"
reveal_type(loaded.display_name)  # computed field present on read views -> str

# Nested model fields use the generated nested views, recursively and through containers.
reveal_type(loaded.primary_address)  # N: "examples.models.AddressLoad"
reveal_type(loaded.primary_address.zip_code)  # read-only nested field -> str
reveal_type(loaded.addresses)  # N: "builtins.list[examples.models.AddressLoad]"
reveal_type(loaded.roles)  # N: "builtins.dict[builtins.str, examples.models.RoleLoad]"
