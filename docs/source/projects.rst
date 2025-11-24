Creating Projects
=================

SSSOM Curator supports creating a project with ``sssom_curator init``.

Target Directory
----------------

SSSOM Curator will create a project in the working directory, or, in a target directory
by providing a name, e.g., ``sssom_curator init -d foo``. If there's already a project
in the target directory, e.g., if there's already a ``positives.sssom.tsv`` file, SSSOM
Curator will exit with an error.

.. code-block:: console

    $ sssom_curator init -d example-repo
    initialized SSSOM project `example-repo` at `/path/to/example-repo`

Contents
--------

The project includes a configuration file ``sssom-curator.json``, a script
(``main.py``), a readme, a license (CC0 by default), and SSSOM data files.

.. code-block:: console

    $ cd example-repo
    $ tree example-repo
    ├── LICENSE
    ├── README.md
    ├── main.py
    ├── data
    │   ├── negative.sssom.tsv
    │   ├── positive.sssom.tsv
    │   ├── predictions.sssom.tsv
    │   └── unsure.sssom.tsv
    └── sssom-curator.json

The ``sssom-curator.json`` file contains metadata described by the
:class:`sssom_curator.Repository` class.

.. code-block:: json

    {
       "predictions_path": "source/predictions.sssom.tsv",
       "positives_path": "source/positive.sssom.tsv",
       "negatives_path": "source/negative.sssom.tsv",
       "unsure_path": "source/unsure.sssom.tsv",
       "mapping_set": {
         "mapping_set_id": "https://example.org/test.tsv",
         "mapping_set_confidence": null,
         "mapping_set_description": null,
         "mapping_set_source": null,
         "mapping_set_title": "Test",
         "mapping_set_version": null,
         "see_also": null,
         "comment": null,
         "license": "spdx:CC0-1.0",
         "creator_id": null
       },
       "purl_base": "https://example.org/",
    }

The ``main.py`` contains boilerplate for loading the configuration JSON and running a
CLI via :meth:`sssom_curator.Repository.run_cli`. It contains `PEP 723
<https://peps.python.org/pep-0723/>`_ compliant inline metadata and an appropriate
shebang so it can be run like:

1. Via uv with ``uv run main.py``
2. As a script with ``./main.py``
3. As a plain Python module with ``python main.py`` (requires manual environment
   construction, not recommended)

Usage with Git and GitHub
-------------------------

Based on the `Open Data, Open Code, Open Infrastructure (O3)
<https://doi.org/10.1038/s41597-024-03406-w>`_ guidelines, we suggest using git as a
version control system in combination with GitHub as a web interface with the following
steps:

1. `Create an account
   <https://docs.github.com/en/get-started/start-your-journey/creating-an-account-on-github>`_
   on GitHub and sign in
2. `Create a repository
   <https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository>`_
   on GitHub
3. `Clone the repository
   <https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository>`_
   to your local system

If your repository is called ``owner/repository`` and you're using the console, then you
can run the following commands to clone the repository locally, ``cd`` into it,
initialize it, then commit/push it.

.. code-block:: console

    $ git clone https://github.com/owner/repository.git
    $ cd repository
    $ sssom_curator init
    $ git add --all
    $ git commit -m "initialized SSSOM project"
    $ git push

Making Predictions
------------------

After initialization, you can generate predicted semantic mappings using the ``predict``
command in the CLI, e.g., between Medical Subject Headings (MeSH) and the Medical
Actions Ontology (MaxO) with:

.. code-block:: console

    $ uv run main.py predict lexical mesh maxo

.. note::

    This is a nested command to make it possible to register additional commands in the
    future

Making New Resources Available
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This workflow accepts two _prefixes_ for resources corresponding to records in `the
Bioregistry <https://bioregistry.io>`_ (:mod:`bioregistry`) as a standard. Note that
despite its name, the Bioregistry (despite the "bio-" name) is domain-agnostic and
contains prefixes for ontologies, controlled vocabularies, databases, and other
resources that mint identifiers in other domains such as engineering, cultural heritage,
digital humanities, and more. Bioregistry records that contain links to OWL, OBO, or
SKOS ontologies can be readily used in the SSSOM-Curator workflow. If the Bioregistry
contains such an ontology link, then the workflow uses :mod:`pyobo` to parse them.
Otherwise, it looks in :mod:`pyobo.sources` for a custom import module.

If you want to use this interface to predict mappings to/from a resource that is not
available in the Bioregistry, consider submitting a `new prefix request
<https://github.com/biopragmatics/bioregistry/issues/new?template=new-prefix.yml>`_ on
the Bioregistry's issue tracker. If the resource you want to use already has a
Bioregistry record, but does not have an ontology artifact, then request a `new source
module <https://github.com/biopragmatics/pyobo/issues/new>`_ on the PyOBO issue tracker
or submit a pull request implementing one.

