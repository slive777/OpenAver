"""core.media_probe_backfill — 補讀 job（TASK-198a-T2a，CD-198a-7）。

``status()``／``start()`` 形狀照 ``tags_backfill``；用 ``JobShell`` 收鎖。
job 只活在記憶體；逐列 submit 給同一個單例 worker。
"""
from __future__ import annotations

import threading

from core import media_probe
from core.ai_services.backfill_state import meta_delete, meta_get, meta_set
from core.ai_services.job_shell import JobShell
from core.database.video import VideoRepository
from core.logger import get_logger
from core.media_probe_worker import get_worker
from core.readonly_source import (
    readonly_source_prefixes,
    writable_source_prefixes,
)

logger = get_logger(__name__)

THREAD_NAME = "media-probe-backfill"
META_DISMISSED = "media_probe.reminder_dismissed"
META_INCLUDE_READONLY = "media_probe.include_readonly"

_SHELL = JobShell()
_job_lock = threading.Lock()
_job_done = 0
_job_total = 0
_done_paths: set = set()


def get_dismissed() -> bool:
    return meta_get(META_DISMISSED) == "1"


def set_dismissed(value: bool) -> None:
    if value:
        meta_set(META_DISMISSED, "1")
    else:
        meta_delete(META_DISMISSED)


def get_include_readonly() -> bool:
    return meta_get(META_INCLUDE_READONLY) == "1"


def set_include_readonly(value: bool) -> None:
    if value:
        meta_set(META_INCLUDE_READONLY, "1")
    else:
        meta_delete(META_INCLUDE_READONLY)


def _prefixes():
    from core.config import load_config

    gallery = load_config().get("gallery", {}) or {}
    mappings = gallery.get("path_mappings", {}) or {}
    return (
        readonly_source_prefixes(gallery, mappings),
        writable_source_prefixes(gallery, mappings),
        mappings,
    )


def status() -> dict:
    """CD-198a-8：{available, dismissed, include_readonly, pending, job:{running, done, total}}。"""
    include_ro = get_include_readonly()
    try:
        ro, wr, _mappings = _prefixes()
        pending = len(
            VideoRepository().list_media_probe_pending(
                include_readonly=include_ro,
                readonly_prefixes=ro,
                writable_prefixes=wr,
            )
        )
    except Exception:
        logger.exception("media_probe_backfill.status pending count failed")
        pending = 0
    with _job_lock:
        done, total = _job_done, _job_total
    return {
        "available": media_probe.is_available(),
        "dismissed": get_dismissed(),
        "include_readonly": include_ro,
        "pending": pending,
        "job": {
            "running": _SHELL.is_running(),
            "done": done,
            "total": total,
        },
    }


def start() -> dict:
    """回 {ok, status: started|already_running|nothing_to_do|unavailable}。"""
    if not media_probe.is_available():
        return {"ok": False, "status": "unavailable"}
    with _SHELL.state_lock:
        if not _SHELL.try_acquire():
            return {"ok": False, "status": "already_running"}
        try:
            include_ro = get_include_readonly()
            ro, wr, mappings = _prefixes()
            snapshot = VideoRepository().list_media_probe_pending(
                include_readonly=include_ro,
                readonly_prefixes=ro,
                writable_prefixes=wr,
            )
            if not snapshot:
                _SHELL.abort_acquire()
                return {"ok": False, "status": "nothing_to_do"}
            _SHELL.begin_locked()
            global _job_done, _job_total, _done_paths
            with _job_lock:
                _job_done = 0
                _job_total = len(snapshot)
                _done_paths = set()
        except BaseException:
            _SHELL.abort_acquire()
            raise
    _SHELL.start_thread(
        _worker_main,
        (list(snapshot), mappings),
        name=THREAD_NAME,
        on_failure=lambda: _SHELL.release_unlaunched(),
    )
    return {"ok": True, "status": "started"}


def _mark_done(path: str) -> None:
    global _job_done
    with _job_lock:
        if path in _done_paths:
            return
        if _job_done >= _job_total:
            return
        _done_paths.add(path)
        _job_done += 1


def _worker_main(snapshot: list, mappings: dict) -> None:
    """逐列 submit；完成通知以 path 為 key（不綁 job 物件）。"""
    worker = get_worker()
    snapshot_paths = {p for p, _m, _s in snapshot}
    done_event = threading.Event()

    def _on_path_done(path=None):
        if path is not None and path in snapshot_paths:
            _mark_done(path)
        with _job_lock:
            finished = _job_done >= _job_total
        if finished:
            done_event.set()

    try:
        for path, mtime, size_bytes in snapshot:
            def _cb(p=path):
                _on_path_done(p)

            worker.on_complete(path, _cb)
            try:
                from core.path_utils import uri_to_local_fs_path

                fs_path = uri_to_local_fs_path(path, mappings or {})
            except Exception:
                fs_path = path
            worker.submit(path, fs_path, mtime, size_bytes, db_path=None)
        # 等快照內全部 path 至少完成一次（含丟棄／失敗）
        if _job_total == 0:
            done_event.set()
        done_event.wait()
    except Exception:
        logger.exception("media_probe_backfill worker_main failed")
    finally:
        with _SHELL.state_lock:
            if _SHELL.is_running():
                _SHELL.release_locked()


def _reset_for_tests() -> None:
    """測試用：重置模組狀態（不放進公開 API）。"""
    global _job_done, _job_total, _done_paths
    _job_done = 0
    _job_total = 0
    _done_paths = set()
    if _SHELL.is_running():
        with _SHELL.state_lock:
            if _SHELL.is_running():
                _SHELL.release_locked()
