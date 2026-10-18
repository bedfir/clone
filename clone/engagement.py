"""Engagement: the gate between a proposal and an action.

The brain proposes, the policy decides (ADR-006). `Engagement.submit` is the only way in: it
finds the recipient's category in the contacts, asks the policy, writes the decision to the
action log and holds or refuses the proposal. `Engagement.release` is the only code that
writes to `state/outbox/`, and only for a proposal the policy allowed to wait for approval,
once, with the owner's explicit approval.

Nothing is sent anywhere yet: the outbox is a simulated channel.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from clone.actionlog import ActionLog, ActionLogError
from clone.contacts import Contacts
from clone.policy import APPROVE, Decision, Policy
from clone.proposals import OutgoingMessage

OUTBOX_DIR = "outbox"


class EngagementError(Exception):
    """A proposal cannot go through; the message is meant to be shown to the owner."""


class Engagement:
    """Submits proposals to the policy and releases the approved ones to the outbox."""

    def __init__(
        self, policy: Policy, contacts: Contacts, log: ActionLog, state_dir: str | Path
    ) -> None:
        self._policy = policy
        self._contacts = contacts
        self._log = log
        self._outbox = Path(state_dir) / OUTBOX_DIR
        self._pending: dict[str, OutgoingMessage] = {}  # in memory; persistence is S2-4's call
        self._refused: set[str] = set()
        self._released: set[str] = set()

    def pending(self) -> list[OutgoingMessage]:
        """Proposals waiting for the owner's approval, oldest first."""
        return list(self._pending.values())

    def submit(self, proposal: OutgoingMessage) -> Decision:
        """Decide `proposal`, log the decision, then hold it (approve) or refuse it (anything else).

        The category comes from the contacts, never from the proposal. A decision that cannot
        be logged is not taken: ActionLogError is raised and nothing is recorded.
        """
        if proposal.id in self._pending or proposal.id in self._refused | self._released:
            raise EngagementError(f"Proposal {proposal.id} was already submitted.")
        category = self._contacts.category_of(proposal.recipient)
        decision = self._policy.decide(proposal, category)
        self._log.append(
            "policy.decided",
            {
                "proposal_id": proposal.id,
                "type": proposal.TYPE,
                "recipient": proposal.recipient,
                "category": category,
                "outcome": decision.outcome,
                "rule": decision.rule,
                "text_sha256": hashlib.sha256(proposal.text.encode("utf-8")).hexdigest(),
            },
        )
        if decision.outcome == APPROVE:
            self._pending[proposal.id] = proposal
        else:  # forbid, and anything unexpected: fail closed
            self._refused.add(proposal.id)
        return decision

    def release(self, proposal_id: str, *, owner_approved: bool = False) -> Path:
        """Write a pending proposal to the simulated outbox, once, and return the file.

        Refuses without `owner_approved=True` (only the CLI passes it, for the owner), and for
        an unknown, refused or already released proposal. The release is logged first: no log
        entry, no action.
        """
        if not owner_approved:
            raise EngagementError("A message is only released with the owner's approval.")
        if proposal_id in self._released:
            raise EngagementError(f"Proposal {proposal_id} was already released.")
        if proposal_id in self._refused:
            raise EngagementError(f"Proposal {proposal_id} was refused by the policy.")
        proposal = self._pending.get(proposal_id)
        if proposal is None:
            raise EngagementError(f"Unknown proposal {proposal_id}.")

        path = self._outbox / f"{proposal.id}.json"
        self._log.append("proposal.released", {"proposal_id": proposal.id, "file": path.name})
        try:
            self._write_outbox(path, proposal)
        except OSError as error:
            try:  # the release was logged before the write: record that it did not happen
                self._log.append(
                    "proposal.release_failed", {"proposal_id": proposal.id, "file": path.name}
                )
            except ActionLogError:
                pass
            raise EngagementError(
                f"Cannot write {path}: {error.strerror}. The proposal stays pending."
            ) from error
        del self._pending[proposal.id]
        self._released.add(proposal.id)
        return path

    def _write_outbox(self, path: Path, proposal: OutgoingMessage) -> None:
        self._outbox.mkdir(exist_ok=True)
        content = {
            "simulated": True,  # nothing is really sent
            "id": proposal.id,
            "recipient": proposal.recipient,
            "text": proposal.text,
        }
        with open(path, "x", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
