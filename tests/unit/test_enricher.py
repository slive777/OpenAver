"""
test_enricher.py - core/enricher.py TDD-lite 單元測試（full mock）

涵蓋 TASK-T4.md 的 25 個邊界條件
"""

import os
import pytest
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch, MagicMock, call

from core.path_utils import to_file_uri


# ── helpers ──────────────────────────────────────────────────────────────────

_MISSING = object()


def _make_video(
    number="SONE-205",
    title="テストタイトル",
    original_title="テストタイトル",
    actresses=_MISSING,
    maker="SOD",
    director="テスト監督",
    series="テストシリーズ",
    label="LABEL",
    tags=_MISSING,
    sample_images=_MISSING,
    duration=120,
    cover_path="https://example.com/cover.jpg",
    release_date="2024-01-01",
    path="",
):
    from core.database import Video
    return Video(
        number=number,
        title=title,
        original_title=original_title,
        actresses=["女優A"] if actresses is _MISSING else actresses,
        maker=maker,
        director=director,
        series=series,
        label=label,
        tags=["タグ"] if tags is _MISSING else tags,
        sample_images=["https://example.com/s1.jpg", "https://example.com/s2.jpg"] if sample_images is _MISSING else sample_images,
        duration=duration,
        cover_path=cover_path,
        release_date=release_date,
        path=path,
    )


def _make_scraper_result(
    number="SONE-205",
    title="テストタイトル",
    actors=None,
    cover="https://example.com/cover.jpg",
    date="2024-01-01",
    maker="SOD",
    director="テスト監督",
    series="テストシリーズ",
    label="LABEL",
    tags=None,
    sample_images=None,
    duration=120,
    url="https://www.javbus.com/SONE-205",
):
    return {
        "number": number,
        "title": title,
        "actors": actors or ["女優A"],
        "cover": cover,
        "date": date,
        "maker": maker,
        "director": director,
        "series": series,
        "label": label,
        "tags": tags or ["タグ"],
        "sample_images": sample_images or ["https://example.com/s1.jpg", "https://example.com/s2.jpg"],
        "duration": duration,
        "url": url,
    }


FS_PATH = "/video/SONE-205.mp4"
NFO_PATH = "/video/SONE-205.nfo"
COVER_PATH = "/video/SONE-205.jpg"


# ── 1. file_path 不存在 ───────────────────────────────────────────────────────

class TestFileNotFound:
    def test_file_not_found_returns_error(self):
        """邊界條件 1: file_path 指向不存在的檔案"""
        with patch("os.path.exists", return_value=False):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path="/nonexistent/SONE-205.mp4",
                number="SONE-205",
            )
        assert result.success is False
        assert "不存在" in result.error


# ── 2. number 為空 ────────────────────────────────────────────────────────────

class TestEmptyNumber:
    def test_empty_number_returns_error(self):
        """邊界條件 2: number 為空字串"""
        with patch("os.path.exists", return_value=True):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="",
            )
        assert result.success is False
        assert "番號" in result.error


# ── 3. mode 不合法 ────────────────────────────────────────────────────────────

class TestInvalidMode:
    def test_invalid_mode_returns_error(self):
        """邊界條件 3: mode 不在合法值列表"""
        with patch("os.path.exists", return_value=True):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="invalid_mode",
            )
        assert result.success is False
        assert "mode" in result.error.lower() or "不支援" in result.error


# ── 4. fill_missing: DB 完整，不打 scraper ────────────────────────────────────

class TestFillMissingDbComplete:
    def test_db_complete_no_scraper(self):
        """邊界條件 4: DB 有完整資料 → 不打 scraper"""
        video = _make_video()
        db_result = {"SONE-205": [video]}

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav") as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_not_called()
        assert result.success is True
        assert result.source_used == "db"


# ── 4b. fill_missing: DB 有完整欄位但缺 label → 觸發 scraper ─────────────────

class TestFillMissingLabelMissing:
    def test_db_missing_label_calls_scraper(self):
        """邊界條件 4b: DB 有 title/actresses/maker/director/release_date 但缺 label → 觸發 scraper"""
        video = _make_video(label="")
        db_result = {"SONE-205": [video]}
        scraper_data = _make_scraper_result()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_called_once()
        assert result.success is True
        assert "label" in result.fields_filled


# ── 5. fill_missing: DB 有資料但缺欄位，打 scraper 補 ────────────────────────

class TestFillMissingDbMissingFields:
    def test_db_missing_fields_calls_scraper(self):
        """邊界條件 5: DB 有資料但缺 director/series → 打 scraper"""
        video = _make_video(director="", series=None)
        db_result = {"SONE-205": [video]}
        scraper_data = _make_scraper_result()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_called_once()
        assert result.success is True
        assert "director" in result.fields_filled or "series" in result.fields_filled


# ── 6. fill_missing: DB miss + NFO 存在 ──────────────────────────────────────

class TestFillMissingDbMissNfoExists:
    def test_db_miss_nfo_exists_reads_nfo(self):
        """邊界條件 6: DB miss + NFO 存在 → 讀 NFO，缺少的才打 scraper"""
        import xml.etree.ElementTree as ET

        nfo_root = ET.Element("movie")
        ET.SubElement(nfo_root, "title").text = "テストタイトル"
        ET.SubElement(nfo_root, "studio").text = "SOD"
        # 缺 director

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=_make_scraper_result()) as mock_search,
            patch("core.enricher.parse_nfo", return_value=(MagicMock(), nfo_root)),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_called_once()
        assert result.success is True


# ── 7. fill_missing: DB miss + NFO 不存在 ────────────────────────────────────

class TestFillMissingDbMissNfoMiss:
    def test_db_miss_nfo_miss_calls_scraper(self):
        """邊界條件 7: DB miss + NFO 不存在 → 打 scraper"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=_make_scraper_result()) as mock_search,
            patch("core.enricher.parse_nfo", return_value=(None, None)),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_called_once()
        assert result.success is True


# ── 8. fill_missing: scraper 找不到 ──────────────────────────────────────────

class TestFillMissingScraperNotFound:
    def test_scraper_not_found_returns_error(self):
        """邊界條件 8: search_jav 回傳 None → error"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.parse_nfo", return_value=(None, None)),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        assert result.success is False
        assert "SONE-205" in result.error or "找不到" in result.error
        # 89b-T2: not-found branch marks scrape_attempted_at (same as refresh_full).
        mock_repo.update_scrape_attempted_at.assert_called_once()
        call_args = mock_repo.update_scrape_attempted_at.call_args[0]
        assert call_args[0] == to_file_uri(FS_PATH)
        assert call_args[1] > 0
        # not-found path must not create/upsert any new row (only mark attempted).
        mock_repo.upsert.assert_not_called()


# ── 9. db_to_sidecar: DB 完整，不打 scraper ──────────────────────────────────

