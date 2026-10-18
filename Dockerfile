# syntax=docker/dockerfile:1

# Shared base: the package and its runtime dependencies, run as a non-root user.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 1000 clone
WORKDIR /app
RUN chown clone:clone /app

COPY --chown=clone:clone pyproject.toml README.md LICENSE ./
COPY --chown=clone:clone clone ./clone

CMD ["clone"]

# Development image: adds pytest, ruff, the tests and the fictional example persona.
FROM base AS dev
RUN pip install ".[dev]"
COPY --chown=clone:clone tests ./tests
COPY --chown=clone:clone example ./example
# Configuration files checked by tests/test_docker.py (no secrets in them).
COPY --chown=clone:clone compose.yaml .dockerignore .gitignore ./
USER clone

# Runtime image (default target, keep it last): runtime dependencies only.
FROM base AS runtime
RUN pip install .
USER clone
