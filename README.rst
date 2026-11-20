.. |docs| image:: https://readthedocs.org/projects/pydantic-views/badge/?version=stable
   :alt: Documentation
   :target: https://pydantic-views.readthedocs.io/stable/

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/pydantic-views
   :alt: Supported Python versions

.. |typed| image:: https://img.shields.io/pypi/types/pydantic-views
   :alt: Typed package

.. |license| image:: https://img.shields.io/pypi/l/pydantic-views
   :alt: License

.. |version| image:: https://img.shields.io/pypi/v/pydantic-views
   :alt: PyPI version

|docs| |python-versions| |typed| |license| |version|

.. image:: docs/source/_static/pydantic-views-banner.png
   :alt: pydantic-views — typed schemas from one model
   :width: 100%

.. start-doc

==============
Pydantic Views
==============

**One domain model. Purpose-built schemas for every operation.**

Define your fields and access rules once, then derive Pydantic models for creation,
responses, updates, and internal workflows. Keep validation constraints and field metadata
consistent as your application grows, without maintaining a separate schema by hand for
each operation.

The generated views are Pydantic models: validate input, serialize output, and generate
JSON Schema with the APIs you already use.

Installation
============

Requires Python 3.13 or later and Pydantic 2.

.. code-block:: bash

   pip install pydantic-views
   # Or, with uv:
   uv add pydantic-views

From one model to an API boundary
=================================

.. code-block:: python

   from pydantic import BaseModel, Field
   from pydantic_views import (
       LoadPreset, ReadOnly, UpdatePreset, View, WriteOnly,
   )

   class User(BaseModel):
       id: ReadOnly[int]
       name: str = Field(min_length=1)
       password: WriteOnly[str]

   class UserLoad(View[User], preset=LoadPreset):
       pass

   class UserUpdate(View[User], preset=UpdatePreset):
       pass

   stored = User(id=1, name="Ada", password="stored-hash")
   response = UserLoad.view_build_from(stored)
   assert response.model_dump() == {"id": 1, "name": "Ada"}

   changes = UserUpdate.model_validate({"name": "Grace"})
   assert changes.model_dump() == {"name": "Grace"}
   updated = changes.view_apply_to(stored)
   assert updated.name == "Grace"
   assert updated.password == "stored-hash"

The load view excludes the password. The update view excludes the ID and accepts omitted
fields, while retaining the name's validation constraint. Nested models receive matching
views automatically.

The generated stub makes these contracts visible to editors and type checkers. The view
declarations in ``models.pyi`` look like this (source-model definitions are omitted here):

.. code-block:: python

   from pydantic_core import MISSING
   from pydantic_views import View

   class UserLoad(View[User]):
       id: int
       name: str

       def __init__(self, *, id: int, name: str) -> None: ...

   class UserUpdate(View[User]):
       name: str | MISSING
       password: str | MISSING

       def __init__(
           self, *, name: str | MISSING = ..., password: str | MISSING = ...
       ) -> None: ...

``UserLoad`` has no password field; ``UserUpdate`` has no ID field. Its constructor
accepts either change independently, and omitted values remain ``MISSING``.

What you can build
==================

* **Operation-specific schemas:** five presets for create, create-result, load, update,
  and unrestricted partial data; custom presets and builders for other workflows.
* **Explicit field access:** read-only, write-only, creation-only, and hidden annotations;
  combine access modes and use tags for more selective views.
* **Consistent field definitions:** retain aliases, defaults, descriptions, JSON Schema
  metadata, and annotation-based constraints such as ``Field(min_length=1)``.
* **Structured data:** derive matching views for nested and recursive models, generic
  models, ``RootModel``, and models inside lists, sets, tuples, dictionaries, and unions.
* **Partial updates:** distinguish an omitted field (``MISSING``) from an explicit
  ``None``; merge nested models and mappings into existing data.
* **Flexible construction:** declare ``View[Model]`` subclasses with extra fields or
  generate and cache classes dynamically with a ``Builder`` and per-model ``Manager``.
* **Computed response fields:** include computed values in load and create-result views.
* **Static tooling:** a mypy plugin for declared views and a runtime ``.pyi`` generator
  for Pyright, Pylance, and other stub-aware tools. The package includes ``py.typed``.

Choose a preset
===============

.. list-table::
   :header-rows: 1
   :widths: 23 47 30

   * - Preset
     - Fields included
     - Behavior
   * - ``CreatePreset``
     - Writable and write-on-creation
     - Hides default ``None`` values
   * - ``CreateResultPreset``
     - Readable and read-on-creation
     - Includes computed fields
   * - ``LoadPreset``
     - Readable
     - Includes computed fields
   * - ``UpdatePreset``
     - Writable
     - All selected fields optional
   * - ``PartialPreset``
     - All model fields, regardless of access mode
     - All optional; no computed fields

Unmarked fields participate in every standard preset. ``PartialPreset`` also includes
hidden and write-only fields: use it for trusted internal data, not as a filtered public
response. Access annotations define schema contents; application authorization remains
separate.

Type checking
=============

For mypy, enable both plugins in this order:

.. code-block:: toml

   [tool.mypy]
   plugins = ["pydantic_views.mypy", "pydantic.mypy"]

For stub-aware editors and type checkers, generate stubs from your runtime models:

.. code-block:: bash

   python -m pydantic_views.stubgen myapp.models

This writes ``myapp/models.pyi`` next to the source. Regenerate it when the models change;
a type checker uses the adjacent stub in preference to the Python file. The mypy plugin
skips stub files, so generated stubs and the plugin can coexist.

Continue reading
================

* `User guide <https://pydantic-views.readthedocs.io/stable/guide.html>`_:
  access rules, presets, custom views, nested data, and update semantics.
* `Practical examples <https://pydantic-views.readthedocs.io/stable/examples.html>`_:
  complete workflows with executable assertions.
* `Type checking <https://pydantic-views.readthedocs.io/stable/type_checking.html>`_:
  plugin configuration, stub generation, and current limitations.
* `API reference <https://pydantic-views.readthedocs.io/stable/api.html>`_:
  public annotations, presets, builders, and view helpers.

Source code and issue tracking are available on
`GitHub <https://github.com/alfred82santa/pydantic-views>`_.
