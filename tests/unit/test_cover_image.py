"""
test_cover_image.py — E1-E24 測試 find_cover_image() 4 層 fallback + NFO thumb 支援
"""
import logging
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.gallery_scanner import VideoScanner


# ─── NFO helper ───────────────────────────────────────────────────────────────

def make_nfo(path: Path, thumb: str = None) -> Path:
    """建立最小 NFO，可選含 <thumb> 元素"""
    thumb_tag = f"  <thumb>{thumb}</thumb>\n" if thumb else ""
    content = f'<?xml version="1.0" encoding="utf-8"?>\n<movie>\n{thumb_tag}</movie>'
    path.write_text(content, encoding='utf-8')
    return path


# ─── TestL1SameName ───────────────────────────────────────────────────────────

class TestL1SameName:
    """E1, E2 — 同名圖片優先（回歸）"""

    def test_e1_same_name_jpg(self, tmp_path):
        """E1: abc-123.mp4 + abc-123.jpg → 命中 L1"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        jpg = tmp_path / "abc-123.jpg"
        jpg.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(jpg)

    def test_e2_jpg_before_png(self, tmp_path):
        """E2: 同時有 abc-123.jpg 和 abc-123.png → jpg 優先（IMAGE_EXTENSIONS 順序）"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        jpg = tmp_path / "abc-123.jpg"
        png = tmp_path / "abc-123.png"
        jpg.write_bytes(b"")
        png.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(jpg)


# ─── TestL2StandardNames ──────────────────────────────────────────────────────

class TestL2StandardNames:
    """E3, E4 — 標準名稱（fanart/poster/cover/folder）回歸"""

    def test_e3_cover_fallback(self, tmp_path):
        """E3: 無同名圖 + cover.jpg → 命中 L2"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(cover)

    def test_e4_poster_before_cover(self, tmp_path):
        """E4: poster.jpg + cover.jpg → poster 優先（['fanart','poster','cover','folder'] 順序）"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        poster = tmp_path / "poster.jpg"
        cover = tmp_path / "cover.jpg"
        poster.write_bytes(b"")
        cover.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(poster)


# ─── TestL3NfoThumb ───────────────────────────────────────────────────────────

