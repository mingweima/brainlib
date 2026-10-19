# Note format (front matter) v0.1

A note is any `.md` or `.markdown` file in the library. Front matter is optional: notes
without it work, and brainlib infers what it needs without changing the file. Unknown
keys are always preserved. The format is compatible with the
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF) v0.2, where only `type` is required.

```yaml
---
type: Note                  # free text; Journal, Profile, Index, Project ... (inferred: Note / Journal)
title: Weekly plan          # inferred from the first "# heading", then from the file name
description: One sentence on what this note is.     # inferred from the first paragraph
read_when: [planning the week, the user asks about this week]   # when an agent should read it
tags: [planning]
tier: L2                    # L0 core, L1 entry, L2 regular, L3 archive (inferred, see below)
authority: canonical        # canonical | pointer | archived
owner: human:me
updated: 2026-10-20         # inferred from the file's modification time
verified: 2026-10-20        # or [{by: human:me, at: 2026-10-20}]
stale_after: 2027-01-01     # or `ttl: 90` (days after `updated`)
sensitivity: internal       # public | internal | private | secret
---
```

## Inference rules

| Field | When missing |
|---|---|
| title | first `# heading`, else the file name |
| description | first paragraph, trimmed to 160 characters |
| tier | `L3` if archived, or a journal entry older than `stream_days` (14); `L1` for a top-level `README.md` / `index.md`; `L0` for a top-level `me.md`; else `L2` |
| authority | the zone's value, else `canonical` |
| updated | `generated.at`, else the date in a journal entry's file name, else the modification date |
| stale_after | `updated` + the tier's TTL (L0 90, L1 180, L2 365 days; L3 never) |
| sensitivity | the zone's value, else `internal` |

A journal entry is a file named like `2026-10-20.md` inside a folder named `journal`,
`daily`, `diary`, `log` (or plural), or any file in a zone with `stream: true`.

## Accepted older values

Libraries written before this spec, including ones that use Chinese values, are read without changing the files.

| Field | Older value | Read as |
|---|---|---|
| authority | `权威`, `stable` | canonical |
| authority | `指针`, `stub` | pointer |
| authority | `归档`, `deprecated` | archived |
| stale_after | `ttl` (days) | updated + ttl |
| updated | `generated: {at: ...}` | its date |

## Zones

Zones in `.brainlib/config.json` set defaults for every note under a folder:

```json
{"zones": [
  {"path": "journal/", "stream": true, "auto_apply": true},
  {"path": "private/", "sensitivity": "private"},
  {"path": "_archive/", "authority": "archived", "tier": "L3"}
]}
```

Front matter always wins over the zone.
