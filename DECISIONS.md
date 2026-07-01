# Decisions — Spinrate Sales Penetration

*Durable choices with rationale. Updated as decisions are made.*

### 2026-07-01 — Fix a stale credential by resyncing the consuming app, not by resetting the DB
- **Why:** Prod 503 traced to spinrate's `DATABASE_URL` Fly secret holding a password that no longer matched the database's actual `postgres`-role password. The temptation was to reset/rotate the DB-side password. Instead, checked whether a currently-working password already existed elsewhere (it did — a 2026-06-30 session had left it in `cinderhaven-data-platform/.env`, confirmed live against the DB) and used that as the canonical value. Resetting DB-level credentials is higher blast radius (affects every consuming app at once, requires a DB restart) than updating one app's stale copy.
- **Scope:** Any Cinderhaven-consumer app reporting `password authentication failed` or `SSL SYSCALL EOF` against `cinderhaven-db.flycast`. Full canonical-credential detail and app inventory live in recall-blast-radius's `recall_infra_topology.md` memory.
- **Do not:** Reset or rotate `cinderhaven-db`'s own role passwords/secrets as a first response to an app-level auth failure. Check whether a currently-valid credential already exists (test it live, don't assume from a Fly secret's mere presence) before treating the DB itself as the thing that needs fixing.

### 2026-06-18 — Do not defer AG Grid JS; keep pre-rendered panel hydration
- **Why:** Deferring AG Grid's JS off the initial Quadrant-only paint requires the `dag.AgGrid` components to NOT be mounted at load. But the pre-rendered-panel fix mounts all four panels at load specifically so the data callbacks (which fire on load and write to `expansion-grid`/`at-risk-grid`/`watchlist-grid` `rowData`) always find their targets. Every route to deferring the grid — placeholder swap, same-ID div, or gating the callbacks — removes the mounted target or gates the callback on tab activation, which is exactly the callback race that caused the At-Risk default-load bug. The two are architecturally coupled; you can't shave the grid off first paint without re-coupling to the hydration logic. After the loading overlay landed, the overlay covers the whole hydration window anyway, so a lighter Quadrant paint underneath it wouldn't change what the prospect sees.
- **Scope:** spinrate tab hydration (layout.py `_build_content_area` + the per-view data callbacks). Applies to any future "lazy-load a tab's heavy component" idea in this app.
- **Do not:** Unmount the grids from the initial layout, or gate the expansion/at-risk data callbacks on tab activation, to save bundle weight. If revisited, it must be a deliberate refactor that moves grid mount AND its data callbacks behind a shared tab-activation gate together, with tests asserting At-Risk/Expansion still populate on first open.

