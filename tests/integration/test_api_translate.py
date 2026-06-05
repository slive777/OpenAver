"""
翻譯 API 日文跳過邏輯測試
"""
import threading

import httpx
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

    @patch("web.routers.translate.httpx.AsyncClient")
    @patch("web.routers.translate.load_config")
    def test_not_skip_optimize_mode(self, mock_config, mock_async_client):
        """optimize 模式不應跳過"""
        mock_config.return_value = {"translate": {"enabled": True, "ollama": {"url": "http://localhost:11434", "model": "test"}}}

        # Mock 掉 Ollama HTTP 呼叫，立即拋 ConnectError，避免空等 60 秒 timeout。
        # 本測試只驗「optimize 模式不被 skip」，不在意翻譯實際結果。
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("no ollama"))
        mock_async_client.return_value.__aenter__.return_value = mock_client

        response = client.post("/api/translate", json={
            "text": "中文標題",
            "mode": "optimize"
        })
        # 不應返回 skipped（即使後端因無 Ollama 而失敗，也不能是 skipped）
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


class TestTranslateServiceSingletonLock:
    """CD-66b-5：translate service 單例 cold-start init 鎖（double-checked locking）"""

    def test_concurrent_cold_start_inits_once(self):
        """並發 cold-start：create_translate_service 只被呼叫一次、兩執行緒拿同一物件。

        確定性（非靠時序碰運氣）：
        - 兩執行緒先各自 barrier.wait() 在 Barrier(2) 會合，被同時釋放後
          才呼叫 get_translate_service()，保證兩者「同時」進入 fast-path 的
          `is None` 區域。
        - barrier 放在 get 呼叫「之前」（不放在 create 內），因為有鎖時只有
          一個執行緒會進 create，若把 Barrier(2) 放 create 內第二方永不到達
          → 死鎖。
        - 有鎖時：先進臨界區的執行緒 init，第二個阻塞於鎖，取得鎖後 re-check
          見非 None → 跳過 create。故 create 只被呼叫一次。
        """
        from web.routers import translate as translate_mod

        translate_mod._translate_service = None
        try:
            barrier = threading.Barrier(2)
            sentinel = object()  # create 的唯一回傳值（單例）

            def fake_create(translate_config, locale):
                return sentinel

            mock_create = patch(
                "web.routers.translate.create_translate_service",
                side_effect=fake_create,
            )
            mock_load = patch(
                "web.routers.translate.load_config",
                return_value={"translate": {}, "general": {"locale": "zh-TW"}},
            )

            results = {}

            def worker(idx):
                barrier.wait()  # 兩執行緒在此會合，同時被釋放
                results[idx] = translate_mod.get_translate_service()

            with mock_load, mock_create as m_create:
                t0 = threading.Thread(target=worker, args=(0,))
                t1 = threading.Thread(target=worker, args=(1,))
                t0.start()
                t1.start()
                t0.join(timeout=5)
                t1.join(timeout=5)

                assert not t0.is_alive() and not t1.is_alive(), "執行緒未在時限內結束（疑似死鎖）"
                # 鎖讓 init 只發生一次
                assert m_create.call_count == 1
                # 兩執行緒拿到同一單例物件
                assert results[0] is sentinel
                assert results[1] is sentinel
                assert results[0] is results[1]
        finally:
            translate_mod._translate_service = None

    def test_reset_under_lock(self):
        """reset_translate_service 在鎖內把單例設回 None。"""
        from web.routers import translate as translate_mod

        try:
            translate_mod._translate_service = object()
            translate_mod.reset_translate_service()
            assert translate_mod._translate_service is None
        finally:
            translate_mod._translate_service = None
