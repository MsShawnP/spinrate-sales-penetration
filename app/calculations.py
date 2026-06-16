"""Pure calculation functions for Spin Rate metrics.

Every function takes DataFrames (or scalars) and returns DataFrames or
scalars.  No database access -- all data is passed in by the caller.
Follows doormath's pattern: DataFrame in, scalar/DataFrame out.
"""

import numpy as np
import pandas as pd

from app.constants import QUADRANT_LABELS


def classify_quadrant(sppd, acv_pct, median_sppd, median_acv):
    """Assign quadrant label based on position relative to medians."""
    if sppd >= median_sppd and acv_pct >= median_acv:
        return QUADRANT_LABELS["star"]
    elif sppd >= median_sppd and acv_pct < median_acv:
        return QUADRANT_LABELS["hidden_gem"]
    elif sppd < median_sppd and acv_pct >= median_acv:
        return QUADRANT_LABELS["wide_but_dead"]
    else:
        return QUADRANT_LABELS["question_mark"]


# Volume tier weights used for ACV% calculation.
VOLUME_TIER_WEIGHTS = {"A": 3, "B": 2, "C": 1}

# Velocity trend thresholds (slope of quarterly SPPD as fraction of mean).
# Rising: slope > +5% of mean; Declining: slope < -5% of mean; else Flat.
_TREND_THRESHOLD = 0.05


# ── SPPD ────────────────────────────────────────────────────────────

