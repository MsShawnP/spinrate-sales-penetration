"""Dash application factory — no external stylesheets, no dash-bootstrap-components."""

import os
import secrets

import dash

app = dash.Dash(
    __name__,
    assets_folder="../assets",
    suppress_callback_exceptions=True,
    title="Spin Rate — Penetration × Velocity",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server
server.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
