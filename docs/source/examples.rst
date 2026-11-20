==================
Practical examples
==================

Each workflow below is self-contained. The assertions are executed by the documentation's
Sphinx doctest build, so the examples describe observable behavior rather than pseudocode.
Use ``model_validate()`` for incoming dictionaries and ``view_build_from()`` to project
existing model instances.

Each example also shows the view declarations emitted by
``python -m pydantic_views.stubgen``. These ``.pyi`` excerpts omit the source-model
definitions and other module symbols to focus on the generated contract. Field annotations
describe the available values; ``= ...`` in a constructor means the argument may be omitted.
The stubs describe types, while the runtime models retain field validation and metadata.

Create a resource and return a safe response
============================================

Keep server-managed fields out of creation input, accept a password without returning it,
and expose a one-time credential only in the creation result.

.. testcode:: lifecycle

   from pydantic import BaseModel, Field, computed_field
   from pydantic_views import (
       CreatePreset,
       CreateResultPreset,
       LoadPreset,
       ReadOnly,
       ReadOnlyOnCreation,
       View,
       WriteOnly,
       WriteOnlyOnCreation,
   )

   class User(BaseModel):
       id: ReadOnly[int]
       name: str = Field(min_length=1)
       password: WriteOnly[str]
       api_key: ReadOnlyOnCreation[str]
       invitation: WriteOnlyOnCreation[str | None] = None

       @computed_field
       @property
       def display_name(self) -> str:
           return f"{self.name} (#{self.id})"

   class UserCreate(View[User], preset=CreatePreset):
       pass

   class UserCreateResult(View[User], preset=CreateResultPreset):
       pass

   class UserLoad(View[User], preset=LoadPreset):
       pass

   incoming = UserCreate.model_validate({"name": "Ada", "password": "example-only"})
   assert set(UserCreate.model_fields) == {"name", "password", "invitation"}

   # A service would hash the password and generate the ID and credential.
   stored = User(id=1, name=incoming.name, password="stored-hash", api_key="issued-once")
   created = UserCreateResult.view_build_from(stored)
   loaded = UserLoad.view_build_from(stored)

   assert created.api_key == "issued-once"
   assert created.display_name == "Ada (#1)"
   assert loaded.model_dump() == {"id": 1, "name": "Ada", "display_name": "Ada (#1)"}
   assert "password" not in created.model_dump()
   assert "api_key" not in loaded.model_dump()

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_views import View

   class UserCreate(View[User]):
       name: str
       password: str
       invitation: str

       def __init__(self, *, name: str, password: str, invitation: str = ...) -> None: ...

   class UserCreateResult(View[User]):
       id: int
       name: str
       api_key: str
       display_name: str

       def __init__(self, *, id: int, name: str, api_key: str, display_name: str) -> None: ...

   class UserLoad(View[User]):
       id: int
       name: str
       display_name: str

       def __init__(self, *, id: int, name: str, display_name: str) -> None: ...

Views define which fields belong to each schema. For input that must reject unknown keys
rather than ignore them, set Pydantic's ``model_config = {"extra": "forbid"}`` on the
source model. Its configuration is carried into the generated views.

Apply a nested partial update
=============================

Update only the supplied nested values. Dictionaries merge by key, while sequences are
replaced. Pass a deep copy to retain an unchanged original instance.

.. testcode:: nested-update

   from pydantic import BaseModel
   from pydantic_views import ReadOnly, UpdatePreset, View

   class Address(BaseModel):
       street: str
       city: str
       postal_code: ReadOnly[str]

   class Profile(BaseModel):
       id: ReadOnly[int]
       address: Address
       preferences: dict[str, str]
       labels: list[str]

   class ProfileUpdate(View[Profile], preset=UpdatePreset):
       pass

   original = Profile(
       id=1,
       address=Address(street="Main Street", city="London", postal_code="E1"),
       preferences={"theme": "light", "language": "en"},
       labels=["customer", "newsletter"],
   )
   changes = ProfileUpdate.model_validate(
       {"address": {"city": "Oxford"}, "preferences": {"theme": "dark"}, "labels": ["customer"]}
   )
   updated = changes.view_apply_to(original.model_copy(deep=True))

   assert updated.address.city == "Oxford"
   assert updated.address.street == "Main Street"
   assert updated.address.postal_code == "E1"
   assert updated.preferences == {"theme": "dark", "language": "en"}
   assert updated.labels == ["customer"]
   assert original.address.city == "London"

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_core import MISSING
   from pydantic_views import View

   class AddressUpdate(View[Address]):
       street: str | MISSING
       city: str | MISSING

       def __init__(self, *, street: str | MISSING = ..., city: str | MISSING = ...) -> None: ...

   class ProfileUpdate(View[Profile]):
       address: AddressUpdate | MISSING
       preferences: dict[str, str] | MISSING
       labels: list[str] | MISSING

       def __init__(
           self,
           *,
           address: AddressUpdate | MISSING = ...,
           preferences: dict[str, str] | MISSING = ...,
           labels: list[str] | MISSING = ...,
       ) -> None: ...

Optional does not mean nullable
===============================

An omitted field means "leave it alone". An explicit ``None`` means "set it to null" and
is accepted only when the field's type permits it.

