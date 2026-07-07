"""Quadrant view — bubble scatter chart of SPPD vs ACV% with click-to-pin detail cards.

Primary visualization for Spin Rate. Each bubble is a SKU positioned by
velocity (SPPD, y-axis) and distribution breadth (ACV%, x-axis). Bubble
size encodes total dollars. Quadrant dividing lines are fixed at the
full-dataset median SPPD/ACV% (db.get_global_medians()) so a SKU's
quadrant doesn't reshuffle when filters change. Indexed SPPD toggle
rescales the y-axis to category-relative performance.
"""

import json
import logging

import numpy as np
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

from app.app import app
from app.calculations import (
    calculate_acv_pct,
    calculate_indexed_sppd,
    calculate_sppd_from_agg,
    calculate_velocity_trend_from_quarterly,
    classify_quadrant,
    days_in_quarter_range,
)
from app.charts import CHART_CONFIG, economist_layout
from app.components import dark_callout_card, definitions_panel
from app.constants import (
    CANVAS,
    CHICAGO_20,
    DISABLED,
    FONT_SANS,
    FONT_SERIF,
    GRIDLINE,
    INFO_BG,
    INK,
    PRODUCT_LINE_COLORS,
    QUADRANT_LABELS,
    REFERENCE,
    SPPD_FORMULA,
    TEXT_SECONDARY,
    WHITE,
    fmt_dollars,
    fmt_number,
    fmt_pct,
)

# ── Configuration ─────────────────────────────────────────────────

# Low-door-count threshold: markers below this get flagged styling.
LOW_DOOR_THRESHOLD = 10

# Bubble size bounds (pixels).
_BUBBLE_SIZE_MIN = 8
_BUBBLE_SIZE_MAX = 45

# Shown next to the SPPD formula only while the Indexed SPPD toggle is on.
INDEXED_SPPD_NOTE = (
    "Indexed SPPD = each SKU's SPPD ÷ its product line's full-dataset "
    "median. 1.0 = category-typical; above 1 is faster-selling, below is "
    "slower."
)


# ── Helper functions ──────────────────────────────────────────────


def _scale_bubble_sizes(dollars_series):
    """Map total dollars to bubble marker sizes within readable bounds.

    Uses square-root scaling so area is proportional to value, then
    normalizes to the min/max pixel range.
    """
    if dollars_series.empty:
        return pd.Series(dtype=float)

    sqrt_vals = np.sqrt(dollars_series.clip(lower=0))
    min_val = sqrt_vals.min()
    max_val = sqrt_vals.max()

    if max_val == min_val:
        return pd.Series(
            _BUBBLE_SIZE_MIN + (_BUBBLE_SIZE_MAX - _BUBBLE_SIZE_MIN) / 2, index=dollars_series.index
        )

    normalized = (sqrt_vals - min_val) / (max_val - min_val)
    return _BUBBLE_SIZE_MIN + normalized * (_BUBBLE_SIZE_MAX - _BUBBLE_SIZE_MIN)


def _assign_product_line_colors(product_lines):
    """Map unique product lines to the categorical palette.

    Five visually distinct hues (Chicago, HK, Singapore families —
    no Red or Tokyo) assigned alphabetically. Cycles if more lines
    than palette entries.
    """
    unique_lines = sorted(product_lines.unique())
    palette = PRODUCT_LINE_COLORS
    color_map = {}
    for i, pl in enumerate(unique_lines):
        color_map[pl] = palette[i % len(palette)]
    return color_map


def _hover_text(df):
    """Pre-format hover text for each row so Plotly renders it directly."""
    return [
        f"<b>{row['product_name']}</b><br>"
        f"SKU: {row['sku']}<br>"
        f"SPPD: {row['sppd']:.4f}<br>"
        f"ACV%: {row['acv_pct']:.1%}<br>"
        f"Total $: ${row['total_dollars']:,.0f}<br>"
        f"Doors: {int(row['door_count']):,}<br>"
        f"Quadrant: {row['quadrant']}"
        for _, row in df.iterrows()
    ]


