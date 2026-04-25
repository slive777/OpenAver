"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
import json
import re
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

    def _extract_searchable_fields(self, js: str) -> set[str]:
        """從 core.js 抓出 `const searchable = [ ... ].filter(Boolean)` 的 array literal，
        回傳所有 `video.XXX` 欄位成一個 set。

        Structural guard：只解析真正 array literal 內容，不受註解或其他函數干擾。
        若重構移除整個 array 或改名，此 helper 會回傳空集合導致測試失敗。
        """
        match = re.search(
            r'const\s+searchable\s*=\s*\[(.*?)\]\.filter\(Boolean\)',
            js,
            re.DOTALL,
        )
        if not match:
            return set()
        array_body = match.group(1)
        return set(re.findall(r'video\.(\w+)', array_body))

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

    def test_searchable_includes_user_tags(self):
        """searchable fields 包含 video.user_tags（用戶自訂 tag 需可搜尋）"""
        js = self._js()
        assert "video.user_tags" in js, \
            "showcase/core.js applyFilterAndSort searchable 缺少 video.user_tags"

    def test_searchable_array_structure(self):
        """Structural guard: 必要欄位都必須在 `const searchable = [...]` array literal 內，
        而非只存在於註解或其他函數中。若 applyFilterAndSort 被移除或 searchable 改名，
        helper 回傳空集合，此測試會 fail。
        """
        js = self._js()
        fields = self._extract_searchable_fields(js)

        assert fields, (
            "找不到 `const searchable = [...].filter(Boolean)` array literal；"
            "applyFilterAndSort 可能已被移除或 searchable 已改名"
        )

        required = {
            "title",
            "original_title",
            "actresses",
            "number",
            "maker",
            "tags",
            "release_date",
            "path",
            "director",
            "series",
            "label",
            "user_tags",
        }
        missing = required - fields
        assert not missing, (
            f"showcase/core.js searchable array literal 缺少必要欄位: "
            f"{sorted(missing)}（實際欄位: {sorted(fields)}）"
        )


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
SEARCH_FILE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "file.js"


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


class TestActressLightboxSourceGuard:
    """49a-T5: Actress Lightbox source state guard（CD-9 顯式 state 取代物件 identity 判斷）

    驗證：
    - init state 含 actressLightboxSource: null
    - openHeroCardLightbox 函數體設 'hero'
    - openActressLightbox 函數體至少 2 處設 'grid'（首次進入 + 切換女優分支）
    - closeLightbox 函數體 reset null
    - showcase.html camera button 含 x-show="actressLightboxSource === 'grid'"
    """

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method（methodName(...) { ... }）函式主體，大括號平衡。"""
        pattern = re.compile(
            r'(?:^|\n)\s*' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"showcase/core.js 找不到 {method_name} 方法"
        start = m.end()  # 位於 { 之後
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_init_state_present(self):
        """core.js Alpine state 含 actressLightboxSource: null（容忍空白）"""
        js = self._js()
        assert re.search(r'actressLightboxSource\s*:\s*null', js), \
            "showcase/core.js 缺少 Alpine state 屬性 actressLightboxSource: null"

    def test_open_hero_card_sets_hero(self):
        """openHeroCardLightbox 函數體設 this.actressLightboxSource = 'hero'"""
        js = self._js()
        body = self._extract_method_body(js, 'openHeroCardLightbox')
        assert re.search(r"this\.actressLightboxSource\s*=\s*['\"]hero['\"]", body), \
            "showcase/core.js openHeroCardLightbox 函數體缺少 this.actressLightboxSource = 'hero'"

    def test_open_actress_lightbox_sets_grid(self):
        """openActressLightbox 函數體至少 2 處設 'grid'（首次進入 + 切換女優分支）"""
        js = self._js()
        body = self._extract_method_body(js, 'openActressLightbox')
        matches = re.findall(r"this\.actressLightboxSource\s*=\s*['\"]grid['\"]", body)
        assert len(matches) >= 2, \
            f"showcase/core.js openActressLightbox 應至少 2 處設 'grid'（首次進入 + 切換女優），目前 {len(matches)} 處"

    def test_close_resets_null(self):
        """closeLightbox 函數體 reset this.actressLightboxSource = null"""
        js = self._js()
        body = self._extract_method_body(js, 'closeLightbox')
        assert re.search(r"this\.actressLightboxSource\s*=\s*null", body), \
            "showcase/core.js closeLightbox 函數體缺少 this.actressLightboxSource = null（reset）"

    def test_camera_button_x_show_binding(self):
        """showcase.html camera button 含 x-show=\"actressLightboxSource === 'grid'\""""
        html = self._html()
        assert "actressLightboxSource === 'grid'" in html, \
            "showcase.html camera button 缺少 x-show=\"actressLightboxSource === 'grid'\" 綁定"


class TestShowcasePreciseMatchState:
    """Phase 44b-T1: Showcase 精準匹配 Alpine state 守衛"""

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def _extract_fn_block(self, content, fn_anchor):
        """提取從 fn_anchor 開始到下一個頂層逗號的函數區塊"""
        start = content.find(fn_anchor)
        if start == -1:
            return ''
        return content[start:start + 2000]

    # --- Module-level flag ---
    def test_actressesLoaded_flag_exists(self):
        """var _actressesLoaded 存在於 module scope"""
        js = self._js()
        assert "var _actressesLoaded" in js, \
            "showcase/core.js 缺少 module-level var _actressesLoaded"

    # --- Alpine state properties ---
    def test_isPreciseActressMatch_state_exists(self):
        """_isPreciseActressMatch 出現於 Alpine state"""
        js = self._js()
        assert "_isPreciseActressMatch" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _isPreciseActressMatch"

    def test_matchedActress_state_exists(self):
        """_matchedActress 出現於 Alpine state"""
        js = self._js()
        assert "_matchedActress" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _matchedActress"

    def test_preciseMatchSource_state_exists(self):
        """_preciseMatchSource 出現於 Alpine state"""
        js = self._js()
        assert "_preciseMatchSource" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _preciseMatchSource"

    def test_favoriteHeartLoading_state_exists(self):
        """_favoriteHeartLoading 出現於 Alpine state"""
        js = self._js()
        assert "_favoriteHeartLoading" in js, \
            "showcase/core.js 缺少 Alpine state 屬性 _favoriteHeartLoading"

    # --- Methods ---
    def test_checkPreciseActressMatch_method_exists(self):
        """_checkPreciseActressMatch 方法存在於 core.js"""
        js = self._js()
        assert "_checkPreciseActressMatch" in js, \
            "showcase/core.js 缺少 _checkPreciseActressMatch 方法"

    def test_clearPreciseMatch_method_exists(self):
        """_clearPreciseMatch 方法存在於 core.js"""
        js = self._js()
        assert "_clearPreciseMatch" in js, \
            "showcase/core.js 缺少 _clearPreciseMatch 方法"

    # --- Trigger points ---
    def test_searchFromMetadata_triggers_preciseMatch(self):
        """_checkPreciseActressMatch 出現於 searchFromMetadata 區段"""
        js = self._js()
        block = self._extract_fn_block(js, 'searchFromMetadata(term')
        assert "_checkPreciseActressMatch" in block, \
            "showcase/core.js searchFromMetadata 缺少 _checkPreciseActressMatch 呼叫"

    def test_onSearchChange_triggers_preciseMatch(self):
        """_checkPreciseActressMatch 出現於 onSearchChange 區段"""
        js = self._js()
        block = self._extract_fn_block(js, 'onSearchChange()')
        assert "_checkPreciseActressMatch" in block, \
            "showcase/core.js onSearchChange 缺少 _checkPreciseActressMatch 呼叫"

    def test_onSearchChange_clears_preciseMatch(self):
        """_clearPreciseMatch 出現於 onSearchChange 區段"""
        js = self._js()
        block = self._extract_fn_block(js, 'onSearchChange()')
        assert "_clearPreciseMatch" in block, \
            "showcase/core.js onSearchChange 缺少 _clearPreciseMatch 呼叫"

    # --- Stale guard pattern ---
    def test_stale_guard_pattern(self):
        """capturedTerm 出現於 core.js（stale guard 標誌）"""
        js = self._js()
        assert "capturedTerm" in js, \
            "showcase/core.js 缺少 capturedTerm stale guard pattern"

    # --- Lazy load flag ---
    def test_loadActresses_sets_loaded_flag(self):
        """_actressesLoaded = true 出現於 core.js（懶載 flag 設定）"""
        js = self._js()
        assert "_actressesLoaded = true" in js, \
            "showcase/core.js loadActresses() 缺少 _actressesLoaded = true"

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    # --- 44b-T2: Heart icon ---
    def test_addFavoriteFromSearch_method_exists(self):
        """44b-T2: addFavoriteFromSearch method must exist in core.js"""
        assert "addFavoriteFromSearch" in self._js(), \
            "Missing addFavoriteFromSearch method in showcase core.js"

    def test_heart_button_in_html(self):
        """44b-T2: heart button calling addFavoriteFromSearch must exist in showcase.html"""
        assert "addFavoriteFromSearch" in self._html(), \
            "Missing addFavoriteFromSearch call in showcase.html"

    def test_heart_button_preciseMatch_condition(self):
        """44b-T2: heart button must be gated by _isPreciseActressMatch"""
        assert "_isPreciseActressMatch" in self._html(), \
            "Heart button missing _isPreciseActressMatch condition in showcase.html"

    def test_heart_icon_loading_state(self):
        """44b-T2: addFavoriteFromSearch must handle _favoriteHeartLoading"""
        js = self._js()
        idx = js.find("addFavoriteFromSearch")
        assert idx != -1, "addFavoriteFromSearch not found"
        block = js[idx:idx+2000]
        assert "_favoriteHeartLoading" in block, \
            "addFavoriteFromSearch must use _favoriteHeartLoading for loading state"

    def test_toggleActressMode_clears_preciseMatch(self):
        """44b: toggleActressMode must call _clearPreciseMatch when entering actress mode"""
        js = self._js()
        block = self._extract_fn_block(js, 'toggleActressMode()')
        assert "_clearPreciseMatch" in block, \
            "toggleActressMode must call _clearPreciseMatch to avoid state leak when clearing search"


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
        """showcase.html lightbox cover-actions 不再有 rescrapeActress() handler（44c-T7 已移除按鈕）"""
        html = self._html()
        assert "rescrapeActress()" not in html, \
            "showcase.html 仍含 rescrapeActress() handler（44c-T7 應已移除 lightbox 按鈕）"

    def test_remove_handler_in_template(self):
        """showcase.html 含 removeActress() handler"""
        html = self._html()
        assert "removeActress()" in html, \
            "showcase.html 缺少 removeActress()（Row 6 移除最愛按鈕 @click handler）"

    def test_search_actress_films_method(self):
        """core.js 含 searchActressFilms() 方法"""
        js = self._js()
        assert "searchActressFilms" in js, \
            "showcase/core.js 缺少 searchActressFilms() 方法（女優搜尋影片功能）"

    def test_search_films_handler_in_template(self):
        """showcase.html 含 searchActressFilms() handler（lightbox + grid 各一處）"""
        html = self._html()
        count = html.count("searchActressFilms(")
        assert count >= 2, \
            f"showcase.html searchActressFilms() handler 出現次數不足（期望 >=2，實際 {count}）"


