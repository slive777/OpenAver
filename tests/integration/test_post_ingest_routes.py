"""入庫後 AI 掛勾的接線判別式（189a-T5）：誰在什麼條件下呼叫 post_ingest.run_after_ingest。

決策與 lane 由 test_post_ingest_decide／test_post_ingest_lanes 守；本檔只守三條入庫路的接線。
"""
import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.ai_services import post_ingest
from core.auto_organize import run_one_round
from core.database import Video
from core.enricher import EnrichResult
from core import path_utils
from core.path_utils import coerce_to_file_uri, to_file_uri, uri_to_fs_path

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

ENRICH_FILE = "/video/ABC-001.mp4"
RO_DIR = "/ro/lib"
RO_FILE = "/ro/lib/ABC-001.mp4"
NEW_FILE = "/organized/ABC-001/ABC-001.mp4"


@pytest.fixture(autouse=True)
def _lanes(monkeypatch):
    monkeypatch.setattr(post_ingest, "_LANES", {})
    yield
    lanes = list(post_ingest._LANES.values())
    for lane in lanes:
        lane.queue.put(None)
    for lane in lanes:
        lane.thread.join(5)
        if lane.thread.is_alive():
            pytest.fail(f"lane thread {lane.item} did not stop")
    assert not [t.name for t in threading.enumerate() if t.name.startswith("post-ingest-")]


class Env:
    def __init__(self, client, mocker, tmp_path, monkeypatch):
        self.client, self.mocker, self.tmp_path = client, mocker, tmp_path
        self.hook_calls, self.round_starts = [], []
        monkeypatch.setattr(
            post_ingest, "run_after_ingest",
            lambda *a, **k: self.hook_calls.append((a, k)),
        )
        monkeypatch.setattr(
            post_ingest, "begin_round", lambda: self.round_starts.append(1),
        )


@pytest.fixture
def env(client, mocker, tmp_path, monkeypatch):
    return Env(client, mocker, tmp_path, monkeypatch)


def _ok(**kw):
    return EnrichResult(success=True, nfo_written=True, cover_written=True,
                        extrafanart_written=0, fields_filled=[], source_used="db",
                        error=None, **kw)


def _fail():
    return EnrichResult(success=False, nfo_written=False, cover_written=False,
                        extrafanart_written=0, fields_filled=[], source_used="",
                        error="boom")


def _scrape(env, inflow="synced", ok=True):
    org = {"success": True, "new_filename": NEW_FILE} if ok else {"success": False, "error": "x"}
    env.mocker.patch("web.routers.scraper.organize_file", return_value=org)
    env.mocker.patch("web.routers.scraper.try_inflow_upsert", return_value=inflow)
    resp = env.client.post("/api/scrape-single", json={
        "file_path": "/dummy/ABC-001.mp4", "number": "ABC-001",
        "metadata": {"number": "ABC-001", "title": "T"},
    })
    assert resp.status_code == 200
    return to_file_uri(NEW_FILE, {})


def _enrich(env, *, mode, overwrite, ok=True, preserve=False):
    env.mocker.patch("web.routers.scraper.enrich_single",
                     return_value=_ok() if ok else _fail())
    resp = env.client.post("/api/enrich-single", json={
        "file_path": ENRICH_FILE, "number": "ABC-001",
        "mode": mode, "overwrite_existing": overwrite, "preserve_title": preserve,
    })
    assert resp.status_code == 200
    return coerce_to_file_uri(ENRICH_FILE, {})


