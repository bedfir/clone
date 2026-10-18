"""Action log: an append-only, hash-chained record of what is done in the owner's name.

One JSON object per line in `<state>/log.jsonl`. Each entry stores the SHA-256 of the
previous entry's line, so editing, deleting or reordering an entry breaks the chain from
that point on (ADR-008). The log records decisions and outgoing messages, never what is
said in private: callers must not put questions, answers, notes or secrets in a payload.

This module imports nothing from the package.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_FILE = "log.jsonl"
GENESIS_HASH = "0" * 64  # the `prev` of the first entry
FIELDS = ("id", "ts", "type", "payload", "prev")
SHORT_ID_LENGTH = 8

_TYPE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")
_TAIL_BLOCK = 4096


class ActionLogError(Exception):
    """The log cannot be read or written; the message is meant to be shown to the owner."""


@dataclass(frozen=True)
class Entry:
    """One log entry, as stored."""

    id: str
    ts: str
    type: str
    payload: dict[str, Any]
    prev: str

    @property
    def short_id(self) -> str:
        return self.id[:SHORT_ID_LENGTH]


@dataclass(frozen=True)
class Verification:
    """Result of checking the whole chain.

    A break is of one of three kinds. "line": an entry that cannot be read (invalid JSON,
    missing field). "link": an entry whose `prev` does not match the entry before it as it
    is now; the culprit may be either of the two, so both are named. "start": the first
    entry does not start the chain.
    """

    ok: bool
    entries: int  # entries checked before the first problem, or all of them if ok
    head: str  # SHA-256 of the last line checked; the owner can note it
    broken_at: int | None = None  # 1-based position of the entry where the check failed
    broken_id: str | None = None
    previous_id: str | None = None  # the entry before it, for a "link" break
    kind: str | None = None  # "line", "link" or "start"
    reason: str | None = None  # technical detail

    @property
    def problem(self) -> str | None:
        """The break described for a human, or None if the chain is valid."""
        if self.ok or self.broken_at is None:
            return None
        here = _short(self.broken_id)
        if self.kind == "link":
            before = self.broken_at - 1
            return (
                f"Broken between entries {before} and {self.broken_at} "
                f"(ids {_short(self.previous_id)} and {here}): entry {self.broken_at} does not "
                f"match entry {before} as it is now. Entry {before} was modified, or entries "
                "were removed or reordered."
            )
        if self.kind == "start":
            return (
                f"Broken at entry {self.broken_at} (id {here}): the first entry does not start "
                "the chain. Entries before it were removed, or it was modified."
            )
        return f"Broken at entry {self.broken_at} (id {here}): {self.reason}"


def _short(entry_id: str | None) -> str:
    return entry_id[:SHORT_ID_LENGTH] if entry_id else "unknown"


class _InvalidLine(Exception):
    def __init__(self, reason: str, entry_id: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.entry_id = entry_id


def hash_line(line: bytes) -> str:
    """The chain hash of a line: SHA-256 of its exact bytes, without the newline."""
    return hashlib.sha256(line).hexdigest()


def format_timestamp(moment: datetime) -> str:
    """RFC 3339, UTC, millisecond precision, e.g. 2026-10-18T13:40:12.123Z."""
    moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{moment.microsecond // 1000:03d}Z"


def _owned_by_root(path: Path) -> bool:
    try:
        return path.stat().st_uid == 0
    except OSError:
        return False


def _encode(entry: dict[str, Any]) -> bytes:
    text = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def _parse(line: bytes) -> Entry:
    """Parse one line; raises _InvalidLine. Never re-serializes: hashing uses the raw line."""
    try:
        data = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _InvalidLine("invalid JSON") from None
    if not isinstance(data, dict):
        raise _InvalidLine("invalid JSON: not an object")
    entry_id = data["id"] if isinstance(data.get("id"), str) else None
    for name in FIELDS:
        if name not in data:
            raise _InvalidLine(f"missing field {name!r}", entry_id)
    for name in ("id", "ts", "type", "prev"):
        if not isinstance(data[name], str):
            raise _InvalidLine(f"invalid field {name!r}: not a string", entry_id)
    if not isinstance(data["payload"], dict):
        raise _InvalidLine("invalid field 'payload': not an object", entry_id)
    return Entry(data["id"], data["ts"], data["type"], data["payload"], data["prev"])


def _last_line(file: Any) -> tuple[bytes | None, bool]:
    """The last line of an open log (without its newline), and whether it ended with one."""
    file.seek(0, os.SEEK_END)
    size = file.tell()
    if size == 0:
        return None, True
    file.seek(size - 1)
    ends_with_newline = file.read(1) == b"\n"
    position = size - 1 if ends_with_newline else size
    pieces: list[bytes] = []
    while position > 0:
        start = max(0, position - _TAIL_BLOCK)
        file.seek(start)
        block = file.read(position - start)
        newline = block.rfind(b"\n")
        if newline != -1:
            pieces.append(block[newline + 1 :])
            break
        pieces.append(block)
        position = start
    return b"".join(reversed(pieces)), ends_with_newline


class ActionLog:
    """The log in a state folder. `clock` and `new_id` can be replaced in tests."""

    def __init__(
        self,
        state_dir: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / LOG_FILE
        self._clock = clock or (lambda: datetime.now(UTC))
        self._new_id = new_id or (lambda: uuid.uuid4().hex)

    def append(self, type: str, payload: dict[str, Any] | None = None) -> Entry:
        """Add an entry at the end of the chain and return it.

        The file is locked for the whole append and the previous line is read under that
        lock, so two sessions can never fork the chain. Raises ActionLogError if the state
        folder is missing or not writable.
        """
        if not _TYPE.fullmatch(type):
            raise ValueError(f"Invalid log entry type {type!r}: use dotted lowercase, e.g. a.b")
        if not self.state_dir.is_dir():
            raise ActionLogError(
                f"The state folder {self.state_dir} does not exist. Create it "
                "(on the host: mkdir state) and make it writable by uid 1000."
            )
        try:
            with open(self.path, "a+b") as file:
                fcntl.flock(file, fcntl.LOCK_EX)
                last, ends_with_newline = _last_line(file)
                entry = Entry(
                    id=self._new_id(),
                    ts=format_timestamp(self._clock()),
                    type=type,
                    payload=payload or {},
                    prev=GENESIS_HASH if last is None else hash_line(last),
                )
                line = _encode(
                    {
                        "id": entry.id,
                        "ts": entry.ts,
                        "type": entry.type,
                        "payload": entry.payload,
                        "prev": entry.prev,
                    }
                )
                # A torn last line (no newline) is kept as it is and ended here, so the
                # damage stays visible to `verify` instead of being glued to the new entry.
                file.write((b"" if ends_with_newline else b"\n") + line + b"\n")
                file.flush()
                os.fsync(file.fileno())
        except OSError as error:
            raise ActionLogError(self._not_writable_message(error)) from error
        return entry

    def _not_writable_message(self, error: OSError) -> str:
        message = f"Cannot write to the state folder {self.state_dir}: {error.strerror or error}."
        if _owned_by_root(self.state_dir):
            # Typical when Docker created the folder because it did not exist: chown would
            # need sudo, and a folder of the owner's own is the simplest fix.
            return (
                f"{message} It is owned by root, probably created by Docker because it did not "
                "exist. Replace it with a folder of your own (on the host): "
                "sudo rm -r state && mkdir state"
            )
        return (
            f"{message} Make it writable by the clone, which runs as uid 1000 "
            f"(for example: chown 1000 {self.state_dir})."
        )

    def recent(self, count: int) -> list[tuple[int, Entry | None]]:
        """The last `count` lines as (1-based position, entry); None for an unreadable line."""
        lines = self._lines()
        result: list[tuple[int, Entry | None]] = []
        for index in range(max(0, len(lines) - max(count, 0)), len(lines)):
            try:
                result.append((index + 1, _parse(lines[index])))
            except _InvalidLine:
                result.append((index + 1, None))
        return result

    def verify(self) -> Verification:
        """Check the whole chain and report the first broken entry.

        Hashes the raw lines as written. A missing or empty log is valid, with 0 entries.
        The last entry's own hash is not referenced by anything: removing or editing the
        last entry cannot be detected by the chain alone (see docs/ARCHITECTURE.md).
        """
        expected = GENESIS_HASH
        previous: Entry | None = None
        lines = self._lines()
        for position, line in enumerate(lines, 1):
            try:
                entry = _parse(line)
            except _InvalidLine as problem:
                return Verification(
                    False,
                    position - 1,
                    expected,
                    position,
                    problem.entry_id,
                    kind="line",
                    reason=problem.reason,
                )
            if entry.prev != expected:
                return Verification(
                    False,
                    position - 1,
                    expected,
                    position,
                    entry.id,
                    previous.id if previous else None,
                    "link" if previous else "start",
                    f"prev mismatch (expected {expected[:12]}, found {entry.prev[:12]})",
                )
            expected = hash_line(line)
            previous = entry
        return Verification(True, len(lines), expected)

    def _lines(self) -> list[bytes]:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError:
            return []
        except OSError as error:
            raise ActionLogError(f"Cannot read the log {self.path}: {error.strerror}.") from error
        lines = data.split(b"\n")
        if lines[-1] == b"":
            lines.pop()
        return lines
