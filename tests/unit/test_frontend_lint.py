"""前端靜態守衛 — 確保 template 包含必要的 Alpine 綁定"""
import json
import re
from pathlib import Path

import pytest

SHOWCASE_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "showcase.html"


SEARCH_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "search.html"


SHOWCASE_BASE_JS     = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
SHOWCASE_VIDEOS_JS   = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js"
SHOWCASE_ACTRESS_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-actress.js"
SHOWCASE_LIGHTBOX_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
SHOWCASE_MAIN_JS     = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "main.js"


SETTINGS_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "settings.html"
SCANNER_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "scanner.html"
SCANNER_SCAN_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
SCANNER_BATCH_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-batch.js"
SCANNER_ALIAS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-alias.js"
SCANNER_MAIN_JS  = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "main.js"
MOTION_LAB_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "motion_lab.html"
THEME_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "theme.css"
TAILWIND_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "tailwind.css"

BASE_HTML_T76 = Path(__file__).parent.parent.parent / "web" / "templates" / "base.html"

APPLE_TOUCH_ICON_PNG = Path(__file__).parent.parent.parent / "web" / "static" / "apple-touch-icon.png"
# theme-color 兩個白名單 hex，須與 CSS --color-base-100 token 換算一致
# （dim=[data-theme=dim] base-100、light=[data-theme=light] base-100）
THEME_COLOR_DIM = "#2a303c"
THEME_COLOR_LIGHT = "#ffffff"


# [lint-guard: migrate→96e] CSS 半邊已遷 css-guard CG-XP-04（theme.css view-transition anchors）；
# 整 class 刪除由 96e 在所有半邊網綠後執行（CD-96-12）。base.html DOM 半邊仍 pytest。
class TestPageTransitionDomGuard:
    """feature/76 T1: Cross-Document View Transitions DOM + CSS 契約守衛。

    全 substring/regex 正向存在性（非行號 allowlist）。守衛 base.html 命名錨點 +
    theme.css opt-in / 命名 / showcase opt-out。settings.css root 作用域化屬 T1a，
    head skipTransition script 屬 T-showcase，皆不在此守衛。
    """

    def _base(self):
        return BASE_HTML_T76.read_text(encoding="utf-8")

    def _theme(self):
        return THEME_CSS.read_text(encoding="utf-8")

    def test_base_html_main_content_id(self):
        """base.html <main> 含 id="main-content"（CD-4，T1 新增的命名錨點）"""
        assert 'id="main-content"' in self._base(), \
            "base.html <main> 缺少 id=\"main-content\"（feature/76 CD-4）"

    def test_base_html_sidebar_id(self):
        """base.html <nav> 含 id="sidebar"（現狀錨點，防回歸——VT 持久化依賴此 id）"""
        assert 'id="sidebar"' in self._base(), \
            "base.html <nav> 缺少 id=\"sidebar\"（feature/76 CD-3 sidebar 持久化依賴）"

    def test_theme_css_view_transition_opt_in(self):
        """theme.css 含 @view-transition + navigation: auto（CD-1 全站 opt-in）"""
        css = self._theme()
        assert "@view-transition" in css, "theme.css 缺少 @view-transition at-rule（feature/76 CD-1）"
        assert re.search(r"@view-transition\s*\{\s*navigation:\s*auto", css), \
            "theme.css @view-transition 缺少 navigation: auto（feature/76 CD-1）"

    def test_theme_css_named_elements(self):
        """theme.css 含 sidebar / main-content 兩個 view-transition-name（CD-2/CD-3）"""
        css = self._theme()
        assert "view-transition-name: sidebar" in css, \
            "theme.css 缺少 view-transition-name: sidebar（feature/76 CD-3）"
        assert "view-transition-name: main-content" in css, \
            "theme.css 缺少 view-transition-name: main-content（feature/76 CD-2）"

    def test_theme_css_showcase_optout(self):
        """theme.css 含 showcase opt-out 單行（CD-11 輔助：.page-showcase + name:none）"""
        css = self._theme()
        assert re.search(r"\.page-showcase\s+#main-content\s*\{\s*view-transition-name:\s*none", css), \
            "theme.css 缺少 .page-showcase #main-content { view-transition-name: none }（feature/76 CD-11 輔助）"

    def test_theme_css_theme_toggle_denames_named_groups(self):
        """主題切換（same-doc startViewTransition）期間 de-name sidebar/main-content（Codex P1）。

        view-transition-name 對 same-document VT 同樣生效 → 不 de-name 則命名群組脫離 root、
        破壞 theme-transition.js 的圓形 reveal（main-content 還會跑 250ms fade 撞 500ms 圓形）。
        守 html.theme-transition-active 期間兩區 view-transition-name: none。
        """
        css = self._theme()
        assert re.search(
            r"html\.theme-transition-active\s+#sidebar\s*,\s*"
            r"html\.theme-transition-active\s+#main-content\s*\{\s*view-transition-name:\s*none",
            css,
        ), "theme.css 缺少 theme-transition-active 期間 de-name sidebar/main-content（feature/76 Codex P1 主題切換共存）"

    def test_base_html_showcase_skip_script_in_head(self):
        """showcase 硬切 head script（pagereveal/pageswap + skipTransition）存在且在 </head> 之前（CD-11/F8）。

        pagereveal 在 first rendering opportunity 前觸發 → listener 必須在 <head> 的
        parser-blocking classic script，掛在 body 底（如 page-lifecycle.js）會漏接。
        斷言三 token 皆落在 </head> 之前，鎖定位置。
        """
        html = self._base()
        head_end = html.find("</head>")
        assert head_end != -1, "base.html 找不到 </head>"
        head = html[:head_end]
        for token in ("pagereveal", "pageswap", "skipTransition"):
            assert token in head, \
                f"base.html <head> 缺少 {token!r}（feature/76 CD-11 showcase 硬切 head script 必須在 head、非 body 底）"
        # 鎖定 parser-blocking classic：包住 skipTransition 的 <script> open tag 不得有
        # type=module / defer / async（任一都會把 pagereveal 延後過 first render → 漏接、靜默壞掉）。
        skip_idx = head.find("skipTransition")
        open_start = head.rfind("<script", 0, skip_idx)
        open_tag = head[open_start:head.find(">", open_start) + 1]
        for banned in ('type="module"', "type='module'", "defer", "async"):
            assert banned not in open_tag, \
                (f"base.html showcase 硬切 script 的 <script> tag 含 {banned!r}（feature/76 CD-11）："
                 "pagereveal listener 必須是 parser-blocking classic script，defer/async/module 會漏接事件")


SETTINGS_CSS_T76 = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "settings.css"
THEME_TRANSITION_JS_T76 = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "theme-transition.js"


# [lint-guard: migrate→96e] CSS 半邊已遷 css-guard CG-XP-05（settings.css root VT 規則 exhaustive-scope）；
# 整 class 刪除由 96e 在所有半邊網綠後執行（CD-96-12）。theme-transition.js lifecycle 半邊仍 pytest。
class TestPageTransitionSettingsScopeGuard:
    """feature/76 T1a（CD-7/F7）：settings.css root 規則作用域化 + theme-transition.js class lifecycle。

    防 settings.css 裸 ::view-transition-*(root) 規則汙染導航到 /settings、/design-system 的
    跨頁 root crossfade。negative 守衛（無裸 root 規則）是關鍵——只查 positive substring 會
    假陽性（漏抓新增的裸規則）。
    """

    # CSS 註解內可能出現字面 pseudo，先 strip 避免假陽性
    _COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
    _ROOT_PSEUDO_RE = re.compile(r"::view-transition-(?:old|new|group|image-pair)\(root\)")
    _REQUIRED_PREFIX = "html.theme-transition-active"

    def _settings_css(self):
        return SETTINGS_CSS_T76.read_text(encoding="utf-8")

    def _theme_js(self):
        return THEME_TRANSITION_JS_T76.read_text(encoding="utf-8")

    def test_settings_root_rules_scoped(self):
        """settings.css root 規則已加 html.theme-transition-active 前綴（positive）"""
        assert f"{self._REQUIRED_PREFIX}::view-transition-old(root)" in self._settings_css(), \
            "settings.css root 規則未作用域化（缺 html.theme-transition-active 前綴，feature/76 CD-7）"

    def test_settings_all_root_rules_scoped(self):
        """settings.css 中『每一條』root VT 規則都恰以 html.theme-transition-active 作用域化（negative，exhaustive）。

        SF-2：不只查「無裸 root 規則」，而是窮舉每個 ::view-transition-*(root) 出現點、斷言其緊鄰
        前綴恰為 html.theme-transition-active。封住「錯誤前綴」盲區——裸規則、`:root::`、`.foo::`
        等任何非 theme-transition-active 前綴皆會被抓（lookbehind 排除法漏抓後兩者）。
        """
        css_nc = self._COMMENT_RE.sub("", self._settings_css())
        for m in self._ROOT_PSEUDO_RE.finditer(css_nc):
            prefix = css_nc[:m.start()]
            assert prefix.endswith(self._REQUIRED_PREFIX), \
                ("settings.css 有未以 html.theme-transition-active 作用域化的 root VT 規則"
                 f"（feature/76 CD-7/F7）: ...{css_nc[max(0, m.start() - 40):m.end()]!r}")

    def test_theme_transition_js_class_lifecycle(self):
        """theme-transition.js 在 startViewTransition 前 add、finished 後 remove theme-transition-active（F7）"""
        js = self._theme_js()
        assert "classList.add('theme-transition-active')" in js, \
            "theme-transition.js 缺少 classList.add('theme-transition-active')（feature/76 F7）"
        assert "transition.finished" in js, \
            "theme-transition.js 缺少 transition.finished（class remove 掛點，feature/76 F7）"
        assert "classList.remove('theme-transition-active')" in js, \
            "theme-transition.js 缺少 classList.remove('theme-transition-active')（feature/76 F7）"


BATCH_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "batch.js"
SEARCH_FLOW_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "search-flow.js"
BASE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "base.js"
SETTINGS_CONFIG_JS    = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
SETTINGS_PROVIDERS_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-providers.js"
SETTINGS_UI_JS        = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-ui.js"
SEARCH_FILE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "file.js"


MAIN_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "main.js"


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
        # 用鍵盤 handler 特有的註釋行作為錨，避免誤中 swipe handler 的
        # `if (this.sampleGalleryOpen)` 短路（81c-T2 起 swipe 也含此條件）。
        block = self._extract_block(content, '// 4. Sample Gallery 開啟時的快捷鍵')
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

    # ----- 71-T7: video delete trash button + delete modal + x-trap（element-bound）-----

    def test_t7_delete_trash_button_in_lightbox_details_row(self):
        """[transient-guard] 71b-T1：垃圾桶鈕在 info panel 的 `.lb-details`（番號·片商·日期·size
        那一行）行末，靠右常駐 muted icon，綁 openDeleteVideoModal()。搬位 / relayout 是一次性 —
        舊斷言（鈕在 .cover-actions / .lb-delete-strip 內）失效屬預期。"""
        html = self._html()
        # 抽 .lb-details 區塊（內部僅 span/a/button，無巢狀 div → 第一個 </div> 即其收尾）
        m = re.search(
            r'<div class="lb-details">(.*?)</div>',
            html, re.DOTALL,
        )
        assert m, '.lb-details（metadata 行）區塊不存在'
        block = m.group(1)
        # 垃圾桶 button：抽出綁 openDeleteVideoModal() 的 <button> tag，三要素同 tag
        btn = re.search(r'<button\b[^>]*openDeleteVideoModal\(\)[^>]*>.*?</button>',
                        block, re.DOTALL)
        assert btn, '.lb-details 行末缺綁 openDeleteVideoModal() 的垃圾桶 button'
        btn_html = btn.group(0)
        assert 'lb-delete-btn' in btn_html, \
            f'垃圾桶 button 缺 .lb-delete-btn class（muted info-panel 樣式）: {btn_html!r}'
        assert 'bi-trash' in btn_html, f'垃圾桶 button 缺 bi-trash icon: {btn_html!r}'
        assert "t('showcase.video.delete')" in btn_html, \
            f'垃圾桶 button 缺 i18n showcase.video.delete: {btn_html!r}'

    def test_t7_delete_modal_contract(self):
        """delete-video modal：deleteVideoModalOpen + 標題 i18n + confirm/cancel handler 綁同一 dialog。"""
        html = self._html()
        # 抽 deleteVideoModalOpen 綁定的 <dialog> ... </dialog>
        m = re.search(
            r'<dialog\b[^>]*deleteVideoModalOpen[^>]*>(.*?)</dialog>',
            html, re.DOTALL,
        )
        assert m, 'delete-video <dialog>（綁 deleteVideoModalOpen）不存在'
        dialog_open_tag = m.group(0)[:m.group(0).find('>') + 1]
        block = m.group(1)
        assert 'fluent-modal' in dialog_open_tag, \
            f'delete modal 缺 fluent-modal class: {dialog_open_tag!r}'
        assert "showcase.video.delete_modal.title" in block, \
            'delete modal 缺 i18n delete_modal.title'
        assert 'confirmDeleteVideo()' in block, 'delete modal 缺 confirmDeleteVideo() 確認 handler'
        assert 'cancelDeleteVideo()' in block, 'delete modal 缺 cancelDeleteVideo() 取消 handler'

    def test_t7_xtrap_releases_on_delete_modal(self):
        """燈箱 x-trap 行必須含 deleteVideoModalOpen（modal 開時釋放 trap 給 modal）。
        錨定 lightbox 已知條件字串（非 re.search 第一個 match），防面板 x-trap 混淆。
        """
        html = self._html()
        m = re.search(r'x-trap\.inert="([^"]*deleteVideoModalOpen[^"]*)"', html)
        assert m, 'showcase.html 缺含 deleteVideoModalOpen 的 x-trap.inert 行'
        expr = m.group(1)
        assert 'deleteVideoModalOpen' in expr, \
            f'x-trap.inert 未含 deleteVideoModalOpen（delete modal 開時 trap 未釋放）: {expr!r}'


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


class TestTutorialSkipPersistsGuard:
    """TASK-79-T7 (issue #63): 教學「跳過」必須視為看完並持久化。

    bug 根因：skip() 呼叫 complete(false) → 不持久化 → 重進 /scanner 又彈。
    修法：skip() 改走 complete(true)（持久化路徑，含 API 失敗的 localStorage fallback）。
    三個 dismiss 入口（跳過 / X / 背景遮罩）共用 skip()，一改全到位。

    Mutation 忠實度：把 skip() 改回 complete(false) 必須讓本守衛 RED。
    """

    def test_skip_persists_and_shares_entry(self):
        js = Path("web/static/js/components/tutorial.js").read_text(encoding="utf-8")

        # 抓 skip() 方法體（容忍空白）
        m = re.search(r"\bskip\s*\(\s*\)\s*\{(.*?)\}", js, re.DOTALL)
        assert m, "tutorial.js 找不到 skip() 方法"
        body = m.group(1)

        # 1a) bug pattern 消失：skip() 不再呼叫 complete(false)
        assert not re.search(r"complete\(\s*false\s*\)", body), \
            "skip() 不得呼叫 complete(false)（issue #63：跳過必須持久化，否則重進 /scanner 又彈）"

        # 1b) 確有寫入動作：complete(true) 或 localStorage.setItem 或 POST /api/tutorial-completed
        assert (
            re.search(r"complete\(\s*true\s*\)", body)
            or "localStorage.setItem" in body
            or "/api/tutorial-completed" in body
        ), "skip() 必須走持久化路徑（complete(true) / localStorage.setItem / POST /api/tutorial-completed 其一）"

        # 2) 三個 dismiss 入口仍共用 skip()（tutorialSkip / tutorialClose / overlay 背景 click）
        assert js.count("this.skip()") >= 3, \
            "三個 dismiss 入口（跳過 / X / 背景遮罩）必須仍共用 this.skip()（≥3 處綁定）"


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


class TestReadonlySourceErrorToastGuard:
    """88c-P2: scanner/state-scan.js done handler 的完成 toast 須依 source_errors 分流。

    唯讀來源整源失敗（readonly_stats.source_errors > 0）時 toast 不可純 success，
    須走 warn；後端完成通知已同步納入 source_errors（Codex P2）。
    """

    def test_done_toast_consults_source_errors(self):
        js = SCANNER_SCAN_JS.read_text(encoding="utf-8")
        assert "data.readonly_stats" in js and "source_errors" in js, \
            "scanner/state-scan.js done toast 未 consult readonly_stats.source_errors"
        # 完成 toast 區塊須有依 source_errors 分流的 warn 分支
        idx = js.find("const srcErrors")
        assert idx != -1, "scanner/state-scan.js 缺 srcErrors 分流變數"
        # 89b-T6：block 內新增 noOutput/unreachable/partial 宣告與 parts.push 後，
        # 'warn' 字串位置後移，window 需放寬（原 800 不足以涵蓋整個 if/else block）。
        window = js[idx:idx + 1300]
        assert "'warn'" in window or '"warn"' in window, \
            "scanner/state-scan.js source_errors 分支缺 warn toast"

    def test_done_toast_consults_per_video_failed(self):
        """PR#91 ②：完成 toast 也須 consult 個別影片失敗數（readonly_stats.failed），
        failed>0 時走 warn 而非純 success。"""
        js = SCANNER_SCAN_JS.read_text(encoding="utf-8")
        idx = js.find("const srcErrors")
        assert idx != -1, "scanner/state-scan.js 缺 srcErrors 分流變數"
        window = js[idx:idx + 1300]
        assert ".failed" in window, \
            "scanner/state-scan.js 完成 toast 未 consult readonly_stats.failed"
        assert "'warn'" in window or '"warn"' in window, \
            "scanner/state-scan.js failed 分支缺 warn toast"

    def test_done_toast_consults_no_output_unreachable_partial(self):
        """89b-T6 Codex P1：完成通知後端 warn-gate 已納入 no_output/unreachable/partial
        （web/routers/scanner.py），但 scanner 頁自己的完成 toast 未同步 consult，
        三種情境仍顯示 success，違反 spec §89b.3.3「警告並略過，不誤報成功」。
        本測試鎖住 done handler 也讀 readonly_stats.no_output/unreachable/partial，
        且三者各自有走 warn 的分支。"""
        js = SCANNER_SCAN_JS.read_text(encoding="utf-8")
        idx = js.find("const srcErrors")
        assert idx != -1, "scanner/state-scan.js 缺 srcErrors 分流變數"
        window = js[idx:idx + 1200]

        assert "const noOutput" in window and "readonly_stats" in window and ".no_output" in window, \
            "scanner/state-scan.js 完成 toast 未 consult readonly_stats.no_output"
        assert "const unreachable" in window and ".unreachable" in window, \
            "scanner/state-scan.js 完成 toast 未 consult readonly_stats.unreachable"
        assert "const partial" in window and ".partial" in window, \
            "scanner/state-scan.js 完成 toast 未 consult readonly_stats.partial"

        # warn 判斷條件須把三者都納入（而非只判斷 srcErrors/failedCount）
        cond_idx = window.find("if (srcErrors > 0")
        assert cond_idx != -1, "scanner/state-scan.js 找不到完成 toast 的 warn 判斷條件"
        cond_line_end = window.find(")", window.find(") {", cond_idx))
        cond_window = window[cond_idx:cond_idx + 300]
        assert "noOutput > 0" in cond_window, \
            "scanner/state-scan.js warn 判斷條件未納入 noOutput > 0"
        assert "unreachable > 0" in cond_window, \
            "scanner/state-scan.js warn 判斷條件未納入 unreachable > 0"
        assert "partial > 0" in cond_window, \
            "scanner/state-scan.js warn 判斷條件未納入 partial > 0"

        # pruned 是正常成功結果，不應被納入 warn 判斷
        assert "pruned > 0" not in cond_window, \
            "scanner/state-scan.js warn 判斷條件不應納入 pruned（prune 非警告）"


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


SHOWCASE_ANIMATIONS_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "animations.js"
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


# [lint-guard: migrate→96e] CSS 半邊已遷 css-guard CG-XP-03（showcase.css footer + 640px media-value）；
# 整 class 刪除由 96e 在所有半邊網綠後執行（CD-96-12）。showcase.html 結構半邊仍 pytest。
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


# ─── 81c-T1: swipe helper 純函式守衛 ──────────────────────────────────────────
SWIPE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "swipe.js"


class TestSwipeHelperGuard:
    """81c-T1: 守衛 shared/swipe.js 的 detectSwipe 純函式（簽名 + 核心判別式 + threshold 不寫死）。

    因專案無 JS 測試框架，邏輯正確性由 T2–T4 真機驗證；此守衛靜態鎖死函式存在、
    五參數簽名、軸判別 `|dX|>|dY|`（防退化回只判水平）、threshold 由參數傳入（不寫死 50）、
    left/right 方向字串皆存在。
    """

    def test_swipe_js_exists(self):
        assert SWIPE_JS.exists(), f"swipe.js 不存在：{SWIPE_JS}"

    def test_detect_swipe_signature(self):
        """export function detectSwipe 五參數簽名存在"""
        js = SWIPE_JS.read_text(encoding="utf-8")
        pattern = re.compile(
            r"export\s+function\s+detectSwipe\s*\(\s*"
            r"startX\s*,\s*startY\s*,\s*endX\s*,\s*endY\s*,\s*threshold\s*\)"
        )
        assert pattern.search(js), \
            "swipe.js 缺少 export function detectSwipe(startX, startY, endX, endY, threshold) 簽名"

    def test_axis_discrimination_present(self):
        """軸判別式 Math.abs(dX) > Math.abs(dY) 存在（CD-2，防退化回只判水平）"""
        js = SWIPE_JS.read_text(encoding="utf-8")
        assert "Math.abs(dX) > Math.abs(dY)" in js, \
            "swipe.js 缺少軸判別 'Math.abs(dX) > Math.abs(dY)'（垂直捲動會誤觸）"

    def test_threshold_from_param_not_hardcoded(self):
        """threshold 判別 Math.abs(dX) > threshold 存在，且不寫死 50"""
        js = SWIPE_JS.read_text(encoding="utf-8")
        assert "Math.abs(dX) > threshold" in js, \
            "swipe.js 缺少 threshold 判別 'Math.abs(dX) > threshold'"
        # 判別式不可寫死 50（threshold 由呼叫端傳入，CD-1）
        assert "Math.abs(dX) > 50" not in js, \
            "swipe.js 不可寫死 'Math.abs(dX) > 50'（threshold 須由參數傳入）"

    def test_direction_strings_present(self):
        """方向字串 'left' 與 'right' 皆存在"""
        js = SWIPE_JS.read_text(encoding="utf-8")
        assert "'left'" in js, "swipe.js 缺少方向字串 'left'"
        assert "'right'" in js, "swipe.js 缺少方向字串 'right'"


