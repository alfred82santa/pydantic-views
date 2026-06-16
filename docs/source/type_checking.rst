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


Generating stub files for other type checkers
==============================================

Type checkers that do not run mypy plugins (pyright, Pylance, PyCharm) see a view as an empty model
with an ``__init__(**data: Any)`` signature. Plain ``stubgen`` does not help either: it does not
execute mypy plugins, so it produces the same empty view.

The reliable approach is to drive mypy's build API **with the plugin enabled**, read the synthesised
``__init__`` of each view, and write a ``.pyi`` stub from it. pydantic-views does not ship a console
command for this, but the generator is small enough to keep as a script in your project. Save the
following as, for example, ``gen_view_stubs.py``:

.. code-block:: python

   """Generate a .pyi stub of pydantic-views views, using the mypy plugin."""

   from __future__ import annotations

   import argparse
   from pathlib import Path

   from mypy import build
   from mypy.modulefinder import BuildSource
   from mypy.nodes import FuncDef, TypeInfo
   from mypy.options import Options
   from mypy.types import CallableType, Instance, get_proper_type

   from pydantic_views.mypy import ROOTVIEW_FULLNAME, VIEW_FULLNAME

   def render(typ) -> str:
       typ = get_proper_type(typ)
       if isinstance(typ, Instance):
           if typ.args:
               return f"{typ.type.name}[{', '.join(render(a) for a in typ.args)}]"
           return typ.type.name
       return "Any" if typ is None else str(typ)

   def stub_for(info: TypeInfo) -> str:
       # The plugin synthesises an __init__ whose keyword-only parameters are exactly the view's
       # fields (source-model fields kept by the access rules, plus any declared on the view body).
       lines = [f"class {info.name}(View[{render(info.bases[0].args[0])}]):"]
       init = info.names.get("__init__")
       if init and isinstance(init.node, FuncDef) and isinstance(init.node.type, CallableType):
           sig = init.node.type
           for name, typ, kind in zip(sig.arg_names, sig.arg_types, sig.arg_kinds):
               if name in (None, "self", "__pydantic_self__") or kind.is_star():
                   continue
               default = " = ..." if kind.is_optional() else ""
               lines.append(f"    {name}: {render(typ)}{default}")
       return "\n".join(lines)

   def main() -> None:
       parser = argparse.ArgumentParser(description=__doc__)
       parser.add_argument("--module", required=True, help="dotted module that declares the views")
       parser.add_argument("--source", required=True, type=Path, help="path to that module's .py file")
       parser.add_argument("--config", required=True, type=Path, help="mypy config (its [pydantic-views-mypy] options are honoured)")
       parser.add_argument("--root", type=Path, default=Path.cwd(), help="import root (default: current directory)")
       parser.add_argument("--output", type=Path, help="stub path (default: --source with a .pyi suffix)")
       args = parser.parse_args()

       options = Options()
       # build.build() does NOT read the config file for the plugin list, so set it explicitly
       # (pydantic_views.mypy must come before pydantic.mypy):
       options.plugins = ["pydantic_views.mypy", "pydantic.mypy"]
       options.config_file = str(args.config.resolve())
       options.incremental = False
       options.namespace_packages = True
       options.explicit_package_bases = True
       options.mypy_path = [str(args.root.resolve())]  # absolute paths; relative ones break resolution
       result = build.build([BuildSource(str(args.source.resolve()), args.module, None)], options)

       tree = result.graph[args.module].tree
       if tree is None:
           raise SystemExit(f"mypy did not analyse {args.module!r}")

       blocks = ["from typing import Any, Literal\n\nfrom pydantic_views import View\n"]
       for sym in tree.names.values():
           node = sym.node
           if (
               isinstance(node, TypeInfo)
               and node.has_base(VIEW_FULLNAME)
               and node.fullname not in (VIEW_FULLNAME, ROOTVIEW_FULLNAME)
           ):
               blocks.append(stub_for(node))

       out = args.output or args.source.with_suffix(".pyi")
       out.write_text("\n\n".join(blocks) + "\n")
       print(f"wrote {out}")

   if __name__ == "__main__":
       main()

Run it from the command line, pointing it at the module that declares your views, that module's
file, and your mypy config:

.. code-block:: console

   $ python gen_view_stubs.py \
       --module myapp.models \
       --source src/myapp/models.py \
       --config mypy.ini \
       --root src \
       --output src/myapp/models.pyi
   wrote src/myapp/models.pyi

Drop the ``--output`` flag to write the stub next to ``--source`` (``models.py`` -> ``models.pyi``),
and adjust ``--root`` to whatever directory is on your import path (often ``.`` or ``src``). Wire the
command into a pre-commit hook or a ``make`` target to keep the stub in sync with your models.

For a model like:

.. code-block:: python

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password: WriteOnly[str]

   class AccountLoad(View[Account], preset=LoadPreset):
       pass

the script emits a stub that other type checkers can read:

.. code-block:: python

   class AccountLoad(View[Account]):
       id: int
       username: str
       def __init__(self, *, id: int, username: str) -> None: ...

.. warning::

   A type checker treats an adjacent ``<module>.pyi`` as the **complete** description of the module
   and ignores the ``.py`` entirely. A stub that contains only the views would therefore hide every
   other symbol (the source models, functions, constants, …). To avoid that, either:

   * declare your views in a **dedicated module** (e.g. ``views.py``) so its ``views.pyi`` only needs
     to describe the views, or
   * generate the rest of the module with ``stubgen`` first and splice the view classes from the
     script into that complete stub.

A complete, working reference — including readable type rendering, nested views, and a check that the
stub's field set matches the runtime ``model_fields`` — lives in
`examples/generate_stubs.py <https://github.com/alfred82santa/pydantic-views/blob/main/examples/generate_stubs.py>`_.
