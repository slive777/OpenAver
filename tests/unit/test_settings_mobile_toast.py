"""T3: Settings 頁行動版 toast 底部定位守衛"""
from pathlib import Path


class TestSettingsMobileToast:
    def _read_settings_css(self):
        return Path("web/static/css/pages/settings.css").read_text()

    def test_mobile_toast_media_query_exists(self):
        """settings.css 必須有 max-width: 480px media query"""
        content = self._read_settings_css()
        assert "max-width: 480px" in content

    def test_mobile_toast_targets_toast_top(self):
        """media query 必須針對 .toast.toast-top"""
        content = self._read_settings_css()
        assert ".toast.toast-top" in content

    def test_mobile_toast_sets_bottom(self):
        """media query 必須設定 bottom 屬性"""
        content = self._read_settings_css()
        assert "bottom" in content

    def test_mobile_toast_inside_media_query(self):
        """bottom 設定必須在 @media 區塊內（桌面不受影響）"""
        content = self._read_settings_css()
        media_idx = content.find("@media (max-width: 480px)")
        bottom_idx = content.find("bottom", media_idx)
        assert media_idx != -1 and bottom_idx > media_idx
