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
