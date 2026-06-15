"""Tests for app.calculations — SPPD, ACV%, indexed SPPD, trend, at-risk, expansion."""

import numpy as np
import pandas as pd
import pytest

from app.calculations import (
    calculate_acv_pct,
    calculate_at_risk_score,
    calculate_expansion_upside,
    calculate_indexed_sppd,
    calculate_sppd,
    calculate_velocity_trend,
    days_in_quarter_range,
)


# ── SPPD ────────────────────────────────────────────────────────────


class TestCalculateSppd:
    """SPPD = Total Units / Carrying Stores / Days in Period."""

    def test_basic_sppd(self, sample_scan_df):
        """100 units / 10 doors / 91 days ~ 0.1099."""
        result = calculate_sppd(sample_scan_df, days_in_period=91)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]
        assert row["total_units"] == 100
        assert row["door_count"] == 10
        assert pytest.approx(row["sppd"], abs=0.01) == 100 / 10 / 91

    def test_higher_velocity_sku(self, sample_scan_df):
        """CHP-AS-002: 500 units / 5 doors / 91 days ~ 1.099."""
        result = calculate_sppd(sample_scan_df, days_in_period=91)
        row = result[result["sku"] == "CHP-AS-002"].iloc[0]
        assert row["total_units"] == 500
        assert row["door_count"] == 5
        assert pytest.approx(row["sppd"], abs=0.01) == 500 / 5 / 91

    def test_empty_scan_data(self):
        """Empty input returns empty DataFrame with expected columns."""
        result = calculate_sppd(pd.DataFrame(columns=["sku", "store_id", "units_sold"]), 91)
        assert result.empty
        assert list(result.columns) == ["sku", "total_units", "door_count", "sppd"]

    def test_zero_days_returns_empty(self, sample_scan_df):
        """Zero days in period should return empty (division guard)."""
        result = calculate_sppd(sample_scan_df, days_in_period=0)
        assert result.empty


# ── ACV% ────────────────────────────────────────────────────────────


class TestCalculateAcvPct:
    """ACV% = sum(carrying weights) / sum(all store weights)."""

    def test_all_a_tier_stores(self, sample_dist_df, sample_stores_df):
        """CHP-AS-001 in all 5 A-tier stores.

        Carrying weight = 5 * 3 = 15.
        Total weight = 5*3 + 10*2 + 5*1 = 40.
        ACV% = 15/40 = 0.375.
        """
        result = calculate_acv_pct(sample_dist_df, sample_stores_df)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]
        assert pytest.approx(row["acv_pct"], abs=0.001) == 15 / 40

    def test_mixed_tier_stores(self, sample_dist_df, sample_stores_df):
        """CHP-AS-002 in 5 A-tier + 5 B-tier stores.

        Carrying weight = 5*3 + 5*2 = 25.
        Total weight = 40.
        ACV% = 25/40 = 0.625.
        """
        result = calculate_acv_pct(sample_dist_df, sample_stores_df)
        row = result[result["sku"] == "CHP-AS-002"].iloc[0]
        assert pytest.approx(row["acv_pct"], abs=0.001) == 25 / 40

    def test_full_distribution(self, sample_dist_df, sample_stores_df):
        """CHP-PS-001 in all 20 stores -> ACV% = 1.0."""
        result = calculate_acv_pct(sample_dist_df, sample_stores_df)
        row = result[result["sku"] == "CHP-PS-001"].iloc[0]
        assert pytest.approx(row["acv_pct"], abs=0.001) == 1.0

    def test_zero_stores(self, sample_stores_df):
        """SKU authorized in 0 stores -> ACV% = 0 (empty dist_df)."""
        empty_dist = pd.DataFrame(columns=["sku", "store_id"])
        result = calculate_acv_pct(empty_dist, sample_stores_df)
        assert result.empty

    def test_empty_stores_df(self, sample_dist_df):
        """Empty store dimension -> empty result."""
        empty_stores = pd.DataFrame(columns=["store_id", "volume_tier"])
        result = calculate_acv_pct(sample_dist_df, empty_stores)
        assert result.empty


# ── Indexed SPPD ────────────────────────────────────────────────────


