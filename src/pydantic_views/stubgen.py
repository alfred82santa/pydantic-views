"""
Generate ``.pyi`` stub files for a Python module (and its submodules) at runtime.

Unlike ``mypy.stubgen``, this generator imports the target module and introspects it directly.
That matters for :mod:`pydantic_views`: a static stub generator only sees the *declared* views as
empty ``BaseModel`` subclasses, because their fields are synthesised. By importing the module we can
read the real :pyattr:`~pydantic.BaseModel.model_fields` of every view, including the views generated
at runtime by the builders (for example the nested ``AddressLoad`` view created while building
``UserLoad``).

The emitted stub for each module contains:

* every regular class defined in the module (plain classes, enums, and Pydantic models);
* every view declared in the module source;
* every view generated at runtime for a model defined in the module;
* module-level functions.

Usage::

    python -m pydantic_views.stubgen examples.models
    python -m pydantic_views.stubgen examples.models --output-dir build/stubs

By default each ``.pyi`` is written next to its source ``.py``. With ``--output-dir`` the package
tree is mirrored under the given directory.
"""

from __future__ import annotations

import argparse
import collections.abc
import enum
import importlib
import inspect
import pkgutil
import sys
import types
import typing
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from .view import RootView, View

_EMPTY = inspect.Parameter.empty
_SIMPLE_LITERALS = (bool, int, str, bytes, type(None))

# Some classes are exposed from a public module that differs from their defining (private) module.
# Importing from the private location is valid, but the canonical public import reads better.
_CANONICAL_MODULES = {
    ("pydantic.main", "BaseModel"): "pydantic",
    ("pydantic.root_model", "RootModel"): "pydantic",
}

# A few classes report ``builtins`` as their module but a name that is not a builtin global
# (e.g. ``types.ModuleType.__qualname__`` is ``"module"``). Map them to their importable location.
_CANONICAL_TYPES = {
    types.ModuleType: ("types", "ModuleType"),
    types.FunctionType: ("types", "FunctionType"),
    types.MethodType: ("types", "MethodType"),
}


class Imports:
    """Accumulates the imports required to render a single module stub.

    References to names defined in the module being generated, and to builtins, are rendered bare;
    everything else is recorded as a ``from <module> import <name>`` statement.
    """

    def __init__(self, current_module: str) -> None:
        self._current_module = current_module
        self._from: dict[str, set[str]] = {}

    @property
    def current_module(self) -> str:
        """Name of the module whose stub is being generated."""
        return self._current_module

    def add(self, module: str, name: str) -> None:
        """Record ``from module import name`` unless it is local or a builtin."""
        if module in ("builtins", self._current_module) or not module:
            return
        self._from.setdefault(module, set()).add(name)

    def add_typing(self, name: str) -> None:
        """Record a name imported from :mod:`typing` (``Any``, ``Literal``, ...)."""
        self._from.setdefault("typing", set()).add(name)

    def ref(self, tp: type) -> str:
        """Return the rendered reference to a class, recording its import if needed.

        A parametrized generic subclass built by Pydantic carries a ``[...]`` suffix in its
        ``__qualname__`` (e.g. ``View[TypeVar]``); only the bare leading name is importable.
        """
        if tp in _CANONICAL_TYPES:
            module, name = _CANONICAL_TYPES[tp]
            self.add(module, name)
            return name
        name = tp.__qualname__.split("[", 1)[0]
        module = _CANONICAL_MODULES.get((tp.__module__, name), tp.__module__)
        self.add(module, name.split(".")[0])
        return name

    def render_block(self) -> str:
        """Return the import block, sorted for stable output."""
        lines: list[str] = []
        for module in sorted(self._from):
            names = ", ".join(sorted(self._from[module]))
            lines.append(f"from {module} import {names}")
        return "\n".join(lines)


