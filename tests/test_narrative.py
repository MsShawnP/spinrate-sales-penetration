"""Tests for narrative intro section (U7)."""

from unittest.mock import patch

import pandas as pd
import pytest

from app.layout import _find_protagonists, _render_narrative, _fallback_narrative


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def narrative_scan_df():
    """Scan data with clear exemplars for each quadrant archetype."""
    rows = []
    # Star: high velocity, high distribution (15 stores, high units).
    for i in range(1, 16):
        rows.append({
            "sku": "STAR-001", "store_id": f"STR-{i:04d}",
            "week_ending": "2025-01-07", "units_sold": 200, "dollars_sold": 1000.0,
        })
    # Hidden gem: high velocity, low distribution (3 stores, high units per store).
    for i in range(1, 4):
        rows.append({
            "sku": "GEM-001", "store_id": f"STR-{i:04d}",
            "week_ending": "2025-01-07", "units_sold": 300, "dollars_sold": 1500.0,
        })
    # Wide but dead: low velocity, high distribution (18 stores, low units).
    for i in range(1, 19):
        rows.append({
            "sku": "WIDE-001", "store_id": f"STR-{i:04d}",
            "week_ending": "2025-01-07", "units_sold": 2, "dollars_sold": 10.0,
        })
    # Question mark: low velocity, low distribution (2 stores, low units).
    for i in range(1, 3):
        rows.append({
            "sku": "QMARK-001", "store_id": f"STR-{i:04d}",
            "week_ending": "2025-01-07", "units_sold": 1, "dollars_sold": 5.0,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def narrative_dist_df():
    """Distribution matching the scan data store counts."""
    rows = []
    for i in range(1, 16):
        rows.append({
            "sku": "STAR-001", "store_id": f"STR-{i:04d}", "retailer_id": "RET-001",
            "chain_name": "Walmart", "region": "Northeast", "state": "NY",
            "volume_tier": "A", "authorized_date": "2024-01-01",
            "deauthorized_date": None, "is_active": True, "weeks_with_sales": 10,
            "total_units": 2000, "total_dollars": 10000.0, "avg_weekly_units": 200,
            "first_scan_week": "2024-01-07", "last_scan_week": "2025-01-07",
        })
    for i in range(1, 4):
        rows.append({
            "sku": "GEM-001", "store_id": f"STR-{i:04d}", "retailer_id": "RET-001",
            "chain_name": "Walmart", "region": "Northeast", "state": "NY",
            "volume_tier": "A", "authorized_date": "2024-01-01",
            "deauthorized_date": None, "is_active": True, "weeks_with_sales": 10,
            "total_units": 3000, "total_dollars": 15000.0, "avg_weekly_units": 300,
            "first_scan_week": "2024-01-07", "last_scan_week": "2025-01-07",
        })
    for i in range(1, 19):
        rows.append({
            "sku": "WIDE-001", "store_id": f"STR-{i:04d}", "retailer_id": "RET-001",
            "chain_name": "Walmart", "region": "Northeast", "state": "NY",
            "volume_tier": "B", "authorized_date": "2024-01-01",
            "deauthorized_date": None, "is_active": True, "weeks_with_sales": 10,
            "total_units": 20, "total_dollars": 100.0, "avg_weekly_units": 2,
            "first_scan_week": "2024-01-07", "last_scan_week": "2025-01-07",
        })
    for i in range(1, 3):
        rows.append({
            "sku": "QMARK-001", "store_id": f"STR-{i:04d}", "retailer_id": "RET-001",
            "chain_name": "Walmart", "region": "Northeast", "state": "NY",
            "volume_tier": "C", "authorized_date": "2024-01-01",
            "deauthorized_date": None, "is_active": True, "weeks_with_sales": 10,
            "total_units": 10, "total_dollars": 50.0, "avg_weekly_units": 1,
            "first_scan_week": "2024-01-07", "last_scan_week": "2025-01-07",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def narrative_products_df():
    return pd.DataFrame([
        {"sku": "STAR-001", "product_name": "Classic Marinara", "product_line": "Artisan Sauces", "wholesale_price": 5.0},
        {"sku": "GEM-001", "product_name": "Truffle Aioli", "product_line": "Artisan Sauces", "wholesale_price": 8.0},
        {"sku": "WIDE-001", "product_name": "Plain Ketchup", "product_line": "Pantry Staples", "wholesale_price": 3.0},
        {"sku": "QMARK-001", "product_name": "Mango Chutney", "product_line": "Specialty", "wholesale_price": 6.0},
    ])


# ── Protagonist discovery ────────────────────────────────────────


class TestFindProtagonists:
    def test_finds_all_four_archetypes(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        assert "star" in protagonists
        assert "hidden_gem" in protagonists
        assert "wide_but_dead" in protagonists
        assert "question_mark" in protagonists

    def test_includes_migration_story(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        assert "migration" in protagonists

    def test_protagonist_has_product_name(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        for key, p in protagonists.items():
            assert "product_name" in p
            assert len(p["product_name"]) > 0

    def test_empty_data_returns_empty(self, sample_stores_df, narrative_products_df):
        result = _find_protagonists(
            pd.DataFrame(), pd.DataFrame(), sample_stores_df, narrative_products_df
        )
        assert result == {}


# ── Narrative rendering ──────────────────────────────────────────


class TestRenderNarrative:
    def test_renders_all_archetypes(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        result = _render_narrative(protagonists)
        text = _extract_text(result)
        assert "star" in text.lower() or "Classic Marinara" in text
        assert "hidden gem" in text.lower() or "Truffle Aioli" in text
        assert "Wide but dead" in text or "Plain Ketchup" in text
        assert "question mark" in text.lower() or "Mango Chutney" in text
        assert "migration" in text.lower() or "Movement" in text

    def test_narrative_uses_business_language(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        """Narrative avoids raw jargon on first use."""
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        result = _render_narrative(protagonists)
        text = _extract_text(result)
        # "units per store per day" explains SPPD in context.
        assert "units per store per day" in text

    def test_narrative_ends_with_transition(
        self, narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
    ):
        protagonists = _find_protagonists(
            narrative_scan_df, narrative_dist_df, sample_stores_df, narrative_products_df
        )
        result = _render_narrative(protagonists)
        text = _extract_text(result)
        assert "Explore the full dataset below" in text

    def test_fallback_when_no_protagonists(self):
        result = _render_narrative({})
        text = _extract_text(result)
        assert "shelf space" in text.lower()

    def test_fallback_narrative_has_transition(self):
        result = _fallback_narrative()
        text = _extract_text(result)
        assert "Explore the full dataset below" in text


# ── Helpers ──────────────────────────────────────────────────────


def _extract_text(component):
    """Recursively extract all text from a Dash component tree."""
    parts = []
    if isinstance(component, str):
        return component
    children = getattr(component, "children", None)
    if isinstance(children, str):
        parts.append(children)
    elif isinstance(children, list):
        for child in children:
            parts.append(_extract_text(child))
    elif children is not None:
        parts.append(_extract_text(children))
    return " ".join(parts)
