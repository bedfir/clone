# Backlog

Two-week sprints. End of each sprint: demo, 10-minute retro, backlog reordering.
Stories are written by the lead, implemented by Claude Code, accepted by the product owner.

## Sprint 1: "The clone speaks" (current)

Sprint goal: the smallest useful clone. You ask a question about yourself and the answer rings true.

### S1-1 Project skeleton
As a contributor, I want a clean repository skeleton so that I can install and test the project in minutes.

Acceptance criteria:
- [ ] Package layout matches `docs/ARCHITECTURE.md`.
- [ ] `pip install -e ".[dev]"` installs the package plus `pytest` and `ruff`.
- [ ] `pytest` runs (even with zero real tests) and `ruff check` passes.
- [ ] `data/` is gitignored; `example/` contains a fictional persona (one personality file, at least three notes).

### S1-1b Containerize
As a contributor, I want the project to run in Docker so that the environment is identical on every machine and ready for home-server deployment (ADR-005).

Acceptance criteria:
- [ ] `Dockerfile` based on an official slim Python 3.12 image, running as a non-root user.
- [ ] A `dev` build target adds the `[dev]` extras (pytest, ruff); the default target installs runtime dependencies only.
- [ ] `.dockerignore` excludes `data/`, `.env`, `.git`, `.venv` and caches: neither personal data nor secrets can ever enter an image.
- [ ] `compose.yaml` defines a `clone` service: mounts `./data` read-only at `/app/data`, loads `.env` if present (optional, no error when missing), keeps stdin and a TTY open for the chat.
- [ ] `docker compose run --rm clone pytest` and `docker compose run --rm clone ruff check` pass.
- [ ] Until S1-5 provides the `clone` command, the default command prints the package version.
- [ ] README: Docker becomes the primary way to install, test and run; the local venv stays documented as an alternative.

### S1-2 Memory with keyword search
As a user, I want my Markdown notes loaded and searched so that the clone answers from what I actually wrote.

Acceptance criteria:
- [ ] Loads every `.md` file under `notes/`, recursively.
- [ ] Each heading starts a new chunk; each chunk keeps its source file and heading.
- [ ] Search is case- and accent-insensitive and ignores common stop words (English and French).
- [ ] `search(question, limit)` returns the most relevant chunks, best first, or an empty list.
- [ ] A missing data folder raises a clear error explaining how to create it from `example/`.
- [ ] Unit tests cover loading, chunking, ranking and the empty case.

### S1-3 Personality
As a user, I want my personality file loaded so that the clone speaks with my style and values.

Acceptance criteria:
- [ ] Reads `personality.md` from the data folder.
- [ ] A missing file is not an error: the clone runs with a neutral default and says so once at startup.
- [ ] Unit test for both cases.

### S1-4 Brain and model client
As a user, I want the clone to answer using my memory and personality so that its answers sound like me and stay grounded.

Acceptance criteria:
- [ ] The system prompt includes: the assistant-mode instructions, the personality, and the retrieved chunks with their sources.
- [ ] Instructions say the clone is an AI acting for its user, must say when the information is not in memory rather than invent it, and may challenge the user.
- [ ] Conversation history is kept for the session, capped at a configurable number of turns.
- [ ] The model name is configurable via `CLONE_MODEL`, with a sensible default.
- [ ] Only `model.py` imports the model SDK; tests use a fake model client.
- [ ] The sources used for the last answer are available to the interface.

### S1-5 CLI
As a user, I want to chat with my clone in the terminal so that I can test it today.

Acceptance criteria:
- [ ] `clone` starts a chat; `clone --data <path>` uses another data folder (default `./data`).
- [ ] Startup line shows the number of memory chunks loaded and the model in use.
- [ ] Commands: `/sources` (sources of the last answer), `/reload` (reload memory and personality), `/quit`.
- [ ] A missing API key, a network or API error produce a readable message, never a stack trace.
- [ ] README explains install, setup from `example/`, and usage.

### S1-6 Product owner validation
- [ ] Write a real personality file and 5 to 10 personal notes in `data/`.
- [ ] Ask 10 questions about yourself and rate each answer from 1 to 5.
- [ ] Sprint retro with the lead, using those ratings.

## Next (priority order)

Phase 1, continued (Sprint 2 candidates):
1. Engagement policy: typed proposals, policy file in `data/`, default "needs approval" (ADR-006)
2. Action log: append-only, hash-chained, unique entry IDs (ADR-006, ADR-008)
3. Container hardening: read-only root filesystem, dropped capabilities, no published ports (ADR-007)
4. Vector search (SQLite + embeddings) behind the same retrieval interface
5. Local API gateway on the internal network only
6. Web / PWA interface, reachable from localhost only by default
7. Streaming responses

Phase 2:
8. First MCP tool, reachable only through the engagement policy
9. OPC UA virtual factory simulator and its MCP server

Phase 3:
10. Public memory store and isolated representative service (ADR-007)
11. Approval queue between the representative and the owner
12. Interlocutor profiles
13. Signed outgoing messages (ADR-008)

Later:
14. Remote access through a private VPN, as an explicit opt-in
15. Agent-to-agent API with owner-verifiable identity

## Ideas

- Telegram or Signal bot
- Import notes from other tools
- Memory that grows from conversations, with user approval
