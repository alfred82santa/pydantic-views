"""
End-to-end coverage for plugin branches that only fire during a real mypy build: ``RootView``
subclasses, views without ``view_name`` / ``access_modes``, ``ClassVar`` and shadowing fields on the
view body, tuple-of-model fields, and the ``init_forbid_extra = false`` configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mypy import build
from mypy.modulefinder import BuildSource
from mypy.nodes import ArgKind, FuncDef, TypeInfo
from mypy.options import Options
from mypy.types import CallableType

ROOT = Path(__file__).resolve().parent.parent

SOURCE = """
from typing import ClassVar
from pydantic import BaseModel, RootModel, computed_field
from pydantic_views import View, RootView, AccessMode, ReadOnly, WriteOnly


class Inner(BaseModel):
    a: int
    b: ReadOnly[str]


class Holder(BaseModel):
    inner: Inner
    pair: tuple[Inner, int]
    name: str
    secret: WriteOnly[str]

    @computed_field()
    def label(self) -> str:
        return self.name


class Bag(RootModel[list[Inner]]):
    pass


# RootView subclass: not a concrete View[Model] -> left untouched, no crash.
class BagView(RootView[Bag], view_name="BagView"):
    pass


# No view_name: nested fields keep the source model type (no nested view names can be derived).
class HolderNoName(View[Holder], access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY)):
    pass


class HolderLoad(
    View[Holder],
    view_name="Load",
    access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
    include_computed_fields=True,
):
    registry: ClassVar[dict[str, int]] = {}   # ClassVar -> not a field
    name: str                                 # shadows the source field
    extra: int = 0                            # view-only field
"""


def _build(tmp_path: Path, *, init_forbid_extra: bool = True):
    (tmp_path / "covmod.py").write_text(SOURCE)
    ini = tmp_path / "mypy.ini"
    ini_text = "[mypy]\nplugins = pydantic_views.mypy, pydantic.mypy\n"
    if not init_forbid_extra:
        ini_text += "[pydantic-views-mypy]\ninit_forbid_extra = false\n"
    ini.write_text(ini_text)

    options = Options()
    options.plugins = ["pydantic_views.mypy", "pydantic.mypy"]
    options.config_file = str(ini)
    options.incremental = False
    options.namespace_packages = True
    options.explicit_package_bases = True
    options.mypy_path = [str(tmp_path)]
    result = build.build([BuildSource(str(tmp_path / "covmod.py"), "covmod", None)], options=options)
    tree = result.graph["covmod"].tree
    assert tree is not None
    return result, tree


def _init_args(info: TypeInfo) -> dict[str, ArgKind]:
    """Map each named ``__init__`` argument to its kind (skipping self)."""
    sym = info.names.get("__init__")
    assert sym is not None and isinstance(sym.node, FuncDef)
    assert isinstance(sym.node.type, CallableType)
    callable_type = sym.node.type
    out: dict[str, ArgKind] = {}
    for name, kind in zip(callable_type.arg_names, callable_type.arg_kinds, strict=False):
        if name is None or name in ("self", "__pydantic_self__"):
            continue
        out[name] = kind
    return out


def _field_type_str(info: TypeInfo, field: str) -> str:
    sym = info.names.get(field)
    assert sym is not None, f"{field} missing on {info.name}"
    return str(sym.node.type)  # type: ignore[union-attr]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("cov"))


def test_rootview_subclass_left_untouched(built):
    _, tree = built
    info = tree.names["BagView"].node
    assert isinstance(info, TypeInfo)
    # The plugin must not have added model fields to a RootView subclass.
    assert "inner" not in info.names


def test_view_without_view_name_keeps_source_model_types(built):
    _, tree = built
    info = tree.names["HolderNoName"].node
    assert isinstance(info, TypeInfo)
    # With no view_name, nested models are NOT replaced by synthesised views.
    assert "covmod.Inner" in _field_type_str(info, "inner")
    assert "HolderNoNameInner" not in tree.names


def test_nested_views_and_containers_are_synthesised(built):
    _, tree = built
    info = tree.names["HolderLoad"].node
    assert isinstance(info, TypeInfo)
    # Nested model -> nested view; tuple element model -> nested view too.
    assert "InnerLoad" in _field_type_str(info, "inner")
    pair = _field_type_str(info, "pair")
    assert pair.startswith("tuple[") and "InnerLoad" in pair
    # The synthesised nested view lives in the model's module.
    assert isinstance(tree.names["InnerLoad"].node, TypeInfo)


def test_computed_field_called_form_included(built):
    _, tree = built
    info = tree.names["HolderLoad"].node
    assert isinstance(info, TypeInfo)
    assert "label" in _init_args(info)


def test_classvar_excluded_and_view_field_kept(built):
    _, tree = built
    info = tree.names["HolderLoad"].node
    assert isinstance(info, TypeInfo)
    args = _init_args(info)
    assert "registry" not in args  # ClassVar is not a field
    assert "extra" in args  # view-only field is a field
    assert "name" in args  # shadowing field present exactly once


def test_write_only_field_excluded_from_read_view(built):
    _, tree = built
    info = tree.names["HolderLoad"].node
    assert isinstance(info, TypeInfo)
    assert "secret" not in _init_args(info)


def test_init_forbid_extra_false_adds_star_kwargs(tmp_path):
    _, tree = _build(tmp_path, init_forbid_extra=False)
    info = tree.names["HolderLoad"].node
    assert isinstance(info, TypeInfo)
    sym = info.names.get("__init__")
    assert isinstance(sym.node, FuncDef) and isinstance(sym.node.type, CallableType)
    assert ArgKind.ARG_STAR2 in sym.node.type.arg_kinds
