from collections.abc import Mapping
from typing import Any, ClassVar, cast, overload
from weakref import ReferenceType

from pydantic import BaseModel, RootModel


class View[T: BaseModel](BaseModel):
    """
    View of model.
    """

    __model_class_root__: ClassVar[ReferenceType[type[BaseModel]]]

    model_config = {
        "protected_namespaces": (
            "view_class_root",
            "view_build_to",
            "view_apply_to",
            "view_build_from",
        )
    }

    @classmethod
    def view_class_root(cls) -> type[T]:
        """
        Returns the class object associated to the view.

        :returns: Associated model class.
        """

        root = cls.__model_class_root__()

        if root is None:  # pragma: no cover
            raise RuntimeError("Root model disappeared")

        return cast(type[T], root)

    @classmethod
    def view_build_from(cls, model: T):
        """
        Build view from given model.

        :param model: Model class to build view from.
        :returns: View of model class.
        """
        return cls.model_validate(model.model_dump(exclude_unset=True, by_alias=True))

    def view_build_to(self) -> T:
        """
        Build associated model from view data.

        :returns: Associated model instance with view data.
        """

        return self.view_class_root().model_validate(
            self.model_dump(exclude_unset=True, exclude_defaults=True, by_alias=True)
        )

    def view_apply_to(self, model: T) -> T:
        """
        Apply view data to associated model.

        :param model: Model instance to use as base..
        :returns: Associated model instance with view data merged to given model data.
        """

        return model_apply(model, self)


class RootView[R](View[RootModel[R]], RootModel[R]):
    """
    View for root models.
    """


def model_apply[T: BaseModel](orig: T, view: View[T] | T) -> T:
    """
    Merge view or model into model
    """

    update_data: dict[str, Any] = {}

    for field in view.model_fields_set:
        value = _merge_values(
            getattr(orig, field),
            getattr(view, field),
        )
        update_data[field] = getattr(
            orig.__pydantic_validator__.validate_assignment(orig, field, value), field
        )
    return orig.model_copy(
        update=update_data,
        deep=True,
    )


@overload
def _merge_values[T: BaseModel](
    orig_value: None, new_value: T
) -> T | dict[str, Any]: ...


@overload
def _merge_values[T: BaseModel, A](orig_value: None, new_value: A) -> A: ...


@overload
def _merge_values[T: BaseModel, A](
    orig_value: T, new_value: View[T]
) -> T | dict[str, Any]: ...


def _merge_values[T: BaseModel, A](
    orig_value: T | None, new_value: View[T] | A
) -> T | A | dict[str, Any]:
    if isinstance(new_value, BaseModel):
        if isinstance(orig_value, BaseModel):
            return cast(T, model_apply(orig_value, new_value))
        if isinstance(new_value, View):
            return cast(View[T], new_value).view_build_to()
        return new_value.model_dump(
            exclude_unset=True, exclude_defaults=True, by_alias=True
        )
    elif isinstance(new_value, Mapping) and isinstance(orig_value, Mapping):
        data: dict[str, Any] = dict(cast(Mapping[str, Any], orig_value))
        for k, v in cast(Mapping[str, Any], new_value).items():
            data[k] = _merge_values(data.get(k), v)

        return cast(T, cast(Mapping[str, Any], orig_value).__class__(**data))
    else:
        return cast(T, new_value)
