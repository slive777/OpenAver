"""前端契約守衛（KEEP，跨檔 contract）— 由 test_frontend_lint.py 拆出（96c T5，純搬移零行為變更）。

module-level 路徑常數為源檔複製（CD-96c-7：源檔殘留 class 仍引用同名常數，故複製非剪走）。
"""
import re
from pathlib import Path

SETTINGS_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "settings.html"
ZH_TW_JSON = Path(__file__).parent.parent.parent.parent / "locales" / "zh_TW.json"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /home/peace/OpenAver
_OPEN_LOCAL_SHARED = PROJECT_ROOT / "web" / "static" / "js" / "shared" / "open-local.js"
_OPEN_LOCAL_PAGE_FILES = [
    PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "result-card.js",
    PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js",
]
_BOOTSTRAP_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "_advanced_search_bootstrap.html"
_STATE_RESCRAPE_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "shared" / "state-rescrape.js"
_APP_PY = Path(__file__).parent.parent.parent.parent / "web" / "app.py"
_MODAL_HTML_70 = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "_rescrape_modal.html"
_LOCALES_ROOT_70 = Path(__file__).parent.parent.parent.parent / "locales"
STATE_RESCRAPE_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "shared" / "state-rescrape.js"
)


class TestOpenLocalGuard:
    """確認 openLocal() 綁定和 open_folder() API 的結構完整性（T5a / T5b / T4）"""

    def _assert_openlocal_wired(self):
        """兩頁各自 import 且掛載 openLocal（CD-10 假綠防護，見 TASK-103-T4）。

        不可用整檔 substring 找 `openLocal`（模板呼叫、殘留註解都會誤中）；
        掛載檢查用整行 anchor `^\\s*openLocal,\\s*$`，刻意排除 import 那一行
        （其內容不同不會誤中）與任何提及 openLocal 字樣的註解（不會單獨成行）。
        """
        for js_file in _OPEN_LOCAL_PAGE_FILES:
            content = js_file.read_text(encoding='utf-8')
            assert "from '@/shared/open-local.js'" in content, \
                f"{js_file.name} 未 import shared/open-local.js（T4/CD-10）"
            assert re.search(r'^\s*openLocal,\s*$', content, re.MULTILINE), \
                f"{js_file.name} 未掛載 openLocal（缺少 shorthand property 行，T4/CD-10）"

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
        """openLocal(path) 定義於 shared/open-local.js；兩頁各自 import 且掛載（T4/CD-10）"""
        shared_content = _OPEN_LOCAL_SHARED.read_text(encoding='utf-8')
        # 整條宣告式 regex（非裸 substring）：鎖死 `export function openLocal(path) {`。
        # 裸 substring 'openLocal(path)' 會被文件註解裡的同名字面騙過（adversarial mutation
        # 實測：換成 `export const openLocal = (path) => {...}` 這種 this 綁定會炸掉 runtime
        # 的 arrow function，只要留一行提及 openLocal(path) 的註解，裸 substring 版仍全綠）。
        # ^export 開頭排除任何縮排的註解行，強制要求 function 關鍵字（非 arrow）。
        assert re.search(r'^export function openLocal\(path\)\s*\{', shared_content, re.MULTILINE), \
            "shared/open-local.js 缺少 `export function openLocal(path) {` 宣告" \
            "（必須是一般 function，非 arrow function——this 由呼叫端決定）"
        self._assert_openlocal_wired()

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
        """openLocal() 的 .then() 必須檢查 open_folder 回傳值；兩頁各自掛載（T4/CD-10）"""
        shared_content = _OPEN_LOCAL_SHARED.read_text(encoding='utf-8')
        assert '.then(async (opened)' in shared_content, \
            "shared/open-local.js openLocal() 的 .then() 缺少 opened 參數檢查"
        self._assert_openlocal_wired()

    def test_open_local_cross_platform_path(self):
        """openLocal() 必須偵測 Windows drive letter；兩頁各自掛載（T4/CD-10）"""
        shared_content = _OPEN_LOCAL_SHARED.read_text(encoding='utf-8')
        assert 'displayPath' in shared_content, \
            "shared/open-local.js openLocal() 缺少跨平台路徑格式偵測（displayPath）"
        self._assert_openlocal_wired()


