"""
T60-2 / B1 regression — `POST /api/gallery/generate-from-ids` DB-miss scrape 路徑
須使用 scraper 回傳的 `tags` key（而非不存在的 `genres` key）建構 VideoInfo.genre。

Bug 來源：`web/routers/scanner.py:1243` 之前讀 `r.get('genres', [])` →
scrapers/models.py:46 實際 key 為 'tags' → VideoInfo.genre 永遠空字串 →
NFO `<genre>` 欄位空白（用戶可見）。

策略：捕獲傳給 HTMLGenerator.generate() 的 VideoInfo 物件，直接斷言 .genre 內容。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch


def _capture_videos_from_generate(mock_generator):
    """從 mock generator.generate(all_videos, ...) 呼叫中抽出 all_videos 參數。"""
    assert mock_generator.generate.called, "HTMLGenerator.generate() 未被呼叫"
    call_args = mock_generator.generate.call_args
    # signature: generate(all_videos, html_path, title=...)
    return call_args.args[0]


class TestScannerGenerateFromIdsTags:
    """DB-miss scrape 路徑必須讀取 scraper 的 'tags' key 填入 genre 欄位。"""

    def test_db_miss_tags_populated_into_genre(self, client, monkeypatch, tmp_path):
        """scraper 回 tags=['巨乳','OL']，VideoInfo.genre 應為 '巨乳,OL'。"""
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}  # DB miss

        mock_generator = MagicMock()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(output_dir), "path_mappings": {}},
            "general": {"theme": "light"}
        })

        scraper_result = {
            'number': 'SONE-100',
            'title': 'Scraped Title',
            'date': '2026-01-01',
            'tags': ['巨乳', 'OL', '單體作品'],
        }

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[scraper_result]):
            response = client.post(
                '/api/gallery/generate-from-ids',
                json={'numbers': ['SONE-100']}
            )

        assert response.status_code == 200
        videos = _capture_videos_from_generate(mock_generator)
        assert len(videos) == 1
        assert videos[0].genre == '巨乳,OL,單體作品'

    def test_db_miss_empty_tags_returns_empty_genre(self, client, monkeypatch, tmp_path):
        """scraper 回 tags=[]，VideoInfo.genre 應為空字串（不崩潰、不寫入殘渣）。"""
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}

        mock_generator = MagicMock()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(output_dir), "path_mappings": {}},
            "general": {"theme": "light"}
        })

        scraper_result = {
            'number': 'SONE-200',
            'title': 'No Tags',
            'date': '2026-02-01',
            'tags': [],
        }

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[scraper_result]):
            response = client.post(
                '/api/gallery/generate-from-ids',
                json={'numbers': ['SONE-200']}
            )

        assert response.status_code == 200
        videos = _capture_videos_from_generate(mock_generator)
        assert len(videos) == 1
        assert videos[0].genre == ''

    def test_db_hit_path_unaffected(self, client, monkeypatch, tmp_path):
        """DB-hit 路徑不走 scrape（regression guard：本修改不應影響 DB hit）。"""
        from core.database import Video
        from core.path_utils import to_file_uri

        video = Video(
            id=1, path=to_file_uri('/video/SONE-300.mp4'), title='DB Title',
            original_title='', actresses=[], number='SONE-300',
            maker='Sony', release_date='2026-03-01', tags=['DB標籤'],
            size_bytes=1000, mtime=0.0, cover_path='', nfo_mtime=None,
            director='', duration=None, series='', label=''
        )

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {'SONE-300': [video]}

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
            response = client.post(
                '/api/gallery/generate-from-ids',
                json={'numbers': ['SONE-300']}
            )

        assert response.status_code == 200
        mock_scrape.assert_not_called()
        videos = _capture_videos_from_generate(mock_generator)
        assert len(videos) == 1
        # DB-hit 走 v.tags（list）→ ','.join
        assert videos[0].genre == 'DB標籤'


class TestScannerGenerateUsesResolveGalleryOutputPath:
    """TASK-153b-T3：generate-from-ids 經 resolve_gallery_output_path 落檔。"""

    def test_empty_output_dir_writes_under_data_root(self, client, monkeypatch, tmp_path):
        """output_dir='' → 寫入 get_data_root() 之下。"""
        from core.data_root import get_data_root
        import hashlib

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}

        data_root = tmp_path / "data_root"
        data_root.mkdir()
        monkeypatch.setenv("OPENAVER_DATA_DIR", str(data_root))

        # 既有檔案：產生前後 hash 不變（自訂／空值都不得搬既有檔）
        existing = data_root / "pre_existing.html"
        existing.write_bytes(b"<html>keep-me</html>")
        before_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

        def fake_generate(all_videos, html_path, **kwargs):
            Path(html_path).parent.mkdir(parents=True, exist_ok=True)
            Path(html_path).write_text("<html>generated</html>", encoding="utf-8")

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = fake_generate

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": "", "path_mappings": {}},
            "general": {"theme": "light"},
            "search": {"proxy_url": ""},
        })

        scraper_result = {
            'number': 'SNIS-001',
            'title': 'Empty Dir',
            'date': '2026-01-01',
            'tags': [],
        }

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[scraper_result]):
            response = client.post(
                '/api/gallery/generate-from-ids',
                json={'numbers': ['SNIS-001']}
            )

        assert response.status_code == 200
        body = response.json()
        assert body.get("success") is True
        html_path = Path(body["html_path"])
        assert html_path.parent == get_data_root()
        assert html_path.exists()
        assert hashlib.sha256(existing.read_bytes()).hexdigest() == before_hash

    def test_absolute_custom_dir_unchanged_and_hash_stable(self, client, monkeypatch, tmp_path):
        """自訂絕對路徑：寫入該處，既有 HTML hash 不變。"""
        import hashlib

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {}

        custom = tmp_path / "custom_abs"
        custom.mkdir()
        existing = custom / "keep.html"
        existing.write_bytes(b"<html>stable</html>")
        before_hash = hashlib.sha256(existing.read_bytes()).hexdigest()

        def fake_generate(all_videos, html_path, **kwargs):
            Path(html_path).parent.mkdir(parents=True, exist_ok=True)
            Path(html_path).write_text("<html>generated</html>", encoding="utf-8")

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = fake_generate

        monkeypatch.setattr("web.routers.scanner.load_config", lambda: {
            "gallery": {"output_dir": str(custom), "path_mappings": {}},
            "general": {"theme": "light"},
            "search": {"proxy_url": ""},
        })

        scraper_result = {
            'number': 'SNIS-002',
            'title': 'Abs Dir',
            'date': '2026-01-02',
            'tags': [],
        }

        with patch('web.routers.scanner.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scanner.HTMLGenerator', return_value=mock_generator), \
             patch('web.routers.scanner.smart_search', return_value=[scraper_result]):
            response = client.post(
                '/api/gallery/generate-from-ids',
                json={'numbers': ['SNIS-002']}
            )

        assert response.status_code == 200
        body = response.json()
        html_path = Path(body["html_path"])
        assert html_path.parent == custom
        assert hashlib.sha256(existing.read_bytes()).hexdigest() == before_hash
