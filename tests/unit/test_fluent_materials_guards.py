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
THEME_CSS  = REPO_ROOT / "web" / "static" / "css" / "theme.css"
RESCRAPE_CSS = REPO_ROOT / "web" / "static" / "css" / "components" / "rescrape-modal.css"


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

    def _theme_css(self) -> str:
        return THEME_CSS.read_text(encoding="utf-8")

    # ─── Guard 2 (77d-T3: role-split) ────────────────────────────────────────

    # The chrome top-bar SHELL rules are theme-agnostic from 77d-T2 (glass material in both
    # dim and light), so they are legitimately NOT dim-scoped. Their light token values are
    # guarded by test_light_shell_tokens_complete (IACVT completeness).
    UNSCOPED_SHELL_TOPBARS = (
        ".search-bar",
        ".settings-header",
        ".avlist-header",
        ".showcase-toolbar",
    )

    def test_non_shell_backdrop_filter_dim_scoped(self):
        """Every backdrop-filter must be dim-scoped EXCEPT the 77d theme-agnostic chrome top-bars.

        CI-backstop for a stylelint-class rule (CI runs pytest only; reference_ci_no_eslint)
        — keep even though it asserts CSS strings (documented exception to CLAUDE.md lint routing).

        Role split (plan-77d CD-D2): the 4 chrome top-bar shell rules (.search-bar /
        .settings-header / .avlist-header / .showcase-toolbar) are intentionally unscoped in
        77d-T2 — they consume shell tokens that have BOTH dim and light values
        (test_light_shell_tokens_complete guards completeness, preventing IACVT). EVERY OTHER
        backdrop-filter (panel / overlay / sidebar / offcanvas / top-navbar / footer) must stay
        [data-theme="dim"]-scoped: those roles have dim-only tokens (S-2), so an unscoped
        reference in light would IACVT to backdrop-filter: none, silently removing the glass.
        The .page-search #main-content:has(.showcase-lightbox.show) rule has no backdrop-filter
        and is excluded by the backdrop-filter check itself. An explicit `backdrop-filter: none`
        value is also excluded: it is a literal (not a dim-only token reference) so it cannot
        IACVT-fail — it removes glass deliberately in both themes (plan-81c T6 mobile sheet).
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        violations = []
        for selector, declarations in blocks:
            # Only check non-webkit lines so we don't double-count
            bf_values = re.findall(r"(?<!-webkit-)backdrop-filter\s*:\s*([^;}]+)", declarations)
            if not bf_values:
                continue
            # Explicit `backdrop-filter: none` cannot IACVT-fail: it is a literal value (not a
            # dim-only token reference), so it resolves to `none` in BOTH themes — it IS the
            # outcome this guard fears (glass removed), applied deliberately. e.g. plan-81c T6
            # mobile sheet G2 fix removes glass on the full-bleed notification drawer. Skip ONLY
            # when EVERY backdrop-filter in the block is `none` — a real value alongside a `none`
            # still trips the guard (declaration-precise, not block-scoped short-circuit).
            if all(re.sub(r"!important", "", v).strip() == "none" for v in bf_values):
                continue
            # The selector may be prefixed by an @media line; strip it to the inner selector.
            clean_selector = re.sub(r"@media\s*\([^)]*\)\s*", "", selector).strip()
            if '[data-theme="dim"]' in clean_selector:
                continue
            # Not dim-scoped — allowed only for the 77d theme-agnostic chrome top-bars.
            if any(cls in clean_selector for cls in self.UNSCOPED_SHELL_TOPBARS):
                continue
            violations.append(
                f"  selector={selector!r} contains backdrop-filter but is neither "
                "dim-scoped nor a 77d theme-agnostic chrome top-bar"
            )

        assert not violations, (
            "fluent-materials.css: backdrop-filter outside [data-theme=\"dim\"] scope "
            "(and not a whitelisted 77d chrome top-bar):\n" + "\n".join(violations)
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

    # ─── Guard 10 (77d-T3: theme-agnostic) ───────────────────────────────────

    def test_77d_search_bar_float_theme_agnostic(self):
        """.search-bar float (@media ≥1024px) sets border-radius + border + margin and is THEME-AGNOSTIC.

        Protects CD-D1 (Rule 45, 77d-T1): the search-bar B floating geometry was unscoped from
        [data-theme="dim"] so light gets the same shape as dim. Assert the desktop rule exists,
        sets radius/border/margin, and its selector does NOT contain [data-theme="dim"]. The
        @media (min-width:1024px) gate still keeps mobile as a full-width shelf (feature/75 compat).
        """
        css_raw = self._css()

        # Extract content of each @media (min-width: 1024px) block
        media_blocks = re.findall(
            r"@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:/\*|@|[\[\.\#a-zA-Z]|$))",
            css_raw,
        )

        search_bar_blocks = []
        for mb in media_blocks:
            for sel, decls in _parse_rule_blocks(mb):
                if ".search-bar" in sel:
                    search_bar_blocks.append((sel, decls))

        assert search_bar_blocks, (
            "fluent-materials.css: no .search-bar rule found inside "
            "@media (min-width: 1024px) — CD-D1 (Rule 45) missing"
        )

        for sel, decls in search_bar_blocks:
            assert '[data-theme="dim"]' not in sel, (
                f".search-bar @media 1024px float rule must be theme-agnostic "
                f"(no [data-theme=\"dim\"]) after 77d-T1: {sel!r}"
            )
            assert re.search(r"border-radius\s*:", decls), (
                ".search-bar @media 1024px block missing border-radius"
            )
            assert re.search(r"\bborder\s*:", decls), (
                ".search-bar @media 1024px block missing border"
            )
            assert re.search(r"\bmargin\s*:", decls), (
                ".search-bar @media 1024px block missing margin"
            )

    # ─── Guard 11 (77d-T3: theme-agnostic) ────────────────────────────────────

    def test_77d_headers_float_theme_agnostic(self):
        """:is(.settings-header, .avlist-header): padding (all widths) + float (@media) THEME-AGNOSTIC.

        Protects CD-D1 (Rules 46/47, 77d-T1): the header flush-left fix (padding: 1rem 1.5rem,
        all widths) and the desktop B floating treatment (border-radius + 4-side border) were
        unscoped from [data-theme="dim"] so light headers match dim. Assert both rules exist,
        set the right declarations, and are NOT dim-scoped.
        """
        css_raw = self._css()
        css_no_comments = _strip_css_comments(css_raw)

        # Guard 11a: all-widths padding rule (theme-agnostic — selector has no @media prefix)
        all_blocks = _parse_rule_blocks(css_no_comments)
        padding_found = False
        for sel, decls in all_blocks:
            if (
                ".settings-header" in sel
                and ".avlist-header" in sel
                and "@media" not in sel
            ):
                if re.search(r"padding\s*:", decls):
                    padding_found = True
                    assert '[data-theme="dim"]' not in sel, (
                        f":is(.settings-header, .avlist-header) padding rule must be "
                        f"theme-agnostic (no [data-theme=\"dim\"]) after 77d-T1: {sel!r}"
                    )
                    assert re.search(r"padding\s*:\s*1rem\s+1\.5rem", decls), (
                        ":is(.settings-header, .avlist-header) padding should be "
                        "'1rem 1.5rem' (flush-left fix CD-C2)"
                    )

        assert padding_found, (
            "fluent-materials.css: :is(.settings-header, .avlist-header) "
            "all-widths padding rule not found (Rule 46)"
        )

        # Guard 11b: desktop-gated floating rule (theme-agnostic)
        media_blocks = re.findall(
            r"@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:/\*|@|[\[\.\#a-zA-Z]|$))",
            css_raw,
        )

        desktop_header_blocks = []
        for mb in media_blocks:
            for sel, decls in _parse_rule_blocks(mb):
                if ".settings-header" in sel and ".avlist-header" in sel:
                    desktop_header_blocks.append((sel, decls))

        assert desktop_header_blocks, (
            "fluent-materials.css: no :is(.settings-header, .avlist-header) "
            "rule inside @media (min-width: 1024px) — Rule 47 missing"
        )

        for sel, decls in desktop_header_blocks:
            assert '[data-theme="dim"]' not in sel, (
                f":is(.settings-header, .avlist-header) @media float rule must be "
                f"theme-agnostic (no [data-theme=\"dim\"]) after 77d-T1: {sel!r}"
            )
            assert re.search(r"border-radius\s*:", decls), (
                ":is(.settings-header, .avlist-header) @media 1024px block missing border-radius"
            )
            assert re.search(r"\bborder\s*:", decls), (
                ":is(.settings-header, .avlist-header) @media 1024px block missing border"
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

    # ─── Guard 13 (77d-T3: IACVT completeness) ────────────────────────────────

    # The 6 shell tokens consumed by the unscoped chrome top-bars (Rule 10/11/12/13a material
    # + Rule 45/47 border). Each must exist in BOTH theme token blocks (dim + light).
    SHELL_TOKENS = (
        "--glass-shell-gradient",
        "--glass-shell-fill",
        "--glass-shell-saturate",
        "--glass-shell-edge-top",
        "--glass-shell-edge-bottom",
        "--glass-shell-border",
    )

    def test_light_shell_tokens_complete(self):
        """Every shell token consumed by the unscoped chrome top-bars must be defined in BOTH
        the [data-theme="dim"] AND the [data-theme="light"] token block.

        Protects CD-D2(a) IACVT completeness: 77d-T2 unscoped the shell application rules
        (.search-bar / .settings-header / .avlist-header / .showcase-toolbar) so they run in
        light too. If any consumed shell token lacks a light value, var(--glass-shell-*) in
        light reverts to initial → the glass background disappears. Fails closed if a future
        edit unscopes a shell rule (or adds a shell token) without a matching light value.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        dim_decls = None
        light_decls = None
        for selector, declarations in blocks:
            sel = selector.strip()
            if sel == '[data-theme="dim"]':
                dim_decls = declarations
            elif sel == '[data-theme="light"]':
                light_decls = declarations

        assert dim_decls is not None, (
            "fluent-materials.css: [data-theme=\"dim\"] token block not found"
        )
        assert light_decls is not None, (
            "fluent-materials.css: [data-theme=\"light\"] token block not found — "
            "77d-T2 light shell tokens missing → light chrome top-bars would IACVT"
        )

        missing_dim = [
            t for t in self.SHELL_TOKENS
            if not re.search(re.escape(t) + r"\s*:", dim_decls)
        ]
        missing_light = [
            t for t in self.SHELL_TOKENS
            if not re.search(re.escape(t) + r"\s*:", light_decls)
        ]

        assert not missing_dim, (
            f"[data-theme=\"dim\"] token block missing shell token(s): {missing_dim}"
        )
        assert not missing_light, (
            f"[data-theme=\"light\"] token block missing shell token(s): {missing_light} "
            "(IACVT risk — CD-D2(a): each unscoped shell rule needs a light value)"
        )

    # ─── Guard 14 (77d-T3: S-2 role boundary) ─────────────────────────────────

    # One representative application-rule marker per non-shell role. These four roles keep
    # dim-only tokens (S-2); their application rules must stay dim-scoped. Caption and
    # media-frame carry no backdrop-filter, so test_non_shell_backdrop_filter_dim_scoped
    # cannot catch them — this guard covers all four via markers.
    NON_SHELL_ROLE_MARKERS = {
        "panel": ".help-card",
        "caption": ".av-card-preview-footer",
        "overlay": ".lightbox-content",
        "media-frame": ".similar-slot",
    }

    def test_non_shell_roles_stay_dim_scoped(self):
        """Panel / caption / overlay / media-frame application rules must stay [data-theme="dim"].

        Protects S-2 / CD-D2(b): 77d only unscopes the SHELL role (chrome top-bars). The other
        four material roles keep dim-only tokens, so their application rules must remain
        dim-scoped — unscoping one without light tokens would IACVT the glass away in light.
        """
        css = _strip_css_comments(self._css())
        blocks = _parse_rule_blocks(css)

        violations = []
        for role, marker in self.NON_SHELL_ROLE_MARKERS.items():
            matched = [(sel, decls) for sel, decls in blocks if marker in sel]
            assert matched, (
                f"fluent-materials.css: {role} marker {marker!r} not found "
                "(selector renamed? update NON_SHELL_ROLE_MARKERS)"
            )
            for sel, _decls in matched:
                clean = re.sub(r"@media\s*\([^)]*\)\s*", "", sel).strip()
                if '[data-theme="dim"]' not in clean:
                    violations.append(
                        f"  {role} rule {sel!r} (marker {marker}) is not dim-scoped — "
                        "S-2 violation (non-shell roles must stay dim-only)"
                    )

        assert not violations, (
            "fluent-materials.css: non-shell role rule unscoped from dim (S-2 / CD-D2(b)):\n"
            + "\n".join(violations)
        )

    # ─── Guard (81c-T6: US-12 notification drawer mobile sheet) ──────────────

    def test_notification_drawer_mobile_sheet(self):
        """≤480px .notification-drawer must become a solid full-width fixed sheet (G2 fix).

        Protects 81c-T6 / US-12: below 480px the bell drawer is overridden from the
        x-anchor 320px glass card into a navbar-bottom full-width fixed sheet with a
        SOLID fill and NO backdrop-filter — rooting out the position:fixed ×
        view-transition-name 逐格模糊 bug (G2). The five positioning props must each
        carry !important (x-anchor writes left/top inline + Tailwind w-80 width, only
        !important overrides). Background must be the solid var(--surface-2) token
        (no hardcoded color), and backdrop-filter must be none (+ -webkit-).
        """
        css = _strip_css_comments(self._css())

        # Locate the @media (max-width:480px){ … } block (tolerate spacing variants),
        # then verify it contains the .notification-drawer rule and its declarations.
        m = re.search(
            r"@media\s*\(\s*max-width\s*:\s*480px\s*\)\s*\{",
            css,
        )
        assert m is not None, (
            "fluent-materials.css: no @media (max-width:480px) block found "
            "(81c-T6 mobile sheet missing)"
        )

        # Walk brace depth from the opening { of the @media block to find its end.
        start = m.end() - 1  # position of '{'
        depth = 0
        end = None
        for i in range(start, len(css)):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        assert end is not None, "fluent-materials.css: unbalanced @media (max-width:480px) block"
        media_body = css[m.end():end]

        assert ".notification-drawer" in media_body, (
            "fluent-materials.css: @media (max-width:480px) must contain a "
            ".notification-drawer rule (81c-T6 mobile sheet)"
        )

        # Isolate the .notification-drawer declarations within the media body.
        dm = re.search(
            r"\.notification-drawer\s*\{([^}]*)\}",
            media_body,
        )
        assert dm is not None, (
            "fluent-materials.css: .notification-drawer rule not parseable inside "
            "@media (max-width:480px)"
        )
        decls = dm.group(1)

        # Five positioning props, each with !important.
        for prop in ("position", "left", "right", "top", "width"):
            assert re.search(
                rf"\b{prop}\s*:[^;]*!important", decls
            ), (
                f"fluent-materials.css: mobile .notification-drawer must set "
                f"{prop} with !important (x-anchor inline / Tailwind w-80 override)"
            )

        # Solid token background with !important (beats dim Rule 42 glass).
        assert re.search(
            r"background\s*:\s*var\(--surface-2\)[^;]*!important", decls
        ), (
            "fluent-materials.css: mobile .notification-drawer must set "
            "background: var(--surface-2) !important (solid fill, G2)"
        )

        # No hardcoded color literals in the mobile drawer rule (token-only).
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", decls), (
            "fluent-materials.css: mobile .notification-drawer must not use a hex "
            "color literal (token-only — ui-conventions §6)"
        )
        assert "rgb(" not in decls and "rgba(" not in decls, (
            "fluent-materials.css: mobile .notification-drawer must not use rgb()/rgba() "
            "(token-only — ui-conventions §6)"
        )

        # backdrop-filter removed (both standard + -webkit-).
        assert re.search(
            r"(?<!-webkit-)backdrop-filter\s*:\s*none\s*!important", decls
        ), (
            "fluent-materials.css: mobile .notification-drawer must set "
            "backdrop-filter: none !important (G2 — remove blur)"
        )
        assert re.search(
            r"-webkit-backdrop-filter\s*:\s*none\s*!important", decls
        ), (
            "fluent-materials.css: mobile .notification-drawer must set "
            "-webkit-backdrop-filter: none !important (macOS WKWebView pairing)"
        )

    def test_rescrape_preview_mobile_stack(self):
        """≤480px .rescrape-preview must stack to a single column (US-12 / AC-22).

        Protects 81c-T7: below 480px the rescrape preview row (cover + metadata
        side-by-side) cramps both columns at 360px (cover max-width:38vw ~137px
        leaves metadata <200px → truncated). The mobile @media must flip the
        preview to flex-direction:column AND widen the cover's max-width off 38vw
        (structural 100%, scales within the fluid modal box). Breakpoint 480 aligns
        with T6 + A-group mobile. >480px keeps the row layout untouched.
        """
        css = _strip_css_comments(RESCRAPE_CSS.read_text(encoding="utf-8"))

        # Locate the @media (max-width:480px){ … } block (tolerate spacing variants).
        m = re.search(r"@media\s*\(\s*max-width\s*:\s*480px\s*\)\s*\{", css)
        assert m is not None, (
            "rescrape-modal.css: no @media (max-width:480px) block found "
            "(81c-T7 mobile stack missing)"
        )

        # Walk brace depth from the opening { to find the media block's end.
        start = m.end() - 1  # position of '{'
        depth = 0
        end = None
        for i in range(start, len(css)):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        assert end is not None, "rescrape-modal.css: unbalanced @media (max-width:480px) block"
        media_body = css[m.end():end]

        # .rescrape-preview rule with flex-direction: column.
        pm = re.search(r"\.rescrape-preview\s*\{([^}]*)\}", media_body)
        assert pm is not None, (
            "rescrape-modal.css: @media (max-width:480px) must contain a "
            ".rescrape-preview rule (81c-T7 mobile stack)"
        )
        assert re.search(r"flex-direction\s*:\s*column", pm.group(1)), (
            "rescrape-modal.css: mobile .rescrape-preview must set "
            "flex-direction: column (AC-22 stack)"
        )

        # Cover img rule with widened max-width (NOT 38vw).
        im = re.search(
            r"\.rescrape-preview\s+\.pv-cover\s+img\s*\{([^}]*)\}", media_body
        )
        assert im is not None, (
            "rescrape-modal.css: @media (max-width:480px) must contain a "
            ".rescrape-preview .pv-cover img rule (81c-T7 cover widen)"
        )
        cover_decls = im.group(1)
        mw = re.search(r"max-width\s*:\s*([^;]+)", cover_decls)
        assert mw is not None, (
            "rescrape-modal.css: mobile cover img must set max-width (widen off 38vw)"
        )
        assert "38vw" not in mw.group(1), (
            "rescrape-modal.css: mobile cover img max-width must be widened off 38vw "
            "(AC-22 — 38vw is the row-mode cramp culprit)"
        )
        assert "100%" in mw.group(1), (
            "rescrape-modal.css: mobile cover img max-width should be 100% "
            "(structural value, scales within fluid modal box)"
        )

        # Token-only: no hardcoded color literals in the mobile cover rule.
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", cover_decls), (
            "rescrape-modal.css: mobile cover img rule must not use a hex color "
            "(token-only — ui-conventions §6)"
        )
