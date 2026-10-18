# Backlog

Two-week sprints. End of each sprint: demo, 10-minute retro, backlog reordering.
Stories are written by the lead, implemented by Claude Code, accepted by the product owner.

## Sprint 1: "The clone speaks" (done)

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

### S1-7 Stable excerpts across turns (bug from product owner testing)
From the third question on, the clone retracted correct earlier answers: excerpts were replaced and renumbered every turn while the history kept answers citing the old numbers.

Acceptance criteria:
- [ ] Each turn's retrieved excerpts are attached to that user turn in the history, labelled as data.
- [ ] Each chunk has a stable short ID derived from its source and heading path, used in citations and `/sources`.
- [ ] The rules say earlier answers rest on earlier turns' excerpts and must not be retracted because those are not repeated.
- [ ] Regression test: three turns retrieving different chunks; turn-1 excerpts are still sent at turn 3, IDs identical across turns.
- [ ] Product owner re-runs questions 1, 3 and 9: no false self-correction.

### S1-6 Product owner validation
- [ ] Write a real personality file and 5 to 10 personal notes in `data/`.
- [ ] Ask 10 questions about yourself and rate each answer from 1 to 5.
- [ ] Sprint retro with the lead, using those ratings.

## Sprint 2: "The clone answers to its owner" (current)

Sprint goal: the first visible proof of the positioning. The clone drafts a message to a fictional colleague; the draft goes through the engagement policy, waits for the owner's approval, and appears in a tamper-evident log. Nothing is ever really sent.

Demo script (product owner, with the product owner's private persona):
1. "Julien asks whether the line 2 packer can restart on Friday. Draft him a reply." The draft respects the persona's red line (no restart date without seeing the machine), is held for approval, and shows in `/pending`.
2. `/approve <id>`: the message lands in the simulated outbox and in the log.
3. "Send the supplier an order for 8,000 euros of parts." The policy holds or forbids it, and says which rule applied.
4. A draft to someone who is not in the contacts is refused.
5. `clone log verify` confirms the log is intact; editing one line by hand makes it fail.


### S2-1 Writable state and container hardening
As the owner, I want the clone's own state kept apart from my data, in a hardened container, so that it can record things without being able to change my notes (ADR-007, ADR-009).

Acceptance criteria:
- [ ] A gitignored `state/` folder, mounted read-write at `/app/state`; `data/` stays read-only.
- [ ] `.dockerignore` excludes `state/`; the guard test checks it.
- [ ] The `clone` service runs with a read-only root filesystem, all Linux capabilities dropped and `no-new-privileges`.
- [ ] `compose.yaml` publishes no port; a test fails if one is added.
- [ ] The README explains `data/` (yours, read-only) versus `state/` (the clone's, writable).

### S2-2 Action log
As the owner, I want every decision and outgoing message recorded in a log nobody can silently edit, so that I can always check what was done in my name (ADR-008).

Acceptance criteria:
- [ ] Append-only JSON Lines file in `state/`; each entry has a unique ID, a UTC timestamp, a type, a payload and the hash of the previous entry.
- [ ] `clone log` lists recent entries; `clone log verify` checks the whole chain and reports the first broken entry.
- [ ] Tests: tampering with, deleting or reordering an entry is detected.
- [ ] The log never contains secrets; the format is documented in `docs/ARCHITECTURE.md`.

### S2-3 Engagement policy
As the owner, I want a rule to decide what the clone may do alone, what needs my approval and what is forbidden, so that nothing commits me without my say (ADR-006).

Acceptance criteria:
- [ ] Typed proposals (at least: outgoing message), each with a unique ID.
- [ ] `data/contacts.toml` lists contacts with a name and a category (colleague, manager, supplier...); `example/` gets fictional ones. The recipient's category always comes from this file, never from the model.
- [ ] A policy file `data/policy.toml` (read with the standard library) maps proposal types and recipient categories to `allow`, `approve` or `forbid`.
- [ ] No policy file, or a case it does not cover: the decision is `approve`. A message to an unknown recipient is `forbid`.
- [ ] No automatic sending: until the `engagement` type exists, an outgoing message can only be `approve` or `forbid`. A policy file that sets `allow` for outgoing messages is refused at load time with a clear error naming the rule, and the chat does not start. Reason: otherwise an order classified as a plain message could leave without approval.
- [ ] Every decision is logged with the rule that produced it.
- [ ] The policy is the only path from a proposal to an action; a test shows the outbox cannot be written without a policy decision.
- [ ] `example/` gets a commented `policy.toml`.

### S2-4 Simulated outgoing channel
As the owner, I want to ask the clone to draft a message to a colleague and approve it before it goes, so that I see the representative's core loop working end to end.

Acceptance criteria:
- [ ] The model can propose a message through a tool (for example `draft_message(recipient, text)`); calling it creates a proposal, never a send.
- [ ] The CLI shows each new proposal with its policy decision; `/pending`, `/approve <id>` and `/reject <id>` manage the queue.
- [ ] Approved messages are written to `state/outbox/`, clearly marked as simulated, and logged; rejected ones are logged too.
- [ ] Contact messages are never fed back into a prompt as instructions (rule 8).
- [ ] The system prompt's rule 3 still holds: drafts are written for the owner, never signed as the owner.

### S2-5 Real-model evaluation set
As the lead, I want a scripted set of questions run against the real model, so that changes to the prompt or retrieval are checked the way the product owner checked Sprint 1.

Acceptance criteria:
- [ ] `clone eval` runs a list of questions from a file in `example/` against the example persona and writes a readable report to `state/`.
- [ ] Each question can state expectations (must cite, must say it does not know, must refuse); simple checks flag clear failures.
- [ ] It is opt-in, needs the API key, and is never part of `pytest`.
- [ ] Covers the Sprint 1 grid, the false self-correction scenario and the Sprint 2 demo.

### S2-6 Product owner demo and retro
- [ ] Run the demo script above with the product owner's private persona.
- [ ] Sprint retro with the lead; decide whether the project is ready to be published.

### Stretch: S2-7 Vector search
Only if S2-1 to S2-5 are done: SQLite + embeddings behind the existing retrieval interface, so that "studies" finds "training" and "running" finds "run".

## Next (priority order)

Phase 1, continued:
1. `engagement` proposal type (orders, commitments, amounts), the prerequisite for any `allow` rule on outgoing messages. Constraints: the classification never rests on the model's own declaration alone (a type or an amount extracted by the model can be manipulated by prompt injection); deterministic checks in code decide, and the model can only make a case stricter, never looser; any doubt blocks (`approve` or `forbid`, never `allow`).
2. Vector search (SQLite + embeddings) behind the same retrieval interface
3. Local API gateway on the internal network only
4. Web / PWA interface, reachable from localhost only by default
5. Streaming responses
6. Do not resend an excerpt already attached to an earlier turn of the session; refer to it by ID (keeps the history small)

Phase 2:
7. First MCP tool, reachable only through the engagement policy
8. OPC UA virtual factory simulator and its MCP server

Phase 3:
9. Public memory store and isolated representative service (ADR-007)
10. Approval queue between the representative and the owner
11. Interlocutor profiles
12. Signed outgoing messages (ADR-008)

Later:
13. Remote access through a private VPN, as an explicit opt-in
14. Agent-to-agent API with owner-verifiable identity

## Ideas

- Telegram or Signal bot
- Import notes from other tools
- Memory that grows from conversations, with user approval
