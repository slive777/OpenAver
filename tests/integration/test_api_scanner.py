import pytest
import os
import threading
from pathlib import Path
from urllib.parse import quote
from core.path_utils import to_file_uri
from tests.conftest import MOCK_FOCAL_XY
from core.focal.subprocess_runner import RunnerOutcome

# TASK-141a-T5：本檔測的兩支端點（generate_avlist / enrich_single_endpoint）收尾會
# 無條件呼叫 reconcile_wishlist()，它用無參數 repo ⇒ 解析到真實 DB。逐檔明示 opt-in
# 隔離（fixture 定義見 tests/conftest.py，刻意不做成 autouse——見該處說明）。
pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")


@pytest.fixture(autouse=True)
def reset_buffer():
    """通知 buffer 是模組層級全域 deque，測試間必須清空，否則「恰好一筆」會閃爍。"""
    import web.routers.notifications as notif_mod
    notif_mod._notifications.clear()
    notif_mod._read_ids.clear()
    yield
    notif_mod._notifications.clear()
    notif_mod._read_ids.clear()


class TestScannerAPI:
    """測試 scanner.py 相關 endpoints"""


    def test_scan_root_unreachable_host_distinguished_from_missing(
        self, client, tmp_path, monkeypatch, parse_sse_events,
    ):
        import errno
        from core.database import init_db, VideoRepository, Video

        scan_dir = tmp_path / "nas_share"
        scan_dir.mkdir()
        video = scan_dir / "existing.mp4"
        video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        uri = to_file_uri(str(video))
        repo.upsert(Video(path=uri, number="EXIST-001", title="既存影片", mtime=video.stat().st_mtime, nfo_mtime=0.0))
        before = len(repo.get_mtime_index())
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.is_synology", lambda: False)

        real_stat = os.stat
        target = os.path.normpath(str(scan_dir))
        hits = []

        def fake_stat(path, *a, **kw):
            if isinstance(path, (str, os.PathLike)) and os.path.normpath(os.fspath(path)) == target:
                hits.append(path)
                raise OSError(errno.EHOSTDOWN, "Host is down")
            return real_stat(path, *a, **kw)

        monkeypatch.setattr(os, "stat", fake_stat)

        def messages(directory):
            monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
                "gallery": {"directories": [str(directory)], "output_dir": str(output_dir),
                            "path_mappings": {}, "min_size_mb": 0},
                "general": {"theme": "light"},
                "scraper": {"video_extensions": [".mp4"]},
            })
            response = client.get("/api/gallery/generate")
            assert response.status_code == 200
            return [e.get("message", "") for e in parse_sse_events(response.text) if e.get("type") == "log"]

        down_messages = messages(scan_dir)
        assert hits, "os.stat 注入沒有打到目標路徑"
        assert any(f"無法存取: {scan_dir}" in m for m in down_messages), down_messages
        assert not any("資料夾不存在" in m for m in down_messages), down_messages
        assert len(repo.get_mtime_index()) == before
        assert uri in repo.get_mtime_index()

        missing_messages = messages(tmp_path / "never_created")
        assert any("資料夾不存在" in m for m in missing_messages), missing_messages
        assert not any("無法存取" in m for m in missing_messages), missing_messages
        assert len(repo.get_mtime_index()) == before

    @pytest.mark.skipif(
        os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        reason="chmod 000 requires POSIX non-root DAC enforcement",
    )
    @pytest.mark.parametrize("synology,server_only", [(True, False), (False, True)])
    def test_scan_root_unreadable_dir_shows_permission_denied_message(
        self, client, tmp_path, monkeypatch, parse_sse_events, synology, server_only,
    ):
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri
        from core.platform_info import DSM_PERMISSION_HINT, LINUX_PERMISSION_HINT

        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        video = scan_dir / "existing.mp4"
        video.write_bytes(b"video")
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        uri = to_file_uri(str(video))
        repo.upsert(Video(path=uri, number="EXIST-001", title="既存影片", mtime=video.stat().st_mtime, nfo_mtime=0.0))
        before = len(repo.get_mtime_index())
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.is_synology", lambda: synology)
        if server_only:
            monkeypatch.setenv("OPENAVER_SERVER_ONLY", "1")
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"directories": [str(scan_dir)], "output_dir": str(output_dir),
                        "path_mappings": {}, "min_size_mb": 0},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        })

        def messages():
            response = client.get("/api/gallery/generate")
            assert response.status_code == 200
            return [e.get("message", "") for e in parse_sse_events(response.text) if e.get("type") == "log"]

        scan_dir.chmod(0o000)
        try:
            assert os.path.exists(scan_dir)
            with pytest.raises(PermissionError):
                with os.scandir(scan_dir):
                    pass
            denied_messages = messages()
            assert any("沒有權限" in m for m in denied_messages)
            assert not any("資料夾不存在" in m for m in denied_messages)
            assert any(DSM_PERMISSION_HINT in m for m in denied_messages) is synology
            if server_only:
                assert any(LINUX_PERMISSION_HINT in m for m in denied_messages)
                assert not any(DSM_PERMISSION_HINT in m for m in denied_messages)
            assert len(repo.get_mtime_index()) == before
        finally:
            scan_dir.chmod(0o700)

        restored_messages = messages()
        assert not any("沒有權限" in m for m in restored_messages)
        assert len(repo.get_mtime_index()) == before
        assert uri in repo.get_mtime_index()

        child = scan_dir / "child"
        child.mkdir()
        child.chmod(0o000)
        try:
            child_messages = messages()
            assert any("讀取失敗，跳過刪除偵測" in m for m in child_messages)
            assert not any("沒有權限" in m for m in child_messages)
            assert len(repo.get_mtime_index()) == before
        finally:
            child.chmod(0o700)

        # A different root error retains the generic warning. This also locks
        # the reason check instead of merely checking that a path was skipped.
        def other_error(directory, extensions, min_size_bytes, on_skip=None):
            on_skip(str(scan_dir), OSError(206, "long path"))
            return []

        monkeypatch.setattr("web.routers.scanner.fast_scan_directory", other_error)
        generic_messages = messages()
        assert any("讀取失敗，跳過刪除偵測" in m for m in generic_messages)
        assert not any("沒有權限" in m for m in generic_messages)
        assert len(repo.get_mtime_index()) == before

    def test_get_video_success(self, client, tmp_path, monkeypatch):
        """測試取得影片成功（路徑在允許名單內）"""
        # 1. 準備影片檔
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        video_file = video_dir / "test.mp4"
        video_file.write_bytes(b'fake_video_content_here')
        
        # 2. Mock config (add tmp_path to list to bypass any realpath discrepancies)
        test_config = {
            "gallery": {
                "directories": [str(video_dir), str(tmp_path)]
            },
            "scraper": {
                "video_extensions": [".mp4"]
            }
        }
        monkeypatch.setattr("web.routers.gallery_media.load_config", lambda: test_config)
        
        # 3. 請求
        path_arg = to_file_uri(str(video_file))
        response = client.get(f"/api/gallery/video?path={quote(path_arg)}")
        
        # 4. 斷言
        assert response.status_code == 200
        assert response.content == b'fake_video_content_here'
        
    def test_get_video_not_allowed(self, client, tmp_path, monkeypatch):
        """測試取得不在 directories 內的影片（應返回 403）"""
        out_dir = tmp_path / "outside"
        out_dir.mkdir()
        video_file = out_dir / "test.mp4"
        video_file.write_bytes(b'fake_video_content')
        
        test_config = {
            "gallery": {
                "directories": [str(tmp_path / "other")]
            },
            "scraper": {
                "video_extensions": [".mp4"]
            }
        }
        monkeypatch.setattr("web.routers.gallery_media.load_config", lambda: test_config)
        
        path_arg = to_file_uri(str(video_file))
        response = client.get(f"/api/gallery/video?path={quote(path_arg)}")
        
        assert response.status_code == 403
        assert "不在允許的資料夾範圍內" in response.text

    def test_get_video_invalid_extension(self, client, tmp_path, monkeypatch):
        """測試取得非影片副檔名（應返回 403）"""
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        bad_file = video_dir / "test.exe"
        bad_file.write_bytes(b'MZ...')
        
        test_config = {
            "gallery": {
                "directories": [str(video_dir), str(tmp_path)]
            },
            "scraper": {
                "video_extensions": [".mp4"]
            }
        }
        monkeypatch.setattr("web.routers.gallery_media.load_config", lambda: test_config)
        
        path_arg = to_file_uri(str(bad_file))
        response = client.get(f"/api/gallery/video?path={quote(path_arg)}")
        
        assert response.status_code == 403
        assert "不允許的檔案類型" in response.text
        
    def test_get_video_unc_verbatim_prefix_allowed(self, client, monkeypatch):
        """realpath 回傳 \\?\\UNC\\... verbatim 前綴 → strip 後命中白名單 → 200"""
        from unittest.mock import patch
        from urllib.parse import quote

        test_config = {
            'gallery': {
                'directories': [r'\\DiskStation\usbshare1'],
                'path_mappings': {},
            },
            'scraper': {'video_extensions': ['.mp4']},
        }
        monkeypatch.setattr('web.routers.gallery_media.load_config', lambda: test_config)

        path_arg = to_file_uri(r'\\DiskStation\usbshare1\a.mp4')

        with patch('os.path.realpath', return_value=r'\\?\UNC\DiskStation\usbshare1\a.mp4'), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024), \
             patch('web.routers.gallery_media.FileResponse',
                   return_value=__import__('starlette.responses', fromlist=['Response']).Response(status_code=200)):
            response = client.get(f'/api/gallery/video?path={quote(path_arg)}')

        assert response.status_code == 200

    def test_get_video_unc_outside_allowlist_still_403(self, client, monkeypatch):
        """realpath 回傳白名單外 NAS → 403（安全守衛不退化）"""
        from unittest.mock import patch
        from urllib.parse import quote

        test_config = {
            'gallery': {
                'directories': [r'\\DiskStation\usbshare1'],
                'path_mappings': {},
            },
            'scraper': {'video_extensions': ['.mp4']},
        }
        monkeypatch.setattr('web.routers.gallery_media.load_config', lambda: test_config)

        path_arg = to_file_uri(r'\\AnotherNAS\evil\a.mp4')

        with patch('os.path.realpath', return_value=r'\\AnotherNAS\evil\a.mp4'), \
             patch('os.path.exists', return_value=True):
            response = client.get(f'/api/gallery/video?path={quote(path_arg)}')

        assert response.status_code == 403


    def test_get_player_success(self, client, tmp_path, monkeypatch):
        """測試 /api/gallery/player 回傳正確的 HTML"""
        # video_player() 內部無條件呼叫 get_db_path()/VideoRepository() 做分組查詢
        # （web/routers/gallery_media.py），未 mock 前連上 output/openaver.db。
        monkeypatch.setattr("web.routers.gallery_media.get_db_path", lambda: tmp_path / "test.db")
        video_path = to_file_uri("C:/videos/test.mp4")
        response = client.get(f"/api/gallery/player?path={quote(video_path)}")

        assert response.status_code == 200
        assert "<video" in response.text
        assert "test.mp4" in response.text
        assert 'src="/api/gallery/video?path=' in response.text
        assert '%2Fvideos%2Ftest.mp4"' in response.text


    def test_player_filename_html_escaped(self, client, tmp_path, monkeypatch):
        """TASK-120a-T2：檔名 html_escape 既有行為不回歸

        檔名刻意不含 `/`（既有 rsplit('/', 1) 取檔名會被 `</...>` 截斷，
        那是既有行為而非本 task 範圍；此處只鎖 escape 本身）。
        """
        # [lint-guard: pytest-justified] 安全指紋（XSS escape）：斷言的是檔名
        # 經過 html_escape 之後出現在 player HTML，raw <>&" 不得原樣出現。
        # static_guard_lint 讀得到 scanner.py 有呼叫 html_escape，讀不到「這個
        # 檔名在這個請求下真的被 escape 進回應」——要打端點 render 才知道。
        from html import escape as html_escape

        monkeypatch.setattr("web.routers.gallery_media.get_db_path", lambda: tmp_path / "test.db")
        raw_name = 'test<>&".mp4'
        video_path = to_file_uri(f"C:/videos/{raw_name}")
        response = client.get(f"/api/gallery/player?path={quote(video_path)}")
        assert response.status_code == 200
        assert raw_name not in response.text
        assert html_escape(raw_name) in response.text


