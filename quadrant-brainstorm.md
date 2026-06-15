# Penetration × Velocity Quadrant

**Working title:** `quadrant` (alts: `spinrate`, `four-corners`)

## Business question this tool answers

> "Is our growth coming from being in more stores, or from selling faster in the stores we're in — and which items are wide but dead?"

Total sales hide the distinction. Two items can post identical dollars where one is in 90% of doors barely moving and the other is in 25% of doors flying off the shelf. They need opposite strategies: the first needs a velocity fix (placement, price, merchandising) or a rationalization conversation; the second needs more doors. The quadrant makes the distinction impossible to miss.

## Why this is the flagship

This is the chart executives actually picture when they say "penetration." It's also the chart buyers use against suppliers — "your velocity doesn't justify your facings" — so a brand that walks in with its own quadrant analysis controls the conversation instead of reacting to it.

## Core construction

- **X-axis:** distribution penetration (ACV% or door %, from tool #1)
- **Y-axis:** velocity — sales per point of distribution (SPPD) or units/store/week
- **Bubble size:** total dollars (so big-but-mediocre items are visible)
- **Quadrants:**
  - High dist / high velocity → **stars** — protect and supply
  - Low dist / high velocity → **hidden gems** — the expansion pitch
  - High dist / low velocity → **wide but dead** — fix or rationalize before the buyer does it for you
  - Low dist / low velocity → **question marks** — kill, fix, or niche

## Inputs

- Outputs of tool #1 (ACV%, door counts by item) — built; schema available
- POS sales (item × store × week)
- Optional: category benchmarks so velocity reads as relative, not absolute

## Outputs (all v1)

1. **Interactive quadrant chart** — item-level, filterable by banner/region/time window, detail easy to see without magnifying glass or multiple navigations
2. **Quadrant migration view** — which items moved quadrants vs last period (the story is in the movement)
3. **Ranked expansion case list** — hidden gems with dollarized upside at three benchmarks (median, 75th percentile, category leader) with per-SKU guidance on which tells the strongest story
4. **Ranked at-risk list** — wide-but-dead items scored on level (vs category median) and trend (velocity direction), producing three urgency tiers

## Output format

Interactive dashboard. The quadrant demands hover/filter interactivity — static Quarto HTML doesn't serve it.

## User experience

- **Narrative intro then handoff:** Written narrative section above the chart walks through 5 protagonist SKUs (one per quadrant archetype + one migration story). Static content with visual callouts — not scrollytelling or step-through. Below the narrative, the interactive tools are already visible and populated.
- **Smart defaults:** Migration view opens with QoQ + arrow overlay. Other period modes (user-selectable, rolling 13-week) and viz modes (side-by-side, migration matrix) are behind a customize toggle.
- **At-risk tiers:** Below median + declining (act now), below median + flat (fix on your timeline), above median + declining (watchlist). Each SKU shows which signal is firing.

## Cinderhaven angle

Design the synthetic data so each quadrant has a clear protagonist item — one star, one hidden gem with an obvious expansion story, one wide-but-dead SKU bleeding velocity, one question mark, plus a 5th item that migrates quadrants between periods. The blog post then walks each character through its strategy. This mirrors how the Product Data Health Audit used deliberate seeded defects.

## Scope notes

- Chart conventions carry over from the UCI work: palette constants, coord_cartesian for zoom, labeled medians
- SPPD definition needs to be stated explicitly in the report — it's the most commonly miscalculated metric in the building
- **Y-axis mode:** Raw SPPD as default; indexed to category median (item SPPD ÷ category median SPPD) as a toggle when category benchmarks are available. Raw stands alone without external data; indexed layers on for cross-category comparison and auto-sets the quadrant dividing line.
- Builds on tool #1's data model
- **Low-distribution SPPD handling:** Items with very low door counts (e.g., 3 flagship stores) can show inflated SPPD and fake a "hidden gem" signal. Two-layer approach: (1) on the quadrant chart, visually flag low-door-count items (dimmed bubbles, dashed outlines, or a "low confidence" marker) — keep them visible but signal caution, with door count in the tooltip; (2) on the expansion case list (output #3), apply a minimum distribution threshold to exclude low-door items from ranked recommendations. No hard filter on the chart itself — filtered-out items are invisible items, and the whole point is surfacing things that need attention.
- **Data source:** Cinderhaven SSOT (Postgres, dbt mart layer) — no tool-to-tool pipeline. Queries `fct_scan_data`, `fct_distribution`, `dim_stores`, `dim_category_benchmarks` independently.
- **Audience:** C-suite prospective clients. Must be legible in ~90 seconds without analyst background.
- **Deployment:** lailarallc.com subdomain.
- **Suite context:** Tool #2 of 5, with a planned pillar content piece across the suite.