class TestShowcaseActressCardFooter:
    """Phase 44c-T2: Actress Card Footer 三欄 + hover 守衛"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def test_actress_footer_default_three_cols(self):
        """showcase.html actress card footer 含 footer-default 三欄結構"""
        html = self._html()
        assert "footer-default" in html and "_actressCardMiddle" in html, \
            "showcase.html actress-card-footer 缺少 footer-default 三欄結構或 _actressCardMiddle 綁定"

    def test_actress_footer_hover(self):
        """showcase.html actress card footer 含 footer-hover + _actressHoverInfo 綁定"""
        html = self._html()
        assert "footer-hover" in html and "_actressHoverInfo" in html, \
            "showcase.html actress-card-footer 缺少 footer-hover 層或 _actressHoverInfo 綁定"

    def test_actress_card_middle_method(self):
        """core.js 含 _actressCardMiddle() 方法"""
        js = self._js()
        assert "_actressCardMiddle" in js, \
            "showcase/core.js 缺少 _actressCardMiddle() 方法（footer 動態排序指標）"

    def test_actress_hover_info_method(self):
        """core.js 含 _actressHoverInfo() 方法"""
        js = self._js()
        assert "_actressHoverInfo" in js, \
            "showcase/core.js 缺少 _actressHoverInfo() 方法（footer hover 身體數據）"

    def test_actress_hover_info_excludes_age(self):
        """_actressHoverInfo 不包含 age（CD-7：age 在右欄不重複）"""
        js = self._js()
        import re
        m = re.search(r'_actressHoverInfo\(actress\)\s*\{(.+?)^\s{8}\},', js, re.DOTALL | re.MULTILINE)
        if m:
            body = m.group(1)
            assert "actress.age" not in body, \
                "_actressHoverInfo 方法體不應包含 age（CD-7）"

    def test_actress_card_middle_uses_actress_sort(self):
        """_actressCardMiddle 讀取 actressSort 狀態"""
        js = self._js()
        assert "actressSort" in js, \
            "showcase/core.js 缺少 actressSort 狀態（_actressCardMiddle 依賴）"


class TestShowcaseActressI18n:
    """Phase 44a-T7: 確保 4 個 locale 都含 showcase 女優相關新 keys"""

    LOCALES_ROOT = Path(__file__).parent.parent.parent / "locales"

    def _locale(self, name):
        return json.loads((self.LOCALES_ROOT / name).read_text(encoding="utf-8"))

    def _get_nested(self, d, dotted_key):
        keys = dotted_key.split(".")
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return cur

    @pytest.mark.parametrize("key", [
        "showcase.mode.actress",
        "showcase.mode.video",
        "showcase.search.actress",
        "showcase.search.video",
        "showcase.actress.add",
        "showcase.actress.addPlaceholder",
        "showcase.actress.addSuccess",
        "showcase.actress.addDuplicate",
        "showcase.actress.addNotFound",
        "showcase.actress.addTimeout",
        "showcase.actress.rescrape",
        "showcase.actress.rescrapeSuccess",
        "showcase.actress.rescrapeError",
        "showcase.actress.remove",
        "showcase.actress.removeConfirm",
        "showcase.actress.removeSuccess",
        "showcase.actress.empty",
        "showcase.actress.emptyHint",
        "showcase.actress.search_films",
        "showcase.sort.actress.video_count",
        "showcase.sort.actress.name",
        "showcase.sort.actress.added_at",
        "showcase.sort.actress.age",
        "showcase.sort.actress.height",
        "showcase.sort.actress.cup",
        "showcase.unit.videos_count",
        "showcase.unit.films",
    ])
    def test_key_exists_all_locales(self, key):
        """指定 key 在 4 個 locale 都存在且非 None"""
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            val = self._get_nested(data, key)
            assert val is not None, f"{locale_file} 缺少 {key}"


class TestShowcaseLightboxSentinel:
    """Phase 44b-T4: Lightbox -1 sentinel nav guards"""

    CORE_JS = Path(__file__).parents[2] / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'core.js'
    SHOWCASE_HTML = Path(__file__).parents[2] / 'web' / 'templates' / 'showcase.html'

    def _js(self):
        return self.CORE_JS.read_text(encoding='utf-8')

    def _html(self):
        return self.SHOWCASE_HTML.read_text(encoding='utf-8')

    def test_openHeroCardLightbox_exists(self):
        """openHeroCardLightbox method exists and is not a stub"""
        js = self._js()
        assert "openHeroCardLightbox" in js, \
            "showcase/core.js 缺少 openHeroCardLightbox 方法"
        idx = js.find("openHeroCardLightbox")
        block = js[idx:idx + 2000]
        assert "lightboxIndex = -1" in block, \
            "openHeroCardLightbox 缺少 lightboxIndex = -1 賦值（-1 sentinel 設置）"
        assert "this.currentLightboxActress" in block, \
            "openHeroCardLightbox 缺少 currentLightboxActress 賦值"

    def test_hasVisiblePrev_exists(self):
        """hasVisiblePrev computed exists"""
        assert "hasVisiblePrev" in self._js(), \
            "showcase/core.js 缺少 hasVisiblePrev computed（-1 sentinel nav arrow guard）"

    def test_hasVisibleNext_exists(self):
        """hasVisibleNext computed exists"""
        assert "hasVisibleNext" in self._js(), \
            "showcase/core.js 缺少 hasVisibleNext computed（-1 sentinel nav arrow guard）"

    def test_prevLightboxVideo_has_sentinel_guard(self):
        """prevLightboxVideo 含 lightboxIndex === -1 guard"""
        js = self._js()
        idx = js.find("prevLightboxVideo()")
        assert idx != -1, "prevLightboxVideo method not found"
        block = js[idx:idx + 1500]
        assert "lightboxIndex === -1" in block, \
            "prevLightboxVideo 缺少 lightboxIndex === -1 guard（-1 時不動）"
        assert "is_favorite" in block, \
            "prevLightboxVideo 缺少 is_favorite 條件（index 0 → -1 退回條件）"

    def test_nextLightboxVideo_has_sentinel_transition(self):
        """nextLightboxVideo 含 lightboxIndex === -1 跳到 index 0 的邏輯"""
        js = self._js()
        idx = js.find("nextLightboxVideo()")
        assert idx != -1, "nextLightboxVideo method not found"
        block = js[idx:idx + 1500]
        assert "lightboxIndex === -1" in block, \
            "nextLightboxVideo 缺少 lightboxIndex === -1 分支（hero card → 第一筆影片）"
        assert "_setLightboxIndex" in block, \
            "nextLightboxVideo -1 分支缺少 _setLightboxIndex（進入影片模式需標準 setter）"

    def test_handleKeydown_uses_showFavoriteActresses(self):
        """handleKeydown lightbox 分支使用 showFavoriteActresses 而非僅 currentLightboxActress"""
        js = self._js()
        idx = js.find("// 5. Lightbox 開啟時的快捷鍵")
        assert idx != -1, "handleKeydown lightbox section anchor not found"
        block = js[idx:idx + 1000]
        assert "showFavoriteActresses" in block, \
            "handleKeydown lightbox 分支缺少 showFavoriteActresses 判斷（影片模式 hero card 鍵盤導航會走錯分支）"

    def test_removeActress_button_has_xshow_guard(self):
        """removeActress button gated by x-show="showFavoriteActresses\""""
        html = self._html()
        idx = html.find("removeActress()")
        assert idx != -1, "removeActress() handler not found in showcase.html"
        # 找 removeActress button 的區塊（往前 300 字）
        surrounding = html[max(0, idx - 300):idx + 100]
        assert "showFavoriteActresses" in surrounding, \
            "removeActress button 缺少 x-show=\"showFavoriteActresses\" guard（hero card lightbox 不應顯示移除按鈕）"


