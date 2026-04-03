"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
from pathlib import Path

SHOWCASE_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "showcase.html"


class TestShowcaseMetadataGuard:
    """T3: 確保 showcase.html 包含 director/duration/series/label 的 Alpine 綁定"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_grid_info_panel_has_video_series(self):
        """Grid info panel 含 video.series 綁定"""
        html = self._html()
        assert "video.series" in html, "showcase.html 缺少 video.series 綁定（Grid info panel）"

    def test_grid_info_panel_has_video_duration(self):
        """Grid info panel 含 video.duration 綁定"""
        html = self._html()
        assert "video.duration" in html, "showcase.html 缺少 video.duration 綁定（Grid info panel）"

    def test_table_has_video_director(self):
        """Table mode 含 video.director 綁定"""
        html = self._html()
        assert "video.director" in html, "showcase.html 缺少 video.director 綁定（Table mode）"

    def test_table_has_video_duration(self):
        """Table mode 含 video.duration 綁定（table-cell-duration）"""
        html = self._html()
        assert "table-cell-duration" in html, "showcase.html 缺少 table-cell-duration（Table mode 片長欄）"

    def test_lightbox_has_current_video_director(self):
        """Lightbox 含 currentLightboxVideo?.director 綁定"""
        html = self._html()
        assert "currentLightboxVideo?.director" in html, \
            "showcase.html 缺少 currentLightboxVideo?.director 綁定（Lightbox）"

    def test_lightbox_has_current_video_duration(self):
        """Lightbox 含 currentLightboxVideo?.duration 綁定"""
        html = self._html()
        assert "currentLightboxVideo?.duration" in html, \
            "showcase.html 缺少 currentLightboxVideo?.duration 綁定（Lightbox）"

    def test_lightbox_has_current_video_series(self):
        """Lightbox 含 currentLightboxVideo?.series 綁定"""
        html = self._html()
        assert "currentLightboxVideo?.series" in html, \
            "showcase.html 缺少 currentLightboxVideo?.series 綁定（Lightbox）"

    def test_lightbox_has_current_video_label(self):
        """Lightbox 含 currentLightboxVideo?.label 綁定"""
        html = self._html()
        assert "currentLightboxVideo?.label" in html, \
            "showcase.html 缺少 currentLightboxVideo?.label 綁定（Lightbox）"

    def test_lb_details_div_exists(self):
        """Lightbox 含 lb-details div（37b 合併後的 meta 列）"""
        html = self._html()
        assert "lb-details" in html, \
            "showcase.html 缺少 lb-details（Lightbox 合併 meta 列，37b-layout）"

    def test_search_from_metadata_used_for_director(self):
        """director 可點擊觸發 searchFromMetadata"""
        html = self._html()
        assert "searchFromMetadata(currentLightboxVideo?.director)" in html, \
            "showcase.html lightbox director 缺少 searchFromMetadata 呼叫"

    def test_search_from_metadata_used_for_series(self):
        """series 可點擊觸發 searchFromMetadata（grid panel + lightbox）"""
        html = self._html()
        # 至少在其中一處有 searchFromMetadata(video.series) 或 searchFromMetadata(currentLightboxVideo?.series)
        assert ("searchFromMetadata(video.series)" in html or
                "searchFromMetadata(currentLightboxVideo?.series)" in html), \
            "showcase.html 缺少 series 的 searchFromMetadata 呼叫"


SEARCH_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "search.html"


class TestSearchLightboxMetadataGuard:
    """T4: 確保 search.html lightbox 包含 director/duration/series/label 的 Alpine 綁定"""

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def test_lightbox_has_current_lightbox_video_director(self):
        """Lightbox 含 currentLightboxVideo()?.director 綁定"""
        html = self._html()
        assert "currentLightboxVideo()?.director" in html, \
            "search.html 缺少 currentLightboxVideo()?.director 綁定（Lightbox）"

    def test_lightbox_has_current_lightbox_video_duration(self):
        """Lightbox 含 currentLightboxVideo()?.duration 綁定"""
        html = self._html()
        assert "currentLightboxVideo()?.duration" in html, \
            "search.html 缺少 currentLightboxVideo()?.duration 綁定（Lightbox）"

    def test_lightbox_has_current_lightbox_video_series(self):
        """Lightbox 含 currentLightboxVideo()?.series 綁定"""
        html = self._html()
        assert "currentLightboxVideo()?.series" in html, \
            "search.html 缺少 currentLightboxVideo()?.series 綁定（Lightbox）"

    def test_lightbox_has_current_lightbox_video_label(self):
        """Lightbox 含 currentLightboxVideo()?.label 綁定"""
        html = self._html()
        assert "currentLightboxVideo()?.label" in html, \
            "search.html 缺少 currentLightboxVideo()?.label 綁定（Lightbox）"

    def test_lb_details_div_exists(self):
        """Lightbox 含 lb-details div（37b 合併後的 meta 列）"""
        html = self._html()
        assert "lb-details" in html, \
            "search.html 缺少 lb-details（Lightbox 合併 meta 列，37b-layout）"


SHOWCASE_CORE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "core.js"


class TestShowcaseCoreJsSearchableFields:
    """T5: 確保 showcase/core.js applyFilterAndSort 的 searchable fields 包含新欄位"""

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def test_searchable_includes_director(self):
        """searchable fields 包含 video.director"""
        js = self._js()
        assert "video.director" in js, \
            "showcase/core.js applyFilterAndSort searchable 缺少 video.director"

    def test_searchable_includes_series(self):
        """searchable fields 包含 video.series"""
        js = self._js()
        assert "video.series" in js, \
            "showcase/core.js applyFilterAndSort searchable 缺少 video.series"

    def test_searchable_includes_label(self):
        """searchable fields 包含 video.label"""
        js = self._js()
        assert "video.label" in js, \
            "showcase/core.js applyFilterAndSort searchable 缺少 video.label"


SETTINGS_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "settings.html"
SCANNER_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "scanner.html"
MOTION_LAB_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
DESIGN_SYSTEM_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "design-system.html"
THEME_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "theme.css"
TAILWIND_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "tailwind.css"


class TestHelpPopoverGuard:
    """38e: 守衛 help-popover CSS class 的使用，防止殘留 inline style"""

    def _settings(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _scanner(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def test_settings_has_help_popover_class_at_least_twice(self):
        """settings.html 含 class="help-popover" 至少 2 處"""
        html = self._settings()
        count = html.count('class="help-popover"')
        assert count >= 2, \
            f"settings.html 應含 class=\"help-popover\" 至少 2 處，實際 {count} 處"

    def test_settings_has_help_popover_btn_class_at_least_twice(self):
        """settings.html 含 class="help-popover-btn" 至少 2 處"""
        html = self._settings()
        count = html.count('class="help-popover-btn"')
        assert count >= 2, \
            f"settings.html 應含 class=\"help-popover-btn\" 至少 2 處，實際 {count} 處"

    def test_scanner_has_help_popover_class(self):
        """scanner.html 含 class="help-popover" 至少 1 處"""
        html = self._scanner()
        count = html.count('class="help-popover"')
        assert count >= 1, \
            f"scanner.html 應含 class=\"help-popover\" 至少 1 處，實際 {count} 處"

    def test_scanner_has_help_popover_btn_class(self):
        """scanner.html 含 class="help-popover-btn" 至少 1 處"""
        html = self._scanner()
        count = html.count('class="help-popover-btn"')
        assert count >= 1, \
            f"scanner.html 應含 class=\"help-popover-btn\" 至少 1 處，實際 {count} 處"

    def test_settings_no_broken_shadow_token(self):
        """settings.html 不含 box-shadow: var(--shadow-4)（未定義的 token）"""
        html = self._settings()
        assert "box-shadow: var(--shadow-4)" not in html, \
            "settings.html 含殘留 box-shadow: var(--shadow-4)（應改為 --fluent-shadow-4）"

    def test_scanner_no_broken_shadow_token(self):
        """scanner.html 不含 box-shadow: var(--shadow-4)（未定義的 token）"""
        html = self._scanner()
        assert "box-shadow: var(--shadow-4)" not in html, \
            "scanner.html 含殘留 box-shadow: var(--shadow-4)（應改為 --fluent-shadow-4）"


class TestInlineStyleCleanup:
    """T4 守衛：確認 inline style 已清理為 CSS class"""

    def _settings(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _theme_css(self):
        return THEME_CSS.read_text(encoding="utf-8")

    def _tailwind_css(self):
        return TAILWIND_CSS.read_text(encoding="utf-8")

    def _motion_lab(self):
        return MOTION_LAB_HTML.read_text(encoding="utf-8")

    def _design_system(self):
        return DESIGN_SYSTEM_HTML.read_text(encoding="utf-8")

    def test_settings_no_inline_position_relative_for_popover(self):
        """settings.html 不應有 style="position: relative;" 用於 popover 錨點"""
        html = self._settings()
        assert 'style="position: relative;"' not in html, \
            'settings.html 仍含 style="position: relative;"，應改用 class="... popover-anchor"'

    def test_theme_css_no_scoped_manual_input(self):
        """theme.css 與 tailwind.css 的 .manual-input 不應有 :is() scope guard"""
        for label, css in [("theme.css", self._theme_css()), ("tailwind.css", self._tailwind_css())]:
            lines = css.splitlines()
            for line in lines:
                if ":is(" in line and "manual-input" in line:
                    raise AssertionError(
                        f"{label} 仍有 :is() scope 限制 manual-input：{line.strip()}"
                    )

    def test_motion_lab_no_inline_object_fit(self):
        """motion_lab.html 不應有 inline object-fit:cover"""
        html = self._motion_lab()
        # 在 style= 屬性中尋找 object-fit:cover 或 object-fit: cover
        import re
        pattern = re.compile(r'style=["\'][^"\']*object-fit\s*:\s*cover[^"\']*["\']')
        matches = pattern.findall(html)
        assert len(matches) == 0, \
            f"motion_lab.html 仍有 {len(matches)} 處 inline object-fit:cover，應改用 class=\"img-cover-fill\""

    def test_design_system_no_inline_bg_card_pattern(self):
        """design-system.html 不應有 inline padding + background: var(--bg-card) + border-radius 三合一 pattern"""
        html = self._design_system()
        import re
        # 找 style= 屬性中同時含 padding（1rem 或 1.5rem 2rem）+ background: var(--bg-card) + border-radius: var(--radius-md) 的
        # 這 7 處的 padding 值為 "1rem 1.5rem" 或 "1.5rem 2rem"，且只有這 3 個屬性（無 max-width、box-shadow 等額外屬性）
        pattern = re.compile(
            r'style=["\']padding:\s*(?:1(?:\.5)?rem\s+(?:1\.5rem|2rem)|1rem\s+1\.5rem);\s*background:\s*var\(--bg-card\);\s*border-radius:\s*var\(--radius-md\);["\']'
        )
        matches = pattern.findall(html)
        assert len(matches) == 0, \
            f"design-system.html 仍有 {len(matches)} 處 padding+bg-card+border-radius inline pattern，應改用 class=\"... ds-demo-panel\""


BATCH_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "batch.js"
SEARCH_FLOW_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "search-flow.js"
BASE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "base.js"


class TestBatchIntervalGuard:
    """T1(40b): 守衛 batch/translate checkInterval 具名 ref + cleanupForNavigation 明確清理"""

    def _batch(self):
        return BATCH_JS.read_text(encoding="utf-8")

    def _search_flow(self):
        return SEARCH_FLOW_JS.read_text(encoding="utf-8")

    def _base(self):
        return BASE_JS.read_text(encoding="utf-8")

    def test_batch_check_interval_assigned(self):
        """batch.js searchAll() 使用 this._batchCheckInterval = setInterval"""
        js = self._batch()
        assert "this._batchCheckInterval = setInterval" in js, \
            "batch.js searchAll() 應將 setInterval 賦值給 this._batchCheckInterval（具名 ref）"

    def test_translate_check_interval_assigned(self):
        """batch.js translateAll() 使用 this._translateCheckInterval = setInterval"""
        js = self._batch()
        assert "this._translateCheckInterval = setInterval" in js, \
            "batch.js translateAll() 應將 setInterval 賦值給 this._translateCheckInterval（具名 ref）"

    def test_batch_interval_self_clear(self):
        """batch.js searchAll() 內 clearInterval(this._batchCheckInterval) 自清"""
        js = self._batch()
        assert "clearInterval(this._batchCheckInterval)" in js, \
            "batch.js searchAll() 應在條件成立時 clearInterval(this._batchCheckInterval)"

    def test_translate_interval_self_clear(self):
        """batch.js translateAll() 內 clearInterval(this._translateCheckInterval) 自清"""
        js = self._batch()
        assert "clearInterval(this._translateCheckInterval)" in js, \
            "batch.js translateAll() 應在條件成立時 clearInterval(this._translateCheckInterval)"

    def test_cleanup_clears_batch_interval(self):
        """search-flow.js cleanupForNavigation() 明確清除 this._batchCheckInterval"""
        js = self._search_flow()
        assert "clearInterval(this._batchCheckInterval)" in js, \
            "search-flow.js cleanupForNavigation() 應明確 clearInterval(this._batchCheckInterval)"

    def test_cleanup_clears_translate_interval(self):
        """search-flow.js cleanupForNavigation() 明確清除 this._translateCheckInterval"""
        js = self._search_flow()
        assert "clearInterval(this._translateCheckInterval)" in js, \
            "search-flow.js cleanupForNavigation() 應明確 clearInterval(this._translateCheckInterval)"

    def test_base_declares_batch_check_interval(self):
        """base.js state 初始化包含 _batchCheckInterval 欄位"""
        js = self._base()
        assert "_batchCheckInterval" in js, \
            "base.js 應在初始 state 宣告 _batchCheckInterval: null"

    def test_base_declares_translate_check_interval(self):
        """base.js state 初始化包含 _translateCheckInterval 欄位"""
        js = self._base()
        assert "_translateCheckInterval" in js, \
            "base.js 應在初始 state 宣告 _translateCheckInterval: null"
