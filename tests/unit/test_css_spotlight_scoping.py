"""
Guard: spotlight-search CSS scoping (44c-T8c)

Reads showcase.css as text and asserts:
1.  The scoped rule '.showcase-toolbar .spotlight-search input' exists.
2.  The bare unscoped override '.spotlight-search input { padding-left: 5.5rem }'
    does NOT exist (outside a more-specific selector context).

Rationale: search.html loads showcase.css, so a bare override would bleed into
the /search page and push input text right with no mode-toggle present.
"""
import re
from pathlib import Path

SHOWCASE_CSS = Path(__file__).parents[2] / "web/static/css/pages/showcase.css"


def _css_text() -> str:
    return SHOWCASE_CSS.read_text(encoding="utf-8")


def test_mode_toggle_variant_class_exists():
    """.spotlight-search--mode-toggle variant with --spotlight-left-slot must exist."""
    css = _css_text()
    assert re.search(
        r"\.spotlight-search--mode-toggle\s*\{[^}]*--spotlight-left-slot",
        css,
    ), (
        "Expected '.spotlight-search--mode-toggle { --spotlight-left-slot: ... }' "
        "in showcase.css but it was not found."
    )


def test_bare_spotlight_input_padding_override_absent():
    """Bare '.spotlight-search input { padding-left: 5.5rem }' must NOT exist in showcase.css."""
    css = _css_text()
    bare_pattern = re.compile(
        r"(?:^|\n)\s*\.spotlight-search\s+input\s*\{[^}]*padding-left\s*:\s*5\.5rem",
    )
    matches = bare_pattern.findall(css)
    assert not matches, (
        "Found bare '.spotlight-search input { padding-left: 5.5rem }' in showcase.css. "
        "This leaks into /search page. Use variant class instead."
    )


def test_spotlight_width_token_in_theme_css():
    """':root { --spotlight-width: 680px }' must exist in theme.css (T8a)."""
    theme_css = Path(__file__).parents[2] / "web/static/css/theme.css"
    css = theme_css.read_text(encoding="utf-8")
    assert "--spotlight-width" in css, (
        "CSS custom property '--spotlight-width' not found in theme.css. "
        "Add ':root { --spotlight-width: 680px }' as required by T8a."
    )


def test_showcase_toolbar_uses_grid():
    """showcase-toolbar must use CSS grid for centered search slot (T8b)."""
    css = _css_text()
    assert "display: grid" in css and "grid-template-columns" in css, (
        "showcase-toolbar must use CSS grid layout for centered search slot."
    )