class TestCalculateIndexedSppd:
    """Indexed SPPD = item SPPD / category median SPPD."""

    def test_double_median(self, sample_scan_df, sample_benchmarks_df, sample_products_df):
        """If one SKU has 2x the category median SPPD, index = 2.0."""
        sppd_df = calculate_sppd(sample_scan_df, 91)

        # Manually check: CHP-AS-001 sppd ~ 0.11, CHP-AS-002 sppd ~ 1.10.
        # Category median for Artisan Sauces = median(0.11, 1.10) = 0.605.
        # CHP-AS-002 indexed = 1.10 / 0.605 ~ 1.82.

        result = calculate_indexed_sppd(sppd_df, sample_benchmarks_df, sample_products_df)
        assert not result.empty
        assert "indexed_sppd" in result.columns

        # Both Artisan Sauces SKUs should have the same median.
        as_rows = result[result["product_line"] == "Artisan Sauces"]
        assert len(as_rows) == 2
        # Median is computed from actual data, so both share it.
        assert as_rows["category_median_sppd"].nunique() == 1

    def test_single_sku_in_category(self, sample_benchmarks_df, sample_products_df):
        """Single SKU in a category: indexed SPPD = 1.0 (it IS the median)."""
        single_sppd = pd.DataFrame([{"sku": "CHP-PS-001", "sppd": 0.5}])
        result = calculate_indexed_sppd(single_sppd, sample_benchmarks_df, sample_products_df)
        row = result[result["sku"] == "CHP-PS-001"].iloc[0]
        assert pytest.approx(row["indexed_sppd"], abs=0.001) == 1.0

    def test_empty_input(self, sample_benchmarks_df, sample_products_df):
        """Empty SPPD DataFrame returns empty result."""
        empty = pd.DataFrame(columns=["sku", "sppd"])
        result = calculate_indexed_sppd(empty, sample_benchmarks_df, sample_products_df)
        assert result.empty

    def test_no_benchmarks_for_category(self, sample_products_df):
        """Category with no benchmarks: indexed SPPD is still computed from peers."""
        sppd_df = pd.DataFrame([
            {"sku": "CHP-AS-001", "sppd": 0.5},
            {"sku": "CHP-AS-002", "sppd": 1.0},
        ])
        # Empty benchmarks -- but indexed SPPD uses peer medians, not benchmarks.
        empty_benchmarks = pd.DataFrame(columns=[
            "product_line", "avg_weekly_units_per_store",
        ])
        result = calculate_indexed_sppd(sppd_df, empty_benchmarks, sample_products_df)
        # Should still work because medians are computed from sppd_df itself.
        assert len(result) == 2
        assert result["indexed_sppd"].notna().all()


# ── Velocity trend ──────────────────────────────────────────────────


class TestCalculateVelocityTrend:
    """Velocity trend: rising / flat / declining over trailing quarters."""

    def test_rising_trend(self, sample_scan_quarterly_df, sample_products_df):
        """CHP-AS-001 has increasing units each quarter -> rising."""
        result = calculate_velocity_trend(sample_scan_quarterly_df, sample_products_df)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]
        assert row["trend"] == "rising"
        assert row["slope"] > 0

    def test_declining_trend(self, sample_scan_quarterly_df, sample_products_df):
        """CHP-AS-002 has decreasing units each quarter -> declining."""
        result = calculate_velocity_trend(sample_scan_quarterly_df, sample_products_df)
        row = result[result["sku"] == "CHP-AS-002"].iloc[0]
        assert row["trend"] == "declining"
        assert row["slope"] < 0

    def test_flat_trend(self, sample_scan_quarterly_df, sample_products_df):
        """CHP-PS-001 has constant units -> flat."""
        result = calculate_velocity_trend(sample_scan_quarterly_df, sample_products_df)
        row = result[result["sku"] == "CHP-PS-001"].iloc[0]
        assert row["trend"] == "flat"

    def test_single_quarter(self, sample_products_df):
        """Only 1 quarter of data -> flat (not enough data for slope)."""
        single = pd.DataFrame([
            {"sku": "CHP-AS-001", "store_id": "STR-0001", "week_ending": "2025-01-15", "units_sold": 10},
        ])
        result = calculate_velocity_trend(single, sample_products_df, n_quarters=4)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]
        assert row["trend"] == "flat"
        assert row["quarters_with_data"] == 1

    def test_empty_scan_data(self, sample_products_df):
        """Empty scan data returns empty result."""
        empty = pd.DataFrame(columns=["sku", "store_id", "week_ending", "units_sold"])
        result = calculate_velocity_trend(empty, sample_products_df)
        assert result.empty


# ── At-risk scoring ─────────────────────────────────────────────────


