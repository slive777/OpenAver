import pytest
import os
import json
from pathlib import Path

class TestConfigAPI:
    """測試 web/routers/config.py 的 API 端點"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH 和 CONFIG_DEFAULT_PATH 避免影響真實設定檔"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        
        # 建立預設設定檔作為基底
        default_data = {
            "general": {"tutorial_completed": False}
        }
        default_path.write_text(json.dumps(default_data))
        
        # Mock module variables（core.config は load_config/save_config が参照する実体）
        # web.routers.config は _core_config.CONFIG_PATH で動態参照するため、
        # core.config.CONFIG_PATH を差し替えるだけで DELETE /api/config も正しく動く
        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        
        # Mock reset_translate_service dependency to do nothing
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        
        return config_path

    def test_delete_config_success(self, client, mock_config_path):
        """測試成功刪除 config.json (恢復原廠設定)"""
        # 手動建立 config_path
        mock_config_path.write_text('{"some": "data"}')
        assert mock_config_path.exists()
        
        response = client.delete("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "恢復預設" in data["message"]
        assert not mock_config_path.exists()

    def test_delete_config_not_exists(self, client, mock_config_path):
        """測試當 config.json 不存在時呼叫刪除，不應出錯"""
        if mock_config_path.exists():
            mock_config_path.unlink()
            
        response = client.delete("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # 不會報錯，一樣回傳成功

    def test_tutorial_flow(self, client, mock_config_path):
        """測試 tutorial 相關的一系列流程"""
        # 1. 初始化狀態應該是 False
        resp = client.get("/api/tutorial-status")
        assert resp.status_code == 200
        assert resp.json()["completed"] is False
        
        # 2. 標記完成
        resp = client.post("/api/tutorial-completed")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        
        # 再次檢查狀態
        resp = client.get("/api/tutorial-status")
        assert resp.json()["completed"] is True
        
        # 確保檔案真的寫入了 config.json
        assert mock_config_path.exists()
        saved_config = json.loads(mock_config_path.read_text())
        assert saved_config.get("general", {}).get("tutorial_completed") is True
        
        # 3. 重置狀態
        resp = client.post("/api/tutorial-reset")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        
        # 第三次檢查狀態
        resp = client.get("/api/tutorial-status")
        assert resp.json()["completed"] is False
        
        saved_config = json.loads(mock_config_path.read_text())
        assert saved_config.get("general", {}).get("tutorial_completed") is False


class TestLocaleChangeResetsTranslateService:
    """locale 變更應觸發 translate service reset（auto 模式依賴 locale）"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH，初始化含 general.locale 的 config"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
            "translate": {"enabled": False, "provider": "ollama",
                          "batch_size": 10,
                          "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                          "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"}},
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)

        return config_path

    def test_locale_change_calls_reset_translate_service(self, client, mock_config_path, monkeypatch):
        """PUT /api/config/general/locale 成功後呼叫 _reset_translate_service()"""
        reset_called = []

        def fake_reset():
            reset_called.append(True)

        monkeypatch.setattr("web.routers.config._reset_translate_service", fake_reset)

        resp = client.put("/api/config/general/locale", json={"value": "en"})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(reset_called) == 1, "locale 變更後應呼叫一次 _reset_translate_service()"

    def test_other_field_change_does_not_call_reset(self, client, mock_config_path, monkeypatch):
        """PUT /api/config/general/theme 不應呼叫 _reset_translate_service()"""
        reset_called = []

        def fake_reset():
            reset_called.append(True)

        monkeypatch.setattr("web.routers.config._reset_translate_service", fake_reset)

        resp = client.put("/api/config/general/theme", json={"value": "dark"})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(reset_called) == 0, "theme 變更不應呼叫 _reset_translate_service()"

    def test_invalid_locale_does_not_call_reset(self, client, mock_config_path, monkeypatch):
        """不支援的 locale 失敗後不應呼叫 _reset_translate_service()"""
        reset_called = []

        def fake_reset():
            reset_called.append(True)

        monkeypatch.setattr("web.routers.config._reset_translate_service", fake_reset)

        resp = client.put("/api/config/general/locale", json={"value": "ko"})

        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert len(reset_called) == 0, "失敗的 locale 設定不應呼叫 reset"


class TestServerModeEndpoint:
    """PUT /api/config/general/server_mode 端點測試（TASK-80a-T1）"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH，初始化含 general 的 config。
        同時 mock lan_listener.start/stop 避免真實 uvicorn 啟動（T6b 起 server_mode true
        觸發 lan_listener.start()，測試環境未 wire → 需 mock）。"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        # T6b: server_mode toggle 呼叫 lan_listener.start()/stop() — mock 避免真實啟動
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)
        monkeypatch.setattr("web.lan_listener.lan_listener.stop", lambda *a, **k: None)

        return config_path

    def test_server_mode_true_returns_200_success(self, client, mock_config_path):
        """PUT server_mode {value: true} → 200 {"success": True}"""
        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_server_mode_true_persisted(self, client, mock_config_path):
        """PUT server_mode {value: true} → config.json 寫入 general.server_mode=True"""
        client.put("/api/config/general/server_mode", json={"value": True})

        saved = json.loads(mock_config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True

    def test_server_mode_reload_yields_true(self, client, mock_config_path, monkeypatch):
        """PUT server_mode true → 持久化後重讀 load_config() 仍為 True（AC-A8）"""
        import core.config as cc
        client.put("/api/config/general/server_mode", json={"value": True})

        reloaded = cc.load_config()
        assert reloaded.get("general", {}).get("server_mode") is True

    def test_server_mode_string_true_returns_400(self, client, mock_config_path):
        """PUT server_mode {value: "true"} (字串) → HTTP 400（gate 擋字串）"""
        resp = client.put("/api/config/general/server_mode", json={"value": "true"})

        assert resp.status_code == 400

    def test_server_mode_string_false_returns_400_not_stored(self, client, mock_config_path):
        """安全性關鍵：字串 "false" 是 truthy，必須 400 且不得寫入 config
        （否則 middleware bool("false")=True 會誤開對外）。"""
        resp = client.put("/api/config/general/server_mode", json={"value": "false"})

        assert resp.status_code == 400
        saved = json.loads(mock_config_path.read_text())
        assert "server_mode" not in saved.get("general", {})

    def test_server_mode_int_one_rejected(self, client, mock_config_path):
        """PUT server_mode {value: 1} (int) → 被拒（StrictBool|StrictStr schema 層擋整數 → 422）"""
        resp = client.put("/api/config/general/server_mode", json={"value": 1})

        assert resp.status_code == 422
        saved = json.loads(mock_config_path.read_text())
        assert "server_mode" not in saved.get("general", {})

    def test_theme_string_still_200_regression(self, client, mock_config_path):
        """PUT theme {value: "dark"} 字串路徑不受影響 → 仍 200 success（不回歸）"""
        resp = client.put("/api/config/general/theme", json={"value": "dark"})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
