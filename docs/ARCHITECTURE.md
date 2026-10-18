# Architecture

Status: approved for Sprint 1, updated for the representative-first positioning (ADR-006 to ADR-008). Owner: lead. Changes go through an Architecture Decision Record (ADR) at the end of this file.

## Overview

```
 Interfaces     CLI      Web/PWA    Messaging    Other agents
                  \         |           |           /
 Gateway                 Local API gateway
                   (authentication, mode selection)
                                |
 Engine   +---------------------------------------------+
          |                    Brain                    |
          |      (builds context, calls the model)      |
          |         /            |             \        |
          |    Memory       Personality     MCP tools   |
          | (private/public)                            |
          |                                             |
          |  Guardrails: permissions, approval queue,   |
          |  action log                                 |
          +---------------------------------------------+
                  |                         |
            Local storage            Language model
              (data/)                  (via API)
```

## Principles

1. **Headless engine.** All logic lives in the engine. Interfaces are thin adapters with no business logic, so a new interface never requires engine changes.
2. **The brain orchestrates, it does not store.** It assembles context from memory, personality and tools, calls the model, and returns the answer. Swapping the model must not affect any other component.
3. **Memory is the only persistent state**, apart from the action log. Private and public memory are physically separated stores, not a filter applied by a prompt (ADR-007).
4. **Guardrails wrap everything that leaves the engine.** No message to a third party and no tool action happens without passing permissions, approval (when required) and the action log.
5. **Local first, privacy first.** Data stays on the user's machine; the only outbound call is to the model API.
6. **The brain proposes, the policy decides.** The brain never sends or acts directly: it produces proposals that the engagement policy allows, forbids or holds for the owner's approval (ADR-006).
7. **One wall between the two faces.** The representative runs as a separate service that cannot read private memory; third-party input is always untrusted data (ADR-007).
8. **Secure by default.** No port is published and nothing is reachable from outside the container network unless the owner explicitly opts in (ADR-007).
9. **Everything said for the owner is traceable.** Outgoing messages and decisions go to an append-only log, designed to be signed (ADR-008).

## Components

| Component | Responsibility | Introduced |
|---|---|---|
| CLI | Terminal chat in assistant mode | Sprint 1 |
| Brain | Context assembly, model call, conversation history | Sprint 1 |
| Model client | Thin wrapper around the model API, easy to mock or replace | Sprint 1 |
| Memory | Load Markdown notes, split into chunks, retrieve relevant chunks | Sprint 1 (keyword search), later vector search |
| Personality | Load and expose the user's style, values and red lines | Sprint 1 |
| Local API gateway | Single entry point for all interfaces, chooses the mode | Phase 1, after Sprint 1 |
| Web / PWA | Browser and mobile interface | Phase 1 |
| Engagement policy | Classifies every proposal: allowed, needs approval, forbidden | Phase 1, Sprint 2 |
| Action log | Append-only record of decisions and outgoing messages, signing-ready | Phase 1, Sprint 2 |
| MCP tools | Actions and data sources (virtual factory, mail, calendar), reachable only through the policy | Phase 2 |
| Public memory | Separate store for what the representative may know | Phase 3 |
| Representative service | Isolated container answering others, with interlocutor profiles | Phase 3 |
| Approval queue | The only channel between the representative and the owner side | Phase 3 |
| Message signing | Signs outgoing messages with an owner-held key | Phase 3 |
| Agent-to-agent API | Lets other agents talk to the clone, with owner-verifiable identity | Phase 4 |

## Sprint 1 scope

Built: CLI, brain, model client, memory with keyword search, personality, local storage.
Not built: gateway, web, tools, compartments, representative mode, guardrails.

## Package layout (target for Sprint 1)

```
clone/
├── clone/
│   ├── __init__.py
│   ├── memory.py        # notes loading, chunking, retrieval
│   ├── personality.py   # personality loading
│   ├── model.py         # model client (only module importing the SDK)
│   ├── actionlog.py     # append-only, hash-chained action log (imports nothing from the package)
│   ├── proposals.py     # typed proposals (OutgoingMessage): what the brain asks for
│   ├── contacts.py      # data/contacts.toml: name -> category, exact lookup
│   ├── policy.py        # data/policy.toml: pure decisions, strict loading
│   ├── engagement.py    # the gate: submit() decides and logs, release() writes the outbox
│   ├── tomlfile.py      # reads a TOML file with readable errors (used by contacts and policy)
│   ├── brain.py         # orchestration
│   └── interfaces/
│       └── cli.py       # terminal adapter
├── example/             # fictional persona, safe to commit
│   ├── personality.md
│   └── notes/*.md
├── data/                # the owner's real data (gitignored, mounted read-only)
├── state/               # the clone's own state, e.g. the action log (gitignored, writable)
├── tests/
├── docs/ARCHITECTURE.md
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── BACKLOG.md
├── CLAUDE.md
└── pyproject.toml
```

