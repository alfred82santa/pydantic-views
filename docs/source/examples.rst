========
Examples
========


Minimal create/load/update
--------------------------

Build common views from a single model and use them as function signatures.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import BuilderCreate, BuilderCreateResult, BuilderLoad, BuilderUpdate

   class User(BaseModel):
       id: int
       email: str
       password: str

   UserCreate = BuilderCreate().build_view(User)
   UserCreateResult = BuilderCreateResult().build_view(User)
   UserLoad = BuilderLoad().build_view(User)
   UserUpdate = BuilderUpdate().build_view(User)

   def create_user(input: UserCreate) -> UserCreateResult: ...
   def get_user(user_id: int) -> UserLoad: ...
   def update_user(user_id: int, input: UserUpdate) -> UserLoad: ...


Declarative views with presets
-------------------------------

Prefer the declarative form when you want the views to be fully type-checked: subclass ``View`` and
pass a preset via ``preset=``. The bundled mypy plugin understands this form (unlike the
``**Preset._asdict()`` splat), and you can still declare extra fields that live only on the view.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import CreatePreset, CreateResultPreset, LoadPreset, UpdatePreset, View

   class User(BaseModel):
       id: int
       email: str
       password: str

   class UserCreate(View[User], preset=CreatePreset):
       # A field that only exists on the view, not on the base model.
       accept_terms: bool = False

   class UserCreateResult(View[User], preset=CreateResultPreset):
       pass

   class UserLoad(View[User], preset=LoadPreset):
       pass

   class UserUpdate(View[User], preset=UpdatePreset):
       pass

   def create_user(input: UserCreate) -> UserCreateResult: ...
   def get_user(user_id: int) -> UserLoad: ...
   def update_user(user_id: int, input: UserUpdate) -> UserLoad: ...


Declarative views without presets
----------------------------------

You do not need a preset: pass the configuration directly as keyword arguments to build any custom
view. The recognised keywords are ``view_name``, ``access_modes``, ``all_optional``,
``all_nullable``, ``hide_default_null`` and ``include_computed_fields``.

.. code-block:: python

   from pydantic import BaseModel, computed_field
   from pydantic_views import AccessMode, ReadOnly, WriteOnly, View

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password: WriteOnly[str]

       @computed_field
       def handle(self) -> str:
           return f"@{self.username}"

   # A bespoke "public" read view spelled out with explicit keywords (no preset).
   class AccountPublic(
       View[Account],
       view_name="Public",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_computed_fields=True,
   ):
       pass
   # -> id, username, handle   (write-only ``password`` is excluded)


Filtering fields with tags
--------------------------

Tag fields with ``AccessTag`` to force-include or force-exclude them regardless of the view's access
modes. ``exclude_tags`` drops tagged fields that would otherwise be kept; ``include_tags`` pulls in
tagged fields that the access modes would otherwise leave out.

.. code-block:: python

   from typing import Annotated

   from pydantic import BaseModel
   from pydantic_views import AccessMode, AccessTag, View

   class Article(BaseModel):
       title: str
       body: str
       # Read-only, but only meant for staff:
       moderation_notes: Annotated[str, AccessMode.READ_ONLY, AccessTag("admin")]
       view_count: Annotated[int, AccessMode.READ_ONLY, AccessTag("stats")]
       # Write-only secret used to build a preview link:
       draft_token: Annotated[str, AccessMode.WRITE_ONLY, AccessTag("preview")]

   # Public view: keep readable fields, but drop anything tagged "admin".
   class ArticlePublic(
       View[Article],
       view_name="Public",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       exclude_tags=(AccessTag("admin"),),
   ):
       pass
   # -> title, body, view_count   (moderation_notes dropped by its tag)

   # Preview view: readable fields plus the write-only ``draft_token`` pulled in by its tag.
   class ArticlePreview(
       View[Article],
       view_name="Preview",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_tags=(AccessTag("preview"),),
   ):
       pass
   # -> title, body, moderation_notes, view_count, draft_token

``AccessTag`` instances are interned by name (``AccessTag("preview") is AccessTag("preview")``), so the
same tag object is reused everywhere you reference it.


Nested models and selective fields
----------------------------------

Views cascade into nested models and respect access modes you annotate.

.. code-block:: python

   from typing import Annotated

   from pydantic import BaseModel, computed_field
   from pydantic_views import AccessMode, ReadOnly, ReadOnlyOnCreation, BuilderLoad

   class Address(BaseModel):
       street: str
       city: str
       zip_code: str

   class Profile(BaseModel):
       username: str
       email: ReadOnly[str]
       # Hide on create/update, show after creation
       api_token: ReadOnlyOnCreation[str]
       # Expose only when reading (load views)
       score: Annotated[int, AccessMode.READ_ONLY]

       @computed_field
       def location(self) -> str:
           return f"{self.username} @ {self.email}"

       address: Address

   ProfileLoad = BuilderLoad().build_view(Profile)

   profile = Profile(
       username="alice",
       email="alice@example.com",
       api_token="secret",
       score=42,
       address=Address(street="Main", city="Springfield", zip_code="00000"),
   )

   loaded = ProfileLoad.view_build_from(profile)
   assert loaded.address.city == "Springfield"
   # api_token and score are present, write-only fields would have been stripped


Applying partial updates
------------------------

Update views accept only the fields you want to change and merge them into an instance.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import BuilderUpdate

   class Settings(BaseModel):
       theme: str
       locale: str
       marketing_opt_in: bool

   SettingsUpdate = BuilderUpdate().build_view(Settings)

   current = Settings(theme="light", locale="en", marketing_opt_in=False)
   patch = SettingsUpdate(theme="dark")

   updated = patch.view_apply_to(current)

   assert updated.theme == "dark"
   assert updated.locale == "en"  # unchanged


Create + result pair with computed fields
-----------------------------------------

Use ``BuilderCreate`` to accept input and ``BuilderCreateResult`` to return read-only and computed fields.

.. code-block:: python

   from pydantic import BaseModel, computed_field
   from pydantic_views import BuilderCreate, BuilderCreateResult, ReadOnly

   class Invoice(BaseModel):
       id: ReadOnly[int]
       description: str
       units: int
       unit_price: float

       @computed_field
       def total(self) -> float:
           return self.units * self.unit_price

   InvoiceCreate = BuilderCreate().build_view(Invoice)
   InvoiceCreateResult = BuilderCreateResult().build_view(Invoice)

   new_invoice = InvoiceCreate(description="Hosting", units=2, unit_price=25.0)
   stored = Invoice(id=1, **new_invoice.model_dump())

   result = InvoiceCreateResult.view_build_from(stored)
   assert result.total == 50.0


Custom builder with nullable fields
-----------------------------------

Craft a bespoke builder to expose only certain access modes and make every field optional and
nullable — a patch-style view where you set just the fields you want to change.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import Builder, AccessMode

   SoftDeleteBuilder = Builder(
       view_name="SoftDelete",
       access_modes=(AccessMode.READ_AND_WRITE,),
       all_optional=True,
       all_nullable=True,
   )

   class Document(BaseModel):
       title: str
       body: str
       deleted_at: float | None = None

   DocumentSoftDelete = SoftDeleteBuilder.build_view(Document)

   doc = Document(title="Plan", body="...")
   soft_delete = DocumentSoftDelete(deleted_at=1720000000.0)

   deleted_doc = soft_delete.view_apply_to(doc)
   assert deleted_doc.deleted_at is not None
