"""Integration tests for POST/GET /api/settings/metatube/* endpoints (CD-63b-1).

Patching strategy:
- MetatubeHttpClient at use-site: web.routers.settings_metatube.MetatubeHttpClient
- probe_all at use-site: web.routers.settings_metatube.probe_all
- load_config / save_config at use-site to isolate real config.json

State isolation: reset metatube_state singleton between tests via fixture.
"""
import time
import json
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from web.app import app
from core.metatube.state import metatube_state as state
from core.metatube.errors import MetatubeUnavailable, MetatubeAuthError, MetatubeNotFound
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

def test_connect_unavailable(client):
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.side_effect = MetatubeUnavailable("connection refused")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    # Fixed Chinese string — must not expose exception detail
    assert isinstance(data["error"], str)
    assert len(data["error"]) > 0
    assert "connection refused" not in data["error"]
    assert "MetatubeUnavailable" not in data["error"]
    # The fixed string exactly
    assert data["error"] == "無法連線到 metatube server，請確認 URL 與 token"


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

def test_connect_order_offset(client):
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
            "HEYZO": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.json()["success"] is True
    saved_cfg = store.saved[-1]

    builtin_sources = [s for s in saved_cfg["sources"] if s.get("type") == "builtin"]
    metatube_sources = [s for s in saved_cfg["sources"] if s.get("type") == "metatube"]

    assert len(metatube_sources) == 2

    # Every metatube order >= 100
    for s in metatube_sources:
        assert s["order"] >= 100, f"metatube source {s['id']} has order {s['order']} < 100"

    # Every builtin order < every metatube order
    builtin_orders = [s["order"] for s in builtin_sources]
    metatube_orders = [s["order"] for s in metatube_sources]
    assert max(builtin_orders) < min(metatube_orders), (
        f"builtin max order {max(builtin_orders)} >= metatube min order {min(metatube_orders)}"
    )


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

def test_status_after_probe_done(client):
    state.connect("http://192.168.1.10:8080", "", ["FANZA"])
    state.set_probe_started()
    state.set_probe_done()

    resp = client.get("/api/settings/metatube/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["probe_done"] is True


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

def test_test_endpoint_while_disconnected(client):
    """POST /test while disconnected (empty availability map) must return success.

    probe_all receives an empty names list and should return early without error.
    """
    # State is freshly reset by the autouse fixture (disconnected).
    # Note: availability_map keys may still be present (set to False) from a
    # prior test since disconnect() preserves keys per design (grey capsule UX).
    # Force a truly blank state by also clearing _availability here.
    with state._lock:
        state._availability = {}
    assert state.is_connected is False
    assert state.availability_map() == {}

    with patch("web.routers.settings_metatube.probe_all") as mock_probe:
        resp = client.post("/api/settings/metatube/test")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # probe_all was scheduled with empty names list
    _wait_called(mock_probe)
    mock_probe.assert_called_once()
    call_args = mock_probe.call_args
    names_arg = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs.get("provider_names", [])
    assert names_arg == [], f"Expected empty names list, got {names_arg}"


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

def test_connect_persistence_failure_rollback(client):
    """If save_config raises, /connect must roll back runtime state and return
    {"success": False, "error": "設定儲存失敗，請重試。"} (FIX 2 / P2-A)."""

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all") as mock_probe, \
         patch("web.routers.settings_metatube.mutate_config", side_effect=OSError("disk full")):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = {
            "FANZA": "http://mt:8080",
            "HEYZO": "http://mt:8080",
        }
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    # Must return failure
    assert data["success"] is False
    # Fixed Chinese error string
    assert data.get("error") == "設定儲存失敗，請重試。"
    # Runtime state must be rolled back (not connected)
    assert state.is_connected is False
    # probe must NOT have been fired (persistence failed before probe step)
    mock_probe.assert_not_called()


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


