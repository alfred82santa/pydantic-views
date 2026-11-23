from pydantic import BaseModel

from pydantic_views import View, is_view_of


class Model(BaseModel):
    value: int


class OtherModel(BaseModel):
    value: int


class ModelView(View[Model], view_name="View"):
    pass


def test_is_view_of_matches_view_instance() -> None:
    view = ModelView.model_validate({"value": 1})

    assert is_view_of(view, Model)
    assert not is_view_of(view, OtherModel)


def test_is_view_of_matches_view_class() -> None:
    assert is_view_of(ModelView, Model)
    assert not is_view_of(ModelView, OtherModel)


def test_is_view_of_rejects_models_and_other_objects() -> None:
    assert not is_view_of(Model(value=1), Model)
    assert not is_view_of(object(), Model)
