"""Shared test fixtures for Spin Rate.

Provides sample DataFrames matching the Cinderhaven SSOT schema so
tests run without a live Postgres connection.
"""

import os

# app.app requires these to be set before it's imported (fails closed if
# missing). Test-only values — set before any test module can import it
# transitively via app.views.*.
os.environ.setdefault("DASH_AUTH_USERNAME", "test")
os.environ.setdefault("DASH_AUTH_PASSWORD", "test")

import pandas as pd
import pytest


@pytest.fixture
def sample_scan_df():
    """POS scan data: 3 SKUs across stores over multiple weeks.

    Designed so CHP-AS-001 has 100 units across 10 stores.
    """
    rows = []
    # CHP-AS-001: 10 units/week across 10 stores for 13 weeks (Q1 2025).
    for store_num in range(1, 11):
        for week in range(1, 14):
            rows.append({
                "sku": "CHP-AS-001",
                "store_id": f"STR-{store_num:04d}",
                "week_ending": f"2025-{1 + (week - 1) // 4:02d}-{7 * ((week - 1) % 4) + 7:02d}",
                "units_sold": 10,
                "dollars_sold": 50.0,
            })
    # Manually correct: total for CHP-AS-001 should be 10 stores * 13 weeks * 10 units = 1300 units.
    # But test expects 100 units / 10 doors / 91 days, so let's make a simpler fixture.
    # Clear and rebuild with exact numbers for the key test case.
    rows = []

    # CHP-AS-001: exactly 100 units total, 10 unique stores, over a 91-day period.
    # 10 stores, 1 week each, 10 units per scan = 100 total units.
    for store_num in range(1, 11):
        rows.append({
            "sku": "CHP-AS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-01-07",
            "units_sold": 10,
            "dollars_sold": 50.0,
        })

    # CHP-AS-002: higher velocity -- 500 units across 5 stores.
    for store_num in range(1, 6):
        rows.append({
            "sku": "CHP-AS-002",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-01-07",
            "units_sold": 100,
            "dollars_sold": 500.0,
        })

    # CHP-PS-001: different product line -- 200 units across 20 stores.
    for store_num in range(1, 21):
        rows.append({
            "sku": "CHP-PS-001",
            "store_id": f"STR-{store_num:04d}",
            "week_ending": "2025-01-07",
            "units_sold": 10,
            "dollars_sold": 45.0,
        })

    return pd.DataFrame(rows)


