"""Utilities for the web app."""

from __future__ import annotations

from typing import Literal, TypeAlias, TypeVar, get_args

__all__ = [
    "Mark",
    "commit",
    "get_branch",
    "normalize_mark",
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


Mark: TypeAlias = Literal["correct", "incorrect", "unsure", "broad", "narrow"]
MARKS: set[Mark] = set(get_args(Mark))
CORRECT = {"yup", "true", "t", "correct", "right", "close enough", "disco"}
INCORRECT = {"no", "nope", "false", "f", "nada", "nein", "incorrect", "negative", "negatory"}
UNSURE = {"unsure", "maybe", "idk", "idgaf", "idgaff"}


def normalize_mark(value: str) -> Mark:
    """Get the mark."""
    value = value.lower()
    if value in CORRECT:
        return "correct"
    elif value in INCORRECT:
        return "incorrect"
    elif value in UNSURE:
        return "unsure"
    elif value in {"broader", "broad"}:
        return "broad"
    elif value in {"narrow", "narrower"}:
        return "narrow"
    else:
        raise ValueError
