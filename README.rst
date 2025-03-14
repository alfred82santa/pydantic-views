
.. |docs| image:: https://readthedocs.org/projects/pydantic-views/badge/?version=latest
    :alt: Documentation Status
    :target: https://pydantic-views.readthedocs.io/latest/?badge=latest

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/pydantic-views
   :alt: PyPI - Python Version

.. |typed| image:: https://img.shields.io/pypi/types/pydantic-views
   :alt: PyPI - Types

.. |license| image:: https://img.shields.io/pypi/l/pydantic-views
   :alt: PyPI - License

.. |version| image:: https://img.shields.io/pypi/v/pydantic-views
   :alt: PyPI - Version


|docs| |python-versions| |typed| |license| |version|

.. start-doc

======================================
View for Pydantic models documentation
======================================

This package provides a simple way to create `views` from `pydantic <https://docs.pydantic.dev/latest/>`_ models. A view is
another `pydantic <https://docs.pydantic.dev/latest/>`_ models with some of field of original model. So, for example, 
read only fields does not appears on `Create` or `Update` views.

As rest service definition you could do:

.. code-block:: python

   ExampleModelCreate = BuilderCreate().build_view(ExampleModel)
   ExampleModelCreateResult = BuilderCreateResult().build_view(ExampleModel)
   ExampleModelLoad = BuilderLoad().build_view(ExampleModel)
   ExampleModelUpdate = BuilderUpdate().build_view(ExampleModel)

   def create(input: ExampleModelCreate) -> ExampleModelCreateResult: ...
   def load(model_id: str) -> ExampleModelLoad: ...
   def update(model_id: str, input: ExampleModelUpdate) -> ExampleModelLoad: ...


--------
Features
--------

- Unlimited views per model.
- Create view for referenced inner models.
- It is possible to set a view manually.
- Tested code.
- Full typed.
- Opensource.
  

------------
Installation
------------

Using pip:

.. code-block:: bash

   pip install pydantic-views

Using `poetry <https://python-poetry.org/>`_:

.. code-block:: bash

   poetry add pydantic-views


----------
How to use
----------

When you define a pydantic model you must mark the access model for each field. It means
you should use our `annotations <https://pydantic-views.readthedocs.io/latest/api.html#field-annotations>`_ to define field typing.

.. code-block:: python

   from typing import Annotated
   from pydantic import BaseModel, gt
   from pydantic_views import ReadOnly, ReadOnlyOnCreation, Hidden, AccessMode

   class ExampleModel(BaseModel):

       # No marked fields are treated like ReadAndWrite fields.
       field_str: str

       # Read only fields are removed on view for create and update views.
       field_read_only_str: ReadOnly[str]

       # Read only on creation fields are removed on view for create, update and load views. 
       # But it is shown on create result view.
       field_api_secret: ReadOnlyOnCreation[str]

       # It is possible to set more than one access mode and to use annotation standard pattern.
       field_int: Annotated[int, AccessMode.READ_ONLY, AccessMode.WRITE_ONLY_ON_CREATION, gt(5)]

       # Hidden field do not appears in any view.
       field_hidden_int: Hidden[int]

       # Computed fields only appears on reading views.
       @computed_field
       def field_computed_field(self) -> int:
           return self.field_hidden_int * 5

So, in order to build a `Load` view it is so simple:

.. code-block:: python

   from pydantic_views import BuilderLoad

   ExampleModelLoad = BuilderLoad().build_view(ExampleModel)

It is equivalent to:


.. code-block:: python

   from pydantic import gt
   from pydantic_views import View

   class ExampleModelLoad(View[ExampleModel]):
       field_str: str
       field_int: Annotated[int, gt(5)]
       field_computed_field: int

In same way to build a `Update` view you must do:

.. code-block:: python

   from pydantic_views import BuilderUpdate

   ExampleModelUpdate = BuilderUpdate().build_view(ExampleModel)
   
It is equivalent to:

.. code-block:: python

   from pydantic import PydanticUndefined
   from pydantic_views import View

   class ExampleModelUpdate(View[ExampleModel]):
       field_str: str = Field(default_factory=lambda: PydanticUndefined)

As you can see, on `Update` view all fields has a default factory returning `PydanticUndefined`
in order to make them optionals. And when an update view is applied to a given model, the fields that are 
not set (use default value) will not be applied to the model.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything"
       field_read_only_str="anything"
       field_api_secret="anything"
       field_int=10
       field_hidden_int=33
   )

   update = ExampleModelUpdate(field_str="new_data")

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "new_data"


But if a field is not set on update view, the original value is kept.

.. code-block:: python

   original_model = ExampleModel(
       field_str="anything"
       field_read_only_str="anything"
       field_api_secret="anything"
       field_int=10
       field_hidden_int=33
   )

   update = ExampleModelUpdate()

   updated_model = update.view_apply_to(original_model)

   assert isinstance(updated_model, ExampleModel)
   assert updated_model.field_str == "anything"