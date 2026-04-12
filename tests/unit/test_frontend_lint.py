"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
import json
from pathlib import Path

import pytest

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
SCANNER_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner.js"
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
SETTINGS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings.js"


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


INDEX_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "index.js"


class TestTimerListenerGuard:
    """T2(40b): 守衛 index.js window listener 具名 ref + cleanup removeEventListener"""

    def _index(self):
        return INDEX_JS.read_text(encoding="utf-8")

    def _base(self):
        return BASE_JS.read_text(encoding="utf-8")

    def test_index_uses_set_timer_for_cover_height(self):
        """index.js $watch('searchResults') 使用 _setTimer('updateCoverHeight'"""
        js = self._index()
        assert "_setTimer('updateCoverHeight'" in js, \
            "index.js $watch('searchResults') 應改用 _setTimer('updateCoverHeight', ...) 取代裸 setTimeout"

    def test_index_no_bare_settimeout_for_cover_height(self):
        """index.js 不含裸 setTimeout(() => this._updateCoverHeight()"""
        js = self._index()
        assert "setTimeout(() => this._updateCoverHeight()" not in js, \
            "index.js 仍含裸 setTimeout(() => this._updateCoverHeight()，應改為 _setTimer"

    def test_index_pywebview_handler_assigned(self):
        """index.js pywebview-files listener 賦值給 this._pywebviewFilesHandler"""
        js = self._index()
        assert "this._pywebviewFilesHandler =" in js, \
            "index.js 應將 pywebview-files handler 賦值給 this._pywebviewFilesHandler（具名 ref）"

    def test_index_resize_handler_assigned(self):
        """index.js resize listener 賦值給 this._resizeHandler"""
        js = self._index()
        assert "this._resizeHandler =" in js, \
            "index.js 應將 resize handler 賦值給 this._resizeHandler（具名 ref）"

    def test_index_cleanup_removes_pywebview_listener(self):
        """index.js cleanup() 含 removeEventListener('pywebview-files', this._pywebviewFilesHandler)"""
        js = self._index()
        assert "removeEventListener('pywebview-files', this._pywebviewFilesHandler)" in js, \
            "index.js cleanup() 應 removeEventListener('pywebview-files', this._pywebviewFilesHandler)"

    def test_index_cleanup_removes_resize_listener(self):
        """index.js cleanup() 含 removeEventListener('resize', this._resizeHandler)"""
        js = self._index()
        assert "removeEventListener('resize', this._resizeHandler)" in js, \
            "index.js cleanup() 應 removeEventListener('resize', this._resizeHandler)"

    def test_base_declares_pywebview_handler(self):
        """base.js state 初始化包含 _pywebviewFilesHandler 欄位"""
        js = self._base()
        assert "_pywebviewFilesHandler" in js, \
            "base.js 應在初始 state 宣告 _pywebviewFilesHandler: null"

    def test_base_declares_resize_handler(self):
        """base.js state 初始化包含 _resizeHandler 欄位"""
        js = self._base()
        assert "_resizeHandler" in js, \
            "base.js 應在初始 state 宣告 _resizeHandler: null"


class TestSettingsCleanupBypassGuard:
    """T3(40b): 確保 dirtyCheckDiscard() 使用 __leavePage 而非直接跳轉"""

    def _js(self):
        return SETTINGS_JS.read_text(encoding="utf-8")

    def test_dirty_check_discard_uses_leave_page(self):
        """dirtyCheckDiscard() 呼叫 window.__leavePage"""
        js = self._js()
        assert "window.__leavePage" in js, \
            "settings.js dirtyCheckDiscard() 應使用 window.__leavePage 而非直接設定 window.location.href"

    def test_dirty_check_discard_has_location_fallback(self):
        """dirtyCheckDiscard() 保留 window.location.href fallback"""
        js = self._js()
        assert "window.location.href" in js, \
            "settings.js dirtyCheckDiscard() 應保留 window.location.href 作為 fallback"

    def test_dirty_check_discard_calls_leave_page_with_url(self):
        """dirtyCheckDiscard() 以 pendingNavigationUrl 呼叫 __leavePage"""
        js = self._js()
        assert "window.__leavePage(this.pendingNavigationUrl)" in js, \
            "settings.js dirtyCheckDiscard() 應以 this.pendingNavigationUrl 呼叫 window.__leavePage"

    def test_dirty_check_discard_gates_on_leave_page_return(self):
        """dirtyCheckDiscard() 使用 !window.__leavePage(...) gate（回傳 false 時阻止導航）"""
        js = self._js()
        assert "if (!window.__leavePage(this.pendingNavigationUrl)) return;" in js, \
            "settings.js dirtyCheckDiscard() 應在 __leavePage 回傳 false 時 return（阻止導航）"

    def test_dirty_check_save_calls_leave_page_with_url(self):
        """dirtyCheckSave() 儲存成功後也透過 __leavePage gate 再跳轉"""
        js = self._js()
        # dirtyCheckSave 在 isDirty 為 false 後跳轉，需同樣呼叫 __leavePage
        # 至少出現兩次（dirtyCheckDiscard 一次 + dirtyCheckSave 一次）
        count = js.count("window.__leavePage(this.pendingNavigationUrl)")
        assert count >= 2, \
            (f"settings.js dirtyCheckSave() 也應使用 window.__leavePage(this.pendingNavigationUrl) gate，"
             f"目前只有 {count} 處")

    def test_dirty_check_save_gates_on_leave_page_return(self):
        """dirtyCheckSave() 使用 !window.__leavePage(...) gate（回傳 false 時阻止導航）"""
        js = self._js()
        # 同一個 gate pattern 在檔案中出現至少兩次
        count = js.count("if (!window.__leavePage(this.pendingNavigationUrl)) return;")
        assert count >= 2, \
            (f"settings.js dirtyCheckSave() 也應在 __leavePage 回傳 false 時 return，"
             f"目前只有 {count} 處")


LOCALES_ROOT = Path(__file__).parent.parent.parent / "locales"


