"""前端靜態守衛 — Settings 掃描來源 Section 3（Metatube 連線狀態機 + Parts Bin）。

61c-4：mixed task 的 frontend-guard 部分。讀 template / state-config.js 做字串斷言，
確保 CD-61-11 兩布林狀態機結構 + flags 就位（sanctioned Alpine-contract guard）。

注意：30-provider 摺疊清單的 runtime render 不爆版屬「手動瀏覽器驗證」（見 TASK card），
pytest 不嘗試斷言 Alpine 執行期渲染。
"""
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
SETTINGS_HTML = _ROOT / "web" / "templates" / "settings.html"
STATE_CONFIG_JS = _ROOT / "web" / "static" / "js" / "pages" / "settings" / "state-config.js"


class TestSection3StateMachineTemplate:
    """settings.html Section 3：三狀態（disabled / idle / connected）結構守衛。"""

    def _html(self):
        return SETTINGS_HTML.read_text(encoding="utf-8")

    def test_section3_wrapper_guarded_by_metatube_enabled(self):
        """disabled：整段 Section 3 由 x-show="metatubeEnabled" 守（B1 hardcoded false → 不渲染）。"""
        html = self._html()
        assert 'class="settings-sources-section3"' in html, \
            "settings.html missing Section 3 wrapper"
        assert 'x-show="metatubeEnabled"' in html, \
            "Section 3 wrapper must be guarded by x-show=\"metatubeEnabled\""

    def test_idle_block_has_connect_form(self):
        """idle：x-show="!metatubeConnected" 連線表單（Server URL + Bearer Token + 連線）。"""
        html = self._html()
        assert 'x-show="!metatubeConnected"' in html, \
            "missing idle block (x-show=\"!metatubeConnected\")"
        assert 'x-model="metatubeServerUrl"' in html, \
            "idle connect form missing Server URL input (x-model=\"metatubeServerUrl\")"
        assert 'x-model="metatubeToken"' in html, \
            "idle connect form missing Bearer Token input (x-model=\"metatubeToken\")"
        assert 'type="password"' in html, \
            "Bearer Token input should be type=password"
        assert '@click="metatubeConnect()"' in html, \
            "idle connect form missing 連線 button (@click=\"metatubeConnect()\")"

    def test_connected_block_has_status_row(self):
        """connected：x-show="metatubeConnected" 連線狀態列（編輯 + 中斷）。"""
        html = self._html()
        assert 'x-show="metatubeConnected"' in html, \
            "missing connected block (x-show=\"metatubeConnected\")"
        assert '@click="metatubeEdit()"' in html, \
            "connected status row missing 編輯 button (@click=\"metatubeEdit()\")"
        assert '@click="metatubeDisconnect()"' in html, \
            "connected status row missing 中斷 button (@click=\"metatubeDisconnect()\")"

    def test_connected_block_has_parts_bin_chevron(self):
        """connected：Parts Bin 摺疊 chevron header（toggle partsBinExpanded）。"""
        html = self._html()
        assert '@click="partsBinExpanded = !partsBinExpanded"' in html, \
            "Parts Bin header missing chevron toggle (@click=\"partsBinExpanded = !partsBinExpanded\")"
        assert 'bi-chevron-right' in html and 'bi-chevron-down' in html, \
            "Parts Bin chevron must toggle between bi-chevron-right / bi-chevron-down"
        assert 'x-show="partsBinExpanded"' in html, \
            "Parts Bin body must be guarded by x-show=\"partsBinExpanded\""

    def test_parts_bin_count_uses_partsBinSources_length(self):
        """Parts Bin「N」count = partsBinSources.length，NOT enabledCount（cap counter）。"""
        html = self._html()
        # 取 Parts Bin count span 區塊（class settings-mt-partsbin-count）做局部斷言
        assert 'class="settings-mt-partsbin-count" x-text="partsBinSources.length"' in html, \
            "Parts Bin count span must bind x-text=\"partsBinSources.length\""
        # count span 不可綁 enabledCount
        assert 'settings-mt-partsbin-count" x-text="enabledCount' not in html, \
            "Parts Bin count must NOT use enabledCount (that's the Active Row cap counter)"

    def test_parts_bin_iterates_partsBinSources(self):
        """connected：Parts Bin pills x-for over partsBinSources + promoteMetatube on click。"""
        html = self._html()
        assert 'partsBinSources.filter(s => s.recommended)' in html, \
            "Parts Bin must group Recommended via partsBinSources.filter(s => s.recommended)"
        assert 'partsBinSources.filter(s => !s.recommended)' in html, \
            "Parts Bin must group Other via partsBinSources.filter(s => !s.recommended)"
        assert '@click="promoteMetatube(src.id)"' in html, \
            "Parts Bin pill click must call promoteMetatube(src.id)"


