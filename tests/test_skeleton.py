"""Smoke tests for the project skeleton (story S1-1)."""

from pathlib import Path

import clone

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "example"


def test_package_imports() -> None:
    assert clone.__version__


def test_example_persona_is_complete() -> None:
    assert (EXAMPLE / "personality.md").is_file()
    notes = list((EXAMPLE / "notes").rglob("*.md"))
    assert len(notes) >= 3
