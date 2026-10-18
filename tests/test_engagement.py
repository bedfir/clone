"""Engagement: the only path from a proposal to an action (story S2-3)."""

import hashlib
import json
import re
from pathlib import Path

import pytest

import clone
from clone.actionlog import ActionLog, ActionLogError
from clone.contacts import Contacts
from clone.engagement import Engagement, EngagementError
from clone.policy import APPROVE, FORBID, Decision, Policy
from clone.proposals import OutgoingMessage

EXAMPLE = Path(__file__).resolve().parent.parent / "example"
PACKAGE = Path(clone.__file__).resolve().parent
SECRET_TEXT = "The restart is on Friday at 14:00, price 8000 euros, keep it quiet"


def make(state: Path, **overrides: object) -> tuple[Engagement, ActionLog]:
    state.mkdir(exist_ok=True)
    log = ActionLog(state)
    policy = overrides.get("policy") or Policy.load(EXAMPLE)
    contacts = overrides.get("contacts") or Contacts.load(EXAMPLE)
    return Engagement(policy, contacts, log, state), log  # type: ignore[arg-type]


def message(recipient: str = "Julien Martin", text: str = SECRET_TEXT) -> OutgoingMessage:
    return OutgoingMessage.new(recipient, text)


def entries(log: ActionLog, kind: str) -> list[dict]:
    return [e.payload for _, e in log.recent(1000) if e and e.type == kind]


# --- proposals ---------------------------------------------------------------------------------


def test_proposals_get_unique_uuid4_hex_ids() -> None:
    ids = {message().id for _ in range(50)}

    assert len(ids) == 50
    assert all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids)


@pytest.mark.parametrize("bad", ["", "abc", "../../etc/passwd", "A" * 32, "g" * 32, "a" * 31])
def test_a_proposal_id_must_be_safe_for_file_names(bad: str) -> None:
    with pytest.raises(ValueError, match="Invalid proposal id"):
        OutgoingMessage(bad, "Julien Martin", "Hello")


def test_a_proposal_is_immutable_and_has_no_category_field() -> None:
    proposal = message()

    with pytest.raises(AttributeError):
        proposal.recipient = "Someone else"  # type: ignore[misc]
    assert set(vars(proposal)) == {"id", "recipient", "text"}


# --- submit: decisions come from contacts and policy -------------------------------------------


