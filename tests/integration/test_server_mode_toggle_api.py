"""
TASK-80a-T6b: server_mode toggle 端點 + GET lan-port 整合測試

涵蓋：
  - PUT server_mode=true 成功 → start mock 回 lan_port，config 持久化 true，回傳 lan_ip
  - PUT server_mode=true 失敗（start 拋例外）→ {success:false}，config 不寫 true
  - PUT server_mode=false → stop mock，config 持久化 false，lan_port null
  - PUT server_mode 非 bool 字串 → 400（T1 回歸守衛）
  - GET /api/config/general/lan-port running → {lan_port: 49200, lan_ip: "192.168.1.50"}
  - GET /api/config/general/lan-port stopped → {lan_port: null, lan_ip: null}

Mock 策略：monkeypatch lan_listener singleton 的方法 / 屬性，避免真實 uvicorn 啟動。
          monkeypatch web.lan_listener.get_lan_ip 回固定值供 deterministic 斷言。
Style：mirror test_api_config_endpoints.py（client fixture + mock_config_path fixture）。
"""
import json
import pytest
from fastapi.testclient import TestClient
from web.app import app


@pytest.fixture(autouse=True)
def _isolate_access_auth(tmp_path, monkeypatch):
    """本檔多支測試會先把 config 的 server_mode 設成 true、再用遠端 IP 發請求，
    於是抵達 `access_gate` middleware 的冷啟動 `ensure_schema()`
    （`web/app.py:327`）—— 未隔離前那會連上 `output/openaver.db`。

    ⚠️ 本檔在 127b-T4 的前幾輪**看起來是乾淨的**：`report` 模式只報了
    `test_remote_cannot_enable_server_mode` 一支，因為它先把 `_snapshot` 暖好，
    後面同路徑的 `test_remote_cannot_disable_server_mode` 就再也不碰 DB 了。
    ⇒ **整檔一次掃完，不要只修 report 當下列出的那一支。**

    形狀比照 `tests/integration/test_capabilities_auth.py` 的 `auth_db` fixture。
    """
    import core.access_auth as access_auth

    monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access.db")
    access_auth.ensure_schema()
    access_auth.reset_state_for_tests()
    yield
    access_auth.reset_state_for_tests()


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
        """PUT server_mode true（start mock → 49200）→ 200 {success:true, lan_port:49200, lan_ip:"192.168.1.50"}"""
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)
        monkeypatch.setattr("web.lan_listener.get_lan_ip", lambda: "192.168.1.50")

        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["lan_port"] == 49200
        assert data["lan_ip"] == "192.168.1.50"

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
        """GET lan-port，listener is_running=True, lan_port=49200 → {lan_port: 49200, lan_ip: "192.168.1.50"}"""
        import web.lan_listener as _ll_mod

        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "is_running", property(lambda self: True))
        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "lan_port", property(lambda self: 49200))
        monkeypatch.setattr(_ll_mod, "get_lan_ip", lambda: "192.168.1.50")

        resp = client.get("/api/config/general/lan-port")

        assert resp.status_code == 200
        data = resp.json()
        assert data["lan_port"] == 49200
        assert data["lan_ip"] == "192.168.1.50"

    @pytest.mark.parametrize("env_name", ["OPENAVER_SYNOLOGY", "OPENAVER_SERVER_ONLY"])
    def test_get_lan_port_synology_uses_request_server_port(self, client, mock_config_path, monkeypatch, env_name):
        """Synology／Linux 伺服器版回傳此請求的主服務埠，不受停止中的 LAN listener 影響。"""
        import web.lan_listener as _ll_mod

        monkeypatch.setenv(env_name, "1")
        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "is_running", property(lambda self: False))
        monkeypatch.setattr(_ll_mod.lan_listener.__class__, "lan_port", property(lambda self: None))
        monkeypatch.setattr(_ll_mod, "get_lan_ip", lambda: "192.168.1.50")

        resp = client.get("/api/config/general/lan-port")

        assert resp.status_code == 200
        data = resp.json()
        assert data["lan_port"] == 80
        assert data["lan_ip"] == "192.168.1.50"
        assert data["public_exposure"] is False


    # ── P1 rollback / persist-first 修復守衛 ───────────────────────────────────

    def test_toggle_true_persist_failure_rolls_back_listener(
        self, client, mock_config_path, monkeypatch
    ):
        """start() 成功但 mutate_config 拋例外 → response success False，
        lan_listener.stop() 被呼叫（rollback），config 不寫 true。"""
        stop_called = []

        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)
        monkeypatch.setattr("web.lan_listener.lan_listener.stop",
                            lambda *a, **k: stop_called.append(True))

        def _fail_persist(fn):
            raise OSError("disk full")

        monkeypatch.setattr("web.routers.config.mutate_config", _fail_persist)

        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False, "persist 失敗應回傳 success=False"
        assert stop_called, "listener 應被 rollback stop() 呼叫"
        # config 檔案未被 mutate_config 修改（mock 拋例外前沒有寫入）
        saved = json.loads(mock_config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is not True, (
            "config 不應寫入 true（persist 失敗時）"
        )


    # ── Loopback-only guard（feature/80 TASK-80b）─────────────────────────────

    def test_remote_cannot_enable_server_mode(self, mock_config_path, monkeypatch):
        """遠端 IP 的 PUT server_mode true → {success:false}，start 不被呼叫，config 不寫 true。

        遠端客人不得開啟 server_mode；LAN 伺服器是否開放是主機的決定。
        loopback-only guard 必須在 listener/config 操作前 early-return。

        注意：lan_access_gate middleware 讀 config.server_mode 決定放行；測試中先把
        config 設 true（模擬 server_mode 已開）讓 middleware 放行，再驗 router 層
        loopback guard 拒絕此遠端 IP 切換 server_mode。
        """
        import core.config as _cc
        # 讓 middleware 放行遠端 IP（模擬 server_mode 已開）
        _cc.mutate_config(lambda cfg: cfg.setdefault("general", {}).update({"server_mode": True}))

        start_called = []

        def _spy_start(*a, **k):
            start_called.append(True)
            return 49200

        monkeypatch.setattr("web.lan_listener.lan_listener.start", _spy_start)

        remote_client = TestClient(app, client=("192.168.1.50", 12345))
        resp = remote_client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False, "遠端 IP 應被拒絕（success=False）"
        assert data["reason"] == "remote_forbidden", "前端據此顯示 remote_only 專屬訊息"
        assert "error" in data
        assert not start_called, "lan_listener.start 不應被呼叫（guard 在 start 之前 early-return）"

        saved = json.loads(mock_config_path.read_text())
        # server_mode 仍為 true（我們設的初始值），remote 沒有修改它
        assert saved.get("general", {}).get("server_mode") is True, (
            "config server_mode 應維持初始 true（router guard 拒絕，不寫入任何新值）"
        )


    @pytest.mark.parametrize("env_name,reason", [("OPENAVER_SYNOLOGY", "synology_fixed"), ("OPENAVER_SERVER_ONLY", "server_fixed")])
    def test_synology_blocks_server_mode_put_even_loopback(self, client, mock_config_path, monkeypatch, env_name, reason):
        """CD-159-6/159-T7: is_synology()=True（或 Linux 伺服器版）時 server_mode PUT 無條件被擋，即使是 loopback 呼叫。"""
        monkeypatch.setenv(env_name, "1")

        resp = client.put("/api/config/general/server_mode", json={"value": False})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reason"] == reason

    @pytest.mark.parametrize("env_name", ["OPENAVER_SYNOLOGY", "OPENAVER_SERVER_ONLY"])
    def test_synology_reset_keeps_server_mode_and_listener(self, client, mock_config_path, monkeypatch, env_name):
        """Synology／Linux 伺服器版重設後仍允許 LAN 存取，且不停止既有 listener。"""
        monkeypatch.setenv(env_name, "1")
        saved = json.loads(mock_config_path.read_text())
        saved["general"]["server_mode"] = True
        mock_config_path.write_text(json.dumps(saved))
        stop_called = []
        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop",
            lambda *a, **k: stop_called.append(True),
        )

        resp = client.delete("/api/config")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert json.loads(mock_config_path.read_text())["general"]["server_mode"] is True
        assert client.get("/api/config").json()["data"]["general"]["server_mode"] is True
        assert not stop_called


    # ── public_exposure 欄位（114a-T7）────────────────────────────────────────

    def test_toggle_true_public_ip_flags_exposure(self, client, mock_config_path, monkeypatch):
        """PUT server_mode true + public IP → public_exposure True"""
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)
        monkeypatch.setattr("web.lan_listener.get_lan_ip", lambda: "8.8.8.8")

        resp = client.put("/api/config/general/server_mode", json={"value": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["public_exposure"] is True


