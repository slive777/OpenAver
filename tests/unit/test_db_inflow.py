"""
test_db_inflow.py — TDD-lite: VideoRepository.repath + try_inflow_upsert B1 邊界條件

U1  正常 UPDATE — id 保留
U2  正常 UPDATE — created_at 保留
U3  正常 UPDATE — user_tags 沿用舊（scanned 空）
U4  正常 UPDATE — user_tags 聯集（scanned 非空）
U5  正常 UPDATE — 舊路徑消失、count 不增
U6  self-no-op（old==new）
U7  碰撞 delete-merge — tag 三方聯集
U8  碰撞 delete-merge — created_at 取較早
U9  碰撞分支單一 transaction atomicity（INSERT 失敗 → rollback）
U10 old-not-in-DB（純 Search，無前置 Scanner）
U11 old_file_path=None 向後相容
U12 scan-fail 保卡（保 path/title/cover/tags/created_at/id，回 "failed"）
U13 ranker invalidate — 正常 UPDATE 分支
U14 ranker invalidate — scan-fail 保卡分支
U15 ranker invalidate — 碰撞 delete-merge 分支
U16 old_uri 使用 to_file_uri(normalize_path(...))，無手拼 URI、無 [8:] strip  # path-contract-ok
U23 scraped_metadata overlay — cd2 skipped-NFO multipart 有完整 metadata
U24 scraped_metadata=None — cd1/normal 路徑行為不變
U25 正常 UPDATE — output_dir 保留（incoming 空，Codex branch-review P2）
U26 正常 UPDATE — scrape_attempted_at 保留（incoming 0，Codex branch-review P2）
U27 正常 UPDATE — output_dir/scrape_attempted_at happy path（incoming 有值正常寫入）
U28 碰撞 delete-merge — output_dir/scrape_attempted_at 保留（Codex branch-review P2）
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.database import Video, VideoRepository, init_db
from core.gallery_scanner import VideoInfo


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> Path:
    """建立並初始化 in-memory-style temp SQLite DB，回傳路徑。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def _seed_video(repo: VideoRepository, path: str, user_tags=None,
                created_at_str: str | None = None, cover_path: str = "",
                title: str = "Old Title") -> Video:
    """INSERT 一筆 video，保留 created_at。回傳 get_by_path 取到的實際 row。"""
    v = Video(
        path=path,
        number="ABC-001",
        title=title,
        original_title="",
        actresses=[],
        maker="",
        director="",
        series=None,
        label="",
        tags=[],
        user_tags=user_tags or [],
        sample_images=[],
        duration=None,
        size_bytes=0,
        cover_path=cover_path,
        release_date="",
        mtime=0.0,
        nfo_mtime=0.0,
    )
    repo.upsert(v)
    # 若 created_at_str 給定，直接 UPDATE（upsert 不帶 created_at）
    if created_at_str:
        conn = repo._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET created_at = ? WHERE path = ?",
                (created_at_str, path),
            )
            conn.commit()
        finally:
            conn.close()
    return repo.get_by_path(path)


def _make_video_info(path: str, user_tags=None, num: str = "ABC-001",
                     title: str = "New Title") -> VideoInfo:
    """建立 VideoInfo stub（scan_file 的回傳值）。"""
    info = VideoInfo()
    info.path = path
    info.num = num
    info.title = title
    info.originaltitle = ""
    info.actor = ""
    info.genre = ""
    info.maker = ""
    info.director = ""
    info.series = None
    info.label = ""
    info.user_tags = user_tags or []
    info.sample_images = []
    info.duration = None
    info.size = 0
    info.img = ""
    info.date = ""
    info.mtime = 0
    return info


# ─── U1: 正常 UPDATE — id 保留 ──────────────────────────────────────────────

def test_u1_normal_update_id_preserved(tmp_path):
    """整理後 id 不變（browse ORDER BY id 不跳位）。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_path = "/tmp/old.mp4"
    new_path = "/tmp/new.mp4"
    old_uri = f"file://{old_path}"
    new_uri = f"file://{new_path}"

    old_row = _seed_video(repo, old_uri)
    old_id = old_row.id
    assert old_id is not None

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert new_row.id == old_id, f"id 應保留 {old_id}，但得到 {new_row.id}"


# ─── U2: 正常 UPDATE — created_at 保留 ─────────────────────────────────────

def test_u2_normal_update_created_at_preserved(tmp_path):
    """整理後 created_at 不變。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"
    old_created = "2024-01-15 10:00:00"

    _seed_video(repo, old_uri, created_at_str=old_created)

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    # created_at 可以是 datetime 或字串，取字串比對前綴
    ca_str = str(new_row.created_at) if new_row.created_at else ""
    assert "2024-01-15" in ca_str, f"created_at 應含 2024-01-15，實際: {ca_str!r}"