class TestL3NfoThumb:
    """E5-E10, E21, E22 — NFO <thumb> 路徑解析（新邏輯 + 跨平台）"""

    def test_e5_relative_thumb(self, tmp_path):
        """E5: <thumb>my_cover.png</thumb> 相對路徑，檔案存在 → 命中 L3"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        cover = tmp_path / "my_cover.png"
        cover.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(
            str(tmp_path / "abc-123.mp4"),
            nfo_thumb="my_cover.png"
        )
        assert result == str(cover)

    def test_e6_windows_absolute_path(self, tmp_path):
        """E6: <thumb>C:\\absolute\\cover.jpg</thumb> — mock is_file=True → 命中 L3"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        scanner = VideoScanner()
        # Mock Path.is_file to True for the resolved path
        with patch('core.gallery_scanner.Path') as MockPath:
            # 建立一個假的 path instance
            mock_path_instance = MagicMock()
            mock_path_instance.is_file.return_value = True
            mock_path_instance.__str__ = lambda self: "/mnt/c/absolute/cover.jpg"
            MockPath.return_value = mock_path_instance
            # 但保留真正的 Path for video_path（需要 parent/stem 等）
            # 用更精準的 approach：patch normalize_path 回傳合法 WSL 路徑，再 mock is_file
            pass

        # 改為直接測試 _resolve_thumb_path
        with patch('core.gallery_scanner.normalize_path', return_value="/mnt/c/absolute/cover.jpg"), \
             patch.object(Path, 'is_file', return_value=True):
            result = scanner._resolve_thumb_path(
                "C:\\absolute\\cover.jpg",
                tmp_path
            )
        assert result == "/mnt/c/absolute/cover.jpg"

    def test_e7_url_thumb_skipped(self, tmp_path):
        """E7: <thumb>https://example.com/cover.jpg</thumb> → URL skip → None"""
        scanner = VideoScanner()
        result = scanner._resolve_thumb_path(
            "https://example.com/cover.jpg",
            tmp_path
        )
        assert result is None

    def test_e8_no_thumb_element(self, tmp_path):
        """E8: nfo_thumb=None → L3 skip → fall through"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        (tmp_path / "x.jpg").write_bytes(b"")  # 只 1 jpg → L4 會命中
        scanner = VideoScanner()
        # nfo_thumb=None → L3 skip，L4: 1 mp4 + 1 jpg → 回傳 jpg
        result = scanner.find_cover_image(
            str(tmp_path / "abc-123.mp4"),
            nfo_thumb=None
        )
        assert result == str(tmp_path / "x.jpg")

    def test_e9_thumb_file_not_exist(self, tmp_path):
        """E9: <thumb> 指向不存在檔案 → _resolve_thumb_path 回傳 None"""
        scanner = VideoScanner()
        result = scanner._resolve_thumb_path(
            "nonexistent_cover.jpg",
            tmp_path
        )
        assert result is None

    def test_e10_no_nfo(self, tmp_path):
        """E10: 無 NFO (nfo_thumb 未設定) → L3 skip → fall through to L4"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        (tmp_path / "x.jpg").write_bytes(b"")  # L4 應命中
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(tmp_path / "x.jpg")

    def test_e21_file_uri_thumb(self, tmp_path):
        """E21: <thumb>file:///path/cover.jpg</thumb> → uri_to_fs_path 解析 → 命中 L3"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"")
        scanner = VideoScanner()
        # 用 Path.as_uri() 產生平台正確的 file:/// URI（不依賴手工字串拼接）
        file_uri = cover.as_uri()
        result = scanner._resolve_thumb_path(file_uri, tmp_path)
        assert result == str(cover)

    def test_e22_unc_path_wsl_valueerror(self, tmp_path):
        """E22: UNC backslash path → WSL normalize_path 拋 ValueError → None (fall through)"""
        scanner = VideoScanner()
        # 在 WSL 環境，normalize_path('\\\\NAS\\share\\...') 會拋 ValueError
        with patch('core.gallery_scanner.normalize_path', side_effect=ValueError("WSL 環境不支援 SMB 路徑")):
            result = scanner._resolve_thumb_path(
                "\\\\NAS\\share\\cover.jpg",
                tmp_path
            )
        assert result is None

    def test_e3_l3_takes_priority_over_l4(self, tmp_path):
        """L3 命中時不走到 L4（確保 fallback 優先順序正確）"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        nfo_cover = tmp_path / "nfo_cover.jpg"
        nfo_cover.write_bytes(b"")
        other_jpg = tmp_path / "other.jpg"
        other_jpg.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(
            str(tmp_path / "abc-123.mp4"),
            nfo_thumb="nfo_cover.jpg"
        )
        assert result == str(nfo_cover)


# ─── TestL4SafeFallback ───────────────────────────────────────────────────────

