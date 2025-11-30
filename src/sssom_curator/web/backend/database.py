"""A database backend."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

import curies
import sssom_pydantic
from curies import Reference
from sssom_pydantic import MappingSet, SemanticMapping
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
from sssom_curator.web.backend.base import Controller, State

__all__ = [
    "DatabaseController",
]


class DatabaseController(Controller):
    """A controller that interacts with a database."""

    def __init__(self, connection: str, user: Reference) -> None:
        """Initialize the database controller."""
        self.db = SemanticMappingDatabase.from_connection(
            connection=connection, semantic_mapping_hash=default_hash
        )
        self.current_author = user
        self.total_curated = 0

    def save(self, repository: Repository) -> None:
        """Save mappings to disk."""
        converter = repository.get_converter()

        def _write_stub(m: list[SemanticMapping], p: Path) -> None:
            if repository.purl_base is None:
                raise NotImplementedError
            mapping_set = MappingSet(id=repository.purl_base + p.name)
            sssom_pydantic.write(m, p, converter=converter, metadata=mapping_set)

        for clause, path in [
            (POSITIVE_MAPPING_CLAUSE, repository.positives_path),
            (NEGATIVE_MAPPING_CLAUSE, repository.negatives_path),
        ]:
            mappings = [
                m.to_semantic_mapping() for m in self.db.get_mappings(where_clauses=[clause])
            ]
            _write_stub(mappings, path)

        unsure: list[SemanticMapping] = []
        predicted: list[SemanticMapping] = []
        for mapping in self.db.get_mappings([UNCURATED_CLAUSE]):
            if mapping.curation_rule_text and UNSURE in mapping.curation_rule_text:
                unsure.append(mapping.to_semantic_mapping())
            else:
                predicted.append(mapping.to_semantic_mapping())

        _write_stub(unsure, repository.unsure_path)
        _write_stub(predicted, repository.predictions_path)

    @classmethod
    def memory(
        cls,
        *,
        connection_uri: str | None = None,
        repository: Repository,
        user: Reference,
        converter: curies.Converter,
        target_references: Iterable[Reference] | None = None,
    ) -> Self:
        """Create an in-memory database."""
        if target_references is not None:
            raise NotImplementedError

        if connection_uri is not None:
            controller = cls(connection_uri, user=user)
        else:
            path = Path.home().joinpath("Desktop", "biomappings.sqlite")
            # sqlite:///:memory:
            connection_uri = f"sqlite:///{path}"
            if not path.is_file():
                controller = cls(connection_uri, user=user)
                controller.db.add_mappings(
                    mapping
                    for path in tqdm(repository.paths, desc="loading database")
                    for mapping in tqdm(
                        sssom_pydantic.read(path)[0], leave=False, desc=path.name, unit_scale=True
                    )
                )
                controller.db.add_mappings(
                    mapping.model_copy(
                        update={
                            "curation_rule_text": [UNSURE],
                            "record": default_hash(mapping),
                        }
                    )
                    for mapping in tqdm(
                        repository.read_unsure_mappings(),
                        leave=False,
                        desc="unsure",
                        unit_scale=True,
                    )
                )
            else:
                controller = cls(connection_uri, user=user)

        return controller

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

    def mark(self, reference: Reference, mark: Mark) -> None:
        """Mark the given mapping as correct."""
        self.total_curated += 1
        self.db.curate(reference, mark=mark, authors=self.current_author)
