"""CLI: the chat loop, commands and readable errors (story S1-5)."""

import io
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fakes import FakeModel

from clone.interfaces import cli
from clone.model import AnthropicClient, Message, ModelError

EXAMPLE = Path(__file__).resolve().parent.parent / "example"
NO_TRACE = "Traceback"


class Session:
    """Runs the chat with scripted input and captures what it prints."""

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
            read=self.read,
            out=self.out,
            err=self.err,
        )


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
    assert "Projects > Line 3 retrofit" in model.calls[0][0]


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


def test_sources_lists_numbered_sources_of_the_last_answer() -> None:
    session = Session("What are my projects at work?", "/sources", "/quit")

    session.run()

    out = session.out.getvalue()
    assert "[1] notes/work/projects.md | Projects > Line 3 retrofit" in out
    assert "[2] notes/work/projects.md | Projects > OPC UA pilot" in out


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

    cli.run_chat(tmp_path, model, max_turns=5, read=read, out=session.out, err=session.err)

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

    cli.run_chat(tmp_path, model, max_turns=5, read=read, out=session.out, err=session.err)

    assert "cp -r example data" in session.err.getvalue()
    assert "Keeping the previous memory" in session.out.getvalue()
    assert "alpha" in model.calls[0][0]


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
