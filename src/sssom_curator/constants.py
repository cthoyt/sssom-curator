"""Constants for sssom-curator."""

from __future__ import annotations

from collections.abc import Collection
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

    prefix_map = {}
    for resource in bioregistry.resources():
        prefix = resource.get_preferred_prefix() or resource.prefix
        uri_prefix = resource.get_rdf_uri_prefix() or resource.get_uri_prefix()
        if uri_prefix:
            prefix_map[prefix] = uri_prefix

    return curies.Converter.from_prefix_map(prefix_map)


def get_prefix_map(prefixes: Collection[str]) -> dict[str, str]:
    """Get a CURIE map containing only the relevant prefixes."""
    import bioregistry

    prefix_map = {}
    for prefix in sorted(prefixes, key=str.casefold):
        resource = bioregistry.get_resource(prefix)
        if resource is None:
            raise KeyError
        uri_prefix = resource.get_rdf_uri_prefix() or resource.get_uri_prefix()
        if uri_prefix is None:
            raise ValueError(f"could not look up URI prefix for {prefix}")
        preferred_prefix = resource.get_preferred_prefix() or prefix
        prefix_map[preferred_prefix] = uri_prefix
    return prefix_map
