"""Thin entry point — named wsgi.py to avoid import collision with app/ package."""

from dotenv import load_dotenv
from flask import jsonify

load_dotenv()

from app.app import server  # noqa: E402
from app.layout import register_layout  # noqa: E402

register_layout()


@server.route("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    from app.app import app

    app.run(debug=True, use_reloader=False, port=8050)
