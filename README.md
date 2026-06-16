# Spinrate Sales Penetration

Total sales hide whether growth comes from being in more stores or selling faster in existing ones. Two items can post identical dollars — one in 90% of doors barely moving, the other in 25% of doors flying off the shelf. They need opposite strategies. The penetration × velocity quadrant makes the distinction impossible to miss.

## Cinderhaven context

Built on the Cinderhaven synthetic dataset — a ~$25M specialty food brand, 50 SKUs across 5 product lines and 6 contracted retailers. Data is synthetic; methodology and deliverables are real.

## What it does

- **Interactive quadrant chart** — items plotted by distribution penetration (x) vs velocity/SPPD (y), bubble-sized by total dollars, filterable by banner/region/time window
- **Quadrant migration view** — which items moved quadrants vs last period
- **Ranked expansion case list** — hidden gems with dollarized upside if distribution rose to category-leader levels
- **Ranked at-risk list** — wide-but-dead items with facings likely under review

Four quadrants:
- **Stars** (high dist / high velocity) — protect and supply
- **Hidden gems** (low dist / high velocity) — the expansion pitch
- **Wide but dead** (high dist / low velocity) — fix or rationalize before the buyer does it for you
- **Question marks** (low dist / low velocity) — kill, fix, or niche

## Stack

- **Application:** Dash 3.x, Plotly 6.0, Python 3.11
- **Data:** pandas 2.x, numpy, psycopg2 (Cinderhaven SSOT Postgres)
- **UI:** dash-ag-grid (tabular views), clientside JS callbacks (click-to-pin)
- **Deploy:** Gunicorn, Docker, Fly.io (shared-cpu-1x, iad region)

## Data contract

**Canonical baseline:** 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers (Walmart·Costco·Whole Foods·Sprouts·Kroger·Regional Group) · 10 channels (6 retail + UNFI·KeHE·DPI + DTC)

## Run

```
TBD
```

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.
