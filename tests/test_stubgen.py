"""Tests for :mod:`pydantic_views.stubgen`."""

from __future__ import annotations

import ast
import enum
import types
import typing
from abc import ABC
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, RootModel, computed_field

from pydantic_views import AccessMode, Builder, ReadOnly, RootView, View, WriteOnly
from pydantic_views import stubgen as stubgen_module
from pydantic_views.stubgen import (
    Imports,
    _inject_nested,
    _is_concrete_view,
    _module_assigned_names,
    _output_path,
    _render_bases,
    _render_enum,
    _render_init,
    _render_module_variables,
    _render_plain_class,
    _render_signature,
    _render_special_form,
    _render_type_params,
    _target_names,
    generate,
    iter_module_tree,
    load_modules,
    main,
    render_annotation,
    render_module,
)


# ---------------------------------------------------------------------------
# Module-level fixtures exercised by ``render_module`` and the helpers.
# ---------------------------------------------------------------------------
class Author(BaseModel):
    id: ReadOnly[int]
    name: str
    secret: WriteOnly[str]

    @computed_field
    def label(self) -> str:
        return self.name


class AuthorCreate(
    View[Author],
    view_name="Create",
    access_modes=(AccessMode.READ_AND_WRITE, AccessMode.WRITE_ONLY),
):
    pass


class AuthorLoad(
    View[Author],
    view_name="Load",
    access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
    include_computed_fields=True,
):
    pass


class Color(enum.Enum):
    RED = "red"
    PAIR = (1, 2)  # non-literal value -> rendered as ``...``


class Outer(BaseModel):
    class Inner(enum.Enum):
        A = "a"

    kind: Inner
    value: int


# A generic model and a concrete subclass, to check that the parametrized base is preserved.
class Container[T: BaseModel](BaseModel):
    items: list[T]
    total: int


class AuthorContainer(Container[Author]):
    pass


# A plain (non-Pydantic, non-enum) class with every member kind.
class Plain:
    attr: int

    def method(self, a: int) -> str: ...

    @staticmethod
    def stat(a: int) -> None: ...

    @classmethod
    def cls_method(cls) -> None: ...

    @property
    def prop(self) -> int: ...

    def __init__(self, a: int): ...  # no return annotation -> ``None``


class Empty:
    pass


# PEP 695 generic functions covering each kind of type parameter.
def plain_generic[T](x: T) -> T: ...


def bound_generic[T: int](x): ...


def constrained_generic[T: (int, str)](x): ...


def paramspec_generic[**P](x): ...


def typevartuple_generic[*Ts](x): ...


def returns_int() -> int: ...


def varargs(*args, **kwargs): ...


def with_default(a, b=1): ...


def future_unresolved(
    x: _UndefinedRuntimeName,  # noqa: F821 # type: ignore
) -> None: ...  # noqa: F821  -- string annotation only


# Module-level variables exercised by the variable renderer.
MODULE_CONSTANT: int = 7  # annotated -> uses the annotation
inferred_constant = Color.RED  # unannotated -> type inferred from the runtime value
unpacked_a, unpacked_b = 1, 2  # tuple-unpacked assignment
module_lambda = lambda x: x  # noqa: E731  -- emitted as a function, not a variable


@pytest.fixture
def imports() -> Imports:
    return Imports("tests.test_stubgen")


@pytest.fixture
def stub() -> str:
    import tests.test_stubgen as module

    return render_module(module)


def _parse(stub: str) -> ast.Module:
    """Parsing succeeds only if the generated stub is syntactically valid Python."""
    return ast.parse(stub)


def _class_names(stub: str) -> set[str]:
    return {node.name for node in ast.walk(_parse(stub)) if isinstance(node, ast.ClassDef)}


# ---------------------------------------------------------------------------
# render_annotation
# ---------------------------------------------------------------------------
def test_render_annotation_scalars(imports: Imports) -> None:
    assert render_annotation(None, imports) == "None"
    assert render_annotation(type(None), imports) == "None"
    assert render_annotation(..., imports) == "..."
    assert render_annotation(Any, imports) == "Any"
    assert render_annotation(int, imports) == "int"


