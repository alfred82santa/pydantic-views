==========
User guide
==========

A view is a Pydantic model derived from another model's fields. It defines a data contract
for a particular operation without duplicating the source field definitions. Start with a
preset, then add explicit access rules or a custom configuration where needed.

Field access rules
==================

Use the annotation aliases exported by :mod:`pydantic_views`, or attach ``AccessMode``
values with ``Annotated``. A field with no access annotation is included regardless of the
selected modes. When a field has several modes, matching any selected mode includes it.

.. list-table:: Standard preset selection
   :header-rows: 1

   * - Annotation
     - Create
     - CreateResult
     - Load
     - Update
     - Partial
   * - Unmarked / ``ReadAndWrite[T]``
     - Yes
     - Yes
     - Yes
     - Yes
     - Yes
   * - ``ReadOnly[T]``
     - No
     - Yes
     - Yes
     - No
     - Yes
   * - ``WriteOnly[T]``
     - Yes
     - No
     - No
     - Yes
     - Yes
   * - ``ReadOnlyOnCreation[T]``
     - No
     - Yes
     - No
     - No
     - Yes
   * - ``WriteOnlyOnCreation[T]``
     - Yes
     - No
     - No
     - No
     - Yes
   * - ``Hidden[T]``
     - No
     - No
     - No
     - No
     - Yes
   * - Computed fields
     - No
     - Yes
     - Yes
     - No
     - No

Creation-only annotations distinguish one-time input, such as an invitation code, from
one-time output, such as a newly issued API credential. ``Hidden`` excludes a field from
presets with access filtering; it is not an unconditional exclusion from every custom view.

``PartialPreset`` has no access filter. It includes all source fields, even hidden and
write-only data, and makes them optional. Use it for internal snapshots or partial data
transfer when access filtering is not the goal.

Presets and declarative views
=============================

Use ``preset=`` on a ``View[Model]`` subclass for named schemas that work with the mypy
plugin and can declare their own fields:

.. testcode:: guide-create

   from pydantic import BaseModel
   from pydantic_views import CreatePreset, ReadOnly, View, WriteOnly

   class Account(BaseModel):
       id: ReadOnly[int]
       username: str
       password: WriteOnly[str]

   class AccountCreate(View[Account], preset=CreatePreset):
       accept_terms: bool

   payload = AccountCreate.model_validate(
       {"username": "ada", "password": "example-only", "accept_terms": True}
   )
   assert payload.accept_terms is True
   assert "id" not in AccountCreate.model_fields

Extra fields belong to the view, not the source model. Handle workflow fields such as
``accept_terms`` before converting or merging data into the source model.

Explicit keywords override preset defaults. For example, ``view_name="Public"`` changes
the registered name, and ``include_computed_fields=False`` suppresses computed output.
To share custom settings, create a ``Preset`` with the same options accepted by ``Builder``:

.. testcode:: guide-custom-preset

   from pydantic import BaseModel
   from pydantic_views import AccessMode, Preset, ReadOnly, View, WriteOnly

   ReviewPreset = Preset(
       view_name="Review",
       access_modes=(AccessMode.READ_AND_WRITE, AccessMode.READ_ONLY),
       include_computed_fields=False,
   )

   class Submission(BaseModel):
       id: ReadOnly[int]
       title: str
       moderation_note: WriteOnly[str]

   class SubmissionReview(View[Submission], preset=ReviewPreset):
       pass

   assert set(SubmissionReview.model_fields) == {"id", "title"}

Optional, nullable, and omitted
===============================

These are distinct properties:

* **Optional input** may be omitted. ``all_optional=True`` uses ``MISSING`` as the field's
  default and adds the sentinel to its annotation. It also replaces source defaults and
  default factories, so omitted fields do not silently become update values.
* **Nullable input** accepts ``None`` when the annotation allows it. Making a field
  optional does not make it nullable.
* **Unset input** is absent from ``model_fields_set``. View update helpers use the set of
  supplied fields to decide what to merge.

Pydantic omits ``MISSING`` values from serialization. A supplied ``None`` remains a value:

.. testcode:: guide-omission

   from pydantic import BaseModel
   from pydantic_core import MISSING
   from pydantic_views import UpdatePreset, View

   class Preferences(BaseModel):
       theme: str = "light"
       nickname: str | None = None

   class PreferencesUpdate(View[Preferences], preset=UpdatePreset):
       pass

   omitted = PreferencesUpdate.model_validate({})
   cleared = PreferencesUpdate.model_validate({"nickname": None})
   assert omitted.theme is MISSING
   assert omitted.model_dump() == {}
   assert cleared.model_dump() == {"nickname": None}

``all_nullable=True`` broadens supported annotations for a view; the source model's
validation rules still apply when rebuilding or applying it. In particular, it does not
make the original model's non-nullable fields accept ``None``. Literal and root-model
annotations have special handling; validate the desired contract before using a custom
nullable preset.

