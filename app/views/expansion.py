"""Expansion cases view — ranked hidden-gem SKUs with three benchmark projections.

Lists SKUs classified as Hidden Gems (high velocity, low distribution) and
projects dollarized upside at three distribution benchmarks: median, 75th
percentile, and category leader door counts.  Minimum distribution threshold
of 10 stores filters out items too thinly distributed for credible ranking.
"""

import json
import logging

import dash_ag_grid as dag
import numpy as np
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update

logger = logging.getLogger(__name__)

from app.app import app
from app.calculations import (
    calculate_acv_pct,
    calculate_expansion_upside,
    calculate_sppd,
    days_in_quarter_range,
)
from app.components import annotation_callout, dark_callout_card
from app.constants import (
    CHICAGO_20,
    FONT_SANS,
    FONT_SERIF,
    GRIDLINE,
    HK_35,
    INK,
    TEXT_SECONDARY,
    WHITE,
    fmt_dollars,
    fmt_number,
    fmt_pct,
)

# ── Configuration ─────────────────────────────────────────────────

# Minimum door count for a SKU to qualify for expansion ranking.
# Items below this threshold are too thinly distributed for credible
# projections (per plan R16, AE1).
MIN_DOOR_THRESHOLD = 10


# ── Data assembly ─────────────────────────────────────────────────


def build_expansion_data(filters):
    """Compute the ranked expansion table from current filter state.

    Returns a tuple (rows_df, summary_dict) where rows_df is a DataFrame
    of qualifying hidden-gem SKUs ranked by median-benchmark upside, and
    summary_dict contains aggregate stats for the header.

    Returns (empty DataFrame, empty dict) when no qualifying SKUs exist.
    """
    from app import db

    scan_df = db.get_scan_data(filters)
    dist_df = db.get_distribution(filters)
    stores_df = db.get_stores()
    benchmarks_df = db.get_benchmarks()
    products_df = db.get_products()

    if scan_df.empty or dist_df.empty or stores_df.empty:
        return pd.DataFrame(), {}

    start_q = filters.get("start_quarter", "Q1 2025")
    end_q = filters.get("end_quarter", "Q4 2025")
    days = days_in_quarter_range(start_q, end_q)

    sppd_df = calculate_sppd(scan_df, days)
    acv_df = calculate_acv_pct(dist_df, stores_df)

    if sppd_df.empty or acv_df.empty:
        return pd.DataFrame(), {}

    # Merge SPPD + ACV to classify quadrants.
    merged = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")

    if merged.empty:
        return pd.DataFrame(), {}

    # Compute medians for quadrant classification.
    median_sppd = merged["sppd"].median()
    median_acv = merged["acv_pct"].median()

    # Identify hidden gems: high velocity (>= median SPPD), low distribution (< median ACV%).
    hidden_gems = merged[
        (merged["sppd"] >= median_sppd) & (merged["acv_pct"] < median_acv)
    ].copy()

    # Apply minimum door count threshold.
    hidden_gems = hidden_gems[hidden_gems["door_count"] >= MIN_DOOR_THRESHOLD]

    if hidden_gems.empty:
        return pd.DataFrame(), {}

    # Compute expansion upside projections.
    upside_df = calculate_expansion_upside(
        sppd_df, dist_df, stores_df, products_df, benchmarks_df
    )

    if upside_df.empty:
        return pd.DataFrame(), {}

    # Filter upside to only hidden gems.
    gem_skus = set(hidden_gems["sku"].unique())
    upside_df = upside_df[upside_df["sku"].isin(gem_skus)].copy()

    if upside_df.empty:
        return pd.DataFrame(), {}

    # Exclude SKUs whose product line has no benchmarks (no peers).
    upside_df = upside_df.dropna(subset=["median_doors", "p75_doors", "leader_doors"])

    if upside_df.empty:
        return pd.DataFrame(), {}

    # Merge product names and ACV%.
    upside_df = upside_df.merge(
        products_df[["sku", "product_name"]], on="sku", how="left"
    )
    upside_df = upside_df.merge(
        acv_df[["sku", "acv_pct"]], on="sku", how="left"
    )

    # Total dollars from scan data.
    dollars = scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
    dollars.columns = ["sku", "current_dollars"]
    upside_df = upside_df.merge(dollars, on="sku", how="left")
    upside_df["current_dollars"] = upside_df["current_dollars"].fillna(0)

    # Generate guidance text per SKU based on ACV% position.
    upside_df["guidance"] = upside_df.apply(_generate_guidance, axis=1)

    # Sort by median-benchmark upside descending.
    upside_df = upside_df.sort_values("upside_median_dollars", ascending=False)

    # Fill missing product names.
    upside_df["product_name"] = upside_df["product_name"].fillna(upside_df["sku"])

    # Summary stats.
    summary = {
        "count": len(upside_df),
        "total_median_upside": upside_df["upside_median_dollars"].sum(),
        "total_p75_upside": upside_df["upside_p75_dollars"].sum(),
        "total_leader_upside": upside_df["upside_leader_dollars"].sum(),
    }

    return upside_df, summary


