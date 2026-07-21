"""
test_api_batch_enrich.py - POST /api/batch-enrich 端點整合測試（SSE Streaming）

使用 FastAPI TestClient + mocker，mock web.routers.scraper.enrich_single（使用端）。
"""

import json
from pathlib import Path

import pytest
from unittest.mock import MagicMock


# ── helper ───────────────────────────────────────────────────────────────────

def parse_sse(text: str) -> list:
    """解析 SSE 文字，回傳事件 dict 列表"""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _ok_result(**kwargs):
    """建立成功的 EnrichResult mock 物件"""
    from core.enricher import EnrichResult
    defaults = dict(
        success=True,
        nfo_written=True,
        cover_written=True,
        extrafanart_written=0,
        fields_filled=[],
        source_used="javbus",
        error=None,
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


def _err_result(error: str):
    """建立失敗的 EnrichResult mock 物件"""
    from core.enricher import EnrichResult
    return EnrichResult(
        success=False,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=0,
        fields_filled=[],
        source_used="",
        error=error,
    )


# ── tests ────────────────────────────────────────────────────────────────────

class TestBatchEnrich:

    @pytest.fixture(autouse=True)
    def _stub_search_jav(self, mocker):
        """預設 mock 掉 search_jav。

        refresh_full 模式下 router 會 pre-fetch search_jav（scraper.py:338），
        未 mock 時會真的打外站、空等 timeout（單測曾各拖 7~17 秒）。這裡給個
        stub 預設值，杜絕整個 class 誤連外網；需要驗證 search 行為（call_count /
        負向 cache）的測試會自行 re-patch 覆蓋。enrich_single 在各測試已 mock，
        會忽略這個 cached data，所以回什麼 dict 不影響斷言。
        """
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"title": "stub", "source": "javbus"},
        )

    def test_batch_single_item_sse_events(self, client, mocker):
        """1 筆成功：progress + result-item(success=True) + done 事件順序正確"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)

        # 應有 3 個事件：progress, result-item, done
        assert len(events) == 3

        # 第一個事件：progress
        assert events[0]["type"] == "progress"
        assert events[0]["current"] == 1
        assert events[0]["total"] == 1
        assert events[0]["number"] == "IPZ-154"

        # 第二個事件：result-item，success=True
        assert events[1]["type"] == "result-item"
        assert events[1]["number"] == "IPZ-154"
        assert events[1]["file_path"] == "/video/IPZ-154.mp4"
        assert events[1]["success"] is True

        # 第三個事件：done
        assert events[2]["type"] == "done"
        assert events[2]["summary"]["total"] == 1
        assert events[2]["summary"]["success"] == 1
        assert events[2]["summary"]["failed"] == 0

    def test_batch_done_summary_counts(self, client, mocker):
        """2 筆，1 成功 1 失敗：done.summary.success/failed 正確計數"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=[
                _ok_result(),
                _err_result("檔案不存在"),
            ],
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"},
                {"file_path": "/video/SONE-205.mp4", "number": "SONE-205"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)

        # 取得 done 事件
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1

        summary = done_events[0]["summary"]
        assert summary["total"] == 2
        assert summary["success"] == 1
        assert summary["failed"] == 1

    def test_batch_empty_items_returns_done(self, client, mocker):
        """空 items → 直接 done，summary 全 0"""
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)

        # 不呼叫 enrich_single
        mock_enrich.assert_not_called()

        # 只有 done 事件
        assert len(events) == 1
        assert events[0]["type"] == "done"
        assert events[0]["summary"]["total"] == 0
        assert events[0]["summary"]["success"] == 0
        assert events[0]["summary"]["failed"] == 0

    def test_batch_over_limit_returns_422(self, client, mocker):
        """21 筆 → HTTP 422"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        items = [
            {"file_path": f"/video/IPZ-{i:03d}.mp4", "number": f"IPZ-{i:03d}"}
            for i in range(21)
        ]

        response = client.post("/api/batch-enrich", json={
            "items": items,
            "mode": "refresh_full",
        })

        assert response.status_code == 422

    def test_batch_duplicate_path_deduped(self, client, mocker):
        """同 file_path 兩筆 → enrich_single 只呼叫 1 次"""
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"},
                {"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"},  # 重複
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200

        # enrich_single 只被呼叫 1 次
        assert mock_enrich.call_count == 1

        events = parse_sse(response.text)
        done_events = [e for e in events if e["type"] == "done"]
        # total 只計去重後的數量
        assert done_events[0]["summary"]["total"] == 1

    def test_batch_enrich_failure_continues(self, client, mocker):
        """第 1 筆 enrich_single 回傳 error → result-item success=False，第 2 筆仍正常處理"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=[
                _err_result("找不到番號資料"),
                _ok_result(),
            ],
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/video/XXX-999.mp4", "number": "XXX-999"},
                {"file_path": "/video/SONE-205.mp4", "number": "SONE-205"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)

        result_items = [e for e in events if e["type"] == "result-item"]
        assert len(result_items) == 2

        # 第 1 筆失敗
        assert result_items[0]["success"] is False
        assert result_items[0]["number"] == "XXX-999"

        # 第 2 筆成功
        assert result_items[1]["success"] is True
        assert result_items[1]["number"] == "SONE-205"

        # done summary 正確計數
        done_events = [e for e in events if e["type"] == "done"]
        assert done_events[0]["summary"]["success"] == 1
        assert done_events[0]["summary"]["failed"] == 1

    def test_batch_content_type_is_event_stream(self, client, mocker):
        """response.headers['content-type'] 含 'text/event-stream'"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"}],
            "mode": "refresh_full",
        })

        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_batch_same_number_only_searches_once(self, client, mocker):
        """同番號不同 file_path → search_jav 只呼叫 1 次（scraper cache 命中）"""
        scraper_result = {"title": "テスト", "source": "javbus"}

        mock_search = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=scraper_result,
        )
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/video/IPZ-154a.mp4", "number": "IPZ-154"},
                {"file_path": "/video/IPZ-154b.mp4", "number": "IPZ-154"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        # search_jav 只應被呼叫 1 次，第 2 筆命中 cache
        assert mock_search.call_count == 1

    def test_batch_fill_missing_does_not_prefetch(self, client, mocker):
        """fill_missing mode → search_jav 不被 router 層 pre-fetch，由 enrich_single 內部決定"""
        mock_search = mocker.patch(
            "web.routers.scraper.search_jav",
        )
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"}],
            "mode": "fill_missing",
        })

        assert response.status_code == 200
        # router 層不應呼叫 search_jav（fill_missing 由 enrich_single 內部處理）
        mock_search.assert_not_called()

    def test_batch_negative_cache_no_repeat_search(self, client, mocker):
        """search_jav 回 None → 負向 cache 生效，同番號第 2 筆不再打外站"""
        mock_search = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=None,  # 找不到資料
        )
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(success=False),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/video/IPZ-154a.mp4", "number": "IPZ-154"},
                {"file_path": "/video/IPZ-154b.mp4", "number": "IPZ-154"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        # search_jav 只應被呼叫 1 次，第 2 筆命中負向 cache
        assert mock_search.call_count == 1

    def test_batch_invalid_mode_returns_422(self, client, mocker):
        """mode='bad_mode' → HTTP 422"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/video/IPZ-154.mp4", "number": "IPZ-154"}],
            "mode": "bad_mode",
        })

        assert response.status_code == 422


