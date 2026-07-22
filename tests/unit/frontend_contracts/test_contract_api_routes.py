"""前端契約守衛（KEEP，跨檔 contract）— 由 test_frontend_lint.py 拆出（96c T5，純搬移零行為變更）。

module-level 路徑常數為源檔複製（CD-96c-7：源檔殘留 class 仍引用同名常數，故複製非剪走）。
"""
import json
import re
from pathlib import Path

SEARCH_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "search.html"
SHOWCASE_BASE_JS     = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
SHOWCASE_VIDEOS_JS   = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js"
SHOWCASE_ACTRESS_JS  = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-actress.js"
SHOWCASE_LIGHTBOX_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
SETTINGS_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "settings.html"
SCANNER_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "scanner.html"
SCANNER_SCAN_JS  = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "scanner" / "state-scan.js"
SETTINGS_CONFIG_JS    = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
MAIN_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "main.js"
LOCALES_ROOT = Path(__file__).parent.parent.parent.parent / "locales"
RESULT_CARD_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js"
PATH_UTILS_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "components" / "path-utils.js"
FILE_LIST_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "file-list.js"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /home/peace/OpenAver
SETTINGS_CSS            = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "pages" / "settings.css"
STATE_RESCRAPE_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "shared" / "state-rescrape.js"
)


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
        # [lint-guard: pytest-justified] tags+「+」按鈕的 file-mode 閘是跨檔 Alpine binding
        # contract（search.html 引用 canEditFile()，定義在 base.js）——非單純字串存在檢查，
        # static_guard_lint 無法表達跨檔語意；canEditFile 的 file+path 邏輯另由 node:test 守。
        html = self._html()
        for expected in [
            # 106-T1 CD-106-1/AC12：tags+ 的 file-mode/path 閘從 inline 三 conjunct
            # (listMode==='file' && fileList[currentFileIndex]?.path) 收斂進 canEditFile()
            # computed（base.js）；canEditFile 的 file+path 語意由 can-edit-file.test.mjs
            # node:test 守。此處守 tags+「+」按鈕仍走 file-mode 閘（!addingTag 保留避免加標籤時重複）。
            "!addingTag && canEditFile()",
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


class TestEditModeCanEditFileGuard:
    """PR#115 Codex P2: editingX 單獨判斷會讓 file 模式殘留的編輯 flag 洩漏進 keyword/advanced
    唯讀模式（例如 file 模式開始編輯後又跑關鍵字搜尋，不經 T5 的 navigate/switchToFile reset）。
    修法：edit div 一律加 `&& canEditFile()`、display div 加 `!(editingX && canEditFile())`
    互補閘，確保 display/edit 恆有且僅有一個可見。
    """

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def test_search_html_edit_divs_gated_by_can_edit_file(self):
        """search.html 三個編輯欄位（標題／中文標題／演員）的編輯 div 皆以 canEditFile() 為
        exact-complement 閘（非單純字串存在檢查——這是「editingX flag 與 file-mode 閘的
        AND 語意」跨檔 Alpine binding contract，canEditFile() 定義在 base.js，
        static_guard_lint 無法表達此語意）。
        """
        # [lint-guard: pytest-justified] 同 TestUserTagsApiGuard.test_search_html_contains 理由：
        # canEditFile() 定義於 base.js、search.html 引用之，是跨檔 Alpine binding contract，
        # 不是單純字串存在檢查，static_guard_lint 無法表達此跨檔語意。
        html = self._html()
        for expected in [
            "editingTitle && canEditFile()",
            "editingChineseTitle && canEditFile()",
            "editingActors && canEditFile()",
        ]:
            assert expected in html, f"search.html missing: {expected!r}"


class TestDateGatingGuard:
    """TASK-106-T7: 發售日欄位特例——唯讀 span 與原生 date picker 的互補閘。
    唯讀 span 顯示 = 不可編輯 或 已有日期；picker 顯示 = file 模式 且 無日期。
    兩閘引用 canEditFile()（定義於 base.js），是跨檔 Alpine binding contract，
    非單純字串存在檢查，static_guard_lint 無法表達此跨檔語意。
    """

    def _html(self):
        return SEARCH_HTML.read_text(encoding="utf-8")

    def test_search_html_date_span_and_picker_complementary_gating(self):
        """search.html date info-cell 的唯讀 span 與 date picker gating 為互補閘：
        span `x-show="!canEditFile() || current().date"`（不可編輯或已有日期都唯讀），
        picker `x-show="canEditFile() && !current().date"`（file 模式且無日期才出日曆）。
        """
        # [lint-guard: pytest-justified] 同 TestEditModeCanEditFileGuard 理由：
        # canEditFile() 定義於 base.js、search.html 引用之，是跨檔 Alpine binding contract，
        # 不是單純字串存在檢查，static_guard_lint 無法表達此跨檔語意。
        # 另 Codex PR#116 P1：picker 為單一持久 DOM 節點（x-show 只切 display），
        # 需 `:value="current().date || ''"` 反應性重設 DOM .value，防切候選殘留上一候選日期
        # （T7 型「拔 :value 造成殘值→畫面有日期但 model 空」回歸）。
        html = self._html()
        for expected in [
            "!canEditFile() || current().date",
            "canEditFile() && !current().date",
            ":value=\"current().date || ''\"",
        ]:
            assert expected in html, f"search.html missing: {expected!r}"

    def test_search_html_date_input_wired_to_identity_guarded_methods(self):
        """Codex PR#116 P2: date picker 是四個可編輯欄位中唯一原本沒有 stale-candidate 身分
        守衛的——@change 直寫 `current().date = ...` 在事件當下才 re-resolve current()，若打開
        日曆到選好日期之間候選被換掉（背景批次/換源/切檔）會把日期寫進錯的候選。

        鎖定 date input 必須改走 result-card.js 的 startEditDate()/confirmEditDate()（與
        title/chineseTitle/actors 同源 identity-guard pattern），防未來改回直寫 current().date
        的回歸。這是 search.html ↔ result-card.js 的跨檔 Alpine binding contract（方法是否被
        定義、guard 邏輯是否正確由對應的 .mjs 單元測試覆蓋），非單純字串存在檢查，
        static_guard_lint 無法表達此跨檔語意。
        """
        # [lint-guard: pytest-justified] 同 class docstring 理由：canEditFile() 系列已在本
        # class 建立先例——跨檔 Alpine binding contract 用 pytest 鎖，不是前端靜態字串存在檢查。
        html = self._html()
        for expected in [
            '@focus="startEditDate()"',
            '@change="confirmEditDate($event.target.value)"',
        ]:
            assert expected in html, f"search.html missing: {expected!r}"
        assert "current().date = $event.target.value" not in html, (
            "date input 不應退回直寫 current().date（繞過身分守衛，見 Codex PR#116 P2）"
        )


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


class TestRescrapeStateGuard:
    """62a-3: 守衛 state-rescrape.js mixin contract — 確保 partial（_rescrape_modal.html）引用的
    state/method 全揭露、commit 契約（enrich-single + refresh_full + overwrite_existing）正確、
    transient 不碰 currentLightboxVideo（CD-62-2），且 main.js mergeState 鏈整合。
    match TestSimilarStageGuard L1164 pattern。
    """

    SHARED_DIR = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "shared"
    SHOWCASE_DIR = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase"
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
        """74c-T3（翻轉）：longPressReset?.() 呼叫已隨長壓基礎設施退役移除；state-rescrape.js 不得再含此呼叫。"""
        src = self._src()
        assert "longPressReset" not in src, \
            "74c-T3 違規：closeRescrape 仍含 longPressReset（長壓基礎設施已退役，此呼叫應移除）"

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


class TestServerModeToggleGuard:
    """80a-T3: settings.html + state-config.js server-mode toggle/banner 靜態守衛。

    每個 assertion 都是 mutation-sensitive：刪除對應實作即 RED。
    使用 BeautifulSoup DOM 解析（attribute 順序無關）+ substring 雙重策略，
    鏡照既有 settings 守衛慣例（SETTINGS_HTML / SETTINGS_CONFIG_JS path 常數）。
    """

    def _html(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def _js(self):
        return SETTINGS_CONFIG_JS.read_text(encoding="utf-8")

    # ── HTML guards ────────────────────────────────────────────────────────────

    def test_settings_root_has_data_lan_ip(self):
        """#settings-components root div 含 data-lan-ip 屬性（傳 lanIp 到 Alpine）。
        移除此屬性 → lanIp 永遠空字串，URL 顯示錯誤。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._html(), "html.parser")
        root = soup.find(id="settings-components")
        assert root is not None, "settings.html 找不到 #settings-components"
        assert root.has_attr("data-lan-ip"), \
            "#settings-components 缺少 data-lan-ip 屬性（80a-T3 lanIp 傳入點）"

    def test_settings_server_mode_segmented_in_header(self):
        """.settings-server-mode 在標題左 cluster（.settings-header-left）內，是 <h4> 的
        cluster-sibling，且含 .settings-sources-segmented + 2 個 button
        （requestServerModeChange(false)/requestServerModeChange(true)，T4 改為確認 modal）。

        81b-T1（CD-1）：膠囊從 .settings-header-actions 搬到 .settings-header-left。
        mutation：膠囊搬回 .settings-header-actions → 「不在 actions」斷言 RED；
        刪 .settings-header-left wrapper → 「在 header-left」斷言 RED。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._html(), "html.parser")
        wrapper = soup.find(class_="settings-server-mode")
        assert wrapper is not None, \
            "settings.html 缺少 .settings-server-mode wrapper（80a-T3 膠囊容器）"
        segmented = wrapper.find(class_="settings-sources-segmented")
        assert segmented is not None, \
            ".settings-server-mode 缺少 .settings-sources-segmented（pill 複用）"
        buttons = segmented.find_all("button")
        assert len(buttons) == 2, \
            f".settings-sources-segmented 應有 2 個 button，實際 {len(buttons)} 個"
        click_attrs = [b.get("@click", "") for b in buttons]
        assert any("requestServerModeChange(false)" in a for a in click_attrs), \
            "segmented 缺少 @click=\"requestServerModeChange(false)\" button（單機態）"
        assert any("requestServerModeChange(true)" in a for a in click_attrs), \
            "segmented 缺少 @click=\"requestServerModeChange(true)\" button（伺服器態）"
        # 81b-T1（CD-1）：位置斷言 — 膠囊在標題左 cluster，h4 sibling，搬離 actions
        left = soup.find(class_="settings-header-left")
        assert left is not None, \
            "settings.html 缺少 .settings-header-left（81b-T1 標題左 cluster wrapper）"
        assert left.find(class_="settings-server-mode") is not None, \
            ".settings-server-mode 不在 .settings-header-left 內（CD-1 膠囊應在標題左 cluster）"
        assert left.find("h4") is not None, \
            "<h4> 不在 .settings-header-left 內（膠囊應與 h4 同 cluster）"
        actions = soup.find(class_="settings-header-actions")
        assert actions is None or actions.find(class_="settings-server-mode") is None, \
            ".settings-server-mode 仍在 .settings-header-actions 內（CD-1 應已搬離至標題左 cluster）"

    def test_settings_server_info_banner_xshow_xcloak(self):
        """恰好一個 .settings-server-inline 元素，帶 x-show=\"serverMode\" 和 x-cloak（防 FOUC）。
        移除 x-cloak → Alpine boot 前裸閃；移除 x-show → 區塊恆顯。
        81b-T1：原獨立第二排 .settings-server-info 收進 header 同排 .settings-server-inline。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._html(), "html.parser")
        banners = soup.find_all(class_="settings-server-inline")
        assert len(banners) == 1, \
            f"settings.html .settings-server-inline 應恰好 1 個，實際 {len(banners)} 個"
        banner = banners[0]
        assert banner.get("x-show") == "serverMode", \
            f".settings-server-inline x-show 應為 'serverMode'，實際: {banner.get('x-show')!r}"
        assert banner.has_attr("x-cloak"), \
            ".settings-server-inline 缺少 x-cloak（Alpine boot 前會 FOUC）"

    def test_settings_server_info_warning_key(self):
        """橫條內含 settings.server_info.warning i18n key 引用（警語行）。
        移除此 key → 警語靜默，用戶不知安全風險。"""
        html = self._html()
        assert "settings.server_info.warning" in html, \
            "settings.html 缺少 settings.server_info.warning i18n key 引用（警語行）"

    def test_settings_server_info_copy_button(self):
        """橫條內含 copyServerUrl() 呼叫（複製鈕 @click）。
        移除 → 複製功能斷掉，用戶無法複製 URL。"""
        html = self._html()
        assert "copyServerUrl()" in html, \
            "settings.html 缺少 copyServerUrl() 呼叫（複製鈕 @click）"

    def test_settings_server_copy_is_clipboard_icon_with_aria(self):
        """copy 鈕為 icon-only（內含 <i class="bi bi-clipboard">）+ a11y 標籤
        （:aria-label 與 :title 皆引用 settings.server_info.copy）。

        81b-T1（CD-4 + #8）：copy 由文字「複製」改 bi-clipboard icon-only，
        i18n key 轉作 aria-label/title 提供無障礙標籤。
        mutation：把 <i class="bi bi-clipboard"> 換回文字 → icon 斷言 RED；
        移除 :aria-label 或改引用別 key → a11y 斷言 RED。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._html(), "html.parser")
        btn = soup.find(class_="settings-server-copy-btn")
        assert btn is not None, \
            "settings.html 缺少 .settings-server-copy-btn（81b-T1 複製鈕）"
        assert btn.find("i", class_="bi-clipboard") is not None, \
            ".settings-server-copy-btn 缺少 <i class=\"bi bi-clipboard\"> icon（CD-4 icon-only）"
        aria = btn.get(":aria-label") or btn.get("aria-label")
        assert aria is not None and "settings.server_info.copy" in aria, \
            f"copy 鈕 aria-label 應引用 settings.server_info.copy，實際: {aria!r}（#8 a11y 標籤）"
        title = btn.get(":title") or btn.get("title")
        assert title is not None and "settings.server_info.copy" in title, \
            f"copy 鈕 title 應引用 settings.server_info.copy，實際: {title!r}（CD-4 hover 提示）"

    def test_settings_amber_active_scoped_to_server_mode(self):
        """琥珀 active（[data-mode="server"].is-on）規則 scope 緊收到
        .settings-server-mode 且 body 用 --color-warning。

        81b-T2（CD-6）：琥珀只套 server 膠囊，不可外溢到來源卡膠囊。
        mutation：把任一條琥珀 server 規則的 scope 從 .settings-server-mode 拿掉
        （污染來源卡）→ 該條成「未 scope 的琥珀規則」→ RED；改用非 --color-warning 顏色
        → 找不到琥珀規則 → RED。

        關鍵（teeth）：不是「存在一條有 scope 的規則就放行」（base + dim 兩條，拔一條
        另一條仍在會假綠），而是「**每一條** [data-mode=\"server\"].is-on 琥珀規則都必須
        scope 在 .settings-server-mode」——即不存在任何未 scope 的琥珀 server 規則。
        先剝 /* ... */ 註解，防註解內 .settings-server-mode 字面混入 selector 比對。"""
        css = SETTINGS_CSS.read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
        # 列舉所有 `selector { body }` 規則塊（巢狀無關，settings.css 為扁平規則）
        amber_rules = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            selector, body = m.group(1), m.group(2)
            if '[data-mode="server"]' in selector and ".is-on" in selector \
                    and "--color-warning" in body:
                amber_rules.append(selector.strip())
        assert amber_rules, \
            "settings.css 缺少 [data-mode=\"server\"].is-on + --color-warning 的琥珀 active 規則（CD-6）"
        # 每一條琥珀 server 規則都必須 scope 在 .settings-server-mode（無任一條外溢）
        unscoped = [s for s in amber_rules if ".settings-server-mode" not in s]
        assert not unscoped, \
            f"琥珀 active 規則未全部 scope 在 .settings-server-mode（CD-6 防外溢來源卡）: {unscoped!r}"

    def test_no_clipboard_emoji_in_copy_context(self):
        """web/ 下所有 .html/.js/.css 不得出現 📋 字面（含 design-system <pre> 範例字串）。

        81b-T4：複製鈕統一 bi-clipboard icon，移除所有 📋 emoji。
        純字串 in-content 掃描（非 bs4 text-only），確保 escaped <pre> 範例也掃到。
        eslint/stylelint 不掃 .html 模板，故 pytest 字串掃描是正確路由。
        mutation：任何人把 📋 寫回任一複製鈕（含教學範例）→ RED。"""
        web_root = Path(__file__).parent.parent.parent.parent / "web"
        offenders = []
        for ext in ("*.html", "*.js", "*.css"):
            for f in web_root.rglob(ext):
                if "\U0001F4CB" in f.read_text(encoding="utf-8"):
                    offenders.append(str(f.relative_to(web_root)))
        assert not offenders, \
            f"web/ 下仍殘留 📋 emoji（應統一用 bi-clipboard icon）: {offenders}"

    def test_settings_server_info_no_lan_ip_key(self):
        """橫條含 settings.server_info.no_lan_ip i18n key（lanIp 為空時提示）。
        移除 → lanIp=None 時橫條空白，用戶看不到說明。"""
        html = self._html()
        assert "settings.server_info.no_lan_ip" in html, \
            "settings.html 缺少 settings.server_info.no_lan_ip i18n key（lanIp 空白提示）"

    def test_settings_server_info_distinguishes_listener_down_from_no_ip(self):
        """Codex P2：banner 須區分「listener 未啟動」(lanIp 在但 lanPort 缺) 與「取不到 IP」。
        listener_down 分支須 lanIp-gated（`!serverUrl() && lanIp`），no_lan_ip 須 `!serverUrl() && !lanIp`。
        若兩者合併回單一 `!serverUrl()` → autostart 失敗時誤顯「取不到 IP」誤導排查 → 此測 RED。"""
        html = self._html()
        assert "settings.server_info.listener_down" in html, \
            "settings.html 缺少 settings.server_info.listener_down（listener 未啟動的專屬訊息）"
        assert 'x-if="!serverUrl() && lanIp"' in html, \
            "listener_down 分支須 gate 在 '!serverUrl() && lanIp'（lanIp 在但無 port）"
        # Codex P2：抓不到 IP 但 port 已知 → 顯示帶 port 的訊息（用戶才湊得出 IP:port）；
        # 連 port 都沒有才用純 no_lan_ip。兩支須各自 lanPort-gated。
        assert "settings.server_info.no_lan_ip_with_port" in html, \
            "settings.html 缺少 no_lan_ip_with_port（IP 抓不到但 lanPort 已知時顯示 port）"
        assert 'x-if="!serverUrl() && !lanIp && lanPort"' in html, \
            "no_lan_ip_with_port 分支須 gate 在 '!serverUrl() && !lanIp && lanPort'"
        assert 'x-if="!serverUrl() && !lanIp && !lanPort"' in html, \
            "no_lan_ip 分支須 gate 在 '!serverUrl() && !lanIp && !lanPort'（連 port 都沒有）"

    # ── JS guards ──────────────────────────────────────────────────────────────

    def test_state_config_server_mode_put_endpoint(self):
        """state-config.js 含 PUT /api/config/general/server_mode endpoint。
        移除或改路徑 → 後端收不到，config 不持久。"""
        js = self._js()
        assert "/api/config/general/server_mode" in js, \
            "state-config.js 缺少 '/api/config/general/server_mode' PUT endpoint"

    def test_state_config_server_url_uses_lan_port(self):
        """serverUrl() 使用後端提供的 this.lanPort（非 window.location.port）。
        T6c 起 dual-listener 後 LAN port ≠ 桌面 local_port，必須用後端回傳值。
        回退至 window.location.port → 遠端裝置連到桌面 port 不是 LAN port。"""
        js = self._js()
        assert "this.lanPort" in js, \
            "state-config.js serverUrl() 缺少 this.lanPort（80a-T6c：用後端 lan_port）"
        assert "window.location.port" not in js, \
            "state-config.js serverUrl() 不應再使用 window.location.port（已改用 lanPort）"

    def test_state_config_lan_port_state_exists(self):
        """state 含 lanPort: null（80a-T6c 新增 state，reload 後補 GET lan-port）。
        移除 → serverUrl() 永遠 null，URL 橫條不顯示。"""
        js = self._js()
        assert "lanPort: null" in js, \
            "state-config.js 缺少 'lanPort: null' state（80a-T6c）"

    def test_state_config_set_server_mode_reads_lan_port(self):
        """setServerMode() 成功分支讀 result.lan_port（後端回傳 LAN port）。
        移除 → 切換成功後 lanPort 不更新，URL 橫條顯示舊值或 null。"""
        js = self._js()
        assert "result.lan_port" in js, \
            "state-config.js setServerMode() 缺少 'result.lan_port'（80a-T6c：讀後端 lan_port）"

    def test_state_config_set_server_mode_reads_lan_ip(self):
        """setServerMode() 成功分支讀 result.lan_ip 並更新 this.lanIp。
        移除 → 切換成功後 lanIp 不更新，serverUrl() 用舊值（或空字串 → null URL）。"""
        js = self._js()
        assert "result.lan_ip" in js, \
            "state-config.js setServerMode() 缺少 'result.lan_ip'（gated get_lan_ip：由後端 toggle 回應提供）"
        assert "this.lanIp = result.lan_ip" in js, \
            "state-config.js setServerMode() 缺少 'this.lanIp = result.lan_ip'（lanIp 未從 toggle 回應更新）"

    def test_state_config_load_config_fetches_lan_port(self):
        """loadConfig() serverMode=true 時 GET /api/config/general/lan-port 補 lanPort。
        移除 → reload 後 lanPort=null，URL 橫條消失（需重新 toggle 才恢復）。"""
        js = self._js()
        assert "/api/config/general/lan-port" in js, \
            "state-config.js loadConfig() 缺少 '/api/config/general/lan-port' GET（80a-T6c）"

    def test_state_config_load_config_reads_lan_ip_from_lan_port_endpoint(self):
        """loadConfig() GET lan-port 分支讀 j.lan_ip 並更新 this.lanIp。
        移除 → reload 後 lanIp 不更新（gated context：server_mode=true 時頁面 lan_ip 已空）。"""
        js = self._js()
        assert "j.lan_ip" in js, \
            "state-config.js loadConfig() 缺少 'j.lan_ip'（lan-port GET 須同步更新 lanIp）"
        assert "this.lanIp = j.lan_ip" in js, \
            "state-config.js loadConfig() 缺少 'this.lanIp = j.lan_ip'（lanIp 未從 lan-port 回應更新）"

    def test_state_config_reads_server_mode_with_nullish_coalesce(self):
        """loadConfig() 用 ?? false 讀 config.general?.server_mode（CD#3 慣例）。
        改成 || false → false 值會被吞（語意等同但守慣例）。"""
        js = self._js()
        assert "config.general?.server_mode ?? false" in js, \
            "state-config.js loadConfig() 缺少 'config.general?.server_mode ?? false'"

    def test_state_config_set_server_mode_failure_direction_aware(self):
        """setServerMode() 失敗分支使用方向感知 toast（val ? toggle_failed : disable_failed）。

        移除三元表達式或合併成同一 key：
          - enable 失敗顯示「無法啟動」✓，disable 失敗仍顯「無法啟動」✗（語意錯誤）。
        兩個 key 都必須存在，且須以 `val ?` ternary 選擇（mutation-sensitive）。
        """
        js = self._js()
        assert "settings.server_info.disable_failed" in js, (
            "state-config.js setServerMode() 失敗分支缺少 'settings.server_info.disable_failed'（80b：方向感知 toast）"
        )
        assert "settings.server_info.toggle_failed" in js, (
            "state-config.js setServerMode() 失敗分支應保留 'settings.server_info.toggle_failed'（enable 失敗路徑）"
        )
        # Ternary pattern: val ? 'toggle_failed' : 'disable_failed'（或反序帶 ! 亦合法，
        # 但實作固定 val ? toggle_failed : disable_failed，故字串比對足以 mutation-catch）
        assert "val ? 'settings.server_info.toggle_failed' : 'settings.server_info.disable_failed'" in js, (
            "state-config.js setServerMode() 失敗分支須以 ternary 按 val 選擇 key（80b：方向感知）"
        )
        # 遠端被拒（loopback 守衛）須給專屬 remote_only 訊息，而非通用「請稍後再試」
        assert "remote_forbidden" in js and "settings.server_info.remote_only" in js, (
            "state-config.js setServerMode() 失敗分支須對 reason==='remote_forbidden' 顯示 "
            "'settings.server_info.remote_only'（遠端切換給專屬訊息，非『請稍後再試』）"
        )

    def test_state_config_set_server_mode_sends_boolean(self):
        """setServerMode() body: JSON.stringify({ value: !!val })，確保送 boolean 不送 string。
        T1 嚴格 bool gate，送字串會 400。"""
        js = self._js()
        assert "value: !!val" in js, \
            "state-config.js setServerMode() 缺少 'value: !!val'（必須送 boolean，不可送字串）"

    def test_set_server_mode_lan_ip_nullish_uses_null_not_stale(self):
        """P2-2: setServerMode() enable 成功分支用 `result.lan_ip ?? null`，不用 `?? this.lanIp`。
        用 `?? this.lanIp` → 後端返 null（IP 偵測失敗）時 banner 仍顯示舊 IP，指向失效 URL。
        必須用 `?? null` 讓 serverUrl() 返 null，正確顯示 no_lan_ip/listener_down 提示。"""
        js = self._js()
        assert "result.lan_ip ?? null" in js, (
            "state-config.js setServerMode() 須用 'result.lan_ip ?? null'（P2-2）；"
            "不可用 '?? this.lanIp'（保留舊 IP 會在 IP 偵測失敗時顯示死連結）"
        )
        assert "result.lan_ip ?? this.lanIp" not in js, (
            "state-config.js setServerMode() 不得用 'result.lan_ip ?? this.lanIp'（P2-2 stale IP bug）"
        )

    def test_load_config_lan_ip_nullish_uses_null_not_stale(self):
        """P2-2: loadConfig() GET lan-port 分支用 `j.lan_ip ?? null`，不用 `?? this.lanIp`。
        用 `?? this.lanIp` → 重載後 lan_ip=null（偵測失敗）時 banner 仍顯示舊 IP。
        必須用 `?? null` 讓 serverUrl() 返 null 觸發正確的 no_lan_ip 提示路徑。"""
        js = self._js()
        assert "j.lan_ip ?? null" in js, (
            "state-config.js loadConfig() 須用 'j.lan_ip ?? null'（P2-2）；"
            "不可用 '?? this.lanIp'（保留舊 IP 會在 IP 偵測失敗時顯示死連結）"
        )
        assert "j.lan_ip ?? this.lanIp" not in js, (
            "state-config.js loadConfig() 不得用 'j.lan_ip ?? this.lanIp'（P2-2 stale IP bug）"
        )