class TestJavlibraryPickerT5Guard:
    """70-T5: javlibrary picker BETA 視覺 + 不可用 gate 靜態守衛。

    守衛靜態字串契約（HTML/JS/Python）：
      (1) bootstrap template 含 cf_transport_available 注入
      (2) app.py get_common_context 注入 cf_transport_available
      (3) state-rescrape.js 定義 isJlUnavailable
      (4) _rescrape_modal.html builtin pill 含 source-pill-badge（BETA）綁於 manual_only && is_beta
      (5) _rescrape_modal.html builtin pill 含 isJlUnavailable gate（aria-disabled + jl_desktop_only toast）
      (6) 4 locale 檔含 jl_desktop_only key
    """

    def test_bootstrap_cf_transport_available(self):
        """(1) _advanced_search_bootstrap.html 含 cf_transport_available 注入。"""
        html = _BOOTSTRAP_HTML.read_text(encoding="utf-8")
        assert "cf_transport_available" in html, (
            "70-T5 違規：_advanced_search_bootstrap.html 未注入 cf_transport_available 到 __ADVANCED_SEARCH__"
        )

    def test_app_py_get_common_context_cf_transport(self):
        """(2) web/app.py get_common_context() 注入 cf_transport_available。"""
        src = _APP_PY.read_text(encoding="utf-8")
        assert "cf_transport_available" in src, (
            "70-T5 違規：web/app.py get_common_context() 未包含 cf_transport_available key"
        )
        assert "get_cf_transport" in src, (
            "70-T5 違規：web/app.py 未 import 或呼叫 get_cf_transport（cf_transport_available 值的來源）"
        )

    def test_state_rescrape_has_isJlUnavailable(self):
        """(3) state-rescrape.js 定義 isJlUnavailable helper。"""
        js = _STATE_RESCRAPE_JS.read_text(encoding="utf-8")
        assert "isJlUnavailable" in js, (
            "70-T5 違規：state-rescrape.js 未定義 isJlUnavailable helper"
        )

    def test_modal_builtin_pill_has_beta_badge(self):
        """(4) _rescrape_modal.html builtin pill 模板含 source-pill-badge（BETA badge）。"""
        html = _MODAL_HTML_70.read_text(encoding="utf-8")
        assert "source-pill-badge" in html, (
            "70-T5 違規：_rescrape_modal.html builtin pill 模板缺 source-pill-badge（BETA badge）"
        )
        assert "manual_only" in html and "is_beta" in html, (
            "70-T5 違規：source-pill-badge 未綁於 manual_only && is_beta 條件（不應對所有 pill 顯示）"
        )

    def test_modal_builtin_pill_jl_unavailable_gate(self):
        """(5) _rescrape_modal.html builtin pill 含 isJlUnavailable gate（aria-disabled + jl_desktop_only）。"""
        html = _MODAL_HTML_70.read_text(encoding="utf-8")
        assert "isJlUnavailable" in html, (
            "70-T5 違規：_rescrape_modal.html builtin pill 模板未使用 isJlUnavailable gate"
        )
        assert "aria-disabled" in html, (
            "70-T5 違規：_rescrape_modal.html builtin pill 缺 aria-disabled 綁定（不可用語義）"
        )
        assert "jl_desktop_only" in html, (
            "70-T5 違規：_rescrape_modal.html builtin pill 缺 jl_desktop_only i18n key（toast / title）"
        )

    def test_i18n_jl_desktop_only_parity(self):
        """(6) 4 locale 檔（zh_TW/zh_CN/en/ja）皆含 jl_desktop_only key。"""
        for lang in ("zh_TW", "zh_CN", "en", "ja"):
            locale_path = _LOCALES_ROOT_70 / f"{lang}.json"
            content = locale_path.read_text(encoding="utf-8")
            assert "jl_desktop_only" in content, (
                f"70-T5 違規：locales/{lang}.json 缺 showcase.rescrape.jl_desktop_only key（i18n parity）"
            )


