"""Components."""

from __future__ import annotations

from typing import Literal, NamedTuple, TypeAlias

from pydantic import BaseModel, Field
from sssom_pydantic.query import Query

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