def render_annotation(tp: Any, imports: Imports) -> str:
    """Render a runtime annotation object as stub-ready source text."""
    if tp is None or tp is type(None):
        return "None"
    if tp is Ellipsis:
        return "..."
    if tp is Any:
        imports.add_typing("Any")
        return "Any"
    if isinstance(tp, str):
        return tp
    if isinstance(tp, typing.ForwardRef):
        return tp.__forward_arg__
    if isinstance(tp, typing.TypeVar):
        return tp.__name__

    # ``Annotated[T, ...]``: keep ``T``, drop the metadata (access modes, validators, ...).
    if hasattr(tp, "__metadata__"):
        return render_annotation(tp.__origin__, imports)

    origin = get_origin(tp)
    if origin is not None:
        args = get_args(tp)
        if origin is typing.Union or origin is types.UnionType:
            return " | ".join(render_annotation(a, imports) for a in args)
        if origin is typing.Literal:
            imports.add_typing("Literal")
            return "Literal[" + ", ".join(repr(a) for a in args) + "]"
        if origin is collections.abc.Callable:
            imports.add("collections.abc", "Callable")
            params, ret = args[0], args[-1]
            if params is Ellipsis:
                rendered_params = "..."
            else:
                rendered_params = "[" + ", ".join(render_annotation(p, imports) for p in params) + "]"
            return f"Callable[{rendered_params}, {render_annotation(ret, imports)}]"
        base = imports.ref(origin) if isinstance(origin, type) else _render_special_form(origin, imports)
        if args:
            return f"{base}[{', '.join(render_annotation(a, imports) for a in args)}]"
        return base

    if isinstance(tp, type):
        return imports.ref(tp)

    return "Any"


def _render_special_form(origin: Any, imports: Imports) -> str:
    """Render a :mod:`typing` special form (``ClassVar``, ``Final``, ...) and record its import."""
    name = getattr(origin, "_name", None) or getattr(origin, "__name__", None)
    if getattr(origin, "__module__", None) == "typing" and name:
        imports.add_typing(name)
        return name
    return str(origin)


def _render_bases(cls: type, imports: Imports) -> str:
    """Render a class's base list, dropping ``object``/``Generic`` and parametrization suffixes.

    Pydantic builds concrete generic subclasses whose ``__qualname__`` contains a ``[...]`` suffix
    (e.g. ``RootModel[TypeVar]``); the bare class name is what is actually importable.
    """
    rendered: list[str] = []
    for base in cls.__bases__:
        if base is object or base is typing.Generic:
            continue
        rendered.append(imports.ref(base))
    return ", ".join(rendered) if rendered else "object"


def _is_concrete_view(cls: Any) -> bool:
    """True for a built view that exposes a resolvable source model (not the ``View`` base itself)."""
    if not (isinstance(cls, type) and issubclass(cls, View)) or cls in (View, RootView):
        return False
    try:
        cls.view_class_root()
    except Exception:
        return False
    return True


def _render_type_params(obj: Any, imports: Imports) -> str:
    """Render PEP 695 type parameters (``[T, U: Bound]``) for a class or function, or ``""``."""
    params = getattr(obj, "__type_params__", ())
    if not params:
        return ""
    rendered: list[str] = []
    for param in params:
        if isinstance(param, typing.ParamSpec):
            prefix = "**"
        elif isinstance(param, typing.TypeVarTuple):
            prefix = "*"
        else:
            prefix = ""
        text = f"{prefix}{param.__name__}"
        bound = getattr(param, "__bound__", None)
        constraints = getattr(param, "__constraints__", ())
        if bound is not None:
            text += f": {render_annotation(bound, imports)}"
        elif constraints:
            text += f": ({', '.join(render_annotation(c, imports) for c in constraints)})"
        rendered.append(text)
    return "[" + ", ".join(rendered) + "]"


def _render_def(name: str, func: Any, imports: Imports) -> str:
    """Render a ``def`` line (with type parameters) for a function or method."""
    return f"def {name}{_render_type_params(func, imports)}{_render_signature(func, imports)}: ..."


def _render_signature(func: Any, imports: Imports) -> str:
    """Best-effort render of a function/method signature for the stub."""
    try:
        # ``eval_str=True`` resolves the string annotations produced by ``from __future__ import
        # annotations`` into real objects, so they can be rendered with their imports recorded.
        sig = inspect.signature(func, eval_str=True)
    except (TypeError, ValueError, NameError):
        try:
            sig = inspect.signature(func)
        except (TypeError, ValueError):
            imports.add_typing("Any")
            return "(*args: Any, **kwargs: Any) -> Any"

    parts: list[str] = []
    for name, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            rendered = f"*{name}"
        elif param.kind is inspect.Parameter.VAR_KEYWORD:
            rendered = f"**{name}"
        else:
            rendered = name
            if param.annotation is not _EMPTY:
                rendered += f": {render_annotation(param.annotation, imports)}"
            if param.default is not _EMPTY:
                rendered += " = ..."
        parts.append(rendered)

    if sig.return_annotation is not _EMPTY:
        ret = render_annotation(sig.return_annotation, imports)
    else:
        ret = "None" if func.__name__ in ("__init__", "__new__") else "Any"
        if ret == "Any":
            imports.add_typing("Any")
    return f"({', '.join(parts)}) -> {ret}"


