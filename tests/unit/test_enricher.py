"""
test_enricher.py - core/enricher.py TDD-lite 單元測試（full mock）

涵蓋 TASK-T4.md 的 25 個邊界條件
"""

import io
import os
import xml.etree.ElementTree as ET
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from core.path_utils import to_file_uri
from tests.conftest import MOCK_FOCAL_XY
from core.focal.subprocess_runner import RunnerOutcome


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


# ── 2. number 為空 ────────────────────────────────────────────────────────────


# ── 4. fill_missing: DB 完整，不打 scraper ────────────────────────────────────


# ── 4b. fill_missing: DB 有完整欄位但缺 label → 觸發 scraper ─────────────────

class TestFillMissingLabelMissing:
    @pytest.mark.parametrize(
        ("video_kwargs", "scraper_kwargs", "expected_filled_any"),
        [
            pytest.param({"label": ""}, {}, ("label",), id="label_empty"),
        ],
    )
    def test_db_missing_label_calls_scraper(self, video_kwargs, scraper_kwargs, expected_filled_any):
        """邊界條件 4b／5／F3: DB 有資料但缺 label／director+series（None）／series（空字串，
        _video_to_meta 把缺失 series 正規化為空字串，_missing_fields 應視為缺失）→ 觸發 scraper"""
        video = _make_video(**video_kwargs)
        db_result = {"SONE-205": [video]}
        scraper_data = _make_scraper_result(**scraper_kwargs)

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
        assert any(f in result.fields_filled for f in expected_filled_any)


# ── 7. fill_missing: DB miss + NFO 不存在 ────────────────────────────────────


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


# ── 10. db_to_sidecar: DB miss → error ───────────────────────────────────────


# ── 11. db_to_sidecar: 封面 URL 缺失 → cover_written=False ───────────────────


# ── 12. refresh_full: 強制打 scraper ─────────────────────────────────────────


# ── 13. refresh_full: scraper 失敗 ───────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# TASK-135-T4：NFO-only 欄位保留（plot/rating/url）＋ rating ÷2
# ══════════════════════════════════════════════════════════════════════════════
#
# CD-135-5：只讀三個 tag（plot/rating/website），rating 讀回時除以 2
# （寫入端 core/organizer.py 的 × 2 相消）。
# CD-135-13：判準問 scraper_data 的 key presence（映射前），不是 meta 的 truthiness
# （映射後）——`_summary: ""` 是「AI 審過了、就是要空」的合法指令，不得被 fallback
# 用既有 NFO 的舊值蓋掉。

_T4_NFO_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <plot>{plot}</plot>
  <rating>{rating}</rating>
  <website>{website}</website>
