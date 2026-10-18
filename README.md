# Clone

**The agent that represents you without being able to impersonate you.**

Clone is an open-source, self-hosted agent that can speak for you to other people and other agents, while staying accountable to you. Nothing that commits you leaves without your approval, and everything it says on your behalf can be traced back to you.

> The code is public. Your data never is: it stays in your `data/` folder, which Git ignores.

## Why Clone

Self-hosted personal agents have proven that people want an agent of their own. They have also shown that security added afterwards does not hold: exposed instances, malicious plugins, prompt injection. Clone is built the other way round, with the guardrails as the foundation.

## Vision

One owner, two faces, one wall between them:

- **The assistant** (facing you): full access to your memory; it helps, challenges and proposes.
- **The representative** (facing others): runs separately, sees only your public memory, answers simple questions for you and asks your approval for anything that commits you.

Three properties define Clone:

1. **It answers to you.** Every action that commits you goes through an engagement policy built into the brain; by default, it needs your approval.
2. **It cannot reach what it must not see.** The public face is isolated from your private memory by the system itself, not by an instruction to the model.
3. **It cannot impersonate you.** Every message it sends for you is logged and signed, traceable to you as its owner.

## Status

Sprint 1, "The clone speaks", in progress. See [BACKLOG.md](BACKLOG.md).

## Getting started

### With Docker (recommended)

Requires Docker with Compose v2.24 or later.

```
cp -r example data          # your private data folder, ignored by Git; then rewrite it
docker compose build
docker compose run --rm clone             # prints the version until the chat lands (S1-5)
docker compose run --rm clone pytest
docker compose run --rm clone ruff check
```

`data/` is mounted read-only at `/app/data`. Secrets such as `ANTHROPIC_API_KEY` go in an optional `.env` file at the repository root, loaded at runtime. Neither `data/` nor `.env` is ever copied into an image.
The source is baked into the image, so rebuild after a change: `docker compose run --rm --build clone pytest`.

### Without Docker

Requires Python 3.10+.

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check && ruff format --check
```

`example/` holds a fictional persona for tests and demos. Your real data goes in `data/`, which Git ignores.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Guidance for Claude Code](CLAUDE.md)

## Roadmap

| Phase | Content |
|---|---|
| 1 – The brain | Memory, personality, assistant mode, engagement policy, action log |
| 2 – The hands | Tools via MCP, all gated by the engagement policy; OPC UA virtual factory |
| 3 – The public face | Isolated representative service, public memory, interlocutor profiles, signed messages |
| 4 – The opening | Agent-to-agent API with an identity verifiable back to the owner |

## Principles

- **Privacy first**: local data, least access, no personal data in the repository.
- **Transparency**: the clone always presents itself as an AI, never as the person.
- **Secure by default**: nothing is exposed on the network unless you explicitly choose to.
- **Traceability**: a log of everything decided, said and done on the user's behalf.
- **Small and working**: every sprint ships something that runs.

## License

Apache 2.0, see [LICENSE](LICENSE).

## Contributing

Ideas, issues and pull requests are welcome. Please open an issue to discuss before a large change.
