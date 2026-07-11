"""前端契約守衛（KEEP，跨檔 contract）— 由 test_frontend_lint.py 拆出（96e T1，純搬移零行為變更）。

module-level 路徑常數為源檔複製（CD-96e-2：源檔殘留 class 仍引用同名常數，故複製非剪走）。
"""
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /home/peace/OpenAver
GRID_MODE_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"
SETTINGS_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "settings.html"
SETTINGS_CONFIG_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
LOCALES_ROOT = Path(__file__).parent.parent.parent.parent / "locales"


class TestNavigateLoadMore:
    # [lint-guard: pytest-justified] method-body ordering — navigate(delta) 抽方法體
    # 驗 this.currentIndex = result.oldLength 位置 < playSlideIn 位置（state-first）
    """T3b: navigate() loadMore + state-first slide (method folded)"""

    NAVIGATION_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"

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
    # [lint-guard: pytest-justified] method-body ordering — nextLightboxVideo() 抽方法體
    # 驗 this.currentIndex = result.oldLength 位置 < playLightboxSwitch 位置（同型 state-first）
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


class TestCoverStateGuard:
    # [lint-guard: pytest-justified] method-body scope（_resetCoverState 500-char body）+
    # call-count（file-list.js >=8 / navigation.js >=2 / search-flow.js >=4）+ ordering，
    # node 字串檢查不忠實（CD-96-10）
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
    # [lint-guard: pytest-justified] method-body 共享狀態隔離 regex — _searchFileBackground
    # 抽方法體驗負向斷言（不讀寫 this.currentFileIndex/currentIndex/displayMode/
    # window.SearchUI.showState/searchResults）+ 正向驗證寫 file.searchResults/file.searched
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


class TestLightboxAnimationGuard:
    # [lint-guard: pytest-justified] method-body ordering — _extract_function 抽 3000-char
    # body，驗 kill-timeline/ESC/same-index/switch-path 呼叫順序，跨 grid-mode.js/
    # navigation.js/state-lightbox.js 三檔
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
    # [lint-guard: pytest-justified] method-body 順序 — prevLightboxVideo/nextLightboxVideo/
    # openLightbox 抽方法體驗 lightboxIndex 更新位置 < playLightboxSwitch 位置（state-first）；
    # 另含 onMidpoint 負向斷言 + _lightboxGeneration 存在性
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
    # [lint-guard: pytest-justified] brace-depth 解析 — _get_return_block 逐字元
    # brace-balance 抽取全部 return {...} block（naive forbidden-string 會誤判巢狀邊界）；
    # 另含 _find_statement_end brace/paren nesting 追蹤賦值語句範圍
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


