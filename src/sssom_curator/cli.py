"""Command line interface for :mod:`sssom_curator`."""

import os
import sys
from pathlib import Path

import click

from .repository import add_commands

__all__ = [
    "main",
]

NAME = "sssom-curator.json"


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
    from .repository import Repository

    if path.is_dir():
        path = path.joinpath(NAME)
        if not path.is_file():
            click.secho(f"no {NAME} found in directory {path}")
            sys.exit(1)

    repository = Repository.model_validate_json(path.read_text())
    repository.update_relative_paths(directory=path.parent)

    ctx.obj = repository


add_commands(main)

if __name__ == "__main__":
    main()
