"""Integration tests for POST/GET /api/settings/metatube/* endpoints (CD-63b-1).

Patching strategy:
- MetatubeHttpClient at use-site: web.routers.settings_metatube.MetatubeHttpClient
- probe_all at use-site: web.routers.settings_metatube.probe_all
- load_config / save_config at use-site to isolate real config.json

State isolation: reset metatube_state singleton between tests via fixture.
"""
import threading
import time
import json
import pytest
from unittest.mock import DEFAULT, MagicMock, patch

from fastapi.testclient import TestClient

from web.app import app
from core.metatube.state import metatube_state as state
from core.metatube.errors import MetatubeUnavailable, MetatubeAuthError
from core.secret_fields import mask_secret
from core.source_config import get_builtin_sources


# ---------------------------------------------------------------------------
# Bounded poll helper (Fix 6 — replaces racy fixed sleep before mock asserts)
# ---------------------------------------------------------------------------

def _wait_called(mock, timeout=2.0):
    """Poll until mock.called is True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mock.called:
            return
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _builtin_sources_dicts() -> list[dict]:
    return [s.model_dump() for s in get_builtin_sources()]


def _fresh_config() -> dict:
    """Minimal in-memory config dict (no metatube key, 8 builtin sources)."""
    return {
        "sources": _builtin_sources_dicts(),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset metatube_state singleton between tests."""
    state.disconnect()
    state.set_probe_done()   # ensure probe flags reset
    with state._lock:
        state._probe_progress = 0
    yield
    state.disconnect()
    state.set_probe_done()
    with state._lock:
        state._probe_progress = 0


# ---------------------------------------------------------------------------
# Helper: patch load/save config with a captured in-memory dict
# ---------------------------------------------------------------------------

class _ConfigStore:
    def __init__(self, initial: dict):
        self.data = initial
        self.saved: list[dict] = []

    def load(self):
        import copy
        return copy.deepcopy(self.data)

    def save(self, cfg: dict):
        import copy
        self.data = copy.deepcopy(cfg)
        self.saved.append(copy.deepcopy(cfg))

    def mutate(self, mutator):
        """Mirror core.config.mutate_config: load → mutator(cfg) → save (RMW)."""
        import copy
        cfg = copy.deepcopy(self.data)
        mutator(cfg)
        self.data = copy.deepcopy(cfg)
        self.saved.append(copy.deepcopy(cfg))


def _make_config_patches(initial: dict | None = None):
    """Return (store, patch_load, patch_save) context managers."""
    store = _ConfigStore(initial or _fresh_config())
    return store


# ---------------------------------------------------------------------------
# Test: connect success
# ---------------------------------------------------------------------------

def test_connect_success(client):
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all") as mock_probe, \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
            "HEYZO": "http://mt:8080",
            "MGS": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["provider_count"] == 3

    # Runtime state updated
    assert state.is_connected is True

    # Config persisted with metatube.url / metatube.token (NO `connected` key)
    assert len(store.saved) >= 1
    saved_cfg = store.saved[-1]
    assert "metatube" in saved_cfg
    assert saved_cfg["metatube"]["url"] == "http://192.168.1.10:8080"
    assert saved_cfg["metatube"]["token"] == ""
    # Step5 persists allow_lan (guards against the write being dropped) — Codex P2
    assert saved_cfg["metatube"]["allow_lan"] is True
    assert "connected" not in saved_cfg["metatube"]

    # probe_all was called (via run_in_executor, so we confirm it was scheduled)
    # use bounded poll instead of fixed sleep to avoid CI flake
    _wait_called(mock_probe)
    mock_probe.assert_called_once()


# ---------------------------------------------------------------------------
# Test: connect SSRF fail (private IP without allow_lan)
# ---------------------------------------------------------------------------

