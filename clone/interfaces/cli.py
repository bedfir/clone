"""CLI: terminal chat in assistant mode.

A thin adapter: it reads lines, forwards questions to the brain and prints what comes back.
Every failure the user can fix (missing data, missing API key, network or API error) is shown
as a short message, never as a stack trace.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from clone.brain import Brain, max_turns_from_env
from clone.memory import Memory, MissingDataError
from clone.model import AnthropicClient, ModelClient, ModelError
from clone.personality import Personality, load_personality

DEFAULT_DATA_DIR = Path("data")
PROMPT = "you> "
COMMANDS = "Commands: /sources (sources of the last answer), /reload, /quit"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clone", description="Chat with your clone.")
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="folder with personality.md and notes/ (default: ./data)",
    )
    return parser


def load_data(data_dir: Path) -> tuple[Memory, Personality]:
    """Load memory and personality; raises MissingDataError, OSError or UnicodeDecodeError."""
    return Memory.load(data_dir), load_personality(data_dir)


def describe_load_error(error: Exception, data_dir: Path) -> str:
    if isinstance(error, MissingDataError):
        return str(error)
    return f"Cannot read the data folder {data_dir}: {error}"


def run_chat(
    data_dir: Path,
    model: ModelClient,
    *,
    max_turns: int,
    read: Callable[[str], str] = input,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run the chat loop and return the process exit code."""
    out = out or sys.stdout
    err = err or sys.stderr

    def say(text: str = "") -> None:
        print(text, file=out)

    try:
        memory, personality = load_data(data_dir)
    except (MissingDataError, OSError, UnicodeDecodeError) as error:
        print(describe_load_error(error, data_dir), file=err)
        return 1

    brain = Brain(memory, personality, model, max_turns=max_turns)
    say(f"Clone ready: {len(memory.chunks)} memory chunks loaded, model {model.model}.")
    if personality.notice:
        say(personality.notice)
    say(COMMANDS)

    while True:
        try:
            line = read(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            say()
            return 0
        if not line:
            continue

        if line.startswith("/"):
            command = line.split()[0].lower()
            if command == "/quit":
                return 0
            if command == "/sources":
                _show_sources(brain, say)
            elif command == "/reload":
                _reload(brain, data_dir, say, err)
            else:
                say(f"Unknown command {command}. {COMMANDS}")
            continue

        try:
            answer = brain.ask(line)
        except ModelError as error:
            print(f"Error: {error}", file=err)
            continue
        say()
        say(answer)
        say()


def _show_sources(brain: Brain, say: Callable[[str], None]) -> None:
    sources = brain.last_sources
    if not sources:
        say("No sources for the last answer.")
    for number, chunk in enumerate(sources, 1):
        say(f"[{number}] {chunk.label}")


def _reload(brain: Brain, data_dir: Path, say: Callable[[str], None], err: TextIO) -> None:
    try:
        memory, personality = load_data(data_dir)
    except (MissingDataError, OSError, UnicodeDecodeError) as error:
        print(describe_load_error(error, data_dir), file=err)
        say("Keeping the previous memory and personality.")
        return
    brain.memory = memory
    brain.personality = personality
    say(f"Reloaded: {len(memory.chunks)} memory chunks.")
    if personality.notice:
        say(personality.notice)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        max_turns = max_turns_from_env()
        model = AnthropicClient()
    except (ValueError, ModelError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return run_chat(args.data, model, max_turns=max_turns)
