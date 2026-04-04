"""
test_api_gallery.py - 畫廊 API 整合測試

測試圖片代理、NFO 更新等 Gallery API 端點。
"""

import pytest
import os
import tempfile
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch


# ============ 圖片代理測試 ============

class TestImageProxy:
    """測試圖片代理 API /api/gallery/image"""

    def test_image_proxy_local_file(self, client, tmp_path, mocker):
        """本地圖片檔案代理"""
        # 建立測試圖片
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)  # JPEG magic bytes

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'

    def test_image_proxy_png(self, client, tmp_path, mocker):
        """PNG 圖片代理"""
        test_image = tmp_path / "test.png"
        # PNG magic bytes
        test_image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

    def test_image_proxy_not_found(self, client, tmp_path, mocker):
        """圖片不存在應返回 404（路徑在白名單內但檔案不存在）"""
        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(tmp_path / 'nonexistent.jpg')})

        assert response.status_code == 404

    def test_image_proxy_webp(self, client, tmp_path, mocker):
        """WebP 圖片代理"""
        test_image = tmp_path / "test.webp"
        # WebP magic bytes (RIFF....WEBP)
        test_image.write_bytes(b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 100)

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/webp'


class TestImageProxyPathConversion:
    """測試圖片代理路徑轉換"""

    def test_unix_path(self, client, tmp_path, mocker):
        """Unix 風格路徑"""
        test_image = tmp_path / "unix_test.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)

        unix_path = str(test_image)  # 已經是 Unix 風格

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': unix_path})

        assert response.status_code == 200

    def test_url_encoded_path(self, client, tmp_path, mocker):
        """URL 編碼路徑"""
        test_image = tmp_path / "test image.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)

        from urllib.parse import quote
        encoded_path = quote(str(test_image))

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': encoded_path})

        assert response.status_code == 200


# ============ Gallery Stats 測試 ============

class TestGalleryStats:
    """測試 Gallery 統計 API"""

    def test_get_stats_success(self, client):
        """Stats 端點正常返回"""
        response = client.get('/api/gallery/stats')

        assert response.status_code == 200
        data = response.json()
        # 實際 API 返回 {success: True, data: {...}}
        assert 'success' in data or 'data' in data or 'total' in data


# ============ 清除快取測試 ============

class TestClearCache:
    """測試 DELETE /api/gallery/cache"""

    def test_clear_cache_no_db(self, client, mocker):
        """DB 不存在時應回傳 deleted=0"""
        mocker.patch('web.routers.scanner.get_db_path',
                      return_value=Path('/nonexistent/openaver.db'))
        response = client.delete('/api/gallery/cache')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['deleted'] == 0

    def test_clear_cache_success(self, client, tmp_path, mocker):
        """有資料時應清除並回傳刪除數量"""
        from core.database import init_db, VideoRepository, Video
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([
            Video(path="file:///v1.mp4", mtime=100.0),
            Video(path="file:///v2.mp4", mtime=200.0),
        ])
        mocker.patch('web.routers.scanner.get_db_path', return_value=db_path)

        response = client.delete('/api/gallery/cache')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['deleted'] == 2
        assert repo.count() == 0

    def test_clear_cache_error_no_leak(self, client, mocker):
        """例外時不外洩內部資訊"""
        mocker.patch('web.routers.scanner.get_db_path',
                      side_effect=RuntimeError('/secret/path leaked'))
        response = client.delete('/api/gallery/cache')
        data = response.json()
        assert data['success'] is False
        assert '/secret' not in data['error']
        assert data['error'] == '清除快取失敗'


# ============ Gallery View 測試 ============

class TestGalleryView:
    """測試 Gallery 列表檢視"""

    def test_view_list_no_file(self, client, mocker, tmp_path):
        """無 HTML 檔案時應返回 404"""
        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}
        })

        response = client.get('/api/gallery/view')

        assert response.status_code == 404

    def test_view_list_with_html(self, client, mocker, tmp_path):
        """有 HTML 檔案時應返回 200 HTML 內容"""
        # 建立測試 HTML
        html_file = tmp_path / "gallery_output.html"
        html_file.write_text('<html><body>Test Gallery</body></html>', encoding='utf-8')

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}
        })

        response = client.get('/api/gallery/view')

        assert response.status_code == 200
        assert 'text/html' in response.headers.get('content-type', '')

    def test_view_list_exception_no_leak(self, client, mocker, tmp_path):
        """open() 拋出 Exception 時：500 且 body 不含原始 exception 訊息"""
        # 建立 HTML 檔案以通過 glob 查找
        html_file = tmp_path / "gallery_output.html"
        html_file.write_text('<html><body>Test</body></html>', encoding='utf-8')

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}
        })

        # Mock open 拋出含敏感路徑的 exception
        mocker.patch('builtins.open', side_effect=Exception("secret internal path /home/user/data"))

        response = client.get('/api/gallery/view')

        assert response.status_code == 500
        assert "secret internal path" not in response.text
        assert "/home/user" not in response.text
        assert "載入失敗" in response.text