def _render_init(model: type[BaseModel], imports: Imports) -> str:
    """Render a keyword-only ``__init__`` from a model's fields."""
    params: list[str] = []
    for name, field in model.model_fields.items():
        rendered = f"{name}: {render_annotation(field.annotation, imports)}"
        if not field.is_required():
            rendered += " = ..."
        params.append(rendered)
    signature = ", ".join(["self", "*", *params]) if params else "self"
    return f"    def __init__({signature}) -> None: ..."


def _render_model(cls: type[BaseModel], imports: Imports) -> str:
    """Render a stub for a Pydantic model or view."""
    if _is_concrete_view(cls):
        view_base = "RootView" if issubclass(cls, RootView) else "View"
        imports.add("pydantic_views", view_base)
        base = f"{view_base}[{render_annotation(cls.view_class_root(), imports)}]"  # type: ignore
    else:
        base = _render_bases(cls, imports)

    lines = [f"class {cls.__name__}{_render_type_params(cls, imports)}({base}):"]
    for name, field in cls.model_fields.items():
        lines.append(f"    {name}: {render_annotation(field.annotation, imports)}")

    # Computed fields are not declared in ``model_fields``; expose them as read-only properties.
    # (View builders fold computed fields into ``model_fields`` already, so this only fires for
    # regular models.)
    for name, computed in cls.model_computed_fields.items():
        lines.append("    @property")
        lines.append(f"    def {name}(self) -> {render_annotation(computed.return_type, imports)}: ...")

    lines.append(_render_init(cls, imports))
    return "\n".join(lines)


def _render_enum(cls: type[enum.Enum], imports: Imports) -> str:
    lines = [f"class {cls.__name__}{_render_type_params(cls, imports)}({_render_bases(cls, imports)}):"]
    for member in cls:
        value = repr(member.value) if isinstance(member.value, _SIMPLE_LITERALS) else "..."
        lines.append(f"    {member.name} = {value}")
    return "\n".join(lines)


def _render_plain_class(cls: type, imports: Imports) -> str:
    base = _render_bases(cls, imports)
    name = f"{cls.__name__}{_render_type_params(cls, imports)}"
    header = f"class {name}:" if base == "object" else f"class {name}({base}):"
    lines = [header]

    annotations = getattr(cls, "__annotations__", {})
    for name, annotation in annotations.items():
        lines.append(f"    {name}: {render_annotation(annotation, imports)}")

    for name, member in vars(cls).items():
        if name.startswith("__") and name not in ("__init__", "__call__"):
            continue
        if isinstance(member, (staticmethod, classmethod)):
            decorator = "staticmethod" if isinstance(member, staticmethod) else "classmethod"
            lines.append(f"    @{decorator}")
            lines.append(f"    {_render_def(name, member.__func__, imports)}")
        elif inspect.isfunction(member):
            lines.append(f"    {_render_def(name, member, imports)}")
        elif isinstance(member, property) and member.fget is not None:
            lines.append("    @property")
            lines.append(f"    {_render_def(name, member.fget, imports)}")

    if len(lines) == 1:
        lines.append("    ...")
    return "\n".join(lines)


def _nested_classes(cls: type, imports: Imports) -> list[type]:
    """Return the classes defined inside ``cls`` (e.g. a nested enum), in definition order.

    A class is considered genuinely nested only when its ``__qualname__`` is ``<cls>.<name>`` and it
    belongs to the module being generated; this excludes classes merely assigned as attributes.
    """
    return [
        member
        for member in vars(cls).values()
        if isinstance(member, type)
        and member.__module__ == imports.current_module
        and member.__qualname__ == f"{cls.__qualname__}.{member.__name__}"
    ]


def _inject_nested(cls: type, rendered: str, imports: Imports) -> str:
    """Insert the (recursively rendered) nested-class definitions after ``cls``'s header line."""
    nested = _nested_classes(cls, imports)
    if not nested:
        return rendered
    indented = "\n\n".join(
        "\n".join(f"    {line}" if line.strip() else "" for line in _render_class(child, imports).split("\n"))
        for child in nested
    )
    header, _, body = rendered.partition("\n")
    return f"{header}\n{indented}" + (f"\n{body}" if body else "")


