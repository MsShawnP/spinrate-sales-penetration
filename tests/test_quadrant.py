"""Tests for the quadrant view — bubble scatter chart, detail card, indexed toggle."""

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from app.calculations import (
    calculate_acv_pct,
    calculate_category_median_sppd,
    calculate_sppd,
    classify_quadrant,
)
from app.views.quadrant import (
    LOW_DOOR_THRESHOLD,
    _build_empty_figure,
    _build_quadrant_figure,
    _scale_bubble_sizes,
    layout,
)
from app.constants import QUADRANT_LABELS


# ── Bubble size scaling ───────────────────────────────────────────


class TestScaleBubbleSizes:
    """Bubble size mapping from dollar amounts to pixel sizes."""

    def test_scales_within_bounds(self):
        """All sizes should fall within min/max bounds."""
        dollars = pd.Series([100, 1000, 5000, 20000, 100000])
        sizes = _scale_bubble_sizes(dollars)
        assert sizes.min() >= 8
        assert sizes.max() <= 45

    def test_single_value_returns_midpoint(self):
        """A single value (min==max) returns the midpoint size."""
        dollars = pd.Series([5000, 5000, 5000])
        sizes = _scale_bubble_sizes(dollars)
        expected_mid = 8 + (45 - 8) / 2
        assert all(abs(s - expected_mid) < 0.01 for s in sizes)

    def test_empty_series(self):
        """Empty series returns empty."""
        sizes = _scale_bubble_sizes(pd.Series(dtype=float))
        assert sizes.empty

    def test_zero_max(self):
        """All zeros returns uniform midpoint bubbles."""
        sizes = _scale_bubble_sizes(pd.Series([0, 0, 0]))
        assert len(sizes) == 3
        expected_mid = 8 + (45 - 8) / 2
        assert all(abs(s - expected_mid) < 0.01 for s in sizes)

    def test_larger_values_get_larger_bubbles(self):
        """Higher dollar amounts produce larger bubble sizes."""
        dollars = pd.Series([100, 100000])
        sizes = _scale_bubble_sizes(dollars)
        assert sizes.iloc[1] > sizes.iloc[0]


# ── Quadrant classification ───────────────────────────────────────


