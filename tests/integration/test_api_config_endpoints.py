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