def _enrich_mapped(env, monkeypatch):
    """設了 path_mappings 且裸路徑命中映射：掛勾拿到的鍵要等於 enricher 寫 DB 的鍵（不套映射）。"""
    monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
    mappings = {"/nas/share": "//NAS/share"}
    bare = "/nas/share/ABC-001.mp4"
    env.mocker.patch("web.routers.scraper.load_config", return_value={
        "gallery": {"path_mappings": mappings}, "search": {}, "scraper": {}})
    env.mocker.patch("web.routers.scraper.enrich_single", return_value=_ok())
    resp = env.client.post("/api/enrich-single", json={
        "file_path": bare, "number": "ABC-001", "mode": "refresh_full", "overwrite_existing": True})
    assert resp.status_code == 200
    db_key = to_file_uri(uri_to_fs_path(bare))  # enricher 寫 DB 用的鍵（core/enricher.py:585）
    assert db_key != coerce_to_file_uri(bare, mappings)  # 映射真的會改鍵，本案才不是空轉
    return db_key


def _readonly(env, action, preserve=False):
    env.mocker.patch("web.routers.scraper.load_config", return_value={
        "gallery": {"directories": [{"path": RO_DIR, "readonly": True}], "path_mappings": {}},
        "search": {}, "scraper": {},
    })
    source = MagicMock()
    source.path = RO_DIR
    env.mocker.patch("web.routers.scraper.resolve_owning_output_root",
                     return_value=(source, "/out/ro", "file:///out/ro"))
    env.mocker.patch("web.routers.scraper.enrich_one_readonly", return_value=_ok())
    resp = env.client.post("/api/enrich-single", json={
        "file_path": RO_FILE, "number": "ABC-001", "readonly_action": action,
        "preserve_title": preserve,
    })
    assert resp.status_code == 200
    return coerce_to_file_uri(RO_FILE, {})


def _batch(env):
    env.mocker.patch("web.routers.scraper.search_jav",
                     return_value={"title": "stub", "source": "javbus"})
    env.mocker.patch("web.routers.scraper.enrich_single", return_value=_ok())
    resp = env.client.post("/api/batch-enrich", json={
        "items": [{"file_path": ENRICH_FILE, "number": "ABC-001"}],
        "mode": "refresh_full", "overwrite_existing": True,
    })
    assert resp.status_code == 200
    return None


def _round(env, statuses):
    fav = env.tmp_path / "fav"
    fav.mkdir()
    for name in statuses:
        (fav / name).write_bytes(b"x" * 1024)
    out = env.tmp_path / "out"
    config = {
        "search": {"favorite_folder": str(fav)},
        "scraper": {"video_extensions": [".mp4"]},
        "gallery": {"min_size_mb": 0, "path_mappings": {}, "directories": []},
        "translate": {"enabled": False},
    }
    env.mocker.patch("core.auto_organize.smart_search", side_effect=lambda number, uncensored_mode=False: [
        {"number": number, "title": f"t-{number}", "actors": []}])
    env.mocker.patch("core.auto_organize.organize_file", side_effect=lambda fp, md, cfg: {
        "success": True, "new_filename": str(out / Path(fp).name), "cover_path": "/c.jpg"})
    env.mocker.patch("core.auto_organize.try_inflow_upsert",
                     side_effect=lambda target, old_file_path=None: statuses[Path(target).name])
    env.mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
    run_one_round(config)
    synced = [n for n, s in statuses.items() if s == "synced"]
    return to_file_uri(str(out / synced[0]), {}) if synced else None


SHOULD_CALL = [
    pytest.param(lambda e: _scrape(e), "scrape_single", True, False, False, id="scrape_single"),
    pytest.param(lambda e: _enrich(e, mode="refresh_full", overwrite=True),
                 "enrich_rescrape", True, False, False, id="enrich_rescrape"),
    pytest.param(lambda e: _enrich(e, mode="refresh_full", overwrite=True, preserve=True),
                 "enrich_rescrape", True, False, True, id="enrich_rescrape_preserve_title"),
    pytest.param(_enrich_mapped, "enrich_rescrape", True, False, False,
                 id="enrich_rescrape_path_mapped"),
    pytest.param(lambda e: _readonly(e, "rescrape"), "readonly_rescrape", True, False, False,
                 id="readonly_rescrape"),
    pytest.param(lambda e: _readonly(e, "rescrape", preserve=True),
                 "readonly_rescrape", True, False, True, id="readonly_rescrape_preserve_title"),
    pytest.param(lambda e: _round(e, {"AAA-001.mp4": "synced", "BBB-002.mp4": "not_linked"}),
                 "auto_organize", False, True, False, id="auto_organize"),
]