# ============ POST /api/gallery/generate-from-ids ============

class TestGenerateFromIds:
    """測試 POST /api/gallery/generate-from-ids"""


    def test_scraper_miss_adds_to_missing(self, client, monkeypatch, tmp_path):
        """scraper 也找不到時加入 missing 列表"""
        from unittest.mock import MagicMock, patch

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}

        mock_generator = MagicMock()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(output_dir), "path_mappings": {}},
            "general": {"theme": "light"}
        })

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[]):
            response = client.post('/api/gallery/generate-from-ids', json={'numbers': ['FAKE-999']})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'FAKE-999' in data['missing']
        assert data['video_count'] == 0


# ============ GET /api/gallery/jellyfin-check ============

class TestJellyfinCheck:
    """測試 GET /api/gallery/jellyfin-check"""

    @pytest.fixture(autouse=True)
    def reset_jellyfin_cache(self):
        """每個測試前後重置 jellyfin 快取，避免測試間污染"""
        import web.routers.scanner as scanner_mod
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0
        yield
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0


    # ---- T3(40c): TTL 快取相關測試 ----


class TestJellyfinExternalManagerGate:
    """Codex PR#122 P2 回歸：/jellyfin-check、/jellyfin-update 必須看 external_manager，
    off 模式下直接回零項、不得呼叫底層 check/generate（spec-111 CD-111-2 停產 -poster/
    -fanart 白名單一致）。反向鎖確保 gate 不是「永遠回零」的空實作。
    """

    @pytest.fixture(autouse=True)
    def reset_jellyfin_cache(self):
        import web.routers.scanner as scanner_mod
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0
        yield
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0


    @pytest.mark.parametrize(
        "scraper_config",
        [
            # Codex PR#123 round-4：這格原本是 'jellyfin_emby'（id=unknown_legacy_value），
            # 與 test_readonly_producer.py 剛移除的那個 parametrize 同根因——本測試 mock 掉
            # load_config()，直接注入該值；但真實 load_config() 會先被 Fix-72d migration
            # （core/config.py:364-367）改寫成 'jellyfin'，所以那是 production 不可達狀態。
            # 換成 'plex'：真正未知、不被任何 migration 攔截、會原樣流到 gate 的值。
            # migration → jellyfin → 產圖的正向鏈路由 test_readonly_producer.py::
            # TestExternalManagerMigrationToImageProduction 負責，不在本測試範圍。
            pytest.param({'external_manager': 'plex'}, id="unknown_value"),
        ],
    )
    def test_jellyfin_check_fail_closed_on_malformed_external_manager(
        self, client, monkeypatch, scraper_config
    ):
        """BE-CONFIG-03：external_manager 是純 str dict 讀取、不經 Pydantic Literal 驗證，
        手改過的 config.json 都可能帶非法值進來。白名單寫法（`not in
        STEM_IMAGE_MODES`）必須讓 None、缺 key、大小寫不符、未知值都 fail-closed 回
        0，而不是意外放行（若寫成 `== 'off'` 只擋字面 off，這些值會漏網）。

        四格都是 **production 真實可達**的狀態——沒有任何一格會被 load_config() 的
        migration 提前攔截（唯一的 Fix-72d migration 只逐字比對 'jellyfin_emby'）。"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True
        mock_check = MagicMock(return_value={'need_update': 7, 'items': [{'x': 1}]})

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.load_config', return_value={'scraper': scraper_config}), \
             patch('web.routers.scanner.check_jellyfin_images_needed', mock_check):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 0
        mock_check.assert_not_called()

    def test_jellyfin_update_off_mode_gate_short_circuits(self, client, monkeypatch, parse_sse_events):
        """off 模式：/jellyfin-update SSE 回 done + updated=0，且 generate_jellyfin_images
        未被呼叫（證明是 gate 擋掉，不是剛好零項）。"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True
        mock_generate = MagicMock(return_value={'poster': True, 'fanart': True})

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.load_config', return_value={'scraper': {'external_manager': 'off'}}), \
             patch('web.routers.scanner.generate_jellyfin_images', mock_generate):
            response = client.get('/api/gallery/jellyfin-update')

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('type') == 'done']
        assert len(done_events) == 1, f"應恰好一個 done 事件: {events}"
        assert done_events[0]['updated'] == 0
        mock_generate.assert_not_called()

    def test_jellyfin_endpoints_run_normally_under_media_server_flavour(self, client, monkeypatch, parse_sse_events):
        """反向鎖：media-server flavour（jellyfin）下兩支端點照常運作——沒有這條，
        gate 寫成「永遠回零」也會全綠。"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True
        mock_repo = MagicMock()
        check_result = {'need_update': 3, 'items': [
            {'cover_path': '/a/1.jpg', 'base_stem': '/a/1', 'number': 'ABC-001', 'maker': 'M'}
        ]}

        # /jellyfin-check：check_jellyfin_images_needed 確實被呼叫
        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.load_config', return_value={'scraper': {'external_manager': 'jellyfin'}}), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', return_value=check_result) as mock_check:
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        assert response.json()['data']['need_update'] == 3
        mock_check.assert_called_once()

        # /jellyfin-update：generate_jellyfin_images 確實被呼叫
        mock_generate = MagicMock(return_value={'poster': True, 'fanart': True})
        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.load_config', return_value={'scraper': {'external_manager': 'kodi'}}), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', return_value=check_result), \
             patch('web.routers.scanner.generate_jellyfin_images', mock_generate):
            response = client.get('/api/gallery/jellyfin-update')

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('type') == 'done']
        assert len(done_events) == 1
        mock_generate.assert_called_once()


_STATION4_FOCAL_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos"


def _station4_oracle_poster_bytes(focal_xy=MOCK_FOCAL_XY):
    """獨立 oracle：不經過 crop_to_poster / generate_jellyfin_images /
    generate_jellyfin_images_stream，直接呼叫底層 primitive 算出期望 bytes。
    不可用「呼叫同一站流程兩次自我比對」（gotchas-backend.md #9，101a-T1 已踩過）。

    TASK-102c-T1：改吃 focal_xy 參數（預設 MOCK_FOCAL_XY），不再自己呼叫真
    detect_focal——呼叫端須確保 patch `core.organizer.run_detection` 回傳
    `RunnerOutcome(kind="FOUND", focal=同一個值)`，否則 production 端與 oracle 端會對不上。
    """
    from core.organizer import _poster_window_ratio
    from core.focal import crop_image_position
    from PIL import Image
    import io

    fixture_path = _STATION4_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    focal = focal_xy
    with Image.open(fixture_path) as img:
        expected_cropped = crop_image_position(img.convert("RGB"), r_window, focal[0])
    buf = io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


class TestJellyfinUpdateStationWiring:
    """DoD①：站4（web/routers/scanner.py check_jellyfin_images_needed() +
    generate_jellyfin_images_stream()）接線——真跑完整流程（真 DB row，不 mock
    generate_jellyfin_images），fixture A（番號驅動）/ B（maker-only 驅動）各一次。

    Opus 追加 (b)：站4 有 module-level 全域快取 _jellyfin_cache_result /
    _jellyfin_cache_time，每個案例前後必須顯式重置，否則第二個 fixture 案例會
    吃到第一個案例的快取結果（假綠）。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}

    # 註：本 class 不需要重置 module-level 的 _jellyfin_cache_result/_jellyfin_cache_time。
    # generate_jellyfin_images_stream() 只「清空」快取（scanner.py:1699/1731），從不讀取；
    # 讀取只發生在 /jellyfin-check 端點（:1764）。故此處既無 setup 需求（不讀）也無
    # teardown 需求（stream 自己已清空）。原本寫過一個 autouse reset fixture，經 review
    # ablation 實測拿掉後測試仍全綠 ⇒ 無效防禦，留著只會讓人誤以為站4 有處理快取污染。
    def _run_station4(self, tmp_path, tag, fixture, monkeypatch):
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri
        from unittest.mock import patch
        from web.routers.scanner import generate_jellyfin_images_stream

        movie_dir = tmp_path / f"{fixture['number']}_{tag}"
        movie_dir.mkdir()
        cover = movie_dir / "cover.jpg"
        src = _STATION4_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        cover.write_bytes(src.read_bytes())

        db_path = tmp_path / f"t_{tag}.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        # video path 是虛構 DB key（scanner 端只讀 cover_path 反解的封面 FS 路徑，從不
        # 反解 path 本身指向的檔案是否存在）——但仍須經 to_file_uri() 產生，不可手拼
        # file URI 字面值（CLAUDE.md 路徑三區模型 + tests/unit/test_frontend_lint.py
        # TestPathContract.test_no_manual_uri_construct 守衛；101a-T3 review 抓到）。
        repo.upsert_batch([
            Video(path=to_file_uri(str(movie_dir / f"{tag}.mp4")), mtime=1.0,
                  number=fixture["number"], maker=fixture["maker"],
                  cover_path=to_file_uri(str(cover))),
        ])

        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {"scraper": {"external_manager": "jellyfin"}, "gallery": {"path_mappings": {}}})

        with patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            events = list(generate_jellyfin_images_stream())
        assert any('"type": "done"' in e for e in events), f"SSE 應完成: {events}"

        poster_path = cover.with_name("cover-poster.jpg")
        assert poster_path.exists(), "station4 應產生 poster"
        expected = _station4_oracle_poster_bytes()
        assert poster_path.read_bytes() == expected, "station4 poster 應對準焦點（獨立 oracle 比對）"

    def test_station4_fixture_a(self, tmp_path, monkeypatch):
        self._run_station4(tmp_path, "a", self._FIXTURE_A, monkeypatch)