# ─── U3: user_tags 沿用舊（scanned 空）─────────────────────────────────────

def test_u3_user_tags_preserve_when_scanned_empty(tmp_path):
    """搬檔 NFO 給 user_tags=[]，browse tag 存活。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    _seed_video(repo, old_uri, user_tags=["看過"])

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],  # 空
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert new_row.user_tags == ["看過"], f"user_tags 應為 ['看過']，實際: {new_row.user_tags}"


# ─── U4: user_tags 聯集（scanned 非空）────────────────────────────────────

def test_u4_user_tags_union_when_scanned_nonempty(tmp_path):
    """scanned 給非空 user_tags → 取聯集。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    _seed_video(repo, old_uri, user_tags=["看過"])

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=["HD"],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert set(new_row.user_tags) == {"看過", "HD"}, \
        f"user_tags 應為聯集 {{看過, HD}}，實際: {new_row.user_tags}"


# ─── U5: 正常 UPDATE — 舊路徑消失、count 不增 ──────────────────────────────

def test_u5_old_path_gone_count_unchanged(tmp_path):
    """整理後舊 URI get_by_path 回 None，count 不增。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    _seed_video(repo, old_uri)
    count_before = repo.count()

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失"
    assert repo.count() == count_before, "count 不應增加"


# ─── U6: self-no-op（old==new） ───────────────────────────────────────────

def test_u6_self_noop_same_path(tmp_path):
    """old_uri == new_uri → 不刪、id/created_at 不變。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    uri = "file:///tmp/same.mp4"
    old_created = "2024-03-01 08:00:00"
    old_row = _seed_video(repo, uri, user_tags=["看過"], created_at_str=old_created)
    old_id = old_row.id

    same_video = Video(path=uri, number="ABC-001", title="Updated Title",
                       original_title="", actresses=[], maker="", director="",
                       series=None, label="", tags=[], user_tags=["HD"],
                       sample_images=[], duration=None, size_bytes=0,
                       cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(uri, uri, same_video)

    row = repo.get_by_path(uri)
    assert row is not None
    assert row.id == old_id, "self-no-op 後 id 不應變"


# ─── U7: 碰撞 delete-merge — tag 三方聯集 ──────────────────────────────────

def test_u7_collision_merge_tags_union(tmp_path):
    """new path 早有一筆 → 收斂一筆、user_tags = A∪B∪C。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    _seed_video(repo, old_uri, user_tags=["B"])
    _seed_video(repo, new_uri, user_tags=["A"])

    # scan 給 C
    collision_video = Video(path=new_uri, number="ABC-001", title="New Title",
                            original_title="", actresses=[], maker="", director="",
                            series=None, label="", tags=[], user_tags=["C"],
                            sample_images=[], duration=None, size_bytes=0,
                            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, collision_video)

    merged = repo.get_by_path(new_uri)
    assert merged is not None
    assert repo.get_by_path(old_uri) is None, "old URI 應消失"
    assert repo.count() == 1, "收斂後應只有 1 筆"
    assert set(merged.user_tags) == {"A", "B", "C"}, \
        f"三方聯集應為 {{A,B,C}}，實際: {merged.user_tags}"


# ─── U8: 碰撞 delete-merge — created_at 取較早 ─────────────────────────────

def test_u8_collision_merge_created_at_min(tmp_path):
    """碰撞 merge 後 created_at = min(old_row, new_row)。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    _seed_video(repo, old_uri, created_at_str="2024-01-01 00:00:00")
    _seed_video(repo, new_uri, created_at_str="2024-06-01 00:00:00")

    collision_video = Video(path=new_uri, number="ABC-001", title="New Title",
                            original_title="", actresses=[], maker="", director="",
                            series=None, label="", tags=[], user_tags=[],
                            sample_images=[], duration=None, size_bytes=0,
                            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, collision_video)

    merged = repo.get_by_path(new_uri)
    assert merged is not None
    ca_str = str(merged.created_at) if merged.created_at else ""
    assert "2024-01-01" in ca_str, \
        f"created_at 應取較早的 2024-01-01，實際: {ca_str!r}"


# ─── U25/U26: 正常 UPDATE 分支 — output_dir / scrape_attempted_at 保留 ─────
# Codex branch-review P2：repath 逐欄直寫，未對 output_dir/scrape_attempted_at
# 套用 upsert() 已有的「incoming 空/0 → 保留既有」保護，organize/搬移時新掃描
# 的 Video（output_dir='' / scrape_attempted_at=0.0）會把既有 marker 洗掉。

def test_u25_normal_update_preserves_output_dir_on_empty_incoming(tmp_path):
    """整理搬移一筆已有 output_dir 的 row（新掃描 Video.output_dir=''）→ 既有值保留。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"
    existing_output_dir = "file:///produced/ABC-001"

    old_row = Video(path=old_uri, number="ABC-001", title="Old Title",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=[],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", output_dir=existing_output_dir,
                    release_date="", mtime=0.0, nfo_mtime=0.0)
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(old_row)

    # 新掃描的 Video（from_video_info 預設 output_dir=''）
    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", output_dir="",
                      release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert new_row.output_dir == existing_output_dir, \
        f"output_dir 應保留 {existing_output_dir}，實際: {new_row.output_dir!r}"


def test_u26_normal_update_preserves_scrape_attempted_at_on_zero_incoming(tmp_path):
    """整理搬移一筆已標記 tried 的 row（新掃描 Video.scrape_attempted_at=0.0）→ 既有值保留。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"
    existing_ts = 1717171717.0

    old_row = Video(path=old_uri, number="ABC-001", title="Old Title",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=[],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", scrape_attempted_at=existing_ts,
                    release_date="", mtime=0.0, nfo_mtime=0.0)
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(old_row)

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", scrape_attempted_at=0.0,
                      release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert new_row.scrape_attempted_at == existing_ts, \
        f"scrape_attempted_at 應保留 {existing_ts}，實際: {new_row.scrape_attempted_at!r}"


def test_u27_normal_update_writes_output_dir_and_scrape_attempted_at_when_nonempty(tmp_path):
    """happy path：incoming output_dir/scrape_attempted_at 有值時正常寫入（非全跳過）。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"

    old_row = Video(path=old_uri, number="ABC-001", title="Old Title",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=[],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", output_dir="file:///produced/OLD",
                    scrape_attempted_at=111.0,
                    release_date="", mtime=0.0, nfo_mtime=0.0)
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(old_row)

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", output_dir="file:///produced/NEW",
                      scrape_attempted_at=222.0,
                      release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert new_row.output_dir == "file:///produced/NEW"
    assert new_row.scrape_attempted_at == 222.0


# ─── U28: 碰撞 delete-merge 分支 — output_dir / scrape_attempted_at 保留 ───

def test_u28_collision_merge_preserves_output_dir_and_scrape_attempted_at(tmp_path):
    """碰撞 delete-merge（ON CONFLICT DO UPDATE）分支同樣要保留 marker，
    不因對稱教訓（Codex C2）漏改而洗掉。new path 既有 row 帶 marker，
    scanned video（走 repath 的 incoming）帶空值 → merge 後應保留 new_row 既有值。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old.mp4"
    new_uri = "file:///tmp/new.mp4"
    existing_output_dir = "file:///produced/ABC-001"
    existing_ts = 1717171717.0

    old_row = Video(path=old_uri, number="ABC-001", title="Old Title",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=[],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)
    new_row_existing = Video(path=new_uri, number="ABC-001", title="Existing New Title",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=[],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", output_dir=existing_output_dir,
                    scrape_attempted_at=existing_ts,
                    release_date="", mtime=0.0, nfo_mtime=0.0)
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(old_row)
        repo.upsert(new_row_existing)

    collision_video = Video(path=new_uri, number="ABC-001", title="Scanned Title",
                            original_title="", actresses=[], maker="", director="",
                            series=None, label="", tags=[], user_tags=[],
                            sample_images=[], duration=None, size_bytes=0,
                            cover_path="", output_dir="", scrape_attempted_at=0.0,
                            release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, collision_video)

    merged = repo.get_by_path(new_uri)
    assert merged is not None
    assert merged.output_dir == existing_output_dir, \
        f"碰撞 merge 後 output_dir 應保留 {existing_output_dir}，實際: {merged.output_dir!r}"
    assert merged.scrape_attempted_at == existing_ts, \
        f"碰撞 merge 後 scrape_attempted_at 應保留 {existing_ts}，實際: {merged.scrape_attempted_at!r}"


# ─── U9: 碰撞分支 atomicity（INSERT 失敗 → rollback） ──────────────────────


def test_u9_collision_rollback_via_real_repath(tmp_path):
    """U9 替代測試：使用真實 repath，確保 old row 在 rollback 後存活。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old9.mp4"
    new_uri = "file:///tmp/new9.mp4"

    _seed_video(repo, old_uri, user_tags=["看過"])
    _seed_video(repo, new_uri, user_tags=["A"])

    # 直接模擬 DB 層：conn.commit 時拋錯以觸發 rollback 路徑
    real_get_connection = repo._get_connection

    call_count = [0]

    def failing_get_connection():
        conn = real_get_connection()
        original_commit = conn.commit

        def patched_commit():
            call_count[0] += 1
            if call_count[0] == 1:
                # 第一次 commit → 讓 DELETE 成功但 INSERT 失敗
                conn.rollback()
                raise sqlite3.OperationalError("Simulated commit failure")
            return original_commit()

        conn.commit = patched_commit
        return conn

    with patch.object(repo, "_get_connection", failing_get_connection):
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            try:
                repo.repath(old_uri, new_uri, Video(
                    path=new_uri, number="ABC-001", title="Fail",
                    original_title="", actresses=[], maker="", director="",
                    series=None, label="", tags=[], user_tags=["C"],
                    sample_images=[], duration=None, size_bytes=0,
                    cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
                ))
            except Exception:
                pass

    # rollback 後 old row 應仍在
    assert repo.get_by_path(old_uri) is not None, \
        "rollback 後 old row 應存活（不雙失）"


# ─── U10: old-not-in-DB（純 Search，無前置 Scanner）───────────────────────

def test_u10_old_not_in_db_falls_back_to_upsert(tmp_path):
    """old_uri 不在 DB → repath 退化為 upsert，new 正常寫入。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/nonexistent_old.mp4"
    new_uri = "file:///tmp/new10.mp4"

    assert repo.get_by_path(old_uri) is None

    new_video = Video(path=new_uri, number="ABC-001", title="New Title",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.repath(old_uri, new_uri, new_video)

    assert repo.get_by_path(new_uri) is not None, "new_uri 應寫入"
    assert repo.count() == 1


# ─── U11: old_file_path=None 向後相容 ──────────────────────────────────────

def test_u11_old_file_path_none_backward_compat(tmp_path):
    """try_inflow_upsert(new, old_file_path=None) 行為等同原本純 upsert。"""
    new_path = "/tmp/new11.mp4"
    new_uri = "file:///tmp/new11.mp4"

    video_info = _make_video_info(new_uri)

    import core.db_inflow as _db_inflow_mod

    mock_repo = MagicMock()
    mock_video = MagicMock()
    mock_video.path = new_uri

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value="/tmp"),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=mock_repo),
        patch.object(_db_inflow_mod, "Video") as MockVideo,
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        MockVideo.from_video_info.return_value = mock_video
        mock_repo.repath.return_value = None

        result = _db_inflow_mod.try_inflow_upsert(new_path, old_file_path=None)

    assert result == "synced"
    # repath 應以 old_uri=None 呼叫
    mock_repo.repath.assert_called_once()
    call_args = mock_repo.repath.call_args
    assert call_args[0][0] is None, "old_uri 應為 None（無 old_file_path）"