class TestDbToSidecarComplete:
    def test_db_complete_no_scraper(self):
        """邊界條件 9: db_to_sidecar + DB 完整 → 不打 scraper，寫 NFO/封面"""
        video = _make_video()
        db_result = {"SONE-205": [video]}

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav") as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="db_to_sidecar",
            )

        mock_search.assert_not_called()
        assert result.success is True


# ── 10. db_to_sidecar: DB miss → error ───────────────────────────────────────

class TestDbToSidecarDbMiss:
    def test_db_miss_returns_error(self):
        """邊界條件 10: db_to_sidecar + DB miss → error"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="db_to_sidecar",
            )

        assert result.success is False
        assert "SONE-205" in result.error or "DB" in result.error


# ── 11. db_to_sidecar: 封面 URL 缺失 → cover_written=False ───────────────────

class TestDbToSidecarNoCoverUrl:
    def test_no_cover_url_cover_not_written(self):
        """邊界條件 11: DB 有資料但 cover_path 為空 → cover_written=False"""
        video = _make_video(cover_path="")
        db_result = {"SONE-205": [video]}

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="db_to_sidecar",
                write_cover=True,
            )

        assert result.cover_written is False
        mock_dl.assert_not_called()


# ── 12. refresh_full: 強制打 scraper ─────────────────────────────────────────

class TestRefreshFullAlwaysScrape:
    def test_always_calls_scraper(self):
        """邊界條件 12: refresh_full → 強制打 scraper，忽略 DB/NFO"""
        video = _make_video()
        db_result = {"SONE-205": [video]}
        scraper_data = _make_scraper_result()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
            )

        mock_search.assert_called_once()
        assert result.success is True


# ── 13. refresh_full: scraper 失敗 ───────────────────────────────────────────

class TestRefreshFullScraperFail:
    def test_scraper_fail_returns_error(self):
        """邊界條件 13: refresh_full + scraper 失敗 → error"""
        with (
            patch("os.path.exists", return_value=True),
            # 89b-T2: must mock VideoRepository — refresh_full not-found now calls
            # repo.update_scrape_attempted_at(); without this mock it would hit the
            # real project output/openaver.db (see TASK-89b-T2 現況分析 §3).
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=None),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
            )

        assert result.success is False
        assert "SONE-205" in result.error or "找不到" in result.error
        # 89b-T2: not-found branch marks scrape_attempted_at via to_file_uri(fs_path) inline
        # (NOT the later-assigned `path_uri` var — that would NameError before this branch).
        mock_repo.update_scrape_attempted_at.assert_called_once()
        call_args = mock_repo.update_scrape_attempted_at.call_args[0]
        assert call_args[0] == to_file_uri(FS_PATH)
        assert call_args[1] > 0
        # not-found path must not create/upsert any new row (only mark attempted).
        mock_repo.upsert.assert_not_called()


# ── 14. write_nfo=False ───────────────────────────────────────────────────────

class TestWriteNfoFalse:
    def test_write_nfo_false_skips_nfo(self):
        """邊界條件 14: write_nfo=False → 不呼叫 generate_nfo"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo") as mock_nfo,
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=False,
            )

        mock_nfo.assert_not_called()
        assert result.nfo_written is False


# ── 15. write_cover=False ─────────────────────────────────────────────────────

class TestWriteCoverFalse:
    def test_write_cover_false_skips_download(self):
        """邊界條件 15: write_cover=False → 不呼叫 download_image"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_cover=False,
            )

        mock_dl.assert_not_called()
        assert result.cover_written is False


# ── 16. write_extrafanart=False（預設）────────────────────────────────────────

class TestWriteExtrafanartFalse:
    def test_write_extrafanart_false_by_default(self):
        """邊界條件 16: write_extrafanart=False（預設）→ extrafanart_written=0"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_extrafanart=False,
            )

        assert result.extrafanart_written == 0


# ── 17. NFO 已存在 + overwrite_existing=False ─────────────────────────────────

class TestNfoExistsNoOverwrite:
    def test_nfo_exists_no_overwrite_skips(self):
        """邊界條件 17: NFO 已存在 + overwrite_existing=False → nfo_written=False"""
        video = _make_video()

        def exists_side_effect(path):
            if str(path).endswith(".nfo"):
                return True
            return True  # video file exists

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo") as mock_nfo,
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=False,
            )

        mock_nfo.assert_not_called()
        assert result.nfo_written is False


# ── 18. NFO 已存在 + overwrite_existing=True ─────────────────────────────────

class TestNfoExistsOverwrite:
    def test_nfo_exists_overwrite_writes(self):
        """邊界條件 18: NFO 已存在 + overwrite_existing=True → 覆寫，nfo_written=True"""
        video = _make_video()

        def exists_side_effect(path):
            return True  # both video and nfo exist

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True) as mock_nfo,
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
            )

        mock_nfo.assert_called_once()
        assert result.nfo_written is True


# ── 19. 封面已存在 + overwrite_existing=False ────────────────────────────────

class TestCoverExistsNoOverwrite:
    def test_cover_exists_no_overwrite_skips(self):
        """邊界條件 19: 封面已存在 + overwrite_existing=False → cover_written=False"""
        video = _make_video()

        def exists_side_effect(path):
            return True  # both video and cover exist

        with (
            patch("os.path.exists", side_effect=exists_side_effect),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_cover=True,
                overwrite_existing=False,
            )

        mock_dl.assert_not_called()
        assert result.cover_written is False


# ── 20. write_extrafanart=True + sample_images 存在 ──────────────────────────

class TestExtrafanartDownloaded:
    def test_extrafanart_downloaded(self):
        """邊界條件 20: write_extrafanart=True + sample_images → 下載 extrafanart"""
        video = _make_video(sample_images=["https://example.com/s1.jpg", "https://example.com/s2.jpg"])
        db_result = {"SONE-205": [video]}

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("os.makedirs"),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_extrafanart=True,
                overwrite_existing=True,
            )

        assert result.extrafanart_written == 2


# ── 21. write_extrafanart=True + 無 sample_images ────────────────────────────

class TestExtrafanartNoSamples:
    def test_extrafanart_no_samples(self):
        """邊界條件 21: write_extrafanart=True + 無 sample_images → extrafanart_written=0"""
        video = _make_video(sample_images=[])

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_extrafanart=True,
            )

        assert result.extrafanart_written == 0


# ── 22. NFO 路徑確實在影片同目錄 ─────────────────────────────────────────────

class TestNfoPathInSameDir:
    def test_nfo_path_in_same_dir_as_video(self):
        """邊界條件 22: generate_nfo output_path 必須在影片 parent 目錄"""
        video = _make_video()

        captured_calls = []

        def fake_generate_nfo(**kwargs):
            captured_calls.append(kwargs.get("output_path", ""))
            return True

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=fake_generate_nfo),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
            )

        assert captured_calls, "generate_nfo should have been called"
        output_path = Path(captured_calls[0])
        video_dir = Path(FS_PATH).parent
        assert output_path.parent == video_dir, (
            f"NFO path {output_path} is outside video dir {video_dir}"
        )


