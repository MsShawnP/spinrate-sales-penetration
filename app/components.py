"""Shared reusable Dash HTML components — dark callout cards, annotations, error banners."""

from dash import html

from app.constants import (
    CARD_BG,
    CARD_BORDER,
    CARD_ITEM,
    CARD_MUTED,
    CARD_SUBTITLE,
    CARD_TEXT,
    FAIL_BG,
    GRIDLINE,
    RED_42,
    TEXT_SECONDARY,
)


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