def test_connect_ssrf_blocked(client):
    resp = client.post(
        "/api/settings/metatube/connect",
        json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    # error is a non-empty Chinese string
    assert isinstance(data["error"], str)
    assert len(data["error"]) > 0
    # Must NOT contain the raw URL or internal IP
    assert "192.168.1.10" not in data["error"]
    assert "192.168" not in data["error"]


# ---------------------------------------------------------------------------
# Test: connect list_providers raises MetatubeUnavailable
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test: connect list_providers raises MetatubeAuthError (401)
# ---------------------------------------------------------------------------

def test_connect_auth_error(client):
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.side_effect = MetatubeAuthError("401 Unauthorized")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "BADTOKEN", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    # Must NOT leak token or raw 401 message
    assert "BADTOKEN" not in data.get("error", "")
    assert "401" not in data.get("error", "")
    assert "Unauthorized" not in data.get("error", "")
    # Same fixed Chinese string (base MetatubeError catch)
    assert data["error"] == "無法連線到 metatube server，請確認 URL 與 token"


# ---------------------------------------------------------------------------
# Test: order +100 — metatube sources must all have order >= 100
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test: disconnect
# ---------------------------------------------------------------------------

def test_disconnect(client):
    store = _make_config_patches()

    # First connect
    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {"FANZA": "http://mt:8080"}
        MockClient.return_value = mock_instance

        client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "mytoken", "allow_lan": True},
        )

    assert state.is_connected is True
    # Config should have metatube url/token set by the connect call
    saved_cfg = store.saved[-1]
    assert saved_cfg["metatube"]["url"] == "http://192.168.1.10:8080"
    assert saved_cfg["metatube"]["token"] == "mytoken"

    save_count_before = len(store.saved)

    # Disconnect inside its own patch scope so save_count assertion is meaningful
    with patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):
        resp = client.post("/api/settings/metatube/disconnect")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert state.is_connected is False

    # disconnect must NOT write config (no mutate_config call)
    assert len(store.saved) == save_count_before, "disconnect must not write config"

    # In-memory config metatube url/token must still be the values set by connect
    assert store.data["metatube"]["url"] == "http://192.168.1.10:8080"
    assert store.data["metatube"]["token"] == "mytoken"


# ---------------------------------------------------------------------------
# Test: GET /status during probe
# ---------------------------------------------------------------------------

def test_status_during_probe(client):
    store = _make_config_patches()

    # Connect first so state.is_connected is True
    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
            "HEYZO": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    # Simulate probe in-progress
    state.set_probe_started()
    state.set_probe_progress(5, 30)

    resp = client.get("/api/settings/metatube/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["connected"] is True
    assert data["probe_done"] is False
    assert data["probe_progress"] == 5
    assert isinstance(data["providers"], list)
    provider_ids = {p["id"] for p in data["providers"]}
    assert "metatube:FANZA" in provider_ids
    assert "metatube:HEYZO" in provider_ids


# ---------------------------------------------------------------------------
# Test: GET /status after probe done
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test: POST /test endpoint fires probe
# ---------------------------------------------------------------------------

def test_test_endpoint(client):
    # Connect state so availability_map has entries
    state.connect("http://192.168.1.10:8080", "", ["FANZA", "HEYZO"])

    with patch("web.routers.settings_metatube.probe_all") as mock_probe:
        resp = client.post("/api/settings/metatube/test")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "message" in data

    _wait_called(mock_probe)
    mock_probe.assert_called_once()
    # names passed should be FANZA and HEYZO (in some order)
    call_kwargs = mock_probe.call_args
    names_arg = call_kwargs.args[3] if len(call_kwargs.args) > 3 else call_kwargs.kwargs.get("provider_names", [])
    assert set(names_arg) == {"FANZA", "HEYZO"}


# ---------------------------------------------------------------------------
# Test: connect preserves `enabled` for pre-existing metatube provider (Fix 4)
# ---------------------------------------------------------------------------

def test_connect_preserves_enabled(client):
    """Existing metatube sources with enabled=True keep that flag after re-connect.

    Newly-added providers default to enabled=False.
    All metatube sources must have order >= 100.
    """
    # Pre-populate config with a metatube:FANZA source (enabled=True)
    existing_fanza = {
        "id": "metatube:FANZA",
        "type": "metatube",
        "enabled": True,
        "order": 100,
        "config": {"censored_type": "censored"},
        "display_name_raw": "FANZA",
        "display_name_key": None,
        "is_beta": False,
        "manual_only": False,
        "requires_proxy": False,
    }
    initial_cfg = _fresh_config()
    initial_cfg["sources"].append(existing_fanza)
    store = _make_config_patches(initial_cfg)

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
            "MGS": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.json()["success"] is True
    saved_cfg = store.saved[-1]

    metatube_sources = {
        s["id"]: s
        for s in saved_cfg["sources"]
        if s.get("type") == "metatube"
    }

    # FANZA was pre-existing with enabled=True — must be preserved
    assert "metatube:FANZA" in metatube_sources
    assert metatube_sources["metatube:FANZA"]["enabled"] is True, (
        "metatube:FANZA enabled flag should be preserved (was True)"
    )

    # MGS is newly added — must default to enabled=False
    assert "metatube:MGS" in metatube_sources
    assert metatube_sources["metatube:MGS"]["enabled"] is False, (
        "newly-added metatube:MGS should have enabled=False"
    )

    # All metatube sources must have order >= 100
    for sid, s in metatube_sources.items():
        assert s["order"] >= 100, f"{sid} has order {s['order']} < 100"


# ---------------------------------------------------------------------------
# Test: POST /test endpoint while disconnected returns success (Fix 5)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test: connect preserves metatube.enabled flag (CD-63b-3 Work Item A)
# ---------------------------------------------------------------------------

def test_connect_preserves_metatube_enabled_flag(client):
    """POST /connect must preserve existing config.metatube.enabled (CD-63b-3).

    Scenario: user previously set enabled=True in Advanced tab.
    After reconnecting (e.g. with different URL/token), enabled must remain True.
    """
    initial_cfg = _fresh_config()
    initial_cfg["metatube"] = {"enabled": True, "url": "", "token": ""}
    store = _make_config_patches(initial_cfg)

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "tok123", "allow_lan": True},
        )

    assert resp.json()["success"] is True
    assert len(store.saved) >= 1
    saved_cfg = store.saved[-1]

    # enabled flag MUST be preserved (was True, must remain True after connect)
    assert saved_cfg["metatube"]["enabled"] is True, (
        "CD-63b-3: connect must not wipe metatube.enabled — "
        "was True before connect, must remain True after"
    )
    # URL and token must be updated to the new values
    assert saved_cfg["metatube"]["url"] == "http://192.168.1.10:8080"
    assert saved_cfg["metatube"]["token"] == "tok123"