# ── 23. organize_file / shutil.move / os.makedirs 不被呼叫 ───────────────────

class TestNoForbiddenCalls:
    def test_organize_file_not_called(self):
        """邊界條件 23: organize_file、shutil.move 不被呼叫"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("shutil.move") as mock_move,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
            )

        mock_move.assert_not_called()
        assert result.success is True

    def test_makedirs_not_called_when_extrafanart_false(self):
        """邊界條件 23b: write_extrafanart=False 正常路徑 → os.makedirs 不被呼叫"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("os.makedirs") as mock_makedirs,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_extrafanart=False,
            )

        mock_makedirs.assert_not_called()
        assert result.success is True


# ── 24. generate_nfo PermissionError ─────────────────────────────────────────

class TestNfoPermissionError:
    def test_nfo_permission_error(self):
        """邊界條件 24: generate_nfo 拋 PermissionError → success=False，提示權限"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=PermissionError("Permission denied")),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
            )

        assert result.success is False
        assert "權限" in result.error or "寫入" in result.error


# ── 25. download_image 失敗 → cover_written=False，不影響 NFO ─────────────────

class TestImageDownloadFail:
    def test_image_download_fail_nfo_still_written(self):
        """邊界條件 25: download_image 失敗 → cover_written=False，nfo_written=True"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=False),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                write_cover=True,
                overwrite_existing=True,
            )

        assert result.cover_written is False
        assert result.nfo_written is True
        assert result.success is True


# ── 26. F1: _db_upsert 把 path 存成 file:/// URI ────────────────────────────────

class TestDbUpsertPathIsFileUri:
    """F1: _db_upsert path 必須為 file:/// URI"""

    def test_fs_path_converted_to_file_uri(self):
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)
        mock_repo.get_by_numbers.return_value = {}

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].path.startswith("file:///")

    def test_file_uri_input_not_double_wrapped(self):
        """已是 file:/// 的 fs_path 不應被雙重包裝（回歸測試）"""
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)
        mock_repo.get_by_numbers.return_value = {}

        # 注意：caller（enrich_single）應先 uri_to_fs_path 再傳入，
        # 但即使誤傳 URI，也不應變成 file:///file:///
        # 此處用 FS path 驗證正常 case
        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/mnt/c/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        path = captured[0].path
        assert path.startswith("file:///")
        assert "file:///file:///" not in path


# ── 26b. 89b-T2: _db_upsert 寫入 scrape_attempted_at ─────────────────────────

class TestDbUpsertScrapeAttemptedAt:
    """89b-T2: _db_upsert 成功路徑 Video 帶 scrape_attempted_at > 0（供 T3/T4 消費）"""

    def test_scrape_attempted_at_set(self):
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)
        mock_repo.get_by_numbers.return_value = {}
        mock_repo.get_by_path.return_value = None

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].scrape_attempted_at > 0


# ── 27. F1: _db_upsert cover_path 處理 ────────────────────────────

class TestDbUpsertCoverPath:
    """F1: cover_path 不寫遠端 URL；有本地封面時寫 file:/// URI；否則保留 DB 既有值"""

    def test_remote_url_not_written(self):
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)
        mock_repo.get_by_path.return_value = None

        meta = {"title": "T", "cover_url": "https://cdn.example.com/cover.jpg",
                "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        # 不傳 local_cover_path → 不應寫遠端 URL
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert not (captured[0].cover_path or "").startswith("http")

    @patch("os.path.exists", return_value=True)
    def test_local_cover_written_as_file_uri(self, _mock_exists):
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta,
                   local_cover_path="/video/SONE-205.jpg")

        assert len(captured) == 1
        assert captured[0].cover_path.startswith("file:///")

    def test_preserves_existing_db_cover_path_by_path(self):
        """沒有新封面時用 get_by_path 精確保留同一筆紀錄的 cover_path"""
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)

        existing_video = MagicMock()
        existing_video.cover_path = to_file_uri("C:/lib/SONE-205/cover.jpg")
        mock_repo.get_by_path.return_value = existing_video

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].cover_path == to_file_uri("C:/lib/SONE-205/cover.jpg")
        # 確認用 path URI 查詢，不是用 number
        mock_repo.get_by_path.assert_called_once()


# ── 27b. TASK-89a-T5 (CD-89a-5 / Codex C2): output_dir 保留（鏡射 TestDbUpsertCoverPath）──

class TestDbUpsertOutputDir:
    """C2 端到端回歸鎖：enricher 補完/重刮不得洗掉 producer 寫入的 output_dir。"""

    def test_c2_end_to_end_preserves_existing_output_dir(self):
        """existing.output_dir 非空（producer row）→ _db_upsert 寫入的 Video.output_dir
        必須等於原值（顯式保留，非僅依賴 T1 DB CASE-WHEN 兜底）。"""
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)

        existing_video = MagicMock()
        existing_video.output_dir = to_file_uri("/output/lib/SONE-205")
        existing_video.cover_path = ""
        existing_video.user_tags = []
        existing_video.sample_images = []
        mock_repo.get_by_path.return_value = existing_video

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].output_dir == to_file_uri("/output/lib/SONE-205")

    def test_no_existing_row_output_dir_defaults_empty(self):
        """existing is None（首次遇到此 path）→ output_dir 傳空字串，不炸，交由 T1
        DB CASE-WHEN 兜底（行為與現況一致，不 regress）。"""
        from core.enricher import _db_upsert

        captured = []
        mock_repo = MagicMock()
        mock_repo.upsert.side_effect = lambda v: captured.append(v)
        mock_repo.get_by_path.return_value = None

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].output_dir == ""


# ── 28. F2: has_subtitle 由 find_subtitle_files 決定 ────────────────────────────

class TestHasSubtitleDetected:
    def test_has_subtitle_true_when_srt_exists(self):
        """F2: 影片同目錄有 .srt 時，generate_nfo 應以 has_subtitle=True 呼叫"""
        video = _make_video()

        captured_calls = []

        def fake_generate_nfo(**kwargs):
            captured_calls.append(kwargs)
            return True

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=fake_generate_nfo),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=["/video/SONE-205.srt"]),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
            )

        assert result.success is True
        assert captured_calls, "generate_nfo 應被呼叫"
        assert captured_calls[0].get("has_subtitle") is True, (
            "有字幕檔時 has_subtitle 應為 True"
        )

    def test_has_subtitle_false_when_no_srt(self):
        """F2: 影片同目錄無字幕時，generate_nfo 應以 has_subtitle=False 呼叫"""
        video = _make_video()

        captured_calls = []

        def fake_generate_nfo(**kwargs):
            captured_calls.append(kwargs)
            return True

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=fake_generate_nfo),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
            )

        assert result.success is True
        assert captured_calls, "generate_nfo 應被呼叫"
        assert captured_calls[0].get("has_subtitle") is False, (
            "無字幕檔時 has_subtitle 應為 False"
        )


# ── 29. F3: series="" 應觸發 scraper ────────────────────────────────────────────

