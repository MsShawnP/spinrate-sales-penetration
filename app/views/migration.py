"""Migration view -- shows which items moved quadrants between two time periods.

Three visualization modes (arrow overlay, side-by-side, sankey) and three
period modes (QoQ, user-selectable, rolling 13-week).  Default view loads
QoQ with arrow overlay, zero user config required.
"""

import json
import logging

import numpy as np
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

from app.app import app
from app.calculations import calculate_acv_pct, calculate_sppd, classify_quadrant, days_in_quarter_range
from app.charts import CHART_CONFIG, economist_layout
from app.components import dark_callout_card
from app.constants import (
    CANVAS,
    CHICAGO_20,
    DISABLED,
    FONT_SANS,
    FONT_SERIF,
    GRIDLINE,
    HK_35,
    HK_85,
    INK,
    MIGRATION_FAVORABLE,
    MIGRATION_UNFAVORABLE,
    QUADRANT_LABELS,
    REFERENCE,
    TEXT_SECONDARY,
    TOKYO_40,
    TOKYO_70,
    WHITE,
    fmt_dollars,
    fmt_number,
    fmt_pct,
)
from app.filters import QUARTER_OPTIONS

# ── Constants ────────────────────────────────────────────────────────

# Max arrows rendered on overlay to avoid clutter.
_MAX_ARROWS = 10

# Quadrant favorability ranking -- higher is better.
# Stars best, Question Marks worst.
_QUADRANT_RANK = {
    QUADRANT_LABELS["star"]: 4,
    QUADRANT_LABELS["hidden_gem"]: 3,
    QUADRANT_LABELS["wide_but_dead"]: 2,
    QUADRANT_LABELS["question_mark"]: 1,
}

# Sankey node ordering.
_SANKEY_ORDER = [
    QUADRANT_LABELS["star"],
    QUADRANT_LABELS["hidden_gem"],
    QUADRANT_LABELS["wide_but_dead"],
    QUADRANT_LABELS["question_mark"],
]

# Sankey node colors.
_SANKEY_COLORS = [HK_35, HK_85, TOKYO_70, DISABLED]


# ── Helpers ──────────────────────────────────────────────────────────


