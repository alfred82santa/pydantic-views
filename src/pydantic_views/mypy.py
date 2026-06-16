"""
A mypy plugin that teaches the type checker about pydantic-views ``View`` subclasses.

At runtime the :class:`~pydantic_views.View` metaclass copies a *filtered* subset of the source
model's fields into the view (based on the ``access_modes`` / ``all_optional`` / ``all_nullable`` /
``include_computed_fields`` class keyword arguments). mypy never executes that metaclass, so without
this plugin a view looks like an empty model with an ``__init__(**data: Any)`` signature.

This plugin reproduces the builder's field selection statically: for every ``View`` subclass it reads
the source model's fields (from the metadata stored by the ``pydantic.mypy`` plugin), recovers each
field's access modes from the raw annotation, applies the same inclusion rules as
:class:`pydantic_views.builder.Builder`, and synthesises matching attributes and an ``__init__``.

Configuration (mypy config file)::

    [mypy]
    # IMPORTANT: pydantic_views.mypy must come *before* pydantic.mypy.
    plugins = pydantic_views.mypy, pydantic.mypy

    [pydantic-views-mypy]
    # Whether the generated __init__ should reject unknown keyword arguments. Default: true.
    init_forbid_extra = true

Limitations (consequences of what mypy can see statically):

* The explicit keyword form and the ``preset=`` form are both understood::

      class UserLoad(View[User], view_name="Load", access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY)):
          ...

      class UserLoad(View[User], preset=LoadPreset):  # resolved to the keywords of ``LoadPreset = Preset(...)``
          ...

  A ``preset=<name>`` keyword is resolved by reading the referenced module-level
  ``<name> = Preset(...)`` assignment; its arguments fill in the matching class keywords, and any
  keyword passed explicitly alongside ``preset`` still wins. The preset must be a direct
  ``Preset(...)`` call bound to a module-level name (the literal form the runtime presets use).
  The ``**LoadPreset._asdict()`` convenience still cannot be analysed because mypy drops ``**``
  unpackings from class keyword arguments; use ``preset=LoadPreset`` or explicit keywords instead.
* Field level :class:`~pydantic_views.AccessTag` tags are attached through ``Annotated`` runtime
  values that mypy discards, so ``include_tags`` / ``exclude_tags`` filtering is not applied here.
* ``RootView`` subclasses are left untouched (their single ``root`` value is not field-expanded).

Nested models are handled the same way the runtime builder handles them: a field referencing another
model gets that model's matching view, synthesised under ``<Model><ViewName>`` (e.g. ``Address`` +
``Load`` -> ``AddressLoad``) in the model's own module, recursively and through containers
(``list``/``set``/``tuple``/``dict``) and unions. Because those nested views are generated (not named
in your source, just like at runtime), build instances via ``model_validate(...)`` or
``view_build_from(...)`` rather than by passing hand-built nested view instances.
"""

from __future__ import annotations

import configparser
from collections.abc import Callable
from typing import Any

from mypy.nodes import (
    ARG_NAMED,
    ARG_NAMED_OPT,
    ARG_STAR2,
    GDEF,
    MDEF,
    Argument,
    AssignmentStmt,
    CallExpr,
    ClassDef,
    Decorator,
    MemberExpr,
    MypyFile,
    NameExpr,
    StrExpr,
    SymbolTableNode,
    TempNode,
    TypeInfo,
    Var,
)
from mypy.options import Options
from mypy.plugin import ClassDefContext, Plugin
from mypy.types import (
    AnyType,
    CallableType,
    Instance,
    NoneType,
    TupleType,
    Type,
    TypeOfAny,
    UnboundType,
    UnionType,
    get_proper_type,
)

# Reuse pydantic's own plugin machinery so we read fields exactly the way it writes them.
from pydantic.mypy import (
    BASEMODEL_FULLNAME,
    PydanticModelField,
    add_method,
)
from pydantic.mypy import (
    METADATA_KEY as PYDANTIC_METADATA_KEY,
)

VIEW_FULLNAME = "pydantic_views.view.View"
ROOTVIEW_FULLNAME = "pydantic_views.view.RootView"

CONFIG_SECTION = "pydantic-views-mypy"