class TestL4SafeFallback:
    """E11-E15, E20, E23 — 安全 fallback 雙條件（mp4==1 AND 0<img<=2）"""

    def test_e11_one_mp4_one_jpg(self, tmp_path):
        """E11: 1 mp4 + 1 jpg（無同名/標準名/NFO）→ L4 命中，回傳 jpg"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        jpg = tmp_path / "x.jpg"
        jpg.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(jpg)

    def test_e12_one_mp4_two_jpg(self, tmp_path):
        """E12: 1 mp4 + 2 jpg → 1==1 AND 0<2<=2 成立 → 回傳 sorted 第一張"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        jpg1 = tmp_path / "a.jpg"
        jpg2 = tmp_path / "b.jpg"
        jpg1.write_bytes(b"")
        jpg2.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == str(jpg1)  # sorted first

    def test_e13_one_mp4_three_jpg(self, tmp_path):
        """E13: 1 mp4 + 3 jpg → 0<3<=2 不成立 → 空字串"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        (tmp_path / "a.jpg").write_bytes(b"")
        (tmp_path / "b.jpg").write_bytes(b"")
        (tmp_path / "c.jpg").write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == ""

    def test_e14_one_mp4_zero_jpg(self, tmp_path):
        """E14: 1 mp4 + 0 圖 → 空字串"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == ""

    def test_e15_flat_dir_many_videos(self, tmp_path):
        """E15: 平鋪 dir（1000 mp4 + 1000 jpg）→ 1000==1 不成立 → 空字串（修復 MTES-035 bug）"""
        # 只建少量模擬大型 flat dir
        for i in range(5):
            (tmp_path / f"video-{i:04d}.mp4").write_bytes(b"")
            (tmp_path / f"cover-{i:04d}.jpg").write_bytes(b"")
        scanner = VideoScanner()
        result = scanner.find_cover_image(str(tmp_path / "video-0000.mp4"))
        assert result == ""

    def test_e20_cross_pollution_blocked(self, tmp_path):
        """E20（Codex F2）: 2 mp4 + 2 jpg 混放 → L4 不 fallback → 空字串"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        (tmp_path / "def-456.mp4").write_bytes(b"")
        (tmp_path / "abc-123-cover.jpg").write_bytes(b"")
        (tmp_path / "def-456-cover.jpg").write_bytes(b"")
        scanner = VideoScanner()
        # def-456 沒同名 jpg → 應回空，不應誤抓 abc-123-cover.jpg
        result = scanner.find_cover_image(str(tmp_path / "def-456.mp4"))
        assert result == ""

    def test_e23_two_mp4_one_jpg(self, tmp_path):
        """E23: 2 mp4 + 1 jpg → 2==1 不成立 → 空字串"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        (tmp_path / "def-456.mp4").write_bytes(b"")
        (tmp_path / "cover.jpg").write_bytes(b"")
        scanner = VideoScanner()
        # "cover.jpg" 是 L2 標準名，需要用非標準名的圖片才能測到 L4
        # 改用非標準名
        (tmp_path / "cover.jpg").unlink()
        (tmp_path / "random.jpg").write_bytes(b"")
        result = scanner.find_cover_image(str(tmp_path / "abc-123.mp4"))
        assert result == ""


# ─── TestDirScanCache ─────────────────────────────────────────────────────────

class TestDirScanCache:
    """E16, E17, E19 — _dir_scan_cache 行為"""

    def test_e16_same_dir_cached(self, tmp_path):
        """E16: 同 dir 兩次呼叫 → os.scandir 只執行一次"""
        (tmp_path / "a.mp4").write_bytes(b"")
        (tmp_path / "b.jpg").write_bytes(b"")
        scanner = VideoScanner()

        call_count = [0]
        original_scandir = os.scandir

        def counting_scandir(path):
            call_count[0] += 1
            return original_scandir(path)

        with patch('os.scandir', side_effect=counting_scandir):
            scanner._scan_dir(tmp_path)
            scanner._scan_dir(tmp_path)

        # 第一次 scandir，第二次 cache hit
        assert call_count[0] == 1

    def test_e17_different_dirs_separate(self, tmp_path):
        """E17: 不同 dir → 各自 scandir"""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "v.mp4").write_bytes(b"")
        (dir_b / "v.mp4").write_bytes(b"")
        scanner = VideoScanner()

        call_count = [0]
        original_scandir = os.scandir

        def counting_scandir(path):
            call_count[0] += 1
            return original_scandir(path)

        with patch('os.scandir', side_effect=counting_scandir):
            scanner._scan_dir(dir_a)
            scanner._scan_dir(dir_b)

        assert call_count[0] == 2

    def test_e19_new_instance_empty_cache(self):
        """E19: 新建 VideoScanner → _dir_scan_cache 為空"""
        s1 = VideoScanner()
        s1._dir_scan_cache["fake_key"] = ([], [])
        s2 = VideoScanner()
        assert len(s2._dir_scan_cache) == 0


