"""Action log: entry format, hash chain, tamper detection and its documented limits (S2-2)."""

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from clone import actionlog
from clone.actionlog import GENESIS_HASH, ActionLog, ActionLogError, format_timestamp

START = datetime(2026, 10, 18, 13, 40, 12, 123456, tzinfo=timezone.utc)
TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")


def make_log(tmp_path: Path) -> ActionLog:
    """A log with a fake clock (one second per entry) and predictable IDs."""
    moments = iter(START + timedelta(seconds=n) for n in range(10_000))
    ids = iter(f"{n:032x}" for n in range(1, 10_000))
    return ActionLog(tmp_path, clock=lambda: next(moments), new_id=lambda: next(ids))


def filled(tmp_path: Path, count: int = 5) -> ActionLog:
    log = make_log(tmp_path)
    for n in range(count):
        log.append("test.event", {"n": n})
    return log


def read_lines(log: ActionLog) -> list[bytes]:
    return log.path.read_bytes().split(b"\n")[:-1]


def write_lines(log: ActionLog, lines: list[bytes]) -> None:
    log.path.write_bytes(b"".join(line + b"\n" for line in lines))


def sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


# --- entry format --------------------------------------------------------------------------


def test_entry_has_id_utc_timestamp_type_payload_and_prev(tmp_path: Path) -> None:
    log = make_log(tmp_path)

    entry = log.append("session.started", {"model": "m", "chunks": 3})

    assert entry.id == f"{1:032x}"
    assert entry.ts == "2026-10-18T13:40:12.123Z"
    assert (entry.type, entry.payload, entry.prev) == (
        "session.started",
        {"model": "m", "chunks": 3},
        GENESIS_HASH,
    )
    assert entry.short_id == "00000000"


def test_line_is_compact_sorted_utf8_json_ending_with_a_newline(tmp_path: Path) -> None:
    log = make_log(tmp_path)

    log.append("test.event", {"b": 1, "a": "Montréal"})

    raw = log.path.read_bytes()
    assert raw == (
        b'{"id":"00000000000000000000000000000001","payload":{"a":"Montr\xc3\xa9al","b":1},'
        b'"prev":"' + GENESIS_HASH.encode() + b'","ts":"2026-10-18T13:40:12.123Z",'
        b'"type":"test.event"}\n'
    )


def test_prev_is_the_sha256_of_the_previous_line_without_its_newline(tmp_path: Path) -> None:
    log = filled(tmp_path, 3)

    lines = read_lines(log)

    prevs = [json.loads(line)["prev"] for line in lines]
    assert prevs == [GENESIS_HASH, sha(lines[0]), sha(lines[1])]


def test_defaults_are_uuid4_hex_ids_and_utc_timestamps(tmp_path: Path) -> None:
    entry = ActionLog(tmp_path).append("test.event")

    assert re.fullmatch(r"[0-9a-f]{32}", entry.id)
    assert uuid.UUID(entry.id).version == 4
    assert TIMESTAMP.fullmatch(entry.ts)
    assert entry.payload == {}


def test_timestamps_are_utc_with_millisecond_precision() -> None:
    paris = datetime(2026, 10, 18, 15, 40, 12, 999999, tzinfo=timezone(timedelta(hours=2)))

    assert format_timestamp(paris) == "2026-10-18T13:40:12.999Z"
    assert format_timestamp(START.replace(microsecond=5000)) == "2026-10-18T13:40:12.005Z"


