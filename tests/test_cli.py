"""CLI: the chat loop, commands and readable errors (story S1-5)."""

import hashlib
import io
import json
import os
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fakes import FakeModel

from clone.actionlog import ActionLog
from clone.interfaces import cli
from clone.memory import Memory
from clone.model import AnthropicClient, Message, ModelError

EXAMPLE = Path(__file__).resolve().parent.parent / "example"
NO_TRACE = "Traceback"


class Session:
    """Runs the chat with scripted input and captures what it prints."""

    state: Path  # a fresh, empty state folder per test (see the autouse fixture below)

    def __init__(self, *lines: str) -> None:
        self.lines: Iterator[str] = iter(lines)
        self.out, self.err = io.StringIO(), io.StringIO()
        self.consumed = 0

    def read(self, prompt: str) -> str:
        assert prompt == cli.PROMPT
        try:
            line = next(self.lines)
        except StopIteration:
            raise EOFError from None
        self.consumed += 1
        return line

    def run(self, data: Path = EXAMPLE, model: object = None, max_turns: int = 10) -> int:
        return cli.run_chat(
            data,
            model or FakeModel("an answer"),  # type: ignore[arg-type]
            max_turns=max_turns,
            state_dir=self.state,
            read=self.read,
            out=self.out,
            err=self.err,
        )


@pytest.fixture(autouse=True)
def state_folder(tmp_path: Path) -> Path:
    Session.state = tmp_path / "state"
    Session.state.mkdir()
    return Session.state


def write_note(data: Path, name: str, text: str) -> None:
    path = data / "notes" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- startup -------------------------------------------------------------------------------


def test_startup_line_shows_chunk_count_and_model() -> None:
    session = Session("/quit")

    assert session.run(model=FakeModel()) == 0

    assert "Clone ready: 9 memory chunks loaded, model fake-model." in session.out.getvalue()


def test_default_data_folder_is_data_in_the_current_directory() -> None:
    assert cli.build_parser().parse_args([]).data == Path("data")
    assert cli.build_parser().parse_args(["--data", "elsewhere"]).data == Path("elsewhere")


def test_missing_personality_notice_is_shown_once_at_startup(tmp_path: Path) -> None:
    write_note(tmp_path, "a.md", "# A\nalpha")
    session = Session("hello", "again", "/quit")

    session.run(data=tmp_path)

    assert session.out.getvalue().count("No personality found") == 1


def test_no_notice_when_the_personality_file_exists() -> None:
    session = Session("/quit")

    session.run()

    assert "No personality found" not in session.out.getvalue()


@pytest.mark.parametrize("make", [lambda tmp: tmp / "nope", lambda tmp: tmp])
def test_missing_or_empty_data_folder_explains_how_to_create_it(
    tmp_path: Path, make: object
) -> None:
    session = Session("/quit")

    code = session.run(data=make(tmp_path))  # type: ignore[operator]

    assert code == 1
    assert "cp -r example data" in session.err.getvalue()
    assert session.consumed == 0
    assert NO_TRACE not in session.err.getvalue()