Dependency direction: `interfaces → brain → (memory, personality, model, engagement)` and `engagement → (policy, contacts, proposals, actionlog)`. Lower layers never import higher ones.

## Data format

`data/` (and `example/`) contains:
- `personality.md`: free Markdown describing who the user is, their style, values and red lines.
- `notes/`: any number of Markdown files, nested folders allowed. Each heading starts a new memory chunk; a chunk keeps its source file and heading for traceability.
- `contacts.toml` (optional): the people the clone may write to, with a category each. See "Engagement policy".
- `policy.toml` (optional): what the clone may do, by type of action and recipient category. See "Engagement policy".

## Action log

The action log is the owner's record of what the clone did in their name (ADR-008). It is a tamper-evident chain, not a secret store: it never contains questions, answers, note content or secrets.

- **File:** `state/log.jsonl` (ADR-009), written by `clone/actionlog.py`. The folder is chosen with `clone --state <path>` (default `./state`) and must exist and be writable; the clone never creates it.
- **Entries:** one JSON object per line, UTF-8, with five fields:

  | Field | Content |
  |---|---|
  | `id` | uuid4, 32 hex characters |
  | `ts` | UTC, RFC 3339 with `Z`, millisecond precision, e.g. `2026-10-18T13:40:12.123Z` |
  | `type` | dotted lowercase string, e.g. `session.started` |
  | `payload` | JSON object, specific to the type |
  | `prev` | hash of the previous entry's line; 64 zeros for the first entry |

- **Serialization:** `json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`, then a newline.
- **Hashing rule:** `prev` is the SHA-256 (hex) of the previous line's exact bytes as written, without the trailing newline. Verification hashes the raw lines and never re-serializes them.
- **Appending:** the file is opened in append mode, locked exclusively (`fcntl.flock`) for the whole append, and the previous line is read under that lock, so two sessions cannot fork the chain. Each entry is one write, flushed and `fsync`ed.
- **Logged today:** `session.started` with the model name and the number of memory chunks. Decisions and messages join in later stories through the same API.
- **Reading:** `clone log [-n N]` shows the last N entries (default 20). `clone log verify` checks the whole chain, reports the first break and exits with an error. A break is reported as a **link between two entries**, because the chain cannot say which of the two is at fault: `Broken between entries 2 and 3 (ids ...): entry 3 does not match entry 2 as it is now. Entry 2 was modified, or entries were removed or reordered.` Two other cases have their own wording: an entry that cannot be read (`Broken at entry <k> (id <short id>): invalid JSON` or `missing field ...`), and a first entry that does not start the chain (entries before it were removed, or it was modified).

**What the chain detects:** editing an entry (the entry after it no longer matches), deleting an entry, inserting a forged one, reordering entries, and a corrupt line.

