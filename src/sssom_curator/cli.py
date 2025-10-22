"""Command line interface for :mod:`sssom_curator`."""

from pathlib import Path

import click

from .repository import add_commands

__all__ = [
    "main",
]


@click.group()
@click.argument("path", type=Path)
@click.pass_context
def main(ctx: click.Context, path: Path) -> None:
    """CLI for sssom_curator."""
    from .repository import Repository

    if not path.exists():
        raise FileNotFoundError

    if path.is_dir():
        path = path.joinpath("sssom-curator.json")

    repository = Repository.model_validate_json(path.read_text())
    repository.update_relative_paths(directory=path.parent)

    ctx.obj = repository


add_commands(main)

if __name__ == "__main__":
    main()
