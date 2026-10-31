import pytest
from unittest.mock import patch
from core.gallery_scanner import VideoScanner
from core.path_utils import to_file_uri


def test_fast_scan_directory_skips_nas_system_dirs(tmp_path):
    from core.gallery_scanner import fast_scan_directory, is_nas_system_dir_name

    scan_root = tmp_path / "scan"
    (scan_root / "#recycle" / "x").mkdir(parents=True)
    (scan_root / "@eaDir" / "片.mp4").mkdir(parents=True)
    (scan_root / "#SNAPSHOT" / "y").mkdir(parents=True)
    (scan_root / "@appstore").mkdir()
    (scan_root / "normal").mkdir()
    (scan_root / "#recycle" / "x" / "片.mp4").touch()
    (scan_root / "@eaDir" / "片.mp4" / "thumb.jpg").touch()
    (scan_root / "@eaDir" / "片.mp4").joinpath("影片.mp4").touch()
    (scan_root / "#SNAPSHOT" / "y" / "片.mp4").touch()
    (scan_root / "@appstore" / "片.mp4").touch()
    normal_video = scan_root / "normal" / "片2.mp4"
    normal_video.touch()

    results = fast_scan_directory(str(scan_root), {'.mp4'}, 0)
    paths = [item['path'] for item in results]
    assert paths == [str(normal_video)]
    assert all(is_nas_system_dir_name(name) for name in ('#RECYCLE', '@EaDir', '#Snapshot', '@whatever'))
    assert all(not is_nas_system_dir_name(name) for name in ('normal', 'AVtest'))


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


    def test_parse_nfo_applies_custom_nfo_title_format(self, tmp_path):
        """AC-b7：認得其他工具用自訂格式產生的 NFO → 讀出片名本體。"""
        scanner = VideoScanner(nfo_title_format='{num}-{title}-{actor}')
        # parse_nfo 的 number 來自 NFO 自身的 <num>，不像 enricher/producer 可由呼叫端傳入。
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>ABC-123-片名-三上悠亜</title>
            <num>ABC-123</num>
            <actor>
                <name>三上悠亜</name>
            </actor>
        </movie>
        """
        nfo_path = tmp_path / "custom.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == '片名'

    def test_parse_nfo_respects_external_title_edit(self, tmp_path):
        """AC-b11：記錄行存在但 <title> 被外部改過 → 以外部改過的內容為準。"""
        scanner = VideoScanner(nfo_title_format='{num}-{title}-{actor}')
        xml_content = """<?xml version="1.0" encoding="utf-8"?>
        <movie>
            <title>外部改過的片名</title>
            <num>ABC-123</num>
            <actor>
                <name>三上悠亜</name>
            </actor>
            <openaver_title_record>
                <written>ABC-123-片名-三上悠亜</written>
                <body>片名</body>
            </openaver_title_record>
        </movie>
        """
        nfo_path = tmp_path / "edited.nfo"
        nfo_path.write_text(xml_content, encoding="utf-8")

        info = scanner.parse_nfo(str(nfo_path))
        assert info is not None
        assert info.title == '外部改過的片名'


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


    def test_find_cover_image_l1_beats_l15(self, scanner, tmp_path):
        """L1.5 邊界5：exact {stem}.jpg 與 {stem}-fanart.jpg 同存 → L1 勝（exact 仍最高優先）"""
        video_path = tmp_path / "TEST-104.mp4"
        exact_path = tmp_path / "TEST-104.jpg"
        fanart_path = tmp_path / "TEST-104-fanart.jpg"
        exact_path.touch()
        fanart_path.touch()

        found = scanner.find_cover_image(str(video_path))
        assert found == str(exact_path)


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


    # --- 負面 case ---

    def test_prefix_too_long_vacation(self, scanner):
        """前綴 vacation（7 字母，正好超上限）— my-vacation-2024.mp4 不應誤抓"""
        result = scanner.find_num_from_filename("my-vacation-2024.mp4")
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


class TestCollectLongPaths:
    """spec-48a §a5 契約 1+2 — _collect_long_paths helper 行為"""

    def test_path_over_260_detected(self):
        from web.routers.scanner import _collect_long_paths
        long = 'C:\\' + 'a' * 260  # len = 263
        short = 'C:\\short.mp4'
        result = _collect_long_paths([{'path': long}, {'path': short}])
        assert result == [long], "只該抓到超過 260 的路徑"


class TestScannerSampleImagesValidationPass:
    """spec-48b §b1 AC#2 — _validate_sample_images + _run_sample_images_cleanup_pass"""


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
        from unittest.mock import patch
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


