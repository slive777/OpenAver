"""自訂來源三個入口接線（TASK-165-T7b）：gate 句、重刮視窗五結果、確認寫挑的那一版、批次一律拒絕。全離線。"""

import json
import os
import threading
import time
from pathlib import Path

import pytest

import core.custom_source.fetch as fetch_mod
from core.config import load_config, save_config
from core.custom_source import registry, state
from core.path_utils import to_file_uri
from tests.unit._custom_source_fake import FakeTransport, finalize_root, page, put_source
from tests.unit._custom_source_pages import FIXTURE_DIR, PAGES

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

NUMBER = "SONE-205"
SOG = "https://single-og.example/sone-205"
TS_SEARCH = "https://two-step.example/search/SONE-205"
TS_X = "https://two-step.example/video/sone-205-x/"
TS_Y = "https://two-step.example/video/sone-205-y/"
SINGLE = (FIXTURE_DIR / "single-og.yaml").read_text(encoding="utf-8")
TWO_STEP = (FIXTURE_DIR / "two-step.yaml").read_text(encoding="utf-8")
SEARCH_PAGE = f"""<html><body class="search-results">
<h3 class="entry-title"><a href="{TS_X}">SONE-205 (x)</a></h3>
<h3 class="entry-title"><a href="{TS_Y}">SONE-205 (y)</a></h3>
</body></html>"""


def _detail(title, date):
    return f"""<html><head>
<script type="application/ld+json">{{"@type":"VideoObject","thumbnailUrl":"https://img.example/two-step/cover.jpg","uploadDate":"{date}"}}</script>
</head><body><h1 class="entry-title">SONE-205 (SUB) {title}</h1>
<div class="tags-items"><a class="tag-item" href="/t/1">TagA</a></div></body></html>"""


# 兩版本標題各異（不能用 _custom_source_pages 的 two-step 兩頁：標題相同）
TITLE_X, TITLE_Y = "Alpha Edition Title", "Omega Edition Title"
TWO_VERSION_ROUTES = {
    TS_SEARCH: page(SEARCH_PAGE),
    TS_X: page(_detail(TITLE_X, "2025-12-17")),
    TS_Y: page(_detail(TITLE_Y, "2024-06-01")),
}
SEVEN_REASONS = ["not_loaded", "load_failed", "verifying", "unverified", "failed", "disabled", "pattern_mismatch"]


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr("core.custom_source.fetch.rate_limit", lambda delay=0: None)

    def _boom(self, url):
        raise AssertionError("real transport used")

    monkeypatch.setattr(fetch_mod.PlainTransport, "request", _boom)
    monkeypatch.setattr(fetch_mod.TlsTransport, "request", _boom)


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
def wire(monkeypatch):
    def _wire(routes):
        transport = FakeTransport(routes)
        monkeypatch.setattr("core.custom_source.interpret.make_transport", lambda fetch, source_id, config: transport)
        return transport
    return _wire


def _ready(env, sid, text, enable=True):
    put_source(env, sid, text)
    sha = registry.load_one(sid).sha256
    assert state.record_result(sid, sha, "passed", {"total": 1, "failed": 0, "cases": []}, state.get_gen(sid))
    assert state.set_enabled(sid, bool(enable), sha)  # 通過即啟用（165-T16），未啟用要明確關閉


def _yaml(text, sid, old):
    return text.replace(f"id: {old}", f"id: {sid}", 1)