def _station4_manual_oracle_poster_bytes(manual_x):
    """DoD⑤ 反向斷言用的獨立 oracle：鏡射 _station4_oracle_poster_bytes，差異只在
    跳過 detect_focal、直接用 manual_x 當 crop_image_position 的 pos——模擬「若程式碼
    改採 DB manual 值」時應該產生的 bytes。用來證明真跑結果「不等於」這個值。
    """
    from core.organizer import _poster_window_ratio
    from core.focal import crop_image_position
    from PIL import Image
    import io

    fixture_path = _STATION4_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    with Image.open(fixture_path) as img:
        expected_cropped = crop_image_position(img.convert("RGB"), r_window, manual_x)
    buf = io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


def _seed_station4_row(tmp_path, tag, *, number, maker, auto_focal='', crop_mode='auto'):
    """建真 cover 檔 + DB row（auto_focal/crop_mode 可控），回傳
    (db_path, repo, video_uri, cover_uri, cover_fs, movie_dir)。

    `upsert_batch` 對全新 path（無衝突）是單純 INSERT，`_FOCAL_PRESERVE` 的
    `ON CONFLICT` CASE 邏輯不觸發——傳入的 auto_focal/crop_mode 會原樣落地。
    """
    from core.database import init_db, VideoRepository, Video
    from core.path_utils import to_file_uri

    movie_dir = tmp_path / f"{number}_{tag}"
    movie_dir.mkdir()
    cover = movie_dir / "cover.jpg"
    cover.write_bytes((_STATION4_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg").read_bytes())
    db_path = tmp_path / f"t_{tag}.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    # video path 是虛構 DB key，仍須經 to_file_uri() 產生、不可手拼 file URI 字面值
    # （同 _run_station4 的理由，見上方註解；101a-T3 review 抓到的既有回歸，一併修）。
    video_uri = to_file_uri(str(movie_dir / f"{tag}.mp4"))
    cover_uri = to_file_uri(str(cover))
    repo.upsert_batch([Video(path=video_uri, mtime=1.0, number=number, maker=maker,
                              cover_path=cover_uri, auto_focal=auto_focal, crop_mode=crop_mode)])
    return db_path, repo, video_uri, cover_uri, cover, movie_dir


class TestPosterBakeStructuralLocks:
    """TASK-101a-T3 DoD④⑤⑥：把 spec-101 §3.2/§3.6/§3.7 的三條產品邊界（stateless、
    不讀手動值、fire-and-forget）用測試釘死。三個測試各自獨立建 DB／檔案，不共用 seed
    （TASK card 邊界條件）。全部走站4（web/routers/scanner.py generate_jellyfin_images_
    stream），因為它是四站中唯一「純烤圖、零其他 DB 寫入」的路徑（站3 會混進既有 98b
    背景 focal trigger，污染判定，見 TASK-101a-T3.md 現況分析第 4 節）。

    gate 用 fixture-A（number='FC2-1234567', maker='S1 NO.1 STYLE'）確保真的走到
    「烤圖 + 偵測」那條路——用 gate=False 的片會提早 no-op，測不出「烤圖有沒有寫 DB」。
    """

    _GATE_FIXTURE = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}

    def test_bake_does_not_touch_db_focal_fields(self, tmp_path, monkeypatch):
        """DoD④ spec §3.7-3 結構鎖：烤圖前後該片 DB auto_focal/crop_mode 零變化。"""
        from unittest.mock import patch
        from web.routers.scanner import generate_jellyfin_images_stream

        db_path, repo, video_uri, cover_uri, cover_fs, movie_dir = _seed_station4_row(
            tmp_path, "d4", number=self._GATE_FIXTURE["number"], maker=self._GATE_FIXTURE["maker"],
        )

        before = repo.get_by_path(video_uri)

        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {"scraper": {"external_manager": "jellyfin"}, "gallery": {"path_mappings": {}}})

        with patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            events = list(generate_jellyfin_images_stream())
        assert any('"type": "done"' in e for e in events), f"SSE 應完成: {events}"

        poster_path = cover_fs.with_name("cover-poster.jpg")
        assert poster_path.exists(), "應真的烤過圖（不是 gate 提早 no-op）"

        after = repo.get_by_path(video_uri)
        assert after.auto_focal == before.auto_focal
        assert after.crop_mode == before.crop_mode

    def test_bake_ignores_manual_focal_uses_pigo_result(self, tmp_path, monkeypatch):
        """DoD⑤ spec §3.7-3 產品邊界鎖（CD-2）：DB 存 crop_mode='manual' + 遠離 pigo
        真值的 auto_focal，站4真跑烤圖，poster bytes 正向等於獨立 pigo oracle、
        反向不等於獨立 manual oracle（兩條缺一不可，見 gotchas-backend.md #9）。
        """
        from unittest.mock import patch
        from web.routers.scanner import generate_jellyfin_images_stream

        db_path, repo, video_uri, cover_uri, cover_fs, movie_dir = _seed_station4_row(
            tmp_path, "d5", number=self._GATE_FIXTURE["number"], maker=self._GATE_FIXTURE["maker"],
            auto_focal='0.9000,0.5000', crop_mode='manual',   # 刻意遠離 pigo 真值 x≈0.3148
        )

        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {"scraper": {"external_manager": "jellyfin"}, "gallery": {"path_mappings": {}}})

        with patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            events = list(generate_jellyfin_images_stream())
        assert any('"type": "done"' in e for e in events), f"SSE 應完成: {events}"

        poster_path = cover_fs.with_name("cover-poster.jpg")
        assert poster_path.exists(), "應真的烤過圖"
        poster_bytes = poster_path.read_bytes()

        assert poster_bytes == _station4_oracle_poster_bytes(), (
            "poster 應採用 pigo 重跑結果"
        )
        assert poster_bytes != _station4_manual_oracle_poster_bytes(0.9000), (
            "poster 不應採用 DB manual 值"
        )

    def test_manual_focal_save_does_not_rebake_poster(self, tmp_path, monkeypatch, mocker, client):
        """DoD⑥ spec §3.7-4 fire-and-forget 正向鎖：先烤一次記下 bytes + st_mtime_ns，
        經 POST /api/showcase/video/save-focal 存入不同焦點（確認 200 + DB 真的寫入 manual
        值），poster bytes 與 mtime 逐一比對完全未變。

        不需要插 time.sleep（TASK-101a-T3.md 現況分析第 5 節：mtime tick 粒度 ~3.8ms，
        本測試真實時間尺度為 pigo ~2s + HTTP round-trip，遠超粒度風險窗口；且斷言方向
        是「未變」，粒度粗對它無害）。

        🔴 mtime 斷言才是這條測試的真網，不是多餘的保險——bytes 斷言對「重烤」這件事
        結構性瞎眼：pigo 是確定性演算法，重烤用的是同一張封面 + 同一組 gate 判定用的
        number/maker，會產生逐位元相同的 poster。實測：套用 DoD⑥ mutation（讓存焦點
        端點追加呼叫 crop_to_poster 重烤）後，bytes 斷言依然綠、只有 mtime 斷言轉紅。
        故不可以「bytes 都一樣了、mtime 檢查是多餘的」為由砍掉下面的 st_after 斷言。
        """
        from unittest.mock import patch
        from web.routers.scanner import generate_jellyfin_images_stream
        from core.path_utils import to_file_uri

        db_path, repo, video_uri, cover_uri, cover_fs, movie_dir = _seed_station4_row(
            tmp_path, "d6", number=self._GATE_FIXTURE["number"], maker=self._GATE_FIXTURE["maker"],
        )

        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {"scraper": {"external_manager": "jellyfin"}, "gallery": {"path_mappings": {}}})

        with patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            events = list(generate_jellyfin_images_stream())  # 先烤一次
        assert any('"type": "done"' in e for e in events), f"SSE 應完成: {events}"

        poster_path = cover_fs.with_name("cover-poster.jpg")
        assert poster_path.exists()
        bytes_before = poster_path.read_bytes()
        st_before = poster_path.stat().st_mtime_ns

        # directories.path 用 to_file_uri(str(tmp_path))（涵蓋 video_uri 所在的
        # movie_dir），不可手拼字面值 "/movies" 或 "file:///movies"——手拼與
        # coerce_to_file_uri() 實際產出的斜線數不保證一致（101a-T3 review 實測踩過：
        # 手拼 "/movies" 經 coerce_to_file_uri 在本機 WSL 環境變成 4 個斜線
        # file:////movies，對不上手拼 video_uri 的 3 個斜線，scope 檢查假 403）。
        # video_uri 與 directories.path 現在兩邊都經 to_file_uri()，斜線數必然一致。
        mocker.patch("web.routers.showcase.get_db_path", return_value=db_path)
        mocker.patch("web.routers.showcase.load_config", return_value={
            "gallery": {"directories": [{"path": to_file_uri(str(tmp_path)), "readonly": False, "output_path": ""}],
                        "path_mappings": {}}})

        resp = client.post("/api/showcase/video/save-focal",
                            json={"path": video_uri, "focal": "0.1000,0.9000",
                                  "expected_cover_path": cover_uri})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        bytes_after = poster_path.read_bytes()
        st_after = poster_path.stat().st_mtime_ns
        assert bytes_after == bytes_before, "存焦點不應重烤 poster（bytes 未變）"
        assert st_after == st_before, "存焦點不應重烤 poster（mtime 未變）"

        # 確認 DB 側真的寫入了（存焦點本身有效，只是沒有回頭碰 poster）
        after_row = repo.get_by_path(video_uri)
        assert after_row.crop_mode == 'manual'
        assert after_row.auto_focal == "0.1000,0.9000"


