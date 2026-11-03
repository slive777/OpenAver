"""Integration tests for AI tags backfill routes + scan hook (TASK-188c-T5)."""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from core.ai_services import tags_backfill, tags_state
from core.config import load_config, save_config
from core.database import Video, VideoRepository
from core.path_utils import to_file_uri
from tests.unit._custom_source_fake import finalize_root  # noqa: PLC2701
from web.app import app

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")


def _reset_state(monkeypatch) -> None:
    for name, val in (
        ("_JOB_LOCK", threading.Lock()),
        ("_STATE_LOCK", threading.Lock()),
        ("_STOP", threading.Event()),
        ("_rerun", False),
    ):
        monkeypatch.setattr(tags_backfill, name, val)
    for name, val in (
        ("unreachable", False),
        ("last_success_at", None),
        ("last_persist_mono", None),
        ("notified", False),
        ("notification_sink", None),
        (
            "job",
            {
                "kind": None,
                "done": 0,
                "skipped": 0,
                "slow": False,
                "waiting": False,
                "stop_reason": None,
                "outcome": None,
            },
        ),
    ):
        monkeypatch.setattr(tags_state._STATE, name, val)


def _workers() -> list:
    return [t for t in threading.enumerate() if t.name == tags_backfill.THREAD_NAME]


def _join_workers(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    for t in _workers():
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            pytest.fail("tags-backfill worker did not finish in time")


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    _reset_state(monkeypatch)
    yield
    tags_backfill.request_stop()
    _join_workers()


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    save_config(load_config())
    finalize_root(root)
    return root


def _enable_ollama_tags():
    cfg = load_config()
    tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
    tags["enabled"] = True
    tags["provider"] = "ollama"
    tags["model"] = "m"
    save_config(cfg)


def _seed_video(db, tmp_path, *, number: str, cover: bool = True) -> str:
    path = to_file_uri(str(tmp_path / f"{number}.mp4"))
    VideoRepository(db).upsert(
        Video(
            path=path,
            number=number,
            cover_path="cover.jpg" if cover else "",
        )
    )
    return path


@pytest.mark.parametrize("case", ["enabled", "disabled", "hook_raises"])
def test_scan_done_triggers_tags_incremental_only_when_enabled(
    case, isolate_reconcile_db, tmp_path, monkeypatch, mocker
):
    """開了 AI 標籤、按「更新片庫」→ 沒跑過的片被標；沒開卻照樣花錢；或掃描卡住不結束。"""
    from core.gallery_scanner import VideoInfo
    from web.routers.scanner import generate_avlist

    db = isolate_reconcile_db
    pending_paths = [
        _seed_video(db, tmp_path, number="PEND-001"),
        _seed_video(db, tmp_path, number="PEND-002"),
    ]
    calls: list[str] = []

    def fake_tag_one(path: str):
        calls.append(path)
        repo = VideoRepository(db)
        cur = list(repo.get_by_path(path).user_tags or [])
        repo.update_user_tags(path, cur + ["校服"], ai_tagged=True)

    monkeypatch.setattr(tags_backfill, "_tag_one", fake_tag_one)
    tags_cfg = {"ai_services": {"tags": {"enabled": case == "enabled"}}}
    monkeypatch.setattr(tags_backfill, "load_config", lambda: tags_cfg)

    src = tmp_path / "src"
    src.mkdir()
    (src / "v.mp4").write_bytes(b"x" * 2048)
    out = tmp_path / "html_out"
    out.mkdir()
    scan_cfg = {
        "gallery": {
            "directories": [str(src)],
            "output_dir": str(out),
            "path_mappings": {},
            "min_size_mb": 0,
        },
        "search": {"proxy_url": ""},
        "general": {"theme": "light"},
        "scraper": {"video_extensions": [".mp4"]},
    }
    monkeypatch.setattr("web.routers.scanner.load_config", lambda: scan_cfg)
    monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: tmp_path / "test.db")
    mocker.patch(
        "web.routers.scanner.VideoScanner.scan_file",
        lambda self, p, base_path=None: VideoInfo(
            path=to_file_uri(p), title="t", num="ABC-001"
        ),
    )
    mocker.patch("web.routers.scanner.HTMLGenerator")
    mocker.patch("web.routers.scanner._emit_notif")
    mocker.patch("web.routers.scanner.similar_index.schedule_incremental")

    if case == "hook_raises":
        hook = mocker.patch(
            "web.routers.scanner.tags_backfill.schedule_incremental",
            side_effect=RuntimeError("boom"),
        )
        chunks = list(generate_avlist())
        events = [
            json.loads(line[6:])
            for c in chunks
            for line in c.split("\n")
            if line.startswith("data: ")
        ]
        assert [e for e in events if e.get("type") == "done"], f"done 事件缺席：{events}"
        assert hook.call_count == 1
        return

    list(generate_avlist())
    _join_workers()

    if case == "disabled":
        assert tags_state.snapshot()["job"]["kind"] is None
        assert len(calls) == 0
        return

    assert sorted(calls) == sorted(pending_paths)
    assert len(calls) == 2
    total, pending = VideoRepository(db).count_ai_tag_progress()
    assert total == 2
    assert pending == 0


