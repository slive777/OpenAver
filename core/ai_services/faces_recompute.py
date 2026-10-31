"""全庫人臉焦點重算工作（187a-T4a，CD-187a-11／-12／-14／-15）。

公開介面：``ensure``／``resume``／``start_rebuild``／``request_stop``／``status``。
HTTP 入口在 T4b；這裡全是 core 邏輯。鎖／停止骨架抄 ``similar_index``，不做掃描承接。
"""
from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from typing import Optional

from core.ai_services import faces_detect, faces_state, samples
from core.ai_services.faces_config import active_in
from core.config import load_config
from core.database import VideoRepository
from core.focal.detector import format_focal
from core.focal.gate import requires_face_detection
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path

logger = get_logger(__name__)

THREAD_NAME = "faces-recompute"
META_TARGET = "ai.faces.target_model"
_DETECT_RATIO = 0.71

_JOB_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_STOP = threading.Event()
_unreadable: int = 0
_stopped_reason: Optional[str] = None
_stopped_kind: Optional[str] = None
_stopped_check: Optional[str] = None


# ── 鎖 ───────────────────────────────────────────────────────────────────────

def _try_acquire_job() -> bool:
    return _JOB_LOCK.acquire(blocking=False)


def _begin_job(kind: str) -> None:
    global _unreadable, _stopped_reason, _stopped_kind, _stopped_check
    _STOP.clear()
    _unreadable = 0
    _stopped_reason = _stopped_kind = _stopped_check = None
    faces_state.job_begin(kind)


def _release_job(outcome: str) -> None:
    faces_state.job_end(outcome)
    if _JOB_LOCK.locked():
        _JOB_LOCK.release()


def _release_unlaunched(outcome: str) -> None:
    with _STATE_LOCK:
        _release_job(outcome)


# ── 設定／候選 ───────────────────────────────────────────────────────────────

def _faces_cfg_object(config: dict) -> SimpleNamespace:
    raw = (config.get("ai_services") or {}).get("faces") or {}
    return SimpleNamespace(
        url=(raw.get("url") or ""),
        api_key=(raw.get("api_key") or ""),
    )


def _path_mappings(config: dict) -> dict:
    return (config.get("gallery") or {}).get("path_mappings") or {}


def _gated_rows(repo: VideoRepository) -> list:
    """list_focal_recompute_rows 後 Python 側 gate 過濾（BE-SCRAPER-03）。"""
    rows = repo.list_focal_recompute_rows()
    return [
        r for r in rows
        if requires_face_detection(r[1] or "", r[2] or "")
    ]


def _counts(repo: VideoRepository, target: Optional[str]) -> dict:
    gated = _gated_rows(repo)
    total = len(gated)
    if not target:
        processed = 0
    else:
        processed = sum(1 for r in gated if r[4] == target)
    return {
        "total": total,
        "processed": processed,
        "pending": total - processed,
        "gated": gated,
    }


def _rebuild_count(repo: VideoRepository) -> int:
    """gate 命中、auto、auto_focal != '' 的片數（前端確認對話用）。"""
    gated = _gated_rows(repo)
    if not gated:
        return 0
    paths = [r[0] for r in gated]
    nonempty: set[str] = set()
    conn = repo._get_connection()
    try:
        chunk = 900
        for i in range(0, len(paths), chunk):
            part = paths[i : i + chunk]
            ph = ", ".join("?" * len(part))
            for (p,) in conn.execute(
                f"SELECT path FROM videos WHERE path IN ({ph}) AND auto_focal != ''",
                part,
            ):
                nonempty.add(p)
    finally:
        conn.close()
    return len(nonempty)


def _pending_rows(repo: VideoRepository, target: str) -> list:
    return [r for r in _gated_rows(repo) if r[4] != target]


def _failure_to_stop_reason(failure: Optional[str]) -> str:
    if failure == "external_contract":
        return "contract"
    return "unreachable"


# ── 公開介面 ─────────────────────────────────────────────────────────────────

def ensure(model: str, kind: str = "model_change") -> bool:
    """設 target＝model；待處理＝0 → 不開工；已在跑 → 只更新 target；否則起 thread。"""
    faces_state.meta_set(META_TARGET, model)
    repo = VideoRepository()
    counts = _counts(repo, model)
    if counts["pending"] == 0:
        return False
    with _STATE_LOCK:
        if not _try_acquire_job():
            return False  # 已在跑：target 已更新，迴圈每張重讀
        _begin_job(kind)
    _start_thread(kind)
    return True


def resume() -> dict:
    """繼續未完成的重算（讀 app_meta target）。"""
    target = faces_state.meta_get(META_TARGET)
    if not target:
        return {"started": False, "reason": "no_target"}
    repo = VideoRepository()
    if _counts(repo, target)["pending"] == 0:
        return {"started": False, "reason": "nothing_pending"}
    with _STATE_LOCK:
        if not _try_acquire_job():
            return {"started": False, "reason": "already_running"}
        _begin_job("resume")
    _start_thread("resume")
    return {"started": True, "reason": "started"}


def start_rebuild() -> dict:
    """「刪除並重新對焦」：先測後清（CD-187a-14）。"""
    with _STATE_LOCK:
        if not _try_acquire_job():
            return {"ok": False, "reason": "already_running"}
        _begin_job("rebuild")
    try:
        return _start_rebuild_after_lock()
    except BaseException:
        _release_unlaunched("error")
        raise


