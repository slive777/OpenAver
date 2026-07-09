"""
test_enricher_reason.py - TASK-94-T1: EnrichResult.reason 欄位 + enrich_single 各 return 點映射

覆蓋 CD-94-2 reason 映射表：
  - error: 缺番號 / mode 非法 / 檔案不存在 / NFO PermissionError（外部管理器 + off 模式）
  - not_found: refresh_full / db_to_sidecar / fill_missing 三處查無
  - hit / no_cover: 成功路徑依「/thumb 可服務真相＝DB cover_path 有值」分流
    （v0.11.9 Codex P1 修正；嚴禁用 cover_written 判、亦不可退回「cover.jpg 磁碟真相」）

Codex P1 回歸鎖（初版）：nfo_written=True, cover_written=False，但磁碟上 cover.jpg 本就存在
（因為 _write_cover 在 overwrite_existing=False 時對已存在檔案 skip）→ reason 必須是
'hit'，不是 'no_cover'。

Codex P1 回歸鎖（v0.11.9 修正）：reason='hit' 必須鏡射 /thumb 的 gate
（web/routers/scanner.py:1276 硬要求 DB cover_path 非空，不 fallback 磁碟 sidecar）。
磁碟有 .jpg 但 DB cover_path 空（db/nfo-sourced 命中跳過 _db_upsert，見 core/enricher.py:514）
時，不能再用「cover.jpg 磁碟真相」判 hit——否則 /thumb 404、飛入破圖、且該片仍留
missing_cover 清單。故 reason 改用 repo.get_by_path 重讀 DB 最終狀態判斷。
"""

import os
from unittest.mock import MagicMock, patch

from core.database import Video
from core.path_utils import to_file_uri


def _make_video(
    number="SONE-205",
    title="テストタイトル",
    original_title="テストタイトル",
    actresses=None,
    maker="SOD",
    director="テスト監督",
    series="テストシリーズ",
    label="LABEL",
    tags=None,
    sample_images=None,
    duration=120,
    cover_path="https://example.com/cover.jpg",
    release_date="2024-01-01",
):
    return Video(
        number=number,
        title=title,
        original_title=original_title,
        actresses=actresses if actresses is not None else ["女優A"],
        maker=maker,
        director=director,
        series=series,
        label=label,
        tags=tags if tags is not None else ["タグ"],
        sample_images=sample_images if sample_images is not None else [],
        duration=duration,
        cover_path=cover_path,
        release_date=release_date,
    )


def _make_scraper_result(number="SONE-205"):
    return {
        "number": number,
        "title": "テストタイトル",
        "actors": ["女優A"],
        "cover": "https://example.com/cover.jpg",
        "date": "2024-01-01",
        "maker": "SOD",
        "director": "テスト監督",
        "series": "テストシリーズ",
        "label": "LABEL",
        "tags": ["タグ"],
        "sample_images": [],
        "duration": 120,
        "url": "https://www.javbus.com/SONE-205",
    }


# ── error 分支 ─────────────────────────────────────────────────────────────


class TestReasonErrorBranches:
    def test_missing_number_reason_error(self):
        with patch("os.path.exists", return_value=True):
            from core.enricher import enrich_single
            result = enrich_single(file_path="/video/x.mp4", number="")
        assert result.success is False
        assert result.reason == "error"

    def test_invalid_mode_reason_error(self):
        with patch("os.path.exists", return_value=True):
            from core.enricher import enrich_single
            result = enrich_single(
                file_path="/video/x.mp4", number="SONE-205", mode="bogus_mode"
            )
        assert result.success is False
        assert result.reason == "error"

    def test_file_not_found_reason_error(self):
        with patch("os.path.exists", return_value=False):
            from core.enricher import enrich_single
            result = enrich_single(file_path="/nonexistent/x.mp4", number="SONE-205")
        assert result.success is False
        assert result.reason == "error"

    def test_external_manager_nfo_permission_error_reason(self, tmp_path):
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        video = _make_video()

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=PermissionError("denied")),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            mock_repo.get_by_path.return_value = None

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                external_manager="jellyfin",
                overwrite_existing=True,
            )

        assert result.success is False
        assert result.reason == "error"

    def test_off_mode_nfo_permission_error_reason(self, tmp_path):
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        video = _make_video()

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", side_effect=PermissionError("denied")),
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            mock_repo.get_by_path.return_value = None

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                external_manager="off",
                overwrite_existing=True,
            )

        assert result.success is False
        assert result.reason == "error"


# ── not_found 分支（三站台）───────────────────────────────────────────────


class TestReasonNotFoundBranches:
    def test_refresh_full_not_found_reason(self, tmp_path):
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=None),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file), number="SONE-205", mode="refresh_full"
            )

        assert result.success is False
        assert result.reason == "not_found"

    def test_db_to_sidecar_not_found_reason(self, tmp_path):
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")

        with patch("core.enricher.VideoRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file), number="SONE-205", mode="db_to_sidecar"
            )

        assert result.success is False
        assert result.reason == "not_found"

    def test_fill_missing_not_found_reason(self, tmp_path):
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.search_jav", return_value=None),
            patch("core.enricher.parse_nfo", return_value=(None, None)),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {}

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file), number="SONE-205", mode="fill_missing"
            )

        assert result.success is False
        assert result.reason == "not_found"