def test_render_annotation_string_and_forwardref(imports: Imports) -> None:
    assert render_annotation("SomeName", imports) == "SomeName"
    assert render_annotation(typing.ForwardRef("Fwd"), imports) == "Fwd"


def test_render_annotation_typevar(imports: Imports) -> None:
    tv = typing.TypeVar("MyVar")
    assert render_annotation(tv, imports) == "MyVar"


def test_render_annotation_annotated_strips_metadata(imports: Imports) -> None:
    assert render_annotation(typing.Annotated[int, "meta"], imports) == "int"


def test_render_annotation_union_and_containers(imports: Imports) -> None:
    assert render_annotation(str | None, imports) == "str | None"
    assert render_annotation(int | str, imports) == "int | str"
    assert render_annotation(list[int], imports) == "list[int]"
    assert render_annotation(dict[str, int], imports) == "dict[str, int]"


def test_render_annotation_literal(imports: Imports) -> None:
    assert render_annotation(Literal["a", "b"], imports) == "Literal['a', 'b']"


def test_render_annotation_callable(imports: Imports) -> None:
    assert render_annotation(Callable[[int, str], bool], imports) == "Callable[[int, str], bool]"
    assert render_annotation(Callable[..., int], imports) == "Callable[..., int]"


def test_render_annotation_classvar_special_form(imports: Imports) -> None:
    assert render_annotation(ClassVar[int], imports) == "ClassVar[int]"
    assert "from typing import ClassVar" in imports.render_block()


def test_render_annotation_generic_without_args(imports: Imports) -> None:
    # ``typing.List`` has list as origin but no args -> renders the bare base name.
    assert render_annotation(typing.List, imports) == "list"  # noqa: UP006


def test_render_annotation_unknown_falls_back_to_any(imports: Imports) -> None:
    assert render_annotation(42, imports) == "Any"


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
def test_imports_current_module() -> None:
    assert Imports("a.b").current_module == "a.b"


def test_imports_canonical_module(imports: Imports) -> None:
    assert imports.ref(BaseModel) == "BaseModel"
    assert "from pydantic import BaseModel" in imports.render_block()


def test_imports_canonical_type(imports: Imports) -> None:
    assert imports.ref(types.ModuleType) == "ModuleType"
    assert "from types import ModuleType" in imports.render_block()


def test_imports_skips_local_and_builtins() -> None:
    imp = Imports("builtins")
    imp.add("builtins", "int")
    imp.add("", "weird")
    assert imp.render_block() == ""


# ---------------------------------------------------------------------------
# _render_special_form
# ---------------------------------------------------------------------------
def test_render_special_form_non_typing(imports: Imports) -> None:
    assert _render_special_form(123, imports) == "123"


# ---------------------------------------------------------------------------
# _render_bases / _is_concrete_view
# ---------------------------------------------------------------------------
def test_render_bases_object_when_no_real_bases(imports: Imports) -> None:
    assert _render_bases(Empty, imports) == "object"


def test_is_concrete_view_false_for_base_and_non_view() -> None:
    assert _is_concrete_view(View) is False
    assert _is_concrete_view(RootView) is False
    assert _is_concrete_view(int) is False
    assert _is_concrete_view(AuthorCreate) is True


def test_is_concrete_view_false_when_root_unresolvable() -> None:
    # An abstract View subclass never gets ``__model_class_root__`` set, so ``view_class_root``
    # raises and the helper must report it is not a concrete view.
    class Broken(View, ABC):
        pass

    assert _is_concrete_view(Broken) is False


# ---------------------------------------------------------------------------
# _render_type_params
# ---------------------------------------------------------------------------
def test_render_type_params_none(imports: Imports) -> None:
    assert _render_type_params(returns_int, imports) == ""


def test_render_type_params_plain_bound_constrained(imports: Imports) -> None:
    assert _render_type_params(plain_generic, imports) == "[T]"
    assert _render_type_params(bound_generic, imports) == "[T: int]"
    assert _render_type_params(constrained_generic, imports) == "[T: (int, str)]"