class TestCalculateAtRiskScore:
    """At-risk tiers: act_now, fix_or_rationalize, watchlist."""

    def test_below_median_declining_is_act_now(self):
        """Indexed SPPD < 1.0 + declining -> act_now."""
        indexed = pd.DataFrame([{"sku": "CHP-AS-001", "indexed_sppd": 0.6}])
        trend = pd.DataFrame([{"sku": "CHP-AS-001", "trend": "declining"}])
        result = calculate_at_risk_score(indexed, trend)
        assert result.iloc[0]["at_risk_tier"] == "act_now"

    def test_below_median_flat_is_fix_or_rationalize(self):
        """Indexed SPPD < 1.0 + flat -> fix_or_rationalize."""
        indexed = pd.DataFrame([{"sku": "CHP-AS-001", "indexed_sppd": 0.8}])
        trend = pd.DataFrame([{"sku": "CHP-AS-001", "trend": "flat"}])
        result = calculate_at_risk_score(indexed, trend)
        assert result.iloc[0]["at_risk_tier"] == "fix_or_rationalize"

    def test_above_median_declining_is_watchlist(self):
        """Indexed SPPD >= 1.0 + declining -> watchlist."""
        indexed = pd.DataFrame([{"sku": "CHP-AS-002", "indexed_sppd": 1.5}])
        trend = pd.DataFrame([{"sku": "CHP-AS-002", "trend": "declining"}])
        result = calculate_at_risk_score(indexed, trend)
        assert result.iloc[0]["at_risk_tier"] == "watchlist"

    def test_above_median_rising_excluded(self):
        """Indexed SPPD >= 1.0 + rising -> no tier (healthy)."""
        indexed = pd.DataFrame([{"sku": "CHP-AS-001", "indexed_sppd": 1.5}])
        trend = pd.DataFrame([{"sku": "CHP-AS-001", "trend": "rising"}])
        result = calculate_at_risk_score(indexed, trend)
        assert result.empty

    def test_empty_inputs(self):
        """Empty DataFrames return empty result."""
        empty_idx = pd.DataFrame(columns=["sku", "indexed_sppd"])
        empty_trend = pd.DataFrame(columns=["sku", "trend"])
        result = calculate_at_risk_score(empty_idx, empty_trend)
        assert result.empty


# ── Expansion upside ────────────────────────────────────────────────


class TestCalculateExpansionUpside:
    """Expansion projections at median, 75th percentile, and leader."""

    def test_projections_monotonically_increasing(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """Median <= P75 <= Leader for dollar projections."""
        sppd_df = calculate_sppd(sample_scan_df, 91)
        result = calculate_expansion_upside(
            sppd_df, sample_dist_df, sample_stores_df,
            sample_products_df, sample_benchmarks_df,
        )
        assert not result.empty

        for _, row in result.iterrows():
            assert row["upside_median_dollars"] <= row["upside_p75_dollars"]
            assert row["upside_p75_dollars"] <= row["upside_leader_dollars"]

    def test_full_distribution_zero_upside(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """SKU already at leader doors should have near-zero leader upside.

        CHP-PS-001 is in all 20 stores (the most doors of any SKU in its
        product line), so leader_doors = current_doors -> upside = 0.
        """
        sppd_df = calculate_sppd(sample_scan_df, 91)
        result = calculate_expansion_upside(
            sppd_df, sample_dist_df, sample_stores_df,
            sample_products_df, sample_benchmarks_df,
        )
        row = result[result["sku"] == "CHP-PS-001"].iloc[0]
        # Since it's the only SKU in Pantry Staples, it IS the leader.
        assert pytest.approx(row["upside_leader_dollars"], abs=0.01) == 0.0

    def test_empty_dist_returns_empty(
        self, sample_scan_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """Empty distribution returns empty result."""
        sppd_df = calculate_sppd(sample_scan_df, 91)
        empty_dist = pd.DataFrame(columns=["sku", "store_id"])
        result = calculate_expansion_upside(
            sppd_df, empty_dist, sample_stores_df,
            sample_products_df, sample_benchmarks_df,
        )
        assert result.empty


# ── days_in_quarter_range utility ───────────────────────────────────


class TestDaysInQuarterRange:
    """Quarter-range to day-count conversion."""

    def test_single_quarter(self):
        assert days_in_quarter_range("Q1 2025", "Q1 2025") == 91

    def test_full_year(self):
        assert days_in_quarter_range("Q1 2025", "Q4 2025") == 364

    def test_cross_year(self):
        assert days_in_quarter_range("Q3 2024", "Q2 2025") == 364

    def test_invalid_quarter_fallback(self):
        """Invalid quarter string falls back to 91."""
        assert days_in_quarter_range("Q5 2025", "Q1 2025") == 91
