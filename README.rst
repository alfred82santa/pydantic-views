
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
Each view exposes only the fields appropriate for a given operation—create, update, load, or a custom
flow—so you avoid hand-maintaining parallel schemas.

You annotate each field of your base model **once** with how it may be accessed (read-only, write-only,
hidden, …), and pydantic-views generates the right model for every operation. Nested and recurrent models
get their matching views automatically, validators and field metadata are preserved, and the result is fully
typed.

Typical service signatures become easy to express:

.. code-block:: python

   class ExampleModelCreate(View[ExampleModel], preset=CreatePreset):
       pass

   class ExampleModelCreateResult(View[ExampleModel], preset=CreateResultPreset):
       pass

   class ExampleModelLoad(View[ExampleModel], preset=LoadPreset):
       pass

   class ExampleModelUpdate(View[ExampleModel], preset=UpdatePreset):
       pass


   def create(input: ExampleModelCreate) -> ExampleModelCreateResult: ...
   def load(model_id: str) -> ExampleModelLoad: ...
   def update(model_id: str, input: ExampleModelUpdate) -> ExampleModelLoad: ...


--------
Features
--------

- Unlimited views per model (create, update, load, or any custom flow).
- Declare field access **once**; every view is derived from a single source of truth.
- Works on nested models; referenced (and recurrent) models get their views too.
- Works on ``RootModel`` and complex container types (``list``, ``set``, ``tuple``, ``dict``, ``Literal``, unions).
- Ready-made presets and builders for common patterns, or define views manually.
- Preserves validators, aliases, defaults, titles, descriptions and other field metadata.
- Custom access tags for fine-grained, per-view field selection.
- Helpers to build a view from a model, build a model from a view, and merge a view into a model.
- Fully typed with a shipped ``py.typed`` marker and an extensive test suite.
- Static type checking via a bundled mypy plugin and a ``.pyi`` stub generator for other type checkers.
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

Mark each field with its access mode using the provided
`annotations <https://pydantic-views.readthedocs.io/latest/api.html#field-annotations>`_.
Unmarked fields default to read/write everywhere.

.. code-block:: python

   from typing import Annotated

   from annotated_types import Gt
   from pydantic import BaseModel, computed_field
   from pydantic_views import AccessMode, Hidden, ReadOnly, ReadOnlyOnCreation

   class ExampleModel(BaseModel):
       # Unmarked fields are read/write everywhere.
       field_str: str

       # Read-only fields are removed from create and update views.
       field_read_only_str: ReadOnly[str]

       # Read-only-on-creation fields are hidden on create, update and load views,
       # but appear on create-result views.
       field_api_secret: ReadOnlyOnCreation[str]

       # Combine access modes with Annotated and keep validators (Gt in this case).
       field_int: Annotated[int, AccessMode.READ_ONLY, AccessMode.WRITE_ONLY_ON_CREATION, Gt(5)]

       # Hidden fields never appear.
       field_hidden_int: Hidden[int]

       # Computed fields appear only on read views.
       @computed_field
       def field_computed_field(self) -> int:
           return self.field_hidden_int * 5


Access modes
============

Every field carries one or more access modes. The mode decides which generated views expose the field.
You can use the convenient annotation aliases (``ReadOnly[T]``, ``WriteOnly[T]``, …) or attach
``AccessMode`` values directly with ``Annotated`` when you want to combine several modes
or keep extra validators.

.. list-table::
   :header-rows: 1

   * - Annotation
     - Access mode
     - Create
     - CreateResult
     - Update
     - Load
   * - *(unmarked)* / ``ReadAndWrite[T]``
     - ``READ_AND_WRITE``
     - ✓
     - ✓
     - ✓
     - ✓
   * - ``ReadOnly[T]``
     - ``READ_ONLY``
     -
     - ✓
     -
     - ✓
   * - ``WriteOnly[T]``
     - ``WRITE_ONLY``
     - ✓
     -
     - ✓
     -
   * - ``ReadOnlyOnCreation[T]``
     - ``READ_ONLY_ON_CREATION``
     -
     - ✓
     -
     -
   * - ``WriteOnlyOnCreation[T]``
     - ``WRITE_ONLY_ON_CREATION``
     - ✓
     -
     -
     -
   * - ``Hidden[T]``
     - ``HIDDEN``
     -
     -
     -
     -
   * - ``@computed_field``
     -
     -
     - ✓
     -
     - ✓

``Create`` also hides default ``None`` values, ``Update`` makes every field optional, and the read views
(``CreateResult`` and ``Load``) include computed fields.


The four standard views
=======================

pydantic-views ships four presets that cover the typical CRUD lifecycle. Each preset is a
``Preset`` (a ``NamedTuple``) you pass to a ``View`` subclass via ``preset=``:

