# CLAUDE.md

Guidance for Claude Code when working in this repository. Read this file and `docs/ARCHITECTURE.md` before writing any code.

## Project

**Clone** (working name) is an open-source, privacy-first personal agent: a digital twin of its user. A headless engine holds the user's memory and personality; interchangeable interfaces (CLI, web/PWA, messaging, other agents) plug into it.

One brain, two faces:
- **Assistant** (facing the user): full memory access, helps and challenges.
- **Representative** (facing others): public memory only, asks the user to approve anything that commits them. Not built before Phase 3.

## Team roles

- **Product owner**: the user. Final say on scope and on anything touching personal data.
- **Lead**: Claude (chat). Writes stories, acceptance criteria and architecture decisions, reviews pull requests.
- **Developer**: Claude Code (you). Implements stories, writes tests, opens pull requests.

Implement only what the current story asks. If a story is ambiguous or conflicts with the architecture, stop and ask rather than guessing. Propose architecture changes in the pull request description; do not make them silently.

## Non-negotiable rules

1. **No personal data in Git.** User data lives in `data/`, which is gitignored. Tests and examples use only the fictional persona in `example/`.
2. **Secrets come from environment variables** (`ANTHROPIC_API_KEY`, ...). Never hard-code or log them.
3. **The clone never claims to be the human.** System prompts must state it is an AI acting for its user.
4. **Local first.** No network call except to the configured language model API, unless a story explicitly adds one.
5. **The brain stores nothing.** Persistent state goes through the memory layer only.

## Conventions

- Language: English for code, comments, docs, commits and issues.
- Python 3.10+, standard library first; every new dependency must be justified in the PR.
- Package layout and module boundaries: see `docs/ARCHITECTURE.md`.
- Type hints on public functions; small modules with one responsibility.
- Formatting and linting: `ruff format` and `ruff check`.
- Tests: `pytest`. The language model is always mocked in tests; the suite must pass with no API key and no network.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
- One story per branch (`story/<id>-<short-name>`) and per pull request.

## Definition of done

A story is done when:
- every acceptance criterion in `BACKLOG.md` is met;
- tests cover the new behaviour and the whole suite passes offline;
- `ruff` reports no issues;
- the README is updated if usage changed;
- the pull request lists what was built, how to try it, and any open question for the lead.