class TestJellyfinCheckManualGuard:
    """40c-T2: 守衛 Jellyfin check 改為手動觸發的所有前端不變式"""

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SCANNER_JS.read_text(encoding="utf-8")

    def test_no_auto_trigger_in_init(self):
        """init() 後的 loadStats 呼叫後，不應緊接 checkJellyfinImages()"""
        # 確認 checkJellyfinImages() 只透過 @click 觸發，不在 init() 或 loadStats 後出現
        js = self._js()
        assert "this.loadStats();\n        this.checkJellyfinImages();" not in js, \
            "scanner.js init() 仍含自動觸發 checkJellyfinImages()"

    def test_jellyfin_check_state_declared(self):
        """Alpine data 宣告 jellyfinCheckState 欄位"""
        js = self._js()
        assert "jellyfinCheckState: 'idle'" in js, \
            "scanner.js 缺少 jellyfinCheckState: 'idle' 初始化宣告"

    def test_jellyfin_check_controller_declared(self):
        """Alpine data 宣告 _jellyfinCheckController 欄位"""
        js = self._js()
        assert "_jellyfinCheckController: null" in js, \
            "scanner.js 缺少 _jellyfinCheckController: null 初始化宣告"

    def test_abort_controller_used_in_check(self):
        """checkJellyfinImages() 建立 AbortController"""
        js = self._js()
        assert "new AbortController()" in js, \
            "scanner.js checkJellyfinImages() 缺少 new AbortController()"

    def test_abort_called_in_cleanup(self):
        """cleanup 回呼內含 _jellyfinCheckController.abort()"""
        js = self._js()
        assert "_jellyfinCheckController.abort()" in js, \
            "scanner.js cleanup 缺少 _jellyfinCheckController.abort()"

    def test_jellyfin_check_state_reset_in_cleanup(self):
        """cleanup 回呼補上 jellyfinCheckState = 'idle' 重設"""
        js = self._js()
        assert "jellyfinCheckState = 'idle'" in js, \
            "scanner.js cleanup 缺少 jellyfinCheckState = 'idle' 重設"

    def test_should_warn_checks_jellyfin_checking(self):
        """shouldWarnBeforeLeave() 含 jellyfinCheckState === 'checking' 判斷"""
        js = self._js()
        assert "jellyfinCheckState === 'checking'" in js, \
            "scanner.js shouldWarnBeforeLeave() 缺少 jellyfinCheckState === 'checking' 判斷"

    def test_trigger_button_click_handler(self):
        """觸發按鈕 @click 呼叫 checkJellyfinImages()"""
        html = self._html()
        assert '@click="checkJellyfinImages()"' in html, \
            "scanner.html 缺少 @click=\"checkJellyfinImages()\" 觸發按鈕"

    def test_no_auto_trigger_after_generate(self):
        """generate SSE done 事件後無自動呼叫 checkJellyfinImages()"""
        js = self._js()
        # loadStats 後面不應接 checkJellyfinImages（generate 路徑）
        assert "this.loadStats();\n                    this.checkJellyfinImages();" not in js, \
            "scanner.js generate done 路徑仍自動呼叫 checkJellyfinImages()"

    def test_clear_cache_resets_jellyfin_state(self):
        """clearCache 成功後含 jellyfinCheckState = 'idle' 重設"""
        js = self._js()
        # jellyfinImageVisible = false 後緊接 jellyfinCheckState = 'idle'
        assert "jellyfinImageVisible = false" in js, \
            "scanner.js clearCache 缺少 jellyfinImageVisible = false"
        # jellyfinCheckState = 'idle' 在 clearCache 函數中也必須出現
        # （在 shouldWarnBeforeLeave 和 beforeLeave 都有，此守衛確認 clearCache 路徑有）
        # 用計數確認至少 2 處（cleanup + clearCache，shouldWarnBeforeLeave 判斷不算 assignment）
        count = js.count("jellyfinCheckState = 'idle'")
        assert count >= 2, \
            f"scanner.js jellyfinCheckState = 'idle' 出現 {count} 次，期望 >= 2（cleanup + clearCache）"

    def test_trigger_row_xshow_uses_jellyfin_image_visible(self):
        """T3(40c) Codex fix: 觸發列 x-show 改為 !jellyfinImageVisible 而非 jellyfinCheckState !== 'done'"""
        html = self._html()
        assert "config?.scraper?.jellyfin_mode && !jellyfinImageVisible" in html, \
            "scanner.html 觸發列 x-show 應使用 !jellyfinImageVisible（而非 jellyfinCheckState !== 'done'）"
        assert "config?.scraper?.jellyfin_mode && jellyfinCheckState !== 'done'" not in html, \
            "scanner.html 觸發列 x-show 仍使用舊的 jellyfinCheckState !== 'done' 條件"

    def test_trigger_row_done_state_text_present(self):
        """T3(40c) Codex fix: 觸發列包含 done 狀態顯示文字"""
        html = self._html()
        assert "jellyfinCheckState === 'done'" in html, \
            "scanner.html 觸發列缺少 done 狀態文字顯示"
        assert "jellyfin_check_done_ok" in html, \
            "scanner.html 觸發列缺少 jellyfin_check_done_ok i18n key 引用"

    def test_jellyfin_update_done_resets_check_state(self):
        """T3(40c) Codex fix: jellyfin-update done handler 重設 jellyfinCheckState = 'idle'"""
        js = self._js()
        # 確認 runJellyfinImageUpdate 的 done 分支有三個重設欄位
        assert "this.jellyfinImageVisible = false" in js, \
            "scanner.js runJellyfinImageUpdate done 缺少 jellyfinImageVisible = false 重設"
        assert "this.jellyfinImageCount = 0" in js, \
            "scanner.js runJellyfinImageUpdate done 缺少 jellyfinImageCount = 0 重設"
        # jellyfinCheckState = 'idle' 重設（update done 分支使用 this. 前綴）
        assert "this.jellyfinCheckState = 'idle'" in js, \
            "scanner.js runJellyfinImageUpdate done 缺少 this.jellyfinCheckState = 'idle' 重設"


class TestJellyfinCheckI18nKeys:
    """40c-T2: 確認新增 i18n key 存在於 zh_TW.json"""

    REQUIRED_KEYS = [
        "scanner.stats.jellyfin_check_btn",
        "scanner.stats.jellyfin_check_idle_label",
        "scanner.stats.jellyfin_checking",
    ]

    def _zh_tw(self):
        return json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    def test_jellyfin_check_btn_key_exists(self):
        zh_tw = self._zh_tw()
        val = self._get_nested(zh_tw, "scanner.stats.jellyfin_check_btn")
        assert val, "zh_TW.json 缺少 scanner.stats.jellyfin_check_btn"

    def test_jellyfin_check_idle_label_key_exists(self):
        zh_tw = self._zh_tw()
        val = self._get_nested(zh_tw, "scanner.stats.jellyfin_check_idle_label")
        assert val, "zh_TW.json 缺少 scanner.stats.jellyfin_check_idle_label"

    def test_jellyfin_checking_key_exists(self):
        zh_tw = self._zh_tw()
        val = self._get_nested(zh_tw, "scanner.stats.jellyfin_checking")
        assert val, "zh_TW.json 缺少 scanner.stats.jellyfin_checking"

    def test_jellyfin_check_done_ok_key_exists(self):
        """T3(40c) Codex fix: 確認 jellyfin_check_done_ok i18n key 存在"""
        zh_tw = self._zh_tw()
        val = self._get_nested(zh_tw, "scanner.stats.jellyfin_check_done_ok")
        assert val, "zh_TW.json 缺少 scanner.stats.jellyfin_check_done_ok"


class TestSmartCloseRemovedGuard:
    """Phase 40d-T1: Showcase Smart Close 系統移除守衛"""

    CORE_JS = Path(__file__).parents[2] / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'core.js'
    SHOWCASE_HTML = Path(__file__).parents[2] / 'web' / 'templates' / 'showcase.html'

    def test_no_mousemove_handler_in_showcase_html(self):
        """showcase.html 不應包含 handleLightboxMousemove binding"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        assert 'handleLightboxMousemove' not in content

    def test_no_lightbox_move_enabled_in_core_js(self):
        """core.js 不應包含 lightboxMoveEnabled（Smart Close 門控已移除）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'lightboxMoveEnabled' not in content

    def test_no_lightbox_move_timer_in_core_js(self):
        """core.js 不應包含 lightboxMoveTimer（Smart Close timer 已移除）"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        assert 'lightboxMoveTimer' not in content


class TestShowcaseKeyboardGuard:
    """Phase 40d-T2: Showcase 鍵盤 preventDefault 守衛"""

    CORE_JS = Path(__file__).parents[2] / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'core.js'

    def _extract_block(self, content, anchor, end_marker='return;'):
        """提取從 anchor 到 end_marker 的區塊"""
        start = content.find(anchor)
        if start == -1:
            return ''
        end = content.find(end_marker, start)
        if end == -1:
            return content[start:]
        return content[start:end + len(end_marker)]

    def test_sample_gallery_keyboard_has_prevent_default(self):
        """sample gallery keyboard 分支應有 e.preventDefault()"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        block = self._extract_block(content, 'if (this.sampleGalleryOpen)')
        assert 'e.preventDefault()' in block, \
            "sample gallery keyboard 分支缺少 e.preventDefault()"

    def test_lightbox_keyboard_has_prevent_default(self):
        """lightbox keyboard 分支應有 e.preventDefault()"""
        content = self.CORE_JS.read_text(encoding='utf-8')
        # 使用鍵盤 handler 特有的注釋行作為錨，避免誤中 cleanup 裡的 if (this.lightboxOpen)
        block = self._extract_block(content, '// 5. Lightbox 開啟時的快捷鍵')
        assert 'e.preventDefault()' in block, \
            "lightbox keyboard 分支缺少 e.preventDefault()"


