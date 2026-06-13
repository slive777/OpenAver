"""
test_search_inflow_upsert.py — TDD-lite: POST /api/scrape-single 後端 in-flow upsert

4 個 case（既有）：
1. synced  — 在 directories 內，scan_file 回有效 VideoInfo，upsert 成功 → db_sync_status: "synced"
2. not_linked — 不在 directories 內 → find_matched_directory 回 None → db_sync_status: "not_linked"
3. failed  — upsert 拋例外 → except 包裹，response 仍 success: true，db_sync_status: "failed"
4. missing_filename — organize_file 回傳缺 new_filename → db_sync_status: "not_linked"，不 crash

B1 dead-card 守衛（新增）：
I1 — B1 端到端死卡守衛（external_manager=off）
I2 — B1 端到端死卡守衛（external_manager=jellyfin，驗 mode-agnostic）
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ─── helper stubs ────────────────────────────────────────────────────────────

def _make_video_info(num="ABC-001"):
    """回傳最小可用的 VideoInfo stub。"""
    from core.gallery_scanner import VideoInfo
    info = VideoInfo()
    info.num = num
    info.path = "file:///tmp/ABC-001/ABC-001.mp4"
    info.title = "Test Title"
    return info


def _organize_ok(new_filename="/tmp/ABC-001/ABC-001.mp4"):
    """organize_file 回傳成功 dict（含 new_filename）。"""
    return {
        "success": True,
        "new_filename": new_filename,
        "new_folder": "/tmp/ABC-001",
        "original_path": "/tmp/ABC-001.mp4",
    }


def _scrape_request_body(file_path="/tmp/ABC-001.mp4"):
    return {
        "file_path": file_path,
        "number": "ABC-001",
        "metadata": {
            "title": "Test Title",
            "number": "ABC-001",
            "cover": "",
            "actresses": [],
            "tags": [],
            "release": "",
        },
    }


# ─── case 1: synced ──────────────────────────────────────────────────────────

def test_scrape_single_db_sync_status_synced(client):
    """
    在 directories 內 + scan_file 回有效 VideoInfo + upsert 成功
    → response db_sync_status == "synced"
    """
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()) as _mock_org,
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # B1: repath replaces upsert

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"


# ─── case 2: not_linked ──────────────────────────────────────────────────────

def test_scrape_single_db_sync_status_not_linked(client):
    """
    不在 directories 內 → find_matched_directory 回 None
    → db_sync_status == "not_linked"，不呼叫 scan_file / upsert
    """
    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/other"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value=None),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
    ):
        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "not_linked"
    MockScanner.return_value.scan_file.assert_not_called()
    MockRepo.return_value.upsert.assert_not_called()


# ─── case 3: failed (upsert 拋例外) ──────────────────────────────────────────

def test_scrape_single_db_sync_status_failed_on_upsert_exception(client):
    """
    upsert 拋 Exception → except 包裹
    → response 仍 success: true，db_sync_status == "failed"（整理本身不受影響）
    """
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        # B1: now calls repath() instead of upsert()
        MockRepo.return_value.repath.side_effect = Exception("DB write error")

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "failed"


# ─── case 5: VideoScanner 用 path_mappings= 構建 ────────────────────────────────

def test_scrape_single_video_scanner_receives_path_mappings(client):
    """
    try_inflow_upsert 必須用 path_mappings=... 構建 VideoScanner（P1 fix 驗證）。
    spy VideoScanner constructor，assert call kwargs 含 path_mappings。
    """
    video_info = _make_video_info()
    path_mappings = {"/mnt/e": "E:"}

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": path_mappings}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # B1: repath replaces upsert

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"
    # VideoScanner 必須以 path_mappings= 構建
    MockScanner.assert_called_once_with(path_mappings=path_mappings)


# ─── case 4: missing new_filename ─────────────────────────────────────────────

def test_scrape_single_db_sync_status_not_linked_on_missing_filename(client):
    """
    organize_file 回傳缺 new_filename（或空字串）
    → skip try_inflow_upsert，log warning
    → db_sync_status == "not_linked"，不 crash
    """
    organize_result = {
        "success": True,
        "new_filename": "",          # 空字串 — 缺失情境
        "new_folder": "/tmp/ABC-001",
        "original_path": "/tmp/ABC-001.mp4",
    }

    with (
        patch("web.routers.scraper.organize_file", return_value=organize_result),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
    ):
        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "not_linked"
    MockScanner.return_value.scan_file.assert_not_called()
    MockRepo.return_value.repath.assert_not_called()


# ─── B1 helpers ──────────────────────────────────────────────────────────────

def _seed_old_card_b1(repo, old_uri: str, user_tags=None, created_at_str: str = None):
    """Seed an old card in the given repo. Returns the stored Video row."""
    from core.database import Video
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(Video(
            path=old_uri,
            number="ABC-001",
            title="Old Title",
            original_title="",
            actresses=[],
            maker="",
            director="",
            series=None,
            label="",
            tags=[],
            user_tags=user_tags or ["看過"],
            sample_images=[],
            duration=None,
            size_bytes=0,
            cover_path="old_cover.jpg",
            release_date="",
            mtime=0.0,
            nfo_mtime=0.0,
        ))
    if created_at_str:
        conn = repo._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET created_at = ? WHERE path = ?",
                (created_at_str, old_uri),
            )
            conn.commit()
        finally:
            conn.close()
    return repo.get_by_path(old_uri)


def _make_scan_info_for_new_b1(new_uri: str, num: str = "ABC-001"):
    """Build a VideoInfo stub for the newly-scanned file (no browse tags)."""
    from core.gallery_scanner import VideoInfo
    info = VideoInfo()
    info.path = new_uri
    info.num = num
    info.title = "New Title"
    info.originaltitle = ""
    info.actor = ""
    info.genre = ""
    info.maker = ""
    info.director = ""
    info.series = None
    info.label = ""
    info.user_tags = []   # scrape NFO does not carry browse tags
    info.sample_images = []
    info.duration = None
    info.size = 0
    info.img = ""
    info.date = ""
    info.mtime = 0
    return info


# ─── I1: B1 死卡守衛（external_manager=off） ────────────────────────────────

def test_b1_repath_no_dead_card_off(client, tmp_path):
    """
    I1 — B1 端到端死卡守衛（external_manager=off）：
    seed 舊卡（user_tags=['看過'] + 已知 created_at + 記下 id）
    → POST /api/scrape-single
    → count() 不增、舊 URI 消失、新 URI 有效、
      id==舊 id（browse 不跳位）、user_tags⊇['看過']、created_at==舊值
    """
    from core.database import Video, VideoRepository, init_db
    from core.path_utils import normalize_path, to_file_uri

    db_file = tmp_path / "b1_off_test.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    old_fs = str(tmp_path / "ABC-001.mp4")
    new_fs = str(tmp_path / "[ABC-001] New Title.mp4")
    old_uri = to_file_uri(normalize_path(old_fs), None)
    new_uri = to_file_uri(normalize_path(new_fs), None)
    old_created = "2024-02-01 10:00:00"

    old_row = _seed_old_card_b1(repo, old_uri, user_tags=["看過"], created_at_str=old_created)
    old_id = old_row.id
    count_before = repo.count()

    video_info = _make_scan_info_for_new_b1(new_uri)

    with (
        patch("web.routers.scraper.organize_file", return_value={
            "success": True,
            "new_filename": new_fs,
            "new_folder": str(tmp_path),
            "original_path": old_fs,
        }),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch("core.db_inflow.find_matched_directory", return_value=str(tmp_path)),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.db_inflow.Video") as MockVideo,
        patch("core.similar.ranker_cache.SimilarRankerCache"),
        patch("web.routers.scraper.VideoRepository", return_value=repo),
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        MockVideo.from_video_info.return_value = Video(
            path=new_uri, number="ABC-001", title="New Title",
            original_title="", actresses=[], maker="", director="",
            series=None, label="", tags=[], user_tags=[],
            sample_images=[], duration=None, size_bytes=0,
            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
        )

        resp = client.post("/api/scrape-single", json=_scrape_request_body(file_path=old_fs))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"

    # 死卡守衛：count 不增
    assert repo.count() == count_before, \
        f"count 應不增（{count_before}），得 {repo.count()}"

    # 舊路徑消失
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失（無死卡）"

    # 新路徑有效
    new_card = repo.get_by_path(new_uri)
    assert new_card is not None, "新 URI 應存在"

    # browse 不跳位：id 不變
    assert new_card.id == old_id, \
        f"id 應保留 {old_id}（browse ORDER BY id 不跳位），得 {new_card.id}"

    # browse tag 存活（union，非被 NFO 覆寫沖掉）
    assert "看過" in new_card.user_tags, \
        f"user_tags 應含 '看過'，實際: {new_card.user_tags}"

    # created_at 不變
    ca_str = str(new_card.created_at) if new_card.created_at else ""
    assert "2024-02-01" in ca_str, \
        f"created_at 應保留 2024-02-01，得 {ca_str!r}"


# ─── I2: B1 死卡守衛（external_manager=jellyfin） ─────────────────────

def test_b1_repath_no_dead_card_jellyfin(client, tmp_path):
    """
    I2 — B1 端到端死卡守衛（external_manager=jellyfin）：
    與 I1 相同斷言 — 驗 mode-agnostic（CD-c8）。
    B1 落在 try_inflow_upsert，不讀 external_manager。
    """
    from core.database import Video, VideoRepository, init_db
    from core.path_utils import normalize_path, to_file_uri

    db_file = tmp_path / "b1_jelly_test.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    old_fs = str(tmp_path / "ABC-002.mp4")
    new_fs = str(tmp_path / "[ABC-002] New Title.mp4")
    old_uri = to_file_uri(normalize_path(old_fs), None)
    new_uri = to_file_uri(normalize_path(new_fs), None)
    old_created = "2024-03-15 08:00:00"

    old_row = _seed_old_card_b1(repo, old_uri, user_tags=["看過", "喜歡"], created_at_str=old_created)
    old_id = old_row.id
    count_before = repo.count()

    video_info = _make_scan_info_for_new_b1(new_uri, num="ABC-002")

    request_body = {
        "file_path": old_fs,
        "number": "ABC-002",
        "metadata": {
            "title": "New Title",
            "number": "ABC-002",
            "cover": "",
            "actresses": [],
            "tags": [],
            "release": "",
        },
    }

    with (
        patch("web.routers.scraper.organize_file", return_value={
            "success": True,
            "new_filename": new_fs,
            "new_folder": str(tmp_path),
            "original_path": old_fs,
        }),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None},
            "scraper": {"external_manager": "jellyfin"},
        }),
        patch("core.db_inflow.find_matched_directory", return_value=str(tmp_path)),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.db_inflow.Video") as MockVideo,
        patch("core.similar.ranker_cache.SimilarRankerCache"),
        patch("web.routers.scraper.VideoRepository", return_value=repo),
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        MockVideo.from_video_info.return_value = Video(
            path=new_uri, number="ABC-002", title="New Title",
            original_title="", actresses=[], maker="", director="",
            series=None, label="", tags=[], user_tags=[],
            sample_images=[], duration=None, size_bytes=0,
            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
        )

        resp = client.post("/api/scrape-single", json=request_body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"

    # 死卡守衛：count 不增
    assert repo.count() == count_before, \
        f"count 應不增（{count_before}），得 {repo.count()}"

    # 舊路徑消失
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失"

    # 新路徑有效
    new_card = repo.get_by_path(new_uri)
    assert new_card is not None, "新 URI 應存在"

    # id 不變（browse 不跳位）
    assert new_card.id == old_id, \
        f"id 應保留 {old_id}，得 {new_card.id}"

    # browse tags 存活（union）
    assert "看過" in new_card.user_tags, \
        f"user_tags 應含 '看過'，得 {new_card.user_tags}"
    assert "喜歡" in new_card.user_tags, \
        f"user_tags 應含 '喜歡'，得 {new_card.user_tags}"

    # created_at 不變
    ca_str = str(new_card.created_at) if new_card.created_at else ""
    assert "2024-03-15" in ca_str, \
        f"created_at 應保留 2024-03-15，得 {ca_str!r}"
