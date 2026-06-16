"""
Unit tests for the pure helpers of ``pydantic_views.mypy``.

These build small mypy AST/type nodes directly and assert the helpers' behaviour, covering the
expression/annotation parsing branches without paying for a full mypy build.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from mypy.nodes import (
    ARG_NAMED,
    ARG_NAMED_OPT,
    AssignmentStmt,
    CallExpr,
    IntExpr,
    MemberExpr,
    NameExpr,
    StrExpr,
    TempNode,
    TupleExpr,
    Var,
)
from mypy.options import Options
from mypy.types import AnyType, NoneType, TypeOfAny, UnboundType, UnionType

from pydantic_views.mypy import (
    PYDANTIC_METADATA_KEY,
    VIEW_FULLNAME,
    _find_preset_call,
    _is_computed_field,
    _make_nullable,
    _modes_from_annotation,
    _normalise_preset_values,
    _preset_fullname,
    _preset_values_from_call,
    _preset_values_from_object,
    _read_access_modes,
    _read_bool,
    _read_init_forbid_extra,
    _ViewConfig,
    _ViewTransformer,
)


def _name(name: str, fullname: str | None = None) -> NameExpr:
    expr = NameExpr(name)
    if fullname is not None:
        expr.fullname = fullname
    return expr


# --- _modes_from_annotation ---------------------------------------------------------------------


def test_modes_from_annotation_non_unbound_type():
    assert _modes_from_annotation(NoneType()) == frozenset()


@pytest.mark.parametrize(
    ("alias", "mode"),
    [
        ("ReadAndWrite", "READ_AND_WRITE"),
        ("ReadOnly", "READ_ONLY"),
        ("WriteOnly", "WRITE_ONLY"),
        ("ReadOnlyOnCreation", "READ_ONLY_ON_CREATION"),
        ("WriteOnlyOnCreation", "WRITE_ONLY_ON_CREATION"),
        ("Hidden", "HIDDEN"),
    ],
)
def test_modes_from_annotation_alias(alias: str, mode: str):
    assert _modes_from_annotation(UnboundType(alias, [UnboundType("int")])) == frozenset({mode})


def test_modes_from_annotation_qualified_alias():
    # `pydantic_views.ReadOnly[str]` — only the trailing component is matched.
    assert _modes_from_annotation(UnboundType("pv.ReadOnly", [UnboundType("str")])) == frozenset({"READ_ONLY"})


def test_modes_from_annotation_unmarked_plain_type():
    assert _modes_from_annotation(UnboundType("int")) == frozenset()


def test_modes_from_annotation_annotated_members():
    annotated = UnboundType(
        "Annotated",
        [
            UnboundType("int"),
            UnboundType("AccessMode.READ_ONLY"),
            UnboundType("AccessMode.WRITE_ONLY_ON_CREATION"),
        ],
    )
    assert _modes_from_annotation(annotated) == frozenset({"READ_ONLY", "WRITE_ONLY_ON_CREATION"})


def test_modes_from_annotation_annotated_with_alias_member():
    # An access-mode *alias* used as an Annotated argument is mapped too.
    annotated = UnboundType("Annotated", [UnboundType("int"), UnboundType("ReadOnly")])
    assert _modes_from_annotation(annotated) == frozenset({"READ_ONLY"})


def test_modes_from_annotation_annotated_ignores_unknown_and_non_unbound():
    annotated = UnboundType("Annotated", [UnboundType("int"), NoneType(), UnboundType("Gt")])
    assert _modes_from_annotation(annotated) == frozenset()


# --- _read_access_modes -------------------------------------------------------------------------


def test_read_access_modes_none():
    assert _read_access_modes(None) is None


def test_read_access_modes_without_items_is_none():
    # e.g. someone passes a non-tuple expression.
    assert _read_access_modes(_name("AccessMode")) is None


def test_read_access_modes_tuple_mixes_member_name_and_junk():
    items = [
        MemberExpr(_name("AccessMode"), "READ_ONLY"),
        _name("WRITE_ONLY"),  # bare imported member
        _name("NOT_A_MODE"),  # ignored
        IntExpr(5),  # ignored
    ]
    assert _read_access_modes(TupleExpr(items)) == frozenset({"READ_ONLY", "WRITE_ONLY"})


def test_read_access_modes_empty_tuple():
    assert _read_access_modes(TupleExpr([])) == frozenset()


# --- _read_bool ---------------------------------------------------------------------------------


def test_read_bool_true():
    assert _read_bool(_name("True", "builtins.True")) is True


def test_read_bool_false():
    assert _read_bool(_name("False", "builtins.False")) is False


@pytest.mark.parametrize("expr", [None, StrExpr("x"), _name("something")])
def test_read_bool_non_true(expr: object):
    assert _read_bool(expr) is False


# --- _is_computed_field -------------------------------------------------------------------------


def test_is_computed_field_name():
    assert _is_computed_field(_name("computed_field")) is True


def test_is_computed_field_member():
    assert _is_computed_field(MemberExpr(_name("pydantic"), "computed_field")) is True


def test_is_computed_field_called_form():
    # `@computed_field()` — a CallExpr wrapping the decorator.
    assert _is_computed_field(CallExpr(_name("computed_field"), [], [], [])) is True


@pytest.mark.parametrize("expr", [_name("other"), IntExpr(1)])
def test_is_computed_field_not(expr: object):
    assert _is_computed_field(expr) is False


# --- _make_nullable -----------------------------------------------------------------------------


def test_make_nullable_wraps_plain_type():
    result = _make_nullable(AnyType(TypeOfAny.explicit))
    assert isinstance(result, UnionType)
    assert any(isinstance(item, NoneType) for item in result.items)


def test_make_nullable_none_type_unchanged():
    none = NoneType()
    assert _make_nullable(none) is none


def test_make_nullable_already_optional_union_unchanged():
    union = UnionType([AnyType(TypeOfAny.explicit), NoneType()])
    assert _make_nullable(union) is union


# --- _read_init_forbid_extra --------------------------------------------------------------------


def _options(config_file: str | None) -> Options:
    options = Options()
    options.config_file = config_file
    return options


def test_read_init_forbid_extra_no_config_file():
    assert _read_init_forbid_extra(_options(None)) is True


def test_read_init_forbid_extra_toml_falls_back_to_default(tmp_path):
    toml = tmp_path / "pyproject.toml"
    toml.write_text("[tool.pydantic-views-mypy]\ninit_forbid_extra = false\n")
    # TOML is not parsed for this option; default (True) is used.
    assert _read_init_forbid_extra(_options(str(toml))) is True


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False)])
def test_read_init_forbid_extra_ini_value(tmp_path, value: str, expected: bool):
    ini = tmp_path / "mypy.ini"
    ini.write_text(f"[mypy]\n[pydantic-views-mypy]\ninit_forbid_extra = {value}\n")
    assert _read_init_forbid_extra(_options(str(ini))) is expected


def test_read_init_forbid_extra_option_absent_defaults_true(tmp_path):
    ini = tmp_path / "mypy.ini"
    ini.write_text("[mypy]\nplugins = pydantic_views.mypy\n")
    assert _read_init_forbid_extra(_options(str(ini))) is True


def test_read_init_forbid_extra_malformed_ini_defaults_true(tmp_path):
    ini = tmp_path / "mypy.ini"
    ini.write_text("not a valid ini without a section header\n")
    assert _read_init_forbid_extra(_options(str(ini))) is True


# --- _ViewTransformer methods exercised with lightweight fakes ----------------------------------


def _transformer() -> _ViewTransformer:
    api = SimpleNamespace(anal_type=lambda t: t, final_iteration=True)
    ctx = SimpleNamespace(cls=SimpleNamespace(keywords={}), api=api)
    plugin = SimpleNamespace(init_forbid_extra=True)
    return _ViewTransformer(ctx, plugin)  # type: ignore[arg-type]


def _config(access_modes: frozenset[str] | None) -> _ViewConfig:
    return _ViewConfig(
        view_name="V",
        access_modes=access_modes,
        all_optional=False,
        all_nullable=False,
        include_computed_fields=False,
    )


def test_keep_no_access_modes_keeps_only_unmarked():
    config = _config(None)
    assert _ViewTransformer._keep(frozenset(), config) is True
    assert _ViewTransformer._keep(frozenset({"READ_ONLY"}), config) is False


def test_keep_with_access_modes():
    config = _config(frozenset({"READ_ONLY"}))
    assert _ViewTransformer._keep(frozenset({"READ_ONLY"}), config) is True
    assert _ViewTransformer._keep(frozenset({"WRITE_ONLY"}), config) is False
    assert _ViewTransformer._keep(frozenset(), config) is True  # unmarked always kept


def test_source_model_info_no_matching_base_returns_none():
    info = SimpleNamespace(bases=[SimpleNamespace(type=SimpleNamespace(fullname="x.Other"), args=[])])
    assert _ViewTransformer._source_model_info(info) is None  # type: ignore[arg-type]


def test_source_model_info_view_base_with_non_instance_arg_returns_none():
    # base is View[...] but the type argument is not a concrete Instance (e.g. a type var / Any).
    info = SimpleNamespace(
        bases=[SimpleNamespace(type=SimpleNamespace(fullname=VIEW_FULLNAME), args=[AnyType(TypeOfAny.explicit)])]
    )
    assert _ViewTransformer._source_model_info(info) is None  # type: ignore[arg-type]


def test_collect_field_modes_skips_entries_without_classdef():
    transformer = _transformer()
    model_info = SimpleNamespace(mro=[SimpleNamespace(defn=None)])
    assert transformer._collect_field_modes(model_info) == {}  # type: ignore[arg-type]


def test_collect_computed_fields_skips_entries_without_classdef():
    transformer = _transformer()
    model_info = SimpleNamespace(mro=[SimpleNamespace(defn=None)])
    assert transformer._collect_computed_fields(model_info) == {}  # type: ignore[arg-type]


def test_computed_return_type_falls_back_to_symbol():
    transformer = _transformer()
    typ = AnyType(TypeOfAny.explicit)
    model_info = SimpleNamespace(names={"label": SimpleNamespace(node=Var("label", typ))})
    decorator = SimpleNamespace(func=SimpleNamespace(name="label", type=None))
    assert transformer._computed_return_type(model_info, decorator) is typ  # type: ignore[arg-type]


def test_computed_return_type_defaults_to_any_when_unknown():
    transformer = _transformer()
    model_info = SimpleNamespace(names={})
    decorator = SimpleNamespace(func=SimpleNamespace(name="label", type=None))
    result = transformer._computed_return_type(model_info, decorator)  # type: ignore[arg-type]
    assert isinstance(result, AnyType)


def test_defer_calls_api_only_before_final_iteration():
    called: list[bool] = []
    api = SimpleNamespace(final_iteration=False, defer=lambda: called.append(True))
    ctx = SimpleNamespace(cls=SimpleNamespace(keywords={}), api=api)
    transformer = _ViewTransformer(ctx, SimpleNamespace(init_forbid_extra=True))  # type: ignore[arg-type]
    transformer._defer()
    assert called == [True]

    api.final_iteration = True
    transformer._defer()  # no further defer on the final iteration
    assert called == [True]


def test_synthesize_view_returns_none_when_module_missing():
    transformer = _transformer()
    transformer._api.modules = {}  # type: ignore[attr-defined]
    model_info = SimpleNamespace(name="X", module_name="missing.mod")
    assert transformer._synthesize_view(model_info, _config(None)) is None  # type: ignore[arg-type]


def test_synthesize_view_defers_when_nested_model_has_no_metadata():
    deferred: list[bool] = []
    transformer = _transformer()
    transformer._api.modules = {"m": SimpleNamespace(names={})}  # type: ignore[attr-defined]
    transformer._api.final_iteration = False  # type: ignore[attr-defined]
    transformer._api.defer = lambda: deferred.append(True)  # type: ignore[attr-defined]
    model_info = SimpleNamespace(name="X", module_name="m", metadata={})
    assert transformer._synthesize_view(model_info, _config(None)) is None  # type: ignore[arg-type]
    assert deferred == [True]


def test_transform_defers_when_source_metadata_missing(monkeypatch):
    deferred: list[bool] = []
    api = SimpleNamespace(final_iteration=False, defer=lambda: deferred.append(True))
    ctx = SimpleNamespace(cls=SimpleNamespace(keywords={}, info=SimpleNamespace(fullname="m.SomeView")), api=api)
    transformer = _ViewTransformer(ctx, SimpleNamespace(init_forbid_extra=True))  # type: ignore[arg-type]
    # A concrete source model is found, but it has not been processed by the pydantic plugin yet.
    monkeypatch.setattr(_ViewTransformer, "_source_model_info", staticmethod(lambda info: SimpleNamespace(metadata={})))
    transformer.transform()
    assert deferred == [True]


def test_populate_view_defers_when_source_metadata_missing():
    deferred: list[bool] = []
    transformer = _transformer()
    transformer._api.final_iteration = False  # type: ignore[attr-defined]
    transformer._api.defer = lambda: deferred.append(True)  # type: ignore[attr-defined]
    view_info = SimpleNamespace()
    model_info = SimpleNamespace(metadata={})
    transformer._populate_view(view_info, model_info, _config(None))  # type: ignore[arg-type]
    assert deferred == [True]


def test_populate_view_defers_and_falls_back_when_field_type_unresolved(monkeypatch):
    deferred: list[bool] = []
    transformer = _transformer()
    transformer._api.final_iteration = False  # type: ignore[attr-defined]
    transformer._api.defer = lambda: deferred.append(True)  # type: ignore[attr-defined]

    # A kept field whose serialized type has not resolved yet -> defer and fall back to ``Any``.
    class _UnresolvedField:
        @staticmethod
        def deserialize(info, data, api):
            return SimpleNamespace(type=None, has_default=False)

    added: list[tuple[str, object]] = []
    monkeypatch.setattr("pydantic_views.mypy.PydanticModelField", _UnresolvedField)
    monkeypatch.setattr("pydantic_views.mypy.add_method", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        _ViewTransformer,
        "_add_field",
        lambda self, info, name, field_type, **kwargs: added.append((name, field_type)),
    )

    model_info = SimpleNamespace(metadata={PYDANTIC_METADATA_KEY: {"fields": {"f": {}}}}, mro=[])
    view_info = SimpleNamespace(fullname="m.V", names={}, defn=SimpleNamespace(defs=SimpleNamespace(body=[])))
    transformer._populate_view(view_info, model_info, _config(None))  # type: ignore[arg-type]

    assert deferred == [True]
    # The field is still added, with the type falling back to ``Any``.
    assert len(added) == 1 and added[0][0] == "f"
    assert isinstance(added[0][1], AnyType)


def _assignment(name: str | None, *, annotated: bool, has_default: bool, lvalue=None) -> AssignmentStmt:
    rvalue = IntExpr(0) if has_default else TempNode(AnyType(TypeOfAny.explicit))
    target = lvalue if lvalue is not None else NameExpr(name or "x")
    stmt = AssignmentStmt([target], rvalue)
    if annotated:
        stmt.unanalyzed_type = UnboundType("int")
    return stmt


def _view_info(body, names):
    return SimpleNamespace(defn=SimpleNamespace(defs=SimpleNamespace(body=body)), names=names)


def test_own_field_arguments_skips_non_field_statements():
    transformer = _transformer()
    # Not annotated, multi-target, and non-NameExpr lvalues are all skipped.
    multi_target = AssignmentStmt([NameExpr("a"), NameExpr("b")], IntExpr(1))
    multi_target.unanalyzed_type = UnboundType("int")
    member_target = _assignment(None, annotated=True, has_default=True, lvalue=MemberExpr(NameExpr("self"), "x"))
    info = _view_info([_assignment("u", annotated=False, has_default=True), multi_target, member_target], names={})
    assert transformer._own_field_arguments(info) == []  # type: ignore[arg-type]


def test_own_field_arguments_skips_fields_without_resolved_type_and_defers():
    deferred: list[bool] = []
    transformer = _transformer()
    transformer._api.final_iteration = False  # type: ignore[attr-defined]
    transformer._api.defer = lambda: deferred.append(True)  # type: ignore[attr-defined]
    body = [_assignment("c", annotated=True, has_default=False)]
    info = _view_info(body, names={"c": SimpleNamespace(node=Var("c", None))})
    assert transformer._own_field_arguments(info) == []  # type: ignore[arg-type]
    assert deferred == [True]


def test_own_field_arguments_returns_required_and_optional():
    transformer = _transformer()
    typ = AnyType(TypeOfAny.explicit)
    body = [
        _assignment("required", annotated=True, has_default=False),
        _assignment("optional", annotated=True, has_default=True),
    ]
    names = {
        "required": SimpleNamespace(node=Var("required", typ)),
        "optional": SimpleNamespace(node=Var("optional", typ)),
    }
    result = dict(transformer._own_field_arguments(_view_info(body, names)))  # type: ignore[arg-type]
    assert result["required"].kind == ARG_NAMED
    assert result["optional"].kind == ARG_NAMED_OPT


# --- preset resolution --------------------------------------------------------------------------


def test_preset_fullname_prefers_node_fullname():
    expr = SimpleNamespace(node=SimpleNamespace(fullname="pkg.LoadPreset"), fullname="wrong.fallback")
    assert _preset_fullname(expr) == "pkg.LoadPreset"


def test_preset_fullname_falls_back_to_expr_fullname():
    assert _preset_fullname(_name("LoadPreset", "pkg.LoadPreset")) == "pkg.LoadPreset"


def test_preset_fullname_none_when_unresolved():
    assert _preset_fullname(SimpleNamespace(node=None)) is None


def test_normalise_preset_values_from_runtime_preset():
    from pydantic_views import LoadPreset

    values = _normalise_preset_values(LoadPreset._asdict())
    assert values == {
        "view_name": "Load",
        "access_modes": frozenset({"READ_AND_WRITE", "READ_ONLY"}),
        "all_optional": False,
        "all_nullable": False,
        "include_computed_fields": True,
    }


def test_normalise_preset_values_none_access_modes_omitted():
    values = _normalise_preset_values({"view_name": "X", "access_modes": None, "all_optional": True})
    assert "access_modes" not in values
    assert values == {"view_name": "X", "all_optional": True}


def test_normalise_preset_values_non_string_view_name_omitted():
    values = _normalise_preset_values({"view_name": None, "all_nullable": True})
    assert "view_name" not in values
    assert values == {"all_nullable": True}


def test_normalise_preset_values_rejects_non_mapping():
    assert _normalise_preset_values(("not", "a", "dict")) is None


def test_preset_values_from_object_reads_builtin_preset():
    # ``pydantic_views.builder`` is imported by the plugin process, so the live object is readable.
    values = _preset_values_from_object("pydantic_views.builder.LoadPreset")
    assert values is not None
    assert values["view_name"] == "Load"
    assert values["include_computed_fields"] is True


def test_preset_values_from_object_missing_returns_none():
    assert _preset_values_from_object("pydantic_views.builder.DoesNotExist") is None
    assert _preset_values_from_object("no.such.module.Thing") is None


def _preset_call(*, names, args) -> CallExpr:
    callee = _name("Preset")
    return CallExpr(callee, list(args), [ARG_NAMED] * len(args), list(names))


def test_preset_values_from_call_keyword_args():
    call = _preset_call(
        names=["view_name", "access_modes", "include_computed_fields"],
        args=[
            StrExpr("Load"),
            TupleExpr([MemberExpr(_name("AccessMode"), "READ_ONLY")]),
            _name("True", "builtins.True"),
        ],
    )
    assert _preset_values_from_call(call) == {
        "view_name": "Load",
        "access_modes": frozenset({"READ_ONLY"}),
        "include_computed_fields": True,
    }


def test_preset_values_from_call_positional_args_mapped_by_field_order():
    # First positional -> view_name, second -> access_modes (None expr leaves access_modes unset).
    call = CallExpr(
        _name("Preset"),
        [StrExpr("Create")],
        [ARG_NAMED],
        [None],
    )
    assert _preset_values_from_call(call) == {"view_name": "Create"}


def test_preset_values_from_call_extra_positionals_ignored():
    # More positionals than ``Preset`` has fields: the 9th (index 8) is dropped, not mis-mapped.
    surplus = [StrExpr(f"x{i}") for i in range(9)]
    call = CallExpr(_name("Preset"), surplus, [ARG_NAMED] * 9, [None] * 9)
    values = _preset_values_from_call(call)
    assert values["view_name"] == "x0"  # index 0 -> view_name
    assert "access_modes" not in values  # index 1 is a StrExpr, not a tuple -> omitted
    assert set(values) == {"view_name", "all_optional", "all_nullable", "include_computed_fields"}


def test_preset_values_from_call_without_view_name_and_empty_access_modes():
    # No view_name keyword, and an access_modes expr that parses to no members -> both omitted.
    call = _preset_call(
        names=["access_modes", "all_optional"],
        args=[TupleExpr([]), _name("True", "builtins.True")],
    )
    assert _preset_values_from_call(call) == {"access_modes": frozenset(), "all_optional": True}


def test_preset_values_from_call_unparseable_access_modes_omitted():
    # ``_read_access_modes`` returns None for a non-tuple expr; access_modes stays unset.
    call = _preset_call(names=["access_modes"], args=[_name("not_a_tuple")])
    assert _preset_values_from_call(call) == {}


def test_find_preset_call_matches_module_level_assignment():
    rvalue = _preset_call(names=["view_name"], args=[StrExpr("Load")])
    stmt = AssignmentStmt([_name("MyPreset")], rvalue)
    other = AssignmentStmt([_name("MyPreset")], _name("not_a_call"))
    module = SimpleNamespace(defs=[other, stmt])
    assert _find_preset_call(module, "MyPreset") is rvalue  # type: ignore[arg-type]
    assert _find_preset_call(module, "Absent") is None  # type: ignore[arg-type]


def test_find_preset_call_ignores_non_preset_callee():
    rvalue = CallExpr(_name("SomethingElse"), [], [], [])
    stmt = AssignmentStmt([_name("MyPreset")], rvalue)
    module = SimpleNamespace(defs=[stmt])
    assert _find_preset_call(module, "MyPreset") is None  # type: ignore[arg-type]


def _transformer_with(*, keywords: dict, modules: dict, final_iteration: bool = True) -> _ViewTransformer:
    deferred: list[bool] = []
    api = SimpleNamespace(
        anal_type=lambda t: t,
        final_iteration=final_iteration,
        modules=modules,
        defer=lambda: deferred.append(True),
    )
    ctx = SimpleNamespace(cls=SimpleNamespace(keywords=keywords), api=api)
    plugin = SimpleNamespace(init_forbid_extra=True)
    transformer = _ViewTransformer(ctx, plugin)  # type: ignore[arg-type]
    transformer._deferred = deferred  # type: ignore[attr-defined]
    return transformer


def test_resolve_preset_none_returns_empty():
    transformer = _transformer_with(keywords={}, modules={})
    assert transformer._resolve_preset(None) == {}


def test_resolve_preset_reads_builtin_via_object():
    transformer = _transformer_with(keywords={}, modules={})
    expr = _name("LoadPreset", "pydantic_views.builder.LoadPreset")
    assert transformer._resolve_preset(expr)["view_name"] == "Load"


def test_resolve_preset_falls_back_to_ast_scan():
    # A preset not importable from ``sys.modules`` is read from the analysed module's AST instead.
    rvalue = CallExpr(_name("Preset"), [StrExpr("Load")], [ARG_NAMED], ["view_name"])
    module = SimpleNamespace(defs=[AssignmentStmt([_name("LocalPreset")], rvalue)])
    transformer = _transformer_with(keywords={}, modules={"some.userland.mod": module})
    expr = _name("LocalPreset", "some.userland.mod.LocalPreset")
    assert transformer._resolve_preset(expr) == {"view_name": "Load"}


def test_resolve_preset_defers_when_unresolvable():
    transformer = _transformer_with(keywords={}, modules={}, final_iteration=False)
    expr = _name("Missing", "nowhere.Missing")
    assert transformer._resolve_preset(expr) == {}
    assert transformer._deferred == [True]  # type: ignore[attr-defined]


def test_resolve_preset_defers_when_fullname_unresolved():
    transformer = _transformer_with(keywords={}, modules={}, final_iteration=False)
    assert transformer._resolve_preset(SimpleNamespace(node=None, fullname=None)) == {}
    assert transformer._deferred == [True]  # type: ignore[attr-defined]


def test_read_config_applies_preset_defaults():
    transformer = _transformer_with(
        keywords={"preset": _name("LoadPreset", "pydantic_views.builder.LoadPreset")},
        modules={},
    )
    config = transformer._read_config()
    assert config.view_name == "Load"
    assert config.access_modes == frozenset({"READ_AND_WRITE", "READ_ONLY"})
    assert config.include_computed_fields is True


def test_read_config_explicit_keyword_overrides_preset():
    transformer = _transformer_with(
        keywords={
            "preset": _name("LoadPreset", "pydantic_views.builder.LoadPreset"),
            "view_name": StrExpr("Custom"),
            "include_computed_fields": _name("False", "builtins.False"),
        },
        modules={},
    )
    config = transformer._read_config()
    assert config.view_name == "Custom"  # explicit keyword wins over the preset's "Load"
    assert config.include_computed_fields is False  # explicit False overrides preset's True
    assert config.access_modes == frozenset({"READ_AND_WRITE", "READ_ONLY"})  # still from preset