@pytest.fixture
def sample_scan_agg_df(sample_scan_df):
    """Pre-aggregated scan data matching get_scan_data_agg() output."""
    agg = sample_scan_df.groupby("sku").agg(
        total_units=("units_sold", "sum"),
        total_dollars=("dollars_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()
    return agg


@pytest.fixture
def sample_scan_quarterly_df():
    """Scan data spanning 4 quarters for velocity trend testing.

    CHP-AS-001: rising -- units increase each quarter.
    CHP-AS-002: declining -- units decrease each quarter.
    CHP-PS-001: flat -- roughly constant.
    """
    rows = []
    quarters = [
        ("2025-01-15", "2025Q1"),
        ("2025-04-15", "2025Q2"),
        ("2025-07-15", "2025Q3"),
        ("2025-10-15", "2025Q4"),
    ]

    # CHP-AS-001: rising pattern (5 stores, increasing units).
    for qi, (date, _qlabel) in enumerate(quarters):
        units = 10 + qi * 5  # 10, 15, 20, 25
        for store_num in range(1, 6):
            rows.append({
                "sku": "CHP-AS-001",
                "store_id": f"STR-{store_num:04d}",
                "week_ending": date,
                "units_sold": units,
                "dollars_sold": units * 5.0,
            })

    # CHP-AS-002: declining pattern (5 stores, decreasing units).
    for qi, (date, _qlabel) in enumerate(quarters):
        units = 30 - qi * 8  # 30, 22, 14, 6
        for store_num in range(1, 6):
            rows.append({
                "sku": "CHP-AS-002",
                "store_id": f"STR-{store_num:04d}",
                "week_ending": date,
                "units_sold": units,
                "dollars_sold": units * 5.0,
            })

    # CHP-PS-001: flat pattern (5 stores, stable units).
    for qi, (date, _qlabel) in enumerate(quarters):
        units = 15  # constant
        for store_num in range(1, 6):
            rows.append({
                "sku": "CHP-PS-001",
                "store_id": f"STR-{store_num:04d}",
                "week_ending": date,
                "units_sold": units,
                "dollars_sold": units * 4.5,
            })

    return pd.DataFrame(rows)


@pytest.fixture
def sample_stores_df():
    """Store dimension with volume tier distribution.

    20 stores: 5 A-tier (weight 3), 10 B-tier (weight 2), 5 C-tier (weight 1).
    Total weight = 5*3 + 10*2 + 5*1 = 15 + 20 + 5 = 40.
    """
    rows = []
    for i in range(1, 6):
        rows.append({
            "store_id": f"STR-{i:04d}",
            "retailer": "Walmart",
            "region": "Northeast",
            "state": "NY",
            "volume_tier": "A",
        })
    for i in range(6, 16):
        rows.append({
            "store_id": f"STR-{i:04d}",
            "retailer": "Kroger",
            "region": "Midwest",
            "state": "OH",
            "volume_tier": "B",
        })
    for i in range(16, 21):
        rows.append({
            "store_id": f"STR-{i:04d}",
            "retailer": "Sprouts",
            "region": "West",
            "state": "CA",
            "volume_tier": "C",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_dist_df():
    """Active distribution data.

    CHP-AS-001: authorized in all 5 A-tier stores (STR-0001 to STR-0005).
    CHP-AS-002: authorized in 5 A-tier + 5 B-tier stores.
    CHP-PS-001: authorized in all 20 stores.
    """
    rows = []
    # CHP-AS-001: 5 A-tier stores only.
    for i in range(1, 6):
        rows.append({
            "sku": "CHP-AS-001",
            "store_id": f"STR-{i:04d}",
            "retailer_id": "RET-WALMART",
            "chain_name": "Walmart",
            "region": "Northeast",
            "state": "NY",
            "volume_tier": "A",
            "authorized_date": "2024-01-01",
            "deauthorized_date": None,
            "is_active": True,
            "weeks_with_sales": 52,
            "total_units": 1000,
            "total_dollars": 5000.0,
            "avg_weekly_units": 19.23,
            "first_scan_week": "2024-01-07",
            "last_scan_week": "2025-01-07",
        })
    # CHP-AS-002: 10 stores (5 A + 5 B).
    for i in range(1, 11):
        rows.append({
            "sku": "CHP-AS-002",
            "store_id": f"STR-{i:04d}",
            "retailer_id": "RET-WALMART" if i <= 5 else "RET-KROGER",
            "chain_name": "Walmart" if i <= 5 else "Kroger",
            "region": "Northeast" if i <= 5 else "Midwest",
            "state": "NY" if i <= 5 else "OH",
            "volume_tier": "A" if i <= 5 else "B",
            "authorized_date": "2024-01-01",
            "deauthorized_date": None,
            "is_active": True,
            "weeks_with_sales": 40,
            "total_units": 800,
            "total_dollars": 4000.0,
            "avg_weekly_units": 20.0,
            "first_scan_week": "2024-03-01",
            "last_scan_week": "2025-01-07",
        })
    # CHP-PS-001: all 20 stores.
    for i in range(1, 21):
        tier = "A" if i <= 5 else ("B" if i <= 15 else "C")
        retailer = "Walmart" if i <= 5 else ("Kroger" if i <= 15 else "Sprouts")
        rows.append({
            "sku": "CHP-PS-001",
            "store_id": f"STR-{i:04d}",
            "retailer_id": f"RET-{retailer.upper()}",
            "chain_name": retailer,
            "region": "Northeast" if i <= 5 else ("Midwest" if i <= 15 else "West"),
            "state": "NY" if i <= 5 else ("OH" if i <= 15 else "CA"),
            "volume_tier": tier,
            "authorized_date": "2024-01-01",
            "deauthorized_date": None,
            "is_active": True,
            "weeks_with_sales": 50,
            "total_units": 600,
            "total_dollars": 2700.0,
            "avg_weekly_units": 12.0,
            "first_scan_week": "2024-01-07",
            "last_scan_week": "2025-01-07",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_products_df():
    """Product dimension with SKU -> product_line mapping."""
    return pd.DataFrame([
        {"sku": "CHP-AS-001", "product_name": "Classic Marinara", "product_line": "Artisan Sauces", "wholesale_price": 5.00},
        {"sku": "CHP-AS-002", "product_name": "Spicy Arrabbiata", "product_line": "Artisan Sauces", "wholesale_price": 5.50},
        {"sku": "CHP-PS-001", "product_name": "Heritage Rice", "product_line": "Pantry Staples", "wholesale_price": 4.50},
    ])


@pytest.fixture
def sample_benchmarks_df():
    """Category benchmarks from dim_category_benchmarks."""
    return pd.DataFrame([
        {
            "product_line": "Artisan Sauces",
            "sku_count": 10,
            "store_count": 640,
            "avg_weekly_units_per_store": 15.0,
            "total_units": 50000,
            "total_dollars": 250000.0,
            "avg_cogs": 2.50,
            "avg_msrp": 6.99,
            "avg_margin_per_unit": 2.00,
            "avg_margin_pct": 0.35,
        },
        {
            "product_line": "Pantry Staples",
            "sku_count": 10,
            "store_count": 640,
            "avg_weekly_units_per_store": 12.0,
            "total_units": 40000,
            "total_dollars": 180000.0,
            "avg_cogs": 2.00,
            "avg_msrp": 5.49,
            "avg_margin_per_unit": 1.80,
            "avg_margin_pct": 0.33,
        },
    ])