# ---------------------------------------------------------------------------
# Test: connect persistence failure → rollback runtime state (FIX 2)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests: 63d-2 — Step 3b token canary (CD-63d-3)
#
# Providers list MUST include a name in METATUBE_PROBE_CANARIES (e.g. JavBus)
# so the canary search actually fires.
# ---------------------------------------------------------------------------

def _canary_providers():
    """Provider dict that includes JavBus (a known METATUBE_PROBE_CANARIES entry)."""
    return {
        "JavBus": "http://mt:8080",
        "FANZA": "http://mt:8080",
        "HEYZO": "http://mt:8080",
    }


def test_canary_search_auth_error_blocks_connect(client):
    """Step 3b: search raises MetatubeAuthError (401) → connect returns success=False
    with a token-related error message. Runtime state must NOT be connected."""
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all") as mock_probe, \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = _canary_providers()
        mock_instance.search.side_effect = MetatubeAuthError("401 Unauthorized")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "BADTOKEN", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    # Error message must mention token
    assert "Token" in data.get("error", ""), (
        f"Expected 'Token' in error message, got: {data.get('error')!r}"
    )
    # Must NOT have advanced to connected state
    assert state.is_connected is False
    # probe must NOT have fired
    mock_probe.assert_not_called()


def test_canary_search_unavailable_does_not_block_connect(client):
    """Step 3b: search raises MetatubeUnavailable (non-401) → connect succeeds.
    Non-401 errors are transient/canary issues, not token errors."""
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = _canary_providers()
        mock_instance.search.side_effect = MetatubeUnavailable("timeout")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "GOODTOKEN", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ---------------------------------------------------------------------------
# TestStartupReconnect — TASK-63e-1
# ---------------------------------------------------------------------------

# Public URL that passes SSRF (globally routable IP, no DNS needed)
# 8.8.8.8 is Google DNS — is_private=False, is_global=True, no DNS resolution needed.
_PUBLIC_URL = "http://8.8.8.8:8080"
_LAN_URL = "http://192.168.1.10:8080"


