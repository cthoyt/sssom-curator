Custom
======

Simplest
--------

First, choose where you want to initialize your SSSOM repository.

We suggest based on the `Open Data, Open Code, Open Infrastructure (O3)
<https://doi.org/10.1038/s41597-024-03406-w>`_ guidelines to begin by `creating a public
version controlled repository on GitHub
<https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository>`_
then `cloning it locally
<https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository>`_.

After creating it on GitHub, this might look like the following in your console:

.. code-block:: console

    $ git clone https://github.com/owner/repository.git
    $ cd repository

Start a repo using ``sssom_curator init``. What are the options here?

.. code-block::

    $ uvx sssom_curator init .

Create some predicted mappings

- quickest way is through the CLI, assuming the resources you care about are available
  through PyOBO. If not, you might be able to make them available by curating a new
  record in the Bioregistry or implementing a custom source in PyOBO (please make an
  issue)

  .. code-block:: console

      $ uv run main.py predict mesh maxo

Run the curator app

.. code-block:: console

    $ uv run main.py web

Understanding the Configuration
-------------------------------

1. What are the parts of the :class:`sssom_curator.Repository` object, and what do they
   do?
2. How to create custom mapping generators? e.g., with a defined configuration, that you
   might want to run periodically
