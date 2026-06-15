"""Layout assembly — brand frame, tab navigation, filter bar, and content area."""

import json

from dash import Input, Output, callback, dcc, html

from app import lailara_frame
from app.app import app
from app.constants import CHICAGO_20
from app.filters import (
    DEFAULT_FILTER_STATE,
    build_empty_state,
    build_filter_bar,
    register_filter_callbacks,
)
from app.views import quadrant

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


def _build_narrative_placeholder():
    """Placeholder for the narrative intro section (built in U7)."""
    return html.Div(id="narrative-section")


def register_layout():
    """Set app.layout and register all callbacks."""
    inner_layout = html.Div(
        [
            dcc.Store(
                id="filter-state", storage_type="session", data=json.dumps(DEFAULT_FILTER_STATE)
            ),
            dcc.Store(id="selected-sku", storage_type="memory"),
            _build_narrative_placeholder(),
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

    @callback(
        Output("tab-content", "children"),
        Input("main-tabs", "value"),
    )
    def _render_tab(tab_value):
        """Render the selected view's layout."""
        if tab_value == "quadrant":
            return quadrant.layout()
        elif tab_value == "migration":
            return html.Div("Migration view — coming in U4.", className="empty-state")
        elif tab_value == "expansion":
            return html.Div("Expansion cases — coming in U5.", className="empty-state")
        elif tab_value == "at-risk":
            return html.Div("At-risk list — coming in U6.", className="empty-state")
        return html.Div("Unknown tab.")
