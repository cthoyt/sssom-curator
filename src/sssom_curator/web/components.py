"""Components."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypeAlias

import curies
import sssom_pydantic
from curies import Reference
from curies.vocabulary import broad_match, manual_mapping_curation, narrow_match
from pydantic import BaseModel, Field
from sssom_pydantic import SemanticMapping

from .utils import MARK_TO_FILE, CorrectIncorrectOrUnsure, Mark
from ..constants import insert
from ..repository import Repository

__all__ = [
    "Controller",
    "PaginationElement",
    "State",
    "get_pagination_elements",
]

#: The default limit
DEFAULT_LIMIT = 10


class Query(BaseModel):
    """A query over SSSOM."""

    query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source or target fields.",
    )
    source_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the source fields.",
    )
    source_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "source prefix field",
    )
    target_query: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a substring "
        "in one of the target fields.",
    )
    target_prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing in the "
        "target prefix field",
    )
    # TODO rename, since this is about mapping tool
    provenance: str | None = Field(
        None, description="If given, filters to provenance values matching this"
    )
    prefix: str | None = Field(
        None,
        description="If given, show only mappings that have it appearing as a "
        "substring in one of the prefixes.",
    )
    same_text: bool | None = Field(
        None, description="If true, filter to predictions with the same label"
    )


Sort: TypeAlias = Literal["asc", "desc", "subject", "object"]
MappingIt: TypeAlias = Iterator[tuple[int, SemanticMapping]]


class Config(BaseModel):
    """Configuration for a query over SSSOM."""

    limit: int | None = Field(
        DEFAULT_LIMIT, description="If given, only iterate this number of predictions."
    )
    offset: int | None = Field(None, description="If given, offset the iteration by this number")
    sort: Sort | None = Field(
        None,
        description="If `desc`, sorts in descending confidence order. If `asc`, sorts in "
        "increasing confidence order. Otherwise, do not sort.",
    )
    show_relations: bool = True
    show_lines: bool = False


class State(Query, Config):
    """Contains the state for queries to the curation app."""


class Controller:
    """A module for interacting with the predictions and mappings."""

    converter: curies.Converter
    repository: Repository
    target_references: set[Reference] | None

    def __init__(
        self,
        *,
        target_references: Iterable[Reference] | None = None,
        repository: Repository,
        user: Reference,
        converter: curies.Converter,
    ) -> None:
        """Instantiate the web controller.

        :param target_references: References that are the
            target of curation. If this is given, pre-filters will be made before on
            predictions to only show ones where either the source or target appears in
            this set
        """
        self.repository = repository
        self._predictions, _, self._predictions_metadata = sssom_pydantic.read(
            self.repository.predictions_path
        )

        self._marked: dict[int, Mark] = {}
        self.total_curated = 0
        self.target_references = set(target_references) if target_references is not None else None
        self.converter = converter

        self._current_author = user

    def _get_current_author(self) -> Reference:
        return self._current_author

    def get_prefix_counter(self, state: State) -> Counter[tuple[str, str]]:
        """Get a subject/object prefix counter."""
        return Counter(
            (mapping.subject.prefix, mapping.object.prefix)
            for _, mapping in self.iterate_predictions(state)
        )

    def iterate_predictions(self, state: State) -> MappingIt:
        """Iterate over pairs of positions and predicted semantic mappings."""
        mappings = self._help_it_predictions(state)
        if state.sort is not None:
            mappings = self._sort(mappings, state.sort)
        if state.offset is not None:
            try:
                for _ in range(state.offset):
                    next(mappings)
            except StopIteration:
                # if next() fails, then there are no remaining entries.
                # do not pass go, do not collect 200 euro $
                return
        if state.limit is None:
            yield from mappings
        else:
            for line_prediction, _ in zip(mappings, range(state.limit), strict=False):
                yield line_prediction

    @staticmethod
    def _sort(mappings: MappingIt, sort: Sort) -> MappingIt:
        if sort == "desc":
            mappings = iter(sorted(mappings, key=_get_confidence, reverse=True))
        elif sort == "asc":
            mappings = iter(sorted(mappings, key=_get_confidence, reverse=False))
        elif sort == "subject":
            mappings = iter(sorted(mappings, key=lambda l_p: l_p[1].subject.curie))
        elif sort == "object":
            mappings = iter(sorted(mappings, key=lambda l_p: l_p[1].object.curie))
        else:
            raise ValueError(f"unknown sort type: {sort}")
        return mappings

    def count_predictions(self, state: State) -> int:
        """Count the number of predictions to check for the given filters."""
        it = self._help_it_predictions(state)
        return sum(1 for _ in it)

    def _help_it_predictions(self, state: State) -> MappingIt:
        mappings: MappingIt = enumerate(self._predictions)
        if self.target_references is not None:
            mappings = (
                (line, mapping)
                for (line, mapping) in mappings
                if mapping.subject in self.target_references
                or mapping.object in self.target_references
            )
        mappings = self._filter_by_query(state, mappings)
        # filter to not include ones that have already been curated, but not yet persisted
        rv = ((line, mapping) for line, mapping in mappings if line not in self._marked)
        return rv

    def _filter_by_query(self, state: Query, mappings: MappingIt) -> MappingIt:
        if state.query is not None:
            mappings = self._help_filter(
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
        if state.source_prefix is not None:
            mappings = self._help_filter(
                state.source_prefix, mappings, lambda mapping: [mapping.subject.curie]
            )
        if state.source_query is not None:
            mappings = self._help_filter(
                state.source_query,
                mappings,
                lambda mapping: [mapping.subject.curie, mapping.subject_name],
            )
        if state.target_query is not None:
            mappings = self._help_filter(
                state.target_query,
                mappings,
                lambda mapping: [mapping.object.curie, mapping.object_name],
            )
        if state.target_prefix is not None:
            mappings = self._help_filter(
                state.target_prefix, mappings, lambda mapping: [mapping.object.curie]
            )
        if state.prefix is not None:
            mappings = self._help_filter(
                state.prefix,
                mappings,
                lambda mapping: [mapping.subject.curie, mapping.object.curie],
            )
        if state.provenance is not None:
            mappings = self._help_filter(
                state.provenance,
                mappings,
                lambda mapping: [mapping.mapping_tool_name],
            )
        if state.same_text:
            mappings = (
                (line, mapping)
                for line, mapping in mappings
                if mapping.subject_name
                and mapping.object_name
                and mapping.subject_name.casefold() == mapping.object_name.casefold()
                and mapping.predicate.curie == "skos:exactMatch"
            )
        yield from mappings

    @staticmethod
    def _help_filter(
        query: str, mappings: MappingIt, get_strings: Callable[[SemanticMapping], list[str | None]]
    ) -> MappingIt:
        query = query.casefold()
        for line, mapping in mappings:
            if any(query in string.casefold() for string in get_strings(mapping) if string):
                yield line, mapping

    def mark(self, line: int, value: Mark) -> None:
        """Mark the given mapping as correct.

        :param line: Position of the prediction
        :param value: Value to mark the prediction with

        :raises ValueError: if an invalid value is used
        """
        if line > len(self._predictions):
            raise IndexError(
                f"given line {line} is larger than the number of "
                f"predictions {len(self._predictions):,}"
            )
        if line not in self._marked:
            self.total_curated += 1
        self._marked[line] = value
        self._persist()

    def _insert(self, mappings: Iterable[SemanticMapping], path: Path) -> None:
        insert(path=path, converter=self.converter, include_mappings=mappings)

    def _persist(self) -> None:
        """Save the current markings to the source files."""
        if not self._marked:
            # no need to persist if there are no marks
            return None

        entries: defaultdict[CorrectIncorrectOrUnsure, list[SemanticMapping]] = defaultdict(list)

        for line, mark in sorted(self._marked.items(), reverse=True):
            if line > len(self._predictions):
                raise IndexError(
                    f"you tried popping the {line} element from the predictions list, "
                    f"which only has {len(self._predictions):,} elements"
                )

            mapping = self._predictions.pop(line)

            update: dict[str, Any] = {
                "authors": [self._get_current_author()],
                "justification": manual_mapping_curation,
                # throw the following fields away, since it's been manually curated now
                "confidence": None,
                "mapping_tool": None,
            }

            if mark == "broad":
                # note these go backwards because of the way they are read
                update["predicate"] = narrow_match
            elif mark == "narrow":
                # note these go backwards because of the way they are read
                update["predicate"] = broad_match
            elif mark == "incorrect":
                update["predicate_modifier"] = "Not"

            # replace some values using model_copy since the model is frozen
            new_mapping = mapping.model_copy(update=update)

            entries[MARK_TO_FILE[mark]].append(new_mapping)

        # no need to standardize since we assume everything was correct on load.
        # only write files that have some values to go in them!
        if entries["correct"]:
            self._insert(entries["correct"], path=self.repository.positives_path)
        if entries["incorrect"]:
            self._insert(entries["incorrect"], path=self.repository.negatives_path)
        if entries["unsure"]:
            self._insert(entries["unsure"], path=self.repository.unsure_path)

        sssom_pydantic.write(
            self._predictions,
            self.repository.predictions_path,
            metadata=self._predictions_metadata,
            converter=self.converter,
            drop_duplicates=True,
            sort=True,
        )
        self._marked.clear()

        return None


def _get_confidence(t: tuple[int, SemanticMapping]) -> float:
    return t[1].confidence or 0.0


class PaginationElement(NamedTuple):
    """Represents pagination element."""

    offset: int | None
    icon: str
    text: str
    position: Literal["before", "after"]


def get_pagination_elements(state: State, remaining_rows: int) -> list[PaginationElement]:
    """Get pagination elements."""
    rv = []

    def _append(
        offset: int | None, icon: str, text: str, position: Literal["before", "after"]
    ) -> None:
        rv.append(PaginationElement(offset, icon, text, position))

    offset = state.offset or 0
    limit = state.limit or DEFAULT_LIMIT
    if 0 <= offset - limit:
        _append(None, "angle-double-left", "First", "after")
        _append(offset - limit, "angle-left", f"Previous {limit:,}", "after")
    if offset < remaining_rows - limit:
        _append(offset + limit, "angle-right", f"Next {limit:,}", "before")
        _append(
            remaining_rows - limit,
            "angle-double-right",
            f"Last ({remaining_rows:,})",
            "before",
        )
    return rv
