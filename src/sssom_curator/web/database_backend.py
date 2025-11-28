"""A database backend."""

from __future__ import annotations

import contextlib
from collections import Counter
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path

import curies
import sqlmodel
import sssom_pydantic
from curies import Reference
from curies.vocabulary import manual_mapping_curation
from sssom_pydantic import SemanticMapping
from sssom_pydantic.database import SemanticMappingModel
from tqdm import tqdm
from typing_extensions import Self

from sssom_curator import Repository
from sssom_curator.constants import default_hash
from sssom_curator.web.components import Controller, State, curate_mapping
from sssom_curator.web.query import Query
from sssom_curator.web.utils import Mark

__all__ = [
    "DatabaseController",
]


class DatabaseController(Controller):
    """A controller that interacts with a database."""

    def __init__(self, connection: str, user: Reference) -> None:
        """Initialize the database controller."""
        from sqlmodel import Session, create_engine

        self.engine = create_engine(connection)
        self.session_cls = Session
        self.current_author = user

        self._predicted_clause = SemanticMappingModel.justification != manual_mapping_curation

    @classmethod
    def memory(
        cls,
        *,
        connection_uri: str | None = None,
        repository: Repository,
        user: Reference,
        converter: curies.Converter,
        target_references: Iterable[Reference] | None = None,
        load: bool = False,
    ) -> Self:
        """Create an in-memory database."""
        if target_references is not None:
            raise NotImplementedError
        from sqlmodel import SQLModel

        if connection_uri is None:
            path = Path.home().joinpath("Desktop", "biomappings.sqlite")
            # sqlite:///:memory:
            connection_uri = f"sqlite:///{path}"
        rv = cls(connection_uri, user=user)
        if load:
            SQLModel.metadata.create_all(rv.engine)

            with rv.get_session() as session:
                session.add_all(
                    SemanticMappingModel.from_semantic_mapping(
                        mapping.model_copy(update={"record": default_hash(mapping)})
                    )
                    for path in tqdm(repository.paths, desc="loading database")
                    for mapping in tqdm(
                        sssom_pydantic.read(path)[0], leave=False, desc=path.name, unit_scale=True
                    )
                )
                session.commit()
        return rv

    @contextlib.contextmanager
    def get_session(self) -> Generator[sqlmodel.Session, None, None]:
        """Open a context manager for a session."""
        with self.session_cls(self.engine) as s:
            yield s

    def count_predictions(self, state: Query) -> int:
        """Count predictions (i.e., anything that's not manually curated)."""
        from sqlalchemy import func
        from sqlmodel import select

        with self.get_session() as session:
            statement = select(func.count(SemanticMappingModel.id))
            statement = statement.where(self._predicted_clause)
            count = session.exec(statement).one()

        return count

    def iterate_predictions(self, state: State) -> Iterator[SemanticMapping]:
        """Iterate over pairs of positions and predicted semantic mappings."""
        from sqlmodel import select

        with self.get_session() as session:
            statement = select(SemanticMappingModel).where(self._predicted_clause)
            if state.limit is not None:
                statement = statement.limit(state.limit)
            if state.offset is not None:
                statement = statement.offset(state.offset)
            models = session.exec(statement).all()
        return iter(models)

    def get_prefix_counter(self, state: State) -> Counter[tuple[str, str]]:
        """Count the number of predictions to check for the given filters."""
        from sqlmodel import select

        with self.get_session() as session:
            statement = select(SemanticMappingModel)
            if state.limit is not None:
                statement = statement.limit(state.limit)
            if state.offset is not None:
                statement = statement.offset(state.offset)
            return Counter((m.subject.prefix, m.object.prefix) for m in session.exec(statement))

    def mark(self, reference: Reference, mark: Mark) -> None:
        """Mark the given mapping as correct."""
        from sqlmodel import select

        with self.get_session() as session:
            statement = select(SemanticMappingModel).where(SemanticMappingModel.record == reference)
            mapping = session.exec(statement).one()

            # replace some values using model_copy since the model is frozen
            new_mapping = curate_mapping(mapping, [self.current_author], mark)

            session.add(new_mapping)
            session.delete(mapping)
            session.commit()