@pytest.mark.parametrize("bad", ["", "Session.started", "a..b", "1a", "a-b", "a.", ".a", "a b"])
def test_type_must_be_dotted_lowercase(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid log entry type"):
        make_log(tmp_path).append(bad)


@pytest.mark.parametrize("good", ["a", "session.started", "policy.decision_made", "a.b.c1"])
def test_valid_types_are_accepted(tmp_path: Path, good: str) -> None:
    assert make_log(tmp_path).append(good).type == good


# --- the chain -----------------------------------------------------------------------------


def test_a_chain_of_several_entries_verifies(tmp_path: Path) -> None:
    log = filled(tmp_path, 5)

    result = log.verify()

    assert result.ok
    assert result.entries == 5
    assert result.head == sha(read_lines(log)[-1])
    assert (result.broken_at, result.broken_id, result.reason) == (None, None, None)


def test_a_missing_or_empty_log_verifies_as_zero_entries(tmp_path: Path) -> None:
    for log in (ActionLog(tmp_path / "nowhere"), ActionLog(tmp_path)):
        result = log.verify()
        assert (result.ok, result.entries, result.head) == (True, 0, GENESIS_HASH)

    (tmp_path / "log.jsonl").write_bytes(b"")
    assert ActionLog(tmp_path).verify().entries == 0


def test_the_head_changes_with_every_entry(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    heads = [log.verify().head]
    for _ in range(3):
        log.append("test.event")
        heads.append(log.verify().head)

    assert len(set(heads)) == 4


def test_the_head_is_never_cached_between_appends(tmp_path: Path) -> None:
    first, second = make_log(tmp_path), make_log(tmp_path)

    for n in range(3):
        first.append("test.event", {"from": 1, "n": n})
        second.append("test.event", {"from": 2, "n": n})

    assert first.verify().ok
    assert first.verify().entries == 6


def test_long_lines_are_read_back_correctly(tmp_path: Path) -> None:
    log = make_log(tmp_path)
    log.append("test.event", {"blob": "x" * 20_000})  # longer than one tail block
    log.append("test.event", {"blob": "y" * 10_000})
    log.append("test.event")

    assert log.verify().ok
    assert log.verify().entries == 3


# --- tamper detection ----------------------------------------------------------------------


def broken(log: ActionLog) -> tuple[int | None, str | None]:
    result = log.verify()
    assert not result.ok
    return result.broken_at, result.reason


def test_editing_a_payload_is_detected_at_the_next_entry(tmp_path: Path) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    lines[1] = lines[1].replace(b'"n":1', b'"n":99')
    write_lines(log, lines)

    position, reason = broken(log)

    assert position == 3
    assert reason is not None and reason.startswith("prev mismatch")


def test_editing_a_timestamp_is_detected(tmp_path: Path) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    lines[1] = lines[1].replace(b"13:40:13.123Z", b"09:00:00.000Z")
    assert lines[1] != read_lines(log)[1]
    write_lines(log, lines)

    assert broken(log)[0] == 3


def test_deleting_the_first_entry_is_detected(tmp_path: Path) -> None:
    log = filled(tmp_path)
    write_lines(log, read_lines(log)[1:])

    position, reason = broken(log)

    assert position == 1
    assert reason is not None and "prev mismatch" in reason


def test_deleting_a_middle_entry_is_detected(tmp_path: Path) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    write_lines(log, lines[:2] + lines[3:])

    assert broken(log)[0] == 3


def test_swapping_two_entries_is_detected(tmp_path: Path) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    lines[1], lines[2] = lines[2], lines[1]
    write_lines(log, lines)

    assert broken(log)[0] == 2


def test_inserting_a_forged_entry_is_detected(tmp_path: Path) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    forged = json.dumps(
        {
            "id": "f" * 32,
            "ts": "2026-10-18T00:00:00.000Z",
            "type": "x.y",
            "payload": {},
            "prev": "",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    write_lines(log, lines[:2] + [forged] + lines[2:])

    assert broken(log)[0] == 3


@pytest.mark.parametrize(
    "garbage", [b"{not json", b"", b"[1,2]", b"\xff\xfe\x00", b'"just a string"']
)
def test_a_corrupt_line_is_reported_as_invalid_json(tmp_path: Path, garbage: bytes) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    lines[2] = garbage
    write_lines(log, lines)

    position, reason = broken(log)

    assert position == 3
    assert reason is not None and reason.startswith("invalid JSON")


@pytest.mark.parametrize("field", ["id", "ts", "type", "payload", "prev"])
def test_a_missing_field_is_reported_with_the_entry_id(tmp_path: Path, field: str) -> None:
    log = filled(tmp_path)
    lines = read_lines(log)
    data = json.loads(lines[3])
    del data[field]
    lines[3] = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    write_lines(log, lines)

    result = log.verify()

    assert (result.ok, result.broken_at, result.reason) == (False, 4, f"missing field {field!r}")
    assert result.broken_id == (None if field == "id" else f"{4:032x}")


def test_a_field_of_the_wrong_type_is_reported(tmp_path: Path) -> None:
    log = filled(tmp_path, 2)
    lines = read_lines(log)
    lines[1] = lines[1].replace(b'"payload":{"n":1}', b'"payload":"text"')
    write_lines(log, lines)

    assert broken(log) == (2, "invalid field 'payload': not an object")


def test_the_first_broken_entry_is_the_one_reported(tmp_path: Path) -> None:
    log = filled(tmp_path, 6)
    lines = read_lines(log)
    lines[4] = b"{broken"
    lines[1] = lines[1].replace(b'"n":1', b'"n":7')
    write_lines(log, lines)

    assert broken(log)[0] == 3  # the edit of entry 2 shows at entry 3, before the corrupt line 5


def test_a_torn_last_line_stays_visible_after_the_next_append(tmp_path: Path) -> None:
    log = filled(tmp_path, 2)
    with open(log.path, "ab") as file:
        file.write(b'{"id":"abc')  # a write cut short, no newline

    log.append("test.event")  # must not be glued to the torn line

    lines = read_lines(log)
    assert len(lines) == 4 and lines[2] == b'{"id":"abc'
    assert json.loads(lines[3])["prev"] == sha(lines[2])
    assert broken(log) == (3, "invalid JSON")


# --- documented limits: the tail of the chain ------------------------------------------------


def test_limit_deleting_the_last_entry_is_not_detected_by_the_chain(tmp_path: Path) -> None:
    """Nothing refers to the last entry's hash, so removing it leaves a valid chain.

    This is why `clone log verify` prints the head hash: noted elsewhere, it exposes the
    removal. Signing the head is planned for Phase 3 (ADR-008).
    """
    log = filled(tmp_path, 5)
    noted_head = log.verify().head
    write_lines(log, read_lines(log)[:-1])

    result = log.verify()

    assert result.ok and result.entries == 4
    assert result.head != noted_head


def test_limit_editing_the_last_entry_is_not_detected_by_the_chain(tmp_path: Path) -> None:
    log = filled(tmp_path, 5)
    noted_head = log.verify().head
    lines = read_lines(log)
    lines[-1] = lines[-1].replace(b'"n":4', b'"n":40')
    write_lines(log, lines)

    result = log.verify()

    assert result.ok and result.entries == 5
    assert result.head != noted_head


# --- reading -------------------------------------------------------------------------------


def test_recent_returns_the_last_entries_with_their_positions(tmp_path: Path) -> None:
    log = filled(tmp_path, 5)

    recent = log.recent(2)

    assert [(position, entry.payload["n"]) for position, entry in recent if entry] == [
        (4, 3),
        (5, 4),
    ]
    assert log.recent(0) == []
    assert len(log.recent(100)) == 5
    assert ActionLog(tmp_path / "nowhere").recent(5) == []


def test_recent_marks_unreadable_lines(tmp_path: Path) -> None:
    log = filled(tmp_path, 3)
    lines = read_lines(log)
    lines[1] = b"garbage"
    write_lines(log, lines)

    assert [entry is None for _, entry in log.recent(3)] == [False, True, False]


# --- errors --------------------------------------------------------------------------------


def test_a_missing_state_folder_is_a_clear_error(tmp_path: Path) -> None:
    folder = tmp_path / "state"

    with pytest.raises(ActionLogError) as error:
        ActionLog(folder).append("test.event")

    message = str(error.value)
    assert str(folder) in message
    assert "mkdir state" in message and "uid 1000" in message
    assert not folder.exists()  # the log never creates it (it would belong to the wrong user)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_a_non_writable_state_folder_is_a_clear_error(tmp_path: Path) -> None:
    folder = tmp_path / "state"
    folder.mkdir()
    folder.chmod(0o555)
    try:
        with pytest.raises(ActionLogError) as error:
            ActionLog(folder).append("test.event")
    finally:
        folder.chmod(0o755)

    message = str(error.value)
    assert str(folder) in message and "Cannot write" in message
    assert "uid 1000" in message


# --- concurrency and layering --------------------------------------------------------------

WRITER = """
import sys
from clone.actionlog import ActionLog
log = ActionLog(sys.argv[1])
for n in range(int(sys.argv[3])):
    log.append("test.event", {"writer": sys.argv[2], "n": n})
"""


def test_concurrent_appends_from_two_processes_keep_a_valid_chain(tmp_path: Path) -> None:
    each = 40
    workers = [
        subprocess.Popen([sys.executable, "-c", WRITER, str(tmp_path), name, str(each)])
        for name in ("a", "b")
    ]
    assert [w.wait(timeout=120) for w in workers] == [0, 0]

    log = ActionLog(tmp_path)
    result = log.verify()
    entries = [entry for _, entry in log.recent(1000) if entry]
    assert result.ok and result.entries == 2 * each
    assert len({entry.id for entry in entries}) == 2 * each
    for name in ("a", "b"):  # each writer's own order is preserved
        assert [e.payload["n"] for e in entries if e.payload["writer"] == name] == list(range(each))


def test_the_module_imports_nothing_from_the_package() -> None:
    source = Path(actionlog.__file__).read_text(encoding="utf-8")

    assert not re.search(r"^\s*(from|import)\s+clone\b", source, re.MULTILINE)
