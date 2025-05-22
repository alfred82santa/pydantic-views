from collections.abc import Callable, Mapping
from itertools import chain, combinations
from types import NoneType
from typing import Any, Literal, Optional, Union, get_args, get_origin  # type: ignore

import pytest
from pydantic import BaseModel, Field, RootModel, computed_field
from pydantic_core import PydanticUndefined

from pydantic_views.annotations import (
    AccessMode,
    Hidden,
    ReadAndWrite,
    ReadOnly,
    ReadOnlyOnCreation,
    WriteOnly,
    WriteOnlyOnCreation,
)
from pydantic_views.builder import (
    Builder,
    BuilderCreate,
    BuilderCreateResult,
    BuilderLoad,
    BuilderUpdate,
    RootView,
    ensure_model_views,
)
from pydantic_views.view import View


class Model(BaseModel):
    """
    Test model
    """

    field_int: int = 1
    read_only_field_int: ReadOnly[int] = Field(
        alias="readOnlyFieldInt", title="Read Only Field"
    )
    read_only_on_creation_field_int: ReadOnlyOnCreation[int] = Field(
        description="Read only on creation field"
    )
    write_only_field_int: WriteOnly[int | None] = None
    write_only_on_creation_field_int: WriteOnlyOnCreation[int | None] = None
    read_and_write_field_int: ReadAndWrite[int | None] = None
    hidden_int: Hidden[int]

    field_str: str
    read_only_field_str: ReadOnly[str] = Field(
        deprecated="Deprecated in favor of other field"
    )
    read_only_on_creation_field_str: ReadOnlyOnCreation[str | None] = None
    write_only_field_str: WriteOnly[str]
    write_only_on_creation_field_str: WriteOnlyOnCreation[str]
    read_and_write_field_str: ReadAndWrite[str]
    hidden_str: Hidden[str]

    literal_int: Literal[1]
    literal_read_only_str: ReadOnly[Literal["literal"]]

    @computed_field
    def computed_field_int(self) -> int:
        return 1


class ListRootModel(RootModel[list[Model]]):
    pass


class SetRootModel(RootModel[set[Model]]):
    pass


class TupleVarRootModel(RootModel[tuple[Model, ...]]):
    pass


class TupleFixedRootModel(RootModel[tuple[Model, int]]):
    pass


class DictRootModel(RootModel[dict[str, Model]]):
    pass


class ModelComplexTypes(BaseModel):
    """
    Test model 2
    """

    field_list_int: list[int]
    field_list_model: list[Model]

    field_set_int: set[int]
    field_set_model: set[Model]

    field_tuple_fixed_int: tuple[int]
    field_tuple_fixed_model: tuple[Model]

    field_tuple_var_int: tuple[int, ...]
    field_fuple_var_model: tuple[Model, ...]

    field_dict_int: dict[str, int]
    field_dict_model: dict[str, Model]

    field_recurrent: list["Model"]


_groups = [
    (
        "ReadOnly",
        (AccessMode.READ_ONLY,),
        {
            "field_int",
            "read_only_field_int",
            "field_str",
            "read_only_field_str",
            "literal_int",
            "literal_read_only_str",
        },
    ),
    (
        "WriteOnly",
        (AccessMode.WRITE_ONLY,),
        {
            "field_int",
            "write_only_field_int",
            "field_str",
            "write_only_field_str",
            "literal_int",
        },
    ),
    (
        "ReadOnlyOnCreation",
        (AccessMode.READ_ONLY_ON_CREATION,),
        {
            "field_int",
            "read_only_on_creation_field_int",
            "field_str",
            "read_only_on_creation_field_str",
            "literal_int",
        },
    ),
    (
        "WriteOnlyOnCreation",
        (AccessMode.WRITE_ONLY_ON_CREATION,),
        {
            "field_int",
            "write_only_on_creation_field_int",
            "field_str",
            "write_only_on_creation_field_str",
            "literal_int",
        },
    ),
    (
        "ReadAndWrite",
        (AccessMode.READ_AND_WRITE,),
        {
            "field_int",
            "field_str",
            "read_and_write_field_int",
            "read_and_write_field_str",
            "literal_int",
        },
    ),
    (
        "Hidden",
        (AccessMode.HIDDEN,),
        {
            "field_int",
            "field_str",
            "hidden_int",
            "hidden_str",
            "literal_int",
        },
    ),
]


