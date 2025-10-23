"""Command line interface for :mod:`sssom_curator`."""

import os
import sys
import typing
import uuid
from pathlib import Path

import click

from .constants import InitializationStrategy
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
    if ctx.invoked_subcommand != "init":
        ctx.obj = _get_repository(path)


@main.command(name="init")
@click.option(
    "-d",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True, exists=True),
    default=os.getcwd,
)
@click.option(
    "--strategy",
    type=click.Choice(list(typing.get_args(InitializationStrategy))),
    required=True,
    default="folder",
)
@click.option(
    "--base-purl",
    prompt=True,
    help="The PURL for the exported mapping set",
    default=lambda: f"https://w3id.org/sssom/mapping/stub/{uuid.uuid4()}",
)
@click.option("--mapping-set-title", prompt=True, help="The title for the mapping set")
def initialize(
    directory: Path, strategy: InitializationStrategy, base_purl: str, mapping_set_title: str
) -> None:
    """Initialize a repository."""
    from sssom_pydantic import MappingSet

    from .initialize import initialize_folder, initialize_package

    if strategy == "folder":
        mapping_set = MappingSet(
            mapping_set_id=f"{base_purl}/sssom.tsv",
            mapping_set_title=mapping_set_title,
            mapping_set_version="1",
        )
        initialize_folder(directory, mapping_set=mapping_set, base_purl=base_purl)
    elif strategy == "package":
        initialize_package(directory)
    else:
        click.secho(f"invalid strategy: {strategy}", fg="red")
        sys.exit(1)


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
