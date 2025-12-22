"""Utilities for the web app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple, TypeAlias

from pydantic import BaseModel, Field
from sssom_pydantic.query import Query

if TYPE_CHECKING:
    from ..repository import Repository

__all__ = [
    "GitCommandFailure",
    "GitCommandSuccess",
    "PaginationElement",
    "PersistRemoteFailure",
    "PersistRemoteSuccess",
    "Sort",
    "State",
    "check_current_branch",
    "commit",
    "get_pagination_elements",
    "push",
]


#: The default limit
DEFAULT_LIMIT: int = 10

#: The default offset
DEFAULT_OFFSET: int = 0

#: Sort mechanisms
Sort: TypeAlias = Literal["asc", "desc", "subject", "object"]


def commit(repository: Repository, message: str) -> GitCommandSuccess | GitCommandFailure:
    """Make a commit with the following message."""
    return _git(repository, "commit", "-m", message, "-a")


def push(
    repository: Repository, branch: str | None = None
) -> GitCommandSuccess | GitCommandFailure:
    """Push the git repo."""
    if branch is not None:
        return _git(repository, "push", "origin", branch)
    else:
        return _git(repository, "push")


class BranchCheck(NamedTuple):
    """Text for a successfully run branch check."""

    name: str
    usable: bool


BRANCH_BLOCKLIST = {"master", "main"}


def check_current_branch(repository: Repository) -> BranchCheck | GitCommandFailure:
    """Return if on the master/main branch."""
    match _git(repository, "rev-parse", "--abbrev-ref", "HEAD"):
        case GitCommandSuccess(name):
            return BranchCheck(name=name, usable=name not in BRANCH_BLOCKLIST)
        case GitCommandFailure() as failure:
            return failure


class GitCommandSuccess(NamedTuple):
    """Text for git command that ran successfully."""

    output: str


class GitCommandFailure(NamedTuple):
    """Text for git command that resulted in a CalledProcessError."""

    message: str


def _git(repository: Repository, *args: str) -> GitCommandSuccess | GitCommandFailure:
    import os
    from subprocess import CalledProcessError, check_output

    directory = repository.predictions_path.parent
    with open(os.devnull, "w") as devnull:
        try:
            ret = check_output(  # noqa: S603
                ["git", *args],  # noqa:S607
                cwd=directory,
                stderr=devnull,
            )
        except CalledProcessError as e:
            return GitCommandFailure(str(e))
        else:
            return GitCommandSuccess(ret.strip().decode("utf-8"))


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
    message: str


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
