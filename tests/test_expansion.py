"""Tests for expansion case list view (U5)."""

from unittest.mock import patch

import pandas as pd
import pytest

from app.views.expansion import (
    MIN_DOOR_THRESHOLD,
    _generate_guidance,
    build_expansion_data,
    layout,
)


def _agg_scan(scan_df):
    """Aggregate raw scan fixture to match get_scan_data_agg() output."""
    if scan_df.empty:
        return pd.DataFrame(columns=["sku", "total_units", "total_dollars", "door_count"])
    return scan_df.groupby("sku").agg(
        total_units=("units_sold", "sum"),
        total_dollars=("dollars_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()


# ── Fixtures specific to expansion tests ─────────────────────────────


@pytest.fixture
def mock_db_returns(
    sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df, sample_benchmarks_df
):
    """Patch db module to return conftest sample DataFrames."""
    with patch("app.db", create=True) as mock_db:
        mock_db.get_scan_data_agg.return_value = _agg_scan(sample_scan_df)
        mock_db.get_distribution.return_value = sample_dist_df.copy()
        mock_db.get_stores.return_value = sample_stores_df.copy()
        mock_db.get_benchmarks.return_value = sample_benchmarks_df.copy()
        mock_db.get_products.return_value = sample_products_df.copy()
        yield mock_db


@pytest.fixture
def default_filters():
    return {"start_quarter": "Q1 2025", "end_quarter": "Q1 2025"}


# ── build_expansion_data ─────────────────────────────────────────────


class TestBuildExpansionData:
    def test_returns_hidden_gems_only(self, mock_db_returns, default_filters):
        rows_df, summary = build_expansion_data(default_filters)
        if not rows_df.empty:
            for _, row in rows_df.iterrows():
                assert row["sku"] != "CHP-PS-001", "Full-distribution SKU should not appear"

    def test_excludes_below_threshold(self, default_filters, sample_stores_df, sample_benchmarks_df, sample_products_df):
        """SKU with fewer than MIN_DOOR_THRESHOLD stores is excluded."""
        scan_df = pd.DataFrame([
            {"sku": "LOW-001", "store_id": f"STR-{i:04d}", "week_ending": "2025-01-07",
             "units_sold": 50, "dollars_sold": 250.0}
            for i in range(1, 4)  # Only 3 stores
        ])
        dist_df = pd.DataFrame([
            {"sku": "LOW-001", "store_id": f"STR-{i:04d}", "retailer_id": "RET-WALMART",
             "chain_name": "Walmart", "region": "Northeast", "state": "NY",
             "volume_tier": "A", "authorized_date": "2024-01-01",
             "deauthorized_date": None, "is_active": True, "weeks_with_sales": 10,
             "total_units": 150, "total_dollars": 750.0, "avg_weekly_units": 15.0,
             "first_scan_week": "2024-01-07", "last_scan_week": "2025-01-07"}
            for i in range(1, 4)
        ])
        products_df = pd.DataFrame([
            {"sku": "LOW-001", "product_name": "Low Door Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0}
        ])

        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(scan_df)
            mock_db.get_distribution.return_value = dist_df
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_benchmarks.return_value = sample_benchmarks_df
            mock_db.get_products.return_value = products_df

            rows_df, summary = build_expansion_data(default_filters)
            if not rows_df.empty:
                assert "LOW-001" not in rows_df["sku"].values

    def test_empty_scan_data(self, default_filters):
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = pd.DataFrame()
            mock_db.get_distribution.return_value = pd.DataFrame()
            mock_db.get_stores.return_value = pd.DataFrame()
            mock_db.get_benchmarks.return_value = pd.DataFrame()
            mock_db.get_products.return_value = pd.DataFrame()
            rows_df, summary = build_expansion_data(default_filters)
            assert rows_df.empty
            assert summary == {}

    def test_projections_monotonically_increasing(self, mock_db_returns, default_filters):
        rows_df, _ = build_expansion_data(default_filters)
        if not rows_df.empty:
            for _, row in rows_df.iterrows():
                assert row["upside_median_dollars"] <= row["upside_p75_dollars"]
                assert row["upside_p75_dollars"] <= row["upside_leader_dollars"]

    def test_sorted_by_median_upside_descending(self, mock_db_returns, default_filters):
        rows_df, _ = build_expansion_data(default_filters)
        if len(rows_df) > 1:
            values = rows_df["upside_median_dollars"].tolist()
            assert values == sorted(values, reverse=True)

    def test_summary_has_expected_keys(self, mock_db_returns, default_filters):
        rows_df, summary = build_expansion_data(default_filters)
        if summary:
            assert "count" in summary
            assert "total_median_upside" in summary
            assert "total_p75_upside" in summary
            assert "total_leader_upside" in summary


# ── _generate_guidance ───────────────────────────────────────────────


class TestGenerateGuidance:
    def test_already_at_leader(self):
        row = {"acv_pct": 0.95, "current_doors": 100, "leader_doors": 90}
        assert "Already at category-leading" in _generate_guidance(row)

    def test_strong_base(self):
        row = {"acv_pct": 0.50, "current_doors": 50, "leader_doors": 200}
        assert "75th percentile" in _generate_guidance(row)

    def test_solid_base(self):
        row = {"acv_pct": 0.25, "current_doors": 30, "leader_doors": 200}
        assert "Median" in _generate_guidance(row)

    def test_narrow_distribution(self):
        row = {"acv_pct": 0.12, "current_doors": 15, "leader_doors": 200}
        assert "Narrow" in _generate_guidance(row)

    def test_very_limited(self):
        row = {"acv_pct": 0.05, "current_doors": 5, "leader_doors": 200}
        assert "Very limited" in _generate_guidance(row)


# ── Layout structure ─────────────────────────────────────────────────


class TestExpansionLayout:
    def test_layout_returns_div(self):
        result = layout()
        assert result is not None

    def test_layout_has_grid(self):
        result = layout()
        ids = _collect_ids(result)
        assert "expansion-grid" in ids

    def test_layout_has_detail_card_area(self):
        result = layout()
        ids = _collect_ids(result)
        assert "expansion-detail-card" in ids

    def test_layout_has_summary_area(self):
        result = layout()
        ids = _collect_ids(result)
        assert "expansion-summary" in ids

    def test_min_door_threshold_is_ten(self):
        assert MIN_DOOR_THRESHOLD == 10


# ── Helpers ──────────────────────────────────────────────────────────


def _collect_ids(component):
    """Recursively collect all component IDs from a Dash layout tree."""
    ids = set()
    if hasattr(component, "id") and component.id:
        ids.add(component.id)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            ids.update(_collect_ids(child))
    elif children is not None and hasattr(children, "id"):
        ids.update(_collect_ids(children))
    return ids
