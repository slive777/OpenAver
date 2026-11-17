"""tests/unit/test_media_probe_force.py — TASK-200b-T6（probe_now 結果表）。

probe_now：不經背景 worker 的同步探針。順序：副檔名略過 → 前 stat →
磁碟 vs DB 比對（changed）→ probe_file → 後 stat 比對 → update_media_probe。
"""
import os
import sqlite3
import threading

import pytest

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.media_probe_force import probe_now
from core.path_utils import to_file_uri


def _ok(*, width=3840, height=2160, video_format="HEVC", duration_ms=7_200_000):
    return ProbeResult(
        status="ok", reason="", width=width, height=height,
        video_format=video_format, duration_ms=duration_ms,
        hdr_format=None, frame_rate=23.976, overall_bitrate=12_000_000,
        container="MPEG-4", audio_langs=("ja",), subtitle_langs=("zh",),
        truncated=False,
    )


def _unreadable():
    return ProbeResult(
        status="unreadable", reason="io error", width=None, height=None,
        video_format=None, duration_ms=None, hdr_format=None, frame_rate=None,
        overall_bitrate=None, container=None, audio_langs=(),
        subtitle_langs=(), truncated=False,
    )


def _failed():
    result = _ok()
    return ProbeResult(
        status="no_video", reason="no stream", width=result.width,
        height=result.height, video_format=result.video_format,
        duration_ms=result.duration_ms, hdr_format=None, frame_rate=None,
        overall_bitrate=None, container=None, audio_langs=(),
        subtitle_langs=(), truncated=False,
    )


def _seed(tmp_path, name, *, content=b"fake-video-bytes-0123456789"):
    fs = tmp_path / name
    fs.write_bytes(content)
    st = os.stat(fs)
    mtime = float(st.st_mtime)
    size = st.st_size
    video_uri = to_file_uri(str(fs), {})
    db_path = tmp_path / f"{fs.stem}.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([Video(
        path=video_uri, number=fs.stem, title=fs.stem,
        mtime=mtime, size_bytes=size,
    )])
    return repo, db_path, video_uri, str(fs), mtime, size


def _probe_view(repo, video_uri):
    return repo.get_media_probe_view(video_uri)


_CASES = [
    "stale",
    "unreadable_pre_stat",
    "unreadable_post_stat_differs",
    "probe_unreadable",
    "skipped_strm",
    "timeout",
    "changed_size",
    "changed_mtime_over_1s",
    "changed_db_null",
    "ok_mtime_within_1s",
]