def test_render_type_params_paramspec_and_typevartuple(imports: Imports) -> None:
    assert _render_type_params(paramspec_generic, imports) == "[**P]"
    assert _render_type_params(typevartuple_generic, imports) == "[*Ts]"


# ---------------------------------------------------------------------------
# _render_signature
# ---------------------------------------------------------------------------
def test_render_signature_varargs(imports: Imports) -> None:
    assert _render_signature(varargs, imports) == "(*args, **kwargs) -> Any"


def test_render_signature_default_and_unannotated(imports: Imports) -> None:
    assert _render_signature(with_default, imports) == "(a, b = ...) -> Any"


def test_render_signature_return_annotation(imports: Imports) -> None:
    assert _render_signature(returns_int, imports) == "() -> int"


def test_render_signature_eval_failure_falls_back_to_strings(imports: Imports) -> None:
    # ``eval_str=True`` raises NameError (annotation references an undefined name); the fallback
    # keeps the raw string annotation.
    assert _render_signature(future_unresolved, imports) == "(x: _UndefinedRuntimeName) -> None"


def test_render_signature_uncallable_uses_safe_fallback(imports: Imports) -> None:
    assert _render_signature(42, imports) == "(*args: Any, **kwargs: Any) -> Any"


# ---------------------------------------------------------------------------
# _render_init / _render_model
# ---------------------------------------------------------------------------
def test_render_init_no_fields(imports: Imports) -> None:
    class NoFields(BaseModel):
        pass

    assert _render_init(NoFields, imports) == "    def __init__(self) -> None: ..."


def test_render_model_view_and_computed_property(stub: str) -> None:
    tree = _parse(stub)
    author = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Author")
    # the computed field is rendered as a read-only property
    props = [n for n in author.body if isinstance(n, ast.FunctionDef) and n.name == "label"]
    assert props and any(isinstance(d, ast.Name) and d.id == "property" for d in props[0].decorator_list)


def test_render_model_rootview_base() -> None:
    import sys

    class IntRoot(RootModel[int]):
        pass

    view = Builder("Load", access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY)).build_view(IntRoot)
    # The builder sets the view as a module attribute; remove it so it does not pollute the module
    # namespace and corrupt subsequent stubs rendered from this module.
    sys.modules[IntRoot.__module__].__dict__.pop(view.__name__, None)
    imports = Imports(IntRoot.__module__)
    from pydantic_views.stubgen import _render_model

    rendered = _render_model(view, imports)
    assert rendered.startswith("class IntRootLoad(RootView[")
    assert _is_concrete_view(view)


def test_generic_model_and_subclass_preserve_parametrization(stub: str) -> None:
    tree = _parse(stub)

    generic = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Container")
    assert ast.unparse(generic.type_params[0]) == "T: BaseModel"  # PEP 695 type parameter kept

    subclass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AuthorContainer")
    assert ast.unparse(subclass.bases[0]) == "Container[Author]"  # parametrized base kept


# ---------------------------------------------------------------------------
# _render_enum
# ---------------------------------------------------------------------------
def test_render_enum_simple_and_complex_values(imports: Imports) -> None:
    rendered = _render_enum(Color, imports)
    assert "RED = 'red'" in rendered
    assert "PAIR = ..." in rendered  # tuple value is not a simple literal


# ---------------------------------------------------------------------------
# _render_plain_class
# ---------------------------------------------------------------------------
def test_render_plain_class_all_members(imports: Imports) -> None:
    rendered = _render_plain_class(Plain, imports)
    assert "attr: int" in rendered
    assert "def method(self, a: int) -> str: ..." in rendered
    assert "@staticmethod" in rendered
    assert "@classmethod" in rendered
    assert "@property" in rendered
    assert "def __init__(self, a: int) -> None: ..." in rendered  # missing return -> None


def test_render_plain_class_empty(imports: Imports) -> None:
    assert _render_plain_class(Empty, imports) == "class Empty:\n    ..."


