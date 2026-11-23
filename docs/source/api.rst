=============
API reference
=============

The main API is exported directly from :mod:`pydantic_views`. Start with the annotation
aliases and a preset; use builders and the registry when generating views dynamically.
For behavior and complete workflows, see :doc:`guide` and :doc:`examples`.

.. _api-annotations:

Field annotations
=================

These generic aliases attach access modes through ``Annotated``. They select fields for
a view; they do not implement application authorization. The preset determines which modes
are included. In particular, ``PartialPreset`` does not filter access modes.

.. py:data:: ReadAndWrite
   :module: pydantic_views
   :type: typing.TypeAlias

   Include a field in both input and output views. Equivalent to
   ``Annotated[T, AccessMode.READ_AND_WRITE]``. Unmarked fields also pass mode selection.

.. py:data:: ReadOnly
   :module: pydantic_views
   :type: typing.TypeAlias

   Include in load and create-result views, excluding normal create and update input.
   Equivalent to ``Annotated[T, AccessMode.READ_ONLY]``.

.. py:data:: WriteOnly
   :module: pydantic_views
   :type: typing.TypeAlias

   Include in create and update input, excluding load and create-result output.
   Equivalent to ``Annotated[T, AccessMode.WRITE_ONLY]``.

.. py:data:: ReadOnlyOnCreation
   :module: pydantic_views
   :type: typing.TypeAlias

   Include only in the standard create-result response, for data returned once after
   creation. Equivalent to ``Annotated[T, AccessMode.READ_ONLY_ON_CREATION]``.

.. py:data:: WriteOnlyOnCreation
   :module: pydantic_views
   :type: typing.TypeAlias

   Include only in standard create input, for data accepted once during creation.
   Equivalent to ``Annotated[T, AccessMode.WRITE_ONLY_ON_CREATION]``.

.. py:data:: Hidden
   :module: pydantic_views
   :type: typing.TypeAlias

   Exclude from standard access-filtered presets. Unfiltered views, including Partial,
   can still include it. Equivalent to ``Annotated[T, AccessMode.HIDDEN]``.

.. autoclass:: pydantic_views.AccessMode
   :members:

.. autoclass:: pydantic_views.AccessTag
   :members:

Standard presets
================

Pass a preset as ``preset=`` on a ``View`` subclass, or use
``Builder(**preset._asdict())``. Explicit class keywords override preset values.

.. autoclass:: pydantic_views.Preset
   :members:

.. py:data:: CreatePreset
   :module: pydantic_views
   :type: Preset

   Select read/write, write-only, and write-only-on-creation fields. Enable
   ``hide_default_null``. Registered view name: ``Create``.

.. py:data:: CreateResultPreset
   :module: pydantic_views
   :type: Preset

   Select read/write, read-only, and read-only-on-creation fields, including computed
   values. Registered view name: ``CreateResult``.

.. py:data:: LoadPreset
   :module: pydantic_views
   :type: Preset

   Select read/write and read-only fields, including computed values.
   Registered view name: ``Load``.

.. py:data:: UpdatePreset
   :module: pydantic_views
   :type: Preset

   Select read/write and write-only fields. Make selected fields optional with a
   ``MISSING`` default. Registered view name: ``Update``.

.. py:data:: PartialPreset
   :module: pydantic_views
   :type: Preset

   Include all model fields, regardless of access mode, and make them optional with a
   ``MISSING`` default. Exclude computed fields. Registered view name: ``Partial``.

Views and conversion
====================

Generated views are `Pydantic <https://pydantic.dev/>`_ models with additional conversion helpers. Reconstruction
validates against the source model. Update helpers merge explicitly supplied fields;
see :doc:`guide` for merge semantics and instance handling.

.. autoclass:: pydantic_views.View
   :members: view_class_root, view_build_from, view_build_to, view_apply_to

.. autoclass:: pydantic_views.RootView
   :no-inherited-members:

.. autofunction:: pydantic_views.view.model_apply

.. autofunction:: pydantic_views.is_view_of

Builders and registry
=====================

A model's registry is keyed by view name. Reusing a source model and name returns the
registered class, so use distinct names for distinct contracts.

.. autoclass:: pydantic_views.Builder
   :members:

.. autofunction:: pydantic_views.BuilderCreate

.. autofunction:: pydantic_views.BuilderCreateResult

.. autofunction:: pydantic_views.BuilderLoad

.. autofunction:: pydantic_views.BuilderUpdate

.. autofunction:: pydantic_views.ensure_model_views

.. autoclass:: pydantic_views.Manager
   :members:
   :special-members: __getitem__, __setitem__

Static tooling
==============

The `mypy <https://mypy.readthedocs.io/>`_ plugin entry point is ``pydantic_views.mypy``.
The runtime stub generator is available as ``python -m pydantic_views.stubgen``. See
:doc:`type_checking` for setup,
supported workflows, and limitations.