def _refusal_case(env, reason):
    """回 (source, number)；每種 reason 用不同的狀態準備（真 gate、真 state）。"""
    number = NUMBER
    sid = reason.replace("_", "-")
    if reason == "not_loaded":
        return f"custom:{sid}", number
    if reason == "load_failed":
        put_source(env, sid, "id: [unclosed")
    elif reason == "unverified":
        put_source(env, sid, _yaml(SINGLE, sid, "single-og"))
    elif reason == "verifying":
        _ready(env, sid, _yaml(SINGLE, sid, "single-og"))
        assert state.try_begin_verify(sid)
    elif reason == "failed":
        put_source(env, sid, _yaml(SINGLE, sid, "single-og"))
        assert state.record_result(sid, registry.load_one(sid).sha256, "failed",
                                   {"total": 1, "failed": 1, "cases": []}, state.get_gen(sid))
    elif reason == "disabled":
        _ready(env, sid, _yaml(SINGLE, sid, "single-og"), enable=False)
    elif reason == "pattern_mismatch":
        _ready(env, sid, _yaml(SINGLE, sid, "single-og"))
        number = "12345"
    return f"custom:{sid}", number


def _all_sentences(client, env, wire):
    wire({})
    out = {}
    for reason in SEVEN_REASONS:
        source, number = _refusal_case(env, reason)
        resp = client.post("/api/rescrape/preview", json={"number": number, "source": source})
        out[reason] = resp.json()["error"]
    return out


# ---------- 三個入口 × 七種 reason ----------

def test_seven_sentences_are_distinct(client, env, wire):
    sentences = _all_sentences(client, env, wire)
    assert len(set(sentences.values())) == 7


@pytest.mark.parametrize("reason", SEVEN_REASONS)
def test_search_refusal_is_400_with_custom_reason(client, env, wire, reason):
    transport = wire({})
    source, number = _refusal_case(env, reason)
    resp = client.get("/api/search", params={"q": number, "mode": "exact", "source": source})
    body = resp.json()
    assert resp.status_code == 400, body
    assert body["success"] is False and body["reason"] == "custom_source_refused"
    assert body["custom_reason"] == reason and body["error"]
    assert transport.calls == []


@pytest.mark.parametrize("reason", SEVEN_REASONS)
def test_preview_refusal_is_200_with_custom_reason(client, env, wire, reason):
    transport = wire({})
    source, number = _refusal_case(env, reason)
    resp = client.post("/api/rescrape/preview", json={"number": number, "source": source})
    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is False and body["custom_error"] == "refused"
    assert body["custom_reason"] == reason and body["error"]
    assert transport.calls == []


@pytest.mark.parametrize("reason", SEVEN_REASONS)
def test_enrich_single_refusal_is_400_same_sentence(client, env, wire, tmp_path, reason):
    transport = wire({})
    source, number = _refusal_case(env, reason)
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    resp = client.post("/api/enrich-single", json={
        "file_path": to_file_uri(str(video)), "number": number, "source": source,
        "mode": "refresh_full", "overwrite_existing": True, "write_cover": False,
    })
    assert resp.status_code == 400, resp.text
    pre = client.post("/api/rescrape/preview", json={"number": number, "source": source}).json()
    assert resp.json()["detail"] == pre["error"]
    assert transport.calls == []
    assert not list(tmp_path.glob("*.nfo"))


def test_search_passes_when_usable_and_transport_reachable(client, env, wire):
    transport = wire({SOG: page(PAGES["single-og"])})
    _ready(env, "single-og", SINGLE)
    resp = client.get("/api/search", params={"q": NUMBER, "mode": "exact", "source": "custom:single-og"})
    assert resp.status_code == 200 and resp.json()["success"] is True
    assert transport.calls  # transport 真接得到，上面的零請求斷言才有意義


# ---------- /api/search 抓不到資料 ----------

def test_search_parse_empty_is_200_custom_error(client, env, wire):
    wire({SOG: page("<html><body>nothing here</body></html>")})
    _ready(env, "single-og", SINGLE)
    resp = client.get("/api/search", params={"q": NUMBER, "mode": "exact", "source": "custom:single-og"})
    body = resp.json()
    assert resp.status_code == 200
    assert body["success"] is False and body["custom_error"] == "parse_empty"
    assert body["source"] == "custom:single-og" and body["data"] == [] and body["error"]


# ---------- preview 五結果 ----------

