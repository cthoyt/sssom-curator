"""Tools for filtering mappings."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from pydantic import BaseModel, Field
from sssom_pydantic import SemanticMapping

__all__ = [
    "Query",
    "filter_mappings",
]


class Query(BaseModel):
    """A query over SSSOM."""

    query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source or target fields.",
    )
    subject_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source fields.",
    )
    subject_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "source prefix field",
    )
    object_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the target fields.",
    )
    object_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "target prefix field",
    )
    mapping_tool: str | None = Field(
        None, description="If given, filters to mapping tool names matching this"
    )
    prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a "
        "substring in one of the prefixes.",
    )
    same_text: bool | None = Field(
        None, description="If true, filter to predictions with the same label"
    )


def filter_mappings(mappings: Iterator[SemanticMapping], state: Query) -> Iterator[SemanticMapping]:
    """Filter mappings based on a query."""
    if state.query is not None:
        mappings = _help_filter(
            state.query,
            mappings,
            lambda mapping: [
                mapping.subject.curie,
                mapping.subject_name,
                mapping.object.curie,
                mapping.object_name,
                mapping.mapping_tool_name,
            ],
        )
    if state.subject_prefix is not None:
        mappings = _help_filter(
            state.subject_prefix, mappings, lambda mapping: [mapping.subject.curie]
        )
    if state.subject_query is not None:
        mappings = _help_filter(
            state.subject_query,
            mappings,
            lambda mapping: [mapping.subject.curie, mapping.subject_name],
        )
    if state.object_query is not None:
        mappings = _help_filter(
            state.object_query,
            mappings,
            lambda mapping: [mapping.object.curie, mapping.object_name],
        )
    if state.object_prefix is not None:
        mappings = _help_filter(
            state.object_prefix, mappings, lambda mapping: [mapping.object.curie]
        )
    if state.prefix is not None:
        mappings = _help_filter(
            state.prefix,
            mappings,
            lambda mapping: [mapping.subject.curie, mapping.object.curie],
        )
    if state.mapping_tool is not None:
        mappings = _help_filter(
            state.mapping_tool,
            mappings,
            lambda mapping: [mapping.mapping_tool_name],
        )
    if state.same_text:
        mappings = (
            mapping
            for mapping in mappings
            if mapping.subject_name
            and mapping.object_name
            and mapping.subject_name.casefold() == mapping.object_name.casefold()
            and mapping.predicate.curie == "skos:exactMatch"
        )
    yield from mappings


def _help_filter(
    query: str,
    mappings: Iterator[SemanticMapping],
    get_strings: Callable[[SemanticMapping], list[str | None]],
) -> Iterator[SemanticMapping]:
    query = query.casefold()
    for mapping in mappings:
        if any(query in string.casefold() for string in get_strings(mapping) if string):
            yield mapping