class TestCfPollUnavailableGuard:
    """
    CD-70c-3: C-class API contract guard.

    The frontend _pollCfThenRetry() must consume the backend's
    {unavailable: true} signal by:
      1. Checking data.unavailable in the poll callback
      2. Calling cancelCfPoll() to stop polling and emit the abandon notification

    This is a cross-boundary contract: cf.py response shape × frontend consumption.
    Per CLAUDE.md: "兩個檔案之間的 API contract → pytest (C/E 類)"
    """

    def _js(self) -> str:
        return STATE_RESCRAPE_JS.read_text(encoding="utf-8")

    def test_poll_checks_data_unavailable(self):
        """
        state-rescrape.js _pollCfThenRetry() must check data.unavailable.
        This is the frontend consumer of {ready: false, unavailable: true}
        from /api/cf/status when the transport window is dead.
        """
        js = self._js()
        assert "data.unavailable" in js, (
            "state-rescrape.js _pollCfThenRetry() missing data.unavailable check — "
            "CD-70c-3: frontend must read the backend unavailable signal to stop polling"
        )

    def test_poll_calls_cancel_cf_poll_on_unavailable(self):
        """
        The data.unavailable branch itself must call cancelCfPoll() (not merely
        have cancelCfPoll defined elsewhere in the file). Verify cancelCfPoll
        appears within a tight window right after the data.unavailable check —
        this pins the branch wiring, not just string presence.
        cancelCfPoll() does clearInterval + POST /api/cf/abandon (emits notification).
        """
        js = self._js()
        idx = js.find("data.unavailable")
        assert idx != -1, (
            "state-rescrape.js missing data.unavailable check — "
            "CD-70c-3: frontend must read the backend unavailable signal"
        )
        branch = js[idx: idx + 200]  # the unavailable branch body, right after the check
        assert "cancelCfPoll" in branch, (
            "data.unavailable branch does not call cancelCfPoll() — "
            "CD-70c-3: dead transport must immediately stop the poll loop "
            "(clearInterval + abandon), not fall through to the timeout"
        )

    def test_unavailable_check_present_in_poll_interval(self):
        """
        Both data.unavailable and cancelCfPoll appear in the same file and are
        co-located in the polling context (not just in separate unrelated methods).
        Verify both appear within the _pollCfThenRetry function definition text span.
        """
        js = self._js()
        # Find the function *definition* (not a call site) by searching for the
        # pattern "methodName(" preceded by whitespace/newline (method definition form).
        import re as _re
        # Match the function definition: optional whitespace then _pollCfThenRetry(
        m = _re.search(r'\b_pollCfThenRetry\s*\(', js)
        assert m is not None, f"state-rescrape.js missing _pollCfThenRetry function"
        # Scan from the first match: if it's a call site (short arg like 'number'),
        # try finding the definition via "function body" marker (contains 'setInterval').
        # Use rfind to find the last definition (definitions come after call sites).
        all_matches = list(_re.finditer(r'\b_pollCfThenRetry\s*\(', js))
        # Prefer the match followed by a simple parameter name (definition) over
        # a call expression with 'this.' arguments.  The definition looks like:
        #   _pollCfThenRetry(number) {
        def_idx = None
        for match in all_matches:
            tail = js[match.start(): match.start() + 80]
            # Definition has a plain identifier parameter, not 'this.'
            if _re.match(r'\b_pollCfThenRetry\s*\(\s*\w+\s*\)\s*\{', tail):
                def_idx = match.start()
                break
        assert def_idx is not None, (
            "Could not find _pollCfThenRetry(param) { definition in state-rescrape.js"
        )
        # Extract ~1500 chars from the function start to cover the setInterval body
        snippet = js[def_idx: def_idx + 1500]
        assert "data.unavailable" in snippet, (
            "data.unavailable check not found inside _pollCfThenRetry() definition — "
            "the check must be inside the setInterval callback"
        )
        assert "cancelCfPoll" in snippet, (
            "cancelCfPoll() call not found inside _pollCfThenRetry() definition — "
            "must be called when data.unavailable is true"
        )


