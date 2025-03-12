from collections.abc import Iterable, Mapping
from copy import deepcopy
from types import NoneType, UnionType
from typing import Union  # type: ignore[deprecated]
from typing import (
    Any,
    ForwardRef,
    cast,
    get_args,
    get_origin,
)
from weakref import ref

from pydantic import BaseModel, RootModel, create_model
from pydantic.fields import ComputedFieldInfo, FieldInfo
from pydantic_core import PydanticUndefined

from .annotations import AccessMode, FieldAccess
from .manager import Manager
from .view import RootView, View


class Builder:
    def __init__(
        self,
        suffix: str,
        access_modes: tuple[AccessMode, ...],
        all_optional: bool = False,
        all_nullable: bool = False,
        hide_default_null: bool = False,
        include_computed_fields: bool = False,
    ) -> None:
        self.suffix = suffix
        self.access_modes = access_modes
        self.all_optional = all_optional
        self.all_nullable = all_nullable
        self.hide_default_null = hide_default_null
        self.include_computed_fields = include_computed_fields
        self._views: dict[type[BaseModel], type[View[BaseModel]] | ForwardRef] = {}

    def build_view[T: BaseModel](self, model: type[T]) -> type[View[T] | T]:
        manager = ensure_model_views(model)
        try:
            result: type[View[T] | T] = manager[self.suffix]
        except (KeyError, TypeError):
            result = manager.build_view(self)

        [
            v.model_rebuild()  # type: ignore
            for v in self._views.values()
            if not isinstance(v, ForwardRef)
        ]

        return result

    def get_view_ref[T: BaseModel](
        self, model: type[T]
    ) -> type[View[T] | T] | ForwardRef:
        try:
            return cast(type[View[T]] | ForwardRef, self._views[model])
        except KeyError:
            pass

        manager = ensure_model_views(model)

        try:
            view: type[View[T] | T] = manager[self.suffix]
        except KeyError:
            view = manager.build_view(self)

        self._views[model] = cast(type[View[BaseModel]], view)

        return view

    def _filter_field(self, f_info: FieldInfo):
        am = {m.mode for m in f_info.metadata if isinstance(m, FieldAccess)}
        return len((am & set(self.access_modes))) == 0 and len(am) > 0

    def _iter_fields[T: BaseModel](self, model: type[T]):
        for f_name, f_info in model.model_fields.items():
            if self._filter_field(f_info):
                continue
            yield f_name, f_info

    def _filter_computed_field(self, f_info: ComputedFieldInfo) -> bool:
        return False

    def _iter_computed_fields[T: BaseModel](self, model: type[T]):
        for f_name, cf_info in model.model_computed_fields.items():
            if self._filter_computed_field(
                cf_info
            ):  # [TODO] does it have sense? #  pragma: no cover
                continue
            yield f_name, cf_info

    def build_from_model[T: BaseModel](self, model: type[T]) -> type[View[T] | T]:
        from pydantic._internal._config import ConfigWrapper

        view_name = model.__name__ + self.suffix[0].upper() + self.suffix[1:]
        try:
            view_cache = self._views[model]
            if not isinstance(view_cache, ForwardRef):
                return cast(type[View[T] | T], view_cache)
        except KeyError:
            self._views[model] = ForwardRef(view_name, module=model.__module__)

        view: type[View[T] | T]

        manager = ensure_model_views(model)

        try:
            view = manager[self.suffix]
            self._views[model] = cast(type[View[BaseModel]], view)
        except KeyError:
            model_fields: dict[str, tuple[type[Any] | None, FieldInfo]] = {}
            for f_name, f_info in self._iter_fields(model):
                model_fields[f_name] = self._map_field_info(
                    f_info.annotation,
                    f_info,
                    ignore_nullable=issubclass(model, RootModel),
                )

            if self.include_computed_fields:
                for f_name, cf_info in self._iter_computed_fields(model):
                    model_fields[f_name] = self._map_computed_field_info(cf_info)

            base_view: type[View[T]] | type[RootView[T]]

            if issubclass(model, RootModel):

                class _RootView(RootView[T]):
                    model_config = deepcopy(model.model_config)

                    __model_class_root__ = ref(cast(type[T], model))

                base_view = _RootView

            else:

                class _View(View[T]):
                    model_config = deepcopy(model.model_config)

                    __model_class_root__ = ref(cast(type[T], model))

                _View.model_config["protected_namespaces"] = tuple(
                    {
                        *ConfigWrapper(_View.model_config).protected_namespaces,
                        *ConfigWrapper(View.model_config).protected_namespaces,
                    }
                )

                base_view = _View

            params: dict[str, Any] = {
                "__module__": model.__module__,
                "__base__": base_view,
                "__doc__": (
                    f"View `{self.suffix}` "
                    f"of model :class:`~{model.__module__}.{model.__qualname__}`"
                ),
                **model_fields,
            }

            view = cast(
                type[View[T]],
                create_model(
                    view_name,
                    **params,
                ),
            )

            self._views[model] = cast(type[View[BaseModel]], view)

        return view

    def _map_field_info(
        self,
        annotation: type[Any] | None,
        f_info: FieldInfo,
        *,
        ignore_nullable: bool = False,
    ) -> tuple[type[Any] | None, FieldInfo]:
        f_info = FieldInfo.merge_field_infos(
            f_info,
            annotation=self._map_annotation(
                f_info.annotation, ignore_nullable=ignore_nullable
            ),
        )

        if self.all_optional:
            f_info = FieldInfo.merge_field_infos(
                f_info,
                default_factory=lambda: PydanticUndefined,
            )
            f_info.default = PydanticUndefined

        if self.hide_default_null and f_info.default is None:
            f_info = FieldInfo.merge_field_infos(
                f_info,
                default_factory=lambda: PydanticUndefined,
            )
            f_info.default = PydanticUndefined

        return f_info.annotation, f_info

    def _map_annotation(
        self, annotation: type[Any] | None, *, ignore_nullable: bool = False
    ) -> type[Any] | ForwardRef | None | UnionType:
        def finish_annotation(a: type[Any] | None) -> type[Any] | None | UnionType:
            if not ignore_nullable and self.all_nullable and a is not Ellipsis:  # type: ignore
                return Union[a, None]  # type: ignore

            return a

        try:
            if annotation and issubclass(annotation, BaseModel):
                return finish_annotation(self.get_view_ref(annotation))  # type: ignore
        except TypeError:
            pass

        origin = get_origin(annotation)
        type_args = get_args(annotation)

        if origin is None:
            return finish_annotation(annotation)

        if origin is not Union and not issubclass(origin, UnionType):  # type: ignore
            if issubclass(origin, Mapping):
                return finish_annotation(
                    origin[  # type: ignore
                        self._map_annotation(type_args[0], ignore_nullable=True),
                        self._map_annotation(type_args[1]),
                    ]
                )
            elif issubclass(origin, Iterable):
                return finish_annotation(
                    origin[  # type: ignore
                        *(
                            self._map_annotation(
                                t, ignore_nullable=issubclass(origin, (list, set))
                            )
                            for t in type_args
                        )
                    ]
                )

        return Union[  # type: ignore
            *(
                self._map_annotation(a)
                for a in type_args
                if a is not NoneType or not self.hide_default_null
            )
        ]

    def _map_computed_field_info(
        self, cf_info: ComputedFieldInfo
    ) -> tuple[type[Any] | None, FieldInfo]:
        return (
            cf_info.return_type,
            FieldInfo(
                annotation=cf_info.return_type,
                alias=cf_info.alias,
                default=None,
                alias_priority=cf_info.alias_priority,
                serialization_alias=cf_info.title,
                title=cf_info.title,
                description=cf_info.title,
                examples=cf_info.examples,
                discriminator=cf_info.title,
                deprecated=cf_info.title,
                json_schema_extra=cf_info.json_schema_extra,
                repr=cf_info.repr,
            ),
        )


