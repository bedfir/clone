"""Memory: load Markdown notes, split them into chunks, retrieve relevant chunks.

Retrieval sits behind the `Retriever` interface (ADR-003): the keyword search used in
Sprint 1 can be replaced by vector search without touching the brain.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

NOTES_DIR = "notes"
HEADING_BOOST = 2
ID_LENGTH = 8

_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_FENCES = ("```", "~~~")
_WORD = re.compile(r"[^\W_]+")  # letters and digits; "_" separates words
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae"})
HEADING_SEPARATOR = " > "

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
    """Lower-case `text`, strip accents and fold ligatures: "Café" and "cafe" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.casefold().translate(_LIGATURES))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    """Split `text` into normalized words."""
    return _WORD.findall(normalize(text))


def fold_plural(word: str) -> str:
    """Strip a trailing "s" or "x" from words longer than 3 characters ("cats" -> "cat")."""
    return word[:-1] if len(word) > 3 and word[-1] in "sx" else word


def tokenize(text: str) -> list[str]:
    """Split `text` into search terms: normalized words with plurals folded."""
    return [fold_plural(word) for word in words(text)]


STOP_WORDS = frozenset(words(_STOP_WORDS_EN) + words(_STOP_WORDS_FR))


class MissingDataError(Exception):
    """The data folder does not exist or holds no notes."""


@dataclass(frozen=True)
class Chunk:
    """A section of a note, kept with its origin for traceability."""

    text: str
    source: str  # path of the note relative to the data folder, with "/" separators
    heading: str  # full path such as "Projects > Line 3 retrofit"; empty before any heading
    occurrence: int = 0  # 0 for the first chunk with this source and heading, then 1, 2...

    @property
    def id(self) -> str:
        """A short ID, stable across turns and reloads, derived from source and heading path.

        Identical for the same note section as long as the note's path and the section's
        heading path do not change, so citations keep their meaning during a conversation.
        """
        key = f"{self.source}\n{self.heading}"
        if self.occurrence:
            key += f"\n{self.occurrence}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:ID_LENGTH]

    @property
    def label(self) -> str:
        """Where the chunk comes from, e.g. "notes/work/projects.md | Projects > Line 3"."""
        return f"{self.source} | {self.heading}" if self.heading else self.source


class Retriever(Protocol):
    """Anything that can find the chunks most relevant to a question."""

    def search(self, question: str, limit: int) -> list[Chunk]:
        """Return at most `limit` chunks, best first, or an empty list."""
        ...


def split_chunks(text: str, source: str) -> list[Chunk]:
    """Split one Markdown note into chunks; each heading starts a new chunk.

    A chunk's heading is the path of the headings above it, so a section keeps the context
    of its parents. Sections without any text of their own are dropped.
    """
    chunks: list[Chunk] = []
    seen: Counter[str] = Counter()  # chunks per heading path, to tell duplicates apart
    parents: list[tuple[int, str]] = []  # (level, title) of the enclosing headings
    lines: list[str] = []
    in_fence = False

    def close_section() -> None:
        body = "\n".join(lines).strip()
        if body:
            heading = HEADING_SEPARATOR.join(title for _, title in parents)
            chunks.append(
                Chunk(text=body, source=source, heading=heading, occurrence=seen[heading])
            )
            seen[heading] += 1

    for line in text.splitlines():
        if line.lstrip().startswith(_FENCES):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            close_section()
            level = len(line.lstrip().split(maxsplit=1)[0])
            while parents and parents[-1][0] >= level:
                parents.pop()
            parents.append((level, match.group(1)))
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


def _path_terms(source: str) -> list[str]:
    """Search terms from a note's folders and file name, without the top `notes/` folder."""
    parts = PurePosixPath(source).with_suffix("").parts
    if len(parts) > 1 and parts[0] == NOTES_DIR:
        parts = parts[1:]
    return tokenize(" ".join(parts))


class KeywordRetriever:
    """Rank chunks by how many of the question's words they contain.

    Case- and accent-insensitive, with plurals folded; common English and French words
    are ignored. Words in the heading path or in the note's path (folders and file name)
    count extra. Ties keep the order in which the chunks were loaded.
    """

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self._index = [
            (
                chunk,
                Counter(tokenize(chunk.text)),
                frozenset(tokenize(chunk.heading) + _path_terms(chunk.source)),
            )
            for chunk in chunks
        ]

    def search(self, question: str, limit: int) -> list[Chunk]:
        terms = {fold_plural(w) for w in words(question) if w not in STOP_WORDS}
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
