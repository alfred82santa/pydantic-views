======================
Type checking and IDEs
======================

Runtime-generated fields need an explicit description for static tools. Choose the mypy
plugin for declared views, or generate stubs from the actual runtime models. Both approaches
can be used in the same project: the pydantic-views plugin skips ``.pyi`` files.

.. list-table:: Choose an approach
   :header-rows: 1
   :widths: 25 35 40

   * - Tool or workflow
     - Recommended setup
     - Source of field information
   * - mypy with declared views
     - Enable both mypy plugins
     - Source annotations and view configuration
   * - Pyright / Pylance
     - Generate ``.pyi`` files
     - Runtime models and views
   * - Dynamic builders or tag-based selection
     - Generate ``.pyi`` files
     - The resolved runtime field set

Configure mypy
==============

Install mypy as a development dependency and enable the plugins in this order. Base-class
hooks are selected on a first-match basis, so ``pydantic_views.mypy`` must come first.

.. code-block:: toml

   [tool.mypy]
   plugins = ["pydantic_views.mypy", "pydantic.mypy"]

The equivalent INI configuration is:

.. code-block:: ini

   [mypy]
   plugins = pydantic_views.mypy, pydantic.mypy

Declare views with ``preset=`` or explicit keywords. For example, save this as a model
module and run mypy against it:

.. code-block:: python

   from typing import assert_type

   from pydantic import BaseModel
   from pydantic_views import LoadPreset, ReadOnly, View, WriteOnly

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password: WriteOnly[str]

   class AccountLoad(View[Account], preset=LoadPreset):
       pass

   account = AccountLoad.model_validate({"id": 1, "username": "ada"})
   assert_type(account.id, int)
   assert_type(account.username, str)
   # account.password is a type error: the load view has no password field.

The plugin synthesizes view attributes and constructor arguments, including generated
nested views. This is static analysis, not execution of your model-building code.

Constructor strictness
----------------------

By default, the plugin reports unknown constructor keywords. To allow extra keywords in
the synthesized signature, use this INI-only option:

.. code-block:: ini

   [mypy]
   plugins = pydantic_views.mypy, pydantic.mypy

   [pydantic-views-mypy]
   init_forbid_extra = false

The default is ``true``. The custom option is read from ``mypy.ini`` or ``setup.cfg``;
``pyproject.toml`` can configure the plugins but not this option. Constructor strictness
is a type-checking setting, separate from Pydantic's runtime ``extra`` configuration.

Current plugin boundaries
-------------------------

* Prefer views declared in the same module as their source model. Access-mode annotations
  may no longer be available when mypy analyzes imported models.
* ``preset=Name`` supports a module-level ``Preset(...)`` definition. Explicit keywords
  override the preset. ``**Preset._asdict()`` works at runtime but cannot be analyzed by
  the plugin.
* Tag-based ``include_tags`` / ``exclude_tags`` filtering is not recovered from mypy's
  processed annotations.
* ``RootView`` is not field-expanded by the plugin.
* Optional constructor arguments are modeled, but the plugin does not reproduce every
  runtime detail, including the ``MISSING`` union members of optional fields.

Use runtime-generated stubs when you need a static description of the resolved fields,
particularly for dynamic builders, tag filters, or views declared in another module.

Generate runtime stubs
======================

The bundled generator imports your modules, reads their models and generated views, and
writes ``.pyi`` files. It does not run the mypy plugin.

.. code-block:: console

   $ python -m pydantic_views.stubgen myapp.models
   wrote /path/to/myapp/models.pyi

The default output sits beside each source file. A package name includes its submodules;
you can also pass multiple modules and mirror their package tree into a separate directory:

.. code-block:: bash

   python -m pydantic_views.stubgen myapp.models myapp.schemas --output-dir build/stubs

When using a separate directory, configure your checker's stub search path, for example
Pyright's ``stubPath``. Keep module/package paths intact. Run generation in your normal
application environment: imports execute module-level code and require the dependencies
and configuration used by those modules.

What is preserved
-----------------

The generator describes both the views and the surrounding module symbols:

* Declared views and views generated for nested models, with their runtime fields and
  explicit keyword-only constructor signatures.
* Ordinary classes, Pydantic models, enums, nested classes, and ``TypedDict`` definitions.
* Module-level functions and variables discovered by the generator, plus ``type`` aliases.
* Generic parameters, parameterized Pydantic annotations, and explicit TypeVar covariance
  or contravariance, including bounds, constraints, and defaults.
* ``MISSING`` in field and constructor annotations, with the corresponding import.

For example, the runtime load view of an account is described as:

.. code-block:: python

   from pydantic_views import View
   from myapp.models import Account  # Source model, shown here for context.

   class AccountLoad(View[Account]):
       id: int
       username: str
       def __init__(self, *, id: int, username: str) -> None: ...

In the actual generated module stub, local classes such as ``Account`` are defined in the
same file rather than imported from themselves. Explicit variance is retained with
``TypeVar(..., covariant=True)`` or ``contravariant=True`` and ``Generic[...]`` bases;
converting those declarations to inferred PEP 695 parameters could change assignability.

Keeping stubs current
---------------------

An adjacent stub takes precedence over its ``.py`` file for type checking. Regenerate stubs
when source schemas change, and include generation in your development or CI workflow.
The generator describes the symbols it can inspect; review the output for unusual dynamic
exports or annotations it cannot resolve. Do not treat it as a general-purpose replacement
for a hand-maintained stub for every possible Python module.

For the bundled example module, run:

.. code-block:: bash

   python -m pydantic_views.stubgen examples.models

The mypy plugin leaves stub declarations unchanged, preserving their field sets and
constructor signatures instead of adding a second ``__init__``.
