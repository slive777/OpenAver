"""
TASK-80a-T6b: server_mode toggle 端點 + GET lan-port 整合測試

涵蓋：
  - PUT server_mode=true 成功 → start mock 回 lan_port，config 持久化 true
  - PUT server_mode=true 失敗（start 拋例外）→ {success:false}，config 不寫 true
  - PUT server_mode=false → stop mock，config 持久化 false，lan_port null
  - PUT server_mode 非 bool 字串 → 400（T1 回歸守衛）
  - GET /api/config/general/lan-port running → {lan_port: 49200}
  - GET /api/config/general/lan-port stopped → {lan_port: null}

Mock 策略：monkeypatch lan_listener singleton 的方法 / 屬性，避免真實 uvicorn 啟動。
Style：mirror test_api_config_endpoints.py（client fixture + mock_config_path fixture）。
"""
import json
import pytest
from fastapi.testclient import TestClient
from web.app import app


class TestServerModeToggleAPI:
    """PUT /api/config/general/server_mode 端點 + GET lan-port（TASK-80a-T6b）"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH，初始化含 general 的 config（server_mode 預設 false）"""
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
                "server_mode": False,
            },
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_toggle_true_returns_lan_port(self, client, mock_config_path, monkeypatch):
        """PUT server_mode true（start mock → 49200）→ 200 {success:true, lan_port:49200}"""
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)

        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["lan_port"] == 49200

    def test_toggle_true_persists_server_mode(self, client, mock_config_path, monkeypatch):
        """PUT server_mode true 成功後 config.json server_mode 寫入 true"""
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)

        client.put("/api/config/general/server_mode", json={"value": True})

        saved = json.loads(mock_config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True

    def test_toggle_true_start_failure_not_persisted(self, client, mock_config_path, monkeypatch):
        """start() 拋 RuntimeError → {success:false, error:...}，config 不寫 true"""
        def _fail_start(*a, **k):
            raise RuntimeError("port occupied")

        monkeypatch.setattr("web.lan_listener.lan_listener.start", _fail_start)

        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "error" in data

        saved = json.loads(mock_config_path.read_text())
        # server_mode must NOT be persisted as true on start failure
        assert saved.get("general", {}).get("server_mode") is not True

    def test_toggle_false_returns_null_port(self, client, mock_config_path, monkeypatch):
        """PUT server_mode false → stop mock，{success:true, lan_port:null}"""
        stop_called = []

        def _mock_stop(*a, **k):
            stop_called.append(True)

        monkeypatch.setattr("web.lan_listener.lan_listener.stop", _mock_stop)

        resp = client.put("/api/config/general/server_mode", json={"value": False})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["lan_port"] is None
        assert stop_called, "stop() should have been called"

    def test_toggle_false_persists_server_mode_false(self, client, mock_config_path, monkeypatch):
        """PUT server_mode false → config.json server_mode 寫入 false"""
        monkeypatch.setattr("web.lan_listener.lan_listener.stop", lambda *a, **k: None)

        client.put("/api/config/general/server_mode", json={"value": False})

        saved = json.loads(mock_config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is False

    def test_toggle_non_bool_still_400(self, client, mock_config_path):
        """PUT server_mode {value: "true"} (字串) → 400（T1 回歸守衛）"""
        resp = client.put("/api/config/general/server_mode", json={"value": "true"})

        assert resp.status_code == 400

    def test_get_lan_port_running(self, client, mock_config_path, monkeypatch):
        """GET lan-port，listener is_running=True, lan_port=49200 → {lan_port: 49200}"""
        import web.lan_listener as _ll_mod

        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "is_running", property(lambda self: True))
        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "lan_port", property(lambda self: 49200))

        resp = client.get("/api/config/general/lan-port")

        assert resp.status_code == 200
        assert resp.json() == {"lan_port": 49200}

    def test_get_lan_port_stopped(self, client, mock_config_path, monkeypatch):
        """GET lan-port，listener is_running=False → {lan_port: null}"""
        import web.lan_listener as _ll_mod

        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "is_running", property(lambda self: False))
        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "lan_port", property(lambda self: None))

        resp = client.get("/api/config/general/lan-port")

        assert resp.status_code == 200
        assert resp.json() == {"lan_port": None}
