"""影片資訊讀取提醒端點（TASK-198a-T5）：N 算對、不再提醒讀寫、原生庫不可用。"""

from __future__ import annotations

import pytest

from core import media_probe_backfill
from core.config import load_config, save_config
from core.database import Video, VideoRepository
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

MTIME, SIZE = 1_700_000_000.0, 1234


@pytest.fixture(autouse=True)
def _fresh_job_state():
    media_probe_backfill._reset_for_tests()
    yield
    media_probe_backfill._reset_for_tests()


def _probe(status: str) -> ProbeResult:
    ok = status == "ok"
    return ProbeResult(
        status=status, reason="", width=1920 if ok else None, height=1080 if ok else None,
        video_format="AVC" if ok else None, duration_ms=60_000 if ok else None,
        hdr_format=None, frame_rate=None, overall_bitrate=None, container=None,
        audio_langs=(), subtitle_langs=(), truncated=False,
    )


def _seed(tmp_path, layout: tuple) -> None:
    """layout = (可寫從未讀, 可寫讀失敗, 可寫已讀, 唯讀從未讀, 唯讀讀失敗, 唯讀已讀)。"""
    wr, ro = tmp_path / "wr", tmp_path / "ro"
    cfg = load_config()
    cfg["gallery"]["directories"] = [
        {"path": str(wr), "readonly": False, "output_path": ""},
        {"path": str(ro), "readonly": True, "output_path": str(tmp_path / "ro_out")},
    ]
    save_config(cfg)
    repo = VideoRepository()
    kinds = (None, "no_video", "ok")
    for i, count in enumerate(layout):
        base, kind = (wr, ro)[i // 3], kinds[i % 3]
        for n in range(count):
            path = to_file_uri(str(base / f"V{i}-{n}.mp4"))
            repo.upsert(Video(path=path, mtime=MTIME, size_bytes=SIZE))
            if kind:
                repo.update_media_probe(path, _probe(kind), MTIME, SIZE)


def _status(client) -> dict:
    r = client.get("/api/media-probe/status")
    assert r.status_code == 200
    return r.json()


def _post_settings(client, body: dict) -> dict:
    r = client.post("/api/media-probe/settings", json=body)
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize(
    "layout, writable_n, readonly_n",
    [((1, 2, 1, 1, 1, 1), 1, 1), ((0, 0, 1, 1, 0, 0), 0, 1)],
    ids=["mixed", "only_readonly_unread"],
)
def test_pending_count_follows_readonly_opt_in(client, tmp_path, layout, writable_n, readonly_n):
    _seed(tmp_path, layout)
    s = _status(client)
    assert (s["include_readonly"], s["pending"], s["readonly_pending"]) == (False, writable_n, readonly_n)

    s = _post_settings(client, {"include_readonly": True})
    assert (s["include_readonly"], s["pending"], s["readonly_pending"]) == (True, writable_n + readonly_n, readonly_n)
    assert _status(client)["pending"] == writable_n + readonly_n

    s = _post_settings(client, {"include_readonly": False})
    assert (s["pending"], s["readonly_pending"]) == (writable_n, readonly_n)


def test_dismissed_roundtrip_keeps_other_key(client):
    assert _status(client)["dismissed"] is False
    assert _post_settings(client, {"dismissed": True})["dismissed"] is True
    assert _status(client)["dismissed"] is True

    s = _post_settings(client, {"include_readonly": True})
    assert (s["dismissed"], s["include_readonly"]) == (True, True)

    s = _post_settings(client, {"dismissed": False})
    assert (s["dismissed"], s["include_readonly"]) == (False, True)
    assert _status(client)["dismissed"] is False


def test_unavailable_blocks_start(client, monkeypatch):
    monkeypatch.setattr("core.media_probe.is_available", lambda: False)
    assert _status(client)["available"] is False
    r = client.post("/api/media-probe/start")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "status": "unavailable"}

    monkeypatch.setattr("core.media_probe.is_available", lambda: True)
    assert _status(client)["available"] is True
    r = client.post("/api/media-probe/start")
    assert r.status_code == 200
    assert r.json()["status"] == "nothing_to_do"


@pytest.mark.parametrize(
    "case",
    ["failed_key_match", "failed_key_stale", "never_read", "ok_key_match"],
    ids=["failed_key_match", "failed_key_stale", "never_read", "ok_key_match"],
)
def test_pending_definition_follows_probe_key(tmp_path, case):
    """I-PEND：pending 的定義跟著探針 key（status 非 NULL 且 key＝列當前）。"""
    wr_uri = to_file_uri(str(tmp_path / "wr"))
    repo = VideoRepository()
    main = to_file_uri(str(tmp_path / "wr" / f"{case}.mp4"))
    ctrl = to_file_uri(str(tmp_path / "wr" / "ctrl-never-read.mp4"))
    repo.upsert(Video(path=main, mtime=MTIME, size_bytes=SIZE))
    repo.upsert(Video(path=ctrl, mtime=MTIME, size_bytes=SIZE))
    if case in ("failed_key_match", "failed_key_stale"):
        assert repo.update_media_probe(main, _probe("no_video"), MTIME, SIZE) is True
    elif case == "ok_key_match":
        assert repo.update_media_probe(main, _probe("ok"), MTIME, SIZE) is True
    if case == "failed_key_stale":
        repo.upsert(Video(path=main, mtime=MTIME + 1, size_bytes=SIZE))
    view = repo.get_media_probe_view(main)
    assert view is not None
    if case == "failed_key_match":
        assert view.media_probe_status == "failed"
        assert view.key_matches is True
    elif case == "failed_key_stale":
        assert view.media_probe_status == "failed"
        assert view.key_matches is False
    elif case == "never_read":
        assert view.media_probe_status is None
    else:
        assert view.key_matches is True
    pending = repo.list_media_probe_pending(
        include_readonly=False,
        readonly_prefixes=[],
        writable_prefixes=[wr_uri],
        configured_dir_uris={wr_uri},
    )
    got = {p for p, _m, _s in pending}
    if case in ("failed_key_stale", "never_read"):
        assert main in got
    else:
        assert main not in got
    assert ctrl in got


def test_failed_probe_clears_reminder_until_file_changes(client, tmp_path, monkeypatch):
    """failed＋key 相符 → 提醒歸零、start 回 nothing_to_do；換檔後重算待讀。"""
    monkeypatch.setattr("core.media_probe.is_available", lambda: True)
    _seed(tmp_path, (0, 1, 0, 0, 0, 0))
    assert _status(client)["pending"] == 0
    r = client.post("/api/media-probe/start")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "status": "nothing_to_do"}
    target = to_file_uri(str(tmp_path / "wr" / "V1-0.mp4"))
    repo = VideoRepository()
    view = repo.get_media_probe_view(target)
    assert view is not None
    assert view.media_probe_status == "failed"
    assert view.key_matches is True
    repo.upsert(Video(path=target, mtime=MTIME + 1, size_bytes=SIZE))
    assert _status(client)["pending"] == 1
