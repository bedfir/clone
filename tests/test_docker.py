"""Guard the Docker build context against personal data and secrets (story S1-1b)."""

from pathlib import Path

import pytest

DOCKERIGNORE = Path(__file__).resolve().parent.parent / ".dockerignore"


@pytest.mark.skipif(not DOCKERIGNORE.is_file(), reason="absent inside the image")
def test_dockerignore_excludes_data_and_secrets() -> None:
    patterns = {line.strip() for line in DOCKERIGNORE.read_text().splitlines()}
    for required in ("data/", ".env", ".git/", ".venv/", "__pycache__/"):
        assert required in patterns
