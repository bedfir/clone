"""Policy: the owner's rules for what the clone may do, and the pure decision function.

`data/policy.toml`:

    [outgoing_message]
    default = "approve"

    [outgoing_message.categories]
    colleague = "approve"
    supplier = "forbid"

Loading is strict and fails closed: an unknown section, key or decision is an error naming it,
never silently ignored. `allow` is refused for outgoing messages: nothing leaves without the
owner's approval until a dedicated engagement type exists (ADR-006).

`Policy.decide` is pure and looks only at facts the code controls: the type of the proposal
and the category found in the contacts. It never reads anything the model says about a
proposal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from clone.proposals import OutgoingMessage
from clone.tomlfile import read_toml

POLICY_FILE = "policy.toml"

ALLOW = "allow"
APPROVE = "approve"
FORBID = "forbid"
DECISIONS = (ALLOW, APPROVE, FORBID)
OUTGOING_DECISIONS = (APPROVE, FORBID)  # `allow` is not available for messages yet

_SECTION = "outgoing_message"
_SECTION_KEYS = {"default", "categories"}

RULE_UNKNOWN_RECIPIENT = "builtin.unknown_recipient"
RULE_UNKNOWN_TYPE = "builtin.unknown_proposal_type"
RULE_NO_POLICY_FILE = "builtin.no_policy_file"
RULE_DEFAULT = f"{_SECTION}.default"
RULE_CATEGORY_PREFIX = f"{_SECTION}.categories."


class PolicyError(Exception):
    """The policy is invalid; the message names the file and the problem."""


@dataclass(frozen=True)
class Decision:
    """What the policy decided, and the stable name of the rule that decided it."""

    outcome: str  # "approve" or "forbid" for outgoing messages
    rule: str


def _normalize(category: str) -> str:
    return category.strip().casefold()


def _check_outgoing(value: object, where: str) -> str:
    """A valid decision for an outgoing message; raises PolicyError naming `where`."""
    if not isinstance(value, str):
        raise PolicyError(f"{where}: the decision must be a string, not {value!r}.")
    if value == ALLOW:
        raise PolicyError(
            f"{where}: 'allow' is not available for outgoing messages. No message leaves "
            "without your approval until the engagement type exists; use 'approve' (you "
            "decide each message) or 'forbid'."
        )
    if value not in OUTGOING_DECISIONS:
        raise PolicyError(
            f"{where}: unknown decision {value!r}; use one of {', '.join(OUTGOING_DECISIONS)}."
        )
    return value


class Policy:
    """Decisions for outgoing messages, by recipient category."""

    def __init__(
        self,
        default: str = APPROVE,
        categories: Mapping[str, str] | None = None,
        *,
        has_file: bool = True,
    ) -> None:
        self.default = _check_outgoing(default, "default")
        self.categories: dict[str, str] = {}
        for category, decision in (categories or {}).items():
            key = _normalize(category)
            if not key:
                raise PolicyError("categories: a category name cannot be empty.")
            if key in self.categories:
                raise PolicyError(f"categories: {category!r} is listed twice (case is ignored).")
            self.categories[key] = _check_outgoing(decision, f"categories.{category}")
        self.has_file = has_file

    @classmethod
    def without_file(cls) -> Policy:
        """The policy when there is no policy file: everything known needs approval."""
        return cls(has_file=False)

    @classmethod
    def load(cls, data_dir: str | Path) -> Policy:
        """Load `<data_dir>/policy.toml`; a missing file gives `Policy.without_file()`."""
        path = Path(data_dir) / POLICY_FILE
        data = read_toml(path, PolicyError)
        if data is None:
            return cls.without_file()
        for key in data:
            if key != _SECTION:
                raise PolicyError(f"{path}: unknown section {key!r}; only [{_SECTION}] exists.")
        section = data.get(_SECTION, {})
        if not isinstance(section, dict):
            raise PolicyError(f"{path}: [{_SECTION}] must be a table.")
        for key in section:
            if key not in _SECTION_KEYS:
                raise PolicyError(f"{path}: [{_SECTION}] unknown key {key!r}.")
        categories = section.get("categories", {})
        if not isinstance(categories, dict):
            raise PolicyError(f"{path}: [{_SECTION}.categories] must be a table.")

        try:
            return cls(section.get("default", APPROVE), categories)
        except PolicyError as problem:
            raise PolicyError(f"{path}: [{_SECTION}] {problem}") from None

    def decide(self, proposal: object, category: str | None) -> Decision:
        """Decide what happens to `proposal`, whose recipient has `category` (None: unknown).

        Order: unsupported proposal type, unknown recipient (both built in and not
        configurable), no policy file, the recipient's category, the default.
        """
        if not isinstance(proposal, OutgoingMessage):
            return Decision(FORBID, RULE_UNKNOWN_TYPE)
        if category is None:
            return Decision(FORBID, RULE_UNKNOWN_RECIPIENT)
        if not self.has_file:
            return Decision(APPROVE, RULE_NO_POLICY_FILE)
        key = _normalize(category)
        if key in self.categories:
            return Decision(self.categories[key], RULE_CATEGORY_PREFIX + key)
        return Decision(self.default, RULE_DEFAULT)
