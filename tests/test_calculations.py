"""Tests for app.calculations — SPPD, ACV%, indexed SPPD, trend, at-risk, expansion."""

import numpy as np
import pandas as pd
import pytest

from app.calculations import (
    calculate_acv_pct,
    calculate_at_risk_score,
    calculate_category_median_sppd,
    calculate_expansion_upside,
    calculate_global_medians,
    calculate_indexed_sppd,
    calculate_sppd,
    calculate_velocity_trend,
    calculate_velocity_trend_from_quarterly,
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

    def test_carrying_store_missing_from_dim_stores_is_excluded(self, sample_stores_df):
        """A carrying store absent from dim_stores must not inflate ACV%
        past 1.0 -- it isn't part of the addressable universe (the
        denominator), so it can't count toward the numerator either.

        Regression test: previously an unmatched store defaulted to
        weight=1 via fillna(1), letting the numerator exceed the
        denominator (ACV% > 100%).
        """
        # CHP-AS-001 authorized in all 5 A-tier stores (weight 15) plus one
        # "ghost" store that doesn't exist in dim_stores.
        dist_with_ghost = pd.DataFrame([
            {"sku": "CHP-AS-001", "store_id": "STR-0001"},
            {"sku": "CHP-AS-001", "store_id": "STR-0002"},
            {"sku": "CHP-AS-001", "store_id": "STR-0003"},
            {"sku": "CHP-AS-001", "store_id": "STR-0004"},
            {"sku": "CHP-AS-001", "store_id": "STR-0005"},
            {"sku": "CHP-AS-001", "store_id": "STR-GHOST"},
        ])
        result = calculate_acv_pct(dist_with_ghost, sample_stores_df)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]

        # Ghost store contributes nothing -- same as the 5-A-tier-only case.
        assert pytest.approx(row["carrying_weight"], abs=0.001) == 15
        assert pytest.approx(row["acv_pct"], abs=0.001) == 15 / 40
        assert row["acv_pct"] <= 1.0

    def test_acv_pct_never_exceeds_one(self, sample_stores_df):
        """Defense-in-depth: acv_pct is clipped to 1.0 even if every
        carrying store happened to be a ghost relative to a hypothetical
        smaller total_weight (belt-and-suspenders on top of the inner join)."""
        dist_all_known = pd.DataFrame([
            {"sku": "CHP-PS-001", "store_id": f"STR-{i:04d}"} for i in range(1, 21)
        ])
        result = calculate_acv_pct(dist_all_known, sample_stores_df)
        assert (result["acv_pct"] <= 1.0).all()


# ── Category median SPPD (full-dataset benchmark) ───────────────────


class TestCalculateCategoryMedianSppd:
    """Category median SPPD, computed from the full unfiltered dataset."""

    def test_median_per_product_line(self, sample_products_df):
        """Median is computed independently per product line."""
        full_sppd_df = pd.DataFrame([
            {"sku": "CHP-AS-001", "sppd": 0.5},
            {"sku": "CHP-AS-002", "sppd": 1.0},
            {"sku": "CHP-PS-001", "sppd": 0.3},
        ])
        result = calculate_category_median_sppd(full_sppd_df, sample_products_df)
        as_row = result[result["product_line"] == "Artisan Sauces"].iloc[0]
        ps_row = result[result["product_line"] == "Pantry Staples"].iloc[0]
        assert pytest.approx(as_row["category_median_sppd"], abs=0.001) == 0.75
        assert pytest.approx(ps_row["category_median_sppd"], abs=0.001) == 0.3

    def test_empty_input(self, sample_products_df):
        """Empty SPPD DataFrame returns empty result with correct columns."""
        empty = pd.DataFrame(columns=["sku", "sppd"])
        result = calculate_category_median_sppd(empty, sample_products_df)
        assert result.empty
        assert list(result.columns) == ["product_line", "category_median_sppd"]


# ── Indexed SPPD ────────────────────────────────────────────────────


