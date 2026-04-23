"""tests/unit/test_enricher_b1.py — spec-48b §b1 AC#1 root-cause fix 測試

- TestDbUpsertSampleImagesGate：驗證 _db_upsert() sample_images gate 行為
  write_extrafanart=False  → DB 不寫入遠端 URL（保留現有值）
  write_extrafanart=True, count=0 → DB 不寫入
  write_extrafanart=True, count>0 → DB 更新
"""


class TestDbUpsertSampleImagesGate:
    """spec-48b §b1 AC#1 — _db_upsert sample_images gate"""

    def _run_enrich(self, write_extrafanart, download_count, existing_samples=None):
        """Helper：執行 enrich_single 並回傳 repo.upsert call args"""
        from unittest.mock import patch, MagicMock, call
        with patch("os.path.exists", return_value=True), \
             patch("core.enricher.VideoRepository") as mock_repo_cls, \
             patch("core.enricher.search_jav") as mock_search, \
             patch("core.enricher.generate_nfo", return_value=True), \
             patch("core.enricher.download_image", return_value=True), \
             patch("core.enricher._write_extrafanart", return_value=download_count), \
             patch("core.enricher.find_subtitle_files", return_value=[]):
            mock_repo = MagicMock()
            mock_existing = MagicMock()
            mock_existing.sample_images = existing_samples or []
            mock_existing.user_tags = []
            mock_existing.cover_path = ""
            mock_repo.get_by_path.return_value = mock_existing
            mock_repo_cls.return_value = mock_repo
            mock_search.return_value = {
                "number": "SONE-205",
                "title": "Test",
                "actors": [],
                "cover": "http://example.com/cover.jpg",
                "date": "2024-01-01",
                "maker": "SOD",
                "director": "",
                "series": "",
                "label": "",
                "tags": [],
                "sample_images": ["http://example.com/s1.jpg"],
                "source": "javbus",
            }
            from core.enricher import enrich_single
            enrich_single(
                file_path="/tmp/SONE-205.mp4",
                number="SONE-205",
                mode="refresh_full",
                write_extrafanart=write_extrafanart,
                write_nfo=False,
                write_cover=False,
            )
            return mock_repo.upsert.call_args

    def test_no_extrafanart_flag_does_not_write_sample_images(self):
        """write_extrafanart=False → sample_images 欄位保留現有值"""
        args = self._run_enrich(write_extrafanart=False, download_count=0, existing_samples=["file:///old.jpg"])
        video = args[0][0]
        assert video.sample_images == ["file:///old.jpg"], \
            "write_extrafanart=False 時不應覆蓋 DB sample_images"

    def test_extrafanart_written_zero_does_not_write_sample_images(self):
        """write_extrafanart=True 但下載 0 張 → 不更新"""
        args = self._run_enrich(write_extrafanart=True, download_count=0, existing_samples=[])
        video = args[0][0]
        assert video.sample_images == [], \
            "extrafanart_written=0 時不應寫入 scraper 回傳的遠端 URL"

    def test_extrafanart_written_positive_updates_sample_images(self):
        """write_extrafanart=True 且下載 > 0 張 → 更新 DB"""
        args = self._run_enrich(write_extrafanart=True, download_count=2, existing_samples=[])
        video = args[0][0]
        assert "http://example.com/s1.jpg" in video.sample_images, \
            "extrafanart_written>0 時應寫入 scraper 回傳的 URLs"