def test_unreadable_notes_are_reported_not_raised(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    session = Session()

    assert session.run(data=tmp_path) == 1
    assert "Cannot read the data folder" in session.err.getvalue()


# --- chatting ------------------------------------------------------------------------------


def test_a_question_is_answered_from_memory() -> None:
    model = FakeModel("You have two projects.")
    session = Session("What are my projects at work?", "/quit")

    session.run(model=model)

    assert "You have two projects." in session.out.getvalue()
    assert "Projects > Line 3 retrofit" in model.calls[0][1][0].content


def test_blank_lines_are_ignored() -> None:
    model = FakeModel()
    session = Session("", "   ", "/quit")

    session.run(model=model)

    assert model.calls == []


def test_end_of_input_exits_cleanly() -> None:
    assert Session("hello").run() == 0


# --- commands ------------------------------------------------------------------------------


def test_quit_stops_the_loop() -> None:
    session = Session("/quit", "never read")

    assert session.run() == 0
    assert session.consumed == 1


def test_sources_lists_the_stable_ids_of_the_last_answer() -> None:
    session = Session("What are my projects at work?", "/sources", "/quit")

    session.run()

    out = session.out.getvalue()
    chunks = Memory.load(EXAMPLE).search("What are my projects at work?", 2)
    assert f"[{chunks[0].id}] notes/work/projects.md | Projects > Line 3 retrofit" in out
    assert f"[{chunks[1].id}] notes/work/projects.md | Projects > OPC UA pilot" in out


def test_sources_before_any_question_says_there_are_none() -> None:
    session = Session("/sources", "/quit")

    session.run()

    assert "No sources for the last answer." in session.out.getvalue()


def test_reload_picks_up_new_notes_and_personality(tmp_path: Path) -> None:
    write_note(tmp_path, "a.md", "# A\nalpha")
    model = FakeModel()
    lines = iter(["/reload", "hello", "/quit"])
    session = Session()

    def read(prompt: str) -> str:
        line = next(lines)
        if line == "/reload":  # the user edits their files, then asks for a reload
            write_note(tmp_path, "b.md", "# B\nbeta\n\n# C\ngamma")
            (tmp_path / "personality.md").write_text("I am Robin.", encoding="utf-8")
        return line

    cli.run_chat(
        tmp_path,
        model,
        max_turns=5,
        state_dir=Session.state,
        read=read,
        out=session.out,
        err=session.err,
    )

    out = session.out.getvalue()
    assert "Clone ready: 1 memory chunks loaded" in out
    assert "Reloaded: 3 memory chunks." in out
    assert "I am Robin." in model.calls[0][0]


def test_failed_reload_keeps_the_previous_memory(tmp_path: Path) -> None:
    write_note(tmp_path, "a.md", "# A\nalpha")
    model = FakeModel()
    lines = iter(["/reload", "alpha?", "/quit"])
    session = Session()

    def read(prompt: str) -> str:
        line = next(lines)
        if line == "/reload":
            (tmp_path / "notes" / "a.md").unlink()
        return line

    cli.run_chat(
        tmp_path,
        model,
        max_turns=5,
        state_dir=Session.state,
        read=read,
        out=session.out,
        err=session.err,
    )

    assert "cp -r example data" in session.err.getvalue()
    assert "Keeping the previous memory" in session.out.getvalue()
    assert "alpha" in model.calls[0][1][0].content


def test_unknown_command_lists_the_commands() -> None:
    session = Session("/nope", "/quit")

    session.run()

    assert "Unknown command /nope" in session.out.getvalue()
    assert "/sources" in session.out.getvalue()


# --- readable errors -----------------------------------------------------------------------


class FlakyModel(FakeModel):
    """Fails on the first call, answers afterwards."""

    def complete(self, system: str, messages: Sequence[Message]) -> str:
        if not self.calls:
            self.calls.append((system, list(messages)))
            raise ModelError("Could not reach the model API.")
        return super().complete(system, messages)


def test_a_model_error_is_a_message_and_the_chat_goes_on() -> None:
    session = Session("first", "second", "/quit")

    session.run(model=FlakyModel("recovered"))

    assert "Error: Could not reach the model API." in session.err.getvalue()
    assert "recovered" in session.out.getvalue()
    assert NO_TRACE not in session.err.getvalue() + session.out.getvalue()


def test_a_missing_api_key_gives_a_readable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    session = Session("hello", "/quit")

    code = session.run(model=AnthropicClient("some-model"))

    assert code == 0
    assert "Error: No API key found. Set ANTHROPIC_API_KEY" in session.err.getvalue()
    assert NO_TRACE not in session.err.getvalue() + session.out.getvalue()


# --- main ----------------------------------------------------------------------------------


def test_main_passes_the_data_option_and_environment_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake_run_chat(data: Path, model: object, *, max_turns: int, **_: object) -> int:
        seen.update(data=data, model=model, max_turns=max_turns)
        return 0

    monkeypatch.setattr(cli, "run_chat", fake_run_chat)
    monkeypatch.setenv("CLONE_MAX_TURNS", "4")
    monkeypatch.setenv("CLONE_MODEL", "some-model")

    assert cli.main(["--data", str(tmp_path)]) == 0

    assert seen["data"] == tmp_path
    assert seen["max_turns"] == 4
    assert seen["model"].model == "some-model"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("variable", "value"), [("CLONE_MAX_TURNS", "zero"), ("CLONE_EFFORT", "turbo")]
)
def test_main_reports_bad_settings_without_a_stack_trace(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    assert cli.main([]) == 2

    err = capsys.readouterr().err
    assert variable in err
    assert NO_TRACE not in err


# --- the action log ------------------------------------------------------------------------


def log_lines(state: Path) -> list[dict]:
    return [json.loads(line) for line in (state / "log.jsonl").read_text("utf-8").splitlines()]


def test_the_session_start_is_logged_with_model_and_chunk_count() -> None:
    Session("/quit").run(model=FakeModel())

    (entry,) = log_lines(Session.state)
    assert entry["type"] == "session.started"
    assert entry["payload"] == {"model": "fake-model", "chunks": 9}


def test_each_session_adds_one_entry_to_the_same_chain() -> None:
    Session("/quit").run()
    Session("/quit").run()

    assert len(log_lines(Session.state)) == 2
    assert ActionLog(Session.state).verify().ok


def test_the_log_holds_no_secret_question_answer_or_note_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_key = "sk-ant-FAKE-KEY-0123456789abcdef"
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)
    session = Session("What are my projects at work?", "My secret question", "/reload", "/quit")

    session.run(model=FakeModel("A very private answer"))

    log = (Session.state / "log.jsonl").read_text(encoding="utf-8")
    for text in (fake_key, "projects at work", "secret question", "private answer", "retrofit"):
        assert text not in log


def test_a_missing_state_folder_stops_the_chat_with_a_clear_message(tmp_path: Path) -> None:
    session = Session("/quit")
    missing = tmp_path / "no-state"

    code = cli.run_chat(
        EXAMPLE, FakeModel(), max_turns=5, state_dir=missing, out=session.out, err=session.err
    )

    assert code == 1
    assert str(missing) in session.err.getvalue()
    assert "mkdir state" in session.err.getvalue()
    assert "Clone ready" not in session.out.getvalue()
    assert NO_TRACE not in session.err.getvalue()
    assert not missing.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anywhere")
