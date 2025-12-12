"""A database backend."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

import curies
import sssom_pydantic
from curies import Reference
from sssom_pydantic import MappingSet, SemanticMapping
from sssom_pydantic.api import SemanticMappingHash
from sssom_pydantic.database import (
    NEGATIVE_MAPPING_CLAUSE,
    POSITIVE_MAPPING_CLAUSE,
    UNCURATED_CLAUSE,
    SemanticMappingDatabase,
    clauses_from_query,
)
from sssom_pydantic.process import UNSURE, Mark
from sssom_pydantic.query import Query
from tqdm import tqdm
from typing_extensions import Self

from sssom_curator import Repository
from sssom_curator.constants import default_hash

from .components import AbstractController, State

__all__ = [
    "DatabaseController",
]


class DatabaseController(AbstractController):
    """A controller that interacts with a database."""

    def __init__(
        self,
        *,
        repository: Repository,
        connection: str | None = None,
        semantic_mapping_hash: SemanticMappingHash | None = None,
        converter: curies.Converter,
        target_references: Iterable[Reference] | None = None,
    ) -> None:
        """Initialize the database controller."""
        super().__init__(
            repository=repository,
            semantic_mapping_hash=semantic_mapping_hash,
            converter=converter,
            target_references=target_references,
        )
        if self.target_references:
            raise NotImplementedError
        self.db = SemanticMappingDatabase.from_connection(
            connection=connection or "sqlite:///:memory:", semantic_mapping_hash=self.mapping_hash
        )

    def count_predictions(self, state: Query) -> int:
        """Count predictions (i.e., anything that's not manually curated)."""
        return self.db.count_mappings(where_clauses=[UNCURATED_CLAUSE, *clauses_from_query(state)])

    def get_predictions(self, state: State) -> Sequence[SemanticMapping]:
        """Iterate over pairs of positions and predicted semantic mappings."""
        models = self.db.get_mappings(
            where_clauses=[UNCURATED_CLAUSE, *clauses_from_query(state)],
            limit=state.limit,
            offset=state.offset,
        )
        return [model.to_semantic_mapping() for model in models]

    def get_prefix_counter(self, state: State) -> Counter[tuple[str, str]]:
        """Count the number of predictions to check for the given filters."""
        return Counter((m.subject.prefix, m.object.prefix) for m in self.get_predictions(state))

    def mark(self, reference: Reference, mark: Mark, authors: Reference | list[Reference]) -> None:
        """Mark the given mapping as correct."""
        self.total_curated += 1
        self.db.curate(reference, mark=mark, authors=authors)

    def persist(self) -> None:
        """Save mappings to disk."""
        save(self.db, self.repository)


def save(db: SemanticMappingDatabase, repository: Repository) -> None:
    """Save mappings to disk."""
    converter = repository.get_converter()

    def _write_stub(m: list[SemanticMapping], p: Path) -> None:
        if repository.purl_base is None:
            raise NotImplementedError
        mapping_set = MappingSet(id=repository.purl_base.rstrip("/") + "/" + p.name)
        sssom_pydantic.write(
            m, p, converter=converter, metadata=mapping_set, exclude_columns=["record_id"]
        )

    for clause, path in [
        (POSITIVE_MAPPING_CLAUSE, repository.positives_path),
        (NEGATIVE_MAPPING_CLAUSE, repository.negatives_path),
    ]:
        mappings = [m.to_semantic_mapping() for m in db.get_mappings(where_clauses=[clause])]
        _write_stub(mappings, path)

    unsure: list[SemanticMapping] = []
    predicted: list[SemanticMapping] = []
    for mapping in db.get_mappings([UNCURATED_CLAUSE]):
        if mapping.curation_rule_text and UNSURE in mapping.curation_rule_text:
            unsure.append(mapping.to_semantic_mapping())
        else:
            predicted.append(mapping.to_semantic_mapping())

    _write_stub(unsure, repository.unsure_path)
    _write_stub(predicted, repository.predictions_path)
