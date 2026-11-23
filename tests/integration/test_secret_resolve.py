"""Integration tests for resolve_secret wiring at six credential entry points (TASK-114c-T2).

R1–R6: GET→PUT mask round-trip, connect mask token, positive write/clear,
and four test endpoints × mask/plaintext (CD-114c-6).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core import config as core_config
from core import secret_store
from core.config import load_config, save_config
from core.metatube.state import metatube_state as state
from core.secret_fields import mask_secret
from web.routers import config as config_router

pytestmark = pytest.mark.usefixtures("isolate_secret_store")

# Canonical non-empty secrets (len > 4 so mask keeps last-4 sentinel).
GEMINI_PLAIN = "gemini-secret-key-aaaa"
OPENAI_PLAIN = "sk-openai-secret-bbbb"
METATUBE_PLAIN = "mt-token-secret-cccc"

GEMINI_NEW = "gemini-new-key-zzzz"
OPENAI_NEW = "sk-openai-new-yyyy"
METATUBE_NEW = "mt-token-new-xxxx"

CLAUDE_PLAIN = "sk-ant-claude-secret-dddd"
CLAUDE_NEW = "sk-ant-claude-new-wwww"
OPENAI_OFFICIAL_PLAIN = "sk-openai-official-eeee"

CONNECT_URL = "http://192.168.1.10:8080"


def _seed_three_secrets() -> None:
    cfg = load_config()
    cfg.setdefault("translate", {}).setdefault("gemini", {})["api_key"] = GEMINI_PLAIN
    cfg.setdefault("translate", {}).setdefault("openai", {})["api_key"] = OPENAI_PLAIN
    cfg.setdefault("metatube", {})["token"] = METATUBE_PLAIN
    save_config(cfg)


def _effective_secrets() -> tuple[str, str, str]:
    """金鑰的有效值（磁碟檔＋庫注入後的 load_config 結果）。"""
    cfg = load_config()
    return (
        cfg["translate"]["gemini"]["api_key"],
        cfg["translate"]["openai"]["api_key"],
        cfg["metatube"]["token"],
    )


_SECRET_PARTS = (
    "translate.gemini.api_key",
    "translate.openai.api_key",
    "translate.claude.api_key",
    "translate.openai_official.api_key",
    "metatube.token",
    "ai_services.image_similar.api_key",
    "ai_services.faces.api_key",
)


def _file_secrets() -> tuple[str, ...]:
    """直接讀 CONFIG_PATH 原始 JSON（不經 load_config 注入），回七條靜態金鑰路徑的值。"""
    with open(core_config.CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for dotted in _SECRET_PARTS:
        node = raw
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        out.append(node if isinstance(node, str) else "")
    return tuple(out)


@pytest.fixture(autouse=True)
def _reset_metatube_state():
    """Reset metatube_state singleton between tests (connect paths touch it)."""
    state.disconnect()
    state.set_probe_done()
    with state._lock:
        state._probe_progress = 0
    yield
    state.disconnect()
    state.set_probe_done()
    with state._lock:
        state._probe_progress = 0


# ---------------------------------------------------------------------------
# httpx helpers (mirror test_gemini_router / test_api_openai_translate)
# ---------------------------------------------------------------------------

def _make_mock_httpx_client(get_response=None, post_response=None):
    mock_client = AsyncMock()
    if get_response is not None:
        mock_client.get = AsyncMock(return_value=get_response)
    if post_response is not None:
        mock_client.post = AsyncMock(return_value=post_response)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, mock_client


def _ok_http_response(json_body: dict):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=json_body)
    mock_resp.raise_for_status = MagicMock(return_value=None)
    return mock_resp


# ===========================================================================
# R1 / R2 — GET→PUT must not overwrite secrets with mask sentinels
# ===========================================================================

class TestR1SettingsPageRoundTrip:
    """設定頁：GET 整包 → 原封不動 PUT → 三憑證 disk 真值一字未變。"""

    def test_r1_put_masked_body_preserves_secrets(self, client):
        _seed_three_secrets()
        before = _effective_secrets()

        get_resp = client.get("/api/config")
        assert get_resp.status_code == 200
        data = get_resp.json()["data"]
        # Sanity: wire is masked (T1 already guarantees this).
        assert data["translate"]["gemini"]["api_key"] == mask_secret(GEMINI_PLAIN)
        assert data["translate"]["openai"]["api_key"] == mask_secret(OPENAI_PLAIN)
        assert data["metatube"]["token"] == mask_secret(METATUBE_PLAIN)

        put_resp = client.put("/api/config", json=data)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True

        after = _effective_secrets()
        assert after == before
        assert after == (GEMINI_PLAIN, OPENAI_PLAIN, METATUBE_PLAIN)
        # 檔內永遠不含明文：七條靜態路徑皆空。
        assert _file_secrets() == ("",) * 7
        # 庫裡真值仍在（保留態＝不變）。
        assert secret_store.snapshot()["translate.gemini.api_key"] == GEMINI_PLAIN
        assert secret_store.snapshot()["translate.openai.api_key"] == OPENAI_PLAIN
        assert secret_store.snapshot()["metatube.token"] == METATUBE_PLAIN

    def test_upgrade_from_0186_config_preserves_translate_keys(self, client):
        """0.18.6 形狀（無 openai_official、無 ai_services）升級後 GET→PUT 金鑰保留。"""
        import json

        from core import config as core_config

        gemini_key = "TESTKEY-gemini-1"
        claude_key = "TESTKEY-claude-1"
        openai_key = "TESTKEY-openai-1"
        provider = "openai"

        cfg = core_config.AppConfig().model_dump()
        cfg.pop("ai_services", None)
        translate = cfg.setdefault("translate", {})
        translate.pop("openai_official", None)
        translate["provider"] = provider
        translate.setdefault("gemini", {})["api_key"] = gemini_key
        translate.setdefault("claude", {})["api_key"] = claude_key
        translate.setdefault("openai", {})["api_key"] = openai_key

        with open(core_config.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

        get_resp = client.get("/api/config")
        assert get_resp.status_code == 200
        data = get_resp.json()["data"]
        assert data["translate"]["gemini"]["api_key"] == mask_secret(gemini_key)
        assert data["translate"]["claude"]["api_key"] == mask_secret(claude_key)
        assert data["translate"]["openai"]["api_key"] == mask_secret(openai_key)

        put_resp = client.put("/api/config", json=data)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True

        disk = load_config()
        assert disk["translate"]["gemini"]["api_key"] == gemini_key
        assert disk["translate"]["claude"]["api_key"] == claude_key
        assert disk["translate"]["openai"]["api_key"] == openai_key
        assert disk["translate"]["openai_official"]["api_key"] == ""
        assert disk["translate"]["provider"] == provider
        # 檔內空、庫內有值。
        assert _file_secrets() == ("",) * 7
        assert secret_store.snapshot()["translate.gemini.api_key"] == gemini_key
        assert secret_store.snapshot()["translate.claude.api_key"] == claude_key
        assert secret_store.snapshot()["translate.openai.api_key"] == openai_key


# ===========================================================================
# R3 — /connect with mask token → all four token sinks get REAL
# ===========================================================================

class TestR3ConnectMaskToken:
    """connect 送遮罩 token → client / canary / state.connect / 背景 probe 四處收真值；config 不毀。"""

    def test_r3_connect_mask_token_four_sinks(self, client):
        cfg = load_config()
        cfg.setdefault("metatube", {})["token"] = METATUBE_PLAIN
        save_config(cfg)

        mask = mask_secret(METATUBE_PLAIN)
        assert mask != METATUBE_PLAIN  # sentinel must differ

        with (
            patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient,
            patch("web.routers.settings_metatube._verify_token_canary") as mock_canary,
            patch.object(state, "connect", wraps=state.connect) as mock_state_connect,
            # Patch _fire_probe itself, not probe_all: _fire_probe schedules its work
            # with run_in_executor and the handler never awaits it (settings_metatube.py
            # :218-236), so probe_all's call args are only readable after a race the
            # test would have to sleep/poll for. The call INTO _fire_probe happens
            # synchronously on the loop thread — that is where the token is observable.
            patch("web.routers.settings_metatube._fire_probe") as mock_fire_probe,
        ):
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {
                "FANZA": "http://mt:8080",
                "HEYZO": "http://mt:8080",
            }
            MockClient.return_value = mock_instance
            mock_canary.return_value = None

            resp = client.post(
                "/api/settings/metatube/connect",
                json={"url": CONNECT_URL, "token": mask, "allow_lan": True},
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

        # (a) MetatubeHttpClient constructor token arg
        MockClient.assert_called()
        call_args = MockClient.call_args
        # MetatubeHttpClient(url, token) — positional
        assert call_args[0][1] == METATUBE_PLAIN, (
            f"MetatubeHttpClient got token={call_args[0][1]!r}, expected REAL"
        )

        # (b) canary call args
        mock_canary.assert_called_once()
        canary_args = mock_canary.call_args[0]
        assert canary_args[1] == METATUBE_PLAIN, (
            f"_verify_token_canary got token={canary_args[1]!r}, expected REAL"
        )

        # (c) state.connect call args
        mock_state_connect.assert_called_once()
        sc_args = mock_state_connect.call_args[0]
        assert sc_args[1] == METATUBE_PLAIN, (
            f"state.connect got token={sc_args[1]!r}, expected REAL"
        )

        # (d) background probe call args — a mask here would make every provider
        # report unavailable while the connection itself looks fine.
        mock_fire_probe.assert_called_once()
        fp_args = mock_fire_probe.call_args[0]
        assert fp_args[1] == METATUBE_PLAIN, (
            f"_fire_probe got token={fp_args[1]!r}, expected REAL"
        )

        # (e) config still REAL (not overwritten by mask)
        assert load_config()["metatube"]["token"] == METATUBE_PLAIN


# ===========================================================================
# R4 — positive plaintext writes
# ===========================================================================

class TestR4PositiveWrite:
    def test_r4a_put_new_gemini_key(self, client):
        _seed_three_secrets()
        get_resp = client.get("/api/config")
        data = get_resp.json()["data"]
        data["translate"]["gemini"]["api_key"] = GEMINI_NEW

        put_resp = client.put("/api/config", json=data)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True
        assert load_config()["translate"]["gemini"]["api_key"] == GEMINI_NEW
        # Other secrets untouched (mask → stored)
        assert load_config()["translate"]["openai"]["api_key"] == OPENAI_PLAIN
        assert load_config()["metatube"]["token"] == METATUBE_PLAIN
        # 檔內七條皆空；庫快取反映「新值」進來、「舊值」保留。
        assert _file_secrets() == ("",) * 7
        assert secret_store.snapshot()["translate.gemini.api_key"] == GEMINI_NEW
        assert secret_store.snapshot()["translate.openai.api_key"] == OPENAI_PLAIN


# ===========================================================================
# R5 — clear with ""
# ===========================================================================

class TestR5Clear:
    def test_r5_put_empty_clears_all_three(self, client):
        _seed_three_secrets()
        get_resp = client.get("/api/config")
        data = get_resp.json()["data"]
        data["translate"]["gemini"]["api_key"] = ""
        data["translate"]["openai"]["api_key"] = ""
        data["metatube"]["token"] = ""

        put_resp = client.put("/api/config", json=data)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True

        disk = load_config()
        assert disk["translate"]["gemini"]["api_key"] == ""
        assert disk["translate"]["openai"]["api_key"] == ""
        assert disk["metatube"]["token"] == ""
        # 檔內七條皆空；庫裡三個名稱都已消失。
        assert _file_secrets() == ("",) * 7
        snapshot = secret_store.snapshot()
        assert "translate.gemini.api_key" not in snapshot
        assert "translate.openai.api_key" not in snapshot
        assert "metatube.token" not in snapshot


# ===========================================================================
# R6 — four test endpoints × mask / new plaintext (CD-114c-6)
# ===========================================================================

class TestR6GeminiTest:
    def test_r6g1_mask_uses_stored(self, client):
        cfg = load_config()
        cfg.setdefault("translate", {}).setdefault("gemini", {})["api_key"] = GEMINI_PLAIN
        save_config(cfg)

        body = {
            "models": [
                {
                    "name": "models/gemini-flash-lite-latest",
                    "displayName": "Flash Lite",
                    "description": "d",
                }
            ]
        }
        mock_cm, mock_client = _make_mock_httpx_client(get_response=_ok_http_response(body))
        with patch("web.routers.gemini.httpx.AsyncClient", return_value=mock_cm):
            resp = client.post(
                "/api/gemini/test",
                json={"api_key": mask_secret(GEMINI_PLAIN)},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_client.get.assert_called_once()
        headers = mock_client.get.call_args.kwargs["headers"]
        assert headers["x-goog-api-key"] == GEMINI_PLAIN

    def test_r6g2_new_plaintext_uses_incoming(self, client):
        cfg = load_config()
        cfg.setdefault("translate", {}).setdefault("gemini", {})["api_key"] = GEMINI_PLAIN
        save_config(cfg)

        body = {
            "models": [
                {
                    "name": "models/gemini-flash-lite-latest",
                    "displayName": "Flash Lite",
                    "description": "d",
                }
            ]
        }
        mock_cm, mock_client = _make_mock_httpx_client(get_response=_ok_http_response(body))
        with patch("web.routers.gemini.httpx.AsyncClient", return_value=mock_cm):
            resp = client.post("/api/gemini/test", json={"api_key": GEMINI_NEW})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        headers = mock_client.get.call_args.kwargs["headers"]
        assert headers["x-goog-api-key"] == GEMINI_NEW


class TestR6OpenAIModels:
    def test_r6o1_mask_uses_stored(self, client):
        cfg = load_config()
        cfg.setdefault("translate", {}).setdefault("openai", {})["api_key"] = OPENAI_PLAIN
        save_config(cfg)

        mock_cm, mock_client = _make_mock_httpx_client(
            get_response=_ok_http_response({"data": [{"id": "m1"}]})
        )
        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            resp = client.post(
                "/api/openai/models",
                json={
                    "base_url": "http://localhost:8080/v1",
                    "api_key": mask_secret(OPENAI_PLAIN),
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        headers = mock_client.get.call_args.kwargs["headers"]
        assert headers["Authorization"] == f"Bearer {OPENAI_PLAIN}"


class TestR6OpenAIOfficialModels:
    def test_r6oo1_mask_uses_official_stored(self, client):
        """官方 models 遮罩還原必須讀 openai_official，不可誤送相容金鑰。"""
        assert OPENAI_PLAIN != OPENAI_OFFICIAL_PLAIN
        cfg = load_config()
        cfg.setdefault("translate", {}).setdefault("openai", {})["api_key"] = OPENAI_PLAIN
        cfg.setdefault("translate", {}).setdefault("openai_official", {})[
            "api_key"
        ] = OPENAI_OFFICIAL_PLAIN
        save_config(cfg)

        mock_cm, mock_client = _make_mock_httpx_client(
            get_response=_ok_http_response({"data": []})
        )
        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            client.post(
                "/api/openai/official/models",
                json={"api_key": mask_secret(OPENAI_OFFICIAL_PLAIN)},
            )
        headers = mock_client.get.call_args.kwargs["headers"]
        assert headers["Authorization"] == f"Bearer {OPENAI_OFFICIAL_PLAIN}"


class TestR6ClaudeModels:
    def test_r6cm1_mask_uses_stored(self, client):
        cfg = load_config()
        cfg.setdefault("translate", {}).setdefault("claude", {})["api_key"] = CLAUDE_PLAIN
        save_config(cfg)

        mask = mask_secret(CLAUDE_PLAIN)
        assert CLAUDE_PLAIN != mask

        mock_cm, mock_client = _make_mock_httpx_client(
            get_response=_ok_http_response(
                {"data": [{"id": "claude-haiku-4", "created_at": "2025-03-01T00:00:00Z"}]}
            )
        )
        with patch("core.anthropic_client.httpx.AsyncClient", return_value=mock_cm):
            resp = client.post(
                "/api/claude/models",
                json={"api_key": mask},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_client.get.assert_called_once()
        headers = mock_client.get.call_args.kwargs["headers"]
        assert headers["x-api-key"] == CLAUDE_PLAIN


# ===========================================================================
# T4 — mask lookalike, face recompute hook, vaulted test buttons, DELETE
# ===========================================================================

FACES_SETTINGS_OLD = "faces-settings-old-3333cccc"
FACES_SETTINGS_NEW = "faces-settings-new-4444dddd"
SIMILAR_VAULT_KEY = "similar-vault-key-1111aaaa"
FACES_VAULT_KEY = "faces-vault-key-2222bbbb"


class TestMaskLookalike:
    def test_put_mask_lookalike_never_becomes_a_stored_key(self, client):
        """某欄沒設過 Key、前端送來「••••」→ 不可被當成真 Key 存進庫／檔。"""
        data = client.get("/api/config").json()["data"]
        assert data["translate"]["gemini"]["api_key"] == ""
        data["translate"]["gemini"]["api_key"] = "••••"

        put_resp = client.put("/api/config", json=data)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True

        assert load_config()["translate"]["gemini"]["api_key"] == ""
        assert "translate.gemini.api_key" not in secret_store.snapshot()
        assert _file_secrets() == ("",) * 7


class TestFaceRecomputeHook:
    def test_put_triggers_face_recompute_only_when_the_key_changed(
        self, client, monkeypatch
    ):
        """只換人臉金鑰 → 鉤子恰 1 次；整包原樣 PUT → 0 次（不得每次都重算）。"""
        cfg = load_config()
        faces = cfg.setdefault("ai_services", {}).setdefault("faces", {})
        faces["enabled"] = True
        faces["url"] = "http://faces.local:9999/v1"
        faces["api_key"] = FACES_SETTINGS_OLD
        save_config(cfg)

        spy = MagicMock(return_value=False)
        monkeypatch.setattr(
            "core.ai_services.faces_recompute.on_settings_saved", spy
        )

        real_after = config_router._after_faces_saved
        joined = []

        def _wrapped(old, new):
            thread = real_after(old, new)
            if thread is not None:
                thread.join(5)
                joined.append(thread)
                assert not thread.is_alive(), "人臉重算鉤子 thread 逾時未結束"
            return thread

        monkeypatch.setattr(config_router, "_after_faces_saved", _wrapped)

        changed = client.get("/api/config").json()["data"]
        changed["ai_services"]["faces"]["api_key"] = FACES_SETTINGS_NEW
        put_changed = client.put("/api/config", json=changed)
        assert put_changed.status_code == 200
        assert put_changed.json()["success"] is True
        assert spy.call_count == 1
        assert len(joined) == 1
        assert load_config()["ai_services"]["faces"]["api_key"] == FACES_SETTINGS_NEW

        unchanged = client.get("/api/config").json()["data"]
        put_same = client.put("/api/config", json=unchanged)
        assert put_same.status_code == 200
        assert put_same.json()["success"] is True
        assert spy.call_count == 1
        assert len(joined) == 1


@pytest.mark.parametrize(
    "case",
    [
        ("/api/ai/similar/test", "web.routers.ai_services.run_consistency_test",
         "image_similar", SIMILAR_VAULT_KEY),
        ("/api/ai/faces/test", "web.routers.ai_services.run_faces_test",
         "faces", FACES_VAULT_KEY),
    ],
    ids=["similar", "faces"],
)
def test_similar_and_faces_test_buttons_use_the_vaulted_key(client, monkeypatch, case):
    """Key 只在庫時按「測試連線」→ 接縫收到庫內真值（不是空／未設定）。"""
    path, seam, section, vaulted = case
    cfg = load_config()
    target = cfg.setdefault("ai_services", {}).setdefault(section, {})
    target["url"] = "http://vaulted.local:9999/v1"
    target["model"] = "vaulted-model"
    target["api_key"] = vaulted
    save_config(cfg)
    assert _file_secrets() == ("",) * 7

    seen: list = []
    stub = SimpleNamespace(
        ok=False, elapsed_ms=1, kind="unreachable", check=None, model=None, dim=None
    )

    def _fake(cfg_obj):
        seen.append(cfg_obj.api_key)
        return stub

    monkeypatch.setattr(seam, _fake)

    resp = client.post(path, json={"url": "http://other-target.local:1234/v1"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert len(seen) == 1
    assert seen[0] == vaulted


class TestDeleteConfigClearsVault:
    def test_delete_config_clears_the_vault_and_get_shows_unset(self, client):
        """按「恢復原廠」→ 庫清空、GET 各金鑰欄回到未設定。"""
        _seed_three_secrets()
        assert secret_store.snapshot()["translate.gemini.api_key"] == GEMINI_PLAIN

        resp = client.delete("/api/config")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        assert secret_store.snapshot() == {}

        data = client.get("/api/config").json()["data"]
        for dotted in _SECRET_PARTS:
            node = data
            for part in dotted.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            assert node == "", f"{dotted} 應回到未設定（空字串）"


