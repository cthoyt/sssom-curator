"""Utilities for the web app."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeAlias

from pydantic import BaseModel, Field
from sssom_pydantic.query import Query

if TYPE_CHECKING:
    from subprocess import CalledProcessError

__all__ = [
    "PaginationElement",
    "PersistRemoteFailure",
    "PersistRemoteSuccess",
    "Sort",
    "State",
    "get_pagination_elements",
]

#: The default limit
DEFAULT_LIMIT: int = 10

#: The default offset
DEFAULT_OFFSET: int = 0

#: Sort mechanisms
Sort: TypeAlias = Literal["asc", "desc", "subject", "object"]


def persist_remote(directory: Path, message: str) -> PersistRemoteSuccess | PersistRemoteFailure:
    """Persist remotely."""
    import subprocess

    from pystow.git import commit, get_current_branch, is_likely_default_branch, push

    branch_name = get_current_branch(directory)

    if is_likely_default_branch(directory):
        return PersistRemoteFailure(
            "branch name", f"refusing to push to {branch_name} - make a branch first."
        )

    try:
        commit_res = commit(directory, message)
    except subprocess.CalledProcessError as e:
        return PersistRemoteFailure("commit", e)

    # TODO what happens if there's no corresponding on remote?
    try:
        push_res = push(directory, branch=branch_name)
    except subprocess.CalledProcessError as e:
        return PersistRemoteFailure("push", e)

    return PersistRemoteSuccess(commit_res.stdout + "\n" + push_res.stderr)


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


class PersistRemoteSuccess(NamedTuple):
    """Represents success message."""

    message: str


class PersistRemoteFailure(NamedTuple):
    """Represents failure message."""

    step: str
    exception: CalledProcessError


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