</movie>
"""


def _t4_write_nfo(nfo_path, plot="既有劇情", rating="7.0", website="http://existing.example/"):
    nfo_path.write_text(
        _T4_NFO_TEMPLATE.format(plot=plot, rating=rating, website=website),
        encoding="utf-8",
    )


class TestPreserveNfoOnlyFields:
    """DoD-1／DoD-2／DoD-4／DoD-5 ＋ 早退設計決策：直接對 `_preserve_nfo_only_fields()`
    單元測試（不透過完整 `enrich_single()`）。"""

    # ── DoD-1: key 不存在 → 讀既有 NFO（三欄各一案例，六案例矩陣的前三個）───

    @pytest.mark.parametrize(
        ("nfo_kwargs", "scraper_data", "meta_key", "expected"),
        [
            pytest.param(
                {"plot": "既有劇情"},
                # 刻意不帶 _summary key
                {"_rating": 3.5, "url": "http://ai.example/"},
                "summary", "既有劇情", id="summary_key_missing",
            ),
        ],
    )
    def test_summary_key_missing_falls_back_to_nfo_plot(self, tmp_path, nfo_kwargs, scraper_data, meta_key, expected):
        from core.enricher import _preserve_nfo_only_fields, _scraper_to_meta
        fs_path = str(tmp_path / "SONE-205.mp4")
        _t4_write_nfo(tmp_path / "SONE-205.nfo", **nfo_kwargs)
        meta = _scraper_to_meta(scraper_data)

        _preserve_nfo_only_fields(meta, scraper_data, fs_path)

        assert meta[meta_key] == expected


    # ── DoD-2: key 存在但值為空 → 不讀 NFO（CD-135-13，三欄各一案例，
    #    與 DoD-1 合計六個獨立案例，不能只寫三個） ─────────────────────────


    # ── DoD-4: 既有 NFO 不存在 → 不炸 ──────────────────────────────────────


    # ── DoD-5: <rating> 內容不是數字（第三方 NFO 手改壞掉）→ 不炸、留空 ────


    # ── 設計決策：三欄全在 scraper_data → 早退，不開檔（效能，非語意合併）──


class TestEnrichSingleRefreshFullRatingRoundtrip:
    """DoD-3：對同一個檔案連續跑兩次 `refresh_full`（都不帶 `_rating`）→ 寫出的 NFO
    `<rating>` 兩次都是 `7.0`，不是 `14.0`（NFO 寫入端 × 2、T4 讀回端 ÷ 2 相消）。

    BE-TEST-11：兩次呼叫都必須帶 `overwrite_existing=True`——否則 `_write_nfo()` 在
    NFO 已存在時直接 `return False` 不寫檔，兩次呼叫都是 no-op，翻倍與否測不出來
    （假綠）。
    """

    def _run_refresh_full(self, tmp_path):
        video_path = tmp_path / "SONE-205.mp4"
        if not video_path.exists():
            video_path.write_bytes(b"fake video bytes")
        # 刻意不帶 _rating —— round-trip 只驗這一格；_summary/url 都帶，避免
        # 那兩欄的 fallback 干擾本測試只想驗證的 rating 行為。
        scraper_data = {
            "title": "T",
            "_summary": "AI 審過的新劇情",
            "url": "http://ai.example/",
        }

        mock_repo = MagicMock()
        mock_repo.get_by_path.return_value = None
        mock_repo.get_by_numbers.return_value = {}
        # db_path 設 :memory: —— 避免 _sync_nfo_mtime 對 MagicMock 做
        # sqlite3.connect() 在 repo root 產生 "<MagicMock ...>" 垃圾檔（見
        # TestKodiStemNaming._make_mock_repo_for 同款防護）。:memory: 下該 UPDATE
        # 因無 videos 表靜默失敗（已被 try/except 包裹），不留任何檔案。
        mock_repo.db_path = ":memory:"

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=scraper_data),
            patch("core.enricher.download_image", return_value=True),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="refresh_full",
                write_nfo=True,
                write_cover=False,
                write_extrafanart=False,
                overwrite_existing=True,
                scraper_data=dict(scraper_data),
            )
        assert result.success is True, f"enrich_single 應成功，error={result.error}"
        assert result.nfo_written is True, "NFO 應真的被寫出（否則翻倍與否測不出來）"

    def test_rating_stable_across_two_refresh_full_runs(self, tmp_path):
        import xml.etree.ElementTree as ET

        nfo_path = tmp_path / "SONE-205.nfo"
        nfo_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<movie>\n"
            "  <rating>7.0</rating>\n"
            "</movie>\n",
            encoding="utf-8",
        )

        self._run_refresh_full(tmp_path)
        first_rating = ET.parse(str(nfo_path)).getroot().find("rating").text
        assert first_rating == "7.0", f"第一次跑完應仍是 7.0，實際：{first_rating}"

        self._run_refresh_full(tmp_path)
        second_rating = ET.parse(str(nfo_path)).getroot().find("rating").text
        assert second_rating == "7.0", (
            f"第二次跑完不應翻倍成 14.0，實際：{second_rating}"
        )


# ── 14. write_nfo=False ───────────────────────────────────────────────────────


# ── 15. write_cover=False ─────────────────────────────────────────────────────


# ── 16. write_extrafanart=False（預設）────────────────────────────────────────


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


# ── 19. 封面已存在 + overwrite_existing=False ────────────────────────────────


# ── 20. write_extrafanart=True + sample_images 存在 ──────────────────────────


# ── 21. write_extrafanart=True + 無 sample_images ────────────────────────────


# ── 22. NFO 路徑確實在影片同目錄 ─────────────────────────────────────────────


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


# ── 26. F1: _db_upsert 把 path 存成 file:/// URI ────────────────────────────────


# ── 26b. 89b-T2: _db_upsert 寫入 scrape_attempted_at ─────────────────────────


# ── 27. F1: _db_upsert cover_path 處理 ────────────────────────────


# ── 27b. TASK-89a-T5 (CD-89a-5 / Codex C2): output_dir 保留（鏡射 TestDbUpsertCoverPath）──


# ── 28. F2: has_subtitle 由 find_subtitle_files 決定 ────────────────────────────

class TestHasSubtitleDetected:
    @pytest.mark.parametrize(
        ("srt_files", "expected_has_subtitle"),
        [
            pytest.param(["/video/SONE-205.srt"], True, id="srt_exists"),
        ],
    )
    def test_has_subtitle_true_when_srt_exists(self, srt_files, expected_has_subtitle):
        """F2: 影片同目錄有 .srt 時 generate_nfo 以 has_subtitle=True 呼叫；無字幕時為 False"""
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
            patch("core.enricher.find_subtitle_files", return_value=srt_files),
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
        assert captured_calls[0].get("has_subtitle") is expected_has_subtitle


# ── T2: source / javbus_lang 參數路由 ─────────────────────────────────────────

class TestSourceParam:
    @pytest.mark.parametrize(
        ("kwarg", "value"),
        [
            pytest.param("source", "javbus", id="source"),
        ],
    )
    def test_source_passed_to_search_jav_refresh_full(self, kwarg, value):
        """T2: source='javbus'／javbus_lang='ja' 在 refresh_full mode 正確傳給 search_jav"""
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
                **{kwarg: value},
            )
        mock_search.assert_called_once()
        assert mock_search.call_args.kwargs.get(kwarg) == value


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


# ── TASK-91 Codex Finding 1: DB key 必須維持映射命名空間，不可用反解後本機路徑 ──
# 反例：若 fs_path_for_db 被誤還原為 fs_path（反解後本機路徑），DB round-trip
# （get_by_path / update_scrape_attempted_at / nfo_mtime WHERE path=?）永遠對不上
# DB 既有 row（DB 存的是映射端 UNC URI）。Mutation-sensitive：revert 該行 → 下列全 RED。

class TestEnrichSingleDbKeyMappingPreserved:
    """站台1 DB key（enrich_single）：get_by_path / update_scrape_attempted_at 必須用
    fs_path_for_db（裸 uri_to_fs_path，維持 DB 映射命名空間），不是反解後 fs_path。"""


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


# ── TASK-98b-T2: 重刮 focal trigger 接線 ─────────────────────────────────────

class TestEnrichFocalTrigger:
    """重刮無碼片 → maybe_submit_video_focal 被呼（wire-point 契約）。

    helper 本體 gate 於 test_focal_trigger.py 覆蓋；此處只驗 enricher 有接線、
    且傳入的 (number, maker, video_path_uri, cover_fs) 對齊 _db_upsert 的 DB key。
    """

    def _run_refresh(self, number="SIRO-1234", maker="SOD"):
        from unittest.mock import patch, MagicMock
        scraper_data = {
            "number": number,
            "title": "Test",
            "actors": [],
            "cover": "http://example.com/cover.jpg",
            "date": "2024-01-01",
            "maker": maker,
            "director": "",
            "series": "",
            "label": "",
            "tags": [],
            "sample_images": [],
            "source": "javbus",
        }
        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=scraper_data),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.focal_trigger.maybe_submit_video_focal") as mock_submit,
        ):
            mock_repo = MagicMock()
            mock_existing = MagicMock()
            mock_existing.sample_images = []
            mock_existing.user_tags = []
            mock_existing.cover_path = ""
            mock_repo.get_by_path.return_value = mock_existing
            mock_repo_cls.return_value = mock_repo

            from core.enricher import enrich_single
            enrich_single(
                file_path="/tmp/SIRO-1234.mp4",
                number=number,
                mode="refresh_full",
                write_nfo=False,
                write_cover=True,
                write_extrafanart=False,
                overwrite_existing=True,
            )
        return mock_submit


class TestEnrichFocalReset:
    """99a-T1b CD-4：重刮實際寫入新封面時同步作廢手動焦點。

    `reset_focal_to_auto` + `maybe_submit_video_focal` 必須一起被 `if cover_written:`
    包住、reset 在 submit 之前——三個 mutation 鎖：
    - hoist reset 出 `if cover_written:` → cover_written=False 也清 manual → RED
      （`test_cover_written_false_preserves_manual`）。
    - reset/submit 順序對調 → submit 呼叫當下 crop_mode 仍是 manual → RED
      （`test_cover_written_true_reset_happens_before_submit`）。
    """

    _SCRAPER_DATA = {
        "number": "PLACEHOLDER", "title": "New", "actors": [],
        "cover": "http://example.com/cover.jpg", "date": "2024-01-01",
        "maker": "SOD", "director": "", "series": "", "label": "",
        "tags": [], "sample_images": [], "source": "javbus",
    }

    def _seed_manual(self, tmp_path, db_name, number, video_name):
        from unittest.mock import patch
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri, uri_to_fs_path

        db_file = tmp_path / db_name
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)

        video_file = tmp_path / video_name
        video_file.write_bytes(b"x")
        file_path = str(video_file)
        db_key = to_file_uri(uri_to_fs_path(file_path))

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=db_key, number=number, title="Old", maker="SOD"))
        assert repo.update_manual_focal(db_key, "0.3000,0.6000", '') is True
        return repo, file_path, db_key


# ── TASK-113b-T1：S3/S4 nfo_mtime TOCTOU 例外對齊 ────────────────────────────

class TestNfoMtimeS3S4ExceptionAlignment:
    """S3（`:527-528`，走刮削路徑寫 DB 時的 nfo_mtime stat）原本裸 `.stat()`，
    TOCTOU 視窗內 NFO 消失會讓整個 enrich_single 直接炸掉；S4（`:549-565`，
    fill-missing 路徑的獨立 nfo_mtime UPDATE）已有 `except Exception`，但範圍過寬
    （把 stat 與 DB 連線/寫入的失敗混在一起）。

    TASK-113b-T1：S3 的 `.stat()` 失敗映射為 `0.0`（沿用既有「NFO 不存在」語意，
    仍照樣呼叫 `_db_upsert`）；S4 的 stat 失敗整段跳過 UPDATE（不得折成 `0.0`
    再寫，DB 段 `except Exception` 的範圍不變）。兩處都要記 warning。

    裁決 1（Opus Step 2）：測試 1／7 的故障注入須 class 級同時 patch `Path.exists`
    （目標 `.nfo` 路徑回 True）與 `Path.stat`（目標路徑拋 `OSError`），非目標路徑
    一律委派原始方法——`Path.exists()` 內部就是呼叫 `self.stat()`，只 patch
    `Path.stat` 會讓 `.exists()` 連帶回 False（ENOENT 類）或重拋（EACCES 類），
    兩者都測不到被測分支；`Path` 有 `__slots__`，只能 class 級 patch。
    裁決 2：測試 3 用 `patch("core.enricher._db_upsert", wraps=...)` 斷言 S3 傳入的
    `nfo_mtime` kwarg（而非只看最終 DB 值——S4 是 S3 的 fill-missing 補網，只驗
    最終值測不出「S3 stat 提前」這類 mutation）。
    裁決 3：測試 4／6／7 的 S4 分支用「seed 一筆完整 DB row」建立（`path`/`number`
    對上、`_missing_fields` 八欄全非空），不用「完整 baseline NFO」——DB row 一旦
    存在，`:409` 的 `get_by_numbers` 會先命中，NFO 內容根本不會被讀到；且只有
    DB row 存在，S4 的 `UPDATE ... WHERE path = ?` 才有列可打。
    """

    _COMPLETE_KWARGS = dict(
        title="Old Title", original_title="Old Title",
        actresses=["女優A"], maker="SOD", director="監督A",
        series="シリーズA", label="LABEL", tags=["タグ"],
        release_date="2024-01-01", duration=120,
        cover_path="https://example.com/cover.jpg",
    )

    def _seed_env(self, tmp_path, db_name, number, video_name):
        """建立真 sqlite DB 檔（非 :memory:，理由見 TASK-113b-T1.md「現況分析 C」）
        + repo + 一支真實影片檔，回傳 (repo, file_path, nfo_file, db_key)。"""
        from core.database import init_db, VideoRepository
        from core.path_utils import to_file_uri, uri_to_fs_path

        db_file = tmp_path / db_name
        init_db(db_file)
        repo = VideoRepository(db_path=db_file)

        video_file = tmp_path / video_name
        video_file.write_bytes(b"x")
        file_path = str(video_file)
        nfo_file = video_file.with_suffix(".nfo")
        db_key = to_file_uri(uri_to_fs_path(file_path))
        return repo, file_path, nfo_file, db_key

    def _seed_complete_row(self, repo, db_key, number, nfo_mtime):
        """seed 一筆完整（`_missing_fields` 八欄全非空）DB row，`nfo_mtime` 用 raw
        UPDATE 顯式覆寫（`Video` dataclass 預設 0.0，upsert() 走一般路徑寫不出
        NULL；比照 conftest.seed_crop_mode 手法直接開連線 UPDATE）。
        BE-ENV-02：seed 一個不可能相等的舊值（如 12345.0）取代 time.sleep 撐 mtime 差異。
        """
        from core.database import Video, get_connection

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=db_key, number=number, **self._COMPLETE_KWARGS))

        conn = get_connection(repo.db_path)
        try:
            conn.execute(
                "UPDATE videos SET nfo_mtime = ? WHERE path = ?",
                (nfo_mtime, db_key),
            )
            conn.commit()
        finally:
            conn.close()

    def _toctou_context(self, target_path_str):
        """class 級 patch `Path.exists`（目標路徑回 True）＋ `Path.stat`（目標路徑
        拋 `OSError`），非目標路徑一律委派原始方法（裁決 1）。回傳可直接 `with` 的
        `ExitStack`。"""
        from contextlib import ExitStack

        orig_exists = Path.exists
        orig_stat = Path.stat

        def fake_exists(self_, *a, **kw):
            if str(self_) == target_path_str:
                return True
            return orig_exists(self_, *a, **kw)

        def fake_stat(self_, *a, **kw):
            if str(self_) == target_path_str:
                # 訊息文字刻意不含 "stat" 字面（避免洩漏進 caplog 的 "stat" 關鍵字
                # 斷言，讓斷言只認生產碼 warning 訊息本身有沒有講 "stat"，不是認
                # 例外字串本身）。
                raise OSError("injected TOCTOU disappearance (test)")
            return orig_stat(self_, *a, **kw)

        stack = ExitStack()
        stack.enter_context(patch("pathlib.Path.exists", new=fake_exists))
        stack.enter_context(patch("pathlib.Path.stat", new=fake_stat))
        return stack

    # ── 測試 1（plan #1）：NFO「存在」但 stat() 拋 OSError → S3（走刮削）────────


    # ── 測試 3（plan #3）：起初無 .nfo → enrich 真寫出 NFO → S3 傳給 _db_upsert 的
    # nfo_mtime 等於新檔 st_mtime（裁決 2：斷言傳入值，不只看最終 DB 值）────────


    # ── 測試 4（plan #4）：NFO 存在且 DB nfo_mtime 為 NULL → S4 補值（回歸釘選）──


    # ── 測試 5（plan #5）：NFO 存在且 DB 已有非 0 值 + 走刮削路徑 → S3 無條件覆寫
    # （回歸釘選；BE-ENV-02：seed 12345.0 不可能相等的舊值）───────────────────


    # ── 測試 6（plan #6）：NFO 存在且 DB 已有非 0 值 + 不走刮削 → S4 guard 擋下
    # （回歸釘選）──────────────────────────────────────────────────────────────


    # ── 測試 7（plan #7）：不走刮削 + DB nfo_mtime 為 NULL + stat() 拋 OSError →
    # S4 整段跳過（不得折成 0.0）────────────────────────────────────────────────


# ── 99b-T2 DoD ④: caller #4（enricher）namespace 真 DB 鎖 ───────────────────

class TestEnrichFocalCoverPathUriNamespace:
    """cover_path_uri 傳給 maybe_submit_video_focal 的值必須實際等於 _db_upsert
    剛寫入 DB 的 cover_path（同一運算式 to_file_uri(local_cover, path_mappings)
    作用在同一變數，CD-99b-5「低風險」評級由 code identity 保證，仍須真 DB 鎖驗證，
    非只憑「程式碼看起來一樣」免驗）。

    download_image 的 side_effect 必須真的把檔案寫到 local_cover 路徑——
    `_db_upsert` 的 `cover_uri` 計算是 `if local_cover_path and
    os.path.exists(local_cover_path)`（:624），若 mock 只回傳 True 不寫實體檔，
    `_db_upsert` 會落 else 分支保留 DB 既有 cover_path（此處為空字串），造成假陽性
    ——測試看起來測了「同源」，實際上驗的是兩個空字串巧合相等。
    """

    def _write_fake_cover(self, url, path):
        from pathlib import Path
        Path(path).write_bytes(b"x")
        return True


# ============ 站2接線測試 (TASK-101a-T2 DoD①④) ============

_T2_FOCAL_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos"


def _t2_write_face_cover(cover_path):
    src = _T2_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    Path(cover_path).write_bytes(src.read_bytes())


def _t2_oracle_poster_bytes(focal_xy):
    """獨立 oracle：不經過 crop_to_poster / _write_external_images / enrich_single，
    直接呼叫底層 primitive 算出「應該要平移到焦點」的期望 bytes。不可用「呼叫同一站
    流程兩次自我比對」（gotchas-backend.md #9，101a-T1 已踩過）。

    TASK-102c-T1：改吃 focal_xy 參數，不再自己呼叫真 detect_focal——呼叫端須確保
    patch `core.organizer.run_detection` 回傳 `RunnerOutcome(kind="FOUND", focal=同一個值)`，
    否則 production 端與 oracle 端會對不上。
    """
    from core.organizer import _poster_window_ratio
    from core.focal import crop_image_position
    from PIL import Image

    fixture_path = _T2_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    focal = focal_xy
    with Image.open(fixture_path) as img:
        expected_cropped = crop_image_position(img.convert("RGB"), r_window, focal[0])
    buf = io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


class TestEnrichSingleStationWiring:
    """DoD①：站2（core/enricher.py enrich_single → _write_external_images →
    crop_to_poster）接線——真跑 enrich_single()（external_manager='jellyfin'），
    不 mock crop_to_poster / _write_external_images 本身（唯一沒有既有 patch 範本
    的一站，見 plan §C-4）。fixture A（番號驅動）/ B（maker-only 驅動）各一次，
    poster bytes 對獨立 oracle。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}

    def _run_station2(self, tmp_path, tag, fixture):
        mp4 = tmp_path / f"{fixture['number']}_{tag}.mp4"
        mp4.touch()
        cover = mp4.with_suffix(".jpg")
        _t2_write_face_cover(cover)

        mock_repo = MagicMock()
        mock_repo.get_by_numbers.return_value = {
            fixture["number"]: [_make_video(number=fixture["number"], maker=fixture["maker"])]
        }
        mock_repo.get_by_path.return_value = None

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", return_value=False),
            patch("core.enricher.find_subtitle_files", return_value=[]),
            patch("core.organizer.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(mp4),
                number=fixture["number"],
                mode="db_to_sidecar",
                write_nfo=True,
                write_cover=True,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is True, f"enrich_single 失敗: {result.error}"
        poster_path = mp4.with_name(mp4.stem + "-poster.jpg")
        assert poster_path.exists(), "station2 應產生 poster"
        expected = _t2_oracle_poster_bytes(MOCK_FOCAL_XY)
        assert poster_path.read_bytes() == expected, "station2 poster 應對準焦點（獨立 oracle 比對）"

    def test_station2_fixture_a(self, tmp_path):
        self._run_station2(tmp_path, "a", self._FIXTURE_A)


# ══════════════════════════════════════════════════════════════════════════════
# 112b-T5：真理表 Table 1 #2/#3/#4/#4b/#5/#6 直接鎖 ＋ ⑤⑥⑦ 專屬守衛 ＋ AC5/AC6/AC8
#
# 對齊 feature/112-cover-canonical-position/TASK-112b-T5.md。fixture 三條件
# （task card §C／Opus 追加要求 #2，形狀照抄
# tests/unit/test_cover_canonical_contract.py:1016-1033 的 `_seed_bare_tracked_row`
# ——讀它、照著寫，**不 import**，該檔案頭明文「本檔案私有」）：
#   1. DB 種一筆 tracked row（key 存在，`cover_path` 依情境需要顯式帶入，見各
#      測試 docstring）
#   2. 留白 `_FILL_MISSING_REQUIRED` 欄位 → `_missing_fields` 非空 →
#      `search_jav` 真的被呼叫 → `source_used` 落在 scraper 值 → `_db_upsert`
#      閘門為 True（不留白會讓 DB 斷言變成零訊號的空頭支票，本卡 §A-2 追出的
#      `source_used` 陷阱，比 `BE-DATA-07` 更上游）
#   3. `search_jav` mock 回非空 meta（含 cover URL）
# 每一支 DB 測試額外斷言 `ctx.mock_search.called`（Opus 追加要求 #3：fixture
# 沒設對就炸，不是靜默恆真）。
# ══════════════════════════════════════════════════════════════════════════════

def _t5_write_jpeg(path, size=(300, 200), color=(128, 64, 32)) -> None:
    """真 JPEG（PIL）。假 bytes（`b"fake"`）會讓 crop_to_poster 靜默回 False，
    poster 斷言測不到東西（§E 假綠風險 #1）。"""
    from PIL import Image
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=color).save(str(path), "JPEG", quality=95)


