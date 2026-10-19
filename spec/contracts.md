# Contracts v0.1

These are stable within a major version. Changes are additive only; renamed commands keep
their old name for one major version; brainlib never rewrites user files to migrate them.

## Command line

- Output for agents: lines starting with `NEXT:`, `WHY:`, `RUN:`, `SAY TO USER:`, `THEN:`
  (from `brainlib next`) and `ERROR:` / `FIX:` (on any failure).
- `--json` gives machine-readable output for most commands.
- Exit codes: `0` ok, `1` findings, `2` usage, `3` privacy refusal, `4` needs the owner's
  approval, `5` conflict (the note changed).
- Agent-facing lines are English; `SAY TO USER:` lines use the user's language (`brainlib lang`).

## Where things live

| What | Where |
|---|---|
| Notes | the library folder (plain Markdown, owned by the user) |
| Settings | `<library>/.brainlib/config.json` (optional; settings only, never content) |
| State: inbox, proposals, receipts, profile | `~/.brainlib/libraries/<library-id>/state/` (mode 700) |
| Outputs: index, reading guide, reports | `~/.brainlib/libraries/<library-id>/out/` |
| Language, agent self-checks, library registry | `~/.brainlib/global.json`, `~/.brainlib/registry.json` |
| Vault | `<library>/vault/` (`*.age` files, `recipient.txt`, `identity.age`) |

`BRAINLIB_HOME` moves `~/.brainlib`. Library selection order: `--library`, `BRAINLIB_LIBRARY`,
a `.brainlib/` folder above the current directory, the registered default.

## Schemas (JSON)

| Schema id | File |
|---|---|
| `brainlib/index@0.1` | `out/index.json`: visible notes only, plus a `private_hidden` count |
| `brainlib/reports@0.1` | `out/reports.json`: `contains_content: false` |
| `brainlib/inbox-item@0.1` | `state/inbox/<date>/<actor>.jsonl` |
| `brainlib/proposal@0.1` | `state/proposals/<id>.json` |
| `brainlib/receipt@0.1` | `state/receipts/<date>.jsonl`: hashes only, `contains_content: false` |
| `brainlib/profile@0.1` | `state/profile.json`, with `profile-history.jsonl` and `profile-signals.jsonl` |
| `brainlib/classify-request@0.1` | stdin of a `command` classifier backend |

## Proposals

| Operation | Rule |
|---|---|
| append | adds text at the end (or at the end of a section); valid even if the note changed |
| create | fails if the file exists |
| replace | records `base_sha256`; goes stale if the note changed |

Approval: L0/L1 always need the owner, with the owner's words. Otherwise the onboarding
answer to Q4 decides (`propose` by default). Every applied change writes a receipt and a
backup for `brainlib undo`. CRLF line endings are kept.

## MCP

`brainlib mcp` speaks MCP over stdio (protocol versions 2025-11-25, 2025-06-18, 2025-03-26,
2024-11-05). Tools mirror the CLI and give the same refusals; see `docs/mcp.md`.