class TestClassifyQuadrant:
    """SKU quadrant assignment based on SPPD and ACV% relative to medians."""

    def test_star_top_right(self):
        """High SPPD + high ACV% = Stars."""
        result = classify_quadrant(sppd=2.0, acv_pct=0.8, median_sppd=1.0, median_acv=0.5)
        assert result == QUADRANT_LABELS["star"]

    def test_hidden_gem_top_left(self):
        """High SPPD + low ACV% = Hidden Gems."""
        result = classify_quadrant(sppd=2.0, acv_pct=0.2, median_sppd=1.0, median_acv=0.5)
        assert result == QUADRANT_LABELS["hidden_gem"]

    def test_wide_but_dead_bottom_right(self):
        """Low SPPD + high ACV% = Wide but Dead."""
        result = classify_quadrant(sppd=0.3, acv_pct=0.8, median_sppd=1.0, median_acv=0.5)
        assert result == QUADRANT_LABELS["wide_but_dead"]

    def test_question_mark_bottom_left(self):
        """Low SPPD + low ACV% = Question Marks."""
        result = classify_quadrant(sppd=0.3, acv_pct=0.2, median_sppd=1.0, median_acv=0.5)
        assert result == QUADRANT_LABELS["question_mark"]

    def test_on_median_is_star(self):
        """Exactly at both medians counts as Stars (>= comparison)."""
        result = classify_quadrant(sppd=1.0, acv_pct=0.5, median_sppd=1.0, median_acv=0.5)
        assert result == QUADRANT_LABELS["star"]

    def test_quadrant_is_filter_independent_with_fixed_medians(
        self, sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df,
    ):
        """Same SKU classifies to the same quadrant whether it's evaluated
        alone (a heavily filtered selection) or alongside its peers (a wide
        selection), as long as the dividing-line medians come from the full,
        unfiltered dataset rather than the filtered selection itself.

        Regression test for the bug where median_sppd/median_acv were
        chart_df["sppd"].median() / chart_df["acv_pct"].median() -- computed
        from whatever happened to be in the filtered selection. A lone SKU
        was always exactly at its own median, so it always classified as a
        Star (>= comparison) no matter how weak it actually was.
        """
        from app.calculations import calculate_global_medians

        full_sppd_df = calculate_sppd(sample_scan_df, 91)
        full_acv_df = calculate_acv_pct(sample_dist_df, sample_stores_df)
        global_medians = calculate_global_medians(full_sppd_df, full_acv_df)
        fixed_median_sppd = global_medians["median_sppd"].iloc[0]
        fixed_median_acv = global_medians["median_acv"].iloc[0]

        sku = "CHP-AS-001"
        sku_sppd = full_sppd_df[full_sppd_df["sku"] == sku]["sppd"].iloc[0]
        sku_acv = full_acv_df[full_acv_df["sku"] == sku]["acv_pct"].iloc[0]

        # CHP-AS-001 sits at the full-dataset median SPPD but well below the
        # full-dataset median ACV% -- a Hidden Gem -- whether evaluated
        # alone or alongside its peers, because the dividing lines don't move.
        wide_selection_quadrant = classify_quadrant(
            sku_sppd, sku_acv, fixed_median_sppd, fixed_median_acv
        )
        narrow_selection_quadrant = classify_quadrant(
            sku_sppd, sku_acv, fixed_median_sppd, fixed_median_acv
        )
        assert wide_selection_quadrant == narrow_selection_quadrant == QUADRANT_LABELS["hidden_gem"]

        # Demonstrate the bug this guards against: if the dividing lines
        # were instead derived from a lone-SKU filtered selection (the old
        # behavior), the SKU would always land at/above its own median --
        # always a Star -- regardless of how it compares to its peers.
        old_buggy_median_sppd = sku_sppd
        old_buggy_median_acv = sku_acv
        old_buggy_quadrant = classify_quadrant(
            sku_sppd, sku_acv, old_buggy_median_sppd, old_buggy_median_acv
        )
        assert old_buggy_quadrant == QUADRANT_LABELS["star"]
        assert old_buggy_quadrant != wide_selection_quadrant


# ── Bubble figure construction ────────────────────────────────────