Creating Custom Mapping Generators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Any custom workflows that produce predicted mappings can be added to the project via
:meth:`sssom_curator.Repository.append_predicted_mappings` like in the following, which
exploits the structure of names of human proteins in MeSH to map them back to HGNC, then
UniProt:

.. code-block:: python

    import re

    import pyobo
    from curies import NamedReference
    from curies.vocabulary import exact_match, lexical_matching_process
    from pyobo.struct import has_gene_product
    from sssom_curator import Repository
    from sssom_pydantic import MappingTool, SemanticMapping

    from main import repository

    MESH_PROTEIN_RE = re.compile(r"^(.+) protein, human$")
    MAPPING_TOOL = MappingTool(name="mesh-uniprot-mapper")

    grounder = pyobo.get_grounder("hgnc")
    hgnc_id_to_uniprot_id = pyobo.get_relation_mapping(
        "hgnc", relation=has_gene_product, target_prefix="uniprot"
    )
    mappings = []
    for mesh_id, mesh_name in pyobo.get_id_name_mapping("mesh").items():
        match = MESH_PROTEIN_RE.match(mesh_name)
        if not match:
            continue
        gene_name = match.groups()[0]
        for gene_reference in grounder.get_matches(gene_name):
            uniprot_id = hgnc_id_to_uniprot_id.get(gene_reference.identifier)
            if not uniprot_id or "," in uniprot_id:
                continue
            mappings.append(
                SemanticMapping(
                    subject=NamedReference(
                        prefix="mesh", identifier=mesh_id, name=mesh_name
                    ),
                    predicate=exact_match.curie,
                    object=NamedReference(
                        prefix="uniprot", identifier=uniprot_id, name=gene_reference.name
                    ),
                    justification=lexical_matching_process,
                    confidence=gene_reference.score,
                    mapping_tool=mapping_tool,
                )
            )
    repository.append_predicted_mappings(mappings)

For example, you might want to implement a graph machine learning-based method for
predicting mappings or implement a wrapper around some of the tricky existing mapping
tools (like LogMap).

Importing Mappings
------------------

As an alternative to predicting mappings directly, SSSOM Curator exposes ways of
importing mappings from other sources.

BioPortal
~~~~~~~~~

`BioPortal <https://bioportal.bioontology.org/>`_ is an instance of the `OntoPortal
<https://ontoportal.org/>`_ ontology catalog focused on biological and biomedical
ontologies. It predicts semantic mappings through an ensemble of methods such lexical
matches produced by `LOOM <https://pubmed.ncbi.nlm.nih.gov/20351849/>`_ and inferred
mappings produced using the UMLS, which can be processed into low-precision SSSOM
mappings that are a good target for curation. See `this blog post
<https://cthoyt.com/2025/11/23/sssom-from-bioportal.html>`_ for more information on how
processing is done.

The OntoPortal mappings endpoint only allows pairwise comparison, so SSSOM Curator
exposes the ``import ontoportal`` command that takes two prefixes. An ``--instance`` can
be given to specify which OntoPortal to use, defaulting to BioPortal

.. code-block:: console

    $ uv run main.py import ontoportal snomed aero

.. note::

    This command accepts Bioregistry prefixes, which are internally mapped to the
    appropriate OntoPortal instance's prefixes.

SeMRA
~~~~~

The `SeMRA Raw Mappings Database <https://doi.org/10.5281/zenodo.11082038>` can be
imported and filtered to mappings that haven't already been curated with high precision.
You need to specify two or more prefixes using the ``-p`` flag.

.. code-block:: console

    $ uv run main.py import semra -p mesh -p hgnc

Note, this takes about five minutes to download and twenty minutes to process due to the
size of the SeMRA Raw Mappings Database.

Curation
--------

Finally, after making predictions, a local, web-based curation application can be run
with the following command. It has integrations with ``git`` to manage making commits
and pushes during curation.

.. code-block:: console

    $ uv run main.py web

Project Maintenance
-------------------

Format/lint the mappings with:

.. code-block:: console

    $ uv run main.py lint

Test the integrity of mappings with:

.. code-block:: console

    $ uv run main.py test

This can easily be incorporated in a GitHub Actions workflow like in the followingL:

.. code-block:: yaml

    name: Tests
    on:
      push:
        branches: [ main ]
      pull_request:
        branches: [ main ]
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: astral-sh/setup-uv@v3
          - name: Test SSSOM integrity
            run: uv run main.py test
