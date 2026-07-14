import ast
import pytest
from pathlib import Path
from unittest.mock import patch
from core.gallery_scanner import VideoScanner
from core.path_utils import to_file_uri


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

    # ── L1.5: {stem}-fanart / {stem}-poster 邊界條件 ──────────────────────────

    def test_find_cover_image_l15_fanart_only(self, scanner, tmp_path):
        """L1.5 邊界1：只有 {stem}-fanart.jpg（無 exact {stem}.jpg）→ 回傳 -fanart 路徑"""
        video_path = tmp_path / "TEST-100.mp4"
        fanart_path = tmp_path / "TEST-100-fanart.jpg"
        fanart_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fanart_path)

    def test_find_cover_image_l15_fanart_over_poster(self, scanner, tmp_path):
        """L1.5 邊界2：-fanart.jpg 與 -poster.jpg 同存 → -fanart 優先（suffix 順序）"""
        video_path = tmp_path / "TEST-101.mp4"
        fanart_path = tmp_path / "TEST-101-fanart.jpg"
        poster_path = tmp_path / "TEST-101-poster.jpg"
        fanart_path.touch()
        poster_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fanart_path)

    def test_find_cover_image_l15_poster_only(self, scanner, tmp_path):
        """L1.5 邊界3：只有 {stem}-poster.jpg → 回傳 -poster 路徑"""
        video_path = tmp_path / "TEST-102.mp4"
        poster_path = tmp_path / "TEST-102-poster.jpg"
        poster_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(poster_path)

    def test_find_cover_image_l15_fallthrough_to_l2(self, scanner, tmp_path):
        """L1.5 邊界4：stem 前綴版皆不存在，固定名 fanart.jpg → fall through 到 L2（L1.5 不 shadow L2）"""
        video_path = tmp_path / "TEST-103.mp4"
        fixed_fanart = tmp_path / "fanart.jpg"
        fixed_fanart.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fixed_fanart)

    def test_find_cover_image_l1_beats_l15(self, scanner, tmp_path):
        """L1.5 邊界5：exact {stem}.jpg 與 {stem}-fanart.jpg 同存 → L1 勝（exact 仍最高優先）"""
        video_path = tmp_path / "TEST-104.mp4"
        exact_path = tmp_path / "TEST-104.jpg"
        fanart_path = tmp_path / "TEST-104-fanart.jpg"
        exact_path.touch()
        fanart_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(exact_path)

    def test_find_cover_image_l15_ext_order_jpg_over_png(self, scanner, tmp_path):
        """L1.5 邊界6：{stem}-fanart.png 與 {stem}-fanart.jpg 同存 → .jpg 優先（IMAGE_EXTENSIONS 順序）"""
        video_path = tmp_path / "TEST-105.mp4"
        fanart_jpg = tmp_path / "TEST-105-fanart.jpg"
        fanart_png = tmp_path / "TEST-105-fanart.png"
        fanart_jpg.touch()
        fanart_png.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fanart_jpg)

    def test_find_cover_image_l15_png_only(self, scanner, tmp_path):
        """L1.5 邊界6b：只有 {stem}-fanart.png → 回傳（非 .jpg 也命中）"""
        video_path = tmp_path / "TEST-106.mp4"
        fanart_png = tmp_path / "TEST-106-fanart.png"
        fanart_png.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fanart_png)

    def test_find_cover_image_l15_mdcx_us6(self, scanner, tmp_path):
        """L1.5 邊界7（MDCX US6）：資料夾只有 {stem}-poster.jpg + {stem}-fanart.jpg，無 exact → 回傳 -fanart"""
        video_path = tmp_path / "TEST-107.mp4"
        fanart_path = tmp_path / "TEST-107-fanart.jpg"
        poster_path = tmp_path / "TEST-107-poster.jpg"
        fanart_path.touch()
        poster_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(fanart_path)


