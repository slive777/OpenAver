"""
Unit tests for core/actress_photo.py
Tests cover: download, rescrape, exception handling, HTTP errors, delete, special chars
"""
import logging
import os

import pytest
from unittest.mock import patch, MagicMock, ANY

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


# -------------------------------------------------------------------
# Test 3: requests exception → False
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# Test 5: delete_local_photo 後 get_local_photo_path 回 None
# -------------------------------------------------------------------
def test_delete_photo_then_get_returns_none(gfriends_dir):
    """delete_local_photo() 後 get_local_photo_path() 回 None"""
    # 先下載一張
    mock_resp = make_mock_response(status_code=200, content_type="image/png")
    with patch("core.actress_photo.requests.get", return_value=mock_resp):
        download_actress_photo("青山あかね", "https://faws.xcity.jp/actress/large/image/person/1/photo.jpg", "xcity")

    # 確認下載成功
    assert get_local_photo_path("青山あかね") is not None

    # 刪除
    deleted = delete_local_photo("青山あかね")
    assert deleted is True

    # 現在應回 None
    assert get_local_photo_path("青山あかね") is None


# -------------------------------------------------------------------
# Test 5b: delete_local_photo 的 showcase revision bump（PR#207 Codex P2）
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# Test 6: 特殊字元女優名（含 ·）
# -------------------------------------------------------------------


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


# -------------------------------------------------------------------
# Test 9: Pillow 未安裝 → None
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Test 10: cover_path 不存在 → None
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# Test 11: happy path — 真實 Pillow（若安裝）或 mock 完整流程
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# Test 12: 未知 crop_spec → None
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Test 13: LRU eviction — 超過 maxsize 時 evict 最舊的 entry
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# Test 14: LRU semantics — get 命中後 move_to_end，evict 順序變更
# -------------------------------------------------------------------


# ===================================================================
# Fix 4: SSRF 白名單測試
# ===================================================================

def test_download_actress_photo_rejects_non_whitelisted_host(gfriends_dir):
    """photo_url host 不在白名單 → return False，不發 requests.get"""
    with patch("core.actress_photo.requests.get") as mock_get:
        result = download_actress_photo("テスト女優", "http://evil.com/x.jpg", "gfriends")
    assert result is False
    mock_get.assert_not_called()


def test_download_actress_photo_redirect_not_followed(gfriends_dir, caplog):
    """白名單內 host 回 302 指向內網 → return False，get 帶 allow_redirects=False"""
    photo_url = "https://www.graphis.ne.jp/photo.jpg"
    mock_resp = make_mock_response(status_code=302)
    mock_resp.headers = {"Location": "http://127.0.0.1/evil", "Content-Type": "text/html"}

    with caplog.at_level(logging.WARNING, logger="OpenAver.core.actress_photo"):
        with patch(
            "core.actress_photo.requests.get", return_value=mock_resp
        ) as mock_get:
            result = download_actress_photo("テスト女優", photo_url, "graphis")

    assert result is False
    mock_get.assert_called_once_with(
        photo_url, headers=ANY, timeout=15, allow_redirects=False
    )
    assert any(
        "www.graphis.ne.jp" in r.getMessage()
        and "302" in r.getMessage()
        and "127.0.0.1" in r.getMessage()
        for r in caplog.records
    ), f"expected 3xx warning with host/status/Location host, got: {caplog.text!r}"
    # MUST NOT：完整 Location URL、也不走既有「下載失敗 HTTP」那條（含完整 photo_url）
    assert "http://127.0.0.1/evil" not in caplog.text
    assert "下載失敗，HTTP" not in caplog.text


# ===================================================================
# Fix 5: Atomic replace 測試
# ===================================================================


