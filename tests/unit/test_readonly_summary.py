"""TASK-88c-T2 — 純函式真值表：_accumulate_readonly / _outcome_to_sse。

橋接 / 分流 / done 事件 / source-level 例外走 integration（TestClient），見
tests/integration/test_api_scanner.py::TestGenerateReadonlyBridge。此檔只測無 IO 純函式。
"""
import pytest

from web.routers.scanner import _accumulate_readonly, _outcome_to_sse, _yield_source_summary
from core.readonly_producer import ProduceResult, ProduceOutcome


def _empty():
    return {"created": 0, "skipped": 0, "no_scrape": 0, "failed": 0,
            "no_output": 0, "sources": 0, "source_errors": 0,
            "unreachable": 0, "partial": 0, "pruned": 0}


class TestAccumulateReadonly:
    def test_normal_result_accumulates_four_numbers_and_sources(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              created=2, skipped=1, no_scrape=1, failed=1))
        assert s["sources"] == 1
        assert (s["created"], s["skipped"], s["no_scrape"], s["failed"]) == (2, 1, 1, 1)
        assert s["no_output"] == 0

    def test_no_output_path_only_increments_no_output(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="",
                                              aborted_reason="no_output_path"))
        assert s["no_output"] == 1
        assert s["sources"] == 0
        assert s["created"] == 0

    def test_not_readonly_is_not_counted(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              created=5, aborted_reason="not_readonly"))
        assert s == _empty()

    def test_cross_source_accumulation(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="a", output_path="o", created=1))
        _accumulate_readonly(s, ProduceResult(source_path="b", output_path="o", created=2, failed=1))
        assert s["sources"] == 2
        assert s["created"] == 3
        assert s["failed"] == 1

    def test_unreachable_only_increments_unreachable_not_generic_log_branch(self):
        """TASK-89b-T6 (Finding-2): unreachable must land in its own branch, not the
        generic `if result.aborted_reason:` log-only branch (which would silently
        drop it with zero counting)."""
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              aborted_reason="unreachable"))
        assert s["unreachable"] == 1
        assert s["sources"] == 0
        assert s["created"] == 0

    def test_pruned_accumulates_on_normal_result(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              created=1, pruned=3))
        assert s["pruned"] == 3

    def test_skipped_paths_nonempty_increments_partial(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              created=1, skipped_paths=["/x/broken"]))
        assert s["partial"] == 1

    def test_skipped_paths_empty_does_not_increment_partial(self):
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o", created=1))
        assert s["partial"] == 0

    def test_unreachable_does_not_accumulate_pruned_or_partial(self):
        """abort branches return before the pruned/partial accumulation lines."""
        s = _empty()
        _accumulate_readonly(s, ProduceResult(source_path="p", output_path="o",
                                              aborted_reason="unreachable",
                                              pruned=5, skipped_paths=["/x"]))
        assert s["pruned"] == 0
        assert s["partial"] == 0


class TestOutcomeToSse:
    @pytest.mark.parametrize("status,label,level", [
        ("created", "✓ 生成", "info"),
        ("skipped", "略過", "info"),
        ("no_scrape", "刮不到", "info"),
        ("failed", "✗ 失敗", "warn"),
    ])
    def test_status_maps_to_label_and_level(self, status, label, level):
        d = _outcome_to_sse(ProduceOutcome(source_uri="u", status=status, number="ABC-001"))
        assert d["type"] == "log"
        assert d["level"] == level
        assert label in d["message"]
        assert "ABC-001" in d["message"]

    def test_failed_appends_error_note(self):
        d = _outcome_to_sse(ProduceOutcome(source_uri="u", status="failed",
                                           number="X", error="生成失敗"))
        assert "生成失敗" in d["message"]

    def test_error_is_fixed_message_no_leak(self):
        # producer 已 sanitize error 為固定字串；轉發不外洩細節
        d = _outcome_to_sse(ProduceOutcome(source_uri="u", status="failed",
                                           number="X", error="生成失敗"))
        assert "/home/" not in d["message"]
        assert "Traceback" not in d["message"]


class TestYieldSourceSummary:
    def test_no_output_path_yields_prompt(self):
        r = ProduceResult(source_path="P", output_path="", aborted_reason="no_output_path")
        msgs = [m for m in _yield_source_summary(r)]
        assert len(msgs) == 1
        assert "請先設定輸出夾" in msgs[0]

    def test_normal_yields_four_number_summary(self):
        r = ProduceResult(source_path="P", output_path="o", created=2, skipped=1, no_scrape=0, failed=1)
        msgs = [m for m in _yield_source_summary(r)]
        assert len(msgs) == 1
        assert "新增 2" in msgs[0] and "略過 1" in msgs[0] and "失敗 1" in msgs[0]

    def test_not_readonly_yields_nothing(self):
        r = ProduceResult(source_path="P", output_path="o", aborted_reason="not_readonly")
        assert list(_yield_source_summary(r)) == []

    def test_unreachable_yields_warn_prompt(self):
        r = ProduceResult(source_path="P", output_path="o", aborted_reason="unreachable")
        msgs = [m for m in _yield_source_summary(r)]
        assert len(msgs) == 1
        assert "來源無法連線" in msgs[0]

    def test_skipped_paths_appends_second_warn_after_summary(self):
        r = ProduceResult(source_path="P", output_path="o", created=1,
                           skipped_paths=["/x/broken_dir"])
        msgs = [m for m in _yield_source_summary(r)]
        assert len(msgs) == 2
        assert "新增 1" in msgs[0]
        assert "已略過刪除偵測" in msgs[1]
        assert "1 個路徑讀取失敗" in msgs[1]