#: Names of the access-mode enum members (``AccessMode.<member>``).
ACCESS_MODE_MEMBERS = frozenset(
    {
        "READ_AND_WRITE",
        "READ_ONLY",
        "WRITE_ONLY",
        "READ_ONLY_ON_CREATION",
        "WRITE_ONLY_ON_CREATION",
        "HIDDEN",
    }
)

#: Annotation alias name -> access-mode member it expands to.
ALIAS_TO_MODE = {
    "ReadAndWrite": "READ_AND_WRITE",
    "ReadOnly": "READ_ONLY",
    "WriteOnly": "WRITE_ONLY",
    "ReadOnlyOnCreation": "READ_ONLY_ON_CREATION",
    "WriteOnlyOnCreation": "WRITE_ONLY_ON_CREATION",
    "Hidden": "HIDDEN",
}


class _ViewConfig:
    """Parsed class keyword arguments of a ``View`` subclass."""

    __slots__ = (
        "view_name",
        "access_modes",
        "all_optional",
        "all_nullable",
        "include_computed_fields",
    )

    def __init__(
        self,
        view_name: str | None,
        access_modes: frozenset[str] | None,
        all_optional: bool,
        all_nullable: bool,
        include_computed_fields: bool,
    ) -> None:
        self.view_name = view_name
        self.access_modes = access_modes
        self.all_optional = all_optional
        self.all_nullable = all_nullable
        self.include_computed_fields = include_computed_fields


class PydanticViewsPlugin(Plugin):
    """mypy plugin entry point for pydantic-views."""

    def __init__(self, options: Options) -> None:
        super().__init__(options)
        self.init_forbid_extra = _read_init_forbid_extra(options)

    def get_base_class_hook(self, fullname: str) -> Callable[[ClassDefContext], None] | None:
        # ``fullname`` is the *base* class of the class being defined. We match whenever that base
        # is ``View`` (or a subclass of it); the callback then inspects the derived class.
        sym = self.lookup_fully_qualified(fullname)
        if sym is not None and isinstance(sym.node, TypeInfo) and sym.node.has_base(VIEW_FULLNAME):
            return self._view_class_callback
        return None

    def _view_class_callback(self, ctx: ClassDefContext) -> None:
        _ViewTransformer(ctx, self).transform()