class TestMissingCheckAPI:
    """T10 — 測試 GET /api/gallery/missing-check 端點"""

    def _make_db(self, tmp_path, videos):
        """建立測試用 SQLite DB，插入指定影片資料"""
        from core.database import init_db, VideoRepository
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        # 單一 transaction 批次插入（避免 5000 筆各開一次交易拖慢測試）
        repo.upsert_batch(videos)
        return db_path


    def test_mixed_missing_counts_correct(self, client, tmp_path, monkeypatch):
        """混合缺失類型：missing_both + missing_nfo + missing_cover 各自正確計數"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            # missing both
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0),
            Video(path=to_file_uri(str(tmp_path / "b.mp4")), number="BBB-002",
                  cover_path="", nfo_mtime=0.0),
            # missing nfo only
            Video(path=to_file_uri(str(tmp_path / "c.mp4")), number="CCC-003",
                  cover_path="/covers/c.jpg", nfo_mtime=0.0),
            # missing cover only
            Video(path=to_file_uri(str(tmp_path / "d.mp4")), number="DDD-004",
                  cover_path="", nfo_mtime=1234567890.0),
            # complete
            Video(path=to_file_uri(str(tmp_path / "e.mp4")), number="EEE-005",
                  cover_path="/covers/e.jpg", nfo_mtime=1234567890.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['data']['missing_both'] == 2
        assert data['data']['missing_nfo'] == 1
        assert data['data']['missing_cover'] == 1
        assert data['data']['total_missing'] == 4
        assert len(data['data']['items']) == 4

    def test_missing_check_category_matches_counts(self, client, tmp_path, monkeypatch):
        """混合缺失類型：item['category'] 正確標記 both/nfo/cover 且與各計數一致"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            # missing both
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0),
            Video(path=to_file_uri(str(tmp_path / "b.mp4")), number="BBB-002",
                  cover_path="", nfo_mtime=0.0),
            # missing nfo only
            Video(path=to_file_uri(str(tmp_path / "c.mp4")), number="CCC-003",
                  cover_path="/covers/c.jpg", nfo_mtime=0.0),
            # missing cover only
            Video(path=to_file_uri(str(tmp_path / "d.mp4")), number="DDD-004",
                  cover_path="", nfo_mtime=1234567890.0),
            # complete
            Video(path=to_file_uri(str(tmp_path / "e.mp4")), number="EEE-005",
                  cover_path="/covers/e.jpg", nfo_mtime=1234567890.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        items_by_num = {i['number']: i for i in data['data']['items']}
        assert items_by_num['AAA-001']['category'] == 'both'
        assert items_by_num['BBB-002']['category'] == 'both'
        assert items_by_num['CCC-003']['category'] == 'nfo'
        assert items_by_num['DDD-004']['category'] == 'cover'
        assert sum(1 for i in data['data']['items'] if i['category'] == 'both') == data['data']['missing_both']
        assert sum(1 for i in data['data']['items'] if i['category'] == 'nfo') == data['data']['missing_nfo']
        assert sum(1 for i in data['data']['items'] if i['category'] == 'cover') == data['data']['missing_cover']


    def test_over_500_returns_full_items(self, client, tmp_path, monkeypatch):
        """total_missing > 500 → items 為完整 list（本 task 後新行為，舊版為 None）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / f"v{i:04d}.mp4")),
                  number=f"AAA-{i:04d}",
                  cover_path="", nfo_mtime=0.0)
            for i in range(750)
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 750
        assert data['data']['items'] is not None
        assert isinstance(data['data']['items'], list)
        assert len(data['data']['items']) == 750


    def test_produced_tried_quadrants_only_untried_unproduced_bucketed(self, client, tmp_path, monkeypatch):
        """produced x tried 2x2 矩陣：僅 (False,False) 進桶，其餘三象限早退（TASK-89b-T4）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        out_dir = to_file_uri(str(tmp_path / "out"))
        videos = [
            # (produced=True, tried=True) -> excluded
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0,
                  output_dir=out_dir, scrape_attempted_at=111.0),
            # (produced=True, tried=False) -> excluded
            Video(path=to_file_uri(str(tmp_path / "b.mp4")), number="BBB-002",
                  cover_path="", nfo_mtime=0.0,
                  output_dir=out_dir, scrape_attempted_at=0.0),
            # (produced=False, tried=True) -> excluded
            Video(path=to_file_uri(str(tmp_path / "c.mp4")), number="CCC-003",
                  cover_path="", nfo_mtime=0.0,
                  output_dir="", scrape_attempted_at=222.0),
            # (produced=False, tried=False) -> bucketed (missing_nfo, has cover)
            Video(path=to_file_uri(str(tmp_path / "d.mp4")), number="DDD-004",
                  cover_path="/covers/d.jpg", nfo_mtime=0.0,
                  output_dir="", scrape_attempted_at=0.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['success'] is True
        assert data['data']['missing_nfo'] == 1
        assert data['data']['missing_both'] == 0
        assert data['data']['missing_cover'] == 0
        assert data['data']['total_missing'] == 1
        assert len(data['data']['items']) == 1
        assert data['data']['items'][0]['number'] == 'DDD-004'


class TestScannerGenerateLongPathsField:
    """spec-48a §a5 契約 3 — /api/gallery/generate SSE done event 必須含 long_paths key"""


    def test_skipped_long_paths_captured_via_on_skip(
        self, client, tmp_path, monkeypatch, parse_sse_events
    ):
        """
        Codex fix: 因 OSError（如 Windows 長路徑）被跳過的 entry 不會進 all_files，
        必須透過 fast_scan_directory 的 on_skip callback 回收，再由 caller
        以 len > 260 篩入 long_paths。若 caller 沒串 on_skip 或沒把 skipped
        併進 long_paths，這個測試會 fail。
        """
        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {
                "directories": [str(scan_dir)],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        })

        # 模擬平台 = win32，讓 long_paths 收集邏輯啟動
        monkeypatch.setattr("web.routers.scanner.sys.platform", "win32")

        # Stub fast_scan_directory：不掃真目錄，而是觸發 on_skip 兩次
        # 一次長路徑（>260，應進 long_paths），一次短路徑（<260，不應進）
        long_skip_path = "C:\\" + "a" * 280  # len > 260
        short_skip_path = "C:\\short-denied.mp4"  # len < 260（權限拒絕，不是長路徑）

        def stub_fast_scan(directory, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None:
                on_skip(long_skip_path, OSError(206, "too long"))
                on_skip(short_skip_path, PermissionError(13, "denied"))
            return []  # 無檔案進 results

        monkeypatch.setattr("web.routers.scanner.fast_scan_directory", stub_fast_scan)
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: tmp_path / "test.db")

        response = client.get('/api/gallery/generate')
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('type') == 'done']
        assert done_events, "SSE stream 未收到 done event"

        done_payload = done_events[-1]
        long_paths = done_payload.get('long_paths', [])
        assert long_skip_path in long_paths, (
            f"skipped 的長路徑 {long_skip_path!r} 未被 caller 透過 on_skip 收集至 long_paths — "
            f"可能 scanner.py 未傳 on_skip，或未把 skipped_paths filter >260 併入 long_paths"
        )
        assert short_skip_path not in long_paths, (
            "短的 skipped 路徑（權限錯誤等非長路徑）不應被當作長路徑警告"
        )

    def test_partial_scan_skipped_paths_do_not_trigger_deletion(
        self, client, tmp_path, monkeypatch, parse_sse_events
    ):
        """
        Codex regression P1：當 fast_scan_directory 回傳 [] + 透過 on_skip 回報路徑失敗時，
        掃描流程必須跳過 deletion 偵測，否則該目錄下既有 DB 紀錄會被全部誤刪。

        控制流守護：
          - 在 DB 預先塞一筆「位於掃描目錄下」的 Video 紀錄
          - stub fast_scan_directory：只透過 on_skip 回報一筆長路徑、return []
          - 跑完 /api/gallery/generate 後 DB 紀錄必須仍存在（未被誤刪）

        若 scanner.py 漏 gate（在 skipped_paths 非空時仍走 deletion 區塊），
        current_paths 會是空 set，該目錄下所有 DB 紀錄都會被 delete_by_paths 清掉，
        這個斷言會 fail。
        """
        from unittest.mock import patch
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        # 1. 準備掃描目錄 + 輸出目錄
        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # 2. 建立測試用 DB + 塞入一筆位於 scan_dir 下的既存紀錄
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        existing_fs_path = str(scan_dir / "existing_video.mp4")
        existing_uri = to_file_uri(existing_fs_path)
        existing_video = Video(
            path=existing_uri,
            number="EXIST-001",
            title="既存影片",
            mtime=1000000.0,
            nfo_mtime=0.0,
        )
        repo.upsert(existing_video)

        # 塞入前確認 DB 真的有這筆
        pre_scan = repo.get_mtime_index()
        assert existing_uri in pre_scan, "DB 預設記錄塞入失敗，測試前提不成立"

        # 3. Stub fast_scan_directory：回傳 [] + on_skip 回報一筆長路徑
        def stub_fast_scan(directory, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None:
                long_path = str(scan_dir / ("x" * 280 + ".mp4"))  # > 260 chars
                on_skip(long_path, OSError(206, "File name too long"))
            return []

        monkeypatch.setattr("web.routers.scanner.fast_scan_directory", stub_fast_scan)

        # 4. Mock config：scan_dir 為唯一掃描目錄
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {
                "directories": [str(scan_dir)],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        })

        # 5. 把 scanner 內部用的 db_path 指向 tmp 測試 DB
        #    （scanner.py 在 generate_avlist 中呼叫 get_db_path() 取得 DB 路徑）
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            response = client.get('/api/gallery/generate')
            assert response.status_code == 200
            events = parse_sse_events(response.text)
            done_events = [e for e in events if e.get('type') == 'done']
            assert done_events, "SSE stream 未收到 done event"

            # 6. 關鍵斷言：scan 不完整（skipped_paths 非空 + all_files 為空）
            #    時，既存 DB 紀錄必須仍存在
            post_scan = repo.get_mtime_index()
            assert existing_uri in post_scan, (
                "partial scan（skipped_paths 非空、all_files 為空）誤刪了位於掃描目錄下的 "
                "DB 紀錄！deletion 區塊必須 gate 在 `not skipped_paths` 才能避免把失敗而沒掃到的 "
                "記錄誤判為已刪除。"
            )

        # 7. 附加斷言：done event 仍含 long_paths 欄位（契約 3 不回歸）
        done_payload = done_events[-1]
        assert 'long_paths' in done_payload, "partial scan 後 done payload 仍應含 long_paths 欄位"


