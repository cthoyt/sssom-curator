Custom
======

Simplest
--------

First, choose where you want to initialize your SSSOM repository.

We suggest based on the `Open Data, Open Code, Open Infrastructure (O3)
<https://doi.org/10.1038/s41597-024-03406-w>`_ guidelines to begin by `creating a
repository
<https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository>`_
on GitHub then `cloning it
<https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository>`_
locally. This will look like the following in your console, where ``owner/repository``
gets replaced with yours:

.. code-block:: console

    $ git clone https://github.com/owner/repository.git
    $ cd repository

Initialize the repository using the following command. This will create four SSSOM files
for positive mappings, negative mappings, unsure mappings, and predicted mappings. It
will also create a ``main.py`` file that contains configuration for running various
workflows (prediction, curation web application, linting, testing). Then, you can
directly commit the changes.

.. code-block:: console

    $ sssom_curator init .
    $ git add -a
    $ git commit -m "initialized SSSOM repository"
    $ git push

Now that your folder has been seeded, you can begin by creating some mapping
predictions. The most straightforward way is lexical matching.

Create some predicted mappings

- quickest way is through the CLI, assuming the resources you care about are available
  through PyOBO. If not, you might be able to make them available by curating a new
  record in the Bioregistry or implementing a custom source in PyOBO (please make an
  issue)

  .. code-block:: console

      $ uv run main.py predict mesh maxo

The prefixes used for resources follow the Bioregistry as a standard. Note that despite
its name, the Bioregistry is domain-agnostic and contains prefixes for ontologies,
controlled vocabularies, databases, and other resources that mint identifiers in other
domains such as engineering, cultural heritage, digital humanities, and more.
Bioregistry records that contain links to OWL, OBO, or SKOS ontologies can be readily
used in the SSSOM-Curator workflow. If you would like to incorporate additional
ontologies, then this can be done by one of:

1. Making a new prefix request to the Bioregistry
2. Creating a custom source in PyOBO, if the source is not available in a standard
   format

Finally, after making predictions, a local, web-based curation application can be run
with the following command. It has integrations with ``git`` to manage making commits
and pushes during curation.

.. code-block:: console

    $ uv run main.py web

Understanding the Configuration
-------------------------------

1. What are the parts of the :class:`sssom_curator.Repository` object, and what do they
   do?
2. How to create custom mapping generators? e.g., with a defined configuration, that you
   might want to run periodically
