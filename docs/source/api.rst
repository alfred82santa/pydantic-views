=============
API Reference
=============

.. _api-annotations:

-----------------
Field annotations
-----------------

.. py:data:: ReadAndWrite
   :module: pydantic_views
   :type: typing.TypeAlias

   Read and write field annotation. Field could be read and written always.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.READ_AND_WRITE`\ ]

.. py:data:: ReadOnly
   :module: pydantic_views
   :type: typing.TypeAlias

   Read only field annotation. Field could be read always but never written.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.READ_ONLY`\ ]

.. py:data:: WriteOnly
   :module: pydantic_views
   :type: typing.TypeAlias

   Write only field annotation. Field could be written always but never read.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.WRITE_ONLY`\ ]

.. py:data:: ReadOnlyOnCreation
   :module: pydantic_views
   :type: typing.TypeAlias

   Read only on creation field annotation. Field could be read only after creation, and never again.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.READ_ONLY_ON_CREATION`\ ]

.. py:data:: WriteOnlyOnCreation
   :module: pydantic_views
   :type: typing.TypeAlias

   Write only on creation field annotation. Field could be written only after creation, and never again.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.WRITE_ONLY_ON_CREATION`\ ]

.. py:data:: Hidden
   :module: pydantic_views
   :type: typing.TypeAlias

   Hidden field annotation. Field could not be read or written.

   alias of :class:`~typing.Annotated`\ [T, :py:obj:`~pydantic_views.AccessMode.HIDDEN`\ ]


-------
Classes
-------

.. automodule:: pydantic_views
   :members:
   :exclude-members: ReadAndWrite,ReadOnly,WriteOnly,ReadOnlyOnCreation,WriteOnlyOnCreation,Hidden
