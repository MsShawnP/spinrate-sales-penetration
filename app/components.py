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


def _definition_item(term, description):
    """One bold term + muted description line, for use inside definitions_panel()."""
    return html.P(
        [html.Strong(term), f" — {description}"],
        style={
            "margin": "0 0 12px 0",
            "fontFamily": FONT_SANS,
            "fontSize": "15px",
            "lineHeight": "1.5",
            "color": TEXT_SECONDARY,
        },
    )


def definitions_panel():
    """Collapsible metric/quadrant definitions -- same disclosure pattern as
    the narrative section (.narrative-details / .narrative-toggle), placed
    at the bottom of every tab."""
    heading_style = {
        "fontFamily": FONT_SERIF,
        "fontSize": "18px",
        "fontWeight": "700",
        "color": INK,
        "margin": "0 0 12px 0",
    }

    return html.Details(
        [
            html.Summary(
                "How to read this — definitions",
                className="narrative-toggle",
            ),
            html.Div(
                [
                    html.H3("What the axes mean", style=heading_style),
                    _definition_item(
                        "Sales Penetration",
                        "how widely a product is distributed: the breadth of its "
                        "availability across stores. On these charts it's the "
                        "horizontal axis, measured by ACV%.",
                    ),
                    _definition_item(
                        "Sales Velocity",
                        "how fast a product sells once it's on the shelf: the depth "
                        "of demand where it's stocked. On these charts it's the "
                        "vertical axis, measured by SPPD.",
                    ),
                    _definition_item(
                        "ACV% (All-Commodity Volume)",
                        "the share of total retail sales volume, weighted by store "
                        "size, that comes from the stores carrying this SKU. Because "
                        "stores are weighted by their overall sales, being on the "
                        "shelf at large, high-traffic retailers counts for more than "
                        "the same shelf at small ones. Higher ACV% means broader, "
                        "more valuable distribution.",
                    ),
                    _definition_item(
                        "SPPD (Sales Per Point of Distribution, per day)",
                        "how many units sell per carrying store per day: Total Units "
                        "÷ Carrying Stores ÷ Days in Period. It isolates true shelf "
                        "performance from how many doors a product is in, so a niche "
                        "item in a few stores and a giant in thousands can be "
                        "compared on equal footing. Higher SPPD means it sells faster "
                        "wherever it's carried.",
                    ),
                    html.H3(
                        "The four quadrants",
                        style={**heading_style, "marginTop": "20px"},
                    ),
                    html.P(
                        "Each SKU is placed by penetration (ACV%, left→right) and "
                        "velocity (SPPD, bottom→top), split at the median of each.",
                        style={
                            "margin": "0 0 12px 0",
                            "fontFamily": FONT_SANS,
                            "fontSize": "15px",
                            "lineHeight": "1.5",
                            "color": TEXT_SECONDARY,
                        },
                    ),
                    _definition_item(
                        "Stars",
                        "high penetration, high velocity. Widely distributed and "
                        "selling fast. Your proven winners — protect the "
                        "distribution and keep feeding them.",
                    ),
                    _definition_item(
                        "Hidden Gems",
                        "low penetration, high velocity. They sell fast wherever "
                        "they're stocked but aren't in enough doors yet. The biggest "
                        "expansion upside — the priority is getting them onto more "
                        "shelves.",
                    ),
                    _definition_item(
                        "Wide but Dead",
                        "high penetration, low velocity. Everywhere, but not moving. "
                        "You're paying for shelf space that isn't earning it — "
                        "either fix the velocity (pricing, merchandising, promotion) "
                        "or rationalize the distribution.",
                    ),
                    _definition_item(
                        "Question Marks",
                        "low penetration, low velocity. Neither broadly distributed "
                        "nor selling. Small, unproven bets — find the wedge that "
                        "makes one work, or cut it.",
                    ),
                ],
                className="narrative-section",
            ),
        ],
        className="narrative-details",
    )
