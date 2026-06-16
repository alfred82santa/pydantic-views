from abc import ABC
from collections.abc import Callable, Iterable
from copy import deepcopy
from functools import wraps
from typing import TYPE_CHECKING, Any, cast
from weakref import ref

from pydantic import PydanticUserError
from pydantic._internal._config import ConfigWrapper
from pydantic._internal._generics import get_args
from pydantic._internal._model_construction import ModelMetaclass

from .annotations import AccessMode, AccessTag

if TYPE_CHECKING:
    from .builder import Preset


def with_preset[F: Callable[..., Any]](new: F) -> F:
    """
    Decorate :meth:`ViewMetaClass.__new__` to accept a ``preset`` keyword.

    When a :class:`~pydantic_views.builder.Preset` is passed as the ``preset`` class keyword,
    its fields supply the default values for the matching ``__new__`` keyword parameters
    (``view_name``, ``access_modes``, ...). Any keyword passed explicitly still takes precedence
    over the preset value.

    :param new: The ``__new__`` method to wrap.
    :returns: Wrapped ``__new__`` resolving ``preset`` into keyword defaults.
    """

    @wraps(new)
    def wrapper(cls, name, bases, namespace, *, preset: "Preset | None" = None, **kwargs):
        if preset is not None:
            for field, value in preset._asdict().items():
                kwargs.setdefault(field, value)
        return new(cls, name, bases, namespace, **kwargs)

    return cast(F, wrapper)


class ViewMetaClass(ModelMetaclass):
    """Metaclass for View classes. It can be used to customize the creation of View classes if needed."""

    @with_preset
    def __new__(
        cls,
        name,
        bases,
        namespace,
        *,
        view_name: str | None = None,
        access_modes: Iterable[AccessMode] | None = None,
        include_tags: Iterable[AccessTag] | None = None,
        exclude_tags: Iterable[AccessTag] | None = None,
        all_optional: bool = False,
        all_nullable: bool = False,
        hide_default_null: bool = False,
        include_computed_fields: bool = False,
        no_process: bool = False,
        **kwargs,
    ):
        if ABC in bases or namespace.get("__module__") == "pydantic_views.view":
            return super().__new__(cls, name, bases, namespace, **kwargs)

        from .builder import ensure_model_views

        if view_name is None:
            raise TypeError("View name must be provided for non-abstract View classes")

        from .view import View

        view_class = next(b for b in bases if issubclass(b, View))

        model_class = get_args(view_class)[0]

        manager = ensure_model_views(model_class)
        try:
            return manager[view_name]
        except KeyError:
            pass

        namespace["__model_class_root__"] = ref(model_class)
        namespace["model_config"] = deepcopy(model_class.model_config)
        namespace["model_config"]["protected_namespaces"] = tuple(
            {
                *ConfigWrapper(model_class.model_config).protected_namespaces,
                *ConfigWrapper(view_class.model_config).protected_namespaces,
            }
        )

        if no_process:
            return super().__new__(cls, name, bases, namespace, **kwargs)

        from .builder import Builder

        builder = Builder(
            view_name=view_name,
            access_modes=set(access_modes) if access_modes is not None else set(),
            include_tags=set(include_tags) if include_tags is not None else set(),
            exclude_tags=set(exclude_tags) if exclude_tags is not None else set(),
            all_optional=all_optional,
            all_nullable=all_nullable,
            hide_default_null=hide_default_null,
            include_computed_fields=include_computed_fields,
        )
        builder.set_forward_ref(model_class, name, namespace["__module__"])

        field_definitions = builder.define_fields_from_model(model_class)

        annotations: dict[str, Any] = {}
        fields: dict[str, Any] = {}
        for f_name, f_def in field_definitions.items():
            if isinstance(f_def, tuple):
                if len(f_def) != 2:  # pragma: no cover
                    raise PydanticUserError(
                        f"Field definition for {f_name!r} should a single element "
                        "representing the type or a two-tuple, the first element "
                        "being the type and the second element the assigned value "
                        "(either a default or the `Field()` function).",
                        code="create-model-field-definitions",
                    )

                annotations[f_name] = f_def[0]
                fields[f_name] = f_def[1]
            else:  # pragma: no cover
                annotations[f_name] = f_def

        if "__annotate_func__" in namespace:
            annotate_func = namespace["__annotate_func__"]
            namespace["__annotate_func__"] = lambda f: annotate_func(f) | annotations
        else:
            namespace.setdefault("__annotations__", {})
            namespace["__annotations__"].update(annotations)
        namespace.update(fields)

        view_cls = super().__new__(cls, name, bases, namespace, **kwargs)
        model_class.model_views[view_name] = view_cls  # type: ignore

        return view_cls
