from typing import TYPE_CHECKING
from weakref import ref

from pydantic import BaseModel

from .view import View

if TYPE_CHECKING:
    from .builder import Builder


class Manager[TModel: BaseModel]:
    """
    Views manager for a given model class.
    """

    __slots__ = ("_model", "_views")

    def __init__(self, model: type[TModel]):
        """ """
        self._model = ref(model)
        self._views: dict[str, type["View[TModel] | TModel"]] = {}

    @property
    def model(self) -> type[TModel]:
        """
        Associated model class.

        :returns: Model class associated.
        """
        result = self._model()
        if not result:  # pragma: no cover
            raise RuntimeError("Model class disappeared")
        return result

    def __getitem__(self, view_name: str) -> type["View[TModel] | TModel"]:
        """
        Get a model view.

        :param view_name: Name of view to get.
        :returns: View of model class.
        """
        return self._views[view_name]

    def __setitem__(self, view_name: str, view: type["View[TModel] | TModel"]):
        """
        Set a model view.

        :param view_name: Name of view to get.
        :param view: View of model class.
        """
        self._views[view_name] = view

    def build_view(self, builder: "Builder") -> type["View[TModel] | TModel"]:
        """
        Build view class for Manager's model.

        :param builder: Builder to use to make the view of model.
        :returns: View of model class.
        """
        view = builder.build_from_model(self.model)
        self[builder.view_name] = view

        return view
