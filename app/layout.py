"""Layout assembly — brand frame, tab navigation, filter bar, and content area."""

import json
import logging

import numpy as np
import pandas as pd
from dash import Input, Output, callback, dcc, html

logger = logging.getLogger(__name__)

from app import lailara_frame
from app.app import app
from app.calculations import calculate_acv_pct, calculate_sppd_from_agg, classify_quadrant, days_in_quarter_range
from app.constants import (
    CHICAGO_20,
    FONT_SANS,
    FONT_SERIF,
    INK,
    TEXT_SECONDARY,
    fmt_dollars,
    fmt_number,
    fmt_pct,
)
from app.filters import (
    DEFAULT_FILTER_STATE,
    build_empty_state,
    build_filter_bar,
    register_filter_callbacks,
)
from app.views import at_risk, expansion, migration, quadrant

TAB_LABELS = ["Quadrant", "Migration", "Expansion Cases", "At-Risk"]
TAB_IDS = ["quadrant", "migration", "expansion", "at-risk"]


def _build_tabs():
    """Build the dcc.Tabs component with 4 view tabs."""
    return dcc.Tabs(
        id="main-tabs",
        value="quadrant",
        children=[
            dcc.Tab(
                label=label,
                value=value,
                className="custom-tab",
                selected_className="custom-tab--selected",
            )
            for label, value in zip(TAB_LABELS, TAB_IDS)
        ],
        className="custom-tabs",
    )


def _build_content_area():
    """Build the loading-wrapped content area."""
    return dcc.Loading(
        id="tab-content-loading",
        type="default",
        color=CHICAGO_20,
        children=html.Div(id="tab-content"),
    )


def _build_narrative_section():
    """Narrative intro as a collapsible panel below the dashboard views."""
    return html.Details(
        [
            html.Summary(
                "Read the strategic narrative",
                className="narrative-toggle",
            ),
            html.Div(id="narrative-section", className="narrative-section"),
        ],
        className="narrative-details",
    )


# ── Protagonist discovery ────────────────────────────────────────


def _find_protagonists(scan_agg, dist_df, stores_df, products_df, filters=None,
                       prev_q_agg=None, end_q_agg=None):
    """Find the best exemplar SKU for each quadrant archetype.

    Returns a dict with keys: star, hidden_gem, wide_but_dead,
    question_mark, migration. Each value is a dict with sku,
    product_name, sppd, acv_pct, dollars, door_count. Returns
    empty dict if data is insufficient.

    prev_q_agg / end_q_agg: optional per-quarter aggregated scan data
    for migration protagonist discovery. If omitted, migration is skipped.
    """
    if scan_agg.empty or dist_df.empty or stores_df.empty:
        return {}

    filters = filters or {}
    start_q = filters.get("start_quarter", "Q1 2025")
    end_q = filters.get("end_quarter", "Q4 2025")
    days = days_in_quarter_range(start_q, end_q)
    sppd_df = calculate_sppd_from_agg(scan_agg, days)
    acv_df = calculate_acv_pct(dist_df, stores_df)

    if sppd_df.empty or acv_df.empty:
        return {}

    merged = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
    merged = merged.merge(
        products_df[["sku", "product_name"]], on="sku", how="left"
    )

    dollars = scan_agg[["sku", "total_dollars"]].rename(columns={"total_dollars": "dollars"})
    merged = merged.merge(dollars, on="sku", how="left")
    merged["dollars"] = merged["dollars"].fillna(0)
    merged["product_name"] = merged["product_name"].fillna(merged["sku"])

    median_sppd = merged["sppd"].median()
    median_acv = merged["acv_pct"].median()

    protagonists = {}

    # Star: high ACV% + high SPPD, pick the one with highest dollars.
    stars = merged[(merged["sppd"] >= median_sppd) & (merged["acv_pct"] >= median_acv)]
    if not stars.empty:
        best = stars.sort_values("dollars", ascending=False).iloc[0]
        protagonists["star"] = _row_to_dict(best)

    # Hidden gem: low ACV% + high SPPD.
    gems = merged[(merged["sppd"] >= median_sppd) & (merged["acv_pct"] < median_acv)]
    if not gems.empty:
        best = gems.sort_values("sppd", ascending=False).iloc[0]
        protagonists["hidden_gem"] = _row_to_dict(best)

    # Wide but dead: high ACV% + low SPPD.
    wide = merged[(merged["sppd"] < median_sppd) & (merged["acv_pct"] >= median_acv)]
    if not wide.empty:
        best = wide.sort_values("acv_pct", ascending=False).iloc[0]
        protagonists["wide_but_dead"] = _row_to_dict(best)

    # Question mark: low ACV% + low SPPD.
    questions = merged[(merged["sppd"] < median_sppd) & (merged["acv_pct"] < median_acv)]
    if not questions.empty:
        best = questions.sort_values("dollars", ascending=True).iloc[0]
        protagonists["question_mark"] = _row_to_dict(best)

    # Migration story: find a SKU that actually changed quadrants.
    # Falls back to the star if no real migration found (single-quarter data).
    end_q = (filters or {}).get("end_quarter", "Q4 2025")
    prev_q = _prev_quarter(end_q)
    migration_prot = _find_migration_protagonist(
        prev_q_agg, end_q_agg, dist_df, stores_df, products_df,
        median_sppd, median_acv,
        prev_q_label=prev_q, end_q_label=end_q,
    )
    if migration_prot:
        protagonists["migration"] = migration_prot
    elif "star" in protagonists:
        protagonists["migration"] = protagonists["star"].copy()

    return protagonists


