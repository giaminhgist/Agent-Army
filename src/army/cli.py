"""`army` command line."""

from __future__ import annotations

from army import __version__


def main(argv: list[str] | None = None) -> int:
    print(f"army {__version__}")
    return 0
