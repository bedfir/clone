"""Read a TOML configuration file with the standard library, with readable errors."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def read_toml(path: Path, error: type[Exception]) -> dict[str, Any] | None:
    """Parse `path`; None if the file does not exist. Problems raise `error` naming the file."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as problem:
        raise error(f"{path}: cannot read the file ({problem.strerror}).") from problem
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as problem:
        raise error(f"{path}: the file is not valid UTF-8.") from problem
    except tomllib.TOMLDecodeError as problem:
        raise error(f"{path}: invalid TOML: {problem}") from problem
