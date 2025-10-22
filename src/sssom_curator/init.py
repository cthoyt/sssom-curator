from pathlib import Path

__all__ = [
    "initialize_folder",
    "initialize_package",
]


def initialize_folder(directory: Path) -> None:
    raise NotImplementedError


def initialize_package(directory: Path) -> None:
    raise NotImplementedError
