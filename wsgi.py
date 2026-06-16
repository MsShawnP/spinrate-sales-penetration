"""Thin entry point — named wsgi.py to avoid import collision with app/ package."""

from dotenv import load_dotenv
from flask import jsonify

load_dotenv()

from app.app import server  # noqa: E402
from app.layout import register_layout  # noqa: E402

register_layout()


@server.route("/health")
def health():
    """Health check with database connectivity status."""
    db_ok = False
    try:
        from app.db import _get_pool
        from psycopg2 import pool as _pool_mod
        p = _get_pool()
        conn = p.getconn(timeout=3)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            db_ok = True
        finally:
            p.putconn(conn)
    except _pool_mod.PoolError:
        pass
    except Exception:
        pass

    status = "ok" if db_ok else "degraded"
    return jsonify(status=status, database=db_ok), 200 if db_ok else 503


if __name__ == "__main__":
    from app.app import app

    import os
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
        use_reloader=False,
        port=8050,
    )
