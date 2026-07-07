"""Postgres connection pool and query functions for Cinderhaven SSOT.

Uses psycopg2 directly (no ORM). Module-level connection pool via
DATABASE_URL environment variable. Query results cached per filter
combination; callers receive .copy() to prevent mutation of cache.
"""

import hashlib
import logging
import os
import threading
from decimal import Decimal

import pandas as pd
import psycopg2
from psycopg2 import pool

from app.calculations import (
    calculate_acv_pct,
    calculate_category_median_sppd,
    calculate_global_medians,
    calculate_sppd_from_agg,
    days_in_quarter_range,
)
from app.filters import DEFAULT_END_QUARTER, DEFAULT_START_QUARTER

logger = logging.getLogger(__name__)

# ── Connection pool ─────────────────────────────────────────────────
_pool = None
_pool_lock = threading.Lock()

# Query timeout in milliseconds (30 seconds).
_QUERY_TIMEOUT_MS = 30_000


def _get_pool():
    """Return the module-level connection pool, creating it on first call.

    Raises RuntimeError if DATABASE_URL is not set so the app fails fast
    at startup rather than producing a confusing runtime error.
    """
    global _pool
    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is not None:
            return _pool

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Set it to a postgresql:// connection string pointing at the Cinderhaven SSOT."
            )

        try:
            _pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=database_url,
                options=f"-c statement_timeout={_QUERY_TIMEOUT_MS} -c search_path=public_marts,public",
            )
        except psycopg2.OperationalError as exc:
            raise RuntimeError(
                f"Could not connect to Cinderhaven SSOT database: {exc}"
            ) from exc

    return _pool


def _execute_query(sql, params=None):
    """Execute a parameterized query and return a pandas DataFrame.

    Handles connection checkout/return and converts psycopg2 timeouts
    into a graceful empty DataFrame with a logged warning.
    """
    p = _get_pool()
    try:
        conn = p.getconn()
    except pool.PoolError:
        logger.error("Connection pool exhausted — returning empty DataFrame")
        return pd.DataFrame()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=cols)
        for col in df.columns:
            if df[col].dtype == object and len(df) > 0:
                if isinstance(df[col].iloc[0], Decimal):
                    df[col] = df[col].astype(float)
        return df
    except psycopg2.extensions.QueryCanceledError:
        conn.rollback()
        logger.warning("Query timed out after %d ms — returning empty DataFrame", _QUERY_TIMEOUT_MS)
        return pd.DataFrame()
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
        logger.error("Database connection failed: %s", exc)
        p.putconn(conn, close=True)
        conn = None
        return pd.DataFrame()
    except psycopg2.Error as exc:
        conn.rollback()
        logger.error("Database query failed: %s", exc)
        return pd.DataFrame()
    finally:
        if conn is not None:
            p.putconn(conn)


# ── Result cache ────────────────────────────────────────────────────
_cache = {}
_CACHE_MAX_ENTRIES = 128


def _cache_key(prefix, filters):
    """Build a deterministic cache key from a prefix and filter dict."""
    normalized = {}
    if filters:
        for k, v in filters.items():
            normalized[k] = sorted(v) if isinstance(v, list) else v
    raw = f"{prefix}|{sorted(normalized.items()) if normalized else ''}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cached(prefix, filters, loader):
    """Return a cached DataFrame copy, populating on first call."""
    key = _cache_key(prefix, filters)
    if key not in _cache:
        result = loader()
        if not result.empty:
            if len(_cache) >= _CACHE_MAX_ENTRIES:
                oldest = next(iter(_cache))
                del _cache[oldest]
            _cache[key] = result
        return result.copy()
    return _cache[key].copy()


def clear_cache():
    """Clear the query cache. Useful for testing or manual refresh."""
    _cache.clear()


# ── Public query functions ──────────────────────────────────────────