# ============ NUM_PATTERNS 多字母後綴 ============

class TestNumPatternsMultiLetterSuffix:
    """VideoScanner.find_num_from_filename() 多字母小寫後綴正/負 case"""

    @pytest.fixture
    def scanner(self):
        return VideoScanner()

    # --- 正面 case ---

    def test_multi_letter_suffix_ch_abp(self, scanner):
        """多字母後綴 ch — abp-321ch.mp4 應抽出 ABP-321"""
        result = scanner.find_num_from_filename("abp-321ch.mp4")
        assert result == "ABP-321"

    def test_multi_letter_suffix_ch_ipzz(self, scanner):
        """多字母後綴 ch，不同前綴長度 — ipzz-789ch.mp4 應抽出 IPZZ-789"""
        result = scanner.find_num_from_filename("ipzz-789ch.mp4")
        assert result == "IPZZ-789"

    def test_multi_letter_suffix_uncen(self, scanner):
        """多字母後綴 uncen — abp-321uncen.mp4 應抽出 ABP-321"""
        result = scanner.find_num_from_filename("abp-321uncen.mp4")
        assert result == "ABP-321"

    def test_separator_number_suffix_not_regressed(self, scanner):
        """有分隔符數字後綴（既已覆蓋）— abp-321-2024.mp4 應抽出 ABP-321，不退化"""
        result = scanner.find_num_from_filename("abp-321-2024.mp4")
        assert result == "ABP-321"

    def test_single_letter_suffix_not_regressed(self, scanner):
        """原有單字母後綴 d — sone-205d.mp4 應抽出 SONE-205，不退化"""
        result = scanner.find_num_from_filename("sone-205d.mp4")
        assert result == "SONE-205"

    # --- 負面 case ---

    def test_prefix_too_long_vacation(self, scanner):
        """前綴 vacation（7 字母，正好超上限）— my-vacation-2024.mp4 不應誤抓"""
        result = scanner.find_num_from_filename("my-vacation-2024.mp4")
        assert result == ""

    def test_prefix_too_long_tutorial(self, scanner):
        """前綴 tutorial（8 字母）超上限 — tutorial-123.mp4 不應誤抓"""
        result = scanner.find_num_from_filename("tutorial-123.mp4")
        assert result == ""

    def test_no_separator_number_suffix_not_supported(self, scanner):
        """無分隔符數字後綴 CD-58-1 釘版不支援 — abp-3212024.mp4 不應誤抓"""
        result = scanner.find_num_from_filename("abp-3212024.mp4")
        assert result == ""


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
        with patch("core.gallery_scanner.uri_to_local_fs_path", return_value="/fake/path/s1.jpg"), \
             patch("os.path.exists", return_value=True):
            result = _validate_sample_images(
                [to_file_uri("/fake/path/s1.jpg")],
                video_path=to_file_uri("/fake/v1.mp4"),
            )

        assert result == [to_file_uri("/fake/path/s1.jpg")], "磁碟存在的 URI 應保留"

    def test_validate_drops_missing_uri(self, tmp_path):
        """磁碟不存在的 URI → 從回傳 list 剔除"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.uri_to_local_fs_path", return_value="/fake/path/missing.jpg"), \
             patch("os.path.exists", return_value=False):
            result = _validate_sample_images(
                [to_file_uri("/fake/path/missing.jpg")],
                video_path=to_file_uri("/fake/v1.mp4"),
            )

        assert result == [], "磁碟不存在的 URI 應剔除"

    def test_validate_drops_conversion_failure(self, tmp_path):
        """uri_to_fs_path 拋 Exception → 視為不存在剔除（並 log warning）"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.uri_to_local_fs_path", side_effect=ValueError("環境不支援")), \
             patch("core.gallery_scanner.logger") as mock_logger:
            result = _validate_sample_images(
                [to_file_uri("/bad/path.jpg")],
                video_path=to_file_uri("/fake/v1.mp4"),
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
        video_with_orphan_1.path = to_file_uri("/A/v1.mp4")
        video_with_orphan_1.sample_images = [to_file_uri("/A/extrafanart/s1.jpg")]

        video_with_orphan_2 = MagicMock()
        video_with_orphan_2.path = to_file_uri("/A/v2.mp4")
        video_with_orphan_2.sample_images = [to_file_uri("/A/extrafanart/s2.jpg")]

        video_clean = MagicMock()
        video_clean.path = to_file_uri("/A/v3.mp4")
        video_clean.sample_images = [to_file_uri("/A/extrafanart/s3.jpg")]  # 這個存在

        mock_repo.get_all.return_value = [video_with_orphan_1, video_with_orphan_2, video_clean]

        def fake_uri_to_fs_path(uri, path_mappings=None):
            return uri.replace("file:///", "/")

        # v1/v2 的 sample 不存在磁碟，v3 的存在
        def fake_exists(path):
            return "s3.jpg" in path  # 只有 s3.jpg 存在

        with patch("core.gallery_scanner.uri_to_local_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            count = _run_sample_images_cleanup_pass(mock_repo)

        assert count == 2, f"期待 2 部影片被清理，實際 {count}"

    def test_cleanup_pass_skips_videos_without_samples(self, tmp_path):
        """影片 sample_images 為空 list → 不呼叫 repo.update_sample_images"""
        from unittest.mock import MagicMock, patch
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        mock_repo = MagicMock()
        video_no_samples = MagicMock()
        video_no_samples.path = to_file_uri("/A/v1.mp4")
        video_no_samples.sample_images = []  # 空 list

        mock_repo.get_all.return_value = [video_no_samples]

        with patch("core.gallery_scanner.uri_to_local_fs_path"), \
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
        video.path = to_file_uri("/A/v1.mp4")
        # 2 個 URI，只有第一個存在
        video.sample_images = [to_file_uri("/A/ext/exist.jpg"), to_file_uri("/A/ext/missing.jpg")]
        mock_repo.get_all.return_value = [video]

        def fake_uri_to_fs_path(uri, path_mappings=None):
            return uri.replace("file:///", "/")

        def fake_exists(path):
            return "exist.jpg" in path  # 只有 exist.jpg 存在

        with patch("core.gallery_scanner.uri_to_local_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            _run_sample_images_cleanup_pass(mock_repo)

        # 驗證 update_sample_images 被呼叫，且只傳入存在的 URI
        mock_repo.update_sample_images.assert_called_once_with(
            to_file_uri("/A/v1.mp4"),
            [to_file_uri("/A/ext/exist.jpg")],
        )

    def test_validate_preserves_relative_path(self, tmp_path):
        """相對路徑（舊 CLI scan_directory(relative_path=True) 格式或 migration 帶入）
        不應被 cleanup 誤刪。cleanup pass 只管 file:/// URI。
        http:// / https:// 遠端 URL 為 Codex P1 pre-fix 污染，應被清除。"""
        from core.gallery_scanner import _validate_sample_images
        # 不用 mock uri_to_fs_path / os.path.exists — 驗證「從未呼叫」才是重點
        result = _validate_sample_images(
            [
                "MOVIE-001/extrafanart/fanart1.jpg",  # 舊相對路徑 → 保留
                "/mnt/d/legacy/abs/path.jpg",          # 舊絕對 FS 路徑 → 保留
                "http://example.com/remote.jpg",       # 遠端 URL（Codex P1 污染）→ 清除
                "https://cdn.example.com/s2.jpg",      # https 遠端 URL → 清除
            ],
            video_path=to_file_uri("/fake/v.mp4"),
        )
        assert result == [
            "MOVIE-001/extrafanart/fanart1.jpg",
            "/mnt/d/legacy/abs/path.jpg",
        ], "非 file:/// URI 中，相對/絕對路徑保留，http:// / https:// 污染清除"

    def test_validate_cleanup_reproduces_codex_scenario(self, tmp_path):
        """Codex 報的最小重現：相對路徑在 cleanup pass 裡不應被當不存在檔案清掉。
        直接跑 _run_sample_images_cleanup_pass，不 mock（用 MagicMock repo）。"""
        from unittest.mock import MagicMock
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        mock_repo = MagicMock()
        video = MagicMock()
        video.path = to_file_uri("/fake/v.mp4")
        video.sample_images = ["MOVIE-001/extrafanart/fanart1.jpg"]  # Codex 重現的值
        mock_repo.get_all.return_value = [video]

        count = _run_sample_images_cleanup_pass(mock_repo)
        assert count == 0, "相對路徑應保留，cleanup 不該觸發 update"
        mock_repo.update_sample_images.assert_not_called()

    def test_validate_purges_http_url_pollution(self, tmp_path):
        """Codex P1: http:// / https:// 遠端 URL 為 pre-fix scraper URL 污染，一律清除。
        seeds DB: valid file:///（disk exists）+ missing file:///（disk absent）+ http:// URL
        asserts: only the valid file:/// URI survives."""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        mixed_samples = [
            to_file_uri("/valid/extrafanart/fanart1.jpg"),   # 磁碟存在 → 保留
            to_file_uri("/missing/extrafanart/fanart2.jpg"), # 磁碟不存在 → 剔除
            "http://example.com/s1.jpg",               # scraper URL 污染 → 清除
            "https://cdn.example.com/s2.jpg",          # scraper URL 污染 → 清除
        ]

        def fake_uri_to_fs_path(uri, path_mappings=None):
            return uri.replace("file:///", "/")

        def fake_exists(path):
            return "valid" in path  # only /valid/... exists

        with patch("core.gallery_scanner.uri_to_local_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            result = _validate_sample_images(mixed_samples, video_path=to_file_uri("/v1.mp4"))

        assert result == [to_file_uri("/valid/extrafanart/fanart1.jpg")], (
            f"只有磁碟存在的 file:/// URI 應保留；missing + http:// 應全部清除。got: {result}"
        )

    def test_validate_purges_http_logged_at_info(self, tmp_path):
        """Codex P1: purge http:// entries 時應 log INFO（讓 debug.log 可見）。"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.logger") as mock_logger:
            _validate_sample_images(
                ["http://example.com/s1.jpg", "https://cdn.example.com/s2.jpg"],
                video_path=to_file_uri("/v1.mp4"),
            )

        # logger.info 應被呼叫，且訊息包含 purged 計數
        assert mock_logger.info.called, "purge http:// 項目時應呼叫 logger.info"
        call_args_str = str(mock_logger.info.call_args_list)
        assert "purged" in call_args_str, f"info log 應包含 'purged'，got: {call_args_str}"
        assert "2" in call_args_str, f"purged 計數應為 2，got: {call_args_str}"

    def test_cleanup_pass_purges_http_urls_end_to_end(self, tmp_path):
        """Codex P1 end-to-end: _run_sample_images_cleanup_pass 透過 repo 清除 http:// 污染。
        DB 最終 sample_images 只剩 file:///valid.jpg；missing + http:// 均被清除。"""
        from unittest.mock import MagicMock, patch
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        mock_repo = MagicMock()
        video = MagicMock()
        video.path = to_file_uri("/A/v1.mp4")
        video.sample_images = [
            to_file_uri("/A/extrafanart/fanart1.jpg"),  # 磁碟存在 → 保留
            to_file_uri("/A/extrafanart/fanart2.jpg"),  # 磁碟不存在 → 剔除
            "http://example.com/s1.jpg",           # scraper URL 污染 → 清除
        ]
        mock_repo.get_all.return_value = [video]

        def fake_uri_to_fs_path(uri, path_mappings=None):
            return uri.replace("file:///", "/")

        def fake_exists(path):
            return "fanart1.jpg" in path  # only fanart1.jpg exists on disk

        with patch("core.gallery_scanner.uri_to_local_fs_path", side_effect=fake_uri_to_fs_path), \
             patch("os.path.exists", side_effect=fake_exists):
            count = _run_sample_images_cleanup_pass(mock_repo)

        assert count == 1, f"1 部影片的 sample_images 應被更新，got: {count}"
        mock_repo.update_sample_images.assert_called_once_with(
            to_file_uri("/A/v1.mp4"),
            [to_file_uri("/A/extrafanart/fanart1.jpg")],
        )

    def test_validate_reverse_maps_wsl_unc_path_mappings(self, tmp_path, monkeypatch):
        """TASK-91-T2b #16：_validate_sample_images(sample_images, video_path, path_mappings)
        在 WSL+UNC mapping 環境下，os.path.exists 檢查的路徑必須是反解後的本機路徑
        （可真的 open()），非裸 uri_to_fs_path() 產生的映射端 UNC 字串（磁碟上不存在）。
        """
        import core.path_utils as path_utils
        from core.gallery_scanner import _validate_sample_images

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        (nas_dir / "s1.jpg").write_bytes(b'\x00')
        mappings = {str(nas_dir): "//NAS/share"}

        mapped_uri = "file://///NAS/share/s1.jpg"
        result = _validate_sample_images(
            [mapped_uri], video_path=to_file_uri("/fake/v1.mp4"), path_mappings=mappings,
        )

        assert result == [mapped_uri], (
            f"反解後應能確認磁碟真的存在該檔案，不應誤判剔除。got: {result}"
        )

    def test_cleanup_pass_threads_path_mappings_to_validate(self, tmp_path, monkeypatch):
        """TASK-91-T2b #16：_run_sample_images_cleanup_pass(repo, path_mappings) 把
        path_mappings 透傳給 _validate_sample_images，WSL+UNC mapping 命中的合法
        sample_image 不應被誤判孤兒而清除。"""
        import core.path_utils as path_utils
        from unittest.mock import MagicMock
        from core.gallery_scanner import _run_sample_images_cleanup_pass

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        (nas_dir / "s1.jpg").write_bytes(b'\x00')
        mappings = {str(nas_dir): "//NAS/share"}

        mock_repo = MagicMock()
        video = MagicMock()
        video.path = to_file_uri("/A/v1.mp4")
        video.sample_images = ["file://///NAS/share/s1.jpg"]
        mock_repo.get_all.return_value = [video]

        count = _run_sample_images_cleanup_pass(mock_repo, mappings)

        assert count == 0, (
            f"WSL+mapping 命中的合法 sample_image 反解後存在，不應被清除，got count={count}"
        )
        mock_repo.update_sample_images.assert_not_called()

    def test_validate_default_none_path_mappings_equivalent_to_before(self, tmp_path):
        """#16 邊界：path_mappings 預設 None → 與改動前裸 uri_to_fs_path 呼叫等價
        （保護既有呼叫端測試不用改就能繼續 GREEN，見上方本 class 其餘測試）。"""
        from unittest.mock import patch
        from core.gallery_scanner import _validate_sample_images

        with patch("core.gallery_scanner.uri_to_local_fs_path", return_value="/fake/path/s1.jpg"), \
             patch("os.path.exists", return_value=True):
            result = _validate_sample_images(
                [to_file_uri("/fake/path/s1.jpg")],
                video_path=to_file_uri("/fake/v1.mp4"),
            )

        assert result == [to_file_uri("/fake/path/s1.jpg")]


# ============ TASK-98b-T2: 掃描 empty-focal gate（gallery_scanner 路徑） ============

class TestScanFocalTrigger:
    """scan_to_sqlite 掃描入庫後的 focal trigger（empty-focal gate）。

    使用真 tmp DB + 真 requires_face_detection gate；patch use-site helper
    `core.gallery_scanner.maybe_submit_video_focal` 只驗接線與 gate，不真跑 pigo。
    """

    def _make_info(self, num, path_uri, cover_uri, maker=""):
        from core.gallery_scanner import VideoInfo
        info = VideoInfo()
        info.num = num
        info.path = path_uri
        info.img = cover_uri
        info.maker = maker
        info.title = "T"
        return info

    def _run_scan(self, tmp_path, num, maker="", seed_auto_focal=None):
        from unittest.mock import patch, MagicMock
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        db_file = tmp_path / "scan_focal.db"
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)

        video_fs = str(tmp_path / f"{num}.mp4")
        cover_fs = tmp_path / f"{num}.jpg"
        cover_fs.write_bytes(b"x")
        path_uri = to_file_uri(video_fs)
        cover_uri = to_file_uri(str(cover_fs))

        # 可選：預先種一筆已有 auto_focal 的 row（測 empty-focal gate 的 non-empty 分支）
        if seed_auto_focal is not None:
            with patch("core.similar.ranker_cache.SimilarRankerCache"):
                repo.upsert(Video(path=path_uri, number=num, maker=maker, cover_path=cover_uri))
            repo.update_auto_focal(path_uri, seed_auto_focal, cover_uri)

        scanner = VideoScanner()
        info = self._make_info(num, path_uri, cover_uri, maker)
        file_infos = [{"path": video_fs, "mtime": 111, "nfo_mtime": 0}]

        with (
            patch("core.gallery_scanner.fast_scan_directory", return_value=file_infos),
            patch.object(scanner, "scan_file", return_value=info),
            patch("core.similar.ranker_cache.SimilarRankerCache"),
            patch("core.gallery_scanner._run_sample_images_cleanup_pass"),
            patch("core.gallery_scanner.maybe_submit_video_focal") as mock_submit,
        ):
            scanner.scan_to_sqlite(str(tmp_path), db_path=db_file)
        return mock_submit

    def test_uncensored_empty_focal_submits(self, tmp_path):
        # SIRO-xxxx = shirouto → requires_face_detection True；新 row auto_focal 空 → submit
        mock_submit = self._run_scan(tmp_path, "SIRO-1234")
        mock_submit.assert_called_once()
        args = mock_submit.call_args[0]
        assert args[0] == "SIRO-1234"

    def test_uncensored_nonempty_focal_no_submit(self, tmp_path):
        # 現有 auto_focal 有值 → empty-focal gate 擋（mutation：拿掉 `not focal_map.get()` 必 RED）
        mock_submit = self._run_scan(tmp_path, "SIRO-1234", seed_auto_focal="0.5,0.5")
        mock_submit.assert_not_called()

    def test_censored_no_submit(self, tmp_path):
        # SONE-205 = 有碼 → requires_face_detection False → 不 submit
        mock_submit = self._run_scan(tmp_path, "SONE-205", maker="SOD")
        mock_submit.assert_not_called()

    def test_existing_unchanged_empty_focal_backfilled(self, tmp_path):
        """Codex PR#105 P2 回歸釘：既有 DB 列、auto_focal=''、mtime 未變（不進
        needs_scan/videos_to_upsert）、無碼 → 重掃一次仍要被送偵測，否則「重掃一次
        自動補焦既有庫」的承諾對這批既有片形同虛設。

        mutation：focal 來源若改回只迴圈 videos_to_upsert，此列不會被 submit → RED。
        """
        from unittest.mock import patch
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        num = "SIRO-9999"
        db_file = tmp_path / "scan_focal_unchanged.db"
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)

        video_fs = str(tmp_path / f"{num}.mp4")
        cover_fs = tmp_path / f"{num}.jpg"
        cover_fs.write_bytes(b"x")
        path_uri = to_file_uri(video_fs)
        cover_uri = to_file_uri(str(cover_fs))

        # 既有列，mtime 與本次掃描一致（不進 needs_scan）；auto_focal 維持 dataclass
        # 預設空字串（不呼叫 update_auto_focal）。
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(
                path=path_uri, number=num, maker="", cover_path=cover_uri,
                mtime=111, nfo_mtime=0.0,
            ))

        scanner = VideoScanner()
        file_infos = [{"path": video_fs, "mtime": 111, "nfo_mtime": 0}]

        with (
            patch("core.gallery_scanner.fast_scan_directory", return_value=file_infos),
            patch("core.similar.ranker_cache.SimilarRankerCache"),
            patch("core.gallery_scanner._run_sample_images_cleanup_pass"),
            patch("core.gallery_scanner.maybe_submit_video_focal") as mock_submit,
        ):
            scanner.scan_to_sqlite(str(tmp_path), db_path=db_file)

        mock_submit.assert_called_once()
        args = mock_submit.call_args[0]
        assert args[0] == num
        assert args[2] == path_uri

    def test_no_face_result_not_resubmitted_on_second_rescan(self, tmp_path):
        """Codex PR#105 P2 no-face re-enqueue 回歸釘：第一次掃描把既有無碼、auto_focal=''
        的列排入 backfill 候選（模擬偵測 commit 出「無臉」結果，即 update_auto_focal(path, '')，
        legitimately no-face）後，第二次掃描（mtime 仍未變，不進 needs_scan）不應再把它
        送進 maybe_submit_video_focal——無臉是已知結果，不是「還沒偵測過」。

        mutation：get_empty_focal_candidates 若拿掉 `AND focal_attempted_at IS NULL`，
        這條會 RED（第二次掃描又把同一列送進 focal 偵測）。
        """
        from unittest.mock import patch
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        num = "SIRO-8888"
        db_file = tmp_path / "scan_focal_no_face_rescan.db"
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)

        video_fs = str(tmp_path / f"{num}.mp4")
        cover_fs = tmp_path / f"{num}.jpg"
        cover_fs.write_bytes(b"x")
        path_uri = to_file_uri(video_fs)
        cover_uri = to_file_uri(str(cover_fs))

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(
                path=path_uri, number=num, maker="", cover_path=cover_uri,
                mtime=111, nfo_mtime=0.0,
            ))

        scanner = VideoScanner()
        file_infos = [{"path": video_fs, "mtime": 111, "nfo_mtime": 0}]

        # 第一次掃描：既有列進 backfill 候選，被送去偵測
        with (
            patch("core.gallery_scanner.fast_scan_directory", return_value=file_infos),
            patch("core.similar.ranker_cache.SimilarRankerCache"),
            patch("core.gallery_scanner._run_sample_images_cleanup_pass"),
            patch("core.gallery_scanner.maybe_submit_video_focal") as mock_submit_1,
        ):
            scanner.scan_to_sqlite(str(tmp_path), db_path=db_file)
        mock_submit_1.assert_called_once()

        # 模擬背景 worker/force-detect 完成偵測、legitimately 無臉：commit auto_focal=''
        assert repo.update_auto_focal(path_uri, "", cover_uri) is True

        # 第二次掃描：mtime 仍未變（不進 needs_scan），auto_focal 仍是 ''，但
        # focal_attempted_at 已蓋章 → 不應再被送進偵測
        with (
            patch("core.gallery_scanner.fast_scan_directory", return_value=file_infos),
            patch("core.similar.ranker_cache.SimilarRankerCache"),
            patch("core.gallery_scanner._run_sample_images_cleanup_pass"),
            patch("core.gallery_scanner.maybe_submit_video_focal") as mock_submit_2,
        ):
            scanner.scan_to_sqlite(str(tmp_path), db_path=db_file)

        mock_submit_2.assert_not_called()