**What it cannot detect on its own:** changing or deleting the **last** entry, or the last few, because no later entry refers to their hash. The head hash printed by `clone log verify` (the first 12 hex characters of the last line's hash) is what closes this gap: an owner who notes it elsewhere can see that the tail changed. Signing the head with an owner-held key is planned for Phase 3 (ADR-008). Until then the log shows tampering in the middle of the history, and tail changes only to someone who kept the head.

**Platform:** `fcntl` locking means POSIX systems (Linux, macOS, the Docker containers used here).

## Engagement policy

The brain proposes, the policy decides (ADR-006). The policy decides on facts the code controls (the type of the proposal and the category found in the contacts), never on anything the model says about a proposal. A proposal has no category field.

**Modules.** `proposals.py` defines `OutgoingMessage(id, recipient, text)` (frozen; `id` is a uuid4 hex). `contacts.py` and `policy.py` load the two files below. `engagement.py` is the gate: `submit(proposal)` is the only way in, and `release(proposal_id, owner_approved=True)` is the only code that writes to `state/outbox/` (a test checks that no other module mentions it). Nothing is really sent: the outbox is a simulated channel. Pending proposals are held in memory for now.

**`data/contacts.toml`** (missing file: no contacts, so every recipient is unknown):

```toml
[[contact]]
name = "Julien Martin"
category = "colleague"
```

Lookup is by exact name, trimmed and case-insensitive, nothing else: no fuzzy matching (a near match could reach the wrong person), no parsing of the recipient string. Categories are trimmed and lower-cased. Duplicate names, a missing name or category, and unknown keys are load errors.

**`data/policy.toml`**:

```toml
[outgoing_message]
default = "approve"

[outgoing_message.categories]
colleague = "approve"
supplier = "forbid"
```

Loading is strict and fails closed: an unknown section, key or decision value is an error naming the file and the problem. `allow` is refused for outgoing messages, in `default` and in a category: a message is free text, and one classified as harmless could be an order, so nothing leaves without the owner's approval until a separate, narrow engagement type exists. A missing file, or a missing `default`, means `approve`. Policy and contacts are read when the chat starts (restart to apply a change); an error stops the chat before it begins.

**Decision order** (`Policy.decide(proposal, category)`, pure; the first rule that applies wins):

| # | Case | Outcome | Rule |
|---|---|---|---|
| 1 | Not an outgoing message (unsupported type) | forbid | `builtin.unknown_proposal_type` |
| 2 | Recipient not in the contacts (category `None`) | forbid | `builtin.unknown_recipient` |
| 3 | No policy file | approve | `builtin.no_policy_file` |
| 4 | The recipient's category is listed | as listed | `outgoing_message.categories.<category>` |
| 5 | Anything else | `default` (approve if absent) | `outgoing_message.default` |

Rules 1 to 3 are built in and cannot be configured. The category in a rule string is the lower-cased one.

**`submit`** logs one `policy.decided` entry per proposal, then holds it (`approve`) or refuses it (anything else: fail closed). The entry holds the proposal id, type, recipient, category (`null` if unknown), outcome, rule and `text_sha256`, the hash of the text, never the text. A decision that cannot be logged is not taken: no log entry, no decision. A proposal id can be submitted only once.

**`release`** refuses without `owner_approved=True` (only the CLI will pass it, for the owner), and for an unknown, refused or already released proposal. It logs `proposal.released` (proposal id and file name) before writing `state/outbox/<id>.json`, which is marked `"simulated": true`; if the write fails it logs `proposal.release_failed` and the proposal stays pending. No log entry, no action.

## Architecture Decision Records

### ADR-001: Python for the whole project
Accepted. Consistent with the planned OPC UA virtual factory and the MCP Python SDK.

### ADR-002: Markdown files as the source of memory
Accepted. Human-readable, editable in any tool, easy to version privately. Indexes (vector search) will be derived from these files, never the other way round.

### ADR-003: Keyword retrieval first, vector search later
Accepted. Keeps Sprint 1 dependency-free; the retrieval interface must allow swapping the implementation without touching the brain.

### ADR-004: Apache 2.0 license
Accepted. Permissive, business-friendly, includes a patent grant.

### ADR-005: Docker as the development and deployment environment
Accepted. One image, run through Docker Compose, for development, tests and the future home server.
- Personal data is never baked into an image: `data/` is mounted as a volume, read-only while the clone only reads memory. Making it writable will be an explicit decision.
- Secrets come from a gitignored `.env` file at runtime, never copied into an image.
- Later components (local API gateway, vector store, OPC UA simulator, MCP servers) join as services in the same `compose.yaml`, on an internal network.

### ADR-006: The engagement policy is a primitive of the brain
Accepted. Positioning: "the agent that represents you without being able to impersonate you".
- The brain never executes or sends anything itself. It returns typed proposals: an answer to the owner, an outgoing message, a tool action.
- The engagement policy classifies each proposal as allowed, needs owner approval, or forbidden. The default for anything that leaves the engine or has a side effect is "needs approval".
- The owner's rules (including red lines) live in a policy file in `data/`, read-only to the clone.
- Tools and outgoing channels are reachable only through the policy executor, so no component can bypass it by construction.
- Every decision is written to the action log.
- Introduced in Sprint 2, before any tool, gateway or outgoing channel exists.

### ADR-007: Structural isolation and secure-by-default deployment
Accepted.
- The representative is a separate Compose service. It mounts only the public memory and never the private `data/` volume. Its only link to the owner side is the approval queue, a narrow interface carrying proposals and decisions, never memory.
- Messages from third parties are untrusted data, never instructions, in every prompt that contains them.
- No port is published by default. Exposing a service requires an explicit Compose override file and a dedicated story.
- Containers are hardened: non-root user, read-only root filesystem where possible, dropped Linux capabilities.

### ADR-008: Signed, traceable outgoing messages
Accepted in principle; the signing mechanism is chosen in Phase 3.
- From Sprint 2, the action log is append-only and hash-chained, and each entry has a unique ID, so it can be signed later without changing its format.
- When the representative ships, every outgoing message is signed with a key held by the owner, and its log entry links the message to the owner's approval when one was required.
- The identity format follows the emerging agent-identity work at that time; no draft standard is adopted before then.

### ADR-009: The clone's own state lives in `state/`, apart from the owner's data
Accepted.
- `data/` belongs to the owner: notes, personality, policy, contacts. It is mounted read-only; the clone never writes there.
- `state/` belongs to the clone: action log, pending proposals, simulated outbox, evaluation reports. It is gitignored, excluded from every image, and mounted read-write.
- Keeping them apart means a compromised or buggy clone can record things but cannot rewrite what its owner said.
