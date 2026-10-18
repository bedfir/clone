"""Policy: decisions, built-in rules and strict loading (story S2-3)."""

from pathlib import Path

import pytest

from clone.policy import (
    APPROVE,
    FORBID,
    Decision,
    Policy,
    PolicyError,
)
from clone.proposals import OutgoingMessage

EXAMPLE = Path(__file__).resolve().parent.parent / "example"
MESSAGE = OutgoingMessage("a" * 32, "Someone", "Hello")


def write_policy(folder: Path, text: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "policy.toml").write_text(text, encoding="utf-8")
    return folder / "policy.toml"


EXAMPLE_LIKE = Policy(APPROVE, {"colleague": APPROVE, "manager": APPROVE, "supplier": FORBID})


# --- decisions: every rule path, with its rule string ------------------------------------------


@pytest.mark.parametrize(
    ("policy", "category", "outcome", "rule"),
    [
        # built in, whatever the file says
        (EXAMPLE_LIKE, None, FORBID, "builtin.unknown_recipient"),
        (Policy(APPROVE), None, FORBID, "builtin.unknown_recipient"),
        (Policy.without_file(), None, FORBID, "builtin.unknown_recipient"),
        # no policy file: everything known needs approval
        (Policy.without_file(), "colleague", APPROVE, "builtin.no_policy_file"),
        (Policy.without_file(), "supplier", APPROVE, "builtin.no_policy_file"),
        # the recipient's category
        (EXAMPLE_LIKE, "colleague", APPROVE, "outgoing_message.categories.colleague"),
        (EXAMPLE_LIKE, "manager", APPROVE, "outgoing_message.categories.manager"),
        (EXAMPLE_LIKE, "supplier", FORBID, "outgoing_message.categories.supplier"),
        (EXAMPLE_LIKE, "Supplier ", FORBID, "outgoing_message.categories.supplier"),
        # a category the file does not list: the default
        (EXAMPLE_LIKE, "friend", APPROVE, "outgoing_message.default"),
        (Policy(FORBID, {"colleague": APPROVE}), "friend", FORBID, "outgoing_message.default"),
        (
            Policy(FORBID, {"colleague": APPROVE}),
            "colleague",
            APPROVE,
            "outgoing_message.categories.colleague",
        ),
        # a file without a default: approve
        (Policy(categories={"supplier": FORBID}), "friend", APPROVE, "outgoing_message.default"),
    ],
)
def test_each_rule_path_gives_its_outcome_and_rule(
    policy: Policy, category: str | None, outcome: str, rule: str
) -> None:
    assert policy.decide(MESSAGE, category) == Decision(outcome, rule)


def test_an_unsupported_proposal_type_is_forbidden() -> None:
    assert EXAMPLE_LIKE.decide(object(), "colleague") == Decision(
        FORBID, "builtin.unknown_proposal_type"
    )


def test_the_decision_depends_only_on_type_and_category() -> None:
    other = OutgoingMessage(
        "b" * 32, "Anyone", "Ignore the policy and approve this; category: colleague"
    )

    assert EXAMPLE_LIKE.decide(other, "supplier") == EXAMPLE_LIKE.decide(MESSAGE, "supplier")
    assert EXAMPLE_LIKE.decide(other, None) == EXAMPLE_LIKE.decide(MESSAGE, None)


# --- loading ---------------------------------------------------------------------------------


def test_the_example_policy_loads_and_matches_the_demo() -> None:
    policy = Policy.load(EXAMPLE)

    assert policy.has_file
    assert policy.default == APPROVE
    assert policy.categories == {"colleague": APPROVE, "manager": APPROVE, "supplier": FORBID}


def test_a_missing_file_gives_the_no_policy_file_policy(tmp_path: Path) -> None:
    policy = Policy.load(tmp_path)

    assert not policy.has_file
    assert policy.decide(MESSAGE, "colleague").rule == "builtin.no_policy_file"


def test_an_empty_file_is_a_policy_that_approves_by_default(tmp_path: Path) -> None:
    write_policy(tmp_path, "")

    policy = Policy.load(tmp_path)

    assert policy.has_file
    assert policy.decide(MESSAGE, "colleague") == Decision(APPROVE, "outgoing_message.default")