class TestGalleryScannerTASK139T1b:
    """TASK-139-T1b: B（VideoScanner.NUM_PATTERNS）FC2 收斂與 F8/F9 守衛測試。"""

    @pytest.mark.parametrize("filename", [
        "FC2PPV-4943690.mp4",
    ])
    def test_find_num_seven_fc2_shapes(self, filename):
        """七形 FC2 檔名全部解析為 FC2-4943690。"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename(filename) == "FC2-4943690"


    # --- F8 must-not-break 四條 ---

    def test_f8_dmm_content_id_1sdms00808(self):
        """F8-1: 1sdms00808.mp4 → SDMS-00808（不被破壞）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("1sdms00808.mp4") == "SDMS-00808"

    def test_f8_tokyo_hot_single_letter(self):
        """F8-2: 東京熱單字母 + 4 位不插 hyphen（n0762, k0150）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("n0762.mp4") == "N0762"
        assert scanner.find_num_from_filename("k0150.mp4") == "K0150"

    def test_f8_date_format_delimiters_not_swapped(self):
        """F8-3: 一本道/加勒比日期格式分隔符不互換（020317-001 與 090122_001）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("020317-001.mp4") == "020317-001"
        assert scanner.find_num_from_filename("090122_001.mp4") == "090122_001"

    # --- F9 反向鎖 ---




def test_scan_chain_has_plot(tmp_path):
    """parse_nfo→scan_file→from_video_info→upsert_batch→讀回→_serialize_video；
    外加一列整理路徑（真 scan_file，不 patch VideoScanner）。"""
    import sqlite3
    from unittest.mock import patch

    import core.db_inflow as _db_inflow_mod
    from core.database import Video, VideoRepository, init_db
    from core.path_utils import normalize_path, to_file_uri
    from web.routers.showcase import _serialize_video

    cases = [
        ("with_plot", "<movie><title>T</title><num>HP-001</num><plot>簡介文字</plot></movie>", True),
        ("no_plot", "<movie><title>T</title><num>HP-002</num></movie>", False),
        ("blank_plot", "<movie><title>T</title><num>HP-003</num><plot>  \n  </plot></movie>", False),
        ("no_nfo", None, False),
        ("bad_xml", "<movie><title>T</title><num>HP-005</num><plot>x</movie>", False),
    ]

    db_path = tmp_path / "chain_has_plot.db"
    init_db(db_path)
    repo = VideoRepository(db_path=db_path)
    scanner = VideoScanner()

    videos = []
    expected = {}
    for name, nfo_body, want in cases:
        video = tmp_path / f"{name}.mp4"
        video.write_bytes(b"fake")
        if nfo_body is not None:
            (tmp_path / f"{name}.nfo").write_text(nfo_body, encoding="utf-8")
        info = scanner.scan_file(str(video))
        assert info.has_plot is want, f"{name}: scan_file has_plot={info.has_plot!r}"
        v = Video.from_video_info(info)
        assert v.has_plot is want, f"{name}: from_video_info has_plot={v.has_plot!r}"
        videos.append(v)
        expected[v.path] = want

    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert_batch(videos)

    for path, want in expected.items():
        got = repo.get_by_path(path)
        assert got is not None
        assert got.has_plot is want, f"DB read {path}: has_plot={got.has_plot!r}"
        conn = sqlite3.connect(str(db_path))
        raw = conn.execute("SELECT has_plot FROM videos WHERE path=?", (path,)).fetchone()[0]
        conn.close()
        assert raw == (1 if want else 0), f"raw SQLite has_plot={raw!r} for {path}"
        ser = _serialize_video(got, {})
        assert "has_plot" in ser
        assert ser["has_plot"] is want

    # 整理路徑：真 scan_file（不 patch VideoScanner）
    org_video = tmp_path / "org.mp4"
    org_video.write_bytes(b"fake")
    (tmp_path / "org.nfo").write_text(
        "<movie><title>Org</title><num>ORG-001</num><plot>整理簡介</plot></movie>",
        encoding="utf-8",
    )
    new_uri = to_file_uri(normalize_path(str(org_video)), None)

    with (
        patch.object(_db_inflow_mod, "load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch.object(_db_inflow_mod, "find_matched_directory", return_value=str(tmp_path)),
        patch.object(_db_inflow_mod, "VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        result = _db_inflow_mod.try_inflow_upsert(str(org_video), old_file_path=None)

    assert result == "synced", f"應回 'synced'，實際: {result!r}"
    org_row = repo.get_by_path(new_uri)
    assert org_row is not None
    assert org_row.has_plot is True
    assert _serialize_video(org_row, {})["has_plot"] is True
