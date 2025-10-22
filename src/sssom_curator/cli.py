"""Command line interface for :mod:`sssom_curator`."""

import os
import sys
from pathlib import Path

import click

from .repository import Repository, add_commands

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
        directory = path
        path = directory.joinpath(NAME)
        if path.is_file():
            return Repository.from_path(path)

        positives_path = directory.joinpath("positive.sssom.tsv")
        negatives_path = directory.joinpath("negative.sssom.tsv")
        predictions_path = directory.joinpath("predictions.sssom.tsv")
        unsure_path = directory.joinpath("unsure.sssom.tsv")

        if (
            positives_path.is_file()
            and negatives_path.is_file()
            and predictions_path.is_file()
            and unsure_path.is_file()
        ):
            from sssom_pydantic import MappingSet

            r = Repository(
                positives_path=positives_path,
                negatives_path=negatives_path,
                predictions_path=predictions_path,
                unsure_path=unsure_path,
                mapping_set=MappingSet(mapping_set_id=""),
            )
            return r

        click.secho(f"no {NAME} found in directory {path}")
        sys.exit(1)

    click.secho(f"bad path: {path}")
    sys.exit(1)


add_commands(main)

if __name__ == "__main__":
    main()
