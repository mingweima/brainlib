# Provenance v0.1

Every saved statement says where it came from. This is the most important rule in the
library: an agent's inference must never be read later as the owner's own view.

| Level | CLI flag | Inline marker | Meaning | Counts as the owner's view |
|---|---|---|---|---|
| principal-said | `--said` | `[said 2026-10-20]` | the owner's exact words, with the date | yes |
| principal-judgment | `--judgment` | `[judgment]` | a view the owner clearly stated, paraphrased | yes |
| principal-authored | `--extracted FILE` | `[extracted: FILE]` | taken from the owner's own writing; the extraction can be wrong | yes |
| agent-inference | `--inferred` | `[inferred]` | an agent's conclusion, with its evidence | no |
| agent-guess | `--guess` | `[guess]` | an agent's guess without evidence | no |
| third-party | `--external SOURCE` | `[external: SOURCE]` | anything from outside: web, articles, other people | no |

Rules enforced by brainlib:

1. A note item must name exactly one level.
2. The owner's record policy (onboarding Q5) decides which levels may be saved at all.
3. Material whose only source is third-party may not go into L0 or L1 pages.
4. The only way to promote an inference to the owner's view is the owner saying they
   agree; that becomes a new `said` item, and the inference stays labeled as it was.

Older aliases accepted on input: `quote`, `owner-said` (said); `judgement`, `view` (judgment);
`authored` (extracted); `inference`, `agent` (inferred); `guessed` (guess); `web`, `source`,
`outside` (external).