def _generate_params(prefix: str = ""):
    return list(
        chain.from_iterable(
            [
                [
                    pytest.param(
                        prefix + "And".join((g[0] for g in gs)),
                        tuple(chain.from_iterable(g[1] for g in gs)),
                        set(chain.from_iterable(g[2] for g in gs)),
                        id="And".join((g[0] for g in gs)),
                    )
                    for gs in combinations(_groups, r + 1)
                ]
                for r in range(3)
            ]
        ),
    )


@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"), _generate_params("TestView")
)
def test_view(
    view_name: str, access_modes: tuple[AccessMode, ...], expected_fields: set[str]
):
    builder = Builder(view_name, access_modes=access_modes)

    view_cls = builder.build_view(Model)

    assert view_cls.__name__ == f"Model{view_name}"
    assert set(view_cls.model_fields.keys()) == expected_fields

    assert view_cls.__module__ == __name__
    assert view_cls.__doc__ == f"View `{view_name}` of model :class:`~{__name__}.Model`"

    assert hasattr(Model, "model_views")
    assert Model.model_views[view_name] == view_cls  # type: ignore

    for f in expected_fields:
        assert view_cls.model_fields[f].default == Model.model_fields[f].default
        assert (
            view_cls.model_fields[f].default_factory
            == Model.model_fields[f].default_factory
        )
        assert view_cls.model_fields[f].alias == Model.model_fields[f].alias
        assert (
            view_cls.model_fields[f].alias_priority
            == Model.model_fields[f].alias_priority
        )
        assert view_cls.model_fields[f].annotation == Model.model_fields[f].annotation
        assert view_cls.model_fields[f].description == Model.model_fields[f].description
        assert view_cls.model_fields[f].title == Model.model_fields[f].title
        assert view_cls.model_fields[f].deprecated == Model.model_fields[f].deprecated
        assert (
            view_cls.model_fields[f].discriminator
            == Model.model_fields[f].discriminator
        )
        assert view_cls.model_fields[f].metadata == [
            m for m in Model.model_fields[f].metadata if not isinstance(m, AccessMode)
        ]


@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("AllNullableView"),
)
def test_view_all_nullable(
    view_name: str, access_modes: tuple[AccessMode, ...], expected_fields: set[str]
):
    builder = Builder(view_name, access_modes=access_modes, all_nullable=True)

    view_cls = builder.build_view(Model)

    for f in expected_fields:
        if get_origin(view_cls.model_fields[f].annotation) is Literal:
            assert (
                view_cls.model_fields[f].annotation == Model.model_fields[f].annotation
            )
            continue

        assert (
            view_cls.model_fields[f].annotation
            == Model.model_fields[f].annotation | None  # type: ignore
        )


@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("AllOptionalView"),
)
def test_view_all_optional(
    view_name: str, access_modes: tuple[AccessMode, ...], expected_fields: set[str]
):
    builder = Builder(view_name, access_modes=access_modes, all_optional=True)

    view_cls = builder.build_view(Model)

    for f in expected_fields:
        assert view_cls.model_fields[f].default == PydanticUndefined
        assert view_cls.model_fields[f].default_factory() == PydanticUndefined  # type: ignore


@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("HideDefaultNullView"),
)
def test_view_hide_default_null(
    view_name: str, access_modes: tuple[AccessMode, ...], expected_fields: set[str]
):
    builder = Builder(view_name, access_modes=access_modes, hide_default_null=True)

    view_cls = builder.build_view(Model)

    for f in expected_fields:
        if Model.model_fields[f].default is not None:
            continue
        assert view_cls.model_fields[f].default == PydanticUndefined
        assert view_cls.model_fields[f].default_factory is not None
        assert view_cls.model_fields[f].default_factory() is PydanticUndefined  # type: ignore


