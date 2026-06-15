# Decisions — Spinrate Sales Penetration

*Durable choices with rationale. Updated as decisions are made.*

### 2026-06-15 — SSOT architecture: no tool-to-tool pipeline
- **Why:** Each tool in the 5-tool suite queries the Cinderhaven data platform independently. No tool consumes another tool's output. This keeps tools independently deployable, testable, and debuggable. If doormath changes its internals, spinrate doesn't break.
- **Scope:** All 5 tools in the sales analytics suite.
- **Do not:** Create intermediate tables or views that one tool writes and another reads. If two tools need the same derived metric, the calculation lives in the SSOT's dbt mart layer.

### 2026-06-15 — Smart defaults over option overload
- **Why:** C-suite audience spends ~90 seconds. Multiple toggles and combinations create an analyst's tool, not an executive's insight. The tool opens with the most compelling default; deeper options are behind a customize toggle.
- **Scope:** All interactive views in spinrate (migration periods, viz modes). Consider for other portfolio tools.
- **Do not:** Show all options equally visible on first load. The default must tell the story without any user action.

### 2026-06-15 — Three-tier at-risk scoring (level × trend)
- **Why:** A binary "at risk / not at risk" flag loses the distinction between flat-but-low (fix on your timeline) and declining (act now before the buyer does). Adding the watchlist tier (above median but declining) catches problems before they cross the threshold.
- **Scope:** At-risk list in spinrate. Pattern may apply to other tools that surface risk.
- **Do not:** Collapse to a single score or binary flag. The three tiers have distinct action imperatives.