def test_download_actress_photo_replace_failure_preserves_old(gfriends_dir):
    """🔴 Codex P1 回歸鎖：os.replace 失敗時，舊照片必須原封不動。

    上面那條只 mock requests.get 失敗——那發生在刪舊檔**之前**，抓不到本 bug。
    原本的順序是「下載成功 → 刪舊檔 → os.replace」，若 replace 拋例外，舊檔已經
    沒了、finally 又清掉 tmp → **新舊照片全部消失**，違反 spec-100 §3.3 失敗矩陣
    「寫檔失敗仍保留舊圖、最壞只退回置中裁」的硬保證。

    不是理論極端 case：Windows 上防毒即時掃描／檔案總管縮圖快取持有 final_path 的
    handle，就會讓 os.replace 拋 PermissionError——Windows 桌面版是本專案主力族群。
    同型 bug 已於 TASK-100a-T2 在 _write_actress_photo 修掉，此處是漏掉的雙胞胎。

    mutation：把刪舊檔迴圈移回 os.replace 之前 → 本測試必紅。
    """
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    old_file = gfriends_dir / "田中美久.jpg"
    old_file.write_bytes(b"old_data")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.content = b"new_data"

    with patch("core.actress_photo.requests.get", return_value=mock_resp), \
         patch("core.atomic_write.os.replace", side_effect=PermissionError("被防毒鎖住")):
        result = download_actress_photo("田中美久", "https://www.graphis.ne.jp/photo.jpg", "graphis")

    assert result is False
    # 🔴 承重斷言：replace 失敗 → 舊照片還在、bytes 一個位元都沒變
    assert old_file.exists(), "os.replace 失敗卻把舊照片刪了 —— spec §3.3 失敗矩陣不成立"
    assert old_file.read_bytes() == b"old_data"


# ===================================================================
# TASK-113d-T2: A4 固定 temp 檔名 → mkstemp（CD-113d-4 行為變更）
# ===================================================================


# ===================================================================
# Fix A (Codex round-2): 擴充 host 白名單 — jsdelivr / data.graphis
# ===================================================================


# ===================================================================
# PR#108 Codex 三審 P2：清舊檔失敗留下殘檔時，解析必須挑「剛寫入的新檔」
# ===================================================================

def test_get_local_photo_path_prefers_newest_when_stale_sibling_survives(gfriends_dir):
    """兩個 {safe}.* 並存（Windows 鎖檔導致清舊檔 warn-and-continue）時，
    必須解析到剛寫入的新檔，不可回字母序在前的舊殘檔。

    🔴 為什麼要強制 glob 順序：`Path.glob` 回 scandir 序——NTFS 是名稱序 B-tree
    （.jpg < .png ⇒ 舊檔必先），ext4 卻是 name-hash 序（約 50/50）。不 patch 就是
    在 dev/CI(ext4) 擲硬幣，mutation 只有一半機率紅＝假綠。這裡固定成 NTFS 序，
    讓 mutation 必紅。（patch glob 的先例：test_api_actress.py 同檔既有做法）

    mutation：`get_local_photo_path` 改回 `return matches[0]` → 本條必紅。
    """
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    old = gfriends_dir / "テスト女優C.jpg"
    old.write_bytes(b"STALE")
    os.utime(old, (1_000_000, 1_000_000))   # 明確拉老，不靠 wall-clock 粒度
    new = gfriends_dir / "テスト女優C.png"
    new.write_bytes(b"FRESH")

    # NTFS 序：舊 .jpg 排第一（matches[0] 就會踩雷）
    with patch.object(type(gfriends_dir), "glob", lambda self, pat: [old, new]):
        found = get_local_photo_path("テスト女優C")

    assert found == new, f"應解析到新寫入的 .png，實得 {found}"
    assert found.read_bytes() == b"FRESH"




# ===================================================================
# 187a-T6：女優頭像改以端點臉心裁切
# ===================================================================
import io as _t6_io

import pytest as _t6_pytest
from PIL import Image as _T6Image

from core.ai_services import faces as _t6_faces
from core.ai_services import faces_detect as _t6_fd
from core.ai_services.embeddings import EndpointError as _T6EndpointError
from core.focal.detector import select_focal_from_boxes as _t6_select

_T6_W, _T6_H = 600, 400


@_t6_pytest.fixture(autouse=True)
def _t6_reset_caches():
    import core.actress_photo as _m
    _m._CROP_CACHE.clear()
    _t6_fd._reset_detect_cache()
    yield
    _m._CROP_CACHE.clear()
    _t6_fd._reset_detect_cache()


