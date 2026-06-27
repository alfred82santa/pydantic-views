"""
Generate ``.pyi`` stubs for the example views *using mypy* (with the pydantic-views plugin enabled),
then cross-check the synthesised field lists against what the runtime builder actually produces.

``stubgen`` does not run mypy plugins, so a plain stub generation would show the views as empty
``**data: Any`` models. Instead this script drives mypy's build API with the plugin active, reads the
synthesised ``TypeInfo`` of each view, writes a ``.pyi`` reflecting the plugin's output, and asserts
that the plugin's field set equals ``set(view.model_fields)`` at runtime.

Usage::

    python examples/generate_stubs.py            # writes examples/stubs/*.pyi and verifies
"""

from __future__ import annotations

import sys
from pathlib import Path

from mypy import build
from mypy.modulefinder import BuildSource
from mypy.nodes import FuncDef, TypeInfo
from mypy.options import Options
from mypy.types import (
    AnyType,
    CallableType,
    Instance,
    LiteralType,
    NoneType,
    TupleType,
    Type,
    UnionType,
    get_proper_type,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODULE = "examples.models"
VIEW_NAMES = [
    "UserCreate",
    "UserCreateResult",
    "UserUpdate",
    "UserLoad",
    "UserPatch",
    "UserSignup",
    "AccountCreate",
    "AccountLoad",
]


def render_type(typ: Type | None) -> str:
    """Render a mypy type as a short, readable annotation for a stub."""
    if typ is None:
        return "Any"
    typ = get_proper_type(typ)
    if isinstance(typ, AnyType):
        return "Any"
    if isinstance(typ, NoneType):
        return "None"
    if isinstance(typ, UnionType):
        return " | ".join(render_type(item) for item in typ.items)
    if isinstance(typ, LiteralType):
        return f"Literal[{typ.value!r}]"
    if isinstance(typ, TupleType):
        return f"tuple[{', '.join(render_type(a) for a in typ.items)}]"
    if isinstance(typ, Instance):
        name = typ.type.name
        if typ.last_known_value is not None:
            return render_type(typ.last_known_value)
        if typ.args:
            return f"{name}[{', '.join(render_type(a) for a in typ.args)}]"
        return name
    return str(typ)


def build_with_plugin() -> build.BuildResult:
    options = Options()
    options.plugins = ["pydantic_views.mypy", "pydantic.mypy"]
    options.config_file = str(HERE / "mypy.ini")
    options.incremental = False
    options.namespace_packages = True
    options.explicit_package_bases = True
    options.mypy_path = [str(ROOT)]
    source = BuildSource(str(HERE / "models.py"), MODULE, None)
    return build.build(sources=[source], options=options)


def stub_for_view(info: TypeInfo) -> tuple[str, list[str]]:
    """Return (stub text, field-name list) for a synthesised view ``TypeInfo``.

    Fields are read from the synthesised ``__init__`` signature, which the plugin builds from both the
    source-model fields *and* any regular pydantic fields declared on the view body — i.e. exactly the
    runtime ``model_fields``.
    """
    fields: list[tuple[str, str, bool]] = []  # (name, type, has_default)
    star_params: list[str] = []
    init = info.names.get("__init__")
    if init is not None and isinstance(init.node, FuncDef) and isinstance(init.node.type, CallableType):
        callable_type = init.node.type
        for arg_name, arg_type, arg_kind in zip(
            callable_type.arg_names,
            callable_type.arg_types,
            callable_type.arg_kinds,
            strict=False,
        ):
            if arg_name in (None, "self", "__pydantic_self__"):
                continue
            if arg_kind.is_star():
                star_params.append(f"**{arg_name}: Any")
                continue
            fields.append((arg_name, render_type(arg_type), arg_kind.is_optional()))

    base = info.bases[0]
    base_str = render_type(base) if base is not None else "object"

    lines = [f"class {info.name}({base_str}):"]
    for fname, ftype, _ in fields:
        lines.append(f"    {fname}: {ftype}")
    init_params = [f"{name}: {ftype}{' = ...' if opt else ''}" for name, ftype, opt in fields]
    init_sig = ", ".join(["self", "*", *init_params, *star_params]) if (init_params or star_params) else "self"
    lines.append(f"    def __init__({init_sig}) -> None: ...")
    return "\n".join(lines) + "\n", [name for name, _, _ in fields]


def collect_runtime_views() -> dict[str, set[str]]:
    """Map every runtime-built view name (top-level and nested) to its field set."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import inspect

    from pydantic import BaseModel

    from examples import models

    result: dict[str, set[str]] = {}
    for _, cls in inspect.getmembers(models, inspect.isclass):
        if cls.__module__ != models.__name__ or not issubclass(cls, BaseModel):
            continue
        manager = getattr(cls, "model_views", None)
        if manager is None:
            continue
        for view_cls in manager._views.values():
            if isinstance(view_cls, type):
                result[view_cls.__name__] = set(view_cls.model_fields.keys())
    return result


def collect_plugin_views(tree: object) -> dict[str, TypeInfo]:
    """Every view ``TypeInfo`` mypy ended up with: user-declared views plus synthesised nested ones."""
    from pydantic_views.mypy import ROOTVIEW_FULLNAME, VIEW_FULLNAME

    views: dict[str, TypeInfo] = {}
    for sym in tree.names.values():  # type: ignore[attr-defined]
        node = sym.node
        if (
            isinstance(node, TypeInfo)
            and node.fullname not in (VIEW_FULLNAME, ROOTVIEW_FULLNAME)
            and node.has_base(VIEW_FULLNAME)
        ):
            views[node.name] = node
    return views


def main() -> int:
    result = build_with_plugin()
    if result.errors:
        print("mypy build reported errors:")
        print("\n".join(result.errors))

    tree = result.graph[MODULE].tree
    assert tree is not None

    out_dir = HERE / "stubs"
    out_dir.mkdir(exist_ok=True)

    header = (
        '# Illustrative output: this is what the pydantic_views.mypy plugin makes mypy "see" for each\n'
        "# view. Nested-model fields use the generated nested views (e.g. AddressLoad), exactly as the\n"
        "# runtime builder produces them. Generated by examples/generate_stubs.py; not an importable stub.\n\n"
        "from typing import Any, Literal\n\n"
        "from pydantic_views import View\n\n"
    )

    runtime_views = collect_runtime_views()
    plugin_views = collect_plugin_views(tree)

    stub_blocks: list[str] = []
    ok = True

    print(f"{'view':<20}{'result':<10}plugin vs runtime")
    print("-" * 72)
    for name in sorted(plugin_views):
        info = plugin_views[name]
        stub_text, plugin_fields = stub_for_view(info)
        stub_blocks.append(stub_text)

        plugin_set = set(plugin_fields)
        runtime_set = runtime_views.get(name)
        if runtime_set is None:
            print(f"{name:<20}{'?':<10}(no runtime view to compare)")
            continue
        match = plugin_set == runtime_set
        ok = ok and match
        kind = "nested" if name not in VIEW_NAMES else "top"
        print(f"{name:<20}{('OK' if match else 'MISMATCH'):<10}[{kind}] {sorted(plugin_set)}")
        if not match:
            print(f"    only in plugin : {sorted(plugin_set - runtime_set)}")
            print(f"    only in runtime: {sorted(runtime_set - plugin_set)}")

    stub_path = out_dir / "models.pyi"
    stub_path.write_text(header + "\n\n".join(stub_blocks))
    print("-" * 72)
    print(f"wrote {stub_path.relative_to(ROOT)} ({len(plugin_views)} views: top-level + nested)")
    print("ALL VIEWS MATCH RUNTIME BUILDER" if ok else "FIELD SETS DIVERGED FROM RUNTIME")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