# ---------------------------------------------------------------------------
# _inject_nested
# ---------------------------------------------------------------------------
def test_inject_nested_renders_inner_class(stub: str) -> None:
    tree = _parse(stub)
    outer = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Outer")
    assert any(isinstance(n, ast.ClassDef) and n.name == "Inner" for n in outer.body)


def test_inject_nested_no_children_returns_unchanged(imports: Imports) -> None:
    assert _inject_nested(Empty, "class Empty: ...", imports) == "class Empty: ..."


def test_inject_nested_single_line_header(imports: Imports) -> None:
    # ``rendered`` has no body line; the nested block is appended after the header only.
    result = _inject_nested(Outer, "class Outer(BaseModel): ...", imports)
    assert result.startswith("class Outer(BaseModel): ...")
    assert "    class Inner(Enum):" in result


# ---------------------------------------------------------------------------
# runtime-generated views (builder sets them as module attributes)
# ---------------------------------------------------------------------------
def test_stub_includes_builder_generated_view() -> None:
    import tests.test_stubgen as module
    from pydantic_views import BuilderUpdate

    BuilderUpdate().build_view(Author)
    assert "AuthorUpdate" in _class_names(render_module(module))


# ---------------------------------------------------------------------------
# render_module integration
# ---------------------------------------------------------------------------
def test_stub_is_valid_python(stub: str) -> None:
    _parse(stub)


def test_includes_regular_model_and_declared_views(stub: str) -> None:
    assert {"Author", "AuthorCreate", "AuthorLoad"} <= _class_names(stub)