class TestShowcaseSwipeGuard:
    """81c-T2: 守衛 showcase 燈箱 swipe 掛載與 handler 契約。

    靜態鎖死：`.showcase-lightbox` 容器有 `@touchstart.passive` + `@touchend.passive`
    綁定（bs4）；`_lbTouchEnd` handler 含 CD-5 攔截短路串（similar 含 mobile / 四 modal
    / sample gallery）、CD-3 分流（`showFavoriteActresses ?` + 女優/影片四 handler）、
    `detectSwipe(` 呼叫、threshold `50`、且 passive 不 `preventDefault`。
    手勢真實行為由 owner 真機 hard-gate。
    """

    def _js(self):
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _lb_touch_end_block(self):
        """抽出 _lbTouchEnd method 區塊（brace-depth 匹配，與方法擺放位置無關）。"""
        js = self._js()
        start = js.index("_lbTouchEnd(e) {")
        depth = 0
        for i in range(js.index("{", start), len(js)):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[start:i + 1]
        raise AssertionError("_lbTouchEnd: unbalanced braces")

    def test_container_has_touch_bindings(self):
        """`.showcase-lightbox` 容器有 @touchstart.passive + @touchend.passive"""
        from bs4 import BeautifulSoup
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        el = BeautifulSoup(html, "html.parser").select_one("div.showcase-lightbox")
        assert el is not None, "showcase.html 缺少 .showcase-lightbox 容器"
        attrs = el.attrs
        assert ("@touchstart.passive" in attrs or "x-on:touchstart.passive" in attrs), \
            ".showcase-lightbox 缺少 @touchstart.passive 綁定"
        assert ("@touchend.passive" in attrs or "x-on:touchend.passive" in attrs), \
            ".showcase-lightbox 缺少 @touchend.passive 綁定"
        # 綁定指向 _lbTouchStart / _lbTouchEnd
        ts = attrs.get("@touchstart.passive") or attrs.get("x-on:touchstart.passive") or ""
        te = attrs.get("@touchend.passive") or attrs.get("x-on:touchend.passive") or ""
        assert "_lbTouchStart" in ts, "@touchstart.passive 未呼叫 _lbTouchStart"
        assert "_lbTouchEnd" in te, "@touchend.passive 未呼叫 _lbTouchEnd"

    def test_lb_touch_end_intercept_chain(self):
        """_lbTouchEnd 含 CD-5 攔截短路串（similar 含 mobile / 四 modal / sample gallery）"""
        block = self._lb_touch_end_block()
        for token in [
            "similarModeOpen",
            "similarModeMobileOpen",
            "removeActressModalOpen",
            "_pickerOpen",
            "rescrapeOpen",
            "deleteVideoModalOpen",
            "sampleGalleryOpen",
            "lightboxOpen",
        ]:
            assert token in block, f"_lbTouchEnd 缺少攔截短路：{token!r}"

    def test_lb_touch_end_branch_split(self):
        """_lbTouchEnd 含 CD-3 分流（showFavoriteActresses + 女優/影片四 handler，不寫死影片）"""
        block = self._lb_touch_end_block()
        for token in [
            "showFavoriteActresses",
            "prevActressLightbox",
            "nextActressLightbox",
            "prevLightboxVideo",
            "nextLightboxVideo",
        ]:
            assert token in block, f"_lbTouchEnd 缺少分流字串：{token!r}"

    def test_lb_touch_end_uses_detect_swipe_with_threshold(self):
        """_lbTouchEnd 呼叫 detectSwipe 並傳 threshold 50"""
        js = self._js()
        assert "import { detectSwipe } from '@/shared/swipe.js';" in js, \
            "state-lightbox.js 缺少 detectSwipe import"
        block = self._lb_touch_end_block()
        assert "detectSwipe(" in block, "_lbTouchEnd 未呼叫 detectSwipe"
        assert "50" in block, "_lbTouchEnd 未傳 threshold 50"

    def test_lb_touch_end_no_prevent_default(self):
        """_lbTouchEnd 不呼叫 preventDefault（CD-2 passive）"""
        block = self._lb_touch_end_block()
        assert "preventDefault" not in block, \
            "_lbTouchEnd 不可呼叫 preventDefault（passive 掛載）"


class TestSearchSwipeGuard:
    """81c-T3: 守衛 search 燈箱 swipe 掛載與 handler 契約。

    靜態鎖死：search.html `.showcase-lightbox` 容器有 `@touchstart.passive` +
    `@touchend.passive` 綁定（bs4）；grid-mode.js `_lbTouchEnd` handler 含 3 條短路
    （`rescrapeOpen` / `sampleGalleryOpen` / `lightboxOpen`）、直呼 `prevLightboxVideo`
    / `nextLightboxVideo`、`detectSwipe(` 呼叫、threshold `50`、passive 不
    `preventDefault`，且**負向**不含 `showFavoriteActresses`（CD-3，search 無此 state）。
    手勢真實行為由 owner 真機 hard-gate。
    """

    def _js(self):
        return GRID_MODE_JS.read_text(encoding="utf-8")

    def _lb_touch_end_block(self):
        """抽出 _lbTouchEnd method 區塊（brace-depth 匹配，與方法擺放位置無關）。"""
        js = self._js()
        start = js.index("_lbTouchEnd(e) {")
        depth = 0
        for i in range(js.index("{", start), len(js)):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[start:i + 1]
        raise AssertionError("_lbTouchEnd: unbalanced braces")

    def test_container_has_touch_bindings(self):
        """search.html `.showcase-lightbox` 容器有 @touchstart.passive + @touchend.passive"""
        from bs4 import BeautifulSoup
        html = SEARCH_HTML.read_text(encoding="utf-8")
        el = BeautifulSoup(html, "html.parser").select_one("div.showcase-lightbox")
        assert el is not None, "search.html 缺少 .showcase-lightbox 容器"
        attrs = el.attrs
        assert ("@touchstart.passive" in attrs or "x-on:touchstart.passive" in attrs), \
            ".showcase-lightbox 缺少 @touchstart.passive 綁定"
        assert ("@touchend.passive" in attrs or "x-on:touchend.passive" in attrs), \
            ".showcase-lightbox 缺少 @touchend.passive 綁定"
        ts = attrs.get("@touchstart.passive") or attrs.get("x-on:touchstart.passive") or ""
        te = attrs.get("@touchend.passive") or attrs.get("x-on:touchend.passive") or ""
        assert "_lbTouchStart" in ts, "@touchstart.passive 未呼叫 _lbTouchStart"
        assert "_lbTouchEnd" in te, "@touchend.passive 未呼叫 _lbTouchEnd"

    def test_lb_touch_end_intercept_chain(self):
        """_lbTouchEnd 含 3 條攔截短路（rescrape / sampleGallery / lightboxOpen）"""
        block = self._lb_touch_end_block()
        for token in [
            "rescrapeOpen",
            "sampleGalleryOpen",
            "lightboxOpen",
        ]:
            assert token in block, f"_lbTouchEnd 缺少攔截短路：{token!r}"

    def test_lb_touch_end_direct_dispatch(self):
        """_lbTouchEnd 直呼 prevLightboxVideo / nextLightboxVideo（CD-3 直呼）"""
        block = self._lb_touch_end_block()
        for token in [
            "prevLightboxVideo",
            "nextLightboxVideo",
        ]:
            assert token in block, f"_lbTouchEnd 缺少 dispatch 字串：{token!r}"

    def test_lb_touch_end_uses_detect_swipe_with_threshold(self):
        """_lbTouchEnd import 並呼叫 detectSwipe，傳 threshold 50"""
        js = self._js()
        assert "import { detectSwipe } from '@/shared/swipe.js';" in js, \
            "grid-mode.js 缺少 detectSwipe import"
        block = self._lb_touch_end_block()
        assert "detectSwipe(" in block, "_lbTouchEnd 未呼叫 detectSwipe"
        assert "50" in block, "_lbTouchEnd 未傳 threshold 50"

    def test_lb_touch_end_no_prevent_default(self):
        """_lbTouchEnd 不呼叫 preventDefault（CD-2 passive）"""
        block = self._lb_touch_end_block()
        assert "preventDefault" not in block, \
            "_lbTouchEnd 不可呼叫 preventDefault（passive 掛載）"

    def test_lb_touch_end_no_actress_gate(self):
        """負向守衛：_lbTouchEnd 不含 showFavoriteActresses（CD-3，search 無此 state）"""
        block = self._lb_touch_end_block()
        assert "showFavoriteActresses" not in block, \
            "_lbTouchEnd 不可含 showFavoriteActresses（search 無此 state，加 gate 會靜默失效）"


class TestDetailSwipeGuard:
    """81c-T4: 守衛 search detail 封面區 swipe 掛載與 handler 契約。

    靜態鎖死：search.html `.av-card-full-cover-wrapper`（只含海報）容器有
    `@touchstart.passive` + `@touchend.passive` 綁定（bs4），且**隔離**確認掛在
    海報 wrapper 而非整個 detail 卡 `.av-card-full`（避免誤掛 metadata 捲動區）、
    亦非外層 `.av-card-full-cover`（含 `.sample-strip` 水平縮圖捲動列，P2 fix：
    避免橫滑縮圖列誤觸 navigate）、且 `.sample-strip` 本身不可有 touch 綁定；navigation.js
    `_dtTouchEnd` handler 含 3 條短路/gate（`rescrapeOpen` / `sampleGalleryOpen` /
    `displayMode`）、直呼 `navigate(1)` / `navigate(-1)`、`detectSwipe(` 呼叫、
    threshold `50`、passive 不 `preventDefault`，且**負向**不含 `showFavoriteActresses`
    （CD-3，detail 純導航不分流）、不含 `lightboxOpen` / `prevLightboxVideo` /
    `nextLightboxVideo`（detail/燈箱隔離）。手勢真實行為由 owner 真機 hard-gate。
    """

    def _js(self):
        return NAVIGATION_JS.read_text(encoding="utf-8")

    def _dt_touch_end_block(self):
        """抽出 _dtTouchEnd method 區塊（brace-depth 匹配，與方法擺放位置無關）。"""
        js = self._js()
        start = js.index("_dtTouchEnd(e) {")
        depth = 0
        for i in range(js.index("{", start), len(js)):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[start:i + 1]
        raise AssertionError("_dtTouchEnd: unbalanced braces")

    def test_container_has_touch_bindings(self):
        """search.html `.av-card-full-cover-wrapper`（海報區）容器有 @touchstart.passive + @touchend.passive"""
        from bs4 import BeautifulSoup
        html = SEARCH_HTML.read_text(encoding="utf-8")
        el = BeautifulSoup(html, "html.parser").select_one("div.av-card-full-cover-wrapper")
        assert el is not None, "search.html 缺少 .av-card-full-cover-wrapper 容器"
        attrs = el.attrs
        assert ("@touchstart.passive" in attrs or "x-on:touchstart.passive" in attrs), \
            ".av-card-full-cover-wrapper 缺少 @touchstart.passive 綁定"
        assert ("@touchend.passive" in attrs or "x-on:touchend.passive" in attrs), \
            ".av-card-full-cover-wrapper 缺少 @touchend.passive 綁定"
        ts = attrs.get("@touchstart.passive") or attrs.get("x-on:touchstart.passive") or ""
        te = attrs.get("@touchend.passive") or attrs.get("x-on:touchend.passive") or ""
        assert "_dtTouchStart" in ts, "@touchstart.passive 未呼叫 _dtTouchStart"
        assert "_dtTouchEnd" in te, "@touchend.passive 未呼叫 _dtTouchEnd"

    def test_touch_bound_on_wrapper_not_full_card(self):
        """隔離守衛：@touch* 掛在 .av-card-full-cover-wrapper（海報區）而非 .av-card-full（含 metadata 捲動區）"""
        from bs4 import BeautifulSoup
        html = SEARCH_HTML.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        # .av-card-full（整個 detail 卡，含 metadata 區）不可有 touch 綁定
        full = soup.select_one("div.av-card-full")
        assert full is not None, "search.html 缺少 .av-card-full 容器"
        full_attrs = full.attrs
        assert "@touchstart.passive" not in full_attrs and "x-on:touchstart.passive" not in full_attrs, \
            ".av-card-full（整個 detail 卡）不應掛 @touchstart（會誤觸 metadata 捲動區）"
        assert "@touchend.passive" not in full_attrs and "x-on:touchend.passive" not in full_attrs, \
            ".av-card-full（整個 detail 卡）不應掛 @touchend（會誤觸 metadata 捲動區）"

    def test_touch_not_bound_on_cover_or_sample_strip(self):
        """P2 隔離守衛：外層 .av-card-full-cover 與 .sample-strip（水平縮圖捲動列）不可有 touch 綁定

        理由：swipe 掛 .av-card-full-cover 時，sample-strip（overflow-x:auto）是其子元素，
        橫滑縮圖列會誤觸 _dtTouchEnd → navigate(±1)。改掛只含海報的 wrapper，結構排除 strip。
        """
        from bs4 import BeautifulSoup
        html = SEARCH_HTML.read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        for sel, label in [
            ("div.av-card-full-cover", ".av-card-full-cover（外層，含 sample-strip）"),
            ("div.sample-strip", ".sample-strip（水平縮圖捲動列）"),
        ]:
            el = soup.select_one(sel)
            assert el is not None, f"search.html 缺少 {sel} 容器"
            a = el.attrs
            assert "@touchstart.passive" not in a and "x-on:touchstart.passive" not in a, \
                f"{label} 不應掛 @touchstart（橫滑縮圖列會誤觸 navigate）"
            assert "@touchend.passive" not in a and "x-on:touchend.passive" not in a, \
                f"{label} 不應掛 @touchend（橫滑縮圖列會誤觸 navigate）"

    def test_dt_touch_end_intercept_chain(self):
        """_dtTouchEnd 含 3 條短路/gate（rescrape / sampleGallery / displayMode）"""
        block = self._dt_touch_end_block()
        for token in [
            "rescrapeOpen",
            "sampleGalleryOpen",
            "displayMode",
        ]:
            assert token in block, f"_dtTouchEnd 缺少短路/gate：{token!r}"

    def test_dt_touch_end_direct_dispatch(self):
        """_dtTouchEnd 直呼 navigate(1) / navigate(-1)（CD-3 直呼，CD-4 方向）"""
        block = self._dt_touch_end_block()
        for token in [
            "navigate(1)",
            "navigate(-1)",
        ]:
            assert token in block, f"_dtTouchEnd 缺少 dispatch 字串：{token!r}"

    def test_dt_touch_end_uses_detect_swipe_with_threshold(self):
        """navigation.js import 並呼叫 detectSwipe，傳 threshold 50"""
        js = self._js()
        assert "import { detectSwipe } from '@/shared/swipe.js';" in js, \
            "navigation.js 缺少 detectSwipe import"
        block = self._dt_touch_end_block()
        assert "detectSwipe(" in block, "_dtTouchEnd 未呼叫 detectSwipe"
        assert "50" in block, "_dtTouchEnd 未傳 threshold 50"

    def test_dt_touch_end_no_prevent_default(self):
        """_dtTouchEnd 不呼叫 preventDefault（CD-2 passive）"""
        block = self._dt_touch_end_block()
        assert "preventDefault" not in block, \
            "_dtTouchEnd 不可呼叫 preventDefault（passive 掛載）"

    def test_dt_touch_end_no_actress_gate(self):
        """負向守衛：_dtTouchEnd 不含 showFavoriteActresses（CD-3，detail 純導航不分流）"""
        block = self._dt_touch_end_block()
        assert "showFavoriteActresses" not in block, \
            "_dtTouchEnd 不可含 showFavoriteActresses（detail 純導航不分流，CD-3）"

    def test_dt_touch_end_no_lightbox_dispatch(self):
        """負向守衛：_dtTouchEnd 不含 lightbox 字串（detail/燈箱隔離）"""
        block = self._dt_touch_end_block()
        for token in [
            "lightboxOpen",
            "prevLightboxVideo",
            "nextLightboxVideo",
        ]:
            assert token not in block, \
                f"_dtTouchEnd 不可含 {token!r}（detail/燈箱隔離，掛不同容器 / 不同 dispatch）"


# ─── 49b-T4cd: Actress Photo Picker UI/Alpine/SSE 整合守衛 ──────────────────
SHOWCASE_CSS_T4CD = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"


# Removed in T55b — superseded by stylelint:
#   TestSettingsCssHardcoded, TestHelpCssHardcoded, TestDesignSystemCssHardcoded
#     -> declaration-property-value-disallowed-list (transition / filter / box-shadow)
#        + color-no-hex (with design-system.css whole-file ignore).
# Removed in 96c-T4 — migrated to scripts/css-guard.mjs (zero-dep HTML <style> scan,
# no postcss-html dependency):
#   TestMotionLabHtmlHardcoded       -> CG-ML-01 (blur/hex/radius/duration bans)
#   TestMotionLabObjectPositionGuard -> CG-ML-02 (clip-lab object-position / slot width)


# === 從 tests/test_frontend_lint.py 搬移（T55e）===

# --- 以下為搬移自根目錄的 module-level helpers ---
from typing import List, Tuple

# 專案根目錄（T55e: 從根目錄 tests/test_frontend_lint.py 搬移）
PROJECT_ROOT = Path(__file__).parent.parent.parent  # /home/peace/OpenAver


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
        """settings.html externalManager segmented control（T-d2：4 態 segmented，off/jellyfin/emby/kodi）
        - 舊的 x-model="form.jellyfinMode" 已移除（dead field）
        - 舊的 interim :checked / @change checkbox 綁定已移除
        - 舊的 jellyfin_emby 合併態已拆為獨立 jellyfin / emby（T-d2）
        - 新的 4 態 segmented control + trailing hint 版面
        """
        import re
        html_file = PROJECT_ROOT / "web" / "templates" / "settings.html"
        content = html_file.read_text(encoding='utf-8')
        # 舊 dead field 不存在
        assert 'x-model="form.jellyfinMode"' not in content, \
            "settings.html 不應再有 x-model=\"form.jellyfinMode\"（dead field，已由 externalManager 取代）"
        # interim checkbox 綁定已移除（負守衛）
        assert ":checked=\"form.externalManager === 'jellyfin_emby'\"" not in content, \
            "settings.html 不應再有 interim :checked binding（T8 已換 segmented control）"
        assert "@change=\"form.externalManager = $event.target.checked" not in content, \
            "settings.html 不應再有 interim @change checkbox binding（T8 已換 segmented control）"
        # segmented 容器存在
        assert 'class="settings-sources-segmented"' in content, \
            "settings.html 缺少 .settings-sources-segmented 容器（T8 segmented control）"

        # ---- 負守衛（forbidden）：舊 jellyfin_emby binding 不得殘留 ----
        assert "'is-on': form.externalManager === 'jellyfin_emby'" not in content, \
            "settings.html 不應殘留 jellyfin_emby is-on binding（T-d2 已拆四態）"
        assert "@click=\"form.externalManager = 'jellyfin_emby'\"" not in content, \
            "settings.html 不應殘留 @click = 'jellyfin_emby'（T-d2 已拆四態）"

        # ---- 正斷言：四態 is-on（element-bound 到 segmented 區塊）----
        #   從 content 擷取 settings-form-row--external-manager 區塊後再斷言，
        #   確保 is-on 綁在外部管理器的 segmented button 而非其他地方（element-bound）
        # 80a-T3：頁面 header 另有一個 .settings-sources-segmented[role=group]（server-mode 膠囊），
        # 故先 anchor 到外部管理器 row 再抓 segmented，避免誤匹配 header 膠囊（regex 健化）。
        _em_anchor = content.find("settings-form-row--external-manager")
        assert _em_anchor != -1, "settings.html 缺少 settings-form-row--external-manager 區塊"
        seg_match = re.search(
            r'class="settings-sources-segmented" role="group".*?</div>',
            content[_em_anchor:], re.DOTALL
        )
        assert seg_match, "settings.html 缺少 .settings-sources-segmented[role=group] 容器（外部管理器）"
        seg_block = seg_match.group(0)

        for val in ('off', 'jellyfin', 'emby', 'kodi'):
            assert f"'is-on': form.externalManager === '{val}'" in seg_block, \
                f"settings.html segmented 缺少 externalManager === '{val}' 的 is-on binding"
            # 90c-T5：@click 從靜默 form.externalManager='x' 改為攔截式 requestExternalManagerChange('x')
            assert f"@click=\"requestExternalManagerChange('{val}')\"" in seg_block, \
                f"settings.html segmented 缺少 @click=\"requestExternalManagerChange('{val}')\"（90c-T5 攔截）"
            assert f"@click=\"form.externalManager = '{val}'\"" not in seg_block, \
                f"settings.html segmented 不應殘留舊 @click 直寫 form.externalManager='{val}'（90c-T5 已改攔截）"

        # ---- 正斷言：四段 hint x-show（trailing） ----
        for val in ('off', 'jellyfin', 'emby', 'kodi'):
            assert f"x-show=\"form.externalManager === '{val}'\"" in content, \
                f"settings.html 缺少 externalManager === '{val}' 的 hint x-show"

        # ---- 正斷言：off hint 的 i18n key（新增，驗證 T-d3 key 已引用） ----
        assert "external_manager_off_hint" in content, \
            "settings.html 缺少 external_manager_off_hint i18n key 引用（T-d3 key）"
        assert "external_manager_emby_hint" in content, \
            "settings.html 缺少 external_manager_emby_hint i18n key 引用（T-d3 key）"

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


