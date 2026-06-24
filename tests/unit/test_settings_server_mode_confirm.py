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
        """settings.html 按鈕必須改用 requestServerModeChange（不再直接 setServerMode）
        [transient-guard] setServerMode 直呼叫遷移至 requestServerModeChange，milestone 前刪除負向 assert。
        """
        content = self._read_settings_html()
        assert "requestServerModeChange(false)" in content
        assert "requestServerModeChange(true)" in content
        assert "@click=\"setServerMode(false)\"" not in content
        assert "@click=\"setServerMode(true)\"" not in content

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
        """zh_TW.json 必須有 settings.server_mode_confirm 區塊"""
        content = self._read_zh_tw()
        assert "server_mode_confirm" in content

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
