"""Utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Sequence
from typing import Literal, TypeAlias

from curies import Reference
from pydantic import BaseModel, Field
from sssom_pydantic import SemanticMapping
from sssom_pydantic.process import Mark
from sssom_pydantic.query import Query

__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_OFFSET",
    "Controller",
    "Sort",
    "State",
]
DEFAULT_LIMIT: int = 10
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


class Controller(ABC):
    """A module for interacting with mappings."""

    @abstractmethod
    def get_prefix_counter(self, state: State) -> Counter[tuple[str, str]]:
        """Get a subject/object prefix counter."""

    @abstractmethod
    def get_predictions(self, state: State) -> Sequence[SemanticMapping]:
        """Get predicted semantic mappings."""

    @abstractmethod
    def count_predictions(self, state: Query) -> int:
        """Count the number of predictions to check for the given filters."""

    @abstractmethod
    def mark(self, reference: Reference, mark: Mark) -> None:
        """Mark the given mapping as correct."""