class _ViewTransformer:
    """Synthesises the fields and ``__init__`` of a single ``View`` subclass."""

    def __init__(self, ctx: ClassDefContext, plugin: PydanticViewsPlugin) -> None:
        self._ctx = ctx
        self._cls = ctx.cls
        self._api = ctx.api
        self._plugin = plugin
        # Fullnames of nested views already (being) synthesised during this transform — both a
        # de-duplication guard and a recursion breaker for self-referential / circular models.
        self._synthesizing: set[str] = set()

    # -- orchestration ---------------------------------------------------------------------------

    def transform(self) -> None:
        info = self._cls.info

        # Only act on user views, not on the library base classes.
        if info.fullname in (VIEW_FULLNAME, ROOTVIEW_FULLNAME):
            return

        model_info = self._source_model_info(info)
        if model_info is None:
            # Not a concrete ``View[ConcreteModel]`` (e.g. a generic intermediate base). Nothing to do.
            return

        if model_info.metadata.get(PYDANTIC_METADATA_KEY) is None:
            # The source model has not been processed by the pydantic plugin yet. Retry next pass.
            self._defer()
            return

        # Guard against a model that references itself: a nested field resolving back to this view
        # must not re-trigger population.
        self._synthesizing.add(info.fullname)
        self._populate_view(info, model_info, self._read_config())

    def _populate_view(self, view_info: TypeInfo, model_info: TypeInfo, config: _ViewConfig) -> None:
        """Add the filtered fields and the ``__init__`` of ``view_info`` from ``model_info``."""
        metadata = model_info.metadata.get(PYDANTIC_METADATA_KEY)
        if metadata is None:
            self._defer()
            return

        field_modes = self._collect_field_modes(model_info)
        arguments: list[Argument] = []
        taken: set[str] = set()

        for name, data in metadata["fields"].items():
            field = PydanticModelField.deserialize(model_info, data, self._api)
            if not self._keep(field_modes.get(name, frozenset()), config):
                continue
            field_type = field.type
            if field_type is None:
                self._defer()
                field_type = AnyType(TypeOfAny.special_form)
            self._add_field(
                view_info,
                name,
                field_type,
                has_default=field.has_default,
                config=config,
                arguments=arguments,
            )
            taken.add(name)

        if config.include_computed_fields:
            for name, computed_type in self._collect_computed_fields(model_info).items():
                self._add_field(
                    view_info,
                    name,
                    computed_type,
                    has_default=True,
                    config=config,
                    arguments=arguments,
                )
                taken.add(name)

        # Fields declared directly on the view body are regular pydantic fields too: keep them in the
        # ``__init__``. They already exist as attributes from normal class analysis, so only add args.
        for name, argument in self._own_field_arguments(view_info):
            if name not in taken:
                arguments.append(argument)
                taken.add(name)

        if not self._plugin.init_forbid_extra:
            arguments.append(Argument(Var("kwargs"), AnyType(TypeOfAny.explicit), None, ARG_STAR2))

        add_method(
            self._api,
            view_info.defn,
            "__init__",
            args=arguments,
            return_type=NoneType(),
        )

    def _own_field_arguments(self, view_info: TypeInfo) -> list[tuple[str, Argument]]:
        """Collect ``__init__`` arguments for fields declared on the view's own body."""
        result: list[tuple[str, Argument]] = []
        for stmt in view_info.defn.defs.body:
            if not isinstance(stmt, AssignmentStmt) or stmt.unanalyzed_type is None:
                continue
            if len(stmt.lvalues) != 1 or not isinstance(stmt.lvalues[0], NameExpr):
                continue
            name = stmt.lvalues[0].name
            sym = view_info.names.get(name)
            if sym is None or not isinstance(sym.node, Var) or sym.node.is_classvar:
                continue
            var = sym.node
            if var.type is None:
                self._defer()
                continue
            has_default = not isinstance(stmt.rvalue, TempNode)
            argument = Argument(
                variable=Var(name, var.type),
                type_annotation=var.type,
                initializer=None,
                kind=ARG_NAMED_OPT if has_default else ARG_NAMED,
            )
            result.append((name, argument))
        return result

    # -- field synthesis -------------------------------------------------------------------------

    def _add_field(
        self,
        info: TypeInfo,
        name: str,
        field_type: Type,
        *,
        has_default: bool,
        config: _ViewConfig,
        arguments: list[Argument],
    ) -> None:
        # Substitute nested models with their views, then optionally make the field nullable.
        typ = self._view_type(field_type, config)
        if config.all_nullable:
            typ = _make_nullable(typ)

        # Register the field as an attribute on the view class.
        var = Var(name, typ)
        var.info = info
        var._fullname = f"{info.fullname}.{name}"
        info.names[name] = SymbolTableNode(MDEF, var, plugin_generated=True)

        optional = has_default or config.all_optional
        arguments.append(
            Argument(
                variable=Var(name, typ),
                type_annotation=typ,
                initializer=None,
                kind=ARG_NAMED_OPT if optional else ARG_NAMED,
            )
        )

    # -- nested view synthesis -------------------------------------------------------------------

    def _view_type(self, typ: Type, config: _ViewConfig) -> Type:
        """Map a source-model field type to its view type, replacing nested models with their views."""
        if config.view_name is None:
            # Without a view name we cannot derive nested view names; keep the source types.
            return typ

        proper = get_proper_type(typ)
        if isinstance(proper, Instance):
            target = proper.type
            if target.has_base(BASEMODEL_FULLNAME) and not target.has_base(VIEW_FULLNAME):
                nested = self._synthesize_view(target, config)
                return Instance(nested, []) if nested is not None else typ
            if proper.args:
                return proper.copy_modified(args=[self._view_type(a, config) for a in proper.args])
            return typ
        if isinstance(proper, UnionType):
            return UnionType([self._view_type(item, config) for item in proper.items])
        if isinstance(proper, TupleType):
            return proper.copy_modified(items=[self._view_type(item, config) for item in proper.items])
        return typ

    def _synthesize_view(self, model_info: TypeInfo, config: _ViewConfig) -> TypeInfo | None:
        """Create (or reuse) the view of a nested model, in the model's own module.

        Mirrors the runtime naming: ``<Model><ViewName>`` (e.g. ``Address`` + ``Load`` ->
        ``AddressLoad``), registered in ``model.__module__``.
        """
        assert config.view_name is not None
        view_name = config.view_name
        name = model_info.name + view_name[:1].upper() + view_name[1:]
        module = self._api.modules.get(model_info.module_name)
        if module is None:
            return None
        fullname = f"{model_info.module_name}.{name}"

        sym = module.names.get(name)
        if sym is not None and isinstance(sym.node, TypeInfo):
            info = sym.node
        else:
            if model_info.metadata.get(PYDANTIC_METADATA_KEY) is None:
                self._defer()
                return None
            base = self._api.named_type(VIEW_FULLNAME, [Instance(model_info, [])])
            info = self._api.basic_new_typeinfo(name, base, model_info.defn.line)
            info._fullname = fullname
            module.names[name] = SymbolTableNode(GDEF, info, plugin_generated=True)

        # Populate each nested view only once per transform; returning early also breaks cycles.
        if fullname not in self._synthesizing:
            self._synthesizing.add(fullname)
            self._populate_view(info, model_info, config)
        return info

    # -- selection logic (mirrors Builder._filter_field) -----------------------------------------

    @staticmethod
    def _keep(modes: frozenset[str], config: _ViewConfig) -> bool:
        access_modes = config.access_modes
        # A field with a matching access mode, or with no access mode at all, is kept.
        # (Field level tags cannot be recovered statically, so include/exclude tags are ignored.)
        return bool((access_modes is not None and (modes & access_modes)) or not modes)

    # -- reading the source model ----------------------------------------------------------------

    @staticmethod
    def _source_model_info(info: TypeInfo) -> TypeInfo | None:
        for base in info.bases:
            if base.type.fullname == VIEW_FULLNAME and base.args:
                arg = base.args[0]
                if isinstance(arg, Instance):
                    return arg.type
        return None

    def _collect_field_modes(self, model_info: TypeInfo) -> dict[str, frozenset[str]]:
        """Recover each field's access modes from raw annotations across the model's MRO."""
        modes: dict[str, frozenset[str]] = {}
        for type_info in reversed(model_info.mro):
            defn = getattr(type_info, "defn", None)
            if not isinstance(defn, ClassDef):
                continue
            for stmt in defn.defs.body:
                if (
                    isinstance(stmt, AssignmentStmt)
                    and stmt.unanalyzed_type is not None
                    and len(stmt.lvalues) == 1
                    and isinstance(stmt.lvalues[0], NameExpr)
                ):
                    modes[stmt.lvalues[0].name] = _modes_from_annotation(stmt.unanalyzed_type)
        return modes

    def _collect_computed_fields(self, model_info: TypeInfo) -> dict[str, Type]:
        computed: dict[str, Type] = {}
        for type_info in reversed(model_info.mro):
            defn = getattr(type_info, "defn", None)
            if not isinstance(defn, ClassDef):
                continue
            for stmt in defn.defs.body:
                if isinstance(stmt, Decorator) and any(_is_computed_field(d) for d in stmt.decorators):
                    computed[stmt.func.name] = self._computed_return_type(type_info, stmt)
        return computed

    def _computed_return_type(self, model_info: TypeInfo, decorator: Decorator) -> Type:
        candidate: Type | None = None
        func_type = decorator.func.type
        if isinstance(func_type, CallableType) and func_type.ret_type is not None:
            candidate = func_type.ret_type
        else:
            # Fall back to the analysed symbol (pydantic exposes computed fields as typed attributes).
            sym = model_info.names.get(decorator.func.name)
            if sym is not None and isinstance(sym.node, Var) and sym.node.type is not None:
                candidate = sym.node.type

        if candidate is None:
            return AnyType(TypeOfAny.special_form)
        # The stored type can still be unbound on early passes; analyse it in the current context.
        analyzed = self._api.anal_type(candidate)
        return analyzed if analyzed is not None else candidate

    # -- class keyword arguments -----------------------------------------------------------------

    def _read_config(self) -> _ViewConfig:
        keywords = self._cls.keywords
        # ``preset=<Preset>`` supplies defaults for the matching class keywords; an explicit keyword
        # still wins (mirrors the runtime ``with_preset`` decorator on ``ViewMetaClass.__new__``).
        preset = self._resolve_preset(keywords.get("preset"))

        def pick(name: str, parse: Callable[[Any], Any], default: Any) -> Any:
            if name in keywords:
                return parse(keywords[name])
            if name in preset:
                return preset[name]
            return default

        return _ViewConfig(
            view_name=pick("view_name", lambda e: e.value if isinstance(e, StrExpr) else None, None),
            access_modes=pick("access_modes", _read_access_modes, None),
            all_optional=pick("all_optional", _read_bool, False),
            all_nullable=pick("all_nullable", _read_bool, False),
            include_computed_fields=pick("include_computed_fields", _read_bool, False),
        )

    def _resolve_preset(self, expr: Any) -> dict[str, Any]:
        """Resolve a ``preset=<name>`` keyword to the config values it implies.

        Returns a mapping of ``_ViewConfig`` field name to its already-parsed value (e.g.
        ``access_modes`` as a ``frozenset[str]``). Two resolution strategies are tried:

        1. The referenced ``Preset`` object read from ``sys.modules`` — the plugin process already
           imports :mod:`pydantic_views`, so the built-in presets (and any preset in an importable
           module) are available as live objects with exact values.
        2. Failing that, the module-level ``<name> = Preset(...)`` assignment is read from the AST,
           which covers presets defined in the module currently under analysis.

        Returns an empty mapping when there is no ``preset`` keyword, or defers when a preset is
        named but cannot be resolved yet.
        """
        if expr is None:
            return {}

        fullname = _preset_fullname(expr)
        if fullname:
            values = _preset_values_from_object(fullname)
            if values is not None:
                return values

            module_name, _, var_name = fullname.rpartition(".")
            module = self._api.modules.get(module_name)
            call = _find_preset_call(module, var_name) if module is not None else None
            if call is not None:
                return _preset_values_from_call(call)

        self._defer()
        return {}

    # -- helpers ---------------------------------------------------------------------------------

    def _defer(self) -> None:
        if not self._api.final_iteration:
            self._api.defer()