class TestShowcaseHeroCard:
    """Phase 44b-T6: Showcase Hero Card i18n + structure guards"""

    SHOWCASE_HTML = Path(__file__).parents[2] / 'web' / 'templates' / 'showcase.html'

    def _html(self):
        return self.SHOWCASE_HTML.read_text(encoding='utf-8')

    def test_hero_card_container_in_html(self):
        """hero-card class exists in showcase.html（Hero Card 容器存在）"""
        assert 'hero-card' in self._html(), \
            "showcase.html 缺少 hero-card class（Hero Card 容器未渲染）"

    def test_hero_card_no_image_uses_i18n(self):
        """Hero Card 圖片失敗 fallback 使用 t('common.no_image') 而非硬編碼"""
        html = self._html()
        assert "t('common.no_image')" in html, \
            "showcase.html Hero Card fallback 應使用 t('common.no_image')，不可硬編碼 'No Image'"
        assert "<span>No Image</span>" not in html, \
            "showcase.html 仍有硬編碼 '<span>No Image</span>'，請改用 x-text=\"t('common.no_image')\""

    def test_hero_card_animation_in_animations_js(self):
        """playHeroCardAppear must exist in showcase animations.js"""
        anim_js = (Path(__file__).parents[2] / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'animations.js').read_text(encoding='utf-8')
        assert "playHeroCardAppear" in anim_js, \
            "animations.js 缺少 playHeroCardAppear 方法"

    def test_searchFromMetadata_actress_type_in_html(self):
        """searchFromMetadata calls for actress tags must pass 'actress' type"""
        html = self._html()
        assert "searchFromMetadata(actress.trim(), 'actress')" in html, \
            "showcase.html actress tag 的 searchFromMetadata 呼叫缺少 'actress' type 參數"


class TestShowcaseAliasGuard:
    """T5 (45-actress-alias): Frontend Guard — alias 展開注入守衛"""

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def test_name_to_group_declaration_exists(self):
        """_nameToGroup module-level 宣告必須存在於 core.js"""
        js = self._js()
        assert "var _nameToGroup = {}" in js, \
            "core.js 缺少 module-level 'var _nameToGroup = {}' 宣告"

    def test_actress_aliases_fetch_exists(self):
        """/api/actress-aliases fetch 呼叫必須存在於 core.js"""
        js = self._js()
        assert "/api/actress-aliases" in js, \
            "core.js 缺少 fetch('/api/actress-aliases') 呼叫"

    def test_name_to_group_used_in_apply_actress_filter_and_sort(self):
        """applyActressFilterAndSort 必須使用 _nameToGroup[a.name] 做 alias 展開"""
        js = self._js()
        assert "_nameToGroup[a.name]" in js, \
            "core.js applyActressFilterAndSort 缺少 _nameToGroup[a.name] alias 展開邏輯"

    def test_name_to_group_used_in_check_precise_actress_match(self):
        """_checkPreciseActressMatch 必須使用 _nameToGroup 做 alias group 比對"""
        js = self._js()
        # 搜尋函數體中含 _nameToGroup 即可（函數宣告後都有使用）
        assert "_nameToGroup" in js, \
            "core.js 缺少 _nameToGroup（_checkPreciseActressMatch alias 展開未實作）"
        # 確認精準匹配函數本身有用到 indexOf（alias group 查找的 sentinel）
        func_start = js.find("async _checkPreciseActressMatch")
        func_end = js.find("},", func_start)
        func_body = js[func_start:func_end]
        assert "_nameToGroup" in func_body, \
            "core.js _checkPreciseActressMatch 函數體缺少 _nameToGroup 使用"

    def test_name_to_group_used_in_apply_filter_and_sort_video_mode(self):
        """applyFilterAndSort 影片模式必須使用 _nameToGroup[term] 做 alias 展開"""
        js = self._js()
        assert "_nameToGroup[term]" in js, \
            "core.js applyFilterAndSort 影片模式缺少 _nameToGroup[term] alias 展開邏輯"


# ---------------------------------------------------------------------------
# T6: Scanner Alias UI v2 — 舊 token 移除 + 新 token 存在守衛
# ---------------------------------------------------------------------------
SCANNER_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner.js"
SCANNER_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "scanner.html"
ZH_TW_JSON = Path(__file__).parent.parent.parent / "locales" / "zh_TW.json"


class TestScannerAliasV2Guard:
    """T6: 確認 scanner.js/html 舊 alias token 已移除、新 token 已存在"""

    def _js(self):
        return SCANNER_JS.read_text(encoding="utf-8")

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def _zh_tw(self):
        return json.loads(ZH_TW_JSON.read_text(encoding="utf-8"))

    def test_scanner_js_no_alias_old_name(self):
        """scanner.js 不含 alias.old_name（舊資料結構殘留）"""
        js = self._js()
        assert "alias.old_name" not in js, \
            "scanner.js 仍含舊 alias.old_name，T6 替換不完整"

    def test_scanner_js_no_alias_new_name(self):
        """scanner.js 不含 alias.new_name（舊資料結構殘留）"""
        js = self._js()
        assert "alias.new_name" not in js, \
            "scanner.js 仍含舊 alias.new_name，T6 替換不完整"

    def test_scanner_js_no_old_endpoint(self):
        """scanner.js 不含 api/gallery/actress-aliases（舊 endpoint 殘留）"""
        js = self._js()
        assert "api/gallery/actress-aliases" not in js, \
            "scanner.js 仍含舊 endpoint /api/gallery/actress-aliases，T6 替換不完整"

    def test_scanner_js_has_alias_records(self):
        """scanner.js 含 aliasRecords（新 state 已宣告）"""
        js = self._js()
        assert "aliasRecords" in js, \
            "scanner.js 缺少 aliasRecords state，T6 新 state 未宣告"

    def test_scanner_html_no_alias_form_old_name(self):
        """scanner.html 不含 aliasForm.oldName（舊 binding 殘留）"""
        html = self._html()
        assert "aliasForm.oldName" not in html, \
            "scanner.html 仍含舊 aliasForm.oldName，T6 替換不完整"

    def test_zh_tw_has_search_placeholder(self):
        """zh_TW.json 含 scanner.alias.search_placeholder（新 i18n key）"""
        data = self._zh_tw()
        alias = data.get("scanner", {}).get("alias", {})
        assert "search_placeholder" in alias, \
            "zh_TW.json 缺少 scanner.alias.search_placeholder，T6 i18n 未更新"

    # --- T8 guards: pill UI + unified input + x-model binding ---

    def test_scanner_js_has_alias_input(self):
        """scanner.js 含 aliasInput 統一輸入狀態（T8 合併 aliasSearch + newPrimaryName）"""
        js = self._js()
        assert "aliasInput" in js, \
            "scanner.js 缺少 aliasInput 狀態變數"

    def test_scanner_js_has_cancel_add_alias(self):
        """scanner.js 含 cancelAddAlias 方法（T8 inline input cancel 按鈕）"""
        js = self._js()
        assert "cancelAddAlias" in js, \
            "scanner.js 缺少 cancelAddAlias 方法"

    def test_scanner_html_uses_x_model_for_inline_input(self):
        """inline add input 使用 x-model 而非 :value+@input（修正 IME 競態）"""
        html = self._html()
        assert 'x-model="addingAlias[group.primary_name]"' in html, \
            "scanner.html inline input 應使用 x-model 綁定，而非 :value+@input"

    def test_scanner_html_no_stale_value_binding(self):
        """:value="addingAlias[ 手動綁定不應存在（已改為 x-model）"""
        html = self._html()
        assert ':value="addingAlias[group.primary_name]"' not in html, \
            "scanner.html 仍有 :value 手動綁定，應已被 x-model 取代"

    def test_scanner_html_cancel_button_has_type(self):
        """alias 區域的 btn-cancel 必須有 type='button'"""
        html = self._html()
        assert 'type="button" class="btn-cancel"' in html, \
            "btn-cancel 缺少 type='button'"

    def test_scanner_html_no_btn_confirm(self):
        """btn-confirm 已移除（改為 Enter key only）"""
        html = self._html()
        assert 'btn-confirm' not in html, \
            "scanner.html 不應含 btn-confirm（已改為 Enter only）"

    def test_zh_tw_has_filter_hint(self):
        """zh_TW.json 含 scanner.alias.filter_hint（T8 篩選提示）"""
        data = self._zh_tw()
        alias = data.get("scanner", {}).get("alias", {})
        assert "filter_hint" in alias, \
            "zh_TW.json 缺少 scanner.alias.filter_hint"


