---
type: Project
title: Remote Work and Wage Dynamics Paper Overview
description: Revise-and-resubmit project studying how hybrid and remote arrangements affect wages using restricted state administrative data.
read_when: [working on the R&R manuscript, reviewing replication scripts, checking referee tasks]
tags: [remote-work, wages, econometrics]
tier: L1
authority: canonical
owner: human:avery
updated: 2026-10-18
verified: {by: human:avery, at: 2026-10-18}
sensitivity: public
---

# Remote Work and Wage Dynamics Paper

We use restricted quarterly unemployment insurance wage records from the New Verdan State Workforce Agency (2018Q1–2024Q4) to estimate wage changes after firm-level remote transitions [said 2026-09-05].

## Replication & Manuscript Structure
- `code/01_build_panel.py` links quarterly worker-firm earnings with occupational teleworkability indices [said 2026-10-03]
- `code/02_event_study.R` runs stacked difference-in-differences and two-way fixed effects regressions [said 2026-10-03]
- Section 2 revises the institutional background and adds three robustness checks requested by Referee 2 [said 2026-10-18]

## Current Priorities
- Automate LaTeX table exports from R so updated standard errors flow directly into the manuscript [judgment].
- See [Analysis Decisions](analysis-decisions.md) for sample restrictions and clustering choices.
- Earlier structural search-model drafts from graduate school were retired in [Archived Old Dissertation Plan](../../_archive/old-dissertation-plan.md).
