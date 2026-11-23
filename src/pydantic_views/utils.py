from typing import Any, TypeGuard, overload

from pydantic import BaseModel

from .view import View


@overload
def is_view_of[T: BaseModel](obj: type, klass: type[T]) -> TypeGuard[type[View[T]]]: ...


@overload
def is_view_of[T: BaseModel](obj: View[Any], klass: type[T]) -> TypeGuard[View[T]]: ...


@overload
def is_view_of[T: BaseModel](obj: object, klass: type[T]) -> TypeGuard[View[T] | type[View[T]]]: ...


def is_view_of[T: BaseModel](obj: object | type, klass: type[T]) -> TypeGuard[View[T] | type[View[T]]]:
    """Return whether ``obj`` is a view of ``klass``.

    ``obj`` may be a view instance or a view class. The check also accepts views
    whose source model is a subclass of ``klass``. Type checkers narrow a matching
    instance or class to the corresponding ``View[T]`` type.

    :param obj: Candidate view instance or view class.
    :param klass: Source model class the view should represent.
    :returns: ``True`` when the candidate is a matching view.
    """

    return (isinstance(obj, View) or (isinstance(obj, type) and issubclass(obj, View))) and issubclass(
        obj.view_class_root(), klass
    )