def test_preview_single_hit(client, env, wire):
    wire({SOG: page(PAGES["single-og"])})
    _ready(env, "single-og", SINGLE)
    body = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:single-og"}).json()
    assert body["success"] is True and "candidates" not in body
    assert "Sample Title One" in body["title"]


def test_preview_multiple_candidates(client, env, wire):
    wire(TWO_VERSION_ROUTES)
    _ready(env, "two-step", TWO_STEP)
    body = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:two-step"}).json()
    assert body["success"] is True and len(body["candidates"]) == 2
    assert {c["title"] for c in body["candidates"]} == {TITLE_X, TITLE_Y}


def test_preview_not_found(client, env, wire):
    wire({"https://single-og.example/zzzz-999": page("", 404)})
    _ready(env, "single-og", SINGLE)
    body = client.post("/api/rescrape/preview", json={"number": "ZZZZ-999", "source": "custom:single-og"}).json()
    assert body == {"success": False, "custom_error": "not_found", "source": "custom:single-og"}


@pytest.mark.parametrize("status,expected", [(403, "refused"), (500, "unreachable")])
def test_preview_access_errors(client, env, wire, status, expected):
    wire({SOG: page("blocked", status)})
    _ready(env, "single-og", SINGLE)
    body = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:single-og"}).json()
    assert body == {"success": False, "access_error": expected, "source": "custom:single-og"}


def test_preview_parse_empty_is_not_unreachable(client, env, wire):
    wire({SOG: page("<html><body>nothing here</body></html>")})
    _ready(env, "single-og", SINGLE)
    body = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:single-og"}).json()
    assert body == {"success": False, "custom_error": "parse_empty", "source": "custom:single-og"}


def test_preview_timeout_is_unreachable_fast(client, env, wire, monkeypatch):
    wire({})
    _ready(env, "single-og", SINGLE)
    monkeypatch.setattr("core.custom_source.service.CALL_LIMIT_S", 0.2)
    hang = threading.Event()
    monkeypatch.setattr("web.routers._custom_preview.search_custom_versions", lambda s, n: hang.wait(5))
    t0 = time.monotonic()
    body = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:single-og"}).json()
    assert body["access_error"] == "unreachable" and time.monotonic() - t0 < 1


# ---------- 確認寫的是挑的那一版 ----------

def _pick_second(client):
    cands = client.post("/api/rescrape/preview", json={"number": NUMBER, "source": "custom:two-step"}).json()["candidates"]
    return cands[1]


def _nfo_title(directory):
    nfos = list(Path(directory).rglob("*.nfo"))
    assert len(nfos) == 1, nfos
    return nfos[0].read_text(encoding="utf-8")


def test_confirm_second_version_writes_second_version(client, env, wire, tmp_path):
    transport = wire(TWO_VERSION_ROUTES)
    _ready(env, "two-step", TWO_STEP)
    second = _pick_second(client)
    searches_before = transport.calls.count(TS_SEARCH)
    video = tmp_path / "lib" / "SONE-205.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    resp = client.post("/api/enrich-single", json={
        "file_path": to_file_uri(str(video)), "number": NUMBER, "source": "custom:two-step",
        "detail_url": second["url"], "mode": "refresh_full", "overwrite_existing": True, "write_cover": False,
    })
    assert resp.status_code == 200 and resp.json()["success"] is True, resp.text
    other = TITLE_X if second["title"] == TITLE_Y else TITLE_Y
    nfo = _nfo_title(video.parent)
    assert second["title"] in nfo and other not in nfo
    assert f"<website>{second['url']}</website>" in nfo
    assert transport.calls.count(TS_SEARCH) == searches_before  # 走明細路徑、沒有重搜


def _ro_config(src, out):
    cfg = load_config()
    cfg["gallery"] = {"directories": [{"path": str(src), "readonly": True}], "path_mappings": {}, "output_dir": str(out)}
    cfg["scraper"] = {**cfg.get("scraper", {}), "external_manager": "off", "folder_layers": [], "folder_format": "",
                      "filename_format": "{num}", "max_title_length": 50, "max_filename_length": 60, "suffix_keywords": []}
    return cfg