class TestExternalManagerSwitchModeGuard:
    # [lint-guard: pytest-justified] method-body 語意 — confirmSwitchMode 抽方法體驗
    # savedState.externalManager 單-key 同步 + 負守衛（不得整份 re-snapshot）；bs4 掃
    # dialog :class 屬性；HTML 骨架 + i18n 半邊隨 class 留置（不拆）
    """90c-T5: settings.html + state-config.js 全域模式切換破壞性 confirm 靜態守衛。

    四顆 external_manager segmented button 改攔截式 requestExternalManagerChange；
    有離線來源時跳破壞性 confirm modal → 確認呼叫 T4 endpoint → 三處同步。
    每個 assertion mutation-sensitive；element-bound（anchor external-manager row）。
    """

    def _html(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SETTINGS_CONFIG_JS.read_text(encoding="utf-8")

    def _seg_block(self):
        """anchor 到 settings-form-row--external-manager 再抓其 segmented 容器
        （settings.html 有 ≥3 個 settings-sources-segmented、其中 header 膠囊也帶
        role=group，故不可全文 substring — element-bound）。"""
        import re
        content = self._html()
        anchor = content.find("settings-form-row--external-manager")
        assert anchor != -1, "settings.html 缺少 settings-form-row--external-manager 區塊"
        m = re.search(
            r'class="settings-sources-segmented" role="group".*?</div>',
            content[anchor:], re.DOTALL,
        )
        assert m, "settings.html 缺少 .settings-sources-segmented[role=group]（外部管理器）"
        return m.group(0)

    # ── HTML: segmented buttons 改攔截式 ────────────────────────────────────────

    def test_segmented_buttons_call_request_method(self):
        """四顆 button @click 呼叫 requestExternalManagerChange('x')，不再直寫 form。"""
        seg = self._seg_block()
        for val in ("off", "jellyfin", "emby", "kodi"):
            assert f"@click=\"requestExternalManagerChange('{val}')\"" in seg, \
                f"segmented 缺少 @click=\"requestExternalManagerChange('{val}')\""
            assert f"@click=\"form.externalManager = '{val}'\"" not in seg, \
                f"segmented 不應殘留舊 @click 直寫 form.externalManager='{val}'"

    # ── HTML: confirm modal ─────────────────────────────────────────────────────

    def test_switch_mode_confirm_modal_exists(self):
        """存在 switch-mode confirm <dialog>：btn-error（破壞性語氣）+ modal-open 綁定 +
        Esc 鏈 + confirmSwitchMode/cancelSwitchMode 呼叫 + {mode}/{count} 插值 body +
        CD-90b-11a 多分頁提醒句 + 不含「風味」。"""
        from bs4 import BeautifulSoup
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        dialog = None
        for d in soup.find_all("dialog"):
            if "switchModeConfirmOpen" in (d.get(":class") or ""):
                dialog = d
                break
        assert dialog is not None, \
            "settings.html 缺少 switch-mode confirm <dialog>（:class 綁 switchModeConfirmOpen）"
        block = str(dialog)
        # modal-open 綁定
        assert "modal-open" in (dialog.get(":class") or ""), \
            "switch-mode dialog :class 缺 'modal-open': switchModeConfirmOpen"
        # 破壞性語氣：btn-error 確認鈕
        assert "btn-error" in block, \
            "switch-mode modal 缺 btn-error 確認鈕（破壞性語氣，CD-90b-13）"
        assert "btn-primary" not in block, \
            "switch-mode modal 不應用 btn-primary（破壞性須 btn-error）"
        # Esc 鏈（modal 級）— 讀 attr 值（避免 BS4 re-serialize 把 && → &amp;&amp;）
        esc = dialog.get("@keydown.escape.window", "")
        assert "switchModeConfirmOpen" in esc and "cancelSwitchMode()" in esc, \
            "switch-mode modal 缺 @keydown.escape.window Esc 鏈"
        # confirm / cancel 呼叫
        assert "confirmSwitchMode()" in block, "switch-mode modal 缺 confirmSwitchMode() 呼叫"
        assert "cancelSwitchMode()" in block, "switch-mode modal 缺 cancelSwitchMode() 呼叫"
        # {mode}/{count} 插值 body（走 i18n key）
        assert "settings.switch_mode_confirm.body" in block, \
            "switch-mode modal 缺 settings.switch_mode_confirm.body i18n 引用"
        assert "pendingOfflineCount" in block, \
            "switch-mode modal body 缺 count: pendingOfflineCount 插值"
        # 不出現「風味」
        assert "風味" not in block, "switch-mode modal 不應出現「風味」（白話模式名）"

    # ── JS: 三方法 + stub ───────────────────────────────────────────────────────

    def test_state_config_defines_methods_and_stubs(self):
        """state-config.js 定義 3 方法 + 3 stub（皆在既有 factory 內，無新 init()）。"""
        js = self._js()
        for name in ("requestExternalManagerChange", "confirmSwitchMode", "cancelSwitchMode"):
            assert name in js, f"state-config.js 缺少方法 {name}"
        for stub in ("switchModeConfirmOpen", "pendingExternalManager", "pendingOfflineCount"):
            assert stub in js, f"state-config.js 缺少 data stub {stub}"

    def test_request_method_realtime_fetch_and_guard(self):
        """requestExternalManagerChange 即時 fetch /api/config（非快取）+ 同值 guard return。"""
        import re
        js = self._js()
        m = re.search(
            r"requestExternalManagerChange\s*\([^)]*\)\s*\{.*?\n        \},",
            js, re.DOTALL,
        )
        assert m, "state-config.js 找不到 requestExternalManagerChange 方法體"
        body = m.group(0)
        assert "this.form.externalManager === val" in body, \
            "requestExternalManagerChange 缺同值 guard return"
        assert "fetch('/api/config')" in body, \
            "requestExternalManagerChange 缺即時 fetch('/api/config')（CD-90b-11 ②）"
        assert "readonly === true" in body, \
            "requestExternalManagerChange 缺 readonly 離線來源枚舉"

    def test_confirm_syncs_three_places_single_key_savedstate(self):
        """confirmSwitchMode 同步三處：form.externalManager + savedState.externalManager（單 key）
        + scannerDirectories 回填；不得整份 re-snapshot savedState。"""
        import re
        js = self._js()
        m = re.search(
            r"confirmSwitchMode\s*\([^)]*\)\s*\{.*?\n        \},",
            js, re.DOTALL,
        )
        assert m, "state-config.js 找不到 confirmSwitchMode 方法體"
        body = m.group(0)
        assert "switch-external-manager" in body, \
            "confirmSwitchMode 缺 POST /api/config/switch-external-manager"
        assert "this.form.externalManager = val" in body, \
            "confirmSwitchMode 缺 form.externalManager 同步"
        assert "this.savedState.externalManager = val" in body, \
            "confirmSwitchMode 缺 savedState.externalManager 單 key 同步"
        assert "this.scannerDirectories" in body, \
            "confirmSwitchMode 缺 scannerDirectories 回填"
        # 負守衛：不可整份 re-snapshot（會清掉其他未存 form dirty 態）
        assert "savedState = JSON.parse" not in body, \
            "confirmSwitchMode 不應整份 re-snapshot savedState（須單 key 同步）"

    def test_confirm_generate_in_progress_specific_toast(self):
        """Finding 2：confirmSwitchMode 失敗時依 reason 分流——generate_in_progress
        顯示專屬提示 key（非只泛用 failed），指路使用者等產生完成。"""
        import re
        js = self._js()
        m = re.search(r"confirmSwitchMode\s*\([^)]*\)\s*\{.*?\n        \},", js, re.DOTALL)
        assert m, "state-config.js 找不到 confirmSwitchMode 方法體"
        body = m.group(0)
        assert "generate_in_progress" in body, \
            "confirmSwitchMode 失敗分流缺 generate_in_progress reason 判斷"
        assert "settings.switch_mode_confirm.generate_in_progress" in body, \
            "confirmSwitchMode 缺 generate_in_progress 專屬 toast i18n key"

    # ── i18n: zh_TW only ────────────────────────────────────────────────────────

    def test_zh_tw_switch_mode_confirm_keys(self):
        """zh_TW.json 含 settings.switch_mode_confirm.{title,body,cancel,confirm}，body 非空
        且含 {mode}/{count} 插值（zh_TW only，不做四語 parity）。"""
        import json
        data = json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        node = data.get("settings", {}).get("switch_mode_confirm")
        assert node is not None, "zh_TW.json 缺 settings.switch_mode_confirm 節點"
        for key in ("title", "body", "cancel", "confirm", "generate_in_progress"):
            assert node.get(key), f"zh_TW.json settings.switch_mode_confirm.{key} 缺或空"
        assert "{mode}" in node["body"] and "{count}" in node["body"], \
            "settings.switch_mode_confirm.body 缺 {mode}/{count} 插值"
        assert "風味" not in node["body"], "switch_mode_confirm.body 不應出現「風味」"
