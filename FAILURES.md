# Failures — Spinrate Sales Penetration

*What didn't work and why, so we don't repeat it.*

### 2026-07-02 — Concurrent-session git race recurred despite an existing documented lesson
- **What happened:** Mid-edit on `app/constants.py` (fixing the categorical product-line palette), a second Claude Code session was independently committing to the same file. My in-progress edit got swept into the other session's commit (`c021056`) because there's one shared git index per working directory, not one per session — the exact failure mode already documented in this file's `DECISIONS.md` entry from session 12. The other session then explicitly overrode my fix with its own follow-up commit.
- **Root cause:** Two active Claude Code sessions in the same working directory at the same time, with no coordination mechanism between them.
- **Fix:** Detected it via `git log` (an unrecognized commit appearing mid-task) and by diffing the actual file content against what I'd written. Stopped issuing further `git add`/`commit` and flagged the situation to the user instead of pushing forward.
- **Lesson:** The existing DECISIONS.md guidance ("stand down on git entirely when a second session is live") is correct but doesn't prevent the race from happening — it only tells you what to do once you notice it. Detection requires actively watching `git log` for unrecognized commits during multi-step tasks, not just checking `git status` before your own commits.

- **What happened:** Diagnosed the quadrant legend clipping bug as a Plotly.js text-measurement race against the async Source Sans 3 web font (`font-display: swap`). Tried forcing Plotly to re-measure/redraw the legend once `document.fonts.ready` resolved, via `Plotly.Plots.resize()` and separately `Plotly.react()`. Live browser tests gave inconsistent results — legend entry positions sometimes stayed frozen at their pre-swap (wrong) values even after the resize/relayout call.
- **Root cause:** Plotly's legend text-width measurement appears to be cached in a way that isn't reliably invalidated by a resize/relayout call alone when the font-family string itself hasn't changed — only the browser's live rendering of it has (pre- vs post-swap).
- **Fix:** Abandoned trying to force-correct Plotly's own SVG legend after the fact. Replaced it entirely with a custom HTML/CSS grid legend (`_build_custom_legend` in `app/views/quadrant.py`), which reflows correctly on any font swap because it's normal DOM text, not an SVG measurement cache.
- **Lesson:** Don't trust `Plotly.Plots.resize()`/`Plotly.react()` to fix a legend/text sizing bug caused by an async font swap — verify live before committing to that fix. If a chart element must render web-font text at guaranteed-correct sizing, prefer plain HTML/CSS over Plotly's SVG-based legend/annotation text.

### 2026-07-02 — Synthetic browser reproduction of a font-load race was too fragile to trust
- **What happened:** Tried to cleanly reproduce the legend clipping bug in isolation by declaring a second `@font-face` rule with `local()` sources to simulate a font swap completing after Plotly's first layout pass. The test page hung / `document.fonts.load()` never resolved as expected, and repeated `preview_eval` calls timed out.
- **Root cause:** `local()` font-face sources resolve near-synchronously (no real network delay to race against), so the synthetic setup couldn't actually recreate the timing window the real bug depends on. Compounded by sequential browser-state mutations across many eval calls in one page session, which made results hard to trust even when they did return.
- **Fix:** Stopped trying to simulate the race and instead tunneled to the real production Postgres via `fly proxy`, then rendered the actual chart-building code against real data with real fonts loading over a real network — reproduced and later confirmed-fixed the bug cleanly on the first real-data test.
- **Lesson:** For browser timing races (font loads, resource loads), don't try to fake the race with `local()` sources or similar shortcuts — either use the real asset over a real network, or don't attempt a synthetic repro at all. Verifying against real data early would have saved significant time here.

### 2026-07-01 — Redeployed without baselining /health first, surfaced an outage mid-rollout
- **What happened:** Redeployed spinrate to ship two verified code fixes. The deploy errored with a Fly API timeout mid-rollout, and only then was it discovered that production was already returning 503 (`database:false`) before the deploy even started — the deploy just rolled machines that were already destined to fail Fly's health gate.
- **Root cause:** Assumed prod was healthy going into the deploy instead of checking. The actual break (a stale `DATABASE_URL` secret) predated the deploy entirely.
- **Fix:** None needed to the deploy itself — separately fixed the credential (see DECISIONS.md). 
- **Lesson:** Always curl `/health` (or equivalent) before redeploying, even for a "just shipping a verified fix" deploy. A calm baseline check surfaces a pre-existing outage cleanly; discovering it via a failed rollout is alarming and wastes time distinguishing "did my deploy break this" from "was this already broken."

