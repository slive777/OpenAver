"""
test_search_inflow_upsert.py — TDD-lite: POST /api/scrape-single 後端 in-flow upsert

4 個 case：
1. synced  — 在 directories 內，scan_file 回有效 VideoInfo，upsert 成功 → db_sync_status: "synced"
2. not_linked — 不在 directories 內 → find_matched_directory 回 None → db_sync_status: "not_linked"
3. failed  — upsert 拋例外 → except 包裹，response 仍 success: true，db_sync_status: "failed"
4. missing_filename — organize_file 回傳缺 new_filename → db_sync_status: "not_linked"，不 crash
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
        MockVideo.from_video_info.return_value = MagicMock()
        MockRepo.return_value.upsert.return_value = 1

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
        MockVideo.from_video_info.return_value = MagicMock()
        MockRepo.return_value.upsert.side_effect = Exception("DB write error")

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
        MockVideo.from_video_info.return_value = MagicMock()
        MockRepo.return_value.upsert.return_value = 1

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
    MockRepo.return_value.upsert.assert_not_called()
