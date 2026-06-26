"""
Negative type-checking assertions for the pydantic-views mypy plugin.

Every ``# type: ignore[...]`` below marks a line that the plugin MUST flag. With
``warn_unused_ignores = true`` (see ``mypy.ini``), if the plugin ever stops producing one of these
errors the corresponding ignore becomes "unused" and mypy fails — so this file fails loudly when the
field filtering regresses.

    mypy --config-file examples/mypy.ini examples/check_errors.py   # must report: Success
"""

from __future__ import annotations

from .models import AccountCreate, AccountLoad, UserLoad, UserUpdate

# `id` is read-only -> not a writable field, so the (all-optional) Update view rejects it.
UserUpdate(id=1)  # type: ignore[call-arg]

# `internal_flags` is Hidden -> present in no view at all.
UserUpdate(internal_flags=1)  # type: ignore[call-arg]

# `password` is write-only -> absent as a readable attribute on the Load view.
loaded = UserLoad.model_validate({})
_ = loaded.password  # type: ignore[attr-defined]

# The `preset=` form filters identically: write-only `password` is absent on the preset-built view.
account_loaded = AccountLoad.model_validate({})
_ = account_loaded.password  # type: ignore[attr-defined]

# View-only fields are real fields: omitting the required `accept_terms` is an error...
AccountCreate(username="ada", password="secret")  # type: ignore[call-arg]  # noqa: S106
# ...and a read-only source field (`id`) is still excluded from the view.
AccountCreate(username="ada", password="secret", accept_terms=True, id=1)  # type: ignore[call-arg]  # noqa: S106
