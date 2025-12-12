"""Utilities for the web app."""

from __future__ import annotations

from typing import TypeVar, get_args

from sssom_pydantic.process import Mark

__all__ = [
    "Mark",
    "commit",
    "get_branch",
    "not_main",
    "push",
]

X = TypeVar("X")
Y = TypeVar("Y")


def commit(message: str) -> str | None:
    """Make a commit with the following message."""
    return _git("commit", "-m", message, "-a")


def push(branch_name: str | None = None) -> str | None:
    """Push the git repo."""
    if branch_name is not None:
        return _git("push", "origin", branch_name)
    else:
        return _git("push")


def not_main() -> bool:
    """Return if on the master branch."""
    return "master" != _git("rev-parse", "--abbrev-ref", "HEAD")


def get_branch() -> str:
    """Return current git branch."""
    rv = _git("branch", "--show-current")
    if rv is None:
        raise RuntimeError
    return rv


def _git(*args: str) -> str | None:
    import os
    from subprocess import CalledProcessError, check_output

    with open(os.devnull, "w") as devnull:
        try:
            ret = check_output(  # noqa: S603
                ["git", *args],  # noqa:S607
                cwd=os.path.dirname(__file__),
                stderr=devnull,
            )
        except CalledProcessError as e:
            print(e)  # noqa:T201
            return None
        else:
            return ret.strip().decode("utf-8")


#: The set of all possible curation marks
MARKS: set[Mark] = set(get_args(Mark))
