"""Shared filter bar component and callbacks."""

import json

from dash import Input, Output, State, callback, dcc, html, no_update

QUARTER_OPTIONS = [
    {"label": f"Q{q} {y}", "value": f"Q{q} {y}"} for y in [2024, 2025] for q in [1, 2, 3, 4]
]

DEFAULT_START_QUARTER = "Q1 2025"
DEFAULT_END_QUARTER = "Q4 2025"

DEFAULT_FILTER_STATE = {
    "retailers": [],
    "region": None,
    "start_quarter": DEFAULT_START_QUARTER,
    "end_quarter": DEFAULT_END_QUARTER,
}


def build_filter_bar():
    """Return the filter bar component.

    Retailer and region options are populated from the database at startup.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Retailer"),
                    dcc.Dropdown(
                        id="filter-retailer",
                        options=[],
                        value=[],
                        multi=True,
                        placeholder="All retailers",
                        clearable=False,
                    ),
                ],
                className="filter-group",
                style={"minWidth": "220px", "flex": "1"},
            ),
            html.Div(
                [
                    html.Label("Region"),
                    dcc.Dropdown(
                        id="filter-region",
                        options=[],
                        value=None,
                        multi=False,
                        placeholder="All regions",
                        clearable=True,
                    ),
                ],
                className="filter-group",
                style={"minWidth": "160px", "flex": "1"},
            ),
            html.Div(
                [
                    html.Label("Start Quarter"),
                    dcc.Dropdown(
                        id="filter-start-quarter",
                        options=QUARTER_OPTIONS,
                        value=DEFAULT_START_QUARTER,
                        clearable=False,
                        searchable=False,
                    ),
                ],
                className="filter-group",
                style={"minWidth": "140px"},
            ),
            html.Div(
                [
                    html.Label("End Quarter"),
                    dcc.Dropdown(
                        id="filter-end-quarter",
                        options=QUARTER_OPTIONS,
                        value=DEFAULT_END_QUARTER,
                        clearable=False,
                        searchable=False,
                    ),
                ],
                className="filter-group",
                style={"minWidth": "140px"},
            ),
        ],
        className="filter-bar",
    )


def build_empty_state():
    """Return the empty-state placeholder shown when no data matches filters."""
    return html.Div(
        [
            html.P("No data matches the current filters."),
            html.Button("Reset filters", id="reset-filters-btn", n_clicks=0),
        ],
        id="empty-state",
        className="empty-state",
        style={"display": "none"},
    )


def register_filter_callbacks():
    """Register all filter-related callbacks."""

    @callback(
        Output("filter-state", "data"),
        Input("filter-retailer", "value"),
        Input("filter-region", "value"),
        Input("filter-start-quarter", "value"),
        Input("filter-end-quarter", "value"),
    )
    def _sync_filter_state(retailers, region, start_q, end_q):
        """Write current filter selections to the shared store."""
        return json.dumps(
            {
                "retailers": retailers or [],
                "region": region,
                "start_quarter": start_q,
                "end_quarter": end_q,
            }
        )

    @callback(
        Output("filter-retailer", "value"),
        Output("filter-region", "value"),
        Output("filter-start-quarter", "value"),
        Output("filter-end-quarter", "value"),
        Input("reset-filters-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _reset_filters(n_clicks):
        """Reset all filters to defaults."""
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        return (
            [],
            None,
            DEFAULT_START_QUARTER,
            DEFAULT_END_QUARTER,
        )
