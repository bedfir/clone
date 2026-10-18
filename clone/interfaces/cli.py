"""CLI: terminal chat in assistant mode, and the `log` commands for the action log.

A thin adapter: it reads lines, forwards questions to the brain and prints what comes back.
Every failure the user can fix (missing data or state folder, missing API key, network or API
error) is shown as a short message, never as a stack trace.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from clone.actionlog import ActionLog, ActionLogError
from clone.brain import Brain, max_turns_from_env
from clone.contacts import Contacts, ContactsError
from clone.engagement import Engagement
from clone.memory import Memory, MissingDataError
from clone.model import AnthropicClient, ModelClient, ModelError
from clone.personality import Personality, load_personality
from clone.policy import Policy, PolicyError

DEFAULT_DATA_DIR = Path("data")
DEFAULT_STATE_DIR = Path("state")
DEFAULT_LOG_ENTRIES = 20
PROMPT = "you> "
COMMANDS = "Commands: /sources (sources of the last answer), /reload, /quit"


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of at least 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clone", description="Chat with your clone (the default), or inspect its log."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="folder with personality.md and notes/ (default: ./data)",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="folder for the clone's own state, such as the action log (default: ./state)",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")
    log = commands.add_parser(
        "log",
        help="show the action log; `log verify` checks that nobody edited it",
        description="Show the last entries of the action log, or verify its whole chain.",
    )
    log.add_argument("action", nargs="?", choices=["verify"], help="check the whole chain")
    log.add_argument(
        "-n",
        type=_positive_int,
        default=DEFAULT_LOG_ENTRIES,
        metavar="N",
        help=f"number of entries to show (default: {DEFAULT_LOG_ENTRIES})",
    )
    log.add_argument("--state", type=Path, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
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
    state_dir: Path,
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

    try:
        policy, contacts = Policy.load(data_dir), Contacts.load(data_dir)
    except (PolicyError, ContactsError) as error:
        print(error, file=err)
        return 1

    log = ActionLog(state_dir)
    brain = Brain(
        memory,
        personality,
        model,
        max_turns=max_turns,
        log=log,
        engagement=Engagement(policy, contacts, log, state_dir),
    )
    try:
        brain.start_session(len(memory.chunks))
    except ActionLogError as error:
        print(error, file=err)
        return 1
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
    for chunk in sources:
        say(f"[{chunk.id}] {chunk.label}")


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


def run_log(
    state_dir: Path,
    *,
    count: int = DEFAULT_LOG_ENTRIES,
    verify: bool = False,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Show the last `count` log entries, or verify the chain; returns the exit code."""
    out = out or sys.stdout
    err = err or sys.stderr
    log = ActionLog(state_dir)
    try:
        if verify:
            result = log.verify()
        else:
            entries = log.recent(count)
    except ActionLogError as error:
        print(error, file=err)
        return 1

    if verify:
        if result.ok:
            print(f"OK: {result.entries} entries, head {result.head[:12]}", file=out)
            return 0
        print(result.problem, file=err)
        return 1

    if not entries:
        print("No log yet.", file=out)
    for position, entry in entries:
        if entry is None:
            print(f"{position:>5}  (unreadable line; run: clone log verify)", file=out)
            continue
        payload = json.dumps(
            entry.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        print(f"{entry.ts}  {entry.short_id}  {entry.type}  {payload}", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "log":
        return run_log(args.state, count=args.n, verify=args.action == "verify")
    try:
        max_turns = max_turns_from_env()
        model = AnthropicClient()
    except (ValueError, ModelError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return run_chat(args.data, model, max_turns=max_turns, state_dir=args.state)
