"""Guards against color drift from the Lailara design-system palette package.

app/constants.py sources every color from lailara_palette; assets/lailara-frame.css
copies the same values by hand (CSS can't import a Python package). These tests
catch both: a hardcoded hex creeping back into constants.py, or the CSS file
drifting from the values it's supposed to mirror.
"""

import re
from pathlib import Path

import lailara_palette as llp

from app import constants


CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "lailara-frame.css"
APP_DIR = Path(__file__).resolve().parent.parent / "app"

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")

# Matches a triple-quoted string body (handles both `"""` and `'''`).  This
# is how AG Grid `cellStyle` clientside functions embed their JS source
# (app/views/at_risk.py) and how the branded loading overlay embeds raw CSS
# (app/app.py) -- neither can reference Python color constants, so any hex
# literal inside has to be checked against the palette directly.
_TRIPLE_QUOTED_RE = re.compile(r"(\"\"\"|''')(.*?)\1", re.DOTALL)

# Matches `style={...}` / `"style": {...}` / `"cellStyle": {...}` dict
# literals, up to one level of brace nesting -- enough for a plain Dash
# style dict or an AG Grid column's cellStyle mapping.
_STYLE_DICT_RE = re.compile(r"(?:style|cellStyle)\s*[:=]\s*(\{(?:[^{}]|\{[^{}]*\})*\})")

# constants.py is covered by TestPythonConstantsMatchPalettePackage above,
# which checks its re-exported names against lailara_palette by identity
# rather than by re-deriving a hex allowlist -- a stricter check than hex
# membership alone. Excluding it here avoids double-guarding the same file
# with a weaker rule.
_EXCLUDED_FILENAMES = {"constants.py"}


def _parse_css_custom_properties(path):
    """Parse `--ll-*: #hex;` declarations into {name: hex}."""
    text = path.read_text(encoding="utf-8")
    return dict(re.findall(r"(--ll-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", text))


def _known_palette_hexes():
    """Every hex literal lailara_palette actually defines.

    Walks all public module attributes, including nested lists/dicts (e.g.
    LL_CAT_10, LL_SEQ, LL_STATUS), so a value like Red-18 (#7a0906) -- which
    only appears inside LL_STATUS/LL_SEQ_RED rather than as its own
    top-level name -- still counts as a legitimate palette color.
    """
    hexes = set()

    def _collect(value):
        if isinstance(value, str):
            if _HEX_RE.fullmatch(value):
                hexes.add(value.lower())
        elif isinstance(value, (list, tuple)):
            for item in value:
                _collect(item)
        elif isinstance(value, dict):
            for item in value.values():
                _collect(item)

    for name in dir(llp):
        if not name.startswith("_"):
            _collect(getattr(llp, name))

    return hexes


def _inline_style_hexes(path):
    """Hex literals found in style-related spans of one Python file."""
    text = path.read_text(encoding="utf-8")
    spans = [m.group(2) for m in _TRIPLE_QUOTED_RE.finditer(text)]
    spans += [m.group(1) for m in _STYLE_DICT_RE.finditer(text)]

    hexes = set()
    for span in spans:
        hexes.update(m.group(0).lower() for m in _HEX_RE.finditer(span))
    return hexes


class TestPythonConstantsMatchPalettePackage:
    """app/constants.py re-exports must equal the package's canonical values.

    Locks in the current import-based sourcing so a future edit can't
    silently swap one of these back to a hardcoded literal.
    """

    def test_canvas_and_greyscale(self):
        assert constants.CANVAS == llp.LL_CANVAS
        assert constants.TEXT_PRIMARY == llp.LL_TEXT
        assert constants.TEXT_SECONDARY == llp.LL_TEXT_SEC
        assert constants.GRIDLINE == llp.LL_GRIDLINE
        assert constants.REFERENCE == llp.LL_REFERENCE
        assert constants.DISABLED == llp.LL_DISABLED
        assert constants.INK == llp.LL_INK

    def test_chicago(self):
        assert constants.CHICAGO_20 == llp.LL_CHICAGO
        assert constants.CHICAGO_10 == llp.LL_CHICAGO_HOVER
        assert constants.CHICAGO_70 == llp.LL_CHICAGO_LIGHT

    def test_hong_kong_sequential(self):
        assert constants.TEAL_SEQUENTIAL == list(llp.LL_SEQ)
        assert constants.HK_35 == llp.LL_HK
        assert constants.HK_70 == llp.LL_HK_LIGHT

    def test_tokyo_and_singapore(self):
        assert constants.TOKYO_40 == llp.LL_TOKYO
        assert constants.TOKYO_70 == llp.LL_TOKYO_LIGHT
        assert constants.SG_55 == llp.LL_SG
        assert constants.SG_70 == llp.LL_SG_LIGHT

    def test_semantic_status_colors(self):
        assert constants.PASS_BG == llp.LL_STATUS["pass"]["fill"]
        assert constants.WARN_BG == llp.LL_STATUS["warn"]["fill"]
        assert constants.FAIL_BG == llp.LL_STATUS["fail"]["fill"]
        assert constants.INFO_BG == llp.LL_STATUS["info"]["fill"]

    def test_categorical_palette_slots_are_from_ll_cat_10(self):
        """PRODUCT_LINE_COLORS is a deliberate subset (no Red/Tokyo, see
        DECISIONS.md) but every hex it uses must still be an actual
        LL_CAT_10 slot value, not an invented color."""
        for hex_value in constants.PRODUCT_LINE_COLORS:
            assert hex_value in llp.LL_CAT_10, (
                f"{hex_value} is not one of the spec's LL_CAT_10 slots"
            )

    def test_typography(self):
        assert constants.FONT_SERIF.startswith(llp.LL_SERIF)
        assert constants.FONT_SANS.startswith(llp.LL_SANS)


