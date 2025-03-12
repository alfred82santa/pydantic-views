from typing import TYPE_CHECKING
from weakref import ref

from pydantic import BaseModel

from .view import View

if TYPE_CHECKING:
    from .builder import Builder


class Manager[TModel: BaseModel]:
    __slots__ = ("_model", "_views")

    def __init__(self, model: type[TModel]):
        self._model = ref(model)
        self._views: dict[str, type["View[TModel] | TModel"]] = {}

    @property
    def model(self) -> type[TModel]:
        result = self._model()
        if not result:  # pragma: no cover
            raise RuntimeError("Model class disappeared")
        return result

    def __getitem__(self, view_name: str) -> type["View[TModel] | TModel"]:
        return self._views[view_name]

    def __setitem__(self, view_name: str, view: type["View[TModel] | TModel"]):
        self._views[view_name] = view

    def build_view(self, builder: "Builder") -> type["View[TModel] | TModel"]:
        view = builder.build_from_model(self.model)
        self[builder.suffix] = view

        return view