def _t6_cover(tmp_path):
    """600x400 水平漸層：像素值 = 100 + 155*x/(W-1)，全部 >= 100（黑邊=0 一眼可辨）。"""
    img = _T6Image.new("RGB", (_T6_W, _T6_H))
    px = img.load()
    for x in range(_T6_W):
        v = 100 + int(155 * x / (_T6_W - 1))
        for y in range(_T6_H):
            px[x, y] = (v, v, v)
    p = tmp_path / "cover.jpg"
    img.save(p, format="JPEG", quality=95)
    return str(p)


def _t6_endpoint(monkeypatch, *, enabled=True, boxes=None, error=None):
    calls = []
    cfg = {"ai_services": {"faces": {
        "enabled": enabled, "url": "http://faces.test", "api_key": "", "model": "m"}}}
    monkeypatch.setattr(_t6_fd, "load_config", lambda: cfg)
    monkeypatch.setattr(_t6_fd.faces_state, "observe_success", lambda *a, **k: None)
    monkeypatch.setattr(_t6_fd, "observe_model", lambda *a, **k: None)

    def fake_detect(c, data_uri, *, profile="background"):
        calls.append(profile)
        if error is not None:
            raise error
        return _t6_faces.FacesResult(boxes=list(boxes or []), model="m")

    monkeypatch.setattr(_t6_fd.faces, "detect", fake_detect)
    return calls


# 兩種獨立失敗：臉在中間（中心要對）、臉在左緣（clamp，不出黑邊）
# 若下方 precondition 斷言失敗：只調整 Box 數值，不要改斷言。
_T6_FACES = {
    "mid": [_t6_faces.Box(0.30, 0.20, 0.10, 0.15, 0.9), _t6_faces.Box(0.38, 0.22, 0.10, 0.15, 0.8)],
    "edge": [_t6_faces.Box(0.00, 0.20, 0.10, 0.15, 0.9)],
}


@_t6_pytest.mark.parametrize("case", ["mid", "edge"])
def test_cover_crop_follows_main_face(tmp_path, monkeypatch, case):
    """收藏合輯封面的女優 → 頭像要裁在主要那張臉上，臉在邊緣也不能出黑邊。"""
    import core.actress_photo as _m
    path = _t6_cover(tmp_path)
    _t6_endpoint(monkeypatch, boxes=_T6_FACES[case])
    fx, fy = _t6_select(_T6_FACES[case], _T6_W, _T6_H, 0.75)
    if case == "mid":
        assert 0.25 < fx < 0.75 and abs(fx - 0.75) > 0.2  # precondition：非 clamp、且不同於固定裁法中心
    else:
        assert fx < 0.15  # precondition：臉貼左緣，未 clamp 會 x0 < 0
    out = _m.crop_video_cover(path, "v1")
    assert out is not None
    im = _T6Image.open(_t6_io.BytesIO(out)).convert("L")
    assert im.size == (240, 320)
    assert im.getextrema()[0] > 60  # 沒有 clamp 會有 0 值黑邊
    if case == "mid":
        mean = sum(im.getdata()) / (im.size[0] * im.size[1])
        assert abs(mean - (100 + 155 * fx)) < 8  # 裁窗中心＝主群質心


@_t6_pytest.mark.parametrize("mode", ["disabled", "no_face", "endpoint_down"])
def test_cover_crop_unchanged_without_face(tmp_path, monkeypatch, mode):
    """沒開端點／封面沒臉／端點掛掉 → 頭像與昨天（固定右半上 80% 置中）逐位元相同。"""
    import core.actress_photo as _m
    path = _t6_cover(tmp_path)
    kwargs = {"disabled": {"enabled": False},
              "no_face": {"boxes": []},
              "endpoint_down": {"error": _T6EndpointError("unreachable", "timeout")}}[mode]
    calls = _t6_endpoint(monkeypatch, **kwargs)
    # 獨立算出的固定裁法 golden：右半上 80% 取 3:4 置中 → (330, 0, 570, 320)
    buf = _t6_io.BytesIO()
    _T6Image.open(path).crop((330, 0, 570, 320)).convert("RGB").save(buf, format="JPEG", quality=85)
    out = _m.crop_video_cover(path, "v1")
    assert out == buf.getvalue()
    assert len(calls) == (0 if mode == "disabled" else 1)  # 非 vacuous：確實走過（或沒走過）端點