# -- module level helpers ------------------------------------------------------------------------


def _modes_from_annotation(unanalyzed: Any) -> frozenset[str]:
    """Extract access-mode member names from a raw (unanalyzed) field annotation."""
    if not isinstance(unanalyzed, UnboundType):
        return frozenset()

    base_name = unanalyzed.name.split(".")[-1]
    if base_name in ALIAS_TO_MODE:
        return frozenset({ALIAS_TO_MODE[base_name]})

    modes: set[str] = set()
    if base_name == "Annotated":
        # Annotated[<type>, AccessMode.X, AccessMode.Y, ...] — skip the first (the real type).
        for arg in unanalyzed.args[1:]:
            if not isinstance(arg, UnboundType):
                continue
            member = arg.name.split(".")[-1]
            if member in ACCESS_MODE_MEMBERS:
                modes.add(member)
            elif member in ALIAS_TO_MODE:
                modes.add(ALIAS_TO_MODE[member])
    return frozenset(modes)


#: ``Preset`` field order, used to map positional ``Preset(...)`` arguments to their names.
PRESET_FIELDS = (
    "view_name",
    "access_modes",
    "include_tags",
    "exclude_tags",
    "all_optional",
    "all_nullable",
    "hide_default_null",
    "include_computed_fields",
)