class TestPathContract:
    """路徑契約守衛測試 — 確保路徑處理邏輯集中在 path_utils.py（T7.0）

    4 個守衛測試掃描 production code 禁止模式（T7a-T7e 已全部修正通過）。

    # [lint-guard: pytest-justified] 守 Python 源碼語意（掃 .py 手動 URI strip / file:/// 建構）——
    # 標的是後端 Python 源碼、非 html/js/css 前端靜態字串，永久留 pytest（CD-96a-8c / CD-96-2）。
    """

    # 掃描範圍：core/ web/ windows/ tests/（排除 path_utils.py 本身）
    # T4（feature/78）：擴及 tests/——test 檔手寫 file:/// / [8:] 也擋。  # path-contract-ok
    _SCAN_DIRS = ['core', 'web', 'windows', 'tests']
    _ALLOWED_FILE = 'path_utils.py'
    # 自描述守衛文字（docstring/comment/pattern 變數）以行尾錨點豁免，
    # 避免守衛掃到自己描述禁止 pattern 的文字而自傷。真違規行不會帶此 token。
    _CONTRACT_OK = staticmethod(lambda line, _n: '# path-contract-ok' in line)

    def _collect_py_files(self):
        """收集 core/、web/、windows/、tests/ 下所有 .py 檔（排除 path_utils.py）"""
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
        """掃描 Python 檔，確認無 path[8:] 或 path[len('file:///'):]  手動 URI strip"""  # path-contract-ok
        # 符合 [8:] 或 [len('file:///'):]  # path-contract-ok
        pattern = r'''\[8:\]|\[len\(['"]file:///['"]\):\]'''
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern, exclude_lines=self._CONTRACT_OK)
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
            matches = find_pattern_in_file(py_file, pattern, exclude_lines=self._CONTRACT_OK)
            for line_num, line_content in matches:
                violations.append(
                    f"{py_file.relative_to(PROJECT_ROOT)}:{line_num} — {line_content[:80]}"
                )
        assert len(violations) == 0, (
            f"發現 {len(violations)} 個手動 URI 建構違規（應改用 to_file_uri()）:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_shadow_path_helpers(self):
        """掃描 Python 檔，確認無 def wsl_to_windows_path / def to_file_uri shadow helper"""  # path-contract-ok
        pattern = r'def wsl_to_windows_path|def to_file_uri'  # path-contract-ok
        violations = []
        for py_file in self._collect_py_files():
            matches = find_pattern_in_file(py_file, pattern, exclude_lines=self._CONTRACT_OK)
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

    def test_help_hero_terminal_has_capabilities_base(self):
        """help.html .hero-terminal 帶 data-capabilities-base 屬性（server-aware base_url 來源）。

        81b-T4/T5（US-7）：copy 來源從 window.location.origin 改 server-render base_url，
        經 .hero-terminal 的 data-attr 傳入。值為 Jinja {{ base_url }}，只斷屬性存在。
        mutation：移除 data-capabilities-base → help.js 退 window.location.origin（複製回歸）→ RED。"""
        from bs4 import BeautifulSoup
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        term = BeautifulSoup(html, "html.parser").find(class_="hero-terminal")
        assert term is not None, "help.html 缺少 .hero-terminal 元素"
        assert term.has_attr("data-capabilities-base"), \
            ".hero-terminal 缺少 data-capabilities-base 屬性（US-7 server-aware base_url 來源）"

    def test_help_copy_button_has_aria_label(self):
        """help.html .terminal-copy-btn 為 icon-only（<i class="bi bi-clipboard">）+ a11y 標籤
        （:aria-label 引用 help.hero.copy_curl，鏡像 settings copy 鈕 T6 守衛）。

        Codex P3：T4 換 bi-clipboard icon 後 copy 鈕失去 accessible name → 補 aria-label。
        mutation：移除 :aria-label 或改引用別 key → a11y 斷言 RED。"""
        from bs4 import BeautifulSoup
        html = (PROJECT_ROOT / 'web/templates/help.html').read_text(encoding='utf-8')
        btn = BeautifulSoup(html, "html.parser").find(class_="terminal-copy-btn")
        assert btn is not None, "help.html 缺少 .terminal-copy-btn（curl 複製鈕）"
        assert btn.find("i", class_="bi-clipboard") is not None, \
            ".terminal-copy-btn 缺少 <i class=\"bi bi-clipboard\"> icon"
        aria = btn.get(":aria-label") or btn.get("aria-label")
        assert aria is not None and "help.hero.copy_curl" in aria, \
            f"copy 鈕 aria-label 應引用 help.hero.copy_curl，實際: {aria!r}（P3 a11y 標籤）"

    def test_help_js_copy_uses_capabilities_base_dataset(self):
        """help.js 複製來源讀 dataset.capabilitiesBase（primary），curl 模板用該 base。

        81b-T5（US-7 #7）：base = .hero-terminal?.dataset.capabilitiesBase || window.location.origin。
        防呆 fallback || window.location.origin 刻意保留 — 守衛**不**斷言其不存在（會 false-fail），
        只斷 capabilitiesBase 為 primary 來源 + curl 模板用 derived base。
        mutation：把複製來源改回純 window.location.origin（移除 dataset 讀取）→ capabilitiesBase 消失 → RED。"""
        js = (PROJECT_ROOT / 'web/static/js/pages/help.js').read_text(encoding='utf-8')
        assert "capabilitiesBase" in js, \
            "help.js 缺少 capabilitiesBase（dataset 複製來源 — US-7 #7 primary source）"
        assert "${base}" in js, \
            "help.js curl 模板未用 derived base（應為 `${base}/api/capabilities` — 證 data-attr 是實際來源）"


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


# [lint-guard: pytest-justified｜method-block-scoped gsap.getById scope — CD-96d-5 精神]
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


class TestRescrapeVersionStateGuard:
    """86-T3: state-rescrape.js candidates 短狀態 + routing + confirm contract。"""

    SHARED_DIR = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared"
    SEARCH_STATE_DIR = (
        Path(__file__).parent.parent.parent
        / "web" / "static" / "js" / "pages" / "search" / "state"
    )
    STATE_RESCRAPE_JS = SHARED_DIR / "state-rescrape.js"
    ADVANCED_PICKER_JS = SEARCH_STATE_DIR / "advanced-picker.js"

    def _rescrape(self):
        return self.STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def _picker(self):
        return self.ADVANCED_PICKER_JS.read_text(encoding="utf-8")

    # ── (B) advanced-picker.js: _commitSearchResults helper ──

    def test_commit_search_results_helper_exists(self):
        """CD-86-14: _commitSearchResults method 必須存在於 advanced-picker.js。"""
        src = self._picker()
        assert "_commitSearchResults" in src, (
            "CD-86-14 違規：advanced-picker.js 缺少 _commitSearchResults helper"
        )

    def test_advanced_search_delegates_to_helper(self):
        """CD-86-14: advancedSearch 成功分支必須委派給 _commitSearchResults，不 inline 賦值。
        element-bound：確認 advancedSearch body 內呼叫 _commitSearchResults（不靠字串存在性）。
        """
        src = self._picker()
        m = re.search(
            r"async\s+advancedSearch\s*\([^)]*\)\s*\{.*?this\._commitSearchResults\s*\(",
            src, re.DOTALL,
        )
        assert m, (
            "CD-86-14 違規：advancedSearch body 中未找到 this._commitSearchResults( 呼叫"
        )

    # ── (B) state-rescrape.js: candidates 短狀態 ──

    def test_candidates_state_keys_present(self):
        """86-T3: rescrapeCandidates / rescrapeVersionIdx 必須平鋪定義。"""
        src = self._rescrape()
        for key in ("rescrapeCandidates", "rescrapeVersionIdx"):
            assert key in src, f"state-rescrape.js missing state key: {key}"

    def test_version_methods_present(self):
        """86-T3: rescrapeHasVersions / rescrapeVersionGo 必須存在。"""
        src = self._rescrape()
        for method in ("rescrapeHasVersions", "rescrapeVersionGo"):
            assert method in src, f"state-rescrape.js missing method: {method}"

    # ── (B) routing: search 入口 javlib 不早 return ──

    def test_search_javlib_does_not_early_return_advancedSearch(self):
        """CD-86-8: rescrapeWithSource search+javlib 分支不得無條件 early return advancedSearch。
        守衛：search early return 必須帶 sourceId !== 'javlibrary' 的判斷（只有非 javlib 才走 advancedSearch）。
        element-bound：檢測 search 條件 if-block 的前 400 字元內有 javlibrary（防 file-wide false GREEN）。
        """
        src = self._rescrape()
        # 先找 search 分支位置，再在其後 400 字元內確認 javlibrary 出現（不跨函式）
        m_search = re.search(
            r"rescrapeEntryPoint\s*===\s*['\"]search['\"]",
            src,
        )
        assert m_search, "rescrapeWithSource 中未見 rescrapeEntryPoint === 'search' 判斷"
        # 取 search 分支後 400 字元（足夠涵蓋 if block body，不跨到 _pollCfThenRetry）
        window = src[m_search.start():m_search.start() + 400]
        assert "javlibrary" in window, (
            "CD-86-8 違規：rescrapeWithSource search 分支（前 400 字元）未見 javlibrary 判斷——"
            "search+javlib 可能仍走早 return advancedSearch 路徑"
        )

    # ── (B) switch-source 多版本切換器（T7） ──

    def test_switch_source_takes_candidates_first(self):
        """T7（語意反轉）: switch-source 多版本（candidates.length > 1）進 rescrapeStep='preview'，
        不再直接取 candidates[0] 靜默替換；candidates[0] 僅作單版本 fallback。
        element-bound: switch-source + candidates.length > 1 後 900 字元內必有 rescrapeStep='preview'
        （900 < showcase block 距離，mutation A 移除後 next occurrence 在 4000+ 字元外 → RED）。
        """
        src = self._rescrape()
        m = re.search(
            r"rescrapeEntryPoint\s*===\s*['\"]switch-source['\"]"
            r".*?data\.candidates\s*&&\s*data\.candidates\.length\s*>\s*1",
            src, re.DOTALL,
        )
        assert m, (
            "T7 違規：switch-source 分支缺 candidates.length > 1 多版本分叉"
        )
        # element-bound 900-char window（switch-source multiversion block ~773 chars）
        window = src[m.end():m.end() + 900]
        assert re.search(r"rescrapeStep\s*=\s*['\"]preview['\"]", window), (
            "T7 違規：switch-source candidates.length > 1 分叉（900 字元窗口內）缺 rescrapeStep='preview'——"
            "多版本應進 preview 切換器，不直接取 candidates[0] 靜默替換"
        )

    def test_switch_source_multiversion_enters_preview(self):
        """T7: switch-source 分支 candidates.length > 1 → rescrapeStep = 'preview'。
        element-bound: 先找 switch-source if-block 起點，再在 900 字元窗口內斷言 rescrapeStep='preview'。
        （防 DOTALL 跨 block 假綠；showcase block 的 rescrapeStep 距離 4000+ 字元外）
        """
        src = self._rescrape()
        m = re.search(
            r"rescrapeEntryPoint\s*===\s*['\"]switch-source['\"]"
            r".*?if\s*\(\s*data\.candidates\s*&&\s*data\.candidates\.length\s*>\s*1\s*\)",
            src, re.DOTALL,
        )
        assert m, (
            "T7 違規：switch-source if-block 缺 candidates.length > 1 多版本分叉"
        )
        # 900-char window covers multiversion block body but stops before showcase block
        window = src[m.end():m.end() + 900]
        assert re.search(r"rescrapeStep\s*=\s*['\"]preview['\"]", window), (
            "T7 違規：switch-source candidates.length > 1 if-block body（900 字元內）缺 rescrapeStep='preview'"
        )

    def test_switch_source_confirm_branch_present(self):
        """T7: rescrapeConfirm 必須有 switch-source 分支，body 含 t.arr[t.idx] in-place 替換，
        不含 _commitSearchResults（in-place 替換語意，非搜尋結果提交）。
        element-bound: 鎖定 rescrapeConfirm 的 switch-source 分支起點後 800 字元。
        """
        src = self._rescrape()
        m = re.search(
            r"rescrapeConfirm\s*\(\s*\).*?rescrapeEntryPoint\s*===\s*['\"]switch-source['\"]",
            src, re.DOTALL,
        )
        assert m, (
            "T7 違規：rescrapeConfirm 中未見 rescrapeEntryPoint === 'switch-source' 分支"
        )
        # m.end() 是 switch-source 條件字串結尾，從此往後 800 字元是分支 body
        block = src[m.end():m.end() + 800]
        assert re.search(r"t\.arr\s*\[\s*t\.idx\s*\]", block), (
            "T7 違規：rescrapeConfirm switch-source 分支缺 t.arr[t.idx] in-place 替換"
        )
        assert "_commitSearchResults" not in block, (
            "T7 違規：rescrapeConfirm switch-source 分支不得呼叫 _commitSearchResults"
            "（in-place 替換語意，非搜尋結果提交）"
        )

    # ── (B) confirm: detail_url 取值 .url ──

    def test_confirm_lightbox_detail_url_from_url_field(self):
        """CD-86-13: rescrapeConfirm lightbox 分支 detail_url 值必須來自 rescrapePreview.url。"""
        src = self._rescrape()
        # 確認 .url 在 confirm context 存在
        assert re.search(
            r"rescrapeConfirm.*?detail_url.*?rescrapePreview.*?\.url",
            src, re.DOTALL,
        ), (
            "CD-86-13: rescrapeConfirm 中未見 rescrapePreview.url 取值（detail_url 欄位值）"
        )

    # ── (B) confirm: search 走 helper 非 inline ──

    def test_confirm_search_calls_commit_helper(self):
        """CD-86-14: rescrapeConfirm search 分支必須呼叫 _commitSearchResults，禁 inline。
        element-bound：rescrapeConfirm body 內找 search 分支 + helper 呼叫。
        """
        src = self._rescrape()
        m = re.search(
            r"rescrapeConfirm.*?rescrapeEntryPoint.*?['\"]search['\"].*?_commitSearchResults",
            src, re.DOTALL,
        )
        assert m, (
            "CD-86-14 違規：rescrapeConfirm search 分支未呼叫 _commitSearchResults helper"
        )

    # ── lifecycle 對稱：close/back reset candidates ──

    def test_close_rescrape_resets_candidates(self):
        """lifecycle 對稱：closeRescrape 必須 reset rescrapeCandidates。
        element-bound：在 closeRescrape method 體內找 rescrapeCandidates（允許內層 if block）。
        """
        src = self._rescrape()
        # closeRescrape 函式體可能含有內層 if {...} block，故使用 .*? 而非 [^}]*
        m = re.search(
            r"closeRescrape\s*\(\s*\)\s*\{.*?rescrapeCandidates",
            src, re.DOTALL,
        )
        assert m, "closeRescrape 必須 reset rescrapeCandidates（lifecycle 對稱）"

    def test_back_to_pick_resets_candidates(self):
        """lifecycle 對稱：rescrapeBackToPick 必須 reset rescrapeCandidates。"""
        src = self._rescrape()
        m = re.search(
            r"rescrapeBackToPick\s*\(\s*\)\s*\{[^}]*rescrapeCandidates",
            src, re.DOTALL,
        )
        assert m, "rescrapeBackToPick 必須 reset rescrapeCandidates（lifecycle 對稱）"

    # ── CD-86-P2: javlib search 採用路徑同步 currentQuery ──

    def test_javlib_single_version_search_falls_through_to_preview(self):
        """86 修正（取代過時的 ..._syncs_current_query 守衛）：rescrapeWithSource 的單版本
        分支（data.success）不再於 search 入口靜默 _commitSearchResults + closeRescrape
        early-return，而是 fall through 進 preview 卡（rescrapeStep='preview'）。

        為何過時：原守衛斷言「rescrapeWithSource 單版本 search 分支在 _commitSearchResults
        前同步 currentQuery」。該 search-entry 早 return commit 已移除（單版本 search 一閃
        就關被使用者回報「直接跳過」），採用改由 rescrapeConfirm 的 search 分支負責（query
        同步由 test_javlib_confirm_search_syncs_current_query 涵蓋）。

        element-bound：鎖定 data.success 分支區塊（到 not-found else 的 rescrapeNotFound=true
        為止），斷言 (a) 進入 preview（rescrapeStep='preview'），(b) 該區塊不含
        _commitSearchResults / closeRescrape（單版本不再於 rescrapeWithSource commit/關窗）。
        mutation 驗證：把 _commitSearchResults + closeRescrape 早 return 加回 → RED。
        """
        src = self._rescrape()
        # 取 rescrapeWithSource 內 data.success else-if 區塊（至 not-found else 的 rescrapeNotFound）
        m_ctx = re.search(
            r"else\s+if\s*\(\s*data\s*&&\s*data\.success\s*\)\s*\{(.*?)this\.rescrapeNotFound\s*=\s*true",
            src, re.DOTALL,
        )
        assert m_ctx, (
            "86 修正：未找到 rescrapeWithSource 的 data.success 單版本分支區塊"
        )
        block = m_ctx.group(1)
        # (a) 單版本 fall through 進 preview
        assert re.search(r"rescrapeStep\s*=\s*['\"]preview['\"]", block), (
            "86 修正違規：data.success 單版本分支未進 preview（rescrapeStep='preview' 不可達）"
        )
        # (b) 不再於 rescrapeWithSource 單版本分支 commit / 關窗（已移交 rescrapeConfirm）
        # 比對「呼叫」語法（含 ?. optional chain），避免誤判註解中提及的字串。
        assert not re.search(r"_commitSearchResults\s*\??\.?\s*\(", block), (
            "86 修正違規：data.success 單版本分支仍呼叫 _commitSearchResults——"
            "search 單版本應 fall through 進 preview，採用由 rescrapeConfirm 負責"
        )
        assert not re.search(r"\bcloseRescrape\s*\(", block), (
            "86 修正違規：data.success 單版本分支仍呼叫 closeRescrape early return——"
            "search 單版本應 fall through 進 preview（一閃就關是回報的 bug）"
        )

    def test_javlib_confirm_search_syncs_current_query(self):
        """CD-86-P2: rescrapeConfirm search 採用路徑，在 _commitSearchResults 前
        必須同步 currentQuery（對齊非 javlib 路徑，防 session restore 回舊 query）。

        element-bound：在 rescrapeConfirm 的 search 分支找 currentQuery 賦值，
        確認在同一 if(search) block 的 _commitSearchResults 呼叫之前。
        mutation 驗證：移除補的同步 → RED。
        """
        src = self._rescrape()
        # 鎖定 rescrapeConfirm 函式體中 search 分支，_commitSearchResults 呼叫前的 currentQuery 賦值
        m_ctx = re.search(
            r"rescrapeConfirm\b.*?"
            r"rescrapeEntryPoint\s*===\s*['\"]search['\"]"
            r"(.*?)_commitSearchResults",
            src, re.DOTALL,
        )
        assert m_ctx, (
            "CD-86-P2 違規（rescrapeConfirm）：未在 search 分支 _commitSearchResults 前 "
            "找到 currentQuery 同步——多版本 confirm 採用後 session restore 殘留舊 query"
        )
        block = m_ctx.group(1)
        assert re.search(r"\bthis\.currentQuery\s*=", block), (
            "CD-86-P2 違規（rescrapeConfirm）：_commitSearchResults 前缺少 "
            "this.currentQuery = ... 賦值（對齊 advancedSearch :38 的同步語意）"
        )


# ─── 63c-7: i18n zh_TW（DMM proxy hint + Help metatube SQLite hint）───
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

    def test_advanced_search_toggle_removed_from_quick_toggle_row(self):
        """74c-T1：進階搜尋 toggle 已從 quick-toggle 列退役（負向守衛）。"""
        html = self._html()
        assert 'x-model="form.advancedSearchEnabled"' not in html, \
            "74c-T1 違規：settings.html 仍含 form.advancedSearchEnabled（toggle 應已退役）"
        assert 'id="advancedSearchToggle"' not in html, \
            "74c-T1 違規：settings.html 仍含 id=advancedSearchToggle（toggle 應已退役）"

    def test_download_sample_images_not_duplicated_in_card(self):
        """downloadSampleImages x-model 只出現一次（已從 Card ② 搬走）"""
        html = self._html()
        count = html.count('x-model="form.downloadSampleImages"')
        assert count == 1, \
            f"64b-3 違規：form.downloadSampleImages x-model 出現 {count} 次，應只在 quick-toggle 列（1 次）"

    def test_thumbnail_cache_enabled_in_quick_toggle_row(self):
        """71-T5：封面縮圖快取 toggle（form.thumbnailCacheEnabled）必須在 quick-toggle 列內"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'x-model="form.thumbnailCacheEnabled"' in row_block, \
            "71-T5 違規：form.thumbnailCacheEnabled x-model 必須在 .settings-quick-toggle-row 內"

    def test_thumbnail_cache_has_help_popover_state(self):
        """71-T5：封面縮圖快取區塊必須有 showThumbCacheHelp state binding（Alpine↔HTML API contract）"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'showThumbCacheHelp' in row_block, \
            "71-T5 違規：quick-toggle 列內封面縮圖快取區塊缺少 showThumbCacheHelp state binding"

    # ── 71-T11: 估算搬出 help-popover → confirm modal ──────────────────
    def test_thumbnail_cache_help_popover_no_longer_has_hint_estimate(self):
        """71-T11：help-popover（quick-toggle 列內）不得再含動態估算 hint_estimate x-text（已搬入 confirm modal）"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        assert 'hint_estimate' not in row_block, \
            "71-T11 違規：估算 hint_estimate 必須搬出 help-popover（不得留在 quick-toggle 列內）"

    def test_thumbnail_cache_toggle_has_change_interceptor(self):
        """71-T11：thumbnailCacheEnabled toggle 必須有 @change="onThumbCacheToggleChange()" 攔截（鏡像 metatube）"""
        html = self._html()
        row_start = html.index('class="settings-quick-toggle-row"')
        sec_search_pos = html.index('id="sec-search"')
        row_block = html[row_start:sec_search_pos]
        m = re.search(
            r'<input\b[^>]*x-model="form\.thumbnailCacheEnabled"[^>]*>',
            row_block, re.DOTALL,
        )
        assert m, "71-T11 違規：找不到 form.thumbnailCacheEnabled toggle input"
        tag = m.group(0)
        assert 'onThumbCacheToggleChange()' in tag, \
            "71-T11 違規：thumbnailCacheEnabled toggle 必須在同一 input 上綁 @change=onThumbCacheToggleChange()"
        assert 'x-model="form.thumbnailCacheEnabled"' in tag, \
            "71-T11 違規：thumbnailCacheEnabled toggle 必須保留 x-model（@change 攔截不取代 x-model）"

    def test_thumbnail_cache_confirm_modal_exists(self):
        """71-T11：confirm fluent-modal 存在 + 綁 thumbCacheConfirmOpen + confirm/cancel handler"""
        html = self._html()
        idx = html.find('thumbCacheConfirmOpen')
        assert idx != -1, \
            "71-T11 違規：settings.html 缺少 thumbCacheConfirmOpen confirm modal binding"
        # 抽 thumbCacheConfirmOpen 首次出現的鄰域（modal 區塊）
        block = html[idx - 200: idx + 1200]
        assert 'fluent-modal' in block, \
            "71-T11 違規：thumbCacheConfirmOpen 必須綁在 fluent-modal 上"
        assert 'confirmThumbCacheEnable()' in block, \
            "71-T11 違規：confirm modal 缺少 confirmThumbCacheEnable() 確認 handler"
        assert 'cancelThumbCacheConfirm()' in block, \
            "71-T11 違規：confirm modal 缺少 cancelThumbCacheConfirm() 取消 handler"

    def test_thumbnail_cache_confirm_modal_body_is_dynamic(self):
        """71-T11：confirm modal body 用 x-text 動態替換 {count}/{mb}/{min}（非靜態 SSR）"""
        html = self._html()
        idx = html.find('thumbCacheConfirmOpen')
        assert idx != -1, \
            "71-T11 違規：settings.html 缺少 thumbCacheConfirmOpen confirm modal binding"
        block = html[idx - 200: idx + 1200]
        assert 'confirm_modal.body' in block, \
            "71-T11 違規：confirm modal body 必須引用 settings.thumbnail_cache.confirm_modal.body"
        for token in ("'{count}'", "'{mb}'", "'{min}'"):
            assert token in block, \
                f"71-T11 違規：confirm modal body 必須 .replace({token}, ...) 動態填值"
        assert '_thumbEstimateMin' in block, \
            "71-T11 違規：confirm modal body 必須用 _thumbEstimateMin（HDD 時間估算）"

    # ===== 71b-T2: disable confirm modal contract =====
    STATE_CONFIG_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    STATE_UI_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-ui.js"
    LOCALES_ROOT = Path(__file__).parent.parent.parent / "locales"

    def test_thumb_cache_disable_modal_contract(self):
        """71b-T2：disable fluent-modal 綁 thumbCacheDisableConfirmOpen + i18n title + confirm/cancel handler（element-bound）。"""
        html = self._html()
        # 抽 thumbCacheDisableConfirmOpen 綁定的 <dialog> ... </dialog>
        m = re.search(
            r'<dialog\b[^>]*thumbCacheDisableConfirmOpen[^>]*>(.*?)</dialog>',
            html, re.DOTALL,
        )
        assert m, "71b-T2 違規：缺少綁 thumbCacheDisableConfirmOpen 的 disable <dialog>"
        dialog_open_tag = m.group(0)[:m.group(0).find('>') + 1]
        block = m.group(1)
        assert 'fluent-modal' in dialog_open_tag, \
            f"71b-T2 違規：disable modal 缺 fluent-modal class: {dialog_open_tag!r}"
        assert 'settings.thumbnail_cache.disable_modal.title' in block, \
            "71b-T2 違規：disable modal 缺 i18n disable_modal.title"
        assert 'confirmThumbCacheDisable()' in block, \
            "71b-T2 違規：disable modal 缺 confirmThumbCacheDisable() 確認 handler"
        assert 'cancelThumbCacheDisable()' in block, \
            "71b-T2 違規：disable modal 缺 cancelThumbCacheDisable() 取消 handler"

    def test_thumb_cache_disable_modal_body_releases_mb(self):
        """71b-T2：disable modal body 引用 disable_modal.body 並動態替換 {mb} 釋放估算。"""
        html = self._html()
        m = re.search(
            r'<dialog\b[^>]*thumbCacheDisableConfirmOpen[^>]*>(.*?)</dialog>',
            html, re.DOTALL,
        )
        assert m, "71b-T2 違規：缺少 disable <dialog>"
        block = m.group(1)
        assert 'settings.thumbnail_cache.disable_modal.body' in block, \
            "71b-T2 違規：disable modal body 必須引用 disable_modal.body"
        assert "'{mb}'" in block, \
            "71b-T2 違規：disable modal body 必須 .replace('{mb}', ...) 顯示釋放估算"

    def test_thumb_cache_disable_state_stub_declared(self):
        """71b-T2：state-ui.js 必須先宣告 thumbCacheDisableConfirmOpen stub（Alpine 3 ReferenceError 防護）。"""
        js = self.STATE_UI_JS.read_text(encoding="utf-8")
        assert 'thumbCacheDisableConfirmOpen' in js, \
            "71b-T2 違規：state-ui.js 缺 thumbCacheDisableConfirmOpen state stub"

    def test_thumb_cache_disable_handlers_in_state_config(self):
        """71b-T2：state-config.js 含 disable 流程三件（trigger clear + cancel + confirm handler）。"""
        js = self.STATE_CONFIG_JS.read_text(encoding="utf-8")
        assert '_triggerThumbClear' in js, \
            "71b-T2 違規：state-config.js 缺 _triggerThumbClear()（fire-and-forget POST clear）"
        assert '/api/gallery/thumb/clear' in js, \
            "71b-T2 違規：_triggerThumbClear 必須 POST /api/gallery/thumb/clear"
        assert 'cancelThumbCacheDisable' in js, \
            "71b-T2 違規：state-config.js 缺 cancelThumbCacheDisable()"
        assert 'confirmThumbCacheDisable' in js, \
            "71b-T2 違規：state-config.js 缺 confirmThumbCacheDisable()"

    def test_thumb_cache_disable_clear_gated_on_save_success(self):
        """71b-T2：clear trigger 必綁在 saveConfig 成功分支（prevThumbEnabled true→false 才清，先存才清）。"""
        js = self.STATE_CONFIG_JS.read_text(encoding="utf-8")
        # prevThumbEnabled 與 false 的轉換條件 + _triggerThumbClear 同時出現
        assert re.search(
            r'prevThumbEnabled\b.*thumbnailCacheEnabled\s*===\s*false',
            js, re.DOTALL,
        ), "71b-T2 違規：缺 prevThumbEnabled && thumbnailCacheEnabled===false 的 clear 觸發條件"

    def test_thumb_cache_disable_modal_title_key_in_zh_tw(self):
        """71b-T2：zh_TW.json 含 thumbnail_cache.disable_modal 四鍵（其餘 3 語系留 milestone）。"""
        data = json.loads((self.LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        dm = data.get("settings", {}).get("thumbnail_cache", {}).get("disable_modal", {})
        for key in ("title", "body", "cancel", "confirm"):
            assert dm.get(key), \
                f"71b-T2 違規：zh_TW.json settings.thumbnail_cache.disable_modal.{key} 缺或空"
        assert "{mb}" in dm["body"], \
            "71b-T2 違規：disable_modal.body 必須含 {mb} 釋放估算占位"


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

    # ---- 71-T6: 燈箱封面 blur-up（thumb 底層秒出 → 原圖淡入）----

    def _lightbox_cover_block(self):
        """抽出影片燈箱封面 <div class="lightbox-cover" :class="{'has-cover':…}">…</div> 區塊"""
        html = self._html()
        # 83a modal-hug 給影片 div 加了 :class has-cover（與女優 div 區分）；
        # 83b-T1 在 </div> 後插入說明注釋，故用 has-cover 錨點 + .*?<!-- Metadata Panel 取代 \s*
        m = re.search(r'<div class="lightbox-cover"[^>]*has-cover[^>]*>.*?</div>.*?<!-- Metadata Panel', html, re.S)
        assert m, "showcase.html: 影片燈箱 .lightbox-cover（has-cover :class）區塊不存在"
        return m.group(0)

    def _lb_overlay_img(self):
        """抽出燈箱封面 overlay <img class=\"lb-full\" …>（blur-up 原圖層）"""
        block = self._lightbox_cover_block()
        m = re.search(r'<img class="lb-full"[^>]*>', block, re.S)
        assert m, "showcase.html .lightbox-cover 內缺 overlay <img class=\"lb-full\">（blur-up 原圖層）"
        return m.group(0)

    def test_lb_base_img_keeps_cover_url_and_error(self):
        """71-T6: 底層 <img> 保留 x-ref/cover_url/@error 三態（base 撐容器 + 破圖偵測沿用 base）"""
        block = self._lightbox_cover_block()
        m = re.search(r'<img x-ref="lightboxCoverImg"[^>]*>', block, re.S)
        assert m, "showcase.html .lightbox-cover 缺 base <img x-ref=\"lightboxCoverImg\">"
        base = m.group(0)
        assert ':src="currentLightboxVideo?.cover_url"' in base, \
            "base <img> 須綁 :src=\"currentLightboxVideo?.cover_url\"（快取開啟=小 webp 秒出）"
        assert '@error="handleCoverError(currentLightboxVideo, $event)"' in base, \
            "base <img> 須保留 @error=\"handleCoverError\"（破圖三態留 base，不移 overlay）"

    def test_lb_overlay_img_binds_cover_full_url(self):
        """71-T6: overlay <img class=\"lb-full\"> 須綁 :src=\"currentLightboxVideo?.cover_full_url\"（原圖層）"""
        overlay = self._lb_overlay_img()
        assert ':src="currentLightboxVideo?.cover_full_url"' in overlay, \
            "overlay <img class=\"lb-full\"> 須綁 :src=\"currentLightboxVideo?.cover_full_url\"（原圖載完淡入）"

    def test_lb_overlay_img_load_sets_flag(self):
        """71-T6: overlay <img> 須含 @load=\"_lbFullLoaded=true\"（原圖載完翻旗標觸發淡入）"""
        overlay = self._lb_overlay_img()
        assert re.search(r'@load="_lbFullLoaded\s*=\s*true"', overlay), \
            "overlay <img class=\"lb-full\"> 須含 @load=\"_lbFullLoaded=true\"（原圖載完觸發淡入）"

    def test_lb_overlay_img_class_binds_shown(self):
        """71-T6: overlay <img> 須 :class 綁 lb-full-shown（opacity 0→1 淡入，非 x-show/display:none）"""
        overlay = self._lb_overlay_img()
        assert re.search(r":class=\"\{\s*'lb-full-shown'\s*:\s*_lbFullLoaded\s*\}\"", overlay), \
            "overlay <img class=\"lb-full\"> 須 :class=\"{'lb-full-shown':_lbFullLoaded}\"（CSS opacity 淡入）"
        assert "x-show" not in overlay, \
            "overlay <img class=\"lb-full\"> 不得用 x-show（display:none 的 img 不載入、@load 永不 fire）"

    def test_lb_full_css_opacity_transition_with_token(self):
        """71-T6: showcase.css .lb-full 用 opacity:0 + fluent token transition（非裸 .3s）；.lb-full-shown opacity:1"""
        css = self._css()
        m = re.search(r'\.lb-full\s*\{([^}]*)\}', css)
        assert m, "showcase.css 缺 .lb-full 規則"
        body = m.group(1)
        assert "position: absolute" in body and "opacity: 0" in body, \
            ".lb-full 須 position:absolute + opacity:0（疊在 base 上、預設隱藏）"
        assert "pointer-events: none" in body, \
            ".lb-full 須 pointer-events:none（overlay 不擋 cover-actions/sparkle 點擊）"
        assert re.search(r'transition:\s*opacity\s+var\(--fluent-duration-', body), \
            ".lb-full transition 須用 fluent duration token（不寫裸 .3s magic number）"
        assert re.search(r'var\(--fluent-ease-(decel|standard)\)', body), \
            ".lb-full transition 須用 fluent ease token（decel/standard）"
        shown = re.search(r'\.lb-full-shown\s*\{([^}]*)\}', css)
        assert shown and "opacity: 1" in shown.group(1), \
            "showcase.css 缺 .lb-full-shown { opacity: 1 }（淡入終態）"

    def test_lb_full_reduced_motion_no_transition(self):
        """71-T6: prefers-reduced-motion 內 .lb-full { transition: none }（瞬切，鏡像既有 PRM 範式）"""
        css = self._css()
        prm_blocks = re.findall(r'@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}', css, re.S)
        assert any(re.search(r'\.lb-full\s*\{[^}]*transition:\s*none', b) for b in prm_blocks), \
            "showcase.css 缺 @media (prefers-reduced-motion: reduce) .lb-full { transition: none }（reduced-motion 瞬切）"

    def test_lightbox_js_declares_and_resets_lbfullloaded(self):
        """71-T6/71c-P2: state-lightbox.js 宣告 _lbFullLoaded stub（Alpine 3 ReferenceError 防護）+
        _refreshLbFullBlurUp helper 含 reset（71c-P2 抽 helper 後邏輯在 helper 而非 inline _setLightboxIndex）"""
        src = SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        assert "_lbFullLoaded: false" in src, \
            "state-lightbox.js 缺 _lbFullLoaded: false 宣告（Alpine 3 未宣告丟 ReferenceError，x||fallback 擋不住）"
        # 71c-P2：reset 邏輯抽至 _refreshLbFullBlurUp helper，確認 helper 含 this._lbFullLoaded = false
        helper_m = re.search(r'_refreshLbFullBlurUp\(\)\s*\{(.*?)\n\s{8}\}', src, re.S)
        assert helper_m, "state-lightbox.js 找不到 _refreshLbFullBlurUp() helper（71c-P2 blur-up 共用 helper）"
        assert "this._lbFullLoaded = false" in helper_m.group(1), \
            "_refreshLbFullBlurUp helper 缺 this._lbFullLoaded = false（開燈箱/prev-next/slip-through 每次重走 blur-up）"
        # _setLightboxIndex 仍須委託 helper（不可 inline 走樣）
        set_m = re.search(r'_setLightboxIndex\(idx\)\s*\{(.*?)\n\s{8}\}', src, re.S)
        assert set_m, "state-lightbox.js: 找不到 _setLightboxIndex(idx) 方法"
        assert "_refreshLbFullBlurUp" in set_m.group(1), \
            "_setLightboxIndex 未委託 _refreshLbFullBlurUp（71c-P2 抽 helper 後應呼叫 helper 不可 inline）"


# ── TASK-70-T5: JavLibrary Picker BETA 視覺 + 不可用 gate 靜態守衛 ──

_BOOTSTRAP_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "_advanced_search_bootstrap.html"
_STATE_RESCRAPE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "state-rescrape.js"
_APP_PY = Path(__file__).parent.parent.parent / "web" / "app.py"
_MODAL_HTML_70 = Path(__file__).parent.parent.parent / "web" / "templates" / "_rescrape_modal.html"
_LOCALES_ROOT_70 = Path(__file__).parent.parent.parent / "locales"


# ── TASK-70-T6: CF flow 前端靜態守衛 ──

class TestJavlibraryCfFlowT6Guard:
    """70-T6: CF flow 前端靜態守衛。"""

    # (1) state-rescrape.js factory 宣告 rescrapeCfWaiting
    def test_state_rescrape_declares_rescrapeCfWaiting(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "rescrapeCfWaiting" in js, \
            "70-T6 違規：state-rescrape.js factory 未宣告 rescrapeCfWaiting"

    # (2) state-rescrape.js factory 宣告 _cfPollHandle
    def test_state_rescrape_declares_cfPollHandle(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "_cfPollHandle" in js, \
            "70-T6 違規：state-rescrape.js factory 未宣告 _cfPollHandle"

    # (3) state-rescrape.js 定義 _pollCfThenRetry
    def test_state_rescrape_has_pollCfThenRetry(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "_pollCfThenRetry" in js, \
            "70-T6 違規：state-rescrape.js 未定義 _pollCfThenRetry"

    # (4) state-rescrape.js 定義 cancelCfPoll
    def test_state_rescrape_has_cancelCfPoll(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "cancelCfPoll" in js, \
            "70-T6 違規：state-rescrape.js 未定義 cancelCfPoll"

    # (5) rescrapeWithSource 含 cf_needed 且在 rescrapeNotFound = true 之前
    def test_state_rescrape_cf_needed_before_notfound(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        # Anchor on the consuming expression `data.cf_needed` (not bare `cf_needed`
        # which could match a comment at an earlier position — B2-P3-1 hardening).
        assert "data.cf_needed" in js, \
            "70-T6 違規：state-rescrape.js 未含 data.cf_needed 消費表達式"
        cf_pos = js.index("data.cf_needed")
        # rescrapeNotFound = true 在 showcase 分支的 else 中（最後一次出現）
        notfound_pos = js.rindex("rescrapeNotFound = true")
        assert cf_pos < notfound_pos, \
            "70-T6 違規：cf_needed check 必須在 rescrapeNotFound = true 之前"

    # (5b) P2-2（Codex PR#89）：rescrapeConfirm lightbox 寫檔分支接 cf_needed / cf_unavailable
    def test_rescrape_confirm_handles_cf(self):
        """P2-2：rescrapeConfirm 的 lightbox 寫檔分支必須接 result.cf_needed / result.cf_unavailable。

        T2 後 javlibrary && detail_url 走後端 detail 重抓分支，若預覽→確認間 CF session 過期，
        後端回 {cf_needed} / {cf_unavailable}（已 begin_solve）。confirm 不接 → 卡在模糊「失敗」
        且不啟動 CF 流程。element-bound：鎖定 rescrapeConfirm body（至 _pollCfThenRetry 定義前）。
        mutation：拿掉 CF 接法 → RED。
        """
        import re as _re
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        m = _re.search(r"rescrapeConfirm\s*\(\s*\)\s*\{", js)
        assert m is not None, "P2-2 違規：找不到 rescrapeConfirm() 定義"
        # _pollCfThenRetry(number) 是其後的方法定義（call site 用 this.rescrapeNumber.trim() 不匹配）
        end = js.index("_pollCfThenRetry(number)", m.start())
        body = js[m.start():end]
        assert "result.cf_unavailable" in body, (
            "P2-2 違規：rescrapeConfirm lightbox 分支未接 result.cf_unavailable（CF session 過期靜默卡死）"
        )
        assert "result.cf_needed" in body, (
            "P2-2 違規：rescrapeConfirm lightbox 分支未接 result.cf_needed（CF flow 不啟動）"
        )

    # (6) closeRescrape 含 clearInterval（清 CF poll）
    def test_close_rescrape_clears_interval(self):
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        # 找 closeRescrape 方法定義（定義行含 `closeRescrape() {`）
        # 用 rindex 找最後一個出現的 closeRescrape()，往後 500 chars 覆蓋方法體
        close_pos = js.rindex("closeRescrape()")
        segment = js[close_pos:close_pos + 500]
        assert "clearInterval" in segment, \
            "70-T6 違規：closeRescrape 未呼叫 clearInterval 清 CF poll handle"

    # (7) _rescrape_modal.html 含 rescrapeCfWaiting div + jl_cf_solving + cancelCfPoll
    def test_modal_has_cf_waiting_block(self):
        html = _MODAL_HTML_70.read_text(encoding="utf-8")
        assert "rescrapeCfWaiting" in html, \
            "70-T6 違規：_rescrape_modal.html 缺 rescrapeCfWaiting waiting 區塊"
        assert "jl_cf_solving" in html, \
            "70-T6 違規：_rescrape_modal.html 缺 jl_cf_solving i18n key"
        assert "cancelCfPoll" in html, \
            "70-T6 違規：_rescrape_modal.html Cancel 鈕缺 cancelCfPoll() 綁定"

    # (8) 4 locale 有 jl_cf_solving + notif.jl_cf_timeout
    def test_i18n_t6_keys_parity(self):
        for lang in ("zh_TW", "zh_CN", "en", "ja"):
            content = (_LOCALES_ROOT_70 / f"{lang}.json").read_text(encoding="utf-8")
            assert "jl_cf_solving" in content, \
                f"70-T6 違規：locales/{lang}.json 缺 jl_cf_solving"
            assert "jl_cf_timeout" in content, \
                f"70-T6 違規：locales/{lang}.json 缺 notif.jl_cf_timeout"

    # (9) P2 fix: cf_needed / cf_unavailable 必須在 switch-source 分支之前（字串位置守衛）
    # 防回歸：確保 cf_needed 處理不再被 switch-source 分支攔截而落入 rescrapeNotFound=true
    def test_cf_needed_before_switch_source_branch(self):
        """70-T6 P2：cf_needed / cf_unavailable 處理必須在 switch-source 分支之前。

        Codex P2 指出：switch-source 收到 {cf_needed:true} 時，因 data.success falsy
        落入 rescrapeNotFound=true，CF flow 不觸發。修法：上移 cf_needed/cf_unavailable
        至所有入口分支（switch-source / showcase）之前統一處理。
        此守衛確保上移後不回歸（字串位置比對）。

        B2-P3-1 hardening: anchor on `data.cf_needed` (the consuming expression),
        not bare `cf_needed` which could match a comment appearing earlier in the file.

        74a-T4 hardening: anchor sw_pos on the PREVIEW switch-source branch opener
        `rescrapeEntryPoint === 'switch-source') {` (bare, closing-paren + brace),
        NOT the bare-first-occurrence `.index()`. 74a-T4 introduces a switch-source + auto
        short-circuit branch (`rescrapeEntryPoint === 'switch-source' && sourceId === 'auto'`)
        that runs BEFORE the fetch — it cannot intercept CF data, so it is irrelevant to the
        property this guard protects (CF handling must precede the data-consuming PREVIEW branch).
        Anchoring on the bare-opener keeps the guard meaningful (the auto branch opener has
        `&& sourceId === 'auto'` before `)`, so it never matches this anchor).
        """
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "data.cf_needed" in js, \
            "70-T6 P2 違規：state-rescrape.js 未含 data.cf_needed 消費表達式"
        assert "rescrapeEntryPoint === 'switch-source') {" in js, \
            "70-T6 P2 違規：state-rescrape.js 未含 preview switch-source 分支"
        cf_pos = js.index("data.cf_needed")
        sw_pos = js.index("rescrapeEntryPoint === 'switch-source') {")
        assert cf_pos < sw_pos, (
            f"70-T6 P2 違規：data.cf_needed 處理（pos={cf_pos}）必須在 preview switch-source 分支"
            f"（pos={sw_pos}）之前，否則 switch-source 入口永遠看不到 CF flow"
        )

    def test_cf_unavailable_before_switch_source_branch(self):
        """70-T6 P2：cf_unavailable 處理必須在 switch-source 分支之前（與 cf_needed 同理）。

        74a-T4 hardening: 同 test_cf_needed_before_switch_source_branch，sw_pos 錨在 preview
        switch-source 分支 opener（bare `) {`），不受 74a-T4 fetch 前的 auto short-circuit 分支影響。
        """
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "cf_unavailable" in js, \
            "70-T6 P2 違規：state-rescrape.js 未含 cf_unavailable 處理"
        assert "rescrapeEntryPoint === 'switch-source') {" in js, \
            "70-T6 P2 違規：state-rescrape.js 未含 preview switch-source 分支"
        cf_unav_pos = js.index("cf_unavailable")
        sw_pos = js.index("rescrapeEntryPoint === 'switch-source') {")
        assert cf_unav_pos < sw_pos, (
            f"70-T6 P2 違規：cf_unavailable 處理（pos={cf_unav_pos}）必須在 preview switch-source 分支"
            f"（pos={sw_pos}）之前"
        )


# ── CD-86-7 frontend guard: search 入口 JL pill gate 改用 isJlUnavailable ──

class TestRescrapeModalSearchHideJlPillGuard:
    """
    CD-86-7：_rescrape_modal.html builtin pill 在 search 入口不再隱藏，改由 isJlUnavailable gate。

    86-T4 rewrite: 舊 search-hide x-show 表達式（FIX-2）已移除（CD-86-7），
    改交 isJlUnavailable 統一管可點性（非桌面仍 aria-disabled，AC8 不回歸）。
    """

    def _html(self):
        return _MODAL_HTML_70.read_text(encoding="utf-8")

    def test_modal_builtin_pill_search_gate_uses_isJlUnavailable(self):
        """CD-86-7: search 入口 javlib pill 不再由 manual_only+is_beta+search 隱藏，
        改由 isJlUnavailable 統一 gate（非桌面仍 aria-disabled）。
        舊 search-hide 表達式必須已移除。
        """
        html = self._html()
        OLD_HIDE = "s.manual_only && s.is_beta && rescrapeEntryPoint === 'search'"
        assert OLD_HIDE not in html, (
            "CD-86-7 違規：_rescrape_modal.html builtin pill 仍含舊 search 入口隱藏條件—"
            "應已移除，改交 isJlUnavailable gate"
        )
        assert "isJlUnavailable" in html, (
            "CD-86-7 違規：_rescrape_modal.html 移除 search-hide 後必須保留 isJlUnavailable gate"
        )

    def test_modal_builtin_pill_jl_gate_preserves_aria_disabled(self):
        """CD-86-7 + AC8: search 入口 javlib pill x-show 放開後，
        isJlUnavailable gate 必須仍帶 aria-disabled 綁定（非桌面不可點語義不回歸）。
        """
        import re
        html = self._html()
        assert "isJlUnavailable" in html, (
            "AC8 違規：_rescrape_modal.html 缺 isJlUnavailable gate"
        )
        assert "aria-disabled" in html, (
            "AC8 違規：_rescrape_modal.html builtin pill 缺 aria-disabled 綁定"
        )
        # element-bound: 確認 isJlUnavailable 和 aria-disabled 在同一 template 上下文（pill 區）
        m = re.search(
            r"isJlUnavailable.*?aria-disabled|aria-disabled.*?isJlUnavailable",
            html, re.DOTALL,
        )
        assert m, (
            "AC8 違規：isJlUnavailable 與 aria-disabled 未出現在 pill 相近上下文"
        )


# ── 86-T4 frontend guard: 版本切換器 + i18n + entry-point gate ──

class TestRescrapeVersionSwitcherGuard:
    """86-T4: _rescrape_modal.html 版本切換器 + i18n + gate 靜態守衛。"""

    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates"
    LOCALES_DIR = Path(__file__).parent.parent.parent / "locales"
    MODAL_HTML = TEMPLATES_DIR / "_rescrape_modal.html"
    ZH_TW_JSON = LOCALES_DIR / "zh_TW.json"

    def _html(self):
        return self.MODAL_HTML.read_text(encoding="utf-8")

    def _locale(self):
        import json
        return json.loads(self.ZH_TW_JSON.read_text(encoding="utf-8"))

    # ── 切換器 x-show binding ──

    def test_version_switcher_uses_rescrapeHasVersions(self):
        """切換器 ‹ › 鈕必須綁 x-show="rescrapeHasVersions()"（element-bound，防 comment 假陽性）。"""
        html = self._html()
        # element-bound: 要求完整屬性綁定出現在非注釋上下文
        BINDING = 'x-show="rescrapeHasVersions()"'
        assert html.count(BINDING) >= 2, (
            f"86-T4 違規：_rescrape_modal.html 缺足夠的 {BINDING!r} 綁定（切換器 ‹ › 各一）"
        )

    def test_version_switcher_uses_rescrapeVersionGo(self):
        """切換器 ‹ › 鈕必須綁 @click rescrapeVersionGo。"""
        html = self._html()
        assert "rescrapeVersionGo(-1)" in html, (
            "86-T4 違規：_rescrape_modal.html 缺 rescrapeVersionGo(-1)（‹ 鈕）"
        )
        assert "rescrapeVersionGo(1)" in html, (
            "86-T4 違規：_rescrape_modal.html 缺 rescrapeVersionGo(1)（› 鈕）"
        )

    # ── versions_found 走 t() 非硬編碼 ──

    def test_versions_found_uses_t_function(self):
        """「找到 X 部」文字必須走 t('showcase.rescrape.versions_found')，禁硬編碼繁中。"""
        html = self._html()
        assert "showcase.rescrape.versions_found" in html, (
            "86-T4 違規：_rescrape_modal.html 缺 showcase.rescrape.versions_found t() 呼叫"
        )
        # 禁止硬編碼
        assert "找到" not in html, (
            "86-T4 違規：_rescrape_modal.html 含硬編碼「找到」文字（應走 i18n）"
        )

    # ── 不可逆警告 entry-point gate ──

    def test_overwrite_warning_gated_by_lightbox_entrypoint(self):
        """不可逆警告 rescrape-caption 必須以 rescrapeEntryPoint === 'lightbox' gate。"""
        import re
        html = self._html()
        # element-bound: 在同一個 tag 內找 rescrape-caption 和 lightbox gate
        m = re.search(
            r'rescrape-caption[^>]*rescrapeEntryPoint[^>]*lightbox'
            r'|rescrapeEntryPoint[^>]*lightbox[^>]*rescrape-caption',
            html,
        )
        assert m, (
            "CD-86-9 違規：rescrape-caption（不可逆警告）缺 rescrapeEntryPoint === 'lightbox' gate"
        )

    # 註：search 入口 javlib gate 改 isJlUnavailable 的回歸守衛（CD-86-7 + AC8）
    # 由 TestRescrapeModalSearchHideJlPillGuard 兩條改寫守衛涵蓋，此處不重複。

    # ── i18n key 存在性守衛 ──

    def test_i18n_versions_found_key_exists(self):
        """showcase.rescrape.versions_found key 必須存在於 zh_TW.json，且含 {count} 插值。"""
        data = self._locale()
        key_val = data.get("showcase", {}).get("rescrape", {}).get("versions_found", None)
        assert key_val is not None, (
            "86-T4 違規：locales/zh_TW.json 缺 showcase.rescrape.versions_found key"
        )
        assert "{count}" in key_val, (
            "CD-86-11 違規：showcase.rescrape.versions_found 缺 {count} 插值"
        )

    def test_i18n_version_nav_aria_keys_exist(self):
        """切換器 prev/next aria key 必須存在於 zh_TW.json。"""
        data = self._locale()
        rescrape = data.get("showcase", {}).get("rescrape", {})
        for key in ("version_prev_aria", "version_next_aria"):
            assert key in rescrape, (
                f"86-T4 違規：locales/zh_TW.json 缺 showcase.rescrape.{key} key"
            )

    def test_i18n_adopt_version_key_exists(self):
        """search 入口「採用此版本」key 必須存在於 zh_TW.json。"""
        data = self._locale()
        rescrape = data.get("showcase", {}).get("rescrape", {})
        assert "adopt_version" in rescrape, (
            "86-T4 違規：locales/zh_TW.json 缺 showcase.rescrape.adopt_version key"
        )

    # ── 86-T6: search adopt 鈕 icon 化 + 琥珀色守衛 ──

    def test_search_adopt_btn_uses_check_icon(self):
        """86-T6: search 入口 adopt 鈕必須用 bi-check-lg icon，禁 x-text 文字（破版防回流）。
        element-bound：守衛綁 rescrapeEntryPoint === 'search' 的 confirm-row block。
        aria-label 必須走 adopt_version key（螢幕報讀不退化）。
        """
        import re
        html = self._html()

        # 截出 search confirm-row block（class=rescrape-confirm-row + search gate 的 div 到 </div>）
        m = re.search(
            r'<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*[\'"]search[\'"][^>]*>(.*?)</div>',
            html,
            re.DOTALL,
        )
        assert m, (
            "86-T6 違規：_rescrape_modal.html 缺 rescrapeEntryPoint === 'search' confirm-row block"
        )
        block = m.group(0)

        # adopt 鈕含 bi-check-lg icon
        assert "bi-check-lg" in block, (
            "86-T6 違規：search adopt 鈕缺 bi-check-lg icon（應鏡射 lightbox ✓ 鈕寫法）"
        )
        # 禁 x-text（防文字溢出破版回流）
        assert "x-text" not in block, (
            "86-T6 違規：search adopt 鈕不得含 x-text（文字溢出 48px 圓鈕破版）"
        )
        # aria-label 走 adopt_version key
        assert "adopt_version" in block, (
            "86-T6 違規：search adopt 鈕缺 adopt_version aria-label（螢幕報讀退化）"
        )

    def test_version_status_uses_warning_color(self):
        """86-T6: .rescrape-version-status 與 .rescrape-ver-indicator 的 color 必須為 var(--color-warning)。
        CSS 守衛（正向 require 值：stylelint 不易 require 特定 token 值，pytest 正向斷言合適）。
        element-bound：綁定該 selector block，避免誤命中其他 selector。
        """
        import re
        css_path = (
            Path(__file__).parent.parent.parent
            / "web" / "static" / "css" / "components" / "rescrape-modal.css"
        )
        css = css_path.read_text(encoding="utf-8")

        def extract_block(selector: str, text: str) -> str:
            """擷取 selector 對應的 { ... } block 內容。"""
            pattern = re.escape(selector) + r"\s*\{([^}]*)\}"
            m = re.search(pattern, text)
            assert m, f"86-T6 違規：rescrape-modal.css 缺 {selector!r} selector block"
            return m.group(1)

        status_block = extract_block(".rescrape-version-status", css)
        assert "var(--color-warning)" in status_block, (
            "86-T6 違規：.rescrape-version-status 的 color 未使用 var(--color-warning)（撞號提示應為琥珀色）"
        )

        indicator_block = extract_block(".rescrape-ver-indicator", css)
        assert "var(--color-warning)" in indicator_block, (
            "86-T6 違規：.rescrape-ver-indicator 的 color 未使用 var(--color-warning)（N/M 指示應為琥珀色）"
        )

    # ── T7: switch-source confirm-row ──

    def test_switch_source_modal_confirm_row(self):
        """T7: _rescrape_modal.html 必須有 rescrapeEntryPoint === 'switch-source' confirm-row，
        含 bi-check-lg icon，且不含 overwrite_warning（只替換結果列 slot，不寫檔）。
        element-bound: 在 switch-source confirm-row block 內驗 icon + 排除 overwrite_warning。
        """
        import re as _re
        html = self._html()
        m = _re.search(
            r'<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*[\'"]switch-source[\'"][^>]*>(.*?)</div>',
            html,
            _re.DOTALL,
        )
        assert m, (
            "T7 違規：_rescrape_modal.html 缺 rescrapeEntryPoint === 'switch-source' confirm-row"
        )
        block = m.group(0)
        assert "bi-check-lg" in block, (
            "T7 違規：switch-source confirm-row 缺 bi-check-lg icon"
        )
        assert "overwrite_warning" not in block, (
            "T7 違規：switch-source confirm-row 不得含 overwrite_warning（非寫檔操作）"
        )

    def test_i18n_adopt_switch_source_key_exists(self):
        """T7: showcase.rescrape.adopt_switch_source key 必須存在於 zh_TW.json。"""
        data = self._locale()
        rescrape = data.get("showcase", {}).get("rescrape", {})
        assert "adopt_switch_source" in rescrape, (
            "T7 違規：locales/zh_TW.json 缺 showcase.rescrape.adopt_switch_source key"
        )


# ──────────────────────────────────────────────────────────────
# CD-70c-3: frontend CF poll unavailable contract guard
# ──────────────────────────────────────────────────────────────

STATE_RESCRAPE_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "shared" / "state-rescrape.js"
)


SHOWCASE_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
SHOWCASE_SIMILAR_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"


SOURCE_PILL_MACRO = (
    Path(__file__).parent.parent.parent
    / "web" / "templates" / "_macros" / "source_pill.html"
)


class TestSearchAutoSourcePill:
    """TASK-74a-T2: 搜尋列自動膠囊 macro 呼叫 DOM contract（call-site-bound）。

    守衛抽出 search.html 內含 extra_classes='search-auto-pill' 的 source_pill(...)
    macro 呼叫文字，斷言同一呼叫上：x-show 含 isComposing()；@click 含
    openRescrape(null, 'search') 與 rescrapeNumber = 預填（CD-74a-14 + Codex P1-2）。

    過「三問」：把 isComposing()/@click 搬到別的 macro 呼叫 → 紅（regex 只取
    search-auto-pill 那一個 call）；註解化 → 紅；刪 rescrapeNumber 預填子表達式 → 紅。
    """

    def _auto_pill_call(self) -> str:
        """抽出帶 extra_classes='search-auto-pill' 的 source_pill(...) macro 呼叫文字。"""
        html = SEARCH_HTML.read_text(encoding="utf-8")
        m = re.search(
            r"source_pill\((?:[^()]|\([^()]*\))*search-auto-pill(?:[^()]|\([^()]*\))*\)",
            html,
            re.DOTALL,
        )
        assert m, "search.html 找不到 extra_classes='search-auto-pill' 的 source_pill(...) 呼叫"
        return m.group(0)

    def test_auto_pill_xshow_is_composing(self):
        """自動膠囊 macro 呼叫的 x-show 含 isComposing()（compose 態才顯示）。"""
        call = self._auto_pill_call()
        xshow_m = re.search(r'x-show=\\?["\']([^"\']*)', call)
        assert xshow_m, f"search-auto-pill 呼叫缺 x-show binding；call: {call!r}"
        assert "isComposing()" in xshow_m.group(1), (
            f"search-auto-pill x-show 缺 isComposing()；x-show: {xshow_m.group(1)!r}"
        )

    def test_auto_pill_click_opens_rescrape_with_prefill(self):
        """自動膠囊 @click 含 openRescrape(null, 'search') 且預填 rescrapeNumber =。

        刪任一子表達式 → 此斷言紅（漏 rescrapeNumber 預填會在挑源時觸發 rescrapeNotFound，
        state-rescrape.js:163）。
        """
        call = self._auto_pill_call()
        # raw template 內單引號被 Jinja 字串轉義（\'search\'），故 regex 容忍可選反斜線
        assert re.search(r"openRescrape\(null,\s*\\?'search\\?'\)", call), (
            f"search-auto-pill 呼叫缺 openRescrape(null, 'search')；call: {call!r}"
        )
        assert "rescrapeNumber =" in call, (
            f"search-auto-pill @click 缺 rescrapeNumber = 預填；call: {call!r}"
        )

    def test_auto_pill_xshow_contains_can_reopen_source_pick(self):
        """自動膠囊 x-show 含 canReopenSourcePick()（CD-86-P2 修正：exact 結果頁再開入口）。

        JavLibrary 採用後 searchQuery == currentQuery → isComposing() false，
        需要 canReopenSourcePick() 讓 pill 在 exact 結果時常駐。
        mutation：把 x-show 改回只 isComposing() → 此斷言紅。
        """
        call = self._auto_pill_call()
        xshow_m = re.search(r'x-show=\\?["\']([^"\']*)', call)
        assert xshow_m, f"search-auto-pill 呼叫缺 x-show binding；call: {call!r}"
        assert "canReopenSourcePick()" in xshow_m.group(1), (
            f"search-auto-pill x-show 缺 canReopenSourcePick()；x-show: {xshow_m.group(1)!r}"
        )

    def test_can_reopen_source_pick_defined_in_search_flow_js(self):
        """search-flow.js 定義 canReopenSourcePick()，且包含 listMode + exact + pageState + searchQuery 四條件。

        listMode==='search' gate（CD-86-P2 副作用修正）：file/batch mode 也進 result+exact，但 searchQuery
        切檔不同步，頂部再入口會帶舊番號 → 限定 search workflow。
        mutation：移除 method 或刪任一條件（含 listMode）→ 此斷言紅。
        """
        js_path = (
            SEARCH_HTML.parent.parent
            / "static" / "js" / "pages" / "search" / "state" / "search-flow.js"
        )
        js = js_path.read_text(encoding="utf-8")
        m = re.search(r"canReopenSourcePick\s*\(\s*\)\s*\{(.*?)\n    \},", js, re.DOTALL)
        assert m, "search-flow.js 找不到 canReopenSourcePick() method 定義"
        body = m.group(1)
        assert "listMode" in body and "'search'" in body, (
            f"canReopenSourcePick body 缺 listMode === 'search' 條件；body: {body!r}"
        )
        assert "pageState" in body and "'result'" in body, (
            f"canReopenSourcePick body 缺 pageState === 'result' 條件；body: {body!r}"
        )
        assert "'exact'" in body, (
            f"canReopenSourcePick body 缺 currentMode === 'exact' 條件；body: {body!r}"
        )
        assert "searchQuery" in body, (
            f"canReopenSourcePick body 缺 searchQuery 非空條件；body: {body!r}"
        )


class TestResultSourcePill:
    """TASK-74a-T3: 結果面板「目前來源膠囊」macro 呼叫 DOM contract（call-site-bound）。

    守衛抽出 search.html 內含 extra_classes='result-source-pill' 的 source_pill(...)
    macro 呼叫文字，斷言同一呼叫上接 openSwitchSourcePicker()（@click）、
    _resolveSourceName（name 表達式）、isSwitchingSource（:disabled / :class is-loading）。

    過「三問」：把 binding 搬到別的 macro 呼叫 → 紅（regex 只取 result-source-pill 那一個 call）；
    註解化 → 紅；刪關鍵子表達式 → 紅。
    """

    def _result_pill_call(self) -> str:
        """抽出帶 extra_classes='result-source-pill' 的 source_pill(...) macro 呼叫文字。

        macro 呼叫 attrs 內含多層巢狀括號（rescrapeSources.find(... (current()...) ...)），
        故不走 balanced-paren regex；改抽「source_pill( 起點 → 含 result-source-pill →
        到下一個 ) }} macro 收尾」的呼叫文字（call-site-bound）。
        """
        html = SEARCH_HTML.read_text(encoding="utf-8")
        m = re.search(
            r"source_pill\((?:(?!source_pill\().)*?result-source-pill.*?\)\s*\}\}",
            html,
            re.DOTALL,
        )
        assert m, "search.html 找不到 extra_classes='result-source-pill' 的 source_pill(...) 呼叫"
        return m.group(0)

    def test_result_pill_click_opens_switch_picker(self):
        """目前來源膠囊 @click 含 openSwitchSourcePicker()（沿用既有換源入口）。"""
        call = self._result_pill_call()
        assert "openSwitchSourcePicker()" in call, (
            f"result-source-pill 呼叫缺 openSwitchSourcePicker()（@click）；call: {call!r}"
        )

    def test_result_pill_name_resolves_source(self):
        """目前來源膠囊 name 表達式走 _resolveSourceName（backend-authoritative 顯示名）。"""
        call = self._result_pill_call()
        assert "_resolveSourceName" in call, (
            f"result-source-pill 呼叫缺 _resolveSourceName（name 顯示名）；call: {call!r}"
        )

    def test_result_pill_loading_bound_to_switching(self):
        """目前來源膠囊 loading 綁 isSwitchingSource（:disabled + :class is-loading 驅動 spinner）。"""
        call = self._result_pill_call()
        assert "isSwitchingSource" in call, (
            f"result-source-pill 呼叫缺 isSwitchingSource 綁定（:disabled / is-loading）；call: {call!r}"
        )


class TestIsComposingGetter:
    """TASK-74a-T2: search-flow.js isComposing() computed getter（source-bound，CD-74a-2）。

    抽出 isComposing method body，斷言同一 body 內含三個條件子表達式：
    pageState !== 'loading'、searchQuery、currentQuery。
    過「三問」：刪任一條件 → 紅；把它搬到別的 method → 抽不到 isComposing body → 紅。
    """

    def _is_composing_body(self) -> str:
        js = SEARCH_FLOW_JS.read_text(encoding="utf-8")
        # 抽 isComposing() { ... } 到下一個 method（以 method-or-end 為界）
        m = re.search(r"isComposing\s*\(\s*\)\s*\{(.*?)\n    \}", js, re.DOTALL)
        assert m, "search-flow.js 找不到 isComposing() method 定義"
        return m.group(1)

    def test_is_composing_three_conditions(self):
        """isComposing() body 含 pageState !== 'loading' + searchQuery + currentQuery 三條件。"""
        body = self._is_composing_body()
        assert "pageState !== 'loading'" in body, (
            f"isComposing() 缺 pageState !== 'loading' 條件；body: {body!r}"
        )
        assert "searchQuery" in body, (
            f"isComposing() 缺 searchQuery 條件；body: {body!r}"
        )
        assert "currentQuery" in body, (
            f"isComposing() 缺 currentQuery 條件；body: {body!r}"
        )


STATE_RESCRAPE_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "shared" / "state-rescrape.js"
)


# ── 75a-T4 path constants ──────────────────────────────────────────────────
CONSTELLATION_ANIMATIONS_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "shared" / "constellation" / "animations.js"
)
T4_STATE_SIMILAR_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
)
T4_CONSTELLATION_HOST_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "motion-lab" / "constellation-host.js"
)


class TestSimilarSlotGsapGuard:
    """75a-T4: GSAP width literal 守衛 — constellation/animations.js + state-similar.js。

    animations.js: T1 後所有 width 已改為 SLOT_W/MAIN_W 具名常量（無 120/200 literal）；
    用全文 ban 安全（確認無其他合法 120/200 出現）。
    assert 'width: 120' not in js + assert 'width: 200' not in js；
    正向斷言 POSTER_CROP_RATIO 常數存在。

    state-similar.js: 全文只有一處 width: 107（gsap.set slot reset），無 120 出現；
    用全文 ban 安全。
    """

    def _animations(self):
        return CONSTELLATION_ANIMATIONS_JS.read_text(encoding="utf-8")

    def _similar(self):
        return T4_STATE_SIMILAR_JS.read_text(encoding="utf-8")

    def test_animations_no_width_120_literal(self):
        """animations.js 全文不含 width: 120（T1 後已改 SLOT_W 常量）"""
        js = self._animations()
        assert "width: 120" not in js, \
            "animations.js must not contain literal 'width: 120' (use SLOT_W constant)"

    def test_animations_no_width_200_literal(self):
        """animations.js 全文不含 width: 200（T1 後已改 MAIN_W 常量）"""
        js = self._animations()
        assert "width: 200" not in js, \
            "animations.js must not contain literal 'width: 200' (use MAIN_W constant)"

    def test_animations_has_poster_crop_ratio_const(self):
        """animations.js 含 POSTER_CROP_RATIO 具名常量（單一真理 NC#7）"""
        js = self._animations()
        assert "POSTER_CROP_RATIO" in js, \
            "animations.js must define POSTER_CROP_RATIO constant (single source of truth NC#7)"

    def test_animations_has_slot_w_const(self):
        """animations.js 含 SLOT_W 具名常量"""
        js = self._animations()
        assert "SLOT_W" in js, \
            "animations.js must define SLOT_W constant derived from POSTER_CROP_RATIO"

    def test_animations_has_main_w_const(self):
        """animations.js 含 MAIN_W 具名常量"""
        js = self._animations()
        assert "MAIN_W" in js, \
            "animations.js must define MAIN_W constant derived from POSTER_CROP_RATIO"

    def test_state_similar_no_width_120(self):
        """state-similar.js 全文不含 width: 120（slot reset 應為 107）"""
        js = self._similar()
        assert "width: 120" not in js, \
            "state-similar.js must not contain 'width: 120' (slot width should be 107)"

    def test_state_similar_has_width_107(self):
        """state-similar.js 含 width: 107（slot reset 正確值）"""
        js = self._similar()
        assert "width: 107" in js, \
            "state-similar.js must contain 'width: 107' (slot reset value)"

    def _host(self):
        return T4_CONSTELLATION_HOST_JS.read_text(encoding="utf-8")

    def test_constellation_host_no_width_120(self):
        """constellation-host.js 全文不含 width: 120（reduced-motion click + reset baseline path
        繞過 animations.js gsap.set，應為 107；Codex P3 補洞——plan 6 處 inventory 漏此 host 檔）"""
        js = self._host()
        assert "width: 120" not in js, \
            "constellation-host.js must not contain 'width: 120' (slot box should be 107, NC#7 mirror)"

    def test_constellation_host_has_width_107(self):
        """constellation-host.js 含 width: 107（reduced-motion / reset slot 正確值）"""
        js = self._host()
        assert "width: 107" in js, \
            "constellation-host.js must contain 'width: 107' (reduced-motion + reset slot value)"


class TestSimilarJSThresholdGuard:
    """75a-T4: state-similar.js openSimilarMode 手機門檻 960px 守衛。

    提取 openSimilarMode 函式體後斷言 < 960（不是 < 768）。
    三問：改回 768 → 紅；刪 960 → 紅；加 768 → 紅。
    """

    def _js(self):
        return T4_STATE_SIMILAR_JS.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """提取 Alpine/module method 函式體（大括號平衡法）"""
        pattern = re.compile(
            r'(?:^|\n)\s*async ' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        if m is None:
            # try non-async form
            pattern2 = re.compile(
                r'(?:^|\n)\s*' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
                re.DOTALL,
            )
            m = pattern2.search(js)
        assert m is not None, f"state-similar.js: cannot find method {method_name}"
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

    def test_open_similar_mode_threshold_960(self):
        """openSimilarMode 函式體含 innerWidth < 960"""
        js = self._js()
        body = self._extract_method_body(js, 'openSimilarMode')
        assert "innerWidth < 960" in body, \
            "state-similar.js openSimilarMode must use 'innerWidth < 960' threshold (not 768)"

    def test_open_similar_mode_no_threshold_768(self):
        """openSimilarMode 函式體不含 innerWidth < 768（舊錯誤門檻）"""
        js = self._js()
        body = self._extract_method_body(js, 'openSimilarMode')
        assert "innerWidth < 768" not in body, \
            "state-similar.js openSimilarMode must not use 'innerWidth < 768' (should be 960)"


# ============================================================================
# TASK-75b-T6：US1 搜尋詳情重排 + US5 影片卡 poster 格 守衛
# search.html DOM 結構 / search.css + showcase.css element-bound CSS read
# ============================================================================

SEARCH_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "search.css"


# ============================================================================
# TASK-75b-T7（CD-75b-12）：≤480px poster 格 → lightbox ghost-fly 溶接守衛
# 跨檔契約：state-lightbox.js 計算並傳 posterCrop → ghost-fly.js 消費（對齊右裁 + 落地 crossfade）
# ============================================================================

GHOST_FLY_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "shared" / "ghost-fly.js"
STATE_LIGHTBOX_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"


# ============================================================================
# TASK-75b-T8：≤480px 影片燈箱封面貼合原圖比例（消 letterbox 死白 + 根治 T7 seam）
# CSS element-bound 讀取守衛（require-presence of a rule，比照 US5 其他 guard）
# ============================================================================


# ============================================================================
# TASK-75b-T9：search 頁 ≤480px 影片格 + 燈箱修正守衛
# Port of showcase T4/T5/T7/T8 — all search-specific rules live in search.css (決策 ②)
# ============================================================================

class TestUS9SearchGridMobileFix:
    """TASK-75b-T9：search grid ≤480px 三欄 poster + 燈箱 letterbox 消除守衛。

    [lint-guard: pytest-justified] 6 個純-CSS 子測（T4 3-col / T5 poster-crop scope+caption+coarse footer /
    T8 cover-fit + showcase 回歸護欄）已遷 css-guard CG-PC-04（scripts/css-guard.mjs，search.css 靜態掃描）。
    此殘餘子測為跨檔 JS↔CSS posterCrop 穿線（grid-mode.js 計算並傳入 playGridToLightbox），非純 CSS
    靜態掃描、屬源碼語意契約，故保留 pytest（同 TestUS5PosterCropGhostCrossfade KEEP 型）。
    """

    def test_search_grid_mode_threads_poster_crop(self):
        """T7：grid-mode.js openLightbox 計算 posterCrop 並傳入 playGridToLightbox。
        三問：刪 posterCrop 計算 → 紅；刪傳遞 → 紅；拔 hero-card 判斷 → 紅。
        """
        js = GRID_MODE_JS.read_text(encoding="utf-8")
        assert "posterCrop" in js, "grid-mode.js 應計算 posterCrop"
        # T11（US-10）：門檻由 ≤480 擴到 ≤899（共用常數 POSTER_CROP_MAX_W，對齊守衛 TestPosterCropThresholdAlignment）。
        assert "window.innerWidth <= POSTER_CROP_MAX_W" in js, "posterCrop 應 gate ≤POSTER_CROP_MAX_W"
        assert "hero-card" in js, "posterCrop 應排除 hero 卡（防禦性 guard）"
        assert "posterCrop: posterCrop" in js, (
            "grid-mode.js 應把 posterCrop 傳入 playGridToLightbox options"
        )


# ============================================================================
# TASK-75b-T11：≤480px hero 卡（女優精準匹配入口）直式比例修正守衛
# showcase + search 兩頁 video-mode grid ≤480px hero 卡改 0.71 直式 + img cover
# ============================================================================

class TestCoverCacheBustGuard:
    """BUGfix-lightbox-cover-stale: refreshVideoData 必須對 cover_url 與 cover_full_url 都追加 cache-bust。
    守衛契約：擋「只 bust 一邊」回歸——任何人把任一欄位的 &t= 移除，對應守衛即紅。
    三問：
      1. 移除 cover_url &t= → test_cover_url_has_cache_bust 紅；cover_full_url bust 仍在 → 其守衛獨立 GREEN ✓
      2. 移除 cover_full_url &t= → test_cover_full_url_has_cache_bust 紅；cover_url bust 仍在 → 其守衛獨立 GREEN ✓
      3. 把 bust 搬出 refreshVideoData 函式體 → 兩條都紅 ✓
      4. 只在 comment 留 '&t=' 字串但移除實作 → 紅（守衛先過濾純注釋行，不被 comment 騙過）✓
    每條 regex 只匹配「同一條賦值語句內」：[^;\\n]* 不跨 ; 與換行，鎖在單一 statement，
    防止 re.DOTALL 跨行把兩個欄位的 &t= 混用。
    """

    _LIGHTBOX_JS = (
        Path(__file__).parent.parent.parent
        / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
    )

    def _js(self):
        return self._LIGHTBOX_JS.read_text(encoding="utf-8")

    def _extract_refreshVideoData_body(self, js):
        """定位 refreshVideoData 函式體（從函式宣告到第一個同層 closing brace）。
        用計數括弧深度的方式抓完整函式體，確保邊界正確。
        """
        # 找 refreshVideoData 宣告起點
        m = re.search(r'async\s+refreshVideoData\s*\(', js)
        assert m, "state-lightbox.js 找不到 async refreshVideoData 函式宣告"
        start = m.start()
        # 從宣告後面找第一個 '{' 並計數到同層 '}'
        body_start = js.index('{', start)
        depth = 0
        for i, ch in enumerate(js[body_start:], body_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return js[body_start:i + 1]
        raise AssertionError("state-lightbox.js: refreshVideoData 函式體找不到對應的結束括弧")

    @staticmethod
    def _strip_line_comments(body: str) -> str:
        """移除函式體內的 // 注釋——整行注釋與「行內尾注釋」都砍。
        去注釋後 regex 才不會被注釋裡的 `+ '&t='` 騙過：例如
        `data.video.cover_url = data.video.cover_url // + '&t='`（bust 移進行內注釋）
        若不砍行內注釋，[^;\\n]* 仍會配到注釋內的 + '&t=' 造成 false-pass。
        以 (?<!:)// 切除，保護 URL 的 `://`（https:// 等不被誤砍；/api 單斜線不觸發）。
        state-lightbox.js refreshVideoData 函式體內字串無 `//`、未用區塊注釋（/* */），
        此 heuristic 對本守衛充分。
        """
        return "\n".join(
            re.sub(r"(?<!:)//.*$", "", line)
            for line in body.splitlines()
        )

    def test_cover_url_has_cache_bust(self):
        """refreshVideoData 函式體內必須對 cover_url 賦值並串接 '&t=' cache-bust。
        要求：必須匹配「data.video.cover_url = ... + '&t='」賦值結構，
        且 regex 只匹配同一條賦值語句內（[^;\\n]* 不跨 ; 與換行），
        不被跨語句的 DOTALL 匹配混淆——保證 cover_url 守衛與 cover_full_url 守衛彼此獨立。
        先過濾純注釋行，確保配對只落在實際程式碼。
        """
        js = self._js()
        body = self._strip_line_comments(self._extract_refreshVideoData_body(js))
        m = re.search(
            r"data\.video\.cover_url\s*=\s*[^;\n]*\+\s*['\"]&t=",
            body
        )
        assert m, (
            "refreshVideoData 函式體找不到 'data.video.cover_url = ... + &t=' 賦值語句。\n"
            "cover_url 分支的 cache-bust 遺失，grid 封面更新後瀏覽器可能吃舊快取。\n"
            f"當前函式體（去注釋後）：\n{body[:500]}"
        )

    def test_cover_full_url_has_cache_bust(self):
        """refreshVideoData 函式體內必須對 cover_full_url 賦值並串接 '&t=' cache-bust。
        這是本 bug 的核心守衛：lightbox overlay（.lb-full）用 cover_full_url，
        URL 不變會吃瀏覽器 max-age=86400 舊快取。
        要求：必須匹配「data.video.cover_full_url = ... + '&t='」賦值結構，
        且 regex 只匹配同一條賦值語句內（[^;\\n]* 不跨 ; 與換行），
        不被跨語句的 DOTALL 匹配混淆——保證 cover_full_url 守衛與 cover_url 守衛彼此獨立。
        先過濾注釋行，確保不被注釋裡的 cover_full_url 字樣或別欄位的 &t= 騙過。
        """
        js = self._js()
        body = self._strip_line_comments(self._extract_refreshVideoData_body(js))
        m = re.search(
            r"data\.video\.cover_full_url\s*=\s*[^;\n]*\+\s*['\"]&t=",
            body
        )
        assert m, (
            "refreshVideoData 函式體找不到 'data.video.cover_full_url = ... + &t=' 賦值語句。\n"
            "lightbox overlay（.lb-full `:src='cover_full_url'`）不加 cache-bust 會吃 max-age=86400 舊快取。\n"
            f"當前函式體（去注釋後）：\n{body[:500]}"
        )


SHOWCASE_SIMILAR_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
)


# ─── 90c-T5: external_manager switch-mode destructive confirm frontend guards ─

class TestExternalManagerSwitchModeGuard:
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


# ─── 80a-T3: Server Mode toggle + info banner frontend guards ───────────────

SETTINGS_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "settings.css"


class TestMobileToolbarToggle:
    """feature/81 T2（US-1 / CD-1·CD-2·CD-4）：行動搜尋 store + navbar icon + toolbar 綁定。

    純靜態守衛（bs4 + 字串）。斷言：
    - base.html alpine:init 註冊 Alpine.store('ui', { toolbarOpen:false })。
    - navbar 搜尋 button：navbar-search-btn + lg:hidden + bi-search + @click 翻轉 $store.ui.toolbarOpen。
    - 該 button 被 {% if page == 'showcase' %} Jinja gate（**僅 showcase**；owner 2026-06-22
      拍板 search 頁 Spotlight 中央輸入維持原樣、不收進 navbar icon）。
    - showcase.toolbar 綁 :class mobile-toolbar-open ← $store.ui.toolbarOpen；search.search-bar **不**綁。
    動畫/收合/CSS gate 屬 T3/T4，不在此守衛。
    """

    def _base(self):
        return BASE_HTML_T76.read_text(encoding="utf-8")

    def test_store_registered_in_alpine_init(self):
        """base.html 在 alpine:init 監聽內註冊 Alpine.store('ui', { toolbarOpen: false, showcaseHasSearch: false })。"""
        html = self._base()
        assert "alpine:init" in html, "base.html missing alpine:init listener"
        assert "Alpine.store('ui'" in html, "base.html missing Alpine.store('ui') registration"
        assert "toolbarOpen" in html, "base.html missing toolbarOpen store field"
        # T2: showcaseHasSearch 欄位必須在同一 store 定義內
        assert "showcaseHasSearch" in html, "base.html missing showcaseHasSearch store field"
        # 註冊字串與 alpine:init 監聽同段（store 註冊掛在 alpine:init callback 內）
        assert re.search(
            r"alpine:init['\"]\s*,\s*\(\)\s*=>\s*\{\s*Alpine\.store\(\s*['\"]ui['\"]\s*,\s*\{\s*toolbarOpen:\s*false",
            html,
        ), "base.html: Alpine.store('ui', { toolbarOpen: false ... }) 須在 alpine:init callback 內註冊"

    def test_navbar_search_button(self):
        """navbar 搜尋 button：navbar-search-btn + lg:hidden + bi-search + @click 條件分支（T2）。"""
        from bs4 import BeautifulSoup
        html = self._base()
        btns = BeautifulSoup(html, "html.parser").select("button.navbar-search-btn")
        assert len(btns) == 1, f"base.html 須有且僅有 1 個 button.navbar-search-btn（實得 {len(btns)}）"
        btn = btns[0]
        classes = btn.get("class", [])
        assert "lg:hidden" in classes, "navbar-search-btn 須有 lg:hidden（≤1023px gate）"
        # T2: icon 改為 Alpine 動態 :class 綁定，BS4 CSS selector 無法匹配；改用字串檢查
        btn_html = str(btn)
        assert "bi-search" in btn_html, "navbar-search-btn 內須包含 bi-search（靜態 class 或動態 :class 均可）"
        click = btn.get("@click", "")
        # T2: @click 改為條件分支 — showcaseHasSearch 判斷 + dispatch + toolbarOpen 仍在 else 分支
        assert "$store.ui.showcaseHasSearch" in click, \
            f"navbar-search-btn @click 須包含 $store.ui.showcaseHasSearch 條件（實得 {click!r}）"
        assert "showcase:clear-search" in click, \
            f"navbar-search-btn @click 須 dispatch showcase:clear-search（實得 {click!r}）"
        assert "$store.ui.toolbarOpen" in click, \
            f"navbar-search-btn @click 須包含 $store.ui.toolbarOpen（else 分支保留舊行為，實得 {click!r}）"

    def test_navbar_search_button_jinja_gated(self):
        """搜尋 button 被 {% if page == 'showcase' %} Jinja gate（僅 showcase 渲染，不含 search）。"""
        html = self._base()
        # 容忍引號/空白變體
        assert re.search(
            r"\{%\s*if\s+page\s*==\s*['\"]showcase['\"]\s*%\}",
            html,
        ), "base.html: navbar 搜尋 button 須被 {% if page == 'showcase' %} gate"
        # button 落在該 gate 與其 endif 之間
        m = re.search(
            r"\{%\s*if\s+page\s*==\s*['\"]showcase['\"]\s*%\}(.*?)\{%\s*endif\s*%\}",
            html, re.DOTALL,
        )
        assert m and "navbar-search-btn" in m.group(1), \
            "navbar-search-btn 須落在 {% if page == 'showcase' %} … {% endif %} 區段內"

    def test_showcase_toolbar_class_binding(self):
        """showcase.html .showcase-toolbar 綁 :class mobile-toolbar-open ← $store.ui.toolbarOpen。"""
        from bs4 import BeautifulSoup
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        divs = BeautifulSoup(html, "html.parser").select("div.showcase-toolbar")
        assert divs, "showcase.html missing div.showcase-toolbar"
        binding = divs[0].get(":class", "")
        assert "mobile-toolbar-open" in binding and "$store.ui.toolbarOpen" in binding, \
            f".showcase-toolbar :class 須含 mobile-toolbar-open ← $store.ui.toolbarOpen（實得 {binding!r}）"

    def test_search_bar_not_bound(self):
        """search.html .search-bar（Spotlight 中央輸入）**不**綁 mobile-toolbar-open。

        owner 2026-06-22 拍板：US-1 navbar 收合只作用 showcase；search 頁的
        .search-bar 即 Spotlight 中央搜尋輸入（該頁唯一搜尋框），必須永遠可見、
        維持原樣（spec §3.1 末句優先於 CD-4）。守衛防回退把搜尋框收進 navbar icon。
        """
        from bs4 import BeautifulSoup
        html = SEARCH_HTML.read_text(encoding="utf-8")
        divs = BeautifulSoup(html, "html.parser").select("div.search-bar")
        assert divs, "search.html missing div.search-bar"
        binding = divs[0].get(":class", "")
        assert "mobile-toolbar-open" not in binding, \
            f".search-bar 不可綁 mobile-toolbar-open（search Spotlight 維持原樣，實得 {binding!r}）"


class TestMobileToolbarCss:
    """feature/81 T3（US-1 / CD-1·CD-3，**showcase 單頁**，owner 2026-06-22 拍板）：

    showcase.css ≤480 工具列收合/展開 overlay + 透明 backdrop 的靜態守衛。
    search 頁不在範圍（其 .search-bar 即 Spotlight 中央輸入，永遠可見）。

    斷言：
    - showcase.css @media (max-width:480px) 內 .showcase-toolbar 收合預設
      （position:fixed + translateY(-100%) + pointer-events:none）。
    - .showcase-toolbar.mobile-toolbar-open 展開態（translateY(0) + pointer-events:auto）。
    - transition 走 token（var(--fluent-duration-fast)/--duration-fast），無字面秒數。
    - showcase.html 有 div.mobile-toolbar-backdrop（x-show/@click 綁 store + x-cloak）。
    - .mobile-toolbar-backdrop CSS：position:fixed + z-index:85；toolbar ≤480 z-index:90（85<90）。
    """

    def _css(self):
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    def _480_block(self, css):
        """擷取 ≤480 區塊中含 .showcase-toolbar 的 @media block（容忍巢狀無，平掃）。"""
        # 找出所有 @media (max-width:480px){ ... } 區塊（簡單括號配對）
        blocks = []
        for m in re.finditer(r"@media[^{]*max-width:\s*480px[^{]*\{", css):
            start = m.end()
            depth = 1
            i = start
            while i < len(css) and depth > 0:
                if css[i] == "{":
                    depth += 1
                elif css[i] == "}":
                    depth -= 1
                i += 1
            blocks.append(css[start:i - 1])
        return "\n".join(blocks)

    def test_toolbar_collapsed_default(self):
        """≤480 .showcase-toolbar 收合預設：fixed + translateY(-100%) + pointer-events:none。"""
        block = self._480_block(self._css())
        assert block, "showcase.css 須有 @media (max-width:480px) 區塊"
        # 收合態須出現於同區塊
        assert re.search(r"\.showcase-toolbar\b", block), \
            "≤480 區塊缺 .showcase-toolbar 規則"
        assert "position: fixed" in block or "position:fixed" in block, \
            "≤480 .showcase-toolbar 須 position:fixed"
        assert re.search(r"transform:\s*translateY\(-100%\)", block), \
            "≤480 .showcase-toolbar 收合須 transform:translateY(-100%)"
        assert re.search(r"pointer-events:\s*none", block), \
            "≤480 .showcase-toolbar 收合須 pointer-events:none"

    def test_toolbar_open_state(self):
        """.showcase-toolbar.mobile-toolbar-open 展開：translateY(0) + pointer-events:auto。"""
        block = self._480_block(self._css())
        m = re.search(
            r"\.showcase-toolbar\.mobile-toolbar-open\b[^{]*\{([^}]*)\}", block,
        )
        assert m, "≤480 區塊缺 .showcase-toolbar.mobile-toolbar-open 規則"
        body = m.group(1)
        assert re.search(r"transform:\s*translateY\(0\)", body), \
            ".mobile-toolbar-open 須 transform:translateY(0)"
        assert re.search(r"pointer-events:\s*auto", body), \
            ".mobile-toolbar-open 須 pointer-events:auto"

    def test_transition_uses_token_not_literal_seconds(self):
        """toolbar transition 走 duration token，無字面秒數（stylelint 雙保險）。"""
        block = self._480_block(self._css())
        m = re.search(r"\.showcase-toolbar\b[^{]*\{([^}]*)\}", block)
        assert m, "≤480 區塊缺 .showcase-toolbar 規則"
        body = m.group(1)
        trans = re.search(r"transition:[^;]*;", body)
        assert trans, "≤480 .showcase-toolbar 須有 transition"
        trans_val = trans.group(0)
        assert ("var(--fluent-duration" in trans_val
                or "var(--duration-fast" in trans_val), \
            f"transition 須用 duration token（實得 {trans_val!r}）"
        assert not re.search(r"\b0?\.\d+s\b", trans_val), \
            f"transition 不可含字面秒數（實得 {trans_val!r}）"

    def test_backdrop_css(self):
        """.mobile-toolbar-backdrop CSS：position:fixed + z-index:85；toolbar ≤480 z-index:90。"""
        css = self._css()
        m = re.search(r"\.mobile-toolbar-backdrop\b[^{]*\{([^}]*)\}", css)
        assert m, "showcase.css 缺 .mobile-toolbar-backdrop 規則"
        body = m.group(1)
        assert "position: fixed" in body or "position:fixed" in body, \
            ".mobile-toolbar-backdrop 須 position:fixed"
        assert re.search(r"z-index:\s*85\b", body), \
            ".mobile-toolbar-backdrop 須 z-index:85"
        # toolbar ≤480 須 z-index:90（85<90 階層）
        block = self._480_block(css)
        tm = re.search(r"\.showcase-toolbar\b[^{]*\{([^}]*)\}", block)
        assert tm and re.search(r"z-index:\s*90\b", tm.group(1)), \
            "≤480 .showcase-toolbar 須 z-index:90（backdrop 85 < toolbar 90）"

    def test_backdrop_dom(self):
        """showcase.html 有 div.mobile-toolbar-backdrop：x-show/@click 綁 store + x-cloak。"""
        from bs4 import BeautifulSoup
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        divs = BeautifulSoup(html, "html.parser").select("div.mobile-toolbar-backdrop")
        assert len(divs) == 1, \
            f"showcase.html 須有且僅 1 個 div.mobile-toolbar-backdrop（實得 {len(divs)}）"
        bd = divs[0]
        assert bd.get("x-show", "") == "$store.ui.toolbarOpen", \
            f"backdrop x-show 須為 $store.ui.toolbarOpen（實得 {bd.get('x-show')!r}）"
        click = bd.get("@click", "")
        assert "$store.ui.toolbarOpen" in click and "false" in click, \
            f"backdrop @click 須將 $store.ui.toolbarOpen 設 false（實得 {click!r}）"
        assert bd.has_attr("x-cloak"), "backdrop 須有 x-cloak"

    def test_navbar_search_btn_hidden_above_480(self):
        """showcase.css 在 @media (min-width:481px) 把 .navbar-search-btn 隱藏（Codex P2）。

        base.html 的 navbar 搜尋 icon 僅 lg:hidden（<1024 可見），但收合 overlay CSS 只在 ≤480；
        若不收緊，481–1023px 會看到 icon 但點了無收合反應（誤導控制）。此守衛鎖定
        「icon 可見區 = 收合 UI 生效區 = ≤480」的斷點一致性，防回退。
        """
        css = self._css()
        blocks = re.findall(
            r"@media\s*\(\s*min-width:\s*481px\s*\)\s*\{(.*?)\n\}",
            css,
            re.DOTALL,
        )
        hidden = any(
            re.search(r"\.navbar-search-btn\b[^{}]*\{[^}]*display:\s*none", block)
            for block in blocks
        )
        assert hidden, \
            "showcase.css 須在 @media (min-width:481px) 將 .navbar-search-btn display:none（Codex P2：icon 斷點對齊 ≤480 收合 UI）"


class TestMobileToolbarAutoCollapse:
    """feature/81 T4（US-1 / CD-5）：showcase 工具列「送出搜尋」自動收合。

    收合掛在**箭頭送出鈕**的 @click（明確送出手勢），**不**掛 onSearchChange() JS——
    因搜尋框是 @input.debounce live-filter，寫進 JS 會讓打字途中工具列滑走（破 UX）。
    箭頭鈕 @click 一處同時覆蓋影片(onSearchChange) / 女優(onActressSearchChange) 兩模式。
    點外面收合由 T3 backdrop 處理（見 TestMobileToolbarCss.test_backdrop_dom）。
    """

    def _submit_btn_click(self):
        """回傳 showcase 箭頭送出鈕的 @click 字串。

        以 title `{{ t('showcase.action.search') }}` 唯一辨識（清除鈕 @click 也含兩個
        SearchChange 呼叫，不能靠 @click 內容辨識，須靠 title 區分）。
        """
        from bs4 import BeautifulSoup
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        for btn in BeautifulSoup(html, "html.parser").select("button"):
            if btn.get("title", "") == "{{ t('showcase.action.search') }}":
                return btn.get("@click", "")
        return None

    def test_submit_button_collapses_toolbar(self):
        """箭頭送出鈕 @click 同時跑搜尋並 set $store.ui.toolbarOpen = false。"""
        click = self._submit_btn_click()
        assert click is not None, \
            "showcase.html 找不到箭頭送出鈕（title=showcase.action.search）"
        # 仍須跑搜尋（防 mutation 只留收合、丟掉送出）
        assert "SearchChange()" in click, \
            f"箭頭送出鈕 @click 須仍呼叫 (onActress)SearchChange()（實得 {click!r}）"
        assert re.search(r"\$store\.ui\.toolbarOpen\s*=\s*false", click), \
            f"箭頭送出鈕 @click 須在送出後 set $store.ui.toolbarOpen = false（實得 {click!r}）"

    def test_live_filter_input_does_not_collapse(self):
        """@input.debounce live-filter 綁定**不可**含收合（防回退把收合塞進每次 keystroke）。"""
        from bs4 import BeautifulSoup
        html = SHOWCASE_HTML.read_text(encoding="utf-8")
        for inp in BeautifulSoup(html, "html.parser").select("input"):
            for attr, val in inp.attrs.items():
                if attr.startswith("@input") and "SearchChange" in (val if isinstance(val, str) else ""):
                    assert "toolbarOpen" not in val, \
                        f"@input live-filter 不可含 toolbarOpen 收合（打字途中收合破 UX，實得 {val!r}）"


# ─── TASK-81a-T5: Settings + Help 窄螢幕破版 / 長字串溢出（3 點純 CSS 補丁）───
# ── feature/81 T10 (US-10): 481–899px 影片 grid → 4-col 直式右裁 poster ────────
# ==================== TASK-81a-T11: posterCrop JS↔CSS 門檻對齊（US-10 / CD-10）====================
# 鎖死「posterCrop ghost-fly 門檻 == 燈箱封面貼合斷點 == CSS poster grid 斷點 == 899」跨 4+2 檔。
# 任一處未來漂移（只改一邊）即紅。比照 v0.10.2「JS bail 門檻對齊 CSS」防漂移前例。
T11_BREAKPOINTS_JS    = PROJECT_ROOT / "web" / "static" / "js" / "shared" / "breakpoints.js"
T11_STATE_LIGHTBOX_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
T11_GRID_MODE_JS      = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"
T11_SHOWCASE_CSS      = PROJECT_ROOT / "web" / "static" / "css" / "pages" / "showcase.css"
T11_SEARCH_CSS        = PROJECT_ROOT / "web" / "static" / "css" / "pages" / "search.css"


# ---------------------------------------------------------------------------
# feature/82 T4: Settings closeAction select guard
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# feature/83a T2: Lightbox modal-hug contract guards (8 guards, pure additive)
# ---------------------------------------------------------------------------

class TestLightboxModalHugContract:
    """83a-T2: 固化 T1/T1fix1 modal-hug 契約（8 條純加法守衛）

    83b-T2：:not(.similar-open) gate 已移除，選擇器改為無條件形式。
    #1 has-cover 含 aspect-ratio:var(--lb-cover-ar)
    #2 has-cover 含 flex-shrink:0（防 T1 letterbox 主因回歸）
    #3 has-cover 含 min-width:0 AND min-height:0
    #4 width formula 含 90dvh 且整塊不含 100dvh/100vh（T1fix1 FHD 捲動修正）
    #5 has-cover img 填滿盒（position:absolute + width/height:100%）
    #6 has-cover .lb-full 填滿盒（width/height:100% + margin:0）
    #7 .lightbox-metadata 不含 max-width:600px
    #8 state-lightbox.js _setCoverAspect + closest + setProperty 三元素存在
    """

    def _css(self):
        # Reuse module-level constant declared at line 3474
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    def _js(self):
        # Reuse module-level constant declared at line 91
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _has_cover_block(self, css):
        """擷取 .lightbox-content .lightbox-cover.has-cover { ... } 塊內容
        （83b-T2 後：:not(.similar-open) gate 移除）
        """
        m = re.search(
            r'\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def _has_cover_img_block(self, css):
        m = re.search(
            r'\.lightbox-content\s+\.lightbox-cover\.has-cover\s+img\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def _has_cover_lb_full_block(self, css):
        m = re.search(
            r'\.lightbox-content\s+\.lightbox-cover\.has-cover\s+\.lb-full\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def _metadata_block(self, css):
        m = re.search(r'\.lightbox-metadata\s*\{([^}]*)\}', css, re.DOTALL)
        return m.group(1) if m else None

    def test_has_cover_aspect_ratio_set(self):
        """modal-hug 主規則含 aspect-ratio:var(--lb-cover-ar)（無此行盒不跟圖比例）"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover 規則（83b-T2 後 gate 已移除）"
        )
        assert re.search(r'aspect-ratio\s*:\s*var\(--lb-cover-ar', block), (
            ".lightbox-cover.has-cover 缺少 aspect-ratio: var(--lb-cover-ar)（modal-hug 核心）"
        )

    def test_has_cover_flex_shrink_zero(self):
        """.lightbox-cover.has-cover 含 flex-shrink:0（T1 letterbox 主 bug 的修正守衛）"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover 規則（83b-T2 後 gate 已移除）"
        )
        assert re.search(r'flex-shrink\s*:\s*0', block), (
            ".lightbox-cover.has-cover 缺少 flex-shrink:0（此為 T1 letterbox 主 bug 的修正守衛）"
        )

    def test_has_cover_floor_zeroed(self):
        """.lightbox-cover.has-cover 含 min-width:0 且 min-height:0（floor 歸零讓 AR 完整掌控尺寸）"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover 規則（83b-T2 後 gate 已移除）"
        )
        assert re.search(r'min-width\s*:\s*0', block), ".lightbox-cover.has-cover 缺少 min-width:0"
        assert re.search(r'min-height\s*:\s*0', block), ".lightbox-cover.has-cover 缺少 min-height:0"

    def test_has_cover_width_formula_uses_90dvh(self):
        """width formula 含 90dvh 且整塊不含 100dvh/100vh（T1fix1 FHD 捲動修正）"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover 規則（83b-T2 後 gate 已移除）"
        )
        assert '90dvh' in block, (
            ".lightbox-cover.has-cover width formula 缺少 90dvh（T1fix1 FHD 捲動修正）"
        )
        assert '100dvh' not in block, (
            ".lightbox-cover.has-cover 含 100dvh，應為 90dvh（T1fix1 FHD 捲動修正）"
        )
        assert '100vh' not in block, (
            ".lightbox-cover.has-cover 含 100vh，應為 90vh/90dvh"
        )

    def test_has_cover_img_fills_box(self):
        """.has-cover img 填滿盒（position:absolute + width/height:100%）"""
        block = self._has_cover_img_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover img 規則（83b-T2 後 gate 已移除）"
        )
        assert re.search(r'position\s*:\s*absolute', block), ".has-cover img 缺少 position:absolute"
        assert re.search(r'width\s*:\s*100%', block), ".has-cover img 缺少 width:100%"
        assert re.search(r'height\s*:\s*100%', block), ".has-cover img 缺少 height:100%"

    def test_has_cover_lb_full_fills_box(self):
        """.has-cover .lb-full 填滿盒（width/height:100% + margin:0）"""
        block = self._has_cover_lb_full_block(self._css())
        assert block is not None, (
            "showcase.css 找不到 .lightbox-content .lightbox-cover.has-cover .lb-full 規則（83b-T2 後 gate 已移除）"
        )
        assert re.search(r'width\s*:\s*100%', block), ".has-cover .lb-full 缺少 width:100%"
        assert re.search(r'height\s*:\s*100%', block), ".has-cover .lb-full 缺少 height:100%"
        assert re.search(r'margin\s*:\s*0', block), ".has-cover .lb-full 缺少 margin:0"

    def test_metadata_no_max_width_600(self):
        """.lightbox-metadata 不含 max-width:600px（T1 M4 已移除，勿復原）"""
        block = self._metadata_block(self._css())
        assert block is not None, "showcase.css 找不到 .lightbox-metadata 規則"
        assert not re.search(r'max-width\s*:\s*600px', block), (
            ".lightbox-metadata 含 max-width:600px（T1 M4 已移除，勿復原）"
        )

    def test_set_cover_aspect_js_contract(self):
        """state-lightbox.js 含 _setCoverAspect + closest('.lightbox-cover') + setProperty('--lb-cover-ar') 三元素"""
        js = self._js()
        assert '_setCoverAspect' in js, "state-lightbox.js 缺少 _setCoverAspect 函數"
        assert "closest('.lightbox-cover')" in js, (
            "state-lightbox.js 缺少 closest('.lightbox-cover') 呼叫"
        )
        assert "setProperty('--lb-cover-ar'" in js, (
            "state-lightbox.js 缺少 setProperty('--lb-cover-ar') 呼叫"
        )

    def test_metadata_flex_distribution(self):
        """83a-T3-fix P1: .lightbox-metadata 有 flex:1 1 auto + overflow-y:auto（metadata 自行捲，modal 不捲）"""
        block = self._metadata_block(self._css())
        assert block is not None, "showcase.css 找不到 .lightbox-metadata 規則"
        assert re.search(r'flex\s*:\s*1\s+1\s+auto', block), (
            ".lightbox-metadata 缺少 flex:1 1 auto（P1 fix：metadata 佔剩餘高度）"
        )
        assert re.search(r'overflow-y\s*:\s*auto', block), (
            ".lightbox-metadata 缺少 overflow-y:auto（P1 fix：metadata 內部捲，modal 不捲）"
        )


class TestSearchLightboxModalHugContract:
    """83a-T3: 固化 search 頁 lightbox modal-hug 契約（7 條純加法守衛）

    #S1 search.css .search-container .lightbox-cover.has-cover 含 aspect-ratio:var(--lb-cover-ar)
    #S2 search.css .search-container .lightbox-cover.has-cover 含 flex-shrink:0
    #S3 search.css .search-container .lightbox-cover.has-cover 含 min-width:0 AND min-height:0
    #S4 search.css .search-container .lightbox-cover.has-cover 含 90dvh（且不含 100dvh/100vh）
    #S5 search.css .search-container .lightbox-cover.has-cover img 含 position:absolute + width/height:100%
    #S6 search.html lightbox img 含 @load="_setCoverAspect($event)"
    #S7 grid-mode.js 含 _setCoverAspect + closest('.lightbox-cover') + setProperty('--lb-cover-ar')
    """

    GRID_MODE_JS = Path(__file__).parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"
    SEARCH_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "search.html"

    def _css(self):
        return SEARCH_CSS.read_text(encoding="utf-8")

    def _js(self):
        return self.GRID_MODE_JS.read_text(encoding="utf-8")

    def _html(self):
        return self.SEARCH_HTML.read_text(encoding="utf-8")

    def _has_cover_block(self, css):
        """擷取 .search-container .lightbox-cover.has-cover { ... } 塊內容"""
        m = re.search(
            r'\.search-container\s+\.lightbox-cover\.has-cover\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def _has_cover_img_block(self, css):
        m = re.search(
            r'\.search-container\s+\.lightbox-cover\.has-cover\s+img\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def test_s1_has_cover_aspect_ratio(self):
        """#S1 .search-container .lightbox-cover.has-cover 含 aspect-ratio:var(--lb-cover-ar)"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-cover.has-cover 規則"
        )
        assert re.search(r'aspect-ratio\s*:\s*var\(--lb-cover-ar', block), (
            ".search-container .lightbox-cover.has-cover 缺少 aspect-ratio: var(--lb-cover-ar)（modal-hug 核心）"
        )

    def test_s2_has_cover_flex_shrink_zero(self):
        """#S2 .search-container .lightbox-cover.has-cover 含 flex-shrink:0"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-cover.has-cover 規則"
        )
        assert re.search(r'flex-shrink\s*:\s*0', block), (
            ".search-container .lightbox-cover.has-cover 缺少 flex-shrink:0"
        )

    def test_s3_has_cover_floor_zeroed(self):
        """#S3 .search-container .lightbox-cover.has-cover 含 min-width:0 AND min-height:0"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-cover.has-cover 規則"
        )
        assert re.search(r'min-width\s*:\s*0', block), (
            ".search-container .lightbox-cover.has-cover 缺少 min-width:0"
        )
        assert re.search(r'min-height\s*:\s*0', block), (
            ".search-container .lightbox-cover.has-cover 缺少 min-height:0"
        )

    def test_s4_has_cover_width_formula_uses_90dvh(self):
        """#S4 width formula 含 90dvh 且不含 100dvh/100vh"""
        block = self._has_cover_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-cover.has-cover 規則"
        )
        assert '90dvh' in block, (
            ".search-container .lightbox-cover.has-cover width formula 缺少 90dvh"
        )
        assert '100dvh' not in block, (
            ".search-container .lightbox-cover.has-cover 含 100dvh，應為 90dvh"
        )
        assert '100vh' not in block, (
            ".search-container .lightbox-cover.has-cover 含 100vh，應為 90vh/90dvh"
        )

    def test_s5_has_cover_img_fills_box(self):
        """#S5 .search-container .lightbox-cover.has-cover img 含 position:absolute + width/height:100%"""
        block = self._has_cover_img_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-cover.has-cover img 規則"
        )
        assert re.search(r'position\s*:\s*absolute', block), (
            ".search-container .lightbox-cover.has-cover img 缺少 position:absolute"
        )
        assert re.search(r'width\s*:\s*100%', block), (
            ".search-container .lightbox-cover.has-cover img 缺少 width:100%"
        )
        assert re.search(r'height\s*:\s*100%', block), (
            ".search-container .lightbox-cover.has-cover img 缺少 height:100%"
        )

    def test_s6_search_html_load_handler(self):
        """#S6 search.html lightbox img 含 @load="_setCoverAspect($event)" """
        html = self._html()
        assert '@load="_setCoverAspect($event)"' in html, (
            "search.html lightbox img 缺少 @load=\"_setCoverAspect($event)\"（83a-T3 移植守衛）"
        )

    def test_s7_grid_mode_js_set_cover_aspect(self):
        """#S7 grid-mode.js 含 _setCoverAspect + closest('.lightbox-cover') + setProperty('--lb-cover-ar')"""
        js = self._js()
        assert '_setCoverAspect' in js, (
            "grid-mode.js 缺少 _setCoverAspect 函式（83a-T3 移植守衛）"
        )
        assert "closest('.lightbox-cover')" in js, (
            "grid-mode.js 缺少 closest('.lightbox-cover') 呼叫"
        )
        assert "setProperty('--lb-cover-ar'" in js, (
            "grid-mode.js 缺少 setProperty('--lb-cover-ar') 呼叫"
        )

    def _search_lightbox_content_block(self, css):
        m = re.search(
            r'\.search-container\s+\.lightbox-content\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        return m.group(1) if m else None

    def test_s8_search_lightbox_content_overflow_hidden(self):
        """83a-T3-fix P1: .search-container .lightbox-content 有 overflow-y:hidden（modal 不捲）"""
        block = self._search_lightbox_content_block(self._css())
        assert block is not None, (
            "search.css 找不到 .search-container .lightbox-content 規則（P1 fix 缺失）"
        )
        assert re.search(r'overflow-y\s*:\s*hidden', block), (
            ".search-container .lightbox-content 缺少 overflow-y:hidden（P1 fix：modal 整體不捲）"
        )


# feature/83a2 T4: Search detail cover fix contract guards (pure additive)
# 鎖 search detail 封面欄留白 + 劇照截斷修正（Bug A/B）的跨檔 CSS 覆寫契約。
class TestSearchDetailCoverFixContract:
    """83a2-T4: 固化 search detail 封面欄修正契約（純加法守衛）

    #D1 .search-container .av-card-full-cover 含 min-height:0（清 theme.css 200px 地板）
    #D2 .search-container .av-card-full-cover-wrapper 含 min-height:0（清 search.css 400px 地板）
    #D3 .search-container .av-card-full-cover-img 含 height:auto（不依賴父容器死高）
    #D4 :has(.cover-error-placeholder...) min-height fallback 存在（無圖時 placeholder 不塌）
    #D5 @media ≤1024px .search-container .av-card-full-cover 含 overflow:visible（mobile 不截 sample-strip）
    """

    def _css(self):
        # 去 /* ... */ 註解：本 task 的說明註解刻意提到 override 值（min-height:0 等），
        # 不剝除會讓守衛比對到註解文字而非真宣告（false-positive，mutation 抓不到）。
        raw = SEARCH_CSS.read_text(encoding="utf-8")
        return re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)

    def _block(self, css, selector_regex):
        """擷取首個 `selector { ... }` 塊內容（非貪婪到第一個 }）"""
        m = re.search(selector_regex + r'\s*\{([^}]*)\}', css, re.DOTALL)
        return m.group(1) if m else None

    def test_d1_cover_min_height_zero(self):
        """#D1 .search-container .av-card-full-cover 含 min-height:0（覆寫 theme.css min-height:200px）"""
        block = self._block(
            self._css(),
            r'\.search-container\s+\.av-card-full-cover(?![-\w])'
        )
        assert block is not None, (
            "search.css 找不到 .search-container .av-card-full-cover 規則"
        )
        assert re.search(r'min-height\s*:\s*0', block), (
            ".search-container .av-card-full-cover 缺少 min-height:0（Bug B 留白會回歸）"
        )

    def test_d2_wrapper_min_height_zero(self):
        """#D2 .search-container .av-card-full-cover-wrapper 含 min-height:0（覆寫 400px 主地板）"""
        block = self._block(
            self._css(),
            r'\.search-container\s+\.av-card-full-cover-wrapper(?![-\w])'
        )
        assert block is not None, (
            "search.css 找不到 .search-container .av-card-full-cover-wrapper 規則"
        )
        assert re.search(r'min-height\s*:\s*0', block), (
            ".search-container .av-card-full-cover-wrapper 缺少 min-height:0（Bug B 主地板未清）"
        )

    def test_d3_cover_img_height_auto(self):
        """#D3 .search-container .av-card-full-cover-img 含 height:auto（圖高由 AR 自然推導）"""
        block = self._block(
            self._css(),
            r'\.search-container\s+\.av-card-full-cover-img(?![-\w])'
        )
        assert block is not None, (
            "search.css 找不到 .search-container .av-card-full-cover-img 規則"
        )
        assert re.search(r'height\s*:\s*auto', block), (
            ".search-container .av-card-full-cover-img 缺少 height:auto（仍靠父容器死高 → 留白）"
        )

    def test_d4_error_placeholder_min_height_fallback(self):
        """#D4 :has(.cover-error-placeholder:not([style*=display:none])) min-height fallback 存在"""
        css = self._css()
        # 找 :has(.cover-error-placeholder...) 規則塊
        # 用 [^{]* 而非 [^)]*：selector 含 :not(...) 巢狀括號，不能在第一個 ) 停
        m = re.search(
            r'\.search-container\s+\.av-card-full-cover-wrapper:has\([^{]*cover-error-placeholder[^{]*\)\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        assert m is not None, (
            "search.css 找不到 wrapper:has(.cover-error-placeholder) fallback 規則"
            "（min-height:0 後無圖時 placeholder 會塌掉不可見）"
        )
        block = m.group(1)
        # 必須非零（min-height:0 等於沒 fallback，placeholder 仍塌）
        assert re.search(r'min-height\s*:\s*[1-9]\d*', block), (
            "error-placeholder fallback 規則缺少非零 min-height（placeholder 仍會塌）"
        )

    def test_d4b_loading_placeholder_min_height_fallback(self):
        """#D4b :has(.cover-loading-placeholder:not([style*=display:none])) min-height fallback 存在

        83a2-T4 Codex P2：封面載入中（_coverLoaded=false，慢速/未快取）走 .cover-loading-placeholder
        shimmer 路徑，img height:auto 尚無 intrinsic size + shimmer position:absolute → wrapper 塌 0，
        shimmer 與 nav-indicator 一起閃失。D4（error-placeholder）抓不到此單邊回歸，須獨立守衛。
        """
        css = self._css()
        m = re.search(
            r'\.search-container\s+\.av-card-full-cover-wrapper:has\([^{]*cover-loading-placeholder[^{]*\)\s*\{([^}]*)\}',
            css, re.DOTALL
        )
        assert m is not None, (
            "search.css 找不到 wrapper:has(.cover-loading-placeholder) fallback 規則"
            "（83a2-T4 Codex P2：載入期 shimmer 塌 0 高、nav-indicator 閃失）"
        )
        block = m.group(1)
        assert re.search(r'min-height\s*:\s*[1-9]\d*', block), (
            "loading-placeholder fallback 規則缺少非零 min-height（shimmer 仍會塌）"
        )

    def test_d5_mobile_cover_overflow_visible(self):
        """#D5 @media ≤1024px .search-container .av-card-full-cover 含 overflow:visible"""
        css = self._css()
        # 擷取 @media (max-width:1024px) { ... } 整段（巢狀 brace，用平衡掃描）
        start = re.search(r'@media\s*\(\s*max-width\s*:\s*1024px\s*\)\s*\{', css)
        assert start is not None, "search.css 找不到 @media (max-width:1024px) 區塊"
        i = start.end()
        depth = 1
        while i < len(css) and depth > 0:
            if css[i] == '{':
                depth += 1
            elif css[i] == '}':
                depth -= 1
            i += 1
        media_body = css[start.end():i - 1]
        block = self._block(
            media_body,
            r'\.search-container\s+\.av-card-full-cover(?![-\w])'
        )
        assert block is not None, (
            "≤1024px media 內找不到 .search-container .av-card-full-cover 規則"
        )
        assert re.search(r'overflow\s*:\s*visible', block), (
            "≤1024px .search-container .av-card-full-cover 缺少 overflow:visible"
            "（Bug A mobile：max-height:50vh+overflow:hidden 截 sample-strip 會回歸）"
        )


# ============================================================================
# TASK-83b-T2: Mobile Similar Panel Contract Guards（13 條）
# 鎖住 T1 建立的行動相似面板合約：CSS default-hidden、safety-net、scrim、burst-card、
# JS drill-lock、no-desktop-close、picker-params、matchMedia、keydown intercept。
# ============================================================================

_T2_SHOWCASE_HTML = Path(__file__).parent.parent.parent / "web" / "templates" / "showcase.html"
_T2_SHOWCASE_CSS = Path(__file__).parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
_T2_SIMILAR_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
)
_T2_LIGHTBOX_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
)
_T2_BASE_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
)
_T2_BURST_PICKER_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "shared" / "burst-picker.js"
)


