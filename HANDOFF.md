# Handoff — Spinrate Sales Penetration

## 2026-06-16 (session 5)

**Started from:** Context continuation — data variance fixed, quadrant `.tolist()` applied but unverified, migration/expansion/at-risk unchecked for Plotly 6.0 binary encoding, three UI issues queued.

**Did:** Applied `.tolist()` to 7 Plotly traces in migration.py. Fixed migration legend truncation (shortened labels). Widened expansion column headers + added tooltips. Changed toggle button to INFO_BG fill. Verified all four views render with proper data variance. 138 tests passing.

**State:** All views rendering correctly. Data variance confirmed (ACV 5%-62%, SPPD 0.29-7.01). All UI issues resolved. Ready for Fly.io deploy.

**Next:**
1. Deploy to Fly.io: `fly deploy`, `fly secrets set DATABASE_URL=<url>`, DNS CNAME `spinrate.lailarallc.com`, `fly certs create`
2. Run `/ce:compound` — extract learnings
3. Address remaining P2/P3 review findings in a follow-up session

## 2026-06-16 (session 4)

**Started from:** All 8 units implemented, 138 tests passing. Needed code review, then deploy.

**Did:** Ran `/ce:review` (11-agent, 22 findings fixed). Created private GitHub repo. Set up local dev with localhost Postgres. Diagnosed and fixed two runtime bugs: psycopg2 Decimal-to-float cast at db layer (all four views), Dash 4.x purple accent-color override. Verified all four tabs render with live SSOT data.

**State:** All views rendering with real data. 138 tests passing. Pushed to GitHub. Remaining review findings (#16, #19, #20, #24, #27-29) are P2/P3. Not yet deployed to Fly.io.

**Next:**
1. Deploy to Fly.io: `fly deploy`, `fly secrets set DATABASE_URL=<url>`, DNS CNAME `spinrate.lailarallc.com`, `fly certs create`
2. Run `/ce:compound` — extract learnings
3. Verify protagonist narrative with production SSOT data
4. Address remaining P2/P3 review findings in a follow-up session

## Issues encountered (session 4)

- **Flycast hostname not reachable locally:** cinderhaven-data-platform `.env` uses `cinderhaven-db.flycast` — only works inside Fly.io private network. Use the-question-engine's `.env` which points to `localhost:5432/cinderhaven` for local dev.
- **psycopg2 Decimal vs Plotly 6.0:** Postgres `numeric` columns come back as Python `Decimal`. Plotly 6.0 rejects `Decimal`-backed Series for marker.size (Plotly 5.x was lenient). Fixed by casting in `_execute_query()`.
- **Dash 4.x purple accent-color:** Dash injects `accent-color: rgb(127, 75, 196)` directly on `.dash-dropdown` elements. Override with `!important` on both `:root` and `.dash-dropdown`.
- **Port 8050 collision:** Doormath from a prior session can squat on 8050. Kill stale Python processes before starting Spinrate.

## 2026-06-15 (session 3)

**Started from:** Plan complete and reviewed, no code written.

**Did:** Ran `/ce:work` and implemented all 8 units (U1–U8). Full Dash 3.x + Plotly 6.0 dashboard with 4 interactive views, narrative intro, and deployment config. 138 tests passing across 7 test files.

**Commits this session:**
- `d8615c6` U1 — Dash scaffold, design system, filters, brand frame, Dockerfile, fly.toml
- `bd0e670` U2 — psycopg2 pool, SPPD/ACV%/indexed SPPD/velocity trend/at-risk scoring/expansion upside calculations (30 tests)
- `24a1784` U3 — Quadrant bubble scatter, click-to-pin, indexed SPPD toggle, low-door flagging (26 tests)
- `4f754ab` U4 — Migration view: arrow overlay, side-by-side, sankey; QoQ/custom/rolling (37 tests)
- `dced537` U5 — Expansion case list: AG Grid of hidden gems with 3 benchmark projections (16 tests)
- `7826f1c` U6 — At-risk list: act now/fix or rationalize/watchlist with signal transparency (20 tests)
- `82ea26a` U7 — Data-driven narrative intro, 5 protagonist SKUs discovered at runtime (9 tests)
- `c3e71b2` U8 — Health check with database connectivity status

**State:** All code complete and tested. Not yet deployed. Not yet code-reviewed.

**Next:**
1. Deploy to Fly.io: `fly deploy`, `fly secrets set DATABASE_URL=<url>`, DNS CNAME `spinrate.lailarallc.com`, `fly certs create`
2. Run `/ce:review` — code review pass
3. Run `/ce:compound` — extract learnings
4. Verify protagonist narrative renders with real SSOT data (may need to seed exemplar SKUs if archetypes aren't well-represented)

## Issues encountered

- **Mock path for lazy imports:** `patch("app.db")` fails when `app/__init__.py` is empty because the `db` submodule isn't loaded yet. Fix: `patch("app.db", create=True)`. Applies to expansion and at-risk test files.
- **U5 subagent socket crash:** Subagent created expansion.py and wired layout.py but died before writing tests or committing. Recovery: verified files manually, wrote tests inline.
- **numpy bool identity:** `np.True_ is True` is `False`. Use `==` not `is` for numpy boolean comparisons in assertions.

## Key context

- **Stack:** Dash 3.x + Plotly 6.0, psycopg2 direct (no ORM), Cinderhaven SSOT Postgres
- **Region:** Fly.io `iad` (co-located with SSOT)
- **138 tests** across: test_calculations (30), test_quadrant (26), test_migration (37), test_expansion (16), test_at_risk (20), test_narrative (9)
- **Design system:** Lailara tokens throughout — Canvas, London greyscale, Chicago accent, HK teal sequential, Tokyo rose for risk, Singapore orange for warnings
- **Interaction:** Click-to-pin via clientside JS (not hover), dark callout detail cards, AG Grid for tabular views
- **Narrative:** Runtime protagonist discovery — queries SSOT for best exemplar per quadrant archetype; falls back to generic intro if data insufficient

## Previous sessions

### 2026-06-15 (session 2)
Ran `/ce:plan` (Deep tier). Produced 640-line plan with 8 units. Ran doc review (5 reviewers). Applied 4 safe_auto fixes.

### 2026-06-15 (session 1)
Scaffolded repo. Confirmed Heavy tier. Ran `/clarify` and `/ce:brainstorm`. Requirements doc with 24 requirements.
