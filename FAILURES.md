# Failures — Spinrate Sales Penetration

*What didn't work and why, so we don't repeat it.*

### 2026-06-15 — Mock path `patch("app.db")` fails on lazy imports
- **What happened:** Tests using `patch("app.db")` raised `AttributeError: <module 'app'> does not have the attribute 'db'` because `app/__init__.py` is empty and `db` is imported lazily inside functions with `from app import db`.
- **Root cause:** `unittest.mock.patch` checks that the target attribute exists before patching. When the `db` submodule hasn't been imported yet, it doesn't exist as an attribute on the `app` package.
- **Fix:** Use `patch("app.db", create=True)` to tell mock to create the attribute even if it doesn't exist yet.
- **Lesson:** Any module that uses lazy `from app import X` inside a function body needs `create=True` in its test mocks. This pattern applies whenever the `__init__.py` doesn't re-export the submodule.

### 2026-06-15 — numpy bool `is True` identity check fails
- **What happened:** `assert row["limited_history"] is True` failed because pandas returns `np.True_` which is not identical to Python's `True`.
- **Fix:** Use `== True` instead of `is True` for boolean comparisons on pandas/numpy values.
- **Lesson:** Never use `is` for boolean identity checks on values that come from pandas DataFrames. Always use `==`.

### 2026-06-15 — U5 subagent socket crash mid-implementation
- **What happened:** Subagent implementing expansion.py crashed with `API Error: The socket connection was closed unexpectedly`. It had created the main source file and modified layout.py but hadn't written tests or committed.
- **Fix:** Verified created files manually, wrote tests inline in the orchestrator context, then committed.
- **Lesson:** For subagent-dispatched work, verify file state after crashes rather than re-dispatching. The partial work may be correct and complete.