def _row_to_dict(row):
    return {
        "sku": row["sku"],
        "product_name": row["product_name"],
        "sppd": float(row["sppd"]),
        "acv_pct": float(row["acv_pct"]),
        "dollars": float(row["dollars"]),
        "door_count": int(row["door_count"]),
    }


def _prev_quarter(quarter_str):
    """Return the quarter before the given one, e.g. 'Q4 2025' -> 'Q3 2025'."""
    q, year = quarter_str.split()
    q_num = int(q[1])
    if q_num == 1:
        return f"Q4 {int(year) - 1}"
    return f"Q{q_num - 1} {year}"


def _quarter_date_range(quarter_str):
    """Return (start_date, end_date) strings for a single quarter."""
    q, year = quarter_str.split()
    q_num = int(q[1])
    start_month = (q_num - 1) * 3 + 1
    end_month = q_num * 3
    end_day = 31 if end_month in (3, 12) else 30
    return (f"{year}-{start_month:02d}-01", f"{year}-{end_month:02d}-{end_day:02d}")


_QUADRANT_RANK = {"Stars": 4, "Hidden Gems": 3, "Wide but Dead": 2, "Question Marks": 1}


def _find_migration_protagonist(prev_q_agg, end_q_agg, dist_df, stores_df,
                                 products_df, median_sppd, median_acv,
                                 prev_q_label="", end_q_label=""):
    """Find a SKU that changed quadrants between two consecutive quarters.

    Takes per-quarter pre-aggregated scan data to avoid pulling row-level data.
    Returns None if either quarter's data is missing.
    """
    if prev_q_agg is None or end_q_agg is None:
        return None
    if prev_q_agg.empty or end_q_agg.empty:
        return None

    days_q = 91
    sppd_prev = calculate_sppd_from_agg(prev_q_agg, days_q)
    sppd_end = calculate_sppd_from_agg(end_q_agg, days_q)
    acv_df = calculate_acv_pct(dist_df, stores_df)

    if sppd_prev.empty or sppd_end.empty or acv_df.empty:
        return None

    prev_m = sppd_prev.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
    end_m = sppd_end.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")

    prev_m["quadrant"] = prev_m.apply(
        lambda r: classify_quadrant(r["sppd"], r["acv_pct"], median_sppd, median_acv), axis=1
    )
    end_m["quadrant"] = end_m.apply(
        lambda r: classify_quadrant(r["sppd"], r["acv_pct"], median_sppd, median_acv), axis=1
    )

    comp = prev_m[["sku", "sppd", "acv_pct", "quadrant"]].merge(
        end_m[["sku", "sppd", "acv_pct", "quadrant"]],
        on="sku", suffixes=("_p1", "_p2"),
    )
    movers = comp[comp["quadrant_p1"] != comp["quadrant_p2"]].copy()

    if movers.empty:
        return None

    movers["rank_delta"] = (
        movers["quadrant_p2"].map(_QUADRANT_RANK).fillna(0)
        - movers["quadrant_p1"].map(_QUADRANT_RANK).fillna(0)
    )
    best = movers.loc[movers["rank_delta"].abs().idxmax()]

    name_row = products_df[products_df["sku"] == best["sku"]]
    product_name = name_row.iloc[0]["product_name"] if not name_row.empty else best["sku"]

    return {
        "sku": best["sku"],
        "product_name": product_name,
        "sppd_p1": float(best["sppd_p1"]),
        "sppd_p2": float(best["sppd_p2"]),
        "acv_pct_p1": float(best["acv_pct_p1"]),
        "acv_pct_p2": float(best["acv_pct_p2"]),
        "quadrant_p1": best["quadrant_p1"],
        "quadrant_p2": best["quadrant_p2"],
        "q1_label": prev_q_label,
        "q2_label": end_q_label,
    }