def _build_custom_legend(chart_df):
    """Build a custom HTML legend below the chart, laid out as a 3-column
    CSS grid (3 items per row) instead of Plotly's built-in SVG legend.

    Plotly's native horizontal legend wraps by available width, not by a
    fixed item count, and its wrap decisions come from a canvas-based
    text measurement that doesn't reliably track async web-font loading
    (Source Sans 3 loads via font-display: swap). A plain HTML/CSS grid
    sidesteps that whole class of bug: normal DOM text reflows correctly
    on any font swap, and grid-template-columns gives an exact,
    deterministic item count per row regardless of label length or font
    load timing.
    """
    if chart_df.empty:
        return []

    color_map = _assign_product_line_colors(chart_df["product_line"])
    product_lines_sorted = sorted(chart_df["product_line"].unique())

    items = [
        html.Div(
            [
                html.Span(
                    style={
                        "display": "inline-block",
                        "width": "10px",
                        "height": "10px",
                        "borderRadius": "50%",
                        "backgroundColor": color_map[pl],
                        "marginRight": "8px",
                        "flexShrink": "0",
                    }
                ),
                html.Span(pl, style={"whiteSpace": "nowrap"}),
            ],
            style={
                "display": "flex",
                "alignItems": "center",
                "fontFamily": FONT_SANS,
                "fontSize": "12px",
                "color": TEXT_SECONDARY,
            },
        )
        for pl in product_lines_sorted
    ]

    return html.Div(
        items,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(3, auto)",
            "justifyContent": "center",
            "columnGap": "24px",
            "rowGap": "8px",
            "marginTop": "12px",
        },
    )


