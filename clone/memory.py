"""Memory: load Markdown notes, split them into chunks, retrieve relevant chunks.

Retrieval sits behind the `Retriever` interface (ADR-003): the keyword search used in
Sprint 1 can be replaced by vector search without touching the brain.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

NOTES_DIR = "notes"
HEADING_BOOST = 2

_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_FENCES = ("```", "~~~")
_WORD = re.compile(r"\w+")

_STOP_WORDS_EN = """
a an and are as at be but by do does did for from has have he her his how i if in into is it
its me my no not of on or our she so that the their them then there these they this to was we
were what when where which who why will with you your
"""
_STOP_WORDS_FR = """
a ai as au aux avec avons avez c ce ces cet cette car d dans de des donc dont du elle elles en
es est et etes il ils j je l la le les leur leurs m ma mais mes mon n ne nos notre nous on ou
pas par pour qu que quel quelle quelles quels qui quoi s sa sans se ses si son sommes sont
sur t ta tes ton tu un une vos votre vous y
"""


def normalize(text: str) -> str:
    """Lower-case `text` and strip accents, so that "Café" and "cafe" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """Split `text` into normalized words."""
    return _WORD.findall(normalize(text))


STOP_WORDS = frozenset(tokenize(_STOP_WORDS_EN) + tokenize(_STOP_WORDS_FR))


class MissingDataError(Exception):
    """The data folder does not exist or holds no notes."""


@dataclass(frozen=True)
class Chunk:
    """A section of a note, kept with its origin for traceability."""

    text: str
    source: str  # path of the note relative to the data folder, with "/" separators
    heading: str  # empty for text that comes before the first heading


class Retriever(Protocol):
    """Anything that can find the chunks most relevant to a question."""

    def search(self, question: str, limit: int) -> list[Chunk]:
        """Return at most `limit` chunks, best first, or an empty list."""
        ...


def split_chunks(text: str, source: str) -> list[Chunk]:
    """Split one Markdown note into chunks; each heading starts a new chunk.

    Sections without any text of their own are dropped.
    """
    chunks: list[Chunk] = []
    heading = ""
    lines: list[str] = []
    in_fence = False

    def close_section() -> None:
        body = "\n".join(lines).strip()
        if body:
            chunks.append(Chunk(text=body, source=source, heading=heading))

    for line in text.splitlines():
        if line.lstrip().startswith(_FENCES):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            close_section()
            heading = match.group(1)
            lines = []
        else:
            lines.append(line)
    close_section()
    return chunks


def load_chunks(data_dir: str | Path) -> list[Chunk]:
    """Load every Markdown note under `<data_dir>/notes`, recursively, as chunks.

    Raises MissingDataError if the folder is missing or contains no notes.
    """
    root = Path(data_dir)
    if not root.is_dir():
        raise MissingDataError(_missing_message(f"Data folder not found: {root}"))

    chunks: list[Chunk] = []
    for path in sorted((root / NOTES_DIR).rglob("*.md")):
        source = path.relative_to(root).as_posix()
        chunks.extend(split_chunks(path.read_text(encoding="utf-8"), source))
    if not chunks:
        raise MissingDataError(
            _missing_message(f"No notes found: {root / NOTES_DIR} has no Markdown text")
        )
    return chunks


def _missing_message(problem: str) -> str:
    return (
        f"{problem}\n"
        "Create your data folder from the example persona, then edit it:\n"
        "    cp -r example data"
    )


class KeywordRetriever:
    """Rank chunks by how many of the question's words they contain.

    Case- and accent-insensitive; common English and French words are ignored. A word
    found in a heading counts extra. Ties keep the order in which the chunks were loaded.
    """

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self._index = [
            (chunk, Counter(tokenize(chunk.text)), frozenset(tokenize(chunk.heading)))
            for chunk in chunks
        ]

    def search(self, question: str, limit: int) -> list[Chunk]:
        terms = {t for t in tokenize(question) if t not in STOP_WORDS}
        if not terms or limit <= 0:
            return []

        ranked = []
        for position, (chunk, counts, heading_terms) in enumerate(self._index):
            matched = [t for t in terms if t in counts or t in heading_terms]
            if not matched:
                continue
            weight = sum(counts[t] + (HEADING_BOOST if t in heading_terms else 0) for t in matched)
            ranked.append((-len(matched), -weight, position, chunk))
        ranked.sort(key=lambda entry: entry[:3])
        return [entry[3] for entry in ranked[:limit]]


class Memory:
    """The user's notes as chunks, searched through a swappable `Retriever`."""

    def __init__(self, chunks: Sequence[Chunk], retriever: Retriever | None = None) -> None:
        self.chunks = tuple(chunks)
        self._retriever = retriever if retriever is not None else KeywordRetriever(self.chunks)

    @classmethod
    def load(cls, data_dir: str | Path) -> Memory:
        """Load the notes under `data_dir`; see `load_chunks` for the errors."""
        return cls(load_chunks(data_dir))

    def search(self, question: str, limit: int) -> list[Chunk]:
        return self._retriever.search(question, limit)
