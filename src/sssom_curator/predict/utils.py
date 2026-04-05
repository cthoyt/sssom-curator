"""Utilities for lexical prediction workflows."""

from __future__ import annotations

import curies
from bioregistry import NormalizedReference
from curies import NamedReference
from curies.vocabulary import exact_match
from sssom_pydantic import MappingTool

from ..version import get_version

__all__ = [
    "TOOL_NAME",
    "resolve_mapping_tool",
    "resolve_predicate",
]

#: The name of the lexical mapping tool
TOOL_NAME = "sssom-curator"
TOOL_REFERENCE = NamedReference(prefix="wikidata", identifier="Q138902949", name="SSSOM Curator")


def resolve_mapping_tool(mapping_tool: str | MappingTool | None) -> MappingTool:
    """Resolve the mapping tool."""
    if mapping_tool is None:
        return MappingTool(name=TOOL_NAME, reference=TOOL_REFERENCE, version=get_version())
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
