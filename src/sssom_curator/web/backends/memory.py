"""A dictionary-based backend for the SSSOM Curator web application."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING

import curies
import sssom_pydantic
from curies import Reference
from sssom_pydantic import SemanticMapping
from sssom_pydantic.api import SemanticMappingHash
from sssom_pydantic.process import MARK_TO_CALL, Call, Mark, curate
from sssom_pydantic.query import Query, filter_mappings

from .base import Controller
from ..utils import Sort, State
from ...constants import insert

if TYPE_CHECKING:
    from ...repository import Repository

__all__ = [
    "DictController",
]


class DictController(Controller):
    """A controller that interacts with the file system."""

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
        super().__init__(
            repository=repository,
            semantic_mapping_hash=mapping_hash,
            converter=converter,
            target_references=target_references,
        )
        predicted_mappings, _, self._predictions_metadata = sssom_pydantic.read(
            self.repository.predictions_path
        )
        self._predictions = {}
        for mapping in predicted_mappings:  # this is fast
            if mapping.record:
                raise ValueError("SSSOM Curator doesn't yet support custom record_ids")
            reference = self.mapping_hash(mapping)
            self._predictions[reference] = mapping.model_copy(update={"record": reference})

        self.curations: defaultdict[Call, list[SemanticMapping]] = defaultdict(list)

    def get_prefix_counter(self, state: State | None = None) -> Counter[tuple[str, str]]:
        """Get a subject/object prefix counter."""
        return Counter(
            (mapping.subject.prefix, mapping.object.prefix)
            for mapping in self.iterate_predictions(state)
        )

    def get_predictions(self, state: State | None = None) -> Sequence[SemanticMapping]:
        """Get predicted semantic mappings."""
        return list(self.iterate_predictions(state))

    def iterate_predictions(self, state: State | None = None) -> Iterable[SemanticMapping]:
        """Iterate over pairs of positions and predicted semantic mappings."""
        if state is None:
            yield from self._help_it_predictions()
            return

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

    def count_predictions(self, query: Query | None = None) -> int:
        """Count the number of predictions to check for the given filters."""
        it = self._help_it_predictions(query)
        return sum(1 for _ in it)

    def _help_it_predictions(self, query: Query | None = None) -> Iterable[SemanticMapping]:
        mappings = iter(self._predictions.values())
        if self.target_references is not None:
            mappings = (
                mapping
                for mapping in mappings
                if mapping.subject in self.target_references
                or mapping.object in self.target_references
            )
        if query is not None:
            yield from filter_mappings(mappings, query)
        else:
            yield from mappings

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

    def count_unpersisted(self) -> int:
        """Count the number of unpersisted curations."""
        return sum(len(m) for m in self.curations.values())

    def persist(self) -> None:
        """Persist the curated mappings."""
        total = self.count_unpersisted()
        for call, mappings in self.curations.items():
            if mappings:
                insert(
                    path=self.repository.call_to_path[call],
                    converter=self.converter,
                    include_mappings=mappings,
                    exclude_columns=["record_id", "predicate_label"],
                )
        self.curations.clear()

        if total > 0:
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