# ============ Check Update 測試 ============

class TestCheckUpdate:
    """測試 NFO 更新檢查"""

    def test_check_update_endpoint(self, client):
        """檢查更新端點正常回應"""
        response = client.get('/api/gallery/update-check')

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert 'success' in data


# ============ Generate From IDs 測試 ============

class TestGenerateFromIds:
    """測試 POST /api/gallery/generate-from-ids（封面嵌入功能）"""

    # ---- helper: 共用的 mock HTML generator ----

    def _mock_generator(self, mocker, html_content: bytes = b"<html>fake</html>"):
        """Mock HTMLGenerator.generate() — 直接寫 html_content 到 output path。"""
        def _fake_generate(videos, out_path, **kwargs):
            Path(out_path).write_bytes(html_content)

        mocker.patch(
            'web.routers.scanner.HTMLGenerator.generate',
            side_effect=_fake_generate,
        )

    def _mock_db_miss(self, mocker):
        """Mock VideoRepository.get_by_numbers → 空 dict（全 DB miss）。"""
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}
        mocker.patch('web.routers.scanner.VideoRepository', return_value=mock_repo)
        mocker.patch('web.routers.scanner.get_db_path', return_value=Path('/fake/db.db'))

    def _mock_db_hit(self, mocker, number: str, cover_path: str):
        """Mock VideoRepository.get_by_numbers → DB hit，含指定 cover_path。"""
        from core.database import Video
        fake_video = MagicMock(spec=Video)
        fake_video.path = f'file:///fake/{number}.mp4'
        fake_video.title = f'Test {number}'
        fake_video.original_title = ''
        fake_video.actresses = []
        fake_video.number = number
        fake_video.maker = 'TestMaker'
        fake_video.release_date = '2024-01-01'
        fake_video.tags = []
        fake_video.size_bytes = 1024
        fake_video.mtime = 1700000000.0
        fake_video.cover_path = cover_path

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {number: [fake_video]}
        mocker.patch('web.routers.scanner.VideoRepository', return_value=mock_repo)
        mocker.patch('web.routers.scanner.get_db_path', return_value=Path('/fake/db.db'))

    # ---- 端點層測試 ----

    def test_embed_covers_true_with_legacy_cover_key(self, client, tmp_path, mocker):
        """T1: smart_search 回傳 legacy dict（key='cover'），embed 成功，Referer 正確。"""
        number = 'SONE-205'
        cover_url = 'https://www.javbus.com/pics/cover/SONE-205.jpg'
        fake_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 200000

        self._mock_db_miss(mocker)
        mocker.patch('web.routers.scanner.smart_search', return_value=[{
            'title': 'Test', 'original_title': '', 'actors': ['A'],
            'number': number, 'maker': 'S1', 'date': '2024-01-01',
            'genres': [], 'cover': cover_url,
        }])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_bytes
        mock_resp.headers = {'Content-Type': 'image/jpeg'}
        mock_get = mocker.patch('web.routers.scanner.requests.get', return_value=mock_resp)

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}, 'general': {'theme': 'light'},
        })

        captured_videos = []
        def _capture(videos, out_path, **kwargs):
            captured_videos.extend(videos)
            Path(out_path).write_bytes(b"<html></html>")
        mocker.patch('web.routers.scanner.HTMLGenerator.generate', side_effect=_capture)

        response = client.post('/api/gallery/generate-from-ids', json={
            'numbers': [number], 'embed_covers': True,
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['embedded_count'] == 1
        assert data['embed_failed_count'] == 0
        assert captured_videos[0].img.startswith('data:image/jpeg;base64,')
        # 驗證 Referer header
        call_headers = mock_get.call_args.kwargs.get('headers', mock_get.call_args[1].get('headers', {}))
        assert call_headers.get('Referer') == 'https://www.javbus.com/'

    def test_embed_failed_count_on_http_error(self, client, tmp_path, mocker):
        """T2: JavBus 404 時 img 保留原 URL，embed_failed_count 累加。"""
        number = 'ABC-001'
        cover_url = 'https://www.javbus.com/pics/cover/ABC-001.jpg'

        self._mock_db_miss(mocker)
        mocker.patch('web.routers.scanner.smart_search', return_value=[{
            'title': 'Test', 'original_title': '', 'actors': [],
            'number': number, 'maker': '', 'date': '', 'genres': [],
            'cover': cover_url,
        }])

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mocker.patch('web.routers.scanner.requests.get', return_value=mock_resp)
        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}, 'general': {'theme': 'light'},
        })

        captured_videos = []
        def _capture(videos, out_path, **kwargs):
            captured_videos.extend(videos)
            Path(out_path).write_bytes(b"<html></html>")
        mocker.patch('web.routers.scanner.HTMLGenerator.generate', side_effect=_capture)

        response = client.post('/api/gallery/generate-from-ids', json={
            'numbers': [number], 'embed_covers': True,
        })

        data = response.json()
        assert data['success'] is True
        assert data['embedded_count'] == 0
        assert data['embed_failed_count'] == 1
        assert captured_videos[0].img == cover_url  # 保留原 URL

    def test_embed_covers_false(self, client, tmp_path, mocker):
        """embed_covers=false → _embed_cover 完全不呼叫，img 保持原 URL。"""
        number = 'ABC-002'
        cover_url = 'https://example.com/cover2.jpg'

        self._mock_db_miss(mocker)
        mocker.patch('web.routers.scanner.smart_search', return_value=[{
            'title': 'Test',
            'original_title': '',
            'actors': [],
            'number': number,
            'maker': '',
            'date': '',
            'genres': [],
            'cover': cover_url,
        }])

        mock_get = mocker.patch('web.routers.scanner.requests.get')

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)},
            'general': {'theme': 'light'},
        })

        # 捕獲傳入 generator 的 videos
        captured_videos = []
        def _fake_generate(videos, out_path, **kwargs):
            captured_videos.extend(videos)
            Path(out_path).write_bytes(b"<html></html>")
        mocker.patch('web.routers.scanner.HTMLGenerator.generate', side_effect=_fake_generate)

        response = client.post('/api/gallery/generate-from-ids', json={
            'numbers': [number],
            'embed_covers': False,
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        # requests.get 不應被呼叫（embed 沒有執行）
        mock_get.assert_not_called()
        # img 保持原 HTTP URL
        assert captured_videos[0].img == cover_url
        # response 不含 embed 統計
        assert 'embedded_count' not in data

    # ---- _embed_cover 單元層測試（直接 import） ----

    def test_embed_cover_file_uri(self, mocker):
        """file:/// URI → 讀本地檔案 → 回傳 data:image/jpeg;base64,..."""
        from web.routers.scanner import _embed_cover

        fake_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 2000
        mocker.patch('web.routers.scanner.Path.read_bytes', return_value=fake_bytes)
        mocker.patch('web.routers.scanner.uri_to_fs_path', return_value='/fake/cover.jpg')

        result = _embed_cover('file:///fake/cover.jpg')

        expected_b64 = base64.b64encode(fake_bytes).decode('ascii')
        assert result == f'data:image/jpeg;base64,{expected_b64}'

    def test_embed_cover_http_download(self, mocker):
        """HTTP URL → requests.get → 回傳 data:image/jpeg;base64,..."""
        from web.routers.scanner import _embed_cover

        fake_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 2000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_bytes
        mock_resp.headers = {'Content-Type': 'image/jpeg'}
        mocker.patch('web.routers.scanner.requests.get', return_value=mock_resp)

        result = _embed_cover('https://example.com/cover.jpg')

        expected_b64 = base64.b64encode(fake_bytes).decode('ascii')
        assert result == f'data:image/jpeg;base64,{expected_b64}'

    def test_embed_cover_http_png(self, mocker):
        """PNG URL → Content-Type image/png 優先於副檔名。"""
        from web.routers.scanner import _embed_cover

        fake_bytes = b'\x89PNG\r\n' + b'\x00' * 2000
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = fake_bytes
        mock_resp.headers = {'Content-Type': 'image/png'}
        mocker.patch('web.routers.scanner.requests.get', return_value=mock_resp)

        result = _embed_cover('https://example.com/img.png')

        expected_b64 = base64.b64encode(fake_bytes).decode('ascii')
        assert result == f'data:image/png;base64,{expected_b64}'

    def test_embed_cover_failure_graceful(self, mocker):
        """requests.get 拋 Timeout → 回傳原 URL（不中斷）。"""
        from web.routers.scanner import _embed_cover
        import requests as req_lib

        mocker.patch('web.routers.scanner.requests.get',
                     side_effect=req_lib.exceptions.Timeout('timeout'))

        url = 'https://example.com/slow.jpg'
        result = _embed_cover(url)

        assert result == url  # 保留原值

    def test_embed_cover_http_404(self, mocker):
        """HTTP 404 → 回傳原 URL。"""
        from web.routers.scanner import _embed_cover

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mocker.patch('web.routers.scanner.requests.get', return_value=mock_resp)

        url = 'https://example.com/notfound.jpg'
        result = _embed_cover(url)

        assert result == url

    def test_embed_cover_empty_string(self):
        """空字串 → 空字串。"""
        from web.routers.scanner import _embed_cover

        assert _embed_cover('') == ''

    def test_embed_cover_already_data_uri(self):
        """已是 data: URI → 原值（冪等）。"""
        from web.routers.scanner import _embed_cover

        data_uri = 'data:image/jpeg;base64,/9j/abc123=='
        assert _embed_cover(data_uri) == data_uri

    def test_embed_cover_unknown_scheme(self):
        """非 file:// 非 http(s):// 的格式（如相對路徑）→ 保留原值。"""
        from web.routers.scanner import _embed_cover

        assert _embed_cover('ftp://example.com/cover.jpg') == 'ftp://example.com/cover.jpg'
        assert _embed_cover('covers/SONE-205.jpg') == 'covers/SONE-205.jpg'
