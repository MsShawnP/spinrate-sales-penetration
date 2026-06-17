# Plan — Spinrate Sales Penetration

**Tier:** Heavy
**Status:** UX pass rounds 1+2 deployed. Performance profiled — user to pick fix direction. 145 tests, compound pass pending

## Goal (2026-06-15)

Interactive penetration × velocity quadrant dashboard for the Lailara portfolio. Plots Cinderhaven SKUs by distribution (x) vs SPPD (y), bubble-sized by total dollars. Four required views: quadrant chart, quadrant migration, ranked expansion cases, ranked at-risk list. Guided narrative walks 5 protagonist SKUs through their strategic story, then hands the user full interactive controls. Deployed to a lailarallc.com subdomain. Part of a 5-tool suite with a planned pillar content piece. Audience is C-suite prospective clients — must be legible in 90 seconds without analyst background.

## Focus

UX rounds 1+2 deployed. Pick perf fix, commit, then `/ce:compound`.

## Tasks

- [x] Scaffold repo (git init, .gitignore, README, state files)
- [x] Confirm tier → Heavy
- [x] `/clarify` — requirements nailed
- [x] `/ce:brainstorm` — full requirements doc with 24 requirements
- [x] `/ce:plan` — Deep plan with 8 implementation units, doc reviewed
- [x] `/ce:work` — U1: Scaffold + shared infrastructure
- [x] `/ce:work` — U2: Data layer (Postgres, SPPD, ACV%, calculations)
- [x] `/ce:work` — U3: Quadrant chart view
- [x] `/ce:work` — U4: Migration view
- [x] `/ce:work` — U5: Expansion case list
- [x] `/ce:work` — U6: At-risk list
- [x] `/ce:work` — U7: Narrative intro + protagonist data
- [x] `/ce:work` — U8: Deployment + subdomain
- [x] Deploy to Fly.io + DNS
- [x] `/ce:review` — 11-agent review, 22 findings fixed, 2 runtime bugs fixed
- [x] UX pass round 1 — filters, narrative, tooltips, summaries, table overflow (#1–#5)
- [x] UX pass round 2 — interactive summary, dead label, migration colors, hero cards (#1–#3, #6)
- [x] Deploy UX pass rounds 1+2 to production
- [x] Profile expansion + at-risk callbacks in production (#4, #5)
- [ ] Fix cold-cache performance (user to pick direction: preload, indexes, dbt, or SQL-agg)
- [ ] Commit UX round 2 changes
- [ ] `/ce:compound`
