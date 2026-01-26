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

Craft a bespoke builder to allow nullable fields and expose only certain access modes.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import Builder, AccessMode

   SoftDeleteBuilder = Builder(
	   view_name="SoftDelete",
	   access_modes=(AccessMode.READ_AND_WRITE,),
	   all_nullable=True,
   )

   class Document(BaseModel):
	   title: str
	   body: str
	   deleted_at: float | None

   DocumentSoftDelete = SoftDeleteBuilder.build_view(Document)

   doc = Document(title="Plan", body="...")
   soft_delete = DocumentSoftDelete(deleted_at=1720000000.0)

   deleted_doc = soft_delete.view_apply_to(doc)
   assert deleted_doc.deleted_at is not None