@pytest.mark.parametrize("run, route, skip_faces, notify, skip_translate", SHOULD_CALL)
def test_hook_called_on_rows_that_should(env, monkeypatch, run, route, skip_faces, notify,
                                         skip_translate):
    uri = run(env, monkeypatch) if run is _enrich_mapped else run(env)
    assert len(env.hook_calls) == 1
    args, kwargs = env.hook_calls[0]
    assert args == (uri,)
    assert kwargs["route"] == route
    assert kwargs["skip_faces"] is skip_faces
    assert kwargs.get("notify", False) is notify
    assert kwargs.get("skip_translate", False) is skip_translate
    assert len(env.round_starts) == (1 if route == "auto_organize" else 0)


SHOULD_NOT_CALL = [
    pytest.param(lambda e: _scrape(e, inflow="not_linked"), id="scrape_not_linked"),
    pytest.param(lambda e: _scrape(e, ok=False), id="scrape_failed"),
    pytest.param(lambda e: _enrich(e, mode="refresh_full", overwrite=False),
                 id="enrich_refresh_no_overwrite"),
    pytest.param(lambda e: _enrich(e, mode="fill_missing", overwrite=True),
                 id="enrich_fill_missing"),
    pytest.param(lambda e: _enrich(e, mode="refresh_full", overwrite=True, ok=False),
                 id="enrich_failed"),
    pytest.param(lambda e: _readonly(e, "ingest"), id="readonly_ingest"),
    pytest.param(_batch, id="batch_enrich"),
    pytest.param(lambda e: _round(e, {"AAA-001.mp4": "not_linked"}), id="round_not_linked"),
]


@pytest.mark.parametrize("run", SHOULD_NOT_CALL)
def test_hook_not_called_on_rows_that_should_not(env, run):
    run(env)
    assert env.hook_calls == []


class _Repo:
    def __init__(self, row):
        self.row = row

    def get_by_path(self, _path):
        return self.row


def test_scrape_single_returns_200_while_translation_blocked(client, mocker, monkeypatch, caplog):
    started, release = threading.Event(), threading.Event()
    cfg = {"translate": {"enabled": True}, "general": {"locale": "zh-TW"},
           "ai_services": {"image_similar": {"enabled": False}, "tags": {"enabled": False}}}
    row = Video(path=to_file_uri(NEW_FILE, {}), number="ABC-001", title="これはテスト",
                nfo_mtime=1.0, cover_path="")
    monkeypatch.setattr(post_ingest, "load_config", lambda: cfg)
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: _Repo(row))

    def fake_translate(ctx):
        started.set()
        release.wait(10)

    monkeypatch.setattr(post_ingest, "_job_translate", fake_translate)
    mocker.patch("web.routers.scraper.organize_file",
                     return_value={"success": True, "new_filename": NEW_FILE})
    mocker.patch("web.routers.scraper.try_inflow_upsert", return_value="synced")
    done, box = threading.Event(), {}

    def post():
        box["resp"] = client.post("/api/scrape-single", json={
            "file_path": "/dummy/ABC-001.mp4", "number": "ABC-001",
            "metadata": {"number": "ABC-001", "title": "T"},
        })
        done.set()

    try:
        with caplog.at_level(logging.INFO, logger=post_ingest.logger.name):
            t = threading.Thread(target=post, daemon=True)
            t.start()
            if not done.wait(5):
                pytest.fail("scrape-single 回應被翻譯 job 擋住")
            assert box["resp"].status_code == 200
            assert box["resp"].json()["success"] is True
            assert started.wait(5)
    finally:
        release.set()
    t.join(5)
    assert "[post_ingest] route=scrape_single" in caplog.text