class TestBatchEnrichReadonlyGuard:
    """TASK-104-T3（CD-104-5，前身 TASK-90c-T1 的「一律拒絕」guard）：batch 逐項唯讀
    不再拒絕——改道 output_dir，action 固定 'ingest'（batch 語意＝補缺、非撞號選版），
    經 `run_in_executor` offload（async-offload 守衛）。混合批（1 唯讀 + 1 可寫）→
    唯讀項改道成功（success:True，經 `resolve_owning_output_root` →
    `resolve_ingest_plan` → `_produce_one`）、可寫項照常走既有 `enrich_single`；
    整批不中斷。load_config patch 呼叫處 binding，batch 走
    await asyncio.to_thread(load_config) 仍生效；iter_gallery_sources 用 real。

    Mock 邊界：`resolve_owning_output_root`/`resolve_ingest_plan`/`_produce_one`/
    `VideoRepository`（router-level，比照 test_api_enrich.py 的
    `TestReadonlyRoutingE2E` 慣例）——唯讀項用假路徑（不落真實 FS），若不 mock這三者
    會落到真實 `core.readonly_producer.search_jav`（真連外站）；本檔案其餘測試向來
    只 mock 使用端 `web.routers.scraper.*`，故沿用同一層級 mock，不下探到
    `core.readonly_producer.*`（那層的行為已有 test_readonly_producer.py /
    test_api_enrich.py::TestReadonlyRoutingE2E 覆蓋，此檔只驗證 router 的
    dispatch/offload/SSE 契約）。"""

    @pytest.fixture(autouse=True)
    def _stub_search_jav(self, mocker):
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"title": "stub", "source": "javbus"},
        )

    def _readonly_config(self):
        return {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {},
            "scraper": {},
        }

    def _mock_readonly_routing(self, mocker, plan_return=None, produce_side_effect=None):
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mock_owning = mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mock_plan = mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=plan_return
            if plan_return is not None
            else ({"number": "RO-001", "title": "T", "cover": ""}, ("none",)),
        )
        # _produce_one now returns (movie_dir, assets) — this default return_value
        # (only used when produce_side_effect is None) keeps the router's
        # `_, assets = _produce_one(...)` unpack from raising on a bare MagicMock.
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            side_effect=produce_side_effect,
            return_value=(Path("/out/ro_src-x/RO-001"), {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0)
        return mock_owning, mock_plan, mock_produce, mock_repo

    def test_mixed_batch_readonly_routes_writable_enriched(self, client, mocker):
        """唯讀項不再拒絕：改道成功（success:True），可寫項照常 enrich，整批不中斷。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )
        emit_spy = mocker.patch("web.routers.scraper._emit_notif")
        _mock_owning, mock_plan, mock_produce, _mock_repo = self._mock_readonly_routing(mocker)

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"},
                {"file_path": "/tmp/rw/RW-002.mp4", "number": "RW-002"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)
        result_items = [e for e in events if e["type"] == "result-item"]
        assert len(result_items) == 2

        by_number = {e["number"]: e for e in result_items}
        # 唯讀項：不再拒絕，改道成功
        assert by_number["RO-001"]["success"] is True
        assert by_number["RO-001"]["file_path"] == "/tmp/ro_src/RO-001.mp4"
        # 可寫項：照常 enrich 成功
        assert by_number["RW-002"]["success"] is True

        # 唯讀項經 resolve_ingest_plan(action='ingest') → _produce_one(assets_mode='full')
        mock_plan.assert_called_once()
        assert mock_plan.call_args.kwargs["action"] == "ingest"
        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["assets_mode"] == "full"

        # enrich_single 只被可寫項呼叫一次（唯讀項改走 resolve_ingest_plan/_produce_one）
        assert mock_enrich.call_count == 1

        # done summary 計數對稱（兩項皆成功）
        done = [e for e in events if e["type"] == "done"][0]
        assert done["summary"] == {"total": 2, "success": 2, "failed": 0}

        # _emit_notif 只在批次層呼叫（started + done），唯讀項不逐項發 notif
        assert emit_spy.call_count == 2

    # P2 review (2026-07-21): the readonly batch success result-item was
    # `{'success': True}` only — no nfo_written/cover_written — so
    # state-batch.js's badge counter / cover fly-in animation (which key off
    # `event.nfo_written || event.cover_written`, see
    # web/static/js/pages/scanner/state-batch.js:174/188) never fired for a
    # readonly item that DID generate assets. cover_written must reflect
    # `assets['cover_fs']` truthiness (here: non-empty → True); nfo_written is
    # unconditionally True on any 'ok' full-mode result (a failed NFO write
    # raises inside _produce_one, which the offload's except-branch turns into
    # an 'error' status, never reaching 'ok').
    def test_readonly_batch_success_item_carries_nfo_and_cover_written(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=({"number": "RO-001", "title": "T", "cover": ""}, ("none",)),
        )
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(
                Path("/out/ro_src-x/RO-001"),
                {"cover_fs": "/out/ro_src-x/RO-001/RO-001.jpg", "sample_fs": [], "nfo_mtime": 1.0},
            ),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["nfo_written"] is True
        assert result_items[0]["cover_written"] is True
        # Codex PR#113 P2 #2: reason must mirror non-readonly EnrichResult
        # semantics (core/enricher.py:603) — a cover-bearing success is 'hit',
        # matching state-batch.js _resolveCardStatus's explicit 'hit' case
        # (not its success-implies-'hit' default fallback, :300).
        assert result_items[0]["reason"] == "hit"

    def test_readonly_batch_success_item_cover_written_false_when_no_cover(self, client, mocker):
        """cover_written must be False, not just truthy-omitted, when
        assets['cover_fs'] is '' (e.g. cover_strategy=('none',) — an ingest with
        an .nfo but no local/remote cover available)."""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=({"number": "RO-001", "title": "T", "cover": ""}, ("none",)),
        )
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-x/RO-001"), {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["nfo_written"] is True
        assert result_items[0]["cover_written"] is False
        # Codex PR#113 P2 #2: an NFO-only ingest (no cover) success must carry
        # reason='no_cover', NOT be left to state-batch.js's success-implies-'hit'
        # default fallback (:300) — that default would wrongly build a
        # /api/gallery/thumb URL for a cover that was never written.
        assert result_items[0]["reason"] == "no_cover"

    def test_readonly_item_no_scrape_still_fails_batch_continues(self, client, mocker):
        """唯讀項改道但找不到可用番號資料（resolve_ingest_plan 回 meta=None）→
        仍是失敗結果（reason='no_scrape'），可寫項不受影響，整批不中斷。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )
        _mock_owning, _mock_plan, mock_produce, _mock_repo = self._mock_readonly_routing(
            mocker, plan_return=(None, ("none",)),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"},
                {"file_path": "/tmp/rw/RW-002.mp4", "number": "RW-002"},
            ],
            "mode": "refresh_full",
        })

        events = parse_sse(response.text)
        result_items = [e for e in events if e["type"] == "result-item"]
        by_number = {e["number"]: e for e in result_items}

        assert by_number["RO-001"]["success"] is False
        assert by_number["RO-001"]["reason"] == "no_scrape"
        mock_produce.assert_not_called()
        assert by_number["RW-002"]["success"] is True

        done = [e for e in events if e["type"] == "done"][0]
        assert done["summary"] == {"total": 2, "success": 1, "failed": 1}