def test_readonly_confirm_second_version_writes_second_version(client, env, wire, tmp_path, mocker, monkeypatch):
    from core.database import VideoRepository as RealRepo, init_db
    transport = wire(TWO_VERSION_ROUTES)
    _ready(env, "two-step", TWO_STEP)
    second = _pick_second(client)
    searches_before = transport.calls.count(TS_SEARCH)
    src = tmp_path / "src"
    src.mkdir()
    video = src / "SONE-205.mp4"
    video.write_bytes(b"x")
    db_path = tmp_path / "db" / "t.db"
    db_path.parent.mkdir()
    init_db(db_path)
    out = tmp_path / "out"
    out.mkdir()
    mocker.patch("web.routers.scraper.load_config", return_value=_ro_config(src, out))
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: db_path)
    mocker.patch("web.routers.scraper.VideoRepository", side_effect=lambda *a, **kw: RealRepo(db_path))
    mocker.patch("core.readonly_assets.generate_jellyfin_images", return_value={"poster": False, "fanart": False})
    mocker.patch("core.readonly_assets.download_image", return_value=False)
    canonical = to_file_uri(str(video))
    resp = client.post("/api/enrich-single", json={
        "file_path": canonical, "number": NUMBER, "source": "custom:two-step", "detail_url": second["url"],
        "readonly_action": "rescrape", "mode": "refresh_full", "overwrite_existing": True,
    })
    assert resp.status_code == 200 and resp.json()["success"] is True, resp.text
    other = TITLE_X if second["title"] == TITLE_Y else TITLE_Y
    from core.path_utils import uri_to_local_fs_path
    row = RealRepo(db_path).get_by_path(canonical)
    nfo = _nfo_title(uri_to_local_fs_path(row.output_dir, {}))
    assert second["title"] in nfo and other not in nfo
    assert transport.calls.count(TS_SEARCH) == searches_before
    assert not list(src.glob("*.nfo"))


def test_metadata_and_custom_detail_url_mutually_exclusive(client, env, wire, tmp_path):
    transport = wire({})
    _ready(env, "two-step", TWO_STEP)
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    resp = client.post("/api/enrich-single", json={
        "file_path": to_file_uri(str(video)), "number": NUMBER, "source": "custom:two-step",
        "detail_url": TS_Y, "mode": "refresh_full", "metadata": {"number": NUMBER, "title": "T"},
    })
    assert resp.status_code == 400 and "不可同時提供" in resp.json()["detail"]
    assert transport.calls == []


def test_enrich_prefetch_failures_are_classified(client, env, wire, tmp_path):
    wire({TS_Y: page("<html><body>nothing</body></html>")})
    _ready(env, "two-step", TWO_STEP)
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    resp = client.post("/api/enrich-single", json={
        "file_path": to_file_uri(str(video)), "number": NUMBER, "source": "custom:two-step",
        "detail_url": TS_Y, "mode": "refresh_full", "overwrite_existing": True, "write_cover": False,
    })
    body = resp.json()
    assert body["success"] is False and body["custom_error"] == "parse_empty" and body["error"]
    assert not list(tmp_path.glob("*.nfo"))


def test_enrich_prefetch_timeout_is_unreachable_fast(client, env, wire, tmp_path, monkeypatch):
    wire({})
    _ready(env, "two-step", TWO_STEP)
    monkeypatch.setattr("core.custom_source.service.CALL_LIMIT_S", 0.2)
    hang = threading.Event()
    monkeypatch.setattr("web.routers._custom_preview.fetch_custom_by_detail_url", lambda s, u, n: hang.wait(5))
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    t0 = time.monotonic()
    body = client.post("/api/enrich-single", json={
        "file_path": to_file_uri(str(video)), "number": NUMBER, "source": "custom:two-step",
        "detail_url": TS_Y, "mode": "refresh_full", "overwrite_existing": True, "write_cover": False,
    }).json()
    assert body["success"] is False and body["access_error"] == "unreachable" and time.monotonic() - t0 < 1


