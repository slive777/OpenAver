"""Fluent Material System static guards — feature/77.

CI-effective protection: CI runs pytest only (not stylelint).
These pytest guards are the load-bearing backstop for CSS correctness.
Reference: reference_ci_no_eslint memory note.

All tests are pure static analysis (pathlib + re). No app needed.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FLUENT_CSS = REPO_ROOT / "web" / "static" / "css" / "components" / "fluent-materials.css"
BASE_HTML  = REPO_ROOT / "web" / "templates" / "base.html"
THEME_CSS  = REPO_ROOT / "web" / "static" / "css" / "theme.css"


def _strip_css_comments(text: str) -> str:
    """Remove /* … */ block comments (possibly multi-line)."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def _parse_rule_blocks(css_text: str):
    """
    Yield (selector_text, declarations_text) pairs by splitting on '}' boundaries.

    Handles nested @media blocks by returning the innermost rule blocks.
    Each yielded tuple:
      selector_text — everything before the matching '{'
      declarations_text — the content between '{' and '}'
    """
    # We walk character-by-character to track brace depth, so we can handle
    # @media wrappers without recursion.
    blocks = []
    depth = 0
    start = 0
    i = 0
    text = css_text
    while i < len(text):
        ch = text[i]
        if ch == "{":
            if depth == 0:
                selector = text[start:i].strip()
                block_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                declarations = text[block_start:i]
                blocks.append((selector, declarations))
                start = i + 1
        i += 1
    return blocks


