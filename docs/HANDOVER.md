# Lead handover

Read this first when starting a new lead conversation. Updated at the end of every sprint.

## Where we are (end of Sprint 1)

- Sprint 1 "The clone speaks" is done: 8 stories (S1-1 to S1-7, with S1-1b), 129 tests, all merged on `master`.
- The clone chats in the terminal, answers from the owner's Markdown notes with cited, stable excerpt IDs, speaks in the owner's style, says when it does not know, and refuses to claim to be the owner.
- Product owner validation used a fictional private persona in the gitignored `data/` folder.
- Sprint 2 "The clone answers to its owner" is planned in `BACKLOG.md`, ending on a live demo.

## Positioning

"The agent that represents you without being able to impersonate you." Decided by the product owner after the strategy review: self-hosting alone is not a differentiator; the representative with built-in guardrails is. See README and ADR-006 to ADR-009.

## Team and workflow

- Product owner: the user. Decides scope, positioning, and anything touching personal data. Runs the real-model validation.
- Lead: Claude (chat, claude.ai Project "Clone"). Writes stories and ADRs, reviews every story, owns `docs/`, `BACKLOG.md`, `CLAUDE.md`. One lead conversation per sprint, started from this file.
- Developer: Claude Code in `/srv/docker/clone` (WSL). One branch per story, `story/<id>-<name>`, merged with `--no-ff` after lead approval.
- Strategist: a separate conversation for vision, competition and articles. Its "For the lead" items reach the lead through the product owner.

## Working agreements learned in Sprint 1

- The lead never runs `git checkout` in the developer's folder. Reviews and doc changes happen in a separate `git worktree`, then the developer merges.
- Reviews include a manual test, not only reading the code and running the suite: two real bugs were found that way (lost parent headings, false self-corrections).
- Any story that changes what the model sees is also validated with the real model (S2-5 automates part of this).
- Claude Code reports with: what was built, how to try it, open questions. The lead answers every question explicitly.

## Decisions taken in reviews (not all are ADRs)

- Retrieval: keyword search with accent, case, ligature and simple plural folding; chunks carry their full heading path; folder and file names are searchable, except the top-level `notes/`. Real stemming and synonyms wait for vector search.
- Each user turn carries its own retrieved excerpts in the history; citations use stable chunk IDs; the clone must not retract earlier answers because their excerpts are not repeated.
- Model: `claude-sonnet-5-5` by default (`CLONE_MODEL`), low effort by default (`CLONE_EFFORT`), history capped by `CLONE_MAX_TURNS` (default 10). No server-side fallbacks, no streaming yet.
- Missing or empty `data/` is an error with the `cp -r example data` hint; a missing or empty personality file falls back to a neutral default with a notice.
- Docker: dev image for tests, runtime image as default target, source copied (not mounted), compose override file planned for deployment.

## Environment notes

- Windows with WSL (Ubuntu), Docker Desktop with WSL integration enabled. The repo lives at `/srv/docker/clone`.
- The lead reaches the repo through the "WSL + Windows Workspace" connector, with allowed roots `/srv/docker/clone` and `~`.
- No Git remote yet. Plan: a private GitHub repository, made public once the product owner decides after the Sprint 2 demo.

## Open items

- Publication timing: decided at the Sprint 2 retro, after the demo.
- Excerpt deduplication across turns, streaming, vector search: in the backlog.