class TestGenerateAvlistCleanupPass:
    """spec-48b §b1 AC#2 — /api/gallery/generate 主 UI 路徑也清孤兒 sample_images
    驗證 generate_avlist() 在 SSE 流完成後，DB 中孤兒 URI 已被清除。
    （Canonical Decision #4：雙流程覆蓋，Scanner UI 主路徑不呼叫 scan_to_sqlite）
    """


    def test_generate_avlist_passes_nfo_title_format_to_scanner(self, client, tmp_path, monkeypatch):
        """generate_avlist() 必須把 scraper.nfo_title_format 傳進 VideoScanner。"""
        from unittest.mock import patch

        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {
                "directories": [str(scan_dir)],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "general": {"theme": "light"},
            "scraper": {
                "video_extensions": [".mp4"],
                "nfo_title_format": "{num}-{title}",
            },
        })

        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: tmp_path / "test.db")

        with patch("web.routers.scanner.VideoScanner") as MockScanner:
            response = client.get('/api/gallery/generate')

        assert response.status_code == 200
        assert MockScanner.call_args.kwargs['nfo_title_format'] == '{num}-{title}'


class TestScanPruneThumbnailInvalidation:
    """feature/71 T8 邊界2：scan prune → 每個 deleted_paths 被 invalidate（原樣 DB URI）。"""

    def test_prune_invalidates_each_deleted_path_raw_uri(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        """DB 有一筆位於掃描目錄下的 row、current scan 不含之 → prune 觸發；
        spy invalidate 對該 deleted_path 以「原樣 DB URI」（未經 to_file_uri）呼叫一次。
        """
        from core.database import init_db, VideoRepository, Video

        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        # row 位於 scan_dir 下，但 scan 不會掃到它（目錄空）→ 應被 prune
        deleted_fs = str(scan_dir / "deleted_video.mp4")
        deleted_uri = to_file_uri(deleted_fs)
        repo.upsert(Video(
            path=deleted_uri,
            number="DEL-001",
            title="待刪影片",
            mtime=1000000.0,
            nfo_mtime=0.0,
        ))

        # 掃到一個「現存」檔案（≠ deleted row），無 skipped → 走 else 分支 prune。
        # all_files 非空才不會在 "沒有影片檔案" 早退（scanner.py:187），prune 才會跑。
        kept_fs = str(scan_dir / "kept_video.mp4")
        Path(kept_fs).write_bytes(b"x" * 1024)

        def stub_fast_scan(directory, extensions, min_size_bytes, on_skip=None):
            return [{"path": kept_fs, "size": 1024, "mtime": 2000000.0}]

        monkeypatch.setattr("web.routers.scanner.fast_scan_directory", stub_fast_scan)
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {
                "directories": [str(scan_dir)],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        })

        invalidate_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.invalidate"
        )

        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)
        response = client.get("/api/gallery/generate")
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        assert [e for e in events if e.get("type") == "done"], "未收到 done event"

        # 該 row 已被刪
        assert deleted_uri not in repo.get_mtime_index()
        # invalidate 以原樣 DB URI 呼叫
        invalidate_spy.assert_any_call(deleted_uri)
        called_args = [c.args[0] for c in invalidate_spy.call_args_list]
        assert deleted_uri in called_args
        # 原樣 URI：未被再次包一層 to_file_uri（否則會變 file:////... 之類）
        assert to_file_uri(deleted_uri) not in called_args or to_file_uri(deleted_uri) == deleted_uri


