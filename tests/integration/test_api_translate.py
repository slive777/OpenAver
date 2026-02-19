"""
翻譯 API 日文跳過邏輯測試
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from web.app import app


client = TestClient(app)


class TestTranslateSkipNonJapanese:
    """測試 /api/translate 跳過非日文"""

    @patch("web.routers.translate.load_config")
    def test_skip_chinese_only(self, mock_config):
        """純中文應被跳過"""
        mock_config.return_value = {"translate": {"enabled": True}}

        response = client.post("/api/translate", json={
            "text": "中文標題沒有日文",
            "mode": "translate"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("skipped") is True
        assert data.get("success") is True  # 新增：驗證 success 欄位
        assert data.get("reason") == "no_japanese"
        assert data.get("original") == "中文標題沒有日文"

    @patch("web.routers.translate.load_config")
    def test_skip_english_only(self, mock_config):
        """純英文應被跳過"""
        mock_config.return_value = {"translate": {"enabled": True}}

        response = client.post("/api/translate", json={
            "text": "English Title Only",
            "mode": "translate"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("skipped") is True
        assert data.get("success") is True  # 新增
        assert data.get("reason") == "no_japanese"

    @patch("web.routers.translate.load_config")
    def test_not_skip_optimize_mode(self, mock_config):
        """optimize 模式不應跳過"""
        mock_config.return_value = {"translate": {"enabled": True, "ollama": {"url": "http://localhost:11434", "model": "test"}}}

        # optimize 模式應該繼續執行（雖然可能失敗因為沒有 Ollama）
        response = client.post("/api/translate", json={
            "text": "中文標題",
            "mode": "optimize"
        })
        # 不應返回 skipped
        data = response.json()
        assert data.get("skipped") is not True


class TestTranslateBatchSkip:
    """測試 /api/translate-batch 過濾非日文"""

    @patch("web.routers.translate.get_translate_service")
    @patch("web.routers.translate.load_config")
    def test_batch_skip_non_japanese(self, mock_config, mock_service):
        """批次翻譯應跳過非日文標題"""
        mock_config.return_value = {"translate": {"enabled": True, "batch_size": 10}}

        # Mock translate service
        mock_translate = AsyncMock()
        mock_translate.translate_batch = AsyncMock(return_value=["翻譯結果"])
        mock_service.return_value = mock_translate

        response = client.post("/api/translate-batch", json={
            "titles": [
                "これはテスト",     # 日文，應翻譯
                "中文標題",          # 中文，應跳過
                "English Title"      # 英文，應跳過
            ]
        })
        assert response.status_code == 200
        data = response.json()

        # 應該只翻譯 1 個日文標題
        assert data["skipped"] == 2  # 2 個非日文
        assert data["translations"][1] == "中文標題"  # 保持原文
        assert data["translations"][2] == "English Title"  # 保持原文

    @patch("web.routers.translate.get_translate_service")
    @patch("web.routers.translate.load_config")
    def test_batch_all_non_japanese(self, mock_config, mock_service):
        """全部非日文時不呼叫翻譯服務"""
        mock_config.return_value = {"translate": {"enabled": True, "batch_size": 10}}

        mock_translate = AsyncMock()
        mock_translate.translate_batch = AsyncMock(return_value=[])
        mock_service.return_value = mock_translate

        response = client.post("/api/translate-batch", json={
            "titles": ["中文1", "中文2", "English"]
        })
        assert response.status_code == 200
        data = response.json()

        assert data["skipped"] == 3
        assert data["translations"] == ["中文1", "中文2", "English"]
        # translate_batch 不應被呼叫
        mock_translate.translate_batch.assert_not_called()


class TestTranslateDisabled:
    """測試翻譯功能關閉時的回應"""

    @patch("web.routers.translate.load_config")
    def test_translate_disabled_returns_error(self, mock_config):
        """translate.enabled = False 時應回傳 success=False 且含錯誤訊息"""
        mock_config.return_value = {"translate": {"enabled": False}}
        response = client.post("/api/translate", json={
            "text": "テスト", "mode": "translate"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "翻譯功能未啟用" in data["error"]
