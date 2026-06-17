"""At-risk list view — three-tier urgency scoring with signal transparency.

Scores each SKU on velocity level (vs category median) and velocity trend
(direction over trailing quarters).  Three tiers: act now, fix or
rationalize, watchlist.  Each row surfaces which signal fires so the
user gets three distinct reads.  Watchlist tier rendered separately.
"""

import json
import logging

import dash_ag_grid as dag
import pandas as pd
from dash import Input, Output, callback, dcc, html, no_update

logger = logging.getLogger(__name__)

from app.app import app
from app.calculations import (
    calculate_at_risk_score,
    calculate_indexed_sppd,
    calculate_sppd,
    calculate_velocity_trend,
    days_in_quarter_range,
)
from app.components import annotation_callout, dark_callout_card
from app.constants import (
    FAIL_BG,
    FAIL_TEXT,
    FONT_SANS,
    FONT_SERIF,
    HK_35,
    HK_85,
    INK,
    SG_20,
    SG_55,
    SPPD_FORMULA,
    TEXT_SECONDARY,
    TOKYO_20,
    TOKYO_40,
    TOKYO_95,
    WARN_BG,
    WARN_TEXT,
    fmt_dollars,
    fmt_number,
    fmt_pct,
)

# ── Tier metadata ────────────────────────────────────────────────

TIER_CONFIG = {
    "act_now": {
        "label": "Act Now",
        "signal": "Level + Trend",
        "bg": FAIL_BG,
        "text": FAIL_TEXT,
        "accent": TOKYO_40,
        "description": "Below category median and declining — needs immediate attention.",
    },
    "fix_or_rationalize": {
        "label": "Fix or Rationalize",
        "signal": "Level",
        "bg": WARN_BG,
        "text": WARN_TEXT,
        "accent": SG_55,
        "description": "Below category median but stable — fix velocity or rationalize distribution.",
    },
    "watchlist": {
        "label": "Watchlist",
        "signal": "Trend",
        "bg": HK_85,
        "text": HK_35,
        "accent": HK_35,
        "description": "Above median but velocity declining — monitor before it worsens.",
    },
}


# ── Data assembly ────────────────────────────────────────────────


def build_at_risk_data(filters):
    """Compute the at-risk table from current filter state.

    Returns a tuple (at_risk_df, watchlist_df, summary_dict) where:
    - at_risk_df contains act_now + fix_or_rationalize rows
    - watchlist_df contains watchlist rows
    - summary_dict has aggregate counts per tier

    Returns (empty, empty, empty dict) when no at-risk SKUs exist.
    """
    from app import db

    scan_df = db.get_scan_data(filters)
    stores_df = db.get_stores()
    benchmarks_df = db.get_benchmarks()
    products_df = db.get_products()

    if scan_df.empty or stores_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    start_q = filters.get("start_quarter", "Q1 2025")
    end_q = filters.get("end_quarter", "Q4 2025")
    days = days_in_quarter_range(start_q, end_q)

    sppd_df = calculate_sppd(scan_df, days)
    if sppd_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    indexed_df = calculate_indexed_sppd(sppd_df, benchmarks_df, products_df)

    # Trend uses full history (no date filter) so seasonal patterns don't
    # dominate the OLS slope within a single year.
    trend_filters = {k: v for k, v in filters.items()
                     if k not in ("start_quarter", "end_quarter")}
    trend_scan_df = db.get_scan_data(trend_filters)
    trend_df = calculate_velocity_trend(trend_scan_df, products_df, n_quarters=8)

    if indexed_df.empty or trend_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    scored = calculate_at_risk_score(indexed_df, trend_df)
    if scored.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    # Enrich with product info, SPPD, trend details, and dollars.
    scored = scored.merge(
        products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
    )
    scored = scored.merge(
        sppd_df[["sku", "sppd", "door_count"]], on="sku", how="left"
    )
    scored = scored.merge(
        indexed_df[["sku", "category_median_sppd"]], on="sku", how="left"
    )
    scored = scored.merge(
        trend_df[["sku", "slope", "mean_sppd", "quarters_with_data"]], on="sku", how="left"
    )

    # Total dollars from scan data.
    dollars = scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
    dollars.columns = ["sku", "current_dollars"]
    scored = scored.merge(dollars, on="sku", how="left")
    scored["current_dollars"] = scored["current_dollars"].fillna(0)

    # Signal label per SKU.
    scored["signal"] = scored["at_risk_tier"].map(
        lambda t: TIER_CONFIG[t]["signal"] if t in TIER_CONFIG else ""
    )

    # Tier label for display.
    scored["tier_label"] = scored["at_risk_tier"].map(
        lambda t: TIER_CONFIG[t]["label"] if t in TIER_CONFIG else ""
    )

    # Velocity gap from median (for sorting worst-first).
    scored["velocity_gap"] = scored["indexed_sppd"] - 1.0

    # Flag limited history.
    scored["limited_history"] = scored["quarters_with_data"] < 4

    # Fill missing product names.
    scored["product_name"] = scored["product_name"].fillna(scored["sku"])

    # Split into at-risk (act_now + fix_or_rationalize) and watchlist.
    at_risk_mask = scored["at_risk_tier"].isin(["act_now", "fix_or_rationalize"])
    at_risk_df = scored[at_risk_mask].copy()
    watchlist_df = scored[scored["at_risk_tier"] == "watchlist"].copy()

    # Sort: tier urgency first (act_now before fix_or_rationalize), then
    # by velocity gap ascending (worst gap first, i.e. most below median).
    tier_order = {"act_now": 0, "fix_or_rationalize": 1}
    at_risk_df["_sort_tier"] = at_risk_df["at_risk_tier"].map(tier_order)
    at_risk_df = at_risk_df.sort_values(
        ["_sort_tier", "velocity_gap"], ascending=[True, True]
    ).drop(columns=["_sort_tier"])

    # Watchlist sorted by velocity gap ascending (worst first).
    watchlist_df = watchlist_df.sort_values("velocity_gap", ascending=True)

    summary = {
        "act_now_count": int((scored["at_risk_tier"] == "act_now").sum()),
        "fix_or_rationalize_count": int((scored["at_risk_tier"] == "fix_or_rationalize").sum()),
        "watchlist_count": int((scored["at_risk_tier"] == "watchlist").sum()),
        "total_at_risk_dollars": float(at_risk_df["current_dollars"].sum()),
    }

    return at_risk_df, watchlist_df, summary