# ============================================================================
# TASK-83b-T3: Mobile Similar Panel Transition Guards（6 條）
# 鎖住 T3 建立的封面飛行進 / 退場合約：helper 存在 / 不包裝禁區 / token 化 /
# async closeMobilePanel / PRM 分支 / 桌面禁區 anchor 不被 mobile helper 引用。
# ============================================================================

_T3_GHOST_FLY_JS = (
    Path(__file__).parent.parent.parent
    / "web" / "static" / "js" / "shared" / "ghost-fly.js"
)


class TestSimilarMobilePanelT4Guard:
    """83b-T4: 行動相似面板主圖播放按鈕合約守衛"""

    def _html(self):
        return Path("web/templates/showcase.html").read_text(encoding="utf-8")

    def _css(self):
        return Path("web/static/css/pages/showcase.css").read_text(encoding="utf-8")

    def test_mobile_play_btn_exists_in_stage(self):
        """T4: .similar-mobile-stage 內含 .similar-mobile-play-btn button（.similar-mobile-cover 子元素，overflow:hidden 已移至 img）"""
        html = self._html()
        # 先找 .similar-mobile-stage block
        m = re.search(
            r'<div class="similar-mobile-stage">(.*?)</div>\s*<!-- 右上',
            html, re.S
        )
        assert m, "showcase.html: .similar-mobile-stage block 不存在"
        stage = m.group(1)
        assert 'class="similar-mobile-play-btn"' in stage, \
            ".similar-mobile-stage 內缺 <button class=\"similar-mobile-play-btn\">（T4 播放按鈕）"

    def test_mobile_play_btn_handlers(self):
        """T4: 播放按鈕有 @click.stop + x-show path guard + :disabled drill-lock + aria-label"""
        html = self._html()
        m = re.search(r'<button class="similar-mobile-play-btn"[^>]*>', html, re.S)
        assert m, "showcase.html: 找不到 <button class=\"similar-mobile-play-btn\">"
        btn = m.group(0)
        assert '@click.stop="playVideo(currentLightboxVideo?.path)"' in btn, \
            "播放按鈕須有 @click.stop=\"playVideo(currentLightboxVideo?.path)\"（stop 防冒泡觸發 closeMobilePanel）"
        assert 'x-show="!!currentLightboxVideo?.path"' in btn, \
            "播放按鈕須有 x-show=\"!!currentLightboxVideo?.path\"（tier-3 孤兒 path=undefined 時隱藏）"
        assert ':disabled="similarModeAnimating"' in btn, \
            "播放按鈕須有 :disabled=\"similarModeAnimating\"（drill 動畫中 lock）"
        assert ":aria-label=\"t('showcase.action.play')\"" in btn, \
            "播放按鈕須有 :aria-label=\"t('showcase.action.play')\"（i18n）"

    def test_mobile_play_btn_css_tokens(self):
        """T4: .similar-mobile-play-btn CSS 在 max-width:959px 內，使用 Fluent token，含雙寫 -webkit-backdrop-filter"""
        css = self._css()
        # 確認 class 存在
        assert ".similar-mobile-play-btn" in css, \
            "showcase.css 缺 .similar-mobile-play-btn 規則"
        # 找規則區塊
        m = re.search(r'\.similar-mobile-play-btn\s*\{([^}]*)\}', css, re.S)
        assert m, "showcase.css: .similar-mobile-play-btn {} block 不存在"
        body = m.group(1)
        assert "var(--overlay-control)" in body, \
            ".similar-mobile-play-btn background 須用 var(--overlay-control)（不硬編碼 rgba）"
        assert "var(--fluent-blur-light)" in body, \
            ".similar-mobile-play-btn backdrop-filter 須用 var(--fluent-blur-light)（不硬編碼 px）"
        assert "-webkit-backdrop-filter" in body, \
            ".similar-mobile-play-btn 須含 -webkit-backdrop-filter 雙寫（iOS Safari）"
        assert "border-radius: 50%" in body, \
            ".similar-mobile-play-btn 須是圓形（border-radius: 50%）"
        # 確認在 max-width:959px media query 內
        # 找包含此 class 的 @media block
        media_block = re.search(
            r'@media\s*\(max-width:\s*959px\)[^{]*\{(.*?)(?=@media|\Z)',
            css, re.S
        )
        assert media_block and ".similar-mobile-play-btn" in media_block.group(1), \
            ".similar-mobile-play-btn 須在 @media (max-width:959px) 內（行動限定）"

    def test_mobile_play_btn_ghost_hide(self):
        """T4-fix: ghost-fly 飛行期間按鈕隱藏規則（img[data-ghost-hidden] ~ .similar-mobile-play-btn）"""
        css = self._css()
        assert "img[data-ghost-hidden] ~ .similar-mobile-play-btn" in css, \
            "showcase.css 缺 ghost-hide 規則：img[data-ghost-hidden] ~ .similar-mobile-play-btn"
        m = re.search(
            r'img\[data-ghost-hidden\]\s*~\s*\.similar-mobile-play-btn\s*\{([^}]*)\}',
            css, re.S
        )
        assert m, "showcase.css: ghost-hide rule block 不存在"
        body = m.group(1)
        assert "opacity: 0" in body, \
            "ghost-hide 規則須含 opacity: 0"
        assert "pointer-events: none" in body, \
            "ghost-hide 規則須含 pointer-events: none（飛行期間防誤點）"


