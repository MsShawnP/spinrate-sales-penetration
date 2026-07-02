"""Tests for at-risk list view (U6)."""

from unittest.mock import patch

import pandas as pd
import pytest

from app.calculations import calculate_category_median_sppd, calculate_sppd_from_agg
from app.views.at_risk import (
    TIER_CONFIG,
    WINDOW_NOTE,
    _COLUMN_DEFS,
    _build_summary,
    build_at_risk_data,
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


def _category_median(scan_df, products_df, days=91):
    """Build a category-median benchmark from a scan fixture, mirroring
    what db.get_category_median_sppd() computes in production (from the
    full dataset, independent of the UI filter selection)."""
    sppd_df = calculate_sppd_from_agg(_agg_scan(scan_df), days)
    return calculate_category_median_sppd(sppd_df, products_df)


def _scan_to_quarterly_sppd(scan_df):
    """Convert raw scan fixture data to the quarterly SPPD format
    returned by db.get_quarterly_sppd()."""
    df = scan_df.copy()
    df["week_ending"] = pd.to_datetime(df["week_ending"])
    df["quarter"] = (df["week_ending"].dt.year.astype(str) + "Q" +
                     df["week_ending"].dt.quarter.astype(str))
    quarterly = df.groupby(["sku", "quarter"]).agg(
        total_units=("units_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()
    quarterly["sppd"] = quarterly["total_units"] / quarterly["door_count"] / 91.0
    return quarterly[["sku", "quarter", "total_units", "door_count", "sppd"]]


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def mock_db_returns(
    sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df
):
    """Patch db module to return conftest sample DataFrames."""
    with patch("app.db", create=True) as mock_db:
        mock_db.get_scan_data_agg.return_value = _agg_scan(sample_scan_df)
        mock_db.get_stores.return_value = sample_stores_df.copy()
        mock_db.get_category_median_sppd.return_value = _category_median(
            sample_scan_df, sample_products_df
        )
        mock_db.get_products.return_value = sample_products_df.copy()
        yield mock_db


@pytest.fixture
def default_filters():
    return {"start_quarter": "Q1 2025", "end_quarter": "Q1 2025"}


@pytest.fixture
def at_risk_scan_df():
    """Scan data with a clear at-risk SKU (low velocity, declining)."""
    rows = []
    quarters = [
        ("2024-04-07", 40),   # Q2 2024 — starts higher
        ("2024-07-07", 30),   # Q3 2024 — declining
        ("2024-10-07", 20),   # Q4 2024 — declining
        ("2025-01-07", 10),   # Q1 2025 — declining still
    ]
    for week, units in quarters:
        for i in range(1, 6):
            rows.append({
                "sku": "RISK-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": units,
                "dollars_sold": units * 5.0,
            })
    # A healthy SKU for contrast.
    for week, units in quarters:
        for i in range(1, 16):
            rows.append({
                "sku": "SAFE-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": 100,
                "dollars_sold": 500.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def flat_risk_scan_df():
    """Scan data with a below-median but flat SKU (fix_or_rationalize)."""
    rows = []
    quarters = [
        ("2024-04-07", 10),
        ("2024-07-07", 10),
        ("2024-10-07", 10),
        ("2025-01-07", 10),
    ]
    for week, units in quarters:
        for i in range(1, 6):
            rows.append({
                "sku": "FLAT-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": units,
                "dollars_sold": units * 5.0,
            })
    # A healthy high-velocity SKU for contrast.
    for week, _ in quarters:
        for i in range(1, 16):
            rows.append({
                "sku": "FAST-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": 200,
                "dollars_sold": 1000.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def watchlist_scan_df():
    """Scan data with an above-median but declining SKU (watchlist)."""
    rows = []
    quarters = [
        ("2024-04-07", 200),   # Q2 2024 — high
        ("2024-07-07", 150),   # Q3 2024 — declining
        ("2024-10-07", 100),   # Q4 2024 — declining
        ("2025-01-07", 60),    # Q1 2025 — declining
    ]
    for week, units in quarters:
        for i in range(1, 16):
            rows.append({
                "sku": "WATCH-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": units,
                "dollars_sold": units * 5.0,
            })
    # A low-velocity SKU so WATCH-001 is above median.
    for week, _ in quarters:
        for i in range(1, 4):
            rows.append({
                "sku": "LOW-001",
                "store_id": f"STR-{i:04d}",
                "week_ending": week,
                "units_sold": 5,
                "dollars_sold": 25.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def multi_product_df():
    """Products covering test SKUs."""
    return pd.DataFrame([
        {"sku": "RISK-001", "product_name": "Risky Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "SAFE-001", "product_name": "Safe Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "FLAT-001", "product_name": "Flat Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "FAST-001", "product_name": "Fast Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "WATCH-001", "product_name": "Watch Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "LOW-001", "product_name": "Low Item", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
    ])


# ── Tier config ──────────────────────────────────────────────────


class TestTierConfig:
    def test_act_now_has_level_and_trend_signal(self):
        assert TIER_CONFIG["act_now"]["signal"] == "Level + Trend"

    def test_fix_or_rationalize_has_level_signal(self):
        assert TIER_CONFIG["fix_or_rationalize"]["signal"] == "Level"

    def test_watchlist_has_trend_signal(self):
        assert TIER_CONFIG["watchlist"]["signal"] == "Trend"

    def test_three_tiers_defined(self):
        assert set(TIER_CONFIG.keys()) == {"act_now", "fix_or_rationalize", "watchlist"}


# ── Tier summary hero cards ────────────────────────────────────────


class TestBuildSummary:
    """Tier summary now renders Lailara design-system hero_card components
    (shared with Expansion) instead of off-system custom chips."""

    def _hero_cards(self, summary):
        """Pull the three tier hero-card Divs out of _build_summary()'s output."""
        result = _build_summary(summary)
        chip_row = result.children[1]
        return chip_row.children

    def test_renders_three_hero_cards_with_counts_and_labels(self):
        summary = {
            "act_now_count": 3,
            "fix_or_rationalize_count": 5,
            "watchlist_count": 2,
            "total_at_risk_dollars": 1000.0,
        }
        cards = self._hero_cards(summary)
        assert len(cards) == 3

        def _texts(card):
            texts = []
            for child in card.children:
                if isinstance(child.children, str):
                    texts.append(child.children)
            return texts

        assert _texts(cards[0]) == ["3", "Act Now"]
        assert _texts(cards[1]) == ["5", "Fix or Rationalize"]
        assert _texts(cards[2]) == ["2", "Watchlist"]

    def test_hero_cards_use_tier_accent_colors(self):
        """Act Now = red, Fix or Rationalize = amber, Watchlist = teal --
        pulled from TIER_CONFIG's existing accent values."""
        summary = {
            "act_now_count": 1, "fix_or_rationalize_count": 1,
            "watchlist_count": 1, "total_at_risk_dollars": 0.0,
        }
        cards = self._hero_cards(summary)
        assert cards[0].style["borderTop"] == f"3px solid {TIER_CONFIG['act_now']['accent']}"
        assert cards[1].style["borderTop"] == f"3px solid {TIER_CONFIG['fix_or_rationalize']['accent']}"
        assert cards[2].style["borderTop"] == f"3px solid {TIER_CONFIG['watchlist']['accent']}"


# ── build_at_risk_data ───────────────────────────────────────────


class TestBuildAtRiskData:
    def test_declining_below_median_is_act_now(
        self, at_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """SKU below median + declining → act now tier, both signals."""
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(at_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(at_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(at_risk_scan_df)

            at_risk_df, watchlist_df, summary = build_at_risk_data(default_filters)

        assert not at_risk_df.empty, "at_risk_df should not be empty"
        risk_skus = at_risk_df[at_risk_df["at_risk_tier"] == "act_now"]
        assert "RISK-001" in risk_skus["sku"].values, "RISK-001 should be in act_now tier"
        row = risk_skus[risk_skus["sku"] == "RISK-001"].iloc[0]
        assert row["signal"] == "Level + Trend"

    def test_flat_below_median_is_fix_or_rationalize(
        self, flat_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """SKU below median + flat → fix or rationalize tier, level signal."""
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(flat_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(flat_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(flat_risk_scan_df)

            at_risk_df, watchlist_df, summary = build_at_risk_data(default_filters)

        assert not at_risk_df.empty, "at_risk_df should not be empty"
        fix_skus = at_risk_df[at_risk_df["at_risk_tier"] == "fix_or_rationalize"]
        assert "FLAT-001" in fix_skus["sku"].values, "FLAT-001 should be in fix_or_rationalize tier"
        row = fix_skus[fix_skus["sku"] == "FLAT-001"].iloc[0]
        assert row["signal"] == "Level"

    def test_declining_above_median_is_watchlist(
        self, watchlist_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """SKU above median + declining → watchlist tier, trend signal."""
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(watchlist_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(watchlist_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(watchlist_scan_df)

            at_risk_df, watchlist_df, summary = build_at_risk_data(default_filters)

        assert not watchlist_df.empty, "watchlist_df should not be empty"
        assert "WATCH-001" in watchlist_df["sku"].values, "WATCH-001 should be in watchlist"
        row = watchlist_df[watchlist_df["sku"] == "WATCH-001"].iloc[0]
        assert row["signal"] == "Trend"

    def test_healthy_sku_excluded(
        self, at_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """SKU above median + rising/flat → excluded from all tiers."""
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(at_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(at_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(at_risk_scan_df)

            at_risk_df, watchlist_df, summary = build_at_risk_data(default_filters)

        all_skus = set()
        if not at_risk_df.empty:
            all_skus.update(at_risk_df["sku"].values)
        if not watchlist_df.empty:
            all_skus.update(watchlist_df["sku"].values)
        # SAFE-001 has high, stable velocity — should not appear.
        assert "SAFE-001" not in all_skus

    def test_act_now_sorted_worst_first(
        self, at_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """Act-now items are sorted by velocity gap ascending (worst first)."""
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(at_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(at_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(at_risk_scan_df)

            at_risk_df, _, _ = build_at_risk_data(default_filters)

        if len(at_risk_df) > 1:
            gaps = at_risk_df["velocity_gap"].tolist()
            assert gaps == sorted(gaps)

    def test_empty_scan_data(self, default_filters):
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = pd.DataFrame()
            mock_db.get_stores.return_value = pd.DataFrame()
            mock_db.get_category_median_sppd.return_value = pd.DataFrame()
            mock_db.get_products.return_value = pd.DataFrame()
            mock_db.get_quarterly_sppd.return_value = pd.DataFrame()

            at_risk_df, watchlist_df, summary = build_at_risk_data(default_filters)

        assert at_risk_df.empty
        assert watchlist_df.empty
        assert summary == {}

    def test_summary_has_tier_counts(
        self, at_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(at_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(at_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(at_risk_scan_df)

            _, _, summary = build_at_risk_data(default_filters)

        if summary:
            assert "act_now_count" in summary
            assert "fix_or_rationalize_count" in summary
            assert "watchlist_count" in summary
            assert "total_at_risk_dollars" in summary

    def test_signal_column_present(
        self, at_risk_scan_df, sample_stores_df, multi_product_df, default_filters
    ):
        """Each row has a signal column with valid label."""
        valid_signals = {"Level", "Trend", "Level + Trend"}
        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(at_risk_scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(at_risk_scan_df, multi_product_df)
            mock_db.get_products.return_value = multi_product_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(at_risk_scan_df)

            at_risk_df, watchlist_df, _ = build_at_risk_data(default_filters)

        for df in [at_risk_df, watchlist_df]:
            if not df.empty:
                assert "signal" in df.columns
                for sig in df["signal"].values:
                    assert sig in valid_signals

    def test_limited_history_flagged(self, sample_stores_df, default_filters):
        """SKU with fewer than 4 quarters flagged as limited history."""
        # Only 2 quarters of data.
        rows = []
        for week in ["2024-10-07", "2025-01-07"]:
            for i in range(1, 6):
                rows.append({
                    "sku": "SHORT-001", "store_id": f"STR-{i:04d}",
                    "week_ending": week, "units_sold": 10, "dollars_sold": 50.0,
                })
            for i in range(1, 16):
                rows.append({
                    "sku": "LONG-001", "store_id": f"STR-{i:04d}",
                    "week_ending": week, "units_sold": 200, "dollars_sold": 1000.0,
                })
        scan_df = pd.DataFrame(rows)
        products_df = pd.DataFrame([
            {"sku": "SHORT-001", "product_name": "Short History", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
            {"sku": "LONG-001", "product_name": "Long History", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        ])

        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(scan_df, products_df)
            mock_db.get_products.return_value = products_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(scan_df)

            at_risk_df, watchlist_df, _ = build_at_risk_data(default_filters)

        all_results = pd.concat([at_risk_df, watchlist_df], ignore_index=True) if not at_risk_df.empty or not watchlist_df.empty else pd.DataFrame()
        assert not all_results.empty, "Expected SHORT-001 to be scored (below median, 2 quarters of data)"
        assert "SHORT-001" in all_results["sku"].values, "SHORT-001 missing from at-risk/watchlist results"
        row = all_results[all_results["sku"] == "SHORT-001"].iloc[0]
        assert row["limited_history"] == True  # noqa: E712 — numpy bool


# ── Tier scoring consistency with calculations.py ────────────────


class TestTierConsistency:
    def test_scoring_matches_calculations(self, sample_stores_df, default_filters):
        """Tier assignments match calculate_at_risk_score for same inputs."""
        from app.calculations import (
            calculate_at_risk_score,
            calculate_indexed_sppd,
            calculate_sppd,
            calculate_velocity_trend,
            days_in_quarter_range,
        )

        rows = []
        for week in ["2024-04-07", "2024-07-07", "2024-10-07", "2025-01-07"]:
            for i in range(1, 6):
                rows.append({
                    "sku": "TEST-001", "store_id": f"STR-{i:04d}",
                    "week_ending": week, "units_sold": 10, "dollars_sold": 50.0,
                })
            for i in range(1, 16):
                rows.append({
                    "sku": "TEST-002", "store_id": f"STR-{i:04d}",
                    "week_ending": week, "units_sold": 200, "dollars_sold": 1000.0,
                })
        scan_df = pd.DataFrame(rows)
        products_df = pd.DataFrame([
            {"sku": "TEST-001", "product_name": "Test 1", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
            {"sku": "TEST-002", "product_name": "Test 2", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        ])

        days = days_in_quarter_range("Q1 2025", "Q1 2025")
        sppd_df = calculate_sppd(scan_df, days)
        category_median_df = _category_median(scan_df, products_df, days)
        indexed_df = calculate_indexed_sppd(sppd_df, category_median_df, products_df)
        trend_df = calculate_velocity_trend(scan_df, products_df)
        direct_scored = calculate_at_risk_score(indexed_df, trend_df)

        with patch("app.db", create=True) as mock_db:
            mock_db.get_scan_data_agg.return_value = _agg_scan(scan_df)
            mock_db.get_stores.return_value = sample_stores_df
            mock_db.get_category_median_sppd.return_value = _category_median(scan_df, products_df)
            mock_db.get_products.return_value = products_df
            mock_db.get_quarterly_sppd.return_value = _scan_to_quarterly_sppd(scan_df)

            at_risk_df, watchlist_df, _ = build_at_risk_data(default_filters)

        all_view = pd.concat([at_risk_df, watchlist_df], ignore_index=True) if not at_risk_df.empty or not watchlist_df.empty else pd.DataFrame()

        assert not direct_scored.empty, "Expected TEST-001 to be scored as fix_or_rationalize"
        assert not all_view.empty, "Expected build_at_risk_data to return the same SKU"

        # Every SKU scored by calculations.py should appear in the view with same tier.
        for _, row in direct_scored.iterrows():
            assert row["sku"] in all_view["sku"].values, f"{row['sku']} missing from view results"
            view_row = all_view[all_view["sku"] == row["sku"]].iloc[0]
            assert view_row["at_risk_tier"] == row["at_risk_tier"]


# ── Layout structure ─────────────────────────────────────────────


class TestAtRiskLayout:
    def test_layout_returns_div(self):
        result = layout()
        assert result is not None

    def test_layout_has_at_risk_grid(self):
        result = layout()
        ids = _collect_ids(result)
        assert "at-risk-grid" in ids

    def test_layout_has_watchlist_grid(self):
        result = layout()
        ids = _collect_ids(result)
        assert "watchlist-grid" in ids

    def test_layout_has_separate_watchlist_section(self):
        """Watchlist section is separate from main at-risk grid (R20)."""
        result = layout()
        ids = _collect_ids(result)
        assert "watchlist-section" in ids

    def test_layout_has_detail_card_area(self):
        result = layout()
        ids = _collect_ids(result)
        assert "at-risk-detail-card" in ids

    def test_layout_has_summary_area(self):
        result = layout()
        ids = _collect_ids(result)
        assert "at-risk-summary" in ids

    def test_layout_has_window_note(self):
        """Layout surfaces the Level-vs-Trend window mismatch to the user."""
        result = layout()
        all_text = _collect_text(result)
        assert any(WINDOW_NOTE in text for text in all_text)


# ── Level vs Trend window disclosure ──────────────────────────────


class TestWindowDisclosure:
    """Trend uses a fixed 8-quarter window independent of the date filter;
    Level uses the selected date range. This must stay disclosed, not
    silently conflated."""

    def test_indexed_sppd_column_has_window_tooltip(self):
        col = next(c for c in _COLUMN_DEFS if c["field"] == "indexed_sppd")
        assert "headerTooltip" in col
        assert "date-range filter" in col["headerTooltip"]

    def test_trend_column_has_window_tooltip(self):
        col = next(c for c in _COLUMN_DEFS if c["field"] == "trend")
        assert "headerTooltip" in col
        assert "8 quarters" in col["headerTooltip"]
        assert "independent" in col["headerTooltip"]


# ── Helpers ──────────────────────────────────────────────────────


def _collect_text(component):
    """Recursively collect all string children from a Dash layout tree."""
    texts = []
    children = getattr(component, "children", None)
    if isinstance(children, str):
        texts.append(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            texts.extend(_collect_text(child))
    elif children is not None:
        texts.extend(_collect_text(children))
    return texts


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
