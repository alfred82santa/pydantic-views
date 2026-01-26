
.. |docs| image:: https://readthedocs.org/projects/pydantic-views/badge/?version=stable
    :alt: Documentation Status
    :target: https://pydantic-views.readthedocs.io/stable/?badge=stable

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/pydantic-views
   :alt: PyPI - Python Version

.. |typed| image:: https://img.shields.io/pypi/types/pydantic-views
   :alt: PyPI - Types

.. |license| image:: https://img.shields.io/pypi/l/pydantic-views
   :alt: PyPI - License

.. |version| image:: https://img.shields.io/pypi/v/pydantic-views
   :alt: PyPI - Version


|docs| |python-versions| |typed| |license| |version|

.. start-doc

===============================
Typed views for Pydantic models
===============================

pydantic-views lets you derive focused, type-safe Pydantic models ("views") from a base model.
Each view exposes only the fields appropriate for a given operation—create, update, load, or a custom flow—so you avoid
hand-maintaining parallel schemas.

Typical service signatures become easy to express:

.. code-block:: python

   ExampleModelCreate = BuilderCreate().build_view(ExampleModel)
   ExampleModelCreateResult = BuilderCreateResult().build_view(ExampleModel)
   ExampleModelLoad = BuilderLoad().build_view(ExampleModel)
   ExampleModelUpdate = BuilderUpdate().build_view(ExampleModel)

   def create(input: ExampleModelCreate) -> ExampleModelCreateResult: ...
   def load(model_id: str) -> ExampleModelLoad: ...
   def update(model_id: str, input: ExampleModelUpdate) -> ExampleModelLoad: ...


--------
Features
--------

- Unlimited views per model (create, update, load, custom).
- Works on nested models; referenced models get views too.
- Builders for common patterns, or define views manually.
- Fully typed with shipped ``py.typed`` and tests.
- Open source and published on PyPI.


------------
Installation
------------

Using pip:

.. code-block:: bash

   pip install pydantic-views

Using `poetry <https://python-poetry.org/>`_:

.. code-block:: bash

   poetry add pydantic-views

Using `uv <https://docs.astral.sh/uv/>`_:

.. code-block:: bash

   uv add pydantic-views


----------
Quickstart
----------

Mark each field with its access mode using the provided `annotations <https://pydantic-views.readthedocs.io/latest/api.html#field-annotations>`_.
Unmarked fields default to read/write.

.. code-block:: python

   from typing import Annotated

   from pydantic import BaseModel, computed_field, gt
   from pydantic_views import AccessMode, Hidden, ReadOnly, ReadOnlyOnCreation

   class ExampleModel(BaseModel):
       # Unmarked fields are read/write everywhere.
       field_str: str

       # Read-only fields are removed from create and update views.
       field_read_only_str: ReadOnly[str]

       # Read-only-on-creation fields are hidden on create, update and load views,
       # but appear on create-result views.
       field_api_secret: ReadOnlyOnCreation[str]

       # Combine access modes with Annotated and keep validators (gt in this case).
       field_int: Annotated[int, AccessMode.READ_ONLY, AccessMode.WRITE_ONLY_ON_CREATION, gt(5)]

       # Hidden fields never appear.
       field_hidden_int: Hidden[int]

       # Computed fields appear only on read views.
       @computed_field
       def field_computed_field(self) -> int:
           return self.field_hidden_int * 5

Build a load view:

.. code-block:: python

   from pydantic_views import BuilderLoad

   ExampleModelLoad = BuilderLoad().build_view(ExampleModel)

Which is equivalent to:


.. code-block:: python

   from pydantic import gt
   from pydantic_views import View

   class ExampleModelLoad(View[ExampleModel]):
       field_str: str
       field_int: Annotated[int, gt(5)]
       field_computed_field: int

To build an update view:

.. code-block:: python

   from pydantic_views import BuilderUpdate

   ExampleModelUpdate = BuilderUpdate().build_view(ExampleModel)
   
Which is equivalent to:

.. code-block:: python

   from pydantic import Field, PydanticUndefined
   from pydantic_views import View

   class ExampleModelUpdate(View[ExampleModel]):
       field_str: str = Field(default_factory=lambda: PydanticUndefined)

On ``Update`` views every field uses a default factory that returns ``PydanticUndefined``,
so fields become optional. Applying the view to a model only updates values that were set.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything"
       field_read_only_str="anything"
       field_api_secret="anything"
       field_int=10
       field_hidden_int=33
   )

   update = ExampleModelUpdate(field_str="new_data")

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "new_data"


If a field is not set on the update view, the original value is kept.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything"
       field_read_only_str="anything"
       field_api_secret="anything"
       field_int=10
       field_hidden_int=33
   )

   update = ExampleModelUpdate()

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "anything"
