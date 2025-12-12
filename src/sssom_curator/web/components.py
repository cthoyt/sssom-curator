"""Components."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from typing import Literal, NamedTuple, TypeAlias

import curies
import sssom_pydantic
from curies import Reference
from pydantic import BaseModel, Field
from sssom_pydantic import SemanticMapping
from sssom_pydantic.api import SemanticMappingHash
from sssom_pydantic.process import MARK_TO_CALL, Call, Mark, curate
from sssom_pydantic.query import Query, filter_mappings

from ..constants import default_hash, insert
from ..repository import Repository

__all__ = [
    "Controller",
    "PaginationElement",
    "State",
    "get_pagination_elements",
]

#: The default limit
DEFAULT_LIMIT: int = 10

#: The default offset
DEFAULT_OFFSET: int = 0

Sort: TypeAlias = Literal["asc", "desc", "subject", "object"]


class Config(BaseModel):
    """Configuration for a query over SSSOM."""

    limit: int | None = Field(
        DEFAULT_LIMIT, description="If given, only iterate this number of predictions."
    )
    offset: int = Field(DEFAULT_OFFSET, description="If given, offset the iteration by this number")
    sort: Sort | None = Field(
        None,
        description="If `desc`, sorts in descending confidence order. If `asc`, sorts in "
        "increasing confidence order. Otherwise, do not sort.",
    )
    show_relations: bool = True


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
        converter: curies.Converter,
        mapping_hash: SemanticMappingHash | None = None,
    ) -> None:
        """Instantiate the web controller.

        :param target_references: References that are the
            target of curation. If this is given, pre-filters will be made before on
            predictions to only show ones where either the source or target appears in
            this set
        """
        self.repository = repository
        self.mapping_hash = mapping_hash if mapping_hash is not None else default_hash
        predicted_mappings, _, self._predictions_metadata = sssom_pydantic.read(
            self.repository.predictions_path
        )
        self._predictions = {}
        for mapping in predicted_mappings:  # this is fast
            if mapping.record:
                raise ValueError("SSSOM Curator doesn't yet support custom record_ids")
            reference = self.mapping_hash(mapping)
            self._predictions[reference] = mapping.model_copy(update={"record": reference})

        self.total_curated = 0
        self.target_references = set(target_references) if target_references is not None else None
        self.converter = converter
        self.curations: defaultdict[Call, list[SemanticMapping]] = defaultdict(list)

    def get_prefix_counter(self, state: State) -> Counter[tuple[str, str]]:
        """Get a subject/object prefix counter."""
        return Counter(
            (mapping.subject.prefix, mapping.object.prefix)
            for mapping in self.iterate_predictions(state)
        )

    def get_predictions(self, state: State) -> Sequence[SemanticMapping]:
        """Get predicted semantic mappings."""
        return list(self.iterate_predictions(state))

    def iterate_predictions(self, state: State) -> Iterable[SemanticMapping]:
        """Iterate over pairs of positions and predicted semantic mappings."""
        mappings = iter(self._help_it_predictions(state))
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
    def _sort(mappings: Iterator[SemanticMapping], sort: Sort) -> Iterator[SemanticMapping]:
        if sort == "desc":
            mappings = iter(sorted(mappings, key=_get_confidence, reverse=True))
        elif sort == "asc":
            mappings = iter(sorted(mappings, key=_get_confidence, reverse=False))
        elif sort == "subject":
            mappings = iter(sorted(mappings, key=lambda m: m.subject.curie))
        elif sort == "object":
            mappings = iter(sorted(mappings, key=lambda m: m.object.curie))
        else:
            raise ValueError(f"unknown sort type: {sort}")
        return mappings

    def count_predictions(self, state: Query) -> int:
        """Count the number of predictions to check for the given filters."""
        it = self._help_it_predictions(state)
        return sum(1 for _ in it)

    def _help_it_predictions(self, state: Query) -> Iterable[SemanticMapping]:
        mappings = iter(self._predictions.values())
        if self.target_references is not None:
            mappings = (
                mapping
                for mapping in mappings
                if mapping.subject in self.target_references
                or mapping.object in self.target_references
            )
        yield from filter_mappings(mappings, state)

    def mark(
        self,
        reference: Reference | SemanticMapping,
        mark: Mark,
        authors: Reference | list[Reference],
    ) -> None:
        """Mark the given mapping as correct.

        :param reference: The reference for the mapping, corresponding to the ``record`` field
        :param mark: Value to mark the prediction with
        :param authors: Author or author of the mark

        :raises KeyError:
            if there's no predicted mapping whose record corresponds to the given reference
        """
        if isinstance(reference, SemanticMapping):
            if not reference.record:
                raise RuntimeError("all predicted mappings should have pre-calculated records")
            reference = reference.record

        if reference not in self._predictions:
            raise KeyError(f"the mapping with hash {reference.curie} is not present")

        self.total_curated += 1

        mapping = self._predictions.pop(reference)

        # TODO start using dates!
        new_mapping = curate(mapping, authors=authors, mark=mark, add_date=False)
        self.curations[MARK_TO_CALL[mark]].append(new_mapping)
        self.persist()

    def persist(self) -> None:
        """Persist the curated mappings."""
        for call, mappings in self.curations.items():
            if mappings:
                insert(
                    path=self.repository.call_to_path[call],
                    converter=self.converter,
                    include_mappings=mappings,
                    exclude_columns=["record_id", "predicate_label"],
                )
        self.curations.clear()

        sssom_pydantic.write(
            self._predictions.values(),
            self.repository.predictions_path,
            metadata=self._predictions_metadata,
            converter=self.converter,
            drop_duplicates=True,
            sort=True,
            exclude_columns=["record_id", "predicate_label"],
            # TODO is there a way of pre-calculating some things to make this faster?
            #  e.g., say "no condensation"
        )


def _get_confidence(t: SemanticMapping) -> float:
    return t.confidence or 0.0


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

    offset = state.offset or DEFAULT_OFFSET
    limit = state.limit or DEFAULT_LIMIT
    if 0 <= offset - limit:
        _append(None, "skip-start-circle", "First", "after")
        _append(offset - limit, "skip-backward-circle", f"Previous {limit:,}", "after")
    if offset < remaining_rows - limit:
        _append(offset + limit, "skip-forward-circle", f"Next {limit:,}", "before")
        _append(
            remaining_rows - limit,
            "skip-end-circle",
            f"Last ({remaining_rows:,})",
            "before",
        )
    return rv
