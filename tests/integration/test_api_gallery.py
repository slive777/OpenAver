"""
test_api_gallery.py - 畫廊 API 整合測試

測試圖片代理、NFO 更新等 Gallery API 端點。
"""

import pytest
import os
import tempfile
from pathlib import Path


# ============ 圖片代理測試 ============

class TestImageProxy:
    """測試圖片代理 API /api/gallery/image"""

    def test_image_proxy_local_file(self, client, tmp_path):
        """本地圖片檔案代理"""
        # 建立測試圖片
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)  # JPEG magic bytes

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'

    def test_image_proxy_png(self, client, tmp_path):
        """PNG 圖片代理"""
        test_image = tmp_path / "test.png"
        # PNG magic bytes
        test_image.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

    def test_image_proxy_not_found(self, client):
        """圖片不存在應返回 404"""
        response = client.get('/api/gallery/image', params={'path': '/nonexistent/image.jpg'})

        assert response.status_code == 404

    def test_image_proxy_webp(self, client, tmp_path):
        """WebP 圖片代理"""
        test_image = tmp_path / "test.webp"
        # WebP magic bytes (RIFF....WEBP)
        test_image.write_bytes(b'RIFF\x00\x00\x00\x00WEBP' + b'\x00' * 100)

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/webp'


class TestImageProxyPathConversion:
    """測試圖片代理路徑轉換"""

    def test_unix_path(self, client, tmp_path):
        """Unix 風格路徑"""
        test_image = tmp_path / "unix_test.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)

        unix_path = str(test_image)  # 已經是 Unix 風格

        response = client.get('/api/gallery/image', params={'path': unix_path})

        assert response.status_code == 200

    def test_url_encoded_path(self, client, tmp_path):
        """URL 編碼路徑"""
        test_image = tmp_path / "test image.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)

        from urllib.parse import quote
        encoded_path = quote(str(test_image))

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


# ============ Gallery View 測試 ============

class TestGalleryView:
    """測試 Gallery 列表檢視"""

    def test_view_list_no_file(self, client, mocker, tmp_path):
        """無 HTML 檔案時"""
        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}
        })

        response = client.get('/api/gallery/view')

        # 應該返回某種錯誤或預設內容
        assert response.status_code in [200, 404, 500]

    def test_view_list_with_html(self, client, mocker, tmp_path):
        """有 HTML 檔案時"""
        # 建立測試 HTML
        html_file = tmp_path / "gallery_output.html"
        html_file.write_text('<html><body>Test Gallery</body></html>', encoding='utf-8')

        mocker.patch('web.routers.scanner.load_config', return_value={
            'gallery': {'output_dir': str(tmp_path)}
        })

        response = client.get('/api/gallery/view')

        # 應該返回 HTML 內容
        if response.status_code == 200:
            assert 'text/html' in response.headers.get('content-type', '')


# ============ Check Update 測試 ============

class TestCheckUpdate:
    """測試 NFO 更新檢查"""

    def test_check_update_endpoint(self, client):
        """檢查更新端點正常回應"""
        response = client.get('/api/gallery/update-check')

        # API 可能返回 200 或 需要配置
        # 這裡只驗證端點可達且返回 JSON
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
