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
        
    def test_get_player_success(self, client):
        """測試 /api/gallery/player 回傳正確的 HTML"""
        video_path = "file:///C:/videos/test.mp4"
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
            id=1, path='file:///video/SONE-100.mp4', title='DB Title',
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
        assert data['error'] == '檢查 Jellyfin 圖片狀態失敗'

    def test_jellyfin_check_uses_to_thread(self):
        """靜態掃描確認 scanner.py 使用 asyncio.to_thread 包裝同步呼叫"""
        import pathlib
        scanner_src = (pathlib.Path(__file__).parents[2] / 'web' / 'routers' / 'scanner.py').read_text(encoding='utf-8')
        assert 'asyncio.to_thread(check_jellyfin_images_needed' in scanner_src

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
        for v in videos:
            repo.upsert(v)
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