def _build_quadrant_figure(chart_df, median_sppd, median_acv, indexed_mode=False):
    """Build the Plotly bubble scatter figure.

    Parameters
    ----------
    chart_df : DataFrame
        Must contain: sku, product_name, product_line, acv_pct,
        sppd (or indexed_sppd if indexed_mode), total_dollars,
        door_count, bubble_size, color, opacity, quadrant.
    median_sppd : float
        Horizontal dividing line y-value.
    median_acv : float
        Vertical dividing line x-value.
    indexed_mode : bool
        If True, y-axis shows indexed SPPD with 1.0 dividing line.
    """
    y_col = "indexed_sppd" if indexed_mode else "sppd"
    y_label = "Indexed SPPD (vs category median)" if indexed_mode else "SPPD (units / store / day)"

    fig = go.Figure()

    color_map = _assign_product_line_colors(chart_df["product_line"])
    product_lines_sorted = sorted(chart_df["product_line"].unique())

    for pl in product_lines_sorted:
        pl_data = chart_df[chart_df["product_line"] == pl]
        color = color_map[pl]

        # Separate low-door and normal markers for legend clarity.
        normal = pl_data[pl_data["door_count"] >= LOW_DOOR_THRESHOLD]
        low_door = pl_data[pl_data["door_count"] < LOW_DOOR_THRESHOLD]

        if not normal.empty:
            fig.add_trace(
                go.Scatter(
                    x=normal["acv_pct"].tolist(),
                    y=normal[y_col].tolist(),
                    mode="markers",
                    name=pl,
                    customdata=np.stack(
                        [
                            normal["sku"],
                            normal["product_name"],
                            normal["product_line"],
                            normal["total_dollars"],
                            normal["door_count"],
                            normal["sppd"],
                            normal["quadrant"],
                        ],
                        axis=-1,
                    ).tolist(),
                    marker=dict(
                        size=normal["bubble_size"].tolist(),
                        color=color,
                        opacity=normal["opacity"].tolist(),
                        line=dict(width=1, color=INK),
                    ),
                    hovertext=_hover_text(normal),
                    hoverinfo="text",
                    legendgroup=pl,
                    showlegend=True,
                )
            )

        if not low_door.empty:
            fig.add_trace(
                go.Scatter(
                    x=low_door["acv_pct"].tolist(),
                    y=low_door[y_col].tolist(),
                    mode="markers",
                    # No "(low doors)" suffix -- the low-door/normal split is
                    # communicated by the faded/dashed marker style plus the
                    # caption below the chart, not a separate legend label.
                    name=pl,
                    customdata=np.stack(
                        [
                            low_door["sku"],
                            low_door["product_name"],
                            low_door["product_line"],
                            low_door["total_dollars"],
                            low_door["door_count"],
                            low_door["sppd"],
                            low_door["quadrant"],
                        ],
                        axis=-1,
                    ).tolist(),
                    marker=dict(
                        size=low_door["bubble_size"].tolist(),
                        color=color,
                        opacity=0.4,
                        line=dict(width=2, color=color, dash="dash"),
                    ),
                    hovertext=_hover_text(low_door),
                    hoverinfo="text",
                    legendgroup=pl,
                    # Fold low-door markers into the product line's legend entry so
                    # each line contributes ONE entry (halves entry count → no wrap
                    # overflow). Only surface separately if the line has no normal
                    # markers, so a line is never dropped from the legend.
                    showlegend=normal.empty,
                )
            )

    # Quadrant dividing lines — add as shapes directly to avoid empty annotations.
    fig.add_shape(
        type="line",
        x0=0,
        x1=1,
        xref="paper",
        y0=median_sppd,
        y1=median_sppd,
        yref="y",
        line=dict(dash="dash", color=REFERENCE, width=2),
    )
    fig.add_shape(
        type="line",
        x0=median_acv,
        x1=median_acv,
        xref="x",
        y0=0,
        y1=1,
        yref="paper",
        line=dict(dash="dash", color=REFERENCE, width=2),
    )

    # Quadrant corner labels positioned in paper coordinates (0-1 range)
    # so they're robust regardless of data range.
    quadrant_annotations = [
        # Stars — top-right
        dict(
            x=0.75,
            y=0.92,
            xref="paper",
            yref="paper",
            text=QUADRANT_LABELS["star"],
            showarrow=False,
            # Muted subtitle text, not DISABLED (London-70) -- these labels
            # are always visible, never a disabled UI state.
            font=dict(family=FONT_SANS, size=13, color=TEXT_SECONDARY),
        ),
        # Hidden Gems — top-left
        dict(
            x=0.25,
            y=0.92,
            xref="paper",
            yref="paper",
            text=QUADRANT_LABELS["hidden_gem"],
            showarrow=False,
            # Muted subtitle text, not DISABLED (London-70) -- these labels
            # are always visible, never a disabled UI state.
            font=dict(family=FONT_SANS, size=13, color=TEXT_SECONDARY),
        ),
        # Wide but Dead — bottom-right
        dict(
            x=0.75,
            y=0.08,
            xref="paper",
            yref="paper",
            text=QUADRANT_LABELS["wide_but_dead"],
            showarrow=False,
            # Muted subtitle text, not DISABLED (London-70) -- these labels
            # are always visible, never a disabled UI state.
            font=dict(family=FONT_SANS, size=13, color=TEXT_SECONDARY),
        ),
        # Question Marks — bottom-left
        dict(
            x=0.25,
            y=0.08,
            xref="paper",
            yref="paper",
            text=QUADRANT_LABELS["question_mark"],
            showarrow=False,
            # Muted subtitle text, not DISABLED (London-70) -- these labels
            # are always visible, never a disabled UI state.
            font=dict(family=FONT_SANS, size=13, color=TEXT_SECONDARY),
        ),
    ]

    x_max = chart_df["acv_pct"].max() if not chart_df.empty else 1.0

    layout = economist_layout(
        title=dict(
            text="Penetration vs Velocity",
            font=dict(family=FONT_SERIF, size=22, color=INK),
        ),
        xaxis=dict(
            title=dict(text="ACV%", font=dict(family=FONT_SANS, size=14, color=TEXT_SECONDARY)),
            showgrid=False,
            showline=True,
            linecolor=GRIDLINE,
            tickformat=".0%",
            tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
            range=[0, max(x_max * 1.1, 0.1)],
        ),
        yaxis=dict(
            title=dict(text=y_label, font=dict(family=FONT_SANS, size=14, color=TEXT_SECONDARY)),
            showgrid=True,
            gridcolor=GRIDLINE,
            gridwidth=1,
            showline=False,
            tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
            rangemode="tozero",
        ),
        annotations=quadrant_annotations,
        margin=dict(l=70, r=20, t=70, b=40),
        # Plotly's own SVG legend is off -- rendered as a custom HTML/CSS
        # grid instead (see _build_custom_legend / #quadrant-legend). See
        # that function's docstring for why.
        showlegend=False,
    )

    fig.update_layout(**layout)

    return fig