# ─── TestEdgeCases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    """E18, E24 — Edge cases"""

    def test_e18_bare_ampersand_nfo(self, tmp_path):
        """E18: NFO 含 bare & → sanitize_nfo_bytes 已處理，<thumb> 正常讀取"""
        (tmp_path / "abc-123.mp4").write_bytes(b"")
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"")
        nfo_path = tmp_path / "abc-123.nfo"
        # 含 bare & 的 NFO
        nfo_content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<movie>\n'
            '  <title>AT&T Special</title>\n'
            f'  <thumb>cover.jpg</thumb>\n'
            '</movie>'
        )
        nfo_path.write_bytes(nfo_content.encode('utf-8'))
        scanner = VideoScanner()
        nfo_info = scanner.parse_nfo(str(nfo_path))
        assert nfo_info is not None
        assert nfo_info.nfo_thumb == "cover.jpg"

    def test_e24_oserror_logged(self, tmp_path, caplog):
        """E24: _scan_dir OSError → logger.warning + 空 tuple"""
        scanner = VideoScanner()
        fake_dir = tmp_path / "nonexistent"
        with caplog.at_level(logging.WARNING, logger="core.gallery_scanner"):
            videos, images = scanner._scan_dir(fake_dir)
        assert videos == []
        assert images == []
        assert any(
            "掃描" in r.message or "scan" in r.message.lower()
            for r in caplog.records
        )

    def test_resolve_thumb_empty_string(self, tmp_path):
        """_resolve_thumb_path 收到空字串 → None"""
        scanner = VideoScanner()
        result = scanner._resolve_thumb_path("", tmp_path)
        assert result is None

    def test_resolve_thumb_http_url(self, tmp_path):
        """http:// URL → None"""
        scanner = VideoScanner()
        result = scanner._resolve_thumb_path("http://example.com/cover.jpg", tmp_path)
        assert result is None

    def test_resolve_thumb_posix_absolute_exists(self, tmp_path):
        """POSIX 絕對路徑，檔案存在 → 回傳路徑"""
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"")
        scanner = VideoScanner()
        result = scanner._resolve_thumb_path(str(cover), tmp_path)
        assert result == str(cover)

    def test_resolve_thumb_unc_forward_slash(self, tmp_path):
        """UNC // 正斜線 → normalize_path 處理（WSL 不拋 ValueError，is_file() 兜底）"""
        scanner = VideoScanner()
        # //NAS/share/cover.jpg 在 WSL: normalize_path 不拋，但 is_file() 返回 False
        result = scanner._resolve_thumb_path("//NAS/share/cover.jpg", tmp_path)
        # 因為路徑不存在，should be None
        assert result is None


# ─── TestParseNfoThumb ────────────────────────────────────────────────────────

class TestParseNfoThumb:
    """驗證 parse_nfo() 能正確讀取 <thumb> 元素"""

    def test_parse_nfo_with_thumb(self, tmp_path):
        """NFO 含 <thumb> → nfo_info.nfo_thumb 正確設定"""
        nfo_path = tmp_path / "test.nfo"
        make_nfo(nfo_path, thumb="my_cover.jpg")
        scanner = VideoScanner()
        nfo_info = scanner.parse_nfo(str(nfo_path))
        assert nfo_info is not None
        assert nfo_info.nfo_thumb == "my_cover.jpg"

    def test_parse_nfo_without_thumb(self, tmp_path):
        """NFO 無 <thumb> → nfo_info.nfo_thumb 為 None"""
        nfo_path = tmp_path / "test.nfo"
        make_nfo(nfo_path, thumb=None)
        scanner = VideoScanner()
        nfo_info = scanner.parse_nfo(str(nfo_path))
        assert nfo_info is not None
        assert nfo_info.nfo_thumb is None

    def test_video_info_to_dict_excludes_nfo_thumb(self):
        """nfo_thumb 欄位不序列化進 to_dict()"""
        from core.gallery_scanner import VideoInfo
        vi = VideoInfo(title="test", nfo_thumb="cover.jpg")
        d = vi.to_dict()
        assert "nfo_thumb" not in d
