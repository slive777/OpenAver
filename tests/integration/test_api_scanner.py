import pytest
import os
from pathlib import Path
from urllib.parse import quote
from core.path_utils import to_file_uri

class TestScannerAPI:
    """測試 scanner.py 相關 endpoints"""

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
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)
        
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
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)
        
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
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)
        
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
        monkeypatch.setattr('web.routers.scanner.load_config', lambda: test_config)

        path_arg = to_file_uri(r'\\DiskStation\usbshare1\a.mp4')

        with patch('os.path.realpath', return_value=r'\\?\UNC\DiskStation\usbshare1\a.mp4'), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024), \
             patch('web.routers.scanner.FileResponse',
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
        monkeypatch.setattr('web.routers.scanner.load_config', lambda: test_config)

        path_arg = to_file_uri(r'\\AnotherNAS\evil\a.mp4')

        with patch('os.path.realpath', return_value=r'\\AnotherNAS\evil\a.mp4'), \
             patch('os.path.exists', return_value=True):
            response = client.get(f'/api/gallery/video?path={quote(path_arg)}')

        assert response.status_code == 403

    def test_get_video_output_path_not_allowed(self, client, tmp_path, monkeypatch):
        """TASK-88c-T1 回歸鎖：唯讀來源 output_path 底下的影片 → /api/gallery/video 仍 403

        證明 get_video call site 未被 88c-T1 波及（get_image 開放 output_path、
        get_video 刻意不對稱，spec P1a 明令）。
        """
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        video_file = out_dir / "test.mp4"
        video_file.write_bytes(b'fake_video_content')

        test_config = {
            "gallery": {
                "directories": [
                    {"path": str(src_dir), "readonly": True, "output_path": str(out_dir)},
                ],
                "path_mappings": {},
            },
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)

        path_arg = to_file_uri(str(video_file))
        response = client.get(f"/api/gallery/video?path={quote(path_arg)}")

        assert response.status_code == 403
        assert "不在允許的資料夾範圍內" in response.text

    def test_get_player_success(self, client):
        """測試 /api/gallery/player 回傳正確的 HTML"""
        video_path = to_file_uri("C:/videos/test.mp4")
        response = client.get(f"/api/gallery/player?path={quote(video_path)}")

        assert response.status_code == 200
        assert "<video" in response.text
        assert "test.mp4" in response.text
        assert 'src="/api/gallery/video?path=' in response.text
        assert '%2Fvideos%2Ftest.mp4"' in response.text

    def test_player_missing_path(self, client):
        """測試 /api/gallery/player 缺少 path 參數應返回 422"""
        response = client.get("/api/gallery/player")
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "validation_error"


# ============ POST /api/gallery/generate-from-ids ============

class TestGenerateFromIds:
    """測試 POST /api/gallery/generate-from-ids"""

    def test_empty_numbers_returns_400(self, client, monkeypatch):
        """空 numbers → 400"""
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {}, "general": {}
        })
        response = client.post('/api/gallery/generate-from-ids', json={'numbers': []})
        assert response.status_code == 400

    def test_over_100_numbers_returns_422(self, client, monkeypatch):
        """超過 100 筆 → 422"""
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {}, "general": {}
        })
        numbers = [f'SONE-{i:03d}' for i in range(101)]
        response = client.post('/api/gallery/generate-from-ids', json={'numbers': numbers})
        assert response.status_code == 422

    def test_invalid_mode_returns_422(self, client, monkeypatch):
        """mode 不在 enum → 422"""
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {}, "general": {}
        })
        response = client.post('/api/gallery/generate-from-ids', json={
            'numbers': ['SONE-100'],
            'mode': 'invalid_mode'
        })
        assert response.status_code == 422

    def test_invalid_sort_returns_422(self, client, monkeypatch):
        """sort 不在 enum → 422"""
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {}, "general": {}
        })
        response = client.post('/api/gallery/generate-from-ids', json={
            'numbers': ['SONE-100'],
            'sort': 'invalid_sort'
        })
        assert response.status_code == 422

    def test_db_hit_no_scrape(self, client, monkeypatch, tmp_path):
        """DB 有資料時不走 scraper"""
        from unittest.mock import MagicMock, patch
        from core.database import Video
        from core.gallery_scanner import VideoInfo

        video = Video(
            id=1, path=to_file_uri('/video/SONE-100.mp4'), title='DB Title',
            original_title='', actresses=[], number='SONE-100',
            maker='Sony', release_date='2026-01-01', tags=[],
            size_bytes=1000, mtime=0.0, cover_path='', nfo_mtime=None,
            director='', duration=None, series='', label=''
        )

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {'SONE-100': [video]}

        mock_generator = MagicMock()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(output_dir), "path_mappings": {}},
            "general": {"theme": "light"}
        })

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[]) as mock_scrape:
            response = client.post('/api/gallery/generate-from-ids', json={'numbers': ['SONE-100']})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['video_count'] == 1
        assert data['missing'] == []
        mock_scrape.assert_not_called()

    def test_db_miss_triggers_scraper(self, client, monkeypatch, tmp_path):
        """DB 無資料時走 scraper"""
        from unittest.mock import MagicMock, patch

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}  # DB miss

        mock_generator = MagicMock()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(output_dir), "path_mappings": {}},
            "general": {"theme": "light"}
        })

        scraper_result = {'number': 'SONE-100', 'title': 'Scraped Title', 'date': '2026-01-01'}

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[scraper_result]) as mock_scrape:
            response = client.post('/api/gallery/generate-from-ids', json={'numbers': ['SONE-100']})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['video_count'] == 1
        assert data['missing'] == []
        mock_scrape.assert_called_once()

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

    def test_response_structure(self, client, monkeypatch, tmp_path):
        """回傳結構符合規範"""
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
        assert 'success' in data
        assert 'html_path' in data
        assert 'video_count' in data
        assert 'missing' in data


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

    def test_jellyfin_check_no_db(self, client, monkeypatch):
        """DB 不存在時，回傳 need_update: 0，不呼叫 check_jellyfin_images_needed"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = False

        mock_check = MagicMock()

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.check_jellyfin_images_needed', mock_check):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 0
        mock_check.assert_not_called()

    def test_jellyfin_check_has_updates(self, client, monkeypatch):
        """DB 存在，check_jellyfin_images_needed 回傳 need_update: 5"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        mock_repo = MagicMock()
        check_result = {'need_update': 5, 'items': [{'cover_path': f'/a/{i}.jpg', 'base_stem': f'/a/{i}', 'number': f'SONE-{i:03d}'} for i in range(5)]}

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', return_value=check_result):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 5

    def test_jellyfin_check_no_updates(self, client, monkeypatch):
        """DB 存在，check_jellyfin_images_needed 回傳 need_update: 0"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        mock_repo = MagicMock()
        check_result = {'need_update': 0, 'items': []}

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', return_value=check_result):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 0

    def test_jellyfin_check_exception(self, client, monkeypatch):
        """check_jellyfin_images_needed 拋出例外時，回傳 success: false，HTTP 200"""
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        mock_repo = MagicMock()

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', side_effect=RuntimeError('IO error')):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert 'error' in data
        assert data['error'] == '檢查圖片狀態失敗'

    def test_jellyfin_check_uses_to_thread(self):
        """靜態掃描確認 scanner.py 使用 asyncio.to_thread 包裝 _check_jellyfin_needed helper，
        且 helper 內含 db_path.exists、VideoRepository、check_jellyfin_images_needed"""
        import pathlib
        scanner_src = (pathlib.Path(__file__).parents[2] / 'web' / 'routers' / 'scanner.py').read_text(encoding='utf-8')
        # helper 函式透過 to_thread 包裝
        assert 'asyncio.to_thread(_check_jellyfin_needed' in scanner_src
        # helper 函式 body 包含三個被 offload 的呼叫
        assert 'def _check_jellyfin_needed(' in scanner_src
        assert 'db_path.exists()' in scanner_src
        assert 'VideoRepository(db_path)' in scanner_src
        assert 'check_jellyfin_images_needed(repo)' in scanner_src

    # ---- T3(40c): TTL 快取相關測試 ----

    def test_jellyfin_check_cache_hit(self, client, monkeypatch):
        """TTL 內命中快取，check_jellyfin_images_needed 不被呼叫"""
        import time
        import web.routers.scanner as scanner_mod
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        # 注入有效快取（10 秒前寫入，TTL=60 秒未到期）
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_result', {'need_update': 7, 'items': []})
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_time', time.time() - 10)

        mock_check = MagicMock()

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.check_jellyfin_images_needed', mock_check):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 7
        mock_check.assert_not_called()

    def test_jellyfin_check_cache_expired(self, client, monkeypatch):
        """TTL 過期（> 60s）後重新呼叫 check_jellyfin_images_needed"""
        import time
        import web.routers.scanner as scanner_mod
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = True

        mock_repo = MagicMock()

        # 注入過期快取（61 秒前寫入）
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_result', {'need_update': 3, 'items': []})
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_time', time.time() - 61)

        new_result = {'need_update': 99, 'items': []}

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path), \
             patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.check_jellyfin_images_needed', return_value=new_result) as mock_check:
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 99
        mock_check.assert_called_once()

    def test_jellyfin_check_no_db_no_cache_write(self, client, monkeypatch):
        """DB 不存在時 early-return，不更新快取"""
        import web.routers.scanner as scanner_mod
        from unittest.mock import MagicMock, patch

        mock_db_path = MagicMock()
        mock_db_path.exists.return_value = False

        # 確保快取為 None
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_result', None)
        monkeypatch.setattr(scanner_mod, '_jellyfin_cache_time', 0)

        with patch('web.routers.scanner.get_db_path', return_value=mock_db_path):
            response = client.get('/api/gallery/jellyfin-check')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data']['need_update'] == 0
        # DB 不存在時不寫入快取
        assert scanner_mod._jellyfin_cache_result is None

    def test_jellyfin_cache_cleared_after_update_static(self):
        """靜態掃描確認 generate_jellyfin_images_stream 在 done 路徑清空快取"""
        import pathlib
        scanner_src = (pathlib.Path(__file__).parents[2] / 'web' / 'routers' / 'scanner.py').read_text(encoding='utf-8')
        assert '_jellyfin_cache_result = None' in scanner_src

    def test_jellyfin_cache_cleared_after_clear_cache_static(self):
        """靜態掃描確認 clear_cache 中有清空 _jellyfin_cache_result"""
        import pathlib
        scanner_src = (pathlib.Path(__file__).parents[2] / 'web' / 'routers' / 'scanner.py').read_text(encoding='utf-8')
        # 確認 clear_cache 和 generate_jellyfin_images_stream 兩個函數都有清空快取的程式碼
        assert scanner_src.count('_jellyfin_cache_result = None') >= 2

    def test_jellyfin_cache_cleared_after_generate_avlist_static(self):
        """T3(40c) Codex fix: 靜態掃描確認 generate_avlist 正常和例外路徑都清空 jellyfin 快取"""
        import pathlib
        scanner_src = (pathlib.Path(__file__).parents[2] / 'web' / 'routers' / 'scanner.py').read_text(encoding='utf-8')
        # T3(40c) Codex fix 後應有 4 處：
        #   clear_cache + generate_jellyfin_images_stream + generate_avlist(done) + generate_avlist(except)
        assert scanner_src.count('_jellyfin_cache_result = None') >= 4


class TestMissingCheckAPI:
    """T10 — 測試 GET /api/gallery/missing-check 端點"""

    def _make_db(self, tmp_path, videos):
        """建立測試用 SQLite DB，插入指定影片資料"""
        from core.database import init_db, VideoRepository, Video
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        # 單一 transaction 批次插入（避免 5000 筆各開一次交易拖慢測試）
        repo.upsert_batch(videos)
        return db_path

    def test_db_not_exist_returns_zero(self, client, tmp_path, monkeypatch):
        """DB 不存在時回 {success: true, data: {total_missing: 0, items: []}}"""
        from unittest.mock import patch
        missing_path = tmp_path / "nonexistent.db"
        with patch('web.routers.scanner.get_db_path', return_value=missing_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 0
        assert data['data']['items'] == []

    def test_all_complete_returns_zero(self, client, tmp_path, monkeypatch):
        """所有影片均有 NFO + 封面時，total_missing = 0"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="/covers/a.jpg", nfo_mtime=1234567890.0),
            Video(path=to_file_uri(str(tmp_path / "b.mp4")), number="BBB-002",
                  cover_path="/covers/b.jpg", nfo_mtime=1234567891.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 0
        assert data['data']['missing_both'] == 0
        assert data['data']['missing_nfo'] == 0
        assert data['data']['missing_cover'] == 0
        assert data['data']['items'] == []

    def test_missing_both_counted(self, client, tmp_path, monkeypatch):
        """cover_path='' 且 nfo_mtime=0 的影片計入 missing_both"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['success'] is True
        assert data['data']['missing_both'] == 1
        assert data['data']['missing_nfo'] == 0
        assert data['data']['missing_cover'] == 0
        assert data['data']['total_missing'] == 1
        assert len(data['data']['items']) == 1
        assert data['data']['items'][0]['number'] == 'AAA-001'

    def test_missing_nfo_only_counted(self, client, tmp_path, monkeypatch):
        """nfo_mtime=0 但有封面 → 計入 missing_nfo"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="/covers/a.jpg", nfo_mtime=0.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['data']['missing_nfo'] == 1
        assert data['data']['missing_both'] == 0
        assert data['data']['missing_cover'] == 0
        assert data['data']['total_missing'] == 1

    def test_missing_cover_only_counted(self, client, tmp_path, monkeypatch):
        """cover_path='' 但有 NFO → 計入 missing_cover"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=1234567890.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['data']['missing_cover'] == 1
        assert data['data']['missing_both'] == 0
        assert data['data']['missing_nfo'] == 0
        assert data['data']['total_missing'] == 1

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

    def test_null_number_excluded(self, client, tmp_path, monkeypatch):
        """number IS NULL 的記錄不計入 items（無法補完）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number=None,
                  cover_path="", nfo_mtime=0.0),
            Video(path=to_file_uri(str(tmp_path / "b.mp4")), number="BBB-002",
                  cover_path="", nfo_mtime=0.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['data']['total_missing'] == 1
        assert len(data['data']['items']) == 1
        assert data['data']['items'][0]['number'] == 'BBB-002'

    def test_response_includes_file_path(self, client, tmp_path, monkeypatch):
        """items 的每個元素包含 file_path 和 number"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        video_uri = to_file_uri(str(tmp_path / "a.mp4"))
        videos = [
            Video(path=video_uri, number="AAA-001",
                  cover_path="", nfo_mtime=0.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        item = data['data']['items'][0]
        assert 'file_path' in item
        assert 'number' in item
        assert item['number'] == 'AAA-001'

    def test_exactly_500_returns_full_items(self, client, tmp_path, monkeypatch):
        """total_missing == 500（邊界，剛好不超過舊 cap）→ items 為完整 list"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / f"v{i:04d}.mp4")),
                  number=f"AAA-{i:04d}",
                  cover_path="", nfo_mtime=0.0)
            for i in range(500)
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 500
        assert data['data']['items'] is not None
        assert isinstance(data['data']['items'], list)
        assert len(data['data']['items']) == 500

    def test_exactly_501_returns_full_items(self, client, tmp_path, monkeypatch):
        """total_missing == 501（邊界，剛好超過舊 cap）→ items 為完整 list（非 None）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / f"v{i:04d}.mp4")),
                  number=f"AAA-{i:04d}",
                  cover_path="", nfo_mtime=0.0)
            for i in range(501)
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 501
        assert data['data']['items'] is not None
        assert isinstance(data['data']['items'], list)
        assert len(data['data']['items']) == 501

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

    def test_over_5000_returns_full_items(self, client, tmp_path, monkeypatch):
        """total_missing > 5000（大批量）→ items 為完整 list"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / f"v{i:05d}.mp4")),
                  number=f"AAA-{i:05d}",
                  cover_path="", nfo_mtime=0.0)
            for i in range(5000)
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['data']['total_missing'] == 5000
        assert data['data']['items'] is not None
        assert isinstance(data['data']['items'], list)
        assert len(data['data']['items']) == 5000

    def test_producer_row_excluded_from_buckets(self, client, tmp_path, monkeypatch):
        """producer 產出的 row（output_dir!=''，nfo_mtime 恆 0）不進任何桶、不計入 total_missing（TASK-89b-T4）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0,
                  output_dir=to_file_uri(str(tmp_path / "out"))),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['success'] is True
        assert data['data']['missing_both'] == 0
        assert data['data']['missing_nfo'] == 0
        assert data['data']['missing_cover'] == 0
        assert data['data']['total_missing'] == 0
        assert data['data']['items'] == []

    def test_tried_non_producer_row_excluded_from_buckets(self, client, tmp_path, monkeypatch):
        """scrape_attempted_at>0 但非 producer（output_dir==''）同樣被排除（一般 NOT-FOUND 記憶場景，TASK-89b-T4）"""
        from unittest.mock import patch
        from core.database import Video
        from core.path_utils import to_file_uri
        videos = [
            Video(path=to_file_uri(str(tmp_path / "a.mp4")), number="AAA-001",
                  cover_path="", nfo_mtime=0.0,
                  scrape_attempted_at=1234567890.0),
        ]
        db_path = self._make_db(tmp_path, videos)
        with patch('web.routers.scanner.get_db_path', return_value=db_path):
            resp = client.get('/api/gallery/missing-check')
        data = resp.json()
        assert data['success'] is True
        assert data['data']['missing_both'] == 0
        assert data['data']['total_missing'] == 0
        assert data['data']['items'] == []

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

    def test_done_event_has_long_paths_key(self, client, tmp_path, monkeypatch, parse_sse_events):
        """
        SSE done event payload 必須含 long_paths 欄位（即使平台非 win32 也應為 [] 而非缺 key）。
        用空資料夾讓掃描快速結束，重點驗證 payload 結構，不驗證內容。
        """
        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock config — 單一空目錄，掃完即 done
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

        response = client.get('/api/gallery/generate')
        assert response.status_code == 200

        events = parse_sse_events(response.text)
        done_events = [e for e in events if e.get('type') == 'done']
        assert done_events, "SSE stream 未收到 done event"

        done_payload = done_events[-1]
        assert 'long_paths' in done_payload, (
            "done SSE payload 缺少 long_paths 欄位"
            "（實作可能漏掉 long_paths 參數或未抽 module-level helper）"
        )
        assert isinstance(done_payload['long_paths'], list), \
            "long_paths 應為 list 型別"
        # 非 win32 平台（CI / 開發機多為 linux）應為空 list
        # win32 平台上空目錄也應為空 list
        assert done_payload['long_paths'] == [], \
            "空目錄 / 非 win32 平台下 long_paths 應為 []"

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

    def test_generate_avlist_calls_cleanup_pass(self, client, tmp_path, monkeypatch):
        """呼叫 /api/gallery/generate 後，_run_sample_images_cleanup_pass 應被執行。
        用 mock 確認 helper 有被呼叫（驗行為，不驗 DB 狀態，避免過重 fixture）。
        """
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        scan_dir = tmp_path / "videos"
        scan_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock config
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

        # 驗證 _run_sample_images_cleanup_pass 被呼叫
        with patch(
            "web.routers.scanner._run_sample_images_cleanup_pass",
            return_value=0,
        ) as mock_cleanup:
            response = client.get('/api/gallery/generate')

        assert response.status_code == 200
        mock_cleanup.assert_called_once(), (
            "_run_sample_images_cleanup_pass 應在 generate_avlist() 中被呼叫一次。"
            "若未呼叫，Scanner UI 主路徑不會清孤兒（Canonical Decision #4 雙流程覆蓋未達成）"
        )


class TestClearCacheThumbnailInvalidation:
    """feature/71 T8 邊界1：clear_cache → thumbnail_cache.clear_all() 連動清整個 thumb/。"""

    def test_clear_cache_calls_clear_all(self, client, tmp_path, mocker):
        """DB 存在 → repo.clear_all() 後 thumbnail_cache.clear_all() 被呼叫一次；回應正常。"""
        from core.database import init_db
        db_path = tmp_path / "test.db"
        init_db(db_path)
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)

        clear_all_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.clear_all"
        )

        resp = client.delete("/api/gallery/cache")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        clear_all_spy.assert_called_once()

    def test_clear_cache_db_missing_does_not_call_clear_all(self, client, tmp_path, mocker):
        """DB 不存在（早退）→ clear_all 不被呼叫（放在 repo.clear_all() 之後）。"""
        missing = tmp_path / "nonexistent.db"
        mocker.patch("web.routers.scanner.get_db_path", return_value=missing)

        clear_all_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.clear_all"
        )

        resp = client.delete("/api/gallery/cache")

        assert resp.status_code == 200
        clear_all_spy.assert_not_called()


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

    def _readonly_config(self, tmp_path, sources, proxy_url="http://proxy:8080"):
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
            "search": {"proxy_url": proxy_url},
            "general": {"theme": "light"},
            "scraper": {"video_extensions": [".mp4"]},
        }

    def _result(self, tmp_path, **kw):
        from core.readonly_producer import ProduceResult
        out = str(tmp_path / "out")
        return ProduceResult(source_path=str(tmp_path / "src0"), output_path=out, **kw)

    # 1. 分流互斥（正向）：readonly → produce_source 呼叫一次，args + proxy_url kwarg 正確
    def test_readonly_source_calls_produce_source_once(self, client, tmp_path, monkeypatch, mocker):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
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
        # proxy_url kwarg 正確傳入
        assert call.kwargs["proxy_url"] == "http://proxy:8080"
        assert call.kwargs["should_abort"] is None

    # 2. 分流互斥（反向）：非 readonly → produce_source 未被呼叫
    def test_non_readonly_does_not_call_produce_source(self, client, tmp_path, monkeypatch, mocker):
        cfg = self._readonly_config(tmp_path, [(False, "")])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mock_ps = mocker.patch("web.routers.scanner.produce_source")
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        mock_ps.assert_not_called()

    # 3. SSE 逐片橋接：on_progress 連發 3 outcome → SSE 出 3 條對應 log；sentinel 後續下一來源
    def test_sse_per_outcome_streaming(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        from core.readonly_producer import ProduceOutcome
        cfg = self._readonly_config(tmp_path, [
            (True, str(tmp_path / "out0")),
            (True, str(tmp_path / "out1")),
        ])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)

        def side_effect(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None, force=False, reachable=True):
            from core.readonly_producer import ProduceResult
            if source.path == str(tmp_path / "src0"):
                on_progress(ProduceOutcome(source_uri="uri1", status="created", number="ABC-001"))
                on_progress(ProduceOutcome(source_uri="uri2", status="skipped", number="ABC-002"))
                on_progress(ProduceOutcome(source_uri="uri3", status="failed", number="ABC-003", error="生成失敗"))
                return ProduceResult(source_path=source.path, output_path=source.output_path,
                                     created=1, skipped=1, failed=1)
            return ProduceResult(source_path=source.path, output_path=source.output_path)

        mock_ps = mocker.patch("web.routers.scanner.produce_source", side_effect=side_effect)
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        msgs = [e.get("message", "") for e in events if e.get("type") == "log"]
        assert any("✓ 生成" in m and "ABC-001" in m for m in msgs)
        assert any("略過" in m and "ABC-002" in m for m in msgs)
        assert any("✗ 失敗" in m and "ABC-003" in m for m in msgs)
        # 第 2 來源也被處理（sentinel 後迴圈續跑）
        assert mock_ps.call_count == 2

    # 4. 四數摘要累計
    def test_four_number_summary(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.produce_source",
                     return_value=self._result(tmp_path, created=2, skipped=1, no_scrape=1, failed=1))
        resp = client.get("/api/gallery/generate")
        events = parse_sse_events(resp.text)
        done = [e for e in events if e.get("type") == "done"][-1]
        rs = done["readonly_stats"]
        assert rs["created"] == 2 and rs["skipped"] == 1
        assert rs["no_scrape"] == 1 and rs["failed"] == 1
        assert rs["sources"] == 1
        # 該來源小結四數皆出現
        msgs = [e.get("message", "") for e in events if e.get("type") == "log"]
        assert any("新增 2" in m and "略過 1" in m and "刮不到 1" in m and "失敗 1" in m for m in msgs)

    # 5. no_output_path 提示
    def test_no_output_path_prompt(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        cfg = self._readonly_config(tmp_path, [(True, "")])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.produce_source",
                     return_value=self._result(tmp_path, aborted_reason="no_output_path"))
        resp = client.get("/api/gallery/generate")
        events = parse_sse_events(resp.text)
        msgs = [e.get("message", "") for e in events if e.get("type") == "log"]
        assert any("請先設定輸出夾" in m for m in msgs)
        done = [e for e in events if e.get("type") == "done"][-1]
        rs = done["readonly_stats"]
        assert rs["no_output"] == 1
        assert rs["created"] == 0 and rs["skipped"] == 0
        assert rs["no_scrape"] == 0 and rs["failed"] == 0
        assert rs["sources"] == 0

    # 6. CRITICAL：source-level 例外傳遞 + 續跑
    def test_source_level_exception_continues(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        from core.readonly_producer import ProduceResult
        cfg = self._readonly_config(tmp_path, [
            (True, str(tmp_path / "out0")),
            (True, str(tmp_path / "out1")),
        ])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)

        def side_effect(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None, force=False, reachable=True):
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
    def test_cross_thread_db_write(self, client, tmp_path, monkeypatch, mocker, parse_sse_events):
        from core.database import init_db, VideoRepository, Video
        from core.readonly_producer import ProduceResult
        db_path = tmp_path / "test.db"
        init_db(db_path)
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)

        written_uri = to_file_uri(str(tmp_path / "src0" / "worker_written.mp4"))

        def side_effect(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None, force=False, reachable=True):
            # 在 worker frame 用傳入的 repo 寫一筆（per-call 連線）
            repo.upsert(Video(path=written_uri, number="WK-001", title="worker",
                              mtime=1.0, nfo_mtime=0.0))
            return ProduceResult(source_path=source.path, output_path=source.output_path, created=1)

        mocker.patch("web.routers.scanner.produce_source", side_effect=side_effect)
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        assert [e for e in events if e.get("type") == "done"], "未收到 done event"
        # 無 ProgrammingError → 寫入成功
        check = VideoRepository(db_path)
        assert written_uri in check.get_mtime_index()

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
        mock_ps = mocker.patch("web.routers.scanner.produce_source",
                               return_value=ProduceResult(source_path=unc, output_path=str(tmp_path / "out0")))
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        assert mock_ps.call_count == 1
        assert mock_ps.call_args.args[0].path == unc

    # 10. 88c-P2：來源級失敗 → 完成通知走 warn（非純 success）
    def test_source_level_failure_completion_notif_is_warn(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        """readonly 來源整源拋錯（source_errors>0）→ 最終完成通知必須是 warn/
        scanner_done_with_errors，不可 success/scanner_done（Codex P2）。"""
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch("web.routers.scanner.produce_source",
                     side_effect=ValueError("boom（迴圈前逃出）"))
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        # drain SSE 讓 generator 跑完（完成通知在 done 之前 emit）
        parse_sse_events(resp.text)

        # 完成通知（scanner_generate task_type，排除 scanner_started）
        completion_calls = [
            c for c in mock_notif.call_args_list
            if c.kwargs.get("task_type") == "scanner_generate"
            and c.args and c.args[1] != "notif.scanner_started"
        ]
        assert completion_calls, "未發出完成通知"
        final = completion_calls[-1]
        assert final.args[0] == "warn", f"完成通知應為 warn，實得 {final.args[0]}"
        assert final.args[1] == "notif.scanner_done_with_errors"
        assert "來源失敗" in final.kwargs.get("message", "")

    # 11. PR#91 ②：個別影片失敗（readonly failed>0, source_errors=0）→ 完成通知走 warn
    def test_per_video_failure_completion_notif_is_warn(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        """produce_source 未拋錯（source_errors=0）但回傳 failed>0（例如 NFO 寫入失敗）
        → 完成通知仍須 warn/scanner_done_with_errors，不可純 success（PR#91 ②）。
        no fix → failed-only 的完成通知會報 success，本測試 RED。"""
        from core.readonly_producer import ProduceResult
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch(
            "web.routers.scanner.produce_source",
            return_value=ProduceResult(
                source_path=str(tmp_path / "src0"),
                output_path=str(tmp_path / "out0"),
                created=1, failed=2,
            ),
        )
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        # readonly_stats 帶 failed=2、source_errors=0
        done = [e for e in events if e.get("type") == "done"][-1]
        assert done["readonly_stats"]["failed"] == 2
        assert done["readonly_stats"]["source_errors"] == 0

        completion_calls = [
            c for c in mock_notif.call_args_list
            if c.kwargs.get("task_type") == "scanner_generate"
            and c.args and c.args[1] != "notif.scanner_started"
        ]
        assert completion_calls, "未發出完成通知"
        final = completion_calls[-1]
        assert final.args[0] == "warn", f"完成通知應為 warn，實得 {final.args[0]}"
        assert final.args[1] == "notif.scanner_done_with_errors"
        assert "2 部失敗" in final.kwargs.get("message", "")

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
    def test_pruned_count_reaches_done_sse_readonly_stats(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch(
            "web.routers.scanner.produce_source",
            return_value=self._result(tmp_path, created=1, pruned=3),
        )
        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        done = [e for e in events if e.get("type") == "done"][-1]
        assert done["readonly_stats"]["pruned"] == 3

    # 13. Finding-2 情境一：來源不可達 → per-source warn SSE + unreachable 計數 +
    #     完成通知 warn（非 success）
    def test_unreachable_source_warns_and_completion_is_warn(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
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
    def test_partial_scan_warns_and_completion_is_warn(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        cfg = self._readonly_config(tmp_path, [(True, str(tmp_path / "out0"))])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch(
            "web.routers.scanner.produce_source",
            return_value=self._result(
                tmp_path, created=1, skipped_paths=["/src0/broken_dir"],
            ),
        )
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        # 正常小結仍要 yield（info），另外追加一則「已略過刪除偵測」warn
        warn_logs = [
            e for e in events
            if e.get("type") == "log" and e.get("level") == "warn"
            and "已略過刪除偵測" in e.get("message", "")
        ]
        assert warn_logs, "partial-scan 應追加一則含「已略過刪除偵測」的 warn SSE"

        done = [e for e in events if e.get("type") == "done"][-1]
        assert done["readonly_stats"]["partial"] == 1

        final = self._completion_calls(mock_notif)[-1]
        assert final.args[0] == "warn", f"完成通知應為 warn，實得 {final.args[0]}"
        assert "部分讀取失敗" in final.kwargs.get("message", "")

    # 15. Finding-2 情境三：no_output>0（原本已計數但完成通知未讀）→ 完成通知 warn
    def test_no_output_completion_is_warn_not_success(
        self, client, tmp_path, monkeypatch, mocker, parse_sse_events
    ):
        cfg = self._readonly_config(tmp_path, [(True, "")])
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
        mocker.patch(
            "web.routers.scanner.produce_source",
            return_value=self._result(tmp_path, aborted_reason="no_output_path"),
        )
        mock_notif = mocker.patch("web.routers.scanner._emit_notif")

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        parse_sse_events(resp.text)

        final = self._completion_calls(mock_notif)[-1]
        assert final.args[0] == "warn", f"完成通知應為 warn，實得 {final.args[0]}"
        assert final.args[1] == "notif.scanner_done_with_errors"
        assert "未設輸出夾" in final.kwargs.get("message", "")

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

    def test_delete_by_paths_only_removes_db_row_not_output_files(
        self, client, tmp_path, monkeypatch, parse_sse_events
    ):
        """輸出夾檔案（nfo/封面/資料夾）在 prune 前後必須 exists() 不變——DB-row-only。"""
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri

        src_a = tmp_path / "srcA"
        src_a.mkdir()
        output_dir = tmp_path / "html_out"
        output_dir.mkdir()
        out_a = tmp_path / "outA"

        # 模擬既有輸出夾產物：資料夾 + nfo + 封面
        produced_dir = out_a / "GONE-001"
        produced_dir.mkdir(parents=True)
        nfo_file = produced_dir / "GONE-001.nfo"
        nfo_file.write_text("<movie></movie>", encoding="utf-8")
        cover_file = produced_dir / "poster.jpg"
        cover_file.write_bytes(b"\xff\xd8\xff")

        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        gone_uri = to_file_uri(str(src_a / "gone.mp4"))
        repo.upsert(Video(
            path=gone_uri, number="GONE-001", title="已消失但輸出夾仍在",
            mtime=1.0, nfo_mtime=0.0, output_dir=str(produced_dir),
        ))
        kept_fs = str(src_a / "kept.mp4")

        cfg = {
            "gallery": {
                "directories": [
                    {"path": str(src_a), "readonly": True, "output_path": str(out_a)},
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
            # gone.mp4 不再出現，但列表非空（有 kept.mp4）→ gate 通過，觸發 prune
            return [{"path": kept_fs, "size": 1024, "mtime": 2.0}]

        monkeypatch.setattr("core.readonly_producer.fast_scan_directory", stub_fast_scan)
        monkeypatch.setattr("core.readonly_producer.extract_number", lambda basename: None)

        resp = client.get("/api/gallery/generate")
        assert resp.status_code == 200
        parse_sse_events(resp.text)

        # DB row 已刪
        assert gone_uri not in repo.get_mtime_index()
        # 輸出夾檔案完全不動
        assert produced_dir.exists()
        assert nfo_file.exists()
        assert cover_file.exists()
