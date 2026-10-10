"""
test_enrich_single_metadata.py - POST /api/enrich-single 帶 metadata 之整合測試

覆蓋：
- DoD-1 (AC-1): 零查詢，search_jav 零呼叫，NFO 與 DB 寫入
- DoD-2 (CD-135-1 / M1): 模式閘（非唯讀與唯讀檔案各一案例，fill_missing / db_to_sidecar 均 400）
- DoD-3 (CD-135-2): 未知欄位 400 且 detail 含 key 名
- DoD-4 (AC-4): tags/actors/duration 型別錯誤 400 且指名欄位
- DoD-5 (CD-135-3 / M3): 忽略清單放行 ＋ 回應 source_used == "javdb"
- DoD-7 (CD-135-11): metadata ＋ javlibrary ＋ detail_url 互斥 400
- DoD-8 (CD-135-12 item 1b/3): 唯讀路徑門口檢查（ingest 400、rescrape 缺 number/title/number 為 int 400）
"""

import sqlite3
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from core.database import Video
from core.enricher import EnrichResult
from core.path_utils import to_file_uri, uri_to_fs_path

# TASK-141a-T5：本檔測的兩支端點（generate_avlist / enrich_single_endpoint）收尾會
# 無條件呼叫 reconcile_wishlist()，它用無參數 repo ⇒ 解析到真實 DB。逐檔明示 opt-in
# 隔離（fixture 定義見 tests/conftest.py，刻意不做成 autouse——見該處說明）。
pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")



@pytest.fixture(autouse=True)
def reset_buffer():
    """通知 buffer 是模組層級全域 deque，測試間必須清空，否則「恰好一筆」會閃爍。"""
    import web.routers.notifications as notif_mod
    notif_mod._notifications.clear()
    notif_mod._read_ids.clear()
    yield
    notif_mod._notifications.clear()
    notif_mod._read_ids.clear()



def _owning_stub(path="/tmp/ro_src", output_root="/out/ro_src-abcdef", output_uri="file:///out/ro_src-abcdef"):
    """`resolve_owning_output_root` 的成功回傳 stub：(source, output_root, output_uri)。"""
    source = MagicMock()
    source.path = path
    return (source, output_root, output_uri)