@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("ComputedFieldView"),
)
def test_computed_fields(
    view_name: str, access_modes: tuple[AccessMode, ...], expected_fields: set[str]
):
    expected_fields.add("computed_field_int")

    builder = Builder(
        view_name, access_modes=access_modes, include_computed_fields=True
    )

    view_cls = builder.build_view(Model)

    assert view_cls.__name__ == f"Model{view_name}"
    assert set(view_cls.model_fields.keys()) == expected_fields


@pytest.mark.parametrize(
    ("root_class",),
    [
        (ListRootModel,),
        (SetRootModel,),
        (TupleVarRootModel,),
        (TupleFixedRootModel,),
        (DictRootModel,),
    ],
)
@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"), _generate_params("TestView")
)
def test_root_view(
    root_class: type[RootModel[Any]],
    view_name: str,
    access_modes: tuple[AccessMode, ...],
    expected_fields: set[str],
):
    builder = Builder(view_name, access_modes=access_modes)

    view_cls = builder.build_view(root_class)

    assert view_cls.__name__ == f"{root_class.__name__}{view_name}"
    assert issubclass(view_cls, RootView)

    assert get_origin(view_cls.model_fields["root"].annotation) == get_origin(
        root_class.model_fields["root"].annotation
    )

    assert len(get_args(view_cls.model_fields["root"].annotation)) == len(
        get_args(root_class.model_fields["root"].annotation)
    )

    for idx, arg in enumerate(get_args(view_cls.model_fields["root"].annotation)):
        if arg is not Ellipsis and issubclass(arg, View):
            assert (
                arg
                == get_args(root_class.model_fields["root"].annotation)[
                    idx
                ].model_views[view_name]
            )
        else:
            assert arg == get_args(root_class.model_fields["root"].annotation)[idx]


@pytest.mark.parametrize(
    ("root_class",),
    [
        (ListRootModel,),
        (SetRootModel,),
        # (TupleVarRootModel,),
        # (TupleFixedRootModel,),
        # (DictRootModel,),
    ],
)
@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("AllNullableListAndSetView"),
)
def test_root_view_all_nullable_list_and_set(
    root_class: type[RootModel[Any]],
    view_name: str,
    access_modes: tuple[AccessMode, ...],
    expected_fields: set[str],
):
    builder = Builder(view_name, access_modes=access_modes, all_nullable=True)

    view_cls = builder.build_view(root_class)

    assert view_cls.__name__ == f"{root_class.__name__}{view_name}"
    assert issubclass(view_cls, RootView)

    assert get_origin(view_cls.model_fields["root"].annotation) == get_origin(
        root_class.model_fields["root"].annotation
    )

    assert len(get_args(view_cls.model_fields["root"].annotation)) == len(
        get_args(root_class.model_fields["root"].annotation)
    )

    for idx, arg in enumerate(get_args(view_cls.model_fields["root"].annotation)):
        if arg is not Ellipsis and issubclass(arg, View):
            assert (
                arg
                == get_args(root_class.model_fields["root"].annotation)[
                    idx
                ].model_views[view_name]
            )
        else:
            assert arg == get_args(root_class.model_fields["root"].annotation)[idx]


