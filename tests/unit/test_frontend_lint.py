"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
import json
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

    def test_no_auto_trigger_in_init(self):
        """init() 後的 loadStats 呼叫後，不應緊接 checkJellyfinImages()"""
        # 確認 checkJellyfinImages() 只透過 @click 觸發，不在 init() 或 loadStats 後出現
        html = self._html()
        assert "this.loadStats();\n        this.checkJellyfinImages();" not in html, \
            "scanner.html init() 仍含自動觸發 checkJellyfinImages()"

    def test_jellyfin_check_state_declared(self):
        """Alpine data 宣告 jellyfinCheckState 欄位"""
        html = self._html()
        assert "jellyfinCheckState: 'idle'" in html, \
            "scanner.html 缺少 jellyfinCheckState: 'idle' 初始化宣告"

    def test_jellyfin_check_controller_declared(self):
        """Alpine data 宣告 _jellyfinCheckController 欄位"""
        html = self._html()
        assert "_jellyfinCheckController: null" in html, \
            "scanner.html 缺少 _jellyfinCheckController: null 初始化宣告"

    def test_abort_controller_used_in_check(self):
        """checkJellyfinImages() 建立 AbortController"""
        html = self._html()
        assert "new AbortController()" in html, \
            "scanner.html checkJellyfinImages() 缺少 new AbortController()"

    def test_abort_called_in_cleanup(self):
        """cleanup 回呼內含 _jellyfinCheckController.abort()"""
        html = self._html()
        assert "_jellyfinCheckController.abort()" in html, \
            "scanner.html cleanup 缺少 _jellyfinCheckController.abort()"

    def test_jellyfin_check_state_reset_in_cleanup(self):
        """cleanup 回呼補上 jellyfinCheckState = 'idle' 重設"""
        html = self._html()
        assert "jellyfinCheckState = 'idle'" in html, \
            "scanner.html cleanup 缺少 jellyfinCheckState = 'idle' 重設"

    def test_should_warn_checks_jellyfin_checking(self):
        """shouldWarnBeforeLeave() 含 jellyfinCheckState === 'checking' 判斷"""
        html = self._html()
        assert "jellyfinCheckState === 'checking'" in html, \
            "scanner.html shouldWarnBeforeLeave() 缺少 jellyfinCheckState === 'checking' 判斷"

    def test_trigger_button_click_handler(self):
        """觸發按鈕 @click 呼叫 checkJellyfinImages()"""
        html = self._html()
        assert '@click="checkJellyfinImages()"' in html, \
            "scanner.html 缺少 @click=\"checkJellyfinImages()\" 觸發按鈕"

    def test_no_auto_trigger_after_generate(self):
        """generate SSE done 事件後無自動呼叫 checkJellyfinImages()"""
        html = self._html()
        # loadStats 後面不應接 checkJellyfinImages（generate 路徑）
        assert "this.loadStats();\n                    this.checkJellyfinImages();" not in html, \
            "scanner.html generate done 路徑仍自動呼叫 checkJellyfinImages()"

    def test_clear_cache_resets_jellyfin_state(self):
        """clearCache 成功後含 jellyfinCheckState = 'idle' 重設"""
        html = self._html()
        # jellyfinImageVisible = false 後緊接 jellyfinCheckState = 'idle'
        assert "jellyfinImageVisible = false" in html, \
            "scanner.html clearCache 缺少 jellyfinImageVisible = false"
        # jellyfinCheckState = 'idle' 在 clearCache 函數中也必須出現
        # （在 shouldWarnBeforeLeave 和 beforeLeave 都有，此守衛確認 clearCache 路徑有）
        # 用計數確認至少 2 處（cleanup + clearCache，shouldWarnBeforeLeave 判斷不算 assignment）
        count = html.count("jellyfinCheckState = 'idle'")
        assert count >= 2, \
            f"scanner.html jellyfinCheckState = 'idle' 出現 {count} 次，期望 >= 2（cleanup + clearCache）"

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
        html = self._html()
        # 確認 runJellyfinImageUpdate 的 done 分支有三個重設欄位
        assert "this.jellyfinImageVisible = false" in html, \
            "scanner.html runJellyfinImageUpdate done 缺少 jellyfinImageVisible = false 重設"
        assert "this.jellyfinImageCount = 0" in html, \
            "scanner.html runJellyfinImageUpdate done 缺少 jellyfinImageCount = 0 重設"
        # jellyfinCheckState = 'idle' 重設（update done 分支使用 this. 前綴）
        assert "this.jellyfinCheckState = 'idle'" in html, \
            "scanner.html runJellyfinImageUpdate done 缺少 this.jellyfinCheckState = 'idle' 重設"


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
