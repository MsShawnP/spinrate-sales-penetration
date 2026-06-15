"""Layout assembly — brand frame, tab navigation, filter bar, and content area."""

import json

import numpy as np
import pandas as pd
from dash import Input, Output, callback, dcc, html

from app import lailara_frame
from app.app import app
from app.calculations import calculate_acv_pct, calculate_sppd, days_in_quarter_range
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
    """Narrative intro section populated by callback on page load."""
    return html.Div(id="narrative-section", className="narrative-section")


# ── Protagonist discovery ────────────────────────────────────────


def _find_protagonists(scan_df, dist_df, stores_df, products_df):
    """Find the best exemplar SKU for each quadrant archetype.

    Returns a dict with keys: star, hidden_gem, wide_but_dead,
    question_mark, migration. Each value is a dict with sku,
    product_name, sppd, acv_pct, dollars, door_count. Returns
    empty dict if data is insufficient.
    """
    if scan_df.empty or dist_df.empty or stores_df.empty:
        return {}

    days = days_in_quarter_range("Q1 2025", "Q1 2025")
    sppd_df = calculate_sppd(scan_df, days)
    acv_df = calculate_acv_pct(dist_df, stores_df)

    if sppd_df.empty or acv_df.empty:
        return {}

    merged = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
    merged = merged.merge(
        products_df[["sku", "product_name"]], on="sku", how="left"
    )

    dollars = scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
    dollars.columns = ["sku", "dollars"]
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

    # Migration story: pick the star (most likely to have an interesting story).
    if "star" in protagonists:
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
        children.append(
            _protagonist_block(
                "Movement tells the story",
                f"A single snapshot hides momentum. The migration view tracks "
                f"how items shift between quadrants over time. An item that was "
                f"a question mark last quarter and is now a hidden gem demands "
                f"different action than one drifting the other way. "
                f"Select the Migration tab below to see quarter-over-quarter "
                f"arrows for every SKU in the portfolio.",
            )
        )

    children.append(
        html.P(
            "Explore the full dataset below.",
            className="narrative-transition",
        ),
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
            html.P(
                "Explore the full dataset below.",
                className="narrative-transition",
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
            _build_narrative_section(),
            html.Div(
                [
                    _build_tabs(),
                    build_filter_bar(),
                    build_empty_state(),
                    _build_content_area(),
                ],
                className="lailara-container",
            ),
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

            scan_df = db.get_scan_data(filters)
            dist_df = db.get_distribution(filters)
            stores_df = db.get_stores()
            products_df = db.get_products()

            protagonists = _find_protagonists(scan_df, dist_df, stores_df, products_df)
            return _render_narrative(protagonists)
        except Exception:
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
