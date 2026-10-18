"""Proposals: what the brain asks for, before anything is decided or done.

A proposal never carries its own classification: the category of a recipient and the
decision about the proposal come from facts the code controls (contacts and policy),
never from anything the model says about it.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import ClassVar

_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class OutgoingMessage:
    """A message the clone would like to send to someone, on the owner's behalf."""

    TYPE: ClassVar[str] = "outgoing_message"

    id: str  # uuid4 hex; also used in file names, hence the strict format
    recipient: str  # the name as given, not interpreted
    text: str

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.id):
            raise ValueError(f"Invalid proposal id {self.id!r}: expected 32 lowercase hex digits")
        if not isinstance(self.recipient, str) or not isinstance(self.text, str):
            raise TypeError("recipient and text must be strings")

    @classmethod
    def new(cls, recipient: str, text: str) -> OutgoingMessage:
        """A proposal with a fresh unique id."""
        return cls(uuid.uuid4().hex, recipient, text)
