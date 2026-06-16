# Decisions — Spinrate Sales Penetration

*Durable choices with rationale. Updated as decisions are made.*

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
