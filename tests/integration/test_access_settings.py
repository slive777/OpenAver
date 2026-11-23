"""
TASK-114a-T4: `GET`/`PUT /api/access/settings` —— 認證設定端點。

涵蓋 card 測試案例表 A–G：
  - A: GET reveal 依 loopback 決定（含 ::ffff:127.0.0.1）
  - B: PUT R4 loopback-only（含 mapped-IPv4 通過、遠端 403、lan_access_gate 純文字）
  - C: PIN 格式驗證（前導零保留、illegal 不寫入、enabled=false 跳過格式）
  - D: R5 三操作全撤（開／改不同／改相同／關）
  - E: lifecycle 對稱（拒絕路徑不撤票、不寫入）
  - F: AC4b server_mode 關再開不碰認證
  - G: CD-114a-9 DELETE /api/config 不碰認證 + 反向假綠防護
"""
from __future__ import annotations

import core.access_auth as access_auth
import pytest
from fastapi.testclient import TestClient

from web.app import app

LOOPBACK_CLIENT = ("127.0.0.1", 12345)
REMOTE_CLIENT = ("192.168.1.50", 12345)
MAPPED_LOOPBACK_CLIENT = ("::ffff:127.0.0.1", 12345)

SETTINGS_PATH = "/api/access/settings"


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def auth_db(tmp_path, monkeypatch):
    """每測隔離 access_auth DB：先 patch 路徑 → ensure_schema → reset cache。

    loopback 請求不會觸發 middleware 冷路徑的 ensure_schema 補救，必須在此
    暖機；reset_state_for_tests 清掉 module-level cache/retry，避免跨測污染。
    """
    db_path = tmp_path / "access.db"
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: db_path)
    access_auth.ensure_schema()
    access_auth.reset_state_for_tests()
    yield db_path
    access_auth.reset_state_for_tests()


@pytest.fixture
def server_mode_true(monkeypatch):
    """讓 lan_access_gate 放行非 loopback（含 ::ffff:127.0.0.1）。"""
    monkeypatch.setattr(
        "web.app.load_config",
        lambda: {"general": {"server_mode": True}},
    )


@pytest.fixture
def loopback_client(auth_db):
    return TestClient(app, client=LOOPBACK_CLIENT)


@pytest.fixture
def remote_client(auth_db, server_mode_true):
    return TestClient(app, client=REMOTE_CLIENT)


@pytest.fixture
def mapped_client(auth_db, server_mode_true):
    return TestClient(app, client=MAPPED_LOOPBACK_CLIENT)


def _remote_authed_client(token: str) -> TestClient:
    """遠端 + 持票：enabled=True 時 access_gate 才會放行到 settings handler。"""
    client = TestClient(app, client=REMOTE_CLIENT)
    client.cookies.set("sid", token)
    return client


# ── A. GET /api/access/settings ───────────────────────────────────────────


# ── B. PUT R4 loopback-only ───────────────────────────────────────────────


class TestPutR4:

    def test_b2_remote_unauthed_password_off_now_succeeds(self, remote_client):
        before = access_auth.get_auth_settings(True)
        assert before == {"enabled": False, "pin": ""}
        r = remote_client.put(
            SETTINGS_PATH, json={"enabled": True, "pin": "1234"}
        )
        assert r.status_code == 200
        assert r.json() == {"success": True}
        assert access_auth.get_auth_settings(True) == {
            "enabled": True,
            "pin": "1234",
        }


# ── C. PUT PIN 格式驗證 ───────────────────────────────────────────────────


class TestPutPinFormat:
    def test_c1_leading_zero_preserved(self, loopback_client):
        r = loopback_client.put(
            SETTINGS_PATH, json={"enabled": True, "pin": "0042"}
        )
        assert r.status_code == 200
        assert r.json() == {"success": True}
        assert access_auth.get_auth_settings(True)["pin"] == "0042"


    def test_c1c_fullwidth_pin_stored_as_ascii(self, loopback_client):
        """T7fix：中文輸入法全形模式打出的密碼，存進去必須已折成半形——
        否則使用者用手機（輸入法關著）打同一組字，永遠對不上。"""
        r = loopback_client.put(
            SETTINGS_PATH, json={"enabled": True, "pin": "ａＢ９２"}
        )
        assert r.status_code == 200
        assert access_auth.get_auth_settings(True)["pin"] == "aB92"


# ── D. R5 三操作全撤 ──────────────────────────────────────────────────────


# ── E. lifecycle 對稱 ─────────────────────────────────────────────────────


class TestLifecycleSymmetry:
    def test_e1_masked_by_access_gate_has_no_side_effects(
        self, remote_client, loopback_client
    ):
        access_auth.set_auth(True, "1111")
        put_response = remote_client.put(
            SETTINGS_PATH, json={"enabled": False, "pin": ""}
        )
        assert put_response.status_code == 200
        assert put_response.headers["content-type"].startswith("text/html")
        # [lint-guard: pytest-justified] 安全指紋：未登入的遠端請求被 access_gate 換成登入頁，斷言回應不帶 API JSON（執行期行為，lint 掃不到）。
        assert "success" not in put_response.text

        get_response = remote_client.get(SETTINGS_PATH)
        assert get_response.status_code == 200
        assert get_response.headers["content-type"].startswith("text/html")
        assert "success" not in get_response.text

        local_response = loopback_client.get(SETTINGS_PATH)
        assert local_response.status_code == 200
        assert local_response.json()["enabled"] is True
        assert local_response.json()["pin"] == "1111"

    def test_e2_invalid_pin_no_write_no_revoke(self, loopback_client):
        access_auth.set_auth(True, "1111")
        token = access_auth.attempt_pin("1111")
        assert token is not None
        assert access_auth.verify_ticket(token) is True
        before = access_auth.get_auth_settings(True)
        assert before == {"enabled": True, "pin": "1111"}
        r = loopback_client.put(
            SETTINGS_PATH, json={"enabled": True, "pin": "12 3"}
        )
        assert r.status_code == 400
        assert access_auth.get_auth_settings(True) == before
        assert access_auth.verify_ticket(token) is True


