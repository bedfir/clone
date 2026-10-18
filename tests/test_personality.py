"""Personality: loading and the neutral default (story S1-3)."""

from pathlib import Path

import pytest

from clone.personality import DEFAULT_PERSONALITY, Personality, load_personality

EXAMPLE = Path(__file__).resolve().parent.parent / "example"


def test_reads_personality_md_from_the_data_folder(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("\n# Me\nDirect and concise.\n\n", encoding="utf-8")

    personality = load_personality(tmp_path)

    assert personality == Personality(text="# Me\nDirect and concise.")
    assert personality.notice is None
    assert not personality.is_default


def test_loads_the_example_persona() -> None:
    personality = load_personality(EXAMPLE)

    assert "Alex Moreau" in personality.text
    assert not personality.is_default


def test_missing_file_uses_the_neutral_default_and_returns_a_notice(tmp_path: Path) -> None:
    personality = load_personality(tmp_path)

    assert personality.text == DEFAULT_PERSONALITY
    assert personality.is_default
    assert personality.notice is not None
    assert str(tmp_path / "personality.md") in personality.notice
    assert "example/personality.md" in personality.notice


def test_missing_data_folder_is_not_an_error(tmp_path: Path) -> None:
    assert load_personality(tmp_path / "nope").is_default


@pytest.mark.parametrize("content", ["", "  \n\n"])
def test_empty_file_uses_the_default(tmp_path: Path, content: str) -> None:
    (tmp_path / "personality.md").write_text(content, encoding="utf-8")

    assert load_personality(tmp_path).text == DEFAULT_PERSONALITY


def test_the_module_returns_the_notice_instead_of_printing_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    notice = load_personality(tmp_path).notice

    captured = capsys.readouterr()
    assert notice
    assert captured.out == ""
    assert captured.err == ""
