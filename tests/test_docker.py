"""Guard the container setup: what enters an image, what is writable, what is reachable.

The checks read the configuration files as text (no YAML dependency). `compose.yaml`,
`.dockerignore` and `.gitignore` are copied into the dev image, so these tests run in Docker too.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def active_text(name: str) -> str:
    """The content of a config file without comments and blank lines."""
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return "\n".join(s for line in lines if (s := line.split("#", 1)[0].rstrip()))


def has_key(text: str, key: str) -> bool:
    return re.search(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE) is not None


def publishes_a_port(text: str) -> bool:
    """True if a service publishes a port or shares the host network."""
    return has_key(text, "ports") or re.search(r"network_mode\s*:\s*[\"']?host", text) is not None


def is_hardened(text: str) -> bool:
    return (
        re.search(r"^\s*read_only\s*:\s*true\s*$", text, re.MULTILINE) is not None
        and re.search(r"cap_drop\s*:\s*\n\s*-\s*ALL\b", text) is not None
        and re.search(r"-\s*[\"']?no-new-privileges(:|=)true", text) is not None
    )


# --- what can enter an image or Git ----------------------------------------------------------


def test_dockerignore_excludes_data_state_and_secrets() -> None:
    patterns = set(active_text(".dockerignore").splitlines())

    for required in ("data/", "state/", ".env", ".git/", ".venv/", "**/__pycache__/", "**/*.pyc"):
        assert required in patterns


def test_gitignore_keeps_private_folders_and_secrets_out_of_git() -> None:
    patterns = set(active_text(".gitignore").splitlines())

    assert {"data/", "state/", ".env"} <= patterns


# --- data/ is the owner's, state/ is the clone's ---------------------------------------------


def test_data_is_mounted_read_only_and_state_is_writable() -> None:
    compose = active_text("compose.yaml")

    assert re.search(r"^\s*-\s*\./data:/app/data:ro\s*$", compose, re.MULTILINE)
    assert re.search(r"^\s*-\s*\./state:/app/state\s*$", compose, re.MULTILINE)


# --- nothing is reachable from outside -------------------------------------------------------


def test_compose_publishes_no_port() -> None:
    assert not publishes_a_port(active_text("compose.yaml"))


def test_the_port_check_detects_published_ports_and_host_networking() -> None:
    assert publishes_a_port('services:\n  clone:\n    ports:\n      - "8080:80"')
    assert publishes_a_port("services:\n  clone:\n    network_mode: host")
    assert not publishes_a_port("services:\n  clone:\n    expose:\n      - 8080")


# --- hardening (ADR-007) ---------------------------------------------------------------------


def test_clone_service_is_hardened() -> None:
    assert is_hardened(active_text("compose.yaml"))


def test_the_hardening_check_detects_each_missing_protection() -> None:
    full = "read_only: true\ncap_drop:\n  - ALL\nsecurity_opt:\n  - no-new-privileges:true\n"
    assert is_hardened(full)
    assert not is_hardened(full.replace("read_only: true", "read_only: false"))
    assert not is_hardened(full.replace("  - ALL", "  - NET_RAW"))
    assert not is_hardened(full.replace("no-new-privileges:true", "seccomp=unconfined"))