class TestMissingFieldsEmptySeries:
    def test_empty_series_string_triggers_scraper(self):
        """F3: _video_to_meta 把缺失 series 正規化為空字串，_missing_fields 應視為缺失"""
        video = _make_video(series="")  # 空字串，非 None
        db_result = {"SONE-205": [video]}
        scraper_data = _make_scraper_result(series="テストシリーズ")

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = db_result

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="fill_missing",
            )

        mock_search.assert_called_once(), "series='' 應視為缺失，觸發 scraper"
        assert result.success is True
        assert "series" in result.fields_filled


# ── T2: source / javbus_lang 參數路由 ─────────────────────────────────────────

class TestSourceParam:
    def test_source_passed_to_search_jav_refresh_full(self):
        """T2: source='javbus' 在 refresh_full mode 正確傳給 search_jav"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.search_jav", return_value=_make_scraper_result()) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.enricher.VideoRepository"),
        ):
            from core.enricher import enrich_single
            enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
                source="javbus",
            )
        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs.get("source") == "javbus"

    def test_javbus_lang_passed_to_search_jav(self):
        """T2: javbus_lang='ja' 正確傳給 search_jav"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.search_jav", return_value=_make_scraper_result()) as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.enricher.VideoRepository"),
        ):
            from core.enricher import enrich_single
            enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
                javbus_lang="ja",
            )
        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs.get("javbus_lang") == "ja"

    def test_invalid_source_returns_error(self):
        """T2: 無效 source 經 search_jav 攔截後回傳 None，enrich_single 回 error"""
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.VideoRepository"),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
                source="invalid_xyz",
            )
        assert result.success is False
        assert result.error is not None


# ── P1: scraper_data 參數傳入時跳過 search_jav ────────────────────────────────

class TestScraperDataSkipsSearchJav:
    def test_scraper_data_skips_search_jav(self):
        """P1: 傳入 scraper_data → search_jav 不應被呼叫（refresh_full mode）"""
        provided_data = _make_scraper_result()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.search_jav") as mock_search,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.enricher.VideoRepository"),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
                scraper_data=provided_data,
            )

        mock_search.assert_not_called()
        assert result.success is True


# ══════════════════════════════════════════════════════════════════════════════
# 72b-T6：_write_external_images + enrich_single external_manager 整合
# ══════════════════════════════════════════════════════════════════════════════

# ── T6-A. _write_external_images 單元測試（tmp_path 真實 JPEG）─────────────────

def _create_dummy_jpeg(path) -> None:
    """建立最小合法 JPEG（300×200 橫向圖，確保 crop_to_poster h/w < 1.0 走橫向裁切）。"""
    from PIL import Image
    img = Image.new("RGB", (300, 200), color=(128, 64, 32))
    img.save(str(path), "JPEG", quality=95)