class TestUserTagCSSGuard:
    """T3: 確保 user-tag 選擇器不使用 --text-inverse（dark mode 對比度修正）"""

    def test_search_user_tag_no_text_inverse(self):
        """search.css 的 .tag-badge.user-tag 不使用 --text-inverse"""
        css = Path("web/static/css/pages/search.css").read_text(encoding="utf-8")
        # 截取 .tag-badge.user-tag 選擇器區塊
        match = re.search(r'\.tag-badge\.user-tag\s*\{([^}]+)\}', css)
        assert match, ".tag-badge.user-tag selector not found in search.css"
        block = match.group(1)
        assert "--text-inverse" not in block, \
            ".tag-badge.user-tag should use --color-primary-content, not --text-inverse"

    def test_showcase_lb_user_tag_no_text_inverse(self):
        """showcase.css 的 .lb-user-tag 不使用 --text-inverse"""
        css = Path("web/static/css/pages/showcase.css").read_text(encoding="utf-8")
        match = re.search(r'\.lb-user-tag\s*\{([^}]+)\}', css)
        assert match, ".lb-user-tag selector not found in showcase.css"
        block = match.group(1)
        assert "--text-inverse" not in block, \
            ".lb-user-tag should use --color-primary-content, not --text-inverse"


class TestShowcaseToolbarStructureGuard:
    """T5: 確保影片模式 .toolbar-controls 直接子 .control-group 數量為 2"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_video_mode_toolbar_has_two_control_groups(self):
        """影片模式 .toolbar-controls 直接子 .control-group 應有 2 個

        group 1: funnel + sort-dir
        group 2: mode dropdown + eye button + perPage dropdown
        """
        html = self._html()

        # 找到影片模式的 toolbar-controls（x-show="!showFavoriteActresses"）
        # 用正則截取從開啟標籤到對應結尾 </div> 的區塊
        # 先找到開啟的 div
        start_pattern = re.compile(
            r'<div[^>]+class="[^"]*toolbar-section toolbar-controls[^"]*"[^>]+x-show="!showFavoriteActresses"[^>]*>'
        )
        start_match = start_pattern.search(html)
        assert start_match, (
            "showcase.html 找不到影片模式 .toolbar-controls（x-show=\"!showFavoriteActresses\"）"
        )

        # 從開啟標籤後，追蹤 div 巢狀深度找到對應的結尾 </div>
        pos = start_match.end()
        depth = 1
        tag_pattern = re.compile(r'<(/?)div[\s>]')
        while depth > 0 and pos < len(html):
            m = tag_pattern.search(html, pos)
            if not m:
                break
            if m.group(1) == '/':
                depth -= 1
            else:
                depth += 1
            pos = m.end()

        block = html[start_match.end():pos]

        # 計算直接子 .control-group 數量：找開啟的 <div class="control-group">
        # 只計算深度 1 的（直接子）
        direct_groups = 0
        depth = 0
        tag_re = re.compile(r'<(/?)(div)(?:\s+([^>]*))?>')
        for m in tag_re.finditer(block):
            closing, tag, attrs = m.group(1), m.group(2), m.group(3) or ''
            if closing:
                depth -= 1
            else:
                if depth == 0 and 'control-group' in attrs:
                    direct_groups += 1
                depth += 1

        assert direct_groups == 1, (
            f"影片模式 .toolbar-controls 直接子 .control-group 應為 1 個（全部 5 icon 合併），實際為 {direct_groups} 個。"
        )


class TestActressIconGuard:
    """T6E: 確保女優 icon 統一為 bi-person-circle"""

    def test_showcase_no_bare_bi_person(self):
        """showcase.html 不應有 bi-person（非 circle/heart）"""
        html = Path("web/templates/showcase.html").read_text(encoding="utf-8")
        # 匹配 bi-person 但排除 bi-person-circle 和 bi-person-heart
        matches = re.findall(r'class="bi bi-person(?!-circle|-heart)"', html)
        # 排除 icon catalog 展示（如有）
        assert len(matches) == 0, f"showcase.html 仍有 {len(matches)} 處 bi-person（非 circle/heart）"

    def test_scanner_no_bi_person_badge(self):
        """scanner.html 不應有 bi-person-badge"""
        html = Path("web/templates/scanner.html").read_text(encoding="utf-8")
        assert "bi-person-badge" not in html, "scanner.html 仍有 bi-person-badge"


class TestGhostFlyGuards:
    """T8: Ghost Fly 架構守衛"""

    def test_ghost_fly_js_exists(self):
        """ghost-fly.js 檔案存在"""
        assert Path("web/static/js/shared/ghost-fly.js").exists()

    def test_ghost_fly_loaded_in_base_html(self):
        """base.html 載入 ghost-fly.js"""
        html = Path("web/templates/base.html").read_text(encoding="utf-8")
        assert "ghost-fly.js" in html

    def test_skip_cover_supported_in_showcase_animations(self):
        """showcase/animations.js playLightboxOpen 支援 skipCover"""
        js = Path("web/static/js/pages/showcase/animations.js").read_text(encoding="utf-8")
        assert "skipCover" in js

    def test_skip_cover_supported_in_search_animations(self):
        """search/animations.js playLightboxOpen 支援 skipCover"""
        js = Path("web/static/js/pages/search/animations.js").read_text(encoding="utf-8")
        assert "skipCover" in js

    def test_ghost_fly_fallback_exists_in_search_animations(self):
        """search/animations.js 委派函式有 GhostFly fallback"""
        js = Path("web/static/js/pages/search/animations.js").read_text(encoding="utf-8")
        # createCoverGhost 應委派到 window.GhostFly
        assert "window.GhostFly" in js
        # 應有 else fallback（GhostFly 不存在時）
        # 在 createCoverGhost / cleanupGhost / cleanupStaleGhosts 區域
        lines = js.split('\n')
        ghost_fly_refs = [i for i, line in enumerate(lines) if 'window.GhostFly' in line]
        assert len(ghost_fly_refs) >= 3, "應有至少 3 個 window.GhostFly 引用（三個委派函式）"

    def test_gsap_animating_before_lightbox_open(self):
        """showcase/core.js 的 gsap-animating 在 lightboxOpen = true 之前"""
        js = Path("web/static/js/pages/showcase/core.js").read_text(encoding="utf-8")
        # 只在 openLightbox 函數區域內檢查順序
        idx_fn = js.find("openLightbox(")
        assert idx_fn > 0, "找不到 openLightbox 函數"
        fn_scope = js[idx_fn:]
        idx_animating = fn_scope.find("classList.add('gsap-animating')")
        idx_open = fn_scope.find("this.lightboxOpen = true")
        assert idx_animating > 0, "找不到 gsap-animating classList.add"
        assert idx_open > 0, "找不到 lightboxOpen = true"
        assert idx_animating < idx_open, "gsap-animating 應在 lightboxOpen = true 之前"


class TestTutorialExpandGuard:
    """T10: 新手教學 7 步守衛"""

    def test_tutorial_has_7_steps(self):
        """tutorial.js 包含 7 個步驟 id"""
        js = Path("web/static/js/components/tutorial.js").read_text(encoding="utf-8")
        expected_ids = ['search', 'files', 'scanner', 'showcase', 'settings', 'help', 'samples']
        for step_id in expected_ids:
            assert f"id: '{step_id}'" in js, f"tutorial.js 缺少步驟 id: '{step_id}'"

    def test_tutorial_last_step_has_large(self):
        """最後一步（samples）有 large: true"""
        js = Path("web/static/js/components/tutorial.js").read_text(encoding="utf-8")
        # 找 samples step 區塊，確認包含 large: true
        samples_idx = js.find("id: 'samples'")
        assert samples_idx > 0, "找不到 samples 步驟"
        # 從 samples 往後找到這個物件的結尾 }
        block_end = js.find('}', samples_idx)
        block = js[samples_idx:block_end]
        assert 'large: true' in block, "samples 步驟缺少 large: true"

    @pytest.mark.parametrize("locale", ["zh_TW", "en", "ja", "zh_CN"])
    def test_tutorial_i18n_keys_complete(self, locale):
        """四語系 tutorial step1-7 key 全部存在且非空"""
        import json
        data = json.loads(Path(f"locales/{locale}.json").read_text(encoding="utf-8"))
        tutorial = data.get("tutorial", {})
        for i in range(1, 8):
            title_key = f"step{i}_title"
            content_key = f"step{i}_content"
            assert title_key in tutorial and tutorial[title_key], \
                f"{locale}.json 缺少或為空: tutorial.{title_key}"
            assert content_key in tutorial and tutorial[content_key], \
                f"{locale}.json 缺少或為空: tutorial.{content_key}"


class TestMissingEnrichConfirmGuard:
    """TASK-13 (0.7.6 hotfix): 守衛 Scanner 一鍵補完 > 500 confirm dialog 的實作"""

    def _js(self):
        return SCANNER_JS.read_text(encoding="utf-8")

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def _extract_function_body(self, js, fn_name):
        """抓取具名 function（async fn_name(...) { ... }）函式主體（大括號平衡匹配）。
        也涵蓋 `async runMissingEnrich({ skipConfirm = false } = {})` 這類 options pattern。"""
        pattern = re.compile(
            r'async\s+' + re.escape(fn_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        if not m:
            # 非 async 版本（例如 resumeMissingEnrich）
            pattern_sync = re.compile(
                re.escape(fn_name) + r'\s*\([^)]*\)\s*\{',
                re.DOTALL,
            )
            m = pattern_sync.search(js)
        assert m is not None, f"scanner.js 找不到 {fn_name} 函式"
        start = m.end()  # 位於 { 之後
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_js_has_missing_confirm_modal_open_state(self):
        """scanner.js 含 missingConfirmModalOpen state 欄位宣告"""
        js = self._js()
        assert "missingConfirmModalOpen" in js, \
            "scanner.js 缺少 missingConfirmModalOpen state（confirm modal 綁定用）"

    def test_js_run_missing_enrich_has_threshold_check(self):
        """runMissingEnrich 函式體含 skipConfirm 參數 + > 500 threshold 檢查 + missingConfirmModalOpen"""
        js = self._js()
        body = self._extract_function_body(js, "runMissingEnrich")
        assert "skipConfirm" in body, \
            "runMissingEnrich 函式體缺少 skipConfirm 參數處理"
        assert "> 500" in body, \
            "runMissingEnrich 函式體缺少 > 500 threshold 檢查"
        assert "missingConfirmModalOpen" in body, \
            "runMissingEnrich 函式體缺少 missingConfirmModalOpen 觸發"

    def test_js_resume_missing_enrich_uses_skip_confirm(self):
        """resumeMissingEnrich 不清 localStorage.avlist_enrich_pending 且用 skipConfirm: true 呼叫 runMissingEnrich"""
        js = self._js()
        body = self._extract_function_body(js, "resumeMissingEnrich")
        assert "localStorage.removeItem('avlist_enrich_pending')" not in body and \
               'localStorage.removeItem("avlist_enrich_pending")' not in body, \
            "resumeMissingEnrich 不應 localStorage.removeItem('avlist_enrich_pending')（會丟恢復點）"
        assert "skipConfirm: true" in body, \
            "resumeMissingEnrich 應呼叫 runMissingEnrich({ skipConfirm: true })"

    def test_html_has_missing_confirm_modal(self):
        """scanner.html 含 missingConfirmModalOpen 綁定 + cancel/confirm 方法"""
        html = self._html()
        assert "missingConfirmModalOpen" in html, \
            "scanner.html 缺少 missingConfirmModalOpen 綁定（confirm modal）"
        assert "cancelLargeMissingEnrich" in html, \
            "scanner.html 缺少 cancelLargeMissingEnrich 綁定"
        assert "confirmLargeMissingEnrich" in html, \
            "scanner.html 缺少 confirmLargeMissingEnrich 綁定"

    @pytest.mark.parametrize("locale", ["zh_TW", "zh_CN", "ja", "en"])
    def test_all_locales_have_missing_enrich_confirm_keys(self, locale):
        """四語系都有 6 個 missing_enrich_confirm_* keys（純文字）"""
        data = json.loads((LOCALES_ROOT / f"{locale}.json").read_text(encoding="utf-8"))
        stats = data.get("scanner", {}).get("stats", {})
        required = [
            "missing_enrich_confirm_title",
            "missing_enrich_confirm_body_prefix",
            "missing_enrich_confirm_body_middle",
            "missing_enrich_confirm_body_suffix",
            "missing_enrich_confirm_cancel",
            "missing_enrich_confirm_confirm",
        ]
        for key in required:
            assert key in stats and stats[key], \
                f"{locale}.json 缺少或為空：scanner.stats.{key}"
            # 確保純文字：不含 HTML tag
            value = stats[key]
            assert "<" not in value and ">" not in value, \
                f"{locale}.json scanner.stats.{key} 含 HTML tag（應純文字）: {value!r}"


class TestIMEGuard:
    """spec-48a §a4 — IME composition guard"""

    def test_search_input_has_keydown_enter_handler(self):
        """#searchQuery input 本身必須有 @keydown.enter handler（不是別的元素）"""
        content = (Path(__file__).parent.parent.parent / "web" / "templates" / "search.html").read_text(encoding="utf-8")
        m = re.search(r'<input\b[^>]*\bid="searchQuery"[^>]*>', content, re.DOTALL)
        assert m, \
            "search.html 找不到 id=\"searchQuery\" 的 <input> tag"
        tag = m.group(0)
        handler_m = re.search(r'@keydown\.enter(?:\.prevent)?="([^"]*)"', tag)
        assert handler_m, \
            "id=\"searchQuery\" input 缺少 @keydown.enter handler（handler 必須在 searchQuery input 上，不是別的元素）"

    def test_handler_contains_iscomposing(self):
        """#searchQuery @keydown.enter handler 必須含 isComposing guard"""
        content = (Path(__file__).parent.parent.parent / "web" / "templates" / "search.html").read_text(encoding="utf-8")
        m = re.search(r'<input\b[^>]*\bid="searchQuery"[^>]*>', content, re.DOTALL)
        assert m, "search.html 找不到 id=\"searchQuery\" 的 <input> tag"
        tag = m.group(0)
        handler_m = re.search(r'@keydown\.enter(?:\.prevent)?="([^"]*)"', tag)
        assert handler_m, "id=\"searchQuery\" input 缺少 @keydown.enter handler"
        expr = handler_m.group(1)
        assert "isComposing" in expr, \
            f"id=\"searchQuery\" @keydown.enter handler 不含 isComposing guard（目前 handler: {expr!r}）"

    def test_handler_contains_preventdefault(self):
        """#searchQuery @keydown.enter handler 必須含 preventDefault()（防止 IME 確認觸發搜尋）"""
        content = (Path(__file__).parent.parent.parent / "web" / "templates" / "search.html").read_text(encoding="utf-8")
        m = re.search(r'<input\b[^>]*\bid="searchQuery"[^>]*>', content, re.DOTALL)
        assert m, "search.html 找不到 id=\"searchQuery\" 的 <input> tag"
        tag = m.group(0)
        handler_m = re.search(r'@keydown\.enter(?:\.prevent)?="([^"]*)"', tag)
        assert handler_m, "id=\"searchQuery\" input 缺少 @keydown.enter handler"
        expr = handler_m.group(1)
        assert "preventDefault()" in expr, \
            f"id=\"searchQuery\" @keydown.enter handler 不含 preventDefault()（只用 return 無法阻擋 form submit，IME bug 會回來；目前 handler: {expr!r}）"