# ── AG Grid column definitions ───────────────────────────────────

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
        "field": "tier_label",
        "headerName": "Tier",
        "width": 150,
        "cellStyle": {"function": """
            params.data.at_risk_tier === 'act_now'
                ? {background: '#fde8e7', color: '#7a0906', fontWeight: 'bold'}
                : params.data.at_risk_tier === 'fix_or_rationalize'
                    ? {background: '#fdeee0', color: '#7a3d10', fontWeight: 'bold'}
                    : {background: '#b5e4d8', color: '#158f75', fontWeight: 'bold'}
        """},
    },
    {
        "field": "signal",
        "headerName": "Signal",
        "width": 130,
        "tooltipField": "signal",
    },
    {
        "field": "indexed_sppd",
        "headerName": "Indexed SPPD",
        "width": 120,
        "valueFormatter": {"function": "d3.format('.2f')(params.value)"},
    },
    {
        "field": "trend",
        "headerName": "Trend",
        "width": 100,
        "cellStyle": {"function": """
            params.value === 'declining'
                ? {color: '#b82d4a'}
                : params.value === 'rising'
                    ? {color: '#158f75'}
                    : {}
        """},
    },
    {
        "field": "sppd",
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
        "field": "velocity_gap",
        "headerName": "Gap vs Median",
        "width": 120,
        "valueFormatter": {"function": "d3.format('+.1%')(params.value)"},
        "sort": "asc",
    },
]


# ── Layout ───────────────────────────────────────────────────────


