import ast
import pytest
from pathlib import Path
from unittest.mock import patch
from core.gallery_scanner import VideoScanner


# ============ 靜態守衛：確保 import json 存在 ============

class TestGalleryScannerImports:
    def test_import_json_present(self):
        """靜態守衛：gallery_scanner.py 必須 import json（防止再次誤刪）"""
        source = Path(__file__).parent.parent.parent / "core" / "gallery_scanner.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert "json" in imported_names, (
            "core/gallery_scanner.py 缺少 `import json`；"
            "load_cache/save_cache 依賴此模組"
        )

class TestGalleryScanner:
    @pytest.fixture
    def scanner(self):
        return VideoScanner()

    def test_parse_nfo_valid(self, scanner, tmp_path):
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>Test Title</title>
            <originaltitle>Original Test Title</originaltitle>
            <num>TEST-001</num>
            <maker>TestMaker</maker>
            <release>2023-01-01</release>
            <actor>
                <name>Actor1</name>
            </actor>
            <actor>
                <name>Actor2</name>
            </actor>
            <genre>Tag1</genre>
            <tag>Tag2</tag>
        </movie>
        """
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")
        
        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == "Test Title"
        assert info.num == "TEST-001"
        assert info.maker == "TestMaker"
        assert info.date == "2023-01-01"
        assert info.actor == "Actor1,Actor2"
        assert sorted(info.genre.split(",")) == sorted(["Tag1", "Tag2"])

    def test_parse_nfo_invalid(self, scanner, tmp_path):
        # 標籤未閉合的無效 XML
        xml_content = """<?xml version="1.0" encoding="utf-8"?><movie><title>Test</movie>"""
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")
        
        info = scanner.parse_nfo(str(nfo_path))
        assert info is None

    def test_parse_nfo_bare_ampersand(self, scanner, tmp_path):
        """NFO 包含 bare & (如 AT&T)，sanitize_nfo_bytes 應修正為 &amp;"""
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>AT&T Special</title>
            <num>AMP-001</num>
        </movie>
        """
        nfo_path = tmp_path / "ampersand.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == "AT&T Special"
        assert info.num == "AMP-001"

    def test_parse_nfo_empty_file(self, scanner, tmp_path):
        """空檔案應回傳 None（XML 解析失敗）"""
        nfo_path = tmp_path / "empty.nfo"
        nfo_path.write_text("", encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is None

    def test_parse_filename_fallback_naming_format(self, scanner):
        # 預設 naming formats 的 \[ 會被 _compile_naming_formats 中的 re.escape
        # 雙重轉義為 \\[，所以帶 [...] 的檔名不會匹配 naming format。
        # 結果走 fallback 路徑：find_num_from_filename 提取番號，title = stem。
        filename = "ActorName - [TEST-002]Some Title Here.mp4"
        info = scanner.parse_filename(filename)
        # find_num_from_filename 提取到 TEST-002
        assert info.num == "TEST-002"
        # title fallback 為整個 stem（因 naming format 未命中）
        assert info.title == "ActorName - [TEST-002]Some Title Here"
        # actor 無法從 fallback 路徑取得
        assert info.actor == ""

    def test_parse_filename_fallback_regex(self, scanner):
        # 測試檔名不符合 format 但能用 find_num_from_filename 取出番號
        # 這時候 title 會直接用檔名
        filename = "Random Words FC2-PPV-1234567 And More.mp4"
        info = scanner.parse_filename(filename)
        assert info.num == "FC2PPV-1234567"
        assert info.title == "Random Words FC2-PPV-1234567 And More"
        assert info.actor == ""

    def test_parse_filename_fallback_stem(self, scanner):
        # 完全沒有符合的，全靠 fallback
        filename = "Just Some Random Text.mp4"
        info = scanner.parse_filename(filename)
        assert info.num == ""
        assert info.title == "Just Some Random Text"

    def test_find_cover_image_exact_match(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-003.mp4"
        cover_path = tmp_path / "TEST-003.jpg"
        cover_path.touch()
        
        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_fallback_names(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-004.mp4"
        # 不存在同名圖片，但存在 poster.jpg
        cover_path = tmp_path / "poster.jpg"
        cover_path.touch()
        
        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_any_image(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-005.mp4"
        # 既沒有同名，也沒有 poster/fanart，只有隨機命名的 JPG
        # L4 安全 fallback：目錄 1 mp4 + 1 jpg → 命中
        video_path.touch()
        cover_path = tmp_path / "random_image.jpg"
        cover_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(cover_path)

    def test_find_cover_image_none(self, scanner, tmp_path):
        video_path = tmp_path / "TEST-006.mp4"
        # 資料夾裡沒圖片
        found = scanner.find_cover_image(str(video_path))
        assert found == ""


# ============ normalize_maker() 兩步邏輯 ============

class TestNormalizeMaker:
    """VideoScanner.normalize_maker() 的 name mapping → prefix fallback 兩步邏輯"""

    MOCK_NAME_MAPPING = {
        "エスワン ナンバーワンスタイル": "S1",
        "ムーディーズ": "Moodyz",
    }
    MOCK_PREFIX_MAPPING = {
        "SONE": "S1",
        "MIAA": "Moodyz",
    }

    @pytest.fixture
    def scanner(self):
        """建立 VideoScanner，mock load_name_mapping + load_prefix_mapping"""
        with patch("core.gallery_scanner.load_name_mapping",
                   return_value=self.MOCK_NAME_MAPPING), \
             patch("core.gallery_scanner.load_prefix_mapping",
                   return_value=self.MOCK_PREFIX_MAPPING):
            return VideoScanner()

    def test_name_mapping_hit_skips_prefix(self, scanner):
        """Step 1 name mapping 命中 → 回傳 name 結果，不查 prefix"""
        result = scanner.normalize_maker("SONE-123", "エスワン ナンバーワンスタイル")
        assert result == "S1"

    def test_name_mapping_miss_prefix_hit(self, scanner):
        """Step 1 miss → Step 2 prefix 命中 → 回傳 prefix 結果"""
        result = scanner.normalize_maker("MIAA-456", "SomeMaker")
        assert result == "Moodyz"

    def test_both_miss_returns_original(self, scanner):
        """name + prefix 都 miss → 回傳原值"""
        result = scanner.normalize_maker("ZZXX-001", "UnknownMaker")
        assert result == "UnknownMaker"

    def test_empty_maker_skips_name_mapping(self, scanner):
        """maker 為空 → 跳過 name mapping → 走 prefix（prefix 命中）"""
        result = scanner.normalize_maker("MIAA-456", "")
        # maker 空字串：name mapping skip，prefix 命中 MIAA → Moodyz
        assert result == "Moodyz"

    def test_empty_num_name_mapping_miss_returns_original(self, scanner):
        """num 為空且 name mapping miss → 回傳原值（不查 prefix）"""
        result = scanner.normalize_maker("", "UnknownMaker")
        assert result == "UnknownMaker"

    def test_empty_num_name_mapping_hit(self, scanner):
        """num 為空但 name mapping 命中 → Step 1 直接回傳（不依賴 num）"""
        result = scanner.normalize_maker("", "エスワン ナンバーワンスタイル")
        assert result == "S1"

    def test_name_mapping_empty_dict_falls_through_to_prefix(self):
        """name_mapping 為空 dict → Step 1 無命中 → Step 2 prefix fallback 正常"""
        with patch("core.gallery_scanner.load_name_mapping", return_value={}), \
             patch("core.gallery_scanner.load_prefix_mapping",
                   return_value=self.MOCK_PREFIX_MAPPING):
            sc = VideoScanner()
        result = sc.normalize_maker("SONE-123", "AnyMaker")
        assert result == "S1"


class TestFastScanDirectorySkipCallback:
    """spec-48a §a5 Codex fix — fast_scan_directory on_skip callback

    背景：Windows 長路徑觸發 os.DirEntry.stat()/.is_file() 拋 OSError，
    導致 entry 根本不進 results。T5 的 _collect_long_paths(results) 只看「掃到」
    的檔案，永遠抓不到「因長而失敗」的那批。on_skip callback 讓呼叫端能捕捉
    這些被跳過的 entry.path，再由呼叫端以 >260 篩出長路徑加進警告。
    """

    def test_on_skip_called_on_inner_entry_oserror(self, tmp_path, monkeypatch):
        """當 entry.is_file() 拋 OSError，on_skip 必須被呼叫且帶 entry.path"""
        import os
        from core.gallery_scanner import fast_scan_directory

        # 建一個空目錄作為掃描根
        scan_root = tmp_path / "scan"
        scan_root.mkdir()

        # 建一個 fake DirEntry：is_dir/is_file 均拋 OSError
        class FakeBadEntry:
            def __init__(self, path):
                self.path = path
                self.name = os.path.basename(path)

            def is_dir(self, follow_symlinks=False):
                raise OSError(206, "The filename or extension is too long")

            def is_file(self, follow_symlinks=False):
                raise OSError(206, "The filename or extension is too long")

            def stat(self, follow_symlinks=True):
                raise OSError(206, "The filename or extension is too long")

        bad_entry_path = str(scan_root / ("longname" + "x" * 300 + ".mp4"))
        fake_entry = FakeBadEntry(bad_entry_path)

        # monkeypatch os.scandir — 僅對 scan_root 回傳 fake entry
        real_scandir = os.scandir

        class FakeScandirCtx:
            def __init__(self, entries):
                self._entries = entries

            def __enter__(self):
                return iter(self._entries)

            def __exit__(self, *a):
                return False

        def fake_scandir(path):
            if os.path.normpath(path) == os.path.normpath(str(scan_root)):
                return FakeScandirCtx([fake_entry])
            return real_scandir(path)

        monkeypatch.setattr("core.gallery_scanner.os.scandir", fake_scandir)

        calls = []
        results = fast_scan_directory(
            str(scan_root), {'.mp4'}, 0,
            on_skip=lambda p, e: calls.append((p, type(e).__name__)),
        )

        # 結果：entry 沒進 results，但 on_skip 被呼叫一次
        assert results == [], "拋 OSError 的 entry 不應進入 results"
        assert len(calls) == 1, "on_skip 應被呼叫一次"
        assert calls[0][0] == bad_entry_path, "on_skip 應收到 entry.path"
        assert calls[0][1] == 'OSError', "on_skip 應收到實際的 exception 類型"

    def test_on_skip_called_on_outer_scandir_oserror(self, tmp_path, monkeypatch):
        """當外層 os.scandir() 自己拋 OSError（整個目錄無法開），on_skip 收到目錄路徑"""
        import os
        from core.gallery_scanner import fast_scan_directory

        scan_root = tmp_path / "scan"
        scan_root.mkdir()

        def fake_scandir(path):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("core.gallery_scanner.os.scandir", fake_scandir)

        calls = []
        results = fast_scan_directory(
            str(scan_root), {'.mp4'}, 0,
            on_skip=lambda p, e: calls.append((p, type(e).__name__)),
        )

        assert results == []
        assert len(calls) == 1, "外層 scandir 失敗 on_skip 應被呼叫一次"
        assert calls[0][0] == str(scan_root)
        assert calls[0][1] == 'PermissionError'

    def test_on_skip_none_is_default_silent(self, tmp_path, monkeypatch):
        """on_skip=None（或未傳）時完全靜默，保持既有 caller 行為不變"""
        import os
        from core.gallery_scanner import fast_scan_directory

        scan_root = tmp_path / "scan"
        scan_root.mkdir()

        def fake_scandir(path):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr("core.gallery_scanner.os.scandir", fake_scandir)

        # 不傳 on_skip — 不應拋，回傳空 list
        results = fast_scan_directory(str(scan_root), {'.mp4'}, 0)
        assert results == []

    def test_on_skip_callback_exception_does_not_break_scan(self, tmp_path, monkeypatch):
        """callback 本身拋例外不得中斷掃描（safety net）"""
        import os
        from core.gallery_scanner import fast_scan_directory

        scan_root = tmp_path / "scan"
        scan_root.mkdir()

        def fake_scandir(path):
            raise OSError(206, "long path")

        monkeypatch.setattr("core.gallery_scanner.os.scandir", fake_scandir)

        def angry_callback(p, e):
            raise RuntimeError("callback boom")

        # 不應把 RuntimeError 傳出來
        results = fast_scan_directory(str(scan_root), {'.mp4'}, 0, on_skip=angry_callback)
        assert results == []


class TestCollectLongPaths:
    """spec-48a §a5 契約 1+2 — _collect_long_paths helper 行為"""

    def test_path_over_260_detected(self):
        from web.routers.scanner import _collect_long_paths
        long = 'C:\\' + 'a' * 260  # len = 263
        short = 'C:\\short.mp4'
        result = _collect_long_paths([{'path': long}, {'path': short}])
        assert result == [long], "只該抓到超過 260 的路徑"

    def test_path_exactly_260_not_flagged(self):
        """恰好 260 字元不算長路徑（> 260 而非 >= 260）"""
        from web.routers.scanner import _collect_long_paths
        exactly = 'C:\\' + 'a' * 257  # 3 + 257 = 260
        assert len(exactly) == 260
        assert _collect_long_paths([{'path': exactly}]) == []

    def test_path_261_flagged(self):
        from web.routers.scanner import _collect_long_paths
        p = 'C:\\' + 'a' * 258  # 3 + 258 = 261
        assert len(p) == 261
        assert _collect_long_paths([{'path': p}]) == [p]

    def test_empty_input(self):
        from web.routers.scanner import _collect_long_paths
        assert _collect_long_paths([]) == []

    def test_custom_threshold(self):
        """threshold 參數可覆寫（方便測試，實際 caller 用預設 260）"""
        from web.routers.scanner import _collect_long_paths
        p = 'C:\\' + 'a' * 10  # len = 13
        assert _collect_long_paths([{'path': p}], threshold=5) == [p]
        assert _collect_long_paths([{'path': p}], threshold=20) == []

    def test_helper_does_not_check_platform(self):
        """helper 本身不 gate 平台（gate 是呼叫端責任，見 Canonical #13）"""
        from web.routers.scanner import _collect_long_paths
        # 即使在 linux 上呼叫 helper 也會收集 — 這是刻意的，避免 helper 被平台綁死
        long = 'C:\\' + 'a' * 300
        # 不 monkeypatch sys.platform，直接在當前平台驗證 helper 無 platform 判斷
        assert _collect_long_paths([{'path': long}]) == [long]


class TestEmitLongPathWarnings:
    """spec-48a §a5 契約 4 — _emit_long_path_warnings helper 行為"""

    def test_warning_emitted_when_non_empty(self, caplog):
        """非空 list 應輸出 [a5] warning 到 scanner logger"""
        import logging
        from core.logger import get_logger
        from web.routers.scanner import _emit_long_path_warnings
        logger = get_logger('web.routers.scanner')
        long_paths = ['C:\\' + 'a' * 280, 'C:\\' + 'b' * 290]
        with caplog.at_level(logging.WARNING, logger='web.routers.scanner'):
            _emit_long_path_warnings(logger, long_paths)
        messages = [r.message for r in caplog.records]
        # 第一則 summary + 每個路徑各一則（共 3）
        assert any('[a5]' in m and '2' in m for m in messages), "summary warning 缺失"
        assert any('a' * 280 in m for m in messages), "第一個路徑未輸出"
        assert any('b' * 290 in m for m in messages), "第二個路徑未輸出"

    def test_silent_when_empty(self, caplog):
        """空 list 應完全靜默（不輸出任何 record）"""
        import logging
        from core.logger import get_logger
        from web.routers.scanner import _emit_long_path_warnings
        logger = get_logger('web.routers.scanner')
        with caplog.at_level(logging.WARNING, logger='web.routers.scanner'):
            _emit_long_path_warnings(logger, [])
        assert not any('[a5]' in r.message for r in caplog.records)


class TestScannerSampleImagesValidationPass:
    """spec-48b §b1 AC#2 — _validate_sample_images + _run_sample_images_cleanup_pass"""

    def test_validate_keeps_existing_uri(self, tmp_path):
        """磁碟存在的 URI → 保留在回傳 list"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        # uri_to_fs_path 正常回傳路徑，os.path.exists 回傳 True
        with patch("core.gallery_scanner.uri_to_fs_path", return_value="/fake/path/s1.jpg"), \
             patch("os.path.exists", return_value=True):
            result = _validate_sample_images(
                ["file:///fake/path/s1.jpg"],
                video_path="file:///fake/v1.mp4",
            )

        assert result == ["file:///fake/path/s1.jpg"], "磁碟存在的 URI 應保留"

    def test_validate_drops_missing_uri(self, tmp_path):
        """磁碟不存在的 URI → 從回傳 list 剔除"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.uri_to_fs_path", return_value="/fake/path/missing.jpg"), \
             patch("os.path.exists", return_value=False):
            result = _validate_sample_images(
                ["file:///fake/path/missing.jpg"],
                video_path="file:///fake/v1.mp4",
            )

        assert result == [], "磁碟不存在的 URI 應剔除"

    def test_validate_drops_conversion_failure(self, tmp_path):
        """uri_to_fs_path 拋 Exception → 視為不存在剔除（並 log warning）"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.uri_to_fs_path", side_effect=ValueError("環境不支援")), \
             patch("core.gallery_scanner.logger") as mock_logger:
            result = _validate_sample_images(
                ["file:///bad/path.jpg"],
                video_path="file:///fake/v1.mp4",
            )

        assert result == [], "轉換失敗的 URI 應剔除"
        mock_logger.warning.assert_called_once()
        call_args_str = str(mock_logger.warning.call_args)
        assert "ValueError" in call_args_str, "warning log 應包含 exception 型別 ValueError"

    def test_cleanup_pass_returns_count(self, tmp_path):
        """3 部影片，2 部有孤兒（磁碟不存在），回傳 cleaned_count = 2"""
        from unittest.mock import MagicMock, patch
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        # 建立 mock repo
        mock_repo = MagicMock()
        video_with_orphan_1 = MagicMock()
        video_with_orphan_1.path = "file:///A/v1.mp4"
        video_with_orphan_1.sample_images = ["file:///A/extrafanart/s1.jpg"]

        video_with_orphan_2 = MagicMock()
        video_with_orphan_2.path = "file:///A/v2.mp4"
        video_with_orphan_2.sample_images = ["file:///A/extrafanart/s2.jpg"]

        video_clean = MagicMock()
        video_clean.path = "file:///A/v3.mp4"
        video_clean.sample_images = ["file:///A/extrafanart/s3.jpg"]  # 這個存在

        mock_repo.get_all.return_value = [video_with_orphan_1, video_with_orphan_2, video_clean]

        def fake_uri_to_fs_path(uri):
            return uri.replace("file:///", "/")

        # v1/v2 的 sample 不存在磁碟，v3 的存在
        def fake_exists(path):
            return "s3.jpg" in path  # 只有 s3.jpg 存在

        with patch("core.gallery_scanner.uri_to_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            count = _run_sample_images_cleanup_pass(mock_repo)

        assert count == 2, f"期待 2 部影片被清理，實際 {count}"

    def test_cleanup_pass_skips_videos_without_samples(self, tmp_path):
        """影片 sample_images 為空 list → 不呼叫 repo.update_sample_images"""
        from unittest.mock import MagicMock, patch
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        mock_repo = MagicMock()
        video_no_samples = MagicMock()
        video_no_samples.path = "file:///A/v1.mp4"
        video_no_samples.sample_images = []  # 空 list

        mock_repo.get_all.return_value = [video_no_samples]

        with patch("core.gallery_scanner.uri_to_fs_path"), \
             patch("os.path.exists"):
            count = _run_sample_images_cleanup_pass(mock_repo)

        assert count == 0, "空 sample_images 的影片不應被計入 cleaned_count"
        mock_repo.update_sample_images.assert_not_called()

    def test_cleanup_pass_calls_update_sample_images(self, tmp_path):
        """確認 repo.update_sample_images 被呼叫時傳入正確的 path + validated list"""
        from unittest.mock import MagicMock, patch, call
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        mock_repo = MagicMock()
        video = MagicMock()
        video.path = "file:///A/v1.mp4"
        # 2 個 URI，只有第一個存在
        video.sample_images = ["file:///A/ext/exist.jpg", "file:///A/ext/missing.jpg"]
        mock_repo.get_all.return_value = [video]

        def fake_uri_to_fs_path(uri):
            return uri.replace("file:///", "/")

        def fake_exists(path):
            return "exist.jpg" in path  # 只有 exist.jpg 存在

        with patch("core.gallery_scanner.uri_to_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            _run_sample_images_cleanup_pass(mock_repo)

        # 驗證 update_sample_images 被呼叫，且只傳入存在的 URI
        mock_repo.update_sample_images.assert_called_once_with(
            "file:///A/v1.mp4",
            ["file:///A/ext/exist.jpg"],
        )