def _preset_fullname(expr: Any) -> str | None:
    """Return the canonical fullname of the symbol a ``preset=`` keyword expression refers to."""
    node = getattr(expr, "node", None)
    if node is not None and getattr(node, "fullname", None):
        return node.fullname
    return getattr(expr, "fullname", None)


def _find_preset_call(module: MypyFile, name: str) -> CallExpr | None:
    """Find a module-level ``<name> = Preset(...)`` assignment and return its call expression."""
    for stmt in module.defs:
        if (
            isinstance(stmt, AssignmentStmt)
            and len(stmt.lvalues) == 1
            and isinstance(stmt.lvalues[0], NameExpr)
            and stmt.lvalues[0].name == name
            and isinstance(stmt.rvalue, CallExpr)
        ):
            callee = stmt.rvalue.callee
            if isinstance(callee, (NameExpr, MemberExpr)) and callee.name == "Preset":
                return stmt.rvalue
    return None


def _preset_values_from_object(fullname: str) -> dict[str, Any] | None:
    """Read preset config values from a live ``Preset`` object already present in ``sys.modules``.

    Only modules already imported by the plugin process are consulted, so this never triggers a new
    import (and never runs the target project's code as a side effect). Returns ``None`` when the
    preset is not available this way.
    """
    import sys

    module_name, _, var_name = fullname.rpartition(".")
    module = sys.modules.get(module_name)
    preset = getattr(module, var_name, None) if module is not None else None
    asdict = getattr(preset, "_asdict", None)
    if not callable(asdict):
        return None
    try:
        data = asdict()
    except Exception:  # pragma: no cover - defensive: a non-Preset object named like one
        return None
    return _normalise_preset_values(data)


