"""Memory: loading, chunking, ranking and the empty case (story S1-2)."""

from pathlib import Path

import pytest

from clone.memory import (
    Chunk,
    KeywordRetriever,
    Memory,
    MissingDataError,
    fold_plural,
    load_chunks,
    normalize,
    split_chunks,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "example"


def write_note(data: Path, name: str, text: str) -> None:
    path = data / "notes" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_memory(*sections: tuple[str, str]) -> Memory:
    """A memory with one chunk per (heading, text) pair."""
    return Memory([Chunk(text=text, source="n.md", heading=heading) for heading, text in sections])


# --- loading -----------------------------------------------------------------------------


def test_loads_every_markdown_file_recursively(tmp_path: Path) -> None:
    write_note(tmp_path, "a.md", "# A\n\nalpha")
    write_note(tmp_path, "deep/er/b.md", "# B\n\nbeta")
    write_note(tmp_path, "ignored.txt", "# C\n\ngamma")

    chunks = load_chunks(tmp_path)

    assert [c.source for c in chunks] == ["notes/a.md", "notes/deep/er/b.md"]


def test_loads_the_example_persona() -> None:
    sources = {c.source for c in Memory.load(EXAMPLE).chunks}

    assert "notes/habits.md" in sources
    assert "notes/work/projects.md" in sources


# --- chunking ----------------------------------------------------------------------------


def test_each_heading_starts_a_chunk_that_keeps_source_and_heading_path() -> None:
    text = "# Top\n\n## One\nfirst\n\n## Two\nsecond\nline\n"

    assert split_chunks(text, "notes/x.md") == [
        Chunk(text="first", source="notes/x.md", heading="Top > One"),
        Chunk(text="second\nline", source="notes/x.md", heading="Top > Two"),
    ]


def test_heading_path_follows_the_outline() -> None:
    text = "# A\n## B\n### C\nc text\n## D\nd text\n# E\ne text\n#### Deep\ndeep text\n"

    assert [c.heading for c in split_chunks(text, "n.md")] == [
        "A > B > C",
        "A > D",
        "E",
        "E > Deep",
    ]


def test_text_before_the_first_heading_has_an_empty_heading() -> None:
    chunks = split_chunks("intro\n\n# Later\nbody", "n.md")

    assert [(c.heading, c.text) for c in chunks] == [("", "intro"), ("Later", "body")]


def test_hash_lines_inside_code_fences_are_not_headings() -> None:
    chunks = split_chunks("# Code\n```\n# comment\n```\nafter", "n.md")

    assert len(chunks) == 1
    assert "# comment" in chunks[0].text


def test_closing_hashes_are_not_part_of_the_heading() -> None:
    assert split_chunks("## Title ##\nbody", "n.md")[0].heading == "Title"


# --- search: ranking and the empty case ----------------------------------------------------


def test_best_match_comes_first_and_limit_applies() -> None:
    memory = make_memory(("One", "cats"), ("Both", "cats and dogs"), ("Many", "dogs dogs dogs"))

    assert [c.heading for c in memory.search("cats dogs", 5)] == ["Both", "Many", "One"]
    assert [c.heading for c in memory.search("cats dogs", 2)] == ["Both", "Many"]


def test_a_word_in_the_heading_counts_extra() -> None:
    memory = make_memory(("Misc", "I take trains once"), ("Trains", "nothing here"))

    assert memory.search("trains", 1)[0].heading == "Trains"


def test_ties_keep_the_loading_order() -> None:
    memory = make_memory(("First", "tea"), ("Second", "tea"))

    assert [c.heading for c in memory.search("tea", 5)] == ["First", "Second"]


@pytest.mark.parametrize("question", ["unrelated", "", "   ", "the and le la"])
def test_no_match_returns_an_empty_list(question: str) -> None:
    memory = make_memory(("Pets", "cats and dogs"))

    assert memory.search(question, 5) == []


def test_non_positive_limit_returns_an_empty_list() -> None:
    assert make_memory(("Pets", "cats")).search("cats", 0) == []


# --- search: case, accents, stop words ----------------------------------------------------


def test_normalize_ignores_case_and_accents() -> None:
    assert normalize("Café ÉTÉ Saône") == "cafe ete saone"


@pytest.mark.parametrize("question", ["Saône", "saone", "SAONE", "saône"])
def test_search_ignores_case_and_accents_on_the_example(question: str) -> None:
    results = Memory.load(EXAMPLE).search(question, 3)

    assert [c.heading for c in results] == ["Habits > Mornings"]


@pytest.mark.parametrize("question", ["cafe", "café", "CAFÉ"])
def test_accented_word_in_a_note_matches_plain_question(question: str) -> None:
    results = Memory.load(EXAMPLE).search(question, 1)

    assert results[0].source == "notes/habits.md"


def test_montreal_matches_with_or_without_accent() -> None:
    memory = Memory.load(EXAMPLE)

    plain = memory.search("Montreal", 3)
    accented = memory.search("Montréal", 3)

    assert plain == accented
    assert plain[0].heading == "Preferences > Travel"


def test_english_and_french_stop_words_are_ignored() -> None:
    memory = make_memory(("Noise", "the of and le la les des"), ("Signal", "train"))

    assert [c.heading for c in memory.search("What is the train? Quel est le train", 5)] == [
        "Signal"
    ]


def test_search_finds_chunks_through_their_parent_headings() -> None:
    chunks = split_chunks("# Projects\n## Line 3 retrofit\nreplacing relays\n", "n.md")

    assert Memory(chunks).search("projects", 5) == chunks


def test_search_finds_chunks_through_the_note_path() -> None:
    memory = Memory([Chunk(text="relay logic", source="notes/work/projects.md", heading="")])

    assert memory.search("work", 5) == list(memory.chunks)
    assert memory.search("project", 5) == list(memory.chunks)


def test_the_top_notes_folder_is_not_searchable() -> None:
    memory = Memory([Chunk(text="relay logic", source="notes/work/projects.md", heading="")])

    assert memory.search("notes", 5) == []


def test_path_and_heading_words_count_extra() -> None:
    memory = Memory(
        [
            Chunk(text="I like tea", source="notes/a.md", heading="Misc"),
            Chunk(text="nothing", source="notes/tea.md", heading=""),
        ]
    )

    assert [c.source for c in memory.search("tea", 5)] == ["notes/tea.md", "notes/a.md"]


def test_what_are_my_projects_at_work_finds_both_project_chunks() -> None:
    results = Memory.load(EXAMPLE).search("What are my projects at work?", 5)

    assert [(c.source, c.heading) for c in results[:2]] == [
        ("notes/work/projects.md", "Projects > Line 3 retrofit"),
        ("notes/work/projects.md", "Projects > OPC UA pilot"),
    ]


# --- plurals and ligatures -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "folded"),
    [("cats", "cat"), ("prix", "pri"), ("gas", "gas"), ("bus", "bus"), ("cat", "cat"), ("", "")],
)
def test_fold_plural_strips_s_or_x_from_words_longer_than_three(word: str, folded: str) -> None:
    assert fold_plural(word) == folded