### 2026-07-01 — Mischaracterized a `critical` check as a `warning` when translating to plain English
- **What happened:** Told the user "the database server itself still shows one internal warning light" when the actual check status was `critical` (`pg: critical — connect: connection refused` on the cinderhaven-db app). Also separately cited a real `warning` status (Fly autoscaler's stopped-machine check) for spinrate, and blurred the two together in the summary.
- **Root cause:** Simplifying jargon for a non-technical summary dropped the actual severity level, not just the technical detail.
- **Fix:** Re-pulled `flyctl checks list` for both apps and gave the exact check names/statuses/output.
- **Lesson:** When translating infra status to plain English, keep the severity word (critical/warning/passing) verbatim even while simplifying everything else around it — severity is exactly the thing a non-technical reader needs preserved.

### 2026-06-18 — Could not measure first-paint via the standard browser APIs in the preview tool
- **What happened:** Tried to read First Contentful Paint with `performance.getEntriesByType('paint')` in the preview/automation browser — returned an empty array despite `PerformanceObserver.supportedEntryTypes` reporting `paint` as supported. Separately, `preview_screenshot` timed out (30s) every time, even with the spinner animation paused.
- **Root cause:** The automation browser doesn't populate Paint Timing entries the way a normal Chrome session does. The screenshot timeout is the Dash dev server holding connections open (long-poll / keep-alive) so the page never reaches the "network idle" state the screenshot tool waits for.
- **Fix:** Measured first paint by instrumenting the overlay's own inline script with temporary `performance.now()` marks (`window.__srPaintAt` / `__srClearedAt`), read them via `preview_eval`, then stripped the marks before commit. Verified appearance with `preview_inspect` computed styles (exact token values) instead of a screenshot.
- **Lesson:** In the preview/automation browser, don't rely on `getEntriesByType('paint')` for FCP or on `preview_screenshot` for a Dash dev-server page. Instrument with `performance.now()` marks for timing and use `preview_inspect` for visual/style verification — the tool guidance already says inspect is more reliable than screenshots for styles.

### 2026-06-17 — At-risk OOM invisible from outside; only visible in fly logs
- **What happened:** At-risk tab returned zero rows in production. Health checks passed, app responded 200 on all other tabs. No user-visible error.
- **Root cause:** The at-risk trend calculation loaded all ~1.2M raw scan rows (12 quarters × ~100K rows each) for OLS regression. On a 1024MB Fly.io VM with 2 gunicorn workers, this exceeded available memory. The OOM killed the worker, Firecracker restarted it, and health checks passed on the fresh process — so the failure was invisible unless you checked `fly logs` or specifically clicked the at-risk tab.
- **Fix:** Pushed aggregation to SQL with `get_quarterly_sppd()` — returns ~600 rows instead of 1.2M. Same OLS logic, 2000x less memory.
- **Lesson:** After deploying any view that touches large datasets, verify that specific view loads in production — don't rely on health checks or other tabs working. Also check `fly logs` for OOM patterns (`Process appears to have been OOM killed`). Consider adding per-view health checks or memory budgets.

### 2026-06-17 — Production data never synced after archetype variance fix
- **What happened:** Production ACV was clustered 27.5%-34.5% despite local database having correct 5%-62% range. Expansion and At-Risk tabs failed to load meaningful data in production.
- **Root cause:** The archetype-driven variance was added to seed_config.py and re-seeded locally, but the production Fly.io Postgres was never updated. Multiple sessions verified views against localhost but nobody synced to production.
- **Fix:** Built a Python CSV dump → gzip → fly sftp → on-machine restore pipeline. Transferred 5 mart tables (10 MB compressed).
- **Lesson:** After any data schema or seed change, add a production data verification step to the deploy checklist. A post-deploy smoke script that checks ACV min/max/std would catch this instantly.

### 2026-06-17 — fly postgres connect password auth failure
- **What happened:** `fly postgres connect --app cinderhaven-db` failed with "password authentication failed for user postgres".
- **Root cause:** The Fly Postgres secrets (OPERATOR_PASSWORD, SU_PASSWORD) were in "Staged" state, not "Deployed". The database was running with older credentials.
- **Fix:** Bypassed by SSHing into the spinrate app machine instead, which already has the correct DATABASE_URL secret.
- **Lesson:** For Cinderhaven tools, use `fly ssh console --app <tool-app> -C "python3 ..."` to run queries through the app's configured DATABASE_URL rather than connecting to the Postgres app directly.

### 2026-06-17 — No pg_dump/psql on Windows or WSL for database sync
- **What happened:** Needed to transfer database tables from local to production. Neither pg_dump nor psql were available on Windows or in WSL.
- **Fix:** Wrote a Python script using psycopg2's `copy_expert()` to dump tables to CSV, gzip-compressed them, uploaded via `fly sftp put`, and restored on the production machine with another Python script.
- **Lesson:** Keep a Python-based database sync utility in the Cinderhaven data platform for future use. The CSV dump + gzip + sftp pattern works reliably and doesn't require PostgreSQL client tools.

### 2026-06-16 — Fading archetype decline too shallow, masked by seasonal bump
- **What happened:** After adding the "fading" archetype (above-median velocity declining over time), the watchlist tier had 0 items. All 3 fading SKUs showed trend="flat" instead of "declining."
- **Root cause:** The fading decline factor (1.15→0.70, 39% drop over 2 years) was too shallow. The Q4 seasonal multiplier in the synthetic data boosts raw values ~30-40% every year, creating a sawtooth pattern that the OLS regression sees as flat. The `_TREND_THRESHOLD = 0.05` (5% of mean) requires a strong enough slope to overcome seasonal noise.
- **Fix:** Steepened fading decline to 1.3→0.4 (matching the at_risk archetype, 69% drop). The archetype velocity multiplier (2.2-3.0) still keeps fading SKUs above median, while the steeper decline registers as "declining" in the OLS regression.
- **Lesson:** When designing synthetic data decline curves for OLS-based trend detection, the decline must be steep enough to overcome seasonal variation in the raw data. Test decline factors against the actual trend calculation before seeding — don't assume a "moderate" decline will register.

### 2026-06-16 — Fading archetype decline too shallow, masked by Q4 seasonal noise
- **What happened:** Added "fading" archetype to Cinderhaven seed data with decline factor 1.15→0.70 (39% drop). Expected above-median + declining = watchlist tier. Got 0 watchlist items — all fading SKUs registered as "flat" trend.
- **Root cause:** The Q4 seasonal multiplier boosts raw values 30-40% every year, creating a sawtooth pattern. OLS regression over 8 quarters sees the seasonal bumps as noise that cancels the 39% decline, producing a normalized slope within the ±5% flat threshold.
- **Fix:** Steepened fading decline to 1.3→0.4 (69% drop, matching at_risk archetype). The archetype velocity multiplier (2.2-3.0) keeps fading SKUs above median while the steeper decline registers clearly in OLS.
- **Lesson:** When synthetic data has seasonal multipliers, decline factors must be steep enough to overcome the seasonal amplitude in the trend detection algorithm. Test archetype patterns against the actual trend calculation before committing to a full reseed.

### 2026-06-16 — Plotly 6.0 binary-encodes numpy arrays, breaks Dash 3.x charts
- **What happened:** Quadrant chart callback returned 200 with valid-looking data, but the chart rendered empty — zero data points visible.
- **Root cause:** Plotly Python 6.0's `.to_plotly_json()` serializes numpy arrays as `{dtype: "f8", bdata: "base64..."}`. Plotly.js 3.6.0 (bundled with Dash 3.x) cannot decode this binary format — the browser receives Object instances with no `.length`, so traces render with 0 points.
- **Fix:** Call `.tolist()` on every pandas Series or numpy array passed to Plotly trace constructors (`x=`, `y=`, `customdata=`, `marker.size=`, `marker.color=`). This forces JSON-array serialization that Plotly.js 3.6.0 can read.
- **Lesson:** When using Plotly 6.0 with Dash 3.x, always convert pandas Series to Python lists before passing to `go.Scatter()`, `go.Bar()`, etc. The Decimal-to-float fix (below) handles type conversion at the data layer; this fix handles serialization format at the chart layer. Both are needed.

### 2026-06-16 — psycopg2 Decimal types break Plotly 6.0 marker arrays
- **What happened:** Quadrant chart rendered blank — all four views showed empty/error states despite the narrative intro pulling real data. The `except Exception` in the callback silently caught the error and returned an empty figure.
- **Root cause:** psycopg2 returns Postgres `numeric` columns as Python `Decimal` objects. `np.sqrt(Decimal)` produces a Decimal-backed Series (`dtype: object`). Plotly 6.0 rejects non-float arrays for `marker.size` with `ValueError: Input value is not numeric`. Plotly 5.x was lenient about this.
- **Fix:** Cast Decimal columns to float in `_execute_query()` (db.py line 81) — one fix at the data layer instead of patching individual views.
- **Lesson:** When psycopg2 feeds a Plotly 6.0 pipeline, always cast Decimal to float at the DataFrame construction point. Don't patch downstream functions. Also: bare `except` blocks that return empty figures hide the real error — the narrative worked fine because it only used the data for string formatting, not Plotly arrays.

### 2026-06-16 — Flycast hostname unreachable from local dev
- **What happened:** Copied `DATABASE_URL` from cinderhaven-data-platform `.env`. Connection failed with `could not translate host name "cinderhaven-db.flycast"`.
- **Root cause:** `.flycast` is Fly.io's private DNS, only resolvable inside their network. Local dev needs `localhost:5432/cinderhaven`.
- **Fix:** Used the-question-engine's `.env` which points to localhost. Other projects (recall-blast-radius, trade-spend-leakage, etc.) also use localhost.
- **Lesson:** For local dev of any Cinderhaven tool, use a sibling project's `.env` that points to localhost, not the data-platform `.env` which uses the Fly.io internal hostname.

### 2026-06-16 — Dash 4.x injects purple accent-color on dropdown controls
- **What happened:** Dropdown borders appeared purple despite all CSS using correct Chicago-20 navy tokens.
- **Root cause:** Dash 4.x sets `accent-color: rgb(127, 75, 196)` directly on `.dash-dropdown` button elements. Setting `accent-color` on `:root` doesn't cascade because the element-level style has higher specificity.
- **Fix:** Override with `accent-color: var(--ll-chicago-20) !important` on both `:root` and `.dash-dropdown`.
- **Lesson:** When using Dash 4.x with a custom design system, override `accent-color` on `.dash-dropdown` specifically, not just `:root`.

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
