"""Model client: configuration, SDK boundary and error handling (story S1-4)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from clone import model
from clone.model import DEFAULT_MODEL, AnthropicClient, Message, ModelError, model_name

PACKAGE = Path(model.__file__).resolve().parent


def sdk_response(*blocks: SimpleNamespace, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


class FakeSdk:
    """Stands in for `anthropic.Anthropic`: records the call, returns or raises."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._response, self._error = response, error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


# --- configuration -------------------------------------------------------------------------


def test_default_model_is_sonnet_5_5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLONE_MODEL", raising=False)

    assert DEFAULT_MODEL == "claude-sonnet-5-5"
    assert model_name() == "claude-sonnet-5-5"


def test_clone_model_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLONE_MODEL", "claude-opus-5-5")

    assert model_name() == "claude-opus-5-5"
    assert AnthropicClient().model == "claude-opus-5-5"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_clone_model_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("CLONE_MODEL", value)

    assert model_name() == DEFAULT_MODEL


def test_an_explicit_model_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLONE_MODEL", "from-env")

    assert AnthropicClient("explicit").model == "explicit"


# --- the SDK boundary ----------------------------------------------------------------------


def test_only_model_py_imports_the_sdk() -> None:
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if path.name != "model.py"
        and any(
            line.split()[:2] in (["import", "anthropic"], ["from", "anthropic"])
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]

    assert offenders == []


# --- completing ----------------------------------------------------------------------------


def test_complete_sends_system_prompt_and_conversation() -> None:
    sdk = FakeSdk(sdk_response(text("Hello!")))
    client = AnthropicClient("some-model", client=sdk)

    answer = client.complete("SYSTEM", [Message("user", "hi"), Message("assistant", "yo")])

    assert answer == "Hello!"
    (call,) = sdk.calls
    assert call["model"] == "some-model"
    assert call["system"] == "SYSTEM"
    assert call["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]
    assert call["max_tokens"] > 0


def test_complete_keeps_only_text_blocks() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="")
    sdk = FakeSdk(sdk_response(thinking, text("One "), text("two")))

    assert AnthropicClient("m", client=sdk).complete("s", [Message("user", "q")]) == "One two"


def test_a_refusal_becomes_a_model_error() -> None:
    sdk = FakeSdk(sdk_response(stop_reason="refusal"))

    with pytest.raises(ModelError, match="declined"):
        AnthropicClient("m", client=sdk).complete("s", [Message("user", "q")])


def test_an_empty_answer_becomes_a_model_error() -> None:
    sdk = FakeSdk(sdk_response(text("  ")))

    with pytest.raises(ModelError, match="empty"):
        AnthropicClient("m", client=sdk).complete("s", [Message("user", "q")])


# --- errors --------------------------------------------------------------------------------


def status_error(cls: type, status: int, message: str) -> Exception:
    response = SimpleNamespace(status_code=status, headers={}, request=None)
    return cls(message, response=response, body=None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(model.anthropic.AuthenticationError, 401, "bad key"), "ANTHROPIC_API_KEY"),
        (status_error(model.anthropic.RateLimitError, 429, "slow down"), "rate limiting"),
        (status_error(model.anthropic.InternalServerError, 500, "boom"), "(500): boom"),
        (model.anthropic.APIConnectionError(request=None), "network"),
    ],
)
def test_sdk_errors_become_readable_model_errors(error: Exception, expected: str) -> None:
    client = AnthropicClient("m", client=FakeSdk(error=error))

    with pytest.raises(ModelError, match=expected.replace("(", r"\(").replace(")", r"\)")):
        client.complete("s", [Message("user", "q")])


def test_missing_credentials_become_a_model_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    error = TypeError("Could not resolve authentication method. Expected one of api_key")
    client = AnthropicClient("m", client=FakeSdk(error=error))

    with pytest.raises(ModelError, match="ANTHROPIC_API_KEY"):
        client.complete("s", [Message("user", "q")])


def test_unrelated_type_errors_are_not_swallowed() -> None:
    client = AnthropicClient("m", client=FakeSdk(error=TypeError("a real bug")))

    with pytest.raises(TypeError, match="real bug"):
        client.complete("s", [Message("user", "q")])