def BuilderCreate(suffix: str = "Create") -> Builder:
    return Builder(
        suffix,
        access_modes=(
            AccessMode.READ_AND_WRITE,
            AccessMode.WRITE_ONLY,
            AccessMode.WRITE_ONLY_ON_CREATION,
        ),
        hide_default_null=True,
    )


def BuilderCreateResult(suffix: str = "CreateResult") -> Builder:
    return Builder(
        suffix,
        access_modes=(
            AccessMode.READ_AND_WRITE,
            AccessMode.READ_ONLY,
            AccessMode.READ_ONLY_ON_CREATION,
        ),
        include_computed_fields=True,
    )


def BuilderUpdate(suffix: str = "Update") -> Builder:
    return Builder(
        suffix,
        access_modes=(AccessMode.READ_AND_WRITE, AccessMode.WRITE_ONLY),
        all_optional=True,
    )


def BuilderLoad(suffix: str = "Load") -> Builder:
    return Builder(
        suffix,
        access_modes=(
            AccessMode.READ_AND_WRITE,
            AccessMode.READ_ONLY,
        ),
        include_computed_fields=True,
    )


def ensure_model_views[T: BaseModel](model: type[T]):
    try:
        if (
            manager := cast(Manager[T], getattr(model, "model_views"))
        ) and manager.model == model:
            return manager
    except AttributeError:
        pass

    manager = Manager(model)
    setattr(
        model,
        "model_views",
        manager,
    )

    return manager
