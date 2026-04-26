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
        result = download_actress_photo("田中美久", "https://raw.githubusercontent.com/photo.jpg", "gfriends")

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
        result = download_actress_photo("田中美久", "https://raw.githubusercontent.com/photo.webp", "gfriends")

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
        result = download_actress_photo("佐藤みき", "https://www.graphis.ne.jp/photo.jpg", "graphis")

    assert result is False


# -------------------------------------------------------------------
# Test 4: HTTP 非 200 → False
# -------------------------------------------------------------------
def test_download_http_non_200(gfriends_dir):
    """HTTP status != 200 時回 False，不寫檔"""
    mock_resp = make_mock_response(status_code=404, content_type="text/html", content=b"not found")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("鈴木りん", "https://upload.wikimedia.org/photo.jpg", "wiki")

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
        download_actress_photo("青山あかね", "https://www.minnano-av.com/photo.png", "minnano")

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
        result = download_actress_photo("田中·ナナ", "https://raw.githubusercontent.com/photo.jpg", "gfriends")

    assert result is True
    found = get_local_photo_path("田中·ナナ")
    assert found is not None
    # · 應被保留（不在 illegal_chars 中）
    assert "田中·ナナ" in found.stem
    assert found.exists()


# ===================================================================
# crop_video_cover 相關測試（T2 新增）
# ===================================================================

import io as _io


def _make_fake_pil_image(width=200, height=300):
    """建立假 PIL Image mock（不需 Pillow）"""
    mock_img = MagicMock()
    mock_img.size = (width, height)
    mock_img.crop.return_value = mock_img
    mock_img.convert.return_value = mock_img
    # save 方法：把假 bytes 寫入 buffer
    def fake_save(buf, format=None, quality=None):
        buf.write(b"FAKE_JPEG_BYTES")
    mock_img.save.side_effect = fake_save
    return mock_img


