"""Lailara design-system tokens and format helpers for Plotly/Dash charts."""

# ── Canvas & London greyscale ──
WHITE = "#ffffff"
CANVAS = "#f5f3ee"
TEXT_PRIMARY = "#333333"
TEXT_SECONDARY = "#595959"
GRIDLINE = "#d9d9d9"
REFERENCE = "#666666"
DISABLED = "#b3b3b3"
INK = "#0d0d0d"

# ── Chicago (accent blue) ──
CHICAGO_20 = "#1f2e7a"
CHICAGO_10 = "#141e52"
CHICAGO_70 = "#8e9ad0"

# ── Brand red ──
RED_42 = "#cc100a"

# ── Hong Kong sequential teal ──
HK_5 = "#063d32"
HK_15 = "#0a5c4b"
HK_25 = "#0e6e5a"
HK_35 = "#158f75"
HK_45 = "#1fa282"
HK_55 = "#35b595"
HK_70 = "#6dcdb5"
HK_85 = "#b5e4d8"
HK_95 = "#e4f5f0"

# ── Singapore (orange) ──
SG_20 = "#7a3d10"
SG_55 = "#ee8a2a"
SG_70 = "#f6b97c"
SG_95 = "#fdeee0"

# ── Tokyo (berry/rose) ──
TOKYO_20 = "#7e1f34"
TOKYO_40 = "#b82d4a"
TOKYO_70 = "#e68a9a"
TOKYO_95 = "#fbe9ed"

# ── New York (amber) ──
NY_35 = "#a88312"
NY_55 = "#f9c31f"
NY_95 = "#fef5d8"

# ── Dark card tokens ──
CARD_BG = "#1a1a1a"
CARD_TEXT = "#ffffff"
CARD_SUBTITLE = "#d8d8d8"
CARD_MUTED = "#9a9a9a"
CARD_BORDER = "rgba(255, 255, 255, 0.12)"
CARD_ITEM = "#ededed"

# ── Semantic status ──
PASS_BG = "#e4f5f0"
PASS_TEXT = "#0e6e5a"
WARN_BG = "#fdeee0"
WARN_TEXT = "#7a3d10"
FAIL_BG = "#fde8e7"
FAIL_TEXT = "#7a0906"
INFO_BG = "#e5e8f5"
INFO_TEXT = "#1f2e7a"

# ── Semantic aliases for charts ──
TREND_UP = HK_35
TREND_DOWN = TOKYO_40
MIGRATION_FAVORABLE = HK_35
MIGRATION_UNFAVORABLE = TOKYO_40

# ── Teal sequential palette (for charts) ──
TEAL_SEQUENTIAL = [HK_5, HK_15, HK_25, HK_35, HK_45, HK_55, HK_70, HK_85]

# ── Typography (for Plotly) ──
FONT_SERIF = "Playfair Display, Georgia, Times New Roman, serif"
FONT_SANS = "Source Sans 3, Source Sans Pro, Helvetica Neue, Helvetica, Arial, sans-serif"

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
def fmt_pct(value, decimals=1):
    """Format a decimal as percentage string."""
    return f"{value * 100:.{decimals}f}%"


def fmt_delta(value, decimals=1):
    """Format a percentage point delta with direction arrow."""
    arrow = "↑" if value > 0 else "↓" if value < 0 else "→"
    return f"{arrow} {abs(value * 100):.{decimals}f} pp"


def fmt_number(value):
    """Format large numbers with commas."""
    return f"{value:,.0f}"


def fmt_dollars(value):
    """Format dollar amounts with K/M suffixes."""
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"