class TestStateConfigStateMachineFlags:
    """state-config.js：CD-61-11 兩布林狀態機 flags + handlers 宣告守衛。"""

    def _js(self):
        return STATE_CONFIG_JS.read_text(encoding="utf-8")

    def test_state_machine_flags_declared(self):
        """metatubeEnabled / metatubeConnected / partsBinExpanded + connect-form 欄位宣告。"""
        js = self._js()
        for decl in [
            "metatubeEnabled: false",
            "metatubeConnected: false",
            "partsBinExpanded: false",
            "metatubeServerUrl:",
            "metatubeToken:",
        ]:
            assert decl in js, f"state-config.js missing flag declaration: {decl!r}"

    def test_metatube_enabled_stays_false(self):
        """B1：metatubeEnabled hardcoded false（production Section 3 不渲染）。

        [transient-guard] B3 啟用 metatube 連線時會把 metatubeEnabled 翻 true →
        本守衛（含正/負兩條斷言）屆時失效，B3 milestone 刪除。
        """
        js = self._js()
        assert "metatubeEnabled: false" in js, \
            "metatubeEnabled must stay hardcoded false in B1 (do not flip to true)"
        assert "metatubeEnabled: true" not in js, \
            "metatubeEnabled must NOT be set true in production state-config.js (B3 owns the flip)"

    def test_connect_disconnect_handlers_declared(self):
        """metatubeConnect / metatubeDisconnect / metatubeEdit handler 宣告。"""
        js = self._js()
        for handler in ["metatubeConnect(", "metatubeDisconnect(", "metatubeEdit("]:
            assert handler in js, f"state-config.js missing handler: {handler!r}"

    def test_connect_bulk_sets_available(self):
        """available-on-connect（NOTE-A / EC-9）：connect bulk-set available=true 於 metatube source。"""
        js = self._js()
        assert "s.available = true" in js, \
            "metatubeConnect must bulk-set available=true on metatube sources (NOTE-A)"
        assert "s.available = false" in js, \
            "metatubeDisconnect must set available=false on metatube sources (EC-9)"

    def test_mock_provider_fixture_marked_for_removal(self):
        """mock fixture 帶 TODO(B4) 移除標記（CD-61-13）。

        [transient-guard] B4 移除 metatube mock fixture 後本守衛失效，B4 milestone 刪除。
        """
        js = self._js()
        assert "TODO(B4)" in js, \
            "metatube mock provider fixture must carry a // TODO(B4) removal marker (CD-61-13)"


class TestSourcesI18nWiring:
    """61c-6：i18n key 綁定守衛（warn 條走 i18n key、斷線 toast 不硬編碼中文）。"""

    def test_warn_bar_references_warn_all_disabled_key(self):
        """全停用警告條須引用 settings.sources.warn_all_disabled key（非硬編碼文案）。"""
        html = SETTINGS_HTML.read_text(encoding="utf-8")
        assert "settings.sources.warn_all_disabled" in html, \
            "full-disable warning bar must bind t('settings.sources.warn_all_disabled')"

    def test_disconnect_toast_uses_i18n_key_not_hardcoded(self):
        """clickDisconnectedMetatube 須走 window.t()，不得硬編碼中文 toast。"""
        js = STATE_CONFIG_JS.read_text(encoding="utf-8")
        assert "window.t('settings.sources.mt_disconnect_toast')" in js, \
            "clickDisconnectedMetatube must use window.t('settings.sources.mt_disconnect_toast')"
        assert "'Metatube 已中斷" not in js, \
            "clickDisconnectedMetatube must not hardcode the Chinese disconnect toast literal"