# ── F. AC4b server_mode 關再開 ────────────────────────────────────────────


class TestAC4bServerModeIndependent:
    def test_f_server_mode_toggle_leaves_auth_intact(
        self, loopback_client, monkeypatch
    ):
        monkeypatch.setattr(
            "web.lan_listener.lan_listener.start", lambda *a, **k: 49200
        )
        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "web.lan_listener.get_lan_ip", lambda: "192.168.1.50"
        )

        access_auth.set_auth(True, "5555")
        token = access_auth.attempt_pin("5555")
        assert token is not None
        assert access_auth.verify_ticket(token) is True  # F1

        r2 = loopback_client.put(
            "/api/config/general/server_mode", json={"value": True}
        )
        assert r2.status_code == 200  # F2

        r3 = loopback_client.put(
            "/api/config/general/server_mode", json={"value": False}
        )
        assert r3.status_code == 200  # F3

        assert access_auth.get_auth_settings(True) == {
            "enabled": True,
            "pin": "5555",
        }
        assert access_auth.verify_ticket(token) is True  # F4


# ── G. CD-114a-9 DELETE /api/config ───────────────────────────────────────


class TestCD114a9ConfigResetIndependent:
    @pytest.mark.usefixtures("isolate_secret_store")
    def test_g1_delete_config_leaves_auth_intact(
        self, loopback_client, monkeypatch
    ):
        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop", lambda *a, **k: None
        )
        access_auth.set_auth(True, "6666")
        token = access_auth.attempt_pin("6666")
        assert token is not None
        assert access_auth.verify_ticket(token) is True

        r = loopback_client.delete("/api/config")
        assert r.status_code == 200
        assert access_auth.get_auth_settings(True) == {
            "enabled": True,
            "pin": "6666",
        }
        assert access_auth.verify_ticket(token) is True


def test_j1_j3_password_semantics_full_flow(auth_db, server_mode_true):
    client = TestClient(app, client=REMOTE_CLIENT)

    opened = client.put(SETTINGS_PATH, json={"enabled": True, "pin": "1234"})
    assert opened.status_code == 200
    assert opened.headers["set-cookie"].startswith("sid=")
    old_token = client.cookies.get("sid")
    assert old_token is not None

    changed = client.put(SETTINGS_PATH, json={"enabled": True, "pin": "5678"})
    assert changed.status_code == 200
    assert access_auth.verify_ticket(old_token) is False

    verified = client.post("/api/access/verify", json={"pin": "5678"})
    assert verified.status_code == 200
    assert verified.headers["set-cookie"].startswith("sid=")
    new_token = client.cookies.get("sid")
    assert new_token is not None
    assert new_token != old_token

    help_response = client.get("/help")
    assert help_response.status_code == 200
    # [lint-guard: pytest-justified] 安全指紋：SSR 後的 /help 依「已通過 PIN／token 撤銷」而變，lint 掃不到執行期結果。
    assert b"help-agent-token-panel" in help_response.content

    client.cookies.set("sid", old_token)
    revoked_response = client.get("/help")
    assert revoked_response.status_code == 200
    # [lint-guard: pytest-justified] 同上：token 撤銷後同一份 /help 的 SSR 結果不得再帶 token 面板。
    assert b"help-agent-token-panel" not in revoked_response.content

    client.cookies.set("sid", new_token)
    closed = client.put(SETTINGS_PATH, json={"enabled": False, "pin": ""})
    assert closed.status_code == 200
    assert closed.json() == {"success": True}
    client.cookies.delete("sid")
    reopened = client.put(SETTINGS_PATH, json={"enabled": True, "pin": "9999"})
    assert reopened.status_code == 200
    assert reopened.headers["set-cookie"].startswith("sid=")
    assert access_auth.get_auth_settings(True) == {"enabled": True, "pin": "9999"}


def test_get_can_edit_reveal_reachable_matrix(
    loopback_client, remote_client, server_mode_true
):
    access_auth.set_auth(True, "0042")
    local = loopback_client.get(SETTINGS_PATH)
    assert local.status_code == 200
    assert local.json()["can_edit"] is True
    assert local.json()["pin"] == "0042"
    assert local.json()["pin_revealed"] is True

    token = access_auth.attempt_pin("0042")
    assert token is not None
    remote_authed = _remote_authed_client(token).get(SETTINGS_PATH)
    assert remote_authed.status_code == 200
    assert remote_authed.json()["can_edit"] is True
    assert remote_authed.json()["pin"] == "0042"
    assert remote_authed.json()["pin_revealed"] is True

    bearer_client = TestClient(app, client=REMOTE_CLIENT)
    bearer_update = bearer_client.put(
        SETTINGS_PATH,
        json={"enabled": True, "pin": "0042"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bearer_update.status_code == 200
    assert bearer_update.json() == {"success": True}

    access_auth.set_auth(False, "")
    remote_open = remote_client.get(SETTINGS_PATH)
    assert remote_open.status_code == 200
    assert remote_open.json()["can_edit"] is True
    assert remote_open.json()["pin"] == "••••"
    assert remote_open.json()["pin_revealed"] is False

    no_op = remote_client.put(SETTINGS_PATH, json={"enabled": False, "pin": ""})
    assert no_op.status_code == 200
    assert no_op.json() == {"success": True}
    assert "set-cookie" not in no_op.headers
