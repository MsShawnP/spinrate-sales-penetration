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

1. **Interactive quadrant chart** — item-level, filterable by banner/region/time window, hover for detail
2. **Quadrant migration view** — which items moved quadrants vs last period (the story is in the movement)
3. **Ranked expansion case list** — hidden gems with dollarized upside if distribution rose to category-leader levels
4. **Ranked at-risk list** — wide-but-dead items with facings likely under review

## Output format

Interactive dashboard. The quadrant demands hover/filter interactivity — static Quarto HTML doesn't serve it.

## Cinderhaven angle

Design the synthetic data so each quadrant has a clear protagonist item — one star, one hidden gem with an obvious expansion story, one wide-but-dead SKU bleeding velocity, one question mark. The blog post then walks each character through its strategy. This mirrors how the Product Data Health Audit used deliberate seeded defects.

## Scope notes

- Chart conventions carry over from the UCI work: palette constants, coord_cartesian for zoom, labeled medians
- SPPD definition needs to be stated explicitly in the report — it's the most commonly miscalculated metric in the building
- Builds on tool #1's data model