# ─── U12: scan-fail 保卡 ──────────────────────────────────────────────────

def test_u12_scan_fail_path_only_update(tmp_path):
    """
    scan_file 回 None → UPDATE-path-only 保卡：
    - get_by_path(old_uri) is None（舊 URI 不再存在）
    - get_by_path(new_uri) 有效（卡在新位置）
    - title/cover_path/user_tags/created_at/id 全部保留
    - 回傳 "failed"
    """
    from core.path_utils import normalize_path, to_file_uri

    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_path_fs = str(tmp_path / "old_scan_fail.mp4")
    new_path_fs = str(tmp_path / "new_scan_fail.mp4")
    # 用 to_file_uri 算出真實 URI（與 try_inflow_upsert 內部一致）
    old_uri = to_file_uri(normalize_path(old_path_fs), None)
    new_uri = to_file_uri(normalize_path(new_path_fs), None)
    old_created = "2023-11-01 00:00:00"

    # seed 舊 row
    _seed_video(repo, old_uri,
                user_tags=["看過"],
                created_at_str=old_created,
                cover_path="old_cover.jpg",
                title="Preserved Title")
    old_row = repo.get_by_path(old_uri)
    assert old_row is not None, f"seed 失敗，old_uri={old_uri!r}"
    old_id = old_row.id

    import core.db_inflow as _db_inflow_mod

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value=str(tmp_path)),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        MockScanner.return_value.scan_file.return_value = None  # scan 失敗

        result = _db_inflow_mod.try_inflow_upsert(new_path_fs, old_file_path=old_path_fs)

    assert result == "failed", f"scan-fail 應回 'failed'，實際: {result!r}"

    # 舊 URI 消失（保卡搬到新位置）
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失（保卡已搬到新位置）"

    # 新 URI 存在，metadata 保留
    new_row = repo.get_by_path(new_uri)
    assert new_row is not None, f"新 URI 應存在（new_uri={new_uri!r}）"
    assert new_row.id == old_id, f"id 應保留 {old_id}，得 {new_row.id}"
    assert new_row.title == "Preserved Title", f"title 應保留，得 {new_row.title!r}"
    assert new_row.cover_path == "old_cover.jpg", f"cover_path 應保留，得 {new_row.cover_path!r}"
    assert "看過" in new_row.user_tags, f"user_tags 應含 '看過'，得 {new_row.user_tags}"
    ca_str = str(new_row.created_at) if new_row.created_at else ""
    assert "2023-11-01" in ca_str, f"created_at 應保留，得 {ca_str!r}"