@pytest.mark.parametrize(
    "case",
    ["rebuild_keeps_user_tags", "rebuild_refused_while_running"],
)
def test_rebuild_is_additive_and_refused_while_running(
    case, isolate_reconcile_db, tmp_path, monkeypatch, data_root
):
    """按「全部重建」→ 自己打的標籤不見；或補完全庫跑到一半又按重建，進度被清掉重來。"""
    db = isolate_reconcile_db
    _enable_ollama_tags()

    tagged = _seed_video(db, tmp_path, number="TAG-001")
    pending_with = _seed_video(db, tmp_path, number="PEND-001")
    pending_empty = _seed_video(db, tmp_path, number="PEND-002")
    repo = VideoRepository(db)
    repo.update_user_tags(tagged, ["待看"], ai_tagged=True)
    repo.update_user_tags(pending_with, ["待看"])

    if case == "rebuild_keeps_user_tags":
        calls: list[str] = []

        def fake_tag_one(path: str):
            calls.append(path)
            r = VideoRepository(db)
            cur = list(r.get_by_path(path).user_tags or [])
            r.update_user_tags(path, cur + ["校服"], ai_tagged=True)

        monkeypatch.setattr(tags_backfill, "_tag_one", fake_tag_one)
        before = {
            p: list(VideoRepository(db).get_by_path(p).user_tags or [])
            for p in (tagged, pending_with, pending_empty)
        }

        with TestClient(app) as c:
            resp = c.post("/api/ai/tags/backfill/rebuild")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "status": "started"}
        _join_workers()

        for p in (tagged, pending_with, pending_empty):
            after = list(VideoRepository(db).get_by_path(p).user_tags or [])
            assert set(before[p]).issubset(set(after)), (p, before[p], after)
            assert "校服" in after
        assert VideoRepository(db).count_ai_tag_progress()[1] == 0
        return

    # rebuild_refused_while_running
    entered = threading.Event()
    release = threading.Event()

    def blocking_tag_one(path: str):
        entered.set()
        release.wait(10)
        r = VideoRepository(db)
        cur = list(r.get_by_path(path).user_tags or [])
        r.update_user_tags(path, cur + ["校服"], ai_tagged=True)

    monkeypatch.setattr(tags_backfill, "_tag_one", blocking_tag_one)

    with TestClient(app) as c:
        start = c.post("/api/ai/tags/backfill")
        assert start.status_code == 200
        assert start.json() == {"ok": True, "status": "started"}
        assert entered.wait(10), "worker did not enter stub"
        tagged_before = c.get("/api/ai/tags/backfill/status").json()["tagged"]
        rebuild = c.post("/api/ai/tags/backfill/rebuild")
        assert rebuild.status_code == 200
        assert rebuild.json() == {"ok": False, "status": "already_running"}
        tagged_after = c.get("/api/ai/tags/backfill/status").json()["tagged"]
        assert tagged_after == tagged_before
        c.post("/api/ai/tags/backfill/stop")
        release.set()
    _join_workers()


@pytest.mark.parametrize(
    "case",
    ["not_enabled", "not_configured", "nothing_to_do"],
)
def test_backfill_preflight_says_why_nothing_started(
    case, isolate_reconcile_db, tmp_path, monkeypatch, data_root
):
    """開關沒開或連線沒設好時按「補完全庫」→ 就地看到原因，不起一份馬上停的 job。"""
    calls: list[str] = []

    def fake_tag_one(path: str):
        calls.append(path)
        raise AssertionError("_tag_one must not be called")

    monkeypatch.setattr(tags_backfill, "_tag_one", fake_tag_one)

    if case == "not_enabled":
        # default: enabled false
        expected = "not_enabled"
    elif case == "not_configured":
        cfg = load_config()
        tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
        tags["enabled"] = True
        tags["provider"] = ""
        tags["model"] = ""
        save_config(cfg)
        expected = "not_configured"
    else:
        _enable_ollama_tags()
        # empty library → pending == 0
        expected = "nothing_to_do"

    with TestClient(app) as c:
        resp = c.post("/api/ai/tags/backfill")
        assert resp.status_code == 200
        assert resp.json() == {"ok": False, "status": expected}
        st = c.get("/api/ai/tags/backfill/status").json()
        assert st["running"] is False
        assert st["resumable"] is False
    assert len(calls) == 0