# ── 成功路徑：hit / no_cover 依「/thumb 可服務真相＝DB cover_path」分流 ──────


class TestReasonSuccessBranches:
    def test_fresh_cover_download_reason_hit(self, tmp_path):
        """有下載 + 磁碟真的寫出檔案，且 DB 該片本就有 cover_path（db_to_sidecar
        的來源片，代表先前掃描/入庫時已記錄）→ hit（/thumb 服務得到）。"""
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        cover_path = tmp_path / "SONE-205.jpg"
        video = _make_video(cover_path="https://example.com/cover.jpg")

        def fake_download(url, path):
            # 模擬真正把封面寫到磁碟
            with open(path, "wb") as f:
                f.write(b"jpegdata")
            return True

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image", side_effect=fake_download),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # DB 現有紀錄的 cover_path 有值 + 解析後的實體封面檔真的存在
            # （fake_download 已把 SONE-205.jpg 寫到磁碟）→ /thumb 兩道 gate 皆過 → hit
            mock_repo.get_by_path.return_value = _make_video(
                cover_path=to_file_uri(str(cover_path))
            )

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=True,
            )

        assert result.success is True
        assert result.cover_written is True
        assert cover_path.exists()
        assert result.reason == "hit"

    def test_no_cover_url_and_no_disk_file_reason_no_cover(self, tmp_path):
        """沒下載（無 cover_url）+ 磁碟無檔 + DB cover_path 也空 → no_cover。"""
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        video = _make_video(cover_path="")  # 無 cover_url

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # DB 該片同樣沒有 cover_path 紀錄
            mock_repo.get_by_path.return_value = _make_video(cover_path="")

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=True,
            )

        assert result.success is True
        assert result.cover_written is False
        mock_dl.assert_not_called()
        assert result.reason == "no_cover"

    def test_download_declared_true_but_file_missing_reason_no_cover(self, tmp_path):
        """cover_written=True（download_image 宣告成功）但磁碟實際上沒有檔案
        （極罕見），且 db_to_sidecar 不打 DB（source_used='db' 跳過 _db_upsert），
        DB cover_path 仍空 → /thumb 服務不到 → no_cover。"""
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        video = _make_video(cover_path="https://example.com/cover.jpg")

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            # download_image 宣告 True，但不真的寫檔
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # DB 該片 cover_path 仍空（db_to_sidecar 不寫 DB）
            mock_repo.get_by_path.return_value = _make_video(cover_path="")

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=True,
            )

        assert result.success is True
        assert result.cover_written is True  # 宣告值
        assert not (tmp_path / "SONE-205.jpg").exists()  # 磁碟無檔
        # db_to_sidecar 跳過 _db_upsert、DB cover_path 仍空 → /thumb 服務不到 → no_cover
        assert result.reason == "no_cover"

    def test_codex_p1_regression_lock_nfo_only_cover_already_exists_is_hit(self, tmp_path):
        """Codex P1 回歸鎖（初版）：本輪只補 NFO（nfo_written=True），封面本就存在磁碟
        （cover_written=False 是因為 _write_cover 對既存檔案 skip，不是因為沒有封面），
        且 DB 該片的 cover_path 本就有值（掃描/入庫時已記錄，這是主路徑：封面早已
        存在且被 DB 追蹤，本輪只是補 NFO）→ reason 必須是 'hit'，絕不能是 'no_cover'。

        這條測試若實作用 `cover_written` 來判斷 reason 就會 FAIL（因為
        cover_written 是 False）；只有用「DB cover_path 真相」（鏡射 /thumb gate）
        判斷才會 PASS。
        """
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        cover_path = tmp_path / "SONE-205.jpg"
        cover_path.write_bytes(b"existing-cover")  # 封面本就在磁碟上
        video = _make_video(cover_path="https://example.com/cover.jpg")

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True) as mock_nfo,
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # 真實主路徑：封面已入 DB（掃描時記錄）且實體檔本就在磁碟上
            # （cover_path.write_bytes 已建立），/thumb 兩道 gate 皆過 → hit
            mock_repo.get_by_path.return_value = _make_video(
                cover_path=to_file_uri(str(cover_path))
            )

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=False,  # NFO 不存在會寫；cover 已存在則 skip
            )

        # NFO 本來不存在 → 這輪會寫
        mock_nfo.assert_called_once()
        assert result.nfo_written is True
        # cover 本就存在磁碟 + overwrite_existing=False → _write_cover skip，不下載
        mock_dl.assert_not_called()
        assert result.cover_written is False
        # 磁碟上封面確實還在
        assert cover_path.exists()
        # 回歸鎖核心斷言
        assert result.reason == "hit"

    def test_codex_p1_v2_disk_cover_not_in_db_is_no_cover(self, tmp_path):
        """Codex P1 回歸鎖（v0.11.9 修正版）：磁碟有 .jpg，但 DB 該片 cover_path
        空（散落 sidecar 未入 DB／db·nfo-sourced 命中跳過 core/enricher.py:514 的
        _db_upsert）→ reason 必須是 'no_cover'，不能是 'hit'。

        /thumb（web/routers/scanner.py:1276）硬要求 DB cover_path 非空、不
        fallback 磁碟 sidecar；若這裡誤判 hit，前端命中封面飛入會拿到 404 破圖，
        且該片仍會留在 missing_cover 清單（scanner.py:~982 同樣看 DB cover_path）。

        這條測試若實作退回「cover.jpg 磁碟真相」（os.path.exists）判斷會 FAIL
        （因為磁碟上確實有檔案，會誤判 hit）；只有重讀 DB cover_path 真相
        （鏡射 /thumb gate）才會 PASS。
        """
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        cover_path = tmp_path / "SONE-205.jpg"
        cover_path.write_bytes(b"stray-cover-not-tracked-in-db")  # 磁碟有，DB 沒記錄
        video = _make_video(cover_path="https://example.com/cover.jpg")

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True) as mock_nfo,
            patch("core.enricher.download_image") as mock_dl,
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # DB 該片 cover_path 空（散落 sidecar 未入庫的 bug 案例）
            mock_repo.get_by_path.return_value = _make_video(cover_path="")

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=False,  # NFO 不存在會寫；cover 已存在則 skip
            )

        mock_nfo.assert_called_once()
        assert result.nfo_written is True
        mock_dl.assert_not_called()
        assert result.cover_written is False
        # 磁碟上確實有檔案 —— 但這不該再是 reason 的判準
        assert cover_path.exists()
        # 回歸鎖核心斷言：DB 沒記錄 → /thumb 服務不到 → 誠實回報 no_cover
        assert result.reason == "no_cover"

    def test_codex_p2_db_cover_path_set_but_file_absent_is_no_cover(self, tmp_path):
        """Codex PR #98 P2 回歸鎖：DB cover_path 非空，但用 /thumb 同一解析
        （uri_to_local_fs_path）反解後的實體封面檔不存在（已被刪/移／path_mapping
        失效解不到）→ reason 必須是 'no_cover'，不能是 'hit'。

        /thumb（scanner.py get_thumb）除了 gate 1（DB cover_path 非空，:1276）外，
        cache miss 或 disabled 時還有 gate 2：要讀實體封面檔（:1290 反解、:1300
        generate、:1332-1333 fallback os.path.isfile），檔不在 → 404。若 reason 只
        鏡射 gate 1（單看 DB cover_path 非空）就會誤判 hit → 前端命中封面飛入拿到
        404 破圖。

        mutation 驗證：把實作改回「has_servable_cover = bool(cover_uri)」（拿掉
        os.path.exists 那道 gate）會讓這條 RED。
        """
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")
        video = _make_video(cover_path="https://example.com/cover.jpg")
        # DB 記了一個實體檔已不存在的 cover_path（刪/移／UNC 未掛載）
        absent_cover_uri = to_file_uri(str(tmp_path / "gone" / "SONE-205.jpg"))

        with (
            patch("core.enricher.VideoRepository") as mock_repo_cls,
            patch("core.enricher.generate_nfo", return_value=True),
            # download_image 宣告 True 但不真的寫檔（sidecar 仍不存在）
            patch("core.enricher.download_image", return_value=True),
        ):
            mock_repo = MagicMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get_by_numbers.return_value = {"SONE-205": [video]}
            # DB cover_path 非空（過 gate 1）但實體檔不存在（擋 gate 2）
            mock_repo.get_by_path.return_value = _make_video(cover_path=absent_cover_uri)

            from core.enricher import enrich_single
            result = enrich_single(
                file_path=str(video_file),
                number="SONE-205",
                mode="db_to_sidecar",
                overwrite_existing=False,
            )

        assert result.success is True
        # 解析後的實體封面檔確實不存在
        from core.path_utils import uri_to_local_fs_path
        assert not os.path.exists(uri_to_local_fs_path(absent_cover_uri, None))
        # 回歸鎖核心斷言：DB 有 cover_path 但實體檔缺 → /thumb 服務不到 → no_cover
        assert result.reason == "no_cover"


# ── fetch_samples_only 不 crash（default reason）─────────────────────────


class TestFetchSamplesOnlyReasonDefault:
    def test_fetch_samples_only_result_has_default_reason(self, tmp_path):
        """fetch_samples_only 未顯式帶 reason → EnrichResult default (None)，不 crash。"""
        video_file = tmp_path / "SONE-205.mp4"
        video_file.write_bytes(b"x")

        with (
            patch("core.enricher.search_jav", return_value=None),
        ):
            from core.enricher import fetch_samples_only
            result = fetch_samples_only(file_path=str(video_file), number="SONE-205")

        assert result.success is False
        assert result.reason is None
        from dataclasses import asdict
        d = asdict(result)  # 不應 crash
        assert d["reason"] is None