def _ok_result(**kwargs):
    """建立成功的 EnrichResult"""
    defaults = dict(
        success=True,
        nfo_written=True,
        cover_written=True,
        extrafanart_written=0,
        fields_filled=[],
        source_used="javdb",
        error=None,
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


class TestEnrichSingleMetadataIntegration:
    """POST /api/enrich-single 帶 metadata 之整合測試"""

    def test_ac1_zero_query_and_returns_200(self, client, mocker):
        """DoD-1 (AC-1): POST /api/enrich-single 帶合法 metadata ＋ mode=refresh_full → 200，
        且 search_jav 零呼叫；enrich_single 接收到清洗後的 metadata 作為 scraper_data。
        （本測試只驗證端點到 enrich_single 邊界傳遞，DoD-1 的真實落地由 test_ac1_e2e_full_enrich_writes_nfo_and_db 負責）
        """
        mock_search = mocker.patch("core.enricher.search_jav")
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None

        req_payload = {
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "AI 審核後標題",
                "actors": ["演員A"],
                "tags": ["標籤1"],
                "source": "javdb",
            },
        }

        response = client.post("/api/enrich-single", json=req_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 斷言 search_jav 零呼叫
        mock_search.assert_not_called()

        # 斷言 enrich_single 接收到 scraper_data
        assert mock_enrich.call_count == 1
        _, kwargs = mock_enrich.call_args
        assert kwargs["scraper_data"] is not None
        assert kwargs["scraper_data"]["title"] == "AI 審核後標題"
        assert kwargs["scraper_data"]["actors"] == ["演員A"]
        assert kwargs["scraper_data"]["source"] == "javdb"

    def test_ac1_e2e_full_enrich_writes_nfo_and_db(self, client, mocker, tmp_path):
        """DoD-1 (AC-1): 端到端真實 enrich 流程 — 帶合法 metadata ＋ mode=refresh_full，
        不 mock enrich_single，斷言三向：
        1. HTTP 200 且 success is True；
        2. 真的 NFO 檔案被寫出，XML 欄位（title/originaltitle/actors/tags/studio/director/label）逐字符合；
        3. search_jav 零呼叫，DB VideoRepository upsert 收到欄位值等於 metadata 給的值。
        """
        number = "ABC-123"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        mock_search = mocker.patch("core.enricher.search_jav")
        mock_download = mocker.patch("core.enricher.download_image", return_value=True)

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = None
        mock_repo.get_by_numbers.return_value = {}

        req_payload = {
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "AI 審核後標題",
                "original_title": "AI 審核後原標題",
                "actors": ["演員A", "演員B"],
                "tags": ["標籤1", "標籤2"],
                "maker": "片商A",
                "director": "導演A",
                "series": "系列A",
                "label": "廠牌A",
                "date": "2024-05-01",
                "duration": 120,
                "source": "javdb",
            },
        }

        response = client.post("/api/enrich-single", json=req_payload)

        # 斷言 1: HTTP 200 且 success is True
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_used"] == "javdb"

        # 斷言 2: 真的 NFO 檔案被寫出，解析 XML 比對欄位
        nfo_path = tmp_path / f"{number}.nfo"
        assert nfo_path.exists(), "NFO 檔案應被真實寫出"
        root = ET.fromstring(nfo_path.read_text(encoding="utf-8"))
        assert root.findtext("title") == f"[{number}]AI 審核後標題"
        assert root.findtext("originaltitle") == "AI 審核後原標題"
        assert root.findtext("studio") == "片商A"
        assert root.findtext("director") == "導演A"
        assert root.findtext("label") == "廠牌A"

        actor_names = [a.findtext("name") for a in root.findall("actor")]
        assert actor_names == ["演員A", "演員B"]

        nfo_tags = [t.text for t in root.findall("tag")]
        assert "標籤1" in nfo_tags
        assert "標籤2" in nfo_tags

        # 斷言 3: search_jav 零呼叫；DB upsert 收到欄位值等於 metadata
        mock_search.assert_not_called()
        mock_download.assert_not_called()

        assert mock_repo.upsert.call_count == 1
        saved_video = mock_repo.upsert.call_args[0][0]
        assert saved_video.title == "AI 審核後標題"
        assert saved_video.original_title == "AI 審核後原標題"
        assert saved_video.actresses == ["演員A", "演員B"]
        assert "標籤1" in saved_video.tags
        assert "標籤2" in saved_video.tags
        assert saved_video.maker == "片商A"
        assert saved_video.director == "導演A"
        assert saved_video.series == "系列A"
        assert saved_video.label == "廠牌A"
        assert saved_video.release_date == "2024-05-01"
        assert saved_video.duration == 120

    def test_ac_c5_refresh_full_overwrites_actresses_and_series_from_wrong_old_record(self, client, mocker, tmp_path):
        """AC-c5 / CD-155c-10: 進階重刮（refresh_full）覆蓋既有錯誤的女優（ログイン）與系列（VIP動画）。

        即使 preserve_title=True，重刮後 NFO 與 DB upsert 都必須換成新刮削到的女優與系列，
        舊的錯誤值不得殘留；同時舊標題保留生效。
        """
        from core.organizer import generate_nfo

        number = "051515-877"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)
        nfo_path = tmp_path / f"{number}.nfo"

        old_title = "舊保留標題"
        old_actors = ["ログイン"]
        old_series = "VIP動画"

        generate_nfo(
            number=number,
            title=old_title,
            actors=old_actors,
            series=old_series,
            output_path=str(nfo_path),
        )

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None

        new_title = "新刮削標題"
        new_actors = ["波多野結衣"]
        new_series = "〇〇を我慢できたら生中出し"

        mock_search = mocker.patch("core.enricher.search_jav")
        mock_search.return_value = {
            "number": number,
            "title": new_title,
            "actors": new_actors,
            "series": new_series,
            "cover": "",
            "source": "javdb",
        }
        mock_download = mocker.patch("core.enricher.download_image", return_value=True)

        old_video = Video(
            path=to_file_uri(str(mp4_path)),
            number=number,
            title=old_title,
            actresses=old_actors,
            series=old_series,
        )

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = old_video
        mock_repo.get_by_numbers.return_value = {}

        req_payload = {
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "write_nfo": True,
            "write_cover": True,
            "readonly_action": "rescrape",
            "preserve_title": True,
        }

        response = client.post("/api/enrich-single", json=req_payload)

        # 斷言 1: HTTP 200 且 success is True
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 斷言 2: NFO 檔案被寫出，且女優與系列被新值覆蓋、不留舊值；title 仍為舊標題（保留生效）
        assert nfo_path.exists(), "NFO 檔案應被真實寫出"
        root = ET.fromstring(nfo_path.read_text(encoding="utf-8"))
        assert root.findtext("title") == f"[{number}]{old_title}"
        actor_names = [a.findtext("name") for a in root.findall("actor")]
        assert actor_names == new_actors
        assert "ログイン" not in actor_names
        assert root.findtext("set/name") == new_series
        assert root.findtext("set/name") != old_series

        # 斷言 3: search_jav 被呼叫一次，download_image 零呼叫（cover 為空）
        mock_search.assert_called_once()
        mock_download.assert_not_called()

        # 斷言 4: DB upsert 收到欄位值等於新刮削值，不留舊值；title 仍為舊標題（保留生效）
        assert mock_repo.upsert.call_count == 1
        saved_video = mock_repo.upsert.call_args[0][0]
        assert saved_video.title == old_title
        assert saved_video.actresses == new_actors
        assert "ログイン" not in saved_video.actresses
        assert saved_video.series == new_series
        assert saved_video.series != old_series

    def test_mode_gate_non_readonly_fill_missing_raises_400(self, client, mocker):
        """DoD-2 (CD-135-1 / M1): 非唯讀路徑 ＋ 帶 metadata ＋ mode=fill_missing → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "fill_missing",
            "metadata": {"title": "標題"},
        })

        assert response.status_code == 400
        assert "metadata 只在 mode=refresh_full 時合法" in response.json()["detail"]

    def test_mode_gate_non_readonly_db_to_sidecar_raises_400(self, client, mocker):
        """DoD-2 (CD-135-1): 非唯讀路徑 ＋ 帶 metadata ＋ mode=db_to_sidecar → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "db_to_sidecar",
            "metadata": {"title": "標題"},
        })

        assert response.status_code == 400
        assert "metadata 只在 mode=refresh_full 時合法" in response.json()["detail"]

    def test_mode_gate_readonly_fill_missing_raises_400(self, client, mocker):
        """DoD-2 (CD-135-1 / CD-135-12): 唯讀來源 ＋ 帶 metadata ＋ mode=fill_missing → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())

        response = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "fill_missing",
            "readonly_action": "rescrape",
            "metadata": {"number": "ABC-123", "title": "標題"},
        })

        assert response.status_code == 400
        assert "metadata 只在 mode=refresh_full 時合法" in response.json()["detail"]

    def test_mode_gate_readonly_db_to_sidecar_raises_400(self, client, mocker):
        """DoD-2 (CD-135-1 / CD-135-12): 唯讀來源 ＋ 帶 metadata ＋ mode=db_to_sidecar → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())

        response = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "db_to_sidecar",
            "readonly_action": "rescrape",
            "metadata": {"number": "ABC-123", "title": "標題"},
        })

        assert response.status_code == 400
        assert "metadata 只在 mode=refresh_full 時合法" in response.json()["detail"]

    def test_unknown_field_returns_400(self, client, mocker):
        """DoD-3 (CD-135-2): metadata 含未知 key（例 titl）→ 400 且 detail 字串內含該 key 名"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"titl": "錯字標題"},
        })

        assert response.status_code == 400
        assert "titl" in response.json()["detail"]

    def test_type_validation_returns_400(self, client, mocker):
        """DoD-4 (AC-4): tags 傳字串、actors 傳字串、duration 傳 '120' → 各自 400 且指名該欄位"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)

        # tags as string
        resp1 = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"tags": "tag1,tag2"},
        })
        assert resp1.status_code == 400
        assert "tags" in resp1.json()["detail"]

        # actors as string
        resp2 = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"actors": "三上悠亞"},
        })
        assert resp2.status_code == 400
        assert "actors" in resp2.json()["detail"]

        # duration as string
        resp3 = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"duration": "120"},
        })
        assert resp3.status_code == 400
        assert "duration" in resp3.json()["detail"]

    def test_source_sink_reports_source_used(self, client, mocker):
        """DoD-5 (CD-135-3 / M3): 帶 metadata 含 source: 'javdb' → 200 且回應 source_used == 'javdb'"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None

        # Mock enrich_single: 回傳 source_used 來自 scraper_data['source']
        def mock_enrich_impl(**kwargs):
            s_data = kwargs.get("scraper_data") or {}
            source_used = s_data.get("source", "scraper") or "scraper"
            return _ok_result(source_used=source_used)

        mocker.patch("web.routers.scraper.enrich_single", side_effect=mock_enrich_impl)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "標題",
                "source": "javdb",
                "number": "ABC-123",
                "mode": "refresh_full",
                "success": True,
                "total": 1,
            },
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_used"] == "javdb"

    # --- PR #167 Codex P2: metadata.source 不可冒充後端保留值 -------------------

    def test_source_sentinel_db_rejected_400_and_nothing_written(self, client, mocker, tmp_path):
        """Codex P2: metadata.source == "db" → 400，且 NFO 與 DB 都沒被動到。

        守衛拿掉時的失敗形狀（＝這條 finding 的實害）：請求會通過，
        core/enricher.py:677 的 `source_used not in ("db", "nfo", "")` 判為 False →
        NFO 被整份改寫、`_db_upsert()` 完全不跑（DB 的 title/maker/director/series/
        label/duration/cover_path/release_date 全留舊值，只有 tags 經
        `_sync_tags_to_db` 同步），而 HTTP 仍是 200 success。
        所以這裡鎖三件事，缺一都驗不出實害：400、NFO 檔不存在、repo.upsert 零呼叫。
        """
        number = "ABC-123"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        mock_search = mocker.patch("core.enricher.search_jav")
        mocker.patch("core.enricher.download_image", return_value=True)

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = None
        mock_repo.get_by_numbers.return_value = {}

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "AI 審核後標題",
                "maker": "片商A",
                "source": "db",
            },
        })

        assert response.status_code == 400
        assert "source" in response.json()["detail"]

        # 實害鎖點：擋下來之後不得有任何寫入
        assert not (tmp_path / f"{number}.nfo").exists(), "被拒的請求不得寫出 NFO"
        assert mock_repo.upsert.call_count == 0
        mock_search.assert_not_called()

    def test_source_sentinel_nfo_rejected_400(self, client, mocker):
        """Codex P2: 另一個保留值 "nfo" 同樣 400（core/enricher.py:571 的 sentinel）。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"title": "標題", "source": "nfo"},
        })

        assert response.status_code == 400
        assert "source" in response.json()["detail"]
        mock_enrich.assert_not_called()

    def test_source_non_string_rejected_400(self, client, mocker):
        """Codex P2 後半：`source` 是忽略清單裡唯一有 sink 卻零型別驗證的 key。

        非字串本身撞不到 sentinel（`123 == "db"` 恆假），但會讓回應的 `source_used`
        違反 capabilities 宣告的 string 型別，故一併在邊界收斂。
        """
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "metadata": {"title": "標題", "source": 123},
        })

        assert response.status_code == 400
        assert "source" in response.json()["detail"]
        mock_enrich.assert_not_called()

    def test_source_sentinel_rejected_on_readonly_path_too(self, client, mocker):
        """Codex P2: 唯讀重刮走同一道 `_validate_metadata_shape`，故同樣被擋。

        鎖的是「單一驗證閘」這個結構：唯讀路徑不清洗 metadata（直接 dict(...)），
        若守衛只寫在非唯讀分支，這條路會漏。
        """
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=_owning_stub(),
        )
        mock_ro = mocker.patch("web.routers.scraper.enrich_one_readonly")

        response = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "readonly_action": "rescrape",
            "metadata": {"number": "ABC-123", "title": "標題", "source": "db"},
        })

        assert response.status_code == 400
        assert "source" in response.json()["detail"]
        mock_ro.assert_not_called()

    def test_existing_db_row_legit_source_updates_both_nfo_and_db(self, client, mocker, tmp_path):
        """Codex P2 建議的正向對照：DB 已有舊資料 ＋ 合法 source → NFO 與 DB 都更新。

        這是 sentinel 洞的「正確樣子」：同一份請求換成真實來源代號時，
        `_db_upsert()` 必須跑，DB 主欄位不得留舊值。
        """
        number = "ABC-123"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        existing = Video(
            path=to_file_uri(str(mp4_path)),  # db-ns-ok: 測試 fixture，DB round-trip 值
            number=number,
            title="舊標題",
            maker="舊片商",
            director="舊導演",
        )

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = existing
        mock_search = mocker.patch("core.enricher.search_jav")
        mocker.patch("core.enricher.download_image", return_value=True)

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = existing
        mock_repo.get_by_numbers.return_value = {}

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "AI 審核後標題",
                "maker": "片商A",
                "director": "導演A",
                "source": "javdb",
            },
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["source_used"] == "javdb"

        # NFO 有寫
        nfo_path = tmp_path / f"{number}.nfo"
        assert nfo_path.exists()
        root = ET.fromstring(nfo_path.read_text(encoding="utf-8"))
        assert root.findtext("studio") == "片商A"

        # DB 也有寫，且不是舊值
        assert mock_repo.upsert.call_count == 1
        saved = mock_repo.upsert.call_args[0][0]
        assert saved.title == "AI 審核後標題"
        assert saved.maker == "片商A"
        assert saved.director == "導演A"
        mock_search.assert_not_called()

    def test_mutual_exclusion_metadata_and_javlib_detail_url_raises_400(self, client, mocker):
        """DoD-7 (CD-135-11): 帶 metadata ＋ source=javlibrary ＋ detail_url → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "source": "javlibrary",
            "detail_url": "https://www.javlibrary.com/ja/?v=javli12345",
            "metadata": {"title": "標題"},
        })

        assert response.status_code == 400
        assert "metadata 與 javlibrary／自訂來源明細網址（detail_url）不可同時提供" in response.json()["detail"]

    def test_readonly_ingest_with_metadata_raises_400(self, client, mocker):
        """明確宣告 readonly_action="ingest" 又帶 metadata 才是 400（D-151b-2 保留的例外）。

        未宣告的情形已改為自動推導成 rescrape，那條的正向驗收在
        tests/integration/test_enrich_single_readonly_metadata.py::TestReadonlyRescrapeMetadataWiring::test_unlabeled_metadata_auto_rescrapes_200。
        """
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())

        # 明確 readonly_action="ingest"
        response = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "readonly_action": "ingest",
            "metadata": {"number": "ABC-123", "title": "標題"},
        })
        assert response.status_code == 400
        assert "唯讀來源：metadata 只在 rescrape（重刮）意圖下生效" in response.json()["detail"]

    def test_readonly_rescrape_missing_number_or_title_raises_400(self, client, mocker):
        """DoD-8 (CD-135-12 item 3): 唯讀 ＋ rescrape 但 metadata 缺 number 或缺 title → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())

        # 缺 number
        resp1 = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "readonly_action": "rescrape",
            "metadata": {"title": "標題"},
        })
        assert resp1.status_code == 400
        assert "唯讀來源重刮：metadata 缺 number" in resp1.json()["detail"]

        # 缺 title
        resp2 = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "readonly_action": "rescrape",
            "metadata": {"number": "ABC-123"},
        })
        assert resp2.status_code == 400
        assert "唯讀來源重刮：metadata 缺 title" in resp2.json()["detail"]

    def test_readonly_rescrape_number_as_int_raises_400(self, client, mocker):
        """DoD-8 (CD-135-12 / Codex round 2 P2-1): 唯讀 ＋ rescrape 但 metadata['number'] 為 int → 400"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())

        response = client.post("/api/enrich-single", json={
            "file_path": "/ro/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "readonly_action": "rescrape",
            "metadata": {"number": 123, "title": "標題"},
        })
        assert response.status_code == 400
        assert "唯讀來源重刮：metadata.number 型別錯誤，必須是字串" in response.json()["detail"]

    def test_number_guard_mismatch_raises_400_and_nfo_unchanged(self, client, mocker, tmp_path):
        """DoD-1 (AC-5 / M1): DB 既有 number="SONE-205"、請求送 number="SONE-206" ＋ metadata ＋ mode=refresh_full
        → 400，且 detail 同時含兩個番號；且既有 NFO 檔案的 mtime 與 bytes 逐位元組不變（BE-TEST-10）。
        """
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_video = Video(number="SONE-205")
        mock_repo_cls = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo_cls.return_value.get_by_path.return_value = mock_video
        # SA-pre-9 P3-1 / BE-TEST-11：沒有 path_mappings 時 canonical 與 DB round-trip key
        # 產生同一個字串，兩者對調測試不會紅（實測過）。注入一組映射讓這個分岔在測資裡
        # 真的存在，下面的 assert_called_once_with 才鎖得住「查的是哪一個 key」。
        mocker.patch("web.routers.scraper.load_config", return_value={
            "gallery": {"path_mappings": {str(tmp_path): "/mnt/nas-guard-probe"}},
        })

        # 建立既有 NFO 檔案並在 POST 之前記錄 baseline (BE-TEST-10)
        nfo_path = tmp_path / "SONE-206.nfo"
        initial_content = b"<movie><title>[SONE-205] \xe5\x8e\x9f\xe5\xa7\x8b\xe6\xa8\x99\xe9\xa1\x8c</title></movie>"
        nfo_path.write_bytes(initial_content)
        before_bytes = nfo_path.read_bytes()
        before_mtime = nfo_path.stat().st_mtime_ns

        mp4_path = tmp_path / "SONE-206.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": "SONE-206",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {"title": "新標題"},
        })

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "SONE-206" in detail
        assert "SONE-205" in detail
        assert "allow_number_change=true" in detail

        # 斷言 NFO 檔案未被改動（bytes 逐位元組 ＋ mtime 不變）
        assert nfo_path.read_bytes() == before_bytes
        assert nfo_path.stat().st_mtime_ns == before_mtime

        # SA-pre-9 P3-1：鎖住「查的是哪一個 DB key」。非唯讀那條路必須用
        # to_file_uri(uri_to_fs_path(...))（不套 path_mappings），與 core/enricher.py 的
        # _db_upsert 寫入 key 同構；換成 canonical 會在有 path_mappings 的部署上永久失效，
        # 而 mock 對任何 key 都回同一個物件，沒有這條斷言的話換掉也不會紅。
        mock_repo_cls.return_value.get_by_path.assert_called_once_with(
            to_file_uri(uri_to_fs_path(str(mp4_path)))
        )

    def test_number_guard_allow_flag_permits_change(self, client, mocker, tmp_path):
        """DoD-2 (AC-5 / M2): DB 既有 number="SONE-205"、請求送 number="SONE-206" ＋ allow_number_change=True
        → 200，且寫出的 NFO／DB 的番號真的是新番號。
        """
        number = "SONE-206"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_search = mocker.patch("core.enricher.search_jav")
        mock_download = mocker.patch("core.enricher.download_image", return_value=True)

        mock_existing = Video(number="SONE-205", title="舊標題")
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = mock_existing
        mock_repo.get_by_numbers.return_value = {}

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "allow_number_change": True,
            "metadata": {
                "title": "新標題",
                "source": "javdb",
            },
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        nfo_path = tmp_path / f"{number}.nfo"
        assert nfo_path.exists()
        root = ET.fromstring(nfo_path.read_text(encoding="utf-8"))
        assert root.findtext("title") == f"[{number}]新標題"

        mock_search.assert_not_called()
        assert mock_repo.upsert.call_count == 1
        saved_video = mock_repo.upsert.call_args[0][0]
        assert saved_video.number == number
        assert saved_video.title == "新標題"

    def test_number_guard_new_file_not_blocked(self, client, mocker):
        """DoD-3 (AC-5): DB 查無該列（get_by_path 回 None）→ 不擋（200）。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-206.mp4",
            "number": "SONE-206",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {"title": "標題"},
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_enrich.call_count == 1

    def test_number_guard_db_empty_number_not_blocked(self, client, mocker):
        """DoD-4 (AC-5 / M3): DB 有列但 existing.number 為 "" 或 None → 不擋（200）。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_existing = Video(number="")
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-206.mp4",
            "number": "SONE-206",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {"title": "標題"},
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_enrich.call_count == 1

    def test_number_guard_without_metadata_not_affected(self, client, mocker):
        """DoD-5 (AC-10): 不帶 metadata、番號與 DB 不符的既有呼叫 → 行為與現況完全相同（不擋，200）。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_existing = Video(number="SONE-205")
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-206.mp4",
            "number": "SONE-206",
            "mode": "fill_missing",
            "overwrite_existing": True,
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_enrich.call_count == 1

    def test_write_cover_none_with_metadata_preserves_cover_and_focal(self, client, mocker, tmp_path):
        """DoD-1: 帶 metadata ＋ mode=refresh_full ＋ overwrite_existing=true ＋ 不帶 write_cover
        → 200，且既有封面檔 bytes/mtime 逐位元組不變、DB cover_path 記錄不變、手動對焦排程未被呼叫、回應 cover_written=False。
        """
        number = "SONE-205"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        cover_path = tmp_path / f"{number}.jpg"
        initial_cover_bytes = b"existing-cover-image-binary-data-12345"
        cover_path.write_bytes(initial_cover_bytes)
        before_bytes = cover_path.read_bytes()
        before_mtime = cover_path.stat().st_mtime_ns

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_existing = Video(
            number=number,
            title="舊標題",
            cover_path=f"file://{cover_path}",
            auto_focal="0.5,0.5",
            crop_mode="manual",
        )
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing

        mock_search = mocker.patch("core.enricher.search_jav")
        mock_download = mocker.patch("core.enricher.download_image", return_value=True)
        mock_focal = mocker.patch("core.enricher.schedule_focal_after_cover_write")

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = mock_existing
        mock_repo.get_by_numbers.return_value = {}

        req_payload = {
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "新標題",
                "source": "javdb",
                "cover": "https://example.com/new_cover.jpg",
            },
        }

        response = client.post("/api/enrich-single", json=req_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cover_written"] is False

        # 斷言封面檔案 bytes/mtime 逐位元組不變 (BE-TEST-10)
        assert cover_path.read_bytes() == before_bytes
        assert cover_path.stat().st_mtime_ns == before_mtime

        # 斷言 DB 的 cover_path 記錄不變
        assert mock_repo.upsert.call_count == 1
        saved_video = mock_repo.upsert.call_args[0][0]
        assert saved_video.cover_path == mock_existing.cover_path

        # 斷言手動對焦座標排程未被觸發
        mock_focal.assert_not_called()
        mock_download.assert_not_called()
        mock_search.assert_not_called()

    def test_write_cover_explicit_true_with_metadata_writes_cover(self, client, mocker, tmp_path):
        """DoD-2: 帶 metadata ＋ mode=refresh_full ＋ overwrite_existing=true ＋ write_cover=True
        → 200，且封面真的被重新下載與寫入（download_image 被呼叫，cover_written=True）。
        """
        number = "SONE-205"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        cover_path = tmp_path / f"{number}.jpg"
        cover_path.write_bytes(b"old-cover")

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_existing = Video(number=number, cover_path=f"file://{cover_path}")
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing

        mock_download = mocker.patch("core.enricher.download_image", return_value=True)
        mocker.patch("core.enricher.schedule_focal_after_cover_write")

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = mock_existing
        mock_repo.get_by_numbers.return_value = {}

        req_payload = {
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "write_cover": True,
            "metadata": {
                "title": "新標題",
                "cover": "https://example.com/new_cover.jpg",
                "source": "javdb",
            },
        }

        response = client.post("/api/enrich-single", json=req_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cover_written"] is True
        mock_download.assert_called()

    def test_write_cover_none_without_metadata_writes_cover(self, client, mocker):
        """DoD-3 (AC-10 / M3): 不帶 metadata、不帶 write_cover（None）→ 照舊換封面（傳給 enrich_single 的 write_cover 必須為 True）。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )
        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "fill_missing",
        })
        assert response.status_code == 200
        assert mock_enrich.call_count == 1
        assert mock_enrich.call_args.kwargs["write_cover"] is True

    def test_write_cover_explicit_false_without_metadata_preserves_cover(self, client, mocker):
        """DoD-4 (AC-10): 不帶 metadata、顯式 write_cover=False → 傳給 enrich_single 的 write_cover 必須為 False。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javdb")
        )
        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "fill_missing",
            "write_cover": False,
        })
        assert response.status_code == 200
        assert mock_enrich.call_count == 1
        assert mock_enrich.call_args.kwargs["write_cover"] is False

    def test_will_write_external_guard_requires_resolved_write_cover_p1_3_regression(self, client, mocker, tmp_path):
        """DoD-6 (Codex P1-3 / M2): external_manager=jellyfin ＋ metadata（不帶 write_cover）＋ overwrite_existing=false
        ＋ 既有 NFO 存在 ＋ 既有正典同名封面存在 ＋ -poster.jpg 存在但 -fanart.jpg 缺 → 400（分裂守衛擋下）。
        """
        number = "SONE-205"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        nfo_path = tmp_path / f"{number}.nfo"
        nfo_path.write_text("<movie><title>舊標題</title></movie>", encoding="utf-8")

        # 注意：正典封面必須建同名 .jpg（不是 -fanart.jpg）
        cover_path = tmp_path / f"{number}.jpg"
        cover_path.write_bytes(b"existing-cover-bytes")

        poster_path = tmp_path / f"{number}-poster.jpg"
        poster_path.write_bytes(b"existing-poster-bytes")

        # SONE-205-fanart.jpg 刻意不建立（fanart 缺）

        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={
                "scraper": {"external_manager": "jellyfin"},
                "search": {},
                "gallery": {},
            },
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mock_existing = Video(number=number)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = mock_existing

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": False,
            "metadata": {"title": "任意新標題"},
        })

        assert response.status_code == 400
        assert "不會寫出任何 NFO/封面" in response.json()["detail"]