class TestWriteExternalImages:
    """_write_external_images 契約：gate on cover_path.exists()、模式、overwrite。"""

    def test_off_mode_returns_false_false(self, tmp_path):
        """off 模式：直接 no-op 回 False/False，即使底圖存在。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "off", True)
        assert result == {"poster": False, "fanart": False}

    def test_no_cover_returns_false_false(self, tmp_path):
        """底圖不存在 → gate 落空 → False/False。"""
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", True)
        assert result == {"poster": False, "fanart": False}

    def test_jellyfin_creates_stem_poster_fanart(self, tmp_path):
        """jellyfin：產 {stem}-poster.jpg + {stem}-fanart.jpg，回傳 True/True。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", True)
        assert result == {"poster": True, "fanart": True}
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()

    def test_emby_creates_stem_poster_fanart(self, tmp_path):
        """emby：產 {stem}-poster.jpg + {stem}-fanart.jpg（等價 jellyfin/kodi），回傳 True/True。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "emby", True)
        assert result == {"poster": True, "fanart": True}
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()
        # 裸短名不存在
        assert not (tmp_path / "poster.jpg").exists()
        assert not (tmp_path / "fanart.jpg").exists()

    def test_kodi_creates_stem_poster_fanart(self, tmp_path):
        """kodi：產 {stem}-poster.jpg + {stem}-fanart.jpg（與 jellyfin 相同），回傳 True/True。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "kodi", True)
        assert result == {"poster": True, "fanart": True}
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()
        # 裸短名不存在
        assert not (tmp_path / "poster.jpg").exists()
        assert not (tmp_path / "fanart.jpg").exists()

    def test_overwrite_false_existing_skips_but_reports_true(self, tmp_path):
        """overwrite=False + 已有 poster/fanart → 跳過寫入，但回傳 True（磁碟存在）。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        poster = tmp_path / "SONE-205-poster.jpg"
        fanart = tmp_path / "SONE-205-fanart.jpg"
        poster.write_bytes(b"existing")
        fanart.write_bytes(b"existing")
        poster_mtime = poster.stat().st_mtime
        fanart_mtime = fanart.stat().st_mtime

        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", False)
        assert result == {"poster": True, "fanart": True}
        # 檔案未被覆蓋（mtime 不變）
        assert poster.stat().st_mtime == poster_mtime
        assert fanart.stat().st_mtime == fanart_mtime

    def test_overwrite_true_overwrites_existing(self, tmp_path):
        """overwrite=True → 即使已存在也重產（fanart 應比 existing dummy 大）。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        fanart = tmp_path / "SONE-205-fanart.jpg"
        fanart.write_bytes(b"tiny")  # 比真實 JPEG 小

        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", True)
        assert result["fanart"] is True
        assert fanart.stat().st_size > 4  # 覆蓋後應為真實 JPEG

    def test_unknown_manager_returns_false_false(self, tmp_path):
        """未知 external_manager 值 → 不產圖、不崩。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "unknown_mode", True)
        assert result == {"poster": False, "fanart": False}

    def test_no_cover_but_stem_poster_fanart_exist_returns_true(self, tmp_path):
        """72d-P2B：無 {stem}.jpg，但 stem-poster + stem-fanart 皆存在，overwrite=False
        → {"poster": True, "fanart": True}，且兩檔內容不被修改（無 copy/crop）。"""
        # 不建立 {stem}.jpg（cover）
        poster = tmp_path / "SONE-205-poster.jpg"
        fanart = tmp_path / "SONE-205-fanart.jpg"
        poster.write_bytes(b"existing-poster")
        fanart.write_bytes(b"existing-fanart")
        poster_content = poster.read_bytes()
        fanart_content = fanart.read_bytes()

        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", False)

        assert result == {"poster": True, "fanart": True}
        # 檔案未被覆蓋（bytes 不變）
        assert poster.read_bytes() == poster_content
        assert fanart.read_bytes() == fanart_content

    def test_no_cover_stem_poster_only_partial_return(self, tmp_path):
        """72d-P2B：無 {stem}.jpg，只有 stem-poster.jpg（無 fanart），overwrite=False
        → {"poster": True, "fanart": False}。"""
        # 不建立 {stem}.jpg（cover）
        poster = tmp_path / "SONE-205-poster.jpg"
        poster.write_bytes(b"existing-poster")
        # 不建立 fanart

        from core.enricher import _write_external_images
        result = _write_external_images(str(tmp_path / "SONE-205.mp4"), "jellyfin", False)

        assert result == {"poster": True, "fanart": False}


# ── T6-B. enrich_single external_manager 整合測試（mock scraper/DB/generate_nfo）──

class TestEnrichSingleExternalManager:
    """enrich_single 整合：external_manager 穿線 + 寫序 + NFO has_poster/has_fanart。"""

    def _make_mock_repo(self):
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {"SONE-205": [_make_video()]}
        mock_repo.get_by_path.return_value = None
        return mock_repo

    def test_off_mode_no_external_images(self, tmp_path):
        """off 模式：不產 poster/fanart，generate_nfo has_poster/has_fanart=False。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="off",
            )

        assert result.success is True
        # off 模式 → 無外部圖
        assert not (tmp_path / "SONE-205-poster.jpg").exists()
        assert not (tmp_path / "SONE-205-fanart.jpg").exists()
        assert not (tmp_path / "poster.jpg").exists()
        assert not (tmp_path / "fanart.jpg").exists()
        # generate_nfo 收到的 external_manager 應為 off（或未傳，即 default off）
        if captured:
            assert captured[0].get("external_manager", "off") == "off"
            assert captured[0].get("has_poster", False) is False
            assert captured[0].get("has_fanart", False) is False

    def test_jellyfin_creates_images_nfo_has_poster_fanart(self, tmp_path):
        """jellyfin：cover 已存在 → 產 {stem}-poster/-fanart，NFO has_poster/has_fanart=True。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is True
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()
        assert captured, "generate_nfo 應被呼叫"
        assert captured[0].get("external_manager") == "jellyfin"
        assert captured[0].get("has_poster") is True
        assert captured[0].get("has_fanart") is True

    def test_kodi_creates_stem_images_nfo_has_poster_fanart(self, tmp_path):
        """kodi：產 {stem}-poster.jpg + {stem}-fanart.jpg（與 jellyfin 相同），NFO has_poster/has_fanart=True。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        assert result.success is True
        # kodi 固定 stem 命名（與 jellyfin 相同）
        assert (tmp_path / "SONE-205-poster.jpg").exists(), "kodi 應產 stem-poster.jpg"
        assert (tmp_path / "SONE-205-fanart.jpg").exists(), "kodi 應產 stem-fanart.jpg"
        assert not (tmp_path / "poster.jpg").exists(), "kodi 不應有裸 poster.jpg"
        assert not (tmp_path / "fanart.jpg").exists(), "kodi 不應有裸 fanart.jpg"
        assert captured, "generate_nfo 應被呼叫"
        assert captured[0].get("external_manager") == "kodi"
        assert captured[0].get("has_poster") is True
        assert captured[0].get("has_fanart") is True

    def test_cover_preexists_overwrite_false_still_produces_external_images(self, tmp_path):
        """落點 2：.jpg 預存 + overwrite=False → _write_cover 回 False，但底圖在磁碟 →
        _write_external_images gate cover_path.exists() → poster/fanart 仍產出；
        NFO has_poster/has_fanart=True。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=True,   # 開著，但 cover 已存在 + overwrite=False
                overwrite_existing=False,
                external_manager="jellyfin",
            )

        assert result.success is True
        # cover_written=False（gate: cover 已存在 + overwrite=False）
        assert result.cover_written is False
        # 但外部圖仍產出（gate on cover_path.exists()，不是 cover_written）
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()
        # NFO has_poster/has_fanart=True
        assert captured, "generate_nfo 應被呼叫"
        assert captured[0].get("has_poster") is True
        assert captured[0].get("has_fanart") is True

    def test_reorder_nfo_written_after_images(self, tmp_path):
        """寫序驗證：external 模式 NFO 在圖片後寫入 → generate_nfo 呼叫時 poster 已存在。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        write_order: list = []

        def fake_nfo(**kwargs):
            # 記錄呼叫時 poster 是否存在（應已存在）
            poster_exists = (tmp_path / "SONE-205-poster.jpg").exists()
            write_order.append(("nfo", poster_exists))

        original_copy2 = __import__("shutil").copy2

        def spy_copy2(src, dst):
            write_order.append(("copy2", Path(dst).name))
            return original_copy2(src, dst)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.enricher.shutil.copy2", side_effect=spy_copy2),
        ):
            from core.enricher import enrich_single
            enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        # NFO 應在 copy2（fanart）之後
        nfo_calls = [i for i, (kind, _) in enumerate(write_order) if kind == "nfo"]
        copy2_calls = [i for i, (kind, _) in enumerate(write_order) if kind == "copy2"]
        assert nfo_calls, "generate_nfo 應被呼叫"
        assert copy2_calls, "shutil.copy2 (fanart) 應被呼叫"
        assert min(nfo_calls) > max(copy2_calls), (
            "NFO 應在 fanart copy2 之後寫入；實際寫序：" + str(write_order)
        )
        # 且 generate_nfo 呼叫時 poster 已存在
        _, poster_present = write_order[nfo_calls[0]]
        assert poster_present, "generate_nfo 被呼叫時 poster 應已存在"

    def test_no_cover_no_external_images(self, tmp_path):
        """無底圖：.jpg 不存在 → external images 不產出，NFO has_* False。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        # 不建立 cover.jpg

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is True
        assert not (tmp_path / "SONE-205-poster.jpg").exists()
        assert not (tmp_path / "SONE-205-fanart.jpg").exists()
        if captured:
            assert captured[0].get("has_poster", False) is False
            assert captured[0].get("has_fanart", False) is False

    def test_permission_error_nfo_external_mode(self, tmp_path):
        """PermissionError on NFO（external 模式）→ success=False，提示權限。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo()),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=PermissionError("read-only")),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is False
        assert "權限" in result.error or "寫入" in result.error

    def test_extrafanart_untouched_in_external_mode(self, tmp_path):
        """_write_extrafanart 在 external 模式仍由 write_extrafanart=False 控制（不被呼叫）。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        mock_repo = self._make_mock_repo()
        mock_repo.get_by_numbers.return_value = {"SONE-205": [_make_video(
            sample_images=["https://example.com/s1.jpg"]
        )]}

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo"),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=False,
                write_cover=False,
                write_extrafanart=False,  # 預設關閉
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.extrafanart_written == 0
        assert not (tmp_path / "extrafanart").exists()


# ══════════════════════════════════════════════════════════════════════════════
# 72c-codexP1：kodi 多片共用資料夾 stem 命名（E1/E2/E3/E4）
# ══════════════════════════════════════════════════════════════════════════════


class TestKodiStemNaming:
    """E1/E2/E3/E4：kodi 模式 stem/短名切換 + 多片不碰撞（72c-codexP1）"""

    def _make_mock_repo_for(self, number: str):
        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {number: [_make_video(number=number)]}
        mock_repo.get_by_path.return_value = None
        # db_path 設 in-memory：避免 enrich nfo_mtime 更新路徑（enricher.py:525
        # get_connection(repo.db_path)）對 MagicMock 做 sqlite3.connect → 在 repo root
        # 產生 "<MagicMock ...>" 垃圾檔。:memory: 下該 UPDATE 因無 videos 表靜默失敗
        # （已被 try/except 包裹），不留任何檔案。
        mock_repo.db_path = ":memory:"
        return mock_repo

    def test_E1_kodi_two_videos_stem_named_no_collision(self, tmp_path):
        """E1：kodi + 同資料夾 2 片 → 各得 {stem}-poster.jpg/{stem}-fanart.jpg；
        無共用 poster.jpg；各 NFO <poster> 各指自己 stem。"""
        # 建立 2 個 mp4 + 各自封面
        mp4_a = tmp_path / "SONE-205.mp4"
        mp4_b = tmp_path / "MIDE-001.mp4"
        mp4_a.touch()
        mp4_b.touch()
        cover_a = tmp_path / "SONE-205.jpg"
        cover_b = tmp_path / "MIDE-001.jpg"
        _create_dummy_jpeg(cover_a)
        _create_dummy_jpeg(cover_b)

        captured_a = []
        captured_b = []

        def fake_nfo_a(**kwargs):
            captured_a.append(kwargs)

        def fake_nfo_b(**kwargs):
            captured_b.append(kwargs)

        # 處理第一片 SONE-205
        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("SONE-205")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo_a),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result_a = enrich_single(
                file_path=str(mp4_a),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        # 處理第二片 MIDE-001
        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("MIDE-001")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo_b),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result_b = enrich_single(
                file_path=str(mp4_b),
                number="MIDE-001",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        assert result_a.success is True
        assert result_b.success is True

        # E1：各得 stem 命名
        assert (tmp_path / "SONE-205-poster.jpg").exists(), "A 應產 stem poster"
        assert (tmp_path / "SONE-205-fanart.jpg").exists(), "A 應產 stem fanart"
        assert (tmp_path / "MIDE-001-poster.jpg").exists(), "B 應產 stem poster"
        assert (tmp_path / "MIDE-001-fanart.jpg").exists(), "B 應產 stem fanart"

        # E1：不存在共用短名（kodi 固定 stem 長格式）
        assert not (tmp_path / "poster.jpg").exists(), "共用 poster.jpg 不應存在"
        assert not (tmp_path / "fanart.jpg").exists(), "共用 fanart.jpg 不應存在"

        # E1：generate_nfo 均被呼叫且 external_manager='kodi'
        assert captured_a, "SONE-205 generate_nfo 應被呼叫"
        assert captured_b, "MIDE-001 generate_nfo 應被呼叫"
        assert captured_a[0].get("external_manager") == "kodi"
        assert captured_b[0].get("external_manager") == "kodi"

    def test_E2_kodi_single_video_stem_named(self, tmp_path):
        """E2：kodi + 同資料夾僅 1 片 → 仍使用 stem 命名（固定行為，與 jellyfin 相同）。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("SONE-205")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        assert result.success is True

        # E2：stem 命名（kodi 固定長格式）
        assert (tmp_path / "SONE-205-poster.jpg").exists(), "kodi 應產 {stem}-poster.jpg"
        assert (tmp_path / "SONE-205-fanart.jpg").exists(), "kodi 應產 {stem}-fanart.jpg"

        # E2：裸短名不存在
        assert not (tmp_path / "poster.jpg").exists(), "kodi 不應有裸 poster.jpg"
        assert not (tmp_path / "fanart.jpg").exists(), "kodi 不應有裸 fanart.jpg"

        # E2：generate_nfo 呼叫帶 external_manager='kodi'
        assert captured, "generate_nfo 應被呼叫"
        assert captured[0].get("external_manager") == "kodi"

    def test_E3_kodi_two_videos_overwrite_true_no_cross_contamination(self, tmp_path):
        """E3：kodi 2 片 + overwrite_existing=True → 第二片不覆蓋第一片 artwork（路徑互異）。"""
        mp4_a = tmp_path / "SONE-205.mp4"
        mp4_b = tmp_path / "MIDE-001.mp4"
        mp4_a.touch()
        mp4_b.touch()
        cover_a = tmp_path / "SONE-205.jpg"
        cover_b = tmp_path / "MIDE-001.jpg"
        _create_dummy_jpeg(cover_a)
        _create_dummy_jpeg(cover_b)

        # 處理第一片
        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("SONE-205")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo"),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            enrich_single(
                file_path=str(mp4_a),
                number="SONE-205",
                write_nfo=False,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        # 記錄第一片 artwork mtime
        poster_a = tmp_path / "SONE-205-poster.jpg"
        fanart_a = tmp_path / "SONE-205-fanart.jpg"
        assert poster_a.exists(), "E3 前置：A poster 應存在"
        mtime_a_poster = poster_a.stat().st_mtime
        mtime_a_fanart = fanart_a.stat().st_mtime

        # 處理第二片
        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("MIDE-001")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo"),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            enrich_single(
                file_path=str(mp4_b),
                number="MIDE-001",
                write_nfo=False,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        # E3：A 的 artwork 不被 B 覆蓋（路徑互異，mtime 不變）
        assert poster_a.stat().st_mtime == mtime_a_poster, "A poster 不應被 B 覆蓋"
        assert fanart_a.stat().st_mtime == mtime_a_fanart, "A fanart 不應被 B 覆蓋"
        # B 有自己的 artwork
        assert (tmp_path / "MIDE-001-poster.jpg").exists(), "B 應有自己的 poster"
        assert (tmp_path / "MIDE-001-fanart.jpg").exists(), "B 應有自己的 fanart"

    def test_E4_jellyfin_unchanged(self, tmp_path):
        """E4：jellyfin 行為不變（回歸）— stem 命名，NFO external_manager='jellyfin'。"""
        mp4_a = tmp_path / "SONE-205.mp4"
        mp4_b = tmp_path / "MIDE-001.mp4"
        mp4_a.touch()
        mp4_b.touch()
        cover_a = tmp_path / "SONE-205.jpg"
        cover_b = tmp_path / "MIDE-001.jpg"
        _create_dummy_jpeg(cover_a)
        _create_dummy_jpeg(cover_b)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        # 只測第一片（jellyfin 的 stem 命名本就 per-video，回歸即可）
        with (
            patch("core.enricher.VideoRepository", return_value=MagicMock(
                **{"get_by_numbers.return_value": {"SONE-205": [_make_video()]},
                   "get_by_path.return_value": None}
            )),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4_a),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is True
        # jellyfin：stem 命名
        assert (tmp_path / "SONE-205-poster.jpg").exists()
        assert (tmp_path / "SONE-205-fanart.jpg").exists()
        # E4：NFO external_manager='jellyfin'
        assert captured
        assert captured[0].get("external_manager") == "jellyfin"
        assert captured[0].get("has_poster") is True
        assert captured[0].get("has_fanart") is True

    def test_E4_off_unchanged(self, tmp_path):
        """E4 off：off 模式不寫 external images（回歸）。"""
        mp4 = tmp_path / "SONE-205.mp4"
        mp4.touch()
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)

        with (
            patch("core.enricher.VideoRepository", return_value=MagicMock(
                **{"get_by_numbers.return_value": {"SONE-205": [_make_video()]},
                   "get_by_path.return_value": None}
            )),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo"),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number="SONE-205",
                write_nfo=False,
                write_cover=False,
                overwrite_existing=True,
                external_manager="off",
            )

        assert result.success is True
        # off 模式：無任何 poster/fanart
        assert not (tmp_path / "poster.jpg").exists()
        assert not (tmp_path / "fanart.jpg").exists()
        assert not (tmp_path / "SONE-205-poster.jpg").exists()
        assert not (tmp_path / "SONE-205-fanart.jpg").exists()

    def test_E5_uri_input_kodi_stem_named(self, tmp_path):
        """E5：enrich_single 接收 file:/// URI（production path）時，
        kodi → stem 命名（固定，不論 sibling video 數量）。"""
        mp4_a = tmp_path / "SONE-205.mp4"
        mp4_b = tmp_path / "MIDE-001.mp4"
        mp4_a.touch()
        mp4_b.touch()
        cover_a = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover_a)

        captured = []

        def fake_nfo(**kwargs):
            captured.append(kwargs)

        # 關鍵：file_path 用 to_file_uri 包裝成 file:/// URI（模擬 web API 傳入）
        file_uri = to_file_uri(str(mp4_a))

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("SONE-205")),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", side_effect=fake_nfo),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=file_uri,
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        assert result.success is True, f"enrich_single 應成功，error={result.error}"
        # URI input 下 kodi 固定 stem 命名
        assert captured, "generate_nfo 應被呼叫"
        assert captured[0].get("external_manager") == "kodi"
        # 磁碟上應有 stem 命名 artwork
        assert (tmp_path / "SONE-205-poster.jpg").exists(), "URI input 下應產 stem poster"
        assert (tmp_path / "SONE-205-fanart.jpg").exists(), "URI input 下應產 stem fanart"
        assert not (tmp_path / "poster.jpg").exists(), "URI input 下不應有共用 poster.jpg"

    def test_E6_kodi_nfo_disk_content_stem_names(self, tmp_path):
        """E6（disk 驗證）：kodi → 寫入磁碟的 NFO <poster>/<fanart>
        包含 {stem}-poster.jpg/{stem}-fanart.jpg，且不含 bare poster.jpg。
        不 mock generate_nfo — 驗證 NFO 實際寫入內容。"""
        import xml.etree.ElementTree as ET

        mp4_a = tmp_path / "SONE-205.mp4"
        mp4_b = tmp_path / "MIDE-001.mp4"
        mp4_a.touch()
        mp4_b.touch()
        cover_a = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover_a)

        with (
            patch("core.enricher.VideoRepository", return_value=self._make_mock_repo_for("SONE-205")),
            patch("core.enricher.search_jav", return_value=None),
            # generate_nfo NOT mocked — 真實寫 NFO 到磁碟
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4_a),
                number="SONE-205",
                write_nfo=True,
                write_cover=False,
                overwrite_existing=True,
                external_manager="kodi",
            )

        assert result.success is True, f"enrich_single 應成功，error={result.error}"
        assert result.nfo_written is True, "NFO 應寫出"

        nfo_path = tmp_path / "SONE-205.nfo"
        assert nfo_path.exists(), "NFO 檔應存在於磁碟"

        tree = ET.parse(str(nfo_path))
        root = tree.getroot()

        poster_elem = root.find("poster")
        fanart_elem = root.find("fanart")
        assert poster_elem is not None, "NFO 應有 <poster> 標籤"
        assert fanart_elem is not None, "NFO 應有 <fanart> 標籤"

        poster_text = poster_elem.text or ""
        fanart_text = fanart_elem.text or ""

        # kodi 固定 stem 命名
        assert "SONE-205-poster" in poster_text, (
            f"NFO <poster> 應含 stem 命名（SONE-205-poster），實際：{poster_text!r}"
        )
        assert "SONE-205-fanart" in fanart_text, (
            f"NFO <fanart> 應含 stem 命名（SONE-205-fanart），實際：{fanart_text!r}"
        )
        assert poster_text.strip() != "poster.jpg", (
            "NFO <poster> 不應是 bare 'poster.jpg'"
        )
        assert fanart_text.strip() != "fanart.jpg", (
            "NFO <fanart> 不應是 bare 'fanart.jpg'"
        )