class TestCalculateIndexedSppd:
    """Indexed SPPD = item SPPD / category median SPPD (full-dataset benchmark)."""

    def test_double_median(self, sample_products_df):
        """If a SKU has 2x the category median SPPD, index = 2.0."""
        category_median_df = pd.DataFrame([
            {"product_line": "Artisan Sauces", "category_median_sppd": 0.5},
        ])
        sppd_df = pd.DataFrame([{"sku": "CHP-AS-002", "sppd": 1.0}])

        result = calculate_indexed_sppd(sppd_df, category_median_df, sample_products_df)
        row = result[result["sku"] == "CHP-AS-002"].iloc[0]
        assert pytest.approx(row["indexed_sppd"], abs=0.001) == 2.0

    def test_lone_sku_not_forced_to_one(self, sample_products_df):
        """A lone SKU in a filtered selection must NOT trivially index to 1.0.

        Regression test for the bug where the benchmark was derived from
        the filtered sppd_df itself -- a lone SKU was always its own
        median. The benchmark here comes from the full dataset (0.5),
        independent of what's in the filtered sppd_df (only one SKU).
        """
        category_median_df = pd.DataFrame([
            {"product_line": "Artisan Sauces", "category_median_sppd": 0.5},
        ])
        filtered_sppd_df = pd.DataFrame([{"sku": "CHP-AS-001", "sppd": 0.1}])

        result = calculate_indexed_sppd(filtered_sppd_df, category_median_df, sample_products_df)
        row = result[result["sku"] == "CHP-AS-001"].iloc[0]
        assert pytest.approx(row["indexed_sppd"], abs=0.001) == 0.2
        assert row["indexed_sppd"] != 1.0

    def test_filter_independent(self, sample_products_df):
        """Same SKU indexes to the same value regardless of what else is
        in the filtered selection, as long as the (full-dataset) benchmark
        is unchanged."""
        category_median_df = pd.DataFrame([
            {"product_line": "Artisan Sauces", "category_median_sppd": 0.5},
        ])

        # "Filtered to one retailer": only CHP-AS-001 present.
        narrow_selection = pd.DataFrame([{"sku": "CHP-AS-001", "sppd": 0.25}])
        # "Filtered to all retailers": both Artisan Sauces SKUs present.
        wide_selection = pd.DataFrame([
            {"sku": "CHP-AS-001", "sppd": 0.25},
            {"sku": "CHP-AS-002", "sppd": 5.0},
        ])

        narrow_result = calculate_indexed_sppd(narrow_selection, category_median_df, sample_products_df)
        wide_result = calculate_indexed_sppd(wide_selection, category_median_df, sample_products_df)

        narrow_val = narrow_result[narrow_result["sku"] == "CHP-AS-001"].iloc[0]["indexed_sppd"]
        wide_val = wide_result[wide_result["sku"] == "CHP-AS-001"].iloc[0]["indexed_sppd"]
        assert pytest.approx(narrow_val, abs=0.001) == pytest.approx(wide_val, abs=0.001)

    def test_no_benchmark_for_category_is_nan(self, sample_products_df):
        """SKU whose product line has no benchmark: indexed SPPD is NaN,
        not silently defaulted or computed from peers."""
        sppd_df = pd.DataFrame([
            {"sku": "CHP-AS-001", "sppd": 0.5},
            {"sku": "CHP-AS-002", "sppd": 1.0},
        ])
        empty_benchmark = pd.DataFrame(columns=["product_line", "category_median_sppd"])
        result = calculate_indexed_sppd(sppd_df, empty_benchmark, sample_products_df)
        assert len(result) == 2
        assert result["indexed_sppd"].isna().all()

    def test_empty_input(self, sample_products_df):
        """Empty SPPD DataFrame returns empty result."""
        empty = pd.DataFrame(columns=["sku", "sppd"])
        category_median_df = pd.DataFrame([
            {"product_line": "Artisan Sauces", "category_median_sppd": 0.5},
        ])
        result = calculate_indexed_sppd(empty, category_median_df, sample_products_df)
        assert result.empty


# ── Global medians (fixed quadrant benchmark) ────────────────────────


class TestCalculateGlobalMedians:
    """Fixed SPPD/ACV% medians for the quadrant dividing lines, computed
    from the full unfiltered dataset."""

    def test_medians_of_full_dataset(self):
        """Median is computed across all SKUs, independent of product line."""
        full_sppd_df = pd.DataFrame([
            {"sku": "CHP-AS-001", "sppd": 0.2},
            {"sku": "CHP-AS-002", "sppd": 0.6},
            {"sku": "CHP-PS-001", "sppd": 1.0},
        ])
        full_acv_df = pd.DataFrame([
            {"sku": "CHP-AS-001", "acv_pct": 0.1},
            {"sku": "CHP-AS-002", "acv_pct": 0.5},
            {"sku": "CHP-PS-001", "acv_pct": 0.9},
        ])
        result = calculate_global_medians(full_sppd_df, full_acv_df)
        assert len(result) == 1
        assert pytest.approx(result["median_sppd"].iloc[0], abs=0.001) == 0.6
        assert pytest.approx(result["median_acv"].iloc[0], abs=0.001) == 0.5

    def test_empty_sppd_input(self):
        """Empty SPPD DataFrame returns empty result with correct columns."""
        empty = pd.DataFrame(columns=["sku", "sppd"])
        full_acv_df = pd.DataFrame([{"sku": "CHP-AS-001", "acv_pct": 0.5}])
        result = calculate_global_medians(empty, full_acv_df)
        assert result.empty
        assert list(result.columns) == ["median_sppd", "median_acv"]

    def test_empty_acv_input(self):
        """Empty ACV% DataFrame returns empty result with correct columns."""
        full_sppd_df = pd.DataFrame([{"sku": "CHP-AS-001", "sppd": 0.5}])
        empty = pd.DataFrame(columns=["sku", "acv_pct"])
        result = calculate_global_medians(full_sppd_df, empty)
        assert result.empty
        assert list(result.columns) == ["median_sppd", "median_acv"]


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


