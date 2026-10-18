# Clone

**Your open-source digital twin, keeping your data at home.**

Clone is a headless personal agent: an engine that holds your memory and personality, with interchangeable interfaces plugged into it (terminal, web, mobile, messaging, other agents).

> The code is public. Your data never is: it stays in your `data/` folder, which Git ignores.

## Vision

One brain, two faces:

- **The assistant** (facing you): full access to your memory; it helps, challenges and proposes.
- **The representative** (facing others): sees only your public memory, answers simple questions for you and asks your approval for anything that commits you.

## Status

Sprint 1, "The clone speaks", in progress. See [BACKLOG.md](BACKLOG.md).

## Getting started

### With Docker (recommended)

Requires Docker with Compose v2.24 or later.

**1. Set up your data.** Start from the fictional example persona, then rewrite it with your own personality and notes (see [Your data](#your-data)):

```
cp -r example data          # your private data folder, ignored by Git
```

**2. Set your API key.** Create a `.env` file at the repository root (Git ignores it):

```
ANTHROPIC_API_KEY=your-key-here
```

**3. Chat.**

```
docker compose build
docker compose run --rm clone
```

To run the tests and the linter:

```
docker compose run --rm clone pytest
docker compose run --rm clone ruff check
```

`data/` is mounted read-only at `/app/data`. `.env` is loaded at runtime. Neither is ever copied into an image.
The source is baked into the image, so rebuild after a change: `docker compose run --rm --build clone pytest`.

### Without Docker

Requires Python 3.10+.

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=your-key-here
clone                       # chat; use `clone --data <path>` for another data folder
pytest
ruff check && ruff format --check
```

## Using the chat

`clone` loads your notes and personality, then waits for your questions. The first line tells you how many memory chunks were loaded and which model is in use.

| Command | Effect |
|---|---|
| `/sources` | Show the sources of the last answer, numbered like the `[1]` citations in the answer |
| `/reload` | Reload your notes and personality after editing them |
| `/quit` | Leave (Ctrl-D works too) |

Anything else is a question. The clone answers from your notes, says so when the answer is not in them, and may challenge you. It is an AI acting for you, never you.

Errors such as a missing API key or no network are shown as a short message; the chat keeps going.

### Your data

```
data/
├── personality.md      # who you are: style, values, red lines (optional)
└── notes/              # Markdown notes, nested folders allowed
    └── *.md            # each heading starts a new memory chunk
```

Without `personality.md` the clone uses a neutral default and says so at startup.

### Settings

Environment variables, set in `.env` (Docker) or in your shell:

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Your API key (required) |
| `CLONE_MODEL` | `claude-sonnet-5-5` | Language model to use |
| `CLONE_EFFORT` | `low` | How much the model thinks: `low`, `medium`, `high`, `xhigh` or `max` |
| `CLONE_MAX_TURNS` | `10` | Question and answer pairs kept as conversation history |

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Guidance for Claude Code](CLAUDE.md)

## Roadmap

| Phase | Content |
|---|---|
| 1 – The brain | Memory, personality, assistant mode |
| 2 – The hands | Tools via MCP, connection to an OPC UA virtual factory |
| 3 – The public face | Representative mode, interlocutor profiles, approval queue |
| 4 – The opening | API to talk with other agents |

## Principles

- **Privacy first**: local data, least access, no personal data in the repository.
- **Transparency**: the clone always presents itself as an AI, never as the person.
- **Traceability**: eventually, a log of everything said and done on the user's behalf.
- **Small and working**: every sprint ships something that runs.

## License

Apache 2.0, see [LICENSE](LICENSE).

## Contributing

Ideas, issues and pull requests are welcome. Please open an issue to discuss before a large change.