``CreatePreset`` uses ``hide_default_null=True``. For fields whose default is ``None``,
the view preserves omission without advertising a ``None`` default in its schema. The
builder also removes ``None`` branches while mapping union annotations in this mode:
omitting such a field can be allowed even when explicitly passing ``None`` is rejected.

Nested models and containers
============================

A view's configuration propagates to referenced Pydantic models, including recursive and
circular references. For example, ``UserLoad`` can contain generated ``AddressLoad``
instances, while ``UserUpdate`` contains the corresponding update views. Models inside
lists, sets, tuples, dictionaries, and unions are supported, as are generic Pydantic models.

Build nested values from dictionaries with ``model_validate()`` or project an existing
model with ``view_build_from()``. Generated nested classes need not be imported manually.
See :doc:`examples` for a complete nested-update workflow.

``RootModel`` sources receive ``RootView`` wrappers. Their payload remains available as
``root`` and serializes in the usual root-model form. The mypy plugin does not expand
``RootView`` fields; generated stubs can describe their runtime structure.

Validation and metadata
=======================

Views retain field definitions: aliases, defaults (unless overridden by a preset), titles,
descriptions, field metadata, and annotation-based validation constraints. For example:

.. testcode:: guide-validation

   from typing import Annotated

   from annotated_types import Gt
   from pydantic import BaseModel, Field
   from pydantic_views import AccessMode, LoadPreset, View

   class Metric(BaseModel):
       score: Annotated[int, AccessMode.READ_ONLY, Gt(0)]
       label: str = Field(min_length=1, description="Human-readable label")

   class MetricLoad(View[Metric], preset=LoadPreset):
       pass

   assert MetricLoad.model_validate({"score": 5, "label": "quality"}).score == 5

A view is a generated model, not a subclass of the source model. Do not assume that source
methods or ``@field_validator`` / ``@model_validator`` decorators are copied to it. Put
reusable field constraints in annotations, add view-specific validation explicitly, and
validate against the source model when reconstructing domain data.

Read presets include computed values as ordinary view fields. Populate them from a source
instance with ``view_build_from()``; a view does not recompute the source property itself.

Custom selection with tags
==========================

``AccessTag`` provides a second selection mechanism alongside access modes. Tags are
immutable, interned by name, and reusable across models.

.. testcode:: guide-tags

   from typing import Annotated

   from pydantic import BaseModel
   from pydantic_views import AccessMode, AccessTag, Hidden, View

   class Record(BaseModel):
       title: str
       owner: Annotated[str, AccessMode.READ_ONLY]
       internal_note: Annotated[str, AccessMode.WRITE_ONLY, AccessTag("support")]
       secret: Hidden[str]

   class SupportRecord(
       View[Record],
       view_name="Support",
       access_modes=(AccessMode.READ_ONLY,),
       include_tags=(AccessTag("support"),),
   ):
       pass

   assert set(SupportRecord.model_fields) == {"title", "owner", "internal_note"}

Unmarked fields pass the access-mode selection. ``include_tags`` can admit fields that do
not match the selected modes; ``exclude_tags`` removes matching fields from the normal
selection. Avoid overlapping include and exclude rules when defining a contract. With no
access modes or tag filters, every field is included, as in ``PartialPreset``.

Builders and the view registry
==============================

Builders create classes dynamically using the same configuration as declarative views.
The four CRUD builder helpers correspond to the create, create-result, load, and update
presets. Use ``Builder(**PartialPreset._asdict())`` for a dynamic Partial view.

.. testcode:: guide-registry

   from pydantic import BaseModel
   from pydantic_views import Builder, PartialPreset, ensure_model_views

   class Event(BaseModel):
       name: str
       sequence: int

   builder = Builder(**PartialPreset._asdict())
   EventPartial = builder.build_view(Event)
   assert builder.build_view(Event) is EventPartial
   assert ensure_model_views(Event)["Partial"] is EventPartial

``ensure_model_views(Model)`` returns the model's ``Manager``, a registry indexed by view
name. View classes are reused for a given source model and name; choose distinct names for
different configurations. Prefer declarative subclasses when you want mypy to understand
the source declaration, and generate stubs for dynamic classes.

Moving between models and views
===============================

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Helper
     - Purpose
   * - ``ViewClass.view_build_from(model)``
     - Validate a projection of the source model's explicitly set data.
   * - ``view.view_build_to()``
     - Validate view data against the source model; missing required source fields raise
       a validation error.
   * - ``view.view_apply_to(model)``
     - Apply explicitly supplied changes and return the merged model.
   * - ``ViewClass.view_class_root()``
     - Retrieve the source model class.

Updates merge nested model instances and mappings recursively. Sequences are replaced;
list items are not matched or merged by identity. Source-model validation applies to
assigned values. The current merge implementation validates assignments on the supplied
instance before returning a deep copy; pass ``model.model_copy(deep=True)`` if the original
must remain unchanged. Use update views whose fields belong to the source model.

Next steps
==========

Follow :doc:`examples` for complete workflows, :doc:`type_checking` to configure static
tools, or :doc:`api` for the public API.
