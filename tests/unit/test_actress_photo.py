"""
Unit tests for core/actress_photo.py
Tests cover: download, rescrape, exception handling, HTTP errors, delete, special chars
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import core.actress_photo as actress_photo
from core.actress_photo import (
    download_actress_photo,
    get_local_photo_path,
    delete_local_photo,
)


@pytest.fixture
def gfriends_dir(tmp_path, monkeypatch):
    monkeypatch.setattr('core.actress_photo.GFRIENDS_DIR', tmp_path / "Gfriends")
    return tmp_path / "Gfriends"


def make_mock_response(status_code=200, content_type="image/jpeg", content=b"fake_image_data"):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = {"Content-Type": content_type}
    mock_resp.content = content
    return mock_resp


# -------------------------------------------------------------------
# Test 1: download 成功 + get_local_photo_path 找到
# -------------------------------------------------------------------
def test_download_success_and_get_local_path(gfriends_dir):
    """download_actress_photo() 成功下載後，get_local_photo_path() 能找到檔案"""
    mock_resp = make_mock_response(status_code=200, content_type="image/jpeg")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("田中美久", "https://example.com/photo.jpg", "gfriends")

    assert result is True
    assert gfriends_dir.exists()
    found = get_local_photo_path("田中美久")
    assert found is not None
    assert found.suffix == ".jpg"
    assert found.exists()


# -------------------------------------------------------------------
# Test 2: 同名 rescrape（.jpg → .webp），舊檔被刪
# -------------------------------------------------------------------
def test_rescrape_old_file_deleted(gfriends_dir):
    """rescrape 時舊副檔名的檔案被刪，只剩新副檔名的檔案"""
    # 先建立 Gfriends dir 並放一個舊的 .jpg 檔
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    old_file = gfriends_dir / "田中美久.jpg"
    old_file.write_bytes(b"old_jpeg_data")
    assert old_file.exists()

    # 再次下載，但這次 Content-Type 是 webp
    mock_resp = make_mock_response(status_code=200, content_type="image/webp")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("田中美久", "https://example.com/photo.webp", "gfriends")

    assert result is True
    # 舊 .jpg 應該被刪掉
    assert not old_file.exists()
    # 新 .webp 應該存在
    new_file = gfriends_dir / "田中美久.webp"
    assert new_file.exists()
    # 目錄裡只有一個檔案
    files = list(gfriends_dir.glob("田中美久.*"))
    assert len(files) == 1


# -------------------------------------------------------------------
# Test 3: requests exception → False
# -------------------------------------------------------------------
def test_download_requests_exception(gfriends_dir):
    """requests.get() 拋例外時，download_actress_photo() 回 False，不 re-raise"""
    import requests as req_module
    with patch("core.actress_photo.requests.get", side_effect=req_module.exceptions.ConnectionError("no conn")):
        result = download_actress_photo("佐藤みき", "https://example.com/photo.jpg", "graphis")

    assert result is False


# -------------------------------------------------------------------
# Test 4: HTTP 非 200 → False
# -------------------------------------------------------------------
def test_download_http_non_200(gfriends_dir):
    """HTTP status != 200 時回 False，不寫檔"""
    mock_resp = make_mock_response(status_code=404, content_type="text/html", content=b"not found")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("鈴木りん", "https://example.com/photo.jpg", "wiki")

    assert result is False
    # 目錄不存在或目錄為空（沒有寫任何檔案）
    if gfriends_dir.exists():
        files = list(gfriends_dir.glob("鈴木りん.*"))
        assert len(files) == 0


# -------------------------------------------------------------------
# Test 5: delete_local_photo 後 get_local_photo_path 回 None
# -------------------------------------------------------------------
def test_delete_photo_then_get_returns_none(gfriends_dir):
    """delete_local_photo() 後 get_local_photo_path() 回 None"""
    # 先下載一張
    mock_resp = make_mock_response(status_code=200, content_type="image/png")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        download_actress_photo("青山あかね", "https://example.com/photo.png", "minnano")

    # 確認下載成功
    assert get_local_photo_path("青山あかね") is not None

    # 刪除
    deleted = delete_local_photo("青山あかね")
    assert deleted is True

    # 現在應回 None
    assert get_local_photo_path("青山あかね") is None


# -------------------------------------------------------------------
# Test 6: 特殊字元女優名（含 ·）
# -------------------------------------------------------------------
def test_special_chars_actress_name(gfriends_dir):
    """含 · 的女優名可正常下載與讀取；/ \\ : 等非法字元被替換為空格"""
    mock_resp = make_mock_response(status_code=200, content_type="image/jpeg")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("田中·ナナ", "https://example.com/photo.jpg", "gfriends")

    assert result is True
    found = get_local_photo_path("田中·ナナ")
    assert found is not None
    # · 應被保留（不在 illegal_chars 中）
    assert "田中·ナナ" in found.stem
    assert found.exists()