class TestShowcaseActressState:
    """Phase 44a-T2: Showcase 女優模式 Alpine state 守衛"""

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    # --- Module-level arrays ---
    def test_module_level_actresses_declared(self):
        """var _actresses = [] 存在於 module scope"""
        js = self._js()
        assert "var _actresses = []" in js, \
            "showcase/core.js 缺少 module-level var _actresses = []"

    def test_module_level_filtered_actresses_declared(self):
        """var _filteredActresses = [] 存在於 module scope"""
        js = self._js()
        assert "var _filteredActresses = []" in js, \
            "showcase/core.js 缺少 module-level var _filteredActresses = []"

    # --- Alpine state properties ---
    def test_state_has_show_favorite_actresses(self):
        """showFavoriteActresses 出現於 Alpine state"""
        js = self._js()
        assert "showFavoriteActresses" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 showFavoriteActresses"

    def test_state_has_actress_count(self):
        """actressCount 出現於 Alpine state"""
        js = self._js()
        assert "actressCount" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressCount"

    def test_state_has_filtered_actress_count(self):
        """filteredActressCount 出現於 Alpine state"""
        js = self._js()
        assert "filteredActressCount" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 filteredActressCount"

    def test_state_has_paginated_actresses(self):
        """paginatedActresses 出現於 Alpine state"""
        js = self._js()
        assert "paginatedActresses" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 paginatedActresses"

    def test_state_has_actress_search(self):
        """actressSearch 出現於 Alpine state"""
        js = self._js()
        assert "actressSearch" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressSearch"

    def test_state_has_actress_sort(self):
        """actressSort 出現於 Alpine state"""
        js = self._js()
        assert "actressSort" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressSort"

    def test_state_has_actress_order(self):
        """actressOrder 出現於 Alpine state"""
        js = self._js()
        assert "actressOrder" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressOrder"

    def test_state_has_actress_loading(self):
        """actressLoading 出現於 Alpine state"""
        js = self._js()
        assert "actressLoading" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressLoading"

    def test_state_has_actress_lightbox_index(self):
        """actressLightboxIndex 出現於 Alpine state"""
        js = self._js()
        assert "actressLightboxIndex" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 actressLightboxIndex"

    def test_state_has_current_lightbox_actress(self):
        """currentLightboxActress 出現於 Alpine state"""
        js = self._js()
        assert "currentLightboxActress" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 currentLightboxActress"

    def test_state_has_actress_chips_expanded(self):
        """_actressChipsExpanded 出現於 Alpine state"""
        js = self._js()
        assert "_actressChipsExpanded" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _actressChipsExpanded"

    def test_state_has_add_actress_name(self):
        """_addActressName 出現於 Alpine state"""
        js = self._js()
        assert "_addActressName" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _addActressName"

    def test_state_has_adding_actress(self):
        """_addingActress 出現於 Alpine state"""
        js = self._js()
        assert "_addingActress" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _addingActress"

    def test_state_has_add_dropdown_open(self):
        """_addDropdownOpen 出現於 Alpine state"""
        js = self._js()
        assert "_addDropdownOpen" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _addDropdownOpen"

    def test_state_has_rescraping(self):
        """_rescraping 出現於 Alpine state"""
        js = self._js()
        assert "_rescraping" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _rescraping"

    def test_state_has_video_chips_expanded(self):
        """_videoChipsExpanded 出現於 Alpine state"""
        js = self._js()
        assert "_videoChipsExpanded" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _videoChipsExpanded"

    # --- Core methods ---
    def test_toggle_actress_mode_defined(self):
        """toggleActressMode 方法存在"""
        js = self._js()
        assert "toggleActressMode" in js, \
            "showcase/core.js 缺少方法 toggleActressMode"

    def test_load_actresses_defined(self):
        """loadActresses 方法存在"""
        js = self._js()
        assert "loadActresses" in js, \
            "showcase/core.js 缺少方法 loadActresses"

    def test_apply_actress_filter_and_sort_defined(self):
        """applyActressFilterAndSort 方法存在"""
        js = self._js()
        assert "applyActressFilterAndSort" in js, \
            "showcase/core.js 缺少方法 applyActressFilterAndSort"

    def test_on_actress_search_change_defined(self):
        """onActressSearchChange 方法存在"""
        js = self._js()
        assert "onActressSearchChange" in js, \
            "showcase/core.js 缺少方法 onActressSearchChange"

    def test_on_actress_sort_change_defined(self):
        """onActressSortChange 方法存在"""
        js = self._js()
        assert "onActressSortChange" in js, \
            "showcase/core.js 缺少方法 onActressSortChange"

    def test_toggle_actress_order_defined(self):
        """toggleActressOrder 方法存在"""
        js = self._js()
        assert "toggleActressOrder" in js, \
            "showcase/core.js 缺少方法 toggleActressOrder"

    # --- Lightbox methods ---
    def test_open_actress_lightbox_defined(self):
        """openActressLightbox 方法存在"""
        js = self._js()
        assert "openActressLightbox" in js, \
            "showcase/core.js 缺少方法 openActressLightbox"

    def test_close_actress_lightbox_defined(self):
        """closeActressLightbox 方法存在"""
        js = self._js()
        assert "closeActressLightbox" in js, \
            "showcase/core.js 缺少方法 closeActressLightbox"

    def test_prev_actress_lightbox_defined(self):
        """prevActressLightbox 方法存在"""
        js = self._js()
        assert "prevActressLightbox" in js, \
            "showcase/core.js 缺少方法 prevActressLightbox"

    def test_next_actress_lightbox_defined(self):
        """nextActressLightbox 方法存在"""
        js = self._js()
        assert "nextActressLightbox" in js, \
            "showcase/core.js 缺少方法 nextActressLightbox"

    def test_set_actress_lightbox_index_defined(self):
        """_setActressLightboxIndex 方法存在"""
        js = self._js()
        assert "_setActressLightboxIndex" in js, \
            "showcase/core.js 缺少方法 _setActressLightboxIndex"

    # --- Sort logic ---
    def test_cup_rank_defined(self):
        """cupRank 出現於排序邏輯"""
        js = self._js()
        assert "cupRank" in js, \
            "showcase/core.js applyActressFilterAndSort 缺少 cupRank 排序定義"

    # --- _setLightboxIndex mutual exclusion ---
    def test_set_lightbox_index_clears_actress(self):
        """_setLightboxIndex 內含 currentLightboxActress = null"""
        js = self._js()
        assert "currentLightboxActress = null" in js, \
            "showcase/core.js _setLightboxIndex 缺少 this.currentLightboxActress = null（互斥保證）"

    def test_set_lightbox_index_resets_video_chips(self):
        """_setLightboxIndex 內含 _videoChipsExpanded = false"""
        js = self._js()
        assert "_videoChipsExpanded = false" in js, \
            "showcase/core.js _setLightboxIndex 缺少 this._videoChipsExpanded = false（reset chips）"

    # --- saveState / restoreState ---
    def test_save_state_includes_actress_mode(self):
        """saveState 內含 showFavoriteActresses key"""
        js = self._js()
        assert "showFavoriteActresses: this.showFavoriteActresses" in js, \
            "showcase/core.js saveState() 缺少 showFavoriteActresses key"

    def test_save_state_includes_actress_sort(self):
        """saveState 內含 actressSort key"""
        js = self._js()
        assert "actressSort: this.actressSort" in js, \
            "showcase/core.js saveState() 缺少 actressSort key"

    def test_save_state_includes_actress_order(self):
        """saveState 內含 actressOrder key"""
        js = self._js()
        assert "actressOrder: this.actressOrder" in js, \
            "showcase/core.js saveState() 缺少 actressOrder key"

    def test_restore_state_restores_actress_mode(self):
        """restoreState 內含 showFavoriteActresses 還原邏輯"""
        js = self._js()
        assert "showFavoriteActresses === true" in js, \
            "showcase/core.js restoreState() 缺少 showFavoriteActresses === true（strict equality 還原）"

    def test_restore_state_restores_actress_sort(self):
        """restoreState 內含 actressSort 還原邏輯"""
        js = self._js()
        assert "state.actressSort" in js, \
            "showcase/core.js restoreState() 缺少 state.actressSort 還原邏輯"

    def test_restore_state_restores_actress_order(self):
        """restoreState 內含 actressOrder 還原邏輯"""
        js = self._js()
        assert "state.actressOrder" in js, \
            "showcase/core.js restoreState() 缺少 state.actressOrder 還原邏輯"

    # --- handleKeydown dispatch ---
    def test_keydown_dispatches_actress_lightbox(self):
        """handleKeydown 內含 currentLightboxActress 判斷"""
        js = self._js()
        assert "this.currentLightboxActress" in js, \
            "showcase/core.js handleKeydown 缺少 currentLightboxActress 判斷分支"

    def test_keydown_prev_actress_lightbox_present(self):
        """handleKeydown 內含 prevActressLightbox() 呼叫"""
        js = self._js()
        assert "this.prevActressLightbox()" in js, \
            "showcase/core.js handleKeydown 缺少 this.prevActressLightbox() 呼叫"

    def test_keydown_next_actress_lightbox_present(self):
        """handleKeydown 內含 nextActressLightbox() 呼叫"""
        js = self._js()
        assert "this.nextActressLightbox()" in js, \
            "showcase/core.js handleKeydown 缺少 this.nextActressLightbox() 呼叫"


class TestGeminiLocaleKeyGuard:
    """39a-T3: 守衛 settings.js 不再使用 gemini_n_flash_models locale key"""

    def _js(self):
        return SETTINGS_JS.read_text(encoding="utf-8")

    def test_settings_js_no_gemini_n_flash_models(self):
        """settings.js 不應出現 gemini_n_flash_models（已替換為 connected_n_models）"""
        js = self._js()
        assert "gemini_n_flash_models" not in js, \
            "settings.js 仍含 gemini_n_flash_models，應改為 connected_n_models"


