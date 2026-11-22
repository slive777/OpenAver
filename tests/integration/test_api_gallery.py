"""
test_api_gallery.py - 畫廊 API 整合測試

測試圖片代理、NFO 更新等 Gallery API 端點。
"""

import base64
from pathlib import Path
from unittest.mock import MagicMock

from core.path_utils import to_file_uri


# ============ 圖片代理測試 ============

class TestImageProxy:
    """測試圖片代理 API /api/gallery/image"""

    def test_image_proxy_local_file(self, client, tmp_path, mocker):
        """本地圖片檔案代理"""
        # 建立測試圖片
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)  # JPEG magic bytes

        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'


    def test_image_proxy_svg_forbidden(self, client, tmp_path, mocker):
        """不服務 .svg（可執行內容）；即使檔案在白名單目錄內也 403"""
        test_image = tmp_path / "logo.svg"
        test_image.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')

        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'gallery': {'directories': [str(tmp_path)], 'path_mappings': {}},
        })

        response = client.get('/api/gallery/image', params={'path': str(test_image)})

        assert response.status_code == 403


class TestImageProxyUNCAllowlist:
    """UNC NAS 路徑白名單 — 大小寫不敏感修正（TASK-62-NAS-UNC）"""

    def test_unc_host_uppercase_allowed(self, client, mocker):
        """realpath 回傳 host 大寫 UNC → 白名單命中 → 200"""
        # 白名單設 \\DiskStation\usbshare1，realpath 回傳 \\DISKSTATION\usbshare1\a.jpg
        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'gallery': {
                'directories': [r'\\DiskStation\usbshare1'],
                'path_mappings': {},
            },
        })
        # TASK-89a-T2 (CD-89a-7): scope the fake host-case rewrite to the two UNC
        # strings this test is about. A blanket return_value would ALSO corrupt the
        # off-flavor fixed-root candidate that _image_whitelist_dirs now always
        # injects (config omits `scraper` → defaults off), making every realpath()
        # return the same value and spuriously widening the whitelist.
        request_path = r'\\DiskStation\usbshare1\a.jpg'
        dir_path = r'\\DiskStation\usbshare1'
        fake_realpath_result = r'\\DISKSTATION\usbshare1\a.jpg'
        mocker.patch(
            'os.path.realpath',
            side_effect=lambda p: fake_realpath_result if p in (request_path, dir_path) else p,
        )
        mocker.patch('os.path.exists', return_value=True)
        mocker.patch('web.routers.gallery_media.FileResponse',
                     return_value=__import__('starlette.responses', fromlist=['Response']).Response(status_code=200))

        response = client.get('/api/gallery/image', params={'path': request_path})
        assert response.status_code == 200

    def test_unc_outside_allowlist_still_403(self, client, mocker):
        """realpath 回傳白名單外 UNC → 403（安全守衛不退化）"""
        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'gallery': {
                'directories': [r'\\DiskStation\usbshare1'],
                'path_mappings': {},
            },
        })
        # TASK-89a-T2 (CD-89a-7): scope the realpath rewrite to the ONE request
        # path (same rationale as test_unc_host_uppercase_allowed) so a blanket
        # mock doesn't corrupt the off-flavor fixed-root candidate that
        # _image_whitelist_dirs now always injects. This must still exercise the
        # realpath ESCAPE it exists for: the request normpath-looks INSIDE the
        # whitelist (\\DiskStation\usbshare1\evil.jpg) but realpath resolves it
        # OUT to \\OtherServer\secret — without the realpath step it would be
        # 200, so the mock is load-bearing (drop it → test goes 200 → RED).
        # Whitelist dir + off-candidate stay identity (not escaped).
        inside_looking = r'\\DiskStation\usbshare1\evil.jpg'
        escaped_outside = r'\\OtherServer\secret\evil.jpg'
        mocker.patch(
            'os.path.realpath',
            side_effect=lambda p: escaped_outside if p == inside_looking else p,
        )
        mocker.patch('os.path.exists', return_value=True)

        response = client.get('/api/gallery/image', params={'path': inside_looking})
        assert response.status_code == 403


