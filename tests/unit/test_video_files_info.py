"""tests/unit/test_video_files_info.py — thumb_is_stale 判定表（TASK-200b-T5）。

純函式測試，零磁碟。
"""
from __future__ import annotations

import pytest

from core.video_files_info import poster_regen_verdict, thumb_is_stale


@pytest.mark.parametrize(
    "mode,db_sig,live_sig,thumb_mtime_ns,expected",
    [
        ("cache", (100, 10), (200, 20), 50, True),
        ("cache", (100, 10), (200, 5), 300, True),
        ("cache", None, (200, 20), 50, True),
        ("cache", None, (200, 20), 500, False),
        ("cover", (100, 10), (200, 20), 50, False),
        ("cache", (100, 10), None, 50, False),
    ],
    ids=[
        "sig-diff-cover-newer",
        "sig-diff-cover-older-than-thumb",
        "sig-null-cover-newer",
        "sig-null-cover-older",
        "cover-mode",
        "live-unknown",
    ],
)
def test_thumb_stale_table(mode, db_sig, live_sig, thumb_mtime_ns, expected):
    assert thumb_is_stale(
        mode=mode, db_sig=db_sig, live_sig=live_sig,
        thumb_mtime_ns=thumb_mtime_ns,
    ) is expected


@pytest.mark.parametrize("cover_dir,expected", [
    ("library", (True, None)),
    ("other", (False, "generic_cover_name")),
])
def test_poster_regen_cover_directory(tmp_path, cover_dir, expected):
    assert poster_regen_verdict(
        external_mode_on=True, has_cover_file=True,
        cover_fs=str(tmp_path / cover_dir / "ABC.jpg"),
        video_fs=str(tmp_path / "library" / "ABC.mp4"), readonly=False,
    ) == expected
