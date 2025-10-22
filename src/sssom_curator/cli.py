"""Command line interface for :mod:`sssom_curator`."""

import os
import sys
from pathlib import Path

import click

from .repository import NAME, Repository, add_commands

__all__ = [
    "main",
]


@click.group(help="A CLI for managing SSSOM repositories.")
@click.option(
    "-p",
    "--path",
    type=click.Path(file_okay=True, dir_okay=True, exists=True),
    default=os.getcwd,
    help=f"Either the path to a sssom-curator configuration file or a directory "
    f"containing a file named {NAME}. Defaults to current working directory",
)
@click.pass_context
def main(ctx: click.Context, path: Path) -> None:
    """Run the CLI."""
    ctx.obj = _get_repository(path)


def _get_repository(path: str | Path | None) -> Repository:
    if path is None:
        raise ValueError("path not given")

    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError

    if path.is_file():
        return Repository.from_path(path)

    if path.is_dir():
        try:
            repository = Repository.from_directory(path)
        except FileNotFoundError as e:
            click.secho(e.args[0])
            sys.exit(1)
        else:
            return repository

    click.secho(f"bad path: {path}")
    sys.exit(1)


add_commands(main)

if __name__ == "__main__":
    main()
