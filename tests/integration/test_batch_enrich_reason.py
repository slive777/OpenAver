"""
test_batch_enrich_reason.py - POST /api/batch-enrich `result-item` 三站台 reason 契約
（TASK-94-T2）

三個 emit 站台：
- 〔a〕正常結果：`asdict(EnrichResult)` 因 T1（core/enricher.py）已加 `reason` 欄位而
  自動流出（連同既有的 `source_used`）。本 task 對此站台零改動，這裡只補斷言。
- 〔b〕唯讀 guard：手組 dict 加 `reason: 'readonly'`。
- 〔c〕例外 catch-all：手組 dict 加 `reason: 'error'`。

Mock 邊界：patch `web.routers.scraper.search_jav` / `web.routers.scraper.enrich_single`
（使用端，非定義端），不打真網路。
"""

import json
from pathlib import Path

import pytest

from core.path_utils import to_file_uri


# ── helper ───────────────────────────────────────────────────────────────────

def parse_sse(text: str) -> list:
    """解析 SSE 文字，回傳事件 dict 列表"""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _ok_result(**kwargs):
    """建立成功的 EnrichResult mock 物件（T1 已加 reason 欄位）"""
    from core.enricher import EnrichResult
    defaults = dict(
        success=True,
        nfo_written=True,
        cover_written=True,
        extrafanart_written=0,
        fields_filled=[],
        source_used="javbus",
        error=None,
        reason="hit",
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


def _err_result(error: str, reason: str, **kwargs):
    """建立失敗的 EnrichResult mock 物件"""
    from core.enricher import EnrichResult
    defaults = dict(
        success=False,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=0,
        fields_filled=[],
        source_used="",
        error=error,
        reason=reason,
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


@pytest.fixture(autouse=True)
def _stub_search_jav(mocker):
    """整檔預設 mock 掉 search_jav，杜絕 refresh_full pre-fetch 打真外站。"""
    mocker.patch(
        "web.routers.scraper.search_jav",
        return_value={"title": "stub", "source": "javbus"},
    )


# ── 站台〔a〕正常結果：reason + source_used 隨 asdict 自動流出 ──────────────────

class TestResultItemNormalStationReason:
    """本 task 對此站台零改動（T1 已在 EnrichResult 加 reason），這裡只驗證 SSE 契約。"""

    @pytest.mark.parametrize("reason", ["hit", "no_cover", "not_found", "error"])
    def test_reason_enum_values_flow_through(self, client, mocker, reason):
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(reason=reason, source_used="javbus"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "file:///nas/IPZ-154.mp4", "number": "IPZ-154"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["reason"] == reason
        assert result_items[0]["source_used"] == "javbus"

    def test_not_found_result_item_reason_and_success_false(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_err_result("找不到番號資料", reason="not_found"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "file:///nas/XXX-999.mp4", "number": "XXX-999"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "not_found"


# ── 站台〔b〕唯讀改道：TASK-104-T3（CD-104-5）前身「唯讀 guard：reason=='readonly'」──
#
# 唯讀項不再是一個會被拒絕的獨立「站台」——它現在改道 `resolve_owning_output_root`
# → `resolve_ingest_plan` → `_produce_one`（router-level mock，同 test_api_enrich.py
# 的 TestReadonlyRoutingE2E 慣例，避免真連 core.readonly_producer.search_jav 外站）。
# 成功改道時的 result-item 是手組 dict `{'type':..., 'number':..., 'file_path':...,
# 'success': True}`（scraper.py 的 `_do_readonly` 'ok' 分支）——**不含** `reason` /
# `source_used` 欄位（與站台〔a〕`asdict(EnrichResult)` 不同源，非同一個 dataclass），
# 這是本 task 對三站台 reason 契約的既有事實變動，非疏漏。失敗分支（no_scrape/
# error/skip）仍帶 `reason`，維持原本「reason 契約」對失敗語意的覆蓋。


class TestResultItemReadonlyStationReason:
    def _readonly_config(self):
        return {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {},
            "scraper": {},
        }

    def _mock_readonly_routing(self, mocker, plan_return=None):
        from unittest.mock import MagicMock
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=plan_return
            if plan_return is not None
            else ({"number": "RO-001", "title": "T", "cover": ""}, ("none",)),
        )
        # _produce_one now returns (movie_dir, assets) — tuple default so the
        # router's `_, assets = _produce_one(...)` unpack succeeds.
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-x/RO-001"), {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        # cover_path="" explicit (FIX#1 has_servable_cover reads this) — a bare
        # MagicMock() attribute is truthy by default, which would silently flip
        # reason to 'hit' for the no-cover scenario this helper's default models.
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0, cover_path="")
        return mock_produce

    # 歷史命名保留（TASK-104-T3 改寫，CD-104-10：不可為保綠而還原新碼）：唯讀項
    # 改道成功 → success:True，不再是 reason:'readonly' 的拒絕結果；enrich_single
    # 仍不被呼叫（唯讀路徑走 resolve_ingest_plan/_produce_one，非 enrich_single）。
    def test_readonly_item_reason_readonly(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")
        mock_produce = self._mock_readonly_routing(mocker)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is True
        assert result_items[0]["file_path"] == "/tmp/ro_src/RO-001.mp4"
        # Codex PR#113 one-pass alignment（2026-07-21）：改道成功 result-item 現在
        # spread 一個真 asdict(EnrichResult(...)) 進 SSE envelope（shape parity 用
        # dataclass 結構保證，不再是手組 dict）——之前的斷言「source_used 這組概念
        # 不適用於唯讀改道」已過期：EnrichResult 的 8 個欄位一律齊全，source_used
        # 缺 'source' key 的 mock meta 落回 meta.get('source','') == ''，而非整個
        # 缺席。reason 語意不變（hit/no_cover）——此 mock 的 cover_strategy=('none',)
        # + assets['cover_fs']='' → no_cover（不然 state-batch.js _resolveCardStatus
        # 的 success-implies-'hit' 預設會誤報成 hit，見
        # web/static/js/pages/scanner/state-batch.js:300）。
        assert result_items[0]["reason"] == "no_cover"
        assert result_items[0]["source_used"] == ""
        assert set(result_items[0]) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }
        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["assets_mode"] == "full"
        # 唯讀項改走 resolve_ingest_plan/_produce_one，不觸及 enrich_single
        mock_enrich.assert_not_called()

    # 失敗分支仍帶 reason（此處 'not_found'——Codex PR#113 one-pass alignment，對齊
    # core.enricher 自己的 not_found reason 值，取代內部狀態碼 'no_scrape'）——
    # 站台〔b〕reason 契約在失敗語意上維持成立。
    def test_readonly_item_no_scrape_reason_no_scrape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")
        mock_produce = self._mock_readonly_routing(mocker, plan_return=(None, ("none",)))

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "not_found"
        assert set(result_items[0]) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }
        mock_produce.assert_not_called()
        mock_enrich.assert_not_called()


# ── 站台〔c〕例外 catch-all：reason == 'error' ──────────────────────────────

class TestResultItemExceptionStationReason:
    def test_enrich_exception_reason_error(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=Exception("boom"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "file:///nas/ERR-001.mp4", "number": "ERR-001"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "error"


# ── 時序鎖（CD-94-4）：hit 片 result-item 後，/thumb 回 200 ─────────────────

class TestResultItemThumbTimingLock:
    """CD-94-4：某 hit 片 result-item 後，`GET /api/gallery/thumb?path=<file_path>` 回 200。

    `enrich_single` 真跑時，DB upsert（`_db_upsert`，enricher.py:503-512）保證在 return
    （T1 已完成、非本 task 範圍）之前完成；router 層的 `thumbnail_cache.invalidate`
    （scraper.py:556）在 `result-item` yield（559）之前執行。本測試 mock 掉
    `enrich_single`（依專案規則不可打真網路 / 真 enrich pipeline），改為**先在 DB
    種好「已完成」狀態**（模擬 enrich_single 真跑後的落地結果），驗證 router 層
    invalidate + emit 之後，前端立刻打 /thumb 不會因 stale cache 或 DB 未就緒而失敗
    ——這是本 task 唯一能在 router 邊界鎖住的部分（DB 寫入時序本身由 T1 背書）。
    """

    @pytest.fixture
    def thumb_dir(self, tmp_path, mocker):
        d = tmp_path / "thumb"
        d.mkdir()
        mocker.patch("core.thumbnail_cache._thumb_dir", return_value=d)
        return d

    @pytest.fixture
    def temp_db(self, tmp_path, mocker):
        from core.database import init_db, VideoRepository
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)
        return db_path, repo

    def test_hit_result_item_then_thumb_returns_200(
        self, client, mocker, thumb_dir, temp_db, tmp_path
    ):
        from PIL import Image
        from core.database import Video

        _, repo = temp_db
        cover = tmp_path / "cover.jpg"
        Image.new("RGB", (200, 150), (10, 20, 30)).save(cover, "JPEG")

        file_uri = to_file_uri("/nas/videos/IPZ-900.mp4")
        cover_uri = to_file_uri(str(cover))

        # 模擬 enrich_single 真跑後「已完成」的落地狀態：DB row + 真封面檔已就緒
        repo.upsert_batch([Video(path=file_uri, mtime=100.0, cover_path=cover_uri)])

        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={"gallery": {}, "search": {}, "scraper": {}},
        )
        mocker.patch(
            "web.routers.scanner.load_config",
            return_value={"thumbnail_cache_enabled": False, "gallery": {}},
        )
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(reason="hit", source_used="javbus"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": file_uri, "number": "IPZ-900"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is True
        assert result_items[0]["reason"] == "hit"
        assert result_items[0]["file_path"] == file_uri

        # 時序鎖：result-item 已收到後，/thumb 立刻查詢應 200
        # （thumbnail_cache_enabled=False → fallback 原圖路徑；DB cover 已就緒 → 非 404）
        thumb_resp = client.get("/api/gallery/thumb", params={"path": file_uri})
        assert thumb_resp.status_code == 200
