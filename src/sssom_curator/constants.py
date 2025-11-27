"""Constants for sssom-curator."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias

from curies import Reference

if TYPE_CHECKING:
    import curies
    from sssom_pydantic import SemanticMapping

__all__ = [
    "DEFAULT_RESOLVER_BASE",
    "NEGATIVES_NAME",
    "POSITIVES_NAME",
    "PREDICTIONS_NAME",
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

STUB_SSSOM_COLUMNS = [
    "subject_id",
    "subject_label",
    "predicate_id",
    "object_id",
    "object_label",
    "mapping_justification",
    "author_id",
    "mapping_tool",
    "predicate_modifier",
]

DEFAULT_HASH_PREFIX = "sssom-curator-hash-v1"


def default_hash(m: SemanticMapping) -> Reference:
    """Hash a mapping into a reference."""
    v = hash(m) & ((1 << 64) - 1)
    return Reference(prefix=DEFAULT_HASH_PREFIX, identifier=str(v))


def insert(
    path: Path,
    *,
    converter: curies.Converter | None = None,
    include_mappings: Iterable[SemanticMapping] | None = None,
    exclude_columns: Collection[str] | None = None,
) -> None:
    """Append eagerly with linting at the same time."""
    import sssom_pydantic

    mappings, converter_processed, metadata = sssom_pydantic.read(path, converter=converter)

    if include_mappings is not None:
        prefixes: set[str] = set()
        for mapping in include_mappings:
            prefixes.update(mapping.get_prefixes())
            mappings.append(mapping)

        if DEFAULT_HASH_PREFIX in prefixes:
            prefixes.remove(DEFAULT_HASH_PREFIX)
        for prefix in prefixes:
            if not converter_processed.standardize_prefix(prefix):
                raise NotImplementedError(f"amending prefixes not yet implemented: {prefix}")

    sssom_pydantic.write(
        mappings,
        path,
        converter=converter_processed,
        metadata=metadata,
        sort=True,
        drop_duplicates=True,
        exclude_columns=exclude_columns,
    )
