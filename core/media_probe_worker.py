"""core.media_probe_worker — 單一背景探針 worker（TASK-198a-T2a，CD-198a-4）。

照 ``core/focal/worker.py`` 形狀：latest-wins 佇列、``_process_one()`` 測試縫、
lazy-start。本模組直接寫 DB（透過 ``VideoRepository.update_media_probe``）。
"""
from __future__ import annotations

import os
import queue
import threading

from core import media_probe
from core.database.video import VideoRepository
from core.logger import get_logger

logger = get_logger(__name__)


def _default_stat(fs_path):
    """(st_mtime_ns, st_size) 或 None。"""
    try:
        st = os.stat(fs_path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class _Job:
    __slots__ = ("path_uri", "fs_path", "expected_mtime", "expected_size", "db_path")

    def __init__(self, path_uri, fs_path, expected_mtime, expected_size, db_path):
        self.path_uri = path_uri
        self.fs_path = fs_path
        self.expected_mtime = expected_mtime
        self.expected_size = expected_size
        self.db_path = db_path


class MediaProbeWorker:
    """單一 daemon-thread 背景 worker；latest-wins。"""

    def __init__(
        self,
        probe_fn=None,
        stat_fn=_default_stat,
        auto_start=True,
    ):
        # 建構時取模組屬性，測試可注入／patch media_probe.probe_file
        self._probe = probe_fn if probe_fn is not None else media_probe.probe_file
        self._stat = stat_fn
        self._auto_start = auto_start
        self._lock = threading.Lock()
        self._pending = {}       # path_uri -> _Job (latest-wins)
        self._queued = set()
        self._inflight = set()
        self._queue = queue.Queue()
        self._thread = None
        # path → list[callback]；每處理完一個 key（finally）通知，不綁在 job 上（I6）
        self._completion = {}

    def on_complete(self, path_uri, callback) -> None:
        """以 path 為 key 登錄完成通知（寫入／丟棄／例外皆算）。"""
        with self._lock:
            self._completion.setdefault(path_uri, []).append(callback)

    def clear_completion(self, path_uri) -> None:
        """測試／重開 job 時清掉殘留 callback。"""
        with self._lock:
            self._completion.pop(path_uri, None)

    def submit(self, path_uri, fs_path, expected_mtime, expected_size, db_path=None):
        # Known limitation (mirrored from focal/worker.py:104–121): `key` has no DB
        # namespace. If two different db_path scans ever ran concurrently in the
        # same process against the same URI, the later submit()'s latest-wins
        # overwrite would drop the earlier one's job — its probe result would
        # silently never land in its own DB. Not reachable today: production
        # uses a single process-wide DB via get_db_path(). If a future feature
        # adds concurrent multi-DB scanning against this same singleton worker,
        # `key` must be widened to `(db_path_namespace, path_uri)`.
        key = path_uri
        job = _Job(path_uri, fs_path, expected_mtime, expected_size, db_path)
        with self._lock:
            self._pending[key] = job  # always overwrite -> latest-wins
            if key not in self._queued:
                self._queued.add(key)
                self._queue.put(key)
        if self._auto_start:
            self._ensure_started()

    def _ensure_started(self):
        if self._thread is not None:
            return
        with self._lock:
            if self._thread is None:
                t = threading.Thread(target=self._worker_loop, daemon=True)
                self._thread = t
                t.start()

    def _worker_loop(self):
        while True:
            self._process_one()

    def _notify_complete(self, key) -> None:
        callbacks = []
        with self._lock:
            callbacks = list(self._completion.pop(key, []))
        for cb in callbacks:
            try:
                cb()
            except Exception:
                logger.exception("media probe completion callback failed for %s", key)

    def _process_one(self):
        """Process a single queued key. Synchronous — tests call this
        directly for determinism instead of racing the daemon thread."""
        key = self._queue.get()
        with self._lock:
            job = self._pending.pop(key, None)
            self._queued.discard(key)
            self._inflight.add(key)
        try:
            if job is None:
                return
            start_stat = self._stat(job.fs_path)
            if start_stat is None:
                return
            result = self._probe(job.fs_path)
            if getattr(result, "status", None) == "unreadable":
                return
            end_stat = self._stat(job.fs_path)
            if end_stat != start_stat:
                return
            repo = VideoRepository(job.db_path)
            repo.update_media_probe(
                job.path_uri,
                result,
                job.expected_mtime,
                job.expected_size,
            )
        except Exception:
            logger.exception("MediaProbeWorker job failed for path=%s", key)
        finally:
            with self._lock:
                self._inflight.discard(key)
            self._notify_complete(key)


# Module-level default singleton.
_worker = MediaProbeWorker()


def submit_media_probe(path_uri, fs_path, expected_mtime, expected_size, db_path=None):
    """Convenience wrapper delegating to the module-level singleton."""
    _worker.submit(path_uri, fs_path, expected_mtime, expected_size, db_path=db_path)


def get_worker() -> MediaProbeWorker:
    """測試／backfill 取得單例（可被 monkeypatch 換成假實例）。"""
    return _worker