- ``CreatePreset`` — input accepted when creating a resource (writable and write-on-creation fields).
- ``CreateResultPreset`` — what you return after creation (readable fields plus computed fields).
- ``UpdatePreset`` — partial input for updates (writable fields, all optional).
- ``LoadPreset`` — what you return when reading a resource (readable fields plus computed fields).


Build a load view
=================

.. code-block:: python

   from pydantic_views import View, LoadPreset

   class ExampleModelLoad(View[ExampleModel], preset=LoadPreset):
       pass

Which is equivalent to:

.. code-block:: python

   from typing import Annotated

   from annotated_types import Gt
   from pydantic import BaseModel
   from pydantic_views import View

   class ExampleModelLoad(BaseModel):
       field_str: str
       field_int: Annotated[int, Gt(5)]
       field_computed_field: int

Build an update view
====================

.. code-block:: python

   from pydantic_views import View, UpdatePreset

   class ExampleModelUpdate(View[ExampleModel], preset=UpdatePreset):
       pass

Which is equivalent to:

.. code-block:: python

   from pydantic import Field, BaseModel
   from pydantic_core import MISSING
   from pydantic_views import View

   class ExampleModelUpdate(BaseModel):
       field_str: str = Field(default_factory=lambda: MISSING)

On ``Update`` views every field uses a default factory that returns ``MISSING``,
so fields become optional. Applying the view to a model only updates values that were set.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything",
       field_read_only_str="anything",
       field_api_secret="anything",
       field_int=10,
       field_hidden_int=33,
   )

   update = ExampleModelUpdate(field_str="new_data")

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "new_data"


If a field is not set on the update view, the original value is kept.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything",
       field_read_only_str="anything",
       field_api_secret="anything",
       field_int=10,
       field_hidden_int=33,
   )

   update = ExampleModelUpdate()

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "anything"


----------------------
Working with view data
----------------------

Every generated view inherits a small set of helpers from ``View`` to move data
between the base model and its views:

- ``View.view_build_from(model)`` — build a view instance from a model instance, omitting unset fields.
- ``view.view_build_to()`` — build a base-model instance from the view, using only the fields set on the view.
- ``view.view_apply_to(model)`` — return a copy of ``model`` updated with the fields set on the view (deep merge).
- ``View.view_class_root()`` — return the base model class the view was generated from.

.. code-block:: python

   # Project a stored model into the read view returned by your API.
   stored = ExampleModel(
       field_str="value",
       field_read_only_str="ro",
       field_api_secret="secret",
       field_int=10,
       field_hidden_int=33,
   )
   payload = ExampleModelLoad.view_build_from(stored)

   # Apply a partial update and get a new, validated model back.
   patched = ExampleModelUpdate(field_str="updated").view_apply_to(stored)


-----------------------------
Two ways to define your views
-----------------------------

Subclass ``View`` (with a preset)
=================================

The declarative form integrates with type checkers and IDEs, and lets you add extra fields:

.. code-block:: python

   from pydantic_views import View, CreatePreset

   class ExampleModelCreate(View[ExampleModel], preset=CreatePreset):
       # You can add fields that are not part of the base model.
       extra_flag: bool = False

The ``preset=`` keyword expands the preset's configuration into the view; an explicit keyword
passed alongside it (for example ``view_name=...``) overrides the preset's value. The bundled
mypy plugin understands both the ``preset=`` form and explicit keywords. (The older
``**LoadPreset._asdict()`` splat still works at runtime, but mypy cannot analyse ``**`` unpackings
in class keywords, so prefer ``preset=`` for full type checking.)

You can also pass the configuration directly as keyword arguments instead of a preset:

.. code-block:: python

   from pydantic_views import AccessMode, View

   class ExampleModelReadOnly(
       View[ExampleModel],
       view_name="ReadOnly",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_computed_fields=True,
   ):
       pass

Use a builder
=============

The imperative form builds (and caches) a view class on demand—handy when generating views dynamically:

.. code-block:: python

   from pydantic_views import BuilderLoad, BuilderUpdate

   ExampleModelLoad = BuilderLoad().build_view(ExampleModel)
   ExampleModelUpdate = BuilderUpdate().build_view(ExampleModel)

Views are cached per base model, so building the same view twice returns the same class.


--------------------------
Custom views with builders
--------------------------

For anything beyond the standard presets, build your own ``Builder``. The
configuration is shared by builders, presets and the ``View`` subclass keyword arguments:

- ``access_modes`` — which access modes to include in the view.
- ``include_tags`` / ``exclude_tags`` — force-include or force-exclude fields by ``AccessTag``.
- ``all_optional`` — make every field optional (the basis of ``Update`` views).
- ``all_nullable`` — make every field nullable.
- ``hide_default_null`` — drop default ``None`` values so they don't appear in the schema.
- ``include_computed_fields`` — include ``@computed_field`` properties.

.. code-block:: python

   from pydantic_views import AccessMode, Builder

   builder = Builder(
       view_name="Summary",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_computed_fields=True,
       all_nullable=True,
   )

   ExampleModelSummary = builder.build_view(ExampleModel)


Access tags
===========

Access tags give you a second axis of selection on top of access modes. Tag fields with
``AccessTag`` and then ``include_tags`` / ``exclude_tags`` to override what a view would
normally expose.

.. code-block:: python

   from typing import Annotated

   from pydantic import BaseModel
   from pydantic_views import AccessMode, AccessTag, View

   class ModelTagged(BaseModel):
       field_int: Annotated[int, AccessMode.READ_ONLY, AccessTag("tag1")]
       field_str: Annotated[str, AccessMode.WRITE_ONLY, AccessTag("tag2"), AccessTag("tag3")]
       field_float: Annotated[float, AccessTag("tag3"), AccessTag("tag4")]
       field_bool: bool

   # A plain read-only view: read-only and read/write fields only.
   class ReadOnlyView(
       View[ModelTagged],
       view_name="ReadOnly",
       access_modes=(AccessMode.READ_ONLY,),
   ):
       pass
   # -> field_int, field_float, field_bool

   # Pull in a write-only field that matches a tag.
   class ReadOnlyWithTag3(
       View[ModelTagged],
       view_name="ReadOnlyWithTag3",
       access_modes=(AccessMode.READ_ONLY,),
       include_tags=(AccessTag("tag3"),),
   ):
       pass
   # -> field_int, field_float, field_bool, field_str

   # Exclude tagged fields that would otherwise match.
   class ReadWriteWithoutTag3(
       View[ModelTagged],
       view_name="ReadWriteWithoutTag3",
       access_modes=(AccessMode.READ_ONLY, AccessMode.WRITE_ONLY),
       exclude_tags=(AccessTag("tag3"),),
   ):
       pass
   # -> field_int, field_bool

``AccessTag`` instances are interned by name (``AccessTag("tag1") is AccessTag("tag1")``), immutable, and
compare equal to their name string, so they are cheap to reuse across models.


-------------
Nested models
-------------

When a field references another Pydantic model, pydantic-views generates a matching view for it
automatically, recursively, and even for self-referential or circular models. Container types
(``list``, ``set``, ``tuple``, ``dict``, ``Literal`` and unions) are traversed too.

.. code-block:: python

   from pydantic import BaseModel
   from pydantic_views import ReadOnly, View, LoadPreset

   class Address(BaseModel):
       street: str
       zip_code: ReadOnly[str]

   class User(BaseModel):
       name: str
       addresses: list[Address]

   class UserLoad(View[User], preset=LoadPreset):
       pass

   # UserLoad.addresses is a list of the generated AddressLoad view.


--------------------
Static type checking
--------------------

Views are generated at runtime, so a type checker cannot see their fields on its own. pydantic-views
ships a mypy plugin (``pydantic_views.mypy``) that reproduces the builder's field selection
statically. Enable it in your mypy configuration, **before** ``pydantic.mypy``:

.. code-block:: ini

   [mypy]
   plugins = pydantic_views.mypy, pydantic.mypy

It understands both the ``preset=`` and explicit-keyword forms of a view, and types nested-model
fields with their generated views (``Address`` + ``Load`` -> ``AddressLoad``):

.. code-block:: python

   from pydantic_views import LoadPreset, View

   class UserLoad(View[User], preset=LoadPreset):
       pass

   reveal_type(UserLoad.model_validate({}).id)   # int — the plugin knows the field exists
   UserLoad(password="secret")                    # error: write-only field is not in a load view

For type checkers that don't run mypy plugins (pyright, Pylance, PyCharm, …), pydantic-views ships a
stub generator. It imports your module and writes a ``.pyi`` describing every view's real fields
(plus the regular classes, models and functions around them):

.. code-block:: bash

   python -m pydantic_views.stubgen myapp.models

Pass a package name to stub every submodule, list several modules at once, and use ``-o/--output-dir``
to write the stubs to a separate tree. See
`Type checking and stub files <https://pydantic-views.readthedocs.io/stable/type_checking.html>`_
for the stub generator and mypy plugin options, and the full list of what is and isn't analysed
statically.


-------------
Documentation
-------------

Full documentation, including the complete API reference, is available at
`pydantic-views.readthedocs.io <https://pydantic-views.readthedocs.io/stable/>`_.