# ── TASK-91-T3: 站台 1/2/3 — uri_to_local_fs_path WSL+UNC path_mappings 反解 ──

_WSL_UNC_MAPPINGS = {"/home/user/nas": "//NAS/share"}
_WSL_UNC_URI = "file://///NAS/share/dir/movie.mp4"
_WSL_UNC_REVERSED = "/home/user/nas/dir/movie.mp4"


class TestEnrichSinglePathMappingReverse:
    """站台1（enrich_single :358）：fs_path 必須是 path_mappings 反解後的本機路徑，
    不是裸 uri_to_fs_path 產出的 UNC 字面值（mutation-sensitive）。"""

    def test_wsl_unc_mapping_reverses_fs_path(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        captured = []

        def fake_exists(p):
            captured.append(p)
            return False  # 提早以「檔案不存在」return，不需 mock 整條 pipeline

        with patch("os.path.exists", side_effect=fake_exists):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.error == "檔案不存在"
        assert captured, "os.path.exists 應被呼叫"
        assert captured[0] == _WSL_UNC_REVERSED, (
            f"fs_path 應反解為本機路徑 {_WSL_UNC_REVERSED}，實際: {captured[0]!r}"
        )

    def test_non_file_uri_fallback_passthrough_unchanged(self, monkeypatch):
        """邊界4：非 file:/// 輸入的 try/except passthrough 不可回歸。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        bare_path = "just-a-bare-local-string-not-a-uri"
        captured = []

        def fake_exists(p):
            captured.append(p)
            return False

        with patch("os.path.exists", side_effect=fake_exists):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=bare_path,
                number="SONE-205",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.error == "檔案不存在"
        assert captured[0] == bare_path, (
            f"非 URI 輸入應原樣 passthrough，實際: {captured[0]!r}"
        )


class TestFetchSamplesOnlyPathMappingReverse:
    """站台2（fetch_samples_only :618）：同站台1的反解行為。"""

    def test_wsl_unc_mapping_reverses_fs_path(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        captured = []

        def fake_exists(p):
            captured.append(p)
            return False

        with patch("os.path.exists", side_effect=fake_exists):
            from core.enricher import fetch_samples_only
            result = fetch_samples_only(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.error == "檔案不存在"
        assert captured, "os.path.exists 應被呼叫"
        assert captured[0] == _WSL_UNC_REVERSED, (
            f"fs_path 應反解為本機路徑 {_WSL_UNC_REVERSED}，實際: {captured[0]!r}"
        )

    def test_non_file_uri_fallback_passthrough_unchanged(self, monkeypatch):
        """邊界4：非 file:/// 輸入的 try/except passthrough 不可回歸。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        bare_path = "just-a-bare-local-string-not-a-uri"
        captured = []

        def fake_exists(p):
            captured.append(p)
            return False

        with patch("os.path.exists", side_effect=fake_exists):
            from core.enricher import fetch_samples_only
            result = fetch_samples_only(
                file_path=bare_path,
                number="SONE-205",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.error == "檔案不存在"
        assert captured[0] == bare_path, (
            f"非 URI 輸入應原樣 passthrough，實際: {captured[0]!r}"
        )


class TestResolveNfoCoverPathsMappingReverse:
    """站台3（resolve_nfo_cover_paths :667）：純函式，直接測反解後的 nfo/cover 路徑。"""

    def test_wsl_unc_mapping_reverses_paths(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        from core.enricher import resolve_nfo_cover_paths
        nfo_path, cover_path = resolve_nfo_cover_paths(
            _WSL_UNC_URI,
            path_mappings=_WSL_UNC_MAPPINGS,
        )

        assert nfo_path == "/home/user/nas/dir/movie.nfo", (
            f"nfo_path 應反解為本機路徑，實際: {nfo_path!r}"
        )
        assert cover_path == "/home/user/nas/dir/movie.jpg", (
            f"cover_path 應反解為本機路徑，實際: {cover_path!r}"
        )

    def test_non_file_uri_fallback_passthrough_unchanged(self, monkeypatch):
        """邊界4：非 file:/// 輸入的 try/except passthrough 不可回歸。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        bare_path = "just-a-bare-local-string-not-a-uri"
        from core.enricher import resolve_nfo_cover_paths
        nfo_path, cover_path = resolve_nfo_cover_paths(
            bare_path,
            path_mappings=_WSL_UNC_MAPPINGS,
        )

        assert nfo_path == bare_path + ".nfo"
        assert cover_path == bare_path + ".jpg"


# ── TASK-91 Codex Finding 1: DB key 必須維持映射命名空間，不可用反解後本機路徑 ──
# 反例：若 fs_path_for_db 被誤還原為 fs_path（反解後本機路徑），DB round-trip
# （get_by_path / update_scrape_attempted_at / nfo_mtime WHERE path=?）永遠對不上
# DB 既有 row（DB 存的是映射端 UNC URI）。Mutation-sensitive：revert 該行 → 下列全 RED。

class TestEnrichSingleDbKeyMappingPreserved:
    """站台1 DB key（enrich_single）：get_by_path / update_scrape_attempted_at 必須用
    fs_path_for_db（裸 uri_to_fs_path，維持 DB 映射命名空間），不是反解後 fs_path。"""

    def test_not_found_branch_marks_scrape_attempted_at_with_mapped_key(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=None),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                mode="refresh_full",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.success is False
        mock_repo.update_scrape_attempted_at.assert_called_once()
        call_args = mock_repo.update_scrape_attempted_at.call_args[0]
        assert call_args[0] == _WSL_UNC_URI, (
            f"DB key 必須維持映射命名空間（{_WSL_UNC_URI!r}），"
            f"不可用反解後本機路徑組出的 URI，實際: {call_args[0]!r}"
        )

    def test_get_by_path_uses_mapped_db_key(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            mock_repo.get_by_path.return_value = None

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                mode="fill_missing",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.success is True
        # v0.11.9 起 get_by_path 在 enrich_single 內被呼叫兩次：一次讀 user_tags
        # （既有行為），一次是 Codex P1 修正新增的「reason=hit 鏡射 /thumb gate」
        # DB 最終狀態重讀（core/enricher.py 尾段）。兩次都必須用映射命名空間查 DB。
        assert mock_repo.get_by_path.call_count == 2
        for call in mock_repo.get_by_path.call_args_list:
            called_uri = call[0][0]
            assert called_uri == _WSL_UNC_URI, (
                f"get_by_path 必須用映射命名空間查 DB（{_WSL_UNC_URI!r}），實際: {called_uri!r}"
            )


class TestDbUpsertCoverAndSampleUrisForwardMapped:
    """TASK-91 Finding 1 extension：新產生的 cover / extrafanart 磁碟路徑寫回 DB 前，
    必須 forward-map 回映射命名空間（cover/sample 是新產生的磁碟路徑，不是自描述輸入，
    走 to_file_uri(local_path, path_mappings) 正向 pattern，非 uri-no-reverse pattern）。"""

    def test_full_flow_cover_and_sample_uris_are_mapped(self, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        scraper_data = _make_scraper_result()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("os.makedirs"),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}
            mock_repo.get_by_path.return_value = None
            captured = []
            mock_repo.upsert.side_effect = lambda v: captured.append(v)

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                mode="refresh_full",
                write_extrafanart=True,
                overwrite_existing=True,
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.success is True
        assert len(captured) == 1
        video = captured[0]
        assert video.path == _WSL_UNC_URI, (
            f"DB row path 必須是映射命名空間，實際: {video.path!r}"
        )
        assert video.cover_path.startswith("file://///NAS/share/dir/"), (
            f"cover_path 應 forward-map 回映射命名空間，不應殘留反解後本機路徑，實際: {video.cover_path!r}"
        )
        assert video.sample_images, "extrafanart 應有實際寫入"
        for uri in video.sample_images:
            assert uri.startswith("file://///NAS/share/dir/extrafanart/"), (
                f"sample_images 應 forward-map 回映射命名空間，實際: {uri!r}"
            )

    def test_fetch_samples_only_sample_uris_are_mapped(self, monkeypatch):
        """站台2（fetch_samples_only）：_db_upsert_samples_only 用 fs_path_for_db 當 key，
        _write_extrafanart 產生的 sample uri 亦需 forward-map。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        meta = {"sample_images": ["https://example.com/s1.jpg"], "source": "javbus"}

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=meta),
            patch("core.enricher.download_image", return_value=True),
            patch("os.makedirs"),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo

            from core.enricher import fetch_samples_only
            result = fetch_samples_only(
                file_path=_WSL_UNC_URI,
                number="SONE-205",
                path_mappings=_WSL_UNC_MAPPINGS,
            )

        assert result.success is True
        mock_repo.update_sample_images.assert_called_once()
        call_args = mock_repo.update_sample_images.call_args[0]
        assert call_args[0] == _WSL_UNC_URI, (
            f"update_sample_images DB key 必須維持映射命名空間，實際: {call_args[0]!r}"
        )
        for uri in call_args[1]:
            assert uri.startswith("file://///NAS/share/dir/extrafanart/"), (
                f"sample uri 應 forward-map 回映射命名空間，實際: {uri!r}"
            )