def _normalise_preset_values(data: Any) -> dict[str, Any] | None:
    """Convert a ``Preset._asdict()`` mapping to ``_ViewConfig`` field values."""
    if not isinstance(data, dict):  # pragma: no cover - defensive
        return None
    values: dict[str, Any] = {}
    view_name = data.get("view_name")
    if isinstance(view_name, str):
        values["view_name"] = view_name
    access_modes = data.get("access_modes")
    if access_modes is not None:
        values["access_modes"] = frozenset(getattr(m, "name", m) for m in access_modes)
    for field in ("all_optional", "all_nullable", "include_computed_fields"):
        if field in data:
            values[field] = bool(data[field])
    return values


def _preset_values_from_call(call: CallExpr) -> dict[str, Any]:
    """Parse a ``Preset(...)`` call expression into ``_ViewConfig`` field values."""
    keywords: dict[str, Any] = {}
    for index, (arg, arg_name) in enumerate(zip(call.args, call.arg_names, strict=False)):
        if arg_name is not None:
            keywords[arg_name] = arg
        elif index < len(PRESET_FIELDS):
            keywords[PRESET_FIELDS[index]] = arg

    values: dict[str, Any] = {}
    view_name = keywords.get("view_name")
    if isinstance(view_name, StrExpr):
        values["view_name"] = view_name.value
    if "access_modes" in keywords:
        access_modes = _read_access_modes(keywords["access_modes"])
        if access_modes is not None:
            values["access_modes"] = access_modes
    for field in ("all_optional", "all_nullable", "include_computed_fields"):
        if field in keywords:
            values[field] = _read_bool(keywords[field])
    return values


def _read_access_modes(expr: Any) -> frozenset[str] | None:
    if expr is None:
        return None
    items = getattr(expr, "items", None)
    if items is None:
        return None
    modes: set[str] = set()
    for item in items:
        # ``AccessMode.READ_ONLY`` -> MemberExpr; a bare imported member -> NameExpr. Both expose ``.name``.
        if isinstance(item, (MemberExpr, NameExpr)) and item.name in ACCESS_MODE_MEMBERS:
            modes.add(item.name)
    return frozenset(modes)


def _read_bool(expr: Any) -> bool:
    return isinstance(expr, NameExpr) and expr.fullname == "builtins.True"


def _is_computed_field(decorator: Any) -> bool:
    if isinstance(decorator, CallExpr):
        decorator = decorator.callee
    # ``@computed_field`` -> NameExpr; ``@pydantic.computed_field`` -> MemberExpr. Both expose ``.name``.
    return isinstance(decorator, (MemberExpr, NameExpr)) and decorator.name == "computed_field"


def _make_nullable(typ: Type) -> Type:
    if isinstance(typ, NoneType):
        return typ
    if isinstance(typ, UnionType) and any(isinstance(item, NoneType) for item in typ.items):
        return typ
    return UnionType([typ, NoneType()])


def _read_init_forbid_extra(options: Options) -> bool:
    config_file = options.config_file
    if not config_file or config_file.endswith(".toml"):
        # TOML config for this option is not parsed; fall back to the default.
        return True
    parser = configparser.ConfigParser()
    try:
        parser.read(config_file)
    except (OSError, configparser.Error):
        return True
    if parser.has_option(CONFIG_SECTION, "init_forbid_extra"):
        return parser.getboolean(CONFIG_SECTION, "init_forbid_extra", fallback=True)
    return True


def plugin(version: str) -> type[Plugin]:
    """mypy plugin entry point."""
    return PydanticViewsPlugin
