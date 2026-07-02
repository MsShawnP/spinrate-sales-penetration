"""Tests for shared reusable Dash components — app/components.py."""

from dash import html

from app.components import hero_card
from app.constants import INK


def _collect_text(component):
    """Recursively collect all string children from a Dash component tree."""
    texts = []
    children = getattr(component, "children", None)
    if isinstance(children, str):
        texts.append(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            texts.extend(_collect_text(child))
    elif children is not None:
        texts.extend(_collect_text(children))
    return texts


class TestHeroCard:
    """Shared hero-card component — used by Expansion (upside) and
    At-Risk (tier counts)."""

    def test_renders_value_and_label(self):
        card = hero_card("$1,234", "Median benchmark")
        assert isinstance(card, html.Div)
        texts = _collect_text(card)
        assert "$1,234" in texts
        assert "Median benchmark" in texts

    def test_no_accent_has_no_top_border(self):
        card = hero_card("42", "Act Now")
        assert "borderTop" not in card.style

    def test_accent_sets_top_border_color(self):
        card = hero_card("42", "Act Now", accent="#b82d4a")
        assert card.style["borderTop"] == "3px solid #b82d4a"

    def test_value_color_is_ink_regardless_of_accent(self):
        """The accent colors the border stripe, not the headline number --
        the value text stays a neutral ink color for legibility."""
        card = hero_card("42", "Act Now", accent="#b82d4a")
        value_span = card.children[0]
        assert value_span.style["color"] == INK