class TestLongPathWarning:
    """spec-48a §a5 — scanner.js long_paths 警告處理"""

    def _js(self):
        return SCANNER_JS.read_text(encoding="utf-8")

    def test_scanner_js_handles_long_paths(self):
        """scanner.js done event 處理須偵測 data.long_paths 並顯示警告 toast"""
        js = self._js()
        assert "long_paths" in js, \
            "scanner.js 缺少 long_paths 處理（done event 應檢查 data.long_paths）"
        assert "showToast" in js, \
            "scanner.js 缺少 showToast 呼叫（既有功能,不應被移除）"

    def test_long_path_warning_uses_warn_type_and_long_duration(self):
        """long_paths 警告 toast 必須用 'warn' type + >=6000ms duration（延長顯示）"""
        js = self._js()
        # 定位 long_paths 判斷區塊（給出 300 字元窗口,足以涵蓋 if + showToast 完整呼叫）
        idx = js.find("long_paths")
        assert idx >= 0, "scanner.js 找不到 long_paths 引用"
        window = js[idx:idx + 500]
        assert "'warn'" in window or '"warn"' in window, \
            "long_paths 警告 toast 應使用 'warn' type（與 L1150 既有風格一致）"
        assert "6000" in window, \
            "long_paths 警告 toast 應傳第三參數 duration=6000（延長顯示讓用戶看清楚）"

    def test_long_path_warning_message_mentions_260_and_debug_log(self):
        """警告訊息必須提到 260 字元門檻 + debug.log（用戶可循線追詳細清單）"""
        js = self._js()
        idx = js.find("long_paths")
        assert idx >= 0
        window = js[idx:idx + 500]
        assert "260" in window, \
            "long_paths 警告訊息應提到「260」字元門檻（讓用戶理解原因）"
        assert "debug.log" in window, \
            "long_paths 警告訊息應提到「debug.log」（引導用戶查詳細清單）"


