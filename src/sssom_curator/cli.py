"""Command line interface for :mod:`sssom_curator`."""

import click

__all__ = [
    "main",
]


@click.command()
def main() -> None:
    """CLI for sssom_curator."""


if __name__ == "__main__":
    main()
