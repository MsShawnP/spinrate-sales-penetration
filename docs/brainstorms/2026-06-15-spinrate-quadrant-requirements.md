---
date: 2026-06-15
topic: spinrate-quadrant
---

# Spinrate: Penetration × Velocity Quadrant

## Summary

An interactive dashboard deployed to a lailarallc.com subdomain that plots Cinderhaven SKUs on a penetration × velocity quadrant. A narrative intro walks C-suite visitors through 5 protagonist SKUs, then hands off to four interactive views: the quadrant chart, a migration view, a three-benchmark expansion case list, and a three-tiered at-risk list — all querying the Cinderhaven SSOT.

---

## Problem Frame

Total sales hide whether growth comes from being in more stores or selling faster in existing ones. Two items can post identical dollars — one in 90% of doors barely moving, the other in 25% of doors flying off the shelf. They need opposite strategies: the first needs a velocity fix or a rationalization conversation; the second needs more doors.

This is the chart buyers use against suppliers — "your velocity doesn't justify your facings." A brand that walks in with its own quadrant analysis controls the conversation instead of reacting to it. For the Lailara portfolio, this is the flagship tool: the one C-suite visitors will spend 90 seconds with to decide if the work is credible. It is tool #2 in a 5-tool sales analytics suite that will anchor a pillar content piece.

---

## Actors

- A1. Portfolio visitor: C-suite or C-suite-adjacent prospective client. Not an analyst — expects legibility without jargon or training. Spends roughly 90 seconds before forming a credibility judgment.
- A2. Cinderhaven SSOT: Postgres database (dbt mart layer) providing POS, distribution, and benchmark data. Shared across multiple Lailara tools.

---

## Key Flows

- F1. First visit (guided)
  - **Trigger:** Visitor lands on the subdomain
  - **Actors:** A1
  - **Steps:** (1) Visitor reads the narrative intro, which walks through 5 protagonist SKUs — one per quadrant archetype plus a migration story. (2) Each protagonist is introduced with its quadrant position and strategic implication in business language. (3) Below the narrative, the interactive quadrant chart is already visible and populated. (4) Visitor scrolls past the narrative into the interactive section and begins exploring.
  - **Outcome:** Visitor understands the quadrant framework and what each position means strategically before touching controls.
  - **Covered by:** R1, R2, R3

- F2. Free exploration
  - **Trigger:** Visitor reaches the interactive section (or returns directly)
  - **Actors:** A1
  - **Steps:** (1) Visitor sees the quadrant chart with all SKUs plotted. (2) Visitor filters by banner, region, or time window. (3) Visitor inspects individual SKUs — detail is easy to see and understand without a magnifying glass or multiple navigations. (4) Visitor navigates to migration view, expansion cases, or at-risk list.
  - **Outcome:** Visitor can self-serve any question about which items are where and why.
  - **Covered by:** R4, R5, R6, R7, R8, R9, R10, R11

---

## Requirements

**Narrative intro**

- R1. A written narrative section sits above the interactive tools. It introduces the quadrant framework and walks through up to 5 protagonist SKUs using business language a C-suite visitor understands without analyst background.
- R2. The 5 protagonist SKUs include at least one from each quadrant archetype (star, hidden gem, wide-but-dead, question mark) plus a 5th that migrates quadrants between periods.
- R3. The narrative uses the migration view's default visualization (quarter-over-quarter, arrow overlay) to illustrate the migration protagonist's story.

**Quadrant chart**

- R4. X-axis is distribution penetration (ACV% or door %). Y-axis is velocity (SPPD). Bubble size is total dollars.
- R5. Quadrant dividing lines are labeled: stars (high/high), hidden gems (low dist/high velocity), wide but dead (high dist/low velocity), question marks (low/low).
- R6. Raw SPPD is the default y-axis mode. An indexed mode (item SPPD ÷ category median SPPD) is available as a toggle when category benchmarks exist. Indexed mode auto-sets the quadrant dividing line at 1.0.
- R7. Items with low door counts are visually flagged on the chart (dimmed bubbles, dashed outlines, or a "low confidence" marker). Door count appears in the detail view. No hard filter — all items remain visible.
- R8. Filters: banner/retailer, region, time window. Controls are inline near the chart.
- R9. Detail for any SKU must be easy to see and understand without a magnifying glass or multiple navigations. Implementation decides the interaction mechanism.
- R10. SPPD formula is explicitly defined and visible somewhere in the tool — not buried in a footnote.

**Migration view**

- R11. Shows which items moved quadrants between two time periods.
- R12. Three period comparison modes: quarter-over-quarter, user-selectable periods, and rolling 13-week. The tool opens with a smart default (QoQ with arrow overlay). Other period and visualization modes are available behind a customize toggle.
- R13. Multiple visualization modes are available (arrow overlay on quadrant, side-by-side quadrants, migration matrix/sankey). The narrative uses the default.

**Expansion case list**

- R14. Ranks hidden-gem SKUs by dollarized upside.
- R15. Shows three benchmark projections per SKU: what total dollars would be if distribution rose to (a) the category median, (b) 75th percentile, and (c) category leader. Per-SKU guidance indicates which benchmark tells the strongest story.
- R16. Items below a minimum distribution threshold are excluded from this list (the low-door-count safeguard from R7 — items too thinly distributed to rank as credible expansion candidates).

**At-risk list**

- R17. Scores items on two dimensions: level (velocity vs category median) and trend (velocity direction over the trailing N periods).
- R18. Three urgency tiers: (a) below median + declining velocity → "act now before the next review"; (b) below median + flat velocity → "fix or rationalize on your timeline"; (c) above median + declining velocity → "watchlist — not at-risk yet but headed there."
- R19. The list surfaces which signal is firing per SKU (level, trend, or both) so the user gets three actionable reads per item, not a binary flag.
- R20. The watchlist tier (above median + declining) appears separately or below the main at-risk tiers.

