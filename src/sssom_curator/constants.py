"""Constants for sssom-curator."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, TypeAlias

if TYPE_CHECKING:
    import curies
    from sssom_pydantic import MappingSet

__all__ = [
    "DEFAULT_RESOLVER_BASE",
    "InitializationStrategy",
    "PredictionMethod",
    "RecognitionMethod",
    "ensure_converter",
]


RecognitionMethod: TypeAlias = Literal["ner", "grounding"]
PredictionMethod: TypeAlias = Literal["ner", "grounding", "embedding"]
InitializationStrategy: TypeAlias = Literal["folder", "package"]

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


def sssom_mapping_set_model_dump(mapping_set: MappingSet) -> dict[str, Any]:
    """Prepare a mapping set for writing SSSOM."""
    metadata = mapping_set.model_dump(exclude_none=True, exclude_unset=True)
    # fix dumping
    metadata["creator_id"] = [
        creator["prefix"] + ":" + creator["identifier"] for creator in metadata["creator_id"]
    ]
    return metadata
