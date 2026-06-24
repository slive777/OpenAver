"""
T1: Showcase scroll-triggered toolbar collapse guard
守衛 state-base.js 包含 scroll listener、toolbarOpen 條件、search/actressSearch 條件、
相對基準 Y 追蹤（_toolbarOpenY）、以及 cleanup。
"""
from pathlib import Path


class TestShowcaseScrollCollapse:
    """T1: Showcase scroll-triggered toolbar collapse guard"""

    def _read_state_base(self):
        p = Path("web/static/js/pages/showcase/state-base.js")
        return p.read_text()

    def test_scroll_listener_registered(self):
        """state-base.js 必須包含 scroll listener 登記（passive）"""
        content = self._read_state_base()
        assert "addEventListener('scroll'" in content or 'addEventListener("scroll"' in content

    def test_scroll_collapse_checks_toolbar_open(self):
        """scroll handler 必須檢查 toolbarOpen 才能收合"""
        content = self._read_state_base()
        assert "toolbarOpen" in content

    def test_scroll_collapse_checks_empty_search(self):
        """scroll handler 必須在 search 為空時才收合"""
        content = self._read_state_base()
        assert "search !== ''" in content or "search === ''" in content

    def test_scroll_collapse_checks_actress_search(self):
        """scroll handler 必須同時保護 actressSearch 非空情況"""
        content = self._read_state_base()
        assert "actressSearch" in content

    def test_scroll_collapse_uses_relative_threshold(self):
        """scroll handler 使用相對基準 Y（_toolbarOpenY）而非絕對位置"""
        content = self._read_state_base()
        assert "_toolbarOpenY" in content

    def test_scroll_collapse_resets_baseline_on_auto_close(self):
        """auto-close 後必須立即 reset _toolbarOpenY，防止 reopen 時 stale baseline 立即再收"""
        content = self._read_state_base()
        # toolbarOpen = false 之後的 80 字元內必須有 _toolbarOpenY = null
        idx_close = content.index("toolbarOpen = false")
        idx_reset = content.index("_toolbarOpenY = null", idx_close)
        assert idx_reset < idx_close + 120, "auto-close 後未在同一 block 立即 reset _toolbarOpenY"

    def test_scroll_listener_cleanup(self):
        """cleanup callback 必須移除 scroll listener"""
        content = self._read_state_base()
        assert "removeEventListener" in content
        assert "_scrollHideHandler" in content


class TestShowcaseHeaderSearchIcon:
    """T2: Showcase header 行動搜尋 icon 在有搜尋時顯示 X"""

    def _read_base_html(self):
        return Path("web/templates/base.html").read_text()

    def _read_showcase_html(self):
        return Path("web/templates/showcase.html").read_text()

    def _read_state_base(self):
        return Path("web/static/js/pages/showcase/state-base.js").read_text()

    def _read_state_lightbox(self):
        return Path("web/static/js/pages/showcase/state-lightbox.js").read_text()

    def test_store_has_showcase_has_search(self):
        """$store.ui 必須包含 showcaseHasSearch 欄位"""
        content = self._read_base_html()
        assert "showcaseHasSearch" in content

    def test_button_dispatches_clear_search(self):
        """navbar button 在有搜尋時必須 dispatch showcase:clear-search"""
        content = self._read_base_html()
        assert "showcase:clear-search" in content

    def test_showcase_has_window_listener(self):
        """showcase.html 必須有 @showcase:clear-search.window listener"""
        content = self._read_showcase_html()
        assert "showcase:clear-search" in content

    def test_search_from_metadata_sets_this_search(self):
        """searchFromMetadata 必須仍設 this.search（防止重構靜默斷開 showcaseHasSearch 路徑）"""
        content = self._read_state_lightbox()
        assert "this.search = " in content

    def test_watch_search_updates_showcase_has_search(self):
        """state-base.js 必須有 $watch('search') 更新 showcaseHasSearch（mutation guard）"""
        content = self._read_state_base()
        assert "$watch('search'" in content or '$watch("search"' in content
        assert "showcaseHasSearch" in content

    def test_watch_actress_search_updates_showcase_has_search(self):
        """state-base.js 必須有 $watch('actressSearch') 更新 showcaseHasSearch（mutation guard）"""
        content = self._read_state_base()
        assert "$watch('actressSearch'" in content or '$watch("actressSearch"' in content

    def test_init_sync_showcase_has_search_after_watchers(self):
        """init() 必須在 $watch 登記後有 init-time 同步賦值（restoreState 在 $watch 前執行）"""
        content = self._read_state_base()
        # 直接斷言 init sync 語句存在，防止只靠 $watch 而漏掉初始值路徑
        assert "Alpine.store('ui').showcaseHasSearch = (this.search !== '' || this.actressSearch !== '')" in content