**Data and calculations**

- R21. All data comes from the Cinderhaven SSOT (Postgres, dbt mart layer). No tool-to-tool pipeline — spinrate queries the same database doormath uses, independently.
- R22. Key tables: `fct_scan_data` (POS: sku × store × week, units_sold, dollars_sold), `fct_distribution` (authorization history), `dim_stores` (640 doors, volume tiers), `dim_category_benchmarks`.

**Deployment and design**

- R23. Deployed to a lailarallc.com subdomain.
- R24. Follows the Lailara design system (colors, typography, chart rules, interaction patterns).

---

## Acceptance Examples

- AE1. **Covers R7, R16.** Given a SKU authorized in only 3 stores with high SPPD, when viewing the quadrant chart, the SKU appears as a visually flagged (dimmed/dashed) bubble in the hidden-gems quadrant with door count visible in detail. When viewing the expansion case list, the same SKU does not appear.
- AE2. **Covers R17, R18, R19.** Given a SKU with velocity below category median and declining over the last 4 quarters, when viewing the at-risk list, it appears in the top tier ("act now") with both level and trend signals surfaced.
- AE3. **Covers R17, R18, R20.** Given a SKU with velocity above category median but declining over the last 4 quarters, when viewing the at-risk list, it appears in the watchlist tier (separate from the main at-risk items) with the trend signal surfaced.
- AE4. **Covers R6.** Given category benchmarks are available, when the user toggles to indexed SPPD mode, the y-axis rescales to show item SPPD ÷ category median SPPD, and the horizontal quadrant dividing line moves to 1.0.
- AE5. **Covers R15.** Given a hidden-gem SKU currently in 25% of doors with high velocity, the expansion case list shows three rows: projected dollars at category median penetration, at 75th percentile, and at category-leader penetration — with guidance indicating which projection is most compelling for this SKU.

---

## Success Criteria

- A C-suite visitor who has never seen the tool can read the narrative intro, understand what each quadrant means, and form a strategic read on any SKU within 90 seconds.
- All four views (quadrant chart, migration, expansion cases, at-risk list) are functional and tell a coherent story using Cinderhaven data.
- The Cinderhaven synthetic data includes clear protagonist items — each quadrant archetype is immediately identifiable without hunting.
- `ce-plan` can proceed to implementation without needing to invent any product behavior, interaction model, or scoring logic.

---

## Scope Boundaries

- No bring-your-own-data or CSV upload — this is a portfolio demo on Cinderhaven data
- No blog post or pillar content piece — the in-tool narrative is v1; external content is separate
- No tool-to-tool pipeline — spinrate queries the SSOT independently, does not consume doormath output
- No print or PDF export — spinrate is interactive-first; doormath covers the print pattern
- No cross-product-line category comparison — indexed toggle compares within a category

---

## Key Decisions

- **Narrative as reading, not animation:** The guided intro is static written content with visual callouts above the interactive section — not a scrollytelling, step-through, or modal tour. Rationale: lowest friction for a C-suite visitor who may skip ahead.
- **Smart defaults over option overload:** Migration view opens with QoQ + arrow overlay. All period and viz options are available but tucked behind a customize toggle. Rationale: a CEO making 9 combinations is an analyst's tool; a CEO seeing the right default is an executive's insight.
- **Three-benchmark expansion projections:** Median, 75th percentile, and category leader shown side by side with per-SKU guidance on which tells the strongest story. Rationale: different SKUs have different realistic ceilings — a single benchmark either undersells some or oversells others.
- **Three-tier at-risk scoring:** Level × trend produces three urgency tiers with distinct action imperatives. Rationale: flat-but-low and declining are different urgencies requiring different responses.
- **No hard filter on the quadrant chart:** Low-distribution items are flagged visually but never hidden. Rationale: filtered-out items are invisible items, and the whole point is surfacing things that need attention.
- **SPPD made explicit:** The formula is defined in the tool itself, not just the narrative. Rationale: "the most commonly miscalculated metric in the building."

---

## Dependencies / Assumptions

- Cinderhaven data platform is operational with `fct_scan_data`, `fct_distribution`, `dim_stores`, and `dim_category_benchmarks` populated (verified: 41 raw tables, 27 mart tables, 437 dbt tests passing as of 2026-06-13).
- Doormath data model is stable (confirmed: finishing PDF export, data model set).
- Cinderhaven synthetic data already has deliberate protagonist items per quadrant archetype, or they will be seeded during implementation.
- Volume tier weights (A=3, B=2, C=1) from the doormath store universe are the basis for ACV% calculation.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4][Technical] Whether x-axis uses ACV% or raw door % as the default — both are available; implementation should pick the one that tells a clearer story with Cinderhaven data.
- [Affects R12][Technical] What specific default period and visualization the migration view opens with — QoQ + arrow overlay is the product decision; exact quarter boundaries and animation behavior are implementation.
- [Affects R16][Technical] What minimum distribution threshold qualifies for the expansion case list exclusion — needs to be calibrated against Cinderhaven data distribution.
- [Affects R17][Technical] How many trailing periods ("last N") define the velocity trend for at-risk scoring.
- [Affects R23][Needs research] Stack selection — interactive dashboard framework, hosting approach, data connection pattern.
- [Affects R2][Needs research] Whether Cinderhaven synthetic data already has protagonist items per quadrant or whether they need to be seeded.