def _t5_jpeg_bytes(size=(300, 200), color=(200, 100, 50)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _t5_download_image_side_effect(content: bytes):
    """供 `patch("core.enricher.download_image", side_effect=...)`：真的把
    bytes 寫進 save_path 並回 True，讓後續 crop_to_poster／位元組斷言吃得到
    真實內容。**patch target 必須是 `core.enricher.download_image`**（值匯入
    到 enricher 模組命名空間，patch `core.organizer.download_image` 對它無效，
    §E 假綠風險 #4）。"""
    def _side_effect(url, save_path, referer=""):
        Path(save_path).write_bytes(content)
        return True
    return _side_effect


def _t5_read_nfo_tags(nfo_path) -> dict:
    from xml.etree import ElementTree as ET
    root = ET.parse(str(nfo_path)).getroot()
    return {
        "poster": root.findtext("poster") or "",
        "thumb": root.findtext("thumb") or "",
        "fanart": root.findtext("fanart") or "",
    }


def _t5_assert_nfo_tags_exist(nfo_path, expect_exists: dict) -> dict:
    """讀 NFO 三個 tag，逐一斷言其指向的檔案在 NFO 所在目錄下是否存在
    （只驗『指得到』不驗『字面值』的呼叫端另外自行比對字面值，§E 假綠風險 #3：
    只驗存在不驗字面值/只驗字面值不驗存在都不夠）。"""
    tags = _t5_read_nfo_tags(nfo_path)
    nfo_dir = Path(nfo_path).parent
    for key, expected in expect_exists.items():
        target = nfo_dir / tags[key]
        actual = target.exists()
        assert actual == expected, (
            f"NFO <{key}> = {tags[key]!r}（{target}），exists()={actual}，預期 {expected}"
        )
    return tags


def _t5_scraper_data(number):
    return {
        "number": number, "title": "T5 Scraper Title", "actors": ["T5 Actress"],
        "cover": "http://example.com/t5-cover.jpg", "date": "2024-05-01",
        "maker": "T5Maker", "director": "T5 Dir", "series": "T5 Series",
        "label": "T5Lab", "tags": ["t5tag"], "sample_images": [],
        "source": "javbus",
    }


def _t5_seed_tracked_row(repo, db_key, number, cover_path=""):
    """DB 已追蹤此片（key 存在）——**不是**「DB 裡沒有這片」。`_merge_meta`
    的 cover_url 合併判斷（`core/enricher.py:146`，`merged.get("cover_url")
    == ""`）在 key 不存在時恆假，會讓 scraper 的封面 URL 永遠合併不進去
    （`BE-DATA-07`）。其餘 `_FILL_MISSING_REQUIRED` 欄位（title/actresses/
    maker/director/series/label/tags/release_date）全部靠 `Video` dataclass
    預設值留白 → `_missing_fields` 保證非空 → `search_jav` 保證被呼叫 →
    `source_used` 落在 scraper 值 → `_db_upsert` 閘門為 True（Opus 追加
    要求 #2）。`cover_path` 依情境需要顯式帶入：留空＝DB 尚未追蹤任何既有
    封面（沿用 test_cover_canonical_contract.py B-jf-4 的理由：避免磁碟上
    孤兒檔案的 URI 干擾 cover_url 合併判斷）；帶入既有檔案的 URI＝這片已被
    追蹤過同一張封面（用於「DB cover_path 不變」的非平凡驗證，見各測試
    docstring）。"""
    from core.database import Video
    repo.upsert(Video(path=db_key, number=number, cover_path=cover_path))


def _t5_run(tmp_path, db_name, *, number, external_manager, video_name=None,
            overwrite_existing=False, pre_stage=None, download_content=None,
            capture=None):
    """T5 共用 fixture 骨架：真 DB + patch `VideoRepository` 綁 tmp db
    （`get_db_path()` 硬編碼 repo-root、不讀 config ⇒ `temp_config_path` 對它
    無效）+ 真 `search_jav` mock（非空 meta）+ patch `core.enricher.download_image`
    真的落地寫檔（不需要另外 mock `requests.get`：`crop_to_poster` 純讀本地
    檔案，沒有網路呼叫，見 task card §B 讀碼）。"""
    from core.database import init_db, VideoRepository
    from core.path_utils import to_file_uri as _to_file_uri, uri_to_fs_path

    if capture is None:
        capture = {}

    video_dir = tmp_path / f"{db_name}_video"
    video_dir.mkdir()
    video_file = video_dir / (video_name or f"{number}.mp4")
    video_file.write_bytes(b"video-bytes")
    file_path = str(video_file)
    db_key = _to_file_uri(uri_to_fs_path(file_path))

    db_file = tmp_path / f"{db_name}.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    if pre_stage is not None:
        pre_stage(repo, video_dir, db_key, number, capture)

    scraper_data = _t5_scraper_data(number)
    content = download_content if download_content is not None else _t5_jpeg_bytes()
    with (
        patch("core.enricher.VideoRepository", return_value=repo),
        patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
        patch("core.enricher.download_image",
              side_effect=_t5_download_image_side_effect(content)) as mock_download,
    ):
        from core.enricher import enrich_single
        result = enrich_single(
            file_path=file_path, number=number, mode="fill_missing",
            write_nfo=True, write_cover=True, write_extrafanart=False,
            overwrite_existing=overwrite_existing, external_manager=external_manager,
        )
    return SimpleNamespace(
        result=result, repo=repo, db_key=db_key, video_dir=video_dir,
        video_file=video_file, mock_search=mock_search, mock_download=mock_download,
        capture=capture,
    )


class TestTable1Row2ExistingFullPreservedAC6:
    """真理表 Table 1 #2（AC8 + AC1b-1）＋ AC6：jellyfin + 既有 `{stem}.jpg`
    完整（含衍生圖）+ ovw=False → `download_image` 零呼叫、DB cover_path 與
    crop_mode/auto_focal 操作前後完全相同；既有封面 bytes/mtime 完全不變
    （AC6，`BE-TEST-10`：基準值在操作**之前**取得）。"""

    def test_preserve_no_download_db_and_focal_unchanged(self, tmp_path, seed_crop_mode):
        number = "T5ROW2-001"

        def _stage(repo, video_dir, db_key, number_, capture):
            stem = number_
            cover = video_dir / f"{stem}.jpg"
            _t5_write_jpeg(cover, color=(11, 12, 13))
            _t5_write_jpeg(video_dir / f"{stem}-poster.jpg", color=(21, 22, 23))
            _t5_write_jpeg(video_dir / f"{stem}-fanart.jpg", color=(31, 32, 33))
            cover_uri = to_file_uri(str(cover))
            _t5_seed_tracked_row(repo, db_key, number_, cover_path=cover_uri)
            assert seed_crop_mode(repo, db_key, "manual") is True
            capture["cover_uri"] = cover_uri
            capture["before_bytes"] = cover.read_bytes()
            capture["before_mtime"] = cover.stat().st_mtime

        ctx = _t5_run(tmp_path, "t5_row2", external_manager="jellyfin", number=number,
                       pre_stage=_stage)
        assert ctx.mock_search.called, (
            "fixture 沒逼出 search_jav → _db_upsert 不會執行 → 下面的 DB 斷言恆空"
        )

        stem = ctx.video_file.stem
        cover = ctx.video_dir / f"{stem}.jpg"
        poster = ctx.video_dir / f"{stem}-poster.jpg"
        fanart = ctx.video_dir / f"{stem}-fanart.jpg"

        ctx.mock_download.assert_not_called()  # AC8：preserve 命中 → 零下載

        # AC6：既有封面 bytes/mtime 操作前後完全相同（基準值在操作之前取得）
        assert cover.read_bytes() == ctx.capture["before_bytes"]
        assert cover.stat().st_mtime == ctx.capture["before_mtime"]

        # 衍生圖 gate 是磁碟真相，既有衍生圖原樣算數（不重生）
        assert poster.exists() and fanart.exists()

        nfo = ctx.video_dir / f"{stem}.nfo"
        tags = _t5_assert_nfo_tags_exist(nfo, {"poster": True, "thumb": True, "fanart": True})
        assert tags["poster"] == f"{stem}-poster.jpg"
        # <thumb> 改用既有 fanart_tag 變數（CD-112-5，core/organizer.py:755），
        # has_fanart=True 時字面值恆為 {stem}-fanart.jpg——與「正典封面仍是
        # {stem}.jpg」正交，不是「thumb 沿用 canonical cover 位置」（實測更正
        # task card §D 表格原先「== {stem}.jpg」的預測，見 T5 §F 記錄）。
        assert tags["thumb"] == f"{stem}-fanart.jpg"
        assert tags["fanart"] == f"{stem}-fanart.jpg"

        row = ctx.repo.get_by_path(ctx.db_key)
        assert row.cover_path == ctx.capture["cover_uri"], "DB cover_path 操作前後完全相同"  # 真理表 Table 1 #2
        assert row.crop_mode == "manual", "AC1b-1：crop_mode 操作前後完全相同"
        assert row.auto_focal == ""


class TestTable1Row3ExistingMissingDerivativesBackfilled:
    """真理表 Table 1 #3（AC1b-1 衍生圖邊界）：jellyfin + 既有 `{stem}.jpg`
    但**缺衍生圖** + ovw=False → cover 本身仍 preserve（零下載），但衍生圖
    gate 是磁碟真相（`cover_path.exists()`，`core/enricher.py:280-303`），
    與 preserve 無關 → **會補**。這格證明 AC1b-1 的承諾是「不動正典封面」
    而不是「不寫任何檔」。"""

    def test_derivatives_backfilled_cover_preserved(self, tmp_path, seed_crop_mode):
        number = "T5ROW3-001"

        def _stage(repo, video_dir, db_key, number_, capture):
            stem = number_
            cover = video_dir / f"{stem}.jpg"
            _t5_write_jpeg(cover, color=(41, 42, 43))
            cover_uri = to_file_uri(str(cover))
            _t5_seed_tracked_row(repo, db_key, number_, cover_path=cover_uri)
            assert seed_crop_mode(repo, db_key, "manual") is True
            capture["cover_uri"] = cover_uri
            capture["before_bytes"] = cover.read_bytes()

        ctx = _t5_run(tmp_path, "t5_row3", external_manager="jellyfin", number=number,
                       pre_stage=_stage)
        assert ctx.mock_search.called, (
            "fixture 沒逼出 search_jav → _db_upsert 不會執行 → 下面的 DB 斷言恆空"
        )

        stem = ctx.video_file.stem
        cover = ctx.video_dir / f"{stem}.jpg"
        poster = ctx.video_dir / f"{stem}-poster.jpg"
        fanart = ctx.video_dir / f"{stem}-fanart.jpg"

        ctx.mock_download.assert_not_called()  # cover 本身仍走 preserve
        assert cover.read_bytes() == ctx.capture["before_bytes"]
        assert poster.exists() and fanart.exists(), "衍生圖 gate 看磁碟 cover_path.exists()，會補"  # 真理表 Table 1 #3

        nfo = ctx.video_dir / f"{stem}.nfo"
        tags = _t5_assert_nfo_tags_exist(nfo, {"poster": True, "thumb": True, "fanart": True})
        assert tags["poster"] == f"{stem}-poster.jpg"
        # <thumb> = fanart_tag（CD-112-5），has_fanart=True → 恆 {stem}-fanart.jpg
        assert tags["thumb"] == f"{stem}-fanart.jpg"
        assert tags["fanart"] == f"{stem}-fanart.jpg"

        row = ctx.repo.get_by_path(ctx.db_key)
        assert row.cover_path == ctx.capture["cover_uri"], "DB cover_path 不變"
        assert row.crop_mode == "manual", "焦點不清"
        assert row.auto_focal == ""


class TestTable1Row5ExistingFullOverwritten:
    """真理表 Table 1 #5（AC1b-2 核心）：jellyfin + 既有 `{stem}.jpg` +
    **ovw=True** → 覆寫回同一個檔名、DB cover_path 字面值不變（重算後相同）、
    crop_mode 被重置。**焦點重置鎖的是改動前就有的行為（CD-112-14），不是
    112 的承諾**（R8，Opus 追加要求 #5）——測試方法名稱刻意不用
    `preserves_focal` 這種會被誤讀成承諾的字眼。"""

    def test_overwrite_true_rewrites_same_name_legacy_focal_reset_cd_112_14(
        self, tmp_path, seed_crop_mode
    ):
        number = "T5ROW5-001"
        old_content = (71, 72, 73)
        new_content = (210, 211, 212)

        def _stage(repo, video_dir, db_key, number_, capture):
            stem = number_
            cover = video_dir / f"{stem}.jpg"
            _t5_write_jpeg(cover, color=old_content)
            cover_uri = to_file_uri(str(cover))
            _t5_seed_tracked_row(repo, db_key, number_, cover_path=cover_uri)
            assert seed_crop_mode(repo, db_key, "manual") is True
            capture["cover_uri"] = cover_uri

        ctx = _t5_run(tmp_path, "t5_row5", external_manager="jellyfin", number=number,
                       overwrite_existing=True, pre_stage=_stage,
                       download_content=_t5_jpeg_bytes(color=new_content))
        assert ctx.mock_search.called, (
            "fixture 沒逼出 search_jav → _db_upsert 不會執行 → 下面的 DB 斷言恆空"
        )

        stem = ctx.video_file.stem
        cover = ctx.video_dir / f"{stem}.jpg"

        ctx.mock_download.assert_called_once()
        assert cover.read_bytes() == _t5_jpeg_bytes(color=new_content), "覆寫回同一個檔名，內容是新下載的圖"  # 真理表 Table 1 #5

        nfo = ctx.video_dir / f"{stem}.nfo"
        tags = _t5_assert_nfo_tags_exist(nfo, {"poster": True, "thumb": True, "fanart": True})
        assert tags["poster"] == f"{stem}-poster.jpg"
        # <thumb> = fanart_tag（CD-112-5），has_fanart=True → 恆 {stem}-fanart.jpg
        assert tags["thumb"] == f"{stem}-fanart.jpg"
        assert tags["fanart"] == f"{stem}-fanart.jpg"

        row = ctx.repo.get_by_path(ctx.db_key)
        assert row.cover_path == ctx.capture["cover_uri"], "DB cover_path 字面值不變（同一路徑）"
        assert row.crop_mode == "auto", (
            "cover_written=True → 無條件 reset（既有行為，非 112 承諾，R8）"
        )
        assert row.auto_focal == ""


class TestWriteExternalImagesWriteCoverGate:
    """spec-135 T5／CD-135-16：`write_cover` 在 `_write_external_images()` 三處
    既有條件裡的效力，與 `overwrite_existing` 完全同構——都是「別重寫，照磁碟
    現況回報」。DoD-1～DoD-7 對應本卡承重段逐條。"""


    def test_overwrite_true_write_cover_false_files_exist_unchanged_reports_true(self, tmp_path):
        """DoD-2（CD-135-16 核心情境，被否決做法在此回 False）：要求覆蓋
        + 不換封面 + 檔案都在 → bytes/mtime 不變，仍回報 True。
        BE-TEST-11：overwrite_existing 必須是 True（不能用 False 頂替），
        否則 `not overwrite_existing` 本身已真，M1 拿掉 `or not write_cover`
        測不出差異。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        poster = tmp_path / "SONE-205-poster.jpg"
        fanart = tmp_path / "SONE-205-fanart.jpg"
        poster.write_bytes(b"existing-poster")
        fanart.write_bytes(b"existing-fanart")
        poster_bytes = poster.read_bytes()
        fanart_bytes = fanart.read_bytes()
        poster_mtime = poster.stat().st_mtime
        fanart_mtime = fanart.stat().st_mtime

        from core.enricher import _write_external_images
        result = _write_external_images(
            str(tmp_path / "SONE-205.mp4"), "jellyfin", True, write_cover=False,
        )

        assert result == {"poster": True, "fanart": True}
        assert poster.read_bytes() == poster_bytes
        assert fanart.read_bytes() == fanart_bytes
        assert poster.stat().st_mtime == poster_mtime
        assert fanart.stat().st_mtime == fanart_mtime

    def test_write_cover_true_regenerates_as_before(self, tmp_path):
        """DoD-3：換封面（write_cover=True）→ 照舊重生（行為與現況相同）。"""
        cover = tmp_path / "SONE-205.jpg"
        _create_dummy_jpeg(cover)
        fanart = tmp_path / "SONE-205-fanart.jpg"
        fanart.write_bytes(b"tiny")  # 比真實 JPEG 小

        from core.enricher import _write_external_images
        result = _write_external_images(
            str(tmp_path / "SONE-205.mp4"), "jellyfin", True, write_cover=True,
        )

        assert result["fanart"] is True
        assert fanart.stat().st_size > 4  # 覆蓋後應為真實 JPEG


class TestWriteExternalImagesPreflightSamefileGuard:
    """⑥⑦ 專屬守衛（Opus 追加要求 #1）：`same_target_verdict` 對未知
    `OSError` 的 fail-closed 承諾——preflight 真正承重的是 `os.path.samefile`
    拋出未知例外那一格，**不是** `src == dst` 的字串相等短路（那格從不呼叫
    `os.path.samefile`，本卡實測 `core/cover_layout.py:257-258` 的
    `if src == dst: return True, True` 在呼叫 `os.path.samefile` 之前就
    已短路）。監控 `os.path.samefile` 拋錯：

    - **fanart（⑥）**：`cover_path == fanart_path`（字串相等，#4b 常態
      路徑）→ unmutated code 完全不受 monkeypatch 影響（string-equal 短路），
      維持安全；mutation 拿掉 preflight 三行後，`shutil.copy2` 內部
      `shutil._samefile()` 才會真的呼叫 `os.path.samefile` → patch 生效 →
      誤判「不同檔」→ `copyfile` 用 `'wb'` 開啟同一個檔案 → 截斷（T3 §D
      實測 7427→0 bytes 仍報成功）。
    - **poster（⑦）**：`poster_path` 字串永不等於 `cover_path`，
      `same_target_verdict` 一定會呼叫 `os.path.samefile` → patch 直接命中
      未知 `OSError` 分支 → `(True, False)` → fail-closed，`poster_ok`
      老實回 `False`（**unmutated code 即可驗到**，不需要靠 mutation）。
    """

    def test_samefile_oserror_fails_closed_no_corruption(self, tmp_path, monkeypatch):
        video = tmp_path / "T5PF-001.mp4"
        video.write_bytes(b"video")
        stem = str(video.with_suffix(""))
        fanart = Path(stem + "-fanart.jpg")
        _t5_write_jpeg(fanart, color=(9, 9, 9))
        before_bytes = fanart.read_bytes()
        poster = Path(stem + "-poster.jpg")

        def _raise(a, b):
            raise OSError("boom（模擬權限被拒／網路磁碟逾時）")

        monkeypatch.setattr(os.path, "samefile", _raise)

        from core.enricher import _write_external_images
        result = _write_external_images(
            str(video), "jellyfin", True, number="T5PF-001", maker="TestMaker",
        )

        assert fanart.read_bytes() == before_bytes, (
            "-fanart.jpg 的 bytes 不得被清空/改動（基準值在操作之前取得，BE-TEST-10）"
        )
        # fanart：cover_path == fanart_path（字串相等）→ same_target_verdict 在
        # 呼叫 os.path.samefile 之前就已 `src == dst` 短路回 (True, True)，
        # 完全不受本測試的 monkeypatch 影響——unmutated code 正確回 True（安全，
        # 沒有觸碰檔案）。這正是本卡實測更正 Opus 追加要求 #1 原始描述的地方：
        # 真正被 samefile 拋錯打中的是 poster 那一側，不是 fanart。
        assert result["fanart"] is True, "字串相等短路，不受 samefile patch 影響（unmutated 安全）"
        assert result["poster"] is False, (
            "poster_path 字串永不等於 cover_path，samefile 拋錯 → fail-closed，"
            "certain=False，不得宣稱成功"
        )
        assert not poster.exists(), "fail-closed 不動作，不應寫出 poster"


class TestResolveNfoCoverPathsFlavourCoverage:
    """TASK-112b-T6b DoD-2（PR1 residual 的關閉）：`resolve_nfo_cover_paths`
    （`core/enricher.py:730`）在 T3 翻面後改呼叫**真實** `resolve_cover_target`
    三步規則，不再是 stub。既有 `TestResolveNfoCoverPathsMappingReverse`
    （`:2185`，2 支）只鎖路徑映射反解、**不變化 `external_manager`**，翻面後
    對「flavour 是否正確接線」零鑑別力（plan-112b.md §8.1 第 2 點具名
    residual）。

    同一個 `file_path` × `{off, jellyfin, emby, kodi, 非法值}` ×
    `{磁碟上無圖(neither), 只有同名(same_name_only), 只有 fanart(fanart_only)}`
    共 15 格，逐格斷言 `cover_path`；`nfo_path` 那一半只用
    `with_suffix('.nfo')`，與 flavour 完全正交——這條反向鎖（Opus 追加要求
    #3 / plan §8.3 DoD-2）與 15 格一起跑，也另外用一支獨立測試把它單獨列出來。

    白名單語意沿用 `core.config.STEM_IMAGE_MODES = ('jellyfin', 'emby',
    'kodi')`（`BE-CONFIG-03`），不自建字面值清單去判斷「新建時要不要走
    fanart」——`_FLAVOURS` 只是本測試挑的樣本，不是白名單本身。
    """

    _FLAVOURS = ["off", "jellyfin", "emby", "kodi", "plex"]  # "plex"＝非法值（不在白名單）
    _DISK_STATES = ["neither", "same_name_only", "fanart_only"]

    def _make_disk(self, video_path, state):
        """依 state 在 video_path 同層造出對應候選檔案，回傳 (same, fanart) 兩個 Path。"""
        same = video_path.with_suffix(".jpg")
        fanart = Path(str(video_path.with_suffix("")) + "-fanart.jpg")
        if state == "same_name_only":
            same.write_bytes(b"SAME-COVER")
        elif state == "fanart_only":
            fanart.write_bytes(b"FANART-COVER")
        return same, fanart


# ══════════════════════════════════════════════════════════════════════════════
# TASK-126-T4b：preview_* 管線接通 enricher（caller 層級）
# ══════════════════════════════════════════════════════════════════════════════

import requests


_T4B_BIG = b"P" * 1001
_T4B_PROXY = b"F" * 1001


def _t4b_ok(content=_T4B_BIG):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = content
    return resp


class _T4bFailedHostsMixin:
    @pytest.fixture(autouse=True)
    def _clear_failed_hosts(self):
        import core.organizer as org
        with org._failed_hosts_lock:
            org._failed_hosts.clear()
        yield
        with org._failed_hosts_lock:
            org._failed_hosts.clear()


def _t4b_scraper(**overrides):
    data = {
        "number": "SONE-205",
        "title": "テストタイトル",
        "actors": ["女優A"],
        "cover": "https://cdn.example/cover.jpg",
        "preview_cover_url": "https://mt.example/v1/images/?url=cover",
        "date": "2024-01-01",
        "maker": "SOD",
        "director": "監督",
        "series": "シリーズ",
        "label": "LABEL",
        "tags": ["タグ"],
        "sample_images": [
            "https://cdn.example/s1.jpg",
            "https://cdn.example/s2.jpg",
        ],
        "preview_sample_images": [
            "https://mt.example/v1/images/?url=s1",
            "https://mt.example/v1/images/?url=s2",
        ],
        "duration": 120,
        "url": "https://example.com/SONE-205",
        "source": "metatube:MGS",
    }
    data.update(overrides)
    return data


class TestT4bEnrichCallerFallback(_T4bFailedHostsMixin):
    """邊界 1：enrich_single 入口，原址 ConnectTimeout → 代理成功存檔。"""

    def test_enrich_single_connect_timeout_uses_preview_fallback(self, tmp_path):
        video = tmp_path / "SONE-205.mp4"
        video.write_bytes(b"fake-video")
        scraper = _t4b_scraper()

        def fake_get(url, **kwargs):
            if "cdn.example" in url:
                raise requests.exceptions.ConnectTimeout("connect timed out")
            return _t4b_ok(_T4B_PROXY)

        with (
            patch("core.organizer.requests.get", side_effect=fake_get),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            mock_repo_cls.return_value = MagicMock()
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video),
                number="SONE-205",
                mode="refresh_full",
                scraper_data=scraper,
                write_nfo=False,
                write_cover=True,
                write_extrafanart=True,
                overwrite_existing=True,
            )

        assert result.success is True
        assert result.cover_written is True
        cover = tmp_path / "SONE-205.jpg"
        assert cover.exists()
        assert cover.read_bytes() == _T4B_PROXY
        ef = tmp_path / "extrafanart"
        assert (ef / "fanart1.jpg").read_bytes() == _T4B_PROXY
        assert (ef / "fanart2.jpg").read_bytes() == _T4B_PROXY


class TestT4bEnrichExternalManagerBranch(_T4bFailedHostsMixin):
    """SA-pre-6 缺口：`external_manager != "off"` 的那個 _write_cover 呼叫點沒被驗過。

    T4b 系列全部走 `external_manager` 預設值 "off"，只打到 enricher.py:610 那個
    call site；:558 那條（Jellyfin / Emby / Kodi 使用者走的路）的
    `preview_cover_url=` wiring 是「有寫但沒人驗過真的會退代理」。

    使用者流程：使用者的外部管理器設成 Jellyfin、按「補齊資料」→ 封面原址連不到 →
    這條 wiring 若被改壞，封面就抓不到，而測試全綠不會有人發現。
    """

    def test_external_manager_branch_uses_preview_fallback(self, tmp_path):
        video = tmp_path / "SONE-205.mp4"
        video.write_bytes(b"fake-video")
        scraper = _t4b_scraper()

        def fake_get(url, **kwargs):
            if "cdn.example" in url:
                raise requests.exceptions.ConnectTimeout("connect timed out")
            return _t4b_ok(_T4B_PROXY)

        with (
            patch("core.organizer.requests.get", side_effect=fake_get),
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.find_subtitle_files", return_value=[]),
        ):
            mock_repo_cls.return_value = MagicMock()
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video),
                number="SONE-205",
                mode="refresh_full",
                scraper_data=scraper,
                write_nfo=False,
                write_cover=True,
                write_extrafanart=False,
                overwrite_existing=True,
                external_manager="jellyfin",
            )

        assert result.success is True
        assert result.cover_written is True, (
            "external_manager 分支的 _write_cover 沒有把 preview_cover_url 傳下去"
        )
        # jellyfin flavour 下封面落點不是 <stem>.jpg（走 stem 長格式 -poster/-fanart），
        # 所以掃「實際寫出了哪些 .jpg」而不是猜檔名。原址是 ConnectTimeout，
        # 磁碟上只可能出現代理副本的位元組——這正是本測試要鎖的東西。
        written = sorted(f.name for f in tmp_path.iterdir() if f.suffix == ".jpg")
        assert written, f"jellyfin 分支沒有寫出任何圖片：{sorted(p.name for p in tmp_path.iterdir())}"
        assert all(
            (tmp_path / name).read_bytes() == _T4B_PROXY for name in written
        ), f"寫出的圖片不是代理副本（原址是 ConnectTimeout，只可能來自代理）：{written}"


class TestNfoToMetaTitleResolution:
    """TASK-154b-T3：_nfo_to_meta 改用 resolve_title_body() 解析標題本體。"""

    def test_nfo_to_meta_applies_custom_nfo_title_format(self):
        """AC-b7：認得其他工具用自訂格式產生的 NFO → 讀出片名本體。"""
        from core.enricher import _nfo_to_meta

        root = ET.fromstring(
            "<movie>"
            "<title>ABC-123-片名-三上悠亜</title>"
            "<actor><name>三上悠亜</name></actor>"
            "</movie>"
        )
        meta = _nfo_to_meta(
            root, number='ABC-123', nfo_title_format='{num}-{title}-{actor}'
        )
        assert meta['title'] == '片名'

    def test_nfo_to_meta_respects_external_title_edit(self):
        """AC-b11：記錄行存在但 <title> 被外部改過 → 以外部改過的內容為準。"""
        from core.enricher import _nfo_to_meta

        root = ET.fromstring(
            "<movie>"
            "<title>外部改過的片名</title>"
            "<actor><name>三上悠亜</name></actor>"
            "<openaver_title_record>"
            "<written>ABC-123-片名-三上悠亜</written>"
            "<body>片名</body>"
            "</openaver_title_record>"
            "</movie>"
        )
        meta = _nfo_to_meta(
            root, number='ABC-123', nfo_title_format='{num}-{title}-{actor}'
        )
        assert meta['title'] == '外部改過的片名'


# ============ TASK-126-T4b review MAJOR-1：fetch_samples_only 這條下載路徑 ============
#
# spec §3.2 末條要求「**每條下載路徑**都要有 caller 層級的驗證」，不是「四個入口函式」。
# T4b 的初版只守住 enrich_single，**fetch_samples_only（片庫頁按「補劇照」走的正是這條）
# 完全沒有測試碰到**——review 在沙盒把那行 wiring 拔掉，127 條照樣全綠。

class TestT4bFetchSamplesOnlyFallback(_T4bFailedHostsMixin):

    def test_fetch_samples_only_uses_preview_fallback(self, tmp_path):
        """被牆的使用者按「補劇照」→ 原址 ConnectTimeout → 代理接手，劇照落地。"""
        import requests as _rq
        fs = tmp_path / "ABC-999.mp4"
        fs.write_bytes(b"v" * 100)
        meta = {
            "number": "ABC-999",
            "sample_images": ["https://cdn.blocked/s1.jpg", "https://cdn.blocked/s2.jpg"],
            "preview_sample_images": [
                "http://mt.example/v1/images/primary/MGS/ABC-999?url=s1",
                "http://mt.example/v1/images/primary/MGS/ABC-999?url=s2",
            ],
        }

        def _side(url, **kwargs):
            if "mt.example" in url:
                return _t4b_ok(b"PROXY" + b"\x00" * 2000)
            raise _rq.exceptions.ConnectTimeout("blocked")

        with (
            patch("core.enricher.search_jav", return_value=meta),
            patch("core.organizer.requests.get", side_effect=_side),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher._db_upsert_samples_only"),
        ):
            mock_repo_cls.return_value = MagicMock()
            from core.enricher import fetch_samples_only
            result = fetch_samples_only(str(fs), "ABC-999")

        assert result.extrafanart_written == 2, (
            "兩張劇照都應該經由代理落地——這條 wiring 若被帶壞，使用者按「補劇照」"
            "會拿到 0 張且沒有任何錯誤訊息"
        )
        written = sorted((tmp_path / "extrafanart").glob("fanart*.jpg"))
        assert len(written) == 2
        for p in written:
            assert p.read_bytes().startswith(b"PROXY")


# ══════════════════════════════════════════════════════════════════════════════
# TASK-145-T1（CD-145a-9）：fill_missing 標題佔位判定 —— 不再被檔名佔位卡死
# ══════════════════════════════════════════════════════════════════════════════
#
# DB／sidecar NFO 讀出的 title 剝掉番號前綴後等於檔名 stem，就當成缺項讓既有的
# _missing_fields()/_merge_meta() 流程去刮回真標題；刮不到／刮到但沒給 title
# 時還原成原本的佔位值。
#
# BE-TEST-11：本節 fixture 的檔名 stem 與 number（"SONE-205"）刻意不同（DoD8
# 「真標題巧合等於檔名」除外，那一條本來就是要測 stem/number 巧合的殘留情境），
# 確保「剝完前綴後是否等於 stem」這個分岔的兩側都有真實命中的樣本。
#
# generate_nfo() 本身會把 title 再剝一次番號前綴、重組成 f"[{number}]{stem 或
# 真標題}"（core/organizer.py:842-844），所以這裡的斷言一律比對
# f"[SONE-205]{content}" 這個 generate_nfo 正規化後的形狀，不是 meta['title'] 的
# 裸字串。


def _t1_write_video(tmp_path, stem):
    video_path = tmp_path / f"{stem}.mp4"
    video_path.write_bytes(b"fake video bytes")
    return video_path


def _t1_nfo_title(video_path):
    nfo_path = video_path.with_suffix(".nfo")
    return ET.parse(str(nfo_path)).getroot().find("title").text


def _t1_expected_title(number, content):
    return f"[{number}]{content}"


def _t1_mock_repo(get_by_numbers_result):
    mock_repo = MagicMock()
    mock_repo.get_by_path.return_value = None
    mock_repo.get_by_numbers.return_value = get_by_numbers_result
    mock_repo.db_path = ":memory:"
    return mock_repo


class TestFillMissingPlaceholderTitle:


    def test_fill_missing_user_edited_title_not_overwritten(self, tmp_path):
        """驗收 4a：DB title 是使用者手改過、剝前綴後不等於 stem 的字串 →
        不判定為佔位、不進 missing，其餘欄位齊全時 search_jav 完全不被呼叫。"""
        stem = "user_edited_video"
        video_path = _t1_write_video(tmp_path, stem)
        video = _make_video(title="使用者自己改過的標題")
        mock_repo = _t1_mock_repo({"SONE-205": [video]})

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav") as mock_search,
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="fill_missing",
                write_cover=False,
                write_extrafanart=False,
            )

        mock_search.assert_not_called()
        assert result.success is True
        assert _t1_nfo_title(video_path) == _t1_expected_title("SONE-205", "使用者自己改過的標題")


    def test_fill_missing_scraper_offline_with_synthetic_title_only_missing_succeeds(self, tmp_path):
        """強制刮削回歸防呆・今天會成功的列不得變失敗：DB 列八欄全滿、只有
        title 是佔位形狀，scraper 整個失敗（search_jav 回 None）→ 仍必須成功，
        title 落回原佔位值，且不記一次 scrape_attempted_at。"""
        stem = "offline_synthetic_video"
        video_path = _t1_write_video(tmp_path, stem)
        video = _make_video(title=stem)
        mock_repo = _t1_mock_repo({"SONE-205": [video]})

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=None) as mock_search,
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="fill_missing",
                write_cover=False,
                write_extrafanart=False,
            )

        mock_search.assert_called_once()
        assert result.success is True, f"today 本來就會成功的列不該變 not_found，error={result.error}"
        assert result.reason != "not_found"
        mock_repo.update_scrape_attempted_at.assert_not_called()
        assert _t1_nfo_title(video_path) == _t1_expected_title("SONE-205", stem)


    def test_fill_missing_end_to_end_number_prefixed_stem_placeholder_replaced_with_scraped(self, tmp_path):
        """CD-145a-15 表格第 1 列端到端正向：檔名 stem 就是番號本身
        （issue #182／owner 真機樣本 JURA-163.mp4 的同類情境）→ 判定為佔位，
        search_jav 被呼叫一次，NFO title 變成刮回來的真標題。"""
        stem = "SONE-205"
        video_path = _t1_write_video(tmp_path, stem)
        video = _make_video(title=stem)
        mock_repo = _t1_mock_repo({"SONE-205": [video]})
        scraper_data = _make_scraper_result(title="真正刮回來的標題")

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="fill_missing",
                write_cover=False,
                write_extrafanart=False,
            )

        mock_search.assert_called_once()
        assert result.success is True
        assert _t1_nfo_title(video_path) == _t1_expected_title("SONE-205", "真正刮回來的標題")


# ══════════════════════════════════════════════════════════════════════════════
# TASK-147b-T1（CD-147b-1 / 1b / 2 / 4b）：文字齊全但缺封面也要觸發外站查詢
# ══════════════════════════════════════════════════════════════════════════════


class TestFillMissingCoverAlsoMissing:
    def test_fill_missing_text_complete_cover_missing_triggers_search(self, tmp_path):
        """文字齊全＋缺封面＋write_cover=True＋外站有回應 → search_jav 被呼叫、
        cover_written 依外站回應、fields_filled == []（既有文字欄位逐字未變）。"""
        stem = "cover_missing_complete_video"
        video_path = _t1_write_video(tmp_path, stem)
        video = _make_video(title="使用者自己改過的標題", cover_path="")
        mock_repo = _t1_mock_repo({"SONE-205": [video]})
        scraper_data = _make_scraper_result(
            title="外站標題不該覆寫",
            cover="https://example.com/new-cover.jpg",
        )

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=scraper_data) as mock_search,
            patch("core.enricher.download_image", return_value=True),
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="fill_missing",
                write_cover=True,
                write_extrafanart=False,
            )

        mock_search.assert_called_once()
        assert result.success is True
        assert result.cover_written is True
        assert result.fields_filled == []
        assert _t1_nfo_title(video_path) == _t1_expected_title("SONE-205", "使用者自己改過的標題")


    def test_fill_missing_cover_only_missing_scraper_offline_does_not_early_return(self, tmp_path):
        """無 .nfo、文字齊全、缺封面、search_jav 回 None（非佔位標題）→ 不早退，
        success=True、nfo_written=True、磁碟真的有 .nfo、
        repo.update_scrape_attempted_at 被呼叫一次（CD-147b-1b）。"""
        stem = "cover_only_offline_no_early"
        video_path = _t1_write_video(tmp_path, stem)
        video = _make_video(title="使用者自己改過的標題", cover_path="")
        mock_repo = _t1_mock_repo({"SONE-205": [video]})

        with (
            patch("core.enricher.VideoRepository", return_value=mock_repo),
            patch("core.enricher.search_jav", return_value=None) as mock_search,
        ):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_path),
                number="SONE-205",
                mode="fill_missing",
                write_cover=True,
                write_extrafanart=False,
            )

        mock_search.assert_called_once()
        assert result.success is True, f"不得早退成 not_found，error={result.error}"
        assert result.reason != "not_found"
        assert result.nfo_written is True
        nfo_path = video_path.with_suffix(".nfo")
        assert nfo_path.is_file(), "磁碟上必須真的寫出 .nfo"
        assert nfo_path.read_text(encoding="utf-8")
        mock_repo.update_scrape_attempted_at.assert_called_once()
        assert _t1_nfo_title(video_path) == _t1_expected_title("SONE-205", "使用者自己改過的標題")


class TestIsFilenamePlaceholderTitle:
    """CD-145a-15 判定表 8 列，直接對純函式 _is_filename_placeholder_title() 驗證
    （零 mock、零 I/O）。"""

    @pytest.mark.parametrize(
        "title, stem, expected",
        [
            ("[SONE-205]", "SONE-205", True),
            ("真標題", "[SONE-205]真標題", False),
        ],
        ids=[
            "row5_legacy_bracket_only",
            "row8_organized_real_title_not_placeholder",
        ],
    )
    def test_is_filename_placeholder_title(self, title, stem, expected):
        from core.enricher import _is_filename_placeholder_title
        fs_path = f"/video/{stem}.mp4"
        assert _is_filename_placeholder_title(title, "SONE-205", fs_path) is expected


# ── TASK-154a-T1: enrich_single preserve_title ───────────────────────────────

class TestEnrichSinglePreserveTitle:
    """TASK-154a-T1: 非唯讀 enrich_single preserve_title=True 時保留既有標題。"""

    def _scraper_data(self, number="ABC-123"):
        return {
            "number": number,
            "title": "日文片名",
            "original_title": "新原題",
            "actors": ["女優A"],
            "cover": "",
            "date": "2024-01-01",
            "maker": "SOD",
            "director": "監督",
            "series": "シリーズ",
            "label": "LABEL",
            "tags": ["タグ"],
            "sample_images": [],
            "duration": 120,
            "url": "https://www.javbus.com/ABC-123",
        }

    def test_refresh_full_preserve_title_true_keeps_existing_title(self, tmp_path, mocker):
        """oracle 1（非唯讀）：preserve_title=True 時，DB title 與 NFO <title> 均保留既有標題（含前綴），其他欄位為新值。"""
        import xml.etree.ElementTree as ET
        from core.database import init_db, VideoRepository, Video
        from core.enricher import enrich_single
        from core.path_utils import to_file_uri

        db_path = tmp_path / "test_preserve.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_file = tmp_path / "ABC-123.mp4"
        video_file.write_bytes(b"\x00")
        path_uri = to_file_uri(str(video_file))

        repo.upsert(Video(
            path=path_uri,
            number="ABC-123",
            title="[ABC-123]中文片名",
            original_title="旧原題",
            maker="旧片商",
            actresses=["旧演員"],
            tags=["旧標籤"],
        ))

        mocker.patch("core.enricher.VideoRepository", return_value=repo)
        mocker.patch("core.enricher.search_jav", return_value=self._scraper_data("ABC-123"))

        result = enrich_single(
            file_path=path_uri,
            number="ABC-123",
            mode="refresh_full",
            write_nfo=True,
            write_cover=False,
            write_extrafanart=False,
            preserve_title=True,
        )
        assert result.success, result.error

        # DB title 保留既有值，其他欄位更新為新刮到的值
        row = repo.get_by_path(path_uri)
        assert row.title == "[ABC-123]中文片名"
        assert row.original_title == "新原題"
        assert row.maker == "SOD"
        assert row.actresses == ["女優A"]
        assert row.tags == ["タグ"]

        # NFO <title> 保留既有值，只有一層番號，演員與標籤為新值
        nfo_file = video_file.with_suffix(".nfo")
        assert nfo_file.exists()
        root = ET.parse(nfo_file).getroot()
        assert root.findtext("title") == "[ABC-123]中文片名"
        assert root.findtext("originaltitle") == "新原題"
        assert [a.findtext("name") for a in root.findall("actor")] == ["女優A"]
        assert [t.text for t in root.findall("tag")] == ["タグ"]

    def test_refresh_full_preserve_title_true_with_number_change_uses_new_title(self, tmp_path, mocker):
        """非唯讀 enrich_single 真實路徑（不手塞 meta['number']——search_jav 回傳走
        真正的 `_scraper_to_meta()`，其產出天生沒有 'number' key）。`allow_number_change=true`
        由 router 守衛放行後把 `number` 參數改成與 existing.number 不同的新番號
        （模擬使用者/AI 助理把這部片從 ABC-001 改號成 XYZ-002）；preserve_title=True
        若沒有正確比對 existing.number，會把舊番號 ABC-001 的標題文字配上新番號
        XYZ-002 寫進 NFO／DB。
        """
        import xml.etree.ElementTree as ET
        from core.database import init_db, VideoRepository, Video
        from core.enricher import enrich_single
        from core.path_utils import to_file_uri

        db_path = tmp_path / "test_preserve_number_change.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_file = tmp_path / "ABC-001.mp4"
        video_file.write_bytes(b"\x00")
        path_uri = to_file_uri(str(video_file))

        repo.upsert(Video(
            path=path_uri,
            number="ABC-001",
            title="[ABC-001]舊片名",
            original_title="旧原題",
            maker="旧片商",
            actresses=["旧演員"],
            tags=["旧標籤"],
        ))

        mocker.patch("core.enricher.VideoRepository", return_value=repo)
        mocker.patch("core.enricher.search_jav", return_value=self._scraper_data("XYZ-002"))

        result = enrich_single(
            file_path=path_uri,
            number="XYZ-002",  # allow_number_change=true 放行後，這次真正要寫入的新番號
            mode="refresh_full",
            write_nfo=True,
            write_cover=False,
            write_extrafanart=False,
            preserve_title=True,
        )
        assert result.success, result.error

        row = repo.get_by_path(path_uri)
        assert row.number == "XYZ-002"
        # 番號已變 → 不得保留舊標題「[ABC-001]舊片名」，必須是這次刮到的新標題
        assert row.title == "日文片名"

        nfo_file = video_file.with_suffix(".nfo")
        assert nfo_file.exists()
        root = ET.parse(nfo_file).getroot()
        assert root.findtext("title") == "[XYZ-002]日文片名"


class TestEnrichSinglePreservedTitleOverride:
    """TASK-154b-T6 / CD-154b-12：enrich_single 保留分支讀磁碟 NFO 收斂本體。"""

    def _scraper_data(self, number="ABC-123", title="日文片名", actors=None):
        return {
            "number": number,
            "title": title,
            "original_title": "新原題",
            "actors": actors if actors is not None else ["三上悠亜"],
            "cover": "",
            "date": "2024-01-01",
            "maker": "SOD",
            "director": "監督",
            "series": "シリーズ",
            "label": "LABEL",
            "tags": ["タグ"],
            "sample_images": [],
            "duration": 120,
            "url": "https://www.javbus.com/ABC-123",
        }

    def test_enrich_single_oracle_a_scanned_body_override_written_once(self, tmp_path, mocker):
        """oracle (a)：原樣掃入的自訂格式 → DB 寫回本體、NFO 單層不疊演員。"""
        import xml.etree.ElementTree as ET
        from core.database import init_db, VideoRepository, Video
        from core.enricher import enrich_single
        from core.path_utils import to_file_uri

        db_path = tmp_path / "test_oracle_a.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_file = tmp_path / "ABC-123.mp4"
        video_file.write_bytes(b"\x00")
        path_uri = to_file_uri(str(video_file))
        disk_title = "ABC-123-片名-三上悠亜"
        video_file.with_suffix(".nfo").write_text(
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<movie>\n  <title>{disk_title}</title>\n  <num>ABC-123</num>\n</movie>\n',
            encoding="utf-8",
        )

        repo.upsert(Video(
            path=path_uri,
            number="ABC-123",
            title=disk_title,
            actresses=["三上悠亜"],
            maker="",
            release_date="",
        ))

        mocker.patch("core.enricher.VideoRepository", return_value=repo)
        mocker.patch("core.enricher.search_jav", return_value=self._scraper_data())

        result = enrich_single(
            file_path=path_uri,
            number="ABC-123",
            mode="refresh_full",
            write_nfo=True,
            write_cover=False,
            write_extrafanart=False,
            overwrite_existing=True,
            preserve_title=True,
            nfo_title_format="{num}-{title}-{actor}",
        )
        assert result.success, result.error

        row = repo.get_by_path(path_uri)
        assert row.title == "片名"
        root = ET.parse(video_file.with_suffix(".nfo")).getroot()
        assert root.findtext("title") == "ABC-123-片名-三上悠亜"

    def test_enrich_single_oracle_b_disk_mismatch_keeps_existing_verbatim(self, tmp_path, mocker):
        """oracle (b)：DB 是使用者自訂標題、磁碟 NFO 是舊自訂格式 → 保留自訂值。

        若拿掉 disk≠DB 判斷，磁碟會反推出 '片名' 覆寫使用者自訂標題。
        """
        import xml.etree.ElementTree as ET
        from core.database import init_db, VideoRepository, Video
        from core.enricher import enrich_single
        from core.path_utils import to_file_uri

        db_path = tmp_path / "test_oracle_b.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_file = tmp_path / "ABC-123.mp4"
        video_file.write_bytes(b"\x00")
        path_uri = to_file_uri(str(video_file))
        existing_title = "我的自訂標題"
        disk_title = "ABC-123-片名-三上悠亜"
        video_file.with_suffix(".nfo").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<movie>\n'
            f'  <title>{disk_title}</title>\n'
            '  <num>ABC-123</num>\n'
            '</movie>\n',
            encoding="utf-8",
        )

        repo.upsert(Video(
            path=path_uri,
            number="ABC-123",
            title=existing_title,
            actresses=["三上悠亜"],
        ))

        mocker.patch("core.enricher.VideoRepository", return_value=repo)
        mocker.patch("core.enricher.search_jav", return_value=self._scraper_data())

        result = enrich_single(
            file_path=path_uri,
            number="ABC-123",
            mode="refresh_full",
            write_nfo=True,
            write_cover=False,
            write_extrafanart=False,
            overwrite_existing=True,
            preserve_title=True,
            nfo_title_format="{num}-{title}-{actor}",
        )
        assert result.success, result.error

        row = repo.get_by_path(path_uri)
        assert row.title == existing_title
        root = ET.parse(video_file.with_suffix(".nfo")).getroot()
        # generate_nfo 以保留的自訂本體重組顯示標題（不是磁碟反推的「片名」）
        assert root.findtext("title") == "ABC-123-我的自訂標題-三上悠亜"


class TestNfoTitleFormatWiring:
    """TASK-154b-T2: enrich_single nfo_title_format 轉傳測試"""

    def test_enrich_single_applies_custom_nfo_title_format_external_manager(self):
        """external_manager != 'off' 分支也能正確轉傳 nfo_title_format 給 generate_nfo"""
        video = _make_video()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo") as mock_nfo,
            patch("core.enricher.download_image", return_value=True),
            patch("core.enricher._write_cover", return_value=True),
            patch("core.enricher._write_external_images", return_value={"poster": True, "fanart": True}),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}

            from core.enricher import enrich_single
            enrich_single(
                file_path=FS_PATH,
                number="SONE-205",
                write_nfo=True,
                overwrite_existing=True,
                external_manager="jellyfin",
                nfo_title_format="{num}-{title}",
            )

        assert mock_nfo.call_args is not None, "generate_nfo 應被呼叫"
        assert mock_nfo.call_args.kwargs.get("nfo_title_format") == "{num}-{title}"


class TestEnrichHasPlotFollowsDiskNfo:
    """187b-T3：has_plot 跟磁碟 NFO；讀不到沿用既有值。"""

    def test_enrich_has_plot_follows_disk_nfo(self, tmp_path):
        from contextlib import ExitStack
        from core.enricher import enrich_single

        def _repo(**kw):
            r = MagicMock()
            r.db_path = ":memory:"
            r.get_by_numbers.return_value = kw.get("by_num", {})
            r.get_by_path.return_value = kw.get("by_path")
            return r

        def _run(repo, path, mode, data, extra=(), **ekw):
            with ExitStack() as stack:
                for p in (
                    patch("core.enricher.VideoRepository", return_value=repo),
                    patch("core.enricher.search_jav", return_value=data),
                    patch("core.enricher.download_image", return_value=True),
                    *extra,
                ):
                    stack.enter_context(p)
                return enrich_single(
                    file_path=str(path), number="SONE-205", mode=mode,
                    write_nfo=True, write_cover=False, write_extrafanart=False,
                    **ekw,
                )

        # refresh_full 寫出含 <plot> → True
        p = tmp_path / "rf.mp4"; p.write_bytes(b"x")
        data = {"title": "T", "_summary": "簡介", "url": "http://x/", "source": "scraper"}
        repo = _repo()
        assert _run(repo, p, "refresh_full", data, overwrite_existing=True,
                    scraper_data=dict(data)).success
        repo.upsert.assert_called()
        assert repo.upsert.call_args.args[0].has_plot is True

        # fill_missing + 預置含 <plot> NFO（_write_nfo 回 False）→ True
        p = tmp_path / "fm.mp4"; p.write_bytes(b"x")
        p.with_suffix(".nfo").write_text(
            '<?xml version="1.0"?><movie><title>t</title><plot>預置</plot></movie>',
            encoding="utf-8",
        )
        data = _make_scraper_result(label="FILLED")
        repo = _repo(by_num={"SONE-205": [_make_video(label="")]})
        assert _run(repo, p, "fill_missing", data, overwrite_existing=False).success
        repo.upsert.assert_called()
        assert repo.upsert.call_args.args[0].has_plot is True

        # read_plot_flag None + 既有 True → 仍 True
        p = tmp_path / "rn.mp4"; p.write_bytes(b"x")
        existing = _make_video(); existing.has_plot = True
        data = {"title": "T", "_summary": "x", "url": "http://x/", "source": "scraper"}
        repo = _repo(by_path=existing)
        assert _run(
            repo, p, "refresh_full", data,
            extra=(patch("core.enricher.read_plot_flag", return_value=None),),
            overwrite_existing=True, scraper_data=dict(data),
        ).success
        repo.upsert.assert_called()
        assert repo.upsert.call_args.args[0].has_plot is True
