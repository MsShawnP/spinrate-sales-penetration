"""Shared Economist-style chart defaults and SVG config for Plotly figures."""

from app.constants import (
    CANVAS,
    FONT_SANS,
    FONT_SERIF,
    GRIDLINE,
    INK,
    TEXT_SECONDARY,
)


def economist_layout(**overrides):
    """Return a Plotly layout dict with Lailara/Economist-style defaults."""
    defaults = dict(
        paper_bgcolor=CANVAS,
        plot_bgcolor=CANVAS,
        font=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
        title=dict(font=dict(family=FONT_SERIF, size=22, color=INK)),
        xaxis=dict(
            showgrid=False,
            showline=True,
            linecolor=GRIDLINE,
            tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor=GRIDLINE,
            gridwidth=1,
            showline=False,
            tickfont=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
        ),
        margin=dict(l=60, r=20, t=60, b=40),
        hoverlabel=dict(
            bgcolor=CANVAS,
            font=dict(family=FONT_SANS, size=13, color=INK),
            bordercolor=GRIDLINE,
        ),
        dragmode=False,
        showlegend=True,
        legend=dict(
            font=dict(family=FONT_SANS, size=12, color=TEXT_SECONDARY),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    defaults.update(overrides)
    return defaults


CHART_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "toImageButtonOptions": {"format": "svg"},
}