def _no_canary_providers():
    """Provider dict with NO entries present in METATUBE_PROBE_CANARIES."""
    # SOD, KIN8, JAV321, FC2PPVDB are explicitly NOT in METATUBE_PROBE_CANARIES
    return {
        "SOD": "http://mt:8080",
        "KIN8": "http://mt:8080",
        "JAV321": "http://mt:8080",
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


def test_canary_search_not_found_does_not_block_connect(client):
    """Step 3b: search raises MetatubeNotFound (non-401) → connect succeeds.
    404 on canary番号 is a canary-data issue, not a token issue."""
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = _canary_providers()
        mock_instance.search.side_effect = MetatubeNotFound("404")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "GOODTOKEN", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_canary_search_success_allows_connect(client):
    """Step 3b: search returns a normal list (token OK path) → connect succeeds."""
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = _canary_providers()
        mock_instance.search.return_value = [{"id": "SSIS-001", "title": "Some Title"}]
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "GOODTOKEN", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


def test_canary_skipped_when_no_canary_provider_in_list(client):
    """Step 3b: providers list has NO entry in METATUBE_PROBE_CANARIES → canary step
    is bypassed entirely and connect succeeds (defensive skip)."""
    store = _make_config_patches()

    with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
         patch("web.routers.settings_metatube.probe_all"), \
         patch("web.routers.settings_metatube.mutate_config", side_effect=store.mutate):

        mock_instance = MagicMock()
        mock_instance.list_providers.return_value = _no_canary_providers()
        # search is deliberately NOT set up — if it were called it would use MagicMock default
        # We track whether it was called to verify the canary step was skipped
        mock_instance.search.side_effect = MetatubeAuthError("should not be called")
        MockClient.return_value = mock_instance

        resp = client.post(
            "/api/settings/metatube/connect",
            json={"url": "http://192.168.1.10:8080", "token": "", "allow_lan": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True, (
        "When no canary provider is in the providers list, connect must succeed "
        "(canary step should be skipped defensively)"
    )


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
    def test_empty_url_no_connect(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config(url="")
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False
        MockClient.assert_not_called()

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
        from core.metatube.errors import MetatubeError

        cfg = _startup_config(url=_LAN_URL, allow_lan=True)
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {"FANZA": _LAN_URL, "HEYZO": _LAN_URL}
            mock_instance.search.return_value = []  # canary passes
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert state.is_connected is True
        assert isinstance(result, list)
        assert len(result) > 0

    # ------------------------------------------------------------------
    # (a-5) list_providers raises MetatubeError → no connect
    # ------------------------------------------------------------------
    def test_list_providers_error_no_connect(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect
        from core.metatube.errors import MetatubeUnavailable

        cfg = _startup_config()
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.side_effect = MetatubeUnavailable("conn refused")
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False

    # ------------------------------------------------------------------
    # (a-6) canary raises MetatubeAuthError (401) → return None, no connect
    # ------------------------------------------------------------------
    def test_canary_auth_error_no_connect(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect
        from core.metatube.errors import MetatubeAuthError as _AuthError

        # Use a provider list that includes a canary (JavBus is in METATUBE_PROBE_CANARIES)
        cfg = _startup_config()
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {
                "JavBus": _PUBLIC_URL,
                "FANZA": _PUBLIC_URL,
            }
            mock_instance.search.side_effect = _AuthError("401")
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False

    # ------------------------------------------------------------------
    # (a-7) canary raises non-401 MetatubeError → continue, connect succeeds
    # ------------------------------------------------------------------
    def test_canary_non401_error_continues(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect
        from core.metatube.errors import MetatubeUnavailable

        cfg = _startup_config()
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {
                "JavBus": _PUBLIC_URL,
                "FANZA": _PUBLIC_URL,
            }
            mock_instance.search.side_effect = MetatubeUnavailable("timeout")
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert state.is_connected is True
        assert result is not None
        assert isinstance(result, list)

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
        assert isinstance(result, list)
        assert set(result) == {"FANZA", "HEYZO", "MGS"}

    # ------------------------------------------------------------------
    # (a-9) config has no 'metatube' key → walks enabled=False path
    # ------------------------------------------------------------------
    def test_no_metatube_key_in_config(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = {"sources": _builtin_sources_dicts()}  # no 'metatube' key
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            result = startup_reconnect(cfg)

        assert result is None
        assert state.is_connected is False
        MockClient.assert_not_called()

    # ------------------------------------------------------------------
    # (a-10) return value is list[str]
    # ------------------------------------------------------------------
    def test_return_value_is_list_of_str(self, reset_state):
        from web.routers.settings_metatube import startup_reconnect

        cfg = _startup_config()
        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_providers.return_value = {
                "FANZA": _PUBLIC_URL,
                "HEYZO": _PUBLIC_URL,
            }
            mock_instance.search.return_value = []
            MockClient.return_value = mock_instance

            result = startup_reconnect(cfg)

        assert isinstance(result, list)
        assert all(isinstance(n, str) for n in result)

    # ------------------------------------------------------------------
    # (b) Lifespan glue layer — TestClient context manager triggers lifespan
    # ------------------------------------------------------------------

    def test_lifespan_calls_startup_reconnect(self, reset_state):
        """startup_reconnect is called during app lifespan startup."""
        with patch("web.app.load_config") as mock_load, \
             patch("web.app.startup_reconnect") as mock_sr, \
             patch("web.app._fire_probe") as mock_probe:

            mock_load.return_value = _startup_config()
            mock_sr.return_value = None  # simulate not connected

            with TestClient(app):
                pass

        mock_sr.assert_called_once()

    def test_lifespan_fires_probe_when_names_returned(self, reset_state):
        """When startup_reconnect returns names, _fire_probe is called once."""
        names = ["FANZA", "HEYZO"]
        # Set state so it looks connected (startup_reconnect mock won't really connect)
        state.connect(_PUBLIC_URL, "tok", names)

        with patch("web.app.load_config") as mock_load, \
             patch("web.app.startup_reconnect") as mock_sr, \
             patch("web.app._fire_probe") as mock_probe:

            mock_load.return_value = _startup_config()
            mock_sr.return_value = names

            with TestClient(app):
                pass

        mock_probe.assert_called_once()

    def test_lifespan_no_probe_when_none_returned(self, reset_state):
        """When startup_reconnect returns None, _fire_probe is NOT called."""
        with patch("web.app.load_config") as mock_load, \
             patch("web.app.startup_reconnect") as mock_sr, \
             patch("web.app._fire_probe") as mock_probe:

            mock_load.return_value = _startup_config(enabled=False)
            mock_sr.return_value = None

            with TestClient(app):
                pass

        mock_probe.assert_not_called()

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

    def test_dedup_persist_failure_returns_error(self, reset_state):
        """dedup hit but save_config fails → connect must NOT report success
        (else the LAN opt-in is silently lost → restart bug returns). Codex P2."""
        store = _make_config_patches(
            _startup_config(enabled=True, url=_LAN_URL, token="tok", allow_lan=False)
        )
        state.connect(_LAN_URL, "tok", ["FANZA"])

        from fastapi.testclient import TestClient as TC
        tc = TC(app)

        with patch("web.routers.settings_metatube.MetatubeHttpClient"), \
             patch("web.routers.settings_metatube.probe_all"), \
             patch("web.routers.settings_metatube.mutate_config",
                   side_effect=OSError("disk full")):

            resp = tc.post(
                "/api/settings/metatube/connect",
                json={"url": _LAN_URL, "token": "tok", "allow_lan": True},
            )

        assert resp.json()["success"] is False
        assert resp.json()["error"] == "設定儲存失敗，請重試。"


# ======================================================================
# 66 Codex P2 (round 2): connect 序列化鎖 — 防並發 connect 交錯
# clobber config/runtime 或 rollback 拆別人連線
# ======================================================================

class TestConnectSerialization:
    """確定性測試（無真 race）：_connect_lock 在臨界段持有 + 序列結果一致。"""

    def test_connect_lock_is_threading_lock(self):
        import threading
        from web.routers.settings_metatube import _connect_lock
        assert isinstance(_connect_lock, type(threading.Lock()))

    def test_connect_sync_holds_lock_during_save_config(self, reset_state):
        """config 寫入時 _connect_lock 必須持有（臨界段涵蓋 mutate_config）。

        mutate_config 在 _connect_lock 內被呼叫（鎖序：外 _connect_lock → 內
        _config_write_lock），語意等價於「save 時 _connect_lock 持有」。
        """
        from web.routers.settings_metatube import _connect_sync, _connect_lock

        held = []

        def _fake_mutate(mutator):
            held.append(_connect_lock.locked())
            mutator(_fresh_config())

        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
             patch("web.routers.settings_metatube.mutate_config", side_effect=_fake_mutate):
            mock_inst = MagicMock()
            mock_inst.list_providers.return_value = {"FANZA": _PUBLIC_URL}
            mock_inst.search.return_value = []
            MockClient.return_value = mock_inst

            result = _connect_sync(_PUBLIC_URL, "", True)

        assert result["ok"] is True
        assert held and all(held), "mutate_config 必須在 _connect_lock 持有時被呼叫"

    def test_persist_allow_lan_holds_lock_during_save_config(self, reset_state):
        """_persist_allow_lan 的 config 寫入也在 _connect_lock 內。"""
        from web.routers.settings_metatube import _persist_allow_lan, _connect_lock

        held = []

        def _fake_mutate(mutator):
            held.append(_connect_lock.locked())
            mutator({"metatube": {"url": _PUBLIC_URL, "token": "tok", "allow_lan": False}})

        with patch("web.routers.settings_metatube.mutate_config", side_effect=_fake_mutate):
            ok = _persist_allow_lan(_PUBLIC_URL, "tok", True)

        assert ok is True
        assert held and all(held), "_persist_allow_lan 的寫入必須在 _connect_lock 內"

    def test_sequential_connects_leave_config_consistent(self, reset_state):
        """兩次連續 connect 後 config 與 runtime state 皆指向最後一次（B）。

        序列代理並發 clobber 場景：序列化下，config 永遠反映最後一次 connect，
        不會殘留前一台 server 的 URL。
        """
        import copy
        from web.routers.settings_metatube import _connect_sync

        saved = []

        def _fake_mutate(mutator):
            cfg = copy.deepcopy(saved[-1]) if saved else _fresh_config()
            mutator(cfg)
            saved.append(copy.deepcopy(cfg))

        with patch("web.routers.settings_metatube.MetatubeHttpClient") as MockClient, \
             patch("web.routers.settings_metatube.mutate_config", side_effect=_fake_mutate):
            mock_inst = MagicMock()
            mock_inst.list_providers.return_value = {"FANZA": _PUBLIC_URL}
            mock_inst.search.return_value = []
            MockClient.return_value = mock_inst

            r1 = _connect_sync("http://8.8.4.4:8080", "", True)
            r2 = _connect_sync("http://8.8.8.8:8080", "", True)

        assert r1["ok"] is True and r2["ok"] is True
        assert state.base_url == "http://8.8.8.8:8080"
        assert saved[-1]["metatube"]["url"] == "http://8.8.8.8:8080"

    def test_disconnect_holds_connect_lock(self, client, reset_state):
        """disconnect 路由經 _connect_lock 序列化：state.disconnect() 在鎖內執行。"""
        from web.routers.settings_metatube import _connect_lock

        held = []
        orig = state.disconnect

        def _spy():
            held.append(_connect_lock.locked())
            orig()

        with patch.object(state, "disconnect", side_effect=_spy):
            resp = client.post("/api/settings/metatube/disconnect")

        assert resp.json()["success"] is True
        assert held == [True], "state.disconnect() 必須在 _connect_lock 持有時執行"

    def test_disconnect_waits_for_inflight_connect_then_wins(self, reset_state):
        """在途 connect 持鎖時 disconnect 必須等待，鎖釋放後斷線（last-action-wins）。

        確定性：用 Barrier/Event 強制順序，不依賴 timing。
        """
        import threading
        import time
        from web.routers.settings_metatube import _disconnect_sync, _connect_lock

        barrier = threading.Barrier(2)
        release = threading.Event()

        def _hold_lock():
            with _connect_lock:
                barrier.wait()            # 通知「已持鎖」
                release.wait(timeout=2.0)  # 持鎖直到被釋放

        holder = threading.Thread(target=_hold_lock, daemon=True)
        holder.start()
        barrier.wait()                     # 等 holder 拿到鎖

        state.connect("http://8.8.8.8:8080", "", ["FANZA"])
        assert state.is_connected is True

        result = []

        def _run_disconnect():
            _disconnect_sync()
            result.append(state.is_connected)

        t = threading.Thread(target=_run_disconnect, daemon=True)
        t.start()

        time.sleep(0.05)
        assert state.is_connected is True, "鎖被持有時 disconnect 必須仍在等待"

        release.set()
        t.join(timeout=2.0)
        assert result == [False], "鎖釋放後 disconnect 應使狀態變為斷線"