def _render_class(cls: type, imports: Imports) -> str:
    if issubclass(cls, BaseModel):
        rendered = _render_model(cls, imports)
    elif issubclass(cls, enum.Enum):
        rendered = _render_enum(cls, imports)
    else:
        rendered = _render_plain_class(cls, imports)
    return _inject_nested(cls, rendered, imports)


def _collect_runtime_views(module: types.ModuleType) -> list[type[View[Any]]]:
    """Collect views generated at runtime for models defined in ``module``.

    These views (e.g. the nested ``AddressLoad``) live in their source model's view manager but are
    never assigned as module attributes, so they would be missed by a plain ``vars(module)`` scan.
    """
    views: dict[str, type[View[Any]]] = {}
    for obj in vars(module).values():
        if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
            continue
        if obj.__module__ != module.__name__:
            continue
        manager = getattr(obj, "model_views", None)
        if manager is None:
            continue
        for view_cls in manager._views.values():
            # Skip Pydantic-internal parametrized generics such as ``View[Any]`` (their names are
            # not valid identifiers); keep only concrete, named views for this module.
            if (
                _is_concrete_view(view_cls)
                and view_cls.__module__ == module.__name__
                and view_cls.__name__.isidentifier()
                and "[" not in view_cls.__qualname__
            ):
                views[view_cls.__name__] = view_cls
    return list(views.values())


def render_module(module: types.ModuleType) -> str:
    """Render the full ``.pyi`` text for a single module."""
    imports = Imports(module.__name__)
    emitted: set[int] = set()
    blocks: list[str] = []
    functions: list[str] = []

    # 1. Members declared in the module, in definition order. Pydantic registers parametrized
    # generics (e.g. ``View[Any]``) as module attributes whose ``__name__`` is not a valid
    # identifier; those are implementation details and must be skipped.
    for obj in vars(module).values():
        if isinstance(obj, type) and obj.__module__ == module.__name__ and obj.__name__.isidentifier():
            blocks.append(_render_class(obj, imports))
            emitted.add(id(obj))
        elif inspect.isfunction(obj) and obj.__module__ == module.__name__:
            functions.append(_render_def(obj.__name__, obj, imports))

    # 2. Views generated at runtime that are not module attributes, sorted for stable output.
    runtime_views = [v for v in _collect_runtime_views(module) if id(v) not in emitted]
    for view_cls in sorted(runtime_views, key=lambda v: v.__name__):
        blocks.append(_render_model(view_cls, imports))
        emitted.add(id(view_cls))

    header = (
        "# Stub generated by pydantic_views.stubgen. Includes regular types, Pydantic models,\n"
        "# declared views, and views generated at runtime by the builders.\n"
    )
    import_block = imports.render_block()
    body = "\n\n\n".join([*blocks, *functions])
    sections = [header, import_block, body]
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


def iter_module_tree(module: types.ModuleType) -> list[types.ModuleType]:
    """Return ``module`` and, if it is a package, all of its importable submodules."""
    modules = [module]
    if hasattr(module, "__path__"):
        for info in pkgutil.walk_packages(module.__path__, prefix=f"{module.__name__}."):
            modules.append(importlib.import_module(info.name))
    return modules


def _output_path(module: types.ModuleType, output_dir: Path | None) -> Path:
    source = Path(module.__file__)  # type: ignore[arg-type]
    if output_dir is None:
        return source.with_suffix(".pyi")
    relative = Path(*module.__name__.split("."))
    if source.name == "__init__.py":
        relative = relative / "__init__"
    return (output_dir / relative).with_suffix(".pyi")


def generate(module_name: str, output_dir: Path | None = None) -> list[Path]:
    """Generate stubs for ``module_name`` and its children, returning the written paths."""
    root = importlib.import_module(module_name)
    written: list[Path] = []
    for module in iter_module_tree(root):
        if getattr(module, "__file__", None) is None:
            continue
        path = _output_path(module, output_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_module(module))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pydantic_views.stubgen",
        description="Generate .pyi stubs (including runtime-generated views) for a module and its children.",
    )
    parser.add_argument("module", help="Importable module name, e.g. examples.models")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to mirror the package tree into. Defaults to writing each .pyi next to its source.",
    )
    args = parser.parse_args(argv)

    if "" not in sys.path and "." not in sys.path:
        sys.path.insert(0, "")

    written = generate(args.module, args.output_dir)
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