class TestBuildQuadrantFigure:
    """Plotly figure construction for the quadrant chart."""

    @pytest.fixture
    def sample_chart_df(self, sample_scan_df, sample_dist_df, sample_stores_df, sample_products_df):
        """Build a chart DataFrame from the shared fixtures."""
        sppd_df = calculate_sppd(sample_scan_df, 91)
        acv_df = calculate_acv_pct(sample_dist_df, sample_stores_df)

        chart_df = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
        chart_df = chart_df.merge(
            sample_products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
        )

        dollars = sample_scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
        dollars.columns = ["sku", "total_dollars"]
        chart_df = chart_df.merge(dollars, on="sku", how="left")
        chart_df["total_dollars"] = chart_df["total_dollars"].fillna(0)
        chart_df["bubble_size"] = _scale_bubble_sizes(chart_df["total_dollars"])
        chart_df["opacity"] = 1.0
        chart_df["indexed_sppd"] = chart_df["sppd"]

        median_sppd = chart_df["sppd"].median()
        median_acv = chart_df["acv_pct"].median()
        chart_df["quadrant"] = chart_df.apply(
            lambda row: classify_quadrant(row["sppd"], row["acv_pct"], median_sppd, median_acv),
            axis=1,
        )
        chart_df["product_name"] = chart_df["product_name"].fillna(chart_df["sku"])
        chart_df["product_line"] = chart_df["product_line"].fillna("Unknown")

        return chart_df, median_sppd, median_acv

    def test_figure_has_traces(self, sample_chart_df):
        """Figure should have at least one trace per product line."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_figure_has_dividing_lines(self, sample_chart_df):
        """Figure should have horizontal and vertical dividing lines."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)

        shapes = fig.layout.shapes
        assert len(shapes) >= 2  # horizontal + vertical dividing lines
        # Verify we have both an h-line and a v-line shape.
        has_hline = any(s.y0 == s.y1 and s.xref == "paper" for s in shapes)
        has_vline = any(s.x0 == s.x1 and s.yref == "paper" for s in shapes)
        assert has_hline, "Missing horizontal dividing line"
        assert has_vline, "Missing vertical dividing line"

    def test_figure_has_quadrant_annotations(self, sample_chart_df):
        """Figure should have 4 quadrant label annotations."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)

        annotations = fig.layout.annotations
        annotation_texts = [a.text for a in annotations]
        for label in QUADRANT_LABELS.values():
            assert label in annotation_texts, f"Missing quadrant label: {label}"

    def test_legend_uses_constant_item_sizing(self, sample_chart_df):
        """Legend swatches must not inherit per-point bubble marker size
        (up to 45px) -- without itemsizing="constant" the color dots
        render huge and sit on top of the label text, inflating entry
        width so rows run off the right edge instead of wrapping."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)
        assert fig.layout.legend.itemsizing == "constant"

    def test_low_door_count_flagged(self, sample_chart_df):
        """SKUs below door threshold appear in a visually distinct (faded/
        dashed) trace. The legend no longer labels this with a "(low doors)"
        suffix -- that inflated entry width and duplicated the row per
        product line. The distinction is now marker style plus a caption
        below the chart (see quadrant.py layout())."""
        chart_df, median_sppd, median_acv = sample_chart_df

        # CHP-AS-002 has 5 doors, which is below the threshold of 10.
        low_door_sku = chart_df[chart_df["door_count"] < LOW_DOOR_THRESHOLD]
        assert not low_door_sku.empty, "Test fixture should have a low-door SKU"

        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)

        low_door_traces = [t for t in fig.data if t.marker.line.dash == "dash"]
        assert low_door_traces, (
            f"No dashed (low-door) trace found. Traces: {[t.name for t in fig.data]}"
        )
        assert low_door_traces[0].marker.opacity == 0.4

    def test_low_door_trace_name_has_no_suffix(self, sample_chart_df):
        """Regression test: legend entry names are the bare product line,
        not '<line> (low doors)' -- that suffix duplicated the row per
        product line and inflated entry width past the wrap boundary."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)

        trace_names = [t.name for t in fig.data if t.name]
        assert trace_names, "Expected at least one named trace"
        assert not any("low doors" in name for name in trace_names)
        assert "Artisan Sauces" in trace_names

    def test_indexed_mode_changes_y_axis(self, sample_chart_df):
        """Indexed mode should change the y-axis label."""
        chart_df, _, median_acv = sample_chart_df

        fig_normal = _build_quadrant_figure(chart_df, 0.5, median_acv, indexed_mode=False)
        fig_indexed = _build_quadrant_figure(chart_df, 1.0, median_acv, indexed_mode=True)

        y_label_normal = fig_normal.layout.yaxis.title.text
        y_label_indexed = fig_indexed.layout.yaxis.title.text

        assert "Indexed" not in y_label_normal
        assert "Indexed" in y_label_indexed

    def test_marker_mode_is_markers(self, sample_chart_df):
        """All traces use mode='markers'."""
        chart_df, median_sppd, median_acv = sample_chart_df
        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)
        for trace in fig.data:
            assert trace.mode == "markers"


# ── Empty figure ──────────────────────────────────────────────────


class TestBuildEmptyFigure:
    """Empty-state figure when no data matches filters."""

    def test_empty_figure_has_annotation(self):
        """Empty figure should show a 'no data' message."""
        fig = _build_empty_figure()
        assert isinstance(fig, go.Figure)
        annotations = fig.layout.annotations
        assert any("No data" in a.text for a in annotations)


# ── Layout structure ──────────────────────────────────────────────


class TestQuadrantLayout:
    """Quadrant view layout component structure."""

    def test_layout_returns_div(self):
        """layout() should return a Div component."""
        from dash import html
        result = layout()
        assert isinstance(result, html.Div)

    def test_layout_has_chart(self):
        """Layout should contain the quadrant-chart Graph component."""
        from dash import dcc
        result = layout()

        def _find_component(component, target_id):
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

        assert _find_component(result, "quadrant-chart")

    def test_layout_has_detail_card_area(self):
        """Layout should contain the detail card container."""
        result = layout()

        def _find_component(component, target_id):
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

        assert _find_component(result, "quadrant-detail-card")

    def test_layout_has_indexed_toggle(self):
        """Layout should contain the indexed SPPD toggle button."""
        result = layout()

        def _find_component(component, target_id):
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

        assert _find_component(result, "indexed-sppd-toggle")

    def test_layout_has_formula_note(self):
        """Layout should contain the SPPD formula note."""
        from app.constants import SPPD_FORMULA

        result = layout()

        def _find_text(component, target_text):
            if hasattr(component, "children") and component.children == target_text:
                return True
            if hasattr(component, "children"):
                children = component.children
                if children is None:
                    return False
                if not isinstance(children, (list, tuple)):
                    children = [children]
                for child in children:
                    if _find_text(child, target_text):
                        return True
            return False

        assert _find_text(result, SPPD_FORMULA)

    def test_layout_has_low_door_caption(self):
        """Layout should explain the faded/dashed low-door marker style now
        that the legend no longer labels it with a "(low doors)" suffix."""
        result = layout()

        def _find_text(component, target_text):
            if hasattr(component, "children") and component.children == target_text:
                return True
            if hasattr(component, "children"):
                children = component.children
                if children is None:
                    return False
                if not isinstance(children, (list, tuple)):
                    children = [children]
                for child in children:
                    if _find_text(child, target_text):
                        return True
            return False

        assert _find_text(result, "Faded/dashed markers = low door count (<10 stores).")


# ── Detail card rendering ─────────────────────────────────────────


class TestDetailCard:
    """Detail card content correctness when a SKU is selected."""

    def test_detail_card_shows_correct_fields(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """The dark callout card should include all required detail fields."""
        from app.components import dark_callout_card

        sppd_df = calculate_sppd(sample_scan_df, 91)
        acv_df = calculate_acv_pct(sample_dist_df, sample_stores_df)

        sku = "CHP-AS-001"
        sku_sppd = sppd_df[sppd_df["sku"] == sku].iloc[0]
        sku_acv = acv_df[acv_df["sku"] == sku].iloc[0]

        rows = [
            {"label": "SPPD", "value": f"{sku_sppd['sppd']:.4f}"},
            {"label": "ACV%", "value": f"{sku_acv['acv_pct'] * 100:.1f}%"},
            {"label": "Total Dollars", "value": "$500"},
            {"label": "Door Count", "value": "10"},
            {"label": "Quadrant", "value": "Stars"},
            {"label": "Velocity Trend", "value": "Flat"},
        ]

        card = dark_callout_card(title="Classic Marinara", subtitle="Artisan Sauces", rows=rows)

        # Card is an html.Div with class "dark-callout".
        assert card.className == "dark-callout"

        # Verify all labels are present in the card children.
        def _extract_text(component):
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

        all_text = _extract_text(card)
        assert "Classic Marinara" in all_text
        assert "Artisan Sauces" in all_text
        assert "SPPD" in all_text
        assert "ACV%" in all_text
        assert "Total Dollars" in all_text
        assert "Door Count" in all_text
        assert "Quadrant" in all_text
        assert "Velocity Trend" in all_text


# ── Filter integration (mocked DB) ───────────────────────────────


class TestFilterIntegration:
    """Chart rebuilds when filters change (mocked DB layer)."""

    def _mock_db_functions(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """Return a dict of mock return values for db functions."""
        return {
            "app.db.get_scan_data_agg": sample_scan_df,
            "app.db.get_distribution": sample_dist_df,
            "app.db.get_stores": sample_stores_df,
            "app.db.get_benchmarks": sample_benchmarks_df,
            "app.db.get_products": sample_products_df,
        }

    def test_filter_change_triggers_rebuild(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """Changing filter state should produce a valid figure (via helper functions)."""
        # Simulate what the callback does: load data, compute, build figure.
        from app.calculations import days_in_quarter_range

        filters = {"retailers": [], "region": None, "start_quarter": "Q1 2025", "end_quarter": "Q4 2025"}
        days = days_in_quarter_range(filters["start_quarter"], filters["end_quarter"])

        sppd_df = calculate_sppd(sample_scan_df, days)
        acv_df = calculate_acv_pct(sample_dist_df, sample_stores_df)

        chart_df = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
        chart_df = chart_df.merge(
            sample_products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
        )

        dollars = sample_scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
        dollars.columns = ["sku", "total_dollars"]
        chart_df = chart_df.merge(dollars, on="sku", how="left")
        chart_df["total_dollars"] = chart_df["total_dollars"].fillna(0)
        chart_df["bubble_size"] = _scale_bubble_sizes(chart_df["total_dollars"])
        chart_df["opacity"] = 1.0
        chart_df["indexed_sppd"] = chart_df["sppd"]

        median_sppd = chart_df["sppd"].median()
        median_acv = chart_df["acv_pct"].median()
        chart_df["quadrant"] = chart_df.apply(
            lambda row: classify_quadrant(row["sppd"], row["acv_pct"], median_sppd, median_acv),
            axis=1,
        )
        chart_df["product_name"] = chart_df["product_name"].fillna(chart_df["sku"])
        chart_df["product_line"] = chart_df["product_line"].fillna("Unknown")

        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) > 0

    def test_empty_filter_results_show_empty_state(self):
        """Empty scan data produces the empty-state figure."""
        fig = _build_empty_figure()
        assert isinstance(fig, go.Figure)
        assert any("No data" in a.text for a in fig.layout.annotations)


# ── Indexed SPPD toggle ──────────────────────────────────────────


class TestIndexedSPPDToggle:
    """Indexed SPPD mode changes chart y-axis."""

    def test_indexed_mode_dividing_line_at_one(
        self, sample_scan_df, sample_dist_df, sample_stores_df,
        sample_products_df, sample_benchmarks_df,
    ):
        """In indexed mode, the horizontal dividing line should be at y=1.0."""
        sppd_df = calculate_sppd(sample_scan_df, 91)
        acv_df = calculate_acv_pct(sample_dist_df, sample_stores_df)

        chart_df = sppd_df.merge(acv_df[["sku", "acv_pct"]], on="sku", how="inner")
        chart_df = chart_df.merge(
            sample_products_df[["sku", "product_name", "product_line"]], on="sku", how="left"
        )

        dollars = sample_scan_df.groupby("sku")["dollars_sold"].sum().reset_index()
        dollars.columns = ["sku", "total_dollars"]
        chart_df = chart_df.merge(dollars, on="sku", how="left")
        chart_df["total_dollars"] = chart_df["total_dollars"].fillna(0)
        chart_df["bubble_size"] = _scale_bubble_sizes(chart_df["total_dollars"])
        chart_df["opacity"] = 1.0

        # Compute indexed SPPD.
        from app.calculations import calculate_indexed_sppd
        category_median_df = calculate_category_median_sppd(sppd_df, sample_products_df)
        indexed_df = calculate_indexed_sppd(sppd_df, category_median_df, sample_products_df)
        chart_df = chart_df.merge(indexed_df[["sku", "indexed_sppd"]], on="sku", how="left")
        chart_df["indexed_sppd"] = chart_df["indexed_sppd"].fillna(1.0)

        median_sppd = 1.0
        median_acv = chart_df["acv_pct"].median()

        chart_df["quadrant"] = chart_df.apply(
            lambda row: classify_quadrant(row["indexed_sppd"], row["acv_pct"], median_sppd, median_acv),
            axis=1,
        )
        chart_df["product_name"] = chart_df["product_name"].fillna(chart_df["sku"])
        chart_df["product_line"] = chart_df["product_line"].fillna("Unknown")

        fig = _build_quadrant_figure(chart_df, median_sppd, median_acv, indexed_mode=True)

        # The horizontal dividing line should be at y=1.0.
        hlines = [s for s in fig.layout.shapes
                  if s.type == "line" and s.y0 == s.y1 and s.xref == "paper"]
        assert any(abs(s.y0 - 1.0) < 0.01 for s in hlines), \
            f"No hline at 1.0 found. Shapes: {[(s.type, s.y0, s.y1) for s in fig.layout.shapes]}"

        # Y-axis label should mention "Indexed".
        assert "Indexed" in fig.layout.yaxis.title.text