def test_a_non_writable_state_folder_stops_the_chat_with_a_clear_message() -> None:
    Session.state.chmod(0o555)
    session = Session("/quit")
    try:
        code = session.run()
    finally:
        Session.state.chmod(0o755)

    assert code == 1
    assert "Cannot write to the state folder" in session.err.getvalue()
    assert "uid 1000" in session.err.getvalue()


def test_state_option_defaults_to_the_state_folder_for_the_chat_and_log() -> None:
    parser = cli.build_parser()

    assert parser.parse_args([]).state == Path("state")
    assert parser.parse_args(["--state", "x"]).state == Path("x")
    assert parser.parse_args(["log"]).state == Path("state")
    assert parser.parse_args(["log", "--state", "x"]).state == Path("x")
    assert parser.parse_args(["--state", "x", "log"]).state == Path("x")
    assert parser.parse_args([]).command is None  # `clone` alone is the chat


def test_main_without_a_command_starts_the_chat_with_the_state_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, object] = {}

    def fake_run_chat(data: Path, model: object, *, state_dir: Path, **_: object) -> int:
        seen["state_dir"] = state_dir
        return 0

    monkeypatch.setattr(cli, "run_chat", fake_run_chat)

    assert cli.main(["--state", str(tmp_path)]) == 0
    assert seen["state_dir"] == tmp_path
    assert cli.main([]) == 0
    assert seen["state_dir"] == Path("state")


def fill_log(state: Path, count: int) -> ActionLog:
    log = ActionLog(state)
    for n in range(count):
        log.append("test.event", {"n": n, "name": "Montréal"})
    return log


def test_clone_log_says_so_when_there_is_no_log_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["log", "--state", str(Session.state)]) == 0

    assert capsys.readouterr().out == "No log yet.\n"


def test_clone_log_lists_the_last_entries_one_line_each(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = fill_log(Session.state, 25)
    last = log.recent(1)[0][1]

    assert cli.main(["--state", str(Session.state), "log"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 20  # the default
    assert re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z  [0-9a-f]{8}  test\.event  "
        r'\{"n":\d+,"name":"Montréal"\}',
        lines[-1],
    )
    assert f"  {last.short_id}  " in lines[-1] and '"n":24' in lines[-1]
    assert '"n":5,' in lines[0]


def test_clone_log_n_limits_the_entries(capsys: pytest.CaptureFixture[str]) -> None:
    fill_log(Session.state, 5)

    cli.main(["log", "-n", "2", "--state", str(Session.state)])

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and '"n":4,' in lines[-1]


@pytest.mark.parametrize("args", [["log", "-n", "0"], ["log", "-n", "x"], ["log", "nonsense"]])
def test_bad_log_arguments_are_a_usage_error_not_a_stack_trace(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        cli.main(args)

    assert exit_.value.code == 2
    assert NO_TRACE not in capsys.readouterr().err


def test_clone_log_marks_an_unreadable_line(capsys: pytest.CaptureFixture[str]) -> None:
    log = fill_log(Session.state, 2)
    with open(log.path, "ab") as file:
        file.write(b"garbage\n")

    cli.main(["log", "--state", str(Session.state)])

    assert "(unreadable line; run: clone log verify)" in capsys.readouterr().out


def test_clone_log_verify_reports_the_entry_count_and_head(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = fill_log(Session.state, 3)
    last_line = log.path.read_bytes().splitlines()[-1]

    assert cli.main(["log", "verify", "--state", str(Session.state)]) == 0

    out = capsys.readouterr().out
    assert out == f"OK: 3 entries, head {hashlib.sha256(last_line).hexdigest()[:12]}\n"


def test_clone_log_verify_of_a_missing_log_is_zero_entries(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert cli.main(["log", "verify", "--state", str(tmp_path / "nowhere")]) == 0

    assert capsys.readouterr().out == "OK: 0 entries, head 000000000000\n"


def test_clone_log_verify_fails_when_a_line_was_edited(
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = fill_log(Session.state, 4)
    lines = log.path.read_bytes().splitlines()
    lines[1] = lines[1].replace(b'"n":1', b'"n":9')
    log.path.write_bytes(b"\n".join(lines) + b"\n")
    third_id = json.loads(lines[2])["id"][:8]

    code = cli.main(["log", "verify", "--state", str(Session.state)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.startswith(f"Broken at entry 3 (id {third_id}): prev mismatch")
    assert NO_TRACE not in captured.err


def test_clone_log_verify_names_a_corrupt_line(capsys: pytest.CaptureFixture[str]) -> None:
    log = fill_log(Session.state, 3)
    lines = log.path.read_bytes().splitlines()
    lines[1] = b"{oops"
    log.path.write_bytes(b"\n".join(lines) + b"\n")

    assert cli.main(["log", "verify", "--state", str(Session.state)]) == 1

    assert "Broken at entry 2 (id unknown): invalid JSON" in capsys.readouterr().err