def _hex_to_rgba(hex_color, alpha=1.0):
    """Convert a hex color string to an rgba() string for Plotly compatibility."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _get_default_qoq_quarters(filter_state):
    """Determine default QoQ quarter pair from filter state.

    Returns (period1_quarter, period2_quarter) where period2 is the
    end_quarter from filters and period1 is the quarter before it.
    """
    all_quarters = [opt["value"] for opt in QUARTER_OPTIONS]
    end_q = filter_state.get("end_quarter", "Q4 2025")

    try:
        end_idx = all_quarters.index(end_q)
    except ValueError:
        end_idx = len(all_quarters) - 1

    start_idx = max(end_idx - 1, 0)
    return all_quarters[start_idx], all_quarters[end_idx]




def _compute_period_metrics(scan_df, dist_df, stores_df, products_df, quarter):
    """Compute SPPD, ACV%, and quadrant for a single quarter.

    Returns a DataFrame with columns: sku, sppd, acv_pct, quadrant,
    product_name, product_line, total_dollars, door_count.
    Returns empty DataFrame if no data.
    """
    days = days_in_quarter_range(quarter, quarter)
    sppd_df = calculate_sppd(scan_df, days)
    acv_df = calculate_acv_pct(dist_df, stores_df)

    if sppd_df.empty or acv_df.empty:
        return pd.DataFrame(columns=[
            "sku", "sppd", "acv_pct", "quadrant",
            "product_name", "product_line", "total_dollars", "door_count",
        ])

    merged = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
    merged = merged.merge(
        products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
    )

    # Total dollars from scan data.
    dollars = scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
    dollars.columns = ["sku", "total_dollars"]
    merged = merged.merge(dollars, on="sku", how="left")
    merged["total_dollars"] = merged["total_dollars"].fillna(0)

    if merged.empty:
        return pd.DataFrame(columns=[
            "sku", "sppd", "acv_pct", "quadrant",
            "product_name", "product_line", "total_dollars", "door_count",
        ])

    median_sppd = merged["sppd"].median()
    median_acv = merged["acv_pct"].median()

    merged["quadrant"] = merged.apply(
        lambda row: classify_quadrant(row["sppd"], row["acv_pct"], median_sppd, median_acv),
        axis=1,
    )
    merged["product_name"] = merged["product_name"].fillna(merged["sku"])
    merged["product_line"] = merged["product_line"].fillna("Unknown")

    return merged[["sku", "sppd", "acv_pct", "quadrant",
                    "product_name", "product_line", "total_dollars", "door_count"]]


def _build_migration_df(p1_df, p2_df):
    """Build migration DataFrame comparing two periods.

    Returns DataFrame with columns from both periods plus migration_type.
    Only includes SKUs present in both periods.
    """
    if p1_df.empty or p2_df.empty:
        return pd.DataFrame()

    merged = p1_df.merge(
        p2_df,
        on="sku",
        how="inner",
        suffixes=("_p1", "_p2"),
    )

    if merged.empty:
        return pd.DataFrame()

    # Determine if SKU moved quadrants.
    merged["moved"] = merged["quadrant_p1"] != merged["quadrant_p2"]

    # Determine favorability: higher rank = more favorable.
    merged["rank_p1"] = merged["quadrant_p1"].map(_QUADRANT_RANK).fillna(0)
    merged["rank_p2"] = merged["quadrant_p2"].map(_QUADRANT_RANK).fillna(0)
    merged["rank_delta"] = merged["rank_p2"] - merged["rank_p1"]

    # Migration magnitude: Euclidean distance in SPPD/ACV% space (normalized).
    sppd_range = max(
        merged[["sppd_p1", "sppd_p2"]].max().max() - merged[["sppd_p1", "sppd_p2"]].min().min(),
        0.001,
    )
    acv_range = max(
        merged[["acv_pct_p1", "acv_pct_p2"]].max().max() - merged[["acv_pct_p1", "acv_pct_p2"]].min().min(),
        0.001,
    )
    merged["magnitude"] = np.sqrt(
        ((merged["sppd_p2"] - merged["sppd_p1"]) / sppd_range) ** 2
        + ((merged["acv_pct_p2"] - merged["acv_pct_p1"]) / acv_range) ** 2
    )

    return merged


def _quadrant_annotations():
    """Return the standard 4 quadrant corner label annotations."""
    return [
        dict(
            x=0.75, y=0.92, xref="paper", yref="paper",
            text=QUADRANT_LABELS["star"], showarrow=False,
            font=dict(family=FONT_SANS, size=13, color=DISABLED),
        ),
        dict(
            x=0.25, y=0.92, xref="paper", yref="paper",
            text=QUADRANT_LABELS["hidden_gem"], showarrow=False,
            font=dict(family=FONT_SANS, size=13, color=DISABLED),
        ),
        dict(
            x=0.75, y=0.08, xref="paper", yref="paper",
            text=QUADRANT_LABELS["wide_but_dead"], showarrow=False,
            font=dict(family=FONT_SANS, size=13, color=DISABLED),
        ),
        dict(
            x=0.25, y=0.08, xref="paper", yref="paper",
            text=QUADRANT_LABELS["question_mark"], showarrow=False,
            font=dict(family=FONT_SANS, size=13, color=DISABLED),
        ),
    ]


def _dividing_line_shapes(median_sppd, median_acv):
    """Return shapes for quadrant dividing lines."""
    return [
        dict(
            type="line",
            x0=0, x1=1, xref="paper",
            y0=median_sppd, y1=median_sppd, yref="y",
            line=dict(dash="dash", color=REFERENCE, width=2),
        ),
        dict(
            type="line",
            x0=median_acv, x1=median_acv, xref="x",
            y0=0, y1=1, yref="paper",
            line=dict(dash="dash", color=REFERENCE, width=2),
        ),
    ]


# ── Arrow overlay figure ────────────────────────────────────────────


def build_arrow_overlay(migration_df, q1_label, q2_label):
    """Build the arrow overlay figure showing migration on the quadrant chart.

    Period 1 as ghost dots, Period 2 as solid dots, arrows between positions.
    """
    if migration_df.empty:
        return _build_no_migration_figure()

    fig = go.Figure()

    # Compute medians from Period 2 (the current period).
    median_sppd = migration_df["sppd_p2"].median()
    median_acv = migration_df["acv_pct_p2"].median()

    movers = migration_df[migration_df["moved"]].copy()
    stayers = migration_df[~migration_df["moved"]].copy()

    # Top movers by magnitude (limit arrows to _MAX_ARROWS).
    top_movers = movers.nlargest(_MAX_ARROWS, "magnitude") if len(movers) > _MAX_ARROWS else movers
    remaining_movers = movers[~movers["sku"].isin(top_movers["sku"])] if len(movers) > _MAX_ARROWS else pd.DataFrame()

    # Ghost dots: Period 1 positions (all SKUs).
    fig.add_trace(go.Scatter(
        x=migration_df["acv_pct_p1"].tolist(),
        y=migration_df["sppd_p1"].tolist(),
        mode="markers",
        name=f"{q1_label} (prior)",
        customdata=np.stack([
            migration_df["sku"],
            migration_df["product_name_p1"],
            migration_df["quadrant_p1"],
            migration_df["sppd_p1"],
            migration_df["acv_pct_p1"],
            migration_df["total_dollars_p1"],
        ], axis=-1).tolist() if not migration_df.empty else None,
        marker=dict(
            size=10,
            color=DISABLED,
            opacity=0.3,
            line=dict(width=1, color=REFERENCE),
        ),
        hoverinfo="skip",
        showlegend=True,
    ))

    # Solid dots: Period 2 positions for stayers.
    if not stayers.empty:
        fig.add_trace(go.Scatter(
            x=stayers["acv_pct_p2"].tolist(),
            y=stayers["sppd_p2"].tolist(),
            mode="markers",
            name="No change",
            customdata=np.stack([
                stayers["sku"],
                stayers["product_name_p2"],
                stayers["quadrant_p2"],
                stayers["sppd_p2"],
                stayers["acv_pct_p2"],
                stayers["total_dollars_p2"],
            ], axis=-1).tolist(),
            marker=dict(
                size=10,
                color=REFERENCE,
                opacity=0.7,
                line=dict(width=1, color=INK),
            ),
            hoverinfo="skip",
            showlegend=True,
        ))

    # Solid dots: Period 2 positions for movers -- favorable.
    favorable = top_movers[top_movers["rank_delta"] > 0]
    if not favorable.empty:
        fig.add_trace(go.Scatter(
            x=favorable["acv_pct_p2"].tolist(),
            y=favorable["sppd_p2"].tolist(),
            mode="markers",
            name="Favorable",
            customdata=np.stack([
                favorable["sku"],
                favorable["product_name_p2"],
                favorable["quadrant_p2"],
                favorable["sppd_p2"],
                favorable["acv_pct_p2"],
                favorable["total_dollars_p2"],
            ], axis=-1).tolist(),
            marker=dict(
                size=12,
                color=MIGRATION_FAVORABLE,
                opacity=1.0,
                line=dict(width=1, color=INK),
            ),
            hoverinfo="skip",
            showlegend=True,
        ))

    # Solid dots: Period 2 positions for movers -- unfavorable.
    unfavorable = top_movers[top_movers["rank_delta"] < 0]
    if not unfavorable.empty:
        fig.add_trace(go.Scatter(
            x=unfavorable["acv_pct_p2"].tolist(),
            y=unfavorable["sppd_p2"].tolist(),
            mode="markers",
            name="Unfavorable",
            customdata=np.stack([
                unfavorable["sku"],
                unfavorable["product_name_p2"],
                unfavorable["quadrant_p2"],
                unfavorable["sppd_p2"],
                unfavorable["acv_pct_p2"],
                unfavorable["total_dollars_p2"],
            ], axis=-1).tolist(),
            marker=dict(
                size=12,
                color=MIGRATION_UNFAVORABLE,
                opacity=1.0,
                line=dict(width=1, color=INK),
            ),
            hoverinfo="skip",
            showlegend=True,
        ))

    # Lateral movers (rank_delta == 0 but still moved quadrant).
    lateral = top_movers[top_movers["rank_delta"] == 0]
    if not lateral.empty:
        fig.add_trace(go.Scatter(
            x=lateral["acv_pct_p2"].tolist(),
            y=lateral["sppd_p2"].tolist(),
            mode="markers",
            name="Lateral",
            customdata=np.stack([
                lateral["sku"],
                lateral["product_name_p2"],
                lateral["quadrant_p2"],
                lateral["sppd_p2"],
                lateral["acv_pct_p2"],
                lateral["total_dollars_p2"],
            ], axis=-1).tolist(),
            marker=dict(
                size=12,
                color=REFERENCE,
                opacity=1.0,
                line=dict(width=1, color=INK),
            ),
            hoverinfo="skip",
            showlegend=True,
        ))

    # Arrows from P1 to P2 for top movers.
    arrow_annotations = []
    for _, row in top_movers.iterrows():
        color = MIGRATION_FAVORABLE if row["rank_delta"] > 0 else MIGRATION_UNFAVORABLE
        if row["rank_delta"] == 0:
            color = REFERENCE
        arrow_annotations.append(dict(
            x=row["acv_pct_p2"],
            y=row["sppd_p2"],
            ax=row["acv_pct_p1"],
            ay=row["sppd_p1"],
            xref="x", yref="y",
            axref="x", ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1.2,
            arrowwidth=2,
            arrowcolor=color,
            opacity=0.7,
        ))

    x_vals = pd.concat([migration_df["acv_pct_p1"], migration_df["acv_pct_p2"]])
    x_max = x_vals.max() if not x_vals.empty else 1.0

    all_annotations = _quadrant_annotations() + arrow_annotations

    layout_dict = economist_layout(
        title=dict(
            text=f"Quadrant Migration: {q1_label} → {q2_label}",
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
            title=dict(text="SPPD (units / store / day)", font=dict(family=FONT_SANS, size=14, color=TEXT_SECONDARY)),
            showgrid=True,
            gridcolor=GRIDLINE,
            gridwidth=1,
            showline=False,
            tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
            rangemode="tozero",
        ),
        annotations=all_annotations,
        shapes=_dividing_line_shapes(median_sppd, median_acv),
        margin=dict(l=70, r=20, t=70, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            font=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
        ),
    )

    fig.update_layout(**layout_dict)
    return fig


# ── Side-by-side figure ─────────────────────────────────────────────


def build_side_by_side(migration_df, q1_label, q2_label):
    """Build two quadrant charts side by side showing both periods."""
    from plotly.subplots import make_subplots

    if migration_df.empty:
        return _build_no_migration_figure()

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[q1_label, q2_label],
        horizontal_spacing=0.08,
    )

    # Period 1.
    median_sppd_p1 = migration_df["sppd_p1"].median()
    median_acv_p1 = migration_df["acv_pct_p1"].median()

    colors_p1 = migration_df["quadrant_p1"].map({
        QUADRANT_LABELS["star"]: MIGRATION_FAVORABLE,
        QUADRANT_LABELS["hidden_gem"]: HK_85,
        QUADRANT_LABELS["wide_but_dead"]: TOKYO_70,
        QUADRANT_LABELS["question_mark"]: DISABLED,
    }).fillna(DISABLED)

    fig.add_trace(go.Scatter(
        x=migration_df["acv_pct_p1"].tolist(),
        y=migration_df["sppd_p1"].tolist(),
        mode="markers",
        name=q1_label,
        customdata=np.stack([
            migration_df["sku"],
            migration_df["product_name_p1"],
            migration_df["quadrant_p1"],
            migration_df["sppd_p1"],
            migration_df["acv_pct_p1"],
            migration_df["total_dollars_p1"],
        ], axis=-1).tolist(),
        marker=dict(size=10, color=colors_p1.tolist(), opacity=0.8, line=dict(width=1, color=INK)),
        hoverinfo="skip",
        showlegend=False,
    ), row=1, col=1)

    # Period 2.
    median_sppd_p2 = migration_df["sppd_p2"].median()
    median_acv_p2 = migration_df["acv_pct_p2"].median()

    colors_p2 = migration_df["quadrant_p2"].map({
        QUADRANT_LABELS["star"]: MIGRATION_FAVORABLE,
        QUADRANT_LABELS["hidden_gem"]: HK_85,
        QUADRANT_LABELS["wide_but_dead"]: TOKYO_70,
        QUADRANT_LABELS["question_mark"]: DISABLED,
    }).fillna(DISABLED)

    fig.add_trace(go.Scatter(
        x=migration_df["acv_pct_p2"].tolist(),
        y=migration_df["sppd_p2"].tolist(),
        mode="markers",
        name=q2_label,
        customdata=np.stack([
            migration_df["sku"],
            migration_df["product_name_p2"],
            migration_df["quadrant_p2"],
            migration_df["sppd_p2"],
            migration_df["acv_pct_p2"],
            migration_df["total_dollars_p2"],
        ], axis=-1).tolist(),
        marker=dict(size=10, color=colors_p2.tolist(), opacity=0.8, line=dict(width=1, color=INK)),
        hoverinfo="skip",
        showlegend=False,
    ), row=1, col=2)

    # Compute common axis ranges for consistent scale.
    all_acv = pd.concat([migration_df["acv_pct_p1"], migration_df["acv_pct_p2"]])
    all_sppd = pd.concat([migration_df["sppd_p1"], migration_df["sppd_p2"]])
    x_max = max(all_acv.max() * 1.1, 0.1)
    y_max = all_sppd.max() * 1.1 if not all_sppd.empty else 1.0

    # Dividing lines for both panels.
    for col_idx, (med_sppd, med_acv) in enumerate(
        [(median_sppd_p1, median_acv_p1), (median_sppd_p2, median_acv_p2)]
    ):
        xref = "x" if col_idx == 0 else "x2"
        yref = "y" if col_idx == 0 else "y2"
        fig.add_shape(
            type="line", x0=0, x1=x_max, y0=med_sppd, y1=med_sppd,
            xref=xref, yref=yref,
            line=dict(dash="dash", color=REFERENCE, width=2),
        )
        fig.add_shape(
            type="line", x0=med_acv, x1=med_acv, y0=0, y1=y_max,
            xref=xref, yref=yref,
            line=dict(dash="dash", color=REFERENCE, width=2),
        )

    base_layout = economist_layout(
        title=dict(
            text=f"Quadrant Migration: {q1_label} vs {q2_label}",
            font=dict(family=FONT_SERIF, size=22, color=INK),
        ),
        margin=dict(l=70, r=20, t=90, b=50),
    )
    fig.update_layout(**base_layout)

    # Axis formatting for both panels.
    for suffix in ["", "2"]:
        fig.update_layout(**{
            f"xaxis{suffix}": dict(
                title=dict(text="ACV%", font=dict(family=FONT_SANS, size=14, color=TEXT_SECONDARY)),
                showgrid=False, showline=True, linecolor=GRIDLINE,
                tickformat=".0%",
                tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
                range=[0, x_max],
            ),
            f"yaxis{suffix}": dict(
                title=dict(text="SPPD", font=dict(family=FONT_SANS, size=14, color=TEXT_SECONDARY)),
                showgrid=True, gridcolor=GRIDLINE, gridwidth=1, showline=False,
                tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
                rangemode="tozero",
                range=[0, y_max],
            ),
        })

    return fig


# ── Sankey figure ────────────────────────────────────────────────────


def build_sankey(migration_df, q1_label, q2_label):
    """Build a Sankey diagram showing flow counts between quadrants."""
    if migration_df.empty:
        return _build_no_migration_figure()

    # Count flows from P1 quadrant to P2 quadrant.
    flows = migration_df.groupby(["quadrant_p1", "quadrant_p2"]).size().reset_index(name="count")

    # Build node list: source (P1) nodes on left, target (P2) nodes on right.
    source_labels = [f"{q} ({q1_label})" for q in _SANKEY_ORDER]
    target_labels = [f"{q} ({q2_label})" for q in _SANKEY_ORDER]
    node_labels = source_labels + target_labels
    node_colors = _SANKEY_COLORS + _SANKEY_COLORS

    source_idx_map = {q: i for i, q in enumerate(_SANKEY_ORDER)}
    target_idx_map = {q: i + len(_SANKEY_ORDER) for i, q in enumerate(_SANKEY_ORDER)}

    sources = []
    targets = []
    values = []
    link_colors = []

    for _, row in flows.iterrows():
        src_q = row["quadrant_p1"]
        tgt_q = row["quadrant_p2"]
        if src_q in source_idx_map and tgt_q in target_idx_map:
            sources.append(source_idx_map[src_q])
            targets.append(target_idx_map[tgt_q])
            values.append(int(row["count"]))

            # Color favorable green, unfavorable rose.
            src_rank = _QUADRANT_RANK.get(src_q, 0)
            tgt_rank = _QUADRANT_RANK.get(tgt_q, 0)
            if tgt_rank > src_rank:
                link_colors.append(MIGRATION_FAVORABLE)
            elif tgt_rank < src_rank:
                link_colors.append(MIGRATION_UNFAVORABLE)
            else:
                link_colors.append(GRIDLINE)

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            label=node_labels,
            color=node_colors,
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=[_hex_to_rgba(c, 0.5) for c in link_colors],  # Semi-transparent.
        ),
    )])

    base_layout = economist_layout(
        title=dict(
            text=f"Quadrant Migration Flow: {q1_label} → {q2_label}",
            font=dict(family=FONT_SERIF, size=22, color=INK),
        ),
        margin=dict(l=40, r=40, t=70, b=40),
    )
    fig.update_layout(**base_layout)

    return fig


# ── Empty/no-migration figure ────────────────────────────────────────


def _build_no_migration_figure():
    """Return a figure with a 'no quadrant changes' annotation."""
    fig = go.Figure()
    layout_dict = economist_layout(
        annotations=[dict(
            text="No quadrant changes detected between the selected periods.",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(family=FONT_SANS, size=17, color=TEXT_SECONDARY),
        )],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    fig.update_layout(**layout_dict)
    return fig


# ── Layout ───────────────────────────────────────────────────────────


def layout():
    """Return the complete migration view layout."""
    return html.Div(
        [
            # Stores for migration-specific state.
            dcc.Store(id="migration-period-mode", storage_type="memory", data="qoq"),
            dcc.Store(id="migration-viz-mode", storage_type="memory", data="arrows"),
            dcc.Store(id="migration-selected-sku", storage_type="memory"),

            # Customize toggle button.
            html.Div(
                [
                    html.Button(
                        "Customize",
                        id="migration-customize-toggle",
                        n_clicks=0,
                        style={
                            "backgroundColor": WHITE,
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

            # Customize panel (collapsed by default).
            html.Div(
                [
                    # Period mode selector.
                    html.Div(
                        [
                            html.Label(
                                "Period Mode",
                                style={"fontFamily": FONT_SANS, "fontSize": "14px",
                                       "fontWeight": "600", "color": TEXT_SECONDARY,
                                       "marginBottom": "4px"},
                            ),
                            dcc.RadioItems(
                                id="migration-period-selector",
                                options=[
                                    {"label": "Quarter over Quarter", "value": "qoq"},
                                    {"label": "Custom Quarters", "value": "custom"},
                                    {"label": "Rolling 13-Week", "value": "rolling"},
                                ],
                                value="qoq",
                                inline=True,
                                style={"fontFamily": FONT_SANS, "fontSize": "13px"},
                            ),
                        ],
                        style={"marginBottom": "12px"},
                    ),

                    # Custom quarter selectors (shown only in custom mode).
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label("Period 1 Quarter",
                                               style={"fontFamily": FONT_SANS, "fontSize": "13px",
                                                      "color": TEXT_SECONDARY}),
                                    dcc.Dropdown(
                                        id="migration-custom-q1",
                                        options=QUARTER_OPTIONS,
                                        value="Q3 2025",
                                        clearable=False,
                                        searchable=False,
                                        style={"minWidth": "140px"},
                                    ),
                                ],
                                style={"flex": "1", "marginRight": "12px"},
                            ),
                            html.Div(
                                [
                                    html.Label("Period 2 Quarter",
                                               style={"fontFamily": FONT_SANS, "fontSize": "13px",
                                                      "color": TEXT_SECONDARY}),
                                    dcc.Dropdown(
                                        id="migration-custom-q2",
                                        options=QUARTER_OPTIONS,
                                        value="Q4 2025",
                                        clearable=False,
                                        searchable=False,
                                        style={"minWidth": "140px"},
                                    ),
                                ],
                                style={"flex": "1"},
                            ),
                        ],
                        id="migration-custom-quarters",
                        style={"display": "none", "flexDirection": "row", "gap": "12px",
                               "marginBottom": "12px"},
                    ),

                    # Visualization mode selector.
                    html.Div(
                        [
                            html.Label(
                                "Visualization",
                                style={"fontFamily": FONT_SANS, "fontSize": "14px",
                                       "fontWeight": "600", "color": TEXT_SECONDARY,
                                       "marginBottom": "4px"},
                            ),
                            dcc.RadioItems(
                                id="migration-viz-selector",
                                options=[
                                    {"label": "Arrow Overlay", "value": "arrows"},
                                    {"label": "Side by Side", "value": "side_by_side"},
                                    {"label": "Migration Flow", "value": "sankey"},
                                ],
                                value="arrows",
                                inline=True,
                                style={"fontFamily": FONT_SANS, "fontSize": "13px"},
                            ),
                        ],
                    ),
                ],
                id="migration-customize-panel",
                style={
                    "display": "none",
                    "padding": "16px",
                    "backgroundColor": CANVAS,
                    "border": f"1px solid {GRIDLINE}",
                    "borderRadius": "2px",
                    "marginBottom": "16px",
                },
            ),

            # Same-period warning.
            html.Div(
                id="migration-same-period-warning",
                style={"display": "none"},
            ),

            # Chart area.
            dcc.Graph(
                id="migration-chart",
                config=CHART_CONFIG,
                style={"minHeight": "500px"},
            ),

            # Detail card area.
            html.Div(
                id="migration-detail-card",
                style={"minWidth": "320px"},
            ),

            # Migration summary table (shown when arrows > _MAX_ARROWS).
            html.Div(
                id="migration-summary-table",
            ),
        ],
        id="migration-view",
    )


# ── Callbacks ────────────────────────────────────────────────────────


def register_callbacks():
    """Register all migration view callbacks."""

    # Customize toggle: show/hide the options panel.
    @callback(
        Output("migration-customize-panel", "style"),
        Input("migration-customize-toggle", "n_clicks"),
        State("migration-customize-panel", "style"),
        prevent_initial_call=True,
    )
    def _toggle_customize(n_clicks, current_style):
        if not n_clicks:
            return no_update
        current_display = current_style.get("display", "none") if current_style else "none"
        new_display = "none" if current_display != "none" else "block"
        return {
            **current_style,
            "display": new_display,
        }

    # Show custom quarter dropdowns only in custom mode.
    @callback(
        Output("migration-custom-quarters", "style"),
        Input("migration-period-selector", "value"),
    )
    def _toggle_custom_quarters(period_mode):
        if period_mode == "custom":
            return {"display": "flex", "flexDirection": "row", "gap": "12px",
                    "marginBottom": "12px"}
        return {"display": "none", "flexDirection": "row", "gap": "12px",
                "marginBottom": "12px"}

    # Sync radio buttons to stores.
    @callback(
        Output("migration-period-mode", "data"),
        Input("migration-period-selector", "value"),
    )
    def _sync_period_mode(value):
        return value

    @callback(
        Output("migration-viz-mode", "data"),
        Input("migration-viz-selector", "value"),
    )
    def _sync_viz_mode(value):
        return value

    # Same-period warning.
    @callback(
        Output("migration-same-period-warning", "children"),
        Output("migration-same-period-warning", "style"),
        Input("migration-period-selector", "value"),
        Input("migration-custom-q1", "value"),
        Input("migration-custom-q2", "value"),
    )
    def _check_same_period(period_mode, q1, q2):
        if period_mode == "custom" and q1 == q2:
            return (
                html.P(
                    "Period 1 and Period 2 are the same quarter. Select different quarters to see migration.",
                    style={
                        "fontFamily": FONT_SANS,
                        "fontSize": "14px",
                        "color": TOKYO_40,
                        "padding": "8px 12px",
                        "backgroundColor": TOKYO_70 + "20",
                        "borderRadius": "2px",
                        "margin": "0 0 12px 0",
                    },
                ),
                {"display": "block"},
            )
        return [], {"display": "none"}

    # Click-to-pin on migration chart.
    app.clientside_callback(
        """
        function(clickData, currentSku) {
            if (!clickData || !clickData.points || clickData.points.length === 0) {
                return window.dash_clientside.no_update;
            }
            var point = clickData.points[0];
            var customdata = point.customdata;
            if (!customdata || !customdata[0]) {
                return window.dash_clientside.no_update;
            }
            var clickedSku = customdata[0];
            if (currentSku === clickedSku) {
                return null;
            }
            return clickedSku;
        }
        """,
        Output("migration-selected-sku", "data"),
        Input("migration-chart", "clickData"),
        State("migration-selected-sku", "data"),
        prevent_initial_call=True,
    )

    # Main chart update callback.
    @callback(
        Output("migration-chart", "figure"),
        Output("migration-summary-table", "children"),
        Input("filter-state", "data"),
        Input("migration-period-mode", "data"),
        Input("migration-viz-mode", "data"),
        Input("migration-custom-q1", "value"),
        Input("migration-custom-q2", "value"),
    )
    def _update_migration_chart(filter_json, period_mode, viz_mode, custom_q1, custom_q2):
        """Rebuild migration chart when inputs change."""
        from app import db

        filters = json.loads(filter_json) if filter_json else {}

        # Determine period quarters.
        if period_mode == "custom":
            if custom_q1 == custom_q2:
                return _build_no_migration_figure(), []
            q1_label = custom_q1
            q2_label = custom_q2
        elif period_mode == "rolling":
            # Rolling 13-week: use the end quarter and the one before.
            q1_label, q2_label = _get_default_qoq_quarters(filters)
        else:
            # QoQ default.
            q1_label, q2_label = _get_default_qoq_quarters(filters)

        # Get data for each period.
        try:
            # Period 1 filters.
            p1_filters = {**filters, "start_quarter": q1_label, "end_quarter": q1_label}
            p1_scan = db.get_scan_data(p1_filters)
            p1_dist = db.get_distribution(p1_filters)

            # Period 2 filters.
            p2_filters = {**filters, "start_quarter": q2_label, "end_quarter": q2_label}
            p2_scan = db.get_scan_data(p2_filters)
            p2_dist = db.get_distribution(p2_filters)

            stores_df = db.get_stores()
            products_df = db.get_products()
        except Exception:
            logger.exception("Migration chart callback failed")
            return _build_no_migration_figure(), []

        p1_metrics = _compute_period_metrics(p1_scan, p1_dist, stores_df, products_df, q1_label)
        p2_metrics = _compute_period_metrics(p2_scan, p2_dist, stores_df, products_df, q2_label)

        migration_df = _build_migration_df(p1_metrics, p2_metrics)

        if migration_df.empty:
            return _build_no_migration_figure(), []

        # Build the selected viz.
        if viz_mode == "side_by_side":
            fig = build_side_by_side(migration_df, q1_label, q2_label)
        elif viz_mode == "sankey":
            fig = build_sankey(migration_df, q1_label, q2_label)
        else:
            fig = build_arrow_overlay(migration_df, q1_label, q2_label)

        # Summary table for movers (shown in arrow mode when there are many).
        summary_children = []
        movers = migration_df[migration_df["moved"]]
        if viz_mode == "arrows" and len(movers) > _MAX_ARROWS:
            summary_children = _build_movers_table(movers, q1_label, q2_label)

        return fig, summary_children

    # Detail card callback.
    @callback(
        Output("migration-detail-card", "children"),
        Input("migration-selected-sku", "data"),
        State("filter-state", "data"),
        State("migration-period-mode", "data"),
        State("migration-custom-q1", "value"),
        State("migration-custom-q2", "value"),
    )
    def _update_migration_detail(selected_sku, filter_json, period_mode, custom_q1, custom_q2):
        """Render detail card comparing both periods for selected SKU."""
        if not selected_sku:
            return []

        from app import db

        filters = json.loads(filter_json) if filter_json else {}

        if period_mode == "custom":
            q1_label, q2_label = custom_q1, custom_q2
        else:
            q1_label, q2_label = _get_default_qoq_quarters(filters)

        try:
            p1_filters = {**filters, "start_quarter": q1_label, "end_quarter": q1_label}
            p1_scan = db.get_scan_data(p1_filters)
            p1_dist = db.get_distribution(p1_filters)

            p2_filters = {**filters, "start_quarter": q2_label, "end_quarter": q2_label}
            p2_scan = db.get_scan_data(p2_filters)
            p2_dist = db.get_distribution(p2_filters)

            stores_df = db.get_stores()
            products_df = db.get_products()
        except Exception:
            logger.exception("Migration detail card callback failed")
            return html.P("Could not load detail data.", style={
                "color": TEXT_SECONDARY, "fontFamily": FONT_SANS, "fontSize": "14px",
            })

        p1_metrics = _compute_period_metrics(p1_scan, p1_dist, stores_df, products_df, q1_label)
        p2_metrics = _compute_period_metrics(p2_scan, p2_dist, stores_df, products_df, q2_label)

        p1_row = p1_metrics[p1_metrics["sku"] == selected_sku]
        p2_row = p2_metrics[p2_metrics["sku"] == selected_sku]

        if p1_row.empty and p2_row.empty:
            return html.P("SKU not found in either period.", style={
                "color": TEXT_SECONDARY, "fontFamily": FONT_SANS, "fontSize": "14px",
            })

        # Use P2 product info if available, else P1.
        if not p2_row.empty:
            product_name = p2_row.iloc[0]["product_name"]
            product_line = p2_row.iloc[0]["product_line"]
        else:
            product_name = p1_row.iloc[0]["product_name"]
            product_line = p1_row.iloc[0]["product_line"]

        rows = []

        # Period 1 metrics.
        if not p1_row.empty:
            r = p1_row.iloc[0]
            rows.append({"label": f"SPPD ({q1_label})", "value": f"{r['sppd']:.4f}"})
            rows.append({"label": f"ACV% ({q1_label})", "value": fmt_pct(r["acv_pct"])})
            rows.append({"label": f"Dollars ({q1_label})", "value": fmt_dollars(r["total_dollars"])})
            rows.append({"label": f"Quadrant ({q1_label})", "value": r["quadrant"]})
        else:
            rows.append({"label": f"{q1_label}", "value": "Not in data"})

        # Period 2 metrics.
        if not p2_row.empty:
            r = p2_row.iloc[0]
            rows.append({"label": f"SPPD ({q2_label})", "value": f"{r['sppd']:.4f}"})
            rows.append({"label": f"ACV% ({q2_label})", "value": fmt_pct(r["acv_pct"])})
            rows.append({"label": f"Dollars ({q2_label})", "value": fmt_dollars(r["total_dollars"])})
            rows.append({"label": f"Quadrant ({q2_label})", "value": r["quadrant"]})
        else:
            rows.append({"label": f"{q2_label}", "value": "Not in data"})

        return dark_callout_card(
            title=product_name,
            subtitle=product_line,
            rows=rows,
        )


def _build_movers_table(movers_df, q1_label, q2_label):
    """Build an HTML table of all quadrant movers."""
    sorted_movers = movers_df.sort_values("magnitude", ascending=False)

    header = html.Tr([
        html.Th("SKU", style={"textAlign": "left", "padding": "6px 12px", "fontFamily": FONT_SANS,
                               "fontSize": "12px", "fontWeight": "600", "color": TEXT_SECONDARY}),
        html.Th("Product", style={"textAlign": "left", "padding": "6px 12px", "fontFamily": FONT_SANS,
                                   "fontSize": "12px", "fontWeight": "600", "color": TEXT_SECONDARY}),
        html.Th(f"Quadrant ({q1_label})", style={"textAlign": "left", "padding": "6px 12px",
                                                   "fontFamily": FONT_SANS, "fontSize": "12px",
                                                   "fontWeight": "600", "color": TEXT_SECONDARY}),
        html.Th(f"Quadrant ({q2_label})", style={"textAlign": "left", "padding": "6px 12px",
                                                   "fontFamily": FONT_SANS, "fontSize": "12px",
                                                   "fontWeight": "600", "color": TEXT_SECONDARY}),
        html.Th("Direction", style={"textAlign": "left", "padding": "6px 12px", "fontFamily": FONT_SANS,
                                     "fontSize": "12px", "fontWeight": "600", "color": TEXT_SECONDARY}),
    ])

    body_rows = []
    for _, row in sorted_movers.iterrows():
        direction = "Favorable" if row["rank_delta"] > 0 else "Unfavorable" if row["rank_delta"] < 0 else "Lateral"
        dir_color = MIGRATION_FAVORABLE if row["rank_delta"] > 0 else MIGRATION_UNFAVORABLE if row["rank_delta"] < 0 else REFERENCE

        body_rows.append(html.Tr([
            html.Td(row["sku"], style={"padding": "6px 12px", "fontFamily": FONT_SANS,
                                        "fontSize": "13px", "color": INK}),
            html.Td(row.get("product_name_p2", row["sku"]),
                     style={"padding": "6px 12px", "fontFamily": FONT_SANS,
                            "fontSize": "13px", "color": TEXT_SECONDARY}),
            html.Td(row["quadrant_p1"], style={"padding": "6px 12px", "fontFamily": FONT_SANS,
                                                 "fontSize": "13px", "color": TEXT_SECONDARY}),
            html.Td(row["quadrant_p2"], style={"padding": "6px 12px", "fontFamily": FONT_SANS,
                                                 "fontSize": "13px", "color": TEXT_SECONDARY}),
            html.Td(direction, style={"padding": "6px 12px", "fontFamily": FONT_SANS,
                                       "fontSize": "13px", "fontWeight": "600", "color": dir_color}),
        ]))

    return [
        html.H4(
            "All Quadrant Movers",
            style={"fontFamily": FONT_SERIF, "fontSize": "18px", "color": INK,
                   "marginTop": "24px", "marginBottom": "8px"},
        ),
        html.Table(
            [html.Thead(header), html.Tbody(body_rows)],
            style={
                "width": "100%",
                "borderCollapse": "collapse",
                "borderTop": f"1px solid {GRIDLINE}",
            },
        ),
    ]