class TestBatchEnrichReadonlyCoverPreserveGate:
    """Codex PR#113 P2#3/P2#4（round 2，owner-confirmed 全面對齊）：batch readonly
    的 cover-preserve gate + cover-written focal reset/re-submit，鏡射
    tests/integration/test_api_enrich.py::TestEnrichSingleReadonlyCoverPreserveGate
    同一組場景。BatchEnrichRequest 沒有 per-item mode/write_cover/overwrite_existing
    覆寫欄位（BatchEnrichItem 只帶 file_path/number/source/javbus_lang），一律用整批
    request 的值——每個測試只需構造單一 readonly item。"""

    def _readonly_config(self):
        return {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {},
            "scraper": {},
        }

    def _mock_routing(
        self, mocker, *, existing_cover_path="",
        plan_cover_strategy=("download", "http://x/new.jpg"),
        produce_cover_fs="/out/ro_src-x/RO-001/RO-001.jpg",
    ):
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=(
                {"number": "RO-001", "title": "T", "maker": "M", "cover": "http://x/new.jpg"},
                plan_cover_strategy,
            ),
        )
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(
                Path("/out/ro_src-x/RO-001"),
                {"cover_fs": produce_cover_fs, "sample_fs": [], "nfo_mtime": 1.0},
            ),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        # cover_path='' (default) → had_cover=False；帶字串 URI → had_cover=True.
        mock_repo.return_value.get_by_path.return_value = MagicMock(
            size_bytes=10, mtime=1.0, cover_path=existing_cover_path,
        )
        mock_focal = mocker.patch("web.routers.scraper.maybe_submit_video_focal")
        return mock_produce, mock_repo, mock_focal

    def _post(self, client, **overrides):
        body = {
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        }
        body.update(overrides)
        return client.post("/api/batch-enrich", json=body)

    # ── P2#3: cover-preserve gate ────────────────────────────────────────────

    def test_fill_missing_with_existing_cover_preserves_cover(self, client, mocker):
        """放大鏡-with-cover（batch mode=fill_missing + overwrite=False + 既有
        cover_path）→ cover_strategy 被覆蓋為 ('none',)。MUTATION LOCK：拿掉
        preserve gate 這條會讓本測試 RED。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    def test_fill_missing_without_existing_cover_writes(self, client, mocker):
        """既有 row 沒有 cover_path（had_cover=False）→ 不觸發 preserve，
        cover_strategy 原樣傳給 _produce_one。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="")

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    def test_refresh_full_writes_regardless_of_had_cover(self, client, mocker):
        """batch 預設 mode=refresh_full（BatchEnrichRequest 預設值）→ 不 preserve，
        即使既有 cover_path 存在（回歸鎖：不得被 P2#3 誤擋）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(client, mode="refresh_full")

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    def test_write_cover_false_preserves_regardless_of_mode(self, client, mocker):
        """write_cover=false → 不論 mode 為何，一律 preserve。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(client, mode="refresh_full", write_cover=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    # ── P2#4: cover-written focal reset + re-submit ──────────────────────────

    def test_cover_written_resets_and_resubmits_focal(self, client, mocker):
        """本次實際寫入新封面（assets['cover_fs'] 非空）→ reset_focal_to_auto +
        maybe_submit_video_focal 都被呼叫，參數對齊 enricher.py:537-547。留在
        `_do_readonly`（已在 run_in_executor 的執行緒內）完成，不在 event loop 上
        裸呼叫。MUTATION LOCK：拿掉整個 focal 區塊會讓本測試 RED。"""
        from core.path_utils import to_file_uri

        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        cover_fs = "/out/ro_src-x/RO-001/RO-001.jpg"
        mock_produce, mock_repo, mock_focal = self._mock_routing(
            mocker, existing_cover_path="", produce_cover_fs=cover_fs,
        )

        response = self._post(client, mode="refresh_full")

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["cover_written"] is True
        canonical = to_file_uri("/tmp/ro_src/RO-001.mp4", {})
        mock_repo.return_value.reset_focal_to_auto.assert_called_once_with(canonical)
        mock_focal.assert_called_once()
        args, kwargs = mock_focal.call_args
        assert args[0] == "RO-001"        # number
        assert args[1] == "M"             # maker
        assert args[2] == canonical       # video_path_uri (DB key)
        assert args[3] == cover_fs        # cover_fs_path
        assert kwargs["cover_path_uri"] == to_file_uri(cover_fs, {})

    def test_cover_preserved_skips_focal(self, client, mocker):
        """preserve_cover=True → assets['cover_fs'] 空 → focal 兩函式皆不呼叫。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, mock_repo, mock_focal = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", produce_cover_fs="",
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["cover_written"] is False
        mock_repo.return_value.reset_focal_to_auto.assert_not_called()
        mock_focal.assert_not_called()


class TestBatchEnrichThumbnailInvalidation:
    """feature/71 T8 邊界5 + PR #60 Codex P2：每筆成功 → invalidate 用 canonical key
    （輸入 URI 原值，非 double-encoded）；失敗不呼叫；去重後至多一次。

    file_path 為 DB file:/// URI（前端送 v.path）。端點走冪等 coerce_to_file_uri，不可
    再套 to_file_uri 造成 file:///file:/// double-encode 砍錯 hash → 舊縮圖殘留。舊測餵裸
    FS path + 斷言 to_file_uri(path, mappings)，是把 bug 行為當合約鎖死，已整套重寫。"""

    @pytest.fixture(autouse=True)
    def _stub(self, mocker):
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"title": "stub", "source": "javbus"},
        )
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={"gallery": {}, "search": {}},
        )

    def test_each_success_invalidates_canonical(self, client, mocker):
        """2 筆皆成功 → 各以 canonical key（輸入 URI 原值）invalidate 一次，非 double-encoded；
        與縮圖 generate 端 thumb_file_for 同 hash（砍到的正是生成的那張）。"""
        import core.thumbnail_cache as tc
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        uri_a, uri_b = "file:///nas/a.mp4", "file:///nas/b.mp4"
        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": uri_a, "number": "IPZ-154"},
                {"file_path": uri_b, "number": "SONE-205"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        called = [c.args[0] for c in inval_spy.call_args_list]
        assert uri_a in called and uri_b in called
        assert len(called) == 2
        assert all("file:///file:///" not in k for k in called), \
            f"invalidate key double-encoded: {called!r}"
        # canonical 一致性：invalidate 的 key hash == generate 端 thumb_file_for 的 hash
        assert tc.thumb_file_for(uri_a) in {tc.thumb_file_for(k) for k in called}

    def test_failed_item_not_invalidated(self, client, mocker):
        """1 成功 1 失敗 → 只有成功筆 invalidate（canonical key）。"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=[_ok_result(), _err_result("找不到番號資料")],
        )
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "file:///nas/ok.mp4", "number": "IPZ-154"},
                {"file_path": "file:///nas/bad.mp4", "number": "XXX-999"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        called = [c.args[0] for c in inval_spy.call_args_list]
        assert called == ["file:///nas/ok.mp4"]

    def test_duplicate_path_invalidated_once(self, client, mocker):
        """同 file_path 兩筆 → 去重後成功的唯一 file_path 至多 invalidate 一次（canonical key）。"""
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "file:///nas/dup.mp4", "number": "IPZ-154"},
                {"file_path": "file:///nas/dup.mp4", "number": "IPZ-154"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        called = [c.args[0] for c in inval_spy.call_args_list]
        assert called == ["file:///nas/dup.mp4"]
