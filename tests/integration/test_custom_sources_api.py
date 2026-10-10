"""自訂來源 HTTP 路由（TASK-165-T5）：六端點、413 入口、{id} 驗證、測試連線標「請用驗收」。全離線。"""

import threading

import pytest

import core.config as core_config
import core.custom_source.fetch as fetch_mod
from core.config import load_config, save_config
from core.custom_source import registry, service, state
from core.proxy_policy import ProxySettings
from core.source_probe import skip_reason
from tests.unit._custom_source_fake import FakeTransport, finalize_root, gate_route, page, put_source
from tests.unit._custom_source_pages import FIXTURE_DIR, PAGES

GOOD = (FIXTURE_DIR / "single-og.yaml").read_text(encoding="utf-8")
SOG = "https://single-og.example/sone-205"
SOG_MISS = "https://single-og.example/zzzz-999"
NEXT_SENTENCE = "請呼叫驗收；通過即自動啟用，請使用者重新整理搜尋頁／瀏覽頁"


def _yaml(source_id, extra=""):
    return GOOD.replace("id: single-og", f"id: {source_id}", 1) + extra


def _routes():
    return {SOG: page(PAGES["single-og"]), SOG_MISS: page("", 404)}


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr("core.custom_source.fetch.rate_limit", lambda delay=0: None)

    def _boom(self, url):
        raise AssertionError("real transport used")

    monkeypatch.setattr(fetch_mod.PlainTransport, "request", _boom)
    monkeypatch.setattr(fetch_mod.TlsTransport, "request", _boom)


@pytest.fixture
def fake(monkeypatch):
    transport = FakeTransport(_routes())
    # 使用端名字：interpret 自己 import 進來的 make_transport
    monkeypatch.setattr("core.custom_source.interpret.make_transport", lambda fetch, source_id, config: transport)
    return transport


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    save_config(load_config())
    finalize_root(root)
    return root


@pytest.fixture
def unfinalized_root(tmp_path, monkeypatch):
    root = tmp_path / "root2"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    save_config(load_config())
    return root


def _upload(client, text, ctype="text/plain"):
    data = text.encode("utf-8") if isinstance(text, str) else text
    return client.post("/api/custom-sources", content=data, headers={"Content-Type": ctype})


def _assert_error(resp, status, reason):
    body = resp.json()
    assert resp.status_code == status, body
    assert body["success"] is False
    assert body["reason"] == reason
    assert isinstance(body["error"], str) and body["error"]
    return body


@pytest.mark.parametrize("ctype,sid", [
    ("text/plain", "ct-plain"),
    ("application/x-yaml", "ct-xyaml"),
    ("application/octet-stream", "ct-octet"),
    ("application/x-www-form-urlencoded", "ct-form"),
])
def test_upload_accepts_any_content_type(client, env, ctype, sid):
    text = _yaml(sid)
    resp = _upload(client, text, ctype)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["id"] == sid
    assert body["source_id"] == f"custom:{sid}" and body["status"] == "unverified"
    assert body["replaced"] is False and body["next"] == NEXT_SENTENCE
    assert (registry.custom_sources_dir() / f"{sid}.yaml").read_bytes() == text.encode("utf-8")


def test_upload_accepts_bom(client, env):
    resp = _upload(client, b"\xef\xbb\xbf" + _yaml("ct-bom").encode("utf-8"))
    assert resp.status_code == 200, resp.text
    assert (registry.custom_sources_dir() / "ct-bom.yaml").exists()


def test_upload_content_length_over_limit_is_413(client, env):
    resp = _upload(client, b"#" * 300_000)
    assert resp.status_code == 413
    assert not (env / "custom_sources").exists()


def test_upload_between_64k_and_256k_is_400_too_large(client, env):
    resp = _upload(client, b"#" * 70_000)
    _assert_error(resp, 400, "too_large")
    assert not (env / "custom_sources").exists()


def test_upload_non_utf8_is_400_yaml_syntax(client, env):
    _assert_error(_upload(client, b"\xff\xfe\x00"), 400, "yaml_syntax")
    assert not (env / "custom_sources").exists()


def test_upload_bad_yaml_body_shape(client, env):
    body = _assert_error(_upload(client, "id: [unclosed"), 400, "yaml_syntax")
    assert "field_path" in body and isinstance(body["line"], int)
    assert not (env / "custom_sources").exists()
    body = _assert_error(_upload(client, _yaml("bogus-one", "\nbogus_key: 1\n")), 400, "unknown_key")
    assert body["line"] is None