def _build_empty_figure():
    """Return an empty figure with a 'no data' annotation."""
    fig = go.Figure()
    layout = economist_layout(
        annotations=[
            dict(
                text="No data matches the current filters.",
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(family=FONT_SANS, size=17, color=TEXT_SECONDARY),
            )
        ],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    fig.update_layout(**layout)
    return fig


def _build_quadrant_summary(chart_df):
    """Build interactive summary — click a quadrant count to expand its item list."""
    if chart_df.empty:
        return []

    quadrant_order = [
        ("star", "stars"),
        ("hidden_gem", "hidden gems"),
        ("wide_but_dead", "wide but dead"),
        ("question_mark", "question marks"),
    ]

    sections = []
    for key, label in quadrant_order:
        q_label = QUADRANT_LABELS[key]
        subset = chart_df[chart_df["quadrant"] == q_label].sort_values(
            "total_dollars", ascending=False
        )
        count = len(subset)

        if count == 0:
            sections.append(
                html.Div(
                    [html.Strong("0"), f" {label}"],
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": "14px",
                        "color": DISABLED,
                        "padding": "6px 0",
                    },
                )
            )
            continue

        top = subset.iloc[0]

        item_list = []
        for _, row in subset.iterrows():
            item_list.append(
                html.Div(
                    [
                        html.Span(
                            row["product_name"],
                            style={"fontWeight": "600", "color": INK},
                        ),
                        html.Span(
                            f"  {fmt_dollars(row['total_dollars'])}  ·  "
                            f"{row['sppd']:.4f} SPPD  ·  {row['acv_pct']:.1%} ACV%",
                            style={"color": TEXT_SECONDARY},
                        ),
                    ],
                    style={
                        "padding": "4px 0",
                        "borderBottom": f"1px solid {GRIDLINE}",
                        "fontFamily": FONT_SANS,
                        "fontSize": "13px",
                    },
                )
            )

        sections.append(
            html.Details(
                [
                    html.Summary(
                        [
                            html.Strong(f"{count}"),
                            f" {label}",
                            html.Span(
                                f" (top: {top['product_name']})",
                                style={"color": TEXT_SECONDARY},
                            ),
                        ],
                        className="quadrant-summary-toggle",
                    ),
                    html.Div(
                        item_list,
                        style={
                            "padding": "8px 0 8px 16px",
                            "maxHeight": "300px",
                            "overflowY": "auto",
                        },
                    ),
                ],
                className="quadrant-summary-bucket",
            )
        )

    return html.Div(
        sections,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": "14px",
            "color": INK,
            "padding": "12px 0",
        },
    )


# ── Layout ────────────────────────────────────────────────────────


