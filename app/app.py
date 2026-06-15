"""Dash application factory — no external stylesheets, no dash-bootstrap-components."""

import dash

app = dash.Dash(
    __name__,
    assets_folder="../assets",
    suppress_callback_exceptions=True,
    title="Spin Rate — Penetration × Velocity",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server
