from collections.abc import Callable
from typing import Self, cast

import pytest
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from pydantic_views.annotations import WriteOnly
from pydantic_views.builder import BuilderLoad, BuilderUpdate, ensure_model_views
from pydantic_views.view import View, model_apply


class Model(BaseModel):
    """
    Test model
    """

    field_int: int = 1
    field_str: WriteOnly[str] = "default str"
    field_recurrent: WriteOnly["Self | None"] = None
    field_dict: dict[str, "Self"] = Field(default_factory=dict)


ModelUpdate = BuilderUpdate().build_view(Model)
ModelLoad = BuilderLoad().build_view(Model)
ensure_model_views(Model)["Replica"] = Model


class ModelAlias(Model, alias_generator=to_camel):
    pass


ModelAliasUpdate = BuilderUpdate().build_view(ModelAlias)
ModelAliasLoad = BuilderLoad().build_view(ModelAlias)
ensure_model_views(model=ModelAlias)["Replica"] = ModelAlias


@pytest.mark.parametrize(
    ("model_cls", "alias_gen"),
    [
        (Model, cast(Callable[[str], str], lambda s: s)),  # type: ignore
        (ModelAlias, to_camel),
    ],
)
def test_update_model[T: Model](model_cls: type[T], alias_gen: Callable[[str], str]):
    orig = model_cls.model_validate(
        {
            alias_gen("field_int"): 3,
            alias_gen("field_recurrent"): {
                alias_gen("field_int"): 2,
                alias_gen("field_str"): "no-touch",
            },
            alias_gen("field_dict"): {"test": {alias_gen("field_str"): "nnn"}},
        }
    )

    update = cast(View[T], ensure_model_views(model_cls)["Update"]).model_validate(
        {
            alias_gen("field_recurrent"): {alias_gen("field_int"): 5},
            alias_gen("field_dict"): {
                "test": {alias_gen("field_int"): 8},
                "test2": {alias_gen("field_int"): 9},
            },
        },
    )

    new_model = update.view_apply_to(orig)

    assert new_model.field_recurrent.field_int == 5  # type: ignore
    assert new_model.field_recurrent.field_str == "no-touch"  # type: ignore
    assert "test" in new_model.field_dict
    assert isinstance(new_model.field_dict["test"], model_cls)
    assert new_model.field_dict["test"].field_str == "nnn"
    assert new_model.field_dict["test"].field_int == 8
    assert "test2" in new_model.field_dict
    assert isinstance(new_model.field_dict["test2"], model_cls)
    assert new_model.field_dict["test2"].field_int == 9
    assert new_model.field_dict["test2"].field_str == "default str"


@pytest.mark.parametrize(
    ("model_cls", "alias_gen"),
    [
        (Model, cast(Callable[[str], str], lambda s: s)),  # type: ignore
        (ModelAlias, to_camel),
    ],
)
def test_model_perspective[T: Model](
    model_cls: type[T], alias_gen: Callable[[str], str]
):
    orig = model_cls.model_validate(
        {
            alias_gen("field_int"): 3,
            alias_gen("field_recurrent"): {
                alias_gen("field_int"): 2,
                alias_gen("field_str"): "no-touch",
            },
            alias_gen("field_dict"): {"test": {alias_gen("field_str"): "nnn"}},
        }
    )

    pov = cast(View[T], ensure_model_views(model_cls)["Load"]).view_build_from(orig)

    assert pov.field_int == 3  # type: ignore
    assert pov.field_dict["test"].field_int == 1  # type: ignore
    assert pov.field_dict["test"].field_dict == {}  # type: ignore


@pytest.mark.parametrize(
    ("model_cls", "alias_gen"),
    [
        (Model, cast(Callable[[str], str], lambda s: s)),  # type: ignore
        (ModelAlias, to_camel),
    ],
)
def test_no_view[T: Model](model_cls: type[T], alias_gen: Callable[[str], str]):
    assert (
        model_cls.model_fields == ensure_model_views(model_cls)["Replica"].model_fields
    )

    orig = model_cls.model_validate(
        {
            alias_gen("field_int"): 3,
            alias_gen("field_recurrent"): {
                alias_gen("field_int"): 2,
                alias_gen("field_str"): "no-touch",
            },
            alias_gen("field_dict"): {"test": {alias_gen("field_str"): "nnn"}},
        }
    )

    update = cast(View[T], ensure_model_views(model_cls)["Replica"]).model_validate(  # type: ignore
        {
            alias_gen("field_recurrent"): {alias_gen("field_int"): 5},
            alias_gen("field_dict"): {
                "test": {alias_gen("field_int"): 8},
                "test2": {alias_gen("field_int"): 9},
            },
        },
    )

    new_model = model_apply(orig, update)

    assert new_model.field_recurrent.field_int == 5  # type: ignore
    assert new_model.field_recurrent.field_str == "no-touch"  # type: ignore
    assert "test" in new_model.field_dict
    assert isinstance(new_model.field_dict["test"], model_cls)
    assert new_model.field_dict["test"].field_str == "nnn"
    assert new_model.field_dict["test"].field_int == 8
    assert "test2" in new_model.field_dict
    assert isinstance(new_model.field_dict["test2"], model_cls)
    assert new_model.field_dict["test2"].field_int == 9
    assert new_model.field_dict["test2"].field_str == "default str"