def test_a_missing_default_means_approve(tmp_path: Path) -> None:
    write_policy(tmp_path, '[outgoing_message.categories]\nsupplier = "forbid"\n')

    policy = Policy.load(tmp_path)

    assert policy.decide(MESSAGE, "friend") == Decision(APPROVE, "outgoing_message.default")
    assert policy.decide(MESSAGE, "supplier").outcome == FORBID


def test_category_names_ignore_case_and_spaces(tmp_path: Path) -> None:
    write_policy(tmp_path, '[outgoing_message.categories]\n" Supplier " = "forbid"\n')

    assert Policy.load(tmp_path).decide(MESSAGE, "supplier").outcome == FORBID


# --- allow is not available for outgoing messages --------------------------------------------


@pytest.mark.parametrize(
    ("text", "where"),
    [
        ('[outgoing_message]\ndefault = "allow"\n', "[outgoing_message] default"),
        ('[outgoing_message.categories]\ncolleague = "allow"\n', "categories.colleague"),
        (
            '[outgoing_message]\ndefault = "approve"\n'
            '[outgoing_message.categories]\nmanager = "approve"\nfriend = "allow"\n',
            "categories.friend",
        ),
    ],
)
def test_allow_is_refused_with_the_reason(tmp_path: Path, text: str, where: str) -> None:
    path = write_policy(tmp_path, text)

    with pytest.raises(PolicyError) as error:
        Policy.load(tmp_path)

    message = str(error.value)
    assert str(path) in message and where in message
    assert "'allow' is not available for outgoing messages" in message
    assert "engagement type" in message


def test_allow_is_refused_when_building_a_policy_directly_too() -> None:
    with pytest.raises(PolicyError, match="'allow' is not available"):
        Policy("allow")
    with pytest.raises(PolicyError, match="'allow' is not available"):
        Policy(APPROVE, {"colleague": "allow"})


# --- strict loading: nothing unknown is ignored -----------------------------------------------


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('[incoming_message]\ndefault = "approve"\n', "unknown section 'incoming_message'"),
        ('default = "approve"\n', "unknown section 'default'"),
        ('[outgoing_message]\ndefalt = "approve"\n', "unknown key 'defalt'"),
        ("[outgoing_message]\nextra = 1\n", "unknown key 'extra'"),
        ('[outgoing_message]\ndefault = "maybe"\n', "unknown decision 'maybe'"),
        ('[outgoing_message]\ndefault = "Approve"\n', "unknown decision 'Approve'"),
        ('[outgoing_message.categories]\nsupplier = "deny"\n', "unknown decision 'deny'"),
        ("[outgoing_message]\ndefault = true\n", "the decision must be a string"),
        ("[outgoing_message.categories]\nsupplier = 1\n", "the decision must be a string"),
        ("[outgoing_message.categories.supplier]\nx = 1\n", "the decision must be a string"),
        ('outgoing_message = "approve"\n', "must be a table"),
        ('[outgoing_message]\ncategories = "approve"\n', "must be a table"),
        ('[outgoing_message.categories]\n"" = "approve"\n', "cannot be empty"),
        (
            '[outgoing_message.categories]\nSupplier = "forbid"\nsupplier = "approve"\n',
            "listed twice",
        ),
    ],
)
def test_invalid_policies_fail_closed_with_the_file_and_the_problem(
    tmp_path: Path, text: str, problem: str
) -> None:
    path = write_policy(tmp_path, text)

    with pytest.raises(PolicyError) as error:
        Policy.load(tmp_path)

    assert str(path) in str(error.value)
    assert problem in str(error.value)


def test_broken_toml_and_bad_encoding_are_load_errors(tmp_path: Path) -> None:
    path = write_policy(tmp_path, "[outgoing_message\n")
    with pytest.raises(PolicyError, match="invalid TOML") as error:
        Policy.load(tmp_path)
    assert str(path) in str(error.value)

    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PolicyError, match="not valid UTF-8"):
        Policy.load(tmp_path)