def get_scan_data(filters=None):
    """Fetch POS scan data from fct_scan_data, optionally filtered.

    Columns returned: sku, store_id, week_ending, units_sold, dollars_sold.

    Supported filter keys:
        retailers  - list of retailer names (joined via dim_stores)
        region     - single region string
        start_quarter / end_quarter - e.g. "Q1 2025" / "Q4 2025"
    """
    filters = filters or {}

    def _load():
        clauses = []
        params = []

        # Quarter filters translate to week_ending date ranges.
        start_q = filters.get("start_quarter")
        end_q = filters.get("end_quarter")
        if start_q:
            start_date = _quarter_start_date(start_q)
            clauses.append("sd.week_ending >= %s")
            params.append(start_date)
        if end_q:
            end_date = _quarter_end_date(end_q)
            clauses.append("sd.week_ending <= %s")
            params.append(end_date)

        retailers = filters.get("retailers")
        region = filters.get("region")

        needs_store_join = bool(retailers) or bool(region)

        if needs_store_join:
            base = (
                "SELECT sd.sku, sd.store_id, sd.week_ending, "
                "sd.units_sold, sd.dollars_sold "
                "FROM fct_scan_data sd "
                "INNER JOIN dim_stores ds ON sd.store_id = ds.store_id"
            )
            if retailers:
                placeholders = ", ".join(["%s"] * len(retailers))
                clauses.append(f"ds.retailer IN ({placeholders})")
                params.extend(retailers)
            if region:
                clauses.append("ds.region = %s")
                params.append(region)
        else:
            base = (
                "SELECT sd.sku, sd.store_id, sd.week_ending, "
                "sd.units_sold, sd.dollars_sold "
                "FROM fct_scan_data sd"
            )

        sql = base
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sd.sku, sd.store_id, sd.week_ending"

        return _execute_query(sql, params)

    return _cached("scan_data", filters, _load)


def _scan_data_agg_from_scan(clauses, params, needs_store_join=False):
    """Aggregate per-SKU scan totals from fct_scan_data via GROUP BY."""
    if needs_store_join:
        base = (
            "SELECT sd.sku, "
            "SUM(sd.units_sold) AS total_units, "
            "SUM(sd.dollars_sold) AS total_dollars, "
            "COUNT(DISTINCT sd.store_id) AS door_count "
            "FROM fct_scan_data sd "
            "INNER JOIN dim_stores ds ON sd.store_id = ds.store_id"
        )
    else:
        base = (
            "SELECT sd.sku, "
            "SUM(sd.units_sold) AS total_units, "
            "SUM(sd.dollars_sold) AS total_dollars, "
            "COUNT(DISTINCT sd.store_id) AS door_count "
            "FROM fct_scan_data sd"
        )
    if clauses:
        base += " WHERE " + " AND ".join(clauses)
    base += " GROUP BY sd.sku ORDER BY sd.sku"
    return _execute_query(base, params)


def get_scan_data_agg(filters=None):
    """Fetch per-SKU aggregated scan data.

    Fast path reads mart_sku_scan_totals directly (~50 rows, no GROUP BY),
    but only when no restriction is in effect: the mart has no retailer
    dimension and covers the full default quarter range, so any retailer/
    region filter or narrower date selection falls back to a GROUP BY
    over fct_scan_data with the appropriate WHERE clauses.

    Returns ~50 rows. Columns: sku, total_units, total_dollars, door_count.
    """
    filters = filters or {}

    def _load():
        retailers = filters.get("retailers")
        region = filters.get("region")
        needs_store_filter = bool(retailers) or bool(region)

        start_q = filters.get("start_quarter")
        end_q = filters.get("end_quarter")
        # The mart aggregates the full default range; a date restriction is
        # in effect whenever either bound narrows that range.
        needs_date_filter = (
            (start_q is not None and start_q != DEFAULT_START_QUARTER)
            or (end_q is not None and end_q != DEFAULT_END_QUARTER)
        )

        if not needs_store_filter and not needs_date_filter:
            sql = (
                "SELECT sku, "
                "total_units::float AS total_units, "
                "total_dollars::float AS total_dollars, "
                "door_count::int AS door_count "
                "FROM mart_sku_scan_totals "
                "ORDER BY sku"
            )
            df = _execute_query(sql)
            if df.empty:
                df = _scan_data_agg_from_scan([], [])
            return df

        clauses = []
        params = []

        if start_q:
            clauses.append("sd.week_ending >= %s")
            params.append(_quarter_start_date(start_q))
        if end_q:
            clauses.append("sd.week_ending <= %s")
            params.append(_quarter_end_date(end_q))

        if retailers:
            placeholders = ", ".join(["%s"] * len(retailers))
            clauses.append(f"ds.retailer IN ({placeholders})")
            params.extend(retailers)
        if region:
            clauses.append("ds.region = %s")
            params.append(region)

        return _scan_data_agg_from_scan(
            clauses, params, needs_store_join=needs_store_filter
        )

    return _cached("scan_data_agg", filters, _load)