def _generate_guidance(row):
    """Return credibility guidance for a single SKU's benchmark projections.

    The guidance helps the sales team understand which benchmark is
    realistic vs aspirational based on the SKU's current distribution.
    """
    acv_pct = row.get("acv_pct", 0)
    current_doors = row.get("current_doors", 0)
    leader_doors = row.get("leader_doors", 0)

    # SKU is already at category-leading distribution.
    if current_doors >= leader_doors and leader_doors > 0:
        return "Already at category-leading distribution."

    if acv_pct >= 0.40:
        return "Strong base. 75th percentile is a credible near-term target."
    elif acv_pct >= 0.20:
        return "Solid base. Median benchmark is a realistic first milestone."
    elif acv_pct >= 0.10:
        return "Narrow distribution. Median is achievable; higher benchmarks are aspirational."
    else:
        return "Very limited distribution. All projections are aspirational until base expands."


# ── AG Grid column definitions ────────────────────────────────────

_COLUMN_DEFS = [
    {
        "field": "sku",
        "headerName": "SKU",
        "width": 130,
        "pinned": "left",
    },
    {
        "field": "product_name",
        "headerName": "Item Name",
        "width": 180,
        "tooltipField": "product_name",
    },
    {
        "field": "product_line",
        "headerName": "Product Line",
        "width": 140,
    },
    {
        "field": "acv_pct",
        "headerName": "ACV%",
        "width": 90,
        "valueFormatter": {"function": "d3.format('.1%')(params.value)"},
    },
    {
        "field": "current_sppd",
        "headerName": "SPPD",
        "width": 90,
        "valueFormatter": {"function": "d3.format('.4f')(params.value)"},
    },
    {
        "field": "current_dollars",
        "headerName": "Current $",
        "width": 110,
        "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
    },
    {
        "field": "upside_median_dollars",
        "headerName": "Upside @ Median",
        "headerTooltip": "Projected quarterly upside at peer-median door count",
        "width": 155,
        "sort": "desc",
        "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
        "cellStyle": {
            "fontWeight": "bold",
        },
    },
    {
        "field": "upside_p75_dollars",
        "headerName": "Upside @ 75th",
        "headerTooltip": "Projected quarterly upside at 75th-percentile door count",
        "width": 145,
        "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
    },
    {
        "field": "upside_leader_dollars",
        "headerName": "Upside @ Leader",
        "headerTooltip": "Projected quarterly upside at category-leader door count",
        "width": 155,
        "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
    },
    {
        "field": "guidance",
        "headerName": "Guidance",
        "width": 300,
        "tooltipField": "guidance",
        "cellStyle": {
            "color": TEXT_SECONDARY,
            "fontSize": "12px",
        },
    },
]


# ── Layout ────────────────────────────────────────────────────────


def layout():
    """Return the expansion cases view layout."""
    return html.Div(
        [
            # Summary header area.
            html.Div(id="expansion-summary"),
            # Annotation callout area.
            html.Div(id="expansion-annotation"),
            # AG Grid table.
            html.Div(
                dag.AgGrid(
                    id="expansion-grid",
                    columnDefs=_COLUMN_DEFS,
                    rowData=[],
                    defaultColDef={
                        "sortable": True,
                        "filter": True,
                        "resizable": True,
                    },
                    dashGridOptions={
                        "pagination": True,
                        "paginationPageSize": 25,
                        "rowSelection": {"mode": "singleRow"},
                        "animateRows": True,
                    },
                    style={"height": "500px", "width": "100%"},
                    className="ag-theme-alpine",
                ),
                **{"aria-label": "Expansion cases — hidden gems ranked by upside"},
            ),
            # Inline detail card (shown on row selection).
            html.Div(id="expansion-detail-card"),
            # Hidden store for expansion data (avoids recomputing for detail).
            dcc.Store(id="expansion-data-store", data="[]"),
        ],
    )


# ── Callbacks ─────────────────────────────────────────────────────


