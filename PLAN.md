# Plan — Spinrate Sales Penetration

**Tier:** Heavy
**Status:** Loading state + Performance Fix D deployed to production, prod outage (stale DB credential) fixed and verified live. `docs/AUDIT-2026-07-01.md` fully resolved across two concurrent sessions: Basic Auth added then reverted, Indexed SPPD benchmark fixed, quadrant median consistency, at-risk Level/Trend disclosure, ACV% clamp, quarter validation, test hardening, dependency pinning — plus (2026-07-02) the quadrant legend clipping bug root-caused and fixed (custom HTML/CSS legend replacing Plotly's native SVG legend), all chart legends standardized to bottom placement, and a shared `data_grid()` component rolled out to all three tables (no pagination, autosized columns, compact, full-width). 181 tests. Deployed and live. Compound pass pending.

## Goal (2026-06-15)

Interactive penetration × velocity quadrant dashboard for the Lailara portfolio. Plots Cinderhaven SKUs by distribution (x) vs SPPD (y), bubble-sized by total dollars. Four required views: quadrant chart, quadrant migration, ranked expansion cases, ranked at-risk list. Guided narrative walks 5 protagonist SKUs through their strategic story, then hands the user full interactive controls. Deployed to a lailarallc.com subdomain. Part of a 5-tool suite with a planned pillar content piece. Audience is C-suite prospective clients — must be legible in 90 seconds without analyst background.

## Focus

Loading state + audit remediation shipped. Run `/ce:compound`.

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
- [x] Fix cold-cache performance — Fix D: SQL aggregation (465K rows → ~50)
- [x] Commit UX round 2 changes
- [x] Deploy performance fix to production (shipped with the loading-state deploy)
- [x] Branded pre-hydration loading state for cold-link first paint (deployed)
- [ ] `/ce:compound`

### Un-pinned defect — tests are waiting, fix is not written

Added 2026-07-28 by the FIX-LIST cross-repo test sweep. Strict-xfail tests
assert the corrected behaviour, so the suite fails loudly the moment the fix
lands and the marker has to come off. Do not remove a marker without doing the
fix.

- [ ] **Migration's two periods get identical distribution.** `app/db.py:316` —
      `get_distribution()` builds its WHERE clause from `retailers` and
      `region` only and hardcodes `fd.is_active = TRUE`. It selects
      `authorized_date` and `deauthorized_date` (`:332-333`) and never
      constrains on them, so every SKU carries the same ACV% in both periods
      and 8 of the 12 ordered quadrant transitions are unreachable.
      `is_active = TRUE` compounds it: a SKU deauthorized inside the window is
      dropped from both periods rather than shown as a delisting. Add a
      date-window clause. Tests: `tests/test_migration.py` —
      `test_query_constrains_on_the_authorization_window`,
      `test_query_does_not_hardcode_is_active`. The `two_period_metrics`
      fixture hands the same frame to both periods on purpose — it reproduces
      production; update it once the query is fixed.
      Consider hiding the Migration tab until this lands.
      Related, not fatal: `quadrant.py:693` and `expansion.py:110` also call
      `get_distribution(filters)`, so ACV% is inert to the date filter there
      too — defensible as a current-state reading on a snapshot tab.

## Migration distribution window (fixed 2026-07-28, needs one DB run)

`get_distribution()` built its WHERE clause from `retailers` and `region` only
and hardcoded `fd.is_active = TRUE`, ignoring `start_quarter`/`end_quarter`.
Both of Migration's periods therefore received an identical frame: `acv_pct_p1`
equalled `acv_pct_p2` for every SKU, arrows were strictly vertical, the ACV term
in `magnitude` was permanently zero, and only Stars <-> Wide-but-Dead and Hidden
Gems <-> Question Marks were reachable -- 8 of 12 ordered transitions impossible.
The narrative printed the consequence in plain sight, rendering the same
distribution percentage twice in a sentence asserting movement.

Now filtered on the authorization window overlapping the period:
`authorized_date <= quarter_end AND (deauthorized_date IS NULL OR
deauthorized_date >= quarter_start)`. With no period supplied it falls back to
`is_active = TRUE`, so unfiltered callers are unchanged. `_cache_key` already
hashes every filter key, so the two periods get distinct cache entries.

Verified without a database by patching `_execute_query`: Q3 yields params
['2025-09-30','2025-07-01'] and Q4 ['2025-12-31','2025-10-01'], the no-period
path still emits `is_active = TRUE`, and the clause composes correctly with
retailer and region. `tests/test_db.py` passes 5/5 before and after. Seven
tests replace the two strict-xfails; the load-bearing one asserts that two
periods cannot produce the same parameters.

STILL TO DO before this ships:
1. Run against the live Postgres. The SQL is unverified against real data --
   no query was ever executed. Confirm Migration now shows non-vertical arrows
   and that entries/exits appear once the inner join is also fixed.
2. Blast radius: `quadrant.py:693` and `expansion.py:110` call the same
   function with the user's date range, so ACV% on those tabs becomes
   period-aware too. That is the correct behaviour, but it is a visible change
   to two tabs beyond Migration. Look at both before deploying.
3. `two_period_metrics` still hands one dist frame to both periods. A second
   frame would let migration mechanics be tested against real ACV% movement.
