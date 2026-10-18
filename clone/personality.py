"""Personality: load and expose the user's style, values and red lines.

The module never prints: when it falls back to the default, the startup notice is
returned to the caller, which decides how and when to show it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PERSONALITY_FILE = "personality.md"

DEFAULT_PERSONALITY = (
    "No personality description was provided. Be clear, polite and concise, and do not "
    "imitate any particular style."
)


@dataclass(frozen=True)
class Personality:
    """Who the user is, as text for the system prompt."""

    text: str
    notice: str | None = None  # set when the default is used; to show to the user once

    @property
    def is_default(self) -> bool:
        return self.notice is not None


def load_personality(data_dir: str | Path) -> Personality:
    """Read `personality.md` from `data_dir`.

    A missing or empty file is not an error: the neutral default is used and the returned
    `Personality.notice` says so.
    """
    path = Path(data_dir) / PERSONALITY_FILE
    text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if text:
        return Personality(text=text)
    return Personality(
        text=DEFAULT_PERSONALITY,
        notice=(
            f"No personality found at {path}: using a neutral default. "
            "To describe yourself, copy example/personality.md there and edit it."
        ),
    )
