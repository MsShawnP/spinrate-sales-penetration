# Spinrate Sales Penetration — Distribution vs. Velocity, Made Impossible to Miss

**Live:** https://spinrate.lailarallc.com

Total sales hide whether growth comes from being in more stores or selling faster in existing ones. Two items can post identical dollars — one in 90% of doors barely moving, the other in 25% of doors flying off the shelf. They need opposite strategies. The penetration × velocity quadrant makes the distinction impossible to miss.

![Quadrant dashboard](screenshots/Dashboard.png)

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

## Why it matters

A topline sales report treats every dollar the same; a category buyer does not. Items that are everywhere but barely turning are the first casualties of a shelf reset, while fast-turning items stuck in a quarter of doors are the strongest expansion pitch a brand has. Separating the two — and putting a dollar figure on each expansion case — is the difference between walking into a buyer meeting with a defense and walking in with an ask.

## Cinderhaven context

Built on the Cinderhaven synthetic dataset — a ~$25M specialty food brand, 50 SKUs across 5 product lines and 6 contracted retailers. Data is synthetic; methodology and deliverables are real.

## Data contract

**Canonical baseline:** 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers (Walmart·Costco·Whole Foods·Sprouts·Kroger·Regional Group) · 10 channels (6 retail + UNFI·KeHE·DPI + DTC)

## Quick start

Requires Python 3.11+ and access to the Cinderhaven SSOT Postgres instance.

```
cp .env.example .env               # fill in DATABASE_URL
pip install packages/lailara-palette
pip install -e ".[dev]"
python wsgi.py                     # http://localhost:8050
pytest                             # run the test suite
```

Docker mirrors production:

```
docker build -t spinrate .
docker run -p 8050:8050 --env-file .env spinrate
```

## Tech stack

- **Application:** Dash 4.x, Plotly 6.x, Python 3.11
- **Data:** pandas 2.x, numpy, psycopg2 (Cinderhaven SSOT Postgres)
- **UI:** dash-ag-grid (tabular views), clientside JS callbacks (click-to-pin), vendored `lailara-palette` brand package
- **Deploy:** Gunicorn, Docker, Fly.io (shared-cpu-1x, iad region)

## License

MIT

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.
