# CLAUDE.md

Guidance for Claude Code and other agents working in this repo.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in `jcyr13/fantasy-football`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, label strings unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Constraints

- **No Yahoo Fantasy Sports API.** The owner does not have API access and does
  not expect to get it. Do not propose the official API (OAuth apps, yfpy,
  `yahoo-fantasy-api`, etc.) as a solution for Yahoo data unless the owner
  raises it. ADR-0001's "swappable to the API later" is aspirational only; all
  Yahoo data comes from the owner's signed-in web session.
