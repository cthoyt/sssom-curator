"""Constants for sssom-curator."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, TypeAlias

import curies

__all__ = [
    "DEFAULT_RESOLVER_BASE",
    "PredictionMethod",
    "RecognitionMethod",
    "ensure_converter",
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
        return bioregistry.get_default_converter()


@lru_cache(1)
def _get_preferred() -> curies.Converter:
    import bioregistry

    return bioregistry.get_converter(
        uri_prefix_priority=["rdf", "default"],
        prefix_priority=["preferred", "default"],
    )
