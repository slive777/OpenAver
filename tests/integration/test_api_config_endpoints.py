import pytest
import os
import json
from pathlib import Path
from fastapi.testclient import TestClient
from web.app import app

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


class TestFullConfigSavePreservesServerMode:
    """P2-1: PUT /api/config（全量儲存）不得改寫 server_mode（toggle-lifecycle 所有權）

    Divergence path（confirmed):
      PUT /api/config accepts AppConfig body → Pydantic model_validates the incoming
      general section.  If the payload's general.server_mode is False (Pydantic default
      when the key is absent) or explicitly False, the old save_config() call would write
      that value over a persisted True — leaving the LAN listener running but
      general.server_mode=false in config.json (diverged).

    Fix: update_config() now runs mutate_config(_write_preserving_server_mode) which
    reads the currently-persisted server_mode under the write lock and forces it into the
    payload before writing, regardless of what the incoming body says.
    """

    @pytest.fixture
    def mock_config_path_with_server_mode_true(self, tmp_path, monkeypatch):
        """Config pre-seeded with general.server_mode=true (listener "running")."""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {
                "locale": "zh-TW",
                "theme": "light",
                "sidebar_collapsed": False,
                "tutorial_completed": False,
                "font_size": "md",
                "default_page": "search",
                "server_mode": True,  # persisted True — listener is "running"
            },
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "thumbnail_cache_enabled": False,
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_full_save_omitting_server_mode_preserves_true(
        self, client, mock_config_path_with_server_mode_true
    ):
        """PUT /api/config whose general body OMITS server_mode must NOT reset it to False.

        Simulates the frontend saveConfig() behaviour: it sends a full AppConfig body but
        the general section only sets known form fields (default_page, theme) and does NOT
        include server_mode.  The Pydantic default for missing server_mode is False —
        without the preservation guard this would silently overwrite the persisted True
        and diverge from lan_listener.is_running (still True).
        """
        config_path = mock_config_path_with_server_mode_true

        # Build a minimal valid AppConfig payload.  general.server_mode is deliberately
        # absent — Pydantic will default it to False.
        payload = {
            "general": {
                "default_page": "search",
                "theme": "dark",
                # server_mode intentionally omitted → Pydantic default False
            },
            "scraper": {},
            "search": {},
            "source_links": {},
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "gallery": {},
            "showcase": {},
            "sources": [],
            "thumbnail_cache_enabled": False,
            "metatube": {},
        }

        resp = client.put("/api/config", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        saved = json.loads(config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True, (
            "PUT /api/config must preserve the persisted server_mode=true; "
            "omitting the field in the payload must not reset it to False "
            "(would diverge from running LAN listener)"
        )

    def test_full_save_explicit_false_server_mode_still_preserves_true(
        self, client, mock_config_path_with_server_mode_true
    ):
        """PUT /api/config with general.server_mode=false in the body must also be ignored.

        A stale GET → full PUT round-trip from an old client (or any direct API call)
        that explicitly sends server_mode=false must NOT overwrite the persisted True.
        Only PUT /api/config/general/server_mode (the toggle endpoint) is allowed to
        change this field.
        """
        config_path = mock_config_path_with_server_mode_true

        payload = {
            "general": {
                "default_page": "search",
                "theme": "light",
                "server_mode": False,  # stale / incorrect — must be ignored
            },
            "scraper": {},
            "search": {},
            "source_links": {},
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "gallery": {},
            "showcase": {},
            "sources": [],
            "thumbnail_cache_enabled": False,
            "metatube": {},
        }

        resp = client.put("/api/config", json=payload)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        saved = json.loads(config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True, (
            "PUT /api/config with explicit server_mode=false in the body must be "
            "ignored — server_mode is owned by the toggle lifecycle endpoint only"
        )


class TestDeleteConfigStopsLanListener:
    """P2-4: DELETE /api/config (reset) は LAN listener を停止しなければならない

    reset_config_file() は server_mode を含む config を削除する → defaults では
    server_mode が存在しない（= false）。しかし listener は停止しないと
    runtime（listener 起動中）≠ persisted（server_mode absent）が分離し、
    0.0.0.0 socket が 403 を返し続けてしまう。
    """

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """DELETE /api/config 用 fixture — lan_listener.stop() も mock する"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {"general": {"server_mode": True}}
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_delete_config_calls_lan_listener_stop(self, client, mock_config_path, monkeypatch):
        """DELETE /api/config → lan_listener.stop() は必ず 1 回呼ばれる

        reset は server_mode を消去する（defaults = false）ため、listener の
        runtime↔persisted を一致させるために stop() を呼ぶ必要がある。
        stop() は idempotent なので listener が起動していなくても安全。
        """
        stop_called = []

        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop",
            lambda *a, **k: stop_called.append(True),
        )

        resp = client.delete("/api/config")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(stop_called) == 1, (
            "DELETE /api/config must call lan_listener.stop() once to keep "
            "runtime↔persisted consistent after config reset clears server_mode"
        )

    def test_delete_config_stop_called_even_when_not_running(
        self, client, mock_config_path, monkeypatch
    ):
        """stop() は idempotent なので listener が起動していなくても呼ばれてよい

        stop() の no-op 保証により、listener が実行中かどうかに関わらず
        reset ハンドラは stop() を呼び出す（毎回呼ぶ方が明確で安全）。
        """
        stop_called = []

        # Simulate listener already not running — stop() is still called (idempotent no-op)
        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop",
            lambda *a, **k: stop_called.append(True),
        )

        resp = client.delete("/api/config")

        assert resp.status_code == 200
        assert len(stop_called) == 1, "stop() must always be called on reset (idempotent)"