class TestGenerateReadonlyBridge:
    """TASK-88c-T2 — generate_avlist readonly 分流 + SSE thread/queue 橋接 + 四數摘要。

    mock patch target = web.routers.scanner.produce_source（T-2 import 落點）。
    """

    def _readonly_config(self, tmp_path, sources):
        """組一份 config：sources 為 [(readonly, output_path 或 None), ...]。"""
        output_dir = tmp_path / "html_out"
        output_dir.mkdir(exist_ok=True)
        directories = []
        for i, (readonly, out) in enumerate(sources):
            src_dir = tmp_path / f"src{i}"
            src_dir.mkdir(exist_ok=True)
            directories.append({
                "path": str(src_dir),
                "readonly": readonly,
                "output_path": out if out is not None else "",
            })
        return {
            "gallery": {
                "directories": directories,
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }

    def _result(self, tmp_path, **kw):
        from core.readonly_producer import ProduceResult
        out = str(tmp_path / "out")
        return ProduceResult(source_path=str(tmp_path / "src0"), output_path=out, **kw)

    # 1. 分流互斥（正向）：readonly → produce_source 呼叫一次，args 正確
    def test_readonly_source_calls_produce_source_once(self, client, tmp_path, monkeypatch, mocker):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.get_db_path", return_value=tmp_path / "test.db")
        mock_ps = mocker.patch("web.routers.scanner.produce_source",
                               return_value=self._result(tmp_path))
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        assert mock_ps.call_count == 1
        call = mock_ps.call_args
        src_arg = call.args[0]
        assert src_arg.readonly is True
        assert src_arg.path == str(tmp_path / "src0")
        # config + repo 位置參數
        assert call.args[1] is cfg
        from core.database import VideoRepository
        assert isinstance(call.args[2], VideoRepository)
        # TASK-90b-T3: production 路徑（真的 client.get 打 /api/gallery/generate handler）
        # 現在會傳入 handler 建立的 cancel_event.is_set（bound method），不再是寫死的 None——
        # 斷言它是 callable 且確實是 threading.Event 的 is_set bound method，而非零參數
        # 直呼 generate_avlist() 時才會拿到的 None 預設值。
        should_abort = call.kwargs["should_abort"]
        assert callable(should_abort)
        assert should_abort.__func__ is threading.Event.is_set
        assert should_abort() is False

    # 1b. TASK-90b-T3 wiring：should_abort 從 generate_avlist 直呼一路轉發到 produce_source，
    # 中間不包 lambda，用 `is` 斷言身分一致（非包裝出的新 callable）。

    # 2. 分流互斥（反向）：非 readonly → produce_source 未被呼叫

    # 3. SSE 逐片橋接：on_progress 連發 3 outcome → SSE 出 3 條對應 log；sentinel 後續下一來源

    # 4. 四數摘要累計

    # 5. no_output_path 提示

    # 6. CRITICAL：source-level 例外傳遞 + 續跑
    def test_source_level_exception_continues(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        from core.readonly_producer import ProduceResult
        cfg = self._readonly_config(tmp_path, [
            (True, str(tmp_path / "out0")),
            (True, str(tmp_path / "out1")),
        ])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.get_db_path", return_value=tmp_path / "test.db")

        def side_effect(source, config, repo, *, on_progress=None, should_abort=None, force=False, reachable=True, strm_mappings_getter=None):
            if source.path == str(tmp_path / "src0"):
                raise ValueError("boom (迴圈前 normalize/列檔/DB 逃出)")
            return ProduceResult(source_path=source.path, output_path=source.output_path, created=3)

        mock_ps = mocker.patch("web.routers.scanner.produce_source", side_effect=side_effect)
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        # error 事件（type=log, level=error）
        errs = [e for e in events if e.get("type") == "log" and e.get("level") == "error"]
        assert any("生成失敗" in e.get("message", "") for e in errs)
        # source_errors 計數
        done = [e for e in events if e.get("type") == "done"][-1]
        assert done["readonly_stats"]["source_errors"] == 1
        # 迴圈續跑：第二來源仍被呼叫 + 產出摘要
        assert mock_ps.call_count == 2
        assert done["readonly_stats"]["created"] == 3
        assert done["readonly_stats"]["sources"] == 1

    # 7. 跨 thread DB 寫入（回歸鎖，無 ProgrammingError）

    # 8. deletion 安全（readonly continue 早於 deletion → 影片未被誤刪）
    def test_readonly_video_not_deleted(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        from core.database import init_db, VideoRepository, Video
        from core.readonly_producer import ProduceResult
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        src_dir = tmp_path / "src0"
        src_dir.mkdir()
        out_dir = tmp_path / "out0"
        out_dir.mkdir()
        # RED-able mutation guard：磁碟上放一個「真實但不匹配」的影片檔，讓 normal-scan
        # 路徑（若 readonly 分流被移除）的 all_files 非空、繞過 :369 空目錄短路 → deletion
        # 區塊會真的跑。current_paths 只含 other.mp4，DB 預置的 movie.mp4（在同夾下、
        # 但不在磁碟）就會被 delete_by_paths prune → 移除分流時本測試 RED。
        (src_dir / "other.mp4").write_bytes(b"x" * 4096)  # 真實檔，掃得到、非 DB 預置那筆
        # readonly-source 影片：path=來源 URI（movie.mp4，磁碟上不存在），cover 在 output_path 下
        vid_uri = to_file_uri(str(src_dir / "movie.mp4"))
        cover_uri = to_file_uri(str(out_dir / "movie" / "movie.jpg"))
        repo.upsert(Video(path=vid_uri, number="RO-001", title="唯讀影片",
                          cover_path=cover_uri, mtime=1.0, nfo_mtime=0.0))
        assert vid_uri in repo.get_mtime_index()

        cfg = {
            "gallery": {
                "directories": [{"path": str(src_dir), "readonly": True, "output_path": str(out_dir)}],
                "output_dir": str(tmp_path / "html_out"),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)
        # produce_source 空 result，不動 DB
        mocker.patch("web.routers.scanner.produce_source",
                     return_value=ProduceResult(source_path=str(src_dir), output_path=str(out_dir)))
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        assert [e for e in events if e.get("type") == "done"], "未收到 done event"
        # 未被誤刪
        assert vid_uri in repo.get_mtime_index(), "readonly 來源影片被誤刪（deletion 未被 continue 繞過）"

    # 9. UNC readonly 來源 → 分流早於 normalize，produce_source 被呼叫
    def test_unc_readonly_source_reaches_producer(self, client, tmp_path, monkeypatch, mocker):
        from core.readonly_producer import ProduceResult
        unc = r"\\server\share"
        cfg = {
            "gallery": {
                "directories": [{"path": unc, "readonly": True, "output_path": str(tmp_path / "out0")}],
                "output_dir": str(tmp_path / "html_out"),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.get_db_path", return_value=tmp_path / "test.db")
        mock_ps = mocker.patch("web.routers.scanner.produce_source",
                               return_value=ProduceResult(source_path=unc, output_path=str(tmp_path / "out0")))
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        assert mock_ps.call_count == 1
        assert mock_ps.call_args.args[0].path == unc

    # 10. 88c-P2：來源級失敗 → 完成通知走 warn（非純 success）

    # 11. PR#91 ②：個別影片失敗（readonly failed>0, source_errors=0）→ 完成通知走 warn

    # -----------------------------------------------------------------
    # TASK-89b-T6: DB-row-only prune + Finding-2 不誤報成功回歸鎖
    # -----------------------------------------------------------------

    def _completion_calls(self, mock_notif):
        return [
            c for c in mock_notif.call_args_list
            if c.kwargs.get("task_type") == "scanner_generate"
            and c.args and c.args[1] != "notif.scanner_started"
        ]

    # 12. pruned 計數進 done SSE readonly_stats（mock-based，不觸發真實 prune 邏輯，
    #     只驗證 ProduceResult.pruned 有被 scanner.py 正確累計/傳遞）

    # 13. Finding-2 情境一：來源不可達 → per-source warn SSE + unreachable 計數 +
    #     完成通知 warn（非 success）
    def test_unreachable_source_warns_and_completion_is_warn(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.get_db_path", return_value=tmp_path / "test.db")
        mocker.patch(
            "web.routers.scanner.produce_source",
            return_value=self._result(tmp_path, aborted_reason="unreachable"),
        )
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        warn_logs = [
            e for e in events
            if e.get("type") == "log" and e.get("level") == "warn"
            and "來源無法連線" in e.get("message", "")
        ]
        assert warn_logs, "unreachable 來源應有一則含「來源無法連線」的 warn SSE"

        done = [e for e in events if e.get("type") == "done"][-1]
        assert done["readonly_stats"]["unreachable"] == 1

        final = self._completion_calls(mock_notif)[-1]
        assert final.args[0] == "warn", f"完成通知應為 warn，實得 {final.args[0]}"
        assert "無法連線" in final.kwargs.get("message", "")

    # 14. Finding-2 情境二：partial-scan（skipped_paths 非空）→ 追加 warn SSE +
    #     partial 計數 + 完成通知 warn

    # 15. Finding-2 情境三：no_output>0（原本已計數但完成通知未讀）→ 完成通知 warn

    # 16. Real produce_source (unmocked): 跨來源隔離 + partial suppression + DB-row-only
    #     （不動輸出夾檔案）。以下測試不 mock produce_source，讓真實 prune 邏輯跑，
    #     只 stub fast_scan_directory/extract_number 避免真實掃描/網路呼叫。
    def _run_real_readonly_prune(self, client, tmp_path, monkeypatch, sources_scan_map,
                                  extra_config=None):
        """sources_scan_map: {src_dir_name: [{"path": fs_path, "size": n, "mtime": t}, ...]}"""

        def stub_fast_scan(directory, extensions, min_size_bytes, on_skip=None):
            key = Path(directory).name
            return sources_scan_map.get(key, [])

        monkeypatch.setattr("core.readonly_producer.fast_scan_directory", stub_fast_scan)
        # extract_number → None：所有片走 no_scrape 早退，不觸發 search_jav（避免網路呼叫）
        monkeypatch.setattr("core.readonly_producer.extract_number", lambda basename: None)

        return client.get("/api/gallery/generate")

    def test_cross_source_isolation_real_prune(self, client, tmp_path, monkeypatch, parse_sse_events):
        import time
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        src_a = tmp_path / "srcA"
        src_a.mkdir()
        src_b = tmp_path / "srcB"
        src_b.mkdir()
        output_dir = tmp_path / "html_out"
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        # A 的既存片「消失」（本次掃描不含它，但本次列表非空——另有 kept_a.mp4，
        # 使 gate 通過；若本次列表整個是空的則屬「不刪」的另一分支，非本測試要驗的情境）
        gone_a_uri = to_file_uri(str(src_a / "gone_a.mp4"))
        repo.upsert(Video(path=gone_a_uri, number="GONE-A", title="A 已消失", mtime=1.0, nfo_mtime=0.0))
        repo.update_scrape_attempted_at(gone_a_uri, time.time())
        kept_a_fs = str(src_a / "kept_a.mp4")

        # B 的既存片「仍在」本次掃描列表 → 不應被刪（也不應被 A 的 prune 誤刪）
        kept_b_fs = str(src_b / "kept_b.mp4")
        kept_b_uri = to_file_uri(kept_b_fs)
        repo.upsert(Video(path=kept_b_uri, number="KEPT-B", title="B 仍在", mtime=1.0, nfo_mtime=0.0))
        repo.update_scrape_attempted_at(kept_b_uri, time.time())

        cfg = {
            "gallery": {
                "directories": [
                    {"path": str(src_a), "readonly": True, "output_path": str(tmp_path / "outA")},
                    {"path": str(src_b), "readonly": True, "output_path": str(tmp_path / "outB")},
                ],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)

        resp = self._run_real_readonly_prune(
            client, tmp_path, monkeypatch,
            sources_scan_map={
                # gone_a.mp4 不再出現，但列表非空（有 kept_a.mp4）→ gate 通過
                "srcA": [{"path": kept_a_fs, "size": 1024, "mtime": 2.0}],
                "srcB": [{"path": kept_b_fs, "size": 1024, "mtime": 2.0}],
            },
        )
        assert resp.status_code == 200
        parse_sse_events(resp.text)

        remaining = repo.get_mtime_index()
        assert gone_a_uri not in remaining, "A 的消失片應被本次 prune 刪除"
        assert kept_b_uri in remaining, "B 的仍在片不應被刪（跨來源隔離）"

    def test_partial_scan_suppresses_prune_even_when_files_look_gone(
        self, client, tmp_path, monkeypatch, parse_sse_events
    ):
        import time
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        src_a = tmp_path / "srcA"
        src_a.mkdir()
        output_dir = tmp_path / "html_out"
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        gone_looking_uri = to_file_uri(str(src_a / "looks_gone.mp4"))
        repo.upsert(Video(path=gone_looking_uri, number="X-001", title="看似消失", mtime=1.0, nfo_mtime=0.0))
        repo.update_scrape_attempted_at(gone_looking_uri, time.time())

        cfg = {
            "gallery": {
                "directories": [
                    {"path": str(src_a), "readonly": True, "output_path": str(tmp_path / "outA")},
                ],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)

        def stub_fast_scan(directory, extensions, min_size_bytes, on_skip=None):
            # 回報一筆讀取失敗路徑 + 回傳空列表 → skipped_paths 非空
            if on_skip is not None:
                on_skip(str(src_a / "unreadable_dir"), OSError("denied"))
            return []

        monkeypatch.setattr("core.readonly_producer.fast_scan_directory", stub_fast_scan)
        monkeypatch.setattr("core.readonly_producer.extract_number", lambda basename: None)

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        parse_sse_events(resp.text)

        remaining = repo.get_mtime_index()
        assert gone_looking_uri in remaining, (
            "partial scan（skipped_paths 非空）必須抑制 prune，即使該片看似從本次列表消失"
        )


class TestGenerateAvlistShouldAbortTopLevel:
    """TASK-90b-T4 — 一般掃描分支（非 readonly）逐來源 / 逐檔迴圈頂端中止檢查
    + 迴圈結束後一次性 `_aborted` 判斷，決定尾段留/跳（見 TASK-90b-T4.md
    「尾段逐步留/跳決策表」）。直呼 generate_avlist(should_abort=fake)，比照
    T3 `test_should_abort_forwarded_by_identity_to_produce_source` 手法
    （:1304 附近），不透過 client（cancel_event 由 handler 建立，非本 task 範圍）。
    """

    def _config(self, tmp_path, dirs):
        """組一份非 readonly config：dirs 為多個資料夾 path 字串 list。"""
        output_dir = tmp_path / "html_out"
        output_dir.mkdir(exist_ok=True)
        return {
            "gallery": {
                "directories": [str(d) for d in dirs],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "search": {"proxy_url": ""},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }

    def _make_dir_with_files(self, tmp_path, name, count):
        d = tmp_path / name
        d.mkdir()
        paths = []
        for i in range(count):
            f = d / f"video_{i}.mp4"
            f.write_bytes(b"x" * 2048)
            paths.append(str(f))
        return d, paths

    def _counting_should_abort(self, trigger_after):
        """回傳一個 callable：前 `trigger_after` 次呼叫回 False，之後回 True。"""
        state = {"n": 0}

        def fake():
            state["n"] += 1
            return state["n"] > trigger_after

        fake.call_count_ref = state
        return fake

    def _patch_scan_file(self, mocker):
        """mock VideoScanner.scan_file，回傳最小可用 VideoInfo，避免真的觸發
        NFO/外部刮削；用 call 次數與傳入路徑斷言迴圈提前結束。"""
        from core.gallery_scanner import VideoInfo
        calls = []

        def fake_scan_file(self, video_path, base_path=None):
            calls.append(video_path)
            return VideoInfo(path=to_file_uri(video_path), title="t", num="ABC-001")

        mocker.patch("web.routers.scanner.VideoScanner.scan_file", fake_scan_file)
        return calls

    def _assert_cancelled_terminal(self, mock_notif):
        """abort 尾段的通知契約（PR#90b Codex P1+P2）：不發 success/warn 完成通知，
        改發恰好一筆中性 info `notif.scanner_cancelled`，與 scanner_started 配對。"""
        gen_calls = [
            c for c in mock_notif.call_args_list
            if c.kwargs.get("task_type") == "scanner_generate" and c.args
        ]
        titles = [c.args[1] for c in gen_calls]
        assert "notif.scanner_done" not in titles, f"abort 不應誤報完成，實得 {titles}"
        assert "notif.scanner_done_with_errors" not in titles, f"abort 不應誤報完成，實得 {titles}"
        assert titles.count("notif.scanner_cancelled") == 1, \
            f"abort 應發恰好一筆取消通知配對 started，實得 {titles}"
        cancel_call = next(c for c in gen_calls if c.args[1] == "notif.scanner_cancelled")
        assert cancel_call.args[0] == "info", "取消通知須為中性 info，不可誤報 success"

    def _parse_events(self, sse_strings):
        """把 generate_avlist() yield 出的原始 SSE 字串（"data: {...}\\n\\n"）
        解析為 dict list，比照 conftest.parse_sse_events 邏輯（但輸入是
        generator 直呼的原始字串 list，非 TestClient response.text）。"""
        import json as _json
        events = []
        for chunk in sse_strings:
            for line in chunk.strip().split('\n'):
                if line.startswith('data: '):
                    try:
                        events.append(_json.loads(line[6:]))
                    except _json.JSONDecodeError:
                        pass
        return events

    # ---- (1) 逐來源迴圈中途 abort：第二個來源完全未被迭代 ----

    def test_outer_loop_break_leaves_second_source_unprocessed(self, tmp_path, monkeypatch, mocker):
        from web.routers.scanner import generate_avlist

        dir0, _ = self._make_dir_with_files(tmp_path, "src0", 1)
        dir1, _ = self._make_dir_with_files(tmp_path, "src1", 1)
        cfg = self._config(tmp_path, [dir0, dir1])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: tmp_path / "test.db")

        scan_calls = self._patch_scan_file(mocker)
        mock_html = mocker.patch("web.routers.scanner.HTMLGenerator")
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        # calls 序列：outer(dir0) outer 檢查=#1, inner(file0@dir0)=#2, outer(dir1)=#3
        # trigger_after=2 → 前兩次 False，第 3 次（outer dir1 之前）True → dir1 整個不處理
        fake_should_abort = self._counting_should_abort(trigger_after=2)

        # 先塞非預設哨兵值，讓 (d) 的「cache 被重設」斷言能真正觀察到 None/0 的
        # 狀態轉移——否則 module 層預設就是 None/0，即使 abort 誤跳過重設也會假綠。
        import web.routers.scanner as scanner_mod
        scanner_mod._jellyfin_cache_result = {"need_update": 1}
        scanner_mod._jellyfin_cache_time = 12345.0

        events = list(generate_avlist(should_abort=fake_should_abort))

        # (a) 只有 dir0 的檔案被掃到，dir1 完全未被迭代
        assert len(scan_calls) == 1
        assert str(dir0) in scan_calls[0]
        assert not any(str(dir1) in c for c in scan_calls)

        # (b) HTML 未被產生
        mock_html.return_value.generate.assert_not_called()

        # (c) 不發 success/warn 完成通知，改發恰好一筆中性 info「取消」通知，與
        # 函式開頭無條件 emit 的 scanner_started 配對（PR#90b Codex P2：只發 started
        # 不發 terminal 會在 append-only 通知抽屜永久殘留一筆看似未完成的「掃描開
        # 始」，使用者每中止一次累積一筆錯狀態）。
        self._assert_cancelled_terminal(mock_notif)

        # (d) jellyfin cache 仍被重設（必要資源收尾）——哨兵值已被覆寫回 None/0
        assert scanner_mod._jellyfin_cache_result is None
        assert scanner_mod._jellyfin_cache_time == 0

        # (e) done event 未被 yield
        parsed = self._parse_events(events)
        assert not [e for e in parsed if e.get("type") == "done"]

    # ---- (2) 逐檔內層迴圈中途 abort：同一資料夾內後續檔案未被迭代 ----


    # ---- (2b) tail-race：迴圈已跑完、尾段進行中才斷線（PR#90b Codex P1）----


    # ---- (3) 零回歸：should_abort=None → 尾段全部照舊執行 ----


    # ---- (4) 零回歸：should_abort 設置但從未觸發（正常跑完）----


# ============ TASK-98b-T2: 掃描 empty-focal gate（scanner.py router 路徑） ============

class TestGenerateAvlistFocalTrigger:
    """generate_avlist 掃描入庫後的 focal trigger（empty-focal gate，router 路徑）。

    與 gallery_scanner.scan_to_sqlite 對稱：直接 driver generate_avlist()，真 tmp DB +
    真 requires_face_detection gate；patch use-site `web.routers.scanner.
    maybe_submit_video_focal` 只驗接線與 gate，不真跑 pigo。
    """

    def _run(self, tmp_path, num, maker="", seed_auto_focal=None, seed_unchanged=False,
             should_abort=None, extra_nums=None):
        """extra_nums: 額外的無碼候選番號列表（都用同一個 maker，全部視為新檔案，
        全部 requires_face_detection=True）。單檔既有 caller 不傳此參數，行為不變。"""
        import types
        from unittest.mock import patch, MagicMock
        from core.database import init_db, VideoRepository, Video
        from core.gallery_scanner import VideoInfo
        from core.path_utils import to_file_uri

        scan_dir = tmp_path / "lib"
        scan_dir.mkdir()
        video_fs = str(scan_dir / f"{num}.mp4")
        cover_fs = scan_dir / f"{num}.jpg"
        cover_fs.write_bytes(b"x")
        path_uri = to_file_uri(video_fs)
        cover_uri = to_file_uri(str(cover_fs))

        db_file = tmp_path / "avlist_focal.db"
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)
        if seed_auto_focal is not None:
            with patch("core.similar.ranker_cache.SimilarRankerCache"):
                repo.upsert(Video(path=path_uri, number=num, maker=maker, cover_path=cover_uri))
            repo.update_auto_focal(path_uri, seed_auto_focal, cover_uri)
        elif seed_unchanged:
            # Codex PR#105 P2 回歸釘：既有列 mtime 與本次掃描一致（111）→ 不進
            # needs_scan/videos_to_upsert，auto_focal 維持 dataclass 預設空字串。
            with patch("core.similar.ranker_cache.SimilarRankerCache"):
                repo.upsert(Video(
                    path=path_uri, number=num, maker=maker, cover_path=cover_uri,
                    mtime=111, nfo_mtime=0.0,
                ))

        info = VideoInfo()
        info.num = num
        info.path = path_uri
        info.img = cover_uri
        info.maker = maker
        info.title = "T"

        fast_scan_files = [{"path": video_fs, "mtime": 111, "nfo_mtime": 0}]
        scan_file_infos = {video_fs: info}

        # TASK-99a: 支援多候選（focal 迴圈中途 abort 測試需要 >= 2 個候選才能
        # 觀察「第 1 個 submit 之後、第 2 個未 submit」）。
        for extra_num in (extra_nums or []):
            extra_video_fs = str(scan_dir / f"{extra_num}.mp4")
            extra_cover_fs = scan_dir / f"{extra_num}.jpg"
            extra_cover_fs.write_bytes(b"x")
            extra_path_uri = to_file_uri(extra_video_fs)
            extra_cover_uri = to_file_uri(str(extra_cover_fs))

            extra_info = VideoInfo()
            extra_info.num = extra_num
            extra_info.path = extra_path_uri
            extra_info.img = extra_cover_uri
            extra_info.maker = maker
            extra_info.title = "T"

            fast_scan_files.append({"path": extra_video_fs, "mtime": 111, "nfo_mtime": 0})
            scan_file_infos[extra_video_fs] = extra_info

        config = {
            "gallery": {
                "directories": [str(scan_dir)], "output_dir": "output",
                "output_filename": "gallery_output.html", "path_mappings": {},
                "min_size_mb": 0, "default_mode": "image", "default_sort": "date",
                "default_order": "descending", "items_per_page": 90,
            },
            "general": {"theme": "light"},
            "search": {"proxy_url": ""},
        }
        src = types.SimpleNamespace(path=str(scan_dir), readonly=False)
        mock_scanner = MagicMock()
        if extra_nums:
            mock_scanner.scan_file.side_effect = (
                lambda video_path, base_path=None: scan_file_infos[video_path]
            )
        else:
            mock_scanner.scan_file.return_value = info

        with (
            patch("web.routers.scanner.load_config", return_value=config),
            patch("web.routers.scanner.get_gallery_source_paths", return_value=[str(scan_dir)]),
            patch("web.routers.scanner.iter_gallery_sources", return_value=[src]),
            patch("web.routers.scanner.get_db_path", return_value=db_file),
            patch("web.routers.scanner.VideoScanner", return_value=mock_scanner),
            patch("web.routers.scanner.fast_scan_directory", return_value=fast_scan_files),
            patch("web.routers.scanner.HTMLGenerator"),
            patch("web.routers.scanner._run_sample_images_cleanup_pass", return_value=0),
            patch("web.routers.scanner.check_cache_needs_update",
                  return_value={"need_update": 0, "paths": []}),
            patch("web.routers.scanner._emit_notif"),
            patch("core.similar.ranker_cache.SimilarRankerCache"),
            patch("web.routers.scanner.maybe_submit_video_focal") as mock_submit,
        ):
            from web.routers.scanner import generate_avlist
            list(generate_avlist(should_abort=should_abort))
        return mock_submit


    def test_uncensored_nonempty_focal_no_submit(self, tmp_path):
        # empty-focal gate：現有 auto_focal 有值 → 不 submit（mutation：拿掉 gate 必 RED）
        mock_submit = self._run(tmp_path, "SIRO-1234", seed_auto_focal="0.5,0.5")
        mock_submit.assert_not_called()


    def test_existing_unchanged_empty_focal_backfilled(self, tmp_path):
        # Codex PR#105 P2 回歸釘：既有 DB 列、auto_focal=''、mtime 未變（不進
        # needs_scan/videos_to_upsert）、無碼 → 重掃一次仍要被送偵測，否則「重掃一次
        # 自動補焦既有庫」的承諾對這批既有片形同虛設。
        # mutation：focal 來源若改回只迴圈 videos_to_upsert，此列不會被 submit → RED。
        mock_submit = self._run(tmp_path, "SIRO-1234", seed_unchanged=True)
        mock_submit.assert_called_once()
        args = mock_submit.call_args[0]
        assert args[0] == "SIRO-1234"


class TestJellyfinFanartCoverSelfHealRoundTrip:
    """TASK-112-T2c 端到端回歸鎖：DB `cover_path` 指向 `<stem>-fanart.jpg` 的片
    （外部庫掃描 find_cover_image L1.5 命中即如此）。P0-2c 修好後，
    /jellyfin-update 補齊該片時不應留下誤導性的「fanart 複製失敗」SSE 警告
    （fanart == cover 本來就是同一個檔案，內容已經對了），且補完後再
    /jellyfin-check 一次必須回 0（poster 已補齊，fanart 本來就存在）。

    真跑（不 mock check_jellyfin_images_needed / generate_jellyfin_images），
    仿 TestJellyfinUpdateStationWiring._run_station4 的手法：真 DB row +
    真封面檔 + external_manager='jellyfin'（不能是 'off'，會被 CD-111-2 gate 擋掉）。
    """

    @pytest.fixture(autouse=True)
    def reset_jellyfin_cache(self):
        import web.routers.scanner as scanner_mod
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0
        yield
        scanner_mod._jellyfin_cache_result = None
        scanner_mod._jellyfin_cache_time = 0


# ============ feature/122 T5：播放頁多段接續 ============

_ALLOWED_PLAYER_MODULE = (
    '<script type="module" src="/static/js/pages/player.js"></script>'
)


def _seed_player_videos(tmp_path, monkeypatch, filenames, *, dir_name="videos"):
    """真 temp DB + 合成列；get_db_path 指到這份 DB，不碰 owner 片庫。"""
    from core.database import init_db, VideoRepository, Video

    video_dir = tmp_path / dir_name
    video_dir.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "player_t5.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    uris = []
    rows = []
    for name in filenames:
        fs = video_dir / name
        fs.write_bytes(b"\x00fake-mp4\x00")
        uri = to_file_uri(str(fs), {})
        uris.append(uri)
        rows.append(Video(
            path=uri,
            number="ABC-123",
            title=name,
            size_bytes=10,
            mtime=1.0,
        ))
    repo.upsert_batch(rows)
    monkeypatch.setattr("web.routers.gallery_media.get_db_path", lambda: db_path)
    return {"db_path": db_path, "uris": uris, "dir": video_dir}


def _parse_player_video(html: str):
    """HTMLParser 會還原屬性實體，所以 data-parts 拿到的是可 JSON.parse 的字面。"""
    from html.parser import HTMLParser
    import json as json_lib

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.attrs = {}

        def handle_starttag(self, tag, attrs):
            if tag == "video":
                self.attrs = dict(attrs)

    parser = _P()
    parser.feed(html)
    parts = None
    raw = parser.attrs.get("data-parts")
    if raw is not None:
        parts = json_lib.loads(raw)
    return parser.attrs, parts


def _path_from_video_url(url: str) -> str:
    from urllib.parse import unquote

    return unquote(url.split("path=", 1)[1])


class TestVideoPlayerMultipart:
    """TASK-122-T5：多段播放頁 HTML 契約。既有 TestScannerAPI 播放頁測試一字不改。"""

    def test_multipart_data_parts_length_and_order(
        self, client, tmp_path, monkeypatch
    ):
        """多段：data-parts JSON.parse 後長度與順序正確（part-1 在前）。AC-8 HTML 側。"""
        # [lint-guard: pytest-justified] 斷言的是端點 render 出的 HTML 屬性值
        # （data-parts JSON 內容／順序、src=part-1、段落模板、progress 脫離 flex
        # 的 CSS）。static_guard_lint 讀得到 f-string 字面，讀不到「這次請求的
        # 這兩個 DB 列被排成 [cd1, cd2] 寫進屬性」。
        setup = _seed_player_videos(
            tmp_path, monkeypatch,
            ["ABC-123-cd2.mp4", "ABC-123-cd1.mp4"],
        )
        cd1_uri, cd2_uri = setup["uris"][1], setup["uris"][0]
        response = client.get(f"/api/gallery/player?path={quote(cd1_uri)}")
        assert response.status_code == 200
        html = response.text
        attrs, parts = _parse_player_video(html)
        assert parts is not None
        assert len(parts) == 2
        assert _path_from_video_url(parts[0]) == cd1_uri
        assert _path_from_video_url(parts[1]) == cd2_uri
        assert attrs.get("src") == parts[0]
        assert attrs.get("id") == "oa-player"
        assert attrs.get("data-part-label-template") == "第 {current}／{total} 段"
        assert 'id="oa-player-progress"' in html
        assert "position: fixed" in html
        assert "pointer-events: none" in html
        assert "onerror=" in html
        assert 'id="video-error-hint-network"' in html and 'id="video-error-hint-format"' in html


    def test_multipart_data_parts_escaping(self, client, tmp_path, monkeypatch):
        """path 含 \" / & / < / > 時 data-parts 仍是合法屬性，JSON.parse 得回原值。

        mutation-sensitive：把整個 html_escape(...) 呼叫拿掉（只留 json.dumps）
        這支必須轉紅——**實測驗證過**。
        注意不要寫成「拿掉 quote=True 就會轉紅」：`html.escape()` 的簽章本來就是
        `(s, quote=True)`，只刪那個關鍵字參數行為完全不變、測試照樣綠，那是一個
        不會咬人的 mutation（T5 review P3 抓到的措辭失真）。
        """
        # [lint-guard: pytest-justified] XSS 屬性 escaping：斷言特殊字元 path
        # 經 json.dumps + html_escape(quote=True) 後，HTMLParser 還原再
        # JSON.parse 得回原 URI。static_guard_lint 讀得到 quote=True 呼叫，
        # 讀不到「這個 path 在這個請求下真的 round-trip」。
        setup = _seed_player_videos(
            tmp_path, monkeypatch,
            ["ABC-123-cd1.mp4", "ABC-123-cd2.mp4"],
            dir_name='dir"&<>x',
        )
        cd1_uri, cd2_uri = setup["uris"]
        assert any(ch in cd1_uri for ch in '"&<>')
        response = client.get(f"/api/gallery/player?path={quote(cd1_uri)}")
        assert response.status_code == 200
        html = response.text
        assert "&quot;" in html
        attrs, parts = _parse_player_video(html)
        assert parts is not None
        assert len(parts) == 2
        assert _path_from_video_url(parts[0]) == cd1_uri
        assert _path_from_video_url(parts[1]) == cd2_uri
        scanner_src = Path("web/routers/gallery_media.py").read_text(encoding="utf-8")
        assert "html_escape(json.dumps(parts_urls), quote=True)" in scanner_src

    def test_ac16_nontoken_plus_cd2_does_not_continue(
        self, client, tmp_path, monkeypatch
    ):
        """AC-16：同資料夾 ABC-123.mp4（無 token）＋ ABC-123-cd2.mp4 → 不接續。

        mutation-sensitive：把分流條件 len(group.members) > 1 改成 >= 1，這支必須轉紅。
        """
        # [lint-guard: pytest-justified] 斷言 multipart 分支的標記（data-parts /
        # oa-player / player.js）不得出現在 AC-16 反例的 HTML。源碼掃描看不到
        # 「這兩個檔名組合 resolve 成 1-member 之後走了單檔 f-string」。
        setup = _seed_player_videos(
            tmp_path, monkeypatch,
            ["ABC-123.mp4", "ABC-123-cd2.mp4"],
        )
        bare_uri = setup["uris"][0]
        response = client.get(f"/api/gallery/player?path={quote(bare_uri)}")
        assert response.status_code == 200
        html = response.text
        assert "data-parts" not in html
        assert 'id="oa-player"' not in html
        assert "oa-player-progress" not in html
        assert "/static/js/pages/player.js" not in html
        assert "<video controls autoplay src=" in html


class TestGenerateAvlistWishlistReconcile:
    """TASK-141a-T5：掃描完成收尾掛 reconcile_wishlist（DoD 1/3/6）。"""

    def _scan_config(self, scan_dir, output_dir):
        return {
            "gallery": {
                "directories": [str(scan_dir)],
                "output_dir": str(output_dir),
                "path_mappings": {},
                "min_size_mb": 0,
            },
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
            "search": {"proxy_url": ""},
        }

    def _patch_db_paths(self, monkeypatch, db_path):
        monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
        monkeypatch.setattr("core.wishlist_cover_cache.get_db_path", lambda: db_path)

    def test_generate_avlist_reconciles_wishlist_on_completion(
        self, client, tmp_path, monkeypatch, parse_sse_events
    ):
        """DoD 1：書籤有已入手項目 → 完整掃描後恰好一筆 auto_removed 通知，DB 真刪。"""
        import sqlite3
        from core.database import init_db, WishlistRepository, VideoRepository, Video

        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        db_path = tmp_path / "test.db"
        init_db(db_path)

        monkeypatch.setattr(
            "web.routers.scanner.load_config",
            lambda: self._scan_config(scan_dir, output_dir),
        )
        self._patch_db_paths(monkeypatch, db_path)

        number = "OWNED-SCAN-001"
        WishlistRepository().add(number, title="Owned Title")
        VideoRepository().upsert(Video(
            path=to_file_uri(f"/test/{number}.mp4"),
            number=number,
            title="Owned Video",
        ))

        response = client.get("/api/gallery/generate")
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        assert [e for e in events if e.get("type") == "done"], "掃描應正常完成並 yield done"

        notif_items = client.get("/api/notifications").json()["items"]
        auto_removed = [
            i for i in notif_items if i["title_key"] == "notif.wishlist_auto_removed"
        ]
        assert len(auto_removed) == 1, (
            f"掃描完成應對帳並恰好發 1 筆 auto_removed，實得 {[i['title_key'] for i in notif_items]}"
        )
        assert auto_removed[0]["level"] == "info"
        assert auto_removed[0]["task_type"] == "wishlist_reconcile"

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT 1 FROM wishlist WHERE number = ?", (number,)
        ).fetchone()
        conn.close()
        assert row is None, "已入手書籤應被對帳刪除"


