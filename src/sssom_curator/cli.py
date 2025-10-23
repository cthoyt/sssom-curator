"""Command line interface for :mod:`sssom_curator`."""

import os
import sys
from pathlib import Path

import click

from .repository import CONFIGURATION_FILENAME, Repository, add_commands

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
    f"containing a file named {CONFIGURATION_FILENAME}. Defaults to current working directory",
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
    type=click.Path(file_okay=False, dir_okay=True),
    default=os.getcwd,
)
@click.option("--purl-base", help="The PURL for the exported mapping set")
@click.option("--mapping-set-title", help="The title for the mapping set")
def initialize(directory: Path, purl_base: str, mapping_set_title: str | None) -> None:
    """Initialize a repository."""
    from sssom_pydantic import MappingSet

    from .initialize import initialize_folder, normalize_name

    directory = Path(directory).resolve()
    directory.mkdir(exist_ok=True, parents=True)

    if mapping_set_title is None:
        mapping_set_title = directory.name

    click.echo(f"initialized SSSOM project `{mapping_set_title}` at `{directory.resolve()}`")

    if purl_base is None:
        norm_title = normalize_name(mapping_set_title)
        purl_base = click.prompt(
            "PURL base?", default=f"https://w3id.org/sssom/mappings/{norm_title}"
        )

    # always have the PURL end with a trailing slash
    purl_base = purl_base.rstrip("/") + "/"

    mapping_set = MappingSet(
        mapping_set_id=f"{purl_base}sssom.tsv",
        mapping_set_title=mapping_set_title,
        mapping_set_version="1",
    )
    initialize_folder(directory, mapping_set=mapping_set, purl_base=purl_base)


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
