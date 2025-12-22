"""An abstract backend for the SSSOM Curator web application."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterable, Sequence

import curies
from curies import Reference
from sssom_pydantic import SemanticMapping
from sssom_pydantic.api import SemanticMappingHash, mapping_hash_v1
from sssom_pydantic.process import Mark
from sssom_pydantic.query import Query

from ..components import PersistRemoteFailure, PersistRemoteSuccess, State
from ..utils import GitCommandFailure, check_current_branch, commit, push
from ...repository import Repository

__all__ = [
    "Controller",
]


class Controller(ABC):
    """A module for interacting with mappings."""

    def __init__(
        self,
        *,
        repository: Repository,
        semantic_mapping_hash: SemanticMappingHash | None = None,
        converter: curies.Converter,
        target_references: Iterable[Reference] | None = None,
    ) -> None:
        """Initialize the controller."""
        self.repository = repository
        self.mapping_hash = semantic_mapping_hash or mapping_hash_v1
        self.converter = converter
        self.total_curated = 0
        self.target_references = set(target_references) if target_references is not None else None

    @abstractmethod
    def get_prefix_counter(self, state: State | None = None) -> Counter[tuple[str, str]]:
        """Get a subject/object prefix counter."""

    @abstractmethod
    def get_predictions(self, state: State | None = None) -> Sequence[SemanticMapping]:
        """Get predicted semantic mappings."""

    @abstractmethod
    def count_predictions(self, query: Query | None = None) -> int:
        """Count the number of predictions to check for the given filters."""

    @abstractmethod
    def mark(self, reference: Reference, mark: Mark, authors: Reference | list[Reference]) -> None:
        """Mark the given mapping as correct."""

    @abstractmethod
    def count_unpersisted(self) -> int:
        """Count the number of unpersisted curations."""

    @abstractmethod
    def persist(self) -> None:
        """Mark the given mapping as correct."""

    def count_remote_unpersisted(self) -> int:
        """Count the number of curations that haven't been persisted to a remote repository."""
        return self.total_curated

    def persist_remote(self, author: Reference) -> PersistRemoteSuccess | PersistRemoteFailure:
        """Persist remotely."""
        branch_res = check_current_branch(self.repository)
        if isinstance(branch_res, GitCommandFailure):
            return PersistRemoteFailure("branch check", branch_res.message)
        if not branch_res.usable:
            return PersistRemoteFailure(
                "branch name", f"refusing to push to {branch_res.name} - make a branch first."
            )

        label = "mappings" if self.total_curated > 1 else "mapping"
        message = f"Curated {self.total_curated} {label} ({author.curie})"
        commit_res = commit(self.repository, message)
        if isinstance(commit_res, GitCommandFailure):
            return PersistRemoteFailure("commit", commit_res.message)

        # TODO what happens if there's no corresponding on remote?
        push_res = push(self.repository, branch=branch_res.name)
        if isinstance(push_res, GitCommandFailure):
            return PersistRemoteFailure("push", push_res.message)

        self.total_curated = 0
        return PersistRemoteSuccess(commit_res.output + "\n" + push_res.output)
