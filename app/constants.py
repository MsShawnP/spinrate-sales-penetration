"""Lailara design-system tokens and format helpers for Plotly/Dash charts.

All color values are sourced from the lailara-palette package (the single source
of truth). Spinrate re-exports them under short semantic aliases that the rest
of the app imports.
"""

import math

from lailara_palette import (
    LL_CANVAS,
    LL_CARD_BG,
    LL_CARD_BORDER,
    LL_CARD_ITEM,
    LL_CARD_MUTED,
    LL_CARD_SUBTITLE,
    LL_CARD_TEXT,
    LL_CAT_10,
    LL_CHICAGO,
    LL_CHICAGO_HOVER,
    LL_CHICAGO_LIGHT,
    LL_DISABLED,
    LL_GRIDLINE,
    LL_HK,
    LL_HK_LIGHT,
    LL_HK_SURFACE,
    LL_INK,
    LL_NY,
    LL_NY_SURFACE,
    LL_RED,
    LL_REFERENCE,
    LL_SANS,
    LL_SEQ,
    LL_SERIF,
    LL_SG,
    LL_SG_DARK,
    LL_SG_LIGHT,
    LL_SG_SURFACE,
    LL_STATUS,
    LL_TEXT,
    LL_TEXT_SEC,
    LL_TOKYO,
    LL_TOKYO_DARK,
    LL_TOKYO_LIGHT,
    LL_TOKYO_SURFACE,
)

# ── Canvas & London greyscale ──
WHITE = "#ffffff"
CANVAS = LL_CANVAS
TEXT_PRIMARY = LL_TEXT
TEXT_SECONDARY = LL_TEXT_SEC
GRIDLINE = LL_GRIDLINE
REFERENCE = LL_REFERENCE
DISABLED = LL_DISABLED
INK = LL_INK

# ── Chicago (accent blue) ──
CHICAGO_20 = LL_CHICAGO
CHICAGO_10 = LL_CHICAGO_HOVER
CHICAGO_70 = LL_CHICAGO_LIGHT

# ── Brand red ──
RED_42 = LL_RED

# ── Hong Kong sequential teal ──
HK_5 = LL_SEQ[0]
HK_15 = LL_SEQ[1]
HK_25 = LL_SEQ[2]
HK_35 = LL_HK
HK_45 = LL_SEQ[4]
HK_55 = LL_SEQ[5]
HK_70 = LL_HK_LIGHT
HK_85 = LL_SEQ[7]
HK_95 = LL_HK_SURFACE

# ── Singapore (orange) ──
SG_20 = LL_SG_DARK
SG_55 = LL_SG
SG_70 = LL_SG_LIGHT
SG_95 = LL_SG_SURFACE

# ── Tokyo (berry/rose) ──
TOKYO_20 = LL_TOKYO_DARK
TOKYO_40 = LL_TOKYO
TOKYO_70 = LL_TOKYO_LIGHT
TOKYO_95 = LL_TOKYO_SURFACE

# ── New York (amber) ──
NY_35 = "#a88312"
NY_55 = LL_NY
NY_95 = LL_NY_SURFACE

# ── Dark card tokens ──
CARD_BG = LL_CARD_BG
CARD_TEXT = LL_CARD_TEXT
CARD_SUBTITLE = LL_CARD_SUBTITLE
CARD_MUTED = LL_CARD_MUTED
CARD_BORDER = LL_CARD_BORDER
CARD_ITEM = LL_CARD_ITEM

# ── Semantic status ──
PASS_BG = LL_STATUS["pass"]["fill"]
PASS_TEXT = LL_STATUS["pass"]["text"]
WARN_BG = LL_STATUS["warn"]["fill"]
WARN_TEXT = LL_STATUS["warn"]["text"]
FAIL_BG = LL_STATUS["fail"]["fill"]
FAIL_TEXT = LL_STATUS["fail"]["text"]
INFO_BG = LL_STATUS["info"]["fill"]
INFO_TEXT = LL_STATUS["info"]["text"]

# ── Semantic aliases for charts ──
TREND_UP = HK_35
TREND_DOWN = TOKYO_40
MIGRATION_FAVORABLE = HK_35
MIGRATION_UNFAVORABLE = TOKYO_40

# ── Teal sequential palette (for charts) ──
TEAL_SEQUENTIAL = list(LL_SEQ)

# ── Categorical palette for product lines ──
# Spec's LL_CAT_10 paired categorical slots, taken in documented order
# (Chicago-20/70, HK-20/70, Tokyo-20/70, ...) -- "always in order, never
# skip a slot." Product lines are non-ranked categories, not a magnitude
# ramp, so they get the paired categorical palette, not TEAL_SEQUENTIAL.
PRODUCT_LINE_COLORS = list(LL_CAT_10[:5])

# ── Typography (for Plotly) ──
FONT_SERIF = f"{LL_SERIF}, Georgia, Times New Roman, serif"
FONT_SANS = f"{LL_SANS}, Source Sans Pro, Helvetica Neue, Helvetica, Arial, sans-serif"

# ── Quadrant labels ──
QUADRANT_LABELS = {
    "star": "Stars",
    "hidden_gem": "Hidden Gems",
    "wide_but_dead": "Wide but Dead",
    "question_mark": "Question Marks",
}

# ── SPPD formula (for display in UI per R10) ──
SPPD_FORMULA = "SPPD = Total Units ÷ Carrying Stores ÷ Days in Period"


# ── Format helpers ──
def _is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def fmt_pct(value, decimals=1):
    """Format a decimal as percentage string."""
    if _is_missing(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def fmt_delta(value, decimals=1):
    """Format a percentage point delta with direction arrow."""
    if _is_missing(value):
        return "N/A"
    arrow = "↑" if value > 0 else "↓" if value < 0 else "→"
    return f"{arrow} {abs(value * 100):.{decimals}f} pp"


def fmt_number(value):
    """Format large numbers with commas."""
    if _is_missing(value):
        return "N/A"
    return f"{value:,.0f}"


def fmt_dollars(value):
    """Format dollar amounts with K/M suffixes."""
    if _is_missing(value):
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"