# ── Narrative rendering ──────────────────────────────────────────


def _render_narrative(protagonists):
    """Build the narrative HTML from protagonist data."""
    if not protagonists:
        return _fallback_narrative()

    children = [
        html.H2(
            "How every item earns its shelf space",
            className="narrative-title",
        ),
        html.P(
            "Total sales hide whether growth comes from being in more stores "
            "or selling faster in existing ones. Two items can post identical "
            "revenue — one in 90% of stores barely moving, the other in 25% "
            "flying off the shelf — yet they need opposite strategies. "
            "The quadrant below separates distribution reach from selling speed "
            "to surface which items deserve more shelf space, which need a velocity "
            "fix, and which are quietly fading.",
            className="narrative-body",
        ),
    ]

    if "star" in protagonists:
        p = protagonists["star"]
        children.append(
            _protagonist_block(
                "The star",
                f"{p['product_name']} sits in {fmt_pct(p['acv_pct'])} of weighted "
                f"distribution and moves at {p['sppd']:.4f} units per store per day — "
                f"above the category median on both axes. "
                f"At {fmt_dollars(p['dollars'])} this quarter across "
                f"{fmt_number(p['door_count'])} doors, the priority is protecting "
                f"supply and negotiating for additional facings.",
            )
        )

    if "hidden_gem" in protagonists:
        p = protagonists["hidden_gem"]
        children.append(
            _protagonist_block(
                "The hidden gem",
                f"{p['product_name']} flies off the shelf wherever it is authorized — "
                f"{p['sppd']:.4f} units per store per day — but sits in only "
                f"{fmt_pct(p['acv_pct'])} of weighted distribution. "
                f"The expansion case writes itself: every new door added at "
                f"current velocity is incremental revenue.",
            )
        )

    if "wide_but_dead" in protagonists:
        p = protagonists["wide_but_dead"]
        children.append(
            _protagonist_block(
                "Wide but dead",
                f"{p['product_name']} reaches {fmt_pct(p['acv_pct'])} of weighted "
                f"distribution — broad reach — but moves at only "
                f"{p['sppd']:.4f} units per store per day, below the category "
                f"median. The shelf space it occupies could go to a faster mover. "
                f"The question: fix the velocity or rationalize the distribution.",
            )
        )

    if "question_mark" in protagonists:
        p = protagonists["question_mark"]
        children.append(
            _protagonist_block(
                "The question mark",
                f"{p['product_name']} is below median on both axes — "
                f"{fmt_pct(p['acv_pct'])} distribution, {p['sppd']:.4f} "
                f"velocity. It is not earning shelf space on reach or speed. "
                f"The options: reposition, find the niche where it works, "
                f"or cut it.",
            )
        )

    if "migration" in protagonists:
        p = protagonists["migration"]
        if "quadrant_p1" in p:
            children.append(
                _protagonist_block(
                    "The mover",
                    f"{p['product_name']} was classified "
                    f"{p['quadrant_p1']} in {p['q1_label']} "
                    f"({p['sppd_p1']:.4f} velocity, "
                    f"{fmt_pct(p['acv_pct_p1'])} distribution) "
                    f"and shifted to {p['quadrant_p2']} by {p['q2_label']} "
                    f"({p['sppd_p2']:.4f} velocity, "
                    f"{fmt_pct(p['acv_pct_p2'])} distribution). "
                    f"The Migration tab tracks these moves for every SKU "
                    f"in the portfolio.",
                )
            )
        else:
            children.append(
                _protagonist_block(
                    "Movement tells the story",
                    "A single snapshot hides momentum. The migration view tracks "
                    "how items shift between quadrants over time. "
                    "Select the Migration tab below to see quarter-over-quarter "
                    "arrows for every SKU in the portfolio.",
                )
            )

    return html.Div(children, className="narrative-content")


