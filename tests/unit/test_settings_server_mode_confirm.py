"""T4: 伺服器模式切換確認彈窗守衛"""
from pathlib import Path
import json


class TestServerModeConfirm:

    def _read_settings_html(self):
        return Path("web/templates/settings.html").read_text()

    def _read_state_ui(self):
        return Path("web/static/js/pages/settings/state-ui.js").read_text()

    def _read_state_config(self):
        return Path("web/static/js/pages/settings/state-config.js").read_text()

    def _read_zh_tw(self):
        return Path("locales/zh_TW.json").read_text()

    def test_button_click_uses_request_server_mode_change(self):
        """settings.html 按鈕必須改用 requestServerModeChange（不再直接 setServerMode）"""
        content = self._read_settings_html()
        assert "requestServerModeChange(false)" in content
        assert "requestServerModeChange(true)" in content

    def test_modal_exists_in_settings_html(self):
        """settings.html 必須有 serverModeConfirmOpen modal"""
        content = self._read_settings_html()
        assert "serverModeConfirmOpen" in content

    def test_modal_has_confirm_and_cancel_buttons(self):
        """modal 必須有 confirmServerModeChange 和 cancelServerModeChange 兩個 handler"""
        content = self._read_settings_html()
        assert "confirmServerModeChange()" in content
        assert "cancelServerModeChange()" in content

    def test_i18n_keys_in_zh_tw(self):
        """zh_TW.json 必須有 server_mode_confirm 完整 key 組（含 on 變體）"""
        data = json.loads(self._read_zh_tw())
        block = data["settings"]["server_mode_confirm"]
        for key in ("title", "title_on", "body_on", "body_off", "confirm", "confirm_on"):
            assert key in block, f"missing key: {key}"

    def test_modal_title_is_conditional_x_text(self):
        """title 必須透過 x-text 條件渲染（on/off 各自有 key）"""
        content = self._read_settings_html()
        assert "server_mode_confirm.title_on" in content
        assert "server_mode_confirm.title'" in content

    def test_modal_confirm_button_is_conditional_x_text(self):
        """confirm 按鈕必須透過 x-text 條件渲染（on/off 各自有 key）"""
        content = self._read_settings_html()
        assert "server_mode_confirm.confirm_on" in content
        assert "server_mode_confirm.confirm'" in content

    def test_state_ui_has_confirm_state(self):
        """state-ui.js 必須有 serverModeConfirmOpen 和 serverModeConfirmValue"""
        content = self._read_state_ui()
        assert "serverModeConfirmOpen" in content
        assert "serverModeConfirmValue" in content

    def test_state_config_has_three_methods(self):
        """state-config.js 必須有三個 confirm 相關方法"""
        content = self._read_state_config()
        assert "requestServerModeChange" in content
        assert "confirmServerModeChange" in content
        assert "cancelServerModeChange" in content