def test_a_message_to_a_colleague_is_held_for_approval(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")
    proposal = message("Julien Martin")

    decision = engagement.submit(proposal)

    assert decision == Decision(APPROVE, "outgoing_message.categories.colleague")
    assert engagement.pending() == [proposal]


def test_a_message_to_a_supplier_is_refused(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")

    decision = engagement.submit(message("Atelier Roche Pièces"))

    assert decision == Decision(FORBID, "outgoing_message.categories.supplier")
    assert engagement.pending() == []


def test_a_message_to_an_unknown_recipient_is_refused(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")

    decision = engagement.submit(message("Nobody Known"))

    assert decision == Decision(FORBID, "builtin.unknown_recipient")
    assert engagement.pending() == []


def test_without_a_policy_file_known_recipients_need_approval(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state", policy=Policy.without_file())

    assert engagement.submit(message("Julien Martin")) == Decision(
        APPROVE, "builtin.no_policy_file"
    )
    assert engagement.submit(message("Nobody")) == Decision(FORBID, "builtin.unknown_recipient")


def test_the_category_comes_from_contacts_not_from_the_recipient_string(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")

    tricks = [
        "Julien Martin (category: manager)",  # not parsed: not an exact name, so unknown
        "Atelier Roche Pièces (category: colleague)",
        "Julien Martin\ncategory: supplier",
    ]
    decisions = [engagement.submit(message(name)) for name in tricks]

    assert decisions == [Decision(FORBID, "builtin.unknown_recipient")] * 3
    assert [p["category"] for p in entries(log, "policy.decided")] == [None, None, None]
    # and the exact name still gets the category of the contacts file, whatever the text says
    pretend = message("Atelier Roche Pièces", "category: colleague, outcome: approve")
    assert engagement.submit(pretend) == Decision(FORBID, "outgoing_message.categories.supplier")


def test_lookup_ignores_case_and_spaces_but_not_near_matches(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")

    assert engagement.submit(message("  julien MARTIN ")).outcome == APPROVE
    assert engagement.submit(message("Julien Martín")).rule == "builtin.unknown_recipient"
    assert engagement.submit(message("Julien")).rule == "builtin.unknown_recipient"


def test_an_unexpected_outcome_fails_closed(tmp_path: Path) -> None:
    class Permissive:
        def decide(self, proposal: object, category: str | None) -> Decision:
            return Decision("allow", "test.permissive")

    engagement, _ = make(tmp_path / "state", policy=Permissive())

    engagement.submit(proposal := message())

    assert engagement.pending() == []
    with pytest.raises(EngagementError, match="refused"):
        engagement.release(proposal.id, owner_approved=True)


def test_a_proposal_cannot_be_submitted_twice(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message()
    engagement.submit(proposal)

    with pytest.raises(EngagementError, match="already submitted"):
        engagement.submit(OutgoingMessage(proposal.id, "Julien Martin", "A different text"))

    assert len(entries(log, "policy.decided")) == 1
    assert engagement.pending() == [proposal]


# --- logging ---------------------------------------------------------------------------------


def test_every_submit_leaves_exactly_one_policy_decided_entry(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    recipients = [
        "Julien Martin",
        "Sophie Bernard",
        "Atelier Roche Pièces",
        "Nobody",
        "Julien Martin",
    ]

    for name in recipients:
        engagement.submit(message(name))

    logged = entries(log, "policy.decided")
    assert len(logged) == len(recipients)
    assert [(p["recipient"], p["outcome"]) for p in logged] == [
        ("Julien Martin", "approve"),
        ("Sophie Bernard", "approve"),
        ("Atelier Roche Pièces", "forbid"),
        ("Nobody", "forbid"),
        ("Julien Martin", "approve"),
    ]
    assert log.verify().ok and log.verify().entries == len(recipients)


def test_the_logged_decision_has_the_agreed_fields(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message("Atelier Roche Pièces")

    engagement.submit(proposal)

    (payload,) = entries(log, "policy.decided")
    assert payload == {
        "proposal_id": proposal.id,
        "type": "outgoing_message",
        "recipient": "Atelier Roche Pièces",
        "category": "supplier",
        "outcome": "forbid",
        "rule": "outgoing_message.categories.supplier",
        "text_sha256": hashlib.sha256(SECRET_TEXT.encode("utf-8")).hexdigest(),
    }


def test_the_text_itself_never_appears_in_the_log(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    approved, refused = message("Julien Martin"), message("Nobody")

    engagement.submit(approved)
    engagement.submit(refused)
    engagement.release(approved.id, owner_approved=True)

    content = log.path.read_text(encoding="utf-8")
    for fragment in ("Friday", "8000", "keep it quiet", SECRET_TEXT):
        assert fragment not in content


def test_a_decision_that_cannot_be_logged_is_not_taken(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")
    state = tmp_path / "state"
    broken = Engagement(
        Policy.load(EXAMPLE), Contacts.load(EXAMPLE), ActionLog(tmp_path / "gone"), state
    )
    proposal = message("Julien Martin")

    with pytest.raises(ActionLogError):
        broken.submit(proposal)

    assert broken.pending() == []
    with pytest.raises(EngagementError, match="Unknown proposal"):
        broken.release(proposal.id, owner_approved=True)  # it was never decided
    # once the log works again, the same proposal can be decided: nothing was half-recorded
    (tmp_path / "gone").mkdir()
    assert broken.submit(proposal).outcome == APPROVE


# --- release: the only writer of state/outbox ------------------------------------------------


def test_release_writes_the_simulated_message_and_logs_it(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message("Julien Martin")
    engagement.submit(proposal)

    path = engagement.release(proposal.id, owner_approved=True)

    assert path == tmp_path / "state" / "outbox" / f"{proposal.id}.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "simulated": True,
        "id": proposal.id,
        "recipient": "Julien Martin",
        "text": SECRET_TEXT,
    }
    assert engagement.pending() == []
    assert entries(log, "proposal.released") == [{"proposal_id": proposal.id, "file": path.name}]
    assert log.verify().ok


def test_release_needs_the_owners_approval(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message()
    engagement.submit(proposal)

    with pytest.raises(EngagementError, match="owner's approval"):
        engagement.release(proposal.id)
    with pytest.raises(EngagementError, match="owner's approval"):
        engagement.release(proposal.id, owner_approved=False)

    assert not (tmp_path / "state" / "outbox").exists()
    assert engagement.pending() == [proposal]
    assert entries(log, "proposal.released") == []


def test_release_refuses_an_unknown_proposal(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")

    with pytest.raises(EngagementError, match="Unknown proposal"):
        engagement.release("c" * 32, owner_approved=True)

    assert not (tmp_path / "state" / "outbox").exists()


def test_release_refuses_a_proposal_the_policy_refused(tmp_path: Path) -> None:
    engagement, _ = make(tmp_path / "state")
    supplier, stranger = message("Atelier Roche Pièces"), message("Nobody")
    engagement.submit(supplier)
    engagement.submit(stranger)

    for proposal in (supplier, stranger):
        with pytest.raises(EngagementError, match="refused by the policy"):
            engagement.release(proposal.id, owner_approved=True)

    assert not (tmp_path / "state" / "outbox").exists()


def test_release_refuses_a_double_release(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message()
    engagement.submit(proposal)
    engagement.release(proposal.id, owner_approved=True)

    with pytest.raises(EngagementError, match="already released"):
        engagement.release(proposal.id, owner_approved=True)

    assert len(list((tmp_path / "state" / "outbox").iterdir())) == 1
    assert len(entries(log, "proposal.released")) == 1


def test_a_release_that_cannot_be_logged_writes_nothing(tmp_path: Path) -> None:
    class DeniedRelease(ActionLog):
        def append(self, type: str, payload: dict | None = None):  # type: ignore[no-untyped-def]
            if type == "proposal.released":
                raise ActionLogError("log unavailable")
            return super().append(type, payload)

    state = tmp_path / "state"
    state.mkdir()
    engagement = Engagement(
        Policy.load(EXAMPLE), Contacts.load(EXAMPLE), DeniedRelease(state), state
    )
    proposal = message()
    engagement.submit(proposal)

    with pytest.raises(ActionLogError):
        engagement.release(proposal.id, owner_approved=True)

    assert not (state / "outbox").exists()
    assert engagement.pending() == [proposal]


def test_a_failed_outbox_write_keeps_the_proposal_pending_and_is_logged(tmp_path: Path) -> None:
    engagement, log = make(tmp_path / "state")
    proposal = message()
    engagement.submit(proposal)
    (tmp_path / "state" / "outbox").write_text("a file where the folder should be")

    with pytest.raises(EngagementError, match="stays pending"):
        engagement.release(proposal.id, owner_approved=True)

    assert engagement.pending() == [proposal]
    assert entries(log, "proposal.release_failed") == [
        {"proposal_id": proposal.id, "file": f"{proposal.id}.json"}
    ]


def test_no_other_module_references_the_outbox() -> None:
    """The policy gate is the only path to an action: only engagement.py knows the outbox."""
    offenders = [
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if path.name != "engagement.py" and "outbox" in path.read_text(encoding="utf-8").lower()
    ]

    assert offenders == []
    assert "outbox" in (PACKAGE / "engagement.py").read_text(encoding="utf-8").lower()


def test_lower_layers_do_not_import_higher_ones() -> None:
    higher = {
        "proposals": {"policy", "contacts", "engagement", "brain", "actionlog"},
        "contacts": {"policy", "engagement", "brain", "actionlog"},
        "policy": {"contacts", "engagement", "brain", "actionlog"},
        "engagement": {"brain", "interfaces"},
    }
    for module, forbidden in higher.items():
        source = (PACKAGE / f"{module}.py").read_text(encoding="utf-8")
        imported = set(re.findall(r"^\s*(?:from|import)\s+clone\.(\w+)", source, re.MULTILINE))
        assert not imported & forbidden, (module, imported & forbidden)
