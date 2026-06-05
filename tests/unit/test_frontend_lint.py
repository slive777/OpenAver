"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
import json
import re
from pathlib import Path

import pytest

SHOWCASE_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "showcase.html"


class TestShowcaseMetadataGuard:
    """T3: 確保 showcase.html 包含必要 Alpine 綁定（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_showcase_html_contains(self):
        """showcase.html 含 metadata 綁定、lightbox 欄位、searchFromMetadata"""
        html = self._html()
        for expected in [
            "video.series",
            "video.duration",
            "video.director",
            "table-cell-duration",
            "currentLightboxVideo?.director",
            "currentLightboxVideo?.duration",
            "currentLightboxVideo?.series",
            "currentLightboxVideo?.label",
            "lb-details",
            "searchFromMetadata(currentLightboxVideo?.director)",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        # series searchFromMetadata (grid panel or lightbox)
        assert ("searchFromMetadata(video.series)" in html or
                "searchFromMetadata(currentLightboxVideo?.series)" in html), \
            "showcase.html missing: series searchFromMetadata call"


SEARCH_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "search.html"


class TestSearchLightboxMetadataGuard:
    """T4: search.html lightbox metadata bindings (method folded)"""

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def test_search_html_contains(self):
        """search.html lightbox 含 metadata 綁定"""
        html = self._html()
        for expected in [
            "currentLightboxVideo()?.director",
            "currentLightboxVideo()?.duration",
            "currentLightboxVideo()?.series",
            "currentLightboxVideo()?.label",
            "lb-details",
        ]:
            assert expected in html, f"search.html missing: {expected!r}"


SHOWCASE_BASE_JS     = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
SHOWCASE_VIDEOS_JS   = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js"
SHOWCASE_ACTRESS_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-actress.js"
SHOWCASE_LIGHTBOX_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
SHOWCASE_MAIN_JS     = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "main.js"


class TestShowcaseCoreJsSearchableFields:
    """T5: showcase/state-videos.js searchable fields guard (method folded)"""

    def _js(self):
        return SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")

    def _extract_searchable_fields(self, js):
        match = re.search(
            r'const\s+searchable\s*=\s*\[(.*?)\]\.filter\(Boolean\)',
            js, re.DOTALL,
        )
        if not match:
            return set()
        return set(re.findall(r'video\.(\w+)', match.group(1)))

    def test_showcase_js_contains(self):
        """searchable array 含所有必要欄位"""
        js = self._js()
        fields = self._extract_searchable_fields(js)
        assert fields, "showcase/state-videos.js: cannot find 'const searchable = [...].filter(Boolean)'"
        required = {"title", "original_title", "actresses", "number", "maker", "tags",
                    "release_date", "path", "director", "series", "label", "user_tags"}
        missing = required - fields
        assert not missing, f"showcase/state-videos.js searchable missing: {sorted(missing)}"


SETTINGS_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "settings.html"
SCANNER_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "scanner.html"
SCANNER_SCAN_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
SCANNER_BATCH_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-batch.js"
SCANNER_ALIAS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-alias.js"
SCANNER_MAIN_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "main.js"
MOTION_LAB_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
DESIGN_SYSTEM_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "design-system.html"
THEME_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "theme.css"
TAILWIND_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "tailwind.css"


class TestHelpPopoverGuard:
    """38e: help-popover CSS class usage guard (method folded)"""

    def _settings(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _scanner(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def test_settings_html_contains(self):
        """settings.html 含 help-popover classes >=2; 無 broken shadow token"""
        html = self._settings()
        assert html.count('class="help-popover"') >= 2, \
            "settings.html missing: 'class=\"help-popover\"' (x2)"
        assert html.count('class="help-popover-btn"') >= 2, \
            "settings.html missing: 'class=\"help-popover-btn\"' (x2)"
        assert "box-shadow: var(--shadow-4)" not in html, \
            "settings.html should not contain: 'box-shadow: var(--shadow-4)'"

    def test_scanner_html_contains(self):
        """scanner.html 含 help-popover classes; 無 broken shadow token"""
        html = self._scanner()
        assert html.count('class="help-popover"') >= 1, \
            "scanner.html missing: 'class=\"help-popover\"'"
        assert html.count('class="help-popover-btn"') >= 1, \
            "scanner.html missing: 'class=\"help-popover-btn\"'"
        assert "box-shadow: var(--shadow-4)" not in html, \
            "scanner.html should not contain: 'box-shadow: var(--shadow-4)'"


class TestInlineStyleCleanup:
    """T4 守衛：確認 inline style 已清理為 CSS class"""

    def _settings(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _motion_lab(self):
        return MOTION_LAB_HTML.read_text(encoding="utf-8")

    def _design_system(self):
        return DESIGN_SYSTEM_HTML.read_text(encoding="utf-8")

    def test_settings_no_inline_position_relative_for_popover(self):
        """settings.html 不應有 style="position: relative;" 用於 popover 錨點"""
        html = self._settings()
        assert 'style="position: relative;"' not in html, \
            'settings.html 仍含 style="position: relative;"，應改用 class="... popover-anchor"'

    # test_theme_css_no_scoped_manual_input removed in T55b — superseded by
    # stylelint `selector-disallowed-list` rule (/:is\([^)]*manual-input/).

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
SETTINGS_CONFIG_JS    = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
SETTINGS_PROVIDERS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-providers.js"
SETTINGS_UI_JS        = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-ui.js"
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


MAIN_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "main.js"


class TestTimerListenerGuard:
    """T2(40b): 守衛 main.js window listener 具名 ref + cleanup removeEventListener"""

    def _index(self):
        return MAIN_JS.read_text(encoding="utf-8")

    def _base(self):
        return BASE_JS.read_text(encoding="utf-8")

    def test_index_uses_set_timer_for_cover_height(self):
        """main.js $watch('searchResults') 使用 _setTimer('updateCoverHeight'"""
        js = self._index()
        assert "_setTimer('updateCoverHeight'" in js, \
            "main.js $watch('searchResults') 應改用 _setTimer('updateCoverHeight', ...) 取代裸 setTimeout"

    def test_index_no_bare_settimeout_for_cover_height(self):
        """main.js 不含裸 setTimeout(() => this._updateCoverHeight()"""
        js = self._index()
        assert "setTimeout(() => this._updateCoverHeight()" not in js, \
            "main.js 仍含裸 setTimeout(() => this._updateCoverHeight()，應改為 _setTimer"

    def test_index_pywebview_handler_assigned(self):
        """main.js pywebview-files listener 賦值給 this._pywebviewFilesHandler"""
        js = self._index()
        assert "this._pywebviewFilesHandler =" in js, \
            "main.js 應將 pywebview-files handler 賦值給 this._pywebviewFilesHandler（具名 ref）"

    def test_index_resize_handler_assigned(self):
        """main.js resize listener 賦值給 this._resizeHandler"""
        js = self._index()
        assert "this._resizeHandler =" in js, \
            "main.js 應將 resize handler 賦值給 this._resizeHandler（具名 ref）"

    def test_index_cleanup_removes_pywebview_listener(self):
        """main.js cleanup() 含 removeEventListener('pywebview-files', this._pywebviewFilesHandler)"""
        js = self._index()
        assert "removeEventListener('pywebview-files', this._pywebviewFilesHandler)" in js, \
            "main.js cleanup() 應 removeEventListener('pywebview-files', this._pywebviewFilesHandler)"

    def test_index_cleanup_removes_resize_listener(self):
        """main.js cleanup() 含 removeEventListener('resize', this._resizeHandler)"""
        js = self._index()
        assert "removeEventListener('resize', this._resizeHandler)" in js, \
            "main.js cleanup() 應 removeEventListener('resize', this._resizeHandler)"

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
        return SETTINGS_UI_JS.read_text(encoding="utf-8")

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
        return SCANNER_SCAN_JS.read_text(encoding="utf-8")

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

    def test_jellyfin_i18n_keys_exist(self):
        """zh_TW.json 包含 40c 所有 jellyfin check i18n key"""
        zh_tw = self._zh_tw()
        for key in self.REQUIRED_KEYS + ["scanner.stats.jellyfin_check_done_ok"]:
            val = self._get_nested(zh_tw, key)
            assert val, f"zh_TW.json missing: {key!r}"


class TestShowcaseKeyboardGuard:
    """Phase 40d-T2: Showcase 鍵盤 preventDefault 守衛"""

    CORE_JS = SHOWCASE_LIGHTBOX_JS

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
        # 女優 state 分散於 state-base/actress/lightbox，合併讀取確保覆蓋
        return (
            SHOWCASE_BASE_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        )

    def test_actress_js_contains(self):
        """state 屬性、module-level 陣列、method 名、互斥 reset、saveState/restoreState、keydown 全部存在"""
        js = self._js()
        for expected in [
            # module-level arrays
            "var _actresses = []",
            "var _filteredActresses = []",
            # Alpine state properties
            "showFavoriteActresses",
            "actressCount",
            "filteredActressCount",
            "paginatedActresses",
            "actressSearch",
            "actressSort",
            "actressOrder",
            "actressLoading",
            "actressLightboxIndex",
            "currentLightboxActress",
            "_actressChipsExpanded",
            "_addActressName",
            "_addingActress",
            "_addDropdownOpen",
            "_videoChipsExpanded",
            # core methods
            "toggleActressMode",
            "loadActresses",
            "applyActressFilterAndSort",
            "onActressSearchChange",
            "onActressSortChange",
            "toggleActressOrder",
            # lightbox methods
            "openActressLightbox",
            "closeActressLightbox",
            "prevActressLightbox",
            "nextActressLightbox",
            "_setActressLightboxIndex",
            # sort logic
            "cupRank",
            # mutual exclusion
            "currentLightboxActress = null",
            "_videoChipsExpanded = false",
            # saveState / restoreState
            "_persistedShowcase.showFavoriteActresses = this.showFavoriteActresses",
            "_persistedShowcase.actressSort = this.actressSort",
            "_persistedShowcase.actressOrder = this.actressOrder",
            "showFavoriteActresses === true",
            "state.actressSort",
            "state.actressOrder",
            # handleKeydown
            "this.currentLightboxActress",
            "this.prevActressLightbox()",
            "this.nextActressLightbox()",
        ]:
            assert expected in js, \
                f"showcase/core.js (state-base/actress/lightbox) missing: {expected!r}"

    def test_actress_js_excludes(self):
        """_rescraping 不應存在（49b-T5 已刪除 rescrape dead code）"""
        js = self._js()
        for forbidden in ["_rescraping"]:
            assert forbidden not in js, \
                f"showcase/core.js should not contain: {forbidden!r}"


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
        # actressLightboxSource / openActressLightbox / closeLightbox / handleKeydown → state-lightbox.js
        # openHeroCardLightbox → state-lightbox.js
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        )

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

    def test_source_state_init_and_html(self):
        """core.js Alpine state 含 actressLightboxSource: null；showcase.html camera button 含 grid 綁定"""
        js = self._js()
        assert re.search(r'actressLightboxSource\s*:\s*null', js), \
            "showcase/core.js missing: actressLightboxSource: null (Alpine state init)"
        html = self._html()
        assert "actressLightboxSource === 'grid'" in html, \
            "showcase.html missing: actressLightboxSource === 'grid' (camera button x-show binding)"

    def test_source_set_in_open_methods(self):
        """openHeroCardLightbox 設 'hero'；closeLightbox reset null"""
        js = self._js()
        for method_name, pattern, msg in [
            (
                'openHeroCardLightbox',
                r"this\.actressLightboxSource\s*=\s*['\"]hero['\"]",
                "openHeroCardLightbox 函數體缺少 this.actressLightboxSource = 'hero'",
            ),
            (
                'closeLightbox',
                r"this\.actressLightboxSource\s*=\s*null",
                "closeLightbox 函數體缺少 this.actressLightboxSource = null（reset）",
            ),
        ]:
            body = self._extract_method_body(js, method_name)
            assert re.search(pattern, body), \
                f"showcase/core.js {method_name} missing: {msg}"

    def test_open_actress_lightbox_sets_grid(self):
        """openActressLightbox 函數體至少 2 處設 'grid'（首次進入 + 切換女優分支）"""
        js = self._js()
        body = self._extract_method_body(js, 'openActressLightbox')
        matches = re.findall(r"this\.actressLightboxSource\s*=\s*['\"]grid['\"]", body)
        assert len(matches) >= 2, \
            f"showcase/core.js openActressLightbox 應至少 2 處設 'grid'（首次進入 + 切換女優），目前 {len(matches)} 處"


class TestShowcasePreciseMatchState:
    """Phase 44b-T1: Showcase 精準匹配 Alpine state 守衛（method folded）"""

    def _js(self):
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_BASE_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        )

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_actress_js_contains(self):
        """state 屬性、methods、trigger points、stale guard 全部存在"""
        js = self._js()
        for expected in [
            # module-level flag
            "var _actressesLoaded",
            # Alpine state properties
            "_isPreciseActressMatch",
            "_matchedActress",
            "_preciseMatchSource",
            "_favoriteHeartLoading",
            # methods
            "_checkPreciseActressMatch",
            "_clearPreciseMatch",
            # trigger points (checked globally)
            "_checkPreciseActressMatch",
            "_clearPreciseMatch",
            # stale guard
            "capturedTerm",
            # heart method
            "addFavoriteFromSearch",
        ]:
            assert expected in js, f"showcase/core.js missing: {expected!r}"
        # lazy load flag
        assert ("_actressesLoaded = true" in js or "_setActressesLoaded(true)" in js), \
            "showcase state missing: _actressesLoaded set to true"
        # _favoriteHeartLoading used in addFavoriteFromSearch
        idx = js.find("addFavoriteFromSearch")
        assert idx != -1, "showcase/core.js missing: 'addFavoriteFromSearch'"
        block = js[idx:idx+2000]
        assert "_favoriteHeartLoading" in block, \
            "addFavoriteFromSearch missing: '_favoriteHeartLoading'"

    def test_actress_html_contains(self):
        """showcase.html 含 addFavoriteFromSearch 和 _isPreciseActressMatch"""
        html = self._html()
        for expected in ["addFavoriteFromSearch", "_isPreciseActressMatch"]:
            assert expected in html, f"showcase.html missing: {expected!r}"

class TestGeminiLocaleKeyGuard:
    """39a-T3: 守衛 settings.js 不再使用 gemini_n_flash_models locale key"""

    def _js(self):
        return SETTINGS_PROVIDERS_JS.read_text(encoding="utf-8")

    def test_settings_js_no_gemini_n_flash_models(self):
        """settings.js 不應出現 gemini_n_flash_models（已替換為 connected_n_models）"""
        js = self._js()
        assert "gemini_n_flash_models" not in js, \
            "settings.js 仍含 gemini_n_flash_models，應改為 connected_n_models"


GRID_MODE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"


class TestLoadMoreButton:
    """39a-T4: Load More button + hasMoreResults + loadMore trigger (method folded)"""

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

    def test_html_and_js_contains(self):
        """search.html + base/grid-mode/navigation/animations JS 含 load more 所有必要字串"""
        html = SEARCH_HTML.read_text(encoding="utf-8")
        for expected in [
            '@click="gridLoadMore()"',
            "t('search.button.load_more')",
            "hasMoreResults && displayMode === 'grid'",
        ]:
            assert expected in html, f"search.html missing: {expected!r}"
        base = BASE_JS.read_text(encoding="utf-8")
        assert "hasMoreResults" in base, "base.js missing: 'hasMoreResults'"
        gm = GRID_MODE_JS.read_text(encoding="utf-8")
        assert "await this.loadMore('lightbox')" in gm, \
            "grid-mode.js missing: \"await this.loadMore('lightbox')\""
        nav = NAVIGATION_JS.read_text(encoding="utf-8")
        for expected in ["async loadMore(trigger", "return { loadedCount", "async gridLoadMore()"]:
            assert expected in nav, f"navigation.js missing: {expected!r}"
        anim = ANIMATIONS_JS.read_text(encoding="utf-8")
        assert "playAppendCascade" in anim, "animations.js missing: 'playAppendCascade'"

    def test_locales_have_load_more_key(self):
        """4 locales 含 search.button.load_more key"""
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            val = self._get_nested(data, "search.button.load_more")
            assert val, f"{locale_file} missing: search.button.load_more"


NAVIGATION_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"
ANIMATIONS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "animations.js"


class TestCodexFixes:
    """39a Codex review 修正守衛"""

    def _navigation_js(self):
        return NAVIGATION_JS.read_text(encoding="utf-8")

    def _settings_js(self):
        return SETTINGS_PROVIDERS_JS.read_text(encoding="utf-8")

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
        return SETTINGS_PROVIDERS_JS.read_text(encoding="utf-8")

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
        return SETTINGS_PROVIDERS_JS.read_text(encoding="utf-8")

    def _config_js(self):
        return SETTINGS_CONFIG_JS.read_text(encoding="utf-8")

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
        js = self._config_js()
        assert "use_custom_model: this.openaiUseCustomModel" in js, \
            "settings/state-config.js saveConfig() 的 openai 物件應含 use_custom_model: this.openaiUseCustomModel，否則重載後 custom 模式丟失"

    def test_openai_config_loads_use_custom_model(self):
        """loadConfig() 應從 config 還原 openaiUseCustomModel，而非固定從 false 重設"""
        js = self._config_js()
        assert "config.translate.openai?.use_custom_model" in js, \
            "settings/state-config.js loadConfig() 應含 config.translate.openai?.use_custom_model 讀取，否則重載後 custom 模式無法還原"

    def test_fetch_openai_models_has_source_param(self):
        """fetchOpenAIModels() 應接受 source 參數，區分 auto-fetch 與手動 Fetch"""
        js = self._js()
        assert "source = 'manual'" in js, \
            "settings.js fetchOpenAIModels() 應含 source = 'manual' 預設參數，避免共享 boolean 競態"


MOTION_LAB_STATE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab-state.js"


class TestMotionLabStateGuard:
    """39b-T1: motion_lab.html inline x-data 已抽離至 motion-lab-state.js (method folded)"""

    def _html(self):
        return MOTION_LAB_HTML.read_text(encoding="utf-8")

    def _js(self):
        return MOTION_LAB_STATE_JS.read_text(encoding="utf-8")

    def test_motion_lab_html_contains(self):
        """motion_lab.html 含 motionLabPage factory ref + state JS + no inline x-data block"""
        html = self._html()
        for expected in [
            'x-data="motionLabPage"',
            "motion-lab-state.js",
        ]:
            assert expected in html, f"motion_lab.html missing: {expected!r}"
        pattern = re.compile(r'x-data="([^"]{100,})"')
        matches = pattern.findall(html)
        assert len(matches) == 0, \
            f"motion_lab.html has {len(matches)} x-data attributes >100 chars (inline object not removed)"
        # no defer on state script
        tag_pattern = re.compile(r'<script[^>]*motion-lab-state\.js[^>]*>')
        tags = tag_pattern.findall(html)
        assert len(tags) > 0, "motion_lab.html missing: motion-lab-state.js script tag"
        for tag in tags:
            assert "defer" not in tag, \
                f"motion_lab.html motion-lab-state.js script tag should not have defer: {tag}"

    def test_motion_lab_state_js_contains(self):
        """motion-lab-state.js 存在且含必要方法"""
        assert MOTION_LAB_STATE_JS.exists(), \
            f"motion-lab-state.js not found: {MOTION_LAB_STATE_JS}"
        js = self._js()
        for expected in [
            "function motionLabPage()",
            "init()",
            "destroy()",
        ]:
            assert expected in js, f"motion-lab-state.js missing: {expected!r}"


class TestScannerStateGuard:
    """39b-T2: 守衛 scanner.html inline script 已抽離至 scanner.js"""

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def test_scanner_html_has_pre_alpine_module_block(self):
        """scanner.html 含 pre_alpine_module block override，且含 scanner/main.js module script（54c-T2）"""
        html = self._html()
        assert "pre_alpine_module" in html, \
            "scanner.html 缺少 {% block pre_alpine_module %}（54c-T2 未加入 main.js 載入）"
        assert "scanner/main.js" in html, \
            "scanner.html pre_alpine_module block 缺少 main.js module script"

    def test_scanner_no_inline_script(self):
        """scanner.html 的 extra_js 區段（若存在）不含超過 10 行的 inline script"""
        import re
        html = self._html()
        pattern = re.compile(r'\{%-?\s*block extra_js\s*-?%\}(.*?)\{%-?\s*endblock\s*-?%\}', re.DOTALL)
        match = pattern.search(html)
        if match is None:
            return  # extra_js block 已移除，守衛通過
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

    def test_all_locales_cta_keys(self):
        """四語系 5 個 CTA key 新值正確"""
        for locale_file, keys in self.EXPECTED.items():
            data = self._locale(locale_file)
            for key, expected in keys.items():
                actual = self._get_nested(data, key)
                assert actual == expected, \
                    f"{locale_file} missing: {key!r} expected {expected!r}, got {actual!r}"


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

    def test_all_locales_have_toast_keys(self):
        """四語系 search.toast.* 必須全部存在且非空"""
        for locale in ['zh_TW', 'zh_CN', 'en', 'ja']:
            data = self._locale(f"{locale}.json")
            for key in self.EXPECTED_KEYS:
                dotted = f"search.toast.{key}"
                val = self._get_nested(data, dotted)
                assert val is not None, \
                    f"{locale}.json missing: {dotted!r}"
                assert isinstance(val, str) and len(val) > 0, \
                    f"{locale}.json {dotted!r} must not be empty string"


class TestSimilarModeI18nGuard:
    """57c-T1a: 守衛 Similar Mode 入口按鈕 i18n key（zh_TW.json）"""

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

    def test_zh_tw_has_similar_mode_button_aria_label(self):
        """zh_TW.json 必須有 similar_mode.button_aria_label，且為非空字串"""
        data = self._locale("zh_TW.json")
        val = self._get_nested(data, "similar_mode.button_aria_label")
        assert val is not None, \
            "zh_TW.json missing: 'similar_mode.button_aria_label'"
        assert isinstance(val, str) and len(val) > 0, \
            "zh_TW.json 'similar_mode.button_aria_label' must not be empty string"


class TestSimilarStageGuard:
    """57c-T4+T5: 守衛 state-similar.js 整合 contract — 確保新 mixin 串入 main.js mergeState
    鏈、SIMILAR_ANCHORS 揭露給 Alpine template、.similar-stage sibling DOM 在 showcase.html 對齊。
    """

    SHOWCASE_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase"
    STATE_SIMILAR_JS = SHOWCASE_DIR / "state-similar.js"
    MAIN_JS = SHOWCASE_DIR / "main.js"

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _state_similar(self):
        return self.STATE_SIMILAR_JS.read_text(encoding="utf-8")

    def _main(self):
        return self.MAIN_JS.read_text(encoding="utf-8")

    def test_state_similar_file_exists(self):
        """state-similar.js 必須存在（57c-T4+T5 rename）"""
        assert self.STATE_SIMILAR_JS.exists(), \
            f"state-similar.js missing at {self.STATE_SIMILAR_JS!s}"

    def test_main_js_imports_and_merges_state_similar(self):
        """main.js 必須 import stateSimilar 並插入 mergeState 鏈（v0.8.4 descriptor-preserving 規範）"""
        src = self._main()
        assert "from '@/showcase/state-similar.js'" in src, \
            "main.js missing: import { stateSimilar } from '@/showcase/state-similar.js'"
        # mergeState 鏈整合：stateSimilar.call(this) 必須出現
        assert "stateSimilar.call(this)" in src, \
            "main.js mergeState chain missing: stateSimilar.call(this)"

    def test_state_similar_exports_similar_anchors(self):
        """SIMILAR_ANCHORS 必須 export（Alpine template x-for 用：'anchor in SIMILAR_ANCHORS'）"""
        src = self._state_similar()
        assert "export const SIMILAR_ANCHORS" in src, \
            "state-similar.js missing: export const SIMILAR_ANCHORS = ANCHORS.map(...)"

    def test_state_similar_exposes_similar_mode_methods(self):
        """state-similar.js 必須 export stateSimilar factory 並含 4 主流程 method（CD-57c-5）"""
        src = self._state_similar()
        assert re.search(r"export\s+function\s+stateSimilar\s*\(", src), \
            "state-similar.js missing: export function stateSimilar()"
        for method in ("openSimilarMode", "closeSimilarMode", "initSimilarStage", "destroySimilarStage"):
            assert method in src, \
                f"state-similar.js missing method: {method}"

    def test_similar_stage_sibling_dom_in_showcase_html(self):
        """showcase.html 必須含 .similar-stage sibling DOM（z-index 1501，x-effect lifecycle）"""
        html = self._html()
        # backdrop class
        assert "similar-stage" in html, "showcase.html missing: .similar-stage sibling div"
        # x-effect lifecycle 觸發 init/destroy（必須沿用 plan §6 §B 範例）
        assert "initSimilarStage()" in html and "destroySimilarStage()" in html, \
            "showcase.html missing x-effect: similarModeOpen ? initSimilarStage() : destroySimilarStage()"
        # 960×620 inner stage（spec §1 CD-56C-11）
        assert "similar-stage-inner" in html, \
            "showcase.html missing: .similar-stage-inner (960×620 design-space container)"
        # Alpine x-for 對齊 SIMILAR_ANCHORS export
        assert "SIMILAR_ANCHORS" in html, \
            "showcase.html missing: SIMILAR_ANCHORS reference (x-for=\"anchor in SIMILAR_ANCHORS\")"

    # NOTE (v0.8.6 pre-merge SA-pre-6): test_no_filter_brightness_in_clip_files
    # 已遷移到 eslint.config.mjs SEL_FILTER_BRIGHTNESS（Group 5 + Group 5b），對齊
    # CLAUDE.md「Lint 守衛規則」：「某個 JS/CSS 字串不應出現」→ eslint rule。

    def test_no_slot_icon_overlay_in_templates(self):
        """56c-T4fix7: showcase.html + motion_lab.html 整檔不含 slot-icon-overlay 字串
        （spec DoD 3：8 卡不配置任何 action button；整檔守防回歸）"""
        MOTION_LAB_HTML = (
            Path(__file__).parent.parent.parent
            / "web" / "templates" / "motion_lab.html"
        )
        files = [
            (SHOWCASE_HTML, "showcase.html"),
            (MOTION_LAB_HTML, "motion_lab.html"),
        ]
        for fpath, fname in files:
            content = fpath.read_text(encoding="utf-8")
            assert "slot-icon-overlay" not in content, (
                f"{fname} contains 'slot-icon-overlay' — spec §3 Phase 56c DoD 3 禁止 8 卡配置"
                " action button；DOM + CSS 需完全移除（56c-T4fix7 防回歸）"
            )

    def test_no_clip_selector_in_js(self):
        """57c-T4+T5 Codex P1-1 guard: JS 不得用 closest/matches/querySelector 搭配 .clip- selector。
        唯一合法位置：core/clip/ Python 模組（與 JS selector 無關）與 tests/unit/test_clip_*.py。
        ghost-fly.js 已改用 .similar-stage（57c-T4 修正）。
        排除：pages/motion-lab/ — .clip-lab-* 是 motion-lab sandbox 專屬（Non-Goal #12）。"""
        JS_ROOT = Path(__file__).parent.parent.parent / "web" / "static" / "js"
        MOTION_LAB_DIR = JS_ROOT / "pages" / "motion-lab"
        pattern = re.compile(
            r"""(?:closest|matches|querySelector|querySelectorAll)\s*\(\s*['"][^'"]*\.clip-"""
        )
        violations = []
        for js_file in JS_ROOT.rglob("*.js"):
            # motion-lab sandbox 的 .clip-lab-* 是 Non-Goal #12，不在此 guard 範圍
            try:
                js_file.relative_to(MOTION_LAB_DIR)
                continue  # 在 motion-lab/ 下，跳過
            except ValueError:
                pass
            content = js_file.read_text(encoding="utf-8")
            for lineno, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    violations.append(f"{js_file.relative_to(JS_ROOT)}:{lineno}: {line.strip()}")
        assert not violations, (
            "JS 中 .clip- selector 被用於 closest/matches/querySelector — "
            "應改用 .similar-stage（或其他已更名的 selector）：\n"
            + "\n".join(violations)
        )

    def test_no_clip_alpine_methods_in_showcase_and_similar(self):
        """57c-T4+T5 Codex P1-2 guard: showcase.html 與 state-similar.js 不得出現舊的
        *Clip* Alpine method 名（如 onClipMobileCardClick / playClipMainVideo 等）。
        pattern：\\b(?:on|play|build|calc|destroy|init|open|close)Clip[A-Z]
        motion_lab.html 的 .clip-lab-* 不在此 guard 範圍（Non-Goal #12）。"""
        SIMILAR_JS = (
            Path(__file__).parent.parent.parent
            / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
        )
        pattern = re.compile(r"\b(?:on|play|build|calc|destroy|init|open|close)Clip[A-Z]")
        files_to_check = [
            (SHOWCASE_HTML, "showcase.html"),
            (SIMILAR_JS, "state-similar.js"),
        ]
        violations = []
        for fpath, fname in files_to_check:
            content = fpath.read_text(encoding="utf-8")
            for lineno, line in enumerate(content.splitlines(), 1):
                m = pattern.search(line)
                if m:
                    violations.append(f"{fname}:{lineno}: {line.strip()} (matched: {m.group()})")
        assert not violations, (
            "舊的 *Clip* Alpine method 名稱殘留 — "
            "應改用對應的 *Similar* 名稱（57c-T4+T5 rename）：\n"
            + "\n".join(violations)
        )

    def test_no_clip_stage_selector_in_ghost_fly(self):
        """57c-T4+T5 Codex P1-1 guard: ghost-fly.js 不得用 closest('.clip-stage')。
        57c 已改為 closest('.similar-stage')；此 guard 防止回歸。"""
        GHOST_FLY_JS = (
            Path(__file__).parent.parent.parent
            / "web" / "static" / "js" / "shared" / "ghost-fly.js"
        )
        content = GHOST_FLY_JS.read_text(encoding="utf-8")
        assert "closest('.clip-stage')" not in content and 'closest(".clip-stage")' not in content, (
            "ghost-fly.js 含 closest('.clip-stage') — 應為 closest('.similar-stage')（57c-T4 修正）"
        )


SEARCH_STATE_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state"


class TestNoAlertInSearchJs:
    """39c-T2c + T3.6: search/scanner/settings JS 不應使用原生 alert()，改用 showToast / fluent-modal
    (A-class alert tests removed in T55c; clipboard E-class tests retained below)
    """

    def test_scanner_clipboard_has_availability_guard(self):
        """T3.6 P2 fix: scanner/state-scan.js 兩處 clipboard call 必須有 availability guard

        navigator.clipboard 在 HTTP / 舊 WebView 為 undefined，
        若直接呼叫 navigator.clipboard.writeText(...) 會在 property access 階段
        sync throw TypeError，.then().catch() chain 的 .catch 完全不會跑，
        導致 copyLogs 的 fail modal / copyOutputPath 的 error toast 被跳過。
        守衛 if (!navigator.clipboard?.writeText) 必須在兩處 clipboard call 之前。
        """
        content = SCANNER_SCAN_JS.read_text(encoding="utf-8")
        # 兩處 copy 點都應該有 ?. optional chaining guard
        guard_count = content.count("navigator.clipboard?.writeText")
        assert guard_count >= 2, (
            f"scanner/state-scan.js 應該有至少 2 處 navigator.clipboard?.writeText 守衛 "
            f"（copyLogs + copyOutputPath），目前只有 {guard_count} 處。"
            "若沒守衛，clipboard API 不存在時 .catch() 完全不會觸發。"
        )

    def test_all_clipboard_writetext_files_have_availability_guard(self):
        """T3.7: 全 web/static/js 任何使用 navigator.clipboard.writeText 的檔案
        必須同時含 ?. optional chaining 守衛形式（navigator.clipboard?.writeText）。

        此守衛防止未來新檔案再犯同類 pre-existing bug（HTTP / 舊 WebView
        clipboard undefined 時 sync TypeError 跳過 .catch chain）。
        既知合法檔（截至 T3.7）：scanner.js（×2 + ×2 guards）、help.js、
        result-card.js、showcase/core.js — 全部含 ?. 守衛形式。
        """
        js_root = Path(__file__).parent.parent.parent / "web" / "static" / "js"
        offenders = []
        for js_file in js_root.rglob("*.js"):
            text = js_file.read_text(encoding="utf-8")
            if "navigator.clipboard.writeText" not in text:
                continue
            if "navigator.clipboard?.writeText" not in text:
                offenders.append(str(js_file.relative_to(js_root)))
        assert not offenders, (
            f"以下檔案使用 navigator.clipboard.writeText 但缺 ?. 守衛形式："
            f"{offenders}。"
            "請改寫成 if (!navigator.clipboard?.writeText) { ...fallback...; return; } "
            "或 navigator.clipboard?.writeText ? ... : fallback 三元，"
            "避免 clipboard undefined 時 sync TypeError 跳過 .catch。"
        )


class TestNavigateLoadMore:
    """T3b: navigate() loadMore + state-first slide (method folded)"""

    NAVIGATION_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"

    def _js(self):
        return self.NAVIGATION_JS.read_text(encoding="utf-8")

    def _navigate_body(self):
        js = self._js()
        start = js.find("navigate(delta)")
        assert start != -1, "navigation.js missing: 'navigate(delta)'"
        return js[start:start + 3000]

    def test_navigate_js_contains(self):
        """navigation.js navigate() 含 async + loadMore"""
        js = self._js()
        assert "async navigate(delta)" in js, "navigation.js missing: 'async navigate(delta)'"
        body = self._navigate_body()
        for expected in ["await this.loadMore('detail')", "this.currentIndex = result.oldLength"]:
            assert expected in body, f"navigation.js navigate() missing: {expected!r}"

    def test_navigate_state_before_slide_in(self):
        """navigate(): currentIndex update before playSlideIn (state-first)"""
        body = self._navigate_body()
        state_pos = body.find("this.currentIndex = result.oldLength")
        slide_in_pos = body.find("playSlideIn", state_pos if state_pos != -1 else 0)
        assert state_pos != -1 and slide_in_pos != -1, \
            "navigation.js navigate() missing state update or playSlideIn"
        assert state_pos < slide_in_pos, \
            "navigation.js navigate(): currentIndex must update before playSlideIn"


class TestNextLightboxLoadMore:
    """T3c: nextLightboxVideo() loadMore + state-first crossfade (method folded)"""

    def _js(self):
        return GRID_MODE_JS.read_text(encoding="utf-8")

    def _next_lightbox_body(self):
        js = self._js()
        start = js.find("nextLightboxVideo()")
        assert start != -1, "grid-mode.js missing: 'nextLightboxVideo()'"
        return js[start:start + 3000]

    def test_next_lightbox_js_contains(self):
        """grid-mode.js nextLightboxVideo() 含 async + loadMore + state updates"""
        js = self._js()
        assert "async nextLightboxVideo()" in js, \
            "grid-mode.js missing: 'async nextLightboxVideo()'"
        body = self._next_lightbox_body()
        for expected in [
            "await this.loadMore('lightbox')",
            "this.currentIndex = result.oldLength",
            "this.lightboxIndex = result.oldLength",
        ]:
            assert expected in body, f"grid-mode.js nextLightboxVideo() missing: {expected!r}"

    def test_next_lightbox_state_before_switch(self):
        """T3c: currentIndex update before playLightboxSwitch (state-first)"""
        body = self._next_lightbox_body()
        state_pos = body.find("this.currentIndex = result.oldLength")
        switch_pos = body.find("playLightboxSwitch", state_pos if state_pos != -1 else 0)
        assert state_pos != -1, "grid-mode.js nextLightboxVideo() missing: 'this.currentIndex = result.oldLength'"
        assert switch_pos != -1, \
            "grid-mode.js nextLightboxVideo() missing: 'playLightboxSwitch'"
        assert state_pos < switch_pos, \
            "grid-mode.js nextLightboxVideo(): currentIndex must update before playLightboxSwitch"


RESULT_CARD_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js"
PATH_UTILS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "components" / "path-utils.js"
FILE_LIST_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "file-list.js"


class TestUserTagsApiGuard:
    """41b-T3: 確保 confirmAddTag 和 removeUserTag 改接 /api/user-tags API（method folded）"""

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

    def test_result_card_js_contains(self):
        """result-card.js 含 API 呼叫、async functions、file-level user_tags、fetch helper"""
        content = self._result_card()
        for expected in [
            "user-tags",
            "async confirmAddTag()",
            "async removeUserTag(",
            "fileList[this.currentFileIndex].user_tags",
            "currentUserTags()",
            "fetchUserTagsForCurrent",
        ]:
            assert expected in content, f"result-card.js missing: {expected!r}"
        # not-in guards
        for forbidden in ["pathToFileUri", "c.user_tags.push(tag)"]:
            assert forbidden not in content, f"result-card.js should not contain: {forbidden!r}"
        # fetchUserTagsForCurrent writes to file-level
        idx = content.find("async fetchUserTagsForCurrent()")
        assert idx != -1, "result-card.js missing: 'async fetchUserTagsForCurrent()'"
        func_body = content[idx:idx+800]
        has_direct = "fileList[this.currentFileIndex].user_tags" in func_body
        has_captured_ref = ("file.user_tags" in func_body and
                            "this.fileList?.[this.currentFileIndex]" in func_body)
        assert has_direct or has_captured_ref, \
            "fetchUserTagsForCurrent missing file-level user_tags write"

    def test_search_html_contains(self):
        """search.html 含 user-tags 守衛 + currentUserTags()"""
        html = self._html()
        for expected in [
            "listMode === \'file\'",
            "fileList[currentFileIndex]?.path",
            "currentUserTags()",
        ]:
            assert expected in html, f"search.html missing: {expected!r}"

    def test_path_utils_and_locales(self):
        """path-utils.js 無 pathToFileUri + 有 pathToDisplay；locales 含 tag_api_failed"""
        pu = self._path_utils()
        assert "pathToFileUri" not in pu, "path-utils.js should not contain: 'pathToFileUri'"
        assert "pathToDisplay" in pu, "path-utils.js missing: 'pathToDisplay'"
        # file-list.js user_tags init
        file_list_content = FILE_LIST_JS.read_text(encoding="utf-8")
        assert "user_tags: []" in file_list_content, "file-list.js missing: 'user_tags: []'"
        # locales
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            val = self._get_nested(data, "search.error.tag_api_failed")
            assert val, f"{locale_file} missing: search.error.tag_api_failed key"

class TestShowcaseActressTemplate:
    """Phase 44a-T3: 守衛 showcase.html 含有女優模式 UI 結構（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_showcase_html_contains(self):
        """showcase.html 含女優模式所有必要 UI 結構字串"""
        html = self._html()
        for expected in [
            "toggleActressMode()",
            "showFavoriteActresses",
            "actressSearch",
            "paginatedActresses",
            "actress-card",
            "\'actress:\'",
            "openActressLightbox(index)",
            "actressLoading",
            "actressCount === 0",
            "actress.photo_url",
            "actress-no-photo",
            "actress-card-footer",
            "actressSort",
            "!showFavoriteActresses",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"

class TestShowcaseActressLightbox:
    """Phase 44a-T4: Actress Lightbox layout + chips + nav（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")

    def test_showcase_html_contains(self):
        """showcase.html 含女優 lightbox 所有必要 UI 結構"""
        html = self._html()
        for expected in [
            "currentLightboxActress",
            "currentLightboxVideo && !currentLightboxActress",
            "actress-lightbox-meta",
            "lb-chips-more",
            "prevActressLightbox()",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"

    def test_actress_js_contains(self):
        """state-actress.js 含 lightbox 必要 methods"""
        js = self._js()
        for expected in [
            "_actressCoreMetadata",
            "_allInfoChips",
            "_chipsLimit",
            "_visibleAliases",
            "_visibleInfoChips",
            "_visibleVideoTags",
        ]:
            assert expected in js, f"state-actress.js missing: {expected!r}"

class TestShowcaseActressCRUD:
    """Phase 44a-T5: Actress CRUD guards (method folded)"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")

    def test_actress_js_contains(self):
        """state-actress.js 含 CRUD methods"""
        js = self._js()
        for expected in [
            "addFavoriteActress",
            "openRemoveActressModal",
            "confirmRemoveActress",
            "cancelRemoveActressModal",
            "searchActressFilms",
        ]:
            assert expected in js, f"state-actress.js missing: {expected!r}"
        assert "rescrapeActress" not in js, \
            "state-actress.js should not contain: 'rescrapeActress'"

    def test_showcase_html_contains(self):
        """showcase.html 含 CRUD handlers; searchActressFilms >=2; 無 rescrapeActress"""
        html = self._html()
        for expected in ["_addActressName", "addFavoriteActress()", "openRemoveActressModal()"]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        assert html.count("searchActressFilms(") >= 2, \
            "showcase.html missing: 'searchActressFilms(' (x2)"
        assert "rescrapeActress()" not in html, \
            "showcase.html should not contain: 'rescrapeActress()'"


class TestShowcaseActressCardFooter:
    """Phase 44c-T2: Actress Card Footer guards (method folded)"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")

    def test_actress_html_contains(self):
        """showcase.html actress card footer 含 footer-default + footer-hover 結構"""
        html = self._html()
        for expected in ["footer-default", "_actressCardMiddle", "footer-hover", "_actressHoverInfo"]:
            assert expected in html, f"showcase.html missing: {expected!r}"

    def test_actress_js_contains(self):
        """state-actress.js 含 footer 必要方法"""
        js = self._js()
        for expected in ["_actressCardMiddle", "_actressHoverInfo", "actressSort"]:
            assert expected in js, f"state-actress.js missing: {expected!r}"
        # _actressHoverInfo should not include age
        m = re.search(r'_actressHoverInfo\(actress\)\s*\{(.+?)^\s{8}\},', js, re.DOTALL | re.MULTILINE)
        if m:
            assert "actress.age" not in m.group(1), \
                "state-actress.js _actressHoverInfo should not contain: 'actress.age'"


class TestShowcaseActressI18n:
    """Phase 44a-T7: showcase actress i18n keys (method folded)"""

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

    def test_all_locales_actress_keys(self):
        """4 locales 含 23 個 showcase actress keys"""
        keys = [
            "showcase.mode.actress", "showcase.mode.video",
            "showcase.search.actress", "showcase.search.video",
            "showcase.actress.add", "showcase.actress.addPlaceholder",
            "showcase.actress.addSuccess", "showcase.actress.addDuplicate",
            "showcase.actress.addNotFound", "showcase.actress.addTimeout",
            "showcase.actress.remove", "showcase.actress.removeSuccess",
            "showcase.actress.empty", "showcase.actress.emptyHint",
            "showcase.actress.search_films",
            "showcase.sort.actress.video_count", "showcase.sort.actress.name",
            "showcase.sort.actress.added_at", "showcase.sort.actress.age",
            "showcase.sort.actress.height", "showcase.sort.actress.cup",
            "showcase.unit.videos_count", "showcase.unit.films",
        ]
        for locale_file in ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]:
            data = self._locale(locale_file)
            for key in keys:
                val = self._get_nested(data, key)
                assert val is not None, f"{locale_file} missing: {key!r}"
        # remove_modal keys (zh_TW only)
        zh_tw = self._locale("zh_TW.json")
        for key in ["showcase.actress.remove_modal.title", "showcase.actress.remove_modal.body",
                    "showcase.actress.remove_modal.cancel", "showcase.actress.remove_modal.confirm"]:
            val = self._get_nested(zh_tw, key)
            assert val is not None, f"zh_TW.json missing: {key!r}"
        # orphan key removed
        assert self._get_nested(zh_tw, "showcase.actress.removeConfirm") is None, \
            "zh_TW.json should not contain: 'showcase.actress.removeConfirm'"


class TestSettingsResetModalI18n:
    """T3.4 (CD-52-11): resetConfig fluent-modal i18n key guard (method folded)"""

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

    def test_reset_modal_keys_in_zh_tw(self):
        """T3.4: reset_modal.* 3 keys 在 zh_TW.json 存在"""
        data = self._locale("zh_TW.json")
        for key in ["settings.reset_modal.title", "settings.reset_modal.body", "settings.reset_modal.confirm"]:
            val = self._get_nested(data, key)
            assert val is not None, f"zh_TW.json missing: {key!r}"


class TestShowcaseLightboxSentinel:
    """Phase 44b-T4: Lightbox -1 sentinel nav guards (method folded)"""

    CORE_JS = SHOWCASE_LIGHTBOX_JS
    SHOWCASE_HTML = Path(__file__).parents[2] / 'web' / 'templates' / 'showcase.html'

    def _js(self):
        return self.CORE_JS.read_text(encoding='utf-8')

    def _html(self):
        return self.SHOWCASE_HTML.read_text(encoding='utf-8')

    def test_showcase_lightbox_js_contains(self):
        """state-lightbox.js 含 sentinel nav 所有必要方法與邏輯"""
        js = self._js()
        for expected in ["hasVisiblePrev", "hasVisibleNext", "openHeroCardLightbox"]:
            assert expected in js, f"state-lightbox.js missing: {expected!r}"
        # openHeroCardLightbox block checks
        idx = js.find("openHeroCardLightbox")
        block = js[idx:idx + 2000]
        assert "lightboxIndex = -1" in block, \
            "state-lightbox.js openHeroCardLightbox missing: 'lightboxIndex = -1'"
        assert "this.currentLightboxActress" in block, \
            "state-lightbox.js openHeroCardLightbox missing: 'this.currentLightboxActress'"
        # prevLightboxVideo sentinel guard
        prev_idx = js.find("prevLightboxVideo()")
        assert prev_idx != -1, "state-lightbox.js missing: 'prevLightboxVideo()'"
        prev_block = js[prev_idx:prev_idx + 1500]
        assert "lightboxIndex === -1" in prev_block, \
            "state-lightbox.js prevLightboxVideo missing: 'lightboxIndex === -1'"
        assert "is_favorite" in prev_block, \
            "state-lightbox.js prevLightboxVideo missing: 'is_favorite'"
        # nextLightboxVideo -1 transition
        next_idx = js.find("nextLightboxVideo()")
        assert next_idx != -1, "state-lightbox.js missing: 'nextLightboxVideo()'"
        next_block = js[next_idx:next_idx + 1500]
        assert "lightboxIndex === -1" in next_block, \
            "state-lightbox.js nextLightboxVideo missing: 'lightboxIndex === -1'"
        assert "_setLightboxIndex" in next_block, \
            "state-lightbox.js nextLightboxVideo missing: '_setLightboxIndex'"
        # handleKeydown uses showFavoriteActresses
        hkd_idx = js.find("// 5. Lightbox")
        assert hkd_idx != -1, "state-lightbox.js handleKeydown section anchor not found"
        assert "showFavoriteActresses" in js[hkd_idx:hkd_idx + 1000], \
            "state-lightbox.js handleKeydown missing: 'showFavoriteActresses'"

    def test_showcase_html_contains(self):
        """showcase.html removeActress button gated by showFavoriteActresses"""
        html = self._html()
        idx = html.find("openRemoveActressModal()")
        assert idx != -1, "showcase.html missing: 'openRemoveActressModal()'"
        surrounding = html[max(0, idx - 300):idx + 100]
        assert "showFavoriteActresses" in surrounding, \
            "showcase.html removeActress button missing: 'showFavoriteActresses' guard"


class TestShowcaseHeroCard:
    """Phase 44b-T6: Showcase Hero Card guards (method folded)"""

    SHOWCASE_HTML = Path(__file__).parents[2] / 'web' / 'templates' / 'showcase.html'

    def _html(self):
        return self.SHOWCASE_HTML.read_text(encoding='utf-8')

    def test_showcase_html_contains(self):
        """showcase.html Hero Card 含必要結構"""
        html = self._html()
        for expected in [
            "hero-card",
            "t('common.no_image')",
            "searchFromMetadata(actress.trim(), 'actress')",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        assert "<span>No Image</span>" not in html, \
            "showcase.html should not contain: '<span>No Image</span>'"

    def test_animations_js_contains(self):
        """showcase animations.js 含 playHeroCardAppear"""
        anim_js = (Path(__file__).parents[2] / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'animations.js').read_text(encoding='utf-8')
        assert "playHeroCardAppear" in anim_js, \
            "showcase/animations.js missing: 'playHeroCardAppear'"


class TestShowcaseAliasGuard:
    """T5 (45-actress-alias): Frontend Guard — alias injection guard (method folded)"""

    def _js(self):
        return (
            SHOWCASE_BASE_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")
        )

    def test_alias_js_contains(self):
        """showcase JS 含 _nameToGroup 宣告 + API + 使用"""
        js = self._js()
        for expected in [
            "var _nameToGroup = {}",
            "/api/actress-aliases",
            "_nameToGroup[a.name]",
            "_nameToGroup[term]",
        ]:
            assert expected in js, f"showcase JS missing: {expected!r}"
        # _checkPreciseActressMatch function body must use _nameToGroup
        func_start = js.find("async _checkPreciseActressMatch")
        func_end = js.find("},", func_start)
        func_body = js[func_start:func_end]
        assert "_nameToGroup" in func_body, \
            "showcase JS _checkPreciseActressMatch missing: '_nameToGroup'"



# ---------------------------------------------------------------------------
# T6: Scanner Alias UI v2 — 舊 token 移除 + 新 token 存在守衛
# ---------------------------------------------------------------------------
SCANNER_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "scanner.html"
ZH_TW_JSON = Path(__file__).parent.parent.parent / "locales" / "zh_TW.json"


class TestScannerAliasV2Guard:
    """T6/T8: scanner alias V2 guard（method folded）"""

    def _js(self):
        return SCANNER_ALIAS_JS.read_text(encoding="utf-8")

    def _html(self):
        return SCANNER_HTML.read_text(encoding="utf-8")

    def _zh_tw(self):
        return json.loads(ZH_TW_JSON.read_text(encoding="utf-8"))

    def test_scanner_alias_js_contains(self):
        """scanner alias JS 含新 state；不含舊欄位名"""
        js = self._js()
        for expected in ["aliasRecords", "aliasInput", "cancelAddAlias"]:
            assert expected in js, f"scanner alias JS missing: {expected!r}"
        for forbidden in ["alias.old_name", "alias.new_name", "api/gallery/actress-aliases"]:
            assert forbidden not in js, f"scanner alias JS should not contain: {forbidden!r}"

    def test_scanner_html_contains(self):
        """scanner.html 含 x-model 綁定；不含舊 binding"""
        html = self._html()
        x_model = 'x-model="addingAlias[group.primary_name]"'
        assert x_model in html, f"scanner.html missing: {x_model!r}"
        btn_type = 'type="button" class="btn-cancel"'
        assert btn_type in html, f"scanner.html missing: {btn_type!r}"
        for forbidden in [
            "aliasForm.oldName",
            ':value="addingAlias[group.primary_name]"',
            "btn-confirm",
        ]:
            assert forbidden not in html, f"scanner.html should not contain: {forbidden!r}"

    def test_zh_tw_contains(self):
        """zh_TW.json 含 scanner.alias i18n keys"""
        data = self._zh_tw()
        alias = data.get("scanner", {}).get("alias", {})
        for expected in ["search_placeholder", "filter_hint"]:
            assert expected in alias, f"zh_TW.json scanner.alias missing: {expected!r}"

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


class TestFluentCustomEaseRegistered:
    """Phase 50.2.0: motion-adapter.js 同步註冊 fluent CustomEase 三角色"""

    def _js(self):
        return Path("web/static/js/components/motion-adapter.js").read_text(encoding="utf-8")

    def test_fluent_standard_registered(self):
        js = self._js()
        assert "CustomEase.create('fluent'" in js, \
            "motion-adapter.js 缺 CustomEase.create('fluent', ...) — charter §5 standard"

    def test_fluent_decel_registered(self):
        js = self._js()
        assert "CustomEase.create('fluent-decel'" in js, \
            "motion-adapter.js 缺 CustomEase.create('fluent-decel', ...) — charter §5 decel"

    def test_fluent_accel_registered(self):
        js = self._js()
        assert "CustomEase.create('fluent-accel'" in js, \
            "motion-adapter.js 缺 CustomEase.create('fluent-accel', ...) — charter §5 accel"

    def test_register_is_guarded(self):
        """guard 寫法避免 CustomEase plugin 載入失敗時 IIFE 炸掉"""
        js = self._js()
        assert "typeof CustomEase !== 'undefined'" in js, \
            "fluent ease 註冊應用 typeof guard 包住"

    def test_register_is_synchronous(self):
        """同步註冊（不放 DOMContentLoaded handler，CD-2）"""
        js = self._js()
        # 註冊區段位於 IIFE 內、var motion 之前；不應出現 DOMContentLoaded wrapper 包裹 CustomEase.create
        register_idx = js.find("CustomEase.create('fluent'")
        dom_ready_idx = js.find("DOMContentLoaded")
        # 若有 DOMContentLoaded（reduced-motion handler 等），其位置必須在 register 之後
        if dom_ready_idx != -1:
            assert register_idx < dom_ready_idx, \
                "fluent CustomEase 註冊不應被 DOMContentLoaded handler 包住"


class TestShowcaseCssTransitionTokens:
    """Phase 50.2.10 + 51.T1.2: showcase.css transition 硬編碼 → fluent token（影片 + 女優模式全段）"""

    def _css(self):
        return Path("web/static/css/pages/showcase.css").read_text(encoding="utf-8")

    def test_actress_picker_transition_tokenized(self):
        """Phase 51 T1.2: 女優 picker 三處 transition 已 token 化（fluent-duration-fast + fluent-ease-standard）"""
        css = self._css()
        # picker-check-icon (opacity), picker-refresh-btn (all), picker-open cover-actions (opacity)
        assert "transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard)" in css, \
            "picker-check-icon / cover-actions opacity transition 應使用 fluent token"
        assert "transition: all var(--fluent-duration-fast) var(--fluent-ease-standard)" in css, \
            "picker-refresh-btn all transition 應使用 fluent token"


class TestMotionDurationConstants:
    """Phase 50.2.9: motion.DURATION 三角色常數 + 業務 caller 套用 (CD-1)"""

    def _adapter(self):
        return Path("web/static/js/components/motion-adapter.js").read_text(encoding="utf-8")

    def _animations(self):
        return Path("web/static/js/pages/showcase/animations.js").read_text(encoding="utf-8")

    def test_duration_constants_exposed(self):
        """motion.DURATION 三角色常數透過 IIFE 暴露於 window.OpenAver.motion"""
        js = self._adapter()
        assert "DURATION:" in js, "motion-adapter.js 缺 DURATION: 物件定義"
        # 三角色值對齊 charter §5 (167ms / 333ms / 500ms)
        assert "fast:" in js and "0.167" in js, "DURATION.fast 應為 0.167 (charter §5 167ms)"
        assert "medium:" in js and "0.333" in js, "DURATION.medium 應為 0.333 (charter §5 333ms)"
        assert "emphasis:" in js and "0.5" in js, "DURATION.emphasis 應為 0.5 (charter §5 500ms)"

    def test_adapter_callers_use_duration_constants(self):
        """motion-adapter.js 內部 caller 使用 motion.DURATION.* 取代 hardcoded fallback"""
        js = self._adapter()
        assert js.count("motion.DURATION.") >= 4, \
            "motion-adapter.js 至少 4 個 caller (playEnter/Leave/FadeTo/Modal/Stagger) 應走 motion.DURATION.*"

    def test_animations_callers_use_duration_constants(self):
        """showcase/animations.js 業務 caller 使用 OpenAver.motion.DURATION.*"""
        js = self._animations()
        assert js.count("OpenAver.motion.DURATION.") >= 8, \
            "animations.js 至少 8 處 hardcoded duration 應改走 OpenAver.motion.DURATION.*"

    def test_white_list_durations_preserved(self):
        """白名單 hardcoded duration 不被誤改：
        - showcaseSettle 招牌曲線 (charter §5 white-list)
        - HeroCardAppear (女優專屬，plan D10)
        - SourcePulse 0.1 (低於 DURATION.fast 不適合 bucket)"""
        js = self._animations()
        # showcaseSettle: var dur = params.duration || 0.8;
        assert "params.duration || 0.8" in js, "playSettle (showcaseSettle) duration 0.8 不應被改"
        # HeroCardAppear: duration: 0.3
        hero_idx = js.find("playHeroCardAppear")
        hero_scope = js[hero_idx : hero_idx + 800]
        assert "duration: 0.3" in hero_scope, "playHeroCardAppear duration 0.3 (女優白名單) 不應被改"
        # SourcePulse default 0.1 stays
        pulse_idx = js.find("playSourcePulse")
        pulse_scope = js[pulse_idx : pulse_idx + 800]
        assert "options.duration : 0.1" in pulse_scope, \
            "playSourcePulse default 0.1 (低於 fast bucket) 不應被改"


class TestMotionAdapterFluentDefaults:
    """Phase 50.2.1: motion-adapter.js 5 default ease → fluent 角色"""

    def _js(self):
        return Path("web/static/js/components/motion-adapter.js").read_text(encoding="utf-8")

    def _scoped(self, fn_name):
        """擷取從 fn_name 開頭到下一個 /** 區段間的 JS（function body 範圍）"""
        js = self._js()
        idx = js.find(fn_name + ":")
        assert idx > 0, f"找不到 {fn_name}"
        next_doc = js.find("/**", idx + 1)
        return js[idx : next_doc if next_doc > 0 else idx + 800]

    def test_play_enter_default_fluent_decel(self):
        scope = self._scoped("playEnter")
        assert "opts.ease || 'fluent-decel'" in scope, \
            "playEnter default ease 應為 'fluent-decel'（charter §5 進場）"

    def test_play_leave_default_fluent_accel(self):
        scope = self._scoped("playLeave")
        assert "opts.ease || 'fluent-accel'" in scope, \
            "playLeave default ease 應為 'fluent-accel'（charter §5 離場）"

    def test_play_stagger_default_fluent_decel(self):
        scope = self._scoped("playStagger")
        assert "opts.ease || 'fluent-decel'" in scope, \
            "playStagger default ease 應為 'fluent-decel'（charter §5 進場 stagger）"

    def test_play_fade_to_default_fluent(self):
        scope = self._scoped("playFadeTo")
        assert "opts.ease || 'fluent'" in scope and "opts.ease || 'fluent-decel'" not in scope, \
            "playFadeTo default ease 應為 'fluent'（charter §5 standard）"

    def test_play_modal_default_fluent_decel(self):
        scope = self._scoped("playModal")
        assert "opts.ease || 'fluent-decel'" in scope, \
            "playModal default ease 應為 'fluent-decel'（charter §5 modal 彈出）"

    def test_no_legacy_power_ease_defaults(self):
        """confirm 沒有殘留的 power* default ease（在 motion-adapter.js 中）"""
        js = self._js()
        # 註解 / 文件字串若引用 power* 不算違規；但 default fallback 不應有
        assert "opts.ease || 'power" not in js, \
            "motion-adapter.js 殘留 power* default ease — 未完成 fluent 角色化"


class TestShowcaseAnimationsFluent:
    """Phase 50.2.2-2.8: showcase/animations.js 各動畫 ease → charter §5 fluent 角色（method folded）"""

    def _js(self):
        return Path("web/static/js/pages/showcase/animations.js").read_text(encoding="utf-8")

    GHOST_FLY_JS = Path("web/static/js/shared/ghost-fly.js")

    def test_animations_js_contains(self):
        """animations.js ease 角色符合 charter §5 + 招牌曲線保留"""
        js = self._js()
        for expected in [
            # T2.2: playEntry
            "params.easing || 'fluent-decel'",
            # T2.3: playFlipReorder
            "params.ease || 'fluent'",
            # T2.5: playModeCrossfade
            "ease: 'fluent-accel'",
            "ease: 'fluent-decel'",
            # T2.7: playLightboxSwitch + playSampleGallerySwitch
            "ease: 'fluent'",
            # T2.8: playContainerFadeIn + playSourcePulse
            "options.ease || 'fluent-decel'",
            # white-list
            'CustomEase.create("showcaseSettle"',
            # T4.2 delegate
            "GhostFly.playLightboxOpen",
            "showcaseLightboxOpen",
            "typeof window.GhostFly?.playLightboxOpen === 'function'",
        ]:
            assert expected in js, f"showcase/animations.js missing: {expected!r}"
        # T2.4: playFlipFilter onEnter × 2
        assert js.count("ease: 'fluent-decel'") >= 2, \
            "showcase/animations.js missing: 'ease: 'fluent-decel'' (×2 for playFlipFilter onEnter)"
        # not-in: no power2.out in playLightboxSwitch/playSampleGallerySwitch
        # (checking globally is OK since power2.out should only be in ghost-fly for white-list)

    def test_ghost_fly_js_contains(self):
        """ghost-fly.js playLightboxOpen 三段 power2.out + clearProps (×4) + white-list 標注"""
        js = self.GHOST_FLY_JS.read_text(encoding="utf-8")
        idx = js.find("playLightboxOpen:")
        assert idx > 0, "ghost-fly.js missing: 'playLightboxOpen:'"
        scope = js[idx:idx+4500]
        assert scope.count("ease: 'power2.out'") >= 3, \
            "ghost-fly.js playLightboxOpen missing: 'ease: 'power2.out'' (×3 for backdrop/content/cover)"
        assert scope.count("clearProps: 'transform,opacity'") >= 4, \
            "ghost-fly.js playLightboxOpen missing: clearProps ×4 (onComplete + onInterrupt)"
        assert "ease: 'fluent-decel'" not in scope, \
            "ghost-fly.js playLightboxOpen should not contain: 'ease: 'fluent-decel''"
        assert ("white-list" in scope or "ghost-fly" in scope), \
            "ghost-fly.js playLightboxOpen missing: white-list or ghost-fly comment"

    def test_search_animations_js_contains(self):
        """search/animations.js playLightboxOpen delegate GhostFly（Phase 51 T4.3）"""
        search_js = Path("web/static/js/pages/search/animations.js").read_text(encoding="utf-8")
        idx = search_js.find("playLightboxOpen: function")
        assert idx > 0, "search/animations.js missing: 'playLightboxOpen: function'"
        scope = search_js[idx:idx+800]
        assert "GhostFly.playLightboxOpen" in scope, \
            "search/animations.js missing: 'GhostFly.playLightboxOpen'"
        assert "showcaseLightboxOpen" not in scope, \
            "search/animations.js should not contain: 'showcaseLightboxOpen'"
        assert "typeof window.GhostFly?.playLightboxOpen === 'function'" in scope, \
            "search/animations.js missing: typeof guard for playLightboxOpen"

class TestGhostFlyGuards:
    """T8: Ghost Fly architecture guards (method folded)"""

    def test_ghost_fly_js_and_html_contains(self):
        """ghost-fly.js exists + loaded in base.html + skipCover support + delegates"""
        assert Path("web/static/js/shared/ghost-fly.js").exists(), \
            "web/static/js/shared/ghost-fly.js missing"
        html = Path("web/templates/base.html").read_text(encoding="utf-8")
        assert "ghost-fly.js" in html, "base.html missing: 'ghost-fly.js'"
        ghost_fly_js = Path("web/static/js/shared/ghost-fly.js").read_text(encoding="utf-8")
        assert "skipCover" in ghost_fly_js, "ghost-fly.js missing: 'skipCover'"
        for path in [
            "web/static/js/pages/showcase/animations.js",
            "web/static/js/pages/search/animations.js",
        ]:
            js = Path(path).read_text(encoding="utf-8")
            assert "GhostFly.playLightboxOpen" in js, f"{path} missing: 'GhostFly.playLightboxOpen'"
        # search/animations.js fallback
        search_js = Path("web/static/js/pages/search/animations.js").read_text(encoding="utf-8")
        lines = search_js.split('\n')
        ghost_fly_refs = [i for i, line in enumerate(lines) if 'window.GhostFly' in line]
        assert len(ghost_fly_refs) >= 3, \
            "search/animations.js missing: at least 3 window.GhostFly references"

    def test_gsap_animating_before_lightbox_open(self):
        """state-lightbox.js gsap-animating before lightboxOpen = true (ordering)"""
        content = SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        for fn_name in ("openLightbox(", "openHeroCardLightbox("):
            idx_fn = content.find(fn_name)
            assert idx_fn > 0, f"state-lightbox.js missing: {fn_name!r}"
            fn_scope = content[idx_fn:idx_fn + 4000]
            idx_animating = fn_scope.find("gsap-animating")
            idx_open = fn_scope.find("this.lightboxOpen = true")
            assert idx_animating > 0, f"state-lightbox.js {fn_name} missing: 'gsap-animating'"
            assert idx_open > 0, f"state-lightbox.js {fn_name} missing: 'lightboxOpen = true'"
            assert idx_animating < idx_open, \
                f"state-lightbox.js {fn_name}: gsap-animating must precede lightboxOpen = true"


class TestTutorialExpandGuard:
    """T10: 新手教學 7 步守衛 (method folded)

    v0.9 (spec-59) 把 tutorial 從 Search-first 翻轉為 Scanner-first：
    步驟 IDs 改為 folder → generate → scanner → showcase → search → settings → help。
    """

    def test_tutorial_js_and_i18n(self):
        """tutorial.js 7 步 (Scanner-first) + 四語系 i18n keys"""
        js = Path("web/static/js/components/tutorial.js").read_text(encoding="utf-8")
        for step_id in ['folder', 'generate', 'scanner', 'showcase', 'search', 'settings', 'help']:
            assert f"id: '{step_id}'" in js, f"tutorial.js missing: \"id: '{step_id}'\""
        for locale in ["zh_TW", "en", "ja", "zh_CN"]:
            data = json.loads(Path(f"locales/{locale}.json").read_text(encoding="utf-8"))
            tutorial = data.get("tutorial", {})
            for i in range(1, 8):
                for key in [f"step{i}_title", f"step{i}_content"]:
                    assert key in tutorial and tutorial[key], \
                        f"{locale}.json missing or empty: tutorial.{key!r}"


class TestMissingEnrichConfirmGuard:
    """TASK-13 (0.7.6 hotfix): 守衛 Scanner 一鍵補完 > 500 confirm dialog 的實作"""

    def _js(self):
        return SCANNER_BATCH_JS.read_text(encoding="utf-8")

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

    def test_all_locales_have_missing_enrich_confirm_keys(self):
        """四語系都有 6 個 missing_enrich_confirm_* keys（純文字）"""
        required = [
            "missing_enrich_confirm_title",
            "missing_enrich_confirm_body_prefix",
            "missing_enrich_confirm_body_middle",
            "missing_enrich_confirm_body_suffix",
            "missing_enrich_confirm_cancel",
            "missing_enrich_confirm_confirm",
        ]
        for locale in ["zh_TW", "zh_CN", "ja", "en"]:
            data = json.loads((LOCALES_ROOT / f"{locale}.json").read_text(encoding="utf-8"))
            stats = data.get("scanner", {}).get("stats", {})
            for key in required:
                assert key in stats and stats[key], \
                    f"{locale}.json missing or empty: scanner.stats.{key!r}"
                value = stats[key]
                assert "<" not in value and ">" not in value, \
                    f"{locale}.json scanner.stats.{key!r} should not contain HTML tags: {value!r}"


class TestIMEGuard:
    """spec-48a §a4: IME composition guard (method folded)"""

    def test_search_html_ime_guard(self):
        """search.html searchQuery input 含 @keydown.enter + isComposing + preventDefault"""
        content = (Path(__file__).parent.parent.parent / "web" / "templates" / "search.html").read_text(encoding="utf-8")
        m = re.search(r'<input\b[^>]*\bid="searchQuery"[^>]*>', content, re.DOTALL)
        assert m, "search.html missing: id=\"searchQuery\" input tag"
        tag = m.group(0)
        handler_m = re.search(r'@keydown\.enter(?:\.prevent)?="([^"]*)"', tag)
        assert handler_m, "search.html searchQuery input missing: @keydown.enter handler"
        expr = handler_m.group(1)
        assert "isComposing" in expr, \
            f"search.html searchQuery @keydown.enter missing: 'isComposing' (handler: {expr!r})"
        assert "preventDefault()" in expr, \
            f"search.html searchQuery @keydown.enter missing: 'preventDefault()' (handler: {expr!r})"


class TestLongPathWarning:
    """spec-48a §a5: scanner/state-scan.js long_paths warning (method folded)"""

    def test_scanner_js_long_path_warning(self):
        """scanner/state-scan.js long_paths 警告 toast 含 warn + 6000 + 260 + debug.log"""
        js = SCANNER_SCAN_JS.read_text(encoding="utf-8")
        assert "long_paths" in js, "scanner/state-scan.js missing: 'long_paths'"
        assert "showToast" in js, "scanner/state-scan.js missing: 'showToast'"
        idx = js.find("long_paths")
        window = js[idx:idx + 500]
        assert "'warn'" in window or '"warn"' in window, \
            "scanner/state-scan.js long_paths toast missing: 'warn' type"
        assert "6000" in window, "scanner/state-scan.js long_paths toast missing: '6000'"
        assert "260" in window, "scanner/state-scan.js long_paths toast missing: '260'"
        assert "debug.log" in window, "scanner/state-scan.js long_paths toast missing: 'debug.log'"


class TestSearchFileJsSubtitleHelper:
    """48a T2 a2 — 前端 extractChineseTitle 同步套用 stripSubtitleMarkers helper（對齊 Python 端）"""

    def _js(self):
        return SEARCH_FILE_JS.read_text(encoding="utf-8")

    def test_file_js_contains(self):
        """file.js 包含 stripSubtitleMarkers helper、常數定義，且舊 regex 已移除"""
        js = self._js()
        for expected in [
            "function stripSubtitleMarkers(",
            "_SUBTITLE_BRACKETS",
            "_SUBTITLE_TEXT_MARKERS",
        ]:
            assert expected in js, f"file.js missing: {expected!r}"
        assert "/^中文字幕\\s*/" not in js, \
            "file.js should not contain: '/^中文字幕\\s*/' (殘缺舊 regex，應改用 stripSubtitleMarkers())"

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


class TestFetchSamplesButton:
    """spec-48b §b3 b6 — 守衛 showcase.html fetch-samples-btn（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _js(self):
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        )

    def _fetch_samples_btn_tag(self, html: str):
        m = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html, re.DOTALL,
        )
        return m.group(0) if m else None

    def test_html_contains(self):
        """showcase.html fetch-samples-btn 含必要 Alpine 綁定 + loading state + icon"""
        html = self._html()
        tag = self._fetch_samples_btn_tag(html)
        assert tag is not None, "showcase.html missing: class='fetch-samples-btn' button"
        for attr in [
            "x-show=", "sample_images", "@click=", "fetchSamples",
            ":disabled=", "_fetchSamplesFailed",
        ]:
            assert attr in tag, f"fetch-samples-btn tag missing: {attr!r}"
        # boolean coercion in :disabled
        m = re.search(r':disabled=["\'"]([^"\']+)["\'""]', tag)
        assert m, "fetch-samples-btn missing :disabled binding"
        disabled_expr = m.group(1)
        has_coercion = (
            disabled_expr.startswith("!!")
            or "=== true" in disabled_expr
        )
        assert has_coercion, \
            f"fetch-samples-btn :disabled missing boolean coercion: {disabled_expr!r}"
        # x-text and icon in button region
        close_tag_pos = html.find('</button>', tag.__class__ is str and html.find(tag))
        m2 = re.search(
            r'<button\b[^>]*class="[^"]*fetch-samples-btn[^"]*"[^>]*>',
            html, re.DOTALL,
        )
        close_tag_pos = html.find('</button>', m2.end())
        btn_region = html[m2.start():close_tag_pos + len('</button>')]
        for expected in [
            "x-text=", "showcase.samples.fetch_btn",
            "bi bi-cloud-download",
            "_fetchSamplesLoading", "showcase.samples.fetching",
        ]:
            assert expected in btn_region or expected in html, \
                f"showcase.html missing: {expected!r}"
        for forbidden in ["☁"]:
            assert forbidden not in btn_region, f"fetch-samples-btn should not contain: {forbidden!r}"

    def test_core_js_contains(self):
        """core.js 含 fetchSamples method + state init + closeLightbox reset"""
        js = self._js()
        for expected in ["_fetchSamplesLoading:", "_fetchSamplesFailed:"]:
            assert expected in js or expected.replace(":", " :") in js, \
                f"core.js missing: {expected!r}"
        assert "fetchSamples" in js, "core.js missing: 'fetchSamples'"
        close_lb_idx = js.find('closeLightbox() {')
        assert close_lb_idx >= 0, "core.js missing: closeLightbox() method"
        close_lb_body = js[close_lb_idx:close_lb_idx + 2000]
        assert '_fetchSamplesFailed = {}' in close_lb_body, \
            "closeLightbox() missing: '_fetchSamplesFailed = {}'"

    def test_locale_files_have_samples_keys(self):
        """4 語系 showcase.samples 含 5 必要 key + fetch_btn 無 ☁ emoji"""
        required_keys = {"fetch_btn", "fetching", "success", "fetch_failed", "multi_video_error"}
        for locale in ["zh_TW", "zh_CN", "en", "ja"]:
            locale_path = LOCALES_ROOT / f"{locale}.json"
            assert locale_path.exists(), f"locale file missing: {locale_path}"
            data = json.loads(locale_path.read_text(encoding="utf-8"))
            samples = data.get("showcase", {}).get("samples", {})
            missing = required_keys - set(samples.keys())
            assert not missing, f"locales/{locale}.json showcase.samples missing: {sorted(missing)}"
            fetch_btn_val = samples.get("fetch_btn", "")
            assert "☁" not in fetch_btn_val, \
                f"locales/{locale}.json showcase.samples.fetch_btn should not contain ☁: {fetch_btn_val!r}"

class TestActressCoreMetadataVideoCount:
    """T2: _actressCoreMetadata() 加 video_count 前置 + i18n showcase.unit.films 改值"""

    def _js(self):
        # _actressCoreMetadata → state-actress.js
        return SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")

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
        # toggleActressMode / searchActressFilms → state-actress.js
        # switchMode → state-videos.js
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")
        )

    def _anim_js(self):
        return SHOWCASE_ANIMATIONS_JS.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method（methodName(...) { ... }）函式主體，大括號平衡（容忍 async 前綴）。"""
        pattern = re.compile(
            r'(?:^|\n)\s*(?:async\s+)?' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
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
        """switchMode 內 playModeCrossfade 呼叫不含 onOldFadeComplete（保持影片模式內切換行為不變）。
        searchActressFilms 自 T7 起為 async 並使用 onOldFadeComplete 觸發 ghost fly fade-out，
        故僅驗證 switchMode 路徑不退化。"""
        js = self._core_js()
        search_body = self._extract_method_body(js, 'searchActressFilms')
        switch_body = self._extract_method_body(js, 'switchMode')
        # 兩處都應呼叫 playModeCrossfade
        assert 'playModeCrossfade' in search_body, \
            "searchActressFilms 應仍呼叫 playModeCrossfade"
        assert 'playModeCrossfade' in switch_body, \
            "switchMode 應仍呼叫 playModeCrossfade"
        # switchMode 不該帶 onOldFadeComplete（保持原 2/3-arg 行為）
        assert 'onOldFadeComplete' not in switch_body, \
            "switchMode 內 playModeCrossfade 呼叫不應帶 onOldFadeComplete（保持影片模式內切換行為不變）"

    def test_toggle_actress_mode_handles_animations_unavailable(self):
        """Codex P1: animations.js 不可用時 toggleActressMode 必須有 fallback path（不能讓 callback 永不觸發）"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        # callback body 應抽成 named function（給 onOldFadeComplete 用、也給 fallback path 用）
        assert re.search(
            r'(?:function\s+\w*FadeIn\w*|var\s+\w*FadeIn\w*\s*=\s*function|\w*FadeIn\w*\s*=\s*function)',
            body,
        ), "toggleActressMode 應將 callback body 抽成 named function（如 flipAndFadeIn）以便 fallback 重用"
        # 必須顯式檢查 playModeCrossfade 是否存在（不能單靠 optional chaining 短路）
        assert re.search(
            r'(?:typeof\s+\w+\s*===\s*[\'"]function[\'"]|window\.ShowcaseAnimations\s*&&\s*window\.ShowcaseAnimations\.playModeCrossfade)',
            body,
        ), "toggleActressMode 應顯式檢查 playModeCrossfade 是否可用（不能單靠 optional chaining）"
        # 抽出來的 named function 應在函數體內被引用 ≥ 2 次（一次給 onOldFadeComplete、一次 fallback 直接呼叫）
        # 找出第一個 *FadeIn* 識別字
        m = re.search(r'\b(\w*[Ff]adeIn\w*)\b', body)
        assert m is not None, "toggleActressMode 找不到 FadeIn 命名函數"
        fname = m.group(1)
        count = len(re.findall(r'\b' + re.escape(fname) + r'\b', body))
        assert count >= 3, (
            f"toggleActressMode 內 {fname} 應出現 ≥ 3 次"
            f"（宣告 1 + onOldFadeComplete 引用 1 + fallback 同步呼叫 1），實際 {count}"
        )

    def test_toggle_actress_mode_reduced_motion_guard_on_fade_in(self):
        """Codex P2: toggleActressMode 內 newEl fade-in 必須有 reduced-motion 防護。

        49a-T4 起：原本的 inline `gsap.fromTo` 已重構為呼叫
        `window.ShowcaseAnimations.playContainerFadeIn`，該 helper 內部的
        `shouldSkip()` 已涵蓋 reduced-motion。本 test 接受兩種寫法擇一：
        (a) inline guard（舊架構）— 函數體內含 `prefersReducedMotion` 檢查
        (b) helper 委派（新架構）— 函數體內呼叫 `playContainerFadeIn`
        """
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        has_inline_guard = 'prefersReducedMotion' in body
        has_helper_delegation = 'playContainerFadeIn' in body
        assert has_inline_guard or has_helper_delegation, (
            "toggleActressMode newEl fade-in 應走 inline prefersReducedMotion guard，"
            "或委派 ShowcaseAnimations.playContainerFadeIn helper（後者 shouldSkip 已涵蓋）"
        )


class TestAliasLiveQueryGuard:
    """49a-T3: Actress Lightbox 別名即時查 guard

    驗證：
    - _fetchLiveAliases 方法存在
    - 200 分支以 Object.assign 覆蓋 aliases（CD-4 + §8.4 reactivity）
    - 404 / error / timeout 保留 snapshot（catch + 不覆蓋 fallback）
    """

    def _js(self):
        # _fetchLiveAliases / openActressLightbox / prevActressLightbox / nextActressLightbox → state-actress.js
        # openHeroCardLightbox → state-lightbox.js
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        )

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method 函式主體，大括號平衡（容忍 async 前綴）。"""
        pattern = re.compile(
            r'(?:^|\n)\s*(?:async\s+)?' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
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

    def test_fetch_live_aliases_method_exists(self):
        """core.js 含 async _fetchLiveAliases 方法定義"""
        js = self._js()
        assert re.search(r'async\s+_fetchLiveAliases\s*\([^)]*\)\s*\{', js), \
            "showcase/core.js 缺少 async _fetchLiveAliases(...) 方法定義"
        # 必須呼叫 /api/actress-aliases/ 端點
        body = self._extract_method_body(js, '_fetchLiveAliases')
        assert "/api/actress-aliases/" in body, \
            "_fetchLiveAliases 函數體缺少 /api/actress-aliases/ 端點呼叫"

    def test_200_branch_uses_object_assign(self):
        """200 分支用 Object.assign 覆蓋 currentLightboxActress.aliases（§8.4 Alpine reactivity）"""
        js = self._js()
        body = self._extract_method_body(js, '_fetchLiveAliases')
        # 必須有 200 status 分支
        assert re.search(r'(?:resp|response)\.status\s*===\s*200', body), \
            "_fetchLiveAliases 缺少 resp.status === 200 分支"
        # 必須用 Object.assign 建立新物件以觸發 Alpine deep watch（§8.4）
        assert re.search(r'Object\.assign\s*\(', body), \
            "_fetchLiveAliases 200 分支應用 Object.assign 建立新物件以觸發 Alpine reactivity（§8.4）"
        # 覆蓋的目標必須是 aliases
        assert re.search(r'aliases\s*:', body), \
            "_fetchLiveAliases Object.assign 應指定 aliases 屬性"

    def test_fallback_preserves_snapshot_on_error(self):
        """error / timeout / 404 分支保留 snapshot（catch 區塊不覆蓋 aliases）"""
        js = self._js()
        body = self._extract_method_body(js, '_fetchLiveAliases')
        # 必須有 try / catch 區塊（fallback contract）
        assert re.search(r'\btry\s*\{', body), \
            "_fetchLiveAliases 缺少 try 區塊（error fallback contract）"
        assert re.search(r'\bcatch\s*\(', body), \
            "_fetchLiveAliases 缺少 catch 區塊（error fallback contract）"
        # 200 分支應用 if 包裹（亦即 404/其他狀態落入 implicit fallback：不執行覆蓋）
        # 實作必須讓「非 200」 + 「catch」 不執行 Object.assign
        # 用結構驗證：Object.assign 必須出現在 if (resp.status === 200) { ... } 區塊內
        pattern = re.compile(
            r'if\s*\(\s*(?:resp|response)\.status\s*===\s*200\s*\)\s*\{[^}]*?Object\.assign',
            re.DOTALL,
        )
        assert pattern.search(body), \
            "_fetchLiveAliases Object.assign 應位於 if (resp.status === 200) {...} 區塊內，避免非 200 分支誤覆蓋 snapshot"

    def test_callsites_in_open_actress_and_hero(self):
        """openActressLightbox（兩分支）+ openHeroCardLightbox 皆 fire-and-forget 呼叫 _fetchLiveAliases"""
        js = self._js()
        actress_body = self._extract_method_body(js, 'openActressLightbox')
        # 至少 2 處（首次進入 + 切換女優）
        actress_calls = re.findall(r'_fetchLiveAliases\s*\(', actress_body)
        assert len(actress_calls) >= 2, \
            f"openActressLightbox 應至少 2 處呼叫 _fetchLiveAliases（首次進入 + 切換女優），目前 {len(actress_calls)} 處"

        hero_body = self._extract_method_body(js, 'openHeroCardLightbox')
        assert re.search(r'_fetchLiveAliases\s*\(', hero_body), \
            "openHeroCardLightbox 缺少 _fetchLiveAliases 呼叫"

    def test_prev_next_actress_lightbox_refetch_aliases(self):
        """Codex P2: prev/nextActressLightbox 在切換 index 後也須呼叫 _fetchLiveAliases，
        否則方向鍵切換時 SSOT 心智模型破功（看到 stale snapshot）。"""
        js = self._js()
        for method in ('prevActressLightbox', 'nextActressLightbox'):
            body = self._extract_method_body(js, method)
            assert re.search(r'_fetchLiveAliases\s*\(', body), (
                f"{method} 缺少 _fetchLiveAliases 呼叫（Codex P2 fix）— "
                "方向鍵切換時不重抓 alias，違反 T3 SSOT 設計"
            )


GHOST_FLY_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "ghost-fly.js"


class TestGhostFlyInFlightGuard:
    """49a-T7: 女優 → 影片跨模式 Ghost Fly 動畫並發保護 guard

    驗證：
    - state 初始化物件含 _ghostFlyInFlight: false（CD-13 並發 flag）
    - ghost-fly.js 新增 playActressToHeroCard 方法（CD-11）
    - searchActressFilms 為 async 並接受第二參數 fromEl
    - showcase.html 兩個 camera button（grid + lightbox）皆綁 :disabled="_ghostFlyInFlight"
    """

    def _js(self):
        # _ghostFlyInFlight / searchActressFilms → state-actress.js
        return SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")

    def _ghost_js(self):
        return GHOST_FLY_JS.read_text(encoding="utf-8")

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_ghost_fly_in_flight_state_present(self):
        """core.js Alpine state 含 _ghostFlyInFlight: false（CD-13 並發 flag）"""
        js = self._js()
        assert re.search(r'_ghostFlyInFlight\s*:\s*false', js), \
            "showcase/core.js 缺少 Alpine state 屬性 _ghostFlyInFlight: false"

    def test_play_actress_to_hero_card_method_exists(self):
        """ghost-fly.js 含 playActressToHeroCard 方法定義（CD-11）"""
        js = self._ghost_js()
        assert re.search(r'playActressToHeroCard\s*:\s*function', js), \
            "ghost-fly.js 缺少 playActressToHeroCard: function 方法定義"

    def test_search_actress_films_is_async_with_from_el(self):
        """searchActressFilms 為 async 且簽名含第二個參數 fromEl"""
        js = self._js()
        assert re.search(
            r'async\s+searchActressFilms\s*\(\s*actressName\s*,\s*fromEl\s*\)',
            js,
        ), "showcase/core.js searchActressFilms 應為 async 且簽名為 (actressName, fromEl)"

    def test_camera_buttons_disabled_binding(self):
        """showcase.html 兩個 camera button (grid L529 + lightbox L579) 皆綁 :disabled=\"_ghostFlyInFlight\""""
        html = self._html()
        # 計算 :disabled="_ghostFlyInFlight" 出現次數，應 ≥ 2
        matches = re.findall(r':disabled\s*=\s*"_ghostFlyInFlight"', html)
        assert len(matches) >= 2, \
            f"showcase.html 至少 2 個 camera button 應綁 :disabled=\"_ghostFlyInFlight\"（grid + lightbox），目前 {len(matches)} 處"

    def test_camera_buttons_pass_el_to_search(self):
        """showcase.html 兩個 camera button 呼叫 searchActressFilms 時皆傳入 $el 參數"""
        html = self._html()
        # grid camera: searchActressFilms(actress.name, $el)
        # lightbox camera: searchActressFilms(currentLightboxActress?.name, $el)
        assert "searchActressFilms(actress.name, $el)" in html, \
            "showcase.html grid camera button 缺少 searchActressFilms(actress.name, $el) 呼叫"
        assert "searchActressFilms(currentLightboxActress?.name, $el)" in html, \
            "showcase.html lightbox camera button 缺少 searchActressFilms(currentLightboxActress?.name, $el) 呼叫"

    def test_search_actress_films_explicit_ghost_fly_availability_check(self):
        """Codex P1: searchActressFilms 主流程前需 explicit check window.GhostFly?.playActressToHeroCard
        是 function。optional chaining 缺失時 silent no-op，flag 永久 true → camera button 永久 disabled。
        """
        js = self._js()
        body = self._extract_method_body(js, 'searchActressFilms')
        assert re.search(
            r"typeof\s+window\.GhostFly\??\.?playActressToHeroCard\s*!==\s*['\"]function['\"]",
            body,
        ), (
            "searchActressFilms 缺少 explicit GhostFly availability check（Codex P1 fix）— "
            "optional chaining 在缺失時 silent no-op，flag 卡死所有 camera button"
        )

    def _extract_method_body(self, js, name):
        """共用 brace-counting 提取方法體（避免依賴外部 helper class）"""
        m = re.search(r'(?:async\s+)?' + re.escape(name) + r'\s*\([^)]*\)\s*\{', js)
        if not m:
            return ''
        start = m.end() - 1
        depth = 0
        for i, ch in enumerate(js[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return js[start:i + 1]
        return ''


# ============================================================================
# 49a-T4: 底部 footer 整合（status bar 移除 + 三段式 footer + i18n 同步）
# ============================================================================

LOCALES_DIR = Path(__file__).parent.parent.parent / "locales"
LOCALE_FILES = ["zh_TW.json", "zh_CN.json", "en.json", "ja.json"]
SHOWCASE_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"


class TestT4FooterStructure:
    """49a-T4: showcase.html 三段式底部 footer 守衛（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _css(self):
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    def test_showcase_html_contains(self):
        """showcase.html footer 結構、快捷鍵、pager、openPagePicker 全部存在"""
        html = self._html()
        # removed
        assert 'class="showcase-status-bar"' not in html, \
            "showcase.html should not contain: 'class=\"showcase-status-bar\"'"
        # structure
        for expected in [
            'class="showcase-footer"',
            'class="footer-left"',
            'class="footer-center"',
            'class="footer-right"',
            "bi-film",
            "bi-person-circle",
            "<kbd>A</kbd>",
            "<kbd>S</kbd>",
            "<kbd>ESC</kbd>",
            "<kbd>←</kbd>",
            "<kbd>→</kbd>",
            'class="footer-pager"',
            'x-show="!showFavoriteActresses && totalPages > 1"',
            "prevPage()",
            "nextPage()",
            'x-ref="pageSelectFooter"',
            'class="pager-current"',
            "openPagePicker",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        # footer must not have x-data
        idx = html.find('class="showcase-footer"')
        assert idx >= 0
        div_start = html.rfind('<div', 0, idx)
        end = html.find('>', idx)
        opening_tag = html[div_start:end + 1]
        assert 'x-data' not in opening_tag, \
            "showcase-footer opening tag should not have x-data"
        # openPagePicker must use showPicker
        js = SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")
        assert "openPagePicker" in js, "core.js missing: 'openPagePicker'"
        assert "showPicker" in js, "core.js missing: 'showPicker'"

    def test_showcase_css_contains(self):
        """showcase.css 含 footer rules + responsive 隱藏 footer-left/center"""
        css = self._css()
        for expected in [
            ".showcase-footer",
            ".footer-left",
            ".footer-center",
            ".footer-right",
            ".footer-pager",
        ]:
            assert expected in css, f"showcase.css missing: {expected!r}"
        # responsive media query
        media_match = re.search(
            r"@media\'s*\(max-width:\'s*640px\'s*\)\'s*\{(.*?)\n\}",
            css, re.DOTALL,
        )
        if media_match is None:
            media_match = re.search(
                r"@media[^{]*640px[^{]*\{([^@]*?)\n\}",
                css, re.DOTALL,
            )
        assert media_match is not None, "showcase.css missing: @media (max-width: 640px)"
        body = media_match.group(1)
        assert ".footer-left" in body and ".footer-center" in body, \
            "@media (max-width: 640px) missing: .footer-left and .footer-center"
        assert ("display: none" in body or "display:none" in body), \
            "@media (max-width: 640px) missing: display: none"

class TestT4I18n:
    """49a-T4: showcase i18n keys guard (method folded)"""

    EXPECTED_SWITCH_MODE = {
        "zh_TW.json": "切換顯示",
        "zh_CN.json": "切换显示",
        "en.json": "Switch view",
        "ja.json": "表示切替",
    }

    @staticmethod
    def _load(locale):
        return json.loads((LOCALES_DIR / locale).read_text(encoding="utf-8"))

    def test_all_locales_i18n(self):
        """四語系 switch_mode / status / unit.actresses 全部正確"""
        for locale in LOCALE_FILES:
            data = self._load(locale)
            showcase = data.get("showcase", {})
            # switch_mode value check
            val = showcase.get("shortcut", {}).get("switch_mode")
            assert val, f"{locale}: missing showcase.shortcut.switch_mode"
            expected_val = self.EXPECTED_SWITCH_MODE[locale]
            assert val == expected_val, \
                f"{locale}: switch_mode expected {expected_val!r}, got {val!r}"
            # status.search_empty
            assert showcase.get("status", {}).get("search_empty"), \
                f"{locale}: missing showcase.status.search_empty"
            # status search_actresses parts
            status = showcase.get("status", {})
            for key in ("search_actresses_prefix", "search_actresses_middle", "search_actresses_suffix"):
                assert key in status, f"{locale}: missing showcase.status.{key!r}"
            # unit.actresses
            unit = showcase.get("unit", {})
            assert "actresses" in unit and unit["actresses"], \
                f"{locale}: missing or empty showcase.unit.actresses"


# ─── 49b-T4a: BurstPicker 模組抽出守衛 ────────────────────────────────────────
BURST_PICKER_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "burst-picker.js"
BASE_HTML_T4A = Path(__file__).parent.parent.parent / "web" / "templates" / "base.html"
MOTION_LAB_JS_T4A = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab.js"
MOTION_LAB_STATE_JS_T4A = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab-state.js"


class TestBurstPickerGuard:
    """49b-T4a: 守衛 BurstPicker 模組抽出（從 motion-lab.js → shared/burst-picker.js）"""

    PICKER_METHODS = (
        "playPickerBurst",
        "playPickerFloat",
        "playPickerHoverIn",
        "playPickerHoverOut",
        "playPickerFlipReplace",
        "playPickerExitAll",
        "playPickerReverseAll",
    )

    def test_burst_picker_js_contains(self):
        """burst-picker.js 存在暴露 module；motion-lab.js 已無 picker 定義；motion-lab-state.js 用新模組路徑"""
        # burst-picker.js: exists + window.BurstPicker + 7 method defs
        assert BURST_PICKER_JS.exists(), f"burst-picker.js 不存在：{BURST_PICKER_JS}"
        picker_js = BURST_PICKER_JS.read_text(encoding="utf-8")
        assert "window.BurstPicker" in picker_js, \
            "burst-picker.js missing: 'window.BurstPicker'"
        for method in self.PICKER_METHODS:
            assert method + ":" in picker_js, f"burst-picker.js missing: {method + ':'!r}"

        # motion-lab.js: picker methods should be removed
        lab_js = MOTION_LAB_JS_T4A.read_text(encoding="utf-8")
        for method in self.PICKER_METHODS:
            pattern = re.compile(re.escape(method) + r"\s*:\s*function")
            matches = pattern.findall(lab_js)
            assert not matches, \
                f"motion-lab.js 仍內嵌 {method} 方法定義（應只在 burst-picker.js）"

        # motion-lab-state.js: calls new module, not old
        state_js = MOTION_LAB_STATE_JS_T4A.read_text(encoding="utf-8")
        assert "window.BurstPicker.playPicker" in state_js, \
            "motion-lab-state.js missing: 'window.BurstPicker.playPicker'"
        legacy = re.findall(r"window\.MotionLab\.playPicker\w+", state_js)
        assert not legacy, \
            f"motion-lab-state.js 仍有舊呼叫 window.MotionLab.playPicker*：{legacy}"

    def test_base_html_loads_burst_picker(self):
        """base.html 含 burst-picker.js script tag 且使用 defer 或 type="module"（54a-T2 後允許 module）"""
        html = BASE_HTML_T4A.read_text(encoding="utf-8")
        assert "/static/js/shared/burst-picker.js" in html, \
            "base.html 缺少 /static/js/shared/burst-picker.js script 引用"
        # 驗證 defer 或 type="module"（type="module" 天生 deferred，等同 defer）
        pattern = re.compile(r'<script[^>]*burst-picker\.js[^>]*>')
        matches = pattern.findall(html)
        assert matches, "base.html 找不到 burst-picker.js script tag"
        for tag in matches:
            assert "defer" in tag or 'type="module"' in tag, \
                f"burst-picker.js script tag 應含 defer 或 type=\"module\" 屬性：{tag}"


# ─── 49b-T4cd: Actress Photo Picker UI/Alpine/SSE 整合守衛 ──────────────────
SHOWCASE_CSS_T4CD = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"


class TestPickerIntegrationGuard:
    """49b-T4cd: 守衛 Actress Photo Picker 在 Showcase Lightbox 的 UI + Alpine + SSE 整合（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _core_js(self):
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _css(self):
        return SHOWCASE_CSS_T4CD.read_text(encoding="utf-8")

    def test_picker_html_contains(self):
        """showcase.html 含 picker button、overlay 結構"""
        html = self._html()
        for expected in [
            "bi-arrow-clockwise",
            "showcase.actress.change_photo",
            "currentLightboxActress?.is_favorite",
            "actress-picker-overlay",
            "picker-candidates-grid",
            "picker-source-badge",
            "picker-loading",
            "picker-empty",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        # T1: actress-picker-area must be renamed
        assert "actress-picker-area" not in html, \
            "showcase.html should not contain: 'actress-picker-area'"

    def test_picker_js_contains(self):
        """core.js 含 picker state、methods、params、SSE handler 等必要字串"""
        js = self._core_js()
        for expected in [
            # state
            "_pickerOpen: false",
            "_pickerRunId: 0",
            "_candidates: []",
            "_pickerSelected: false",
            # methods
            "openActressPicker(",
            "_startPickerSSE(",
            "_closePicker(",
            "_resetPicker(",
            "_fadeMetadataPanel(",
            "_cancelPicker",
            # params
            "_PICKER_PARAMS",
            "arcOvershoot: 1.3",
            # burst picker animations
            "playPickerFlipReplace",
            "playPickerExitAll",
            "typeof window.BurstPicker",
            "playPickerReverseAll",
            # SSE defer-burst
            "_burstAllPickerCandidates",
            # i18n
            "showcase.actress.picker.replaced",
            "showcase.actress.picker.error",
            "showToast(",
            # reduced motion
            "prefers-reduced-motion",
            "matchMedia",
            # lightbox teardown
            "_pickerOpen",
            "_closePicker",
            # stale name capture
            "capturedName",
            "currentLightboxActress",
        ]:
            assert expected in js, f"core.js missing: {expected!r}"
        # arcDuration
        assert ("arcDuration:  0.75" in js or "arcDuration: 0.75" in js), \
            "core.js missing: 'arcDuration: 0.75' in _PICKER_PARAMS"
        # _burstAllPickerCandidates ≥ 4 occurrences
        assert js.count("_burstAllPickerCandidates") >= 4, \
            "_burstAllPickerCandidates must appear ≥4 times (def + done/timeout/error)"

    def test_picker_css_rules_present(self):
        """showcase.css 含 .picker-candidate-card opacity:0 + overlay fixed + spin keyframes"""
        css = self._css()
        assert ".picker-candidate-card" in css, \
            "showcase.css missing: '.picker-candidate-card'"
        card_block = re.search(
            r"(?:^|\n)\.picker-candidate-card\s*\{[^}]*\}", css, re.DOTALL
        )
        assert card_block, "showcase.css: cannot find .picker-candidate-card style block"
        assert "opacity: 0" in card_block.group(0), \
            ".picker-candidate-card missing: 'opacity: 0'"
        area_block = re.search(
            r"\.actress-picker-overlay\s*\{[^}]*\}", css, re.DOTALL
        )
        assert area_block, "showcase.css: cannot find .actress-picker-overlay style block"
        overlay_css = area_block.group(0)
        for expected in ["position: fixed", "bottom:", "width:"]:
            assert expected in overlay_css, \
                f".actress-picker-overlay missing: {expected!r}"
        assert "@keyframes spin" in css, \
            "showcase.css missing: '@keyframes spin'"

    def test_picker_overlay_is_showcase_lightbox_direct_child(self):
        """49c-T1: actress-picker-overlay 必須為 .showcase-lightbox 的直接 child"""
        import html.parser as _html_parser

        html_text = self._html()
        assert "actress-picker-overlay" in html_text, \
            "showcase.html missing: 'actress-picker-overlay'"

        class _DivStackParser(_html_parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.div_stack = []
                self.overlay_ancestors = None
                self.found_overlay_in_lightbox_content = False

            def handle_starttag(self, tag, attrs):
                if tag != "div":
                    return
                attr_dict = dict(attrs)
                classes = set(attr_dict.get("class", "").split())
                if "actress-picker-overlay" in classes:
                    if self.overlay_ancestors is None:
                        self.overlay_ancestors = [s.copy() for s in self.div_stack]
                    if any("lightbox-content" in s for s in self.div_stack):
                        self.found_overlay_in_lightbox_content = True
                self.div_stack.append(classes)

            def handle_endtag(self, tag):
                if tag != "div":
                    return
                if self.div_stack:
                    self.div_stack.pop()

        parser = _DivStackParser()
        parser.feed(html_text)
        assert parser.overlay_ancestors is not None, \
            "actress-picker-overlay not found in markup"
        assert not parser.found_overlay_in_lightbox_content, \
            "actress-picker-overlay should not be inside lightbox-content"
        assert "showcase-lightbox" in parser.overlay_ancestors[-1], \
            "actress-picker-overlay direct parent should have showcase-lightbox class"

# Removed in T55b — superseded by stylelint:
#   TestSettingsCssHardcoded, TestHelpCssHardcoded, TestDesignSystemCssHardcoded
#     -> declaration-property-value-disallowed-list (transition / filter / box-shadow)
#        + color-no-hex (with design-system.css whole-file ignore).
# TestMotionLabHtmlHardcoded kept below as C-class deferral (HTML <style> scan
# needs postcss-html parser; T55b is minimal toolchain — handled in T55d).


class TestMotionLabHtmlHardcoded:
    """T1.5.6: 確認 motion_lab.html <style> 區塊內無 hardcoded 視覺值（blur / hex / radius / transition）

    掃描策略：僅掃 <style>...</style> block 內容，不掃 HTML style="..." 屬性
    （demo 區大量合法 inline style 用於展示，不納入守衛範疇）
    """

    def _style_blocks(self) -> str:
        """提取 motion_lab.html 所有 <style> block 內容合併"""
        html = MOTION_LAB_HTML.read_text(encoding="utf-8")
        blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)
        return "\n".join(blocks)

    def test_no_hardcoded_blur_px_in_motion_lab_html(self):
        """motion_lab.html <style> 區塊不含 hardcoded blur(Npx)（須用 var(--fluent-blur-*)）"""
        css = self._style_blocks()
        matches = re.findall(r"blur\(\d+px\)", css)
        assert not matches, (
            f"motion_lab.html <style> 仍有 hardcoded blur(Npx)，請改用 var(--fluent-blur-light/overlay/heavy)：{matches}"
        )

    def test_no_hardcoded_hex_color_in_motion_lab_html(self):
        """motion_lab.html <style> 區塊不含裸 hardcoded hex color（#xxx / #xxxxxx）

        允許例外：
        - var(..., #fff) 形式的 CSS fallback 值（在 var() 內部，pattern 不命中）
        """
        css = self._style_blocks()
        lines = css.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳過純註釋行
            if stripped.startswith("/*") or stripped.startswith("//") or stripped.startswith("*"):
                continue
            # 找裸 hex（不在 var() 內部）：pattern 尋找 # 後接 3/4/6/8 hex digits，
            # 但排除 var(..., #xxx) 形式（前方有逗號 + 空格）
            # 實作：先移除 var( ... ) 內容再搜尋
            line_no_var_fallback = re.sub(r"var\([^)]*\)", "", line)
            if re.search(r"#[0-9a-fA-F]{3,8}\b", line_no_var_fallback):
                violations.append(f"L{i}: {stripped}")
        assert not violations, (
            "motion_lab.html <style> 殘留裸 hex 硬編碼（應改用 token；var() 內 fallback 除外）：\n"
            + "\n".join(violations)
        )

    def test_no_hardcoded_border_radius_px_in_motion_lab_html(self):
        """motion_lab.html <style> 區塊 border-radius 不應含裸 px 數字硬編碼

        允許例外：
        - border-radius: 50%（圓形語義，比例值不是像素）
        - var(--fluent-radius-*, Npx) 的 fallback px 值（在 var() 內部）
        """
        css = self._style_blocks()
        lines = css.split("\n")
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("//") or stripped.startswith("*"):
                continue
            if "border-radius" not in line:
                continue
            # 允許 50%
            if re.search(r"border-radius\s*:\s*50%", line):
                continue
            # 移除 var() 內容再搜尋
            line_no_var = re.sub(r"var\([^)]*\)", "", line)
            if re.search(r"border-radius\s*:[^;]*\d+px", line_no_var):
                violations.append(f"L{i}: {stripped}")
        assert not violations, (
            "motion_lab.html <style> border-radius 殘留裸 px 硬編碼（應改用 var(--fluent-radius-*)；"
            "50% 及 var() 內 fallback 除外）：\n"
            + "\n".join(violations)
        )

    def test_no_hardcoded_transition_duration_in_motion_lab_html(self):
        """motion_lab.html <style> 區塊 transition 不應含裸數字秒數或非 fluent 前綴 alias 硬編碼

        允許例外（留 Phase 2 處理，已標記白名單）：
        - .picker-source-badge transition: background 0.15s
        - .picker-check-icon transition: opacity 0.15s
        這兩處屬 Picker demo 的細節 transition，Phase 1 不改動，Phase 2 統一處理。

        非 fluent 前綴 alias 規則：
        - 禁止 var(--duration-*) — 應改用 var(--fluent-duration-*)
        - 禁止 var(--ease-*) — 應改用 var(--fluent-ease-*)
        這些 alias 已在 theme.css 定義，但 motion_lab 的 <style> 應直接用 canonical token。
        """
        css = self._style_blocks()
        lines = css.split("\n")
        violations = []
        # Phase 2 whitelist：picker demo 兩處細節 transition（已知，留 Phase 2 處理）
        phase2_whitelist = {
            "transition: background 0.15s;",
            "transition: opacity 0.15s;",
        }
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("//") or stripped.startswith("*"):
                continue
            # Phase 2 whitelist
            if stripped in phase2_whitelist:
                continue
            if "transition:" in line:
                # 1. 裸數字秒數（不含任何 var(-- 前綴）
                if re.search(r"transition:[^;]*\b0?\.\d+s\b", line) and "var(--" not in line:
                    violations.append(f"L{i}: {stripped}")
                    continue
                # 2. 非 fluent 前綴 alias：var(--duration-*) 或 var(--ease-*)
                #    （直接命中即是 alias，fluent 前綴版本為 var(--fluent-duration-*) 不命中此 pattern）
                if re.search(r"var\(--(?:duration|ease)-", line):
                    violations.append(f"L{i}: {stripped}")
        assert not violations, (
            "motion_lab.html <style> transition 殘留裸數字秒數或非 fluent 前綴 alias\n"
            "（應改用 var(--fluent-duration-*) / var(--fluent-ease-*)；"
            "picker 兩處 0.15s 已列 Phase 2 whitelist）：\n"
            + "\n".join(violations)
        )



# ─── 52-T2.1: §5 Ease Roles Demo 守衛 ────────────────────────────────────────
MOTION_LAB_HTML_T2 = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
MOTION_LAB_JS_T2 = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab.js"


class TestMotionLabT2EaseRoles:
    """52-T2.1: 守衛 §5 Ease Roles 並排 demo 必要元素"""

    def _html(self) -> str:
        return MOTION_LAB_HTML_T2.read_text(encoding="utf-8")

    def _js(self) -> str:
        return MOTION_LAB_JS_T2.read_text(encoding="utf-8")

    def test_html_contains_fluent_decel(self):
        """motion_lab.html 含 fluent-decel 字樣（Ease Roles select 選項或 demo panel）"""
        assert "fluent-decel" in self._html(), \
            "motion_lab.html 缺少 fluent-decel（§5 Ease Roles select / demo panel 未加入）"

    def test_html_contains_fluent_accel(self):
        """motion_lab.html 含 fluent-accel 字樣（Ease Roles select 選項或 demo panel）"""
        assert "fluent-accel" in self._html(), \
            "motion_lab.html 缺少 fluent-accel（§5 Ease Roles select / demo panel 未加入）"

    def test_html_has_ease_roles_tab(self):
        """motion_lab.html tab bar 含 ease-roles tab button"""
        assert "ease-roles" in self._html(), \
            "motion_lab.html tab bar 缺少 ease-roles tab（§5 Ease Roles tab 未加入）"

    def test_js_has_play_ease_roles_demo(self):
        """motion-lab.js 含 playEaseRolesDemo 函式"""
        assert "playEaseRolesDemo" in self._js(), \
            "motion-lab.js 缺少 playEaseRolesDemo（§5 Ease Roles demo 函式未加入）"

    def test_js_no_bare_back_out_in_stream(self):
        """motion-lab.js playCardStreamIn 不含裸 power2.out / power3.out（已改 fluent-decel）"""
        js = self._js()
        # 找到 playCardStreamIn 區塊（到下一個函式前）
        start = js.find("playCardStreamIn:")
        assert start != -1, \
            "playCardStreamIn 函式不見了；如果是重命名請更新此守衛"
        end = js.find("\n        /**", start + 1)
        block = js[start:end] if end != -1 else js[start:]
        assert "power3.out" not in block, \
            "playCardStreamIn 仍含 power3.out（應改為 fluent-decel）"
        assert "power2.out" not in block, \
            "playCardStreamIn 仍含 power2.out（應改為 fluent-decel）"


MOTION_LAB_HTML_T2_2 = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
MOTION_LAB_JS_T2_2 = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab.js"


class TestMotionLabT2DurationBuckets:
    """52-T2.2: 守衛 §5 Duration Buckets 並排 demo 必要元素"""

    def _html(self) -> str:
        return MOTION_LAB_HTML_T2_2.read_text(encoding="utf-8")

    def _js(self) -> str:
        return MOTION_LAB_JS_T2_2.read_text(encoding="utf-8")

    def test_html_has_duration_buckets_tab(self):
        """motion_lab.html tab bar 含 duration-buckets tab button"""
        assert "duration-buckets" in self._html(), \
            "motion_lab.html tab bar 缺少 duration-buckets tab（§5 Duration Buckets tab 未加入）"

    def test_js_has_play_duration_buckets_demo(self):
        """motion-lab.js 含 playDurationBucketsDemo 函式"""
        assert "playDurationBucketsDemo" in self._js(), \
            "motion-lab.js 缺少 playDurationBucketsDemo（§5 Duration Buckets demo 函式未加入）"

    def test_html_shows_duration_fast_label(self):
        """motion_lab.html 含 DURATION.fast 標籤（duration-buckets panel box label）"""
        assert "DURATION.fast" in self._html(), \
            "motion_lab.html 缺少 DURATION.fast 標籤（§5 Duration Buckets panel box label 未加入）"


# ─── 52-T2.3: §5 Special Motion White-list Demo 守衛 ──────────────────────────
MOTION_LAB_HTML_T2_3 = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
MOTION_LAB_JS_T2_3 = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "motion-lab.js"


class TestMotionLabT2SpecialMotion:
    """52-T2.3: 守衛 §5 Special Motion 白名單 demo 必要元素"""

    def _html(self) -> str:
        return MOTION_LAB_HTML_T2_3.read_text(encoding="utf-8")

    def _js(self) -> str:
        return MOTION_LAB_JS_T2_3.read_text(encoding="utf-8")

    def test_html_has_special_motion_tab(self):
        """motion_lab.html tab bar 含 special-motion tab button"""
        assert "special-motion" in self._html(), \
            "motion_lab.html tab bar 缺少 special-motion tab（§5 Special Motion 白名單 tab 未加入）"

    def test_js_has_play_special_motion_checkmark_demo(self):
        """motion-lab.js 含 playSpecialMotionCheckmarkDemo 函式"""
        assert "playSpecialMotionCheckmarkDemo" in self._js(), \
            "motion-lab.js 缺少 playSpecialMotionCheckmarkDemo（§5 Special Motion checkmark demo 函式未加入）"

    def test_js_has_play_special_motion_shake_demo(self):
        """motion-lab.js 含 playSpecialMotionShakeDemo 函式"""
        assert "playSpecialMotionShakeDemo" in self._js(), \
            "motion-lab.js 缺少 playSpecialMotionShakeDemo（§5 Special Motion shake demo 函式未加入）"

    def test_js_has_play_special_motion_pulse_demo(self):
        """motion-lab.js 含 playSpecialMotionPulseDemo 函式"""
        assert "playSpecialMotionPulseDemo" in self._js(), \
            "motion-lab.js 缺少 playSpecialMotionPulseDemo（§5 Special Motion pulse demo 函式未加入）"

    def test_html_has_whitelist_skip_note(self):
        """motion_lab.html special-motion panel 含 whitelist-skip-note 跳過說明"""
        assert "whitelist-skip-note" in self._html(), \
            "motion_lab.html 缺少 whitelist-skip-note（§5 Special Motion 跳過條目說明未加入）"


# ─── 54a-T1: importmap + pre_alpine_module slot + ghost-fly ESM export 守衛 ───
_BASE_HTML_54A = Path(__file__).parent.parent.parent / "web" / "templates" / "base.html"
_GHOST_FLY_JS_54A = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "ghost-fly.js"


class TestImportMapGuard:
    """54a-T1: importmap + pre_alpine_module slot + ghost-fly ESM export guards"""

    def _base(self) -> str:
        return _BASE_HTML_54A.read_text(encoding="utf-8")

    def _ghost_fly(self) -> str:
        return _GHOST_FLY_JS_54A.read_text(encoding="utf-8")

    def test_importmap_exists(self):
        """base.html 含 type="importmap" 字串"""
        assert 'type="importmap"' in self._base(), \
            'base.html 缺少 <script type="importmap">（54a-T1 importmap 未插入）'

    def test_importmap_aliases(self):
        """base.html importmap 含六個 @/ alias"""
        content = self._base()
        for alias in ('"@/shared/"', '"@/components/"', '"@/showcase/"',
                      '"@/scanner/"', '"@/settings/"', '"@/search/"'):
            assert alias in content, \
                f'base.html importmap 缺少 {alias} alias（54a-T1 importmap alias 未設定）'

    def test_pre_alpine_module_slot(self):
        """base.html 含 {% block pre_alpine_module %} slot"""
        assert "{% block pre_alpine_module %}" in self._base(), \
            "base.html 缺少 {% block pre_alpine_module %}（54a-T1 slot 未插入）"

    def test_ghost_fly_has_export(self):
        """ghost-fly.js 含 export 關鍵字"""
        assert "export" in self._ghost_fly(), \
            "ghost-fly.js 缺少 export（54a-T1 ESM export 未加入）"

    def test_ghost_fly_window_bridge(self):
        """ghost-fly.js 含 window.GhostFly 賦值（橋接保留）"""
        assert "window.GhostFly = GhostFly" in self._ghost_fly(), \
            "ghost-fly.js 缺少 window.GhostFly = GhostFly（54a-T1 window 橋接被移除）"

    def test_ghost_fly_script_tag_is_module(self):
        """base.html 中 ghost-fly.js 的 script tag 是 type="module"，無殘留 defer 標籤"""
        content = self._base()
        assert 'type="module" src="/static/js/shared/ghost-fly.js"' in content, \
            'base.html ghost-fly.js script tag 非 type="module"（54a-T1 script tag 未更新）'
        assert '<script defer src="/static/js/shared/ghost-fly.js">' not in content, \
            'base.html 仍有殘留的 <script defer src=".../ghost-fly.js">（54a-T1 舊標籤未移除）'


class TestESMExportGuard:
    """
    54a-T2：守衛五個 shared/components 工具的 ESM export + window 橋接 + base.html script tag
    前置：TestImportMapGuard 通過（T1 spike gate）
    """

    def _read(self, rel_path):
        return Path(__file__).parent.parent.parent / rel_path

    def _burst_picker(self):
        return (self._read("web/static/js/shared/burst-picker.js")).read_text(encoding="utf-8")

    def _motion_adapter(self):
        return (self._read("web/static/js/components/motion-adapter.js")).read_text(encoding="utf-8")

    def _path_utils(self):
        return (self._read("web/static/js/components/path-utils.js")).read_text(encoding="utf-8")

    def _page_lifecycle(self):
        return (self._read("web/static/js/components/page-lifecycle.js")).read_text(encoding="utf-8")

    def _motion_prefs(self):
        return (self._read("web/static/js/components/motion-prefs.js")).read_text(encoding="utf-8")

    def _base(self):
        return (self._read("web/templates/base.html")).read_text(encoding="utf-8")

    def test_burst_picker_export_and_bridge(self):
        """burst-picker.js 含 export + window.BurstPicker 橋接"""
        content = self._burst_picker()
        assert "export" in content, \
            "burst-picker.js 缺少 export（54a-T2 ESM export 未加入）"
        assert "window.BurstPicker" in content, \
            "burst-picker.js 缺少 window.BurstPicker（54a-T2 window 橋接被移除）"

    def test_motion_adapter_export_and_bridge(self):
        """motion-adapter.js 含 export + window.OpenAver.motion 橋接"""
        content = self._motion_adapter()
        assert "export" in content, \
            "motion-adapter.js 缺少 export（54a-T2 ESM export 未加入）"
        assert "window.OpenAver.motion" in content, \
            "motion-adapter.js 缺少 window.OpenAver.motion（54a-T2 window 橋接被移除）"

    def test_path_utils_export_and_bridge(self):
        """path-utils.js 含 export pathToDisplay + window.pathToDisplay 橋接"""
        content = self._path_utils()
        assert "export" in content and "pathToDisplay" in content, \
            "path-utils.js 缺少 export pathToDisplay（54a-T2 ESM export 未加入）"
        assert "window.pathToDisplay" in content, \
            "path-utils.js 缺少 window.pathToDisplay（54a-T2 window 橋接被移除）"

    def test_page_lifecycle_export_and_bridge(self):
        """page-lifecycle.js 含 export + window.__registerPage 橋接"""
        content = self._page_lifecycle()
        assert "export" in content, \
            "page-lifecycle.js 缺少 export（54a-T2 ESM export 未加入）"
        assert "window.__registerPage" in content, \
            "page-lifecycle.js 缺少 window.__registerPage（54a-T2 window 橋接被移除）"

    def test_motion_prefs_export_and_bridge(self):
        """motion-prefs.js 含 export + window.OpenAver 初始化保留"""
        content = self._motion_prefs()
        assert "export" in content, \
            "motion-prefs.js 缺少 export（54a-T2 ESM export 未加入）"
        assert "window.OpenAver" in content, \
            "motion-prefs.js 缺少 window.OpenAver（54a-T2 window 橋接被移除）"

    @pytest.mark.parametrize("path", [
        "/static/js/shared/burst-picker.js",
        "/static/js/components/motion-adapter.js",
        "/static/js/components/path-utils.js",
        "/static/js/components/page-lifecycle.js",
        "/static/js/components/motion-prefs.js",
    ])
    def test_five_files_script_tags_are_module(self, path):
        """base.html 中五個工具的 script tag 均為 type="module"，無殘留 <script defer src>"""
        content = self._base()
        assert f'type="module" src="{path}"' in content, \
            f'base.html {path} script tag 非 type="module"（54a-T2 script tag 未更新）'
        assert f'<script defer src="{path}">' not in content, \
            f'base.html 仍有殘留的 <script defer src="{path}">（54a-T2 舊標籤未移除）'


class TestSettingsESMGuard:
    """54d-T1：守衛 settings state 模組 + main.js 結構"""

    def _read(self, rel_path):
        return (Path(__file__).parent.parent.parent / rel_path).read_text(encoding="utf-8")

    def test_state_config_exists_and_exports(self):
        content = self._read("web/static/js/pages/settings/state-config.js")
        assert "export function stateConfig" in content

    def test_state_providers_exists_and_exports(self):
        content = self._read("web/static/js/pages/settings/state-providers.js")
        assert "export function stateProviders" in content

    def test_state_ui_exists_and_exports(self):
        content = self._read("web/static/js/pages/settings/state-ui.js")
        assert "export function stateUI" in content


    def test_main_js_exists_and_has_alpine_init(self):
        content = self._read("web/static/js/pages/settings/main.js")
        assert "alpine:init" in content

    def test_main_js_registers_settings_name(self):
        content = self._read("web/static/js/pages/settings/main.js")
        assert "Alpine.data('settings'," in content
        assert "Alpine.data('settingsPage'" not in content

    def test_main_js_uses_importmap_alias(self):
        content = self._read("web/static/js/pages/settings/main.js")
        assert "@/settings/" in content

    def test_no_circular_state_imports(self):
        """三個 state 模組頂層 import 不可引用彼此"""
        import re
        forbidden = ["state-config", "state-providers", "state-ui"]
        for fname in ["state-config.js", "state-providers.js", "state-ui.js"]:
            content = self._read(f"web/static/js/pages/settings/{fname}")
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped.startswith("import"):
                    continue
                for f in forbidden:
                    assert f not in stripped, \
                        f"{fname} 有循環 import：{stripped}"

    # ── T2 guards ──────────────────────────────────────────────────────────

    def test_settings_html_has_pre_alpine_module(self):
        """settings.html 含 pre_alpine_module block override，含 main.js module script"""
        content = self._read("web/templates/settings.html")
        assert "pre_alpine_module" in content, \
            "settings.html 缺少 {% block pre_alpine_module %}（54d-T2 未加入 main.js 載入）"
        assert "settings/main.js" in content, \
            "settings.html pre_alpine_module block 缺少 main.js module script"

    def test_settings_html_xdata_is_settings(self):
        """settings.html x-data 值為 'settings'（非 'settingsPage'）"""
        content = self._read("web/templates/settings.html")
        assert 'x-data="settings"' in content, \
            "settings.html x-data 非 settings（54d-T2 切換未完成）"
        assert 'x-data="settingsPage"' not in content, \
            "settings.html 仍有舊 x-data=settingsPage（54d-T2 切換未完成）"

    def test_settings_html_no_settings_js_script(self):
        """settings.html extra_js block 不含 /pages/settings.js script 載入"""
        content = self._read("web/templates/settings.html")
        assert "/pages/settings.js" not in content, \
            "settings.html 仍載入舊 settings.js（54d-T2 未移除）"

    def test_settings_js_deleted(self):
        """web/static/js/pages/settings.js 不存在"""
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "web/static/js/pages/settings.js"
        assert not p.exists(), \
            "settings.js 仍存在（54d-T2 刪除步驟未執行）"

    def test_no_settings_page_xdata_in_templates(self):
        """所有 production templates 不含 x-data=\"settingsPage\"（防殘留）"""
        from pathlib import Path
        templates_dir = Path(__file__).parent.parent.parent / "web/templates"
        for tmpl in templates_dir.rglob("*.html"):
            content = tmpl.read_text(encoding="utf-8")
            assert 'x-data="settingsPage"' not in content, \
                f"{tmpl.name} 仍含 x-data=settingsPage（54d-T2 殘留）"

    def test_no_settings_page_alpine_data_in_js(self):
        """web/static/js/pages/ 下所有 JS 不含 Alpine.data('settingsPage'（防殘留）"""
        from pathlib import Path
        pages_dir = Path(__file__).parent.parent.parent / "web/static/js/pages"
        for js_file in pages_dir.rglob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "Alpine.data('settingsPage'" not in content, \
                f"{js_file.name} 仍含 Alpine.data('settingsPage'（54d-T2 殘留）"

    def test_main_js_no_settingspage_reference(self):
        """settings/main.js 不含 settingsPage 字串"""
        content = self._read("web/static/js/pages/settings/main.js")
        assert "settingsPage" not in content, \
            "settings/main.js 含 settingsPage（54d-T2 設計錯誤）"

    def test_main_js_uses_descriptor_merge(self):
        """main.js 使用 descriptor-preserving merge 而非 object spread，
        防止 getter（isDirty、folderPreviewText 等）在合併時被立即求值成靜態值"""
        content = self._read("web/static/js/pages/settings/main.js")
        assert "getOwnPropertyDescriptors" in content, \
            "settings/main.js 缺少 getOwnPropertyDescriptors（54d Codex P1 修正未套用）"
        assert "...stateConfig()" not in content, \
            "settings/main.js 仍使用 spread 合併 stateConfig()（54d Codex P1 修正未套用）"

    def test_state_config_has_getter_isDirty(self):
        """state-config.js 的 isDirty 必須是 getter（get isDirty()），
        確保 mergeState 有 getter 可以保留"""
        content = self._read("web/static/js/pages/settings/state-config.js")
        assert "get isDirty()" in content, \
            "state-config.js 的 isDirty 不是 getter — spread bug 修正依賴此 getter"


class TestScannerESMGuard:
    """54c-T1：守衛 scanner state 模組 + main.js 結構"""

    def _read(self, rel_path):
        return (Path(__file__).parent.parent.parent / rel_path).read_text(encoding="utf-8")

    def test_state_scan_exists_and_exports(self):
        """驗 state-scan.js 存在且含 export function stateScan"""
        content = self._read("web/static/js/pages/scanner/state-scan.js")
        assert "export function stateScan" in content

    def test_state_batch_exists_and_exports(self):
        """驗 state-batch.js 存在且含 export function stateBatch"""
        content = self._read("web/static/js/pages/scanner/state-batch.js")
        assert "export function stateBatch" in content

    def test_state_alias_exists_and_exports(self):
        """驗 state-alias.js 存在且含 export function stateAlias"""
        content = self._read("web/static/js/pages/scanner/state-alias.js")
        assert "export function stateAlias" in content

    def test_main_js_exists_and_has_alpine_init(self):
        """驗 main.js 存在且含 alpine:init"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "alpine:init" in content

    def test_main_js_registers_scanner_name(self):
        """驗 main.js 含 Alpine.data('scanner', 且不含 scannerPage"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "Alpine.data('scanner'," in content
        assert "Alpine.data('scannerPage'" not in content

    def test_main_js_uses_importmap_alias(self):
        """驗 main.js import 語句使用 @/scanner/ alias"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "@/scanner/" in content

    def test_main_js_has_descriptor_merge(self):
        """驗 main.js 含 getOwnPropertyDescriptors 或 defineProperties（確保 getter 不被 spread 破壞）"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "getOwnPropertyDescriptors" in content or "defineProperties" in content

    def test_main_js_no_plain_spread_merge(self):
        """驗 main.js 不含三個 state 的 plain spread（...stateScan() 等）"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "...stateScan()" not in content
        assert "...stateBatch()" not in content
        assert "...stateAlias()" not in content

    def test_state_scan_no_batch_functions(self):
        """驗 state-scan.js 不含 batch 函式定義（防誤放；跨模組 this.xxx 呼叫允許）"""
        content = self._read("web/static/js/pages/scanner/state-scan.js")
        # 只防函式定義被放錯模組，不攔 this.checkMissing() 等跨模組呼叫
        assert "checkMissing() {" not in content
        assert "runMissingEnrich" not in content
        assert "resumeMissingEnrich" not in content

    def test_state_batch_no_scan_functions(self):
        """驗 state-batch.js 不含 scan 主流程函式（防誤放）"""
        content = self._read("web/static/js/pages/scanner/state-batch.js")
        assert "generate(" not in content
        assert "runNfoUpdate" not in content
        assert "runJellyfinImageUpdate" not in content
        assert "copyOutputPath" not in content

    def test_no_circular_state_imports(self):
        """驗三個 state 模組頂層 import 不引用彼此"""
        forbidden = ["state-scan", "state-batch", "state-alias"]
        for fname in ["state-scan.js", "state-batch.js", "state-alias.js"]:
            content = self._read(f"web/static/js/pages/scanner/{fname}")
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped.startswith("import"):
                    continue
                for f in forbidden:
                    assert f not in stripped, \
                        f"{fname} 有循環 import：{stripped}"

    def test_scanner_html_has_pre_alpine_module(self):
        """scanner.html 含 pre_alpine_module block override，含 main.js module script"""
        content = self._read("web/templates/scanner.html")
        assert "pre_alpine_module" in content, \
            "scanner.html 缺少 {% block pre_alpine_module %}（54c-T2 未加入 main.js 載入）"
        assert "scanner/main.js" in content, \
            "scanner.html pre_alpine_module block 缺少 main.js module script"

    def test_scanner_html_xdata_is_scanner(self):
        """scanner.html x-data 值為 'scanner'（非 'scannerPage'）"""
        content = self._read("web/templates/scanner.html")
        assert 'x-data="scanner"' in content, \
            "scanner.html x-data 非 scanner（54c-T2 切換未完成）"
        assert 'x-data="scannerPage"' not in content, \
            "scanner.html 仍有舊 x-data=scannerPage（54c-T2 切換未完成）"

    def test_scanner_html_no_scanner_js_script(self):
        """scanner.html extra_js block 不含 /pages/scanner.js script 載入"""
        content = self._read("web/templates/scanner.html")
        assert "/pages/scanner.js" not in content, \
            "scanner.html 仍載入舊 scanner.js（54c-T2 未移除）"

    def test_scanner_js_deleted(self):
        """web/static/js/pages/scanner.js 不存在"""
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "web/static/js/pages/scanner.js"
        assert not p.exists(), \
            "scanner.js 仍存在（54c-T2 刪除步驟未執行）"

    def test_no_scanner_page_xdata_in_templates(self):
        """所有 production templates 不含 x-data=\"scannerPage\"（防殘留）"""
        from pathlib import Path
        templates_dir = Path(__file__).parent.parent.parent / "web/templates"
        for tmpl in templates_dir.rglob("*.html"):
            content = tmpl.read_text(encoding="utf-8")
            assert 'x-data="scannerPage"' not in content, \
                f"{tmpl.name} 仍含 x-data=scannerPage（54c-T2 殘留）"

    def test_no_scanner_page_alpine_data_in_js(self):
        """web/static/js/pages/ 下所有 JS 不含 Alpine.data('scannerPage'（防殘留）"""
        from pathlib import Path
        pages_dir = Path(__file__).parent.parent.parent / "web/static/js/pages"
        for js_file in pages_dir.rglob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "Alpine.data('scannerPage'" not in content, \
                f"{js_file.name} 仍含 Alpine.data('scannerPage'（54c-T2 殘留）"

    def test_main_js_no_scannerpage_reference(self):
        """scanner/main.js 不含 scannerPage 字串"""
        content = self._read("web/static/js/pages/scanner/main.js")
        assert "scannerPage" not in content, \
            "scanner/main.js 含 scannerPage（54c-T2 設計錯誤）"


class TestShowcaseESMGuard:
    """54b 守衛 — Showcase ESM 模組化

    T1a：state-base.js（foundation）
    T1b：state-videos / state-actress / state-lightbox / main.js
    T2b：showcase.html 切換 + core.js 刪除
    """

    BASE = Path(__file__).parents[2] / "web" / "static" / "js" / "pages" / "showcase"

    def _read(self, filename):
        return (self.BASE / filename).read_text(encoding="utf-8")

    # ── T1a guards（state-base.js foundation）────────────────────────

    def test_state_base_exists_and_exports(self):
        """state-base.js 存在且含 export function stateBase 和 export var _videos"""
        assert (self.BASE / "state-base.js").exists(), (
            "showcase/state-base.js 不存在"
        )
        content = self._read("state-base.js")
        assert "export function stateBase" in content, (
            "state-base.js 缺少 export function stateBase"
        )
        assert "export var _videos" in content or "export let _videos" in content, (
            "state-base.js 缺少 export var _videos（共用陣列必須 export 供其他模組 import）"
        )

    def test_state_base_has_shared_array_exports(self):
        """state-base.js export _videos、_filteredVideos、_actresses、_filteredActresses"""
        content = self._read("state-base.js")
        for var_name in ("_videos", "_filteredVideos", "_actresses", "_filteredActresses"):
            assert var_name in content, (
                f"state-base.js 缺少 {var_name} — "
                "module-level 共用陣列必須在 state-base.js 宣告（F1 性能優化：大陣列移出 Alpine reactive scope）"
            )

    def test_state_base_no_lightbox_functions(self):
        """state-base.js 不含 openLightbox / closeLightbox（防止 lightbox 邏輯誤放入 base）"""
        content = self._read("state-base.js")
        assert "openLightbox(" not in content, (
            "state-base.js 含 openLightbox — lightbox 邏輯應在 state-lightbox.js"
        )
        assert "closeLightbox(" not in content, (
            "state-base.js 含 closeLightbox — lightbox 邏輯應在 state-lightbox.js"
        )

    def test_state_base_no_picker_params(self):
        """state-base.js 不含 _PICKER_PARAMS（應在 stateLightbox 閉包，非 base state）"""
        content = self._read("state-base.js")
        assert "_PICKER_PARAMS" not in content, (
            "state-base.js 含 _PICKER_PARAMS — "
            "此常數應在 stateLightbox() 函式頂部作閉包常數（OQ-54B-2 Option B），不應放 stateBase"
        )

    # ── T1b guards（state-videos / state-actress / state-lightbox / main.js）──

    def test_state_videos_exists_and_exports(self):
        """state-videos.js 存在且含 export function stateVideos"""
        assert (self.BASE / "state-videos.js").exists(), (
            "showcase/state-videos.js 不存在"
        )
        content = self._read("state-videos.js")
        assert "export function stateVideos" in content, (
            "state-videos.js 缺少 export function stateVideos"
        )

    def test_state_actress_exists_and_exports(self):
        """state-actress.js 存在且含 export function stateActress"""
        assert (self.BASE / "state-actress.js").exists(), (
            "showcase/state-actress.js 不存在"
        )
        content = self._read("state-actress.js")
        assert "export function stateActress" in content, (
            "state-actress.js 缺少 export function stateActress"
        )

    def test_state_lightbox_exists_and_exports(self):
        """state-lightbox.js 存在且含 export function stateLightbox"""
        assert (self.BASE / "state-lightbox.js").exists(), (
            "showcase/state-lightbox.js 不存在"
        )
        content = self._read("state-lightbox.js")
        assert "export function stateLightbox" in content, (
            "state-lightbox.js 缺少 export function stateLightbox"
        )

    def test_main_js_exists_and_has_alpine_init(self):
        """main.js 存在且含 alpine:init 事件監聽"""
        assert (self.BASE / "main.js").exists(), (
            "showcase/main.js 不存在"
        )
        content = self._read("main.js")
        assert "alpine:init" in content, (
            "showcase/main.js 缺少 alpine:init 事件監聽"
        )

    def test_main_js_registers_showcase_name(self):
        """main.js 含 Alpine.data('showcase', — 名稱必須是 showcase，非 showcaseState"""
        content = self._read("main.js")
        assert "Alpine.data('showcase'," in content or 'Alpine.data("showcase",' in content, (
            "showcase/main.js 缺少 Alpine.data('showcase', — "
            "54b 要求 Alpine component 名稱從 showcaseState 改為 showcase"
        )
        assert "Alpine.data('showcaseState'" not in content and 'Alpine.data("showcaseState"' not in content, (
            "showcase/main.js 不應含 Alpine.data('showcaseState' — "
            "舊名稱 showcaseState 應已移除，防殘留"
        )

    def test_main_js_uses_importmap_alias(self):
        """main.js import 語句使用 @/showcase/ alias"""
        content = self._read("main.js")
        assert "@/showcase/" in content, (
            "showcase/main.js import 語句缺少 @/showcase/ alias — "
            "必須使用 importmap alias，不可用相對路徑"
        )

    def test_main_js_has_descriptor_merge(self):
        """main.js 含 getOwnPropertyDescriptors 或 defineProperties"""
        content = self._read("main.js")
        has_merge = (
            "getOwnPropertyDescriptors" in content
            or "defineProperties" in content
        )
        assert has_merge, (
            "showcase/main.js 缺少 descriptor-preserving 合併（getOwnPropertyDescriptors 或 defineProperties）"
        )

    def test_main_js_no_plain_spread_merge(self):
        """main.js 不含 plain spread（...stateBase() 等）"""
        content = self._read("main.js")
        for factory in ("stateBase()", "stateVideos()", "stateActress()", "stateLightbox()"):
            assert f"...{factory}" not in content, (
                f"showcase/main.js 含 ...{factory} plain spread — "
                "必須改用 mergeState（descriptor-preserving）"
            )

    def test_main_js_factory_calls_use_call_this(self):
        """main.js 所有 factory 呼叫使用 .call(this)"""
        content = self._read("main.js")
        for factory in ("stateBase", "stateVideos", "stateActress", "stateLightbox"):
            assert f"{factory}.call(this)" in content, (
                f"showcase/main.js 缺少 {factory}.call(this) — "
                "stateBase() 含 this.$persist(...)，bare call 時 this=undefined 會崩潰"
            )

    def test_main_js_has_window_showcase_state_bridge(self):
        """main.js 含 window.showcaseState 橋接"""
        content = self._read("main.js")
        assert "window.showcaseState" in content, (
            "showcase/main.js 缺少 window.showcaseState 橋接 — "
            "spec-54 §5 明確要求保留向後相容橋接"
        )

    def test_no_circular_state_factory_imports(self):
        """state 模組頂層 import 不含其他 state-*.js 的 factory 函式名稱"""
        import re
        factory_names = ["stateBase", "stateVideos", "stateActress", "stateLightbox"]
        for filename in ("state-videos.js", "state-actress.js", "state-lightbox.js"):
            content = self._read(filename)
            import_lines = [
                line for line in content.split("\n")
                if line.strip().startswith("import ")
            ]
            import_text = "\n".join(import_lines)
            for name in factory_names:
                assert name not in import_text, (
                    f"showcase/{filename} 的 import 語句含 {name} — "
                    "state 模組不可 import 其他 state factory，違反 spec-54 §9 D2"
                )

    def test_state_lightbox_imports_kill_timelines(self):
        """state-lightbox.js 從 state-base.js import _killLightboxTimelines"""
        content = self._read("state-lightbox.js")
        assert "_killLightboxTimelines" in content, (
            "state-lightbox.js 缺少 _killLightboxTimelines — "
            "此函式從 state-base.js import，閉包/全域存取均不符 ESM 規範"
        )

    def test_state_videos_no_actress_functions(self):
        """state-videos.js 不含 loadActresses / addFavoriteActress"""
        content = self._read("state-videos.js")
        assert "loadActresses" not in content, (
            "state-videos.js 含 loadActresses — 女優邏輯應在 state-actress.js"
        )
        assert "addFavoriteActress" not in content, (
            "state-videos.js 含 addFavoriteActress — 女優 CRUD 應在 state-actress.js"
        )

    def test_state_actress_no_lightbox_functions(self):
        """state-actress.js 不含 openLightbox / closeLightbox 定義"""
        import re
        content = self._read("state-actress.js")
        assert not re.search(r"^\s+openLightbox\s*\(", content, re.MULTILINE), (
            "state-actress.js 含 openLightbox 方法定義 — 應在 state-lightbox.js"
        )
        assert not re.search(r"^\s+closeLightbox\s*\(", content, re.MULTILINE), (
            "state-actress.js 含 closeLightbox 方法定義 — 應在 state-lightbox.js"
        )

    def test_no_gsap_at_module_top_level(self):
        """state 模組頂層不含 window.gsap 或 gsap 直接存取"""
        import re
        for filename in ("state-base.js", "state-videos.js", "state-actress.js", "state-lightbox.js", "main.js"):
            content = self._read(filename)
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                if line and not line.startswith(" ") and not line.startswith("\t"):
                    if "window.gsap" in line or (re.match(r"^gsap\b", line)):
                        assert False, (
                            f"showcase/{filename} L{i}: 模組頂層含 gsap 存取 — "
                            "spec-54 §9 D3：window.gsap 只在函式體內存取"
                        )

    def test_no_this_picker_params_in_state_modules(self):
        """state 模組不含 this._PICKER_PARAMS（應改為閉包直接存取）"""
        for filename in ("state-base.js", "state-videos.js", "state-actress.js", "state-lightbox.js"):
            content = self._read(filename)
            assert "this._PICKER_PARAMS" not in content, (
                f"showcase/{filename} 含 this._PICKER_PARAMS — "
                "應改為閉包直接存取 _PICKER_PARAMS（無需 this.）"
            )

    # ── T2b guards ────────────────────────────────────────────────────

    def test_showcase_html_has_pre_alpine_module(self):
        """showcase.html 含 {% block pre_alpine_module %} override（含 main.js module script）"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "showcase.html"
        content = html_path.read_text(encoding="utf-8")
        assert "pre_alpine_module" in content, (
            "showcase.html 缺少 {% block pre_alpine_module %} — "
            "main.js 必須放在此 slot 確保 alpine:init listener 在 Alpine CDN 之前掛上"
        )
        assert "showcase/main.js" in content, (
            "showcase.html 的 pre_alpine_module block 缺少 showcase/main.js module script"
        )

    def test_showcase_html_xdata_is_showcase(self):
        """showcase.html 的 x-data 值為 showcase（非 showcaseState）"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "showcase.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'x-data="showcase"' in content, (
            'showcase.html 缺少 x-data="showcase" — '
            "54b 要求 x-data 從 showcaseState 改為 showcase"
        )
        assert 'x-data="showcaseState"' not in content, (
            'showcase.html 仍含 x-data="showcaseState" — 舊名稱應已移除'
        )

    def test_showcase_html_no_core_js_script(self):
        """showcase.html 不含 core.js script tag"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "showcase.html"
        content = html_path.read_text(encoding="utf-8")
        assert "core.js" not in content, (
            "showcase.html 仍含 core.js script tag — 54b 完成後 core.js 應已刪除且 HTML 不再引用"
        )

    def test_showcase_html_still_has_animations_js(self):
        """showcase.html 仍含 animations.js script tag（B5：不動 animations.js）"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "showcase.html"
        content = html_path.read_text(encoding="utf-8")
        assert "animations.js" in content, (
            "showcase.html 缺少 animations.js script tag — "
            "54b 不動 animations.js，它應仍在 extra_js block 中"
        )

    def test_core_js_deleted(self):
        """web/static/js/pages/showcase/core.js 不存在"""
        core_js = self.BASE / "core.js"
        assert not core_js.exists(), (
            "showcase/core.js 仍然存在 — 54b 完成後應已刪除"
        )

    def test_no_showcase_state_xdata_in_templates(self):
        """所有 production templates 不含 x-data="showcaseState"（防殘留）"""
        templates_dir = Path(__file__).parents[2] / "web" / "templates"
        for tmpl in templates_dir.glob("**/*.html"):
            content = tmpl.read_text(encoding="utf-8")
            assert 'x-data="showcaseState"' not in content, (
                f"{tmpl.name} 仍含 x-data=\"showcaseState\" — 舊名稱應已全部移除"
            )

    def test_no_showcase_state_alpine_data_in_js(self):
        """web/static/js/pages/ 下所有 JS 不含 Alpine.data('showcaseState'（防殘留）"""
        pages_dir = Path(__file__).parents[2] / "web" / "static" / "js" / "pages"
        for js_file in pages_dir.glob("**/*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "Alpine.data('showcaseState'" not in content and \
                   'Alpine.data("showcaseState"' not in content, (
                f"{js_file.name} 含 Alpine.data('showcaseState' — 舊名稱應已全部移除"
            )


class TestSearchESMGuard:
    """54e 守衛 — Search ESM 遷移（window.SearchStateMixin_* → ESM export）"""

    BASE = Path(__file__).parents[2] / "web" / "static" / "js" / "pages" / "search"
    STATE = BASE / "state"

    def _read_state(self, filename):
        return (self.STATE / filename).read_text(encoding="utf-8")

    def _read_main(self):
        return (self.BASE / "main.js").read_text(encoding="utf-8")

    # ── state 模組 export 驗證（8 條）────────────────────────────────

    def test_state_base_exists_and_exports(self):
        """state/base.js 含 export function searchStateBase"""
        content = self._read_state("base.js")
        assert "export function searchStateBase" in content, (
            "state/base.js 缺少 export function searchStateBase — "
            "需將 window.SearchStateMixin_Base = function() 改為 export function searchStateBase()"
        )

    def test_state_persistence_exists_and_exports(self):
        """state/persistence.js 含 export function searchStatePersistence"""
        content = self._read_state("persistence.js")
        assert "export function searchStatePersistence" in content

    def test_state_search_flow_exists_and_exports(self):
        """state/search-flow.js 含 export function searchStateSearchFlow"""
        content = self._read_state("search-flow.js")
        assert "export function searchStateSearchFlow" in content

    def test_state_navigation_exists_and_exports(self):
        """state/navigation.js 含 export function searchStateNavigation"""
        content = self._read_state("navigation.js")
        assert "export function searchStateNavigation" in content

    def test_state_batch_exists_and_exports(self):
        """state/batch.js 含 export function searchStateBatch"""
        content = self._read_state("batch.js")
        assert "export function searchStateBatch" in content

    def test_state_result_card_exists_and_exports(self):
        """state/result-card.js 含 export function searchStateResultCard"""
        content = self._read_state("result-card.js")
        assert "export function searchStateResultCard" in content

    def test_state_file_list_exists_and_exports(self):
        """state/file-list.js 含 export function searchStateFileList"""
        content = self._read_state("file-list.js")
        assert "export function searchStateFileList" in content

    def test_state_grid_mode_exists_and_exports(self):
        """state/grid-mode.js 含 export function searchStateGridMode"""
        content = self._read_state("grid-mode.js")
        assert "export function searchStateGridMode" in content

    # ── main.js 驗證（4 條）─────────────────────────────────────────

    def test_main_js_exists_and_has_alpine_init(self):
        """search/main.js 存在且含 alpine:init"""
        assert (self.BASE / "main.js").exists(), "search/main.js 不存在"
        content = self._read_main()
        assert "alpine:init" in content

    def test_main_js_registers_search_page_name(self):
        """main.js 含 Alpine.data('searchPage',"""
        content = self._read_main()
        assert "Alpine.data('searchPage'" in content or 'Alpine.data("searchPage"' in content, (
            "main.js 缺少 Alpine.data('searchPage', — component 名稱必須保持 searchPage"
        )

    def test_main_js_uses_importmap_alias(self):
        """main.js import 使用 @/search/state/ alias"""
        content = self._read_main()
        assert "@/search/state/" in content, (
            "main.js 缺少 @/search/state/ import alias — 需使用 importmap 別名"
        )

    def test_main_js_uses_merge_state_not_spread(self):
        """main.js 使用 descriptor-preserving mergeState（含 Object.getOwnPropertyDescriptors 和 Object.defineProperties），且不含 plain spread"""
        content = self._read_main()
        assert "Object.getOwnPropertyDescriptors" in content, (
            "main.js 缺少 Object.getOwnPropertyDescriptors — "
            "必須使用 descriptor-preserving mergeState 保留 base.js L300 的 get isCloudSearchMode() getter"
        )
        assert "Object.defineProperties" in content, (
            "main.js 缺少 Object.defineProperties — mergeState 必須用此 API"
        )
        assert "...searchStateBase()" not in content, (
            "main.js 含 ...searchStateBase() plain spread — 會凍結 getter，用 mergeState() 取代"
        )

    # ── 防殘留驗證（4 條）────────────────────────────────────────────

    def test_no_window_mixin_in_state_modules(self):
        """8 個 state 模組均不含 window.SearchStateMixin_ 字串"""
        state_files = [
            "base.js", "persistence.js", "search-flow.js", "navigation.js",
            "batch.js", "result-card.js", "file-list.js", "grid-mode.js",
        ]
        for fname in state_files:
            content = self._read_state(fname)
            assert "window.SearchStateMixin_" not in content, (
                f"state/{fname} 仍含 window.SearchStateMixin_ — 舊全域名稱應已移除"
            )

    def test_no_circular_state_imports(self):
        """8 個 state 模組頂層 import 語句不互相引用"""
        state_files = [
            "base.js", "persistence.js", "search-flow.js", "navigation.js",
            "batch.js", "result-card.js", "file-list.js", "grid-mode.js",
        ]
        state_names = [f.replace(".js", "") for f in state_files]
        for fname in state_files:
            content = self._read_state(fname)
            import_lines = [
                line for line in content.splitlines()
                if line.strip().startswith("import ")
            ]
            for imp_line in import_lines:
                for other in state_names:
                    if other != fname.replace(".js", "") and f"state/{other}" in imp_line:
                        raise AssertionError(
                            f"state/{fname} 頂層 import 引用了 state/{other} — "
                            "state 模組不可互相 import（D2 規則），跨模組連接只在 main.js 做"
                        )

    def test_no_window_search_state_mixin_in_templates(self):
        """所有 templates 不含 window.SearchStateMixin_"""
        templates_dir = Path(__file__).parents[2] / "web" / "templates"
        for tmpl in templates_dir.glob("**/*.html"):
            content = tmpl.read_text(encoding="utf-8")
            assert "window.SearchStateMixin_" not in content, (
                f"{tmpl.name} 含 window.SearchStateMixin_ — 舊全域名稱應已全部移除"
            )

    def test_no_window_search_state_mixin_in_pages_js(self):
        """pages/search/ 下所有 JS 不含 window.SearchStateMixin_ 賦值"""
        search_dir = self.BASE
        for js_file in search_dir.glob("**/*.js"):
            content = js_file.read_text(encoding="utf-8")
            assert "window.SearchStateMixin_" not in content, (
                f"{js_file.name} 含 window.SearchStateMixin_ — 舊全域名稱應已全部移除"
            )

    # ── HTML 切換驗證（4 條）─────────────────────────────────────────

    def test_search_html_has_pre_alpine_module(self):
        """search.html 含 {% block pre_alpine_module %} 且含 search/main.js module script"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "search.html"
        content = html_path.read_text(encoding="utf-8")
        assert "pre_alpine_module" in content, (
            "search.html 缺少 {% block pre_alpine_module %} — "
            "main.js 必須放在此 slot 確保 alpine:init listener 在 Alpine CDN 之前掛上"
        )
        assert "search/main.js" in content, (
            "search.html 缺少 search/main.js module script"
        )

    def test_search_html_xdata_is_search_page(self):
        """search.html 仍含 x-data=\"searchPage\"（防誤改）"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "search.html"
        content = html_path.read_text(encoding="utf-8")
        assert 'x-data="searchPage"' in content, (
            'search.html 缺少 x-data="searchPage" — component 名稱必須保持 searchPage'
        )

    def test_search_html_no_old_state_script_tags(self):
        """search.html 不含 9 個舊 state script tag（逐一 assert）"""
        html_path = Path(__file__).parents[2] / "web" / "templates" / "search.html"
        content = html_path.read_text(encoding="utf-8")
        old_scripts = [
            "state/base.js",
            "state/persistence.js",
            "state/search-flow.js",
            "state/navigation.js",
            "state/batch.js",
            "state/result-card.js",
            "state/file-list.js",
            "state/grid-mode.js",
            "state/index.js",
        ]
        for script in old_scripts:
            assert script not in content, (
                f"search.html 仍含 {script} script tag — "
                "54e 完成後應改由 ESM main.js 載入，所有 state 模組 classic script tag 應已移除"
            )

    def test_search_state_index_js_deleted(self):
        """search/state/index.js 不存在"""
        index_js = self.STATE / "index.js"
        assert not index_js.exists(), (
            "search/state/index.js 仍然存在 — 54e 完成後 index.js 職責已由 main.js 接替，應已刪除"
        )


# === 從 tests/test_frontend_lint.py 搬移（T55e）===

# --- 以下為搬移自根目錄的 module-level helpers ---
from typing import List, Tuple

# 專案根目錄（T55e: 從根目錄 tests/test_frontend_lint.py 搬移）
PROJECT_ROOT = Path(__file__).parent.parent.parent  # /home/peace/OpenAver

# Vanilla inline event handlers (禁止)
# (?i) case-insensitive; (?<=\s) 前方需為空白，避免誤抓 data-onclick / x-onclick
VANILLA_HANDLER_PATTERN = r'(?i)(?<=\s)on(?:click|change|submit|keydown|input)\s*=\s*["\']'


def find_pattern_in_file(file_path: Path, regex: str,
                         exclude_lines: callable = None) -> List[Tuple[int, str]]:
    """
    在檔案中尋找符合 regex 的行

    Args:
        file_path: 檔案路徑
        regex: 正則表達式 pattern
        exclude_lines: 排除規則函數，接收 (line, line_number) 回傳 True 表示排除

    Returns:
        List of (line_number, line_content) tuples
    """
    violations = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if re.search(regex, line):
                    # 套用排除規則
                    if exclude_lines and exclude_lines(line, i):
                        continue
                    violations.append((i, line.rstrip()))
    except Exception as e:
        pytest.fail(f"無法讀取檔案 {file_path}: {e}")

    return violations


class TestNoVanillaHandlers:
    """確認所有 template 無 inline vanilla event handler"""

    def test_no_vanilla_handlers(self):
        """掃描所有 HTML template，確認無 onclick/onchange 等 inline handler"""
        templates_dir = PROJECT_ROOT / "web" / "templates"
        violations = []

        # 掃描主目錄 HTML 檔案（排除 design_system 子目錄）
        html_files = [f for f in templates_dir.glob("*.html")]

        for html_file in html_files:
            matches = find_pattern_in_file(
                html_file, VANILLA_HANDLER_PATTERN
            )
            for line_num, line_content in matches:
                violations.append(f"{html_file.name}:{line_num} — {line_content[:80]}")

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 vanilla inline handler 違規:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoHardcodedColors:
    """確認 CSS/HTML 無 hardcoded hex color"""

    def is_css_variable_definition(self, line: str, line_num: int) -> bool:
        """
        檢查是否為 CSS variable 定義行 (例外)

        CRITICAL FIX: 原本的 '--' in line and ':' in line 會誤判
        像 "background: linear-gradient(135deg, var(--accent) 0%, #007aff 100%)"
        這種只是「引用」CSS variable 的行（因為包含 var(--accent)）。

        必須檢查行是否「定義」CSS variable（以 --variable: 開頭）。
        """
        # 檢查是否為 CSS variable 定義（--variable-name: value;）
        return bool(re.match(r'\s*--[\w-]+\s*:', line))

    def is_svg_data_uri(self, line: str, line_num: int) -> bool:
        """檢查是否在 SVG data-uri 中 (例外)"""
        return 'data:image/svg' in line

    def is_intentional_color(self, line: str) -> bool:
        """檢查行內是否有 lint-ignore 或 VS Code 等已知例外註解"""
        # VS Code diff 配色、或任何帶 lint-ignore 標記的行
        return bool(re.search(r'/\*.*(?:VS Code|lint-ignore).*\*/', line))

    # CSS-scan method removed in T55b — superseded by stylelint `color-no-hex` rule.
    # HTML inline-scan method below stays as C-class deferral (T55d).

    def test_no_hardcoded_colors_in_html(self):
        """掃描 HTML inline styles，確認無 hardcoded hex color"""
        violations = []
        templates_dir = PROJECT_ROOT / "web" / "templates"
        html_files = [f for f in templates_dir.glob("*.html")]

        for html_file in html_files:
            # 跳過參考頁（design-system / motion-lab 是 demo 用途）
            if html_file.name in ("design-system.html", "motion_lab.html"):
                continue

            # 回參照確保同型引號閉合，避免 url('...') 巢狀引號漏判
            matches = find_pattern_in_file(
                html_file,
                r"""style\s*=\s*(["'])(?:(?!\1).)*#[0-9a-fA-F]{3,8}"""
            )

            for line_num, line_content in matches:
                violations.append(f"{html_file.name}:{line_num} — {line_content[:100]}")

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 hardcoded hex color 違規 (HTML inline):\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestSearchCssHardcoded:
    """Phase 51 T2.4 — search.css §1/§2/§3/§4 hardcoded 守衛

    確保 T2.1（color/rgba）/ T2.2（spacing 6px layout）修齊結果不被回退；
    新加違規會被擋下。allow-list 為 (line_num: reason) dict，新增例外
    必須提供 reason 字串說明（§3 角色色白名單 / §2 drop-shadow 例外 /
    var() fallback / §4 micro chip optical 之一）。

    T55b: blur / border-radius 兩支已由 stylelint 接管（無法表達 line-allowlist
    的 RGBA 與 6px layout 守衛保留 pytest）。
    """

    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    HARDCODED_RGBA_ALLOWLIST = {
        # T2.1 commit 41f2a5b 後狀態：
        90: "drop-shadow rgba 0.3 — §2 例外（drop-shadow 跟封面去背形狀，非矩形 box-shadow 無法用 --fluent-shadow-* token）",
        780: "var(--bg-card, rgba(0, 0, 0, 0.05)) fallback — defensive fallback，非硬編碼違規",
    }

    SIX_PX_ALLOWLIST = {
        # T2.2 commit 89d52b6 後狀態：
        235: "row inline btn optical 6px — T2.2 加 optical 註記（btn-sm 12px padding 對 row inline 太寬）",
        516: ".batch-progress-bar height: 6px — intrinsic dimension（非 §4 spacing）",
        571: "chip optical 6px — T2.2 加 optical 註記（對齊 showcase .lb-tag-add-btn）",
    }

    def _scan(self, regex: str, allowlist=None):
        violations = []
        text = self.SEARCH_CSS.read_text(encoding='utf-8')
        for i, line in enumerate(text.splitlines(), 1):
            # 跳過純註解行（CSS comment 不是實際 declaration，提及 6px / rgba 為文檔說明）
            stripped = line.lstrip()
            if stripped.startswith('/*') or stripped.startswith('*'):
                continue
            if re.search(regex, line):
                if allowlist and i in allowlist:
                    continue
                violations.append((i, line.rstrip()))
        return violations

    def test_no_hardcoded_rgba_in_search_css(self):
        """禁 search.css 出現 rgba(0,0,0,...) 硬編碼（須走 var(--overlay-*) 角色色 token）"""
        violations = self._scan(
            r'rgba\(\s*0\s*,\s*0\s*,\s*0\s*,',
            allowlist=self.HARDCODED_RGBA_ALLOWLIST,
        )
        assert not violations, (
            f"search.css 出現新 rgba(0,0,0,...) 硬編碼違規 ({len(violations)} 處)：\n"
            + "\n".join(f"  L{n}: {l[:100]}" for n, l in violations)
            + "\n\n請改用 var(--overlay-*) 角色色 token；如為 §2 drop-shadow 例外 / "
            + "var() fallback，請更新 HARDCODED_RGBA_ALLOWLIST + 說明理由。"
        )

    def test_no_hardcoded_six_px_layout_in_search_css(self):
        """禁 search.css 出現 6px layout 違規（padding/margin/gap/etc.）"""
        # `[:\s]6px(?:\s|;|$)` 限定 6px 出現在 property value 上下文，避免 16px/26px/0.6px 誤抓
        violations = self._scan(
            r'[:\s]6px(?:\s|;|$)',
            allowlist=self.SIX_PX_ALLOWLIST,
        )
        assert not violations, (
            f"search.css 出現新 6px layout 違規 ({len(violations)} 處)：\n"
            + "\n".join(f"  L{n}: {l[:100]}" for n, l in violations)
            + "\n\n請改 layout 8pt grid / micro 4px / 加 /* ... optical 6px ... */ 註記 + 更新 SIX_PX_ALLOWLIST。"
        )


class TestNoInlineStyleDisplay:
    """確認 template 不用 style='display:none' 搭配 x-show"""

    @staticmethod
    def _parse_elements(html_text: str) -> List[Tuple[int, str]]:
        """
        將 HTML 中每個開標籤（可跨行）提取為 (起始行號, 完整標籤文字) 清單。
        只處理 < ... > 範圍，不解析 CDATA / script 等。
        """
        elements = []
        # 容許屬性值內有 > (如 x-show="a > 0")：跳過引號區段再匹配 >
        tag_re = re.compile(r'<[a-zA-Z](?:[^>"\'`]|"[^"]*"|\'[^\']*\'|`[^`]*`)*>', re.DOTALL)
        # 預建行號對照表：offset → line number
        line_starts = [0]
        for i, ch in enumerate(html_text):
            if ch == '\n':
                line_starts.append(i + 1)

        def offset_to_line(offset: int) -> int:
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= offset:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1  # 1-based

        for m in tag_re.finditer(html_text):
            elements.append((offset_to_line(m.start()), m.group()))
        return elements

    def test_no_inline_style_display_with_x_show(self):
        """掃描所有 HTML，確認無 style display:none + x-show 重複（支援跨行、單/雙引號）"""
        # 回參照 \1 確保開閉引號一致，避免 url('...') 提前中斷
        display_none_re = re.compile(r"""style\s*=\s*(["'])(?:(?!\1).)*display:\s*none""")
        violations = []
        templates_dir = PROJECT_ROOT / "web" / "templates"
        html_files = list(templates_dir.rglob("*.html"))

        for html_file in html_files:
            try:
                html_text = html_file.read_text(encoding='utf-8')
            except Exception as e:
                pytest.fail(f"無法讀取 {html_file}: {e}")

            for line_num, tag_text in self._parse_elements(html_text):
                if 'x-show' in tag_text and display_none_re.search(tag_text):
                    preview = ' '.join(tag_text.split())[:100]
                    violations.append(
                        f"{html_file.relative_to(PROJECT_ROOT)}:{line_num} — {preview}"
                    )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 style='display:none' + x-show 重複:\n" +
            "\n".join(f"  - {v}" for v in violations) +
            "\n\n提示：應該移除 style='display:none'，改用 x-cloak 處理初始隱藏"
        )


class TestMotionInfra:
    """確認 GSAP motion 基礎設施完整"""

    def test_motion_js_files_contain(self):
        """motion-prefs.js 和 motion-adapter.js 存在且包含必要 API / 函數"""
        for js_file, expected_strings in [
            (
                PROJECT_ROOT / "web" / "static" / "js" / "components" / "motion-prefs.js",
                ['prefersReducedMotion', 'openaver:motion-pref-change', 'addListener'],
            ),
            (
                PROJECT_ROOT / "web" / "static" / "js" / "components" / "motion-adapter.js",
                ['createContext', 'playEnter', 'playLeave', 'playStagger', 'playModal', '_shouldAnimate'],
            ),
        ]:
            assert js_file.exists(), f"{js_file.name} 不存在: {js_file}"
            content = js_file.read_text(encoding='utf-8')
            for expected in expected_strings:
                assert expected in content, f"{js_file.name} missing: {expected!r}"

    def test_base_html_loads_gsap_and_adapters(self):
        """base.html 載入 GSAP CDN + motion-prefs + motion-adapter，且順序正確"""
        base_html = PROJECT_ROOT / "web" / "templates" / "base.html"
        assert base_html.exists(), f"base.html 不存在: {base_html}"

        content = base_html.read_text(encoding='utf-8')

        assert 'gsap.min.js' in content, "base.html 缺少 GSAP CDN script"
        assert 'motion-prefs.js' in content, "base.html 缺少 motion-prefs.js"
        assert 'motion-adapter.js' in content, "base.html 缺少 motion-adapter.js"
        assert 'alpinejs' in content, "base.html 缺少 Alpine.js"

        # 驗證載入順序：GSAP → motion-prefs → motion-adapter → Alpine
        idx_gsap = content.index('gsap.min.js')
        idx_prefs = content.index('motion-prefs.js')
        idx_adapter = content.index('motion-adapter.js')
        idx_alpine = content.index('alpinejs')

        assert idx_gsap < idx_prefs, \
            "載入順序錯誤：gsap.min.js 應在 motion-prefs.js 之前"
        assert idx_prefs < idx_adapter, \
            "載入順序錯誤：motion-prefs.js 應在 motion-adapter.js 之前"
        assert idx_adapter < idx_alpine, \
            "載入順序錯誤：motion-adapter.js 應在 alpinejs 之前"

    def test_no_direct_gsap_calls_in_pages(self):
        """頁面/元件 JS 不直接呼叫 GSAP API — 必須透過 motion adapter"""
        # 共同根目錄，所有 allowed_files 相對路徑以此為基準
        js_root = PROJECT_ROOT / "web" / "static" / "js"
        scan_dirs = [
            js_root / "pages",
            js_root / "components",
        ]
        # motion-adapter.js 本身是合法 GSAP 呼叫點
        # motion-lab.js 和 search/animations.js 因動態座標計算需求，直接呼叫 GSAP
        # 相對路徑以 js_root 為基準，包含 pages/ 或 components/ 前綴，避免跨目錄衝突
        allowed_files = {
            Path('components') / 'motion-adapter.js',   # components/motion-adapter.js
            Path('pages') / 'motion-lab.js',            # pages/motion-lab.js（T1 新增）
            Path('pages') / 'motion-lab-state.js',      # pages/motion-lab-state.js（39b-T1 Alpine state 含 GSAP 委派呼叫）
            Path('pages') / 'search' / 'animations.js', # pages/search/animations.js（T6 預先加入）
            Path('pages') / 'showcase' / 'animations.js', # pages/showcase/animations.js（B6 動畫模組）
            Path('pages') / 'motion-lab' / 'constellation-host.js',  # 56b-T3 thin host（從 pages/clip-lab/main.js 搬遷）
            Path('pages') / 'showcase' / 'state-similar.js',  # 57c-T4+T5 showcase similar mode host（per-host BreathingManager / GSAP context lifecycle，CD-57c-5）
        }
        violations = []

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for js_file in scan_dir.rglob("*.js"):
                rel = js_file.relative_to(js_root)  # 相對於 js_root，非 scan_dir
                if rel in allowed_files:
                    continue
                matches = find_pattern_in_file(
                    js_file,
                    r'(?:gsap\.(to|from|fromTo|set|timeline)\(|ScrollTrigger\.(create|batch)\()'
                )
                for line_num, line_content in matches:
                    violations.append(
                        f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                    )

        assert len(violations) == 0, (
            f"發現 {len(violations)} 個直接 GSAP 呼叫（應透過 OpenAver.motion.*）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


class TestNoDuplicateNativeDialog:
    """確認 duplicate modal 使用 Alpine state-driven pattern（不使用原生 showModal/close）"""

    def test_duplicate_modal_uses_modal_open_class(self):
        """search.html 的 duplicate modal 應使用 :class=\"{ 'modal-open': ... }\" pattern"""
        html_path = PROJECT_ROOT / "web/templates/search.html"
        content = html_path.read_text(encoding="utf-8")
        assert "duplicateModalOpen" in content, \
            "search.html 未找到 duplicateModalOpen — duplicate modal 應使用 Alpine state"


class TestTranslateAll:
    """確認 translateAll 前端基礎設施完整"""

    def test_translate_all_infra_contains(self):
        """search.html / base.js / batch.js 包含 translateAll 基礎設施（字串指紋守衛）"""
        search_html = PROJECT_ROOT / "web" / "templates" / "search.html"
        base_js = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "base.js"
        batch_js = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "batch.js"

        for path, expected_list in [
            (search_html, ["translateAll()", "listMode === 'search'"]),
            (base_js, ["translateState", "listMode === 'search'"]),
            (batch_js, ["async translateAll"]),
        ]:
            content = path.read_text(encoding='utf-8')
            for expected in expected_list:
                assert expected in content, f"{path.name} missing: {expected!r}"

        # 字串指紋守衛：殘留舊 fileList 判斷邏輯應已移除
        base_content = base_js.read_text(encoding='utf-8')
        assert "fileList.length === 0 && this.searchResults.length > 0" not in base_content, \
            "base.js should not contain: 'fileList.length === 0 && this.searchResults.length > 0'"


class TestJellyfinFrontend:
    """確認 Jellyfin 前端基礎設施完整"""

    def test_jellyfin_toggle_in_settings(self):
        """settings.html 包含 jellyfinMode 的 Alpine 綁定"""
        html_file = PROJECT_ROOT / "web" / "templates" / "settings.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'jellyfinMode' in content, \
            "settings.html 缺少 jellyfinMode 綁定（Jellyfin 圖片模式開關）"

    def test_jellyfin_update_in_scanner(self):
        """scanner/state-scan.js 包含 runJellyfinImageUpdate method"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
        content = js_file.read_text(encoding='utf-8')
        assert 'runJellyfinImageUpdate' in content, \
            "scanner/state-scan.js 缺少 runJellyfinImageUpdate（T6d Jellyfin 批次補齊）"

    def test_jellyfin_settings_hint_has_extrafanart(self):
        """settings.html Jellyfin 模式描述文字應包含 extrafanart/ 說明（T5b）
        i18n 後文字移至 locale JSON，檢查 zh_TW.json 或 HTML 中含 extrafanart"""
        html_file = PROJECT_ROOT / "web" / "templates" / "settings.html"
        html_content = html_file.read_text(encoding='utf-8')
        locale_file = PROJECT_ROOT / "locales" / "zh_TW.json"
        locale_content = locale_file.read_text(encoding='utf-8') if locale_file.exists() else ''
        assert 'extrafanart' in html_content or 'extrafanart' in locale_content, \
            "settings.html 或 locales/zh_TW.json Jellyfin 圖片模式描述缺少 extrafanart/ 說明（T5b）"


class TestOpenLocalGuard:
    """確認 openLocal() 綁定和 open_folder() API 的結構完整性（T5a / T5b）"""

    def test_open_local_in_search(self):
        """search.html 包含 openLocal( 綁定（Detail badge + Grid overlay 兩處）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "search.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'openLocal(' in content, \
            "search.html 缺少 openLocal( 綁定（T5b：Detail badge + Grid overlay）"

    def test_open_local_in_showcase(self):
        """showcase.html 包含 openLocal( 綁定（Grid overlay + Lightbox 兩處）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "showcase.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'openLocal(' in content, \
            "showcase.html 缺少 openLocal( 綁定（T5b：Grid overlay + Lightbox）"

    def test_open_local_method_exists(self):
        """result-card.js 和 showcase/state-videos.js 均包含 openLocal(path) method 定義"""
        result_card = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js"
        showcase_videos = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js"

        rc_content = result_card.read_text(encoding='utf-8')
        assert 'openLocal(path)' in rc_content, \
            "result-card.js 缺少 openLocal(path) method 定義（T5b）"

        sc_content = showcase_videos.read_text(encoding='utf-8')
        assert 'openLocal(path)' in sc_content, \
            "showcase/state-videos.js 缺少 openLocal(path) method 定義（T5b）"

    def test_open_folder_pywebview_api(self):
        """windows/pywebview_api.py 包含 def open_folder（T5a）"""
        api_file = PROJECT_ROOT / "windows" / "pywebview_api.py"
        content = api_file.read_text(encoding='utf-8')
        assert 'def open_folder' in content, \
            "pywebview_api.py 缺少 def open_folder（T5a）"

    def test_no_stale_copy_local_path(self):
        """search.html 不包含 copyLocalPath( 呼叫（確認舊 call 已清除）"""
        html_file = PROJECT_ROOT / "web" / "templates" / "search.html"
        content = html_file.read_text(encoding='utf-8')
        assert 'copyLocalPath(' not in content, \
            "search.html 仍包含 copyLocalPath( — T5b 應已將其改為 openLocal()"

    def test_open_local_checks_return_value(self):
        """openLocal() 的 .then() 必須檢查 open_folder 回傳值（不能無條件當成功）"""
        for js_file in [
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js",
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js",
        ]:
            content = js_file.read_text(encoding='utf-8')
            assert '.then(async (opened)' in content, \
                f"{js_file.name} openLocal() 的 .then() 缺少 opened 參數檢查"

    def test_open_local_cross_platform_path(self):
        """openLocal() 必須偵測 Windows drive letter 而非一律轉反斜線"""
        for js_file in [
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js",
            PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js",
        ]:
            content = js_file.read_text(encoding='utf-8')
            assert 'displayPath' in content, \
                f"{js_file.name} openLocal() 缺少跨平台路徑格式偵測（displayPath）"


class TestPathContract:
    """路徑契約守衛測試 — 確保路徑處理邏輯集中在 path_utils.py（T7.0）

    4 個守衛測試掃描 production code 禁止模式（T7a-T7e 已全部修正通過）。
    """

    # 掃描範圍：core/ web/ windows/（排除 path_utils.py 本身）
    _SCAN_DIRS = ['core', 'web', 'windows']
    _ALLOWED_FILE = 'path_utils.py'

    def _collect_py_files(self):
        """收集 core/、web/、windows/ 下所有 .py 檔（排除 path_utils.py）"""
        files = []
        for dir_name in self._SCAN_DIRS:
            scan_dir = PROJECT_ROOT / dir_name
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob('*.py'):
                if py_file.name == self._ALLOWED_FILE:
                    continue
                files.append(py_file)
        return files

    def test_no_raw_uri_strip(self):
        """掃描 Python 檔，確認無 path[8:] 或 path[len('file:///'):]  手動 URI strip"""
        # 符合 [8:] 或 [len('file:///'):]
        pattern = r'''\[8:\]|\[len\(['"]file:///['"]\):\]'''
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個手動 URI strip 違規（應改用 uri_to_fs_path()）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_manual_uri_construct(self):
        """掃描 Python 檔，確認無 f\"file:///{ 手動 URI 建構"""
        pattern = r'f["\']file:///'
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個手動 URI 建構違規（應改用 to_file_uri()）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_shadow_path_helpers(self):
        """掃描 Python 檔，確認無 def wsl_to_windows_path / def to_file_uri shadow helper"""
        pattern = r'def wsl_to_windows_path|def to_file_uri'
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 shadow path helper 定義（應集中在 path_utils.py）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_path_to_display_js_no_optional_slash(self):
        """pathToDisplay JS 工具不應使用 /? regex（會錯誤吸收路徑前導斜線）"""
        # 搜尋所有 path-utils / pathUtils JS 檔
        candidates = list(PROJECT_ROOT.rglob('path-utils.js')) + \
                     list(PROJECT_ROOT.rglob('pathUtils.js'))
        # 排除 venv/、node_modules/
        js_files = [
            f for f in candidates
            if 'venv' not in f.parts and 'node_modules' not in f.parts
        ]
        if not js_files:
            pytest.skip("pathToDisplay JS 工具尚未建立（T7d 前）")
        violations = []
        for js_file in js_files:
            matches = find_pattern_in_file(js_file, r'\/\?')
            for line_num, line_content in matches:
                violations.append(
                    f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"pathToDisplay 使用了 /? regex（會錯誤匹配路徑前導斜線）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestVideoPlaybackGuard:
    """確認影片播放走 API proxy，不直接開 file:/// URI（瀏覽器安全策略會靜默阻擋）"""

    def test_no_window_open_file_uri_in_js(self):
        """前端 JS 不應有 window.open 搭配 file:/// URI（應走 /api/gallery/player）"""
        js_dirs = [
            PROJECT_ROOT / "web" / "static" / "js" / "pages",
            PROJECT_ROOT / "web" / "static" / "js" / "components",
        ]
        # window.open(path  或 window.open(file:/// 或 location.href = path（且 path 含 file:）
        pattern = r'window\.open\s*\(\s*path\s*,'
        violations = []
        for js_dir in js_dirs:
            if not js_dir.exists():
                continue
            for js_file in js_dir.rglob("*.js"):
                matches = find_pattern_in_file(js_file, pattern)
                for line_num, line_content in matches:
                    violations.append(
                        f"{js_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                    )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 window.open(path, ...) 直接開啟路徑（瀏覽器會阻擋 file:/// URI）:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\n提示：瀏覽器模式應使用 /api/gallery/player?path= 代理播放"
        )

    def test_video_api_files_contain(self):
        """showcase/state-videos.js 和 scanner.py 包含必要 API proxy + 安全守衛字串"""
        for path, expected_list in [
            (
                PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js",
                ['/api/gallery/player'],
            ),
            (
                PROJECT_ROOT / "web" / "routers" / "scanner.py",
                # 66-T1: get_video async→def（移出 event loop，Starlette 自動 threadpool）；
                # video_player 維持 async。security 守衛字串不變。
                ['def get_video(', 'async def video_player(', 'os.path.normpath',
                 'get_proxy_extensions', 'is_path_under_dir'],
            ),
        ]:
            content = path.read_text(encoding='utf-8')
            for expected in expected_list:
                assert expected in content, f"{path.name} missing: {expected!r}"

    def test_no_hardcoded_video_extensions_in_modules(self):
        """gallery_scanner.py, scanner.py, pywebview_api.py must NOT contain hardcoded video extension sets
        (dict entries like '.mp4': 'video/mp4' are OK — those are MIME mappings, not extension sets)"""
        files_to_check = [
            PROJECT_ROOT / "core" / "gallery_scanner.py",
            PROJECT_ROOT / "web" / "routers" / "scanner.py",
            PROJECT_ROOT / "windows" / "pywebview_api.py",
        ]
        import re
        for file_path in files_to_check:
            content = file_path.read_text(encoding='utf-8')
            # Find set literals: = {'.mp4', '.avi', ...} (bare extension strings, no colon after)
            # This looks for lines with extension-only assignments
            # e.g., VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', ...}
            # But NOT: video_mime = {'.mp4': 'video/mp4', ...}
            set_pattern = re.compile(r"""=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}""", re.DOTALL)
            matches = set_pattern.findall(content)
            assert len(matches) == 0, \
                f"{file_path.name} still contains hardcoded video extension set — should import from core.video_extensions"


class TestHelpPage:
    """T4b 守衛 — Help 頁必要元素"""

    def test_help_html_contains(self):
        """help.html 含 helpPage / checkUpdate / hero-terminal / help.hero.ai_instruction；help.js script 無 defer"""
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        for expected in ['helpPage', 'checkUpdate', 'hero-terminal', 'help.hero.ai_instruction']:
            assert expected in html, f"help.html missing: {expected!r}"
        assert (PROJECT_ROOT / 'web/static/js/pages/help.js').exists(), \
            "help.js missing: file does not exist"
        matches = re.findall(r'<script[^>]*help\.js[^>]*>', html)
        assert len(matches) == 1, \
            f"help.html 應恰好有 1 個 help.js script tag，找到 {len(matches)} 個"
        assert 'defer' not in matches[0], \
            "help.js script tag 帶有 defer — Alpine 會在 helpPage() 定義前初始化"

    def test_help_js_contains(self):
        """help.js 含 copyCurlCommand / execCommand"""
        js = (PROJECT_ROOT / 'web/static/js/pages/help.js').read_text(encoding='utf-8')
        for expected in ['copyCurlCommand', 'execCommand']:
            assert expected in js, f"help.js missing: {expected!r}"


class TestScannerClearCache:
    """清除快取守衛 — scanner 頁面必要元素"""

    def test_scanner_clear_cache_js_contains(self):
        """scanner/state-scan.js 含 clearCache() + DELETE /api/gallery/cache"""
        js = (PROJECT_ROOT / 'web/static/js/pages/scanner/state-scan.js').read_text(encoding='utf-8')
        for expected in ['clearCache()', '/api/gallery/cache', 'DELETE']:
            assert expected in js, f"scanner/state-scan.js missing: {expected!r}"


class TestSearchCoreFacade:
    """T3.2 守衛 → T4 更新：SearchCore facade 已完全消除"""

    def test_search_core_facade_files_excludes(self):
        """bridge.js 已刪除；persistence.js 不含 coreState?."""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/state/bridge.js"
        assert not js_file.exists(), \
            "search/state/bridge.js should not exist: T4 Step 8 應已刪除此檔案"
        persistence = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
        content = persistence.read_text(encoding='utf-8')
        assert 'coreState?.' not in content, \
            "persistence.js should not contain: 'coreState?.'"

    def test_search_core_js_excludes(self):
        """core.js（若存在）不含 Alpine.$data / _legacyState / window.SearchCore = {"""
        js_file = PROJECT_ROOT / "web/static/js/pages/search/core.js"
        if not js_file.exists():
            return  # core.js 已刪除，通過
        content = js_file.read_text(encoding='utf-8')
        for forbidden in ['Alpine.$data', '_legacyState', 'window.SearchCore = {']:
            assert forbidden not in content, \
                f"search/core.js should not contain: {forbidden!r}"


class TestPageLifecycleGuard:
    """page-lifecycle.js 存在性守衛 — 確保 script tag 及三頁 __registerPage 呼叫不被移除"""

    def test_base_html_loads_page_lifecycle(self):
        """base.html 必須引用 page-lifecycle.js"""
        base_html = PROJECT_ROOT / "web" / "templates" / "base.html"
        content = base_html.read_text(encoding='utf-8')
        assert 'page-lifecycle.js' in content, \
            "base.html 缺少 page-lifecycle.js script tag — 刪除會導致三頁 __registerPage 呼叫靜默失敗"

    def test_settings_js_calls_register_page(self):
        """settings/state-config.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "settings/state-config.js 缺少 __registerPage 呼叫 — dirty-check lifecycle 會失效"

    def test_search_main_js_calls_register_page(self):
        """search/main.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "main.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "search/main.js 缺少 __registerPage 呼叫 — Search 離頁 save/cleanup 會失效"

    def test_showcase_core_calls_register_page(self):
        """showcase/state-base.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "showcase/state-base.js 缺少 __registerPage 呼叫 — Showcase lightbox cleanup lifecycle 會失效"

    def test_scanner_html_calls_register_page(self):
        """scanner/state-scan.js 必須呼叫 __registerPage"""
        js_file = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
        content = js_file.read_text(encoding='utf-8')
        assert '__registerPage' in content, \
            "scanner/state-scan.js 缺少 __registerPage 呼叫 — Scanner lifecycle 未接入統一機制"


class TestScannerLifecycleGuard:
    """T5.1 守衛 — Scanner 已接入 __registerPage，不再使用舊 shim"""

    SCANNER_HTML = PROJECT_ROOT / "web" / "templates" / "scanner.html"
    PAGE_LIFECYCLE_JS = PROJECT_ROOT / "web" / "static" / "js" / "components" / "page-lifecycle.js"

    def test_scanner_no_confirm_leaving_scanner(self):
        """scanner.html 不含 confirmLeavingScanner（舊 shim 已刪除）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert 'confirmLeavingScanner' not in content, \
            "scanner.html 仍含 confirmLeavingScanner — T5.1 應已刪除舊離頁 shim"

    def test_scanner_no_self_added_beforeunload(self):
        """scanner.html 不自掛 addEventListener('beforeunload'（由 page-lifecycle.js 統一管理）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert "addEventListener('beforeunload'" not in content, \
            "scanner.html 仍自掛 beforeunload listener — T5.1 應刪除，改由 onBeforeUnload hook 處理"

    def test_scanner_no_skip_before_unload(self):
        """scanner.html 不含 _skipBeforeUnload（隨舊 shim 一起刪除）"""
        content = self.SCANNER_HTML.read_text(encoding='utf-8')
        assert '_skipBeforeUnload' not in content, \
            "scanner.html 仍含 _skipBeforeUnload — T5.1 應已隨舊 shim 一起刪除"

    def test_page_lifecycle_no_confirm_leaving_scanner_shim(self):
        """page-lifecycle.js 不含 confirmLeavingScanner compatibility shim"""
        content = self.PAGE_LIFECYCLE_JS.read_text(encoding='utf-8')
        assert 'confirmLeavingScanner' not in content, \
            "page-lifecycle.js 仍含 confirmLeavingScanner shim — T5.1 Scanner 接入後應刪除"


class TestEventSourceTracking:
    """T4.1 守衛 — 所有 EventSource 建立都透過 _trackConnection 包裝"""

    def test_event_source_tracking_js_contains(self):
        """base.js / search-flow.js / file-list.js 含 T4.1 連線追蹤必要字串"""
        base = (PROJECT_ROOT / "web/static/js/pages/search/state/base.js").read_text(encoding='utf-8')
        assert '_activeConnections' in base, \
            "base.js missing: '_activeConnections'"
        sf = (PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js").read_text(encoding='utf-8')
        for expected in ['_trackConnection', '_untrackConnection', '_closeAllConnections',
                         '_trackConnection(new EventSource(', '_closeAllConnections()']:
            assert expected in sf, f"search-flow.js missing: {expected!r}"
        fl = (PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js").read_text(encoding='utf-8')
        assert '_trackConnection(' in fl, \
            "file-list.js missing: '_trackConnection('"

    def test_no_bare_new_event_source_in_search_state(self):
        """search/state/ 下所有 JS 的 new EventSource 都應在 _trackConnection 內"""
        state_dir = PROJECT_ROOT / "web/static/js/pages/search/state"
        violations = []
        for js_file in state_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8')
            for i, line in enumerate(content.splitlines(), 1):
                if 'new EventSource(' in line and '_trackConnection' not in line:
                    violations.append(f"{js_file.name}:{i} — {line.strip()[:80]}")
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個 bare new EventSource（未包在 _trackConnection 內）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestTimerTracking:
    """T4.2 守衛 — 所有 setTimeout 都透過 _timers registry 管理"""

    def test_timer_tracking_js_contains(self):
        """base/search-flow/result-card/persistence/file-list: _timers registry 必要字串"""
        base = (PROJECT_ROOT / "web/static/js/pages/search/state/base.js").read_text(encoding='utf-8')
        assert '_timers: {}' in base, "base.js missing: '_timers: {}'"
        sf = (PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js").read_text(encoding='utf-8')
        for expected in ['_setTimer(', '_clearAllTimers(', '_clearAllTimers()']:
            assert expected in sf, f"search-flow.js missing: {expected!r}"
        rc = (PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js").read_text(encoding='utf-8')
        assert "_setTimer('toast'" in rc, "result-card.js missing: \"_setTimer('toast'\""
        ps = (PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js").read_text(encoding='utf-8')
        assert "_setTimer('autosave'" in ps, "persistence.js missing: \"_setTimer('autosave'\""
        fl = (PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js").read_text(encoding='utf-8')
        assert "_setTimer('loadFavorite'" in fl, "file-list.js missing: \"_setTimer('loadFavorite'\""

    def test_timer_tracking_js_excludes(self):
        """base/result-card/persistence: 舊 _toastTimer / saveTimeout 已移除"""
        base = (PROJECT_ROOT / "web/static/js/pages/search/state/base.js").read_text(encoding='utf-8')
        assert '_toastTimer: null' not in base, \
            "base.js should not contain: '_toastTimer: null'"
        rc = (PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js").read_text(encoding='utf-8')
        assert '_toastTimer =' not in rc, \
            "result-card.js should not contain: '_toastTimer ='"
        ps = (PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js").read_text(encoding='utf-8')
        assert 'saveTimeout' not in ps, \
            "persistence.js should not contain: 'saveTimeout'"


class TestWindowGlobalCleanup:
    """T3.3 守衛 — bridge.js 不再設定多餘的 window.xxx 全域函數"""

    BRIDGE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/bridge.js"
    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    INIT_JS = PROJECT_ROOT / "web/static/js/pages/search/init.js"

    def test_window_global_cleanup_js_contains_and_excludes(self):
        """bridge/file-list/persistence/search-flow/init: window.SearchCore 全域函數已清除，this.xxx 直接呼叫已植入"""
        # bridge.js（T4 已刪除則通過）
        if self.BRIDGE_JS.exists():
            bc = self.BRIDGE_JS.read_text(encoding='utf-8')
            for forbidden in [
                'window.translateWithAI', 'window.startEditTitle', 'window.confirmEditTitle',
                'window.cancelEditTitle', 'window.startEditChineseTitle',
                'window.confirmEditChineseTitle', 'window.cancelEditChineseTitle',
                'window.showAddTagInput', 'window.confirmAddTag', 'window.cancelAddTag',
                'window.removeUserTag', 'window.SearchCore.initProgress',
                'window.SearchCore.updateLog', 'window.SearchCore.handleSearchStatus',
            ]:
                assert forbidden not in bc, \
                    f"bridge.js should not contain: {forbidden!r}"
        # file-list.js: direct this.xxx calls + no window.SearchCore calls
        fl = self.FILE_LIST_JS.read_text(encoding='utf-8')
        for expected in ['this.initProgress(', 'this.updateLog(', 'this.handleSearchStatus(']:
            assert expected in fl, f"file-list.js missing: {expected!r}"
        for forbidden in ['window.SearchCore.initProgress', 'window.SearchCore.updateLog',
                          'window.SearchCore.handleSearchStatus', 'window.SearchCore.updateClearButton']:
            assert forbidden not in fl, f"file-list.js should not contain: {forbidden!r}"
        # persistence / search-flow: no updateClearButton
        for js_file in [self.PERSISTENCE_JS, self.SEARCH_FLOW_JS]:
            content = js_file.read_text(encoding='utf-8')
            assert 'window.SearchCore.updateClearButton' not in content, \
                f"{js_file.name} should not contain: 'window.SearchCore.updateClearButton'"
        # init.js（T4 已刪除則通過）
        if self.INIT_JS.exists():
            ic = self.INIT_JS.read_text(encoding='utf-8')
            for forbidden in ['window.SearchCore.initProgress =', 'window.SearchCore.updateLog =',
                              'window.SearchCore.handleSearchStatus =']:
                assert forbidden not in ic, \
                    f"init.js should not contain: {forbidden!r}"


class TestFetchAbortController:
    """T4.3 守衛 — fetch 可取消化（AbortController per-key）（method folded）"""
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"
    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"

    def test_abort_controller_js_contains(self):
        """base/search-flow: _abortControllers state + abort methods"""
        base = self.BASE_JS.read_text(encoding='utf-8')
        assert '_abortControllers: {}' in base, "base.js missing: '_abortControllers: {}'"
        sf = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        for expected in ["_getAbortSignal(", "_abortAllFetches(", "_abortAllFetches()"]:
            assert expected in sf, f"search-flow.js missing: {expected!r}"

    def test_abort_signal_usage_js_contains(self):
        """navigation/batch/file-list: signal 傳遞 + AbortError 處理"""
        nav = self.NAVIGATION_JS.read_text(encoding='utf-8')
        for expected in ["_getAbortSignal('loadMore')", "AbortError"]:
            assert expected in nav, f"navigation.js missing: {expected!r}"
        batch = self.BATCH_JS.read_text(encoding='utf-8')
        for expected in ["_getAbortSignal('translateAll')", "AbortError"]:
            assert expected in batch, f"batch.js missing: {expected!r}"
        fl = self.FILE_LIST_JS.read_text(encoding='utf-8')
        for expected in ["_getAbortSignal('setFileList')", "_getAbortSignal('loadFavorite')"]:
            assert expected in fl, f"file-list.js missing: {expected!r}"
        assert fl.count('AbortError') >= 2, \
            "file-list.js missing: 'AbortError' × 2"

class TestStreamState:
    """T4 Frontend State + Skeleton Grid 靜態守衛測試

    確認 SSE stream state 的 contract 存在：
    - base.js 宣告 stream state 欄位
    - search-flow.js 處理三種 SSE 事件類型
    - search.html 包含 skeleton template 綁定
    - failed slot 使用 visibility 而非 x-show（C10 約束）
    - search.css 包含 skeleton 動畫樣式
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_base_js_core_stream_state(self):
        """base.js 宣告核心 stream state 欄位"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamSlots' in content, "缺少 streamSlots 宣告"
        assert 'streamComplete' in content, "缺少 streamComplete 宣告"
        assert 'isStreaming' in content, "缺少 isStreaming 宣告"

    def test_base_js_staging_buffer_state(self):
        """base.js 宣告 U2 staging buffer state 欄位"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamBuffer' in content, "缺少 streamBuffer 宣告"
        assert 'streamBurstTimer' in content, "缺少 streamBurstTimer 宣告"
        assert 'streamBurstedSlots' in content, "缺少 streamBurstedSlots 宣告"
        assert 'stagingVisible' in content, "缺少 stagingVisible 宣告"

    def test_base_js_staging_display_state(self):
        """base.js 宣告 U3 staging display state 欄位，並確保已移除 streamFilled"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert 'streamFilled' not in content, "仍含 streamFilled — 應已移除"
        assert 'stagingCover' in content, "缺少 stagingCover 宣告"
        assert 'stagingNumber' in content, "缺少 stagingNumber 宣告"
        assert 'stagingReceivedCount' in content, "缺少 stagingReceivedCount 宣告"

    def test_result_item_uses_stream_buffer(self):
        """result-item handler 推入 streamBuffer，不直接更新 searchResults（U2 batching 約束）；U3 新增 staging state 更新"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'streamBuffer' in content, \
            "search-flow.js 缺少 streamBuffer 引用 — U2 batching 邏輯"
        assert 'streamBurstTimer' in content, \
            "search-flow.js 缺少 streamBurstTimer 引用 — U2 時間窗口 timer"
        # U3: result-item handler 更新 staging state
        assert 'stagingCover' in content, \
            "search-flow.js 缺少 stagingCover 引用 — U3 result-item handler 更新 staging display state"
        assert 'stagingNumber' in content, \
            "search-flow.js 缺少 stagingNumber 引用 — U3 result-item handler 更新 staging display state"

    def test_search_flow_handles_seed_event(self):
        """search-flow.js 包含 seed、result-item、result-complete 三種 SSE 事件 handler"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert "data.type === 'seed'" in content, \
            "search-flow.js 缺少 data.type === 'seed' handler — T4 SSE protocol"
        assert "data.type === 'result-item'" in content, \
            "search-flow.js 缺少 data.type === 'result-item' handler — T4 SSE protocol"
        assert "data.type === 'result-complete'" in content, \
            "search-flow.js 缺少 data.type === 'result-complete' handler — T4 SSE protocol"

    def test_search_html_has_skeleton_template(self):
        """search.html 包含 :data-slot 屬性、_skeleton class 綁定、_failed 相關綁定"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert ':data-slot' in content, \
            "search.html 缺少 :data-slot 屬性綁定 — T4 skeleton grid slot 識別"
        assert '_skeleton' in content, \
            "search.html 缺少 _skeleton class 綁定 — T4 skeleton grid 視覺"
        assert '_failed' in content, \
            "search.html 缺少 _failed 相關綁定 — T4 failed slot 視覺"

    def test_failed_slot_uses_display_none(self):
        """failed slot 使用 display: none 隱藏（C29 約束：_failed slot 完全移除佈局空間）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'display: none' in content or 'display:none' in content, \
            ("search.html 缺少 display: none — "
             "C29 約束：_failed slot 必須用 display: none 完全隱藏")
        assert 'visibility: hidden' not in content and 'visibility:hidden' not in content, \
            ("search.html 仍包含 visibility: hidden — "
             "C29 約束：已改用 display: none，不應殘留 visibility: hidden")

    def test_search_css_has_skeleton_styles(self):
        """search.css 包含 .skeleton-cover class、.shimmer class、@keyframes shimmer"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '.skeleton-cover' in content, \
            "search.css 缺少 .skeleton-cover class — T4 skeleton overlay 樣式"
        assert '.shimmer' in content, \
            "search.css 缺少 .shimmer class — T4 shimmer 動畫樣式"
        assert '@keyframes shimmer' in content, \
            "search.css 缺少 @keyframes shimmer — T4 shimmer 動畫定義"

    def test_search_flow_has_stream_guard(self):
        """search-flow.js 的 result handler 包含 streamComplete guard（C12 約束）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'this.streamComplete' in content, \
            "search-flow.js 缺少 streamComplete guard — T4 防止漸進路徑 result 覆蓋 searchResults"


class TestAnimationHookup:
    """T5 Frontend Animation Hookup 靜態守衛

    確認 animations.js 載入順序、SearchAnimations window 物件、
    動畫觸發 wiring 合約存在。
    """

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_animations_js_exists(self):
        """search/animations.js 必須存在"""
        assert self.ANIMATIONS_JS.exists(), \
            "web/static/js/pages/search/animations.js 不存在 — T5 必須新建此檔案"

    def test_animations_js_exposes_window_object(self):
        """animations.js 暴露 window.SearchAnimations 物件"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'window.SearchAnimations' in content, \
            "animations.js 缺少 window.SearchAnimations — 必須掛 window 物件供 search-flow.js 呼叫"

    def test_animations_js_loaded_before_state_modules(self):
        """animations.js script tag 在 core.js 之前（search.html 載入順序）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        anim_pos = content.find('animations.js')
        core_pos = content.find('search/core.js')
        assert anim_pos != -1, \
            "search.html 缺少 animations.js script tag"
        assert core_pos != -1, \
            "search.html 缺少 search/core.js script tag（預期已存在）"
        assert anim_pos < core_pos, \
            ("animations.js 必須在 core.js 之前載入 — "
             "確保 window.SearchAnimations 在 SearchCore 執行前已掛上")

    def test_search_flow_has_animation_trigger_in_result_item(self):
        """search-flow.js 包含 SearchAnimations 引用；U3 後 playMiniBurst 在 _flushStreamBuffer 呼叫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "search-flow.js 缺少 SearchAnimations 引用 — playGridFadeIn 仍在 seed handler 使用"
        # U3: playMiniBurst 已接入 _flushStreamBuffer，hook point 註解已移除
        assert 'playMiniBurst' in content, \
            "search-flow.js 缺少 playMiniBurst 引用 — U3 _flushStreamBuffer 應呼叫 playMiniBurst"

    def test_staging_card_html_exists(self):
        """search.html 包含 staging-anchor overlay（.staging-card、stagingVisible + displayMode guard、stagingCover、stagingNumber、stagingReceivedCount）"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'staging-anchor' in content, \
            "search.html 缺少 staging-anchor class — U3 staging overlay HTML"
        assert 'staging-card' in content, \
            "search.html 缺少 staging-card class — U3 staging card HTML"
        assert 'stagingVisible' in content, \
            "search.html 缺少 stagingVisible 綁定 — U3 staging card 可見性控制"
        assert "displayMode === 'grid'" in content, \
            "search.html staging x-show 缺少 displayMode === 'grid' guard — 切 detail view 時不該顯示 staging"
        assert 'stagingCover' in content, \
            "search.html 缺少 stagingCover 綁定 — U3 staging card 封面圖"
        assert 'stagingNumber' in content, \
            "search.html 缺少 stagingNumber 綁定 — U3 staging card 番號"
        assert 'stagingReceivedCount' in content, \
            "search.html 缺少 stagingReceivedCount 綁定 — U3 staging card 計數 badge"

    def test_staging_card_css_exists(self):
        """search.css 包含 staging card CSS（.staging-anchor、.staging-counter-badge）"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '.staging-anchor' in content, \
            "search.css 缺少 .staging-anchor class — U3 staging overlay 容器樣式"
        assert '.staging-counter-badge' in content, \
            "search.css 缺少 .staging-counter-badge class — U3 計數 badge 樣式"

    def test_animations_js_has_play_mini_burst(self):
        """animations.js 包含 playMiniBurst 方法（U3 mini-burst 動畫）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playMiniBurst' in content, \
            "animations.js 缺少 playMiniBurst — U3 必須新增此方法（gsap.fromTo 偏移飛行）"

    def test_animations_js_has_staging_animations(self):
        """animations.js 包含 playStagingEntry、playStagingExit、playCoverSwap 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playStagingEntry' in content, \
            "animations.js 缺少 playStagingEntry — U3 staging card 進場 morph"
        assert 'playStagingExit' in content, \
            "animations.js 缺少 playStagingExit — U3 staging card 退場 morph + onComplete"
        assert 'playCoverSwap' in content, \
            "animations.js 缺少 playCoverSwap — U3 staging card 封面替換動畫"

    def test_flush_triggers_animation(self):
        """search-flow.js 的 _flushStreamBuffer 包含 playMiniBurst 引用（U3 接 mini-burst 動畫）"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert '_flushStreamBuffer' in content, \
            "search-flow.js 缺少 _flushStreamBuffer 方法 — U2/U3 batching 核心函數"
        assert 'playMiniBurst' in content, \
            "search-flow.js 缺少 playMiniBurst 呼叫 — U3 _flushStreamBuffer 必須觸發 mini-burst 動畫"

    def test_animations_js_has_reduced_motion_guard(self):
        """animations.js 檢查 prefersReducedMotion（Reduced Motion 降級）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'prefersReducedMotion' in content, \
            "animations.js 缺少 prefersReducedMotion 守衛 — Reduced Motion 時必須跳過動畫"

    # ===== U4: Detail Entry + Grid-Detail Ghost Transition Guards =====

    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"

    def test_animations_js_has_detail_entry(self):
        """animations.js 包含 playDetailEntry 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playDetailEntry' in content, \
            "animations.js 缺少 playDetailEntry — U4 detail entry 動畫（cover slide-in + info fade-in）"

    def test_animations_js_has_grid_to_detail(self):
        """animations.js 包含 playGridToDetail 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playGridToDetail' in content, \
            "animations.js 缺少 playGridToDetail — U4 Grid->Detail ghost 轉場動畫"

    def test_animations_js_has_detail_to_grid(self):
        """animations.js 包含 playDetailToGrid 方法"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playDetailToGrid' in content, \
            "animations.js 缺少 playDetailToGrid — U4 Detail->Grid ghost 飛回動畫"

    def test_grid_mode_switch_to_detail_has_animation(self):
        """grid-mode.js switchToDetail 接入 ghost transition"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "grid-mode.js 缺少 SearchAnimations 引用 — switchToDetail 應接入 ghost 轉場"
        assert 'getBoundingClientRect' in content, \
            "grid-mode.js 缺少 getBoundingClientRect — C17 step 1 capture rect"
        assert '$nextTick' in content, \
            "grid-mode.js 缺少 $nextTick — C17 step 3 animate after render"

    def test_grid_mode_toggle_has_animation(self):
        """grid-mode.js toggleDisplayMode 接入 ghost fly-back"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        assert 'playDetailToGrid' in content, \
            "grid-mode.js 缺少 playDetailToGrid — toggleDisplayMode Detail->Grid 應觸發 ghost 飛回"

    def test_search_flow_exact_result_has_detail_entry(self):
        """search-flow.js exact result 觸發 detail entry 動畫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert 'playDetailEntry' in content, \
            "search-flow.js 缺少 playDetailEntry — exact result 應觸發 detail entry 動畫"

    def test_animations_js_has_ghost_cleanup(self):
        """animations.js 包含 ghost 清除邏輯"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'data-search-ghost' in content, \
            "animations.js 缺少 data-search-ghost attribute — ghost 元素需可識別以便清除"
        assert 'remove()' in content or 'removeChild' in content, \
            "animations.js 缺少 ghost 清除呼叫 — ghost 元素必須在動畫完成後移除"

    # ===== U5: Detail Navigation Slide + Interrupt Guards =====

    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"

    def test_animations_js_has_slide_in(self):
        """animations.js 包含 playSlideIn 方法（U5 導航滑動動畫）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playSlideIn' in content, \
            "animations.js 缺少 playSlideIn — U5 detail 導航滑動動畫"

    def test_navigation_has_kill_tweens(self):
        """navigation.js 包含 killTweensOf（C18 interrupt 策略）"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert 'killTweensOf' in content, \
            "navigation.js 缺少 killTweensOf — C18 interrupt 策略需在導航時打斷舊動畫"

    def test_navigation_has_slide_animation(self):
        """navigation.js 接入 SearchAnimations slide 動畫"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        assert 'SearchAnimations' in content, \
            "navigation.js 缺少 SearchAnimations 引用 — navigate() 應接入 slide 動畫"
        assert 'playSlideIn' in content, \
            "navigation.js 缺少 playSlideIn 引用 — navigate() 應觸發 slide-in 動畫"

    # ===== U6: Integration + Cleanup Guards =====

    def test_no_css_fadein_keyframes(self):
        """search.css 不應包含 @keyframes fadeIn（已由 GSAP playDetailEntry 取代）"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert '@keyframes fadeIn' not in content, \
            "search.css 仍包含 @keyframes fadeIn — U6 應移除（GSAP playDetailEntry 已取代此 CSS 動畫）"

    def test_no_play_card_stream_in_in_search_animations(self):
        """animations.js 不應包含 playCardStreamIn（已由 playMiniBurst 取代）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert 'playCardStreamIn' not in content, \
            "animations.js 仍包含 playCardStreamIn — U3 已由 playMiniBurst 取代，不應存在"

    def test_all_animation_methods_consolidated(self):
        """animations.js 包含所有 9 個預期動畫方法（U3/U4/U5 合併驗證）"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        expected_methods = [
            'playMiniBurst',
            'playCoverSwap',
            'playStagingEntry',
            'playStagingExit',
            'playGridFadeIn',
            'playDetailEntry',
            'playGridToDetail',
            'playDetailToGrid',
            'playSlideIn',
        ]
        for method in expected_methods:
            assert method in content, \
                f"animations.js 缺少 {method} — 預期 9 個動畫方法全部存在"

    # ===== U7a: File Search Detail Entry Guard =====

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"

    def test_file_search_result_has_detail_entry(self):
        """U7a: file-list.js searchForFile() result triggers playDetailEntry"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "playDetailEntry" in content, (
            "file-list.js must call playDetailEntry for file search results (U7a)"
        )

    # ===== U7b: File Switch Cached Slide Guards =====

    def test_file_switch_cached_has_slide(self):
        """U7b: file-list.js switchToFile() cached path triggers playSlideIn"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "playSlideIn" in content, (
            "file-list.js must call playSlideIn for cached file switch (U7b)"
        )

    def test_file_switch_has_kill_tweens(self):
        """U7b: file-list.js switchToFile() cached path interrupts old animation"""
        content = self.FILE_LIST_JS.read_text(encoding="utf-8")
        assert "killTweensOf" in content, (
            "file-list.js must call killTweensOf for C18 interrupt in file switch (U7b)"
        )

    def test_play_slide_in_kills_child_tweens(self):
        """Codex review: playSlideIn must kill child element tweens (cover/info) not just container"""
        content = self.ANIMATIONS_JS.read_text(encoding="utf-8")
        # Find the playSlideIn function definition (not the comment reference)
        slide_in_start = content.find('playSlideIn: function')
        assert slide_in_start != -1, "playSlideIn function definition not found in animations.js"
        # Check that it references child selectors for kill
        slide_in_body = content[slide_in_start:slide_in_start + 800]
        assert 'av-card-full-cover' in slide_in_body, (
            "playSlideIn must kill .av-card-full-cover child tweens (Codex review fix)"
        )
        assert 'av-card-full-info' in slide_in_body, (
            "playSlideIn must kill .av-card-full-info child tweens (Codex review fix)"
        )


class TestCoverStateGuard:
    """U8a Cover State 集中管理守衛

    確認 base.js 有 _resetCoverState helper + state fields，
    search-flow.js 有 _clearTimer method。
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_base_has_reset_cover_state(self):
        """base.js 包含 _resetCoverState 定義"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert '_resetCoverState' in content, \
            "base.js 缺少 _resetCoverState — U8a 必須新增集中式 cover state reset helper"

    def test_reset_cover_state_increments_request_id(self):
        """base.js 的 _resetCoverState 包含 _coverRequestId++"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        # 確認 _resetCoverState 方法體內有 _coverRequestId++
        match = re.search(r'_resetCoverState\s*\(', content)
        assert match, "base.js 缺少 _resetCoverState 方法定義"
        method_body = content[match.start():match.start() + 500]
        assert '_coverRequestId++' in method_body, \
            "base.js _resetCoverState 缺少 _coverRequestId++ — 必須遞增 request ID"

    def test_reset_cover_state_calls_clear_timer(self):
        """base.js 的 _resetCoverState 包含 _clearTimer + coverRetry"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        match = re.search(r'_resetCoverState\s*\(', content)
        assert match, "base.js 缺少 _resetCoverState 方法定義"
        method_body = content[match.start():match.start() + 500]
        assert '_clearTimer' in method_body, \
            "base.js _resetCoverState 缺少 _clearTimer 呼叫 — 必須清除 coverRetry timer"
        assert 'coverRetry' in method_body, \
            "base.js _resetCoverState 缺少 coverRetry 參數 — _clearTimer 需指定 key"

    def test_search_flow_has_clear_timer_method(self):
        """search-flow.js 包含 _clearTimer method 定義"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        assert re.search(r'_clearTimer\s*\(\s*\w+\s*\)', content), \
            "search-flow.js 缺少 _clearTimer(key) 方法定義 — U8a 必須新增單一 timer 清除方法"

    def test_base_has_cover_request_id_field(self):
        """base.js 包含 _coverRequestId 初始值"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert re.search(r'_coverRequestId\s*:\s*0', content), \
            "base.js 缺少 _coverRequestId: 0 初始值 — U8a 必須新增 cover request ID 欄位"

    def test_base_has_cover_loaded_field(self):
        """base.js 包含 _coverLoaded 初始值"""
        content = self.BASE_JS.read_text(encoding='utf-8')
        assert re.search(r'_coverLoaded\s*:\s*false', content), \
            "base.js 缺少 _coverLoaded: false 初始值 — U8a 必須新增 cover loaded 欄位"

    # === U8b guard tests ===

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"
    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"

    def test_file_list_reset_cover_state_count(self):
        """file-list.js 包含至少 8 次 _resetCoverState 呼叫"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 8, (
            f"file-list.js 只有 {count} 次 _resetCoverState（需至少 8 次: "
            f"#4,#5,#6,#7,#8,#9,#10,#11）"
        )

    def test_navigation_reset_cover_state_count(self):
        """navigation.js 包含至少 2 次 _resetCoverState 呼叫"""
        content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 2, (
            f"navigation.js 只有 {count} 次 _resetCoverState（需至少 2 次: "
            f"#1 navigate, #15 loadMore）"
        )

    def test_search_flow_reset_cover_state_count(self):
        """search-flow.js 包含至少 4 次 _resetCoverState 呼叫"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 4, (
            f"search-flow.js 只有 {count} 次 _resetCoverState（需至少 4 次: "
            f"#12 doSearch init, #13 traditional result, #14 fallback result, fallbackSearch）"
        )

    def test_no_bare_cover_error_reset(self):
        """file-list/navigation/search-flow 中不應有裸 coverError = '' 純 reset 行"""
        files_to_check = [self.FILE_LIST_JS, self.NAVIGATION_JS, self.SEARCH_FLOW_JS]
        violations = []
        for fpath in files_to_check:
            content = fpath.read_text(encoding='utf-8')
            for i, line in enumerate(content.splitlines(), 1):
                # 匹配 coverError = '' 或 coverError = "" (純 reset，非 set error)
                if re.search(r"""coverError\s*=\s*['"](['"])\s*;""", line):
                    # 排除 _resetCoverState 方法定義本身
                    if '_resetCoverState' in line:
                        continue
                    violations.append(f"{fpath.name}:{i} — {line.strip()}")
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個裸 coverError = '' reset（應改用 _resetCoverState()）:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )

    def test_grid_mode_reset_cover_state(self):
        """grid-mode.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"grid-mode.js 缺少 _resetCoverState（需至少 1 次: #16 switchToDetail）"
        )

    def test_batch_reset_cover_state(self):
        """batch.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"batch.js 缺少 _resetCoverState（需至少 1 次: #17 scrapeAll）"
        )

    def test_persistence_reset_cover_state(self):
        """persistence.js 包含至少 1 次 _resetCoverState 呼叫"""
        content = self.PERSISTENCE_JS.read_text(encoding='utf-8')
        count = content.count('_resetCoverState')
        assert count >= 1, (
            f"persistence.js 缺少 _resetCoverState（需至少 1 次: #19 restoreState）"
        )

    # === U8c guard tests ===

    RESULT_CARD_JS = PROJECT_ROOT / "web/static/js/pages/search/state/result-card.js"

    def test_cover_error_has_get_attribute_guard(self):
        """result-card.js 的 handleCoverError 內含 getAttribute"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert 'getAttribute' in method_body, \
            "handleCoverError 缺少 getAttribute — Phase 1 stale guard 必須用 getAttribute('src') 比對"

    def test_cover_error_has_cover_url_comparison(self):
        """result-card.js 的 handleCoverError 內含 coverUrl"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert 'coverUrl' in method_body, \
            "handleCoverError 缺少 coverUrl — Phase 1 stale guard 必須與 coverUrl() 比對"

    def test_cover_error_has_request_id_guard(self):
        """result-card.js 的 handleCoverError 內含 _coverRequestId"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        assert '_coverRequestId' in method_body, \
            "handleCoverError 缺少 _coverRequestId — Phase 2 timer 競態守衛必須檢查 request ID"

    def test_cover_retry_uses_set_timer(self):
        """result-card.js 內含 _setTimer + coverRetry"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        assert '_setTimer' in content, \
            "result-card.js 缺少 _setTimer — cover retry 必須使用 _setTimer 而非 raw setTimeout"
        assert 'coverRetry' in content, \
            "result-card.js 缺少 coverRetry — _setTimer 必須使用 'coverRetry' key"

    # === U8d guard tests ===

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    SEARCH_CSS = PROJECT_ROOT / "web/static/css/pages/search.css"

    def test_load_handler_sets_cover_loaded(self):
        """search.html 的 @load handler 包含 _coverLoaded = true"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert '_coverLoaded = true' in content, \
            "search.html 缺少 _coverLoaded = true — U8d 必須在 cover img @load handler 設定 _coverLoaded"

    def test_shimmer_placeholder_in_html(self):
        """search.html 包含 cover-loading-placeholder"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        assert 'cover-loading-placeholder' in content, \
            "search.html 缺少 cover-loading-placeholder — U8d 必須新增 shimmer loading placeholder"

    def test_shimmer_placeholder_in_css(self):
        """search.css 包含 cover-loading-placeholder 樣式"""
        content = self.SEARCH_CSS.read_text(encoding='utf-8')
        assert 'cover-loading-placeholder' in content, \
            "search.css 缺少 cover-loading-placeholder — U8d 必須新增 shimmer placeholder 樣式"

    # === U8 Codex review fix guard tests ===

    UI_JS = PROJECT_ROOT / "web/static/js/pages/search/ui.js"

    def test_switch_source_reset_cover_state(self):
        """ui.js 的 switchSource 包含 _resetCoverState（#20 cover-changing path）"""
        content = self.UI_JS.read_text(encoding='utf-8')
        assert '_resetCoverState' in content, (
            "ui.js 缺少 _resetCoverState — switchSource 替換結果時必須重置 cover state（#20）"
        )

    def test_cover_error_guards_empty_cover_url(self):
        """result-card.js 的 handleCoverError 在 _coverRetried 之前有 coverUrl 空值 early return"""
        content = self.RESULT_CARD_JS.read_text(encoding='utf-8')
        match = re.search(r'handleCoverError\s*\(', content)
        assert match, "result-card.js 缺少 handleCoverError 方法定義"
        method_body = content[match.start():match.start() + 800]
        # coverUrl() 取值必須在 _coverRetried check 之前
        cover_url_pos = method_body.find('coverUrl')
        retried_pos = method_body.find('_coverRetried')
        assert cover_url_pos != -1, \
            "handleCoverError 缺少 coverUrl — 必須檢查空 coverUrl early return"
        assert retried_pos != -1, \
            "handleCoverError 缺少 _coverRetried"
        assert cover_url_pos < retried_pos, (
            "handleCoverError 的 coverUrl 檢查必須在 _coverRetried 之前 — "
            "空 coverUrl 時應直接 return，避免 stale @error 觸發錯誤的 retry"
        )


class TestSearchAllRaceGuard:
    """U10 guard: _searchFileBackground + searchAll 共享狀態競態保護"""

    FILE_LIST_JS = PROJECT_ROOT / "web/static/js/pages/search/state/file-list.js"
    BATCH_JS = PROJECT_ROOT / "web/static/js/pages/search/state/batch.js"

    def test_search_file_background_exists(self):
        """file-list.js 必須包含 _searchFileBackground 方法"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        assert '_searchFileBackground' in content, \
            "file-list.js 缺少 _searchFileBackground — U10a 必須新增背景搜尋方法"

    def test_search_file_background_no_shared_state_writes(self):
        """_searchFileBackground 不應讀寫共享 UI 狀態（只能操作 file 物件）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        # 負面斷言：不應碰共享 UI 狀態
        assert 'this.currentFileIndex' not in method_body, \
            "_searchFileBackground 不應寫入 this.currentFileIndex — 背景搜尋不碰共享狀態"
        assert 'this.currentIndex' not in method_body, \
            "_searchFileBackground 不應寫入 this.currentIndex — 背景搜尋不碰共享狀態"
        assert 'this.displayMode' not in method_body, \
            "_searchFileBackground 不應寫入 this.displayMode — 背景搜尋不碰共享狀態"
        assert 'window.SearchUI.showState' not in method_body, \
            "_searchFileBackground 不應呼叫 window.SearchUI.showState — 背景搜尋不碰 UI"

        # 特殊處理：排除 file.searchResults 誤判
        assert 'this.searchResults' not in method_body, \
            "_searchFileBackground 不應讀寫 this.searchResults — 背景搜尋只能操作 file.searchResults"

        # 正面斷言：應操作 file 物件
        assert 'file.searchResults' in method_body, \
            "_searchFileBackground 必須寫入 file.searchResults — 結果存在 file 物件上"
        assert 'file.searched' in method_body, \
            "_searchFileBackground 必須寫入 file.searched — 標記搜尋完成"

    def test_search_all_uses_background_search(self):
        """batch.js 的 searchAll 必須使用 _searchFileBackground"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        assert '_searchFileBackground' in content, \
            "batch.js 缺少 _searchFileBackground 呼叫 — U10b searchAll 必須改用背景搜尋"

    def test_search_all_no_direct_switch_to_file_in_promise_all(self):
        """searchAll 的 Promise.all(chunk.map 區塊內不應直接呼叫 switchToFile"""
        content = self.BATCH_JS.read_text(encoding='utf-8')
        match = re.search(r'Promise\.all\(chunk\.map', content)
        assert match, "batch.js 缺少 Promise.all(chunk.map — searchAll 結構異常"
        # 取到 })); 的區塊（約 500 字元）
        block = content[match.start():match.start() + 500]
        # 找到 })); 結束位置，截斷
        end_marker = block.find('}));')
        if end_marker != -1:
            block = block[:end_marker + 3]
        assert 'switchToFile' not in block, (
            "searchAll 的 Promise.all(chunk.map) 內不應直接呼叫 switchToFile — "
            "背景搜尋期間切換檔案會造成 UI 競態"
        )

    def test_search_file_background_no_ui_side_effects(self):
        """_searchFileBackground 不應有 UI 副作用（switchToFile / showToast / alert）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        assert 'switchToFile(' not in method_body, \
            "_searchFileBackground 不應呼叫 switchToFile — 背景搜尋不切換 UI"
        assert 'showToast(' not in method_body, \
            "_searchFileBackground 不應呼叫 showToast — 背景搜尋不顯示 toast"
        assert 'alert(' not in method_body, \
            "_searchFileBackground 不應呼叫 alert — 背景搜尋不彈出對話框"

    def test_search_file_background_has_close_wrapper(self):
        """_searchFileBackground 必須有 close-wrapper（確保 forced-close 時 Promise settle）"""
        content = self.FILE_LIST_JS.read_text(encoding='utf-8')
        match = re.search(r'_searchFileBackground\s*\(', content)
        assert match, "file-list.js 缺少 _searchFileBackground 方法定義"
        method_body = content[match.start():match.start() + 2000]

        assert 'settle' in method_body, \
            "_searchFileBackground 缺少 settle 函數 — 必須包裝 close 確保 Promise 可 resolve"
        assert 'originalClose' in method_body, \
            "_searchFileBackground 缺少 originalClose — 必須保存原始 close 再覆寫"


class TestFailedSlotC30Guard:
    """C30 guard: _failed slot 必須從導航、計數、lightbox 中排除

    確認各 JS 方法在計算 navigation、indicator、file count 時
    正確排除 _failed slot，避免用戶看到空白結果或導航到失敗項目。
    """

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    NAVIGATION_JS = PROJECT_ROOT / "web/static/js/pages/search/state/navigation.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"

    def test_failed_slot_method_bodies_contain_failed(self):
        """navigate/prevLightboxVideo/nextLightboxVideo/navIndicatorText/canGoPrev/canGoNext/showNavigation/fileCountText 方法體含 _failed (C30)"""
        nav_content = self.NAVIGATION_JS.read_text(encoding='utf-8')
        match = re.search(r'navigate\s*\(', nav_content)
        assert match, "navigation.js 缺少 navigate() 方法"
        assert '_failed' in nav_content[match.start():match.start() + 500], \
            "navigation.js navigate() missing: '_failed' skip 邏輯 (C30)"

        gm_content = self.GRID_MODE_JS.read_text(encoding='utf-8')
        for method_name in ['prevLightboxVideo', 'nextLightboxVideo']:
            m = re.search(rf'{method_name}\s*\(', gm_content)
            assert m, f"grid-mode.js 缺少 {method_name}() 方法"
            assert '_failed' in gm_content[m.start():m.start() + 800], \
                f"grid-mode.js {method_name}() missing: '_failed' skip 邏輯 (C30)"

        base_content = self.BASE_JS.read_text(encoding='utf-8')
        for method_name, window in [
            ('navIndicatorText', 500), ('canGoPrev', 300), ('canGoNext', 300),
            ('showNavigation', 300), ('fileCountText', 500),
        ]:
            m = re.search(rf'{method_name}\s*\(', base_content)
            assert m, f"base.js 缺少 {method_name}() 方法"
            assert '_failed' in base_content[m.start():m.start() + window], \
                f"base.js {method_name}() missing: '_failed' 排除邏輯 (C30)"

        search_html = self.SEARCH_HTML.read_text(encoding='utf-8')
        for expected in ['hasVisiblePrev()', 'hasVisibleNext()']:
            assert expected in search_html, f"search.html missing: {expected!r}"

    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_repoint_is_conditional(self):
        """result-complete 的 currentIndex repoint 必須是條件式的：只在當前指向 _failed 時才 repoint (Codex review)"""
        content = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        idx = content.find('firstValid')
        assert idx != -1, "search-flow.js 缺少 firstValid repoint 邏輯"
        repoint_context = content[max(0, idx - 200):idx + 200]
        assert 'currentResult' in repoint_context or 'this.searchResults[this.currentIndex]' in repoint_context, \
            "repoint 必須先檢查當前 currentIndex 是否指向 _failed item，不可無條件覆蓋 (Codex review)"


class TestGridSettlePulse:
    """A4 守衛 — Grid Settle Pulse 落地

    確認 animations.js 暴露 playGridSettle 方法、search-flow.js 的
    onExitComplete 呼叫 playGridSettle、CustomEase "settle" 曲線已註冊、
    以及 C4/C6 約束遵守。
    """

    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_grid_settle_pulse_animations_js_contains(self):
        """animations.js 含 playGridSettle + CustomEase.create("settle")"""
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        for expected in ['playGridSettle', 'CustomEase.create("settle"']:
            assert expected in content, f"animations.js missing: {expected!r}"

    def test_grid_settle_pulse_method_bodies(self):
        """search-flow._triggerStagingExit 含 playGridSettle；playGridSettle 方法體含 killTweensOf、不含 rotation"""
        sf = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        match = re.search(r'_triggerStagingExit\s*\(\s*\)\s*\{', sf)
        assert match, "search-flow.js 缺少 _triggerStagingExit 方法定義"
        assert 'playGridSettle' in sf[match.start():match.start() + 1000], \
            "search-flow.js _triggerStagingExit missing: 'playGridSettle'"

        anim = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        m = re.search(r'playGridSettle:\s*function', anim)
        assert m, "animations.js 缺少 playGridSettle 方法定義"
        body = anim[m.start():m.start() + 3000]
        assert 'killTweensOf' in body, "animations.js playGridSettle missing: 'killTweensOf'"
        code_only = '\n'.join(
            l for l in body.split('\n') if l.strip() and not l.strip().startswith('//')
        )
        assert 'rotation' not in code_only, \
            "animations.js playGridSettle should not contain: 'rotation' (C6)"


class TestHeroImageErrorGuard:
    """A6-1 Hero Card / Lightbox 圖片錯誤狀態管理守衛

    確認 Hero Card 和 Lightbox 的 @error handler 不直接修改 DOM，
    改用 Alpine state 管理錯誤狀態。
    """

    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"

    def test_hero_image_error_js_contains(self):
        """base.js 含 _heroCardImageError / _heroLightboxImageError；search-flow.js doSearch 重置兩者"""
        base = self.BASE_JS.read_text(encoding='utf-8')
        for expected in ['_heroCardImageError', '_heroLightboxImageError']:
            assert expected in base, f"base.js missing: {expected!r}"
        sf = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        m = re.search(r'async\s+doSearch', sf)
        assert m, "search-flow.js 缺少 doSearch 方法定義"
        body = sf[m.start():m.start() + 2000]
        for expected in ['_heroCardImageError', '_heroLightboxImageError']:
            assert expected in body and '= false' in body, \
                f"search-flow.js doSearch missing: '{expected} = false' reset"

    def test_hero_card_error_handler_excludes(self):
        """search.html hero-card @error 不含 target.src / .src = / onerror"""
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        match = re.search(r'class="[^"]*hero-card[^"]*"', content)
        assert match, "search.html 缺少 hero-card class 區塊"
        hero_block = content[match.start():match.start() + 1200]
        error_match = re.search(r'@error="([^"]*)"', hero_block)
        assert error_match, "hero-card 區塊缺少 @error handler"
        error_value = error_match.group(1)
        for forbidden in ['target.src', '.src =', 'onerror']:
            assert forbidden not in error_value, \
                f"hero-card @error should not contain: {forbidden!r} (A6-1)"


class TestLightboxModeNormalization:
    """A6-2 Lightbox 模式正規化 + restoreState 防護守衛

    確認 restoreState 後 lightbox 狀態被正規化，
    以及 openActressLightbox 有 actressProfile 存在性 guard。
    """

    PERSISTENCE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/persistence.js"
    GRID_MODE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/grid-mode.js"

    def test_lightbox_mode_normalization_contains(self):
        """persistence.js restoreState 重置 lightboxOpen+lightboxIndex；grid-mode.js openActressLightbox 含 actressProfile guard"""
        ps = self.PERSISTENCE_JS.read_text(encoding='utf-8')
        m = re.search(r'restoreState\s*\(\s*\)', ps)
        assert m, "persistence.js 缺少 restoreState 方法定義"
        body = ps[m.start():m.start() + 3000]
        assert 'lightboxOpen' in body and '= false' in body, \
            "persistence.js restoreState missing: 'lightboxOpen = false' (A6-2)"
        assert 'actressProfile' in body and 'lightboxIndex' in body, \
            "persistence.js restoreState missing: actressProfile + lightboxIndex 處理 (A6-2)"
        gm = self.GRID_MODE_JS.read_text(encoding='utf-8')
        m2 = re.search(r'openActressLightbox\s*\(\s*\)', gm)
        assert m2, "grid-mode.js 缺少 openActressLightbox 方法定義"
        head = gm[m2.start():m2.start() + 300]
        assert re.search(r'if\s*\(\s*!this\.actressProfile\s*\)\s*return', head), \
            "grid-mode.js openActressLightbox missing: actressProfile guard (A6-2)"


class TestHeroSlotReservation:
    """A7-Prod 守衛 — Hero Slot 一律預留落地

    確認 seed handler 設定 _heroSlotReserved、search.html Hero Card
    x-show 包含 _heroSlotReserved、animations.js 暴露 playHeroRemove、
    result-complete 不拆 placeholder、result handler 統一處理 _heroSlotReserved。
    """

    BASE_JS = PROJECT_ROOT / "web/static/js/pages/search/state/base.js"
    SEARCH_FLOW_JS = PROJECT_ROOT / "web/static/js/pages/search/state/search-flow.js"
    SEARCH_HTML = PROJECT_ROOT / "web/templates/search.html"
    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/search/animations.js"

    def test_hero_slot_reservation_js_contains(self):
        """animations.js playHeroRemove；search.html hero-card 含 _heroSlotReserved；search-flow.js seed/fallback/result-complete 邏輯"""
        anim = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        assert re.search(r'playHeroRemove\s*:', anim), \
            "animations.js missing: 'playHeroRemove' method"
        html = self.SEARCH_HTML.read_text(encoding='utf-8')
        m = re.search(r'class="[^"]*hero-card[^"]*"', html)
        assert m, "search.html 缺少 hero-card class 區塊"
        assert '_heroSlotReserved' in html[max(0, m.start() - 200):m.start() + 200], \
            "search.html hero-card missing: '_heroSlotReserved' (A7-Prod)"
        sf = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        seed_m = re.search(r"data\.type\s*===?\s*['\"]seed['\"]", sf)
        assert seed_m, "search-flow.js 缺少 seed handler"
        assert '_heroSlotReserved' in sf[seed_m.start():seed_m.start() + 1000] and \
               '= true' in sf[seed_m.start():seed_m.start() + 1000], \
            "search-flow.js seed handler missing: '_heroSlotReserved = true'"
        rc_m = re.search(r"data\.type\s*===?\s*['\"]result-complete['\"]", sf)
        assert rc_m, "search-flow.js 缺少 result-complete handler"
        assert '_heroSlotReserved = false' not in sf[rc_m.start():rc_m.start() + 1500], \
            "search-flow.js result-complete should not contain: '_heroSlotReserved = false'"
        fb_m = re.search(r'async\s+fallbackSearch\s*\(', sf)
        assert fb_m, "search-flow.js 缺少 fallbackSearch 方法"
        fb_body = sf[fb_m.start():fb_m.start() + 3000]
        for expected in ['_heroSlotReserved', 'playHeroRemove']:
            assert expected in fb_body, f"search-flow.js fallbackSearch missing: {expected!r}"

    def test_result_event_hero_slot_handling(self):
        """search-flow.js result 事件三路徑（正常stream / allFailed+fallback / 全失敗無fallback）均處理 _heroSlotReserved"""
        sf = self.SEARCH_FLOW_JS.read_text(encoding='utf-8')
        for marker, window, expected in [
            ('正常 stream 完成', 2000, ['_heroSlotReserved', 'playHeroRemove']),
            ('Issue 1: Fallback', 2000, ['_heroSlotReserved']),
            ('全部失敗且無 fallback', 500, ['_heroSlotReserved']),
        ]:
            assert marker in sf, f"search-flow.js missing: comment marker {marker!r}"
            block = sf[sf.index(marker):sf.index(marker) + window]
            for expected_str in expected:
                assert expected_str in block, \
                    f"search-flow.js '{marker}' block missing: {expected_str!r}"


class TestShowcaseAnimationsGuard:
    """B5-B15/T20 守衛 — Showcase GSAP 基礎設施落地（method folded）"""

    ANIMATIONS_JS = PROJECT_ROOT / "web/static/js/pages/showcase/animations.js"
    SHOWCASE_HTML = PROJECT_ROOT / "web/templates/showcase.html"

    def _read_core_js(self):
        """合併讀取動畫相關的 ESM 模組（B6/B7/B8/B9/B13/B14/B15 守衛範圍）。"""
        return (
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-base.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-videos.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-lightbox.js").read_text(encoding='utf-8')
        )

    def test_animations_js_contains(self):
        """animations.js 存在且包含所有必要字串；theme.css 含 flip-guard 規則"""
        assert self.ANIMATIONS_JS.exists(), \
            f"animations.js missing: {self.ANIMATIONS_JS!r}"
        content = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        for expected in [
            # B5: IIFE + strict mode + global object
            "window.ShowcaseAnimations",
            "prefersReducedMotion",
            # B5: method stubs
            "playEntry", "playFlipReorder", "playFlipFilter",
            "captureFlipState", "capturePositions",
            "playModeCrossfade",
            # B5: plugin registration
            "registerPlugin(Flip)",
            "showcaseSettle",
            # B6: playEntry implementation
            "gsap.killTweensOf",
            "getBoundingClientRect",
            "gsap.set",
            # B7: captureFlipState + capturePositions
            "Flip.getState",
            ".av-card-preview",
            "data-flip-id",
            # B8: playFlipFilter
            "Flip.from",
            "onEnter",
            "onLeave",
            "clearProps",
            # B8: playFlipFilter returns tweens
            "return gsap.fromTo",
            "return gsap.to",
            # B12: playFlipReorder manual fromTo
            ".fromTo",
            # T20: killLightboxAnimations
            "killLightboxAnimations",
            "getById('showcaseLightboxOpen')",
            "getById('showcaseLightboxSwitch')",
            "typeof gsap",
        ]:
            assert expected in content, \
                f"animations.js missing: {expected!r}"
        # B10: playModeCrossfade not placeholder
        assert ("gsap.fromTo" in content or "tl.fromTo" in content), \
            "animations.js missing: playModeCrossfade fromTo call"
        # B5: strict mode (single or double quote variant)
        assert ("'use strict'" in content or '"\'use strict\""' in content), \
            "animations.js missing: \'use strict\' declaration"
        # B15: theme.css flip-guard rule
        theme_css = (PROJECT_ROOT / "web/static/css/theme.css").read_text(encoding='utf-8')
        for expected in ["flip-guard", "transform: none"]:
            assert expected in theme_css, \
                f"theme.css missing: {expected!r}"

    def test_showcase_html_contains(self):
        """showcase.html 包含 animations.js script tag + data-flip-id；不重複載入 Flip.min.js"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        for expected in ["animations.js", "data-flip-id"]:
            assert expected in content, \
                f"showcase.html missing: {expected!r}"
        assert "Flip.min.js" not in content, \
            "showcase.html should not contain: 'Flip.min.js'"

    def test_core_js_contains(self):
        """core.js (state-base/videos/lightbox) 包含所有動畫 method 及 guard 字串"""
        content = self._read_core_js()
        for expected in [
            # B6: playEntry call
            "playEntry",
            "ShowcaseAnimations",
            # B8: _animateFilter
            "_animateFilter",
            # B8: playFlipFilter call
            "playFlipFilter",
            # B9: _animatePageChange
            "_animatePageChange",
            "scrollTo(0, 0)",
            # B10: playModeCrossfade
            "playModeCrossfade",
            "ShowcaseAnimations?.playModeCrossfade?.(",
            # B12: capturePositions + playFlipReorder in sort helper
            "capturePositions",
            "playFlipReorder",
            # B12/B13: flip-guard management
            "flip-guard",
            # B13: generation token guards
            "_animGeneration",
            # B13: _sortWithFlip method
            "_sortWithFlip",
            # B15: captureFlipState in _animateFilter
            "captureFlipState",
            # B13: page change uses playEntry
            "playEntry",
            # B7: savedPage or equivalent in _sortWithFlip
            "updatePagination",
        ]:
            assert expected in content, \
                f"showcase/core.js missing: {expected!r}"
        # B7: page preservation in _sortWithFlip
        assert ("savedPage" in content or "saved_page" in content or "savePage" in content), \
            "showcase/core.js _sortWithFlip missing page preservation (savedPage/saved_page/savePage)"

    def test_core_js_prev_next_page_call_animate_page_change(self):
        """B9: core.js prevPage/nextPage 呼叫 _animatePageChange"""
        content = self._read_core_js()
        lines = content.split('\n')
        for method_name in ['prevPage', 'nextPage']:
            in_method = False
            method_lines = []
            brace_count = 0
            for line in lines:
                stripped = line.strip()
                if not in_method and method_name in stripped and '{' in stripped and stripped.endswith('{'):
                    in_method = True
                    brace_count = 0
                if in_method:
                    method_lines.append(line)
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0 and len(method_lines) > 1:
                        break
            method_body = '\n'.join(method_lines)
            assert '_animatePageChange' in method_body, (
                f"showcase/core.js {method_name} missing: '_animatePageChange'"
            )

    def test_core_js_no_direct_gsap_getById(self):
        """T20: core.js 不得在 _killLightboxTimelines 之外直接呼叫 gsap.getById"""
        import re
        content = self._read_core_js()
        func_start = content.find('function _killLightboxTimelines(')
        if func_start != -1:
            brace_start = content.index('{', func_start)
            depth = 0
            pos = brace_start
            while pos < len(content):
                if content[pos] == '{':
                    depth += 1
                elif content[pos] == '}':
                    depth -= 1
                    if depth == 0:
                        func_end = pos + 1
                        break
                pos += 1
            else:
                func_end = len(content)
            stripped = content[:func_start] + content[func_end:]
        else:
            stripped = content
        assert 'gsap.getById(' not in stripped, (
            "showcase/core.js 在 _killLightboxTimelines 之外仍有直接 gsap.getById( 呼叫 — "
            "T20 規定只有 _killLightboxTimelines fallback 可直接使用 gsap.getById"
        )

class TestMotionLabShowcase:
    """B11 守衛 — Motion Lab Showcase demo 完整性

    確認 Motion Lab 頁面包含 Showcase tab 及所有 demo 方法，
    涵蓋 B1-B4 在 Motion Lab 新增的功能。
    """

    MOTION_LAB_HTML = PROJECT_ROOT / "web/templates/motion_lab.html"
    MOTION_LAB_JS = PROJECT_ROOT / "web/static/js/pages/motion-lab.js"

    def test_motion_lab_html_contains(self):
        """motion_lab.html 含 showcase tab + Alpine 切換邏輯"""
        content = self.MOTION_LAB_HTML.read_text(encoding='utf-8')
        for expected in ["showcase", "tab === 'showcase'"]:
            assert expected in content, f"motion_lab.html missing: {expected!r}"

    def test_motion_lab_js_contains(self):
        """motion-lab.js 含 B1-B4 四個 Showcase demo 方法"""
        content = self.MOTION_LAB_JS.read_text(encoding='utf-8')
        for expected in ['playShowcaseEntry', 'playFlipReorder', 'playFlipFilter', 'playPageTransition']:
            assert expected in content, f"motion-lab.js missing: {expected!r}"


# ====================================================================
# D1 Guards: 錯誤訊息收斂 + console.log 清理
# ====================================================================

class TestSearchErrorMessageGuard:
    """D1 守衛：search 頁面 JS 的 alert / errorText 不可暴露 err.message 技術細節"""

    SEARCH_JS_DIR = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search'

    def _collect_js_files(self):
        """收集 search 目錄下所有 .js 檔案（含子目錄）"""
        return list(self.SEARCH_JS_DIR.rglob('*.js'))

    @staticmethod
    def _is_console_or_throw(line: str) -> bool:
        """排除 console.error / console.warn / throw 中的合法使用"""
        stripped = line.strip()
        if stripped.startswith('console.error') or stripped.startswith('console.warn'):
            return True
        if stripped.startswith('throw '):
            return True
        # 也排除 JS 註解行
        if stripped.startswith('//'):
            return True
        return False

    def test_no_err_message_exposed_in_search_js(self):
        """D1 守衛：search JS alert() 及 errorText 不可暴露 err.message / error.message / result.error"""
        checks = [
            (r'alert\s*\([^)]*(?:err\.message|error\.message|result\.error)',
             "alert() 內暴露技術錯誤訊息"),
            (r'this\.errorText\s*=\s*.*(?:err\.message|error\.message)',
             "errorText 暴露技術錯誤訊息"),
        ]
        for pattern, label in checks:
            all_violations = []
            for js_file in self._collect_js_files():
                violations = find_pattern_in_file(
                    js_file, pattern,
                    exclude_lines=lambda line, _: self._is_console_or_throw(line)
                )
                for line_num, line_content in violations:
                    all_violations.append(f"  {js_file.relative_to(PROJECT_ROOT)}:{line_num}: {line_content}")
            assert not all_violations, (
                f"D1 守衛違規：{label}\n"
                + "\n".join(all_violations)
                + "\n\n修正：只顯示友善中文提示，技術細節降級到 console.error"
            )


class TestLightboxAnimationGuard:
    """C18 guard: Lightbox interrupt getById kill, ESC/close/open paths (method folded)"""

    SEARCH_GRID_MODE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'grid-mode.js'
    SEARCH_NAVIGATION = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'navigation.js'
    SHOWCASE_CORE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-lightbox.js'

    @staticmethod
    def _extract_function(content, func_name):
        pattern = re.compile(r'^\s*(?:async\s+)?' + re.escape(func_name) + r'\s*\(', re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return ''
        return content[match.start():match.start() + 3000]

    def test_search_js_contains(self):
        """search grid-mode/navigation: getById kill, same-index guard, switch path, ordering"""
        gm = self.SEARCH_GRID_MODE.read_text(encoding='utf-8')
        for expected in ["getById", "playLightboxSwitch"]:
            assert expected in gm, f"search/grid-mode.js missing: {expected!r}"
        # same-index no-op
        body = self._extract_function(gm, 'openLightbox')
        assert re.search(r'lightboxIndex\s*===\s*index', body), \
            "search/grid-mode.js openLightbox missing same-index no-op"
        # navigation: sampleGalleryOpen before lightboxOpen
        nav = self.SEARCH_NAVIGATION.read_text(encoding='utf-8')
        hkd = self._extract_function(nav, 'handleKeydown')
        sg_idx = hkd.find('this.sampleGalleryOpen')
        lb_idx = hkd.find('this.lightboxOpen')
        assert sg_idx >= 0, "navigation.js handleKeydown missing: 'this.sampleGalleryOpen'"
        assert lb_idx >= 0, "navigation.js handleKeydown missing: 'this.lightboxOpen'"
        assert sg_idx < lb_idx, \
            "navigation.js handleKeydown: sampleGalleryOpen block must precede lightboxOpen block"
        assert 'closeSampleGallery' in hkd[sg_idx:lb_idx], \
            "navigation.js sampleGalleryOpen ESC missing: 'closeSampleGallery'"

    def test_showcase_js_contains(self):
        """showcase/state-lightbox.js: _killLightboxTimelines, switch path, searchFromMetadata ordering"""
        content = self.SHOWCASE_CORE.read_text(encoding='utf-8')
        for expected in ["_killLightboxTimelines", "playLightboxSwitch"]:
            assert expected in content, f"showcase/state-lightbox.js missing: {expected!r}"
        body = self._extract_function(content, 'openLightbox')
        assert re.search(r'lightboxIndex\s*===\s*index', body), \
            "showcase/state-lightbox.js openLightbox missing same-index no-op"
        sfm = self._extract_function(content, 'searchFromMetadata')
        assert sfm, "showcase/state-lightbox.js missing: 'searchFromMetadata'"
        assert '_killLightboxTimelines' in sfm, \
            "searchFromMetadata missing: '_killLightboxTimelines'"
        kill_idx = sfm.find('_killLightboxTimelines')
        lb_false_idx = sfm.find('lightboxOpen = false')
        assert lb_false_idx > kill_idx, \
            "searchFromMetadata: 'lightboxOpen = false' must come after '_killLightboxTimelines'"

class TestLightboxStateFirstGuard:
    """B19 守衛：Lightbox 導航必須 state-first（lightboxIndex 在 playLightboxSwitch 之前更新）"""

    SEARCH_GRID_MODE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'grid-mode.js'
    SHOWCASE_CORE = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-lightbox.js'

    @staticmethod
    def _read_file(path):
        return path.read_text(encoding='utf-8')

    @staticmethod
    def _read_showcase():
        """合併 state-base.js + state-lightbox.js 覆蓋 B19 guard 範圍（cleanup 在 base，lightbox nav 在 lightbox）"""
        return (
            (PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-base.js').read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-lightbox.js').read_text(encoding='utf-8')
        )

    @staticmethod
    def _extract_function(content, func_name):
        """粗略擷取函數內容（從函數名到下一個同級函數或檔案結尾）"""
        pattern = re.compile(r'^\s*(?:async\s+)?' + re.escape(func_name) + r'\s*\(', re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return ''
        start = match.start()
        return content[start:start + 3000]

    def test_lightbox_nav_state_first_search(self):
        """B19: search lightbox nav 必須在 playLightboxSwitch 之前更新 lightboxIndex"""
        content = self._read_file(self.SEARCH_GRID_MODE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in grid-mode.js"
            switch_pos = body.find('playLightboxSwitch')
            update_pos = body.find('this.lightboxIndex =')
            assert update_pos != -1 and switch_pos != -1, (
                f"{func} 缺少必要的 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：grid-mode.js {func} 的 lightboxIndex 更新必須在 playLightboxSwitch 之前（state-first）"
            )

    def test_lightbox_nav_state_first_showcase(self):
        """B19: showcase lightbox nav 必須在 playLightboxSwitch 之前更新 lightboxIndex"""
        content = self._read_file(self.SHOWCASE_CORE)
        for func in ['prevLightboxVideo', 'nextLightboxVideo']:
            body = self._extract_function(content, func)
            assert body, f"{func} 函數未找到 in showcase/core.js"
            switch_pos = body.find('playLightboxSwitch')
            # F1: _setLightboxIndex 也是合法的 state-first 更新
            update_pos = body.find('this.lightboxIndex =')
            if update_pos == -1:
                update_pos = body.find('_setLightboxIndex(')
            assert update_pos != -1 and switch_pos != -1, (
                f"{func} 缺少必要的 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：core.js {func} 的 lightboxIndex 更新必須在 playLightboxSwitch 之前（state-first）"
            )

    def test_lightbox_switch_onmidpoint_no_index_update(self):
        """B19: prevLightboxVideo/nextLightboxVideo 不可包含 onMidpoint（state-first 模式下已移除）"""
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            for func in ['prevLightboxVideo', 'nextLightboxVideo']:
                body = self._extract_function(content, func)
                assert body, f"{func} 函數未找到 in {filename}"
                assert 'onMidpoint' not in body, (
                    f"B19 違規：{filename} {func} 仍包含 onMidpoint — "
                    "state-first 模式下 lightboxIndex 應在動畫啟動前就已更新，不需要 onMidpoint callback"
                )

    def test_open_lightbox_switch_state_first(self):
        """B19: openLightbox 的 switch 路徑也必須 state-first"""
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            body = self._extract_function(content, 'openLightbox')
            assert body, f"openLightbox 函數未找到 in {filename}"
            switch_section_start = body.find('lightboxIndex !== index')
            assert switch_section_start != -1, f"{filename} openLightbox 缺少 switch 路徑"
            switch_section = body[switch_section_start:]
            switch_pos = switch_section.find('playLightboxSwitch')
            # F1: _setLightboxIndex(index) 也是合法的 state-first 更新
            update_pos = switch_section.find('lightboxIndex = index')
            if update_pos == -1:
                update_pos = switch_section.find('_setLightboxIndex(index)')
            assert update_pos != -1 and switch_pos != -1, (
                f"{filename} openLightbox switch 路徑缺少 lightboxIndex 更新或 playLightboxSwitch 呼叫"
            )
            assert update_pos < switch_pos, (
                f"B19 違規：{filename} openLightbox switch 路徑的 lightboxIndex 更新必須在 playLightboxSwitch 之前"
            )

    def test_lightbox_nexttick_has_generation_guard(self):
        """B19: 所有 lightbox $nextTick 動畫 callback 必須有 _lightboxGeneration 失效檢查"""
        SEARCH_NAV = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'state' / 'navigation.js'
        for path, filename in [
            (self.SEARCH_GRID_MODE, 'search/state/grid-mode.js'),
            (self.SHOWCASE_CORE, 'showcase/core.js'),
        ]:
            content = self._read_file(path)
            for func in ['prevLightboxVideo', 'nextLightboxVideo', 'openLightbox']:
                body = self._extract_function(content, func)
                if 'playLightboxSwitch' not in body and 'playLightboxOpen' not in body:
                    continue
                assert '_lightboxGeneration' in body, (
                    f"B19 違規：{filename} {func} 的 $nextTick callback 缺少 _lightboxGeneration 失效檢查 — "
                    "close/ESC 後 stale callback 會重設 _lightboxAnimating = true 造成 input lock"
                )

    def test_lightbox_close_increments_generation(self):
        """B19: closeLightbox / ESC / searchFromMetadata / page cleanup 必須 increment _lightboxGeneration"""
        # Search closeLightbox
        content = self._read_file(self.SEARCH_GRID_MODE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in grid-mode.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：search closeLightbox 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Showcase closeLightbox
        content = self._read_file(self.SHOWCASE_CORE)
        body = self._extract_function(content, 'closeLightbox')
        assert body, "closeLightbox 函數未找到 in showcase/core.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：showcase closeLightbox 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Showcase searchFromMetadata
        body = self._extract_function(content, 'searchFromMetadata')
        assert body, "searchFromMetadata 函數未找到 in showcase/core.js"
        assert '_lightboxGeneration++' in body, (
            "B19 違規：showcase searchFromMetadata 缺少 _lightboxGeneration++ — "
            "pending $nextTick callback 不會被 invalidate"
        )

        # Page lifecycle cleanup — search (index.js 已由 main.js 取代，54e)
        SEARCH_MAIN = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'search' / 'main.js'
        search_main_content = SEARCH_MAIN.read_text(encoding='utf-8')
        assert '_lightboxGeneration++' in search_main_content, (
            "B19 違規：search main.js cleanup 缺少 _lightboxGeneration++ — "
            "離頁時 pending $nextTick lightbox callback 不會被 invalidate"
        )

        # Page lifecycle cleanup — showcase (init is async, extract manually)
        showcase_content = self._read_showcase()
        cleanup_start = showcase_content.find('cleanup: ()')
        assert cleanup_start != -1, "showcase/state-base.js 缺少 cleanup callback"
        cleanup_section = showcase_content[cleanup_start:cleanup_start + 500]
        assert '_lightboxGeneration++' in cleanup_section, (
            "B19 違規：showcase init() cleanup 缺少 _lightboxGeneration++ — "
            "離頁時 pending $nextTick lightbox callback 不會被 invalidate"
        )


class TestShowcaseReactiveScopeGuard:
    """F1: videos/filteredVideos 移出 Alpine reactive scope — 守衛測試"""

    CORE_JS = PROJECT_ROOT / "web/static/js/pages/showcase/state-base.js"
    SHOWCASE_HTML = PROJECT_ROOT / "web/templates/showcase.html"

    def _read_js(self):
        """合併讀取全部 4 個 ESM 模組覆蓋 F1 守衛範圍。"""
        return (
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-base.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-videos.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-actress.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-lightbox.js").read_text(encoding='utf-8')
        )

    def _get_return_block(self):
        """Extract and concatenate all 'return { ... }' blocks from the merged showcase state modules."""
        content = self._read_js()
        blocks = []
        pos = 0
        while True:
            start = content.find('return {', pos)
            if start == -1:
                break
            brace_depth = 0
            end = start
            for i in range(start, len(content)):
                if content[i] == '{':
                    brace_depth += 1
                elif content[i] == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        end = i + 1
                        break
            blocks.append(content[start:end])
            pos = end
        assert blocks, "Cannot find any 'return {' block in ESM state modules"
        return '\n'.join(blocks)

    def test_guard1_no_videos_in_return_object(self):
        """Guard 1: showcaseState() return object 不包含 videos: 或 filteredVideos: 屬性"""
        block = self._get_return_block()
        lines = block.split('\n')
        for i, line in enumerate(lines, 1):
            assert not re.search(r'^\s*videos\s*:', line), (
                f"F1 違規：return object 第 {i} 行仍包含 'videos:' 屬性 — "
                "應移至閉包變數 _videos"
            )
            assert not re.search(r'^\s*filteredVideos\s*:', line), (
                f"F1 違規：return object 第 {i} 行仍包含 'filteredVideos:' 屬性 — "
                "應移至閉包變數 _filteredVideos"
            )

    def test_guard2_has_count_scalars(self):
        """Guard 2: return object 包含 videoCount: 和 filteredCount:"""
        block = self._get_return_block()
        assert re.search(r'^\s*videoCount\s*:', block, re.MULTILINE), (
            "F1 違規：return object 缺少 'videoCount:' — "
            "需要 scalar reactive 給 template 綁定"
        )
        assert re.search(r'^\s*filteredCount\s*:', block, re.MULTILINE), (
            "F1 違規：return object 缺少 'filteredCount:' — "
            "需要 scalar reactive 給 template 綁定"
        )

    def test_guard3_no_getter_currentLightboxVideo(self):
        """Guard 3: currentLightboxVideo 不是 getter，應為 reactive property"""
        block = self._get_return_block()
        assert 'get currentLightboxVideo()' not in block, (
            "F1 違規：return object 仍有 'get currentLightboxVideo()' getter — "
            "應改為 'currentLightboxVideo: null' reactive property"
        )
        assert re.search(r'^\s*currentLightboxVideo\s*:', block, re.MULTILINE), (
            "F1 違規：return object 缺少 'currentLightboxVideo:' property — "
            "應為手動更新的 reactive property"
        )

    def test_guard4_no_videos_length_in_template(self):
        """Guard 4: showcase.html 不包含 videos.length 或 filteredVideos.length"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        assert 'videos.length' not in content, (
            "F1 違規：showcase.html 仍引用 'videos.length' — "
            "應改用 videoCount"
        )
        assert 'filteredVideos.length' not in content, (
            "F1 違規：showcase.html 仍引用 'filteredVideos.length' — "
            "應改用 filteredCount"
        )

    def test_guard5_no_bare_videos_in_template(self):
        """Guard 5: showcase.html 不引用 bare videos 或 filteredVideos"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        # Match 'videos' or 'filteredVideos' but exclude allowed compounds
        for i, line in enumerate(content.split('\n'), 1):
            # Remove allowed patterns first, then check for bare references
            cleaned = line
            for allowed in ['paginatedVideos', 'currentLightboxVideo', 'videoCount', 'filteredCount',
                            'fetchVideos', 'prevLightboxVideo', 'nextLightboxVideo',
                            'openLightbox', 'closeLightbox', 'playVideo',
                            'showcase.unit.videos']:
                cleaned = cleaned.replace(allowed, '')
            # Now check for bare 'videos' (word boundary)
            if re.search(r'\bvideos\b', cleaned):
                pytest.fail(
                    f"F1 違規：showcase.html L{i} 引用 bare 'videos' — "
                    f"應改用 videoCount 或 paginatedVideos: {line.strip()}"
                )

    def test_guard6_closure_variables_exist(self):
        """Guard 6: state-base.js 有 var _videos 和 var _filteredVideos（module-level 大陣列）"""
        content = self._read_js()
        # ESM 結構：_videos/_filteredVideos 為 module-level export var
        assert re.search(r'\bvar\s+_videos\b', content), (
            "F1 違規：state-base.js 缺少 'var _videos' module-level 宣告 — "
            "大陣列應為模組閉包變數（ESM export var）"
        )
        assert re.search(r'\bvar\s+_filteredVideos\b', content), (
            "F1 違規：state-base.js 缺少 'var _filteredVideos' module-level 宣告 — "
            "大陣列應為模組閉包變數（ESM export var）"
        )

    def _find_statement_end(self, lines, start_idx):
        """Find the end line of a statement starting at start_idx.

        For multi-line statements (e.g., _filteredVideos = _videos.filter(video => { ... })),
        track brace/paren nesting to find the actual end of the statement.
        Returns the index of the last line of the statement.
        """
        depth = 0
        for j in range(start_idx, min(start_idx + 50, len(lines))):
            for ch in lines[j]:
                if ch in '({':
                    depth += 1
                elif ch in ')}':
                    depth -= 1
            # Statement ends when we return to depth 0 (or never went deeper)
            if depth <= 0 and j > start_idx:
                return j
            if depth == 0 and ';' in lines[j]:
                return j
        return start_idx

    def test_guard7_count_sync_after_assignment(self):
        """Guard 7: 每個 _videos = 賦值附近有 videoCount 同步；_filteredVideos = 附近有 filteredCount 同步"""
        content = self._read_js()
        lines = content.split('\n')

        # Check _videos = assignments
        for i, line in enumerate(lines):
            # Match _videos = but not _filteredVideos =
            if re.search(r'\b_videos\s*=', line) and not re.search(r'_filteredVideos', line):
                # Skip var declaration (including ESM export var)
                if re.search(r'(?:export\s+)?var\s+_videos', line):
                    continue
                # Find statement end for multi-line expressions
                stmt_end = self._find_statement_end(lines, i)
                # Check within 3 lines after statement end for videoCount
                nearby = '\n'.join(lines[max(0, i-3):stmt_end+4])
                assert 'videoCount' in nearby, (
                    f"F1 違規：core.js L{i+1} 有 '_videos =' 但附近無 videoCount 同步 — "
                    f"每次 _videos 賦值後必須更新 this.videoCount: {line.strip()}"
                )

        # Check _filteredVideos = assignments
        for i, line in enumerate(lines):
            if re.search(r'\b_filteredVideos\s*=', line):
                # Skip var declaration (including ESM export var)
                if re.search(r'(?:export\s+)?var\s+_filteredVideos', line):
                    continue
                # Skip sort (in-place, no length change)
                if '.sort(' in line:
                    continue
                # Find statement end for multi-line expressions
                stmt_end = self._find_statement_end(lines, i)
                # Check within 3 lines after statement end for filteredCount
                nearby = '\n'.join(lines[max(0, i-3):stmt_end+4])
                assert 'filteredCount' in nearby, (
                    f"F1 違規：core.js L{i+1} 有 '_filteredVideos =' 但附近無 filteredCount 同步 — "
                    f"每次 _filteredVideos 賦值後必須更新 this.filteredCount: {line.strip()}"
                )


class TestGridPerPageGuard:
    """F2: Grid mode 禁用「全部」(perPage=0) 守衛測試"""

    CORE_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-videos.js'
    SHOWCASE_HTML = PROJECT_ROOT / 'web' / 'templates' / 'showcase.html'

    def _read_js(self):
        """合併讀取 state-base.js + state-videos.js（updatePagination 在 videos，restoreState 在 base）。"""
        return (
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-base.js").read_text(encoding='utf-8') + "\n" +
            (PROJECT_ROOT / "web/static/js/pages/showcase/state-videos.js").read_text(encoding='utf-8')
        )

    def test_grid_per_page_method_bodies_contain_guard(self):
        """Guard 1/3/4: updatePagination / restoreState / switchMode 均含 grid+perPage=120 降級邏輯"""
        content = self._read_js()
        for method_pat, window in [
            (r'updatePagination\s*\(\s*\)\s*\{', 800),
            (r'restoreState\s*\(\s*\)\s*\{', 2500),
            (r'switchMode\s*\(\s*m\s*\)\s*\{', 600),
        ]:
            m = re.search(method_pat, content)
            method_name = method_pat.split(r'\s')[0]
            assert m, f"showcase/core.js 找不到 {method_name} 方法"
            body = content[m.start():m.start() + window]
            has_grid = bool(re.search(r"['\"]grid['\"]", body))
            has_120 = bool(re.search(r'perPage\s*=\s*120', body))
            assert has_grid and has_120, \
                f"F2 違規：{method_name} 缺少 grid+perPage=120 降級邏輯"

    def test_guard5_items_per_page_uses_nullish_coalescing(self):
        """Guard 5 (T3.2 P2 fix): items_per_page 預設值必須用 `??` 而非 `||`

        Settings UI 允許 items_per_page=0（"全部"選項，settings.html L663），
        後端 `core/config.py:GalleryConfig.items_per_page` 沒有 gt=0 validator → 0 會透傳到前端。
        若用 `||` 會把 0 視為 falsy 走 fallback 90，導致：
          1. showcase init 永遠拿不到 0，grid+perPage=0→120 降級邏輯（Guard 1/3/4）永遠不觸發
          2. settings 載入時把存檔的 0 顯示成 90，"全部" 選項失效

        必須用 `??`（nullish coalescing）只對 null/undefined 走 fallback，保留 numeric 0。
        """
        showcase_core = self._read_js()
        settings_js = (PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'settings' / 'state-config.js').read_text(encoding='utf-8')

        # 禁止 `items_per_page || ...` pattern（吞 0 的寫法）
        bad_pattern = re.compile(r'items_per_page\s*\|\|')
        showcase_bad = bad_pattern.findall(showcase_core)
        settings_bad = bad_pattern.findall(settings_js)
        assert not showcase_bad, (
            "T3.2 P2 違規：showcase/core.js 含 `items_per_page ||` — "
            "Settings 的 items_per_page=0 ('全部') 會被吞成 fallback，必須改用 `??`"
        )
        assert not settings_bad, (
            "T3.2 P2 違規：settings.js 含 `items_per_page ||` — "
            "載入存檔的 items_per_page=0 ('全部') 會被吞成 fallback，必須改用 `??`"
        )

        # 正向斷言：showcase / settings 都必須有 `items_per_page ?? <number>` 寫法
        good_pattern = re.compile(r'items_per_page\s*\?\?\s*\d+')
        assert good_pattern.search(showcase_core), (
            "T3.2 P2 違規：showcase/core.js 缺少 `items_per_page ?? <number>` 預設值寫法"
        )
        assert good_pattern.search(settings_js), (
            "T3.2 P2 違規：settings.js 缺少 `items_per_page ?? <number>` 預設值寫法"
        )


class TestSettingsResetConfigNoNativeConfirm:
    """T3.4 (CD-52-11): resetConfig 改 fluent-modal 後 settings.js 不再含原 confirm 文字

    用「資料指紋」式精準字串匹配，避免誤命中 cycleLocale (L262) 既有 confirm —
    該 confirm 屬 backlog，不在 Phase 52 範圍。
    """

    SETTINGS_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'settings' / 'state-config.js'

    def test_settings_resetconfig_no_native_confirm(self):
        """T3.4: resetConfig 改 fluent-modal 後 settings.js 不再含原 confirm 完整文字

        守衛字串對齊舊 native confirm 完整文（含尾句號），與新 i18n key 內容
        ('...無法復原。') 不重疊，避免 fallback 內聯時誤觸發。
        """
        settings_js = self.SETTINGS_JS.read_text(encoding="utf-8")
        assert "確定要重置所有設定嗎？此操作將刪除所有自訂設定。" not in settings_js, (
            "T3.4 違規：resetConfig() native confirm 已於 T3.4 替換為 fluent-modal — "
            "settings.js 不應再含舊 native confirm 完整字串"
        )


class TestScannerDeleteAliasGroupNoNativeConfirm:
    """T3.5 (CD-52-11): deleteAliasGroup 改 fluent-modal 後 scanner.js 不再含原 confirm 完整文字

    用「資料指紋」式精準字串匹配，避免誤命中 L239 page-lifecycle confirm
    （'確定要離開嗎？' — backlog OQ 不在 Phase 52 範圍）+ L734 clearLogs
    confirm（'確定要清除所有日誌嗎？...' — Phase 52 不入）。

    額外 assert 三個新 method 名個別存在（避免假陰性 — 若 deleteAliasGroup
    被混進 confirmRemoveActress 等不相關名稱，弱守衛仍會 pass）。
    """

    SCANNER_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'scanner' / 'state-alias.js'

    def test_scanner_no_delete_alias_group_native_confirm(self):
        """T3.5: deleteAliasGroup native confirm 已替換為 fluent-modal"""
        scanner_js = self.SCANNER_JS.read_text(encoding="utf-8")
        # 守衛舊 native confirm 完整文字（含「確定要刪除「」+ 「整筆別名組嗎？」）
        assert "確定要刪除「" not in scanner_js, (
            "T3.5 違規：deleteAliasGroup() native confirm 已於 T3.5 替換為 fluent-modal"
        )
        assert "整筆別名組嗎？" not in scanner_js, (
            "T3.5 違規：deleteAliasGroup() native confirm 已於 T3.5 替換為 fluent-modal"
        )

    def test_scanner_has_delete_alias_group_modal_methods(self):
        """T3.5: 三個新 method 個別存在（強守衛,避免名字混過去）"""
        scanner_js = self.SCANNER_JS.read_text(encoding="utf-8")
        # 個別 assert，避免「deleteAliasGroup in scanner.js」這種會被舊名混過去的弱 guard
        assert "openDeleteAliasGroupModal" in scanner_js, (
            "T3.5 違規：openDeleteAliasGroupModal method 應存在（modal trigger 入口）"
        )
        assert "confirmDeleteAliasGroup" in scanner_js, (
            "T3.5 違規：confirmDeleteAliasGroup method 應存在（API 執行入口）"
        )
        assert "cancelDeleteAliasGroupModal" in scanner_js, (
            "T3.5 違規：cancelDeleteAliasGroupModal method 應存在（dismiss 入口）"
        )

    def test_scanner_html_escape_ladder_includes_delete_alias_group(self):
        """T3.5: scanner.html root escape.window ladder 含 deleteAliasGroupModalOpen"""
        scanner_html = (PROJECT_ROOT / 'web' / 'templates' / 'scanner.html').read_text(encoding="utf-8")
        assert "deleteAliasGroupModalOpen && cancelDeleteAliasGroupModal" in scanner_html, (
            "T3.5 違規：scanner.html root @keydown.escape.window 應串接 deleteAliasGroupModal 的 cancel"
        )


class TestSampleGalleryTemplateGuard:
    """T8：Search Sample Gallery 模板守衛

    靜態確認舊 sampleLightboxOpen / sampleLightboxIndex 已從所有模板移除，
    新 sampleGalleryOpen / sampleGalleryImages / sampleGalleryIndex 已正確
    出現在 search.html 及 base.html（body x-data fallback）中，且
    .sample-gallery overlay 在 searchPage() x-data scope 範圍內。

    base.html 例外說明：body[x-data] 加入 sampleGalleryOpen 等 fallback
    是必要的。Alpine 嵌套 scope 初始化期間，body scope 偶爾會在
    子 x-data（searchPage()）建立前先評估子元素的 binding，導致
    ReferenceError。Fallback 提供安全預設值。

    此 guard 防止未來模板重構時 .sample-gallery 被移出正確 scope，
    或舊 sampleLightbox* 狀態殘留。
    """

    SEARCH_HTML = PROJECT_ROOT / 'web' / 'templates' / 'search.html'
    BASE_HTML = PROJECT_ROOT / 'web' / 'templates' / 'base.html'
    TEMPLATES_DIR = PROJECT_ROOT / 'web' / 'templates'

    def test_sample_gallery_template_html_contains(self):
        """T8/37b-layout: search.html + base.html 含 sampleGallery* state；search.html 含 lb-header；不含舊殘留字串"""
        search_content = self.SEARCH_HTML.read_text(encoding='utf-8')
        base_content = self.BASE_HTML.read_text(encoding='utf-8')
        for state in ('sampleGalleryOpen', 'sampleGalleryImages', 'sampleGalleryIndex'):
            assert state in search_content, f"search.html missing: {state!r}"
            assert state in base_content, f"base.html missing: {state!r}"
        for expected in ['lb-header']:
            assert expected in search_content, f"search.html missing: {expected!r}"
        for forbidden in ['class="sample-lightbox"', 'lb-meta-extra']:
            assert forbidden not in search_content, \
                f"search.html should not contain: {forbidden!r}"

    def test_sample_gallery_template_structure(self):
        """T8: 舊 sampleLightbox* 不在任何模板；sample-gallery 在 searchPage scope 內；sg-open-btn 在 lb-header 內"""
        # 舊 state 不殘留
        pattern = re.compile(r'sampleLightboxOpen|sampleLightboxIndex')
        violations = [str(t.relative_to(PROJECT_ROOT))
                      for t in self.TEMPLATES_DIR.glob('**/*.html')
                      if pattern.search(t.read_text(encoding='utf-8'))]
        assert not violations, \
            f"T8 違規：舊 sampleLightboxOpen/sampleLightboxIndex 仍殘留：{violations}"
        # sample-gallery 在 searchPage scope 後
        content = self.SEARCH_HTML.read_text(encoding='utf-8')
        lines = content.split('\n')
        sp_line = next((i for i, l in enumerate(lines) if 'x-data="searchPage"' in l), None)
        assert sp_line is not None, "search.html missing: 'x-data=\"searchPage\"'"
        sg_line = next((i for i, l in enumerate(lines) if 'class="sample-gallery"' in l), None)
        assert sg_line is not None, "search.html missing: 'class=\"sample-gallery\"'"
        assert sg_line > sp_line, \
            f"T8 違規：.sample-gallery (L{sg_line+1}) 在 searchPage scope (L{sp_line+1}) 之前"
        # sg-open-btn 在 lb-header 內
        lb_line = next((i for i, l in enumerate(lines) if '"lb-header"' in l), None)
        assert lb_line is not None, "search.html missing: 'lb-header'"
        lb_close = None
        depth = 0
        for i in range(lb_line, len(lines)):
            depth += lines[i].count('<div') - lines[i].count('</div>')
            if i > lb_line and depth <= 0:
                lb_close = i
                break
        assert lb_close is not None, "search.html lb-header 找不到對應的 </div>"
        sg_btn_line = next((i for i, l in enumerate(lines) if 'sg-open-btn' in l), None)
        assert sg_btn_line is not None, "search.html missing: 'sg-open-btn'"
        assert lb_line < sg_btn_line < lb_close, \
            f"T8 違規：sg-open-btn (L{sg_btn_line+1}) 不在 lb-header (L{lb_line+1}~L{lb_close+1}) 內"


class TestShowcaseSampleGalleryGuard:
    """T7：Showcase Sample Gallery 靜態守衛

    確保 sample-gallery 元件正確實作於 showcase.html / core.js / animations.js：
    1. Scope 守衛：.sample-gallery 在 x-data="showcaseState()" scope 之後
    2. State 存在守衛：core.js 包含 sampleGalleryOpen / sampleGalleryImages / sampleGalleryIndex
    3. Method 存在守衛：core.js 包含全部 5 個方法
    4. 入口按鈕守衛：showcase.html 包含 sg-open-btn 和 openSampleGallery( 綁定
    5. Overlay 綁定守衛：.sample-gallery 有 sampleGalleryOpen 的 :class / x-show 綁定
    6. 縮圖 active 守衛：sg-thumb-active 和 sampleGalleryIndex 在同一區域
    7. playSampleGallerySwitch 守衛：animations.js 包含完整 C18/C21 實作
    """

    SHOWCASE_HTML = PROJECT_ROOT / 'web' / 'templates' / 'showcase.html'
    CORE_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'state-lightbox.js'
    ANIMATIONS_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'pages' / 'showcase' / 'animations.js'

    def test_showcase_sample_gallery_js_contains(self):
        """T7 守衛 2/3/7: core.js state props + methods；animations.js playSampleGallerySwitch 完整實作"""
        core = self.CORE_JS.read_text(encoding='utf-8')
        for expected in ('sampleGalleryOpen', 'sampleGalleryImages', 'sampleGalleryIndex',
                         'openSampleGallery', 'closeSampleGallery', 'prevSampleGallery',
                         'nextSampleGallery', 'jumpSampleGallery'):
            assert expected in core, f"showcase/state-lightbox.js missing: {expected!r}"
        anim = self.ANIMATIONS_JS.read_text(encoding='utf-8')
        for expected in ['playSampleGallerySwitch', 'killTweensOf', 'gsap-animating', 'clearProps']:
            assert expected in anim, f"showcase/animations.js missing: {expected!r}"

    def test_showcase_sample_gallery_html_structure(self):
        """T7/37b-layout 守衛 1/4/5/6/8/9/10: showcase.html scope 順序、bindings、lb-header、sg-open-btn 位置"""
        content = self.SHOWCASE_HTML.read_text(encoding='utf-8')
        lines = content.split('\n')
        # 守衛 1: .sample-gallery 在 x-data="showcase" scope 後
        sc_line = next((i for i, l in enumerate(lines) if 'x-data="showcase"' in l), None)
        assert sc_line is not None, "showcase.html missing: 'x-data=\"showcase\"'"
        sg_line = next((i for i, l in enumerate(lines) if 'sample-gallery' in l), None)
        assert sg_line is not None, "showcase.html missing: '.sample-gallery'"
        assert sg_line > sc_line, \
            f"T7 違規：.sample-gallery (L{sg_line+1}) 在 showcase scope (L{sc_line+1}) 之前"
        # 守衛 4: sg-open-btn + openSampleGallery
        for expected in ['sg-open-btn', 'openSampleGallery(']:
            assert expected in content, f"showcase.html missing: {expected!r}"
        # 守衛 5: sampleGalleryOpen 在 .sample-gallery 附近 10 行
        gl_start = next((i for i, l in enumerate(lines)
                         if 'sample-gallery' in l and ('class=' in l or 'class =' in l)), None)
        assert gl_start is not None, "showcase.html missing: class='sample-gallery' element"
        nearby = '\n'.join(lines[gl_start:gl_start + 10])
        assert 'sampleGalleryOpen' in nearby, \
            "showcase.html .sample-gallery missing: 'sampleGalleryOpen' binding nearby"
        # 守衛 6: sg-thumb-active 與 sampleGalleryIndex 在 5 行內
        ta_lines = [i for i, l in enumerate(lines) if 'sg-thumb-active' in l]
        gi_lines = [i for i, l in enumerate(lines) if 'sampleGalleryIndex' in l]
        assert ta_lines, "showcase.html missing: 'sg-thumb-active'"
        assert gi_lines, "showcase.html missing: 'sampleGalleryIndex'"
        assert any(abs(t - g) <= 5 for t in ta_lines for g in gi_lines), \
            "showcase.html: sg-thumb-active 和 sampleGalleryIndex 未在同一區域（5 行內）"
        # 37b-layout: lb-header 存在；無 lb-meta-extra
        assert 'lb-header' in content, "showcase.html missing: 'lb-header'"
        assert 'lb-meta-extra' not in content, \
            "showcase.html should not contain: 'lb-meta-extra'"
        # 守衛 10: sg-open-btn 在 lb-header 範圍內
        lb_line = next((i for i, l in enumerate(lines) if '"lb-header"' in l), None)
        assert lb_line is not None, "showcase.html missing: 'lb-header' container"
        lb_close = None
        depth = 0
        for i in range(lb_line, len(lines)):
            depth += lines[i].count('<div') - lines[i].count('</div>')
            if i > lb_line and depth <= 0:
                lb_close = i
                break
        assert lb_close is not None, "showcase.html lb-header 找不到對應的 </div>"
        sg_btn = next((i for i, l in enumerate(lines) if 'sg-open-btn' in l), None)
        assert sg_btn is not None, "showcase.html missing: 'sg-open-btn'"
        assert lb_line < sg_btn < lb_close, \
            f"showcase.html sg-open-btn (L{sg_btn+1}) 不在 lb-header (L{lb_line+1}~L{lb_close+1}) 內"



class TestHelpPageGuard:
    """37d T4 守衛 — help.html 包含 Phase 36/37 新功能說明
    38a T6 更新：文字已移至 i18n key，改為驗證 HTML 有對應 t() 呼叫 + zh_TW.json 含對應字串"""

    def _zh_tw(self):
        import json
        return json.loads((PROJECT_ROOT / 'locales/zh_TW.json').read_text(encoding='utf-8'))

    def test_help_page_guard_html_contains(self):
        """37d/38a 守衛：help.html 含 i18n keys；zh_TW.json 含對應字串"""
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        zh = self._zh_tw()
        for html_key, json_path, expected_text in [
            ('help.scraper.h6_default_source', ['help', 'scraper', 'h6_default_source'], '排序'),
            ('help.scraper.h6_dmm_fuzzy', ['help', 'scraper', 'h6_dmm_fuzzy'], '模糊搜尋'),
            ('help.showcase.other_lightbox_detail', ['help', 'showcase', 'other_lightbox_detail'], '導演'),
            ('help.showcase.other_gallery', ['help', 'showcase', 'other_gallery'], '劇照'),
            ('help.showcase.other_table_cols', ['help', 'showcase', 'other_table_cols'], '片長'),
            ('help.scanner.subtitle_move', ['help', 'scanner', 'subtitle_move'], '字幕'),
        ]:
            assert html_key in html, f"help.html missing: {html_key!r}"
            cur = zh
            for part in json_path:
                cur = cur[part]
            assert expected_text in cur, \
                f"zh_TW.json {'.'.join(json_path)} missing: {expected_text!r}"

    def test_help_page_guard_direct_mode(self):
        """help.html 含 direct（至少 2 次）"""
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        assert html.lower().count('direct') >= 2, \
            "help.html missing: 'direct' at least 2 occurrences"


class TestScannerMissingPillGuard:
    """T10 guard - missing NFO/cover pill + SSE completion (method folded)"""

    SCANNER_HTML = PROJECT_ROOT / "web" / "templates" / "scanner.html"
    SCANNER_SCAN_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
    SCANNER_BATCH_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-batch.js"
    ZH_TW = PROJECT_ROOT / "locales" / "zh_TW.json"

    def test_scanner_contains(self):
        """scanner.html/JS/i18n contain all T10 missing pill strings"""
        html = self.SCANNER_HTML.read_text(encoding='utf-8')
        for expected in ["missingPillVisible", "resumePillVisible"]:
            assert expected in html, f"scanner.html missing: {expected!r}"
        batch = self.SCANNER_BATCH_JS.read_text(encoding='utf-8')
        for expected in ["missingPillVisible", "missingItems", "resumePillVisible",
                         "runMissingEnrich", "checkMissing"]:
            assert expected in batch, f"scanner/state-batch.js missing: {expected!r}"
        scan = self.SCANNER_SCAN_JS.read_text(encoding='utf-8')
        for expected in ["enriching", "missingPillVisible"]:
            assert expected in scan, f"scanner/state-scan.js missing: {expected!r}"
        zh = self.ZH_TW.read_text(encoding='utf-8')
        for expected in ["missing_enrich_idle", "missing_resume_btn"]:
            assert expected in zh, f"zh_TW.json missing: {expected!r}"

class TestGhostFlyPlayLightboxOpen:
    """Phase 51 Phase 4 T4.1：GhostFly.playLightboxOpen 共用實作守衛

    確認 ghost-fly.js 內 playLightboxOpen 函式存在 + cleanup 契約
    （clearProps）+ opts.timelineId 介面已植入。
    """

    GHOST_FLY_JS = PROJECT_ROOT / 'web' / 'static' / 'js' / 'shared' / 'ghost-fly.js'

    def test_ghost_fly_play_lightbox_open_contains(self):
        """ghost-fly.js 含 playLightboxOpen + clearProps + timelineId"""
        js = self.GHOST_FLY_JS.read_text(encoding='utf-8')
        for expected in ['playLightboxOpen', 'clearProps', 'timelineId']:
            assert expected in js, f"ghost-fly.js missing: {expected!r}"


class TestT36ToastI18nKeys:
    """T3.6 (CD-52-11): alert→toast 改寫後新 i18n keys 必須存在於 zh_TW.json"""

    LOCALE_FILE = PROJECT_ROOT / "locales" / "zh_TW.json"

    REQUIRED_KEYS = [
        # scanner.toast (6)
        "scanner.toast.desktop_only",
        "scanner.toast.folder_already_added",
        "scanner.toast.copy_path_failed",
        "scanner.toast.generate_error",
        "scanner.toast.nfo_update_error",
        "scanner.toast.jellyfin_update_error",
        # scanner.copy_fail_modal (3)
        "scanner.copy_fail_modal.title",
        "scanner.copy_fail_modal.body",
        "scanner.copy_fail_modal.close",
        # settings.toast (1)
        "settings.toast.desktop_only",
        # search.toast (4)
        "search.toast.no_valid_files",
        "search.toast.desktop_only",
        "search.toast.load_failed",
        "search.toast.translate_failed",
    ]

    def test_all_t36_keys_exist_in_zh_tw(self):
        import json
        data = json.loads(self.LOCALE_FILE.read_text(encoding="utf-8"))

        def get_nested(d, dotted):
            cur = d
            for part in dotted.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return None
                cur = cur[part]
            return cur if isinstance(cur, str) else None

        missing = [k for k in self.REQUIRED_KEYS if get_nested(data, k) is None]
        assert not missing, f"T3.6 違規：zh_TW.json 缺 i18n keys：{missing}"


class TestScannerCopyFailModal:
    """T3.6: scanner.html copyFailModal markup + scanner/state-scan.js 三 method + escape ladder"""

    SCANNER_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
    SCANNER_HTML = PROJECT_ROOT / "web" / "templates" / "scanner.html"

    def test_scanner_copy_fail_modal_contains(self):
        """T3.6: scanner.js 三 method + scanner.html markup + escape ladder"""
        js = self.SCANNER_JS.read_text(encoding="utf-8")
        for expected in ['openCopyFailModal', 'closeCopyFailModal', 'copyFailModalOpen']:
            assert expected in js, f"scanner/state-scan.js missing: {expected!r}"
        html = self.SCANNER_HTML.read_text(encoding="utf-8")
        for expected in ['copy_fail_modal.title', 'copy-fail-pre',
                         'copyFailModalOpen && closeCopyFailModal']:
            assert expected in html, f"scanner.html missing: {expected!r}"


class TestClipLabHostRemoved:
    """56b-T3: 驗證 clip-lab thin host 已完全移除（檔案 / 目錄 / app.py import / i18n key）"""

    PROJECT_ROOT = Path(__file__).parent.parent.parent

    def test_clip_lab_router_file_not_exists(self):
        """web/routers/clip_lab.py 不應存在"""
        path = self.PROJECT_ROOT / "web" / "routers" / "clip_lab.py"
        assert not path.exists(), f"56b-T3 違規：{path} 仍存在，應已刪除"

    def test_clip_lab_template_not_exists(self):
        """web/templates/clip_lab.html 不應存在"""
        path = self.PROJECT_ROOT / "web" / "templates" / "clip_lab.html"
        assert not path.exists(), f"56b-T3 違規：{path} 仍存在，應已刪除"

    def test_clip_lab_pages_dir_not_exists(self):
        """web/static/js/pages/clip-lab/ 目錄不應存在"""
        path = self.PROJECT_ROOT / "web" / "static" / "js" / "pages" / "clip-lab"
        assert not path.exists(), f"56b-T3 違規：{path} 目錄仍存在，應已刪除"

    def test_app_py_no_clip_lab_import(self):
        """web/app.py 內容不應含 'clip_lab' 字串（import / include_router 皆已移除）"""
        path = self.PROJECT_ROOT / "web" / "app.py"
        content = path.read_text(encoding="utf-8")
        assert "clip_lab" not in content, (
            "56b-T3 違規：web/app.py 仍含 'clip_lab' 字串（import / include_router 未清乾淨）"
        )

    def test_zh_tw_no_clip_lab_namespace(self):
        """locales/zh_TW.json 解析後不應有 'clip_lab' top-level key"""
        path = self.PROJECT_ROOT / "locales" / "zh_TW.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "clip_lab" not in data, (
            "56b-T3 違規：locales/zh_TW.json 仍含 'clip_lab' top-level namespace"
        )


class TestConstellationRealCovers:
    """56b-T4 visual probe：motion-lab Constellation 已使用本地靜態 sc-N.jpg 模擬 prod 視覺。

    守衛範圍刻意降 brittleness（codex review 點 4）：
      - 不檢 IMAGE_POOL.length === 20 字面字
      - 不檢 sc-1..sc-20 完整列表
      - 改檢「機制 / 結構 / 簽名」是否在位
    """

    PROJECT_ROOT = Path(__file__).parent.parent.parent

    def test_constellation_dom_has_real_cover_imgs(self):
        """motion_lab.html 12 個 .clip-lab-slot-img + 1 個 #main-img-photo；無 #XX label / "MAIN" 文字殘留"""
        path = self.PROJECT_ROOT / "web" / "templates" / "motion_lab.html"
        content = path.read_text(encoding="utf-8")
        slot_img_count = content.count('class="clip-lab-slot-img"')
        assert slot_img_count == 12, (
            f"56b-T4 違規：motion_lab.html 應含 12 個 .clip-lab-slot-img，實際 {slot_img_count}"
        )
        assert 'id="main-img-photo"' in content, (
            "56b-T4 違規：motion_lab.html 缺少 #main-img-photo（中央主圖 <img>）"
        )
        # #XX slot label 殘留檢查（T4 後不應再出現）
        for n in range(1, 13):
            label = f'>#{n:02d}</span>'
            assert label not in content, (
                f"56b-T4 違規：motion_lab.html 仍含舊 slot label '{label}'，應已移除"
            )
        # MAIN 文字殘留（T4 後主圖不再有 MAIN 字樣）
        assert ">MAIN<" not in content, (
            "56b-T4 違規：motion_lab.html 仍含 'MAIN' 文字節點，應已被 <img> 取代"
        )

    def test_constellation_host_no_hardcoded_image_paths(self):
        """constellation-host.js 用 IMAGE_BASE 常數 + 模板字串，不硬編碼 sc-N.jpg 完整路徑陣列"""
        path = (
            self.PROJECT_ROOT / "web" / "static" / "js"
            / "pages" / "motion-lab" / "constellation-host.js"
        )
        content = path.read_text(encoding="utf-8")
        # 必須有 IMAGE_BASE / IMAGE_COUNT 常數識別字
        assert "IMAGE_BASE" in content, (
            "56b-T4 違規：constellation-host.js 缺 IMAGE_BASE 常數（圖路徑應常數化）"
        )
        assert "IMAGE_COUNT" in content, (
            "56b-T4 違規：constellation-host.js 缺 IMAGE_COUNT 常數"
        )
        # /static/img/showcase/sc- 字面字不可硬編 12 條/20 條（容許 IMAGE_BASE = '...' 那一行）
        # 我們允許出現上限為 1（IMAGE_BASE 賦值該行）
        hardcoded_count = content.count("/static/img/showcase/sc-")
        assert hardcoded_count <= 1, (
            f"56b-T4 違規：constellation-host.js 含 {hardcoded_count} 處 '/static/img/showcase/sc-' 字面字，"
            "應只在 IMAGE_BASE 常數定義出現（≤ 1）；其餘走模板字串組合"
        )

    def test_shared_animations_has_on_main_swap_hook(self):
        """shared/constellation/animations.js playSlipThrough 必須含 onMainSwap hook 機制"""
        path = (
            self.PROJECT_ROOT / "web" / "static" / "js" / "shared"
            / "constellation" / "animations.js"
        )
        content = path.read_text(encoding="utf-8")
        # 簽名末加 options 參數
        assert "options = {}" in content, (
            "56b-T4 違規：animations.js playSlipThrough 應有 options = {} 末參數（onMainSwap hook 機制）"
        )
        # callback 內呼叫 hook
        assert "options.onMainSwap" in content, (
            "56b-T4 違規：animations.js 應在 t=0.30 callback 呼叫 options.onMainSwap?.()"
        )


class TestSettingsPanelStructureGuard:
    """61b-4 → 64b-1/64b-5: settings.html — form wraps all 3 sections + ids preserved.

    64b-5 改寫：branch64 把 6-tab x-show panel 拆成單欄三分類常駐 section
    （sec-search / sec-gallery / sec-system）。本守衛從「form 包 6 panel」改為
    「form 包 3 section」+「單欄無 activeTab gating」，仍守住「每個 input 留在
    #settingsForm 內 → :inert 保護」這個結構不變量。
    """

    def _settings(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def test_form_wraps_all_three_sections(self):
        """<form id="settingsForm"> opens before the first .settings-section and
        </form> closes after the last (form contains all 3 sections; modals/toast
        live OUTSIDE the form)."""
        html = self._settings()
        form_open = html.index('<form id="settingsForm"')
        form_close = html.index("</form>")
        first_section = html.index('class="settings-section"')
        last_section = html.rindex('class="settings-section"')
        assert form_open < first_section, (
            "64b-1 違規：<form id=\"settingsForm\"> 必須在第一個 .settings-section 之前"
        )
        assert last_section < form_close, (
            "64b-1 違規：</form> 必須在最後一個 .settings-section 之後（form 須包住全部 section）"
        )
        # exactly 3 sections
        assert html.count('class="settings-section"') == 3, (
            f"64b-1 違規：應有 3 個 .settings-section，實得 {html.count('class=\"settings-section\"')}"
        )
        # 三個 section id 齊全
        for sid in ("sec-search", "sec-gallery", "sec-system"):
            assert f'id="{sid}"' in html, f"64b-1 違規：缺少 section id=\"{sid}\""

    def test_sections_single_column_no_activetab_gating(self):
        """64b-1: 退單欄後 section 常駐——舊 .settings-panel wrapper 已移除，
        section 不再由 activeTab x-show/x-if 控制顯隱（nav 改純 scroll 定位）。"""
        html = self._settings()
        assert 'class="settings-panel"' not in html, (
            "64b-1 違規：殘留舊 .settings-panel wrapper（應已拆為 .settings-section）"
        )
        assert 'x-show="activeTab' not in html, (
            "64b-1 違規：section 不應由 activeTab x-show 控制顯隱（已退單欄，nav 純 scroll）"
        )
        assert 'x-if="activeTab' not in html, (
            "64b-1 違規：不可用 x-if activeTab gating"
        )

    def test_all_form_ids_preserved(self):
        """All control ids from the field→tab mapping must survive the reorg."""
        html = self._settings()
        required_ids = [
            "settingsForm", "saveBtn",
            # sources — 61c-3 removed #uncensoredModeEnabled checkbox (batch-bar button is sole control)
            # translate
            "translateEnabled", "translateProvider", "translateOptions",
            "ollamaUrl", "ollamaModel", "geminiApiKey", "geminiModel",
            "ollamaFields", "geminiFields", "openaiFields",
            # advanced
            "searchFavoriteFolder", "avlistOutputDir", "avlistOutputFilename",
            "avlistMinSize", "defaultPage", "viewerPlayer",
            # scraping
            "createFolder", "folderLayer1", "folderLayer2", "folderLayer3",
            "filenameFormat", "maxTitleLength", "maxFilenameLength", "videoExtensions",
            # organize
            "avlistMode", "avlistSort", "avlistOrder",
            # display
            "avlistItemsPerPage",
        ]
        for _id in required_ids:
            assert f'id="{_id}"' in html, (
                f"61b-4 違規：form id 在 DOM 重組後遺失：id=\"{_id}\""
            )

    def test_no_duplicate_ids(self):
        """No duplicate id="..." in the document (display-tab mirror controls
        must not reuse an existing id)."""
        import re as _re
        html = self._settings()
        ids = _re.findall(r'\sid="([^"]+)"', html)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        assert not dupes, f"61b-4 違規：settings.html 含 duplicate id：{dupes}"


# ─── TASK-62a-0: source pill 跨頁共用 component + bootstrap 注入 ───
SOURCE_PILL_CSS         = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "components" / "source-pill.css"
SETTINGS_CSS            = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "settings.css"
BASE_HTML               = Path(__file__).parent.parent.parent / "web" / "templates" / "base.html"
ADV_SEARCH_BOOTSTRAP    = Path(__file__).parent.parent.parent / "web" / "templates" / "_advanced_search_bootstrap.html"


class TestSourcePillSharedComponentGuard:
    """TASK-62a-0: source pill 抽成 unscoped 共用 component + bootstrap partial 跨頁注入。

    鎖住「樣式去 #settings-components scope + class rename」與「__ADVANCED_SEARCH__
    抽 partial 供 Search/Showcase 共用」兩道靜態 glue。視覺等價走 Manual checklist。
    """

    def _source_pill_css(self):
        return SOURCE_PILL_CSS.read_text(encoding="utf-8")

    def _settings_css(self):
        return SETTINGS_CSS.read_text(encoding="utf-8")

    def _base_html(self):
        return BASE_HTML.read_text(encoding="utf-8")

    def _bootstrap(self):
        return ADV_SEARCH_BOOTSTRAP.read_text(encoding="utf-8")

    def _search_html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _showcase_html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _settings_html(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def test_source_pill_css_exists_with_selectors(self):
        """source-pill.css 存在且含全部 component 選擇器 + strikethrough contract。"""
        assert SOURCE_PILL_CSS.exists(), "62a-0 違規：缺少 web/static/css/components/source-pill.css"
        css = self._source_pill_css()
        for sel in [
            ".source-pill",
            ".source-pill--uncensored",
            ".source-pill--manual-only",
            ".source-pill-mt-badge",
            ".source-pill-badge",
            ".source-pill.is-partsbin",
            '.source-pill[data-enabled="false"] .pill-name',
        ]:
            assert sel in css, f"62a-0 違規：source-pill.css 缺少選擇器 {sel!r}"

    def test_source_pill_css_is_unscoped(self):
        """source-pill.css 不得含 #settings-components（確保 cross-page unscoped）。"""
        assert "#settings-components" not in self._source_pill_css(), (
            "62a-0 違規：source-pill.css 不應含 #settings-components scope"
        )

    def test_settings_css_no_longer_defines_pill(self):
        """settings.css 不再含 .settings-sources-pill 本體規則（無兩份定義）。

        容器 .settings-sources-pills（複數）為 settings 專屬 layout，刻意保留，
        排除它後 settings.css 不應再有任何 settings-sources-pill 規則。
        """
        css = self._settings_css()
        stripped = re.sub(r"settings-sources-pills\b", "", css)
        assert "settings-sources-pill" not in stripped, (
            "62a-0 違規：settings.css 仍含 settings-sources-pill（pill 規則應已搬至 source-pill.css）"
        )

    def test_base_html_links_source_pill_css(self):
        """base.html 載入 source-pill.css（全域 component）。"""
        assert "/static/css/components/source-pill.css" in self._base_html(), (
            "62a-0 違規：base.html 未 <link> source-pill.css"
        )

    def test_bootstrap_partial_exists_with_injection(self):
        """_advanced_search_bootstrap.html 存在且注入 __ADVANCED_SEARCH__ + config 欄位。"""
        assert ADV_SEARCH_BOOTSTRAP.exists(), (
            "62a-0 違規：缺少 web/templates/_advanced_search_bootstrap.html"
        )
        html = self._bootstrap()
        for token in [
            "window.__ADVANCED_SEARCH__",
            "config.advanced_search_enabled",
            "config.sources",
        ]:
            assert token in html, f"62a-0 違規：bootstrap partial 缺少 {token!r}"

    def test_search_and_showcase_include_bootstrap(self):
        """search.html + showcase.html 皆 include bootstrap partial。"""
        for name, html in [("search.html", self._search_html()),
                            ("showcase.html", self._showcase_html())]:
            assert "{% include '_advanced_search_bootstrap.html' %}" in html, (
                f"62a-0 違規：{name} 未 include _advanced_search_bootstrap.html"
            )

    def test_search_html_no_inline_advanced_search(self):
        """search.html 不再 inline 定義 window.__ADVANCED_SEARCH__（改走 include）。"""
        html = self._search_html()
        assert "window.__ADVANCED_SEARCH__ =" not in html, (
            "62a-0 違規：search.html 仍 inline 定義 __ADVANCED_SEARCH__（應改用 include）"
        )

    def test_settings_html_uses_source_pill_class(self):
        """settings.html pill markup 改用 source-pill（無 settings-sources-pill 殘留）。

        容器 .settings-sources-pills（複數）為 settings 專屬 layout，刻意保留，
        故排除它後再檢查；pill 本體 / badge / mt-badge / modifier 不應有 settings-sources- 前綴。
        """
        html = self._settings_html()
        # 移除合法保留的容器 class（複數 pills），再檢查殘留 pill 前綴
        stripped = re.sub(r"settings-sources-pills\b", "", html)
        assert "settings-sources-pill" not in stripped, (
            "62a-0 違規：settings.html 仍含 settings-sources-pill class（應 rename 為 source-pill）"
        )


# ── TASK-62a-2: 進階重刮彈窗 partial + source-pill action/loading modifier + i18n ──
RESCRAPE_MODAL_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "_rescrape_modal.html"
RESCRAPE_MODAL_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "components" / "rescrape-modal.css"


class TestRescrapeModalGuard:
    """TASK-62a-2: 進階重刮彈窗 partial（pick/preview 換頁）+ source-pill action/loading
    modifier + zh_TW i18n 的靜態結構守衛。鏡射 TestSourcePillSharedComponentGuard。

    僅鎖靜態結構 / contract glue（partial 存在、兩步、fluent-modal 開關、proxy-image、
    confirm 圓鈕、include 點、css modifier、i18n key、無硬編碼 token）。
    視覺對齊 mockup 走 Manual checklist。Alpine 行為是 62a-3。
    """

    def _modal_html(self):
        return RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")

    def _modal_css(self):
        return RESCRAPE_MODAL_CSS.read_text(encoding="utf-8")

    def _source_pill_css(self):
        return SOURCE_PILL_CSS.read_text(encoding="utf-8")

    def _showcase_html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _base_html(self):
        return BASE_HTML.read_text(encoding="utf-8")

    def _zh_tw(self):
        return json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))

    def test_partial_exists(self):
        """_rescrape_modal.html 存在。"""
        assert RESCRAPE_MODAL_HTML.exists(), (
            "62a-2 違規：缺少 web/templates/_rescrape_modal.html"
        )

    def test_partial_two_step_structure(self):
        """partial 含 pick / preview 兩步換頁。"""
        html = self._modal_html()
        assert "rescrapeStep === 'pick'" in html, "62a-2 違規：partial 缺少 pick step"
        assert "rescrapeStep === 'preview'" in html, "62a-2 違規：partial 缺少 preview step"

    def test_partial_uses_fluent_modal_pattern(self):
        """沿用 fluent-modal + :class modal-open（非 showModal）。"""
        html = self._modal_html()
        assert "class=\"modal fluent-modal" in html, (
            "62a-2 違規：partial 未沿用 'modal fluent-modal' class"
        )
        assert "{ 'modal-open': rescrapeOpen }" in html, (
            "62a-2 違規：partial 未用 :class=\"{ 'modal-open': rescrapeOpen }\" 開關"
        )
        assert ".showModal()" not in html, (
            "62a-2 違規：partial 不應使用原生 .showModal()"
        )

    def test_partial_uses_source_pill_action_class(self):
        """pill 用 source-pill + source-pill--action（點擊變體）。"""
        html = self._modal_html()
        assert "source-pill source-pill--action" in html, (
            "62a-2 違規：partial pill 未使用 source-pill--action 點擊變體"
        )

    def test_metatube_group_is_data_driven(self):
        """62c-5：Metatube 分組 data-driven（x-for over rescrapeMetatubeSources()，
        鏡射 builtin pill + metatube `m` type badge）；非靜態空組占位。"""
        html = self._modal_html()
        assert 'x-for="s in rescrapeMetatubeSources()"' in html, (
            "62c-5 違規：Metatube 分組未用 x-for over rescrapeMetatubeSources()（仍是靜態空組）"
        )
        # Metatube group-sep label 保留（品牌名不走 i18n，CD-62-12）
        assert '<div class="rescrape-group-sep">Metatube</div>' in html, (
            "62c-5 違規：缺少 Metatube group-sep label"
        )
        # metatube `m` type badge（用 source-pill.css 既有 class；連線態 chrome 留 B3）
        assert "source-pill-mt-badge" in html, (
            "62c-5 違規：metatube pill 缺少 source-pill-mt-badge type badge"
        )
        # 註：連線態 chrome（斷線灰標 / Parts Bin 星標）是 B3 才接資料的擴充，本 task 不做。
        # 不在此加負向守衛——B3 合法加入時不應被本守衛絆住（scope 邊界由 card/commit 記錄即可）。

    def test_metatube_empty_note_is_conditional(self):
        """62c-5：group_metatube_empty note 條件化（僅 metatube=0 顯示），非無條件靜態。"""
        html = self._modal_html()
        m = re.search(
            r'<div class="rescrape-empty-note"([^>]*)>',
            html,
        )
        assert m, "62c-5 違規：找不到 rescrape-empty-note 元素"
        attrs = m.group(1)
        assert 'x-show="rescrapeMetatubeSources().length === 0"' in attrs, (
            "62c-5 違規：rescrape-empty-note 未條件化於 "
            "x-show=\"rescrapeMetatubeSources().length === 0\"（仍是靜態空組 note）"
        )

    def test_preview_img_uses_proxy_image(self):
        """preview cover 走 /api/proxy-image?url= + encodeURIComponent，禁用 gallery/image。"""
        html = self._modal_html()
        assert "/api/proxy-image?url=" in html, (
            "62a-2 違規（CD-62-14 #8）：preview img 未走 /api/proxy-image?url="
        )
        assert "encodeURIComponent" in html, (
            "62a-2 違規（CD-62-14 #8）：preview img URL 未 encodeURIComponent"
        )
        assert "/api/gallery/image" not in html, (
            "62a-2 違規（CD-62-14 #8）：preview img 禁用 /api/gallery/image（那條給 DB file:///）"
        )

    def test_confirm_row_has_cancel_and_confirm_buttons(self):
        """✗/✓ 兩圓鈕：rescrape-confirm-btn cancel + rescrape-confirm-btn confirm。"""
        html = self._modal_html()
        assert "rescrape-confirm-btn cancel" in html, (
            "62a-2 違規：缺少 rescrape-confirm-btn cancel（✗ 鈕）"
        )
        assert "rescrape-confirm-btn confirm" in html, (
            "62a-2 違規：缺少 rescrape-confirm-btn confirm（✓ 鈕）"
        )

    def test_showcase_includes_partial(self):
        """showcase.html include _rescrape_modal.html。"""
        assert "{% include '_rescrape_modal.html' %}" in self._showcase_html(), (
            "62a-2 違規：showcase.html 未 include _rescrape_modal.html"
        )

    def test_source_pill_css_has_action_loading_modifiers(self):
        """source-pill.css 新增 action / loading / spinner modifier。"""
        css = self._source_pill_css()
        for sel in [".source-pill--action", ".source-pill.is-loading", ".pill-spin"]:
            assert sel in css, f"62a-2 違規：source-pill.css 缺少 {sel!r} modifier"
        assert ".source-pill:disabled" in css, (
            "62a-2 違規：source-pill.css 缺少 .source-pill:disabled（loading 期間其餘禁用）"
        )

    def test_source_pill_base_drag_rules_untouched(self):
        """base .source-pill 仍是 cursor: grab（未回歸 settings 拖曳）。"""
        css = self._source_pill_css()
        assert "cursor: grab" in css, (
            "62a-2 違規：source-pill.css base drag 規則（cursor: grab）遭破壞"
        )

    def test_rescrape_modal_css_exists(self):
        """rescrape-modal.css 存在，含彈窗專屬 class。"""
        assert RESCRAPE_MODAL_CSS.exists(), (
            "62a-2 違規：缺少 web/static/css/components/rescrape-modal.css"
        )
        css = self._modal_css()
        for sel in [
            ".rescrape-modal-box",
            ".rescrape-x",
            ".rescrape-num-input",
            ".rescrape-preview",
            ".rescrape-confirm-btn",
        ]:
            assert sel in css, f"62a-2 違規：rescrape-modal.css 缺少 {sel!r}"

    def test_base_html_links_rescrape_modal_css(self):
        """base.html <link> rescrape-modal.css。"""
        assert "/static/css/components/rescrape-modal.css" in self._base_html(), (
            "62a-2 違規：base.html 未 <link> rescrape-modal.css"
        )

    def test_rescrape_modal_css_no_hardcoded_tokens(self):
        """rescrape-modal.css 無硬編碼 hex 色（白名單 #fff）/ px radius（白名單 999px）。"""
        css = self._modal_css()
        # hex 色：允許 #fff（confirm 鈕白前景，與既有按鈕慣例一致）
        hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
        bad_hex = [h for h in hexes if h.lower() not in ("#fff", "#ffffff")]
        assert not bad_hex, (
            f"62a-2 違規：rescrape-modal.css 含硬編碼 hex 色 {bad_hex}（僅 #fff 白名單）"
        )
        # border-radius 不得用 px 字面（用 --fluent-radius-* token；pill 999px 走 source-pill）
        radius_px = re.findall(r"border-radius:\s*\d+px", css)
        assert not radius_px, (
            f"62a-2 違規：rescrape-modal.css border-radius 用 px 字面 {radius_px}（應用 --fluent-radius-* token）"
        )

    # ── Showcase Advanced Rescrape layering fix (CSS z-index + glass backdrop) ──
    # Bug: rescrape modal opened from the lightbox rendered UNDER it because DaisyUI
    # gives .modal z-index 999 < .showcase-lightbox 1000. Fix lifts .rescrape-dialog
    # to 1600 and adds the real class-open glass backdrop (::backdrop never fires for
    # the Alpine class-open pattern). These guards encode the cross-file z-index
    # contract (stylelint can't express "A > B") + token-only backdrop.

    def _theme_css(self):
        return THEME_CSS.read_text(encoding="utf-8")

    def _showcase_css(self):
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    @staticmethod
    def _zindex_of(css, selector):
        """Extract the int z-index declared on `selector { ... z-index: N }`.
        selector is a literal substring of the rule head (regex-escaped)."""
        m = re.search(
            re.escape(selector) + r"\s*\{[^}]*?z-index:\s*(\d+)",
            css, re.DOTALL,
        )
        assert m, f"無法在 CSS 找到 {selector!r} 的 z-index 宣告"
        return int(m.group(1))

    def test_rescrape_dialog_zindex_above_lightbox_stack_below_toast(self):
        """.rescrape-dialog z-index 必須 > showcase-lightbox(1000)/similar-stage(1501)
        且 < fluent-toast-container(2000)。實際數字用 regex 抽出，未來誰調低就紅。"""
        rescrape_z = self._zindex_of(self._modal_css(), ".rescrape-dialog.modal")
        showcase_css = self._showcase_css()
        lightbox_z = self._zindex_of(showcase_css, ".showcase-lightbox")
        similar_z = self._zindex_of(showcase_css, ".similar-stage")
        toast_z = self._zindex_of(self._theme_css(), ".fluent-toast-container")

        assert rescrape_z > lightbox_z, (
            f"62-showcase 違規：rescrape z-index {rescrape_z} 未高於 "
            f".showcase-lightbox {lightbox_z}（會渲染在 lightbox 下方）"
        )
        assert rescrape_z > similar_z, (
            f"62-showcase 違規：rescrape z-index {rescrape_z} 未高於 "
            f".similar-stage {similar_z}"
        )
        assert rescrape_z < toast_z, (
            f"62-showcase 違規：rescrape z-index {rescrape_z} 未低於 "
            f".fluent-toast-container {toast_z}（成功 toast 會被彈窗蓋住）"
        )

    def test_fluent_modal_class_open_backdrop_uses_tokens(self):
        """.fluent-modal.modal-open glass backdrop：12px blur 走 --fluent-blur-light token
        （非硬編碼 blur(Npx)）、dim 走 --overlay-modal、且有 -webkit- 配對 fallback。
        ::backdrop 在 class-open 模式不觸發，故真正生效的是這條 unlayered 規則。"""
        css = self._theme_css()
        m = re.search(
            r"\.fluent-modal\.modal-open\s*\{([^}]*)\}", css, re.DOTALL,
        )
        assert m, (
            "62-showcase 違規：theme.css 缺少 .fluent-modal.modal-open "
            "class-open 玻璃 backdrop 規則"
        )
        rule = m.group(1)
        assert "blur(var(--fluent-blur-light))" in rule, (
            "62-showcase 違規：backdrop blur 未走 --fluent-blur-light token"
        )
        # 禁止硬編碼 blur(Npx)（token only，ui-conventions §2）
        assert not re.search(r"blur\(\s*\d+px", rule), (
            "62-showcase 違規：backdrop 含硬編碼 blur(Npx)，應用 --fluent-blur-light token"
        )
        assert "var(--overlay-modal)" in rule, (
            "62-showcase 違規：backdrop dim 未走 --overlay-modal token"
        )
        # Safari/iOS fallback：-webkit- 配對（gotchas §backdrop-filter）
        assert "-webkit-backdrop-filter: blur(var(--fluent-blur-light))" in rule, (
            "62-showcase 違規：backdrop 缺少 -webkit-backdrop-filter 配對（Safari/iOS）"
        )
        # painted on the dialog itself（保留 @click.self 關窗）—— 不得引入攔截點擊的 child
        assert "background: var(--overlay-modal)" in rule, (
            "62-showcase 違規：dim 應 paint 在 dialog 本體（background），"
            "不可改用攔截點擊的 child div（會破壞 @click.self 關窗）"
        )

    def test_zh_tw_has_rescrape_keys(self):
        """zh_TW.json 含 showcase.rescrape.* key。"""
        data = self._zh_tw()
        rescrape = data.get("showcase", {}).get("rescrape", {})
        for key in [
            "modal_title", "number_label", "filename_hint", "source_question",
            "auto_source", "not_found", "overwrite_warning", "confirm",
            "back_to_pick", "success", "fail",
            # 64a 新增（zh_TW 先行，其餘 locale milestone 同步）
            "search_title", "offline_tooltip",
        ]:
            assert key in rescrape, f"zh_TW.json 缺少 showcase.rescrape.{key}"


class TestRescrapeStateGuard:
    """62a-3: 守衛 state-rescrape.js mixin contract — 確保 partial（_rescrape_modal.html）引用的
    state/method 全揭露、commit 契約（enrich-single + refresh_full + overwrite_existing）正確、
    transient 不碰 currentLightboxVideo（CD-62-2），且 main.js mergeState 鏈整合。
    match TestSimilarStageGuard L1164 pattern。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    SHOWCASE_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase"
    STATE_RESCRAPE_JS = SHARED_DIR / "state-rescrape.js"
    MAIN_JS = SHOWCASE_DIR / "main.js"

    def _src(self):
        return self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def _main(self):
        return self.MAIN_JS.read_text(encoding="utf-8")

    def test_state_rescrape_file_exists(self):
        """state-rescrape.js 必須存在於 shared/（供 showcase + search 共用）。"""
        assert self.STATE_RESCRAPE_JS.exists(), \
            f"state-rescrape.js missing at {self.STATE_RESCRAPE_JS!s}"

    def test_exports_rescrape_state_factory(self):
        """必須 export function rescrapeState（factory，rescrapeState.call(this) 接入 mergeState）。"""
        src = self._src()
        assert re.search(r"export\s+function\s+rescrapeState\s*\(", src), \
            "state-rescrape.js missing: export function rescrapeState()"

    def test_defines_all_state_keys(self):
        """9 個 partial 引用的 state key 必須平鋪定義。"""
        src = self._src()
        for key in (
            "rescrapeOpen", "rescrapeStep", "rescrapeEntryPoint", "rescrapeNumber",
            "rescrapeOriginalFilename", "rescrapeSources", "rescrapeLoadingSource",
            "rescrapePreview", "rescrapeNotFound",
        ):
            assert key in src, f"state-rescrape.js missing state key: {key}"

    def test_defines_all_methods(self):
        """6 個 partial 引用的 method + openRescrape（62b-1 呼叫）必須揭露。"""
        src = self._src()
        for method in (
            "openRescrape", "rescrapeWithSource", "rescrapeConfirm",
            "rescrapeBackToPick", "closeRescrape", "rescrapeBuiltinSources",
            "rescrapeMetatubeSources",
        ):
            assert method in src, f"state-rescrape.js missing method: {method}"

    def test_commit_contract(self):
        """commit 契約：POST /api/enrich-single + mode refresh_full + overwrite_existing。"""
        src = self._src()
        assert "'/api/enrich-single'" in src, "missing POST /api/enrich-single"
        assert "refresh_full" in src, "missing mode: refresh_full（CD-62-0/4）"
        assert "overwrite_existing" in src, "missing overwrite_existing（CD-62-4）"
        assert "true" in src, "overwrite_existing 必須為 true"

    def test_preview_contract(self):
        """preview 契約：POST /api/rescrape/preview。"""
        src = self._src()
        assert "'/api/rescrape/preview'" in src, "missing POST /api/rescrape/preview"

    def test_no_current_lightbox_video(self):
        """CD-62-2 transient 守衛：mixin 絕不讀寫 currentLightboxVideo（用私有 _rescrapeVideo）。"""
        src = self._src()
        assert "currentLightboxVideo" not in src, \
            "state-rescrape.js 違反 CD-62-2：不得引用 currentLightboxVideo，應用私有 _rescrapeVideo"

    def test_rescraping_guard_present(self):
        """連點防護：_rescraping guard 必須存在（鏡像 _enriching）。"""
        src = self._src()
        assert "_rescraping" in src, "missing _rescraping 連點 guard"

    def test_no_proxy_image_construction(self):
        """CD-62-14 #8：/api/proxy-image URL 由 partial 內聯，mixin 不得重複建構。"""
        src = self._src()
        assert "/api/proxy-image" not in src, \
            "state-rescrape.js 不得建構 /api/proxy-image URL（partial 內聯，避免重複）"

    def test_main_js_imports_and_merges_rescrape_state(self):
        """main.js 必須 import rescrapeState 並插入 mergeState 鏈。"""
        src = self._main()
        assert "from '@/shared/state-rescrape.js'" in src, \
            "main.js missing: import { rescrapeState } from '@/shared/state-rescrape.js'"
        assert "rescrapeState.call(this)" in src, \
            "main.js mergeState chain missing: rescrapeState.call(this)"

    def test_open_rescrape_reads_video_number(self):
        """62b-2 #1：openRescrape 內 rescrapeNumber 預填來源必須 = video.number（前端 prefill 持久化連結）。

        鎖住「commit 修正 number → refreshVideoData 突變 video.number → 再開彈窗預填新值」鏈的前端端點。
        若 refactor 把預填改成讀別處（如固定 '' 或 video.code），此守衛 RED。
        """
        src = self._src()
        # 寬鬆匹配：rescrapeNumber = (... video.number ...) ；允許 =、&&、() 周圍空白變動
        assert re.search(r"rescrapeNumber\s*=.*video\s*&&\s*video\.number", src), \
            "openRescrape 必須將 rescrapeNumber 預填自 video.number（前端 prefill 連結，62b-2 #6）"

    def test_close_rescrape_clears_longpress_flag(self):
        """Codex 二輪 P3：closeRescrape 必須清長壓殘留旗標（longPressReset），涵蓋鍵盤 / 輔助技術
        以 click 啟用（無 mousedown 前導）繞過 longPressStart top reset 的卡旗標路徑。
        若 refactor 拿掉此清理，長壓開 modal 後關閉、下次 keyboard quick-enrich 會被吞 → RED。
        """
        src = self._src()
        assert "longPressReset" in src, \
            "closeRescrape 必須呼叫 longPressReset()（清長壓旗標，鍵盤/AT 兜底，Codex 二輪 P3）"

    def test_rescrape_metatube_sources_has_routable_gate(self):
        """Codex PR#47 round-2 P2-B：rescrapeMetatubeSources() 必須同時 filter
        type === 'metatube' AND routable === true（element-bound regex，防空字串假測試）。

        metatube sources 目前後端無路由（validate_source_id 只認 auto + builtin SOURCE_ORDER）；
        B3 才接 metatube route/validator，屆時後端揭露 routable=true 後 pill 才長出。
        直到 B3 前，缺 routable gate 的 metatube pill 點下去 → not-found；本守衛確保回歸會 RED。
        """
        src = self._src()
        # element-bound regex：匹配 rescrapeMetatubeSources 函式體，確認同時含兩個 filter 條件
        m = re.search(
            r"rescrapeMetatubeSources\s*\(\s*\)\s*\{[^}]*\.filter\s*\([^)]*"
            r"s\.type\s*===\s*['\"]metatube['\"][^)]*&&[^)]*s\.routable\s*===\s*true[^)]*\)",
            src,
            re.DOTALL,
        )
        assert m, (
            "rescrapeMetatubeSources() 必須 filter s.type === 'metatube' && s.routable === true "
            "（缺 routable gate：metatube pill 在後端無路由前點下去 → not-found，Codex PR#47 round-2 P2-B）"
        )


class TestRescrapeEntryGuard:
    """62b-1: 守衛三個 Showcase 進階重刮入口接線 contract（lightbox ⚙ + grid 長壓 + lightbox 🔍 長壓）。

    入口全受 rescrapeEnabled() gate；長壓走 shared/long-press.js helper（grid + lightbox 共用）；
    tap 路徑（enrichVideo）不得被長壓覆蓋；長壓 callback 路由到 openRescrape(...,'enrich')，不直接 enrichVideo。
    強守衛採 element-bound regex（綁到具體 button tag）避免「字串存在性」假測試（gotchas Frontend Guard 強度）。
    對齊 TestSimilarStageGuard L1164 / TestRescrapeStateGuard pattern。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    SHOWCASE_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase"
    LONG_PRESS_JS = SHARED_DIR / "long-press.js"
    STATE_RESCRAPE_JS = SHARED_DIR / "state-rescrape.js"
    MAIN_JS = SHOWCASE_DIR / "main.js"

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _grid_enrich_btn(self, html):
        """擷取 grid 缺卡 enrich-btn 的完整 <button>...</button> 區塊（btn-glass-circle enrich-btn）。

        注意：button tag 內 @mousedown 等屬性值含 arrow function `() =>`，含 `>` 字元，
        故不可用 `[^>]*>` 截到第一個 `>`；改用 non-greedy 抓到 </button>。
        """
        m = re.search(
            r'<button\b[^>]*?\bclass="btn-glass-circle enrich-btn".*?</button>',
            html, re.DOTALL,
        )
        assert m, "grid .btn-glass-circle.enrich-btn button 區塊不存在"
        return m.group(0)

    def _lightbox_enrich_btn(self, html):
        """擷取 lightbox cover-actions 🔍 enrich-btn 區塊（含 enrichVideo(currentLightboxVideo) 的 lb-action-btn）。"""
        # (?:(?!</button>).)*? 確保不跨越前一個 </button>，避免抓到 play/open 等其他 lb-action-btn
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bclass="lb-action-btn"'
            r'(?:(?!</button>).)*?enrichVideo\(currentLightboxVideo\)'
            r'(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "lightbox cover-actions .lb-action-btn（enrichVideo(currentLightboxVideo)）button 區塊不存在"
        return m.group(0)

    def _gear_btn(self, html):
        """擷取 lightbox 番號旁 ⚙ gear 的完整 <button>...</button> 區塊。"""
        m = re.search(
            r'<button\b[^>]*?\bclass="lb-rescrape-gear".*?</button>',
            html, re.DOTALL,
        )
        assert m, "lightbox .lb-rescrape-gear ⚙ button 區塊不存在"
        return m.group(0)

    # ── 入口 1：lightbox 番號旁 ⚙ gear ──────────────────────────────────

    def test_gear_has_bi_gear_icon(self):
        """⚙ 入口必須用 bi-gear icon（CD-62-0 #4：magic 已被相似探索佔用）。"""
        html = self._html()
        # icon 緊接在 gear button 之後
        m = re.search(
            r'<button[^>]*\bclass="lb-rescrape-gear"[^>]*>\s*<i[^>]*\bbi-gear\b',
            html, re.DOTALL,
        )
        assert m, "⚙ gear button 內必須含 bi-gear icon"

    def test_gear_opens_rescrape_lightbox(self):
        """⚙ @click 必須呼叫 openRescrape(currentLightboxVideo, 'lightbox')（顯式傳當前影片，CD-62-2）。"""
        tag = self._gear_btn(self._html())
        m = re.search(r'@click(?:\.stop)?="([^"]*)"', tag)
        assert m, "⚙ gear button 缺 @click handler"
        assert "openRescrape(currentLightboxVideo, 'lightbox')" in m.group(1), \
            f"⚙ @click 必須 openRescrape(currentLightboxVideo, 'lightbox')，實際: {m.group(1)!r}"

    def test_gear_gated_by_rescrape_enabled(self):
        """⚙ 必須 x-show=rescrapeEnabled() gate（toggle OFF 時不顯示，決策 #1）。"""
        tag = self._gear_btn(self._html())
        m = re.search(r'x-show="([^"]*)"', tag)
        assert m, "⚙ gear button 缺 x-show gate"
        assert "rescrapeEnabled()" in m.group(1), \
            f"⚙ x-show 必須 gate by rescrapeEnabled()，實際: {m.group(1)!r}"

    def test_gear_tooltip_uses_i18n_key(self):
        """⚙ 的 aria-label / data-tooltip 走 i18n key，不硬編碼（i18n.md）。"""
        tag = self._gear_btn(self._html())
        assert "t('showcase.rescrape.entry_tooltip')" in tag, \
            "⚙ gear 必須用 t('showcase.rescrape.entry_tooltip') 作 aria-label / data-tooltip"
        # aria-label 必須存在於 gear tag（可及性）
        assert re.search(r':aria-label="[^"]*entry_tooltip', tag), \
            "⚙ gear 缺 :aria-label（可及性）"

    # ── 入口 2：grid 缺卡 enrich-btn 長壓 ───────────────────────────────

    def test_grid_enrich_tap_preserved_via_clickguard(self):
        """grid enrich-btn @click 仍走 enrichVideo（tap 路徑不移除），但前置 longPressClickGuard 分流。"""
        tag = self._grid_enrich_btn(self._html())
        m = re.search(r'@click(?:\.stop)?="([^"]*)"', tag)
        assert m, "grid enrich-btn 缺 @click handler"
        expr = m.group(1)
        assert "longPressClickGuard($event)" in expr, \
            f"grid enrich-btn @click 必須前置 longPressClickGuard($event)，實際: {expr!r}"
        assert "enrichVideo(video)" in expr, \
            f"grid enrich-btn tap 路徑（enrichVideo(video)）不得移除，實際: {expr!r}"

    def test_grid_enrich_longpress_events_wired(self):
        """grid enrich-btn 必須疊 6 長壓事件（鏡像 search.html）。"""
        tag = self._grid_enrich_btn(self._html())
        for ev in ("@mousedown", "@mouseup", "@mouseleave",
                   "@touchstart.passive", "@touchend", "@touchcancel"):
            assert ev in tag, f"grid enrich-btn 缺長壓事件 {ev}"

    def test_grid_longpress_routes_to_rescrape_enrich(self):
        """grid 長壓 callback 走 openRescrape(video, 'enrich')（不直接 enrichVideo），且 gate by rescrapeEnabled。"""
        tag = self._grid_enrich_btn(self._html())
        m = re.search(r'@mousedown="([^"]*)"', tag)
        assert m, "grid enrich-btn 缺 @mousedown"
        expr = m.group(1)
        assert "longPressStart(" in expr, f"grid @mousedown 必須呼叫 longPressStart，實際: {expr!r}"
        assert "openRescrape(video, 'enrich')" in expr, \
            f"grid 長壓 callback 必須 openRescrape(video, 'enrich')（不直接 enrichVideo），實際: {expr!r}"
        assert "rescrapeEnabled()" in expr, \
            f"grid 長壓 enabledFn 必須 gate by rescrapeEnabled()，實際: {expr!r}"

    # ── 入口 3：lightbox cover-actions 🔍 enrich-btn 長壓 ───────────────

    def test_lightbox_enrich_tap_preserved_via_clickguard(self):
        """lightbox 🔍 @click 仍走 enrichVideo(currentLightboxVideo)（tap 不移除），前置 longPressClickGuard。"""
        tag = self._lightbox_enrich_btn(self._html())
        m = re.search(r'@click(?:\.stop)?="([^"]*)"', tag)
        assert m, "lightbox 🔍 enrich-btn 缺 @click handler"
        expr = m.group(1)
        assert "longPressClickGuard($event)" in expr, \
            f"lightbox 🔍 @click 必須前置 longPressClickGuard($event)，實際: {expr!r}"
        assert "enrichVideo(currentLightboxVideo)" in expr, \
            f"lightbox 🔍 tap 路徑不得移除，實際: {expr!r}"

    def test_lightbox_enrich_longpress_events_wired(self):
        """lightbox 🔍 enrich-btn 必須疊 6 長壓事件。"""
        tag = self._lightbox_enrich_btn(self._html())
        for ev in ("@mousedown", "@mouseup", "@mouseleave",
                   "@touchstart.passive", "@touchend", "@touchcancel"):
            assert ev in tag, f"lightbox 🔍 enrich-btn 缺長壓事件 {ev}"

    def test_lightbox_longpress_routes_to_rescrape_enrich(self):
        """lightbox 🔍 長壓 callback 走 openRescrape(currentLightboxVideo, 'enrich')，gate by rescrapeEnabled。"""
        tag = self._lightbox_enrich_btn(self._html())
        m = re.search(r'@mousedown="([^"]*)"', tag)
        assert m, "lightbox 🔍 enrich-btn 缺 @mousedown"
        expr = m.group(1)
        assert "longPressStart(" in expr, f"lightbox 🔍 @mousedown 必須呼叫 longPressStart，實際: {expr!r}"
        assert "openRescrape(currentLightboxVideo, 'enrich')" in expr, \
            f"lightbox 🔍 長壓 callback 必須 openRescrape(currentLightboxVideo, 'enrich')，實際: {expr!r}"
        assert "rescrapeEnabled()" in expr, \
            f"lightbox 🔍 長壓 enabledFn 必須 gate by rescrapeEnabled()，實際: {expr!r}"

    # ── helper 檔 + mergeState 接線 ────────────────────────────────────

    def test_long_press_helper_exists(self):
        """shared/long-press.js 必須存在（決策 #2：獨立檔，62c-2 可引用）。"""
        assert self.LONG_PRESS_JS.exists(), \
            f"long-press.js missing at {self.LONG_PRESS_JS!s}"

    def test_long_press_exports_factory_and_methods(self):
        """long-press.js 必須 export function longPressState 並含通用契約 method。"""
        src = self.LONG_PRESS_JS.read_text(encoding="utf-8")
        assert re.search(r"export\s+function\s+longPressState\s*\(", src), \
            "long-press.js missing: export function longPressState()"
        for method in ("longPressStart", "longPressEnd", "longPressCancel",
                       "longPressClickGuard", "longPressReset"):
            assert method in src, f"long-press.js missing method: {method}"
        # 700ms 長壓常數（與 advanced-picker.js 對齊）
        assert "700" in src, "long-press.js missing LONG_PRESS_MS = 700"

    def test_main_js_imports_and_merges_long_press(self):
        """main.js 必須 import longPressState 並插入 mergeState 鏈（descriptor-preserving）。"""
        src = self.MAIN_JS.read_text(encoding="utf-8")
        assert "from '@/shared/long-press.js'" in src, \
            "main.js missing: import { longPressState } from '@/shared/long-press.js'"
        assert "longPressState.call(this)" in src, \
            "main.js mergeState chain missing: longPressState.call(this)"

    def test_rescrape_enabled_method_in_mixin(self):
        """state-rescrape.js 必須揭露 rescrapeEnabled() gate（決策 #1，三入口共用）。"""
        src = self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "rescrapeEnabled()" in src, \
            "state-rescrape.js missing rescrapeEnabled() method（決策 #1）"
        assert "window.__ADVANCED_SEARCH__" in src, \
            "rescrapeEnabled() 必須讀 window.__ADVANCED_SEARCH__.enabled"


class TestSearchRescrapeEntryGuard:
    """62c-1: 守衛 Search 進階搜尋入口改用 62a 共用重刮彈窗 contract。

    B1 radio picker（advancedPickerModal）已移除，改 include _rescrape_modal.html；
    search bar 送出鈕長壓 → openRescrape(null,'search') 開共用彈窗上半部（番號預填 searchQuery）；
    state-rescrape.js search 分支成功走 advancedSearch(source) 整包贏（不打 preview、不 fallbackSearch）。

    62c-2：#btnSubmit 六事件 + click guard 改接共用 shared/long-press.js（longPressState），
    main.js import + mergeState longPressState；form submit guard（advancedLongPressSubmitGuard）已移除，
    form 直接走 doSearch()。US8（長壓開窗不連帶送出一般搜尋）由 longPressClickGuard 的 preventDefault
    取消 submit 按鈕隱式 form 送出保護（方案 A）。advanced-picker.js 的整套 advancedLongPress* mixin 已移除。
    對齊 TestRescrapeStateGuard / TestRescrapeEntryGuard pattern（element-bound regex，避免假測試）。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    SEARCH_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search"
    STATE_RESCRAPE_JS = SHARED_DIR / "state-rescrape.js"
    SEARCH_MAIN_JS = SEARCH_DIR / "main.js"
    ADVANCED_PICKER_JS = SEARCH_DIR / "state" / "advanced-picker.js"

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _main(self):
        return self.SEARCH_MAIN_JS.read_text(encoding="utf-8")

    def _rescrape(self):
        return self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def _picker(self):
        return self.ADVANCED_PICKER_JS.read_text(encoding="utf-8")

    def _submit_btn(self, html):
        """擷取 search bar 送出鈕 #btnSubmit 的完整 <button>...</button> 區塊。"""
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bid="btnSubmit"(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "search.html #btnSubmit button 區塊不存在"
        return m.group(0)

    # ── (a) search main.js import + mergeState（rescrapeState + longPressState）──

    def test_search_main_imports_rescrape_state(self):
        """search main.js 必須 import rescrapeState 並插入 mergeState 鏈（descriptor-preserving）。"""
        src = self._main()
        assert "from '@/shared/state-rescrape.js'" in src, \
            "search main.js missing: import { rescrapeState } from '@/shared/state-rescrape.js'"
        assert re.search(r"rescrapeState\s*\(", src), \
            "search main.js mergeState chain missing: rescrapeState()"

    def test_search_main_imports_long_press_state(self):
        """62c-2（翻轉）：search main.js 必須 import longPressState + 併入 mergeState 鏈（descriptor-preserving）。

        62c-1 原斷言「不得 import longPressState」（留 62c-2）；本 task 兌現 — #btnSubmit 改接共用
        shared/long-press.js，故 main.js 必須 import 並 merge longPressState（CD-62-14 descriptor merge，禁 spread）。
        """
        src = self._main()
        assert "from '@/shared/long-press.js'" in src, \
            "62c-2：search main.js 必須 import { longPressState } from '@/shared/long-press.js'"
        assert re.search(r"longPressState\s*\(", src), \
            "62c-2：search main.js mergeState chain missing: longPressState()"

    # ── (b) search.html include 共用彈窗 + 長壓 wiring（共用 longPressState）──

    def test_search_html_includes_rescrape_modal(self):
        """search.html 必須 include _rescrape_modal.html（取代 B1 picker DOM）。"""
        html = self._html()
        assert "{% include '_rescrape_modal.html' %}" in html, \
            "62c-1 違規：search.html 未 include _rescrape_modal.html"

    def test_search_html_no_advanced_picker_modal(self):
        """負向：B1 advancedPickerModal DOM 整塊必須移除（CD-62-11，HTML 結構守衛）。"""
        html = self._html()
        for dead in ("advancedPickerModal", "advancedPickerConfirm",
                     "advancedPickerSelected", "advancedPickerClose",
                     "advancedPickerBuiltinSources", "advancedPickerMetatubeSources"):
            assert dead not in html, \
                f"62c-1 違規：search.html 仍殘留 B1 picker 引用 {dead}（應隨 DOM 移除）"

    def test_submit_btn_longpress_opens_rescrape_search(self):
        """62c-2（翻轉）：#btnSubmit 長壓 mousedown 改接共用 longPressStart，fire callback 開共用彈窗 + 番號預填。

        62c-1 原接 advancedLongPressStart()；62c-2 改接 shared helper longPressStart(cb, enabledFn)，
        cb 以 template arrow 傳入（openRescrape(null,'search') + rescrapeNumber 預填 searchQuery，US5-a），
        enabledFn 為 rescrapeEnabled()（toggle OFF gate）。
        """
        tag = self._submit_btn(self._html())
        m = re.search(r'@mousedown="([^"]*)"', tag)
        assert m, "#btnSubmit 缺 @mousedown 長壓 wiring"
        wiring = m.group(1)
        assert "longPressStart(" in wiring, \
            f"#btnSubmit @mousedown 必須接共用 longPressStart(...)（62c-2 rewire），實際: {wiring!r}"
        assert re.search(r"openRescrape\(\s*null\s*,\s*'search'\s*\)", wiring), \
            f"#btnSubmit @mousedown fire callback 必須開 openRescrape(null,'search')，實際: {wiring!r}"
        assert "searchQuery" in wiring, \
            f"#btnSubmit @mousedown fire callback 必須以 searchQuery 預填 rescrapeNumber（US5-a），實際: {wiring!r}"
        assert "rescrapeEnabled()" in wiring, \
            f"#btnSubmit @mousedown enabledFn 必須是 rescrapeEnabled()（toggle OFF gate），實際: {wiring!r}"

    def test_submit_btn_six_events_wired(self):
        """62c-2：#btnSubmit 六事件齊全且接共用 longPress*（mousedown/up/leave + touchstart.passive/end/cancel）。"""
        tag = self._submit_btn(self._html())
        assert re.search(r'@mousedown="longPressStart\(', tag), "#btnSubmit 缺 @mousedown longPressStart"
        assert re.search(r'@mouseup="longPressEnd\([^)]*\)"', tag), "#btnSubmit 缺 @mouseup longPressEnd()"
        assert re.search(r'@mouseleave="longPressCancel\([^)]*\)"', tag), "#btnSubmit 缺 @mouseleave longPressCancel()"
        assert re.search(r'@touchstart\.passive="longPressStart\(', tag), "#btnSubmit 缺 @touchstart.passive longPressStart"
        assert re.search(r'@touchend="longPressEnd\([^)]*\)"', tag), "#btnSubmit 缺 @touchend longPressEnd()"
        assert re.search(r'@touchcancel="longPressCancel\([^)]*\)"', tag), "#btnSubmit 缺 @touchcancel longPressCancel()"

    def test_submit_btn_click_guard_preserved(self):
        """62c-2（翻轉）：#btnSubmit @click 改走共用 longPressClickGuard（US8：preventDefault 取消隱式 form 送出）。"""
        tag = self._submit_btn(self._html())
        m = re.search(r'@click="([^"]*)"', tag)
        assert m, "#btnSubmit 缺 @click guard"
        assert "longPressClickGuard($event)" in m.group(1), \
            f"#btnSubmit @click 必須 longPressClickGuard($event)（62c-2 共用 helper），實際: {m.group(1)!r}"

    def test_form_submit_guard_removed(self):
        """62c-2（翻轉）：form submit guard 已移除，#searchForm @submit.prevent 直接走 doSearch()。

        62c-1 為「留給 62c-2」立 placeholder 斷言 submit guard 保留；本 task 兌現方案 A：
        US8 改由 longPressClickGuard 的 preventDefault 取消 submit 按鈕隱式 form 送出保護（路徑 A），
        form submit guard 對 US8 零貢獻（路徑 A 被 click 攔掉、路徑 C Enter 本就不設旗標）→ 移除誤導死碼。
        """
        html = self._html()
        m = re.search(r'<form\b[^>]*\bid="searchForm"[^>]*@submit\.prevent="([^"]*)"', html)
        assert m, "search.html #searchForm @submit.prevent guard 不存在"
        guard = m.group(1)
        assert "advancedLongPressSubmitGuard" not in guard, \
            f"62c-2：form @submit 不應再含 advancedLongPressSubmitGuard（已移除），實際: {guard!r}"
        assert "doSearch()" in guard, \
            f"62c-2：form @submit 應直接走 doSearch()，實際: {guard!r}"

    def test_search_html_no_advanced_long_press_wiring(self):
        """62c-2 負向：search.html 不應殘留任何 advancedLongPress* wiring（rewire 後全改共用 longPress*）。

        eslint 僅 lint web/static/js/**（search.html 無 JS eslint 管線），故「search.html 不應殘留
        advancedLongPress*」沿用 62c-1 test_search_html_no_advanced_picker_modal 的 fallback：pytest 讀 HTML 字串。
        """
        html = self._html()
        for dead in ("advancedLongPressStart", "advancedLongPressEnd", "advancedLongPressCancel",
                     "advancedLongPressClickGuard", "advancedLongPressSubmitGuard"):
            assert dead not in html, \
                f"62c-2 違規：search.html 仍殘留 {dead}（應全改接共用 shared/long-press.js）"

    # ── advanced-picker.js mixin 移除 ──

    def test_picker_long_press_mixin_removed(self):
        """62c-2（翻轉）：advanced-picker.js 整套 advancedLongPress* mixin + 旗標 + LONG_PRESS_MS 已移除。

        62c-1 fire body / submit guard / 旗標保留在 picker；62c-2 改接共用 shared/long-press.js
        （longPressState），fire callback 移到 template arrow → picker 不再有任何長壓 timer/guard/旗標。
        US8 由 longPressClickGuard preventDefault 保護（見 class docstring）。
        """
        src = self._picker()
        for dead in ("advancedLongPressStart", "advancedLongPressEnd", "advancedLongPressCancel",
                     "advancedLongPressClickGuard", "advancedLongPressSubmitGuard",
                     "_advancedLongPressFired", "_advancedLongPressTimer", "LONG_PRESS_MS"):
            assert dead not in src, \
                f"62c-2 違規：advanced-picker.js 仍殘留長壓死碼 {dead}（已改接共用 longPressState）"
        # 保留 advancedSearch 系本體
        assert re.search(r"async\s+advancedSearch\s*\(", src), \
            "advanced-picker.js 必須保留 advancedSearch(source) 本體"

    def test_picker_dead_methods_removed(self):
        """負向：B1 picker-modal 專屬 method（advancedPicker* / _advancedSortedSources）已移除。"""
        src = self._picker()
        for dead in ("advancedPickerOpen", "advancedPickerSelected", "advancedPickerClose",
                     "advancedPickerConfirm", "advancedPickerBuiltinSources",
                     "advancedPickerMetatubeSources", "_advancedSortedSources"):
            assert dead not in src, \
                f"62c-1 違規：advanced-picker.js 仍殘留死碼 {dead}（B1 picker DOM 已移除，應一併清除）"

    # ── (c) state-rescrape.js search 分支走 advancedSearch（不 preview、不 fallbackSearch）──

    def test_search_branch_uses_advanced_search(self):
        """state-rescrape.js search 分支成功路徑必須走 advancedSearch(（正向斷言新行為）。"""
        src = self._rescrape()
        # 提早分流：rescrapeEntryPoint === 'search' → advancedSearch
        assert "advancedSearch(" in src, \
            "state-rescrape.js search 分支必須走 this.advancedSearch(source)（整包贏進結果區）"
        assert re.search(r"rescrapeEntryPoint\s*===\s*'search'", src), \
            "state-rescrape.js 必須以 rescrapeEntryPoint === 'search' 分流"

    def test_search_branch_no_fallback_search(self):
        """負向（亦由 eslint Group 7 守）：search 分支禁 fallbackSearch（無 source 參數，US5 整包贏需 source）。"""
        src = self._rescrape()
        assert "fallbackSearch" not in src, \
            "state-rescrape.js 禁出現 fallbackSearch（誤接 search-flow.js 無 source 版本，違反 US5）"

    def test_bootstrap_include_not_regressed(self):
        """不回歸 62a-0：search.html 仍 include _advanced_search_bootstrap.html（SSR 注入）。"""
        html = self._html()
        assert "{% include '_advanced_search_bootstrap.html' %}" in html, \
            "62a-0 回歸：search.html 必須保留 _advanced_search_bootstrap.html include"


class TestSwitchSourcePickGuard:
    """62c-3 US7：守衛結果面板 🔄（#switchSourceBtn）長壓挑來源 wiring + entryPoint 分支 + 番號可編輯 + seeding helper export。

    tap=維持現有循環切換（switchSource）；長壓 700ms=開來源 picker（openSwitchSourcePicker，entryPoint
    'switch-source'，番號預填當前那一筆、可編輯（2026-05-31 放開唯讀））→ 點 pill → preview 重抓→ 只替換捕捉的當前卡 slot
    + seed cycle state（window.SearchUI.seedSwitchState）。race 安全 + cycle 同步走手動 checklist
    （async 時序無法靜態斷言）；負向「switch-source 分支禁 advancedSearch/fallbackSearch/searchResults =」
    走 eslint Group 7。本 class 只靜態斷言 wiring / 分支字串 / 番號可編輯 / export contract。
    對齊 TestSearchRescrapeEntryGuard pattern（element-bound regex，避免假測試）。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    SEARCH_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search"
    STATE_RESCRAPE_JS = SHARED_DIR / "state-rescrape.js"
    UI_JS = SEARCH_DIR / "ui.js"

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _modal(self):
        return RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")

    def _rescrape(self):
        return self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def _ui(self):
        return self.UI_JS.read_text(encoding="utf-8")

    def _switch_btn(self, html):
        """擷取結果面板 🔄 鈕 #switchSourceBtn 的完整 <button>...</button> 區塊。"""
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bid="switchSourceBtn"(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "search.html #switchSourceBtn button 區塊不存在"
        return m.group(0)

    # ── (a) #switchSourceBtn 長壓六事件 + click 分流（tap 維持循環）──

    def test_switch_btn_longpress_opens_picker(self):
        """#switchSourceBtn @mousedown 長壓接共用 longPressStart，fire callback 開 openSwitchSourcePicker()。"""
        tag = self._switch_btn(self._html())
        m = re.search(r'@mousedown="([^"]*)"', tag)
        assert m, "#switchSourceBtn 缺 @mousedown 長壓 wiring"
        wiring = m.group(1)
        assert "longPressStart(" in wiring, \
            f"#switchSourceBtn @mousedown 必須接共用 longPressStart(...)，實際: {wiring!r}"
        assert "openSwitchSourcePicker()" in wiring, \
            f"#switchSourceBtn @mousedown fire callback 必須開 openSwitchSourcePicker()，實際: {wiring!r}"
        assert "rescrapeEnabled()" in wiring, \
            f"#switchSourceBtn @mousedown enabledFn 必須是 rescrapeEnabled()（toggle OFF gate），實際: {wiring!r}"

    def test_switch_btn_six_events_wired(self):
        """#switchSourceBtn 六事件齊全且接共用 longPress*（mousedown/up/leave + touchstart.passive/end/cancel）。"""
        tag = self._switch_btn(self._html())
        assert re.search(r'@mousedown="longPressStart\(', tag), "#switchSourceBtn 缺 @mousedown longPressStart"
        assert re.search(r'@mouseup="longPressEnd\([^)]*\)"', tag), "#switchSourceBtn 缺 @mouseup longPressEnd()"
        assert re.search(r'@mouseleave="longPressCancel\([^)]*\)"', tag), "#switchSourceBtn 缺 @mouseleave longPressCancel()"
        assert re.search(r'@touchstart\.passive="longPressStart\(', tag), "#switchSourceBtn 缺 @touchstart.passive longPressStart"
        assert re.search(r'@touchend="longPressEnd\([^)]*\)"', tag), "#switchSourceBtn 缺 @touchend longPressEnd()"
        assert re.search(r'@touchcancel="longPressCancel\([^)]*\)"', tag), "#switchSourceBtn 缺 @touchcancel longPressCancel()"

    def test_switch_btn_touchstart_opens_picker(self):
        """#switchSourceBtn @touchstart.passive fire callback 同樣開 openSwitchSourcePicker()（mousedown/touchstart 一致）。"""
        tag = self._switch_btn(self._html())
        m = re.search(r'@touchstart\.passive="([^"]*)"', tag)
        assert m, "#switchSourceBtn 缺 @touchstart.passive 長壓 wiring"
        assert "openSwitchSourcePicker()" in m.group(1), \
            f"#switchSourceBtn @touchstart.passive fire callback 必須開 openSwitchSourcePicker()，實際: {m.group(1)!r}"

    def test_switch_btn_click_guard_preserves_switch_source(self):
        """#switchSourceBtn @click 走 longPressClickGuard($event) || switchSource()（tap 維持循環，長壓 fire 後短路）。"""
        tag = self._switch_btn(self._html())
        m = re.search(r'@click="([^"]*)"', tag)
        assert m, "#switchSourceBtn 缺 @click 分流"
        guard = m.group(1)
        assert "longPressClickGuard($event)" in guard, \
            f"#switchSourceBtn @click 必須 longPressClickGuard($event)（長壓短路），實際: {guard!r}"
        assert "switchSource()" in guard, \
            f"#switchSourceBtn @click 必須保留 switchSource()（tap 循環不回歸），實際: {guard!r}"

    def test_open_source_url_btn_not_touched(self):
        """負向（§1.6 D）：長壓只疊 #switchSourceBtn，旁邊 ↗ openSourceUrl 鈕不得沾長壓 wiring。"""
        html = self._html()
        m = re.search(r'@click="openSourceUrl\([^"]*\)"\s*[^>]*?</button>', html, re.DOTALL)
        # 直接擷取 openSourceUrl 鈕區塊比對：不含 longPress* / openSwitchSourcePicker
        m2 = re.search(
            r'<button\b(?:(?!</button>).)*?openSourceUrl(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m2, "search.html openSourceUrl ↗ 鈕區塊不存在"
        url_btn = m2.group(0)
        for forbidden in ("longPressStart", "longPressEnd", "longPressCancel",
                          "longPressClickGuard", "openSwitchSourcePicker"):
            assert forbidden not in url_btn, \
                f"§1.6 D 違規：↗ openSourceUrl 鈕誤接 {forbidden}（長壓只疊 #switchSourceBtn）"

    # ── (b) _rescrape_modal.html 番號 input 永遠可編輯（含 switch-source 入口）──

    def test_number_input_editable_in_all_entry_points(self):
        """_rescrape_modal.html 番號 input 不得有 switch-source 唯讀綁定。

        2026-05-31 修訂：原 US7 拍板#1 鎖 switch-source 唯讀，後因「拖入檔名解析錯 → 無結果 →
        想在當前卡改正番號重抓」的真實工作流放開。番號在所有入口（lightbox/enrich/search/switch-source）
        皆可編輯。此守衛防回歸：禁止任何 readonly 綁定重新出現在番號 input 上。
        """
        modal = self._modal()
        m = re.search(
            r'<input\b(?:(?!>).)*?\bclass="rescrape-num-input"(?:(?!>).)*?>',
            modal, re.DOTALL,
        )
        assert m, "_rescrape_modal.html 番號 input（.rescrape-num-input）不存在"
        inp = m.group(0)
        assert not re.search(r"(?::readonly|\breadonly)\b", inp), \
            f"番號 input 不得含 readonly / :readonly 綁定（所有入口皆可編輯番號，含 switch-source），實際: {inp!r}"

    # ── (c) state-rescrape.js openSwitchSourcePicker + switch-source 分支 + 註解 ──

    def test_open_switch_source_picker_method_present(self):
        """state-rescrape.js 必須有 openSwitchSourcePicker method（開窗 + 捕捉 _switchTarget）。"""
        src = self._rescrape()
        assert re.search(r"openSwitchSourcePicker\s*\(\s*\)\s*\{", src), \
            "state-rescrape.js 缺 openSwitchSourcePicker() method"
        assert re.search(r"openRescrape\(\s*null\s*,\s*'switch-source'\s*\)", src), \
            "openSwitchSourcePicker 必須 openRescrape(null,'switch-source')"
        assert "_switchTarget" in src, \
            "state-rescrape.js 必須捕捉 _switchTarget（race 防覆蓋錯卡）"

    def test_switch_source_branch_present(self):
        """state-rescrape.js rescrapeWithSource 含 'switch-source' 分支（preview 成功 → 替 slot + seed + close）。"""
        src = self._rescrape()
        assert re.search(r"rescrapeEntryPoint\s*===\s*'switch-source'", src), \
            "state-rescrape.js 必須以 rescrapeEntryPoint === 'switch-source' 分流"
        assert "seedSwitchState" in src, \
            "switch-source 分支必須呼叫 window.SearchUI.seedSwitchState（鎖定#4 cycle 同步）"

    def test_entry_point_comment_lists_switch_source(self):
        """rescrapeEntryPoint 宣告註解必須列出 'switch-source'（與 'lightbox'/'enrich'/'search' 並列）。"""
        src = self._rescrape()
        m = re.search(r"rescrapeEntryPoint\s*:\s*'lightbox'\s*,\s*//([^\n]*)", src)
        assert m, "state-rescrape.js rescrapeEntryPoint 宣告（含行末註解）不存在"
        assert "switch-source" in m.group(1), \
            f"rescrapeEntryPoint 註解必須列出 'switch-source'，實際: {m.group(1)!r}"

    # ── (d) ui.js seedSwitchState export（window.SearchUI）──

    def test_ui_exports_seed_switch_state(self):
        """ui.js 必須 export seedSwitchState 於 window.SearchUI（picker 經此 seed，不直接戳 switchStateMap）。"""
        src = self._ui()
        assert re.search(r"function\s+seedSwitchState\s*\(", src), \
            "ui.js 缺 seedSwitchState 函式定義（鎖定#4 seeding helper）"
        m = re.search(r"window\.SearchUI\s*=\s*\{([^}]*)\}", src, re.DOTALL)
        assert m, "ui.js window.SearchUI export 物件不存在"
        assert "seedSwitchState" in m.group(1), \
            f"window.SearchUI 必須 export seedSwitchState，實際 export: {m.group(1)!r}"


class TestDesignSystemLongPressCard:
    """62c-2 (b)：/design-system 登記 long-press 互動 pattern demo card（D.14）。

    與 D.13 Source Pill card 同批登記、同 #ds-settings-components section（settings-components.html）。
    對齊既有 design-system 守衛慣例（test_design_system_no_inline_bg_card_pattern 等）：HTML 字串斷言走 pytest
    （design-system 是 HTML template、無 HTML eslint 管線）。正向：card 存在 + 引用 longPressState/long-press + 700ms。
    負向（CD-62-0 #7 §7.4）：card 刻意無 hold-progress 進度環 / progress-ring / data-tooltip affordance。
    """

    SETTINGS_COMPONENTS_HTML = (
        Path(__file__).parent.parent.parent / "web" / "templates"
        / "design_system" / "settings-components.html"
    )

    def _html(self):
        return self.SETTINGS_COMPONENTS_HTML.read_text(encoding="utf-8")

    def test_long_press_card_present(self):
        """settings-components.html 含 long-press demo card（標題 + longPressStart/long-press 引用 + 700ms）。"""
        html = self._html()
        assert "Long-press" in html, "design-system 缺 long-press demo card 標題（Long-press）"
        assert "longPressStart" in html, "long-press demo card 必須引用共用 helper longPressStart"
        assert "long-press.js" in html, "long-press demo card 必須引用 shared/long-press.js"
        assert "700" in html, "long-press demo card 必須標出 700ms 長壓門檻"

    def test_long_press_card_no_progress_ring_or_tooltip(self):
        """負向（CD-62-0 #7 §7.4）：long-press card 不得含 hold-progress / progress-ring / data-tooltip affordance。"""
        html = self._html()
        for forbidden in ("hold-progress", "progress-ring", "data-tooltip"):
            assert forbidden not in html, \
                f"long-press demo card 不應含 {forbidden}（刻意無進度環 / 無 tooltip，CD-62-0 #7）"


class TestLongPressTouchSuppression:
    """TASK-62c-7（Codex PR#47 P2，選項 A）：touch synthetic-mouse race 硬化。

    long-press.js：touchend/touchcancel 記 monotonic timestamp（_lpSuppressMouseUntil = performance.now()+700），
    抑制窗內的 synthetic mousedown 在 longPressStart 開頭 early-return（不清 _lpFired → 後續 synthetic click
    的 guard 仍能吞掉 → 不雙觸發）。四長壓入口的 @mousedown/@touchstart wiring 必須傳 $event，
    @touchend 必須 longPressEnd($event)（否則 helper 收不到 event.type 判斷）。
    靜態 element-bound 守衛（pytest 跑不了 JS synthetic event；真機行為走 card 手動 checklist）。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    LONG_PRESS_JS = SHARED_DIR / "long-press.js"

    def _js(self):
        return self.LONG_PRESS_JS.read_text(encoding="utf-8")

    def _search_html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def _showcase_html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    # ── (a) long-press.js helper 機制 ────────────────────────────────────

    def test_helper_has_suppress_state(self):
        """long-press.js 必須宣告 _lpSuppressMouseUntil state（與 _lpTimer/_lpFired 並列，初值 0）。"""
        src = self._js()
        assert re.search(r'_lpSuppressMouseUntil\s*:\s*0', src), \
            "long-press.js 缺 _lpSuppressMouseUntil: 0 state（touchend 抑制窗截止時間）"

    def test_helper_longpressstart_takes_event_and_early_returns(self):
        """longPressStart 必須收 event 第三參，synthetic mousedown 在抑制窗內 early-return（在 _lpFired reset 之前）。"""
        src = self._js()
        m = re.search(r'longPressStart\(cb,\s*enabledFn,\s*event\)\s*\{(.*?)\n        \},', src, re.DOTALL)
        assert m, "longPressStart 必須宣告第三參數 event（longPressStart(cb, enabledFn, event)）"
        body = m.group(1)
        # early-return 條件：mousedown + 抑制窗未過
        guard = re.search(
            r"if\s*\(\s*event\s*&&\s*event\.type\s*===\s*'mousedown'\s*&&\s*performance\.now\(\)\s*<\s*this\._lpSuppressMouseUntil\s*\)\s*\{?\s*return",
            body,
        )
        assert guard, \
            "longPressStart 開頭必須有 synthetic mousedown 抑制 early-return（event.type==='mousedown' && performance.now() < this._lpSuppressMouseUntil → return）"
        # early-return 必在 _lpFired = false reset 之前（否則旗標已被清）。
        # 比對「實際賦值語句」（行尾分號），避免抓到 docstring/註解裡提及的 this._lpFired = false reset 字樣。
        reset_m = re.search(r'this\._lpFired\s*=\s*false\s*;', body)
        assert reset_m, "longPressStart body 缺 this._lpFired = false; reset 賦值"
        assert guard.start() < reset_m.start(), \
            "synthetic mousedown early-return 必須在 this._lpFired = false reset 之前（否則旗標已被清）"

    def test_helper_longpressend_sets_window_on_touchend(self):
        """longPressEnd 必須收 event 參，touchend 時設 _lpSuppressMouseUntil = performance.now() + (窗)。"""
        src = self._js()
        m = re.search(r'longPressEnd\(event\)\s*\{(.*?)\n        \},', src, re.DOTALL)
        assert m, "longPressEnd 必須宣告 event 參數（longPressEnd(event)）"
        body = m.group(1)
        assert re.search(
            r"event\s*&&\s*event\.type\s*===\s*'touchend'", body), \
            "longPressEnd 必須判斷 event.type === 'touchend'"
        assert re.search(
            r"this\._lpSuppressMouseUntil\s*=\s*performance\.now\(\)\s*\+", body), \
            "longPressEnd(touchend) 必須設 this._lpSuppressMouseUntil = performance.now() + 窗"

    def test_helper_longpresscancel_sets_window_on_touchcancel(self):
        """longPressCancel 必須收 event 參，touchcancel 時設 _lpSuppressMouseUntil = performance.now() + (窗)。"""
        src = self._js()
        m = re.search(r'longPressCancel\(event\)\s*\{(.*?)\n        \},', src, re.DOTALL)
        assert m, "longPressCancel 必須宣告 event 參數（longPressCancel(event)）"
        body = m.group(1)
        assert re.search(
            r"event\s*&&\s*event\.type\s*===\s*'touchcancel'", body), \
            "longPressCancel 必須判斷 event.type === 'touchcancel'"
        assert re.search(
            r"this\._lpSuppressMouseUntil\s*=\s*performance\.now\(\)\s*\+", body), \
            "longPressCancel(touchcancel) 必須設 this._lpSuppressMouseUntil = performance.now() + 窗"

    # ── (b) 四入口 wiring 傳 $event（element-bound）─────────────────────

    def _submit_btn(self, html):
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bid="btnSubmit"(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "search.html #btnSubmit button 區塊不存在"
        return m.group(0)

    def _switch_btn(self, html):
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bid="switchSourceBtn"(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "search.html #switchSourceBtn button 區塊不存在"
        return m.group(0)

    def _grid_enrich_btn(self, html):
        m = re.search(
            r'<button\b[^>]*?\bclass="btn-glass-circle enrich-btn".*?</button>',
            html, re.DOTALL,
        )
        assert m, "showcase grid .btn-glass-circle.enrich-btn button 區塊不存在"
        return m.group(0)

    def _lightbox_enrich_btn(self, html):
        m = re.search(
            r'<button\b(?:(?!</button>).)*?\bclass="lb-action-btn"'
            r'(?:(?!</button>).)*?enrichVideo\(currentLightboxVideo\)'
            r'(?:(?!</button>).)*?</button>',
            html, re.DOTALL,
        )
        assert m, "showcase lightbox .lb-action-btn（enrichVideo(currentLightboxVideo)）button 區塊不存在"
        return m.group(0)

    def _assert_entry_passes_event(self, tag, label):
        """element-bound：@mousedown/@touchstart longPressStart 傳 $event；@touchend longPressEnd($event)。"""
        md = re.search(r'@mousedown="(longPressStart\([^"]*)"', tag)
        assert md and '$event)' in md.group(1), \
            f"{label} @mousedown longPressStart 必須傳 $event，實際: {md.group(1) if md else None!r}"
        ts = re.search(r'@touchstart\.passive="(longPressStart\([^"]*)"', tag)
        assert ts and '$event)' in ts.group(1), \
            f"{label} @touchstart.passive longPressStart 必須傳 $event，實際: {ts.group(1) if ts else None!r}"
        assert re.search(r'@touchend="longPressEnd\(\$event\)"', tag), \
            f"{label} @touchend 必須 longPressEnd($event)"
        assert re.search(r'@touchcancel="longPressCancel\(\$event\)"', tag), \
            f"{label} @touchcancel 必須 longPressCancel($event)"

    def test_search_submit_btn_passes_event(self):
        self._assert_entry_passes_event(self._submit_btn(self._search_html()), "#btnSubmit")

    def test_switch_source_btn_passes_event(self):
        self._assert_entry_passes_event(self._switch_btn(self._search_html()), "#switchSourceBtn")

    def test_grid_enrich_btn_passes_event(self):
        self._assert_entry_passes_event(self._grid_enrich_btn(self._showcase_html()), "grid enrich-btn")

    def test_lightbox_enrich_btn_passes_event(self):
        self._assert_entry_passes_event(self._lightbox_enrich_btn(self._showcase_html()), "lightbox enrich-btn")


class TestScannerXShowCssConflictGuard:
    """
    防止 .manual-input / .done-actions 改回裸 x-show。
    這兩個元素的 CSS 有（命中 scanner 的）display:none，Alpine x-show 顯示時
    只移除 inline style、無法覆蓋 CSS none → 面板永遠隱藏。必須用 :style binding
    直接注入 display 值。參見 TASK-62-scanner-manual-input-xshow.md（根因 commit a3a4da4）。
    """

    SCANNER_HTML = Path("web/templates/scanner.html").read_text(encoding="utf-8")

    @staticmethod
    def _tag_with_class(html, class_name):
        """抽出含指定 class 的 <div> 開標籤，斷言綁定綁到正確元素（Codex P2）。

        class 邊界用 (?<![\\w-]) / (?![\\w-]) 而非 \\b：`-` 是 \\W，\\b 會讓
        `manual-input` 誤命中 `manual-input-extra`（reviewer N1）。
        """
        m = re.search(
            rf'<div\b(?=[^>]*class="[^"]*(?<![\w-]){re.escape(class_name)}(?![\w-])[^"]*")[^>]*>',
            html,
        )
        assert m, f"missing .{class_name} div in scanner.html"
        return m.group(0)

    def test_manual_input_style_binding_on_element(self):
        tag = self._tag_with_class(self.SCANNER_HTML, "manual-input")
        # 負向：該 tag 不可有裸 x-show（會被 CSS display:none 蓋掉）
        assert 'x-show=' not in tag, \
            ".manual-input 不可用裸 x-show（會被 CSS display:none 覆蓋）→ 改 :style binding"
        # 正向：該 tag 必須有完整 ternary :style 綁定
        assert re.search(
            r":style=\"\{\s*display:\s*manualInputVisible\s*\?\s*'flex'\s*:\s*'none'\s*\}\"",
            tag,
        ), ".manual-input 應為 :style=\"{ display: manualInputVisible ? 'flex' : 'none' }\""

    def test_done_actions_style_binding_on_element(self):
        tag = self._tag_with_class(self.SCANNER_HTML, "done-actions")
        assert 'id="doneActions"' in tag, "確認命中同一個 done-actions tag"
        assert 'x-show=' not in tag, \
            ".done-actions 不可用裸 x-show（會被 CSS display:none 覆蓋）→ 改 :style binding"
        assert re.search(
            r":style=\"\{\s*display:\s*doneActionsVisible\s*\?\s*'flex'\s*:\s*'none'\s*\}\"",
            tag,
        ), ".done-actions 應為 :style=\"{ display: doneActionsVisible ? 'flex' : 'none' }\""


class TestMetatubeB3Guard:
    """CD-63b-3: 守衛 state-config.js STUB 已移除 + 真實 HTTP 已接線 + helpers 已加入 + settings.html 已更新。"""

    SETTINGS_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    SETTINGS_HTML = PROJECT_ROOT / "web" / "templates" / "settings.html"

    def _js(self) -> str:
        return self.SETTINGS_JS.read_text(encoding="utf-8")

    def _html(self) -> str:
        return self.SETTINGS_HTML.read_text(encoding="utf-8")

    def test_stub_connect_removed(self):
        """B2: STUB connect 字串已從 state-config.js 移除。"""
        js = self._js()
        assert "STUB connect" not in js, (
            "CD-63b-3 違規：state-config.js 仍含 'STUB connect' — B3 應已替換為真實 fetch"
        )

    def test_stub_disconnect_removed(self):
        """B3: STUB disconnect 字串已從 state-config.js 移除。"""
        js = self._js()
        assert "STUB disconnect" not in js, (
            "CD-63b-3 違規：state-config.js 仍含 'STUB disconnect' — B3 應已替換為真實 fetch"
        )

    def test_connect_uses_real_fetch(self):
        """B2: metatubeConnect() 使用真實 POST /api/settings/metatube/connect。"""
        js = self._js()
        assert "'/api/settings/metatube/connect'" in js, (
            "CD-63b-3 違規：state-config.js 缺少 '/api/settings/metatube/connect' fetch 呼叫"
        )

    def test_disconnect_uses_real_fetch(self):
        """B3: metatubeDisconnect() 使用真實 POST /api/settings/metatube/disconnect。"""
        js = self._js()
        assert "'/api/settings/metatube/disconnect'" in js, (
            "CD-63b-3 違規：state-config.js 缺少 '/api/settings/metatube/disconnect' fetch 呼叫"
        )

    def test_start_probe_polling_present(self):
        """B4: startProbePolling helper 已加入 state-config.js。"""
        js = self._js()
        assert "startProbePolling" in js, (
            "CD-63b-3 違規：state-config.js 缺少 startProbePolling 方法"
        )

    def test_stop_probe_polling_present(self):
        """B4: stopProbePolling helper 已加入 state-config.js。"""
        js = self._js()
        assert "stopProbePolling" in js, (
            "CD-63b-3 違規：state-config.js 缺少 stopProbePolling 方法"
        )

    def test_hydrate_metatube_status_present(self):
        """B5: hydrateMetatubeStatus helper 已加入 state-config.js。"""
        js = self._js()
        assert "hydrateMetatubeStatus" in js, (
            "CD-63b-3 違規：state-config.js 缺少 hydrateMetatubeStatus 方法"
        )

    def test_on_metatube_enabled_change_present(self):
        """B7: onMetatubeEnabledChange 已加入 state-config.js。"""
        js = self._js()
        assert "onMetatubeEnabledChange" in js, (
            "CD-63b-3 違規：state-config.js 缺少 onMetatubeEnabledChange 方法"
        )

    def test_settings_html_has_metatube_lan_mode(self):
        """C2: settings.html 含 metatubeLanMode 綁定（LAN checkbox）。"""
        html = self._html()
        assert "metatubeLanMode" in html, (
            "CD-63b-3 違規：settings.html 缺少 metatubeLanMode 綁定（LAN mode checkbox）"
        )

    def test_settings_html_has_metatube_connecting(self):
        """C2: settings.html 含 metatubeConnecting 綁定（connect button loading state）。"""
        html = self._html()
        assert "metatubeConnecting" in html, (
            "CD-63b-3 違規：settings.html 缺少 metatubeConnecting 綁定（button loading state）"
        )

    def test_settings_html_has_metatube_enable_toggle(self):
        """C1: settings.html 含 metatubeEnableToggle ID（Advanced tab toggle）。"""
        html = self._html()
        assert "metatubeEnableToggle" in html, (
            "CD-63b-3 違規：settings.html 缺少 metatubeEnableToggle（Advanced tab 啟用開關）"
        )


class TestMetatubeB4Guard:
    """CD-63b-4: 守衛 probe UI 視覺層（進度列 / retest button / hint details / grey-out）。"""

    SETTINGS_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    SETTINGS_HTML = PROJECT_ROOT / "web" / "templates" / "settings.html"

    def _js(self) -> str:
        return self.SETTINGS_JS.read_text(encoding="utf-8")

    def _html(self) -> str:
        return self.SETTINGS_HTML.read_text(encoding="utf-8")

    def test_html_has_mt_probe_testing_key(self):
        """B1: settings.html 含 mt_probe_testing i18n key（進度列文字）。"""
        html = self._html()
        assert "mt_probe_testing" in html, (
            "CD-63b-4 違規：settings.html 缺少 mt_probe_testing 文字 key（probe 進度列）"
        )

    def test_html_has_metatube_retest_call(self):
        """B2: settings.html 含 metatubeRetest() 呼叫（retest button）。"""
        html = self._html()
        assert "metatubeRetest" in html, (
            "CD-63b-4 違規：settings.html 缺少 metatubeRetest() 呼叫（retest button）"
        )

    def test_html_has_mt_probe_hint_title_key(self):
        """B3: settings.html 含 mt_probe_hint_title i18n key（hint details summary）。"""
        html = self._html()
        assert "mt_probe_hint_title" in html, (
            "CD-63b-4 違規：settings.html 缺少 mt_probe_hint_title key（probe-hint details）"
        )

    def test_html_has_data_available_binding(self):
        """B4: settings.html 含 :data-available 綁定（Parts Bin pill grey-out mechanism）。"""
        html = self._html()
        assert "data-available" in html, (
            "CD-63b-4 違規：settings.html 缺少 :data-available 綁定（probe-failed grey-out）"
        )

    def test_js_has_metatube_retest(self):
        """A1: state-config.js 含 metatubeRetest 方法定義。"""
        js = self._js()
        assert "metatubeRetest" in js, (
            "CD-63b-4 違規：state-config.js 缺少 metatubeRetest 方法"
        )

    def test_js_has_start_probe_polling(self):
        """A1: state-config.js 含 startProbePolling（metatubeRetest 呼叫的 helper）。"""
        js = self._js()
        assert "startProbePolling" in js, (
            "CD-63b-4 違規：state-config.js 缺少 startProbePolling 方法"
        )

    def test_js_promote_metatube_has_available_check(self):
        """A2: state-config.js promoteMetatube 含 available === false 檢查（probe-failed 警告）。"""
        js = self._js()
        assert "s.available === false" in js, (
            "CD-63b-4 違規：state-config.js promoteMetatube 缺少 s.available === false guard"
        )

    def test_js_promote_metatube_has_unavailable_warning_key(self):
        """A2: state-config.js promoteMetatube 含 mt_promote_unavailable_warning toast key。"""
        js = self._js()
        assert "mt_promote_unavailable_warning" in js, (
            "CD-63b-4 違規：state-config.js 缺少 mt_promote_unavailable_warning toast key"
        )


class TestMetatubeB5RecommendedRemoved:
    """CD-63b-7: 守衛靜態 Recommended 群組殘留已徹底拔除。

    「廢棄 feature 拔除要徹底」memory：不留殭屍命名 / 群組頭 / 星標 / i18n key。
    """

    SETTINGS_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    SETTINGS_HTML = PROJECT_ROOT / "web" / "templates" / "settings.html"
    SOURCE_PILL_CSS = PROJECT_ROOT / "web" / "static" / "css" / "components" / "source-pill.css"
    SETTINGS_CSS = PROJECT_ROOT / "web" / "static" / "css" / "pages" / "settings.css"
    ZH_TW = PROJECT_ROOT / "locales" / "zh_TW.json"

    def test_settings_html_no_recommended_filter(self):
        html = self.SETTINGS_HTML.read_text(encoding="utf-8")
        assert "s.recommended" not in html, (
            "CD-63b-7 違規：settings.html 仍含 s.recommended（Recommended filter 應已拔除，flat loop 取代）"
        )

    def test_settings_html_no_recommended_i18n_keys(self):
        html = self.SETTINGS_HTML.read_text(encoding="utf-8")
        assert "mt_recommended_label" not in html and "mt_other_label" not in html, (
            "CD-63b-7 違規：settings.html 仍含 mt_recommended_label / mt_other_label（群組頭已拔）"
        )

    def test_settings_html_no_group_head_class(self):
        html = self.SETTINGS_HTML.read_text(encoding="utf-8")
        assert "settings-mt-group-head" not in html, (
            "CD-63b-7 違規：settings.html 仍含 settings-mt-group-head（群組頭 class 已拔）"
        )

    def test_state_config_no_recommended_mock_field(self):
        js = self.SETTINGS_JS.read_text(encoding="utf-8")
        assert "recommended:" not in js and "recommended: i < 4" not in js, (
            "CD-63b-7 違規：state-config.js mock 仍含 recommended 欄位"
        )

    def test_source_pill_css_no_rec_star(self):
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        assert ".rec-star" not in css, (
            "CD-63b-7 違規：source-pill.css 仍含 .rec-star 規則（星標已拔）"
        )

    def test_settings_css_no_group_head(self):
        css = self.SETTINGS_CSS.read_text(encoding="utf-8")
        assert "settings-mt-group-head" not in css, (
            "CD-63b-7 違規：settings.css 仍含 .settings-mt-group-head 規則（用途消失應移除）"
        )

    def test_zh_tw_no_recommended_label_keys(self):
        data = json.loads(self.ZH_TW.read_text(encoding="utf-8"))
        sources = data.get("settings", {}).get("sources", {})
        assert "mt_recommended_label" not in sources and "mt_other_label" not in sources, (
            "CD-63b-7 違規：zh_TW.json settings.sources 仍含 mt_recommended_label / mt_other_label"
        )


class TestMetatubeB6I18n:
    """CD-63b-6 / CD-63b-8: 63b 新 UI 文字 key 存在於 zh_TW.json（其他 3 locale 待 milestone）。"""

    ZH_TW = PROJECT_ROOT / "locales" / "zh_TW.json"

    NEW_KEYS = [
        "mt_enable_label", "mt_enable_help", "mt_lan_mode_label",
        "mt_connecting_btn", "mt_connect_network_error", "mt_connect_success_toast",
        "mt_probe_testing", "mt_retest_btn",
        "mt_probe_hint_title", "mt_probe_hint_reason1",
        "mt_probe_hint_reason2", "mt_probe_hint_reason3",
        "mt_promote_unavailable_warning",
    ]

    def _sources(self) -> dict:
        data = json.loads(self.ZH_TW.read_text(encoding="utf-8"))
        return data.get("settings", {}).get("sources", {})

    def test_all_new_keys_exist_and_nonempty(self):
        sources = self._sources()
        for key in self.NEW_KEYS:
            assert sources.get(key), f"CD-63b-6 違規：zh_TW.json settings.sources 缺 {key!r} 或為空"

    def test_tier_hint_no_recommended_mention(self):
        """CD-63b-8: mt_connected_tier_hint 已移除 ⭐ / 建議起手 提及。"""
        hint = self._sources().get("mt_connected_tier_hint", "")
        assert "⭐" not in hint and "建議起手" not in hint, (
            "CD-63b-8 違規：mt_connected_tier_hint 仍含 Recommended 星標 / 建議起手 文案"
        )


# ─── 63c-3: 進階 picker 接 metatube 真資料（routable / available / proxy_configured 注入）───
class TestMetatubePickerWiringGuard:
    """63c-3: bootstrap 注入 proxy_configured + state-rescrape.js routable gate 保留 +
    _rescrape_modal.html metatube 分組未被刪除（驗 B1 data-driven 分組仍在）。

    routable/available 隨 config.sources|tojson 自動帶出（不在 template 逐欄寫），
    故守衛綁在 state-rescrape.js 的 routable gate 與後端注入（後端走 integration test）。
    """

    STATE_RESCRAPE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "state-rescrape.js"

    def _bootstrap(self):
        return ADV_SEARCH_BOOTSTRAP.read_text(encoding="utf-8")

    def _modal(self):
        return RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")

    def _state_rescrape(self):
        return self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def test_bootstrap_injects_proxy_configured(self):
        """_advanced_search_bootstrap.html 含 proxy_configured 注入行（63c-3/63c-6 Surface 2）。"""
        assert "proxy_configured:" in self._bootstrap(), (
            "63c-3 違規：bootstrap 缺少 proxy_configured 注入行"
        )

    def test_state_rescrape_keeps_routable_gate(self):
        """rescrapeMetatubeSources() 保留 s.routable === true gate（斷線 metatube 不長 stale pill）。"""
        src = self._state_rescrape()
        assert "rescrapeMetatubeSources" in src, "63c-3 違規：缺 rescrapeMetatubeSources()"
        assert "routable === true" in src, (
            "63c-3 違規：rescrapeMetatubeSources 應保留 routable === true gate"
        )
        assert "s.type === 'metatube'" in src, (
            "63c-3 違規：rescrapeMetatubeSources 應 filter type === 'metatube'"
        )

    def test_modal_metatube_grouping_present(self):
        """_rescrape_modal.html 保留 metatube 分組渲染（rescrapeMetatubeSources 驅動，B1 分組未被刪）。"""
        html = self._modal()
        assert "rescrapeMetatubeSources()" in html, (
            "63c-3 違規：_rescrape_modal.html 缺 metatube 分組（rescrapeMetatubeSources 引用）"
        )


# ─── 63c-6: DMM requires_proxy 灰化（兩 surface） ───
class TestDmmProxyRequiredGuard:
    """63c-6: DMM requires_proxy 灰化 — Surface 1（Settings Active Row）+ Surface 2（rescrape picker）。

    Frontend-guard 強度：每個斷言都綁到具體元素/屬性，而非對整檔做字串存在性檢查。
    gotchas.md 「字串存在性 ≠ contract」：先 regex 擷取目標元素的 tag 範圍，再在 tag 範圍內斷言。
    """

    SETTINGS_CONFIG_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    SETTINGS_HTML      = PROJECT_ROOT / "web" / "templates" / "settings.html"
    STATE_RESCRAPE_JS  = PROJECT_ROOT / "web" / "static" / "js" / "shared" / "state-rescrape.js"
    RESCRAPE_MODAL_HTML = PROJECT_ROOT / "web" / "templates" / "_rescrape_modal.html"
    SOURCE_PILL_CSS    = PROJECT_ROOT / "web" / "static" / "css" / "components" / "source-pill.css"

    # ── Surface 1: state-config.js ──────────────────────────────────────────────

    def test_click_active_row_pill_has_requires_proxy_intercept(self):
        """clickActiveRowPill 在函數開頭加 requires_proxy + isDmmAvailable 攔截（Surface 1）。

        策略：用 regex 擷取 clickActiveRowPill 函數體，再在其中斷言三個 token。
        「字串存在性 ≠ contract」：斷言在函數體範圍內，而非整檔字串搜尋。
        """
        js = self.SETTINGS_CONFIG_JS.read_text(encoding="utf-8")
        # 擷取 clickActiveRowPill 函數體（直到下一個方法定義）
        m = re.search(
            r'clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|\Z)',
            js, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 clickActiveRowPill 函數體"
        fn_body = m.group(1)
        assert "requires_proxy" in fn_body, (
            "63c-6 違規：clickActiveRowPill 函數體缺 requires_proxy 判斷（Surface 1 攔截）"
        )
        assert "isDmmAvailable" in fn_body, (
            "63c-6 違規：clickActiveRowPill 函數體缺 isDmmAvailable() 呼叫（Surface 1 proxy 判斷）"
        )
        assert "dmm_proxy_required_hint" in fn_body, (
            "63c-6 違規：clickActiveRowPill 函數體缺 dmm_proxy_required_hint toast key（Surface 1）"
        )

    def test_click_active_row_pill_no_window_confirm(self):
        """clickActiveRowPill 不含 window.confirm（eslint no-confirm 全域 rule，禁 modal block）。"""
        js = self.SETTINGS_CONFIG_JS.read_text(encoding="utf-8")
        m = re.search(
            r'clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|\Z)',
            js, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 clickActiveRowPill 函數體"
        fn_body = m.group(1)
        assert "window.confirm" not in fn_body, (
            "63c-6 違規：clickActiveRowPill 含 window.confirm — 用 showToast 取代（no-confirm rule）"
        )

    # ── Surface 1: settings.html Active Row pill ─────────────────────────────────

    def test_settings_active_row_pill_has_data_proxy_required_binding(self):
        """settings.html Active Row source-pill div 含 :data-proxy-required binding（Surface 1）。

        策略：用 regex 擷取 x-for="s in activeRowSources" 的 source-pill div 開口 tag（到第一個 >），
        再在 tag 內容中斷言 :data-proxy-required 屬性存在。
        """
        html = self.SETTINGS_HTML.read_text(encoding="utf-8")
        # 擷取 x-for activeRowSources 模板內的 source-pill div 開口 tag
        m = re.search(
            r'x-for="s in activeRowSources"[^>]*>.*?<div\s+class="source-pill"(.*?)role="option"',
            html, re.DOTALL
        )
        assert m, (
            "63c-6 違規：找不到 Active Row source-pill div（settings.html x-for activeRowSources 內）"
        )
        tag_attrs = m.group(1)
        assert ":data-proxy-required" in tag_attrs, (
            "63c-6 違規：settings.html Active Row source-pill 缺 :data-proxy-required binding（Surface 1）"
        )

    def test_settings_active_row_pill_proxy_required_uses_is_dmm_available(self):
        """settings.html Active Row :data-proxy-required 引用 isDmmAvailable()（不用硬編碼邏輯）。"""
        html = self.SETTINGS_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in activeRowSources"[^>]*>.*?<div\s+class="source-pill"(.*?)role="option"',
            html, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 Active Row source-pill div"
        tag_attrs = m.group(1)
        assert "isDmmAvailable" in tag_attrs, (
            "63c-6 違規：settings.html Active Row :data-proxy-required 應引用 isDmmAvailable()（Surface 1）"
        )

    # ── Surface 2: state-rescrape.js ─────────────────────────────────────────────

    def test_state_rescrape_has_is_source_proxy_blocked(self):
        """state-rescrape.js 定義 isSourceProxyBlocked method（Surface 2）。

        綁到 method 定義（非全檔字串存在 — gotchas「字串存在性 ≠ contract」），
        避免 comment 裡的字串繞過守衛。"""
        js = self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert re.search(r"isSourceProxyBlocked\s*\([^)]*\)\s*\{", js), (
            "63c-6 違規：state-rescrape.js 缺 isSourceProxyBlocked 方法定義（Surface 2）"
        )

    def test_state_rescrape_is_source_proxy_blocked_reads_proxy_configured(self):
        """isSourceProxyBlocked helper 讀取 proxy_configured（不依賴 Settings scope isDmmAvailable）。

        策略：擷取 isSourceProxyBlocked 函數體，斷言其中含 proxy_configured。
        """
        js = self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        m = re.search(
            r'isSourceProxyBlocked\s*\([^)]*\)\s*\{([^}]+)\}',
            js, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 isSourceProxyBlocked 函數體（state-rescrape.js）"
        fn_body = m.group(1)
        assert "proxy_configured" in fn_body, (
            "63c-6 違規：isSourceProxyBlocked 函數體缺 proxy_configured 讀取（不可依賴 isDmmAvailable()）"
        )
        assert "requires_proxy" in fn_body, (
            "63c-6 違規：isSourceProxyBlocked 函數體缺 requires_proxy 讀取（Surface 2）"
        )

    # ── Surface 2: _rescrape_modal.html builtin pill ─────────────────────────────

    def test_rescrape_modal_builtin_pill_has_data_proxy_required(self):
        """_rescrape_modal.html builtin pill button 含 :data-proxy-required binding（Surface 2）。

        策略：擷取 x-for="s in rescrapeBuiltinSources()" 模板內的 button tag（到第一個 >），
        再在 tag 屬性內容斷言 :data-proxy-required 存在（綁定到具體 builtin 元素，不是整檔搜尋）。
        """
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>',
            html, re.DOTALL
        )
        assert m, (
            "63c-6 違規：找不到 rescrapeBuiltinSources() 模板內的 button tag（_rescrape_modal.html）"
        )
        button_attrs = m.group(1)
        assert ":data-proxy-required" in button_attrs, (
            "63c-6 違規：_rescrape_modal.html builtin pill button 缺 :data-proxy-required binding（Surface 2）"
        )

    def test_rescrape_modal_builtin_pill_click_uses_is_source_proxy_blocked(self):
        """_rescrape_modal.html builtin pill @click handler 引用 isSourceProxyBlocked（Surface 2）。

        策略：同上，在 builtin pill button tag 屬性內斷言 isSourceProxyBlocked 出現（click guard）。
        """
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>',
            html, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 rescrapeBuiltinSources() 模板內的 button tag"
        button_attrs = m.group(1)
        assert "isSourceProxyBlocked" in button_attrs, (
            "63c-6 違規：_rescrape_modal.html builtin pill @click 缺 isSourceProxyBlocked guard（Surface 2）"
        )

    def test_rescrape_modal_builtin_pill_no_window_confirm(self):
        """_rescrape_modal.html builtin pill button tag 不含 window.confirm。"""
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>',
            html, re.DOTALL
        )
        assert m, "63c-6 違規：找不到 rescrapeBuiltinSources() 模板內的 button tag"
        button_attrs = m.group(1)
        assert "window.confirm" not in button_attrs, (
            "63c-6 違規：_rescrape_modal.html builtin pill 含 window.confirm（用 showToast 取代）"
        )

    # ── CSS: source-pill.css ─────────────────────────────────────────────────────

    def test_source_pill_css_has_proxy_required_opacity_rule(self):
        """source-pill.css 含 [data-proxy-required="true"] opacity rule（兩 surface 共用）。"""
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        # 擷取含 data-proxy-required="true" 的 rule block
        m = re.search(
            r'\.source-pill\[data-proxy-required="true"\]\s*\{([^}]+)\}',
            css, re.DOTALL
        )
        assert m, (
            "63c-6 違規：source-pill.css 缺 .source-pill[data-proxy-required=\"true\"] rule block"
        )
        rule_body = m.group(1)
        assert "opacity" in rule_body, (
            "63c-6 違規：[data-proxy-required=\"true\"] rule 缺 opacity 設定（灰化機制）"
        )

    def test_source_pill_css_proxy_required_hover_no_lift(self):
        """source-pill.css [data-proxy-required="true"]:hover 不 lift（mirror is-disconnected）。"""
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        m = re.search(
            r'\.source-pill\[data-proxy-required="true"\]:hover\s*\{([^}]+)\}',
            css, re.DOTALL
        )
        assert m, (
            "63c-6 違規：source-pill.css 缺 [data-proxy-required=\"true\"]:hover rule（hover 不亮回）"
        )
        hover_body = m.group(1)
        assert "transform" in hover_body, (
            "63c-6 違規：:hover rule 缺 transform: none（防 lift）"
        )


# ─── 64a: 進階 picker 三態膠囊語意 + 標題依入口（CD-64-A1~A5 / US-A2）───
class TestPicker64aThreeStateGuard:
    """64a-1/64a-2: 進階重刮 / 進階搜尋彈窗 picker 膠囊三態 + 標題契約守衛。

    這些是 template(_rescrape_modal.html) ↔ JS state field / CSS 的跨檔契約（C/E 類），
    eslint 只掃 web/static/js、stylelint 只掃 CSS，皆不處理 Jinja template，故守衛留 pytest
    （沿用同檔既有 _rescrape_modal binding 守衛之先例，如 63c-6 TestDmmProxyRequiredGuard）。

    Frontend-guard 強度：先 regex 擷取目標 pill 的 button tag 範圍，再在 tag 內斷言屬性，
    不對整檔做字串存在性檢查（gotchas「字串存在性 ≠ contract」）。
    """

    RESCRAPE_MODAL_HTML = PROJECT_ROOT / "web" / "templates" / "_rescrape_modal.html"
    SOURCE_PILL_CSS     = PROJECT_ROOT / "web" / "static" / "css" / "components" / "source-pill.css"

    def _builtin_button_attrs(self):
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>',
            html, re.DOTALL,
        )
        assert m, "64a 違規：找不到 rescrapeBuiltinSources() 模板內的 button tag"
        return m.group(1)

    def _metatube_button_attrs(self):
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(
            r'x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+([^>]+)>',
            html, re.DOTALL,
        )
        assert m, "64a 違規：找不到 rescrapeMetatubeSources() 模板內的 button tag"
        return m.group(1)

    # ── 64a-1: builtin pill 恆可選（CD-64-A4）─────────────────────────────────────

    def test_builtin_pill_data_enabled_hardcoded_true(self):
        """builtin pill data-enabled 硬編 'true'，不綁 s.enabled（picker 依 usability 不依 promotion）。"""
        attrs = self._builtin_button_attrs()
        assert 'data-enabled="true"' in attrs, (
            "64a-1 違規：builtin pill 缺硬編 data-enabled=\"true\"（CD-64-A4 恆可選）"
        )
        assert ":data-enabled" not in attrs, (
            "64a-1 違規：builtin pill 不得再 :data-enabled 綁 s.enabled（picker 不反映 Settings 開關）"
        )

    # ── 64a-1: metatube pill 依 available（CD-64-A1/A5）──────────────────────────

    def test_metatube_pill_data_enabled_binds_available(self):
        """metatube pill :data-enabled 綁 s.available（非 s.enabled）。"""
        attrs = self._metatube_button_attrs()
        assert ":data-enabled" in attrs and "s.available" in attrs, (
            "64a-1 違規：metatube pill :data-enabled 應綁 s.available（可達性，非 promote）"
        )
        m = re.search(r':data-enabled="([^"]+)"', attrs)
        assert m and "s.available" in m.group(1), (
            "64a-1 違規：metatube pill :data-enabled 表達式未引用 s.available"
        )
        assert "s.enabled" not in m.group(1), (
            "64a-1 違規：metatube pill :data-enabled 不得綁 s.enabled（CD-64-A1）"
        )

    def test_metatube_pill_offline_aria_disabled_and_guard(self):
        """metatube offline 用 aria-disabled + title tooltip + @click guard（非 native disabled，CD-64-A5）。"""
        attrs = self._metatube_button_attrs()
        assert ":aria-disabled" in attrs and "s.available" in attrs, (
            "64a-1 違規：metatube pill 缺 :aria-disabled（依 s.available 的 offline 不可點語意）"
        )
        # tooltip 走 offline_tooltip i18n key
        assert "offline_tooltip" in attrs, (
            "64a-1 違規：metatube pill :title 缺 showcase.rescrape.offline_tooltip"
        )
        # @click offline guard：點擊路徑須以 s.available 把關
        m = re.search(r'@click="([^"]+)"', attrs)
        assert m and "s.available" in m.group(1), (
            "64a-1 違規：metatube pill @click 缺 s.available offline guard"
        )
        # native disabled 仍只給 loading state（保留），不得被 offline 挪用
        dm = re.search(r':disabled="([^"]+)"', attrs)
        assert dm and "rescrapeLoadingSource" in dm.group(1), (
            "64a-1 違規：metatube pill native :disabled 應只綁 loading（rescrapeLoadingSource），不可被 offline 佔用"
        )

    # ── 64a-1: CSS offline scope（CD-64-A2/A3）───────────────────────────────────

    def test_css_action_offline_removes_line_through(self):
        """source-pill.css picker offline 去刪除線：.source-pill--action[data-enabled=false] .pill-name text-decoration:none（雙 class）。"""
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        m = re.search(
            r'\.source-pill\.source-pill--action\[data-enabled="false"\]\s+\.pill-name\s*\{([^}]+)\}',
            css, re.DOTALL,
        )
        assert m, (
            "64a-1 違規：source-pill.css 缺 .source-pill.source-pill--action[data-enabled=\"false\"] .pill-name 規則"
            "（picker offline 去刪除線，雙 class 0,4,0 勝全域 0,3,0）"
        )
        assert "text-decoration: none" in m.group(1), (
            "64a-1 違規：picker offline .pill-name 應 text-decoration: none"
        )

    def test_css_global_line_through_untouched(self):
        """CD-64-A3：全域 .source-pill[data-enabled=false] .pill-name 仍 line-through（picker scope 為加法，不動全域）。"""
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        m = re.search(
            r'(?<!--action)\.source-pill\[data-enabled="false"\]\s+\.pill-name\s*\{([^}]+)\}',
            css, re.DOTALL,
        )
        assert m, "64a-1 違規：全域 .source-pill[data-enabled=\"false\"] .pill-name 規則不應被移除"
        assert "line-through" in m.group(1), (
            "64a-1 違規：全域 line-through 不應被改動（CD-64-A3：只在 picker scope 加法覆寫）"
        )

    def test_css_action_offline_cursor_not_allowed(self):
        """offline 膠囊 cursor: not-allowed（不可點 affordance；scope 在 .source-pill--action[aria-disabled=true]）。"""
        css = self.SOURCE_PILL_CSS.read_text(encoding="utf-8")
        m = re.search(
            r'\.source-pill--action\[aria-disabled="true"\]\s*\{([^}]+)\}',
            css, re.DOTALL,
        )
        assert m, "64a-1 違規：source-pill.css 缺 .source-pill--action[aria-disabled=\"true\"] cursor 規則"
        assert "not-allowed" in m.group(1), (
            "64a-1 違規：offline 膠囊 cursor 應 not-allowed"
        )

    # ── 64a-2: 標題依入口切換（US-A2）────────────────────────────────────────────

    def test_modal_title_switches_by_entrypoint(self):
        """彈窗標題 x-text 依 rescrapeEntryPoint 切：'search'→search_title，其餘→modal_title。"""
        html = self.RESCRAPE_MODAL_HTML.read_text(encoding="utf-8")
        m = re.search(r'class="fluent-modal-title".*?</h3>', html, re.DOTALL)
        assert m, "64a-2 違規：找不到 fluent-modal-title h3"
        title = m.group(0)
        assert "x-text" in title, "64a-2 違規：標題應改 x-text 動態切換（非靜態 Jinja）"
        assert "rescrapeEntryPoint === 'search'" in title, (
            "64a-2 違規：標題未依 rescrapeEntryPoint === 'search' 分支"
        )
        assert "search_title" in title and "modal_title" in title, (
            "64a-2 違規：標題分支應同時引用 search_title 與 modal_title 兩個 i18n key"
        )


# ─── 63c-7: i18n zh_TW（DMM proxy hint + Help metatube SQLite hint）───
class TestMetatube63c7I18nGuard:
    """63c-7: 63c 新 UI 文字 zh_TW key 存在 + help.html 引用（其他 3 locale 待 milestone）。

    本 branch 只交付 zh_TW（對齊 62/63b i18n 慣例）。不驗 zh_CN/ja/en parity。
    """

    ZH_TW = LOCALES_ROOT / "zh_TW.json"
    HELP_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "help.html"

    def _zh(self):
        return json.loads(self.ZH_TW.read_text(encoding="utf-8"))

    def test_dmm_proxy_required_hint_exists(self):
        """63c-6 toast 引用的 key 存在且非空（state-config.js / _rescrape_modal.html）。"""
        v = self._zh().get("settings", {}).get("sources", {}).get("dmm_proxy_required_hint")
        assert v, "63c-7 違規：缺 settings.sources.dmm_proxy_required_hint"

    def test_help_metatube_sqlite_keys_exist(self):
        """Help metatube 教學卡 key（title + db_hint + enable_url）存在且非空。"""
        metatube = self._zh().get("help", {}).get("metatube", {})
        assert metatube.get("title"), "64c-1 違規：缺 help.metatube.title"
        assert metatube.get("db_hint"), "64c-1 違規：缺 help.metatube.db_hint（SQLite 提示）"
        assert metatube.get("enable_url"), "64c-1 違規：缺 help.metatube.enable_url"

    def test_help_html_references_metatube_hint(self):
        """help.html 引用 help.metatube.title + help.metatube.db_hint（非孤兒 key）；舊孤兒 key 不存在。"""
        html = self.HELP_HTML.read_text(encoding="utf-8")
        assert "help.metatube.title" in html, "64c-1 違規：help.html 未引用 help.metatube.title"
        assert "help.metatube.db_hint" in html, "64c-1 違規：help.html 未引用 help.metatube.db_hint"
        assert "help.scraper.h6_metatube" not in html, (
            "64c-1 違規：help.html 仍含孤兒 key help.scraper.h6_metatube"
        )



class TestSettingsQuickToggleGuard:
    """64b-3: quick-toggle 列存在 + 兩 toggle 在列內（CD-64-B8）"""

    SETTINGS_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "settings.html"

    def _html(self):
        return self.SETTINGS_HTML.read_text(encoding="utf-8")

    def test_quick_toggle_row_exists(self):
        assert 'class="settings-quick-toggle-row"' in self._html(), \
            "64b-3 違規：settings.html 缺少 .settings-quick-toggle-row"

    def test_quick_toggle_row_inside_form_before_sec_search(self):
        html = self._html()
        form_pos = html.index('<form id="settingsForm"')
        row_pos = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        assert form_pos < row_pos, \
            "64b-3 違規：.settings-quick-toggle-row 必須在 <form id=settingsForm> 之後"
        assert row_pos < sec_search_pos, \
            "64b-3 違規：.settings-quick-toggle-row 必須在 <section id=sec-search> 之前"

    def test_download_sample_images_in_quick_toggle_row(self):
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        # 結束點：取列 div 結束標記（class 末尾）— 用 sec-search 開始當界
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'x-model="form.downloadSampleImages"' in row_block, \
            "64b-3 違規：form.downloadSampleImages x-model 必須在 .settings-quick-toggle-row 內"

    def test_advanced_search_enabled_in_quick_toggle_row(self):
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'x-model="form.advancedSearchEnabled"' in row_block, \
            "64b-3 違規：form.advancedSearchEnabled x-model 必須在 .settings-quick-toggle-row 內"

    def test_advanced_search_toggle_id_preserved(self):
        """id=advancedSearchToggle 必須在 quick-toggle 列（不可消失）"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'id="advancedSearchToggle"' in row_block, \
            "64b-3 違規：id=advancedSearchToggle 必須保留在 quick-toggle 列內（64b-1 DoD：不得遺失 id）"

    def test_download_sample_images_not_duplicated_in_card(self):
        """downloadSampleImages x-model 只出現一次（已從 Card ② 搬走）"""
        html = self._html()
        count = html.count('x-model="form.downloadSampleImages"')
        assert count == 1, \
            f"64b-3 違規：form.downloadSampleImages x-model 出現 {count} 次，應只在 quick-toggle 列（1 次）"

    def test_advanced_search_toggle_id_unique(self):
        """id=advancedSearchToggle 全頁只出現一次（搬移非複製；重複 id 為無效 HTML）"""
        html = self._html()
        count = html.count('id="advancedSearchToggle"')
        assert count == 1, \
            f"64b-3 違規：id=advancedSearchToggle 出現 {count} 次，應只在 quick-toggle 列（1 次）"

    def test_advanced_search_has_help_popover(self):
        """64e-1 E2：進階搜尋區塊必須有 showAdvancedSearchHelp state 與 help-popover 元件（Alpine↔HTML API contract）"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'showAdvancedSearchHelp' in row_block, \
            "64e-1 違規：quick-toggle 列內進階搜尋區塊缺少 showAdvancedSearchHelp state binding"
        assert 'help-popover' in row_block, \
            "64e-1 違規：quick-toggle 列內進階搜尋區塊缺少 help-popover 元件"


class TestSettingsDmmProxyContract:
    """64b-3: DMM 灰化 + proxy binding contract 驗證（CD-64-B4）"""

    SETTINGS_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "settings.html"
    STATE_CONFIG_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"

    def _html(self): return self.SETTINGS_HTML.read_text(encoding="utf-8")
    def _js(self): return self.STATE_CONFIG_JS.read_text(encoding="utf-8")

    def test_is_dmm_available_in_state_config(self):
        assert "isDmmAvailable" in self._js(), \
            "64b-3 違規：state-config.js 缺少 isDmmAvailable 函式（DMM 灰化 binding contract）"

    def test_proxy_url_in_form_state(self):
        assert "proxyUrl" in self._js(), \
            "64b-3 違規：state-config.js form 缺少 proxyUrl 狀態"

    def test_is_dmm_available_reads_proxy_url(self):
        """isDmmAvailable 必須讀 form.proxyUrl（不可改讀其他變數）"""
        js = self._js()
        # 找到 isDmmAvailable 函式 block，確認其中含 proxyUrl
        idx = js.index("isDmmAvailable")
        block = js[idx:idx+200]
        assert "proxyUrl" in block, \
            "64b-3 違規：isDmmAvailable 應讀 form.proxyUrl（DMM 灰化 reactive 來源）"

    def test_dmm_pill_reads_is_dmm_available(self):
        assert ":data-proxy-required" in self._html(), \
            "64b-3 違規：settings.html 缺少 :data-proxy-required（Active Row DMM pill binding）"

    def test_proxy_url_x_model_in_sources_card(self):
        """64b-6: proxy x-model 已移至搜尋來源卡（sec-search），不在 scraperAdvanced 摺疊內"""
        html = self._html()
        # 1. proxy x-model 存在且只有 1 次（搬移非複製）
        assert html.count('x-model="form.proxyUrl"') == 1, \
            "64b-6 違規：x-model=\"form.proxyUrl\" 應恰好出現 1 次（搬移非複製）"
        proxy_model_pos = html.index('x-model="form.proxyUrl"')
        # 2. 位置在 id="sec-search" 之後
        sec_search_pos = html.index('id="sec-search"')
        assert proxy_model_pos > sec_search_pos, \
            "64b-6 違規：proxy x-model 應在 id=\"sec-search\" 之後（在搜尋來源卡內）"
        # 3. 位置在 id="sec-gallery" 之前
        sec_gallery_pos = html.index('id="sec-gallery"')
        assert proxy_model_pos < sec_gallery_pos, \
            "64b-6 違規：proxy x-model 應在 id=\"sec-gallery\" 之前（在搜尋來源卡內，不在 gallery 卡）"
        # 4. 位置在第一個 collapsible-content（scraperAdvanced 摺疊）之前（已移出摺疊）
        collapsible_pos = html.index('class="collapsible-content"')
        assert proxy_model_pos < collapsible_pos, \
            "64b-6 違規：proxy x-model 應在第一個 collapsible-content 之前（已移出進階刮削摺疊）"

    def test_proxy_row_before_metatube_toggle(self):
        """64e-3: proxy row 整行搬至 metatube enable toggle 正上方（CD-64-E5 方案 B）。

        layout contract：proxy 控件（含「需日本 IP」hint）須貼近 DMM 來源 + metatube
        連線區，故位置在 id="sec-search" 之後、id="metatubeEnableToggle" 之前。
        """
        html = self._html()
        sec_search_pos = html.index('id="sec-search"')
        proxy_model_pos = html.index('x-model="form.proxyUrl"')
        metatube_toggle_pos = html.index('id="metatubeEnableToggle"')
        assert sec_search_pos < proxy_model_pos < metatube_toggle_pos, \
            "64e-3 違規：proxy row 應在 id=\"sec-search\" 之後、id=\"metatubeEnableToggle\" 之前（搬至 metatube toggle 正上方）"


SHOWCASE_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
PAGE_LIFECYCLE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "components" / "page-lifecycle.js"


class TestCoverLoadingUx67Guard:
    """67 Cover Loading UX + Showcase Console 清零 守衛（HTML/CSS contract；JS 字串守衛走 eslint，CD-67-8）。

    全部依 G5：先 regex 抽出目標 tag/區塊再斷言其內容，不整檔裸 grep（showcase.html 別處仍有
    合法 <template x-for> 與多個 <img>）。每條皆可 RED→GREEN（破壞 contract 跑 RED、還原 GREEN）。
    """

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _css(self):
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    def _grid_img(self):
        """抽出 grid 卡片封面 <img>（唯一含 :src="video.cover_url" 的 img tag）"""
        html = self._html()
        m = re.search(r'<img :src="video\.cover_url".*?>', html, re.S)
        assert m, "showcase.html: grid 封面 <img :src=\"video.cover_url\"> 不存在"
        return m.group(0)

    def _hero_img(self):
        """抽出 hero 卡片 <img>（含 _matchedActress?.photo_url 的 img tag）"""
        html = self._html()
        m = re.search(r"<img :src=\"_matchedActress\?\.photo_url \|\| ''\".*?>", html, re.S)
        assert m, "showcase.html: hero <img :src=\"_matchedActress?.photo_url || ''\"> 不存在"
        return m.group(0)

    def _rails_svg(self):
        """抽出相似 stage rails <svg class=\"similar-stage-rails\">…</svg> 區塊"""
        html = self._html()
        m = re.search(r'<svg class="similar-stage-rails".*?</svg>', html, re.S)
        assert m, "showcase.html: <svg class=\"similar-stage-rails\"> 區塊不存在"
        return m.group(0)

    # ---- Track B: SVG 靜態化（B1）----

    def test_rails_svg_has_no_template(self):
        """B-2: rails <svg> 內不得有 <template>（SVG namespace 下無 .content → Alpine x-for 丟錯）"""
        block = self._rails_svg()
        assert "<template" not in block, \
            "showcase.html rails <svg class=\"similar-stage-rails\"> 內仍有 <template>（SVG x-for bug 回退；改靜態 <line>）"

    def test_rails_svg_has_12_static_rail_and_sweep_ids(self):
        """B-2/B-3: rails <svg> 含 12 組靜態 similar-rail-NN + similar-sweep-NN（防漏組/補錯位數）"""
        block = self._rails_svg()
        for nn in range(1, 13):
            rail = f'id="similar-rail-{nn:02d}"'
            sweep = f'id="similar-sweep-{nn:02d}"'
            assert rail in block, f"showcase.html rails <svg> 缺靜態 {rail}"
            assert sweep in block, f"showcase.html rails <svg> 缺靜態 {sweep}"

    # ---- Track A: grid 卡片三態（A2）----

    def test_grid_img_has_load_and_imgloaded_fade(self):
        """A2/DoD A-1: grid <img> 含 @load 旗標 + .cover-loaded 淡入 class（綁在 img 上）"""
        img = self._grid_img()
        assert '@load="video._imgLoaded = true"' in img, \
            "grid <img> 缺 @load=\"video._imgLoaded = true\"（三態的 loaded 觸發）"
        assert ":class=\"{ 'cover-loaded': video._imgLoaded }\"" in img, \
            "grid <img> 缺 :class 淡入綁定（.cover-loaded by _imgLoaded）"

    def test_grid_img_first_screen_fetchpriority(self):
        """A2/DoD A-5: grid <img> 首屏前 8 張 eager+high（不可 lazy+high 並存）"""
        img = self._grid_img()
        assert ":loading=\"index < 8 ? 'eager' : 'lazy'\"" in img, \
            "grid <img> 缺首屏 :loading 綁定（index<8 eager 其餘 lazy）"
        assert ":fetchpriority=\"index < 8 ? 'high' : 'auto'\"" in img, \
            "grid <img> 缺 :fetchpriority 綁定（index<8 high 其餘 auto）"
        assert 'loading="lazy"' not in img, \
            "grid <img> 仍有寫死 loading=\"lazy\"（應改 :loading 綁定）"

    def test_grid_has_no_cover_div(self):
        """A2/CD-67-3 (a): grid 含 no-cover div x-show=\"!video.cover_url\"（DB 缺封面空白 img）"""
        html = self._html()
        assert 'x-show="!video.cover_url"' in html, \
            "showcase.html grid 缺 no-cover div（x-show=\"!video.cover_url\"，DB 缺封面 fallback）"

    # ---- Track A: hero 卡片三態（A3）----

    def test_hero_img_has_load_and_heroloaded_fade(self):
        """A3/CD-67-4: hero <img> 含 @load=_heroCardImageLoaded（獨立旗標，不混 video _imgLoaded）"""
        img = self._hero_img()
        assert '@load="_heroCardImageLoaded = true"' in img, \
            "hero <img> 缺 @load=\"_heroCardImageLoaded = true\""
        assert ":class=\"{ 'cover-loaded': _heroCardImageLoaded }\"" in img, \
            "hero <img> 缺 :class 淡入綁定（.cover-loaded by _heroCardImageLoaded）"
        assert 'fetchpriority="high"' in img and 'loading="eager"' in img, \
            "hero <img> 缺首屏 eager+high（CD-67-5）"

    def test_hero_img_xshow_gated_on_photo_url(self):
        """Codex P2#2: hero <img> x-show 須 gate by _matchedActress?.photo_url（空 photo_url 的 src=""
        不觸發 @load/@error；若 x-show 只看 !_heroCardImageError 會顯空白框）。no-cover div 對應 gate
        !photo_url || error 顯破圖 icon（與 grid no-cover 一致）。"""
        img = self._hero_img()
        assert 'x-show="_matchedActress?.photo_url && !_heroCardImageError"' in img, \
            "hero <img> x-show 須含 _matchedActress?.photo_url（防空 photo_url 顯空白框回退，Codex P2#2）"
        html = self._html()
        assert "!_matchedActress.photo_url || _heroCardImageError" in html, \
            "hero no-cover div x-show 須含 !_matchedActress.photo_url || _heroCardImageError（空 photo 或 error 皆顯破圖 icon）"

    def test_actress_js_declares_and_resets_heroloaded(self):
        """A3/CD-67-4: state-actress.js 宣告 _heroCardImageLoaded + 兩處 lifecycle 重置"""
        src = SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8")
        assert "_heroCardImageLoaded: false" in src, \
            "state-actress.js 缺 _heroCardImageLoaded 宣告"
        n = src.count("this._heroCardImageLoaded = false")
        assert n >= 2, \
            f"state-actress.js _heroCardImageLoaded 重置須 ≥2 處（_clearPreciseMatch + _checkPreciseActressMatch），實際 {n}"

    # ---- Track A: JS 旗標初始化/重置（A2）----

    def test_imgloaded_initialized_in_fetchvideos(self):
        """A2: state-videos.js fetchVideos 初始化 _imgLoaded（唯一來源，涵蓋所有 grid render）"""
        src = SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")
        assert "_imgLoaded === undefined" in src and "_imgLoaded = false" in src, \
            "state-videos.js fetchVideos 缺 _imgLoaded:false 初始化"

    def test_handle_cover_error_marks_loaded(self):
        """Codex P2 (broken cover): handleCoverError 須同時設 has_cover=false 且 _imgLoaded=true，
        讓 stale/404 封面換 placeholder 後確定性顯示（grid 淡入規則使 img 預設 opacity:0；不可只依賴
        placeholder 二次 @load 觸發 _imgLoaded）。抽 handleCoverError body 再斷言，非整檔裸 grep。"""
        src = SHOWCASE_BASE_JS.read_text(encoding="utf-8")
        m = re.search(r"handleCoverError\(video, event\)\s*\{(.*?)\n\s*\},", src, re.S)
        assert m, "state-base.js: 找不到 handleCoverError(video, event) method"
        body = m.group(1)
        assert "has_cover = false" in body, "handleCoverError 須設 video.has_cover = false"
        assert "_imgLoaded = true" in body, \
            ("handleCoverError 須設 video._imgLoaded = true（Codex P2 broken-cover）：否則 stale/404 封面"
             "在 grid opacity:0 淡入規則下停在隱形、no-cover 也不顯 → 空白卡")

    def test_refreshvideodata_resets_imgloaded_before_assign(self):
        """A2/CD-67-3b: refreshVideoData 在 Object.assign 前 reset _imgLoaded（補封面重走三態）"""
        src = SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        m = re.search(r"video\._imgLoaded = false;.*?Object\.assign\(video, data\.video\)", src, re.S)
        assert m, \
            "state-lightbox.js refreshVideoData 須在 Object.assign(video, data.video) 前 reset video._imgLoaded=false"

    # ---- Track A: CSS 淡入歸屬 + PRM 退化（A1，DoD A-3/A-4）----

    def test_fade_not_on_card_preview_container(self):
        """A1/DoD A-3: per-image 淡入 opacity transition 不得掛 .av-card-preview 容器（GSAP playEntry 專屬）。

        負向：任何 bare `.av-card-preview {…}` 規則 body 不得同時含 transition + opacity。
        （`.av-card-preview-img …` 因後接 `-img` 不符 `\\.av-card-preview\\s*\\{`，不誤判。）"""
        css = self._css()
        for m in re.finditer(r'\.av-card-preview\s*\{([^}]*)\}', css):
            body = m.group(1)
            assert not ("transition" in body and "opacity" in body), \
                "DoD A-3 違規：.av-card-preview 容器帶 opacity transition；淡入須掛 .av-card-preview-img img（GSAP playEntry 動容器 opacity，不可共存 CSS transition）"

    def test_fade_rule_on_img_layer_default_hidden(self):
        """A1/DoD A-3: 存在 .av-card-preview-img img 的淡入規則（opacity:0 預設 + transition）"""
        css = self._css()
        rules = re.findall(r'\.av-card-preview-img img\s*\{([^}]*)\}', css)
        assert any("opacity: 0" in b and "transition" in b and "opacity" in b for b in rules), \
            "showcase.css 缺 .av-card-preview-img img 淡入規則（opacity:0 預設 + opacity transition）"

    def test_fade_rule_scoped_to_showcase_container(self):
        """Codex P2#1: 淡入 opacity:0 規則必須 compound .showcase-container scope（防洩漏到 search.html /
        design-system.html——兩頁也載 showcase.css + 共用 ds scope 但無 .cover-loaded 機制，洩漏會讓搜尋
        封面/demo 整片隱形）。抓含 opacity:0 的淡入規則整條 selector，斷言含 .showcase-container。"""
        css = self._css()
        # 先剝除 /* */ 註解（否則 [^{}]*? 會吃進前面提及 .showcase-container 的註解 → 假 GREEN）
        css_nc = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
        # 抓 opacity:0 淡入 base 規則的完整 selector（含前綴）
        m = re.search(r'([^{}]*?\.av-card-preview-img img)\s*\{[^}]*opacity:\s*0[^}]*\}', css_nc)
        assert m, "showcase.css 找不到 opacity:0 的 .av-card-preview-img img 淡入規則"
        selector = m.group(1)
        assert ".showcase-container" in selector, \
            ("淡入 opacity:0 規則未 compound .showcase-container（Codex P2#1）：會洩漏到 search.html / "
             f"design-system.html 讓封面隱形。實際 selector: {selector.strip()!r}")

    def test_prm_degrades_shimmer_and_fade(self):
        """A1/DoD A-4: reduced-motion 下 shimmer animation:none + 淡入 transition:none/opacity:1 皆退化"""
        css = self._css()
        assert "prefers-reduced-motion: reduce" in css, \
            "showcase.css 缺 @media (prefers-reduced-motion: reduce) guard"
        shimmer_rules = re.findall(r'(?<![\w-])\.shimmer\s*\{([^}]*)\}', css)
        assert any("animation: shimmer" in b for b in shimmer_rules), \
            "showcase.css 缺 .shimmer 基礎 animation"
        assert any("animation: none" in b for b in shimmer_rules), \
            "showcase.css PRM 缺 .shimmer { animation: none }（DoD A-4）"
        fade_rules = re.findall(r'\.av-card-preview-img img\s*\{([^}]*)\}', css)
        assert any("transition: none" in b and "opacity: 1" in b for b in fade_rules), \
            "showcase.css PRM 缺淡入退化（.av-card-preview-img img { transition: none; opacity: 1 }，DoD A-4）"

    # ---- Track B: unload 已遷 pagehide（B2，eslint 也擋；此處正向確認 pagehide 在位）----

    def test_page_lifecycle_uses_pagehide_not_unload(self):
        """B-4/CD-67-7: page-lifecycle.js 用 pagehide、無 unload listener（eslint SEL_NO_UNLOAD_LISTENER 同擋）"""
        src = PAGE_LIFECYCLE_JS.read_text(encoding="utf-8")
        assert "addEventListener('pagehide'" in src, \
            "page-lifecycle.js 缺 addEventListener('pagehide')"
        assert "addEventListener('unload'" not in src, \
            "page-lifecycle.js 仍有 addEventListener('unload')（應改 pagehide）"

    def test_pagehide_skips_cleanup_on_bfcache_persist(self):
        """Codex P2 (bfcache): pagehide handler 須在 event.persisted（進 bfcache）時跳過 cleanup，
        否則 Back 還原（不重跑 module init）後頁面缺 SSE/abort/resize listener。抽 pagehide handler
        callback body 再斷言含 persisted 短路，不整檔裸 grep。"""
        src = PAGE_LIFECYCLE_JS.read_text(encoding="utf-8")
        m = re.search(r"addEventListener\('pagehide',\s*function\s*\([^)]*\)\s*\{(.*?)\}\s*\)", src, re.S)
        assert m, "page-lifecycle.js: 找不到 pagehide handler callback"
        body = m.group(1)
        assert "persisted" in body, \
            ("pagehide handler 未檢查 event.persisted（Codex P2 bfcache）：進 bfcache 時無條件 cleanup "
             "會讓 Back 還原的頁面缺 listener/resource。需 `if (e.persisted) return;`")