def register_callbacks():
    """Register all expansion view callbacks."""

    @callback(
        Output("expansion-grid", "rowData"),
        Output("expansion-summary", "children"),
        Output("expansion-annotation", "children"),
        Output("expansion-data-store", "data"),
        Input("filter-state", "data"),
        Input("main-tabs", "value"),
    )
    def _update_expansion_view(filter_json, active_tab):
        """Recompute expansion list when filters change."""
        if active_tab != "expansion":
            return no_update, no_update, no_update, no_update

        filters = json.loads(filter_json) if filter_json else {}

        try:
            rows_df, summary = build_expansion_data(filters)
        except Exception:
            logger.exception("Expansion view callback failed")
            return (
                [],
                _empty_message("Could not load expansion data."),
                [],
                "[]",
            )

        if rows_df.empty:
            return (
                [],
                _empty_message(
                    "No hidden-gem SKUs meet the minimum distribution threshold "
                    f"({MIN_DOOR_THRESHOLD} stores). Items below this threshold appear "
                    "on the quadrant chart but are too thinly distributed for credible "
                    "expansion ranking."
                ),
                [],
                "[]",
            )

        # Build row data for the grid.
        grid_columns = [
            "sku", "product_name", "product_line", "acv_pct",
            "current_sppd", "current_dollars",
            "current_doors", "median_doors", "p75_doors", "leader_doors",
            "upside_median_dollars", "upside_p75_dollars", "upside_leader_dollars",
            "guidance",
        ]
        row_data = rows_df[
            [c for c in grid_columns if c in rows_df.columns]
        ].to_dict("records")

        # Summary header.
        summary_children = html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            fmt_number(summary["count"]),
                            style={
                                "fontFamily": FONT_SERIF,
                                "fontSize": "36px",
                                "fontWeight": "700",
                                "color": INK,
                                "letterSpacing": "-0.02em",
                            },
                        ),
                        html.Span(
                            " hidden gems with expansion upside",
                            style={
                                "fontFamily": FONT_SANS,
                                "fontSize": "17px",
                                "color": TEXT_SECONDARY,
                                "marginLeft": "8px",
                            },
                        ),
                    ],
                ),
                html.Div(
                    [
                        _upside_chip("Median benchmark", summary["total_median_upside"]),
                        _upside_chip("75th percentile", summary["total_p75_upside"]),
                        _upside_chip("Category leader", summary["total_leader_upside"]),
                    ],
                    style={
                        "display": "flex",
                        "gap": "24px",
                        "marginTop": "8px",
                        "flexWrap": "wrap",
                    },
                ),
            ],
            style={
                "padding": "24px 0",
                "marginBottom": "16px",
            },
        )

        # Annotation: if total median upside is significant, call it out.
        annotation = []
        if summary["total_median_upside"] > 0:
            annotation = annotation_callout(
                f"At median distribution levels, these {fmt_number(summary['count'])} "
                f"hidden gems represent {fmt_dollars(summary['total_median_upside'])} "
                f"in quarterly upside. The median benchmark uses each SKU's current "
                f"SPPD projected to peer-median door counts within its product line."
            )

        return (
            row_data,
            summary_children,
            annotation,
            json.dumps(row_data),
        )

    @callback(
        Output("expansion-detail-card", "children"),
        Input("expansion-grid", "selectedRows"),
        prevent_initial_call=True,
    )
    def _show_detail_card(selected_rows):
        """Show an inline detail card with calculation breakdown."""
        if not selected_rows:
            return []

        row = selected_rows[0]

        sku = row.get("sku", "")
        product_name = row.get("product_name", sku)
        product_line = row.get("product_line", "Unknown")
        current_doors = row.get("current_doors", 0)
        current_sppd = row.get("current_sppd", 0)
        acv_pct = row.get("acv_pct", 0)
        current_dollars = row.get("current_dollars", 0)

        median_doors = row.get("median_doors", 0)
        p75_doors = row.get("p75_doors", 0)
        leader_doors = row.get("leader_doors", 0)

        upside_median = row.get("upside_median_dollars", 0)
        upside_p75 = row.get("upside_p75_dollars", 0)
        upside_leader = row.get("upside_leader_dollars", 0)

        guidance = row.get("guidance", "")

        detail_rows = [
            {"label": "Current ACV%", "value": fmt_pct(acv_pct)},
            {"label": "Current SPPD", "value": f"{current_sppd:.4f}"},
            {"label": "Current Doors", "value": fmt_number(current_doors)},
            {"label": "Current Quarterly $", "value": fmt_dollars(current_dollars)},
            {"label": "", "value": ""},  # Separator.
            {
                "label": f"Median target ({fmt_number(median_doors)} doors)",
                "value": f"+{fmt_dollars(upside_median)}",
            },
            {
                "label": f"75th pct target ({fmt_number(p75_doors)} doors)",
                "value": f"+{fmt_dollars(upside_p75)}",
            },
            {
                "label": f"Leader target ({fmt_number(leader_doors)} doors)",
                "value": f"+{fmt_dollars(upside_leader)}",
            },
            {"label": "", "value": ""},  # Separator.
            {"label": "Guidance", "value": guidance},
        ]

        return dark_callout_card(
            title=product_name,
            subtitle=f"{product_line} — {sku}",
            rows=detail_rows,
        )


def _upside_chip(label, value):
    """Render a small summary chip showing a benchmark's total upside."""
    return html.Div(
        [
            html.Span(
                label,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": "12px",
                    "color": TEXT_SECONDARY,
                    "display": "block",
                },
            ),
            html.Span(
                fmt_dollars(value),
                style={
                    "fontFamily": FONT_SERIF,
                    "fontSize": "22px",
                    "fontWeight": "700",
                    "color": INK,
                },
            ),
        ],
    )


def _empty_message(text):
    """Render an empty-state message."""
    return html.Div(
        html.P(
            text,
            style={
                "fontFamily": FONT_SANS,
                "fontSize": "17px",
                "color": TEXT_SECONDARY,
                "padding": "24px 0",
            },
        ),
    )