@pytest.mark.parametrize(
    ("root_class",),
    [
        (TupleVarRootModel,),
        (TupleFixedRootModel,),
        # (DictRootModel,),
    ],
)
@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("AllNullableTupleView"),
)
def test_root_view_all_nullable_tuple(
    root_class: type[RootModel[Any]],
    view_name: str,
    access_modes: tuple[AccessMode, ...],
    expected_fields: set[str],
):
    builder = Builder(view_name, access_modes=access_modes, all_nullable=True)

    view_cls = builder.build_view(root_class)

    assert view_cls.__name__ == f"{root_class.__name__}{view_name}"
    assert issubclass(view_cls, RootView)

    assert get_origin(view_cls.model_fields["root"].annotation) == get_origin(
        root_class.model_fields["root"].annotation
    )

    assert len(get_args(view_cls.model_fields["root"].annotation)) == len(
        get_args(root_class.model_fields["root"].annotation)
    )

    for idx, arg in enumerate(get_args(view_cls.model_fields["root"].annotation)):
        if arg is Ellipsis:
            assert arg == get_args(root_class.model_fields["root"].annotation)[idx]
            continue

        assert get_origin(arg) is Union and issubclass(get_args(arg)[-1], NoneType)  # type: ignore

        t = get_args(arg)[0]
        if issubclass(t, View):
            assert (
                t
                == get_args(root_class.model_fields["root"].annotation)[
                    idx
                ].model_views[view_name]
            )
        else:
            assert t == get_args(root_class.model_fields["root"].annotation)[idx]


@pytest.mark.parametrize(
    ("root_class",),
    [
        (DictRootModel,),
    ],
)
@pytest.mark.parametrize(
    ("view_name", "access_modes", "expected_fields"),
    _generate_params("AllNullableDictiew"),
)
def test_root_view_all_nullable_dict(
    root_class: type[RootModel[Any]],
    view_name: str,
    access_modes: tuple[AccessMode, ...],
    expected_fields: set[str],
):
    builder = Builder(view_name, access_modes=access_modes, all_nullable=True)

    view_cls = builder.build_view(root_class)

    assert view_cls.__name__ == f"{root_class.__name__}{view_name}"
    assert issubclass(view_cls, RootView)

    assert get_origin(view_cls.model_fields["root"].annotation) == get_origin(
        root_class.model_fields["root"].annotation
    )

    assert len(get_args(view_cls.model_fields["root"].annotation)) == 2

    assert (
        get_args(view_cls.model_fields["root"].annotation)[0]
        == get_args(root_class.model_fields["root"].annotation)[0]
    )

    origin = get_origin(get_args(view_cls.model_fields["root"].annotation)[1])
    args = get_args(get_args(view_cls.model_fields["root"].annotation)[1])
    expected_arg = get_args(root_class.model_fields["root"].annotation)[1]

    if issubclass(expected_arg, BaseModel):
        assert (
            origin is Union  # type: ignore
            and args[0] == expected_arg.model_views[view_name]  # type: ignore
            and issubclass(args[-1], NoneType)
        )
    else:
        assert (
            origin is Union  # type: ignore
            and args[0] == expected_arg
            and issubclass(args[-1], NoneType)
        )


@pytest.mark.parametrize(
    ("view_name", "access_modes"),
    [
        ("ReadOnly", (AccessMode.READ_ONLY,)),
    ],
)
def test_view_complex_types(view_name: str, access_modes: tuple[AccessMode, ...]):
    builder = Builder(view_name, access_modes=access_modes)

    view_cls = builder.build_view(ModelComplexTypes)

    assert view_cls.__name__ == f"ModelComplexTypes{view_name}"

    for f_name, f_info in view_cls.model_fields.items():
        expected_origin = get_origin(ModelComplexTypes.model_fields[f_name].annotation)
        expected_args = get_args(ModelComplexTypes.model_fields[f_name].annotation)

        origin = get_origin(f_info.annotation)
        args = get_args(f_info.annotation)

        assert origin == expected_origin
        if issubclass(expected_origin, Mapping):  # type: ignore
            assert args[0] == expected_args[0]

            if issubclass(expected_args[1], BaseModel):
                assert args[1] == expected_args[1].model_views[view_name]  # type: ignore
            else:
                assert args[1] == expected_args[1]
        else:
            if issubclass(expected_args[0], BaseModel):
                assert args[0] == expected_args[0].model_views[view_name]  # type: ignore
            else:
                assert args[0] == expected_args[0]