def test_write_only_field_dropped_from_load_view(stub: str) -> None:
    tree = _parse(stub)
    load = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "AuthorLoad")
    annotated = {n.target.id for n in load.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert "secret" not in annotated
    assert {"id", "name", "label"} <= annotated


# ---------------------------------------------------------------------------
# Module-level variables
# ---------------------------------------------------------------------------
def _module_var_annotations(stub: str) -> dict[str, str]:
    tree = _parse(stub)
    return {
        node.target.id: ast.unparse(node.annotation)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


def test_target_names_handles_unpacking() -> None:
    assign = typing.cast(ast.Assign, ast.parse("a, (b, *c) = x").body[0])
    assert _target_names(assign.targets[0]) == ["a", "b", "c"]


def test_target_names_ignores_non_name_targets() -> None:
    assign = typing.cast(ast.Assign, ast.parse("obj.attr = 1").body[0])
    assert _target_names(assign.targets[0]) == []


def test_module_assigned_names_unreadable_source() -> None:
    module = types.ModuleType("bad_source_mod")
    module.__file__ = "/nonexistent/path/does_not_exist.py"
    assert _module_assigned_names(module) == []


def test_render_module_variables_handles_unresolvable_hints_and_missing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys

    source = (
        "from __future__ import annotations\n"
        "X: int = 1\n"
        "Y: UnresolvableName = 2  # forces get_type_hints to fail\n"
        "TEMP = 1\n"
        "del TEMP  # assigned in source but absent at runtime\n"
    )
    (tmp_path / "tmp_vars_mod.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = importlib.import_module("tmp_vars_mod")
    try:
        lines = _render_module_variables(module, Imports("tmp_vars_mod"), skip=set())
    finally:
        sys.modules.pop("tmp_vars_mod", None)

    assert "X: int" in lines  # resolved from the raw string annotation
    assert "Y: UnresolvableName" in lines
    assert not any(line.startswith("TEMP") for line in lines)  # value gone -> skipped


def test_module_assigned_names_excludes_imports_and_definitions() -> None:
    import tests.test_stubgen as module

    names = _module_assigned_names(module)
    assert {"MODULE_CONSTANT", "inferred_constant", "unpacked_a", "unpacked_b"} <= set(names)
    # imported names and class/function definitions are not assignments
    assert "BaseModel" not in names
    assert "Author" not in names
    assert "returns_int" not in names


def test_module_assigned_names_without_source() -> None:
    assert _module_assigned_names(types.ModuleType("no_source_mod")) == []


def test_stub_renders_module_variables(stub: str) -> None:
    annotations = _module_var_annotations(stub)
    assert annotations["MODULE_CONSTANT"] == "int"  # from the declared annotation
    assert annotations["inferred_constant"] == "Color"  # inferred from the runtime value
    assert annotations["unpacked_a"] == "int"
    assert annotations["unpacked_b"] == "int"


def test_module_variables_skip_emitted_names(imports: Imports) -> None:
    import tests.test_stubgen as module

    # ``module_lambda`` is emitted as a function, so it must not also appear as a variable.
    rendered = _render_module_variables(module, imports, skip={"module_lambda"})
    assert not any(line.startswith("module_lambda:") for line in rendered)


def test_stub_does_not_duplicate_lambda(stub: str) -> None:
    # rendered once as a function definition, never as a module variable
    assert "def module_lambda" in stub
    assert "module_lambda:" not in stub


# ---------------------------------------------------------------------------
# iter_module_tree / _output_path
# ---------------------------------------------------------------------------
def test_iter_module_tree_single_module() -> None:
    import examples.models as mod

    assert iter_module_tree(mod) == [mod]


def test_iter_module_tree_walks_package() -> None:
    import pydantic_views

    modules = iter_module_tree(pydantic_views)
    names = {m.__name__ for m in modules}
    assert "pydantic_views" in names
    assert "pydantic_views.builder" in names
    assert len(modules) > 1


def test_output_path_in_place() -> None:
    import examples.models as mod

    assert _output_path(mod, None) == Path(mod.__file__).with_suffix(".pyi")


def test_output_path_mirrored(tmp_path: Path) -> None:
    import examples.models as mod

    assert _output_path(mod, tmp_path) == tmp_path / "examples" / "models.pyi"


def test_output_path_package_init(tmp_path: Path) -> None:
    import pydantic_views

    assert _output_path(pydantic_views, tmp_path) == tmp_path / "pydantic_views" / "__init__.pyi"


# ---------------------------------------------------------------------------
# generate / main
# ---------------------------------------------------------------------------
def test_generate_writes_parsable_stub(tmp_path: Path) -> None:
    modules = list(load_modules("examples.models"))
    path = generate(modules[0], tmp_path)
    assert path == tmp_path / "examples" / "models.pyi"
    _parse(path.read_text())


def test_generate_whole_package_parses(tmp_path: Path) -> None:
    modules = list(load_modules("pydantic_views"))
    path = generate(modules[0], tmp_path)
    _parse(path.read_text())


def test_generate_skips_module_without_file(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("fake_namespace_pkg")  # a namespace-style module has no ``__file__``
    monkeypatch.setattr(stubgen_module.importlib, "import_module", lambda name: fake)
    monkeypatch.setattr(stubgen_module, "iter_module_tree", lambda module: [fake])
    modules = list(load_modules("fake_namespace_pkg"))
    assert modules == []


def test_main_returns_zero_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["examples.models", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "wrote" in capsys.readouterr().out
    assert (tmp_path / "examples" / "models.pyi").exists()


def test_main_when_cwd_already_on_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend("")  # exercise the branch where the cwd entry is already present
    assert main(["examples.models", "--output-dir", str(tmp_path)]) == 0
    capsys.readouterr()


def test_main_accepts_multiple_modules(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["examples.models", "tests.test_stubgen", "--output-dir", str(tmp_path)])
    assert code == 0
    assert "wrote" in capsys.readouterr().out
    assert (tmp_path / "examples" / "models.pyi").exists()
    assert (tmp_path / "tests" / "test_stubgen.pyi").exists()


def test_render_annotation_handles_common_constructs() -> None:
    imports = Imports("somewhere")
    assert render_annotation(int, imports) == "int"
    assert render_annotation(str | None, imports) == "str | None"
    assert render_annotation(list[int], imports) == "list[int]"
    assert render_annotation(dict[str, int], imports) == "dict[str, int]"
    assert render_annotation(Literal["a", "b"], imports) == "Literal['a', 'b']"
    assert render_annotation(None, imports) == "None"
