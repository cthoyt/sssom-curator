"""Constants for sssom-curator."""

from __future__ import annotations

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


def ensure_converter(converter: curies.Converter | None = None) -> curies.Converter:
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

    return bioregistry.get_converter()