@pytest.mark.parametrize("case", _CASES)
def test_probe_now_outcomes(tmp_path, mocker, case):
    """probe_now 十個出口各一格；unreadable／stale／changed／skipped 時 DB 位元不變。"""
    if case == "skipped_strm":
        fs = tmp_path / "CLIP-001.strm"
        fs.write_bytes(b"http://example.invalid/stream")
        st = os.stat(fs)
        mtime, size = float(st.st_mtime), st.st_size
        video_uri = to_file_uri(str(fs), {})
        db_path = tmp_path / "strm.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([Video(
            path=video_uri, number="CLIP-001", title="CLIP-001",
            mtime=mtime, size_bytes=size,
        )])
        spy = mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("must not probe .strm"))
        result = probe_now(repo, video_uri, str(fs), mtime, size)
        assert result == "skipped"
        assert _probe_view(repo, video_uri).media_probe_status is None
        spy.assert_not_called()
        return

    if case == "unreadable_pre_stat":
        repo, _db, video_uri, fs_path, mtime, size = _seed(tmp_path, "PRE-001.mp4")
        assert repo.update_media_probe(video_uri, _ok(), mtime, size) is True
        before = _probe_view(repo, video_uri)
        os.unlink(fs_path)
        result = probe_now(repo, video_uri, fs_path, mtime, size)
        assert result == "unreadable"
        after = _probe_view(repo, video_uri)
        assert (after.media_width, after.media_probe_mtime) == (before.media_width, before.media_probe_mtime)
        return

    if case == "timeout":
        repo, _db, video_uri, fs_path, mtime, size = _seed(tmp_path, "TMO-001.mp4")
        entered = threading.Event()
        release = threading.Event()

        def _hang(_path):
            entered.set()
            release.wait(timeout=10)
            return _ok()

        mocker.patch("core.media_probe.probe_file", side_effect=_hang)
        try:
            result = probe_now(repo, video_uri, fs_path, mtime, size, timeout=0.2)
            assert result == "timeout"
            assert _probe_view(repo, video_uri).media_probe_status is None
        finally:
            release.set()
            entered.wait(timeout=5)
            for thread in threading.enumerate():
                if thread.name == "media-probe-force":
                    thread.join(timeout=10)
        return

    if case == "stale":
        repo, db_path, video_uri, fs_path, mtime, size = _seed(tmp_path, "STALE-001.mp4")

        def _bump_db_key(_path):
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    "UPDATE videos SET mtime = ?, size_bytes = ? WHERE path = ?",
                    (mtime + 100.0, size + 100, video_uri),
                )
                conn.commit()
            finally:
                conn.close()
            return _ok(width=1280, height=720)

        mocker.patch("core.media_probe.probe_file", side_effect=_bump_db_key)
        result = probe_now(repo, video_uri, fs_path, mtime, size)
        assert result == "stale"
        assert _probe_view(repo, video_uri).media_probe_status is None
        return

    repo, _db, video_uri, fs_path, mtime, size = _seed(
        tmp_path,
        {
            "unreadable_post_stat_differs": "POST-001.mp4",
            "probe_unreadable": "UNR-001.mp4",
            "changed_size": "CHG-001.mp4",
            "changed_mtime_over_1s": "CHGM-001.mp4",
            "changed_db_null": "CHGN-001.mp4",
            "ok_mtime_within_1s": "OK-001.mp4",
        }[case],
    )

    if case == "changed_db_null":
        mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("changed must not probe"))
        result = probe_now(repo, video_uri, fs_path, None, None)
        assert result == "changed"
        assert _probe_view(repo, video_uri).media_probe_status is None
        return

    if case == "changed_size":
        assert repo.update_media_probe(video_uri, _ok(), mtime, size) is True
        before = _probe_view(repo, video_uri)
        mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("changed must not probe"))
        result = probe_now(repo, video_uri, fs_path, mtime, size + 999)
        assert result == "changed"
        after = _probe_view(repo, video_uri)
        assert (after.media_width, after.media_probe_size) == (before.media_width, before.media_probe_size)
        return

    if case == "changed_mtime_over_1s":
        assert repo.update_media_probe(video_uri, _ok(), mtime, size) is True
        before = _probe_view(repo, video_uri)
        mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("changed must not probe"))
        result = probe_now(repo, video_uri, fs_path, mtime + 5.0, size)
        assert result == "changed"
        after = _probe_view(repo, video_uri)
        assert (after.media_width, after.media_probe_mtime) == (before.media_width, before.media_probe_mtime)
        return

    if case == "probe_unreadable":
        assert repo.update_media_probe(video_uri, _ok(), mtime, size) is True
        before = _probe_view(repo, video_uri)
        mocker.patch("core.media_probe.probe_file", return_value=_unreadable())
        result = probe_now(repo, video_uri, fs_path, mtime, size)
        assert result == "unreadable"
        after = _probe_view(repo, video_uri)
        assert (after.media_width, after.media_probe_status) == (before.media_width, "ok")
        return

    if case == "unreadable_post_stat_differs":
        assert repo.update_media_probe(video_uri, _ok(), mtime, size) is True
        before = _probe_view(repo, video_uri)

        def _mutate(_path):
            with open(fs_path, "ab") as handle:
                handle.write(b"more-bytes")
            return _ok(width=1280, height=720)

        mocker.patch("core.media_probe.probe_file", side_effect=_mutate)
        result = probe_now(repo, video_uri, fs_path, mtime, size)
        assert result == "unreadable"
        after = _probe_view(repo, video_uri)
        assert (after.media_width, after.media_probe_status) == (before.media_width, "ok")
        return

    assert case == "ok_mtime_within_1s"
    os.utime(fs_path, (mtime + 0.5, mtime + 0.5))
    mocker.patch("core.media_probe.probe_file", return_value=_ok(width=1280, height=720))
    result = probe_now(repo, video_uri, fs_path, mtime, size)
    assert result == "ok"
    assert _probe_view(repo, video_uri).media_width == 1280
