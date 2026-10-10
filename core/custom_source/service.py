"""自訂來源服務層：上傳／驗收／移除／列表／啟用／適用性／硬限；純後端，無 HTTP。

鎖序單向：state.LOCK → config 鎖；驗收本體（網路 I/O）在任何鎖之外。
"""
import queue
import threading

from core.atomic_write import atomic_write
from core.custom_source import registry, scraper, state, views
from core.custom_source.errors import LoadError
from core.custom_source.interpret import accepts_number, run_tests
from core.custom_source.schema import load_uploaded
from core.data_root import get_data_root, is_layout_finalized
from core.scrapers.errors import SourceUnreachable
from core.scrapers.models import ScraperConfig

VERIFY_TOTAL_BUDGET_S = 180
CALL_LIMIT_S = 30


class ServiceError(Exception):
    """業務錯誤；T5 一行映射成 HTTP 回應。"""

    def __init__(self, code, http_status, **extra):
        self.code = code
        self.http_status = http_status
        self.extra = extra
        super().__init__(code, http_status)

    def payload(self):
        return {"success": False, "reason": self.code, **self.extra}


def _load_error_dict(error):
    return {"reason": error.reason, "field_path": error.field_path, "line": error.line, "message": error.message}


def upload(text):
    """先驗證後寫：壞檔零寫入；好檔覆蓋同 id 現檔並清掉舊紀錄，不連網。"""
    try:
        spec = load_uploaded(text)
    except LoadError as exc:
        raise ServiceError(exc.reason, 400, **{k: v for k, v in _load_error_dict(exc).items() if k != "reason"}) from exc
    if not is_layout_finalized(get_data_root()):
        raise ServiceError("data_root_not_ready", 409)
    source_id = spec.id
    with state.LOCK:
        existing = registry.find_path(source_id)
        state.bump_gen(source_id)
        target = existing or registry.custom_sources_dir() / f"{source_id}.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(target, mode="wb") as handle:
            handle.write(text.encode("utf-8"))
        state.clear(source_id)
    return {"id": source_id, "source_id": f"custom:{source_id}", "status": "unverified", "replaced": existing is not None}


def remove(source_id):
    with state.LOCK:
        path = registry.find_path(source_id)
        if path is None and state.read_entry(source_id) is None:
            raise ServiceError("not_loaded", 404)
        state.bump_gen(source_id)
        if path is not None:
            path.unlink(missing_ok=True)
        state.clear(source_id)
    return {"id": source_id}


def _snapshot(source_id):
    with state.LOCK:
        loaded = registry.load_one(source_id)
        gen_seen = state.get_gen(source_id)
    if loaded is None:
        raise ServiceError("not_loaded", 404)
    if loaded.spec is None:
        raise ServiceError("load_failed", 409, load_error=_load_error_dict(loaded.error))
    return loaded, gen_seen


def _case_dict(case):
    mismatches = [{"key": m.key, "expected": m.expected, "actual": m.actual, "url": m.url} for m in case.mismatches]
    return {"index": case.index, "number": case.number, "passed": case.passed, "mismatches": mismatches}


def _run_verify(source_id, transport):
    loaded, gen_seen = _snapshot(source_id)
    results = run_tests(
        loaded.spec, ScraperConfig(), transport,
        budget_s=scraper.CUSTOM_BUDGET_S, total_budget_s=VERIFY_TOTAL_BUDGET_S,
    )
    cases = [_case_dict(c) for c in results]
    failed = sum(1 for c in cases if not c["passed"])
    status = "passed" if failed == 0 else "failed"
    last_result = {"total": len(cases), "failed": failed, "cases": cases}
    if not state.record_result(source_id, loaded.sha256, status, last_result, gen_seen):
        raise ServiceError("changed_during_verify", 409)
    verified_at = (state.read_entry(source_id) or {}).get("verified_at")
    return {"id": source_id, "status": status, "verified_at": verified_at, **last_result}


def verify(source_id, *, transport=None):
    """單飛行驗收；結果以世代圍欄寫回，期間被重傳／移除則丟棄。"""
    if not state.try_begin_verify(source_id):
        raise ServiceError("verify_busy", 409, busy_id=state.get_running_id())
    try:
        return _run_verify(source_id, transport)
    finally:
        state.end_verify(source_id)


def set_enabled(source_id, enabled):
    loaded = registry.load_one(source_id)
    if loaded is None:
        raise ServiceError("not_loaded", 404)
    if not state.set_enabled(source_id, bool(enabled), loaded.sha256):
        raise ServiceError("not_passed", 409)
    return {"id": source_id, "enabled": bool(enabled)}


def list_sources():
    with state.LOCK:  # 紀錄與檢視在同一次持鎖內讀，避免混出新舊兩輪的結果
        entries = state.read_all()
        all_views = views.custom_source_views()
    items = []
    for view in all_views:
        loaded = view.loaded
        entry = entries.get(loaded.id) if view.status in state.STATUSES and isinstance(entries.get(loaded.id), dict) else None
        items.append({
            "id": loaded.id,
            "source_id": view.config.id,
            "name": view.config.display_name_raw,
            "status": view.status,
            "enabled": view.config.enabled,
            "verified_at": entry.get("verified_at") if entry else None,
            "last_result": entry.get("last_result") if entry else None,
            "load_error": _load_error_dict(loaded.error) if loaded.error is not None else None,
        })
    return items


def applicable(number):
    """純運算：只含 routable（passed＋enabled＋sha 相符）的來源，值為番號是否符合其 pattern。"""
    return {v.config.id: accepts_number(v.loaded.spec, number) for v in views.custom_source_views() if v.routable}


def call_bounded(fn, *, seconds=None):
    """在 daemon thread 跑 fn，逾時丟 SourceUnreachable；工作 thread 的例外原樣重拋。"""
    limit = CALL_LIMIT_S if seconds is None else seconds
    box = queue.Queue(maxsize=1)

    def _work():
        try:
            box.put((True, fn()))
        except BaseException as exc:  # noqa: BLE001 - 原樣轉交給呼叫端
            box.put((False, exc))

    threading.Thread(target=_work, daemon=True).start()
    try:
        ok, value = box.get(timeout=limit)
    except queue.Empty:
        raise SourceUnreachable("custom source did not respond in time") from None
    if ok:
        return value
    raise value