### 2026-06-18 — Loading state lives in app.index_string, not the Dash layout
- **Why:** Anything placed in `app.layout` only appears after the Dash renderer hydrates — which is the exact multi-second window being covered for. Injecting the overlay as static HTML/CSS into `index_string` (before `{%app_entry%}`) makes the browser paint branded content on the first frame, independent of the renderer. The overlay clears itself by watching the DOM for the rendered Plotly chart, not via a Dash callback (a callback can't run until the thing it would hide is already gone).
- **Scope:** spinrate cold-link first paint. Pattern applies to any Dash tool sent as a cold link where hydration latency is visible.
- **Do not:** Move the loading state into the Dash layout or make it depend on the Dash renderer/clientside callbacks being ready. Keep the clearing logic a plain DOM watcher with a safety timeout.

### 2026-06-17 — Push heavy aggregation to SQL for memory-constrained VMs
- **Why:** The at-risk trend calculation loaded ~1.2M raw scan rows for OLS regression, causing OOM on a 1024MB Fly.io VM. Pushing GROUP BY to SQL returns ~600 rows — same analytical result, 2000x less memory. The OLS logic operates on quarterly SPPD either way.
- **Scope:** Any Cinderhaven-backed view that needs multi-quarter trend analysis. Applies to at-risk and any future view that runs regressions over historical data.
- **Do not:** Load raw scan rows for trend/regression calculations on constrained VMs. Always aggregate to the grain the analysis needs (quarterly SPPD, monthly totals, etc.) in SQL before pulling into Python.

### 2026-06-17 — Migration protagonist uses real quadrant movers, not a star copy
- **Why:** The narrative's migration section was copying the star SKU's data and showing a generic "movement tells the story" paragraph. This gave no concrete example of quadrant migration. Querying two consecutive quarters and finding a SKU that actually changed quadrants makes the narrative data-driven end to end.
- **Scope:** Narrative intro in layout.py. Falls back to star copy when only single-quarter data is available (e.g., in tests with minimal fixtures).
- **Do not:** Hardcode a specific migrant SKU. The discovery is runtime — whichever SKU had the biggest rank_delta between the penultimate and final quarter in the filter range wins.

### 2026-06-17 — SPPD formula footer on every tab, not just quadrant
- **Why:** SPPD is the core metric across all four views. Users landing on Migration, Expansion, or At-Risk need the same definition context. Showing it only on quadrant created an inconsistency.
- **Scope:** All four view layout functions (quadrant, migration, expansion, at_risk). Uses the shared `SPPD_FORMULA` constant from constants.py.
- **Do not:** Remove from any tab. If a view uses SPPD (directly or derived), it gets the footer.

### 2026-06-16 — Call .tolist() on all pandas Series passed to Plotly traces
- **Why:** Plotly Python 6.0 binary-encodes numpy arrays as `{dtype, bdata}` which Plotly.js 3.6.0 (bundled with Dash 3.x) cannot decode, rendering charts empty. Converting to Python lists forces JSON-array serialization.
- **Scope:** Every `go.Scatter()`, `go.Bar()`, or similar Plotly trace constructor in any Dash 3.x app using Plotly 6.0. Applies to x, y, customdata, marker.size, marker.color, and any other array property.
- **Do not:** Pass raw pandas Series or numpy arrays directly to Plotly trace constructors. Always call `.tolist()` first.

### 2026-06-16 — Cast Decimal to float at the data layer, not in views
- **Why:** psycopg2 returns Postgres `numeric` columns as Python `Decimal`. Plotly 6.0 rejects non-float arrays. Patching individual view functions would require N fixes across N views and miss future views. Casting in `_execute_query()` fixes it once for all consumers.
- **Scope:** All Cinderhaven-backed Dash tools using psycopg2 + Plotly 6.0. Apply the same pattern to Doormath and future tools.
- **Do not:** Cast in individual view functions, calculation functions, or chart-building functions. The conversion belongs at the data boundary.

### 2026-06-15 — SSOT architecture: no tool-to-tool pipeline
- **Why:** Each tool in the 5-tool suite queries the Cinderhaven data platform independently. No tool consumes another tool's output. This keeps tools independently deployable, testable, and debuggable. If doormath changes its internals, spinrate doesn't break.
- **Scope:** All 5 tools in the sales analytics suite.
- **Do not:** Create intermediate tables or views that one tool writes and another reads. If two tools need the same derived metric, the calculation lives in the SSOT's dbt mart layer.

### 2026-06-15 — Smart defaults over option overload
- **Why:** C-suite audience spends ~90 seconds. Multiple toggles and combinations create an analyst's tool, not an executive's insight. The tool opens with the most compelling default; deeper options are behind a customize toggle.
- **Scope:** All interactive views in spinrate (migration periods, viz modes). Consider for other portfolio tools.
- **Do not:** Show all options equally visible on first load. The default must tell the story without any user action.

### 2026-06-15 — Runtime protagonist discovery (not hardcoded)
- **Why:** The plan specified "static HTML" with protagonist SKUs from the SSOT, but hardcoding specific SKU IDs would break when the SSOT data changes. Instead, the narrative queries the database at page load and picks the best exemplar for each quadrant archetype dynamically. Falls back to a generic intro if the database is unreachable or has no good exemplars.
- **Scope:** Narrative section in layout.py.
- **Do not:** Hardcode SKU IDs in the narrative. The data-driven approach ensures the narrative always reflects current reality.

### 2026-06-15 — Three-tier at-risk scoring (level × trend)
- **Why:** A binary "at risk / not at risk" flag loses the distinction between flat-but-low (fix on your timeline) and declining (act now before the buyer does). Adding the watchlist tier (above median but declining) catches problems before they cross the threshold.
- **Scope:** At-risk list in spinrate. Pattern may apply to other tools that surface risk.
- **Do not:** Collapse to a single score or binary flag. The three tiers have distinct action imperatives.
