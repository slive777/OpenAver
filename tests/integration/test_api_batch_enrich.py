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
        # cover_path="" explicit (FIX#1 has_servable_cover reads this) — a bare
        # MagicMock() attribute is truthy by default, which would silently flip
        # reason to 'hit' in every test using this default routing helper.
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0, cover_path="")
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
        # cover_path="" explicit — this test's whole point is "no cover exists at
        # all" (this-call AND pre-existing), so has_servable_cover (FIX#1) must
        # stay False too; a bare MagicMock() default here would be truthy and
        # silently flip reason to 'hit'.
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0, cover_path="")

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
        仍是失敗結果（reason='not_found'——Codex PR#113 one-pass alignment，對齊
        core.enricher 自己的 not_found reason 值，非內部狀態碼 'no_scrape'），
        可寫項不受影響，整批不中斷。"""
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
        assert by_number["RO-001"]["reason"] == "not_found"
        mock_produce.assert_not_called()
        assert by_number["RW-002"]["success"] is True

        done = [e for e in events if e["type"] == "done"][0]
        assert done["summary"] == {"total": 2, "success": 1, "failed": 1}

    # FIX P2-A (P2 parity closeout): the batch readonly not-found branch must
    # mirror bulk readonly_producer.py:1559-1561's bookkeeping — insert_if_ignore
    # (stub row) THEN update_scrape_attempted_at (a bare UPDATE...WHERE path=?
    # that silently no-ops without the stub row existing first). This branch
    # already canonicalizes reason to 'not_found' (asserted above) — only the
    # DB bookkeeping is new here.
    def test_readonly_item_no_scrape_marks_scrape_attempted_at(self, client, mocker):
        from core.path_utils import coerce_to_file_uri

        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )
        _mock_owning, _mock_plan, mock_produce, mock_repo = self._mock_readonly_routing(
            mocker, plan_return=(None, ("none",)),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        events = parse_sse(response.text)
        result_items = [e for e in events if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "not_found"
        mock_produce.assert_not_called()

        repo_instance = mock_repo.return_value
        repo_instance.insert_if_ignore.assert_called_once()
        repo_instance.update_scrape_attempted_at.assert_called_once()

        # Stub-row-before-update ordering (same trap as enrich-single: missing
        # stub row → update_scrape_attempted_at silently no-ops).
        call_names = [c[0] for c in repo_instance.method_calls]
        assert call_names.index("insert_if_ignore") < call_names.index("update_scrape_attempted_at")

        stub_video = repo_instance.insert_if_ignore.call_args.args[0]
        canonical = coerce_to_file_uri("/tmp/ro_src/RO-001.mp4", {})
        assert stub_video.path == canonical
        assert stub_video.number == "RO-001"
        assert stub_video.title == "RO-001.mp4"

        attempted_args = repo_instance.update_scrape_attempted_at.call_args.args
        assert attempted_args[0] == canonical
        assert attempted_args[1] > 0

    # Codex PR#113 one-pass alignment (2026-07-21): the batch readonly result-item
    # now spreads an actual asdict(EnrichResult(...)) into the SSE envelope, so its
    # shape is structurally guaranteed on success AND every failure branch.
    def test_readonly_success_result_item_has_full_enrich_result_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        _mock_owning, _mock_plan, _mock_produce, _mock_repo = self._mock_readonly_routing(mocker)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert set(result_items[0]) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }

    def test_readonly_no_scrape_result_item_has_full_enrich_result_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        self._mock_readonly_routing(mocker, plan_return=(None, ("none",)))

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert set(result_items[0]) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }

    def test_readonly_error_result_item_has_full_enrich_result_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        self._mock_readonly_routing(
            mocker, produce_side_effect=RuntimeError("boom"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "error"
        assert set(result_items[0]) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }

    # P1 revert + reject (round-3 review 2026-07-21, owner-confirmed): a Codex
    # PR#113 round-3 write_nfo skip-gate threaded down to _produce_one was a P1
    # data-loss (see TestBatchEnrichReadonlyNoNfoRejection below). write_nfo is
    # no longer threaded into _produce_one at all — readonly produce always
    # writes the NFO, and write_nfo=false is rejected before _produce_one is
    # ever called (this test used to assert the buggy "honored" behaviour).
    def test_write_nfo_false_readonly_item_rejected(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        _mock_owning, _mock_plan, mock_produce, _mock_repo = self._mock_readonly_routing(mocker)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
            "write_nfo": False,
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert result_items[0]["nfo_written"] is False
        assert result_items[0]["error"]
        assert result_items[0]["reason"] == "error"
        mock_produce.assert_not_called()

    def test_write_nfo_default_true_produce_one_no_longer_takes_write_nfo_kwarg(self, client, mocker):
        """未帶 write_nfo（BatchEnrichRequest 預設 True，唯一支援值）→ result-item
        nfo_written=True；_produce_one 不再收 write_nfo kwarg 於呼叫中（P1 revert，
        write_nfo 已徹底從 _produce_one 簽名移除，不再是 threading 目標）。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        _mock_owning, _mock_plan, mock_produce, _mock_repo = self._mock_readonly_routing(mocker)

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["nfo_written"] is True
        mock_produce.assert_called_once()
        assert "write_nfo" not in mock_produce.call_args.kwargs

    # TASK-105-T9（BUG，PR#113 round 8 Codex thread `Sn2qv`）：唯讀分支的
    # executor await（含 in-executor 前置如 resolve_ingest_plan）未被任何
    # per-item try/except 隔離——單一唯讀項的例外會上傳批次層 try，`raise` 後
    # SSE 生成器崩潰、整批掛掉（後續項與 done 全失）。故障注入：對其中一個唯讀
    # 項的 resolve_ingest_plan 拋例外，斷言（a）該項回失敗結果項
    # （success=False, reason='error'），（b）其後的可寫項與唯讀成功項仍完成
    # （證明迴圈續跑，故障項故意不放最後一筆），（c）done 事件仍發出、計數正確。
    # §7 mutation 自驗強制：見 task card。
    def test_readonly_item_resolve_plan_raises_isolated_batch_continues(self, client, mocker):
        """單一唯讀項 resolve_ingest_plan 拋例外 → 該項回失敗結果項（reason='error'），
        同批其後的可寫項與唯讀成功項仍完成、done 仍發出（改前整批崩、無 done）。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        # 唯讀路由基座（owning/_produce_one/VideoRepository 預設）；
        # resolve_ingest_plan 另行以 side_effect 覆寫（依 number 分流成功/拋例外）。
        self._mock_readonly_routing(mocker)

        def _plan_side_effect(fs_path, number, *args, **kwargs):
            if number == "RO-FAIL":
                raise RuntimeError("boom in resolve_ingest_plan")
            return ({"number": number, "title": "T", "cover": ""}, ("none",))

        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            side_effect=_plan_side_effect,
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                # 故障唯讀項置批首（非批尾）——證明例外未中斷迴圈：若置批尾，
                # 改前的 bug 恰好也會讓「無後續項」看起來像通過。
                {"file_path": "/tmp/ro_src/RO-FAIL.mp4", "number": "RO-FAIL"},
                {"file_path": "/tmp/rw/RW-OK.mp4", "number": "RW-OK"},
                {"file_path": "/tmp/ro_src/RO-OK.mp4", "number": "RO-OK"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = parse_sse(response.text)
        by_number = {e["number"]: e for e in events if e["type"] == "result-item"}

        # 故障項：隔離成失敗結果項，非整批崩
        assert by_number["RO-FAIL"]["success"] is False
        assert by_number["RO-FAIL"]["reason"] == "error"

        # 其後兩項仍完成（證明迴圈續跑）
        assert by_number["RW-OK"]["success"] is True
        assert by_number["RO-OK"]["success"] is True

        # done 仍發出、計數對稱
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert done_events[0]["summary"] == {"total": 3, "success": 2, "failed": 1}


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
        cover_file_exists=True,
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
        # cover_path='' (default) → had_cover=False；帶字串 URI → had_cover=True
        # (前提是 os.path.exists 也判存在，見下方 mock).
        mock_repo.return_value.get_by_path.return_value = MagicMock(
            size_bytes=10, mtime=1.0, cover_path=existing_cover_path,
        )
        # Codex PR#113 P2 round-6 fix：had_cover 現在還要求輸出封面檔實際存在於
        # 磁碟（對齊 core.enricher._write_cover 的 os.path.exists(cover_path)
        # 語意，鏡射 test_api_enrich.py 同名 mock 註解）——預設 True 讓既有測試
        # 維持原 had_cover=True 行為；cover_file_exists=False 模擬 round-6
        # 回報的 bug 場景（DB row 殘留、輸出檔已被刪除/對應不到）。
        mocker.patch("web.routers.scraper.os.path.exists", return_value=cover_file_exists)
        # feature/105 patch-target migration (CD-105-8): has_servable_cover 的磁碟
        # 複驗隨 compute_has_servable_cover 從 web.routers.scraper 搬進
        # core.enrich_contract；顯式 patch 該命名空間（os.path 為共享 module
        # singleton，機械上與上一行同物件，兩者一致即可）。cover_file_exists
        # 同時餵 had_cover（scraper）與 has_servable_cover（enrich_contract）兩道 gate。
        mocker.patch("core.enrich_contract.os.path.exists", return_value=cover_file_exists)
        # TASK-105-T6: reset+submit 收斂進 schedule_focal_after_cover_write（住
        # core.focal_trigger）；maybe_submit_video_focal 的實際呼叫端隨之從
        # web.routers.scraper 移到 core.focal_trigger（bare name 在該模組 global
        # namespace 內解析），patch target 需對齊使用端（gotchas-backend.md §1）。
        mock_focal = mocker.patch("core.focal_trigger.maybe_submit_video_focal")
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

    # ── Codex PR#113 P2 round-6（found in 2 readonly branches）：had_cover 必須
    # 連同輸出封面檔是否實際存在於磁碟一起判斷，鏡射
    # test_api_enrich.py::TestEnrichSingleReadonlyCoverPreserveGate 同一組場景 ──

    def test_fill_missing_with_cover_path_but_file_missing_on_disk_rebuilds_cover(
        self, client, mocker,
    ):
        """batch 放大鏡-with-cover，但 DB 的 cover_path 對應到的輸出檔已被刪除
        （或路徑對應後在磁碟上不存在）→ had_cover 必須是 False，不得 preserve，
        cover_strategy 原樣傳給 _produce_one（重建封面）。MUTATION LOCK：把
        had_cover 改回純 DB 判斷（bool(existing and existing.cover_path)）會讓
        本測試 RED（cover_strategy 會變成 ('none',)）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=False,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    def test_fill_missing_with_cover_path_and_file_present_preserves_cover(self, client, mocker):
        """同場景但輸出封面檔仍實際存在於磁碟 → 維持既有 preserve 行為（無回歸，
        鏡射 test_fill_missing_with_existing_cover_preserves_cover）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=True,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    def test_refresh_full_writes_regardless_of_had_cover(self, client, mocker):
        """refresh_full + overwrite_existing=True → 寫（不 preserve），即使既有
        cover_path 存在（回歸鎖：不得被 P2#3 誤擋）。feature/105 AC4 後 refresh_full
        的保留政策綁 overwrite_existing（mode-agnostic）：refresh_full+overwrite=False
        現改為「保留」（前端不可達——batch 恆送 fill_missing，見 state-batch.js:108），
        故此回歸鎖須顯式送 overwrite_existing=True 走真實覆蓋路徑。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(client, mode="refresh_full", overwrite_existing=True)

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

    # ── feature/105 T2 AC4 delta（batch 側，鏡射 test_api_enrich.py 同名）：移除唯讀
    # mode=='fill_missing' 顯式閘後，唯讀保留政策與非唯讀 core.enricher._write_cover
    # 完全 mode-agnostic 對齊。refresh_full + overwrite=false + 既有可服務封面 → 保留
    # （改前 mode 閘 False 會靜默覆蓋）。前端不可達（batch 恆送 fill_missing，見
    # state-batch.js:108），latent-safety 對齊。MUTATION SELF-CHECK：把 mode 閘加回
    # （preserve = (not write_cover) or (mode=='fill_missing' and not overwrite and
    # had_cover)）會讓本測試 RED（cover_strategy 變回 ('download', ...)）。────────
    def test_refresh_full_no_overwrite_existing_cover_preserves_mode_agnostic(
        self, client, mocker,
    ):
        """AC4：batch refresh_full + overwrite=false + 既有封面（磁碟檔在）→ preserve
        （('none',)），與 enricher _write_cover 同輸入
        should_preserve_cover(write_cover=True, overwrite=False, cover_exists=True)
        =True 一致。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=True,
        )

        response = self._post(client, mode="refresh_full", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    # ── P2 review round 3 (FIX#1): reason reflects a SERVABLE cover, not just
    # this-call cover_written ────────────────────────────────────────────────

    def test_fill_missing_with_existing_cover_reason_is_hit_despite_cover_written_false(
        self, client, mocker,
    ):
        """放大鏡-with-cover（fill_missing + overwrite=False + 既有 cover_path）→
        cover_strategy 被覆蓋為 ('none',) → cover_written=False，但既有封面仍可服務
        → reason 必須是 'hit'（不是 'no_cover'），否則掃描頁飛入/badge 會被誤壓下
        （state-batch.js 只在 status==='hit' 時顯示封面）。MUTATION LOCK：把
        has_servable_cover 改回單看 cover_written（reason='hit' if cover_written
        else 'no_cover'）會讓本測試 RED（reason 會變回 'no_cover'）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        # produce_cover_fs="" — the mocked _produce_one echoes whatever fixture
        # value it's given regardless of cover_strategy (it's a mock, not the
        # real preserve logic), so this must be explicit to model "preserve
        # gate suppressed the write" → assets['cover_fs'] empty → cover_written
        # False (same as test_cover_preserved_skips_focal's setup).
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", produce_cover_fs="",
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)
        assert result_items[0]["cover_written"] is False
        assert result_items[0]["reason"] == "hit"

    # ── feature/105 AC2 (Bug 1 fix), batch equivalence/regression guard: DB has
    # residual cover_path but the physical cover file is gone → reason must be
    # 'no_cover'. NOTE: batch never had Bug 1 — its pre-T1 form was
    # `cover_written or had_cover`, and had_cover already carried a disk check, so
    # this scenario returned 'no_cover' before T1 too. This test therefore LOCKS
    # that the unification onto the shared compute_has_servable_cover atom
    # PRESERVES that disk-verify guarantee (behavior-equivalent refactor). It goes
    # RED if the shared atom's disk check is dropped (verified: reverting
    # cover_uri_is_servable to `return bool(cover_uri)` flips this to 'hit'). ────
    def test_residual_cover_path_but_file_deleted_reason_is_no_cover(self, client, mocker):
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg",
            produce_cover_fs="", cover_file_exists=False,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert result_items[0]["success"] is True
        assert result_items[0]["cover_written"] is False
        assert result_items[0]["reason"] == "no_cover"

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

    # ── PR#114 P2: 唯讀成功項的 thumbnail_cache.invalidate 是 best-effort cleanup
    # （檔案 unlink 可拋 OSError）。其失敗不得把成功項打成失敗、也不得讓外層 except
    # 再 failed_count+=1 造成同一項 success+failed 雙記（done 匯總 success+failed >
    # total）。故障注入型測試 ──
    def test_thumbnail_invalidate_oserror_does_not_double_count_or_fail_item(
        self, client, mocker,
    ):
        """唯讀成功項的縮圖失效拋 OSError → 不得雙記、不得誤報失敗。修前（invalidate
        未包 best-effort try/except）：外層 except 捕獲 → failed_count+=1，同項既
        success 又 failed → done 匯總 success=1, failed=1, total=1（success+failed=2
        > total），且該項被 yield 成失敗。MUTATION LOCK：拿掉 ok 分支對 invalidate
        外包的 best-effort try/except → 本測試 RED。"""
        mocker.patch("web.routers.scraper.load_config", return_value=self._readonly_config())
        # 既有 servable cover → refresh_full 仍寫（cover_written True），
        # has_servable_cover=True → reason 'hit'（成功項的正常 reason）。
        self._mock_routing(
            mocker,
            existing_cover_path="file:///out/ro_src-x/RO-001/RO-001.jpg",
        )
        inval_spy = mocker.patch(
            "web.routers.scraper.thumbnail_cache.invalidate",
            side_effect=OSError("disk gone"),
        )

        response = self._post(client, mode="refresh_full")

        events = parse_sse(response.text)
        inval_spy.assert_called_once()  # 確有觸發到（否則測試無效）
        done = [e for e in events if e["type"] == "done"][0]["summary"]
        # 無雙記：success + failed 精確等於 total（修前為 2 > 1）。
        assert done["total"] == 1
        assert done["success"] + done["failed"] == done["total"]
        assert done["success"] == 1 and done["failed"] == 0
        # 成功項不因 cleanup 失敗被誤報成失敗。
        result_items = [e for e in events if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is True
        assert result_items[0]["reason"] == "hit"


# ── P2 review round 3 (FIX#4/FIX#5): readonly + mode='db_to_sidecar' clean
# rejection, + canonical `reason` on the batch failure result-item ─────────────
# 鏡射 tests/integration/test_api_enrich.py::TestEnrichSingleReadonlyDbToSidecarRejection
# 同一組場景（見該處註解：zero-write wall，db_to_sidecar 對唯讀來源無意義）。


class TestBatchEnrichReadonlyDbToSidecarRejection:
    def _readonly_config(self):
        return {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {},
            "scraper": {},
        }

    def test_db_to_sidecar_readonly_item_rejected_cleanly(self, client, mocker):
        """MUTATION LOCK：拿掉這條 early-return 會讓 resolve_owning_output_root/
        resolve_ingest_plan/_produce_one 被呼叫（本測試斷言它們不被呼叫），本測試
        會 RED。同時驗證 FIX#5：canonical reason='error'（不是原始內部狀態碼
        'db_to_sidecar'）。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mock_owning = mocker.patch("web.routers.scraper.resolve_owning_output_root")
        mock_plan = mocker.patch("web.routers.scraper.resolve_ingest_plan")
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "db_to_sidecar",
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        item = result_items[0]
        assert item["success"] is False
        assert item["error"]
        assert item["nfo_written"] is False
        assert item["cover_written"] is False
        assert item["extrafanart_written"] == 0
        assert item["fields_filled"] == []
        assert item["source_used"] == ""
        assert item["reason"] == "error"
        assert set(item) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }
        mock_owning.assert_not_called()
        mock_plan.assert_not_called()
        mock_produce.assert_not_called()


class TestBatchEnrichReadonlyNoNfoRejection:
    """P1 revert + reject (round-3 review 2026-07-21, owner-confirmed): mirrors
    TestBatchEnrichReadonlyDbToSidecarRejection above — write_nfo=false is a
    granular flag the holistic readonly produce model doesn't support, so it
    is rejected the same way, before resolve_owning_output_root is ever
    called. See _READONLY_NO_NFO_ERROR_MSG (web/routers/scraper.py) for the P1
    this replaces (a title-changing rescrape with write_nfo=False used to
    skip the new NFO write while stale-cleanup still unlinked the old one)."""

    def _readonly_config(self):
        return {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {},
            "scraper": {},
        }

    def test_write_nfo_false_readonly_item_rejected_cleanly(self, client, mocker):
        """MUTATION LOCK：拿掉這條 early-return 會讓 resolve_owning_output_root/
        resolve_ingest_plan/_produce_one 被呼叫（本測試斷言它們不被呼叫），本測試
        會 RED。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=self._readonly_config(),
        )
        mock_owning = mocker.patch("web.routers.scraper.resolve_owning_output_root")
        mock_plan = mocker.patch("web.routers.scraper.resolve_ingest_plan")
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"}],
            "mode": "refresh_full",
            "write_nfo": False,
        })

        result_items = [e for e in parse_sse(response.text) if e["type"] == "result-item"]
        assert len(result_items) == 1
        item = result_items[0]
        assert item["success"] is False
        assert item["error"]
        assert item["nfo_written"] is False
        assert item["cover_written"] is False
        assert item["extrafanart_written"] == 0
        assert item["fields_filled"] == []
        assert item["source_used"] == ""
        assert item["reason"] == "error"
        assert set(item) >= {
            'type', 'number', 'file_path', 'success', 'nfo_written', 'cover_written',
            'extrafanart_written', 'fields_filled', 'source_used', 'error', 'reason',
        }
        mock_owning.assert_not_called()
        mock_plan.assert_not_called()
        mock_produce.assert_not_called()


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

    def test_invalidate_oserror_does_not_double_count_or_fail_item(self, client, mocker):
        """PR#114 P2（可寫路徑孿生）：enrich 成功後的 thumbnail_cache.invalidate
        拋 OSError → best-effort try/except 吞掉；不得讓外層 except 再 failed_count+=1
        造成同一成功項 success+failed 雙記、也不得誤報失敗。MUTATION LOCK：拿掉可寫
        分支 invalidate 外包的 best-effort try/except → 本測試 RED（done 回 success=1,
        failed=1, total=1，且該項 success=False）。"""
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        inval_spy = mocker.patch(
            "web.routers.scraper.thumbnail_cache.invalidate",
            side_effect=OSError("disk gone"),
        )

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "file:///nas/ok.mp4", "number": "IPZ-154"}],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        inval_spy.assert_called_once()
        events = parse_sse(response.text)
        done = [e for e in events if e["type"] == "done"][0]["summary"]
        assert done["total"] == 1
        assert done["success"] + done["failed"] == done["total"]
        assert done["success"] == 1 and done["failed"] == 0
        result_items = [e for e in events if e["type"] == "result-item"]
        assert len(result_items) == 1
        assert result_items[0]["success"] is True