def layout():
    """Return the at-risk view layout."""
    return html.Div(
        [
            # Summary header area.
            html.Div(id="at-risk-summary"),
            # Annotation callout area.
            html.Div(id="at-risk-annotation"),
            # At-risk section (act now + fix or rationalize).
            html.Div(
                [
                    html.H3(
                        "At-Risk Items",
                        style={
                            "fontFamily": FONT_SERIF,
                            "fontSize": "22px",
                            "fontWeight": "700",
                            "color": INK,
                            "marginBottom": "8px",
                        },
                    ),
                    dag.AgGrid(
                        id="at-risk-grid",
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
                        style={"height": "400px", "width": "100%"},
                        className="ag-theme-alpine",
                    ),
                ],
                **{"aria-label": "At-risk items — act now and fix or rationalize"},
            ),
            # Watchlist section (separate per R20).
            html.Div(
                [
                    html.H3(
                        "Watchlist",
                        style={
                            "fontFamily": FONT_SERIF,
                            "fontSize": "22px",
                            "fontWeight": "700",
                            "color": INK,
                            "marginTop": "32px",
                            "marginBottom": "8px",
                        },
                    ),
                    html.P(
                        "Above category median but velocity declining — monitor before these worsen.",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": "14px",
                            "color": TEXT_SECONDARY,
                            "marginBottom": "12px",
                        },
                    ),
                    dag.AgGrid(
                        id="watchlist-grid",
                        columnDefs=_COLUMN_DEFS,
                        rowData=[],
                        defaultColDef={
                            "sortable": True,
                            "filter": True,
                            "resizable": True,
                        },
                        dashGridOptions={
                            "pagination": True,
                            "paginationPageSize": 15,
                            "rowSelection": {"mode": "singleRow"},
                            "animateRows": True,
                        },
                        style={"height": "350px", "width": "100%"},
                        className="ag-theme-alpine",
                    ),
                ],
                id="watchlist-section",
                **{"aria-label": "Watchlist — emerging risk items"},
            ),
            # Inline detail card (shown on row selection from either grid).
            html.Div(id="at-risk-detail-card"),
            # Hidden stores for data.
            dcc.Store(id="at-risk-data-store", data="[]"),
            dcc.Store(id="watchlist-data-store", data="[]"),
            # SPPD formula note.
            html.P(
                SPPD_FORMULA,
                className="formula-note",
            ),
        ],
    )


# ── Callbacks ────────────────────────────────────────────────────


def register_callbacks():
    """Register all at-risk view callbacks."""

    @callback(
        Output("at-risk-grid", "rowData"),
        Output("watchlist-grid", "rowData"),
        Output("at-risk-summary", "children"),
        Output("at-risk-annotation", "children"),
        Output("at-risk-data-store", "data"),
        Output("watchlist-data-store", "data"),
        Output("watchlist-section", "style"),
        Input("filter-state", "data"),
        Input("main-tabs", "value"),
    )
    def _update_at_risk_view(filter_json, active_tab):
        """Recompute at-risk list when filters change."""
        if active_tab != "at-risk":
            return (no_update,) * 7

        filters = json.loads(filter_json) if filter_json else {}

        try:
            at_risk_df, watchlist_df, summary = build_at_risk_data(filters)
        except Exception:
            logger.exception("At-risk view callback failed")
            return (
                [],
                [],
                _empty_message("Could not load at-risk data."),
                [],
                "[]",
                "[]",
                {"display": "none"},
            )

        if at_risk_df.empty and watchlist_df.empty:
            return (
                [],
                [],
                _empty_message("No at-risk or watchlist items for the current filters."),
                [],
                "[]",
                "[]",
                {"display": "none"},
            )

        grid_columns = [
            "sku", "product_name", "product_line", "at_risk_tier",
            "tier_label", "signal", "indexed_sppd", "trend",
            "sppd", "current_dollars", "velocity_gap",
            "door_count", "category_median_sppd", "slope",
            "mean_sppd", "quarters_with_data", "limited_history",
        ]

        at_risk_rows = at_risk_df[
            [c for c in grid_columns if c in at_risk_df.columns]
        ].to_dict("records") if not at_risk_df.empty else []

        watchlist_rows = watchlist_df[
            [c for c in grid_columns if c in watchlist_df.columns]
        ].to_dict("records") if not watchlist_df.empty else []

        # Summary header.
        summary_children = _build_summary(summary)

        # Annotation.
        annotation = []
        total = summary.get("act_now_count", 0) + summary.get("fix_or_rationalize_count", 0)
        if total > 0:
            annotation = annotation_callout(
                f"{fmt_number(summary['act_now_count'])} items need immediate action "
                f"(below median and declining). "
                f"{fmt_number(summary['fix_or_rationalize_count'])} are below median "
                f"but stable — candidates for velocity improvement or distribution "
                f"rationalization."
            )

        # Show watchlist section only if there are watchlist items.
        watchlist_style = {} if watchlist_rows else {"display": "none"}

        return (
            at_risk_rows,
            watchlist_rows,
            summary_children,
            annotation,
            json.dumps(at_risk_rows),
            json.dumps(watchlist_rows),
            watchlist_style,
        )

    @callback(
        Output("at-risk-detail-card", "children"),
        Input("at-risk-grid", "selectedRows"),
        Input("watchlist-grid", "selectedRows"),
        prevent_initial_call=True,
    )
    def _show_detail_card(at_risk_selected, watchlist_selected):
        """Show inline detail card for selected row from either grid."""
        selected = None
        if at_risk_selected:
            selected = at_risk_selected[0]
        elif watchlist_selected:
            selected = watchlist_selected[0]

        if not selected:
            return []

        sku = selected.get("sku", "")
        product_name = selected.get("product_name", sku)
        product_line = selected.get("product_line", "Unknown")
        tier_label = selected.get("tier_label", "")
        signal = selected.get("signal", "")
        indexed_sppd = selected.get("indexed_sppd", 0)
        trend = selected.get("trend", "")
        sppd = selected.get("sppd", 0)
        category_median = selected.get("category_median_sppd", 0)
        current_dollars = selected.get("current_dollars", 0)
        door_count = selected.get("door_count", 0)
        velocity_gap = selected.get("velocity_gap", 0)
        quarters = selected.get("quarters_with_data", 0)
        limited = selected.get("limited_history", False)

        detail_rows = [
            {"label": "Tier", "value": tier_label},
            {"label": "Signal", "value": signal},
            {"label": "", "value": ""},
            {"label": "SPPD", "value": f"{sppd:.4f}"},
            {"label": "Category Median SPPD", "value": f"{category_median:.4f}" if category_median else "N/A"},
            {"label": "Indexed SPPD", "value": f"{indexed_sppd:.2f}"},
            {"label": "Gap vs Median", "value": f"{velocity_gap:+.1%}"},
            {"label": "", "value": ""},
            {"label": "Trend Direction", "value": trend.capitalize()},
            {"label": "Quarters Analyzed", "value": f"{quarters}" + (" (limited)" if limited else "")},
            {"label": "Current Doors", "value": fmt_number(door_count)},
            {"label": "Current Quarterly $", "value": fmt_dollars(current_dollars)},
        ]

        return dark_callout_card(
            title=product_name,
            subtitle=f"{product_line} — {sku}",
            rows=detail_rows,
        )