.. testcode:: omission

   from pydantic import BaseModel, ValidationError
   from pydantic_core import MISSING
   from pydantic_views import UpdatePreset, View

   class Preferences(BaseModel):
       theme: str = "light"
       nickname: str | None = None

   class PreferencesUpdate(View[Preferences], preset=UpdatePreset):
       pass

   empty = PreferencesUpdate.model_validate({})
   clear = PreferencesUpdate.model_validate({"nickname": None})

   assert empty.theme is MISSING
   assert empty.model_fields_set == set()
   assert empty.model_dump() == {}
   assert clear.model_fields_set == {"nickname"}
   assert clear.model_dump() == {"nickname": None}

   try:
       PreferencesUpdate.model_validate({"theme": None})
   except ValidationError:
       pass
   else:
       raise AssertionError("theme is optional, but not nullable")

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_core import MISSING
   from pydantic_views import View

   class PreferencesUpdate(View[Preferences]):
       theme: str | MISSING
       nickname: str | None | MISSING

       def __init__(self, *, theme: str | MISSING = ..., nickname: str | None | MISSING = ...) -> None: ...

Use Partial for internal data transfer
======================================

``PartialPreset`` keeps every source field and makes it optional, including fields with
read-only, write-only, and hidden access modes. Computed fields are excluded. This is useful
for internal synchronization where a payload contains only the data currently available.

.. testcode:: partial

   from pydantic import BaseModel, computed_field
   from pydantic_core import MISSING
   from pydantic_views import Hidden, PartialPreset, ReadOnly, View, WriteOnly

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password_hash: WriteOnly[str]
       internal_revision: Hidden[int]

       @computed_field
       @property
       def label(self) -> str:
           return f"{self.username} (#{self.id})"

   class AccountPartial(View[Account], preset=PartialPreset):
       pass

   empty = AccountPartial.model_validate({})
   sync = AccountPartial.model_validate({"id": 8, "internal_revision": 3})

   assert empty.username is MISSING
   assert empty.model_dump() == {}
   assert sync.model_dump() == {"id": 8, "internal_revision": 3}
   assert "password_hash" in AccountPartial.model_fields
   assert "label" not in AccountPartial.model_fields

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_core import MISSING
   from pydantic_views import View

   class AccountPartial(View[Account]):
       id: int | MISSING
       username: str | MISSING
       password_hash: str | MISSING
       internal_revision: int | MISSING

       def __init__(
           self,
           *,
           id: int | MISSING = ...,
           username: str | MISSING = ...,
           password_hash: str | MISSING = ...,
           internal_revision: int | MISSING = ...,
       ) -> None: ...

For public update input, prefer ``UpdatePreset``, which filters out read-only and hidden
fields. For public responses, use ``LoadPreset`` or a custom filtered view.

Select fields for an internal workflow
======================================

Combine standard access rules with a tag to include one additional field. Add a field to
the view when it belongs only to that workflow.

.. testcode:: tags

   from typing import Annotated

   from pydantic import BaseModel
   from pydantic_views import AccessMode, AccessTag, Hidden, ReadOnly, View

   class Ticket(BaseModel):
       id: ReadOnly[int]
       subject: str
       staff_note: Annotated[str, AccessMode.WRITE_ONLY, AccessTag("support")]
       internal_token: Hidden[str]

   class SupportTicket(
       View[Ticket],
       view_name="Support",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_tags=(AccessTag("support"),),
   ):
       assigned_queue: str

   ticket = SupportTicket.model_validate(
       {"id": 4, "subject": "Delivery", "staff_note": "Investigating", "assigned_queue": "orders"}
   )
   assert ticket.staff_note == "Investigating"
   assert ticket.assigned_queue == "orders"
   assert "internal_token" not in SupportTicket.model_fields

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_views import View

   class SupportTicket(View[Ticket]):
       assigned_queue: str
       id: int
       subject: str
       staff_note: str

       def __init__(self, *, assigned_queue: str, id: int, subject: str, staff_note: str) -> None: ...

Generate views for root models
==============================

A root model keeps its array-shaped payload rather than adding an object wrapper. Nested
items still receive the selected field filtering.

.. testcode:: root-model

   from pydantic import BaseModel, RootModel
   from pydantic_views import BuilderLoad, ReadOnly, WriteOnly

   class Item(BaseModel):
       id: ReadOnly[int]
       name: str
       internal_note: WriteOnly[str]

   class Catalog(RootModel[list[Item]]):
       pass

   CatalogLoad = BuilderLoad().build_view(Catalog)
   catalog = CatalogLoad.model_validate([{"id": 1, "name": "Notebook"}])
   assert catalog.root[0].name == "Notebook"
   assert catalog.model_dump() == [{"id": 1, "name": "Notebook"}]

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_views import RootView, View

   class CatalogLoad(RootView[Catalog]):
       root: list[ItemLoad]

       def __init__(self, *, root: list[ItemLoad]) -> None: ...

   class ItemLoad(View[Item]):
       id: int
       name: str

       def __init__(self, *, id: int, name: str) -> None: ...

Use generic containers
======================

Specialize a generic model before declaring a view when the endpoint has a concrete item
type. Nested access rules apply to the items as well as the enclosing model.

.. testcode:: generics

   from pydantic import BaseModel
   from pydantic_views import LoadPreset, View, WriteOnly

   class Person(BaseModel):
       name: str
       secret: WriteOnly[str]

   class Page[T: BaseModel](BaseModel):
       items: list[T]
       total: int

   class PeoplePageLoad(View[Page[Person]], preset=LoadPreset):
       pass

   page = PeoplePageLoad.model_validate({"items": [{"name": "Ada"}], "total": 1})
   assert page.model_dump() == {"items": [{"name": "Ada"}], "total": 1}

.. code-block:: python
   :caption: Generated .pyi — view declarations

   from pydantic_views import View

   class PeoplePageLoad(View[Page]):
       items: list[PersonLoad]
       total: int

       def __init__(self, *, items: list[PersonLoad], total: int) -> None: ...

   class PersonLoad(View[Person]):
       name: str

       def __init__(self, *, name: str) -> None: ...

For static typing of runtime-generated classes and generic views, see
:doc:`type_checking`.