def _startup_config(
    enabled: bool = True,
    url: str = _PUBLIC_URL,
    token: str = "tok",
    allow_lan: bool = False,
) -> dict:
    """Minimal config dict for startup_reconnect tests."""
    return {
        "metatube": {
            "enabled": enabled,
            "url": url,
            "token": token,
            "allow_lan": allow_lan,
        },
        "sources": _builtin_sources_dicts(),
    }


def _signal(event):
    """side_effect：被呼叫時 set event，回傳值仍用 mock 的 return_value。"""
    def _fn(*a, **kw):
        event.set()
        return DEFAULT
    return _fn


class TestStartupReconnect:
    """(a) Pure function layer — call startup_reconnect() directly."""

    # ------------------------------------------------------------------
    # (a-1) enabled=False → no connect
    # ------------------------------------------------------------------
    def test_disabled_no_connect(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config(enabled=False)
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False
        MockClient.assert_not_called()

    # ------------------------------------------------------------------
    # (a-2) enabled=True but url='' → no connect
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-3) config allow_lan=False + LAN URL → SSRF blocks, no connect
    # ------------------------------------------------------------------
    def test_lan_url_ssrf_blocked(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config(url=_LAN_URL, allow_lan=False)
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False
        MockClient.assert_not_called()

    # ------------------------------------------------------------------
    # (a-4) config allow_lan=True + LAN URL → SSRF passes, connect succeeds
    # ------------------------------------------------------------------
    def test_lan_url_allowed(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config(url=_LAN_URL, allow_lan=True)
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {"FANZA": _LAN_URL, "HEYZO": _LAN_URL}
            mock_instance.search.return_value = []  # canary passes
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert state.is_connected is True
        names, gen = result
        assert isinstance(names, list)
        assert len(names) > 0
        assert isinstance(gen, int)

    # ------------------------------------------------------------------
    # (a-5) list_providers raises MetatubeError → no connect
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-6) canary raises MetatubeAuthError (401) → return None, no connect
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-7) canary raises non-401 MetatubeError → continue, connect succeeds
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-8) happy path (public URL) → connected + list returned
    # ------------------------------------------------------------------
    def test_happy_path_public_url(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config()
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {
                "FANZA": _PUBLIC_URL,
                "HEYZO": _PUBLIC_URL,
                "MGS": _PUBLIC_URL,
            }
            mock_instance.search.return_value = []
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert state.is_connected is True
        avail = state.availability_map()
        assert len(avail) > 0
        names, gen = result
        assert set(names) == {"FANZA", "HEYZO", "MGS"}

    # ------------------------------------------------------------------
    # (a-9) config has no 'metatube' key → walks enabled=False path
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-10) return value is tuple[list[str], int]
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-11) returned generation == the gen state.connect set (B1, CD-66b-2)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (a-12) connect-critical section runs while _connect_lock is held (B3)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # (b) Lifespan glue layer — TestClient context manager triggers lifespan
    # ------------------------------------------------------------------

    def test_lifespan_calls_startup_reconnect(self, reset_state, tmp_path, monkeypatch):
        """startup_reconnect is called during app lifespan startup."""
        # `with TestClient(app):` 觸發完整 lifespan startup（web/app.py:79 init_db() /
        # :84 ensure_schema()），未 mock 前連上 output/openaver.db（同 4 支測試共用理由）。
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: tmp_path / "app.db")
        monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access.db")
        with patch("web.app.load_config") as mock_load, \
             patch("web.app.backfill_readonly_nfo_mtime_once", return_value=None), \
             patch("web.app.startup_reconnect") as mock_sr, \
             patch("web.app._fire_probe") as mock_probe:

            mock_load.return_value = _startup_config()
            mock_sr.return_value = None  # simulate not connected
            called = threading.Event()
            mock_sr.side_effect = _signal(called)

            with TestClient(app):
                assert called.wait(5), "startup_reconnect was never called"

        mock_sr.assert_called_once()

    def test_lifespan_fires_probe_when_names_returned(self, reset_state, tmp_path, monkeypatch):
        """When startup_reconnect returns names, _fire_probe is called once."""
        names = ["FANZA", "HEYZO"]
        # Set state so it looks connected (startup_reconnect mock won't really connect)
        state.connect(_PUBLIC_URL, "tok", names)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: tmp_path / "app.db")
        monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access.db")

        with patch("web.app.load_config") as mock_load, \
             patch("web.app.backfill_readonly_nfo_mtime_once", return_value=None), \
             patch("web.app.startup_reconnect") as mock_sr, \
             patch("web.app._fire_probe") as mock_probe:

            mock_load.return_value = _startup_config()
            mock_sr.return_value = (names, 1)
            probed = threading.Event()
            mock_probe.side_effect = _signal(probed)

            with TestClient(app):
                assert probed.wait(5), "_fire_probe was never called"

        mock_probe.assert_called_once()


    # ------------------------------------------------------------------
    # (c) connect dedup persist — allow_lan updated in config after dedup hit
    # ------------------------------------------------------------------

    def test_dedup_persists_allow_lan_update(self, reset_state):
        """connect(allow_lan=False) then connect same url+token(allow_lan=True)
        → dedup hits but config.allow_lan updated to True."""
        store = _make_config_patches(
            _startup_config(enabled=True, url=_LAN_URL, token="tok", allow_lan=False)
        )
        # Pre-connect state (as if user already connected with allow_lan=False)
        state.connect(_LAN_URL, "tok", ["FANZA"])

        from fastapi.testclient import TestClient as TC
        tc = TC(app)

        # Second connect: same url+token, but allow_lan=True
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
             patch("web.routers.settings_metatube.probe_all"), \
             patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {"FANZA": _LAN_URL}
            MockClient.return_value = mock_instance

            resp = tc.post(
                "/api/settings/metatube/connect",
                json={"url": _LAN_URL, "token": "tok", "allow_lan": True},
            )

        assert resp.json()["success"] is True
        # Config must have allow_lan=True after the dedup-hit connect
        assert store.data["metatube"]["allow_lan"] is True


