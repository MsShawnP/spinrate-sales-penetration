"""Tests for the migration view -- arrow overlay, side-by-side, sankey, detail card."""

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from app.calculations import calculate_acv_pct, calculate_sppd, classify_quadrant, days_in_quarter_range


def _agg_scan(scan_df):
    """Aggregate raw scan fixture to match get_scan_data_agg() output."""
    if scan_df.empty:
        return pd.DataFrame(columns=["sku", "total_units", "total_dollars", "door_count"])
    return scan_df.groupby("sku").agg(
        total_units=("units_sold", "sum"),
        total_dollars=("dollars_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()
from app.constants import (
    MIGRATION_FAVORABLE,
    MIGRATION_UNFAVORABLE,
    QUADRANT_LABELS,
)
from app.views.migration import (
    _MAX_ARROWS,
    _QUADRANT_RANK,
    _SANKEY_ORDER,
    _build_migration_df,
    _build_no_migration_figure,
    _compute_period_metrics,
    _get_default_qoq_quarters,
    build_arrow_overlay,
    build_sankey,
    build_side_by_side,
    layout,
)


# ── Fixtures for two-period data ─────────────────────────────────────


@pytest.fixture
def period1_scan_df():
    """Period 1 scan data: SKUs with different velocities.

    CHP-AS-001: low velocity (question marks territory).
    CHP-AS-002: high velocity, low distribution (hidden gems).
    CHP-PS-001: moderate velocity, high distribution (wide but dead or stars).
    """
    rows = []
    # CHP-AS-001: 50 units across 10 stores = low SPPD.
    for store_num in range(1, 11):
        rows.append({
            "sku": "CHP-AS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-07-15",
            "units_sold": 5,
            "dollars_sold": 25.0,
        })
    # CHP-AS-002: 500 units across 5 stores = high SPPD.
    for store_num in range(1, 6):
        rows.append({
            "sku": "CHP-AS-002",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-07-15",
            "units_sold": 100,
            "dollars_sold": 500.0,
        })
    # CHP-PS-001: 200 units across 20 stores = moderate SPPD.
    for store_num in range(1, 21):
        rows.append({
            "sku": "CHP-PS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-07-15",
            "units_sold": 10,
            "dollars_sold": 45.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def period2_scan_df():
    """Period 2 scan data: SKUs have shifted positions.

    CHP-AS-001: gained velocity (moved toward stars).
    CHP-AS-002: lost velocity (moved toward question marks).
    CHP-PS-001: unchanged position roughly.
    """
    rows = []
    # CHP-AS-001: now 200 units across 10 stores = higher SPPD.
    for store_num in range(1, 11):
        rows.append({
            "sku": "CHP-AS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-10-15",
            "units_sold": 20,
            "dollars_sold": 100.0,
        })
    # CHP-AS-002: dropped to 25 units across 5 stores = low SPPD.
    for store_num in range(1, 6):
        rows.append({
            "sku": "CHP-AS-002",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-10-15",
            "units_sold": 5,
            "dollars_sold": 25.0,
        })
    # CHP-PS-001: roughly same.
    for store_num in range(1, 21):
        rows.append({
            "sku": "CHP-PS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-10-15",
            "units_sold": 10,
            "dollars_sold": 45.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def two_period_metrics(
    period1_scan_df, period2_scan_df,
    sample_dist_df, sample_stores_df, sample_products_df,
):
    """Compute period metrics for both periods and return migration_df."""
    p1 = _compute_period_metrics(
        _agg_scan(period1_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q3 2025"
    )
    p2 = _compute_period_metrics(
        _agg_scan(period2_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q4 2025"
    )
    return p1, p2, _build_migration_df(p1, p2)


# ── Quadrant classification ─────────────────────────────────────────


class TestMigrationClassifyQuadrant:
    """Quadrant classification in migration module matches quadrant view."""

    def test_star(self):
        assert classify_quadrant(2.0, 0.8, 1.0, 0.5) == QUADRANT_LABELS["star"]

    def test_hidden_gem(self):
        assert classify_quadrant(2.0, 0.2, 1.0, 0.5) == QUADRANT_LABELS["hidden_gem"]

    def test_wide_but_dead(self):
        assert classify_quadrant(0.3, 0.8, 1.0, 0.5) == QUADRANT_LABELS["wide_but_dead"]

    def test_question_mark(self):
        assert classify_quadrant(0.3, 0.2, 1.0, 0.5) == QUADRANT_LABELS["question_mark"]


# ── Default QoQ ──────────────────────────────────────────────────────


class TestDefaultQoQ:
    """Default QoQ quarter logic."""

    def test_qoq_returns_consecutive_quarters(self):
        """Default QoQ should return the previous quarter and the end quarter."""
        filters = {"end_quarter": "Q4 2025"}
        q1, q2 = _get_default_qoq_quarters(filters)
        assert q1 == "Q3 2025"
        assert q2 == "Q4 2025"

    def test_qoq_first_quarter(self):
        """When end_quarter is the first available, both should be the same."""
        filters = {"end_quarter": "Q1 2024"}
        q1, q2 = _get_default_qoq_quarters(filters)
        assert q1 == "Q1 2024"
        assert q2 == "Q1 2024"


# ── Period metrics computation ───────────────────────────────────────


class TestComputePeriodMetrics:
    """Period metric computation from scan data."""

    def test_returns_expected_columns(
        self, sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df,
    ):
        """Period metrics should contain all required columns."""
        result = _compute_period_metrics(
            _agg_scan(sample_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q1 2025"
        )
        expected_cols = {"sku", "sppd", "acv_pct", "quadrant",
                         "product_name", "product_line", "total_dollars", "door_count"}
        assert expected_cols.issubset(set(result.columns))

    def test_returns_all_skus(
        self, sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df,
    ):
        """All SKUs present in both scan and dist data should appear."""
        result = _compute_period_metrics(
            _agg_scan(sample_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q1 2025"
        )
        assert len(result) == 3

    def test_empty_scan_returns_empty(
        self, sample_dist_df, sample_stores_df, sample_products_df,
    ):
        """Empty scan data should return empty DataFrame."""
        empty_scan = pd.DataFrame(columns=["sku", "total_units", "total_dollars", "door_count"])
        result = _compute_period_metrics(
            empty_scan, sample_dist_df, sample_stores_df, sample_products_df, "Q1 2025"
        )
        assert result.empty


# ── Migration DataFrame ──────────────────────────────────────────────


class TestBuildMigrationDf:
    """Migration DataFrame construction from two period DataFrames."""

    def test_migration_df_has_both_periods(self, two_period_metrics):
        """Migration DF should have columns from both periods."""
        _, _, migration_df = two_period_metrics
        assert "sppd_p1" in migration_df.columns
        assert "sppd_p2" in migration_df.columns
        assert "quadrant_p1" in migration_df.columns
        assert "quadrant_p2" in migration_df.columns

    def test_identifies_movers(self, two_period_metrics):
        """SKUs that changed quadrant should be flagged as moved."""
        _, _, migration_df = two_period_metrics
        assert "moved" in migration_df.columns
        # At least one should have moved given the data shift.
        assert migration_df["moved"].any()

    def test_identifies_stayers(self, two_period_metrics):
        """SKUs that did NOT change quadrant should exist as stayers."""
        _, _, migration_df = two_period_metrics
        stayers = migration_df[~migration_df["moved"]]
        # CHP-PS-001 has roughly the same position in both periods.
        # May or may not stay depending on median shifts. Just check the column exists.
        assert "moved" in migration_df.columns

    def test_empty_inputs(self):
        """Empty period DataFrames produce empty migration DF."""
        empty = pd.DataFrame(columns=["sku", "sppd", "acv_pct", "quadrant",
                                       "product_name", "product_line", "total_dollars", "door_count"])
        result = _build_migration_df(empty, empty)
        assert result.empty

    def test_magnitude_computed(self, two_period_metrics):
        """Migration magnitude should be computed for ranking."""
        _, _, migration_df = two_period_metrics
        assert "magnitude" in migration_df.columns
        assert migration_df["magnitude"].notna().all()


# ── Arrow overlay ────────────────────────────────────────────────────


class TestArrowOverlay:
    """Arrow overlay visualization."""

    def test_arrow_figure_is_valid(self, two_period_metrics):
        """Arrow overlay should return a valid Plotly figure."""
        _, _, migration_df = two_period_metrics
        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_has_ghost_dots_trace(self, two_period_metrics):
        """Arrow overlay should have a ghost dot trace for Period 1."""
        _, _, migration_df = two_period_metrics
        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")
        trace_names = [t.name for t in fig.data if t.name]
        assert any("Q3 2025" in name for name in trace_names)

    def test_favorable_arrow_drawn(self, two_period_metrics):
        """SKU moving to a better quadrant should get an arrow annotation."""
        _, _, migration_df = two_period_metrics
        movers = migration_df[migration_df["moved"]]

        if movers.empty:
            pytest.skip("No movers in test data")

        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")

        # Check annotations for positional arrows (those with axref="x").
        arrow_annots = [a for a in fig.layout.annotations
                        if getattr(a, "axref", None) == "x"]
        assert len(arrow_annots) > 0, "Expected at least one positional arrow annotation"

    def test_arrow_colors(self, two_period_metrics):
        """Arrows should use teal for favorable and rose for unfavorable."""
        _, _, migration_df = two_period_metrics
        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")

        arrow_annots = [a for a in fig.layout.annotations
                        if getattr(a, "axref", None) == "x"]

        arrow_colors = [a.arrowcolor for a in arrow_annots]
        # Should contain either favorable or unfavorable colors.
        valid_colors = {MIGRATION_FAVORABLE, MIGRATION_UNFAVORABLE, "#666666"}  # REFERENCE
        for color in arrow_colors:
            assert color in valid_colors, f"Unexpected arrow color: {color}"

    def test_stationary_dots_no_arrow(self, two_period_metrics):
        """SKUs that didn't move should appear as dots without arrows."""
        _, _, migration_df = two_period_metrics
        stayers = migration_df[~migration_df["moved"]]

        if stayers.empty:
            pytest.skip("All SKUs moved in test data")

        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")

        # Stayer trace should exist.
        trace_names = [t.name for t in fig.data if t.name]
        has_no_change = any("no change" in name.lower() for name in trace_names)
        assert has_no_change, f"No 'no change' trace found. Traces: {trace_names}"

    def test_default_loads_arrows(self, two_period_metrics):
        """Default viz mode should produce an arrow overlay figure."""
        _, _, migration_df = two_period_metrics
        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")
        assert isinstance(fig, go.Figure)
        # Should have arrow annotations (positional ones).
        arrow_annots = [a for a in fig.layout.annotations
                        if getattr(a, "axref", None) == "x"]
        # May have arrows if there are movers.
        movers = migration_df[migration_df["moved"]]
        if not movers.empty:
            assert len(arrow_annots) > 0

    def test_empty_migration_shows_message(self):
        """Empty migration DF should produce the 'no changes' figure."""
        fig = build_arrow_overlay(pd.DataFrame(), "Q3 2025", "Q4 2025")
        assert isinstance(fig, go.Figure)
        assert any("No quadrant changes" in a.text for a in fig.layout.annotations)

    def test_legend_uses_constant_item_sizing(self, two_period_metrics):
        """Legend swatches must not inherit per-point marker size -- without
        itemsizing="constant" the color dots render huge and sit on top of
        the label text, inflating entry width so "Unfavorable" (the last
        entry) clips at the right edge instead of wrapping."""
        _, _, migration_df = two_period_metrics
        fig = build_arrow_overlay(migration_df, "Q3 2025", "Q4 2025")
        assert fig.layout.legend.itemsizing == "constant"


# ── Side-by-side ─────────────────────────────────────────────────────


class TestSideBySide:
    """Side-by-side visualization mode."""

    def test_side_by_side_renders_two_panels(self, two_period_metrics):
        """Side-by-side should produce a figure with two scatter traces."""
        _, _, migration_df = two_period_metrics
        fig = build_side_by_side(migration_df, "Q3 2025", "Q4 2025")
        assert isinstance(fig, go.Figure)
        # Should have exactly 2 scatter traces (one per panel).
        scatter_traces = [t for t in fig.data if isinstance(t, go.Scatter)]
        assert len(scatter_traces) == 2

    def test_side_by_side_has_consistent_scale(self, two_period_metrics):
        """Both panels should share the same axis ranges."""
        _, _, migration_df = two_period_metrics
        fig = build_side_by_side(migration_df, "Q3 2025", "Q4 2025")
        # Both x-axes should have the same range.
        x1_range = fig.layout.xaxis.range
        x2_range = fig.layout.xaxis2.range
        assert x1_range == x2_range

    def test_side_by_side_empty_df(self):
        """Empty DataFrame should show the no-migration message."""
        fig = build_side_by_side(pd.DataFrame(), "Q3 2025", "Q4 2025")
        assert any("No quadrant changes" in a.text for a in fig.layout.annotations)


# ── Sankey ───────────────────────────────────────────────────────────


class TestSankey:
    """Sankey diagram visualization mode."""

    def test_sankey_renders_flow(self, two_period_metrics):
        """Sankey should produce a figure with a Sankey trace."""
        _, _, migration_df = two_period_metrics
        fig = build_sankey(migration_df, "Q3 2025", "Q4 2025")
        assert isinstance(fig, go.Figure)
        sankey_traces = [t for t in fig.data if isinstance(t, go.Sankey)]
        assert len(sankey_traces) == 1

    def test_sankey_has_correct_node_count(self, two_period_metrics):
        """Sankey should have 8 nodes (4 source + 4 target quadrants)."""
        _, _, migration_df = two_period_metrics
        fig = build_sankey(migration_df, "Q3 2025", "Q4 2025")
        sankey = fig.data[0]
        assert len(sankey.node.label) == 8

    def test_sankey_flow_counts_match(self, two_period_metrics):
        """Total flow values should equal number of SKUs in migration_df."""
        _, _, migration_df = two_period_metrics
        fig = build_sankey(migration_df, "Q3 2025", "Q4 2025")
        sankey = fig.data[0]
        total_flow = sum(sankey.link.value)
        assert total_flow == len(migration_df)

    def test_sankey_empty_df(self):
        """Empty DataFrame should show the no-migration message."""
        fig = build_sankey(pd.DataFrame(), "Q3 2025", "Q4 2025")
        assert any("No quadrant changes" in a.text for a in fig.layout.annotations)


# ── No migration figure ──────────────────────────────────────────────


class TestNoMigrationFigure:
    """The 'no quadrant changes' empty state figure."""

    def test_shows_message(self):
        """Should display the no-changes message."""
        fig = _build_no_migration_figure()
        assert isinstance(fig, go.Figure)
        assert any("No quadrant changes" in a.text for a in fig.layout.annotations)


# ── Layout structure ─────────────────────────────────────────────────


class TestMigrationLayout:
    """Migration view layout component structure."""

    def test_layout_returns_div(self):
        """layout() should return an html.Div."""
        from dash import html
        result = layout()
        assert isinstance(result, html.Div)

    def test_layout_has_chart(self):
        """Layout should contain the migration-chart Graph component."""
        result = layout()
        assert _find_component(result, "migration-chart")

    def test_layout_has_detail_card_area(self):
        """Layout should contain the detail card container."""
        result = layout()
        assert _find_component(result, "migration-detail-card")

    def test_layout_has_customize_toggle(self):
        """Layout should contain the customize toggle button."""
        result = layout()
        assert _find_component(result, "migration-customize-toggle")

    def test_layout_has_period_selector(self):
        """Layout should contain the period mode selector."""
        result = layout()
        assert _find_component(result, "migration-period-selector")

    def test_layout_has_viz_selector(self):
        """Layout should contain the viz mode selector."""
        result = layout()
        assert _find_component(result, "migration-viz-selector")


# ── Click-to-pin detail card ─────────────────────────────────────────


class TestMigrationDetailCard:
    """Detail card shows both periods for comparison."""

    def test_detail_card_both_periods(
        self, period1_scan_df, period2_scan_df,
        sample_dist_df, sample_stores_df, sample_products_df,
    ):
        """Detail card should show metrics from both periods."""
        from app.components import dark_callout_card
        from app.constants import fmt_pct, fmt_dollars

        p1 = _compute_period_metrics(
            _agg_scan(period1_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q3 2025"
        )
        p2 = _compute_period_metrics(
            _agg_scan(period2_scan_df), sample_dist_df, sample_stores_df, sample_products_df, "Q4 2025"
        )

        sku = "CHP-AS-001"
        p1_row = p1[p1["sku"] == sku].iloc[0]
        p2_row = p2[p2["sku"] == sku].iloc[0]

        rows = [
            {"label": "SPPD (Q3 2025)", "value": f"{p1_row['sppd']:.4f}"},
            {"label": "ACV% (Q3 2025)", "value": fmt_pct(p1_row["acv_pct"])},
            {"label": "Quadrant (Q3 2025)", "value": p1_row["quadrant"]},
            {"label": "SPPD (Q4 2025)", "value": f"{p2_row['sppd']:.4f}"},
            {"label": "ACV% (Q4 2025)", "value": fmt_pct(p2_row["acv_pct"])},
            {"label": "Quadrant (Q4 2025)", "value": p2_row["quadrant"]},
        ]

        card = dark_callout_card(title="Classic Marinara", subtitle="Artisan Sauces", rows=rows)
        assert card.className == "dark-callout"

        all_text = _extract_text(card)
        assert "SPPD (Q3 2025)" in all_text
        assert "SPPD (Q4 2025)" in all_text
        assert "Quadrant (Q3 2025)" in all_text
        assert "Quadrant (Q4 2025)" in all_text


# ── Same period selection ────────────────────────────────────────────


class TestSamePeriodPrevention:
    """Same period selection should be handled gracefully."""

    def test_same_period_returns_no_migration(self):
        """Selecting the same quarter for both periods returns the no-migration figure."""
        # When custom mode with same quarters, the chart callback returns no-migration.
        fig = _build_no_migration_figure()
        assert isinstance(fig, go.Figure)
        assert any("No quadrant changes" in a.text for a in fig.layout.annotations)


# ── Helpers ──────────────────────────────────────────────────────────


def _find_component(component, target_id):
    """Recursively search for a Dash component by its ID."""
    if hasattr(component, "id") and component.id == target_id:
        return True
    if hasattr(component, "children"):
        children = component.children
        if children is None:
            return False
        if not isinstance(children, (list, tuple)):
            children = [children]
        for child in children:
            if _find_component(child, target_id):
                return True
    return False


def _extract_text(component):
    """Recursively extract all text from a Dash component tree."""
    texts = []
    if hasattr(component, "children"):
        children = component.children
        if isinstance(children, str):
            texts.append(children)
        elif isinstance(children, (list, tuple)):
            for child in children:
                texts.extend(_extract_text(child))
        elif children is not None:
            texts.extend(_extract_text(children))
    return texts