class TestImageProxyOutputPath:
    """TASK-88c-T1: /api/gallery/image 白名單納入各來源非空 output_path"""

    def test_cover_under_output_path_allowed(self, client, tmp_path, mocker):
        """封面在唯讀來源的 output_path 底下 → 200（原 403 → 現 200，Acceptance #16）"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        cover = out_dir / "MOVIE-001" / "poster.jpg"
        cover.parent.mkdir()
        cover.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)  # JPEG magic

        # TASK-89a-T2 (CD-89a-7): this test asserts a cover under the *configured*
        # output_path is whitelisted — that is media-server semantics now, so pin
        # external_manager to jellyfin. Under off, resolve_output_root ignores
        # output_path and returns the fixed output/lib/<name> root instead.
        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'scraper': {'external_manager': 'jellyfin'},
            'gallery': {
                'directories': [
                    {'path': str(src_dir), 'readonly': True, 'output_path': str(out_dir)},
                ],
                'path_mappings': {},
            },
        })

        response = client.get('/api/gallery/image', params={'path': str(cover)})
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'

    def test_file_outside_output_path_still_403(self, client, tmp_path, mocker):
        """檔案在 output_path 外、且不在任何 src.path 底下 → 403（守衛不退化）"""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        cover = elsewhere / "poster.jpg"
        cover.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 50)

        mocker.patch('web.routers.gallery_media.load_config', return_value={
            'gallery': {
                'directories': [
                    {'path': str(src_dir), 'readonly': True, 'output_path': str(out_dir)},
                ],
                'path_mappings': {},
            },
        })

        response = client.get('/api/gallery/image', params={'path': str(cover)})
        assert response.status_code == 403


# ============ Gallery Stats 測試 ============


# ============ 清除快取測試 ============

class TestClearCache:
    """測試 DELETE /api/gallery/cache"""


    def test_clear_cache_success(self, client, tmp_path, mocker):
        """有資料時應清除並回傳刪除數量"""
        from core.database import init_db, VideoRepository, Video
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([
            Video(path=to_file_uri("/v1.mp4"), mtime=100.0),
            Video(path=to_file_uri("/v2.mp4"), mtime=200.0),
        ])
        mocker.patch('web.routers.scanner.get_db_path', return_value=db_path)

        response = client.delete('/api/gallery/cache')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['deleted'] == 2
        assert repo.count() == 0


# ============ Gallery View 測試 ============

class TestGalleryView:
    """測試 Gallery 列表檢視"""


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


# ============ Check Update 測試 ============


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

    def _mock_db_miss(self, mocker, tmp_path):
        """Mock VideoRepository.get_by_numbers → 空 dict（全 DB miss）。"""
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}
        mocker.patch('web.routers.scanner.VideoRepository', return_value=mock_repo)
        mocker.patch('web.routers.scanner.get_db_path', return_value=tmp_path / 'isolated.db')

    def _mock_db_hit(self, mocker, number: str, cover_path: str):
        """Mock VideoRepository.get_by_numbers → DB hit，含指定 cover_path。"""
        from core.database import Video
        fake_video = MagicMock(spec=Video)
        fake_video.path = to_file_uri(f'/fake/{number}.mp4')
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

        self._mock_db_miss(mocker, tmp_path)
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


    def test_embed_covers_false(self, client, tmp_path, mocker):
        """embed_covers=false → _embed_cover 完全不呼叫，img 保持原 URL。"""
        number = 'ABC-002'
        cover_url = 'https://example.com/cover2.jpg'

        self._mock_db_miss(mocker, tmp_path)
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
        mocker.patch('web.routers.scanner.uri_to_local_fs_path', return_value='/fake/cover.jpg')

        result = _embed_cover(to_file_uri('/fake/cover.jpg'))

        expected_b64 = base64.b64encode(fake_bytes).decode('ascii')
        assert result == f'data:image/jpeg;base64,{expected_b64}'

    def test_embed_cover_reverse_maps_wsl_unc_path_mappings(self, mocker, tmp_path, monkeypatch):
        """TASK-91-T2b #14：_embed_cover(img_ref, path_mappings) 在 WSL+UNC mapping
        環境下，Path.read_bytes 讀的必須是反解後的本機路徑（可真的 open()），非裸
        uri_to_fs_path() 產生的映射端 UNC 字串。"""
        import core.path_utils as path_utils
        from web.routers.scanner import _embed_cover

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        cover = nas_dir / "cover.jpg"
        fake_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 2000
        cover.write_bytes(fake_bytes)
        mappings = {str(nas_dir): "//NAS/share"}

        result = _embed_cover("file://///NAS/share/cover.jpg", mappings)

        expected_b64 = base64.b64encode(fake_bytes).decode('ascii')
        assert result == f'data:image/jpeg;base64,{expected_b64}', (
            f"應反解成本機路徑真的讀到檔案，實際: {result[:80]}"
        )


    def test_embed_cover_failure_graceful(self, mocker):
        """requests.get 拋 Timeout → 回傳原 URL（不中斷）。"""
        from web.routers.scanner import _embed_cover
        import requests as req_lib

        mocker.patch('web.routers.scanner.requests.get',
                     side_effect=req_lib.exceptions.Timeout('timeout'))

        url = 'https://example.com/slow.jpg'
        result = _embed_cover(url)

        assert result == url  # 保留原值