# ---------- batch 一律拒絕 ----------

def _sse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def batch_spies(mocker):
    return {
        "search_jav": mocker.patch("web.routers.scraper.search_jav", return_value={"title": "BUILTIN"}),
        "enrich_single": mocker.patch("web.routers.scraper.enrich_single"),
        "readonly": mocker.patch("web.routers.scraper.enrich_one_readonly"),
        "builtin": mocker.patch("core.scraper.JavBusScraper"),
    }


def _assert_batch_refused(events, spies, transport, n, files):
    results = [e for e in events if e["type"] == "result-item"]
    assert len(results) == n
    for r in results:
        assert r["success"] is False and "不參與批次補完" in r["error"]
    assert events[-1]["type"] == "done" and events[-1]["summary"] == {"total": n, "success": 0, "failed": n}
    for spy in spies.values():
        spy.assert_not_called()
    assert transport.calls == []
    assert not list(files.rglob("*.nfo"))


@pytest.mark.parametrize("where", ["request", "item"])
def test_batch_refuses_every_custom_source(client, env, wire, batch_spies, tmp_path, where):
    transport = wire(TWO_VERSION_ROUTES)
    _ready(env, "two-step", TWO_STEP)  # 已驗收已啟用也一律拒絕
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    item = {"file_path": to_file_uri(str(video)), "number": NUMBER}
    body = {"items": [item], "mode": "refresh_full"}
    (body if where == "request" else item)["source"] = "custom:two-step"
    events = _sse(client.post("/api/batch-enrich", json=body).text)
    _assert_batch_refused(events, batch_spies, transport, 1, tmp_path)


@pytest.mark.parametrize("bad", ["custom:../x", "custom:"])
def test_batch_refuses_malformed_custom_without_falling_back_to_auto(client, env, wire, batch_spies, tmp_path, bad, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    transport = wire({})
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    body = {"items": [{"file_path": to_file_uri(str(video)), "number": NUMBER, "source": bad}], "mode": "refresh_full"}
    events = _sse(client.post("/api/batch-enrich", json=body).text)
    _assert_batch_refused(events, batch_spies, transport, 1, tmp_path)
    assert "退回" not in caplog.text  # 拒絕在 fallback 之前：不得先 log「退回 auto」


def test_batch_refuses_custom_on_readonly_item(client, env, wire, batch_spies, tmp_path, mocker):
    transport = wire(TWO_VERSION_ROUTES)
    _ready(env, "two-step", TWO_STEP)
    src = tmp_path / "src"
    src.mkdir()
    video = src / "SONE-205.mp4"
    video.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    mocker.patch("web.routers.scraper.load_config", return_value=_ro_config(src, out))
    body = {"items": [{"file_path": to_file_uri(str(video)), "number": NUMBER, "source": "custom:two-step"}],
            "mode": "fill_missing"}
    events = _sse(client.post("/api/batch-enrich", json=body).text)
    _assert_batch_refused(events, batch_spies, transport, 1, tmp_path)


def test_batch_builtin_source_still_goes_through(client, env, wire, batch_spies, tmp_path):
    from core.enricher import EnrichResult
    batch_spies["enrich_single"].return_value = EnrichResult(
        success=True, nfo_written=True, cover_written=True, extrafanart_written=0,
        fields_filled=["title"], source_used="javbus", error=None)
    video = tmp_path / "SONE-205.mp4"
    video.write_bytes(b"x")
    body = {"items": [{"file_path": to_file_uri(str(video)), "number": NUMBER, "source": "javbus"}], "mode": "refresh_full"}
    events = _sse(client.post("/api/batch-enrich", json=body).text)
    assert events[-1]["summary"]["success"] == 1
    batch_spies["search_jav"].assert_called_once()