def test_service_error_codes_map_to_http_status(client, env, tmp_path, monkeypatch, fake):
    # 靜態檢查（各自不同輸入）
    _assert_error(_upload(client, _yaml("map-unknown", "\nbogus_key: 1\n")), 400, "unknown_key")
    _assert_error(_upload(client, GOOD.replace("id: single-og", "id: auto", 1)), 400, "reserved_id")
    _assert_error(_upload(client, "id: [unclosed"), 400, "yaml_syntax")
    # not_loaded：三個端點
    _assert_error(client.post("/api/custom-sources/nope-a/verify"), 404, "not_loaded")
    _assert_error(client.delete("/api/custom-sources/nope-b"), 404, "not_loaded")
    _assert_error(client.post("/api/custom-sources/nope-c/enabled", json={"enabled": True}), 404, "not_loaded")
    # load_failed
    put_source(env, "broken", "id: [unclosed")
    body = _assert_error(client.post("/api/custom-sources/broken/verify"), 409, "load_failed")
    assert body["load_error"]["reason"]
    # not_passed
    assert _upload(client, _yaml("map-unpassed")).status_code == 200
    _assert_error(client.post("/api/custom-sources/map-unpassed/enabled", json={"enabled": True}), 409, "not_passed")


def test_data_root_not_ready_is_409(client, unfinalized_root):
    _assert_error(_upload(client, _yaml("map-notready")), 409, "data_root_not_ready")
    assert not (unfinalized_root / "custom_sources").exists()


def test_verify_busy_and_changed_during_verify(client, env, monkeypatch):
    assert _upload(client, _yaml("busy-a")).status_code == 200
    assert _upload(client, _yaml("busy-b")).status_code == 200
    entered, release = threading.Event(), threading.Event()
    routes = _routes()
    routes[SOG] = gate_route(entered, release, page(PAGES["single-og"]), safety_s=5)
    transport = FakeTransport(routes)
    monkeypatch.setattr("core.custom_source.interpret.make_transport", lambda fetch, source_id, config: transport)
    out = {}

    def _first():
        out["resp"] = client.post("/api/custom-sources/busy-a/verify")

    thread = threading.Thread(target=_first, daemon=True)
    thread.start()
    try:
        assert entered.wait(5)
        body = _assert_error(client.post("/api/custom-sources/busy-b/verify"), 409, "verify_busy")
        assert body["busy_id"] == "busy-a"
        resp = _upload(client, _yaml("busy-a"))
        assert resp.status_code == 200 and resp.json()["replaced"] is True
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    _assert_error(out["resp"], 409, "changed_during_verify")


def test_full_round(client, env, fake):
    assert _upload(client, GOOD).status_code == 200
    resp = client.post("/api/custom-sources/single-og/verify")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["status"] == "passed" and body["failed"] == 0
    listed = client.get("/api/custom-sources").json()
    assert listed["success"] is True
    assert [(s["id"], s["status"], s["enabled"]) for s in listed["sources"]] == [("single-og", "passed", True)]
    assert body["enabled"] is True
    resp = client.post("/api/custom-sources/single-og/enabled", json={"enabled": True})
    assert resp.status_code == 200 and resp.json()["enabled"] is True
    resp = client.post("/api/custom-sources/applicable", json={"number": "SONE-205"})
    assert resp.status_code == 200 and resp.json()["applicable"] == {"custom:single-og": True}
    resp = client.delete("/api/custom-sources/single-og")
    assert resp.status_code == 200 and resp.json() == {"success": True, "id": "single-og"}
    assert client.get("/api/custom-sources").json()["sources"] == []
    assert _upload(client, GOOD).json()["replaced"] is False
    assert _upload(client, GOOD).json()["replaced"] is True


@pytest.mark.parametrize("bad_id", ["%2e%2e", "Bad_Id", "x" * 33, "-x", "..%2Fx", "a%2Fb"])
def test_invalid_id_never_reaches_service(client, env, monkeypatch, bad_id):
    calls = []
    monkeypatch.setattr(service, "verify", lambda *a, **k: calls.append("verify") or {})
    monkeypatch.setattr(service, "remove", lambda *a, **k: calls.append("remove") or {})
    monkeypatch.setattr(service, "set_enabled", lambda *a, **k: calls.append("set_enabled") or {})
    base = f"/api/custom-sources/{bad_id}"
    resps = [
        client.post(f"{base}/verify"),
        client.delete(base),
        client.post(f"{base}/enabled", json={"enabled": True}),
    ]
    assert [r.status_code for r in resps] == [404, 404, 404]
    assert calls == []
    if bad_id in ("%2e%2e", "Bad_Id", "x" * 33, "-x"):
        for r in resps:
            _assert_error(r, 404, "not_loaded")


def test_probe_skips_custom_source_with_use_verify_reason(client):
    assert skip_reason("custom:x", ProxySettings(url="", scope="dmm")) == "custom_use_verify"
    assert skip_reason("custom:fc-javten", ProxySettings(url="", scope="dmm")) == "custom_use_verify"
    resp = client.post("/api/sources/probe", json={
        "source_ids": ["custom:x", "custom:fc-javten"], "proxy_url": "", "proxy_scope": "dmm"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    for key in ("custom:x", "custom:fc-javten"):
        assert results[key]["state"] == "skipped" and results[key]["reason"] == "custom_use_verify"