def layout():
    """Return the complete quadrant view layout."""
    return html.Div(
        [
            # Indexed SPPD toggle.
            html.Div(
                [
                    html.Button(
                        "Show Indexed SPPD",
                        id="indexed-sppd-toggle",
                        n_clicks=0,
                        className="indexed-toggle-btn",
                        style={
                            "backgroundColor": INFO_BG,
                            "color": CHICAGO_20,
                            "border": f"2px solid {CHICAGO_20}",
                            "padding": "8px 20px",
                            "borderRadius": "2px",
                            "fontFamily": FONT_SANS,
                            "fontSize": "14px",
                            "fontWeight": "600",
                            "cursor": "pointer",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "flex-end",
                    "marginBottom": "12px",
                },
            ),
            # Indexed mode state store.
            dcc.Store(id="indexed-mode", storage_type="memory", data=False),
            # Chart area.
            dcc.Graph(
                id="quadrant-chart",
                config=CHART_CONFIG,
                style={"minHeight": "500px"},
            ),
            # Custom HTML legend (3-column grid) -- populated by the same
            # callback that builds the chart figure. Replaces Plotly's
            # built-in SVG legend; see _build_custom_legend.
            html.Div(id="quadrant-legend"),
            # ACV% denominator caption -- only shown when a retailer/region
            # filter is active, since ACV% is always measured against the
            # full store universe (get_stores() is unfiltered).
            html.Div(id="quadrant-acv-caption"),
            # Low-door marker style caption (legend no longer labels this
            # separately -- see the (low doors) trace in _build_quadrant_figure).
            html.P(
                "Faded/dashed markers = low door count (<10 stores).",
                className="formula-note",
            ),
            # Summary callout (quadrant counts + top items).
            html.Div(id="quadrant-summary", className="chart-summary"),
            # SPPD formula note.
            html.P(
                SPPD_FORMULA,
                className="formula-note",
            ),
            definitions_panel(),
            # Indexed SPPD explanation — only populated while the toggle is on.
            html.Div(id="indexed-sppd-note"),
            # Detail card area (populated by click-to-pin callback).
            html.Div(
                id="quadrant-detail-card",
                style={"minWidth": "320px"},
            ),
        ],
        id="quadrant-view",
    )


# ── Callbacks ─────────────────────────────────────────────────────


def register_callbacks():
    """Register all quadrant view callbacks."""

    # Indexed SPPD toggle: flip the boolean store on each click.
    app.clientside_callback(
        """
        function(n_clicks, current_mode) {
            if (!n_clicks) return window.dash_clientside.no_update;
            return !current_mode;
        }
        """,
        Output("indexed-mode", "data"),
        Input("indexed-sppd-toggle", "n_clicks"),
        State("indexed-mode", "data"),
        prevent_initial_call=True,
    )

    # Toggle button label update.
    @callback(
        Output("indexed-sppd-toggle", "children"),
        Output("indexed-sppd-toggle", "style"),
        Output("indexed-sppd-note", "children"),
        Input("indexed-mode", "data"),
    )
    def _update_toggle_label(indexed_mode):
        if indexed_mode:
            return (
                "Show Raw SPPD",
                {
                    "backgroundColor": CHICAGO_20,
                    "color": WHITE,
                    "border": f"2px solid {CHICAGO_20}",
                    "padding": "8px 20px",
                    "borderRadius": "2px",
                    "fontFamily": FONT_SANS,
                    "fontSize": "14px",
                    "fontWeight": "600",
                    "cursor": "pointer",
                },
                html.P(INDEXED_SPPD_NOTE, className="formula-note"),
            )
        return (
            "Show Indexed SPPD",
            {
                "backgroundColor": INFO_BG,
                "color": CHICAGO_20,
                "border": f"2px solid {CHICAGO_20}",
                "padding": "8px 20px",
                "borderRadius": "2px",
                "fontFamily": FONT_SANS,
                "fontSize": "14px",
                "fontWeight": "600",
                "cursor": "pointer",
            },
            [],
        )

    # Click-to-pin: clientside callback to capture clickData into selected-sku store.
    # This is registered via app.clientside_callback so it runs in the browser.
    app.clientside_callback(
        "window.dash_clientside.spinrate.handle_click",
        Output("selected-sku", "data"),
        Input("quadrant-chart", "clickData"),
        State("selected-sku", "data"),
        prevent_initial_call=True,
    )

    # Main chart update callback.
    @callback(
        Output("quadrant-chart", "figure"),
        Output("quadrant-summary", "children"),
        Output("quadrant-legend", "children"),
        Output("quadrant-acv-caption", "children"),
        Input("filter-state", "data"),
        Input("indexed-mode", "data"),
    )
    def _update_quadrant_chart(filter_json, indexed_mode):
        """Rebuild the quadrant chart when filters or indexed mode change."""
        from app import db

        filters = json.loads(filter_json) if filter_json else {}
        indexed_mode = bool(indexed_mode)

        # ACV% is always measured against the total store universe
        # (get_stores() below is unfiltered), so explain the denominator
        # when a retailer/region filter narrows the rest of the view.
        acv_caption = []
        if filters.get("retailers") or filters.get("region"):
            acv_caption = html.P(
                "ACV% is measured against the total store universe, "
                "not just the filtered retailer/region.",
                className="formula-note",
            )

        try:
            scan_agg = db.get_scan_data_agg(filters)
            dist_df = db.get_distribution(filters)
            stores_df = db.get_stores()
            category_median_df = db.get_category_median_sppd()
            global_medians_df = db.get_global_medians()
            products_df = db.get_products()
        except Exception:
            logger.exception("Quadrant chart callback failed")
            return _build_empty_figure(), [], [], acv_caption

        if scan_agg.empty or dist_df.empty:
            return _build_empty_figure(), [], [], acv_caption

        # Compute metrics.
        start_q = filters.get("start_quarter", "Q1 2025")
        end_q = filters.get("end_quarter", "Q4 2025")
        days = days_in_quarter_range(start_q, end_q)

        sppd_df = calculate_sppd_from_agg(scan_agg, days)
        acv_df = calculate_acv_pct(dist_df, stores_df)

        if sppd_df.empty or acv_df.empty:
            return _build_empty_figure(), [], [], acv_caption

        # Merge SPPD + ACV + product info.
        chart_df = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
        chart_df = chart_df.merge(
            products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
        )

        # Total dollars already aggregated by SQL.
        dollars = scan_agg[["sku", "total_dollars"]].copy()
        chart_df = chart_df.merge(dollars, on="sku", how="left")
        chart_df["total_dollars"] = chart_df["total_dollars"].fillna(0)

        if chart_df.empty:
            return _build_empty_figure(), [], [], acv_caption

        # Fixed dividing-line medians from the full unfiltered dataset, so
        # quadrant membership doesn't reshuffle when filters change.
        fixed_median_sppd = (
            global_medians_df["median_sppd"].iloc[0] if not global_medians_df.empty else 0
        )
        fixed_median_acv = (
            global_medians_df["median_acv"].iloc[0] if not global_medians_df.empty else 0
        )

        # Indexed SPPD.
        if indexed_mode and not products_df.empty and not category_median_df.empty:
            indexed_df = calculate_indexed_sppd(sppd_df, category_median_df, products_df)
            chart_df = chart_df.merge(indexed_df[["sku", "indexed_sppd"]], on="sku", how="left")
            chart_df["indexed_sppd"] = chart_df["indexed_sppd"].fillna(1.0)
            median_sppd = 1.0  # Dividing line at index = 1.0
        else:
            chart_df["indexed_sppd"] = chart_df["sppd"]
            median_sppd = fixed_median_sppd

        median_acv = fixed_median_acv

        # Bubble sizing.
        chart_df["bubble_size"] = _scale_bubble_sizes(chart_df["total_dollars"])

        # Default opacity (1.0 for normal, 0.4 for low-door handled in trace).
        chart_df["opacity"] = 1.0

        # Quadrant classification.
        y_col_for_quadrant = "indexed_sppd" if indexed_mode else "sppd"
        chart_df["quadrant"] = chart_df.apply(
            lambda row: classify_quadrant(
                row[y_col_for_quadrant], row["acv_pct"], median_sppd, median_acv
            ),
            axis=1,
        )

        # Fill missing product names.
        chart_df["product_name"] = chart_df["product_name"].fillna(chart_df["sku"])
        chart_df["product_line"] = chart_df["product_line"].fillna("Unknown")

        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv, indexed_mode)
        summary = _build_quadrant_summary(chart_df)
        legend = _build_custom_legend(chart_df)
        return fig, summary, legend, acv_caption

    # Detail card callback — renders when selected-sku changes.
    @callback(
        Output("quadrant-detail-card", "children"),
        Input("selected-sku", "data"),
        State("filter-state", "data"),
        State("indexed-mode", "data"),
    )
    def _update_detail_card(selected_sku, filter_json, indexed_mode):
        """Render the dark callout detail card for the selected SKU."""
        if not selected_sku:
            return []

        from app import db

        filters = json.loads(filter_json) if filter_json else {}
        indexed_mode = bool(indexed_mode)

        try:
            scan_agg = db.get_scan_data_agg(filters)
            dist_df = db.get_distribution(filters)
            stores_df = db.get_stores()
            category_median_df = db.get_category_median_sppd()
            global_medians_df = db.get_global_medians()
            products_df = db.get_products()
        except Exception:
            logger.exception("Quadrant detail card callback failed")
            return html.P(
                "Could not load detail data.",
                style={
                    "color": TEXT_SECONDARY,
                    "fontFamily": FONT_SANS,
                    "fontSize": "14px",
                },
            )

        start_q = filters.get("start_quarter", "Q1 2025")
        end_q = filters.get("end_quarter", "Q4 2025")
        days = days_in_quarter_range(start_q, end_q)

        sppd_df = calculate_sppd_from_agg(scan_agg, days)
        acv_df = calculate_acv_pct(dist_df, stores_df)

        # Get product info.
        product_row = products_df[products_df["sku"] == selected_sku]
        product_name = (
            product_row["product_name"].iloc[0] if not product_row.empty else selected_sku
        )
        product_line = product_row["product_line"].iloc[0] if not product_row.empty else "Unknown"

        # SPPD for this SKU.
        sku_sppd = sppd_df[sppd_df["sku"] == selected_sku]
        sppd_val = sku_sppd["sppd"].iloc[0] if not sku_sppd.empty else 0
        door_count = int(sku_sppd["door_count"].iloc[0]) if not sku_sppd.empty else 0

        # ACV%.
        sku_acv = acv_df[acv_df["sku"] == selected_sku]
        acv_val = sku_acv["acv_pct"].iloc[0] if not sku_acv.empty else 0

        # Total dollars from pre-aggregated data.
        sku_row = scan_agg[scan_agg["sku"] == selected_sku]
        sku_dollars = float(sku_row["total_dollars"].iloc[0]) if not sku_row.empty else 0

        # Quadrant label.
        if not sppd_df.empty and not acv_df.empty:
            fixed_median_sppd = (
                global_medians_df["median_sppd"].iloc[0] if not global_medians_df.empty else 0
            )
            fixed_median_acv = (
                global_medians_df["median_acv"].iloc[0] if not global_medians_df.empty else 0
            )

            if indexed_mode and not category_median_df.empty and not products_df.empty:
                indexed_df = calculate_indexed_sppd(sppd_df, category_median_df, products_df)
                sku_indexed = indexed_df[indexed_df["sku"] == selected_sku]
                y_val = sku_indexed["indexed_sppd"].iloc[0] if not sku_indexed.empty else sppd_val
                med_sppd = 1.0
            else:
                y_val = sppd_val
                med_sppd = fixed_median_sppd

            med_acv = fixed_median_acv
            quadrant = classify_quadrant(y_val, acv_val, med_sppd, med_acv)
        else:
            quadrant = "N/A"

        # Velocity trend from pre-aggregated quarterly SPPD.
        trend_filters = {
            k: v for k, v in filters.items() if k not in ("start_quarter", "end_quarter")
        }
        quarterly_sppd_df = db.get_quarterly_sppd(trend_filters)
        trend_df = calculate_velocity_trend_from_quarterly(quarterly_sppd_df)
        sku_trend = trend_df[trend_df["sku"] == selected_sku]
        trend_label = sku_trend["trend"].iloc[0].capitalize() if not sku_trend.empty else "N/A"

        rows = [
            {"label": "SPPD", "value": f"{sppd_val:.4f}"},
            {"label": "ACV%", "value": fmt_pct(acv_val)},
            {"label": "Total Dollars", "value": fmt_dollars(sku_dollars)},
            {"label": "Door Count", "value": fmt_number(door_count)},
            {"label": "Quadrant", "value": quadrant},
            {"label": "Velocity Trend", "value": trend_label},
        ]

        return dark_callout_card(
            title=product_name,
            subtitle=product_line,
            rows=rows,
        )
