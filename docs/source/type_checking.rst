==============================
Type checking and stub files
==============================

Views are generated at runtime, so a type checker cannot see their fields just by reading your
source. pydantic-views ships a **mypy plugin** (:mod:`pydantic_views.mypy`) that reproduces the
builder's field selection statically — it synthesises the right attributes and ``__init__``
signature for every view. For type checkers other than mypy (pyright, Pylance, PyCharm, …) you can
turn the plugin's output into **stub files** so they become aware of the same fields.


Configuring the mypy plugin
===========================

Enable the plugin in your mypy configuration. It **must** be listed before ``pydantic.mypy`` —
base-class hooks are first-wins, and the pydantic-views plugin needs to run first:

.. code-block:: ini

   ; mypy.ini / setup.cfg
   [mypy]
   plugins = pydantic_views.mypy, pydantic.mypy

The same works from ``pyproject.toml``:

.. code-block:: toml

   [tool.mypy]
   plugins = ["pydantic_views.mypy", "pydantic.mypy"]

That is all that is required. Once enabled, both the ``preset=`` form and the explicit-keyword form
of a view are understood:

.. code-block:: python

   from pydantic_views import LoadPreset, View

   class UserLoad(View[User], preset=LoadPreset):
       pass

   reveal_type(UserLoad.model_validate({}).id)   # int — the plugin knows the field exists
   UserLoad(password="secret")                    # error: write-only field is not in a load view


Plugin options
--------------

The plugin reads a single option from an ``[pydantic-views-mypy]`` section:

.. code-block:: ini

   [mypy]
   plugins = pydantic_views.mypy, pydantic.mypy

   [pydantic-views-mypy]
   ; Whether the synthesised __init__ should reject unknown keyword arguments. Default: true.
   init_forbid_extra = true

.. note::

   ``init_forbid_extra`` is read only from **INI-style** configuration (``mypy.ini`` /
   ``setup.cfg``). When mypy is configured from ``pyproject.toml`` the option is not parsed and
   falls back to its default (``true``). The ``plugins`` entry itself works from either format; only
   this option requires an INI file to override.


What the plugin understands
---------------------------

* The ``preset=<Preset>`` form — resolved to the keywords of the referenced ``Preset(...)``
  definition — and the explicit-keyword form (``view_name=...``, ``access_modes=(...)``,
  ``all_optional``, ``all_nullable``, ``include_computed_fields``). An explicit keyword passed
  alongside ``preset`` overrides the preset's value.
* Nested models, recursively and through ``list`` / ``set`` / ``tuple`` / ``dict`` / unions: a field
  referencing another model is typed with that model's generated view (``Address`` + ``Load`` ->
  ``AddressLoad``).

A few things cannot be recovered statically:

* The ``**LoadPreset._asdict()`` splat — mypy discards ``**`` unpackings in class keywords. Use
  ``preset=LoadPreset`` or explicit keywords instead.
* Field-level :class:`~pydantic_views.AccessTag` filtering (``include_tags`` / ``exclude_tags``):
  the tags live in ``Annotated`` runtime values that mypy drops.
* A view must be declared in the **same module** as its source model, because mypy frees the
  annotations of imported modules.

These limits apply to the mypy plugin only. The runtime stub generator described below is not subject
to any of them, because it reads the views' real fields after import.


Generating stub files for other type checkers
==============================================

Type checkers that do not run mypy plugins (pyright, Pylance, PyCharm) see a view as an empty model
with an ``__init__(**data: Any)`` signature. Plain ``stubgen`` does not help either: it does not
execute mypy plugins, so it produces the same empty view.

pydantic-views ships its own stub generator, :mod:`pydantic_views.stubgen`, that solves this without
mypy. It **imports** the target module, inspects the views at runtime, and writes a ``.pyi`` stub
describing their real fields. Run it as a module, passing the importable name of the module to stub:

.. code-block:: console

   $ python -m pydantic_views.stubgen myapp.models
   wrote /path/to/myapp/models.pyi

By default the stub is written next to its source file (``models.py`` -> ``models.pyi``). Pass a
**package** name to walk every submodule, list **several modules** at once, and use ``-o`` /
``--output-dir`` to mirror the package tree into a separate directory instead of writing the stubs in
place:

.. code-block:: console

   $ python -m pydantic_views.stubgen myapp.models myapp.schemas --output-dir build/stubs

Wire either command into a pre-commit hook or a ``make`` target to keep the stubs in sync with your
models.


What the stub contains
----------------------

Because the generator works from the imported module, each stub is a **complete** description of that
module, not just its views:

* every regular class — plain classes, enums (including ones nested inside a model), and Pydantic
  models, with ``@computed_field`` properties rendered as read-only properties;
* every view declared in the module;
* every view **generated at runtime**, including the nested views built for referenced models
  (``Address`` + ``Load`` -> ``AddressLoad``);
* module-level functions, preserving PEP 695 type parameters.

Each view is emitted with its real field set and a keyword-only ``__init__``, so other type checkers
resolve attributes and constructor calls exactly as the mypy plugin would. For a model like:

.. code-block:: python

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password: WriteOnly[str]

   class AccountLoad(View[Account], preset=LoadPreset):
       pass

the generator emits both the model and the view:

.. code-block:: python

   class Account(BaseModel):
       id: int
       username: str
       password: str
       def __init__(self, *, id: int, username: str, password: str) -> None: ...

   class AccountLoad(View[Account]):
       id: int
       username: str
       def __init__(self, *, id: int, username: str) -> None: ...

Reproducing the whole module is deliberate: a type checker treats an adjacent ``<module>.pyi`` as the
complete description of the module and ignores the ``.py``, so a stub that listed only the views would
hide every other symbol. Because the generator emits the regular classes, models, functions and views
together, you can point it at any module — there is no need to isolate views in a dedicated module.

Because it reflects the runtime model rather than a static analysis, the generator also captures the
views the mypy plugin cannot recover: those built with the ``**Preset._asdict()`` splat, views
declared in a different module from their source model, and
:class:`~pydantic_views.AccessTag` ``include_tags`` / ``exclude_tags`` filtering.

A runnable reference that stubs the bundled example models and verifies the generated field sets
against the runtime ``model_fields`` lives in
`examples/generate_stubs.py <https://github.com/alfred82santa/pydantic-views/blob/main/examples/generate_stubs.py>`_.