def test_plural_questions_match_singular_notes_and_back() -> None:
    assert make_memory(("Pets", "one cat")).search("cats", 5)
    assert make_memory(("Pets", "many cats")).search("cat", 5)


def test_normalize_folds_ligatures() -> None:
    assert normalize("Cœur Æon") == "coeur aeon"


def test_ligature_in_a_note_matches_plain_question() -> None:
    assert make_memory(("Corps", "Le cœur bat")).search("coeur", 5)
    assert make_memory(("Corps", "Le coeur bat")).search("CŒUR", 5)


# --- stable IDs ----------------------------------------------------------------------------


def test_chunk_id_is_short_hex_and_deterministic() -> None:
    chunk = Chunk(text="x", source="notes/a.md", heading="A > B")

    assert len(chunk.id) == 8
    assert int(chunk.id, 16) >= 0
    assert chunk.id == Chunk(text="other text", source="notes/a.md", heading="A > B").id


def test_chunk_id_depends_on_source_and_heading_path_only() -> None:
    base = Chunk(text="x", source="notes/a.md", heading="A > B")

    assert base.id != Chunk(text="x", source="notes/b.md", heading="A > B").id
    assert base.id != Chunk(text="x", source="notes/a.md", heading="A > C").id
    assert base.id != Chunk(text="x", source="notes/a.md", heading="B").id


def test_duplicate_headings_in_one_note_get_distinct_ids() -> None:
    chunks = split_chunks("# Todo\nfirst\n# Todo\nsecond\n", "notes/a.md")

    assert [c.occurrence for c in chunks] == [0, 1]
    assert chunks[0].id != chunks[1].id
    assert chunks[0].id == split_chunks("# Todo\nfirst\n", "notes/a.md")[0].id


def test_ids_of_the_example_persona_are_unique_and_survive_a_reload() -> None:
    first = [c.id for c in Memory.load(EXAMPLE).chunks]
    second = [c.id for c in Memory.load(EXAMPLE).chunks]

    assert first == second
    assert len(set(first)) == len(first)


# --- retrieval interface --------------------------------------------------------------------


def test_memory_delegates_to_any_retriever() -> None:
    class Fixed:
        def search(self, question: str, limit: int) -> list[Chunk]:
            return [Chunk(text=f"{question}/{limit}", source="fake", heading="")]

    memory = Memory([], retriever=Fixed())

    assert memory.search("q", 3) == [Chunk(text="q/3", source="fake", heading="")]


def test_keyword_retriever_works_on_its_own() -> None:
    retriever = KeywordRetriever([Chunk(text="tea time", source="n.md", heading="")])

    assert retriever.search("tea", 1)[0].text == "tea time"


# --- missing or empty data ------------------------------------------------------------------


def assert_explains_how_to_create_data(error: pytest.ExceptionInfo[MissingDataError]) -> None:
    assert "cp -r example data" in str(error.value)


def test_missing_data_folder_explains_how_to_create_it(tmp_path: Path) -> None:
    with pytest.raises(MissingDataError, match="not found") as error:
        Memory.load(tmp_path / "data")

    assert_explains_how_to_create_data(error)


def test_empty_data_folder_explains_how_to_create_it(tmp_path: Path) -> None:
    with pytest.raises(MissingDataError, match="No notes") as error:
        Memory.load(tmp_path)

    assert_explains_how_to_create_data(error)


def test_data_folder_without_notes_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("# Me\nsomeone", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    with pytest.raises(MissingDataError) as error:
        Memory.load(tmp_path)

    assert_explains_how_to_create_data(error)
