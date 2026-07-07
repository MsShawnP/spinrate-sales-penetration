"""Tests for app.db query routing — get_scan_data_agg date handling.

Regression tests for the bug where the default (no retailer/region) path
read the full-range mart_sku_scan_totals and silently dropped the
start_quarter/end_quarter filters, while views divided the totals by
days_in_quarter_range() of the narrower selection — producing wrong SPPD
for any date range other than the full default range.

These tests patch app.db._execute_query to inspect the SQL and params
actually issued, so they run without a live Postgres connection.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from app import db
from app.filters import DEFAULT_END_QUARTER, DEFAULT_START_QUARTER


def _fake_agg_df():
    """Minimal frame matching get_scan_data_agg() output columns."""
    return pd.DataFrame([
        {"sku": "CHP-AS-001", "total_units": 100.0, "total_dollars": 500.0, "door_count": 10},
    ])


@pytest.fixture(autouse=True)
def _clear_db_cache():
    """Isolate each test from the module-level query cache."""
    db.clear_cache()
    yield
    db.clear_cache()


class TestGetScanDataAggDateRouting:
    """get_scan_data_agg must respect start/end quarter without a store filter."""

    def test_narrow_range_applies_date_filter_in_default_state(self):
        """No retailer/region + narrowed quarters must query fct_scan_data with WHERE."""
        with patch("app.db._execute_query", return_value=_fake_agg_df()) as mock_q:
            db.get_scan_data_agg({
                "retailers": [],
                "region": None,
                "start_quarter": "Q2 2025",
                "end_quarter": "Q3 2025",
            })

        sql, params = mock_q.call_args[0]
        assert "fct_scan_data" in sql
        assert "mart_sku_scan_totals" not in sql
        assert "sd.week_ending >= %s" in sql
        assert "sd.week_ending <= %s" in sql
        assert params == ["2025-04-01", "2025-09-30"]
        # No retailer/region filter -> no dim_stores join needed.
        assert "dim_stores" not in sql

    def test_full_default_range_uses_mart_fast_path(self):
        """The full default quarter range carries no restriction -> mart path."""
        with patch("app.db._execute_query", return_value=_fake_agg_df()) as mock_q:
            db.get_scan_data_agg({
                "retailers": [],
                "region": None,
                "start_quarter": DEFAULT_START_QUARTER,
                "end_quarter": DEFAULT_END_QUARTER,
            })

        sql = mock_q.call_args[0][0]
        assert "mart_sku_scan_totals" in sql

    def test_no_filters_uses_mart_fast_path(self):
        """Empty filters (fixed-benchmark callers) keep the mart fast path."""
        with patch("app.db._execute_query", return_value=_fake_agg_df()) as mock_q:
            db.get_scan_data_agg({})

        sql = mock_q.call_args[0][0]
        assert "mart_sku_scan_totals" in sql

    def test_single_quarter_periods_differ(self):
        """Migration-style per-quarter filters must issue distinct date-bounded queries.

        Before the fix, both periods fell through to the same full-range
        mart query in the default state, so the two periods never differed.
        """
        with patch("app.db._execute_query", return_value=_fake_agg_df()) as mock_q:
            db.get_scan_data_agg({
                "retailers": [],
                "region": None,
                "start_quarter": "Q3 2025",
                "end_quarter": "Q3 2025",
            })
            db.get_scan_data_agg({
                "retailers": [],
                "region": None,
                "start_quarter": "Q4 2025",
                "end_quarter": "Q4 2025",
            })

        assert mock_q.call_count == 2
        (sql1, params1), (sql2, params2) = (c[0] for c in mock_q.call_args_list)
        assert "fct_scan_data" in sql1 and "fct_scan_data" in sql2
        assert params1 == ["2025-07-01", "2025-09-30"]
        assert params2 == ["2025-10-01", "2025-12-31"]
        assert params1 != params2

    def test_retailer_filter_with_dates_applies_both(self):
        """Store-filtered path keeps applying date clauses alongside the join."""
        with patch("app.db._execute_query", return_value=_fake_agg_df()) as mock_q:
            db.get_scan_data_agg({
                "retailers": ["Walmart"],
                "region": None,
                "start_quarter": "Q2 2025",
                "end_quarter": "Q2 2025",
            })

        sql, params = mock_q.call_args[0]
        assert "fct_scan_data" in sql
        assert "dim_stores" in sql
        assert "sd.week_ending >= %s" in sql
        assert "sd.week_ending <= %s" in sql
        assert params == ["2025-04-01", "2025-06-30", "Walmart"]
