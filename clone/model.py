"""Model client: thin wrapper around the language model API.

The only module allowed to import the model SDK. Everything else talks to a
`ModelClient`, so the model can be swapped or mocked without touching the brain.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"
MODEL_ENV_VAR = "CLONE_MODEL"
EFFORT_ENV_VAR = "CLONE_EFFORT"
DEFAULT_EFFORT = "low"  # chat should feel responsive; raise it for harder questions
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Room for thinking plus the answer. The API documentation advises against going lower
# without a hard reason: a low cap can truncate the answer, and effort already limits spend.
MAX_TOKENS = 16000


def model_name() -> str:
    """The model to use: `CLONE_MODEL` if set and not blank, else the default."""
    return os.environ.get(MODEL_ENV_VAR, "").strip() or DEFAULT_MODEL


def effort_name() -> str:
    """The effort level: `CLONE_EFFORT` if set and not blank, else the default.

    Raises ModelError if the value is not a known level.
    """
    value = os.environ.get(EFFORT_ENV_VAR, "").strip() or DEFAULT_EFFORT
    return _check_effort(value, EFFORT_ENV_VAR)


def _check_effort(effort: str, name: str = "effort") -> str:
    if effort not in EFFORTS:
        raise ModelError(f"Unknown {name} {effort!r}: use one of {', '.join(EFFORTS)}.")
    return effort


@dataclass(frozen=True)
class Message:
    """One turn of the conversation."""

    role: Literal["user", "assistant"]
    content: str


class ModelError(Exception):
    """The model could not answer; the message is meant to be shown to the user."""


class ModelClient(Protocol):
    """Anything that can answer a conversation given a system prompt."""

    model: str

    def complete(self, system: str, messages: Sequence[Message]) -> str:
        """Return the model's answer, or raise ModelError."""
        ...


class AnthropicClient:
    """`ModelClient` backed by the Anthropic API.

    Credentials come from the environment (`ANTHROPIC_API_KEY`) and are read by the SDK;
    this module never handles or logs them. The SDK client is created on first use, and can
    be injected for tests.
    """

    def __init__(
        self, model: str | None = None, *, effort: str | None = None, client: Any = None
    ) -> None:
        self.model = model or model_name()
        self.effort = _check_effort(effort) if effort else effort_name()
        self._client = client

    def complete(self, system: str, messages: Sequence[Message]) -> str:
        try:
            if self._client is None:
                self._client = anthropic.Anthropic()
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                output_config={"effort": self.effort},
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except anthropic.AnthropicError as error:
            raise ModelError(_describe(error)) from error
        except TypeError as error:
            # The SDK raises a bare TypeError, before any request, when no credentials exist.
            if "authentication method" not in str(error):
                raise
            raise ModelError(
                "No API key found. Set ANTHROPIC_API_KEY (for example in the .env file)."
            ) from error

        if response.stop_reason == "refusal":
            raise ModelError("The model declined to answer this request.")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise ModelError("The model returned an empty answer.")
        return text


def _describe(error: anthropic.AnthropicError) -> str:
    if isinstance(error, anthropic.AuthenticationError):
        return "The API rejected the credentials. Check ANTHROPIC_API_KEY."
    if isinstance(error, anthropic.APIConnectionError):
        return "Could not reach the model API. Check your network connection."
    if isinstance(error, anthropic.RateLimitError):
        return "The model API is rate limiting requests. Try again in a moment."
    if isinstance(error, anthropic.APIStatusError):
        return f"The model API returned an error ({error.status_code}): {error.message}"
    return f"Model API error: {error}"
