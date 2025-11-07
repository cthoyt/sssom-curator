"""Utilities for lexical prediction workflows."""

from __future__ import annotations

import curies
from bioregistry import NormalizedReference
from curies.vocabulary import exact_match
from sssom_pydantic import MappingTool

__all__ = [
    "TOOL_NAME",
    "resolve_mapping_tool",
    "resolve_predicate",
]

#: The name of the lexical mapping tool
TOOL_NAME = "sssom-curator"


def resolve_mapping_tool(mapping_tool: str | MappingTool | None) -> MappingTool:
    """Resolve the mapping tool."""
    if mapping_tool is None:
        return MappingTool(name=TOOL_NAME, version=None)
    if isinstance(mapping_tool, str):
        return MappingTool(name=mapping_tool, version=None)
    return mapping_tool


def resolve_predicate(predicate: str | curies.Reference | None = None) -> NormalizedReference:
    """Ensure a predicate is available."""
    if predicate is None:
        predicate = exact_match
    elif isinstance(predicate, str):
        predicate = NormalizedReference.from_curie(predicate)

    # throw away name so we don't make a label column
    predicate = NormalizedReference(prefix=predicate.prefix, identifier=predicate.identifier)
    return predicate
