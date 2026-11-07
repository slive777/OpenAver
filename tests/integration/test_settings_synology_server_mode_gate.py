"""tests/integration/test_settings_synology_server_mode_gate.py — 159-T7
CD-159-6：Synology 版（is_synology()=True）固定伺服器模式，設定頁不顯示
伺服器模式切換鈕的整合渲染守衛。

`client` fixture 與 config 隔離（`_isolate_config` autouse）都來自
`tests/integration/conftest.py`；TestClient 預設 loopback（根 conftest 的
module-level patch），/settings 走 loopback 短路 access_gate／lan_access_gate
兩層 middleware（web/app.py `_is_loopback_host(client_host)` 一律先短路放行），
不需要額外的 access_auth 隔離 fixture（比照 test_settings_focal_pill.py 的形狀）。

一支測試同時守「is_synology context 有沒有真的注入」與「gate 方向對不對」：
Jinja 對缺席的 context 變數預設回傳 falsy 的 Undefined，若 app.py 忘記注入
is_synology，`{% if not is_synology %}` 會恆真、.settings-server-mode 恆顯示
——渲染測試會直接看到這個假綠，不需要另外讀 app.py 原始碼。
"""
import pytest

SERVER_MODE_ANCHOR = 'class="settings-server-mode"'


class TestSettingsSynologyServerModeGate:
    @pytest.mark.parametrize(
        "synology_env,expect_visible",
        [
            ("1", False),   # Synology 版：伺服器模式固定，開關不顯示
            (None, True),   # 一般平台：開關照常顯示
        ],
    )
    def test_settings_server_mode_toggle_visibility(
        self, client, monkeypatch, synology_env, expect_visible
    ):
        if synology_env is None:
            monkeypatch.delenv("OPENAVER_SYNOLOGY", raising=False)
        else:
            monkeypatch.setenv("OPENAVER_SYNOLOGY", synology_env)

        resp = client.get("/settings")
        assert resp.status_code == 200

        # [lint-guard: pytest-justified] 開關出不出現取決於執行期環境變數 OPENAVER_SYNOLOGY 與 Jinja 渲染結果，靜態 lint 掃不到。
        is_visible = SERVER_MODE_ANCHOR in resp.text
        assert is_visible == expect_visible, (
            f"OPENAVER_SYNOLOGY={synology_env!r} 時，.settings-server-mode "
            f"應{'出現' if expect_visible else '不出現'}在 /settings 渲染結果，"
            f"實際{'出現' if is_visible else '不出現'}"
        )

    def test_settings_server_mode_toggle_hidden_for_server_only(
        self, client, monkeypatch
    ):
        monkeypatch.delenv("OPENAVER_SYNOLOGY", raising=False)
        monkeypatch.setenv("OPENAVER_SERVER_ONLY", "1")

        resp = client.get("/settings")
        assert resp.status_code == 200

        # [lint-guard: pytest-justified] 開關出不出現取決於執行期環境變數 OPENAVER_SERVER_ONLY 與 Jinja 渲染結果，靜態 lint 掃不到。
        assert SERVER_MODE_ANCHOR not in resp.text, (
            "OPENAVER_SERVER_ONLY=1 且未設 OPENAVER_SYNOLOGY 時，"
            ".settings-server-mode 不應出現在 /settings 渲染結果，實際出現"
        )