def _file_token() -> str:
    """直接讀原始 config.json（不經 load_config 注入）的 metatube.token。"""
    from core import config as core_config

    with open(core_config.CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    mt = raw.get("metatube") or {}
    return mt.get("token", "")


@pytest.mark.parametrize("case", ["startup", "dedup"], ids=["startup", "dedup"])
def test_metatube_token_in_vault_survives_restart_and_dedup(
    reset_state, isolate_secret_store, case
):
    """token 只存在加密庫：重啟後仍連得上；dedup 不重連也不丟 token。"""
    from core import secret_store
    from core.config import load_config, save_config
    from web.routers.settings_metatube import startup_reconnect

    vaulted = "metatube-vault-token-5555eeee"
    url = _LAN_URL
    assert mask_secret(vaulted) != vaulted

    cfg = load_config()
    cfg.setdefault("metatube", {}).update(
        {"enabled": True, "url": url, "token": vaulted, "allow_lan": True}
    )
    save_config(cfg)
    assert _file_token() == ""
    assert secret_store.snapshot()["metatube.token"] == vaulted

    if case == "startup":
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            instance = MagicMock()
            instance.list_providers.return_value = {"JavBus": url}
            instance.search.return_value = []
            MockClient.return_value = instance

            result = startup_reconnect(load_config())

        assert result is not None
        assert state.is_connected is True
        # list_providers 與 token canary 各建一次 client，兩次都帶庫內 token。
        ctor_calls = [c for c in MockClient.call_args_list if c.args]
        assert len(ctor_calls) == 2
        assert all(c.args[1] == vaulted for c in ctor_calls)
        return

    # dedup：已連同一組 url+token，POST 送遮罩仍不得重建 client、token 不丟
    state.connect(url, vaulted, ["FANZA"])
    mask = mask_secret(vaulted)

    tc = TestClient(app)
    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
        resp = tc.post(
            "/api/settings/metatube/connect",
            json={"url": url, "token": mask, "allow_lan": True},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    MockClient.assert_not_called()
    assert state.token == vaulted
    assert load_config()["metatube"]["allow_lan"] is True
    assert _file_token() == ""
    assert secret_store.snapshot()["metatube.token"] == vaulted


# ======================================================================
# 66 Codex P2 (round 2): connect 序列化鎖 — 防並發 connect 交錯
# clobber config/runtime 或 rollback 拆別人連線
# ======================================================================