def _start_rebuild_after_lock() -> dict:
    test = _run_rebuild_test()
    if not test.ok:
        _release_unlaunched("test_failed")
        return {
            "ok": False,
            "reason": "test_failed",
            "kind": test.kind,
            "check": test.check,
        }
    _clear_for_rebuild(test.model)
    faces_state.meta_set(META_TARGET, test.model)
    _start_thread("rebuild")
    return {"ok": True, "reason": "started"}


def _run_rebuild_test():
    config = load_config()
    cfg = _faces_cfg_object(config)
    test = samples.run_faces_test(cfg)
    if test.ok:
        faces_state.observe_success(test.model or "")
    else:
        faces_state.observe_failure(test.kind, test.check)
    return test


def _gate_hit_paths_for_clear(repo: VideoRepository) -> list[str]:
    """gate 命中且有封面的 path（**含 manual**）。

    清焦點時把 manual 也放進 ``IN (...)``，讓 SQL 的
    ``crop_mode != 'manual'`` 成為 I-G 的負載點（mutation 可證偽）。
    """
    conn = repo._get_connection()
    try:
        rows = conn.execute(
            "SELECT path, number, maker, cover_path FROM videos "
            "WHERE cover_path != '' ORDER BY path"
        ).fetchall()
    finally:
        conn.close()
    return [
        p for p, number, maker, _cover in rows
        if requires_face_detection(number or "", maker or "")
    ]


def _clear_for_rebuild(model: str) -> None:
    repo = VideoRepository()
    paths = _gate_hit_paths_for_clear(repo)
    if paths:
        repo.clear_auto_focal_for_paths(paths)


def request_stop() -> dict:
    with _STATE_LOCK:
        _STOP.set()
    return {"ok": True, "running": _JOB_LOCK.locked()}


def status() -> dict:
    """純讀 DB＋記憶體，不打端點。"""
    repo = VideoRepository()
    target = faces_state.meta_get(META_TARGET)
    counts = _counts(repo, target)
    snap = faces_state.snapshot()
    running = _JOB_LOCK.locked()
    return {
        "running": running,
        "job_kind": snap["job"]["kind"] if running else None,
        "processed": counts["processed"],
        "total": counts["total"],
        "pending": counts["pending"],
        "unreadable": _unreadable,
        "stopped_reason": _stopped_reason,
        "kind": _stopped_kind if _stopped_reason else snap["kind"],
        "check": _stopped_check if _stopped_reason else snap["check"],
        "target_model": target,
        "rebuild_count": _rebuild_count(repo),
    }


def _start_thread(kind: str) -> None:
    t = threading.Thread(target=_worker_main, args=(kind,), name=THREAD_NAME, daemon=True)
    try:
        t.start()
    except BaseException:
        _release_unlaunched("error")
        raise


# ── 工作 thread ───────────────────────────────────────────────────────────────

def _worker_main(kind: str) -> None:
    outcome = "error"
    try:
        outcome = _work_loop()
    except Exception:
        logger.exception("[faces_recompute] worker crashed")
    finally:
        with _STATE_LOCK:
            if _JOB_LOCK.locked():
                _release_job(outcome)


def _work_loop() -> str:
    """多 pass：一 pass 結束後若 target 變了且仍有待處理 → 再跑。"""
    while True:
        target = faces_state.meta_get(META_TARGET)
        if not target:
            return "no_target"
        pass_target = target
        repo = VideoRepository()
        pending = _pending_rows(repo, pass_target)
        if not pending:
            return "drained"
        config = load_config()
        mappings = _path_mappings(config)
        for row in pending:
            if _STOP.is_set():
                return "stopped"
            stop_reason = _process_one(repo, row, mappings)
            if stop_reason is not None:
                return "failed"
            faces_state.job_progress()
        # pass 結束：target 中途被改且仍有待處理 → 再跑
        new_target = faces_state.meta_get(META_TARGET)
        if new_target and new_target != pass_target:
            if _pending_rows(repo, new_target):
                continue
        return "drained"


def _process_one(repo: VideoRepository, row: tuple, mappings: dict) -> Optional[str]:
    """處理一張。回 stop_reason 字串＝工作須停；None＝繼續。"""
    global _unreadable, _stopped_reason, _stopped_kind, _stopped_check
    path, _number, _maker, cover_path, _focal_model = row
    fs = uri_to_local_fs_path(cover_path, mappings)
    if not fs or not os.path.exists(fs):
        _unreadable += 1
        return None

    result = faces_detect.detect(
        fs, _DETECT_RATIO, profile="background", notify=False
    )
    if result is None:
        if not active_in(load_config()):
            _stopped_reason = "disabled"
            snap = faces_state.snapshot()
            _stopped_kind, _stopped_check = snap["kind"], snap["check"]
            return "disabled"
        _unreadable += 1
        return None

    if result.kind == "FAILED":
        _stopped_reason = _failure_to_stop_reason(result.failure)
        snap = faces_state.snapshot()
        _stopped_kind, _stopped_check = snap["kind"], snap["check"]
        return _stopped_reason

    focal_str = format_focal(result.focal)
    model = result.model or "local-pigo"
    repo.update_auto_focal(path, focal_str, cover_path, model=model)
    return None