class TestCssCustomPropertiesMatchPalettePackage:
    """assets/lailara-frame.css hand-copies palette hex values -- verify the
    ones this app actually renders with haven't drifted."""

    def test_css_file_parses(self):
        css_vars = _parse_css_custom_properties(CSS_PATH)
        assert len(css_vars) > 50, "Expected the full family ramps in lailara-frame.css"

    def test_canvas_and_greyscale_match(self):
        css_vars = _parse_css_custom_properties(CSS_PATH)
        assert css_vars["--ll-canvas"] == llp.LL_CANVAS
        assert css_vars["--ll-london-85"] == llp.LL_GRIDLINE
        assert css_vars["--ll-london-70"] == llp.LL_DISABLED
        assert css_vars["--ll-london-40"] == llp.LL_REFERENCE
        assert css_vars["--ll-london-35"] == llp.LL_TEXT_SEC
        assert css_vars["--ll-london-20"] == llp.LL_TEXT
        assert css_vars["--ll-london-5"] == llp.LL_INK

    def test_default_accent_steps_match(self):
        css_vars = _parse_css_custom_properties(CSS_PATH)
        assert css_vars["--ll-chicago-20"] == llp.LL_CHICAGO
        assert css_vars["--ll-hk-35"] == llp.LL_HK
        assert css_vars["--ll-tokyo-40"] == llp.LL_TOKYO
        assert css_vars["--ll-sg-55"] == llp.LL_SG
        assert css_vars["--ll-ny-55"] == llp.LL_NY
        assert css_vars["--ll-red-42"] == llp.LL_RED

    def test_card_tokens_match(self):
        css_vars = _parse_css_custom_properties(CSS_PATH)
        assert css_vars["--ll-card-bg"] == llp.LL_CARD_BG
        assert css_vars["--ll-card-text"] == llp.LL_CARD_TEXT


class TestNoHardcodedHexDriftInPythonStyles:
    """Guards against a third drift vector: literal hex colors typed inline
    in Dash `style=` dicts or AG Grid `cellStyle` blocks (including the
    clientside JS strings cellStyle embeds), rather than referencing
    app/constants.py.

    Clientside cellStyle functions are plain JS source in a Python string --
    they can't import a Python name, so a literal hex is unavoidable there.
    But every literal found must still equal a real lailara_palette value,
    not a typo or invented color. This is exactly how #fde8e7 (a
    transposed-digit near-miss of Red-95, #fce8e7) shipped in the at-risk
    grid's cellStyle undetected: constants.py sources FAIL_BG from the
    package correctly, but the hardcoded JS copy of that same color drifted
    and nothing was checking it.
    """

    def test_python_style_hex_literals_match_palette(self):
        known = _known_palette_hexes()
        violations = []
        for path in sorted(APP_DIR.rglob("*.py")):
            if path.name in _EXCLUDED_FILENAMES:
                continue
            bad = _inline_style_hexes(path) - known
            if bad:
                rel = path.relative_to(APP_DIR.parent)
                violations.append(f"{rel}: {sorted(bad)}")

        assert not violations, (
            "Hardcoded hex color(s) in Python style/cellStyle blocks don't "
            "match any lailara_palette value -- fix the typo, or if this is "
            "an intentional new color, add it to lailara_palette first:\n"
            + "\n".join(violations)
        )