class TestDirPathHelperGuard:
    """TASK-88a-T2: dirPath helper 簽章守衛 + directory-row template 綁定守衛。

    1. shared/dir-path.js 存在且 export function dirPath
    2. state-scan.js / state-ui.js 各自 import dirPath
    3. scanner.html directory-row 已用 dirPath(dir)（不殘留裸 x-text="dir"）
    4. settings.html directory-row 四處已全 dirPath(dir) 化（:key/:title/@click/x-text）
    5. 無裸 :key="dir" 殘留（settings.html）
    """

    _ROOT = Path(__file__).parent.parent.parent

    def _dir_path_js(self):
        return (self._ROOT / "web" / "static" / "js" / "shared" / "dir-path.js").read_text(encoding="utf-8")

    def _state_scan(self):
        return (self._ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js").read_text(encoding="utf-8")

    def _state_ui(self):
        return (self._ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-ui.js").read_text(encoding="utf-8")

    def _scanner_html(self):
        return (self._ROOT / "web" / "templates" / "scanner.html").read_text(encoding="utf-8")

    def _settings_html(self):
        return (self._ROOT / "web" / "templates" / "settings.html").read_text(encoding="utf-8")

    def test_dir_path_js_exists_and_exports(self):
        """shared/dir-path.js 存在且含 export function dirPath"""
        src = self._dir_path_js()
        assert 'export function dirPath' in src, \
            "shared/dir-path.js 缺 export function dirPath"

    def test_state_scan_imports_dir_path(self):
        """state-scan.js 從 @/shared/dir-path.js import dirPath"""
        src = self._state_scan()
        assert "import { dirPath } from '@/shared/dir-path.js'" in src, \
            "state-scan.js 缺 import { dirPath } from '@/shared/dir-path.js'"

    def test_state_ui_imports_dir_path(self):
        """state-ui.js 從 @/shared/dir-path.js import dirPath"""
        src = self._state_ui()
        assert "import { dirPath } from '@/shared/dir-path.js'" in src, \
            "state-ui.js 缺 import { dirPath } from '@/shared/dir-path.js'"

    def test_state_scan_exposes_dir_path_on_state(self):
        """state-scan.js 把 dirPath 揭露成 state 屬性（否則 template dirPath(dir) runtime throw）"""
        src = self._state_scan()
        assert 'dirPath,' in src, \
            "state-scan.js 未把 dirPath 揭露成 state 屬性（import 不夠，template 求值會 throw）"

    def test_state_ui_exposes_dir_path_on_state(self):
        """state-ui.js 把 dirPath 揭露成 state 屬性（否則 template dirPath(dir) runtime throw）"""
        src = self._state_ui()
        assert 'dirPath,' in src, \
            "state-ui.js 未把 dirPath 揭露成 state 屬性（import 不夠，template 求值會 throw）"

    def test_scanner_html_uses_dir_path(self):
        """scanner.html directory-row 已用 dirPath(dir)（不殘留裸 x-text="dir"）"""
        html = self._scanner_html()
        assert 'x-text="dirPath(dir)"' in html, \
            'scanner.html folder-path span 缺 x-text="dirPath(dir)"'

    def test_scanner_html_no_bare_xtext_dir(self):
        """scanner.html folder-path 不殘留裸 x-text="dir"（directory-row）"""
        html = self._scanner_html()
        assert 'x-text="dir"' not in html, \
            'scanner.html 殘留裸 x-text="dir" — 應改為 x-text="dirPath(dir)"'

    def test_settings_html_key_uses_dir_path(self):
        """settings.html directory-row :key 已改為 dirPath(dir)"""
        html = self._settings_html()
        # The scanner-dir-dropdown x-for must use dirPath
        assert ':key="dirPath(dir)"' in html, \
            'settings.html 缺 :key="dirPath(dir)" — [object Object] key bug 未修'

    def test_settings_html_no_bare_key_dir(self):
        """settings.html directory-row 不殘留裸 :key=dir（應改為 :key="dirPath(dir)"）"""
        html = self._settings_html()
        assert ':key="dir"' not in html, \
            'settings.html 殘留裸 :key="dir" — 應改為 :key="dirPath(dir)"'

    def test_settings_html_title_uses_dir_path(self):
        """settings.html directory-row :title 已改為 dirPath(dir)"""
        html = self._settings_html()
        assert ':title="dirPath(dir)"' in html, \
            'settings.html 缺 :title="dirPath(dir)"'

    def test_settings_html_click_uses_dir_path(self):
        """settings.html directory-row @click 已改為 pickScannerDirectory(dirPath(dir))"""
        html = self._settings_html()
        assert '@click="pickScannerDirectory(dirPath(dir))"' in html, \
            'settings.html 缺 @click="pickScannerDirectory(dirPath(dir))"'

    def test_settings_html_xtext_uses_dir_path(self):
        """settings.html directory-row x-text 已改為 dirPath(dir)"""
        html = self._settings_html()
        # The dropdown button x-text must use dirPath
        assert 'x-text="dirPath(dir)"' in html, \
            'settings.html 缺 x-text="dirPath(dir)"'


class TestDirReadonlyUIGuard:
    """TASK-88a-T4: 唯讀 checkbox + 輸出夾 input Alpine 綁定守衛。

    1. scanner.html 含 x-model="dir.readonly"（checkbox 綁定）
    2. scanner.html 含 x-model="dir.output_path"（輸出夾 input 綁定）
    3. scanner.html 含 x-show="dir.readonly"（條件顯示輸出夾列）
    4. state-scan.js 的 push 包含 readonly 與 output_path 屬性（物件形態，非 bare string）
    """

    _ROOT = Path(__file__).parent.parent.parent

    def _scanner_html(self):
        return (self._ROOT / "web" / "templates" / "scanner.html").read_text(encoding="utf-8")

    def _state_scan(self):
        return (self._ROOT / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js").read_text(encoding="utf-8")

    def test_scanner_html_readonly_checkbox(self):
        """scanner.html 含 :checked="dir.readonly"（唯讀 checkbox 綁定）

        TASK-90b-T1: 改為單向 :checked 綁定 + @click.prevent 攔截（經確認 modal
        才真正生效），不再是雙向 x-model（見 TestReadonlyConfirmGuard）。
        """
        html = self._scanner_html()
        assert ':checked="dir.readonly"' in html, \
            'scanner.html 缺 :checked="dir.readonly" — 唯讀 checkbox 未加'

    def test_scanner_html_output_path_input(self):
        """scanner.html 含 x-model="dir.output_path"（輸出夾 input 綁定）"""
        html = self._scanner_html()
        assert 'x-model="dir.output_path"' in html, \
            'scanner.html 缺 x-model="dir.output_path" — 輸出夾 input 未加'

    def test_scanner_html_output_row_xshow(self):
        """scanner.html 含 x-show="dir.readonly && ..."（條件顯示輸出夾列，非 x-if）

        TASK-89a-T2 (CD-89a-7): 輸出夾欄位現在同時依 `dir.readonly` 與全域
        `external_manager` 白名單顯隱（見 TestOutputPathVisibilityGuard），此測試
        只鎖住「用 x-show 而非 x-if、且條件含 dir.readonly」這個較粗的不變量。
        """
        html = self._scanner_html()
        assert 'x-show="dir.readonly &&' in html, \
            'scanner.html 缺 x-show="dir.readonly && ..." — 應用 x-show 而非 x-if 控制輸出夾列'

    def test_state_scan_push_has_readonly(self):
        """state-scan.js 的 directories.push 包含 readonly 屬性（物件形態）"""
        src = self._state_scan()
        assert 'readonly' in src and 'directories.push' in src, \
            "state-scan.js directories.push 缺 readonly 屬性 — 應改為物件 push"
        # 確認不是 bare push(string)：push 之後必須有物件結構 { path: ..., readonly: ...
        assert '{ path:' in src or '{ path :' in src, \
            "state-scan.js directories.push 應推入 {path, readonly, output_path} 物件"

    def test_state_scan_push_has_output_path(self):
        """state-scan.js 的 directories.push 包含 output_path 屬性（物件形態）"""
        src = self._state_scan()
        assert 'output_path' in src, \
            "state-scan.js 缺 output_path 屬性 — push 物件應含 {path, readonly, output_path}"


# [lint-guard: pytest-justified｜rewrite_failed method-block count (CD-96d-5) + {count} value-format lock (CD-96-14)]
class TestRewriteStrmConfirmGuard:
    """TASK-90c-T6: strm 改寫存後鉤 + heads-up confirm modal 結構守衛（element-bound）"""

    def _html(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SETTINGS_CONFIG_JS.read_text(encoding="utf-8")

    def test_config_js_confirm_calls_real_endpoint_and_toast(self):
        """confirmRewriteStrm 呼叫實際端點 + rewrite_done toast（帶 rewritten）。"""
        js = self._js()
        idx = js.find("async confirmRewriteStrm()")
        assert idx != -1, "state-config.js missing async confirmRewriteStrm()"
        # 界定到方法尾（cancelRewriteStrm 起）——涵蓋 success/else/catch 三分支，避免固定字元窗截斷。
        end = js.find("cancelRewriteStrm()", idx)
        block = js[idx:end if end != -1 else idx + 1200]
        assert "'/api/config/rewrite-strm'" in block, \
            "confirmRewriteStrm missing 實際改寫端點呼叫（無 dry_run）"
        assert "settings.scraper.strm_mapping.rewrite_done" in block, \
            "confirmRewriteStrm missing rewrite_done toast i18n key"
        assert "result.rewritten" in block, \
            "confirmRewriteStrm toast 應帶端點回的精確 rewritten 數"
        # Codex P2：改寫失敗（success:false 或 throw）不可靜默——須 error toast，
        # 否則使用者誤以為「改規則即改寫」已發生（新映射已落盤但既有 .strm 未更新）。
        assert block.count("settings.scraper.strm_mapping.rewrite_failed") >= 2, \
            "confirmRewriteStrm 的 success:false 與 catch 兩分支都須發 rewrite_failed error toast"

    def test_zh_tw_json_has_rewrite_keys(self):
        """locales/zh_TW.json 含 rewrite_confirm 節點 + rewrite_done（只驗 zh_TW，無 4-locale parity）。"""
        zh_tw_path = Path(__file__).parent.parent.parent / "locales" / "zh_TW.json"
        data = json.loads(zh_tw_path.read_text(encoding="utf-8"))
        strm = data.get("settings", {}).get("scraper", {}).get("strm_mapping", {})
        confirm = strm.get("rewrite_confirm")
        assert confirm is not None, "zh_TW.json missing settings.scraper.strm_mapping.rewrite_confirm 節點"
        for key in ["title", "body", "cancel", "confirm"]:
            assert key in confirm, f"rewrite_confirm missing key: {key!r}"
        assert "{count}" in confirm["body"], "rewrite_confirm.body 應含 {count} 插值"
        assert "rewrite_done" in strm, "zh_TW.json missing strm_mapping.rewrite_done"
        assert "{count}" in strm["rewrite_done"], "rewrite_done 應含 {count} 插值"
        assert strm.get("rewrite_failed"), "zh_TW.json missing strm_mapping.rewrite_failed（改寫失敗 toast）"

