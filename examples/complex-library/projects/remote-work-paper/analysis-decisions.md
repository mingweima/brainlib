---
type: Note
title: Empirical Specification and Sample Decisions
description: Sample construction, variable definitions, and clustering choices for the remote work wage R&R.
read_when: [modifying regression scripts, answering referee questions, checking sample filters]
tags: [econometrics, sample, clustering]
tier: L2
authority: canonical
owner: human:avery
updated: 2026-10-14
verified: {by: human:avery, at: 2026-10-14}
stale_after: 2027-04-01
sensitivity: internal
sources:
  - {id: s1, resource: "chat:2026-10-03-coauthor-sync", provenance: principal-said}
  - {id: s2, resource: "https://example.org/verdan-ui-wage-codebook-2026", provenance: third-party}
---

# Empirical Specification and Sample Decisions

- Restrict the baseline panel to full-time workers aged 24–60 with at least four consecutive quarters at the baseline employer [said 2026-10-03].
- Top-coded quarterly bonus payouts in the New Verdan administrative files affect 1.8% of finance-sector observations after 2022Q3 [external: verdan-ui-wage-codebook-2026].
- Cluster standard errors two ways at the firm and commuting-zone levels across all baseline event-study specifications [judgment].
- Deflating nominal quarterly earnings to 2023Q4 dollars and trimming the top and bottom 0.5% of hourly wage changes stabilized the pre-trends [said 2026-10-14].
- Referee 1 will likely accept leaving out firm-by-quarter fixed effects in Table 4 if we show industry-by-quarter controls absorb the shock [guess].
