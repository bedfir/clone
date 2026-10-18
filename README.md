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