class TestSettingsCloseActionSelect:
    """Guards for the closeAction select row in settings.html (feature/82 T4)."""

    SETTINGS_HTML = (
        Path(__file__).parents[3] / "web" / "templates" / "settings.html"
    )
    ZH_TW_JSON = Path(__file__).parents[3] / "locales" / "zh_TW.json"
    SETTINGS_JS = (
        Path(__file__).parents[3]
        / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"
    )

    def _settings_html(self) -> str:
        return self.SETTINGS_HTML.read_text(encoding="utf-8")

    def _zh_tw(self) -> dict:
        import json
        return json.loads(self.ZH_TW_JSON.read_text(encoding="utf-8"))

    def test_close_action_select_inside_jinja_gate(self):
        """#closeAction select element must be inside {% if is_windows_desktop %} … {% endif %}."""
        import re
        content = self._settings_html()

        # Extract all {% if is_windows_desktop %} ... {% endif %} blocks
        gate_pattern = re.compile(
            r'\{%-?\s*if\s+is_windows_desktop\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}',
            re.DOTALL,
        )
        gates = gate_pattern.findall(content)
        assert gates, "No {% if is_windows_desktop %} block found in settings.html"

        # closeAction select must appear inside at least one gate block
        found_in_gate = any('id="closeAction"' in block for block in gates)
        assert found_in_gate, (
            '#closeAction select must be inside {% if is_windows_desktop %} block, '
            'not outside the gate'
        )

    def test_close_action_select_not_outside_gate(self):
        """#closeAction select must NOT appear outside the is_windows_desktop gate."""
        import re
        content = self._settings_html()

        # Remove all gated blocks
        gate_pattern = re.compile(
            r'\{%-?\s*if\s+is_windows_desktop\s*-?%\}.*?\{%-?\s*endif\s*-?%\}',
            re.DOTALL,
        )
        stripped = gate_pattern.sub('', content)
        assert 'id="closeAction"' not in stripped, (
            '#closeAction found outside {% if is_windows_desktop %} block — '
            'non-desktop clients would receive the DOM element'
        )

    def test_close_action_select_has_x_model(self):
        """The #closeAction select must have x-model='form.closeAction'."""
        import re
        content = self._settings_html()

        # Find the select tag with id="closeAction"
        m = re.search(r'<select\b[^>]*\bid="closeAction"[^>]*>', content, re.DOTALL)
        assert m, 'select#closeAction not found in settings.html'
        tag = m.group(0)
        assert 'x-model="form.closeAction"' in tag, (
            f'select#closeAction missing x-model="form.closeAction": {tag!r}'
        )

    def test_close_action_select_has_three_option_values(self):
        """The #closeAction select must have options for ask, tray, and exit."""
        import re
        content = self._settings_html()

        # Find the block from id="closeAction" up to closing </select>
        m = re.search(
            r'<select\b[^>]*\bid="closeAction"[^>]*>.*?</select>',
            content, re.DOTALL,
        )
        assert m, 'select#closeAction not found in settings.html'
        block = m.group(0)

        for val in ("ask", "tray", "exit"):
            assert f'value="{val}"' in block, (
                f'select#closeAction missing option value="{val}": {block!r}'
            )

    def test_close_action_select_has_i18n_keys(self):
        """Each option in the #closeAction select uses a t('settings.system.close_action_*') key."""
        import re
        content = self._settings_html()

        m = re.search(
            r'<select\b[^>]*\bid="closeAction"[^>]*>.*?</select>',
            content, re.DOTALL,
        )
        assert m, 'select#closeAction not found in settings.html'
        block = m.group(0)

        for key in ("settings.system.close_action_ask",
                    "settings.system.close_action_tray",
                    "settings.system.close_action_exit"):
            assert key in block, (
                f'select#closeAction missing i18n key {key!r} in option text'
            )

    def test_zh_tw_has_close_action_label_key(self):
        """zh_TW.json must contain settings.system.close_action_label."""
        data = self._zh_tw()
        system = data.get("settings", {}).get("system", {})
        assert "close_action_label" in system, (
            "zh_TW.json missing settings.system.close_action_label"
        )
        assert system["close_action_label"] == "關閉視窗時"

    def test_zh_tw_has_close_action_option_keys(self):
        """zh_TW.json must contain all 3 close_action option keys."""
        data = self._zh_tw()
        system = data.get("settings", {}).get("system", {})
        expected = {
            "close_action_ask": "每次詢問",
            "close_action_tray": "最小化到系統匣",
            "close_action_exit": "直接結束",
        }
        for key, value in expected.items():
            assert key in system, f"zh_TW.json missing settings.system.{key}"
            assert system[key] == value, (
                f"settings.system.{key} value mismatch: "
                f"expected {value!r}, got {system[key]!r}"
            )


