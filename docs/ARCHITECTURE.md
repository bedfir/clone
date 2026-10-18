# Architecture

Status: approved for Sprint 1. Owner: lead. Changes go through an Architecture Decision Record (ADR) at the end of this file.

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
3. **Memory is the only persistent state.** Private and public memory will be physically separated (Phase 3), not just filtered by a prompt.
4. **Guardrails wrap everything that leaves the engine.** No message to a third party and no tool action happens without passing permissions, approval (when required) and the action log.
5. **Local first, privacy first.** Data stays on the user's machine; the only outbound call is to the model API.

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
| MCP tools | Actions and data sources (virtual factory, mail, calendar) | Phase 2 |
| Memory compartments | Separate private and public stores | Phase 3 |
| Representative mode | Answers others, with interlocutor profiles | Phase 3 |
| Guardrails | Permissions, approval queue, action log | Phase 3 |
| Agent-to-agent API | Lets other agents talk to the clone | Phase 4 |

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
│   ├── brain.py         # orchestration
│   └── interfaces/
│       └── cli.py       # terminal adapter
├── example/             # fictional persona, safe to commit
│   ├── personality.md
│   └── notes/*.md
├── data/                # the user's real data (gitignored)
├── tests/
├── docs/ARCHITECTURE.md
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── BACKLOG.md
├── CLAUDE.md
└── pyproject.toml
```

Dependency direction: `interfaces → brain → (memory, personality, model)`. Lower layers never import higher ones.

## Data format

`data/` (and `example/`) contains:
- `personality.md`: free Markdown describing who the user is, their style, values and red lines.
- `notes/`: any number of Markdown files, nested folders allowed. Each heading starts a new memory chunk; a chunk keeps its source file and heading for traceability.

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