class TestSearchFileJsSubtitleHelper:
    """48a T2 a2 — 前端 extractChineseTitle 同步套用 stripSubtitleMarkers helper（對齊 Python 端）"""

    def _js(self):
        return SEARCH_FILE_JS.read_text(encoding="utf-8")

    def test_strip_subtitle_markers_function_exists(self):
        """file.js 應定義 stripSubtitleMarkers helper（對齊 Python strip_subtitle_markers）"""
        js = self._js()
        assert "function stripSubtitleMarkers(" in js, \
            "file.js 缺少 stripSubtitleMarkers() 函式定義（應對齊 Python core/scrapers/utils.py::strip_subtitle_markers）"

    def test_old_regex_removed(self):
        """殘缺的舊 regex `/^中文字幕\\s*/` 不得留在 file.js（只剝開頭「中文字幕」會漏 [中字] 等變體）"""
        js = self._js()
        assert "/^中文字幕\\s*/" not in js, \
            "file.js 仍保留殘缺的 `/^中文字幕\\s*/` regex，應改用 stripSubtitleMarkers()"

    def test_extract_chinese_title_uses_strip_helper(self):
        """extractChineseTitle() 應呼叫 stripSubtitleMarkers(name)，不再內嵌殘缺 regex"""
        js = self._js()
        start = js.find("function extractChineseTitle(")
        assert start >= 0, "file.js 找不到 extractChineseTitle 函式定義"
        # 找到函式開頭後的第一個 { ，往後掃直到配對的 }
        brace_start = js.find("{", start)
        assert brace_start >= 0
        depth = 0
        end = brace_start
        for i in range(brace_start, len(js)):
            ch = js[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        body = js[start:end]
        assert "stripSubtitleMarkers(name)" in body, \
            "extractChineseTitle() 應呼叫 stripSubtitleMarkers(name) 剝除所有字幕標記變體"
        assert "name.replace(/^中文字幕" not in body, \
            "extractChineseTitle() 不應再內嵌殘缺 `/^中文字幕...` regex"

    def test_subtitle_brackets_constant_present(self):
        """file.js 應有 _SUBTITLE_BRACKETS / _SUBTITLE_TEXT_MARKERS 常數（對齊 Python _SUBTITLE_PATTERNS_*）"""
        js = self._js()
        assert "_SUBTITLE_BRACKETS" in js, \
            "file.js 缺少 _SUBTITLE_BRACKETS 常數（對齊 Python 字幕 bracket pattern）"
        assert "_SUBTITLE_TEXT_MARKERS" in js, \
            "file.js 缺少 _SUBTITLE_TEXT_MARKERS 常數（對齊 Python 字幕純文字 pattern）"


class TestFetchSamplesButton:
    """spec-48b §b3 b6 — 守衛 showcase.html fetch-samples-btn 的所有 Alpine 綁定合約"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def _fetch_samples_btn_tag(self, html: str):
        """從 showcase.html 抽出 fetch-samples-btn 的完整 <button ...> tag。
        回傳 None 若不存在（讓後續測試明確 fail）。
        """
        m = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html,
            re.DOTALL,
        )
        return m.group(0) if m else None

    def test_fetch_samples_btn_exists_in_lb_header(self):
        """showcase.html lb-header 內含 class="fetch-samples-btn" 的 button element"""
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, (
            "showcase.html 缺少 class=\"fetch-samples-btn\" 的 button element（lb-header 內）"
        )

    def test_fetch_samples_btn_has_x_show_with_sample_images_check(self):
        """fetch-samples-btn 的 x-show 在同一個 button tag 上，且含 sample_images 長度檢查"""
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, "fetch-samples-btn element 不存在，無法檢查 x-show"
        # x-show attribute 必須在同一個 <button> tag 內
        assert 'x-show=' in tag, (
            "fetch-samples-btn 缺少 x-show attribute（必須在同一個 button tag 上，非其他 element）"
        )
        # x-show 必須含 sample_images 長度判斷（確保只在無劇照時顯示）
        assert 'sample_images' in tag, (
            "fetch-samples-btn 的 x-show 未包含 sample_images 條件（應為 length === 0）"
        )

    def test_fetch_samples_btn_has_click_handler(self):
        """fetch-samples-btn 的 @click 在同一個 button tag 上，且呼叫 fetchSamples"""
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, "fetch-samples-btn element 不存在，無法檢查 @click"
        assert '@click=' in tag or '@click.' in tag, (
            "fetch-samples-btn 缺少 @click handler（必須在同一個 button tag 上）"
        )
        assert 'fetchSamples' in tag, (
            "fetch-samples-btn 的 @click handler 未呼叫 fetchSamples（確保點擊觸發正確 method）"
        )

    def test_fetch_samples_btn_has_disabled_binding(self):
        """fetch-samples-btn 的 :disabled binding 在同一個 button tag 上，且含 _fetchSamplesFailed"""
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, "fetch-samples-btn element 不存在，無法檢查 :disabled"
        assert ':disabled=' in tag, (
            "fetch-samples-btn 缺少 :disabled binding（必須在同一個 button tag 上）"
        )
        assert '_fetchSamplesFailed' in tag, (
            "fetch-samples-btn 的 :disabled 未包含 _fetchSamplesFailed（確保失敗後鎖住按鈕）"
        )

    def test_disabled_binding_uses_explicit_boolean_coercion(self):
        """fetch-samples-btn 的 :disabled 表達式必須強制 boolean，
        防止 Alpine 3 將 undefined 正規化為 '' 而設置 disabled attribute。

        背景（gotchas.md §Alpine.js Gotchas 第 6 條）：
          - _fetchSamplesFailed[path] 在 key 不存在時回傳 undefined（非 false）
          - Alpine 3 將 undefined 正規化為 "" 存入 _x_bindings.disabled cache
          - 對 boolean attr，"" 視為「屬性存在」→ disabled="" = disabled="disabled"
          - 結果：fresh session 下按鈕無法點擊（b6 bug）

        接受的正確模式：
          - !!_fetchSamplesFailed[   （!! 強制 boolean，推薦）
          - _fetchSamplesFailed[...] === true  （嚴格比較）

        拒絕的錯誤模式：
          - 裸 _fetchSamplesFailed[...]（無 boolean 強制）
        """
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, "fetch-samples-btn element 不存在，無法檢查 :disabled 表達式"

        # 提取 :disabled="..." 的值
        m = re.search(r':disabled=["\']([^"\']*)["\']', tag)
        assert m is not None, (
            "fetch-samples-btn 缺少 :disabled binding，無法驗證 boolean 強制"
        )
        disabled_expr = m.group(1)

        # 確認表達式含有 boolean 強制（!! 或 === true）
        pattern = re.compile(
            r'(!!\s*_fetchSamplesFailed\[|_fetchSamplesFailed\[.+?\]\s*===\s*true)'
        )
        assert pattern.search(disabled_expr), (
            f"fetch-samples-btn :disabled 表達式缺少 boolean 強制（當前：{disabled_expr!r}）。\n"
            "問題：_fetchSamplesFailed[path] 在 key 不存在時回傳 undefined，"
            "Alpine 3 將 undefined 正規化為 '' → disabled='' → 按鈕無法點擊。\n"
            "修法：改為 !!_fetchSamplesFailed[currentLightboxVideo?.path] 或 "
            "_fetchSamplesFailed[...] === true。\n"
            "詳見 feature/AI_COLLABORATION/gotchas.md §Alpine.js Gotchas 第 6 條。"
        )

    def test_fetch_samples_btn_has_x_text_for_i18n(self):
        """fetch-samples-btn 或其子元素的 x-text 引用 showcase.samples.fetch_btn。

        b6fix2 將 x-text 從 button tag 移至內部 <span>，以防 Alpine 覆蓋 innerHTML
        （否則 <i> icon 會消失）。搜尋範圍從 button 起始標籤擴展至 btn_region 完整區段。
        """
        html = self._html()
        m = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html,
            re.DOTALL,
        )
        assert m is not None, "fetch-samples-btn element 不存在，無法檢查 x-text"
        close_tag_pos = html.find('</button>', m.end())
        assert close_tag_pos > m.start(), "找不到 fetch-samples-btn 的 </button> 結束標籤"
        btn_region = html[m.start():close_tag_pos + len('</button>')]
        assert 'x-text=' in btn_region, (
            "fetch-samples-btn 範圍內缺少 x-text binding（應綁定 i18n key，不可 hardcode 文字）"
        )
        assert 'showcase.samples.fetch_btn' in btn_region, (
            "fetch-samples-btn 範圍內的 x-text 未引用 showcase.samples.fetch_btn i18n key"
        )

    def test_fetching_loading_span_exists_with_x_show(self):
        """showcase.html 含 loading span（x-show="_fetchSamplesLoading"）"""
        html = self._html()
        # loading span 不需 element-bound regex（單一用途，位置緊鄰 button）
        assert '_fetchSamplesLoading' in html, (
            "showcase.html 缺少 _fetchSamplesLoading 參照（loading span 或 x-show）"
        )
        assert 'showcase.samples.fetching' in html, (
            "showcase.html 缺少 showcase.samples.fetching i18n key 參照（loading span x-text）"
        )

    def test_core_js_has_fetch_samples_method(self):
        """core.js 含 fetchSamples method 定義"""
        js = self._js()
        # 接受 async fetchSamples(video) { 或 fetchSamples(video) { 兩種形式
        assert re.search(r'(?:async\s+)?fetchSamples\s*\(\s*video\s*\)\s*\{', js), (
            "showcase/core.js 缺少 fetchSamples(video) method 定義"
        )

    def test_core_js_has_fetch_samples_loading_state(self):
        """core.js Alpine data 含 _fetchSamplesLoading 初始化"""
        js = self._js()
        assert '_fetchSamplesLoading:' in js or '_fetchSamplesLoading :' in js, (
            "showcase/core.js Alpine data 缺少 _fetchSamplesLoading 初始化宣告"
        )

    def test_core_js_has_fetch_samples_failed_state(self):
        """core.js Alpine data 含 _fetchSamplesFailed 初始化"""
        js = self._js()
        assert '_fetchSamplesFailed:' in js or '_fetchSamplesFailed :' in js, (
            "showcase/core.js Alpine data 缺少 _fetchSamplesFailed 初始化宣告"
        )

    def test_close_lightbox_resets_fetch_samples_failed(self):
        """closeLightbox() 含 _fetchSamplesFailed = {} 重置（Canonical Decision #12）"""
        js = self._js()
        # 找 closeLightbox 函數體（從 "closeLightbox()" 到下一個頂層 method 的 "," 為止）
        # 用寬鬆 grep 即可：_fetchSamplesFailed = {} 必須出現在 closeLightbox 上下文
        # 精確做法：確認 closeLightbox 定義後有 _fetchSamplesFailed = {}
        close_lb_idx = js.find('closeLightbox() {')
        assert close_lb_idx >= 0, "core.js 找不到 closeLightbox() 方法"
        # 從 closeLightbox() 之後找 _fetchSamplesFailed = {}（在合理的函數體範圍內）
        # 截取 closeLightbox 後 2000 個字元（足夠覆蓋整個函數體）
        close_lb_body = js[close_lb_idx: close_lb_idx + 2000]
        assert '_fetchSamplesFailed = {}' in close_lb_body, (
            "closeLightbox() 函數體內缺少 _fetchSamplesFailed = {}（關閉 Lightbox 應重置失敗記憶，"
            "Canonical Decision #12）"
        )

    @pytest.mark.parametrize("locale", ["zh_TW", "zh_CN", "en", "ja"])
    def test_locale_files_have_samples_keys(self, locale):
        """4 個語系 locale file 均含 showcase.samples 的 5 個 key"""
        locale_file = LOCALES_ROOT / f"{locale}.json"
        assert locale_file.exists(), f"locale 檔案不存在: {locale_file}"
        data = json.loads(locale_file.read_text(encoding="utf-8"))
        showcase = data.get("showcase", {})
        samples = showcase.get("samples", {})
        required_keys = {
            "fetch_btn",
            "fetching",
            "success",
            "fetch_failed",
            "multi_video_error",
        }
        missing = required_keys - set(samples.keys())
        assert not missing, (
            f"locales/{locale}.json showcase.samples 缺少 key: {sorted(missing)}"
        )

    def test_fetch_samples_btn_has_bootstrap_icon(self):
        """fetch-samples-btn 內含 Bootstrap Icon class（bi bi-cloud-download）。

        b6 原始按鈕為裸文字，b6fix2 替換為 Bootstrap Icon。
        靜態守衛確保 icon markup 不被移除（防止未來誤刪或改回 emoji）。
        """
        html = self._html()
        m = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html,
            re.DOTALL,
        )
        assert m is not None, "fetch-samples-btn button element 不存在"

        close_tag_pos = html.find('</button>', m.end())
        assert close_tag_pos > m.start(), "找不到 fetch-samples-btn 的 </button> 結束標籤"
        btn_region = html[m.start():close_tag_pos + len('</button>')]

        assert 'bi bi-cloud-download' in btn_region, (
            "fetch-samples-btn 範圍內缺少 Bootstrap Icon（bi bi-cloud-download）。\n"
            "b6fix2 要求以 <i class=\"bi bi-cloud-download\"> 取代 emoji ☁️。\n"
            "確認 showcase.html 的 fetch-samples-btn 已加入 <i class=\"bi bi-cloud-download\" aria-hidden=\"true\"></i>。"
        )

    def test_fetch_samples_btn_no_emoji_fallback(self):
        """fetch-samples-btn 範圍內不含 ☁️ emoji（U+2601 + 可選 U+FE0F）。

        b6 原始按鈕文字為 '☁️ 補抓劇照'（emoji 前綴）。
        b6fix2 移除 emoji，改用 Bootstrap Icon，並更新 4 語系 locale label。
        靜態守衛：直接掃 showcase.html 的 fetch-samples-btn button region 不含 ☁ 字元。
        此測試範圍僅限 template；locale JSON 值的 emoji 移除由
        test_fetch_btn_locale_no_emoji 負責驗證。
        """
        html = self._html()
        m = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html,
            re.DOTALL,
        )
        assert m is not None, "fetch-samples-btn button element 不存在"

        close_tag_pos = html.find('</button>', m.end())
        assert close_tag_pos > m.start(), "找不到 fetch-samples-btn 的 </button> 結束標籤"
        btn_region = html[m.start():close_tag_pos + len('</button>')]

        assert '☁' not in btn_region, (
            "fetch-samples-btn 範圍內仍含 ☁ emoji（U+2601）。\n"
            "b6fix2 應移除 hardcode emoji，改以 Bootstrap Icon <i class=\"bi bi-cloud-download\"> 替代。"
        )

    @pytest.mark.parametrize("locale", ["zh_TW", "zh_CN", "en", "ja"])
    def test_fetch_btn_locale_no_emoji(self, locale):
        """4 語系 locale JSON 的 showcase.samples.fetch_btn 值不含 ☁ emoji（U+2601）。

        b6fix2 同步更新 4 個語系 fetch_btn label，移除 emoji 前綴。
        此守衛確保 locale JSON 本身的 value 不含 ☁，
        與 test_fetch_samples_btn_no_emoji_fallback（掃 template）互補。
        """
        locale_path = LOCALES_ROOT / f"{locale}.json"
        with locale_path.open(encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("showcase", {}).get("samples", {}).get("fetch_btn", "")
        assert "☁" not in value, (
            f"locales/{locale}.json showcase.samples.fetch_btn 仍含 ☁ emoji（U+2601）。\n"
            f"當前值：{value!r}\n"
            "b6fix2 應將 emoji 前綴從所有 4 語系 locale 值中移除。"
        )


class TestActressLightboxHeartRemoved:
    """T6: Actress Lightbox header 純裝飾愛心 button + CSS 死碼移除守衛"""

    def test_no_decorative_heart_button_in_actress_lightbox(self):
        """showcase.html 不應再含 pointer-events:none 的 is-favorite 愛心裝飾 button"""
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        # 確認舊裝飾按鈕已移除（pointer-events:none + aria-label="favorite"）
        pattern = r'<button[^>]*pointer-events:none[^>]*aria-label="favorite"'
        assert not re.search(pattern, html), "decorative heart button should be removed"
        # 同時確保 hero card 功能按鈕仍存在
        assert 'GhostFly.floatingHearts' in html, "hero card floatingHearts button must remain"

    def test_no_orphan_actress_lb_header_btn_glass_circle_css(self):
        """showcase.css 不應再含 .actress-lb-header .btn-glass-circle 規則"""
        css = Path("web/static/css/pages/showcase.css").read_text(encoding="utf-8")
        assert '.actress-lb-header .btn-glass-circle' not in css, "orphan CSS should be removed"


class TestActressCoreMetadataVideoCount:
    """T2: _actressCoreMetadata() 加 video_count 前置 + i18n showcase.unit.films 改值"""

    def _js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method 函式主體（大括號平衡）。"""
        pattern = re.compile(
            r'(?:^|\n)\s*' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"showcase/core.js 找不到 {method_name} 方法"
        start = m.end()
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_video_count_pushed_first(self):
        """_actressCoreMetadata 函數體前置 push video_count（在 age 之前）"""
        js = self._js()
        body = self._extract_method_body(js, '_actressCoreMetadata')
        assert 'video_count' in body, \
            "showcase/core.js _actressCoreMetadata 函數體缺少 video_count"
        assert 'showcase.unit.films' in body, \
            "showcase/core.js _actressCoreMetadata 函數體缺少 showcase.unit.films i18n key"

        vc_push = re.search(r'parts\.push\([^)]*video_count[^)]*\)', body)
        age_push = re.search(r'parts\.push\([^)]*\.age[^)]*\)', body)
        assert vc_push is not None, \
            "showcase/core.js _actressCoreMetadata 缺少 parts.push(...video_count...) 行"
        assert age_push is not None, \
            "showcase/core.js _actressCoreMetadata 缺少 parts.push(...age...) 行"
        assert vc_push.start() < age_push.start(), \
            "showcase/core.js _actressCoreMetadata video_count push 必須在 age push 之前（前置）"

    def test_video_count_typeof_number_guard(self):
        """_actressCoreMetadata 函數體含 typeof a.video_count === 'number' guard"""
        js = self._js()
        body = self._extract_method_body(js, '_actressCoreMetadata')
        assert re.search(r"typeof\s+\w+\.video_count\s*===\s*['\"]number['\"]", body), \
            "showcase/core.js _actressCoreMetadata 缺少 typeof a.video_count === 'number' guard"

    def test_films_unit_zh_tw_value(self):
        """locales/zh_TW.json showcase.unit.films == '部作品'"""
        data = json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        assert data["showcase"]["unit"]["films"] == "部作品", \
            f"zh_TW.json showcase.unit.films 應為 '部作品'，目前 {data['showcase']['unit']['films']!r}"

    def test_films_unit_zh_cn_value(self):
        """locales/zh_CN.json showcase.unit.films == '部作品'"""
        data = json.loads((LOCALES_ROOT / "zh_CN.json").read_text(encoding="utf-8"))
        assert data["showcase"]["unit"]["films"] == "部作品", \
            f"zh_CN.json showcase.unit.films 應為 '部作品'，目前 {data['showcase']['unit']['films']!r}"

    def test_films_unit_ja_value(self):
        """locales/ja.json showcase.unit.films == '作品'"""
        data = json.loads((LOCALES_ROOT / "ja.json").read_text(encoding="utf-8"))
        assert data["showcase"]["unit"]["films"] == "作品", \
            f"ja.json showcase.unit.films 應為 '作品'，目前 {data['showcase']['unit']['films']!r}"

    def test_films_unit_en_unchanged(self):
        """locales/en.json showcase.unit.films == ' films'（保留前空格，不變）"""
        data = json.loads((LOCALES_ROOT / "en.json").read_text(encoding="utf-8"))
        assert data["showcase"]["unit"]["films"] == " films", \
            f"en.json showcase.unit.films 應保留為 ' films'，目前 {data['showcase']['unit']['films']!r}"


SHOWCASE_ANIMATIONS_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "animations.js"
)


class TestModeToggleFadeOutGuard:
    """T1: 模式切換動畫補 fade-out（playModeCrossfade 4-arg + toggleActressMode callback 延遲翻轉）"""

    def _core_js(self):
        return SHOWCASE_CORE_JS.read_text(encoding="utf-8")

    def _anim_js(self):
        return SHOWCASE_ANIMATIONS_JS.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method（methodName(...) { ... }）函式主體，大括號平衡。"""
        pattern = re.compile(
            r'(?:^|\n)\s*' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"找不到 {method_name} 方法"
        start = m.end()
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def _extract_property_function_body(self, js, prop_name):
        """抓取 propName: function (...) { ... } 形式的函式主體，大括號平衡。"""
        pattern = re.compile(
            r'\b' + re.escape(prop_name) + r'\s*:\s*function\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"找不到 {prop_name} property function"
        start = m.end()
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_play_mode_crossfade_has_callbacks_param(self):
        """animations.js playModeCrossfade 簽名包含 4 個參數 (oldMode, newMode, params, callbacks)"""
        js = self._anim_js()
        assert re.search(
            r'playModeCrossfade\s*:\s*function\s*\(\s*oldMode\s*,\s*newMode\s*,\s*params\s*,\s*callbacks\s*\)',
            js,
        ), "showcase/animations.js playModeCrossfade 缺少 callbacks 第 4 參數"

    def test_play_mode_crossfade_old_fade_out(self):
        """playModeCrossfade 函數體含 oldEl fade-out (tl.to(oldEl,...) + clearProps:'opacity')"""
        js = self._anim_js()
        body = self._extract_property_function_body(js, 'playModeCrossfade')
        assert re.search(r'tl\s*\.\s*to\s*\(\s*oldEl', body), \
            "playModeCrossfade 函數體缺少 oldEl fade-out (tl.to(oldEl,...))"
        assert re.search(r"clearProps\s*:\s*['\"]opacity['\"]", body), \
            "playModeCrossfade 函數體缺少 clearProps: 'opacity'（避免 CSS transition 殘留）"

    def test_play_mode_crossfade_new_fade_in_preserved(self):
        """playModeCrossfade 函數體保留 newEl fade-in（tl.fromTo(newEl,...) + clearProps:'opacity'）"""
        js = self._anim_js()
        body = self._extract_property_function_body(js, 'playModeCrossfade')
        assert re.search(r'(?:tl\s*\.\s*)?fromTo\s*\(\s*newEl', body), \
            "playModeCrossfade 函數體缺少 newEl fade-in (fromTo(newEl,...))"
        # newEl 段落（從第一次 newEl 出現到結尾）必須有 clearProps
        new_idx = body.find('newEl')
        assert new_idx >= 0, "playModeCrossfade 函數體找不到 newEl 區段"
        new_section = body[new_idx:]
        assert re.search(r"clearProps\s*:\s*['\"]opacity['\"]", new_section), \
            "playModeCrossfade newEl fade-in 段落缺少 clearProps: 'opacity'"

    def test_toggle_actress_mode_uses_callback(self):
        """toggleActressMode 函數體使用 onOldFadeComplete callback，不直接翻轉 showFavoriteActresses"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        assert 'onOldFadeComplete' in body, \
            "toggleActressMode 函數體缺少 onOldFadeComplete callback"
        assert 'playModeCrossfade' in body, \
            "toggleActressMode 函數體缺少 playModeCrossfade 呼叫"
        assert not re.search(
            r'this\.showFavoriteActresses\s*=\s*!\s*this\.showFavoriteActresses',
            body,
        ), "toggleActressMode 不應直接翻轉 this.showFavoriteActresses，應延遲到 callback 內"

    def test_toggle_actress_mode_animgen_guard(self):
        """toggleActressMode 函數體內 _animGeneration 出現 ≥ 2 次（外層 gen + 內層 gen2 race guard）"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        count = len(re.findall(r'_animGeneration', body))
        assert count >= 2, \
            f"toggleActressMode 函數體 _animGeneration 出現次數應 ≥ 2 (外 gen + 內 gen2)，實際 {count}"

    def test_old_caller_backward_compat(self):
        """舊 caller (searchActressFilms / switchMode) 內 playModeCrossfade 呼叫保持 ≤3-arg，不含 onOldFadeComplete"""
        js = self._core_js()
        search_body = self._extract_method_body(js, 'searchActressFilms')
        switch_body = self._extract_method_body(js, 'switchMode')
        # 兩處都應呼叫 playModeCrossfade
        assert 'playModeCrossfade' in search_body, \
            "searchActressFilms 應仍呼叫 playModeCrossfade"
        assert 'playModeCrossfade' in switch_body, \
            "switchMode 應仍呼叫 playModeCrossfade"
        # 兩處都不該帶 onOldFadeComplete（保持原 2-arg 行為）
        assert 'onOldFadeComplete' not in search_body, \
            "searchActressFilms 內 playModeCrossfade 呼叫不應帶 onOldFadeComplete（T1 範圍外，T7 處理）"
        assert 'onOldFadeComplete' not in switch_body, \
            "switchMode 內 playModeCrossfade 呼叫不應帶 onOldFadeComplete（保持影片模式內切換行為不變）"
