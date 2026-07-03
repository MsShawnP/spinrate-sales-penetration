"""At-risk list view — three-tier urgency scoring with signal transparency.

Scores each SKU on velocity level (vs category median) and velocity trend
(direction over trailing quarters).  Three tiers: act now, fix or
rationalize, watchlist.  Each row surfaces which signal fires so the
user gets three distinct reads.  Watchlist tier rendered separately.
"""

import json
import logging

import pandas as pd
from dash import Input, Output, callback, dcc, html

logger = logging.getLogger(__name__)

from app.app import app
from app.calculations import (
    calculate_at_risk_score,
    calculate_indexed_sppd,
    calculate_sppd_from_agg,
    calculate_velocity_trend_from_quarterly,
    days_in_quarter_range,
)
from app.components import annotation_callout, dark_callout_card, data_grid, definitions_panel, hero_card
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

# Level and Trend cover different time windows by design: Level (Indexed
# SPPD) uses the date range selected in the filter bar; Trend uses a fixed
# trailing 8 quarters regardless of that filter, because a slope needs
# enough history to be meaningful. A tier like Act Now can therefore
# combine a narrow snapshot with a two-year trend -- surfaced here so it
# isn't silently conflated.
WINDOW_NOTE = (
    "Level (Indexed SPPD) reflects the date range selected above. "
    "Trend is a long-run signal — the trailing 8 quarters, independent of "
    "that date filter — because a velocity slope needs history to be "
    "meaningful. The two can span different periods."
)


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

    scan_agg = db.get_scan_data_agg(filters)
    stores_df = db.get_stores()
    category_median_df = db.get_category_median_sppd()
    products_df = db.get_products()

    if scan_agg.empty or stores_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    start_q = filters.get("start_quarter", "Q1 2025")
    end_q = filters.get("end_quarter", "Q4 2025")
    days = days_in_quarter_range(start_q, end_q)

    sppd_df = calculate_sppd_from_agg(scan_agg, days)
    if sppd_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    indexed_df = calculate_indexed_sppd(sppd_df, category_median_df, products_df)

    # Trend uses full history (no date filter) so seasonal patterns don't
    # dominate the OLS slope within a single year.  Uses SQL-aggregated
    # quarterly SPPD (~600 rows) instead of raw scan data (~1.2M rows)
    # to avoid OOM on constrained VMs.
    trend_filters = {k: v for k, v in filters.items()
                     if k not in ("start_quarter", "end_quarter")}
    quarterly_sppd_df = db.get_quarterly_sppd(trend_filters)
    trend_df = calculate_velocity_trend_from_quarterly(quarterly_sppd_df, n_quarters=8)

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

    # Total dollars already aggregated by SQL.
    dollars = scan_agg[["sku", "total_dollars"]].rename(columns={"total_dollars": "current_dollars"})
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
        "width": 120,
        "pinned": "left",
    },
    {
        "field": "product_name",
        "headerName": "Item Name",
        "minWidth": 130,
        "flex": 1,
        "tooltipField": "product_name",
        "cellStyle": {"textOverflow": "ellipsis", "overflow": "hidden", "whiteSpace": "nowrap"},
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
        "width": 110,
        "tooltipField": "signal",
    },
    {
        "field": "indexed_sppd",
        "headerName": "Idx SPPD",
        "width": 110,
        "valueFormatter": {"function": "d3.format('.2f')(params.value)"},
        "headerTooltip": "Indexed SPPD (Level): computed over the selected date-range filter.",
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
        "headerTooltip": "Trend: trailing 8 quarters, independent of the date-range filter.",
    },
    {
        "field": "sppd",
        "headerName": "SPPD",
        "width": 100,
        "valueFormatter": {"function": "d3.format('.4f')(params.value)"},
        "headerTooltip": "Sales Per Point of Distribution.",
    },
    {
        "field": "current_dollars",
        "headerName": "Current $",
        "width": 130,
        "valueFormatter": {"function": "d3.format('$,.0f')(params.value)"},
        "headerTooltip": "Current quarterly dollars.",
    },
    {
        "field": "velocity_gap",
        "headerName": "Gap vs Median",
        "width": 130,
        "valueFormatter": {"function": "d3.format('+.1%')(params.value)"},
        "headerTooltip": "Indexed SPPD gap vs. the category median (1.0).",
        # No default column sort: the rows arrive pre-sorted by tier priority
        # (Act Now → Fix or Rationalize → others), worst gap first within each
        # tier. A column sort here would override that and bury the red items.
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
            # Level vs Trend window note — the two signals cover different
            # time periods by design; see WINDOW_NOTE for rationale.
            html.P(
                WINDOW_NOTE,
                className="formula-note",
            ),
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
                    data_grid(
                        "at-risk-grid",
                        _COLUMN_DEFS,
                        aria_label="At-risk items — act now and fix or rationalize",
                    ),
                ],
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
                    data_grid(
                        "watchlist-grid",
                        _COLUMN_DEFS,
                        aria_label="Watchlist — emerging risk items",
                    ),
                ],
                id="watchlist-section",
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
            definitions_panel(),
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
    )
    def _update_at_risk_view(filter_json):
        """Recompute at-risk list when filters change."""
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
                    hero_card(
                        fmt_number(act_now),
                        TIER_CONFIG["act_now"]["label"],
                        accent=TIER_CONFIG["act_now"]["accent"],
                    ),
                    hero_card(
                        fmt_number(fix_or_rat),
                        TIER_CONFIG["fix_or_rationalize"]["label"],
                        accent=TIER_CONFIG["fix_or_rationalize"]["accent"],
                    ),
                    hero_card(
                        fmt_number(watchlist),
                        TIER_CONFIG["watchlist"]["label"],
                        accent=TIER_CONFIG["watchlist"]["accent"],
                    ),
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
