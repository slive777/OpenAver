"""TASK-198a-T2a — repo 層：I1 oracle-2、I5 四入口不洗探針欄。"""
from __future__ import annotations

import json
import sqlite3

import pytest

from core.database import Video, VideoRepository
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri


def _ok(*, width=3840, height=2160, video_format="HEVC", duration_ms=7_200_000) -> ProbeResult:
    return ProbeResult(
        status="ok",
        reason="",
        width=width,
        height=height,
        video_format=video_format,
        duration_ms=duration_ms,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=12_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=("zh",),
        truncated=False,
    )


def _probe_snapshot(db_path, path: str) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT media_probe_status, media_probe_mtime, media_probe_size, "
            "media_width, media_height, media_video_format, media_duration_ms, "
            "media_hdr_format, media_frame_rate, media_bitrate, media_container, "
            "media_audio_langs, media_subtitle_langs, media_truncated "
            "FROM videos WHERE path = ?",
            (path,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    keys = (
        "media_probe_status",
        "media_probe_mtime",
        "media_probe_size",
        "media_width",
        "media_height",
        "media_video_format",
        "media_duration_ms",
        "media_hdr_format",
        "media_frame_rate",
        "media_bitrate",
        "media_container",
        "media_audio_langs",
        "media_subtitle_langs",
        "media_truncated",
    )
    return dict(zip(keys, row, strict=True))


def test_stale_key_write_is_rejected(temp_db):
    """I1 oracle-2：以舊 (mtime,size) 呼叫 update_media_probe → False、列不變。"""
    repo = VideoRepository(temp_db)
    path = to_file_uri("/media/stale_key.mp4")
    repo.upsert(Video(path=path, title="片", mtime=100.0, size_bytes=1000))

    assert repo.update_media_probe(path, _ok(), 100.0, 1000) is True
    before = _probe_snapshot(temp_db, path)
    assert before["media_height"] == 2160
    assert before["media_probe_mtime"] == 100.0

    # 列已被掃描改成新 key；舊 key 寫入必須被拒
    repo.upsert(Video(path=path, title="片", mtime=200.0, size_bytes=2000))
    assert repo.update_media_probe(path, _ok(height=1080, width=1920), 100.0, 1000) is False
    after = _probe_snapshot(temp_db, path)
    assert after == before


@pytest.mark.parametrize(
    "entry",
    ["upsert", "insert_if_ignore", "upsert_batch", "repath"],
)
def test_builders_preserve_media_probe(temp_db, entry):
    """I5：四個寫入口之後 media_*／media_probe_* 原值保留。"""
    repo = VideoRepository(temp_db)
    path = to_file_uri(f"/media/preserve_{entry}.mp4")
    new_path = to_file_uri(f"/media/preserve_{entry}_new.mp4")
    repo.upsert(Video(path=path, title="原標題", mtime=50.0, size_bytes=5000))

    assert repo.update_media_probe(path, _ok(), 50.0, 5000) is True
    before = _probe_snapshot(temp_db, path)
    assert before["media_probe_status"] == "ok"
    assert before["media_height"] == 2160
    assert before["media_audio_langs"] == json.dumps(["ja"], ensure_ascii=False)

    touched = Video(path=path, title="改標題", mtime=50.0, size_bytes=5000)
    if entry == "upsert":
        repo.upsert(touched)
        target = path
    elif entry == "insert_if_ignore":
        repo.insert_if_ignore(touched)
        target = path
    elif entry == "upsert_batch":
        repo.upsert_batch([touched])
        target = path
    else:
        moved = Video(path=new_path, title="改標題", mtime=50.0, size_bytes=5000)
        repo.repath(path, new_path, moved)
        target = new_path

    after = _probe_snapshot(temp_db, target)
    assert after == before
