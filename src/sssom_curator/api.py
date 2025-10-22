"""This is a placeholder for putting the main code for your module."""

__all__ = [
    "hello",
    "square",
]


def hello(name: str) -> None:
    """Print hello."""
    print(f"Hello, {name}")  # noqa: T201


def square(x: int) -> int:
    """Square the number.

    :param x: An integer to square

    :returns: The integer, squared

    >>> square(5)
    25
    """
    return x**2
