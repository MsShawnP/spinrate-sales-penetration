"""Shared reusable Dash HTML components — dark callout cards, annotations, error banners."""

import dash_ag_grid as dag
from dash import html

from app.constants import (
    CARD_BG,
    CARD_BORDER,
    CARD_ITEM,
    CARD_MUTED,
    CARD_SUBTITLE,
    CARD_TEXT,
    FAIL_BG,
    FONT_SANS,
    FONT_SERIF,
    GRIDLINE,
    INK,
    RED_42,
    TEXT_SECONDARY,
    WHITE,
)


def data_grid(grid_id, column_defs, aria_label=None):
    """Shared data table used by every spreadsheet-style view.

    One source of truth so all grids behave identically:
    - No pagination and ``domLayout='autoHeight'`` → every row renders, no
      vertical scroll.
    - ``columnSize='responsiveSizeToFit'`` → columns re-fit to the grid
      width whenever data loads or the grid resizes (``autoSize`` measured
      against the empty initial ``rowData`` and collapsed every column to
      a single character).
    - ``.spinrate-grid`` applies a compact font and tighter cell padding.
    - Wrapped in ``.grid-wide`` so the table may extend wider than the
      centered content column.
    """
    grid = dag.AgGrid(
        id=grid_id,
        columnDefs=column_defs,
        rowData=[],
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        # responsiveSizeToFit re-fits columns to the grid width whenever the
        # data loads or the grid resizes. autoSize measured against the empty
        # initial rowData and collapsed columns to a single character.
        columnSize="responsiveSizeToFit",
        dashGridOptions={
            "pagination": False,
            "domLayout": "autoHeight",
            "rowSelection": {"mode": "singleRow"},
            "animateRows": True,
        },
        style={"width": "100%"},
        className="ag-theme-alpine spinrate-grid",
    )
    wrapper_attrs = {"aria-label": aria_label} if aria_label else {}
    return html.Div(grid, className="grid-wide", **wrapper_attrs)


def dark_callout_card(title, subtitle=None, rows=None):
    """Dark callout card for click-to-pin detail displays.

    Args:
        title: Primary heading text (e.g. SKU name).
        subtitle: Optional secondary line below the title.
        rows: List of dicts with 'label' and 'value' keys.
    """
    children = [
        html.H3(
            title,
            style={
                "color": CARD_TEXT,
                "fontFamily": "var(--ll-serif)",
                "fontSize": "20px",
                "fontWeight": "700",
                "margin": "0 0 4px 0",
            },
        ),
    ]

    if subtitle:
        children.append(
            html.P(
                subtitle,
                style={
                    "color": CARD_SUBTITLE,
                    "fontFamily": "var(--ll-sans)",
                    "fontSize": "14px",
                    "margin": "0 0 12px 0",
                },
            )
        )

    if rows:
        for row in rows:
            children.append(
                html.Div(
                    [
                        html.Span(
                            row["label"],
                            style={
                                "color": CARD_MUTED,
                                "fontFamily": "var(--ll-sans)",
                                "fontSize": "13px",
                            },
                        ),
                        html.Span(
                            row["value"],
                            style={
                                "color": CARD_ITEM,
                                "fontFamily": "var(--ll-sans)",
                                "fontSize": "14px",
                                "fontWeight": "600",
                            },
                        ),
                    ],
                    style={
                        "display": "flex",
                        "justifyContent": "space-between",
                        "alignItems": "center",
                        "padding": "6px 0",
                        "borderBottom": f"1px solid {CARD_BORDER}",
                    },
                )
            )

    return html.Div(
        children,
        className="dark-callout",
        style={
            "backgroundColor": CARD_BG,
            "padding": "20px 24px",
            "borderRadius": "2px",
            "marginTop": "16px",
        },
    )


def hero_card(value, label, accent=None):
    """Headline-metric hero card -- serif value, sans label, white card.

    Shared by Expansion (dollar upside per benchmark) and At-Risk (tier
    counts). `accent`, if given, colors a top border stripe so cards in a
    group can be told apart by severity/category without changing the
    neutral ink-colored value text.
    """
    style = {
        "background": WHITE,
        "border": f"1px solid {GRIDLINE}",
        "borderRadius": "2px",
        # Spacing-scale "lg" token (24px) on all sides -- 20px vertical
        # wasn't a documented spacing token.
        "padding": "24px",
        "minWidth": "180px",
        "flex": "1",
    }
    if accent:
        style["borderTop"] = f"3px solid {accent}"

    return html.Div(
        [
            html.Span(
                value,
                style={
                    "fontFamily": FONT_SERIF,
                    "fontSize": "28px",
                    "fontWeight": "700",
                    "color": INK,
                    "letterSpacing": "-0.02em",
                    "display": "block",
                    "lineHeight": "1.2",
                },
            ),
            html.Span(
                label,
                style={
                    "fontFamily": FONT_SANS,
                    "fontSize": "13px",
                    "fontWeight": "600",
                    "color": TEXT_SECONDARY,
                    "display": "block",
                    # Spacing-scale "sm" token (8px) -- 6px wasn't a
                    # documented spacing token.
                    "marginTop": "8px",
                },
            ),
        ],
        style=style,
    )


def annotation_callout(text):
    """Insight-line annotation callout — left-border accent."""
    return html.Div(
        html.P(
            text,
            style={
                "margin": "0",
                "fontFamily": "var(--ll-sans)",
                "fontSize": "15px",
                "lineHeight": "1.5",
                "color": TEXT_SECONDARY,
            },
        ),
        className="insight-line",
        style={
            "borderLeft": f"3px solid {GRIDLINE}",
            "paddingLeft": "16px",
            "marginTop": "12px",
            "marginBottom": "12px",
        },
    )


def error_banner(message, retry_id=None):
    """Error banner with optional retry button."""
    children = [
        html.Span(
            message,
            style={
                "fontFamily": "var(--ll-sans)",
                "fontSize": "14px",
                "color": RED_42,
            },
        ),
    ]

    if retry_id:
        children.append(
            html.Button(
                "Retry",
                id=retry_id,
                n_clicks=0,
                style={
                    "marginLeft": "12px",
                    "cursor": "pointer",
                },
            )
        )

    return html.Div(
        children,
        className="error-banner",
        style={
            "display": "flex",
            "alignItems": "center",
            "padding": "12px 16px",
            "backgroundColor": FAIL_BG,
            "borderRadius": "2px",
            "marginBottom": "16px",
        },
    )