GRID_MODE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"


class TestLoadMoreButton:
    """39a-T4: 守衛 Grid Load More 按鈕 + hasVisibleNext + nextLightboxVideo loadMore 觸發"""

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _base(self):
        return BASE_JS.read_text(encoding="utf-8")

    def _grid_mode(self):
        return GRID_MODE_JS.read_text(encoding="utf-8")

    def _locale(self, name):
        return json.loads((LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    # --- search.html ---

    def test_html_load_more_click_binding(self):
        """search.html grid-staging-wrapper 內含 gridLoadMore() 的 @click 綁定"""
        html = self._html()
        assert '@click="gridLoadMore()"' in html, \
            'search.html 缺少 @click="gridLoadMore()" 綁定（Load More 按鈕）'

    def test_html_load_more_i18n_ref(self):
        """search.html 含 t('search.button.load_more') 引用"""
        html = self._html()
        assert "t('search.button.load_more')" in html, \
            "search.html 缺少 t('search.button.load_more') i18n 引用"

    def test_html_load_more_xshow_condition(self):
        """search.html Load More 按鈕 x-show 含 hasMoreResults && displayMode === 'grid'（loading 狀態由 :disabled 處理）"""
        html = self._html()
        assert "hasMoreResults && displayMode === 'grid'" in html, \
            "search.html Load More 按鈕缺少正確的 x-show 條件（hasMoreResults && displayMode === 'grid'）"

    # --- base.js ---

    def test_base_has_visible_next_checks_has_more_results(self):
        """base.js hasVisibleNext() 含 hasMoreResults 判斷"""
        js = self._base()
        assert "hasMoreResults" in js, \
            "base.js hasVisibleNext() 缺少 hasMoreResults 判斷"

    # --- grid-mode.js ---

    def test_grid_mode_next_lightbox_video_calls_load_more(self):
        """grid-mode.js nextLightboxVideo() 含 await this.loadMore('lightbox') 呼叫（T3c）"""
        js = self._grid_mode()
        assert "await this.loadMore('lightbox')" in js, \
            "grid-mode.js nextLightboxVideo() 缺少 await this.loadMore('lightbox') 呼叫（T3c fire-and-forget 已改為 await）"

    # --- locale files ---

    def test_all_locales_have_load_more_key(self):
        """四個 locale 檔案均含 search.button.load_more key"""
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            val = self._get_nested(data, "search.button.load_more")
            assert val, f"{locale_file} 缺少 search.button.load_more key"

    # --- T3a 守衛 ---

    def _navigation_js(self):
        return NAVIGATION_JS.read_text(encoding="utf-8")

    def _animations_js(self):
        return ANIMATIONS_JS.read_text(encoding="utf-8")

    def test_loadmore_has_trigger_parameter(self):
        """T3a: navigation.js loadMore 函數簽名含 trigger 參數"""
        js = self._navigation_js()
        assert "async loadMore(trigger" in js, \
            "navigation.js 缺少 async loadMore(trigger ...) 簽名（T3a 需加 trigger 參數）"

    def test_loadmore_returns_result_object(self):
        """T3a: navigation.js loadMore 成功分支回傳 { loadedCount, oldLength }"""
        js = self._navigation_js()
        start = js.find("async loadMore(trigger")
        assert start != -1, "navigation.js 找不到 async loadMore(trigger 函數"
        func_body = js[start:]
        finally_pos = func_body.find("finally {")
        if finally_pos != -1:
            end_pos = func_body.find("}", finally_pos + len("finally {"))
            end_pos = func_body.find("},", end_pos + 1)
            func_body = func_body[:end_pos] if end_pos != -1 else func_body
        assert "return { loadedCount" in func_body, \
            "navigation.js loadMore() 成功分支缺少 return { loadedCount ... } 回傳值（T3a 需回傳 append 結果）"

    def test_grid_load_more_exists(self):
        """T3a: navigation.js 含 async gridLoadMore() 函數"""
        js = self._navigation_js()
        assert "async gridLoadMore()" in js, \
            "navigation.js 缺少 async gridLoadMore() 函數（T3a Grid 按鈕入口）"

    def test_animations_has_play_append_cascade(self):
        """T3a: animations.js 含 playAppendCascade 函數"""
        js = self._animations_js()
        assert "playAppendCascade" in js, \
            "animations.js 缺少 playAppendCascade（T3a append cascade 動畫）"


NAVIGATION_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"
ANIMATIONS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "animations.js"


class TestCodexFixes:
    """39a Codex review 修正守衛"""

    def _navigation_js(self):
        return NAVIGATION_JS.read_text(encoding="utf-8")

    def _settings_js(self):
        return SETTINGS_JS.read_text(encoding="utf-8")

    def test_loadmore_no_currentindex_assignment(self):
        """F1：loadMore() 成功分支不含 this.currentIndex = 賦值"""
        js = self._navigation_js()
        # 找到 loadMore 函數體，截取到 finally 區塊結束
        start = js.find("async loadMore(trigger")
        assert start != -1, "navigation.js 找不到 async loadMore(trigger ...) 函數"
        # 截取 loadMore 函數體（到函數結尾）
        func_body = js[start:]
        # 找到 finally { ... } 後的第一個右大括號（函數結束）
        finally_pos = func_body.find("finally {")
        if finally_pos != -1:
            # 截取 loadMore 函數範圍：從函數開始到 finally 區塊後的 } 結尾
            end_pos = func_body.find("}", finally_pos + len("finally {"))
            # 再找外層函數的 }
            end_pos = func_body.find("},", end_pos + 1)
            func_body = func_body[:end_pos] if end_pos != -1 else func_body
        # 確認函數體內不含 this.currentIndex = 賦值（有空格的賦值語句）
        assert "this.currentIndex =" not in func_body, \
            "navigation.js loadMore() 成功分支不應含 this.currentIndex = 賦值（破壞 shared state contract）"

    def test_gemini_model_fallback_includes_check(self):
        """F2：testGeminiConnection() 成功後包含 includes() 檢查舊 model 是否在 allowlist"""
        js = self._settings_js()
        assert "modelNames.includes(this.form.geminiModel)" in js or \
               "includes(this.form.geminiModel)" in js, \
            "settings.js testGeminiConnection() 成功後應含 includes(this.form.geminiModel) allowlist 檢查"


class TestOpenAIErrorI18nGuard:
    """39a-PR-fix P1: 守衛 fetchOpenAIModels/testOpenAITranslation error 使用 window.t(errorKey) 翻譯"""

    def _js(self):
        return SETTINGS_JS.read_text(encoding="utf-8")

    def test_fetch_models_error_uses_i18n(self):
        """fetchOpenAIModels() error 分支使用 settings.status.openai_ 動態 errorKey 拼接"""
        js = self._js()
        # 截取 fetchOpenAIModels 函數體
        start = js.find("async fetchOpenAIModels(")
        assert start != -1, "settings.js 找不到 async fetchOpenAIModels( 函數"
        # 截取到下一個 async 函數起點（保守估計）
        next_async = js.find("async ", start + 1)
        func_body = js[start:next_async] if next_async != -1 else js[start:]
        assert "settings.status.openai_" in func_body, \
            "settings.js fetchOpenAIModels() error 分支應包含 settings.status.openai_ 動態 key 拼接"

    def test_translate_error_uses_i18n(self):
        """testOpenAITranslation() error 分支使用 settings.status.openai_ 動態 errorKey 拼接"""
        js = self._js()
        start = js.find("async testOpenAITranslation()")
        assert start != -1, "settings.js 找不到 async testOpenAITranslation() 函數"
        next_async = js.find("async ", start + 1)
        func_body = js[start:next_async] if next_async != -1 else js[start:]
        assert "settings.status.openai_" in func_body, \
            "settings.js testOpenAITranslation() error 分支應包含 settings.status.openai_ 動態 key 拼接"

    def test_fetch_catch_uses_i18n(self):
        """fetchOpenAIModels() catch 分支使用 window.t('settings.status.openai_connection_failed')"""
        js = self._js()
        assert "window.t('settings.status.openai_connection_failed')" in js, \
            "settings.js fetchOpenAIModels() catch 分支應使用 window.t('settings.status.openai_connection_failed')，不顯示裸 error.message"


class TestAutoFetchDirtyStateGuard:
    """39a-PR-fix P2: 守衛 auto-fallback 後同步 savedState，防止誤觸 dirty state"""

    def _js(self):
        return SETTINGS_JS.read_text(encoding="utf-8")

    def test_gemini_fallback_syncs_saved_state(self):
        """testGeminiConnection() auto-fallback 後同步 savedState.geminiModel"""
        js = self._js()
        assert "this.savedState.geminiModel" in js, \
            "settings.js testGeminiConnection() auto-fallback 後應同步 this.savedState.geminiModel，否則 isDirty 誤判"

    def test_openai_fallback_syncs_saved_state(self):
        """fetchOpenAIModels() auto-assign 後同步 savedState.openaiModel"""
        js = self._js()
        assert "this.savedState.openaiModel" in js, \
            "settings.js fetchOpenAIModels() auto-assign 後應同步 this.savedState.openaiModel，否則 isDirty 誤判"

    def test_openai_config_saves_use_custom_model(self):
        """saveConfig() openai 區段應含 use_custom_model，以便重載後還原 custom/select 模式"""
        js = self._js()
        assert "use_custom_model: this.openaiUseCustomModel" in js, \
            "settings.js saveConfig() 的 openai 物件應含 use_custom_model: this.openaiUseCustomModel，否則重載後 custom 模式丟失"

    def test_openai_config_loads_use_custom_model(self):
        """loadConfig() 應從 config 還原 openaiUseCustomModel，而非固定從 false 重設"""
        js = self._js()
        assert "config.translate.openai?.use_custom_model" in js, \
            "settings.js loadConfig() 應含 config.translate.openai?.use_custom_model 讀取，否則重載後 custom 模式無法還原"

    def test_fetch_openai_models_has_source_param(self):
        """fetchOpenAIModels() 應接受 source 參數，區分 auto-fetch 與手動 Fetch"""
        js = self._js()
        assert "source = 'manual'" in js, \
            "settings.js fetchOpenAIModels() 應含 source = 'manual' 預設參數，避免共享 boolean 競態"


MOTION_LAB_STATE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab-state.js"


class TestMotionLabStateGuard:
    """39b-T1: 守衛 motion_lab.html inline x-data 已抽離至 motion-lab-state.js"""

    def _html(self):
        return MOTION_LAB_HTML.read_text(encoding="utf-8")

    def _js(self):
        return MOTION_LAB_STATE_JS.read_text(encoding="utf-8")

    def test_motion_lab_html_uses_factory(self):
        """motion_lab.html 含 x-data="motionLabPage" """
        html = self._html()
        assert 'x-data="motionLabPage"' in html, \
            'motion_lab.html 應含 x-data="motionLabPage"（Alpine.data() 已正式註冊，去括號）'

    def test_motion_lab_html_no_inline_xdata_block(self):
        """motion_lab.html 的 x-data 屬性值不超過 100 字元（確保 inline 已移除）"""
        import re
        html = self._html()
        # 找所有 x-data 屬性值，確認無超過 100 字元的 inline 物件
        pattern = re.compile(r'x-data="([^"]{100,})"')
        matches = pattern.findall(html)
        assert len(matches) == 0, \
            f"motion_lab.html 仍有 {len(matches)} 處超過 100 字元的 x-data 屬性值（inline 物件未完整移除）"

    def test_motion_lab_state_js_exists(self):
        """web/static/js/pages/motion-lab-state.js 檔案存在"""
        assert MOTION_LAB_STATE_JS.exists(), \
            f"motion-lab-state.js 不存在：{MOTION_LAB_STATE_JS}"

    def test_motion_lab_state_js_has_factory_function(self):
        """motion-lab-state.js 含 function motionLabPage()"""
        js = self._js()
        assert "function motionLabPage()" in js, \
            "motion-lab-state.js 缺少 function motionLabPage()（factory function 宣告）"

    def test_motion_lab_state_js_has_init_method(self):
        """motion-lab-state.js 含 init()"""
        js = self._js()
        assert "init()" in js, \
            "motion-lab-state.js 缺少 init() method（Alpine 自動呼叫）"

    def test_motion_lab_state_js_has_destroy_method(self):
        """motion-lab-state.js 含 destroy()"""
        js = self._js()
        assert "destroy()" in js, \
            "motion-lab-state.js 缺少 destroy() method（清除 keydown 監聽）"

    def test_motion_lab_extra_js_loads_state(self):
        """motion_lab.html 的 extra_js block 含 motion-lab-state.js 引用"""
        html = self._html()
        assert "motion-lab-state.js" in html, \
            "motion_lab.html {% block extra_js %} 缺少 motion-lab-state.js script 引用"

    def test_motion_lab_state_js_no_defer(self):
        """載入 motion-lab-state.js 的 script tag 不含 defer 屬性"""
        import re
        html = self._html()
        # 找含 motion-lab-state.js 的 script tag
        pattern = re.compile(r'<script[^>]*motion-lab-state\.js[^>]*>')
        matches = pattern.findall(html)
        assert len(matches) > 0, \
            "motion_lab.html 找不到載入 motion-lab-state.js 的 script tag"
        for tag in matches:
            assert "defer" not in tag, \
                f"motion_lab.html 載入 motion-lab-state.js 的 script tag 不應含 defer 屬性：{tag}"


class TestScannerStateGuard:
    """39b-T2: 守衛 scanner.html inline script 已抽離至 scanner.js"""

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def test_scanner_extra_js_uses_scanner_js(self):
        """scanner.html 的 extra_js block 含 scanner.js 引用，且 inline <script> 不超過 10 行"""
        import re
        html = self._html()
        # 擷取 {% block extra_js %} 到 {% endblock %} 之間的內容
        pattern = re.compile(r'\{%-?\s*block extra_js\s*-?%\}(.*?)\{%-?\s*endblock\s*-?%\}', re.DOTALL)
        match = pattern.search(html)
        assert match is not None, "scanner.html 找不到 {% block extra_js %} 區段"
        block_content = match.group(1)

        # 必須包含 scanner.js 引用
        assert 'scanner.js' in block_content, \
            "scanner.html {% block extra_js %} 缺少 scanner.js script 引用"
        assert '<script src="/static/js/pages/scanner.js"></script>' in block_content, \
            "scanner.html {% block extra_js %} 應含 <script src=\"/static/js/pages/scanner.js\"></script>"

        # inline <script> 行數不超過 10 行（防止 inline JS 悄悄重新引入）
        inline_scripts = re.findall(r'<script(?:\s[^>]*)?>.*?</script>', block_content, re.DOTALL)
        for script_tag in inline_scripts:
            # 排除有 src 屬性的外部 script
            if 'src=' in script_tag:
                continue
            line_count = script_tag.count('\n') + 1
            assert line_count <= 10, \
                f"scanner.html extra_js 區段含超過 10 行的 inline <script>（{line_count} 行），應將 JS 移至 scanner.js"

    def test_scanner_no_inline_script(self):
        """scanner.html 的 extra_js 區段不含超過 10 行的 inline script"""
        import re
        html = self._html()
        pattern = re.compile(r'\{%-?\s*block extra_js\s*-?%\}(.*?)\{%-?\s*endblock\s*-?%\}', re.DOTALL)
        match = pattern.search(html)
        assert match is not None, "scanner.html 找不到 {% block extra_js %} 區段"
        block_content = match.group(1)
        # 確認區段內沒有 inline script（只有含 src 的外部 script 標籤）
        inline_scripts = re.findall(r'<script(?:\s[^>]*)?>.*?</script>', block_content, re.DOTALL)
        for script_tag in inline_scripts:
            if 'src=' in script_tag:
                continue
            line_count = script_tag.count('\n') + 1
            assert line_count <= 10, \
                f"scanner.html extra_js 含超過 10 行 inline script（{line_count} 行）"


class TestCtaI18nGuard:
    """39c-T1: 守衛 CTA 文案重構 — 四語系 5 個核心 key 的新值"""

    # 5 個核心 CTA key 的預期新值（各語系）
    EXPECTED = {
        "zh_TW.json": {
            "search.button.search_all": "批次搜尋",
            "search.filelist.scrape_all": "批次整理",
            "search.filelist.scrape_nfo": "整理此片",
            "help.batch.h6_generate_all": "批次整理",
            "search.filelist.scrape_all_title": "整理所有已搜尋的檔案（重命名 + 建資料夾 + NFO）",
        },
        "zh_CN.json": {
            "search.button.search_all": "批量搜索",
            "search.filelist.scrape_all": "批量整理",
            "search.filelist.scrape_nfo": "整理此片",
            "help.batch.h6_generate_all": "批量整理",
            "search.filelist.scrape_all_title": "整理所有已搜索的文件（重命名 + 建文件夹 + NFO）",
        },
        "en.json": {
            "search.button.search_all": "Batch Search",
            "search.filelist.scrape_all": "Batch Organize",
            "search.filelist.scrape_nfo": "Organize",
            "help.batch.h6_generate_all": "Batch Organize",
            "search.filelist.scrape_all_title": "Organize all searched files (rename + folder + NFO)",
        },
        "ja.json": {
            "search.button.search_all": "一括検索",
            "search.filelist.scrape_all": "一括整理",
            "search.filelist.scrape_nfo": "この作品を整理",
            "help.batch.h6_generate_all": "一括整理",
            "search.filelist.scrape_all_title": "検索済みのファイルをすべて整理（リネーム + フォルダ作成 + NFO）",
        },
    }

    def _locale(self, name):
        return json.loads((LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    def test_zh_tw_cta_keys(self):
        """zh_TW.json 5 個 CTA key 新值正確"""
        data = self._locale("zh_TW.json")
        for key, expected in self.EXPECTED["zh_TW.json"].items():
            actual = self._get_nested(data, key)
            assert actual == expected, \
                f"zh_TW.json {key} 期望 {expected!r}，實際 {actual!r}"

    def test_zh_cn_cta_keys(self):
        """zh_CN.json 5 個 CTA key 新值正確"""
        data = self._locale("zh_CN.json")
        for key, expected in self.EXPECTED["zh_CN.json"].items():
            actual = self._get_nested(data, key)
            assert actual == expected, \
                f"zh_CN.json {key} 期望 {expected!r}，實際 {actual!r}"

    def test_en_cta_keys(self):
        """en.json 5 個 CTA key 新值正確"""
        data = self._locale("en.json")
        for key, expected in self.EXPECTED["en.json"].items():
            actual = self._get_nested(data, key)
            assert actual == expected, \
                f"en.json {key} 期望 {expected!r}，實際 {actual!r}"

    def test_ja_cta_keys(self):
        """ja.json 5 個 CTA key 新值正確"""
        data = self._locale("ja.json")
        for key, expected in self.EXPECTED["ja.json"].items():
            actual = self._get_nested(data, key)
            assert actual == expected, \
                f"ja.json {key} 期望 {expected!r}，實際 {actual!r}"


class TestScrapeProgressI18nGuard:
    """39c-T2b: 守衛 scrape progress 進度文字 — 四語系 organizing_prefix key"""

    EXPECTED = {
        "zh_TW.json": {
            "search.filelist.organizing_prefix": "整理中",
        },
        "zh_CN.json": {
            "search.filelist.organizing_prefix": "整理中",
        },
        "en.json": {
            "search.filelist.organizing_prefix": "Organizing",
        },
        "ja.json": {
            "search.filelist.organizing_prefix": "整理中",
        },
    }

    def _locale(self, name):
        return json.loads((LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    def test_all_locales_have_organizing_prefix(self):
        """四語系 JSON 都有 search.filelist.organizing_prefix key 且值正確"""
        for locale_file, keys in self.EXPECTED.items():
            data = self._locale(locale_file)
            for key, expected in keys.items():
                actual = self._get_nested(data, key)
                assert actual is not None, \
                    f"{locale_file} 缺少 key: {key}"
                assert actual != "", \
                    f"{locale_file} {key} 值不可為空字串"
                assert actual == expected, \
                    f"{locale_file} {key} 期望 {expected!r}，實際 {actual!r}"

    def test_search_html_uses_organizing_prefix(self):
        """search.html 包含 organizing_prefix 字串（確認 HTML 已引用此 key）"""
        search_html = (LOCALES_ROOT.parent / "web" / "templates" / "search.html").read_text(encoding="utf-8")
        assert "organizing_prefix" in search_html, \
            "search.html 未引用 search.filelist.organizing_prefix（請確認 scrape progress section 已插入）"




class TestScrapeToastI18nGuard:
    """39c-T2c: 守衛批次完成 toast — 四語系 7 個 search.toast.* keys 存在且非空"""

    EXPECTED_KEYS = [
        'no_searchable_files',
        'search_complete',
        'no_scrapable_files',
        'scrape_complete',
        'scrape_complete_dup',
        'no_search_results',
        'scrape_failed',
    ]

    def _locale(self, name):
        return json.loads((LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    @pytest.mark.parametrize('locale', ['zh_TW', 'zh_CN', 'en', 'ja'])
    def test_all_locales_have_toast_keys(self, locale):
        """四語系 search.toast.* 必須全部存在且非空"""
        data = self._locale(f"{locale}.json")
        for key in self.EXPECTED_KEYS:
            dotted = f"search.toast.{key}"
            val = self._get_nested(data, dotted)
            assert val is not None, \
                f"{locale}.json 缺少 key: {dotted}"
            assert isinstance(val, str) and len(val) > 0, \
                f"{locale}.json {dotted} 值不可為空字串"


SEARCH_STATE_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state"


class TestNoAlertInSearchJs:
    """39c-T2c: search state JS 不應使用原生 alert()，改用 showToast"""

    def test_no_alert_in_batch_js(self):
        content = (SEARCH_STATE_DIR / "batch.js").read_text(encoding="utf-8")
        assert "alert(" not in content, \
            "batch.js 含原生 alert()，應改用 this.showToast()"


class TestNavigateLoadMore:
    """T3b 守衛：navigate() 在最後一片時 await loadMore + state-first slide"""

    NAVIGATION_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"

    def _js(self):
        return self.NAVIGATION_JS.read_text(encoding="utf-8")

    def _navigate_body(self):
        """截取 navigate() 函數體"""
        js = self._js()
        start = js.find("navigate(delta)")
        assert start != -1, "navigation.js 找不到 navigate(delta) 函數"
        return js[start:start + 3000]

    def test_navigate_is_async(self):
        js = self._js()
        assert "async navigate(delta)" in js

    def test_navigate_awaits_load_more_detail(self):
        body = self._navigate_body()
        assert "await this.loadMore('detail')" in body

    def test_navigate_sets_currentindex_from_result(self):
        body = self._navigate_body()
        assert "this.currentIndex = result.oldLength" in body

    def test_navigate_plays_slide_in_after_loadmore(self):
        body = self._navigate_body()
        state_pos = body.find("this.currentIndex = result.oldLength")
        slide_in_pos = body.find("playSlideIn", state_pos if state_pos != -1 else 0)
        assert state_pos != -1 and slide_in_pos != -1
        assert state_pos < slide_in_pos


class TestNextLightboxLoadMore:
    """T3c 守衛：nextLightboxVideo() 在最後一片時 await loadMore + state-first crossfade"""

    def _js(self):
        return GRID_MODE_JS.read_text(encoding="utf-8")

    def _next_lightbox_body(self):
        """截取 nextLightboxVideo() 函數體"""
        js = self._js()
        start = js.find("nextLightboxVideo()")
        assert start != -1, "grid-mode.js 找不到 nextLightboxVideo() 函數"
        return js[start:start + 3000]

    def test_next_lightbox_is_async(self):
        """T3c: nextLightboxVideo() 必須是 async（await loadMore 需要）"""
        js = self._js()
        assert "async nextLightboxVideo()" in js, \
            "grid-mode.js nextLightboxVideo() 應改為 async（T3c await loadMore 需要）"

    def test_next_lightbox_awaits_load_more_lightbox(self):
        """T3c: nextLightboxVideo() 使用 await this.loadMore('lightbox')"""
        body = self._next_lightbox_body()
        assert "await this.loadMore('lightbox')" in body, \
            "grid-mode.js nextLightboxVideo() 缺少 await this.loadMore('lightbox')（T3c fire-and-forget 已改為 await）"

    def test_next_lightbox_sets_current_index(self):
        """T3c: nextLightboxVideo() loadMore 成功後設定 currentIndex = result.oldLength（state-first）"""
        body = self._next_lightbox_body()
        assert "this.currentIndex = result.oldLength" in body, \
            "grid-mode.js nextLightboxVideo() 缺少 this.currentIndex = result.oldLength（T3c state-first）"

    def test_next_lightbox_sets_lightbox_index(self):
        """T3c: nextLightboxVideo() loadMore 成功後設定 lightboxIndex = result.oldLength（state-first）"""
        body = self._next_lightbox_body()
        assert "this.lightboxIndex = result.oldLength" in body, \
            "grid-mode.js nextLightboxVideo() 缺少 this.lightboxIndex = result.oldLength（T3c state-first）"

    def test_next_lightbox_plays_switch_after_state(self):
        """T3c: nextLightboxVideo() loadMore 成功後 playLightboxSwitch 在 state 更新之後（animate 在 state 後）"""
        body = self._next_lightbox_body()
        state_pos = body.find("this.currentIndex = result.oldLength")
        switch_pos = body.find("playLightboxSwitch", state_pos if state_pos != -1 else 0)
        assert state_pos != -1, "nextLightboxVideo() 缺少 this.currentIndex = result.oldLength"
        assert switch_pos != -1, \
            "nextLightboxVideo() loadMore 成功後缺少 playLightboxSwitch（T3c 動畫觸發缺失）"
        assert state_pos < switch_pos, \
            "T3c 違反 state-first：currentIndex 更新必須在 playLightboxSwitch 之前"


RESULT_CARD_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js"
PATH_UTILS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "components" / "path-utils.js"
FILE_LIST_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "file-list.js"


class TestUserTagsApiGuard:
    """41b-T3: 確保 confirmAddTag 和 removeUserTag 改接 /api/user-tags API"""

    def _result_card(self):
        return RESULT_CARD_JS.read_text(encoding="utf-8")

    def _path_utils(self):
        return PATH_UTILS_JS.read_text(encoding="utf-8")

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _locale(self, name):
        return json.loads((LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    def test_confirm_add_tag_calls_user_tags_api(self):
        """confirmAddTag() 程式碼含 /api/user-tags fetch call"""
        content = self._result_card()
        assert "user-tags" in content, \
            "result-card.js 缺少 /api/user-tags 呼叫（confirmAddTag 應改接 API）"

    def test_confirm_add_tag_is_async(self):
        """confirmAddTag() 是 async 函數"""
        content = self._result_card()
        assert "async confirmAddTag()" in content, \
            "result-card.js confirmAddTag() 應改為 async（API fetch 需要）"

    def test_remove_user_tag_calls_user_tags_api(self):
        """removeUserTag() 程式碼含 /api/user-tags fetch call"""
        content = self._result_card()
        # 確認 removeUserTag 區塊有 fetch 呼叫
        start = content.find("async removeUserTag(")
        assert start != -1, \
            "result-card.js removeUserTag() 應改為 async（API fetch 需要）"
        func_body = content[start:start + 1500]
        assert "user-tags" in func_body, \
            "result-card.js removeUserTag() 內缺少 /api/user-tags 呼叫"

    def test_remove_user_tag_is_async(self):
        """removeUserTag() 是 async 函數"""
        content = self._result_card()
        assert "async removeUserTag(" in content, \
            "result-card.js removeUserTag() 應改為 async（API fetch 需要）"

    def test_result_card_does_not_use_path_to_file_uri(self):
        """result-card.js 不再呼叫 pathToFileUri()（路徑契約：禁止 JS 手刻 file:///）"""
        content = self._result_card()
        assert "pathToFileUri" not in content, \
            "result-card.js 仍呼叫 pathToFileUri()，違反路徑契約：前端應直接傳 file.path，讓後端正規化"

    def test_path_utils_does_not_have_path_to_file_uri(self):
        """path-utils.js 不含 pathToFileUri 函數定義（已刪除，防止誤用）"""
        content = self._path_utils()
        assert "pathToFileUri" not in content, \
            "path-utils.js 仍含 pathToFileUri 函數，應已刪除（WSL 環境下會產生錯誤 URI）"

    def test_path_utils_still_has_path_to_display(self):
        """path-utils.js 仍保留 pathToDisplay 函數"""
        content = self._path_utils()
        assert "pathToDisplay" in content, \
            "path-utils.js 缺少 pathToDisplay 函數（用於前端顯示路徑）"

    def test_confirm_add_tag_no_direct_push(self):
        """confirmAddTag() 不再直接 c.user_tags.push(tag)（已改為 API response 更新）"""
        content = self._result_card()
        # 找到 confirmAddTag 函數體，確認沒有直接 push 且不先呼叫 API
        start = content.find("async confirmAddTag()")
        assert start != -1, "result-card.js 找不到 async confirmAddTag() 函數"
        # 截取函數體（到下一個同層函數前）
        func_body = content[start:start + 2000]
        # 如果有 push(tag)，只允許在 API 成功分支後的 saveState 附近（不應該在 API 前直接 push）
        # 最簡單守衛：直接 c.user_tags.push(tag) 不應在函數內出現
        assert "c.user_tags.push(tag)" not in func_body, \
            "result-card.js confirmAddTag() 仍直接 c.user_tags.push(tag)，應改為 API response 更新"

    def test_add_button_has_file_mode_guard(self):
        """+ 按鈕 x-show 含 listMode === 'file' guard"""
        html = self._html()
        assert "listMode === 'file'" in html, \
            "search.html + 按鈕缺少 listMode === 'file' guard（應僅在 file 模式顯示）"

    def test_add_button_has_file_path_guard(self):
        """+ 按鈕 x-show 含 fileList[currentFileIndex]?.path guard"""
        html = self._html()
        assert "fileList[currentFileIndex]?.path" in html, \
            "search.html + 按鈕缺少 fileList[currentFileIndex]?.path guard"

    def test_user_tags_stored_at_file_level(self):
        """confirmAddTag/removeUserTag 更新 fileList[currentFileIndex].user_tags（P2: file-level）"""
        content = self._result_card()
        assert "fileList[this.currentFileIndex].user_tags" in content, \
            "result-card.js 未將 user_tags 寫入 fileList[currentFileIndex].user_tags（應為 file-level）"

    def test_current_user_tags_method_exists(self):
        """result-card.js 含 currentUserTags() helper（P2: file-level user_tags）"""
        content = self._result_card()
        assert "currentUserTags()" in content, \
            "result-card.js 缺少 currentUserTags() method（P2: user_tags 應從 file-level 讀取）"

    def test_template_uses_current_user_tags(self):
        """search.html 用戶標籤 template 使用 currentUserTags()（P2）"""
        html = self._html()
        assert "currentUserTags()" in html, \
            "search.html 用戶標籤 template 仍用 current().user_tags，應改為 currentUserTags()"

    def test_set_file_list_initializes_user_tags(self):
        """file-list.js setFileList 給每個 file 初始化 user_tags: []（P2）"""
        content = (FILE_LIST_JS).read_text(encoding="utf-8")
        assert "user_tags: []" in content, \
            "file-list.js setFileList 未初始化 user_tags: []（切換 file 前 user_tags 為 undefined）"

    def test_tag_api_failed_key_exists_all_locales(self):
        """四語系 search.error.tag_api_failed key 都存在"""
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            val = self._get_nested(data, "search.error.tag_api_failed")
            assert val, f"{locale_file} 缺少 search.error.tag_api_failed key"

    def test_fetch_user_tags_method_exists(self):
        """result-card.js 含 fetchUserTagsForCurrent() 補查方法"""
        content = self._result_card()
        assert "fetchUserTagsForCurrent" in content, \
            "result-card.js 缺少 fetchUserTagsForCurrent() 方法（策略二：前端補查 user_tags）"

    def test_fetch_user_tags_writes_to_file_level(self):
        """fetchUserTagsForCurrent 把結果寫入 file-level user_tags（P2）
        實作使用 captured file ref（race-safe pattern）：
        const file = this.fileList?.[this.currentFileIndex]; ... file.user_tags = ...
        """
        content = self._result_card()
        start = content.find("async fetchUserTagsForCurrent()")
        assert start != -1, "result-card.js 找不到 fetchUserTagsForCurrent()"
        func_body = content[start:start + 800]
        # 接受兩種等效寫法：
        # 1. 直接索引：fileList[this.currentFileIndex].user_tags
        # 2. captured ref（race-safe）：const file = ...; file.user_tags = ...
        has_direct = "fileList[this.currentFileIndex].user_tags" in func_body
        has_captured_ref = ("file.user_tags" in func_body and
                            "this.fileList?.[this.currentFileIndex]" in func_body)
        assert has_direct or has_captured_ref, \
            "fetchUserTagsForCurrent 未寫入 file-level user_tags（P2: 需有 fileList[idx].user_tags 或 captured ref file.user_tags）"


class TestShowcaseActressTemplate:
    """Phase 44a-T3: 守衛 showcase.html 含有女優模式 UI 結構"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_toggle_actress_mode_button(self):
        """toolbar search 區域含 toggleActressMode() binding"""
        html = self._html()
        assert "toggleActressMode()" in html, \
            "showcase.html 缺少 toggleActressMode() binding（mode toggle button）"

    def test_show_favorite_actresses_binding(self):
        """showFavoriteActresses 出現於 template"""
        html = self._html()
        assert "showFavoriteActresses" in html, \
            "showcase.html 缺少 showFavoriteActresses binding"

    def test_actress_search_input(self):
        """actressSearch x-model 存在於 template"""
        html = self._html()
        assert "actressSearch" in html, \
            "showcase.html 缺少 actressSearch x-model（女優搜尋框）"

    def test_actress_grid_x_for(self):
        """paginatedActresses x-for 存在於 template"""
        html = self._html()
        assert "paginatedActresses" in html, \
            "showcase.html 缺少 paginatedActresses x-for（女優 grid 迴圈）"

    def test_actress_card_class(self):
        """actress-card class 出現於 template"""
        html = self._html()
        assert "actress-card" in html, \
            "showcase.html 缺少 actress-card class（女優卡片）"

    def test_actress_card_flip_id(self):
        """'actress:' data-flip-id pattern 出現於 template"""
        html = self._html()
        assert "'actress:'" in html, \
            "showcase.html 缺少 'actress:' data-flip-id pattern（FLIP 動畫 key）"

    def test_actress_card_click_opens_lightbox(self):
        """openActressLightbox(index) binding 出現於 template"""
        html = self._html()
        assert "openActressLightbox(index)" in html, \
            "showcase.html 缺少 openActressLightbox(index) binding（女優卡片點擊）"

    def test_actress_loading_state(self):
        """actressLoading binding 出現於 template"""
        html = self._html()
        assert "actressLoading" in html, \
            "showcase.html 缺少 actressLoading binding（loading spinner）"

    def test_actress_empty_state(self):
        """actressCount === 0 條件出現於 template"""
        html = self._html()
        assert "actressCount === 0" in html, \
            "showcase.html 缺少 actressCount === 0 條件（empty state）"

    def test_actress_photo_url_binding(self):
        """actress.photo_url 出現於 template"""
        html = self._html()
        assert "actress.photo_url" in html, \
            "showcase.html 缺少 actress.photo_url binding（女優照片）"

    def test_actress_no_photo_placeholder(self):
        """actress-no-photo class 出現於 template"""
        html = self._html()
        assert "actress-no-photo" in html, \
            "showcase.html 缺少 actress-no-photo class（無照片 placeholder）"

    def test_actress_card_footer(self):
        """actress-card-footer class 出現於 template"""
        html = self._html()
        assert "actress-card-footer" in html, \
            "showcase.html 缺少 actress-card-footer class（卡片 footer）"

    def test_actress_sort_dropdown(self):
        """actress sort options 出現於 template（actressSort binding）"""
        html = self._html()
        assert "actressSort" in html, \
            "showcase.html 缺少 actressSort binding（女優排序 dropdown）"

    def test_video_controls_conditional(self):
        """!showFavoriteActresses 條件用於 video controls 的 x-show"""
        html = self._html()
        assert "!showFavoriteActresses" in html, \
            "showcase.html 缺少 !showFavoriteActresses（video controls x-show 條件）"


class TestShowcaseActressLightbox:
    """Phase 44a-T4: Actress Lightbox 5-row layout + chips +N + nav dispatch 守衛"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    # --- showcase.html x-if branches ---

    def test_actress_x_if_branch(self):
        """showcase.html 含 x-if="currentLightboxActress" 分支"""
        html = self._html()
        assert "currentLightboxActress" in html, \
            "showcase.html 缺少 currentLightboxActress（女優 lightbox x-if 分支）"

    def test_video_x_if_branch(self):
        """showcase.html 含 currentLightboxVideo && !currentLightboxActress video branch"""
        html = self._html()
        assert "currentLightboxVideo && !currentLightboxActress" in html, \
            "showcase.html 缺少 currentLightboxVideo && !currentLightboxActress（video x-if 包裝）"

    def test_actress_lightbox_meta(self):
        """showcase.html 含 actress-lightbox-meta class"""
        html = self._html()
        assert "actress-lightbox-meta" in html, \
            "showcase.html 缺少 actress-lightbox-meta class（女優 lightbox metadata wrapper）"

    def test_lb_chips_more(self):
        """showcase.html 含 lb-chips-more class（chips +N badge）"""
        html = self._html()
        assert "lb-chips-more" in html, \
            "showcase.html 缺少 lb-chips-more class（chips +N 展開 badge）"

    def test_nav_actress_dispatch(self):
        """showcase.html nav arrows 含 prevActressLightbox() dispatch"""
        html = self._html()
        assert "prevActressLightbox()" in html, \
            "showcase.html nav arrows 缺少 prevActressLightbox() dispatch（showFavoriteActresses 模式）"

    # --- core.js new methods ---

    def test_actress_core_metadata_method(self):
        """core.js 含 _actressCoreMetadata() 方法"""
        js = self._js()
        assert "_actressCoreMetadata" in js, \
            "showcase/core.js 缺少 _actressCoreMetadata() 方法（Row 2 metadata 串接）"

    def test_all_info_chips_method(self):
        """core.js 含 _allInfoChips() 方法"""
        js = self._js()
        assert "_allInfoChips" in js, \
            "showcase/core.js 缺少 _allInfoChips() 方法（Row 4 info chips 合併）"

    def test_chips_limit_method(self):
        """core.js 含 _chipsLimit() 方法"""
        js = self._js()
        assert "_chipsLimit" in js, \
            "showcase/core.js 缺少 _chipsLimit() 方法（desktop 10 / mobile 6 chips 上限）"

    def test_visible_aliases_method(self):
        """core.js 含 _visibleAliases() 方法"""
        js = self._js()
        assert "_visibleAliases" in js, \
            "showcase/core.js 缺少 _visibleAliases() 方法（Row 3 aliases chips 分頁）"

    def test_visible_info_chips_method(self):
        """core.js 含 _visibleInfoChips() 方法"""
        js = self._js()
        assert "_visibleInfoChips" in js, \
            "showcase/core.js 缺少 _visibleInfoChips() 方法（Row 4 info chips 分頁）"

    def test_visible_video_tags_method(self):
        """core.js 含 _visibleVideoTags() 方法"""
        js = self._js()
        assert "_visibleVideoTags" in js, \
            "showcase/core.js 缺少 _visibleVideoTags() 方法（video tag chips +N）"


class TestShowcaseActressCRUD:
    """Phase 44a-T5: Actress CRUD — addFavoriteActress / rescrapeActress / removeActress 守衛"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    # --- core.js method guards ---

    def test_add_favorite_actress_method(self):
        """core.js 含 addFavoriteActress() 方法"""
        js = self._js()
        assert "addFavoriteActress" in js, \
            "showcase/core.js 缺少 addFavoriteActress() 方法（[+ 新增] 女優 CRUD）"

    def test_rescrape_actress_method(self):
        """core.js 含 rescrapeActress() 方法"""
        js = self._js()
        assert "rescrapeActress" in js, \
            "showcase/core.js 缺少 rescrapeActress() 方法（[🔄 重新抓取] 女優 CRUD）"

    def test_remove_actress_method(self):
        """core.js 含 removeActress() 方法"""
        js = self._js()
        assert "removeActress" in js, \
            "showcase/core.js 缺少 removeActress() 方法（[🗑 移除最愛] 女優 CRUD）"

    # --- showcase.html popover guards ---

    def test_add_popover_in_template(self):
        """showcase.html 含 _addActressName binding（[+ 新增] popover input）"""
        html = self._html()
        assert "_addActressName" in html, \
            "showcase.html 缺少 _addActressName（[+ 新增] popover 的 x-model binding）"

    def test_add_handler_in_template(self):
        """showcase.html 含 addFavoriteActress() handler"""
        html = self._html()
        assert "addFavoriteActress()" in html, \
            "showcase.html 缺少 addFavoriteActress()（[+ 新增] 按鈕 @click handler）"

    def test_rescrape_handler_in_template(self):
        """showcase.html 含 rescrapeActress() handler"""
        html = self._html()
        assert "rescrapeActress()" in html, \
            "showcase.html 缺少 rescrapeActress()（Row 6 重新抓取按鈕 @click handler）"

    def test_remove_handler_in_template(self):
        """showcase.html 含 removeActress() handler"""
        html = self._html()
        assert "removeActress()" in html, \
            "showcase.html 缺少 removeActress()（Row 6 移除最愛按鈕 @click handler）"