def _build_summary(summary):
    """Build the summary header with tier counts."""
    act_now = summary.get("act_now_count", 0)
    fix_or_rat = summary.get("fix_or_rationalize_count", 0)
    watchlist = summary.get("watchlist_count", 0)
    total_dollars = summary.get("total_at_risk_dollars", 0)

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        fmt_number(act_now + fix_or_rat),
                        style={
                            "fontFamily": FONT_SERIF,
                            "fontSize": "36px",
                            "fontWeight": "700",
                            "color": INK,
                            "letterSpacing": "-0.02em",
                        },
                    ),
                    html.Span(
                        " items at risk",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": "17px",
                            "color": TEXT_SECONDARY,
                            "marginLeft": "8px",
                        },
                    ),
                    html.Span(
                        f" representing {fmt_dollars(total_dollars)} in quarterly revenue",
                        style={
                            "fontFamily": FONT_SANS,
                            "fontSize": "15px",
                            "color": TEXT_SECONDARY,
                            "marginLeft": "4px",
                        },
                    ) if total_dollars > 0 else None,
                ],
            ),
            html.Div(
                [
                    _tier_chip("Act Now", act_now, FAIL_BG, FAIL_TEXT),
                    _tier_chip("Fix or Rationalize", fix_or_rat, WARN_BG, WARN_TEXT),
                    _tier_chip("Watchlist", watchlist, HK_85, HK_35),
                ],
                style={
                    "display": "flex",
                    "gap": "16px",
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


def _tier_chip(label, count, bg_color, text_color):
    """Render a tier count chip with semantic color coding."""
    return html.Div(
        [
            html.Span(
                label,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": "12px",
                    "color": text_color,
                    "display": "block",
                },
            ),
            html.Span(
                fmt_number(count),
                style={
                    "fontFamily": FONT_SERIF,
                    "fontSize": "22px",
                    "fontWeight": "700",
                    "color": text_color,
                },
            ),
        ],
        style={
            "background": bg_color,
            "padding": "8px 16px",
            "borderRadius": "2px",
        },
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
