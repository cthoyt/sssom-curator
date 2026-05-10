"""Constants for sssom-curator."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias

from curies import NamedReference
from sssom_pydantic.api import MAPPING_HASH_CURIE_PREFIX, MAPPING_HASH_URI_PREFIX

if TYPE_CHECKING:
    import curies
    from sssom_pydantic import SemanticMapping

__all__ = [
    "DEFAULT_RESOLVER_BASE",
    "NEGATIVES_NAME",
    "POSITIVES_NAME",
    "PREDICTIONS_NAME",
    "TOOL_NAME",
    "TOOL_REFERENCE",
    "UNSURE_NAME",
    "PredictionMethod",
    "RecognitionMethod",
    "ensure_converter",
    "insert",
]

RecognitionMethod: TypeAlias = Literal["ner", "grounding"]
PredictionMethod: TypeAlias = Literal["ner", "grounding", "embedding"]

DEFAULT_RESOLVER_BASE = "https://bioregistry.io"


def ensure_converter(
    converter: curies.Converter | None = None, *, preferred: bool = False
) -> curies.Converter:
    """Get a converter."""
    if converter is not None:
        return converter
    try:
        import bioregistry
    except ImportError as e:
        raise ImportError(
            "No converter was given, and could not import the Bioregistry. "
            "Install with:\n\n\t$ pip install bioregistry"
        ) from e

    if preferred:
        return _get_preferred()
    else:
        # TODO should this also return a converter with
        #  the RDF URI prefix prioritized?
        return bioregistry.get_default_converter()


@lru_cache(1)
def _get_preferred() -> curies.Converter:
    import bioregistry

    return bioregistry.get_converter(
        uri_prefix_priority=["rdf", "default"],
        prefix_priority=["preferred", "default"],
    )


PREDICTIONS_NAME = "predictions.sssom.tsv"
POSITIVES_NAME = "positive.sssom.tsv"
NEGATIVES_NAME = "negative.sssom.tsv"
UNSURE_NAME = "unsure.sssom.tsv"


def insert(
    path: Path,
    *,
    converter: curies.Converter | None = None,
    include_mappings: Iterable[SemanticMapping],
    exclude_columns: Collection[str] | None = None,
    sort: bool = True,
) -> None:
    """Append eagerly with linting at the same time."""
    import sssom_pydantic

    mappings, converter_processed, metadata = sssom_pydantic.read(
        path, converter=converter, return_errors=False
    )

    # make sure that the converter knows about the sssom.record prefix
    converter_processed.add_prefix(MAPPING_HASH_CURIE_PREFIX, MAPPING_HASH_URI_PREFIX, merge=True)

    for mapping in include_mappings:
        mappings.append(mapping.standardize(converter_processed))

    sssom_pydantic.write(
        mappings,
        path,
        converter=converter_processed,
        metadata=metadata,
        sort=sort,
        drop_duplicates=True,
        exclude_columns=exclude_columns,
        exclude_prefixes={MAPPING_HASH_CURIE_PREFIX},
    )


#: The name of the lexical mapping tool
TOOL_NAME = "sssom-curator"
TOOL_REFERENCE = NamedReference(prefix="wikidata", identifier="Q138902949", name="SSSOM Curator")