class TestEnrichSingleWishlistReconcile:
    """TASK-141a-T5：enrich-single 一般分支掛 reconcile_wishlist（DoD 2/4/5）。"""

    def _patch_reconcile_db(self, monkeypatch, db_path):
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
        monkeypatch.setattr("core.wishlist_cover_cache.get_db_path", lambda: db_path)

    def test_enrich_single_reconciles_wishlist_on_success(
        self, client, mocker, tmp_path, monkeypatch
    ):
        """DoD 2（一般分支）：成功 enrich → 恰好一筆 auto_removed，書籤消失。"""
        from core.database import init_db, WishlistRepository, VideoRepository

        number = "OWNED-ENR-001"
        mp4_path = tmp_path / f"{number}.mp4"
        mp4_path.write_bytes(b"\x00" * 16)

        db_path = tmp_path / "wishlist.db"
        init_db(db_path)
        self._patch_reconcile_db(monkeypatch, db_path)
        WishlistRepository().add(number, title="Owned")
        VideoRepository().upsert(Video(
            path=to_file_uri(str(mp4_path)),
            number=number,
            title="Owned Video",
        ))

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        mocker.patch("core.enricher.search_jav")
        mocker.patch("core.enricher.download_image", return_value=True)

        mock_repo_cls = mocker.patch("core.enricher.VideoRepository")
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.db_path = ":memory:"
        mock_repo.get_by_path.return_value = None
        mock_repo.get_by_numbers.return_value = {}

        response = client.post("/api/enrich-single", json={
            "file_path": str(mp4_path),
            "number": number,
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {
                "title": "AI Title",
                "actors": ["A"],
                "tags": ["T"],
                "source": "javdb",
            },
        })

        assert response.status_code == 200
        assert response.json()["success"] is True

        notif_items = client.get("/api/notifications").json()["items"]
        auto_removed = [
            i for i in notif_items if i["title_key"] == "notif.wishlist_auto_removed"
        ]
        assert len(auto_removed) == 1
        assert auto_removed[0]["level"] == "info"
        assert auto_removed[0]["task_type"] == "wishlist_reconcile"

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT 1 FROM wishlist WHERE number = ?", (number,)
        ).fetchone()
        conn.close()
        assert row is None

    def test_enrich_single_reconcile_failure_keeps_success_response(
        self, client, mocker, monkeypatch, tmp_path
    ):
        """DoD 4（一般分支）：對帳丟例外時回應仍是完整成功 EnrichResult。"""
        from core.database import init_db

        db_path = tmp_path / "wishlist.db"
        init_db(db_path)
        self._patch_reconcile_db(monkeypatch, db_path)

        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        ok = _ok_result(
            nfo_written=True,
            cover_written=False,
            fields_filled=["title"],
            source_used="javdb",
            reason="hit",
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=ok)

        payload = {
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {"title": "T", "source": "javdb"},
        }

        # BE-TEST-10：baseline 在注入例外之前取得（對帳走 tmp DB，不碰真實庫）
        baseline = client.post("/api/enrich-single", json=payload)
        assert baseline.status_code == 200
        baseline_data = baseline.json()
        assert baseline_data["success"] is True

        import web.routers.notifications as notif_mod
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()

        def _boom():
            raise RuntimeError("reconcile exploded")

        # raising=False：實作前屬性尚不存在；RED 應落在「未發 warn」而非 AttributeError
        monkeypatch.setattr("web.routers.scraper.reconcile_wishlist", _boom, raising=False)

        response = client.post("/api/enrich-single", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["nfo_written"] == baseline_data["nfo_written"]
        assert data["cover_written"] == baseline_data["cover_written"]
        assert data["fields_filled"] == baseline_data["fields_filled"]
        assert data["source_used"] == baseline_data["source_used"]
        assert data["reason"] == baseline_data["reason"]

        notif_items = client.get("/api/notifications").json()["items"]
        warn_items = [
            i for i in notif_items
            if i["title_key"] == "notif.wishlist_reconcile_failed"
        ]
        assert len(warn_items) == 1
        assert warn_items[0]["level"] == "warn"

    def test_enrich_single_skips_reconcile_when_enrich_fails(self, client, mocker):
        """DoD 5：result.success 為 False → reconcile_wishlist 呼叫次數為 0。"""
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=None)
        mocker.patch("web.routers.scraper.VideoRepository").return_value.get_by_path.return_value = None
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=EnrichResult(
                success=False,
                nfo_written=False,
                cover_written=False,
                extrafanart_written=0,
                fields_filled=[],
                source_used="",
                error="刮削失敗",
            ),
        )
        reconcile_spy = mocker.patch("web.routers.scraper.reconcile_wishlist", create=True)

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/ABC-123.mp4",
            "number": "ABC-123",
            "mode": "refresh_full",
            "overwrite_existing": True,
            "metadata": {"title": "T", "source": "javdb"},
        })

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert reconcile_spy.call_count == 0

