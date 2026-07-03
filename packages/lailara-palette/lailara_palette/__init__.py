"""Lailara Design System v2 — Python color constants.

Import individual tokens or full palettes:

    from lailara_palette import LL_CANVAS, LL_CHICAGO, LL_HK
    from lailara_palette import LL_CAT_10, LL_SEQ, LL_STATUS
"""

# ── Canvas ─────────────────────────────────────────────────
LL_CANVAS = "#f5f3ee"

# ── Brand red (default = 42) ──────────────────────────────
LL_RED = "#cc100a"
LL_RED_LIGHT = "#ee8880"
LL_RED_DARK = "#8e0b07"
LL_RED_SURFACE = "#fce8e7"

# ── Chicago accent blue (default = 20) ────────────────────
LL_CHICAGO = "#1f2e7a"
LL_CHICAGO_LIGHT = "#8e9ad0"
LL_CHICAGO_DARK = "#1f2e7a"
LL_CHICAGO_HOVER = "#141e52"
LL_CHICAGO_SURFACE = "#e8eaf4"

# ── Hong Kong teal (default = 35) ─────────────────────────
LL_HK = "#158f75"
LL_HK_LIGHT = "#6dcdb5"
LL_HK_DARK = "#0c6552"
LL_HK_SURFACE = "#e4f5f0"

# ── Tokyo berry (default = 40) ────────────────────────────
LL_TOKYO = "#b82d4a"
LL_TOKYO_LIGHT = "#e68a9a"
LL_TOKYO_DARK = "#7e1f34"
LL_TOKYO_SURFACE = "#fbe9ed"

# ── Singapore orange (default = 55) ───────────────────────
LL_SG = "#ee8a2a"
LL_SG_LIGHT = "#f6b97c"
LL_SG_DARK = "#7a3d10"
LL_SG_SURFACE = "#fdeee0"

# ── New York amber (reserve) ──────────────────────────────
LL_NY = "#f9c31f"
LL_NY_SURFACE = "#fef5d8"

# ── London greyscale ──────────────────────────────────────
LL_INK = "#0d0d0d"
LL_TEXT = "#333333"
LL_TEXT_SEC = "#595959"
LL_REFERENCE = "#666666"
LL_DISABLED = "#b3b3b3"
LL_GRIDLINE = "#d9d9d9"
LL_SEPARATOR = "#e0e0e0"
LL_SURFACE = "#f2f2f2"

# ── Dark card tokens ──────────────────────────────────────
LL_CARD_BG = "#1a1a1a"
LL_CARD_TEXT = "#ffffff"
LL_CARD_SUBTITLE = "#d8d8d8"
LL_CARD_MUTED = "#9a9a9a"
LL_CARD_BORDER = "rgba(255,255,255,0.12)"
LL_CARD_ITEM = "#ededed"

# ── Categorical chart palette (10 slots, paired) ──────────
LL_CAT_10 = [
    "#1f2e7a",
    "#8e9ad0",
    "#0c6552",
    "#6dcdb5",
    "#7e1f34",
    "#e68a9a",
    "#7a3d10",
    "#f6b97c",
    "#8e0b07",
    "#ee8880",
]

# ── Sequential palettes (steps 5-85, darkest first) ───────
LL_SEQ = [
    "#063d32",
    "#0a5c4b",
    "#0e6e5a",
    "#158f75",
    "#1fa282",
    "#35b595",
    "#6dcdb5",
    "#b5e4d8",
]

LL_SEQ_CHICAGO = [
    "#0a0f29",
    "#141e52",
    "#1f2e7a",
    "#3348a8",
    "#475ed1",
    "#6474c0",
    "#8e9ad0",
    "#c5cbe6",
]

LL_SEQ_TOKYO = [
    "#470f1c",
    "#6e1a2c",
    "#7e1f34",
    "#94243c",
    "#b82d4a",
    "#cc3a59",
    "#e68a9a",
    "#f3c1cb",
]

LL_SEQ_SINGAPORE = [
    "#4a2508",
    "#7a3d10",
    "#a05a1a",
    "#c87222",
    "#ee8a2a",
    "#f4a85c",
    "#f6b97c",
    "#fbdabc",
]

LL_SEQ_RED = [
    "#4d0604",
    "#7a0906",
    "#8e0b07",
    "#a80d08",
    "#cc100a",
    "#db2418",
    "#e8625d",
    "#f4b3b1",
]

# ── Divergent palette (HK pos -> London neutral -> Tokyo neg)
LL_DIV_POS = ["#0a5c4b", "#158f75", "#6dcdb5"]
LL_DIV_NEU = "#d9d9d9"
LL_DIV_NEG = ["#e68a9a", "#b82d4a", "#6e1a2c"]

# ── Typography ─────────────────────────────────────────────
LL_SERIF = "Playfair Display"
LL_SANS = "Source Sans 3"

# ── Semantic status colors (for conditional formatting) ───
LL_STATUS = {
    "pass": {"fill": LL_HK_SURFACE, "text": "#0e6e5a"},
    "warn": {"fill": LL_SG_SURFACE, "text": "#7a3d10"},
    "fail": {"fill": LL_RED_SURFACE, "text": "#7a0906"},
    "info": {"fill": LL_CHICAGO_SURFACE, "text": "#1f2e7a"},
    "neutral": {"fill": LL_SURFACE, "text": LL_TEXT_SEC},
}
