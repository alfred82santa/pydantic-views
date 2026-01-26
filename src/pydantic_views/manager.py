from typing import TYPE_CHECKING
from weakref import ref

from pydantic import BaseModel

from .view import View

if TYPE_CHECKING:
    from .builder import Builder


class Manager[TModel: BaseModel]:
    """Registry and factory for views derived from a model class."""

    __slots__ = ("_model", "_views")

    def __init__(self, model: type[TModel]):
        """
        Initialize a manager for the given model type.

        :param model: Base model class that views will be derived from.
        """
        self._model = ref(model)
        self._views: dict[str, type[View[TModel] | TModel]] = {}

    @property
    def model(self) -> type[TModel]:
        """
        Associated model class.

        :returns: Model class associated with this manager.
        """
        result = self._model()
        if not result:  # pragma: no cover
            raise RuntimeError("Model class disappeared")
        return result

    def __getitem__(self, view_name: str) -> type["View[TModel] | TModel"]:
        """
        Get a model view.

        :param view_name: Name of view to get.
        :returns: View class registered under ``view_name``.
        """
        return self._views[view_name]

    def __setitem__(self, view_name: str, view: type["View[TModel] | TModel"]):
        """
        Set a model view.

        :param view_name: Name to register the view under.
        :param view: View class to associate with the name.
        """
        self._views[view_name] = view

    def build_view(self, builder: "Builder") -> type["View[TModel] | TModel"]:
        """
        Build view class for Manager's model.

        :param builder: Builder used to generate the view for the managed model.
        :returns: Newly built view class registered under the builder name.
        """
        view = builder.build_from_model(self.model)
        self[builder.view_name] = view

        return view