class TestFluentMaterialsGuards:
    """Static CSS/HTML guards for the Fluent Material System (feature/77)."""

    # ─── helpers ─────────────────────────────────────────────────────────────

    def _css(self) -> str:
        return FLUENT_CSS.read_text(encoding="utf-8")

    def _html(self) -> str:
        return BASE_HTML.read_text(encoding="utf-8")

    def _theme_css(self) -> str:
        return THEME_CSS.read_text(encoding="utf-8")

    # ─── Guard 1 ─────────────────────────────────────────────────────────────

    def test_load_order(self):
        """fluent-materials.css <link> must appear AFTER {% block extra_css %} and after theme.css.

        Protects CD-A2: source-order override contract. If fluent-materials.css is loaded
        before extra_css expansion, page-specific CSS (e.g. design-system.css) would win
        same-specificity ties and break the Fluent surface overrides.
        """
        html_lines = self._html().splitlines()

        fluent_idx = None
        extra_css_idx = None
        theme_idx = None

        for i, line in enumerate(html_lines):
            if "fluent-materials.css" in line and "<link" in line:
                fluent_idx = i
            if "{% block extra_css %}" in line:
                extra_css_idx = i
            if 'href="/static/css/theme.css"' in line and "<link" in line:
                theme_idx = i

        assert fluent_idx is not None, "base.html: <link> for fluent-materials.css not found"
        assert extra_css_idx is not None, "base.html: {% block extra_css %} not found"
        assert theme_idx is not None, "base.html: <link> for theme.css not found"

        assert fluent_idx > extra_css_idx, (
            f"fluent-materials.css link (line {fluent_idx}) must come AFTER "
            f"{{% block extra_css %}} (line {extra_css_idx})"
        )
        assert fluent_idx > theme_idx, (
            f"fluent-materials.css link (line {fluent_idx}) must come AFTER "
            f"theme.css link (line {theme_idx})"
        )

    # ─── Guard 2 ─────────────────────────────────────────────────────────────

    def test_all_backdrop_filter_dim_scoped(self):
        """Every backdrop-filter: declaration must be inside a [data-theme="dim"]-scoped selector.

        CI-backstop for a stylelint-class rule (CI runs pytest only; reference_ci_no_eslint)
        — keep even though it asserts CSS strings (documented exception to CLAUDE.md lint routing).

        Protects IACVT iron rule: unscoped backdrop-filter in light mode causes the property
        to revert to initial (backdrop-filter: none), silently removing glass effects.
        The rule .page-search #main-content:has(.showcase-lightbox.show) has no backdrop-filter
        and is intentionally not dim-scoped — it's excluded by the backdrop-filter check itself.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        violations = []
        for selector, declarations in blocks:
            # Only check non-webkit lines so we don't double-count
            has_backdrop = bool(re.search(r"(?<!-webkit-)backdrop-filter\s*:", declarations))
            if not has_backdrop:
                continue
            # The selector may be prefixed by an @media line; strip it.
            # We need the actual CSS selector (the innermost one).
            # _parse_rule_blocks at depth==0 returns @media blocks as a single entry;
            # since we recurse implicitly via our walker, @media bodies are also blocks.
            # Strip any @media(...) prefix from selector:
            clean_selector = re.sub(r"@media\s*\([^)]*\)\s*", "", selector).strip()
            if '[data-theme="dim"]' not in clean_selector:
                violations.append(
                    f"  selector={selector!r} contains backdrop-filter but is not dim-scoped"
                )

        assert not violations, (
            "fluent-materials.css: backdrop-filter found outside [data-theme=\"dim\"] scope:\n"
            + "\n".join(violations)
        )

    # ─── Guard 3 ─────────────────────────────────────────────────────────────

    def test_no_hardcoded_blur_literal(self):
        """No literal blur(<digit>) values allowed — must use blur(var(--fluent-blur...)).

        CI-backstop for a stylelint-class rule (CI runs pytest only; reference_ci_no_eslint)
        — keep even though it asserts CSS strings (documented exception to CLAUDE.md lint routing).

        Protects the token system: hardcoded px values bypass the --fluent-blur* tokens and
        prevent uniform tuning across all glass surfaces.
        """
        css_no_comments = _strip_css_comments(self._css())
        # Match blur( optionally preceded by whitespace, then a digit or leading decimal
        match = re.search(r"blur\(\s*\.?\d", css_no_comments)
        assert match is None, (
            f"fluent-materials.css: hardcoded blur literal found: "
            f"{match.group()!r} at position {match.start()}. "
            "Use blur(var(--fluent-blur...)) instead."
        )

    # ─── Guard 4 ─────────────────────────────────────────────────────────────

    def test_webkit_backdrop_filter_pairing(self):
        """-webkit-backdrop-filter must immediately follow each backdrop-filter (same value).

        CI-backstop for a stylelint-class rule (CI runs pytest only; reference_ci_no_eslint)
        — keep even though it asserts CSS strings (documented exception to CLAUDE.md lint routing).

        Protects macOS WKWebView / PyWebView compat: without -webkit- prefix, backdrop-filter
        is silently ignored on macOS builds.
        """
        css = _strip_css_comments(self._css())
        lines = css.splitlines()

        unpaired = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Match non-webkit backdrop-filter declarations
            m = re.match(r"(?<!-webkit-)backdrop-filter\s*:\s*(.+)", line)
            if m and not line.startswith("-webkit-"):
                value = m.group(1).rstrip(";").strip()
                # Find next non-blank line
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j < len(lines):
                    next_line = lines[j].strip()
                    webkit_m = re.match(r"-webkit-backdrop-filter\s*:\s*(.+)", next_line)
                    if webkit_m:
                        webkit_value = webkit_m.group(1).rstrip(";").strip()
                        if value != webkit_value:
                            unpaired.append(
                                f"  Line {i+1}: backdrop-filter: {value!r} "
                                f"but -webkit- has: {webkit_value!r}"
                            )
                    else:
                        unpaired.append(
                            f"  Line {i+1}: backdrop-filter: {value!r} "
                            f"not followed by -webkit-backdrop-filter (got: {next_line!r})"
                        )
            i += 1

        assert not unpaired, (
            "fluent-materials.css: backdrop-filter/-webkit-backdrop-filter pairing failures:\n"
            + "\n".join(unpaired)
        )

    # ─── Guard 5 ─────────────────────────────────────────────────────────────

    def test_caption_footer_no_backdrop_filter(self):
        """av-card-preview-footer rule blocks must NOT contain backdrop-filter.

        Protects 90-card performance constraint (spec §7.4 #3 / plan-77b CD-B1):
        adding backdrop-filter to 90 card footers simultaneously would trigger mass
        GPU compositing cost. The comment-comment in fluent-materials.css is explicit:
        'No backdrop-filter on caption (90-card perf)'.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        violations = []
        for selector, declarations in blocks:
            if ".av-card-preview-footer" in selector:
                if re.search(r"backdrop-filter\s*:", declarations):
                    violations.append(
                        f"  selector={selector!r} contains backdrop-filter "
                        "(forbidden — 90-card perf)"
                    )

        assert not violations, (
            "fluent-materials.css: .av-card-preview-footer must not have backdrop-filter:\n"
            + "\n".join(violations)
        )

    # ─── Guard 6 ─────────────────────────────────────────────────────────────

    def test_lightbox_metadata_hairline(self):
        """[data-theme="dim"] .lightbox-metadata must set background: transparent.

        Protects the 'no card-in-card' design principle (CD-B5 / Rule 36): the metadata
        section is a hairline divider within the lightbox glass shell — giving it an
        opaque/gradient background would create an inner card visual, violating the
        Fluent overlay hierarchy.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        found = False
        for selector, declarations in blocks:
            if ".lightbox-metadata" in selector and '[data-theme="dim"]' in selector:
                found = True
                assert re.search(r"background\s*:\s*transparent", declarations), (
                    f"[data-theme=\"dim\"] .lightbox-metadata must set "
                    f"background: transparent (got block: {declarations[:200]!r})"
                )

        assert found, (
            "fluent-materials.css: [data-theme=\"dim\"] .lightbox-metadata rule not found"
        )

    # ─── Guard 7 ─────────────────────────────────────────────────────────────

    def test_modal_box_not_solid(self):
        """[data-theme="dim"] .fluent-modal-box must use overlay glass, not a solid surface token.

        Protects CD-B7 (Rule 38): the modal box uses --glass-overlay-modal-fill (high-opacity
        translucent) or a gradient, NOT a solid var(--surface-2) which would break the Fluent
        overlay glass appearance and ignore the blur/glass-border treatment.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        found = False
        for selector, declarations in blocks:
            if ".fluent-modal-box" in selector and '[data-theme="dim"]' in selector:
                found = True
                # Must use --glass-overlay-modal-fill or a gradient (border-box technique)
                has_overlay = bool(
                    re.search(r"--glass-overlay-modal-fill", declarations)
                    or re.search(r"--glass-overlay-fill-gradient", declarations)
                    or re.search(r"border-box", declarations)
                )
                assert has_overlay, (
                    f"[data-theme=\"dim\"] .fluent-modal-box must reference "
                    f"--glass-overlay-modal-fill or use border-box gradient technique "
                    f"(block: {declarations[:300]!r})"
                )
                # Must NOT set background: var(--surface-2) (solid)
                assert not re.search(r"background\s*:\s*var\(--surface-2\)", declarations), (
                    f"[data-theme=\"dim\"] .fluent-modal-box must NOT set "
                    f"background: var(--surface-2) (solid surface breaks overlay glass)"
                )

        assert found, (
            "fluent-materials.css: [data-theme=\"dim\"] .fluent-modal-box rule not found"
        )

    # ─── Guard 8 ─────────────────────────────────────────────────────────────

    def test_similar_main_static_no_transition_transform(self):
        """[data-theme="dim"] .similar-main-static must NOT contain transition referencing transform.

        Protects C21 GSAP guard (plan-77b CD-B9 / B-T3 comment): slot hover scale is managed
        by GSAP exclusively. A CSS transition: transform would conflict with GSAP's transform
        ownership and cause jank/fighting on similar-slot hover.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        for selector, declarations in blocks:
            if ".similar-main-static" in selector and '[data-theme="dim"]' in selector:
                # Check for any transition declaration that mentions transform
                transition_matches = re.findall(
                    r"transition\s*:[^;]+", declarations
                )
                for t in transition_matches:
                    assert "transform" not in t, (
                        f"[data-theme=\"dim\"] .similar-main-static must NOT reference "
                        f"'transform' in a transition declaration (C21 GSAP guard): {t!r}"
                    )

    # ─── Guard 9 ─────────────────────────────────────────────────────────────

    def test_gsap_animating_guard_exists_in_theme_css(self):
        """theme.css must contain .av-card-preview.gsap-animating { transition: none !important }.

        Protects B-T1 pre-flight contract: GSAP card entrance animation requires CSS transitions
        to be suppressed during animation to prevent the CSS hover transition from fighting
        the GSAP-driven transform. If this rule is removed, cards stutter during grid entrance.
        """
        theme = self._theme_css()
        assert ".av-card-preview.gsap-animating" in theme, (
            "theme.css: .av-card-preview.gsap-animating rule not found "
            "(B-T1 GSAP pre-flight contract)"
        )
        # Find the block
        blocks = _parse_rule_blocks(_strip_css_comments(theme))
        found = False
        for selector, declarations in blocks:
            if ".av-card-preview.gsap-animating" in selector:
                found = True
                assert re.search(r"transition\s*:\s*none\s*!important", declarations), (
                    f".av-card-preview.gsap-animating block must contain "
                    f"'transition: none !important' (block: {declarations!r})"
                )
        assert found, (
            "theme.css: .av-card-preview.gsap-animating rule block not found"
        )

    # ─── Guard 10 ────────────────────────────────────────────────────────────

    def test_77c_search_bar_float_dim_desktop(self):
        """fluent-materials.css: [data-theme="dim"] .search-bar inside @media (min-width:1024px) must set border-radius + border + margin.

        Protects CD-C1 (Rule 45, 77c-T1): the search bar gets B floating treatment only on
        desktop (≥1024px), leaving mobile as a full-width A shelf. This gate ensures the
        search bar doesn't accidentally float on narrow viewports (feature/75 compat).
        """
        css_raw = self._css()

        # Extract content of each @media (min-width: 1024px) block
        media_blocks = re.findall(
            r"@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:/\*|@|[\[\.\#a-zA-Z]|$))",
            css_raw,
        )

        dim_search_bar_blocks = []
        for mb in media_blocks:
            # Find [data-theme="dim"] .search-bar rules inside
            inner_blocks = _parse_rule_blocks(mb)
            for sel, decls in inner_blocks:
                if '[data-theme="dim"]' in sel and ".search-bar" in sel:
                    dim_search_bar_blocks.append((sel, decls))

        assert dim_search_bar_blocks, (
            "fluent-materials.css: no [data-theme=\"dim\"] .search-bar rule found "
            "inside @media (min-width: 1024px) — CD-C1 (Rule 45) missing"
        )

        for sel, decls in dim_search_bar_blocks:
            assert re.search(r"border-radius\s*:", decls), (
                f"[data-theme=\"dim\"] .search-bar @media 1024px block missing border-radius"
            )
            assert re.search(r"\bborder\s*:", decls), (
                f"[data-theme=\"dim\"] .search-bar @media 1024px block missing border"
            )
            assert re.search(r"\bmargin\s*:", decls), (
                f"[data-theme=\"dim\"] .search-bar @media 1024px block missing margin"
            )

    # ─── Guard 11 ────────────────────────────────────────────────────────────

    def test_77c_headers_float_dim_desktop(self):
        """:is(.settings-header, .avlist-header) rules: padding at all widths + radius/border at ≥1024px, dim-scoped.

        Protects CD-C2 (Rules 46/47, 77c-T2): the header flush-left fix (padding: 1rem 1.5rem)
        applies universally; the B floating treatment (border-radius + 4-side border) is
        desktop-gated. Both rules must be dim-scoped.
        """
        css_raw = self._css()
        css_no_comments = _strip_css_comments(css_raw)

        # Guard 11a: all-widths padding rule
        all_blocks = _parse_rule_blocks(css_no_comments)
        padding_found = False
        for sel, decls in all_blocks:
            if (
                '[data-theme="dim"]' in sel
                and ".settings-header" in sel
                and ".avlist-header" in sel
            ):
                if re.search(r"padding\s*:", decls):
                    padding_found = True
                    assert re.search(r"padding\s*:\s*1rem\s+1\.5rem", decls), (
                        f"[data-theme=\"dim\"] :is(.settings-header, .avlist-header) "
                        f"padding should be '1rem 1.5rem' (flush-left fix CD-C2)"
                    )

        assert padding_found, (
            "fluent-materials.css: [data-theme=\"dim\"] :is(.settings-header, .avlist-header) "
            "all-widths padding rule not found (Rule 46 / CD-C2)"
        )

        # Guard 11b: desktop-gated floating rule
        media_blocks = re.findall(
            r"@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:/\*|@|[\[\.\#a-zA-Z]|$))",
            css_raw,
        )

        desktop_header_blocks = []
        for mb in media_blocks:
            inner_blocks = _parse_rule_blocks(mb)
            for sel, decls in inner_blocks:
                if (
                    '[data-theme="dim"]' in sel
                    and ".settings-header" in sel
                    and ".avlist-header" in sel
                ):
                    desktop_header_blocks.append((sel, decls))

        assert desktop_header_blocks, (
            "fluent-materials.css: no [data-theme=\"dim\"] :is(.settings-header, .avlist-header) "
            "rule inside @media (min-width: 1024px) — Rule 47 / CD-C2 missing"
        )

        for sel, decls in desktop_header_blocks:
            assert re.search(r"border-radius\s*:", decls), (
                f"[data-theme=\"dim\"] :is(.settings-header, .avlist-header) "
                f"@media 1024px block missing border-radius"
            )
            assert re.search(r"\bborder\s*:", decls), (
                f"[data-theme=\"dim\"] :is(.settings-header, .avlist-header) "
                f"@media 1024px block missing border"
            )

    # ─── Guard 12 ────────────────────────────────────────────────────────────

    def test_77c_t3_vt_name_regression_anchor(self):
        """fluent-materials.css must contain .page-search #main-content:has(.showcase-lightbox.show) setting view-transition-name: none.

        Regression anchor for 77c-T3: this rule releases #main-content's backdrop root
        while the search lightbox is open, fixing the per-card blur bug (covers blurring
        individually instead of the uniform lightbox scrim blur). If deleted, the bug returns.
        Rule is intentionally NOT dim-scoped (it's a rendering fix for both themes).
        """
        css = self._css()
        assert ".page-search #main-content:has(.showcase-lightbox.show)" in css, (
            "fluent-materials.css: regression anchor rule "
            "'.page-search #main-content:has(.showcase-lightbox.show)' not found. "
            "77c-T3 per-card blur bug will return if this rule is absent."
        )

        # Verify the rule sets view-transition-name: none
        css_no_comments = _strip_css_comments(css)
        blocks = _parse_rule_blocks(css_no_comments)
        found_block = False
        for selector, declarations in blocks:
            if (
                ".page-search" in selector
                and "#main-content" in selector
                and ".showcase-lightbox" in selector
            ):
                found_block = True
                assert re.search(r"view-transition-name\s*:\s*none", declarations), (
                    f"regression anchor rule must set view-transition-name: none "
                    f"(block: {declarations!r})"
                )

        assert found_block, (
            "fluent-materials.css: regression anchor rule block not found after parsing "
            "(selector present but block is empty or malformed?)"
        )