def calculate_sppd(scan_df, days_in_period):
    """Calculate Sales Per Point of Distribution (SPPD) per SKU.

    SPPD = Total Units / Carrying Stores / Days in Period

    Parameters
    ----------
    scan_df : DataFrame
        Must contain columns: sku, store_id, units_sold.
        Should be pre-filtered to the desired date range.
    days_in_period : int
        Number of days in the analysis period (e.g. 91 for one quarter).

    Returns
    -------
    DataFrame with columns: sku, total_units, door_count, sppd.
    """
    if scan_df.empty or days_in_period <= 0:
        return pd.DataFrame(columns=["sku", "total_units", "door_count", "sppd"])

    agg = scan_df.groupby("sku").agg(
        total_units=("units_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()

    # Exclude SKUs with 0 doors (shouldn't happen but defensive).
    agg = agg[agg["door_count"] > 0].copy()
    agg["sppd"] = agg["total_units"] / agg["door_count"] / days_in_period

    return agg


# ── ACV% ────────────────────────────────────────────────────────────

def calculate_acv_pct(dist_df, stores_df):
    """Calculate weighted ACV% per SKU.

    ACV% = sum(carrying store weights) / sum(all addressable store weights)
    Weights: volume tier A=3, B=2, C=1.

    Parameters
    ----------
    dist_df : DataFrame
        Active distribution rows.  Must contain: sku, store_id.
    stores_df : DataFrame
        Full store dimension.  Must contain: store_id, volume_tier.

    Returns
    -------
    DataFrame with columns: sku, carrying_weight, total_weight, acv_pct.
    """
    if dist_df.empty or stores_df.empty:
        return pd.DataFrame(columns=["sku", "carrying_weight", "total_weight", "acv_pct"])

    stores = stores_df[["store_id", "volume_tier"]].copy()
    stores["weight"] = stores["volume_tier"].map(VOLUME_TIER_WEIGHTS).fillna(1)
    total_weight = stores["weight"].sum()

    if total_weight == 0:
        return pd.DataFrame(columns=["sku", "carrying_weight", "total_weight", "acv_pct"])

    carrying = dist_df[["sku", "store_id"]].drop_duplicates().merge(
        stores[["store_id", "weight"]], on="store_id", how="left"
    )
    carrying["weight"] = carrying["weight"].fillna(1)

    per_sku = carrying.groupby("sku")["weight"].sum().reset_index()
    per_sku.columns = ["sku", "carrying_weight"]
    per_sku["total_weight"] = total_weight
    per_sku["acv_pct"] = per_sku["carrying_weight"] / total_weight

    return per_sku


# ── Indexed SPPD ────────────────────────────────────────────────────

def calculate_indexed_sppd(sppd_df, benchmarks_df, products_df):
    """Calculate indexed SPPD: item SPPD / category median SPPD.

    Since dim_category_benchmarks only has avg_weekly_units_per_store
    (not a true SPPD median), we compute per-SKU medians from the sppd_df
    itself, grouped by product_line.

    Parameters
    ----------
    sppd_df : DataFrame
        Output of calculate_sppd().  Must contain: sku, sppd.
    benchmarks_df : DataFrame
        Category benchmarks.  Must contain: product_line,
        avg_weekly_units_per_store.
    products_df : DataFrame
        SKU -> product_line mapping.  Must contain: sku, product_line.

    Returns
    -------
    DataFrame with columns: sku, product_line, sppd, category_median_sppd,
    indexed_sppd.
    """
    if sppd_df.empty or products_df.empty:
        return pd.DataFrame(
            columns=["sku", "product_line", "sppd", "category_median_sppd", "indexed_sppd"]
        )

    merged = sppd_df[["sku", "sppd"]].merge(
        products_df[["sku", "product_line"]], on="sku", how="left"
    )

    # Compute category median SPPD from actual SKU-level data.
    medians = merged.groupby("product_line")["sppd"].median().reset_index()
    medians.columns = ["product_line", "category_median_sppd"]

    result = merged.merge(medians, on="product_line", how="left")

    # Guard against division by zero for categories with no median.
    result["indexed_sppd"] = np.where(
        result["category_median_sppd"] > 0,
        result["sppd"] / result["category_median_sppd"],
        np.nan,
    )

    return result[["sku", "product_line", "sppd", "category_median_sppd", "indexed_sppd"]]


# ── Velocity trend ──────────────────────────────────────────────────

def calculate_velocity_trend(scan_df, products_df, n_quarters=4):
    """Classify each SKU's velocity direction over trailing quarters.

    Fits a simple OLS slope to quarterly SPPD values.  Direction is
    determined by the slope relative to the mean:
        slope / mean > +5%  -> 'rising'
        slope / mean < -5%  -> 'declining'
        else                -> 'flat'

    Parameters
    ----------
    scan_df : DataFrame
        Must contain: sku, store_id, week_ending, units_sold.
    products_df : DataFrame
        Must contain: sku, product_line.
    n_quarters : int
        Number of trailing quarters to evaluate (default 4).

    Returns
    -------
    DataFrame with columns: sku, trend, slope, mean_sppd, quarters_with_data.
    """
    if scan_df.empty:
        return pd.DataFrame(
            columns=["sku", "trend", "slope", "mean_sppd", "quarters_with_data"]
        )

    df = scan_df.copy()

    # Assign quarter labels.
    df["week_ending"] = pd.to_datetime(df["week_ending"])
    df["quarter"] = df["week_ending"].dt.to_period("Q").astype(str)

    # Keep only the most recent n_quarters.
    all_quarters = sorted(df["quarter"].unique())
    recent_quarters = all_quarters[-n_quarters:] if len(all_quarters) > n_quarters else all_quarters

    df = df[df["quarter"].isin(recent_quarters)]

    # Compute SPPD per SKU per quarter.
    quarterly = df.groupby(["sku", "quarter"]).agg(
        total_units=("units_sold", "sum"),
        door_count=("store_id", "nunique"),
    ).reset_index()

    # Days per quarter approximation (91 days).
    quarterly["sppd"] = quarterly["total_units"] / quarterly["door_count"] / 91.0

    # Map quarters to numeric indices for slope calculation.
    quarter_order = {q: i for i, q in enumerate(recent_quarters)}
    quarterly["q_idx"] = quarterly["quarter"].map(quarter_order)

    results = []
    for sku, group in quarterly.groupby("sku"):
        if len(group) < 2:
            results.append({
                "sku": sku,
                "trend": "flat",
                "slope": 0.0,
                "mean_sppd": group["sppd"].mean(),
                "quarters_with_data": len(group),
            })
            continue

        x = group["q_idx"].values.astype(float)
        y = group["sppd"].values.astype(float)
        mean_sppd = y.mean()

        # Simple OLS slope: slope = cov(x,y) / var(x).
        slope = np.polyfit(x, y, 1)[0]

        if mean_sppd > 0:
            relative_slope = slope / mean_sppd
        else:
            relative_slope = 0.0

        if relative_slope > _TREND_THRESHOLD:
            trend = "rising"
        elif relative_slope < -_TREND_THRESHOLD:
            trend = "declining"
        else:
            trend = "flat"

        results.append({
            "sku": sku,
            "trend": trend,
            "slope": float(slope),
            "mean_sppd": float(mean_sppd),
            "quarters_with_data": len(group),
        })

    return pd.DataFrame(results)


# ── At-risk scoring ─────────────────────────────────────────────────

def calculate_at_risk_score(indexed_sppd_df, trend_df):
    """Assign at-risk tier based on indexed SPPD and velocity trend.

    Tiering logic:
        act_now              - indexed_sppd < 1.0 AND trend == 'declining'
        fix_or_rationalize   - indexed_sppd < 1.0 AND trend == 'flat'
        watchlist            - indexed_sppd >= 1.0 AND trend == 'declining'
        (no tier)            - indexed_sppd >= 1.0 AND trend != 'declining'

    Parameters
    ----------
    indexed_sppd_df : DataFrame
        Must contain: sku, indexed_sppd.
    trend_df : DataFrame
        Must contain: sku, trend.

    Returns
    -------
    DataFrame with columns: sku, indexed_sppd, trend, at_risk_tier.
    Only includes SKUs that received a tier (excludes healthy items).
    """
    if indexed_sppd_df.empty or trend_df.empty:
        return pd.DataFrame(columns=["sku", "indexed_sppd", "trend", "at_risk_tier"])

    merged = indexed_sppd_df[["sku", "indexed_sppd"]].merge(
        trend_df[["sku", "trend"]], on="sku", how="inner"
    )

    conditions = [
        (merged["indexed_sppd"] < 1.0) & (merged["trend"] == "declining"),
        (merged["indexed_sppd"] < 1.0) & (merged["trend"] == "flat"),
        (merged["indexed_sppd"] >= 1.0) & (merged["trend"] == "declining"),
    ]
    choices = ["act_now", "fix_or_rationalize", "watchlist"]

    merged["at_risk_tier"] = np.select(conditions, choices, default="")

    # Only return rows with a tier assignment.
    result = merged[merged["at_risk_tier"] != ""].copy()
    return result[["sku", "indexed_sppd", "trend", "at_risk_tier"]]


# ── Expansion upside ────────────────────────────────────────────────

def calculate_expansion_upside(sppd_df, dist_df, stores_df, products_df, benchmarks_df):
    """Project dollarized upside at three distribution benchmarks.

    For each SKU, projects incremental revenue if ACV% were raised to:
        1. Category median ACV%
        2. 75th percentile ACV% (computed from peer SKUs)
        3. Category leader ACV% (max among peers)

    Incremental units = (target_doors - current_doors) * current_sppd * 91
    Incremental dollars = incremental_units * wholesale_price

    Parameters
    ----------
    sppd_df : DataFrame
        Output of calculate_sppd().  Must contain: sku, door_count, sppd.
    dist_df : DataFrame
        Active distribution.  Must contain: sku, store_id.
    stores_df : DataFrame
        Store dimension.  Must contain: store_id, volume_tier.
    products_df : DataFrame
        Must contain: sku, product_line, wholesale_price.
    benchmarks_df : DataFrame
        Must contain: product_line.

    Returns
    -------
    DataFrame with columns: sku, product_line, current_doors, current_sppd,
    median_doors, p75_doors, leader_doors,
    upside_median_dollars, upside_p75_dollars, upside_leader_dollars.
    """
    if sppd_df.empty or dist_df.empty or stores_df.empty:
        return pd.DataFrame(columns=[
            "sku", "product_line", "current_doors", "current_sppd",
            "median_doors", "p75_doors", "leader_doors",
            "upside_median_dollars", "upside_p75_dollars", "upside_leader_dollars",
        ])

    total_stores = stores_df["store_id"].nunique()

    # Current door count per SKU.
    sku_doors = dist_df.groupby("sku")["store_id"].nunique().reset_index()
    sku_doors.columns = ["sku", "current_doors"]

    # Merge with product line info.
    base = sppd_df[["sku", "sppd"]].rename(columns={"sppd": "current_sppd"}).merge(
        sku_doors, on="sku", how="left"
    ).merge(
        products_df[["sku", "product_line", "wholesale_price"]], on="sku", how="left"
    )
    base["current_doors"] = base["current_doors"].fillna(0)

    # Compute door-count percentiles per product line from actual data.
    pl_stats = base.groupby("product_line")["current_doors"].agg(
        median_doors="median",
        p75_doors=lambda x: np.percentile(x, 75) if len(x) > 0 else 0,
        leader_doors="max",
    ).reset_index()

    result = base.merge(pl_stats, on="product_line", how="left")

    # Ensure target doors are at least current doors (no negative upside).
    for col in ["median_doors", "p75_doors", "leader_doors"]:
        result[col] = result[[col, "current_doors"]].max(axis=1)

    # Days in a quarter for projection.
    days = 91.0

    for target, label in [("median_doors", "median"), ("p75_doors", "p75"), ("leader_doors", "leader")]:
        incremental_doors = result[target] - result["current_doors"]
        incremental_units = incremental_doors * result["current_sppd"] * days
        result[f"upside_{label}_dollars"] = incremental_units * result["wholesale_price"].fillna(0)

    return result[[
        "sku", "product_line", "current_doors", "current_sppd",
        "median_doors", "p75_doors", "leader_doors",
        "upside_median_dollars", "upside_p75_dollars", "upside_leader_dollars",
    ]]


# ── Utility: days in period for quarter ranges ──────────────────────

def days_in_quarter_range(start_quarter, end_quarter):
    """Approximate the number of days in a quarter range.

    Each quarter is 91 days (13 weeks).  Returns total days for the
    inclusive range from start_quarter through end_quarter.
    Parses quarter strings directly — no hardcoded year list.
    """
    try:
        sq, sy = start_quarter.split()
        eq, ey = end_quarter.split()
        start_idx = int(sy) * 4 + int(sq[1])
        end_idx = int(ey) * 4 + int(eq[1])
    except (ValueError, IndexError):
        return 91

    n_quarters = max(end_idx - start_idx + 1, 1)
    return n_quarters * 91
