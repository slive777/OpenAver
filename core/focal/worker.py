"""core.focal.worker — single low-priority background face-detection worker.

TASK-98a-T5 (plan-98a.md §D, CD-98a-9). This module is infra only: it never
touches a repo/DB directly. Callers (98b for videos, 98d for actresses)
inject a per-job `commit` callback so the worker stays repo-agnostic.

Design (see plan-98a.md §D for the full rationale):
    key = (kind, id)              kind in {'video', 'actress'}
    job = (key, fs_path, ratio, commit)   -- NO fingerprint at submit time.

Fingerprint is taken at DEQUEUE (job start), not at submit (Codex P2):
taking it at submit would make "swapped while queued" a stale-drop instead
of a recompute of the current image. A second fingerprint is taken right
before commit (compare-and-store): if the image changed mid-detection, the
result is discarded -- the key was already re-queued by the newer submit()
(latest-wins, Codex P1), so nothing is lost.

Single `threading.Lock` guards only the pending/queued/inflight state
transitions -- never the CPU-bound `detect()` call itself.
"""
import os
import queue
import threading

from core.logger import get_logger

from .detector import WORK_WIDTH, detect_focal, format_focal

logger = get_logger(__name__)


def _fingerprint(fs_path):
    """(fs_path, mtime_ns, size) -> tuple; stat failure -> None.

    Nanosecond mtime (not second) -- a same-size fast image swap within the
    same second would otherwise be invisible to compare-and-store.
    """
    try:
        st = os.stat(fs_path)
        return (fs_path, st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class _Job:
    __slots__ = ("key", "fs_path", "ratio", "commit")

    def __init__(self, key, fs_path, ratio, commit):
        self.key = key
        self.fs_path = fs_path
        self.ratio = ratio
        self.commit = commit


class FocalWorker:
    """Single daemon-thread background worker with a latest-wins queue.

    Testing seam: inject `detect_fn` / `fingerprint_fn`. Tests drive
    `_process_one()` synchronously instead of racing the real thread.
    """

    def __init__(self, detect_fn=detect_focal, fingerprint_fn=_fingerprint, auto_start=True):
        self._detect = detect_fn
        self._fingerprint = fingerprint_fn
        # Test-only seam: when False, submit() never starts the real daemon
        # thread, so tests can drive _process_one() synchronously without
        # racing a concurrent worker loop draining the same queue.
        # Production/default behavior (lazy-start on first submit) is
        # unaffected -- see TestLazyStart for that contract.
        self._auto_start = auto_start
        self._lock = threading.Lock()
        self._pending = {}       # key -> _Job (latest-wins snapshot)
        self._queued = set()     # keys currently sitting in self._queue
        self._inflight = set()   # keys currently being processed
        self._queue = queue.Queue()
        self._thread = None

    def submit(self, kind, id, fs_path, ratio, commit):
        # Known limitation (Codex delta review, low-risk): `key` has no DB
        # namespace. If two different db_path scans ever ran concurrently in
        # the same process against the same URI, the later submit()'s
        # latest-wins overwrite would drop the earlier one's `commit`
        # closure -- its detection result would silently never land in its
        # own DB. Not reachable today: every production caller
        # (core/focal_trigger.py -> web/routers/scanner.py,
        # core/gallery_scanner.py's live scan_directory path, core/enricher.py,
        # web/routers/scraper.py) resolves `db_path` from the single
        # process-wide `get_db_path()` default, so there is only ever one
        # active DB per process. `gallery_scanner.scan_to_sqlite(db_path=...)`
        # accepts an arbitrary db_path but has no production caller (test-only
        # today). If a future feature adds concurrent multi-DB scanning
        # against this same singleton worker, `key` must be widened to
        # `(db_path_namespace, kind, id)`.
        key = (kind, id)
        job = _Job(key, fs_path, ratio, commit)
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

    def _process_one(self):
        """Process a single queued key. Synchronous -- tests call this
        directly for determinism instead of racing the daemon thread."""
        key = self._queue.get()
        with self._lock:
            job = self._pending.pop(key, None)
            self._queued.discard(key)
            self._inflight.add(key)
        try:
            if job is None:
                # Defensive only: under the single-consumer invariant every
                # queued key has a live pending entry, so this is unreachable
                # today (belt-and-braces if a 2nd consumer is ever added).
                return
            start_fp = self._fingerprint(job.fs_path)
            if start_fp is None:
                return  # file gone at dequeue time -> give up this round
            focal = self._detect(job.fs_path, job.ratio, WORK_WIDTH)
            end_fp = self._fingerprint(job.fs_path)
            if end_fp == start_fp:
                job.commit(format_focal(focal), start_fp)
            # else: image changed mid-detection -> discard. If the change came
            # from a real re-submit (swap), that submit() already re-queued the
            # key (latest-wins). A bare mtime bump with no resubmit is NOT
            # auto-retried -- it just stays un-updated until the next trigger.
        except Exception:
            logger.exception(f"FocalWorker job failed for key={key}")
        finally:
            with self._lock:
                self._inflight.discard(key)


# Module-level default singleton. Tests must instantiate their own
# FocalWorker() -- never mutate this global.
_worker = FocalWorker()


def submit_focal(kind, id, fs_path, ratio, commit):
    """Convenience wrapper delegating to the module-level singleton."""
    _worker.submit(kind, id, fs_path, ratio, commit)
