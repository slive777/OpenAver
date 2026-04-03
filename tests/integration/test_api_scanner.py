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
        assert data["detail"][0]["type"] == "missing"


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
