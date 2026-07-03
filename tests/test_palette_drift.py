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


def _parse_css_custom_properties(path):
    """Parse `--ll-*: #hex;` declarations into {name: hex}."""
    text = path.read_text(encoding="utf-8")
    return dict(re.findall(r"(--ll-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", text))


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