# ─── U13: ranker invalidate — 正常 UPDATE 分支 ────────────────────────────

def test_u13_ranker_invalidate_normal_update(tmp_path):
    """正常 UPDATE 分支 → SimilarRankerCache.invalidate 被呼叫恰 1 次。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old13.mp4"
    new_uri = "file:///tmp/new13.mp4"
    _seed_video(repo, old_uri)

    new_video = Video(path=new_uri, number="ABC-001", title="New",
                      original_title="", actresses=[], maker="", director="",
                      series=None, label="", tags=[], user_tags=[],
                      sample_images=[], duration=None, size_bytes=0,
                      cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        repo.repath(old_uri, new_uri, new_video)

    MockRanker.invalidate.assert_called_once()


# ─── U14: ranker invalidate — scan-fail 保卡分支 ──────────────────────────

def test_u14_ranker_invalidate_scan_fail(tmp_path):
    """scan-fail 保卡分支 → SimilarRankerCache.invalidate 被呼叫恰 1 次。"""
    from core.path_utils import normalize_path, to_file_uri

    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_path_fs = str(tmp_path / "old14.mp4")
    new_path_fs = str(tmp_path / "new14.mp4")
    old_uri = to_file_uri(normalize_path(old_path_fs), None)
    new_uri = to_file_uri(normalize_path(new_path_fs), None)

    _seed_video(repo, old_uri, user_tags=["看過"])

    import core.db_inflow as _db_inflow_mod

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value=str(tmp_path)),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker,
    ):
        MockScanner.return_value.scan_file.return_value = None

        _db_inflow_mod.try_inflow_upsert(new_path_fs, old_file_path=old_path_fs)

    # scan-fail 保卡後新路徑應存在
    new_row = repo.get_by_path(new_uri)
    assert new_row is not None, "scan-fail 保卡後新路徑應存在"
    # invalidate 應被呼叫（db_inflow 的 scan-fail 保卡路徑顯式 invalidate）
    MockRanker.invalidate.assert_called_once()


# ─── U15: ranker invalidate — 碰撞 delete-merge 分支 ──────────────────────

def test_u15_ranker_invalidate_collision(tmp_path):
    """碰撞 delete-merge 分支 → SimilarRankerCache.invalidate 被呼叫恰 1 次。"""
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/old15.mp4"
    new_uri = "file:///tmp/new15.mp4"
    _seed_video(repo, old_uri, user_tags=["B"])
    _seed_video(repo, new_uri, user_tags=["A"])

    collision_video = Video(path=new_uri, number="ABC-001", title="New",
                            original_title="", actresses=[], maker="", director="",
                            series=None, label="", tags=[], user_tags=["C"],
                            sample_images=[], duration=None, size_bytes=0,
                            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0)

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        repo.repath(old_uri, new_uri, collision_video)

    MockRanker.invalidate.assert_called_once()


# ─── U16: grep 守衛 — 無手拼 URI ─────────────────────────────────────────

def test_u16_no_manual_uri_construction():
    """db_inflow.py 中不應有 'file:///' 手拼或 '[8:]' strip。"""  # path-contract-ok
    import re
    db_inflow_path = Path(__file__).parent.parent.parent / "core" / "db_inflow.py"
    content = db_inflow_path.read_text(encoding="utf-8")

    # 禁止手拼 file:/// URI（comment 內也算）
    bad_furi = re.findall(r'"file:///|\'file:///', content)
    assert not bad_furi, f"db_inflow.py 不應手拼 file:/// URI，發現: {bad_furi}"

    # 禁止 [8:] URI strip  # path-contract-ok
    bad_strip = re.findall(r'\[8:\]', content)
    assert not bad_strip, f"db_inflow.py 不應有 [8:] strip，發現: {bad_strip}"  # path-contract-ok


# ─── U17: repath_path_only — 正常搬移（Fix 2） ────────────────────────────────

def test_u17_repath_path_only_normal(tmp_path):
    """
    repath_path_only 正常路徑：
    - 舊 URI 消失、新 URI 出現
    - title / cover_path / user_tags / created_at / id 全部保留
    - 回傳 True
    - SimilarRankerCache.invalidate 被呼叫恰 1 次
    """
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/rpo_old.mp4"
    new_uri = "file:///tmp/rpo_new.mp4"
    old_created = "2023-05-10 12:00:00"

    _seed_video(repo, old_uri, user_tags=["看過"], created_at_str=old_created,
                cover_path="cover.jpg", title="Preserved Title")
    old_row = repo.get_by_path(old_uri)
    old_id = old_row.id

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        result = repo.repath_path_only(old_uri, new_uri)

    assert result is True, "repath_path_only 應回 True"
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失"

    new_row = repo.get_by_path(new_uri)
    assert new_row is not None, "新 URI 應存在"
    assert new_row.id == old_id, f"id 應保留 {old_id}"
    assert new_row.title == "Preserved Title", f"title 應保留，得 {new_row.title!r}"
    assert new_row.cover_path == "cover.jpg", f"cover_path 應保留，得 {new_row.cover_path!r}"
    assert "看過" in new_row.user_tags, f"user_tags 應含 '看過'，得 {new_row.user_tags}"
    ca_str = str(new_row.created_at) if new_row.created_at else ""
    assert "2023-05-10" in ca_str, f"created_at 應保留，得 {ca_str!r}"
    MockRanker.invalidate.assert_called_once()


# ─── U18: repath_path_only — new_uri 碰撞（Fix 2） ─────────────────────────────

def test_u18_repath_path_only_collision_no_update(tmp_path):
    """
    repath_path_only：new_uri 已有 row → 不 UPDATE，回 False，old row 不動，無 IntegrityError。
    """
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/rpo_coll_old.mp4"
    new_uri = "file:///tmp/rpo_coll_new.mp4"

    _seed_video(repo, old_uri, user_tags=["看過"])
    _seed_video(repo, new_uri, user_tags=["已有"])

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        result = repo.repath_path_only(old_uri, new_uri)

    assert result is False, "碰撞時應回 False"
    # old row 不應被動到
    old_row = repo.get_by_path(old_uri)
    assert old_row is not None, "old row 應仍存在（碰撞時不 UPDATE）"
    assert "看過" in old_row.user_tags
    # new row 也未受影響
    new_row = repo.get_by_path(new_uri)
    assert new_row is not None
    assert "已有" in new_row.user_tags
    # invalidate 不應被呼叫（提前返回 False）
    MockRanker.invalidate.assert_not_called()


# ─── U19: repath_path_only — self no-op（Fix 2） ────────────────────────────────

def test_u19_repath_path_only_same_uri_noop(tmp_path):
    """
    repath_path_only：old_uri == new_uri → 立即回 False，DB 不動。
    """
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    uri = "file:///tmp/rpo_same.mp4"
    _seed_video(repo, uri, user_tags=["看過"])

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        result = repo.repath_path_only(uri, uri)

    assert result is False, "same uri 應回 False"
    row = repo.get_by_path(uri)
    assert row is not None, "row 應仍存在"
    MockRanker.invalidate.assert_not_called()


# ─── U20: repath_path_only — empty old_uri（Fix 2） ─────────────────────────────

def test_u20_repath_path_only_empty_old_uri_noop(tmp_path):
    """
    repath_path_only：old_uri == "" → 立即回 False。
    """
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    with patch("core.similar.ranker_cache.SimilarRankerCache") as MockRanker:
        result = repo.repath_path_only("", "file:///tmp/rpo_any.mp4")

    assert result is False
    MockRanker.invalidate.assert_not_called()


# ─── U21: db_inflow scan-fail 保卡用 repath_path_only（Fix 2 layering） ──────────

def test_u21_scan_fail_uses_repath_path_only(tmp_path):
    """
    scan-fail 保卡分支不再呼叫 repo._get_connection()，
    改呼叫 repo.repath_path_only()（layering 守衛）。
    """
    from core.path_utils import normalize_path, to_file_uri

    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_path_fs = str(tmp_path / "u21_old.mp4")
    new_path_fs = str(tmp_path / "u21_new.mp4")
    old_uri = to_file_uri(normalize_path(old_path_fs), None)

    _seed_video(repo, old_uri, user_tags=["看過"])

    import core.db_inflow as _db_inflow_mod

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value=str(tmp_path)),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        MockScanner.return_value.scan_file.return_value = None

        # 監控 repath_path_only 是否被呼叫，且 _get_connection 不應從 db_inflow 呼叫
        with patch.object(repo, "repath_path_only", wraps=repo.repath_path_only) as mock_rpo:
            result = _db_inflow_mod.try_inflow_upsert(new_path_fs, old_file_path=old_path_fs)

    assert result == "failed", f"scan-fail 應回 'failed'，得 {result!r}"
    mock_rpo.assert_called_once(), "scan-fail 保卡應呼叫 repath_path_only"


# ─── U22: Fix 1 rowcount=0 fallback → upsert（Fix 1） ───────────────────────────

def test_u22_repath_normal_update_rowcount0_falls_back_to_upsert(tmp_path):
    """
    Fix 1：正常 UPDATE 分支的 UPDATE 影響 0 rows（concurrent delete 模擬）
    → 退化為 upsert，新路徑 row 仍寫入。

    機制：seed old_uri 讓 existence check 進入正常-UPDATE 分支，再用 cursor wrapper
    攔截 UPDATE 語句——先從真實 DB 刪掉 old_uri，再執行 UPDATE（WHERE 匹配不到 → rowcount=0）。
    upsert spy 確認 fallback 確實被呼叫，get_by_path(new_uri) 確認新 row 寫入成功。

    決定性屬性：移除 production 的 `if rowcount == 0: self.upsert(video)` 後，
    此測試必須 RED。
    """
    db_path = _make_db(tmp_path)
    repo = VideoRepository(db_path=db_path)

    old_uri = "file:///tmp/u22_old.mp4"
    new_uri = "file:///tmp/u22_new.mp4"

    # seed old row — 讓 repath existence check 進入正常-UPDATE 分支
    _seed_video(repo, old_uri, title="Original Title")

    new_video = Video(
        path=new_uri, number="ABC-001", title="Fallback Title",
        original_title="", actresses=[], maker="", director="",
        series=None, label="", tags=[], user_tags=[],
        sample_images=[], duration=None, size_bytes=0,
        cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
    )

    real_get_conn = repo._get_connection

    class InterceptingCursor:
        """Cursor wrapper: 攔截 UPDATE videos SET 語句，
        先刪 old_uri row，再執行 UPDATE → rowcount=0（WHERE 匹配不到）。
        其他 SQL 照常走。
        """
        def __init__(self, real_c):
            self._c = real_c

        def execute(self, sql, params=()):
            if sql.strip().upper().startswith("UPDATE VIDEOS SET"):
                # 模擬 concurrent delete：先刪掉 old_uri，再執行 UPDATE
                del_conn = real_get_conn()
                del_c = del_conn.cursor()
                try:
                    del_c.execute("DELETE FROM videos WHERE path = ?", (old_uri,))
                    del_conn.commit()
                finally:
                    del_conn.close()
                # 執行真實 UPDATE（old_uri 已不存在 → rowcount 自然為 0）
                self._c.execute(sql, params)
            else:
                self._c.execute(sql, params)

        def fetchone(self):
            return self._c.fetchone()

        def fetchall(self):
            return self._c.fetchall()

        @property
        def rowcount(self):
            return self._c.rowcount

        @property
        def lastrowid(self):
            return self._c.lastrowid

    class InterceptingConn:
        """Connection wrapper: 讓 cursor() 回傳 InterceptingCursor。"""
        def __init__(self, real_conn):
            self._conn = real_conn

        def cursor(self):
            return InterceptingCursor(self._conn.cursor())

        def commit(self):
            self._conn.commit()

        def close(self):
            self._conn.close()

        def execute(self, sql, params=()):
            return self._conn.execute(sql, params)

    def intercepting_get_connection():
        return InterceptingConn(real_get_conn())

    with patch.object(repo, "_get_connection", side_effect=intercepting_get_connection):
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            with patch.object(repo, "upsert", wraps=repo.upsert) as upsert_spy:
                repo.repath(old_uri, new_uri, new_video)

    # (a) upsert fallback 必須被呼叫恰好一次
    upsert_spy.assert_called_once_with(new_video)

    # (b) fallback 應將 new_uri row 寫入 DB
    new_row = repo.get_by_path(new_uri)
    assert new_row is not None, "rowcount=0 fallback 後 upsert 應寫入 new_uri"
    assert new_row.title == "Fallback Title", (
        f"新 row title 應為 'Fallback Title'，得 {new_row.title!r}"
    )


# ─── U23: scraped_metadata overlay — cd2 skipped-NFO multipart ────────────────
# RED before fix: scan_file returns sparse VideoInfo (no actors/tags/date/maker
# because no NFO), so the DB row has empty actresses/tags/release_date/maker.
# GREEN after fix: scraped_metadata is overlaid onto video_info, so the DB row
# has the scraped actors/tags/date/maker.

def test_u23_scraped_metadata_overlay_cd2_multipart(tmp_path):
    """
    cd2 外部模式下刮削：scan_file 回 filename-parsed 稀疏 VideoInfo，
    傳入 scraped_metadata 後，DB row 應有完整的 scraped actors/tags/date/maker。

    RED 條件：目前 try_inflow_upsert 不接受 scraped_metadata，DB row actors/tags 為空。
    GREEN 條件：overlay 後 DB row.actresses == ['花澤ひまり']，tags 含 '美少女'，
                release_date == '2024-03-15'，maker == 'SOD CREATE'。
    """
    new_path = "/tmp/u23_cd2.mp4"
    new_uri = "file:///tmp/u23_cd2.mp4"

    # scan_file 模擬 filename-parsed 稀疏結果（無 NFO）
    sparse_info = _make_video_info(new_uri, num="SONE-001", title="SONE-001 cd2")
    # sparse: actor='', genre='', maker='', date='' — just num/title from filename

    scraped_metadata = {
        'number': 'SONE-001',
        'title': 'SOD 花澤ひまり 美少女',
        'actors': ['花澤ひまり'],
        'tags': ['美少女', '单体作品'],
        'date': '2024-03-15',
        'maker': 'SOD CREATE',
        'director': '山田太郎',
        'series': 'SOD STAR',
        'label': 'SOD',
        'duration': 120,
    }

    import core.db_inflow as _db_inflow_mod

    mock_repo = MagicMock()
    captured_video = {}

    def fake_repath(old_uri, new_uri, video):
        captured_video['video'] = video

    mock_repo.repath.side_effect = fake_repath

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value="/tmp"),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=mock_repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        MockScanner.return_value.scan_file.return_value = sparse_info
        mock_repo.repath.return_value = None

        result = _db_inflow_mod.try_inflow_upsert(
            new_path,
            old_file_path=None,
            scraped_metadata=scraped_metadata,
        )

    assert result == "synced", f"應回 'synced'，實際: {result!r}"
    assert mock_repo.repath.called, "repo.repath 應被呼叫"

    # 拿到傳入 repath 的 Video 物件
    video = captured_video.get('video')
    assert video is not None, "應有 Video 傳入 repath"

    # 驗證 overlay 生效
    assert video.actresses == ['花澤ひまり'], \
        f"actresses 應為 ['花澤ひまり']，實際: {video.actresses}"
    assert '美少女' in video.tags, \
        f"tags 應含 '美少女'，實際: {video.tags}"
    assert video.release_date == '2024-03-15', \
        f"release_date 應為 '2024-03-15'，實際: {video.release_date!r}"
    assert video.maker == 'SOD CREATE', \
        f"maker 應為 'SOD CREATE'，實際: {video.maker!r}"
    assert video.director == '山田太郎', \
        f"director 應為 '山田太郎'，實際: {video.director!r}"
    assert video.series == 'SOD STAR', \
        f"series 應為 'SOD STAR'，實際: {video.series!r}"
    assert video.duration == 120, \
        f"duration 應為 120，實際: {video.duration}"


# ─── U24: scraped_metadata=None — cd1/normal 行為不變 ───────────────────────

def test_u24_no_scraped_metadata_behavior_unchanged(tmp_path):
    """
    cd1/normal 路徑（scraped_metadata=None）：行為與原本 byte-identical。
    scan_file 的 sparse 結果直接進 repath，無 overlay。
    actresses/tags 依 scan_file 結果（空）而非 scraped_metadata。
    """
    new_path = "/tmp/u24_cd1.mp4"
    new_uri = "file:///tmp/u24_cd1.mp4"

    # scan_file 回有 actor 的 VideoInfo（模擬 NFO 存在的 cd1）
    info_with_actor = _make_video_info(new_uri, num="SONE-001", title="SONE-001 cd1")
    info_with_actor.actor = "花澤ひまり"
    info_with_actor.genre = "美少女"
    info_with_actor.date = "2024-03-15"
    info_with_actor.maker = "SOD CREATE"

    import core.db_inflow as _db_inflow_mod

    mock_repo = MagicMock()
    captured_video = {}

    def fake_repath(old_uri, new_uri, video):
        captured_video['video'] = video

    mock_repo.repath.side_effect = fake_repath

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value="/tmp"),
        patch.object(_db_inflow_mod, "VideoScanner") as MockScanner,
        patch.object(_db_inflow_mod, "VideoRepository", return_value=mock_repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        MockScanner.return_value.scan_file.return_value = info_with_actor
        mock_repo.repath.return_value = None

        # scraped_metadata=None — cd1/normal path
        result = _db_inflow_mod.try_inflow_upsert(
            new_path,
            old_file_path=None,
            scraped_metadata=None,
        )

    assert result == "synced"
    video = captured_video.get('video')
    assert video is not None

    # scan_file 的值應直接進 repath，無任何 overlay 改動
    assert video.actresses == ['花澤ひまり'], \
        f"actresses 應由 scan_file 給，得: {video.actresses}"
    assert '美少女' in video.tags, \
        f"tags 應由 scan_file 給，得: {video.tags}"
    assert video.release_date == '2024-03-15'
    assert video.maker == 'SOD CREATE'
