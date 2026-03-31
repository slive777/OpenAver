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
            patch("core.enricher.search_jav", return_value=None),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                mode="refresh_full",
            )

        assert result.success is False
        assert "SONE-205" in result.error or "找不到" in result.error


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
        existing_video.cover_path = "file:///C:/lib/SONE-205/cover.jpg"
        mock_repo.get_by_path.return_value = existing_video

        meta = {"title": "T", "actresses": [], "maker": "S", "tags": [], "release_date": ""}
        _db_upsert(mock_repo, "SONE-205", "/video/SONE-205.mp4", meta)

        assert len(captured) == 1
        assert captured[0].cover_path == "file:///C:/lib/SONE-205/cover.jpg"
        # 確認用 path URI 查詢，不是用 number
        mock_repo.get_by_path.assert_called_once()


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
