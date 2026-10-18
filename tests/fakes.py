"""Test doubles shared by several test modules."""

from collections.abc import Sequence

from clone.model import Message


class FakeModel:
    """A `ModelClient` that records what it receives and answers from a script."""

    model = "fake-model"

    def __init__(self, *answers: str, error: Exception | None = None) -> None:
        self.answers = list(answers) or ["fake answer"]
        self.error = error
        self.calls: list[tuple[str, list[Message]]] = []

    def complete(self, system: str, messages: Sequence[Message]) -> str:
        self.calls.append((system, list(messages)))
        if self.error:
            raise self.error
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