class TestHelpUpdateButtonGuard:
    """84-T3: Help 頁「更新」按鈕 + confirm modal 靜態守衛

    契約：
    1. {% if is_desktop %} gate 存在於 help.html（按鈕被正確 gate）
    2. 「更新」按鈕的 @click="triggerUpdate()" 存在於 gate 內
    3. triggerUpdate() DOM binding 不應出現在 gate 外
    4. help.js 定義 triggerUpdate function
    5. modal 的 x-show="showUpdateModal" binding 存在
    6. modal 內含 confirm / cancel 按鈕
    """

    HELP_HTML = PROJECT_ROOT / "web" / "templates" / "help.html"
    HELP_JS   = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "help.js"

    def _html(self):
        return self.HELP_HTML.read_text(encoding="utf-8")

    def _js(self):
        return self.HELP_JS.read_text(encoding="utf-8")

    def test_is_desktop_gate_exists_in_help_html(self):
        """help.html 含 {% if is_desktop %} gate（確保按鈕被正確 gate）"""
        html = self._html()
        assert '{% if is_desktop %}' in html, \
            "help.html 缺 {% if is_desktop %} gate — 更新按鈕必須在此 gate 內"

    def test_trigger_update_click_inside_desktop_gate(self):
        """@click="triggerUpdate()" 必須在 {% if is_desktop %} block 內"""
        import re
        html = self._html()
        gate_pattern = re.compile(
            r'\{%-?\s*if\s+is_desktop\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}',
            re.DOTALL,
        )
        gates = gate_pattern.findall(html)
        assert gates, "help.html: 找不到 {% if is_desktop %} block"
        found = any('triggerUpdate()' in block for block in gates)
        assert found, (
            '@click="triggerUpdate()" 必須在 {% if is_desktop %} block 內 '
            '（非桌面客戶端不應看到此按鈕）'
        )

    def test_trigger_update_not_outside_gate(self):
        """triggerUpdate() DOM binding 不應出現在 {% if is_desktop %} gate 外"""
        import re
        html = self._html()
        gate_pattern = re.compile(
            r'\{%-?\s*if\s+is_desktop\s*-?%\}.*?\{%-?\s*endif\s*-?%\}',
            re.DOTALL,
        )
        stripped = gate_pattern.sub('', html)
        assert 'triggerUpdate()' not in stripped, (
            'triggerUpdate() 出現在 {% if is_desktop %} gate 外 — '
            '非桌面情境不應渲染此 DOM'
        )

    def test_trigger_update_defined_in_help_js(self):
        """help.js 定義 triggerUpdate function（防函數遺漏導致 Alpine 報錯）"""
        js = self._js()
        assert 'triggerUpdate' in js, \
            "help.js 缺 triggerUpdate 定義 — Alpine @click 呼叫的函數不存在"

    def test_update_modal_x_show_binding_exists(self):
        """modal 含 x-show="showUpdateModal" binding（防按鈕存在但 modal 永不出現）"""
        html = self._html()
        assert 'showUpdateModal' in html, \
            "help.html 缺 showUpdateModal binding — update confirm modal 無法顯示"

    def test_update_modal_has_confirm_and_cancel(self):
        """modal 內含 confirmUpdate() 和 cancelUpdate() 呼叫（confirm/cancel 按鈕齊全）"""
        html = self._html()
        assert 'confirmUpdate()' in html, \
            "help.html 缺 confirmUpdate() — modal 確認按鈕不存在"
        assert 'cancelUpdate()' in html, \
            "help.html 缺 cancelUpdate() — modal 取消按鈕不存在"

