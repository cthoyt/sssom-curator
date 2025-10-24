SSSOM Curator |release| Documentation
=====================================

SSSOM Curator is a suite of tools for predicting and curating semantic mappings encoded
in the `Simple Standard for Sharing Ontological Mappings (SSSOM)
<https://mapping-commons.github.io/sssom/>`_. It has three major components:

1. A semantic mappings prediction workflow, with implementations for lexical matching
   and lexical embedding similarity and extensibility for additional implementations
2. A (local) web-based curation interface for quick triage of predicted semantic
   mappings that supports full curator provenance
3. A set of tools for data integrity testing, summarization, and export

The SSSOM Curator evolved from the `Biomappings
<https://github.com/biopragmatics/biomappings>`_ semi-automated curation workflow, but
is now fully domain-agnostic and reusable in custom environments. This package can be
used by a variety of people:

1. **Curator** - someone who creates data. For example, an ontologist might want to
   curate semantic mappings between terms in their ontology and external ontologies,
   controlled vocabularies, databases, or other resources that mint identifiers for
   entities in the same domain.
2. **Semantic Data Engineer** - someone who builds data pipelines. For example, a
   semantic data engineer might consume SSSOM from multiple sources to support the
   standardized identification of entities, and may directly use the SSSOM Curator
   Python package to support this
3. **Software Developer** - someone who develops tools to support data creators, data
   consumers, and other software developers. For example, a software developer might
   want to integrate SSSOM Curator in their toolchain and extend it to support their
   team of curators and semantic data engineers.

.. toctree::
    :maxdepth: 2
    :caption: Getting Started
    :name: start

    installation
    projects
    cli
    reference

Indices and Tables
------------------

- :ref:`genindex`
- :ref:`modindex`
- :ref:`search`
