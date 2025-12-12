"""Utilities for the web app."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from ..repository import Repository

if TYPE_CHECKING:
    pass

__all__ = [
    "check_current_branch",
    "commit",
    "push",
]


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