# -------------------------------------------------------------------
# Test 7: crop_video_cover spec v1 — 裁切計算正確
# -------------------------------------------------------------------
def test_crop_video_cover_spec_v1_dimensions():
    """spec v1: x 50~100%, y 0~80%, 取 3:4 portrait；呼叫 crop() 時框在正確範圍"""
    import core.actress_photo as _mod

    # 清空 cache 以免受其他測試污染
    _mod._CROP_CACHE.clear()

    mock_img = _make_fake_pil_image(width=400, height=500)

    with patch.dict("sys.modules", {"PIL": MagicMock(), "PIL.Image": MagicMock()}):
        with patch("core.actress_photo.io", _io):
            # 直接 patch PIL.Image.open
            with patch("builtins.__import__", side_effect=None):
                pass

    # 改用直接 mock PIL import
    mock_pil = MagicMock()
    mock_pil.Image.open.return_value = mock_img

    with patch.dict("sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}):
        _mod._CROP_CACHE.clear()
        result = _mod.crop_video_cover("/fake/cover.jpg", "v1")

    # 應有回傳值（bytes）
    assert result is not None
    assert isinstance(result, bytes)
    # crop() 應被呼叫一次
    mock_img.crop.assert_called_once()
    # 取得 crop 呼叫的 box
    (box,), _ = mock_img.crop.call_args
    cx0, cy0, cx1, cy1 = box
    # x0 應 >= 50% of 400 = 200（右半）
    assert cx0 >= 200, f"crop x0 ({cx0}) should be >= 200 (50% of width)"
    # y0 應 >= 0（在上 80% 範圍內，居中所以可能 > 0）
    assert cy0 >= 0, f"crop y0 ({cy0}) should be >= 0"
    # x1 應 <= 400
    assert cx1 <= 400
    # y1 應 <= 80% of 500 = 400
    assert cy1 <= 400, f"crop y1 ({cy1}) should be <= 400 (80% of height)"
    # 寬:高 約等於 3:4
    crop_w = cx1 - cx0
    crop_h = cy1 - cy0
    ratio = crop_w / crop_h
    assert abs(ratio - 3 / 4) < 0.05, f"aspect ratio {ratio} should be ~0.75 (3:4)"


# -------------------------------------------------------------------
# Test 8: cache hit — 不重複 open
# -------------------------------------------------------------------
def test_crop_video_cover_cache_hit():
    """相同 (path, mtime, spec) 第二次呼叫直接回 cache，不呼叫 Image.open"""
    from unittest.mock import MagicMock, patch
    import core.actress_photo as _mod

    _mod._CROP_CACHE.clear()
    fake_bytes = b"CACHED_JPEG"

    # cache key 現在包含 mtime；mock os.stat 回傳固定 mtime=1000.0
    fake_stat = MagicMock()
    fake_stat.st_mtime = 1000.0
    cache_key = ("/some/cover.jpg", 1000.0, "v1")
    _mod._CROP_CACHE[cache_key] = fake_bytes

    mock_pil = MagicMock()

    with patch("os.stat", return_value=fake_stat):
        with patch.dict("sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}):
            result = _mod.crop_video_cover("/some/cover.jpg", "v1")

    assert result == fake_bytes
    # PIL.Image.open 不應被呼叫
    mock_pil.Image.open.assert_not_called()


# -------------------------------------------------------------------
# Test 9: Pillow 未安裝 → None
# -------------------------------------------------------------------
def test_crop_video_cover_no_pillow(monkeypatch):
    """PIL import 失敗時回 None，不拋例外"""
    import core.actress_photo as _mod
    import sys

    _mod._CROP_CACHE.clear()

    # 確保 PIL 不在 sys.modules（或強制 ImportError）
    original_modules = sys.modules.copy()
    # 移除 PIL（若已 import）
    for key in list(sys.modules.keys()):
        if key == "PIL" or key.startswith("PIL."):
            sys.modules[key] = None  # type: ignore

    try:
        result = _mod.crop_video_cover("/nonexistent/cover.jpg", "v1")
    finally:
        # 還原
        for key in list(sys.modules.keys()):
            if key == "PIL" or key.startswith("PIL."):
                if key in original_modules:
                    sys.modules[key] = original_modules[key]
                else:
                    del sys.modules[key]

    assert result is None


# -------------------------------------------------------------------
# Test 10: cover_path 不存在 → None
# -------------------------------------------------------------------
def test_crop_video_cover_file_not_found(tmp_path):
    """cover_path 不存在時 crop_video_cover 回 None"""
    import core.actress_photo as _mod

    _mod._CROP_CACHE.clear()

    mock_pil = MagicMock()
    mock_pil.Image.open.side_effect = FileNotFoundError("no such file")

    nonexistent = str(tmp_path / "does_not_exist.jpg")

    with patch.dict("sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}):
        result = _mod.crop_video_cover(nonexistent, "v1")

    assert result is None


# -------------------------------------------------------------------
# Test 11: happy path — 真實 Pillow（若安裝）或 mock 完整流程
# -------------------------------------------------------------------
def test_crop_video_cover_happy_path(tmp_path):
    """crop_video_cover 正常流程：開圖 → crop → JPEG bytes"""
    import core.actress_photo as _mod

    _mod._CROP_CACHE.clear()

    # 建立假圖片檔（用 mock，不依賴真 Pillow）
    fake_cover = tmp_path / "cover.jpg"
    fake_cover.write_bytes(b"not_real_image")

    fake_bytes = b"FAKE_CROPPED_JPEG"
    mock_img = _make_fake_pil_image(width=800, height=600)

    def fake_save(buf, format=None, quality=None):
        buf.write(fake_bytes)
    mock_img.save.side_effect = fake_save

    mock_pil = MagicMock()
    mock_pil.Image.open.return_value = mock_img

    with patch.dict("sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}):
        _mod._CROP_CACHE.clear()
        result = _mod.crop_video_cover(str(fake_cover), "v1")

    assert result is not None
    assert result == fake_bytes
    # 結果應被 cache（key 包含真實 mtime）
    import os
    mtime = os.stat(str(fake_cover)).st_mtime
    assert _mod._CROP_CACHE[(str(fake_cover), mtime, "v1")] == fake_bytes


# -------------------------------------------------------------------
# Test 12: 未知 crop_spec → None
# -------------------------------------------------------------------
def test_crop_video_cover_unknown_spec_returns_none():
    """未知 crop_spec 回 None"""
    from core.actress_photo import crop_video_cover
    result = crop_video_cover("/fake/path.jpg", crop_spec="v99")
    assert result is None


# -------------------------------------------------------------------
# Test 13: LRU eviction — 超過 maxsize 時 evict 最舊的 entry
# -------------------------------------------------------------------
def test_crop_cache_lru_eviction():
    """超過 maxsize 時 evict 最舊的 entry，且 cache 大小維持在 maxsize 以內"""
    import core.actress_photo as _mod

    _mod._CROP_CACHE.clear()
    original_max = _mod._CROP_CACHE_MAXSIZE
    _mod._CROP_CACHE_MAXSIZE = 3
    try:
        _mod._cache_put(("a", 0.0, "v1"), b"a")
        _mod._cache_put(("b", 0.0, "v1"), b"b")
        _mod._cache_put(("c", 0.0, "v1"), b"c")
        # 加第 4 個，"a" 應被 evict（最早寫入）
        _mod._cache_put(("d", 0.0, "v1"), b"d")
        assert ("a", 0.0, "v1") not in _mod._CROP_CACHE, "最舊的 'a' 應被 evict"
        assert ("d", 0.0, "v1") in _mod._CROP_CACHE, "最新的 'd' 應在 cache"
        assert len(_mod._CROP_CACHE) == 3, "cache 大小應維持在 maxsize=3"
    finally:
        _mod._CROP_CACHE_MAXSIZE = original_max
        _mod._CROP_CACHE.clear()


# -------------------------------------------------------------------
# Test 14: LRU semantics — get 命中後 move_to_end，evict 順序變更
# -------------------------------------------------------------------
def test_crop_cache_lru_get_bumps_recency():
    """get 命中應延長 entry 壽命：put a/b/c → get a → put d → evict b 而非 a"""
    import core.actress_photo as _mod

    _mod._CROP_CACHE.clear()
    original_max = _mod._CROP_CACHE_MAXSIZE
    _mod._CROP_CACHE_MAXSIZE = 3
    try:
        _mod._cache_put(("a", 0.0, "v1"), b"a")
        _mod._cache_put(("b", 0.0, "v1"), b"b")
        _mod._cache_put(("c", 0.0, "v1"), b"c")
        # get "a" → 提升為最近使用
        assert _mod._cache_get(("a", 0.0, "v1")) == b"a"
        # 加第 4 個 → 應 evict "b"（現在最舊）而非 "a"
        _mod._cache_put(("d", 0.0, "v1"), b"d")
        assert ("a", 0.0, "v1") in _mod._CROP_CACHE, "get 後 'a' 應延壽"
        assert ("b", 0.0, "v1") not in _mod._CROP_CACHE, "現最舊的 'b' 應被 evict"
        assert len(_mod._CROP_CACHE) == 3
    finally:
        _mod._CROP_CACHE_MAXSIZE = original_max
        _mod._CROP_CACHE.clear()


# ===================================================================
# Fix 4: SSRF 白名單測試
# ===================================================================

def test_download_actress_photo_rejects_non_whitelisted_host(gfriends_dir):
    """photo_url host 不在白名單 → return False，不發 requests.get"""
    with patch("core.actress_photo.requests.get") as mock_get:
        result = download_actress_photo("テスト女優", "http://evil.com/x.jpg", "gfriends")
    assert result is False
    mock_get.assert_not_called()


def test_download_actress_photo_rejects_bad_scheme(gfriends_dir):
    """photo_url scheme 為 file:// → return False，不發 requests.get"""
    with patch("core.actress_photo.requests.get") as mock_get:
        result = download_actress_photo("テスト女優", "file:///etc/passwd", "graphis")
    assert result is False
    mock_get.assert_not_called()


# ===================================================================
# Fix 5: Atomic replace 測試
# ===================================================================

def test_download_actress_photo_failure_preserves_old(gfriends_dir):
    """requests.get 拋例外時，舊檔仍存在（atomic replace 未執行）"""
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    old_file = gfriends_dir / "田中美久.jpg"
    old_file.write_bytes(b"old_data")

    import requests as req_module
    with patch("core.actress_photo.requests.get",
               side_effect=req_module.exceptions.ConnectionError("fail")):
        result = download_actress_photo("田中美久", "https://www.graphis.ne.jp/photo.jpg", "graphis")

    assert result is False
    # 舊檔仍存在（因為 download 失敗，atomic replace 未執行，舊檔未被刪除）
    assert old_file.exists()
    assert old_file.read_bytes() == b"old_data"


def test_download_actress_photo_success_overwrites_old(gfriends_dir):
    """下載成功時舊檔被刪、新檔寫入（副檔名依 Content-Type）"""
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    old_file = gfriends_dir / "田中美久.jpg"
    old_file.write_bytes(b"old_data")

    mock_resp = make_mock_response(status_code=200, content_type="image/png",
                                   content=b"new_png_data")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        result = download_actress_photo("田中美久",
                                        "https://www.graphis.ne.jp/photo.png", "graphis")

    assert result is True
    # 舊 .jpg 應該被刪掉
    assert not old_file.exists()
    # 新 .png 存在
    new_file = gfriends_dir / "田中美久.png"
    assert new_file.exists()
    assert new_file.read_bytes() == b"new_png_data"


# ===================================================================
# Fix A (Codex round-2): 擴充 host 白名單 — jsdelivr / data.graphis
# ===================================================================

def test_download_actress_photo_accepts_jsdelivr_for_gfriends(gfriends_dir):
    """gfriends source: cdn.jsdelivr.net URL 應通過白名單驗證並觸發下載"""
    url = "https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/Content/最高画質/photo.jpg"
    mock_resp = make_mock_response(status_code=200, content_type="image/jpeg")
    with patch("core.actress_photo.requests.get", return_value=mock_resp) as mock_get:
        result = download_actress_photo("テスト女優A", url, "gfriends")
    assert result is True
    mock_get.assert_called_once()


def test_download_actress_photo_accepts_data_graphis_subdomain(gfriends_dir):
    """graphis source: data.graphis.ne.jp URL 應通過白名單驗證並觸發下載"""
    url = "https://data.graphis.ne.jp/images/actr/profile/001234.jpg"
    mock_resp = make_mock_response(status_code=200, content_type="image/jpeg")
    with patch("core.actress_photo.requests.get", return_value=mock_resp) as mock_get:
        result = download_actress_photo("テスト女優B", url, "graphis")
    assert result is True
    mock_get.assert_called_once()