@pytest.mark.parametrize(
    ("view_name", "access_modes"),
    [
        ("ReadOnlyAllNullable", (AccessMode.READ_ONLY,)),
    ],
)
def test_view_complex_types_all_nullable(
    view_name: str, access_modes: tuple[AccessMode, ...]
):
    builder = Builder(view_name, access_modes=access_modes, all_nullable=True)

    view_cls = builder.build_view(ModelComplexTypes)

    assert view_cls.__name__ == f"ModelComplexTypes{view_name}"

    for f_name, f_info in view_cls.model_fields.items():
        expected_origin = get_origin(ModelComplexTypes.model_fields[f_name].annotation)
        expected_args = get_args(ModelComplexTypes.model_fields[f_name].annotation)

        assert get_origin(f_info.annotation) is Union  # type: ignore
        assert issubclass(get_args(f_info.annotation)[-1], NoneType)
        origin = get_origin(get_args(f_info.annotation)[0])
        args = get_args(get_args(f_info.annotation)[0])

        assert origin == expected_origin
        if issubclass(expected_origin, Mapping):  # type: ignore
            assert args[0] == expected_args[0]
            assert get_origin(args[1]) is Optional or (  # type: ignore
                get_origin(args[1]) is Union  # type: ignore
                and issubclass(get_args(args[1])[-1], NoneType)
            )

            klss = get_args(args[1])[0]

            if issubclass(expected_args[1], BaseModel):
                assert klss == expected_args[1].model_views[view_name]  # type: ignore
            else:
                assert klss == expected_args[1]
        else:
            if issubclass(expected_args[0], BaseModel):
                klss = args[0]
                if issubclass(origin, tuple):
                    assert get_origin(klss) is Optional or (  # type: ignore
                        get_origin(klss) is Union  # type: ignore
                        and issubclass(get_args(klss)[-1], NoneType)
                    )
                    klss = get_args(klss)[0]

                assert klss == expected_args[0].model_views[view_name]  # type: ignore
            elif issubclass(origin, tuple):
                assert args[0] == Optional[expected_args[0]], f_name  # type: ignore
            else:
                assert args[0] == expected_args[0], f_name


@pytest.mark.parametrize(
    ("builder", "view_name", "expected_fields"),
    [
        pytest.param(
            BuilderLoad,
            "Load",
            {
                "field_int",
                "read_only_field_int",
                "field_str",
                "read_only_field_str",
                "read_and_write_field_int",
                "read_and_write_field_str",
                "computed_field_int",
                "literal_int",
                "literal_read_only_str",
            },
            id="Load",
        ),
        pytest.param(
            BuilderUpdate,
            "Update",
            {
                "field_int",
                "write_only_field_int",
                "field_str",
                "write_only_field_str",
                "read_and_write_field_int",
                "read_and_write_field_str",
                "literal_int",
            },
            id="Update",
        ),
        pytest.param(
            BuilderCreateResult,
            "CreateResult",
            {
                "field_int",
                "read_only_field_int",
                "read_only_on_creation_field_int",
                "field_str",
                "read_only_field_str",
                "read_only_on_creation_field_str",
                "read_and_write_field_int",
                "read_and_write_field_str",
                "computed_field_int",
                "literal_int",
                "literal_read_only_str",
            },
            id="CreateResult",
        ),
        pytest.param(
            BuilderCreate,
            "Create",
            {
                "field_int",
                "write_only_field_int",
                "write_only_on_creation_field_int",
                "field_str",
                "write_only_field_str",
                "write_only_on_creation_field_str",
                "read_and_write_field_int",
                "read_and_write_field_str",
                "literal_int",
            },
            id="Create",
        ),
    ],
)
def test_standard_builders(
    builder: Callable[[], Builder], view_name: str, expected_fields: set[str]
):
    view = builder().build_view(Model)

    assert ensure_model_views(Model)[view_name] == view
    assert set(view.model_fields.keys()) == expected_fields