def _protagonist_block(label, text):
    return html.Div(
        [
            html.H3(label, className="narrative-archetype-label"),
            html.P(text, className="narrative-body"),
        ],
        className="narrative-protagonist",
    )


def _fallback_narrative():
    """Generic narrative when no protagonist data is available."""
    return html.Div(
        [
            html.H2(
                "How every item earns its shelf space",
                className="narrative-title",
            ),
            html.P(
                "Total sales hide whether growth comes from being in more stores "
                "or selling faster in existing ones. The quadrant chart below "
                "separates distribution reach from selling speed to surface "
                "which items deserve more shelf space, which need a velocity fix, "
                "and which are quietly fading. Select filters above and explore "
                "the interactive views below.",
                className="narrative-body",
            ),
        ],
        className="narrative-content",
    )


# ── register_layout ──────────────────────────────────────────────


def register_layout():
    """Set app.layout and register all callbacks."""
    inner_layout = html.Div(
        [
            dcc.Store(
                id="filter-state", storage_type="session", data=json.dumps(DEFAULT_FILTER_STATE)
            ),
            dcc.Store(id="selected-sku", storage_type="memory"),
            html.Div(
                [
                    _build_tabs(),
                    build_filter_bar(),
                    build_empty_state(),
                    _build_content_area(),
                ],
                className="lailara-container",
            ),
            _build_narrative_section(),
        ]
    )

    app.layout = lailara_frame.wrap(
        inner_layout,
        tool_name="Spin Rate",
        footer_note="Penetration × velocity quadrant analysis for CPG brands.",
        no_container=True,
    )

    register_filter_callbacks()
    quadrant.register_callbacks()
    migration.register_callbacks()
    expansion.register_callbacks()
    at_risk.register_callbacks()

    @callback(
        Output("narrative-section", "children"),
        Input("filter-state", "data"),
    )
    def _populate_narrative(filter_json):
        """Populate narrative with protagonist SKUs from database."""
        try:
            from app import db
            filters = json.loads(filter_json) if filter_json else {}

            scan_agg = db.get_scan_data_agg(filters)
            dist_df = db.get_distribution(filters)
            stores_df = db.get_stores()
            products_df = db.get_products()

            # Fetch per-quarter agg data for migration protagonist.
            end_q = filters.get("end_quarter", "Q4 2025")
            prev_q = _prev_quarter(end_q)
            base_filters = {k: v for k, v in filters.items()
                            if k not in ("start_quarter", "end_quarter")}
            prev_q_agg = db.get_scan_data_agg({**base_filters, "start_quarter": prev_q, "end_quarter": prev_q})
            end_q_agg = db.get_scan_data_agg({**base_filters, "start_quarter": end_q, "end_quarter": end_q})

            protagonists = _find_protagonists(
                scan_agg, dist_df, stores_df, products_df, filters,
                prev_q_agg=prev_q_agg, end_q_agg=end_q_agg,
            )
            return _render_narrative(protagonists)
        except Exception:
            logger.exception("Narrative callback failed")
            return _fallback_narrative()

    @callback(
        Output("tab-content", "children"),
        Input("main-tabs", "value"),
    )
    def _render_tab(tab_value):
        """Render the selected view's layout."""
        if tab_value == "quadrant":
            return quadrant.layout()
        elif tab_value == "migration":
            return migration.layout()
        elif tab_value == "expansion":
            return expansion.layout()
        elif tab_value == "at-risk":
            return at_risk.layout()
        return html.Div("Unknown tab.")