# ── Velocity trend (from quarterly) ────────────────────────────────


class TestCalculateVelocityTrendFromQuarterly:
    """Same logic as TestCalculateVelocityTrend but from pre-aggregated data."""

    def test_rising_trend(self):
        df = pd.DataFrame([
            {"sku": "SKU-A", "quarter": "2024Q1", "sppd": 0.5},
            {"sku": "SKU-A", "quarter": "2024Q2", "sppd": 0.7},
            {"sku": "SKU-A", "quarter": "2024Q3", "sppd": 0.9},
            {"sku": "SKU-A", "quarter": "2024Q4", "sppd": 1.1},
        ])
        result = calculate_velocity_trend_from_quarterly(df)
        row = result[result["sku"] == "SKU-A"].iloc[0]
        assert row["trend"] == "rising"
        assert row["slope"] > 0
        assert row["quarters_with_data"] == 4

    def test_declining_trend(self):
        df = pd.DataFrame([
            {"sku": "SKU-A", "quarter": "2024Q1", "sppd": 1.2},
            {"sku": "SKU-A", "quarter": "2024Q2", "sppd": 0.9},
            {"sku": "SKU-A", "quarter": "2024Q3", "sppd": 0.6},
            {"sku": "SKU-A", "quarter": "2024Q4", "sppd": 0.3},
        ])
        result = calculate_velocity_trend_from_quarterly(df)
        row = result[result["sku"] == "SKU-A"].iloc[0]
        assert row["trend"] == "declining"
        assert row["slope"] < 0

    def test_flat_trend(self):
        df = pd.DataFrame([
            {"sku": "SKU-A", "quarter": "2024Q1", "sppd": 1.0},
            {"sku": "SKU-A", "quarter": "2024Q2", "sppd": 1.01},
            {"sku": "SKU-A", "quarter": "2024Q3", "sppd": 0.99},
            {"sku": "SKU-A", "quarter": "2024Q4", "sppd": 1.0},
        ])
        result = calculate_velocity_trend_from_quarterly(df)
        row = result[result["sku"] == "SKU-A"].iloc[0]
        assert row["trend"] == "flat"

    def test_single_quarter_is_flat(self):
        df = pd.DataFrame([{"sku": "SKU-A", "quarter": "2024Q3", "sppd": 0.8}])
        result = calculate_velocity_trend_from_quarterly(df)
        row = result[result["sku"] == "SKU-A"].iloc[0]
        assert row["trend"] == "flat"
        assert row["slope"] == 0.0
        assert row["quarters_with_data"] == 1

    def test_empty_input(self):
        empty = pd.DataFrame(columns=["sku", "quarter", "sppd"])
        result = calculate_velocity_trend_from_quarterly(empty)
        assert result.empty
        assert "trend" in result.columns

    def test_multiple_skus(self):
        df = pd.DataFrame([
            {"sku": "SKU-A", "quarter": "2024Q1", "sppd": 0.5},
            {"sku": "SKU-A", "quarter": "2024Q2", "sppd": 1.0},
            {"sku": "SKU-A", "quarter": "2024Q3", "sppd": 1.5},
            {"sku": "SKU-B", "quarter": "2024Q1", "sppd": 1.5},
            {"sku": "SKU-B", "quarter": "2024Q2", "sppd": 1.0},
            {"sku": "SKU-B", "quarter": "2024Q3", "sppd": 0.5},
        ])
        result = calculate_velocity_trend_from_quarterly(df)
        assert len(result) == 2
        assert result[result["sku"] == "SKU-A"].iloc[0]["trend"] == "rising"
        assert result[result["sku"] == "SKU-B"].iloc[0]["trend"] == "declining"

    def test_n_quarters_limits_window(self):
        df = pd.DataFrame([
            {"sku": "SKU-A", "quarter": "2023Q1", "sppd": 2.0},
            {"sku": "SKU-A", "quarter": "2023Q2", "sppd": 1.8},
            {"sku": "SKU-A", "quarter": "2023Q3", "sppd": 1.6},
            {"sku": "SKU-A", "quarter": "2023Q4", "sppd": 1.4},
            {"sku": "SKU-A", "quarter": "2024Q1", "sppd": 0.5},
            {"sku": "SKU-A", "quarter": "2024Q2", "sppd": 0.7},
            {"sku": "SKU-A", "quarter": "2024Q3", "sppd": 0.9},
            {"sku": "SKU-A", "quarter": "2024Q4", "sppd": 1.1},
        ])
        result = calculate_velocity_trend_from_quarterly(df, n_quarters=4)
        row = result[result["sku"] == "SKU-A"].iloc[0]
        assert row["trend"] == "rising"
        assert row["quarters_with_data"] == 4


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