class TestScannerClearCache:
    """清除快取守衛 — scanner 頁面必要元素"""

    def test_scanner_clear_cache_js_contains(self):
        """scanner/state-scan.js 含 clearCache() + DELETE /api/gallery/cache"""
        js = (PROJECT_ROOT / 'web/static/js/pages/scanner/state-scan.js').read_text(encoding='utf-8')
        for expected in ['clearCache()', '/api/gallery/cache', 'DELETE']:
            assert expected in js, f"scanner/state-scan.js missing: {expected!r}"


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
        """T3(40c) / T-d4 / 72d-codexP2: 觸發列 x-show 用正向白名單 gate（fail-closed，含 kodi）"""
        from bs4 import BeautifulSoup
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        # There are multiple nfo-update-row divs; the jellyfin trigger row is the one
        # whose x-show references jellyfinImageVisible (not nfoUpdateVisible etc.)
        rows = soup.find_all("div", class_="nfo-update-row")
        jellyfin_row = next(
            (r for r in rows if "jellyfinImageVisible" in r.get("x-show", "") and "config" in r.get("x-show", "")),
            None
        )
        assert jellyfin_row is not None, \
            "scanner.html 找不到含 jellyfinImageVisible + config 的 nfo-update-row element"
        xshow = jellyfin_row.get("x-show", "")
        # 正向白名單（fail-closed）：config={} / undefined 時 gate 為 false，不顯示
        assert "['jellyfin', 'emby', 'kodi'].includes(config?.scraper?.external_manager)" in xshow, \
            f"nfo-update-row x-show 應使用正向白名單 .includes() gate（fail-closed），實際: {xshow!r}"
        assert "!jellyfinImageVisible" in xshow, \
            f"nfo-update-row x-show 應含 !jellyfinImageVisible，實際: {xshow!r}"
        # forbidden：舊 jellyfin_emby gate 與 interim !='off'（fail-open）皆不得殘留
        assert "=== 'jellyfin_emby'" not in html, \
            "scanner.html 仍殘留舊 === 'jellyfin_emby' gate"
        assert "config?.scraper?.external_manager !== 'off' && !jellyfinImageVisible" not in html, \
            "scanner.html 觸發列仍用 interim !== 'off' gate（undefined 會 fail-open，須改正向白名單）"
        assert "config?.scraper?.jellyfin_mode && !jellyfinImageVisible" not in html, \
            "scanner.html 觸發列 x-show 仍使用舊的 jellyfin_mode 讀取點（應已 repoint 為 external_manager）"

    def test_check_jellyfin_method_gate_is_fail_closed(self):
        """72d-codexP2: checkJellyfinImages() 方法端 gate 用正向白名單，config 未載入時 fail-closed 不打 API"""
        js = self._js()
        assert "async checkJellyfinImages()" in js, "state-scan.js 找不到 checkJellyfinImages() 方法"
        # 正向白名單 early-return（fail-closed）；此字串為該 gate 獨有
        assert "!['jellyfin', 'emby', 'kodi'].includes(this.config?.scraper?.external_manager)" in js, \
            "checkJellyfinImages() 應以正向白名單 early-return（fail-closed），不可用 === 'off'（undefined fail-open）"
        # forbidden：舊 fail-open gate（undefined === 'off' 為 false → 不 return → 打 /jellyfin-check）
        assert "this.config?.scraper?.external_manager === 'off'" not in js, \
            "state-scan.js 仍殘留 external_manager === 'off' gate（undefined 會 fail-open）"

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