def get_distribution(filters=None):
    """Fetch distribution/authorization data from fct_distribution.

    Columns returned: sku, store_id, retailer_id, chain_name, region,
    state, volume_tier, authorized_date, deauthorized_date, is_active,
    weeks_with_sales, total_units, total_dollars, avg_weekly_units,
    first_scan_week, last_scan_week.
    """
    filters = filters or {}

    def _load():
        clauses = ["fd.is_active = TRUE"]
        params = []

        retailers = filters.get("retailers")
        region = filters.get("region")

        if retailers:
            placeholders = ", ".join(["%s"] * len(retailers))
            clauses.append(f"fd.chain_name IN ({placeholders})")
            params.extend(retailers)
        if region:
            clauses.append("fd.region = %s")
            params.append(region)

        sql = (
            "SELECT fd.sku, fd.store_id, fd.retailer_id, fd.chain_name, "
            "fd.region, fd.state, fd.volume_tier, fd.authorized_date, "
            "fd.deauthorized_date, fd.is_active, fd.weeks_with_sales, "
            "fd.total_units, fd.total_dollars, fd.avg_weekly_units, "
            "fd.first_scan_week, fd.last_scan_week "
            "FROM fct_distribution fd"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY fd.sku, fd.store_id"

        return _execute_query(sql, params)

    return _cached("distribution", filters, _load)


def get_stores():
    """Fetch the full store dimension from dim_stores.

    Columns returned: store_id, retailer, region, state, volume_tier.
    Unfiltered -- returns the full universe.
    """

    def _load():
        sql = (
            "SELECT store_id, retailer, region, state, volume_tier "
            "FROM dim_stores "
            "ORDER BY store_id"
        )
        return _execute_query(sql)

    return _cached("stores", {}, _load)


def get_benchmarks():
    """Fetch category-level benchmarks from dim_category_benchmarks.

    Columns returned: product_line, sku_count, store_count,
    avg_weekly_units_per_store, total_units, total_dollars,
    avg_cogs, avg_msrp, avg_margin_per_unit, avg_margin_pct.
    """

    def _load():
        sql = (
            "SELECT product_line, sku_count, store_count, "
            "avg_weekly_units_per_store, total_units, total_dollars, "
            "avg_cogs, avg_msrp, avg_margin_per_unit, avg_margin_pct "
            "FROM dim_category_benchmarks "
            "ORDER BY product_line"
        )
        return _execute_query(sql)

    return _cached("benchmarks", {}, _load)


def get_products():
    """Fetch SKU-to-product-line mapping from dim_products.

    Columns returned: sku, product_name, product_line, wholesale_price.
    """

    def _load():
        sql = (
            "SELECT sku, product_name, product_line, wholesale_price "
            "FROM dim_products "
            "ORDER BY sku"
        )
        return _execute_query(sql)

    return _cached("products", {}, _load)


def get_category_median_sppd():
    """Category median SPPD per product line, from the full unfiltered dataset.

    Fixed benchmark for Indexed SPPD -- deliberately ignores any active
    UI filter (retailer/region/date range) so the benchmark doesn't shift
    with the current selection. Cached like other query functions.

    Columns returned: product_line, category_median_sppd.
    """

    def _load():
        scan_agg = get_scan_data_agg({})
        products_df = get_products()
        if scan_agg.empty or products_df.empty:
            return pd.DataFrame(columns=["product_line", "category_median_sppd"])

        days = days_in_quarter_range(DEFAULT_START_QUARTER, DEFAULT_END_QUARTER)
        full_sppd_df = calculate_sppd_from_agg(scan_agg, days)
        return calculate_category_median_sppd(full_sppd_df, products_df)

    return _cached("category_median_sppd", {}, _load)


def get_global_medians():
    """Fixed SPPD/ACV% medians for the quadrant dividing lines.

    Computed from the full unfiltered dataset -- deliberately ignores any
    active UI filter (retailer/region/date range) so the star/gem/dead/
    question quadrant splits don't reshuffle with the current selection.
    Cached like other query functions.

    Returns a one-row DataFrame with columns: median_sppd, median_acv.
    """

    def _load():
        scan_agg = get_scan_data_agg({})
        dist_df = get_distribution({})
        stores_df = get_stores()
        if scan_agg.empty or dist_df.empty or stores_df.empty:
            return pd.DataFrame(columns=["median_sppd", "median_acv"])

        days = days_in_quarter_range(DEFAULT_START_QUARTER, DEFAULT_END_QUARTER)
        full_sppd_df = calculate_sppd_from_agg(scan_agg, days)
        full_acv_df = calculate_acv_pct(dist_df, stores_df)
        return calculate_global_medians(full_sppd_df, full_acv_df)

    return _cached("global_medians", {}, _load)


def _quarterly_sppd_from_scan(clauses, params):
    """Aggregate quarterly SPPD from fct_scan_data via GROUP BY."""
    base = (
        "SELECT sd.sku, "
        "EXTRACT(YEAR FROM sd.week_ending)::int AS yr, "
        "EXTRACT(QUARTER FROM sd.week_ending)::int AS qtr, "
        "SUM(sd.units_sold)::float AS total_units, "
        "COUNT(DISTINCT sd.store_id)::float AS door_count "
        "FROM fct_scan_data sd"
    )
    if clauses:
        base += " INNER JOIN dim_stores ds ON sd.store_id = ds.store_id"
        base += " WHERE " + " AND ".join(clauses)
    base += " GROUP BY sd.sku, yr, qtr ORDER BY sd.sku, yr, qtr"
    df = _execute_query(base, params)
    if not df.empty:
        df["sppd"] = df["total_units"] / df["door_count"] / 91.0
    return df


def get_quarterly_sppd(filters=None):
    """Quarterly SPPD per SKU from the pre-aggregated mart.

    Unfiltered path reads mart_quarterly_sppd directly (~600 rows, no
    GROUP BY). Filtered path (retailer/region) falls back to a GROUP BY
    over fct_scan_data since the mart has no retailer dimension.

    SPPD source of truth is mart_quarterly_sppd in dbt:
      Total Units / Carrying Stores / Days in Period.

    Columns returned: sku, quarter, total_units, door_count, sppd.
    Quarter format: '2025Q3' (pandas period string).
    """
    filters = filters or {}

    def _load():
        retailers = filters.get("retailers")
        region = filters.get("region")
        needs_store_filter = bool(retailers) or bool(region)

        if not needs_store_filter:
            sql = (
                "SELECT sku, year AS yr, quarter AS qtr, "
                "total_units::float AS total_units, "
                "carrying_stores::float AS door_count, "
                "sppd::float AS sppd "
                "FROM mart_quarterly_sppd "
                "ORDER BY sku, yr, qtr"
            )
            df = _execute_query(sql)
            if df.empty:
                # Mart not yet deployed — fall back to fct_scan_data GROUP BY.
                df = _quarterly_sppd_from_scan([], [])

        else:
            clauses = []
            params = []
            if retailers:
                placeholders = ", ".join(["%s"] * len(retailers))
                clauses.append(f"ds.retailer IN ({placeholders})")
                params.extend(retailers)
            if region:
                clauses.append("ds.region = %s")
                params.append(region)
            df = _quarterly_sppd_from_scan(clauses, params)

        if df.empty:
            return pd.DataFrame(columns=["sku", "quarter", "total_units", "door_count", "sppd"])

        df["quarter"] = df["yr"].astype(int).astype(str) + "Q" + df["qtr"].astype(int).astype(str)
        return df[["sku", "quarter", "total_units", "door_count", "sppd"]]

    return _cached("quarterly_sppd", filters, _load)


# ── Quarter helpers ─────────────────────────────────────────────────

def _quarter_start_date(quarter_str):
    """Convert 'Q1 2025' to the first day of that quarter as a date string.

    Quarter boundaries:
        Q1 = Jan 1, Q2 = Apr 1, Q3 = Jul 1, Q4 = Oct 1.
    """
    q, year = quarter_str.split()
    