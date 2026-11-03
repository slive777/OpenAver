"""補完全庫 job 核心（188c-T4a，CD-188c-2／-3／-4／-8／-9／-10；序列版，並行＝1）。

與 ``similar_index.py``／``faces_recompute.py`` 為三份刻意重複的骨架，統一留給 189。

公開介面：``start_build()``、``start_rebuild()``、``request_stop()``、
``schedule_incremental()``、``status()``。路由（T5）、並行／降速／429／重試（T4b）不在這裡。

併發模型（不變式 J1～J5 的承載）：

- ``_JOB_LOCK`` 以 ``acquire(blocking=False)`` 取得，build／rebuild／incremental 共用，最多一份。
- ``_STATE_LOCK`` 是短暫的互斥：「取得／釋放工作鎖」與承接旗標 ``_rerun`` 只在它裡面動。
  工作結束前的最後檢查（待處理＝0、沒有被停止、沒有排隊中的承接、清「未完成」旗標）與釋放
  工作鎖在**同一個** ``_STATE_LOCK`` 區段內完成；掃描端「嘗試取得，失敗就排隊承接」也在同一把
  鎖內 ⇒ 掃描要嘛看到鎖已釋放（自己開新 job）、要嘛把旗標留給仍在跑的那份 job 消化。
- ``request_stop()`` 在同一把鎖內設停止旗標並清掉承接；停止後 job 不會自行重開（J2）。
- 本次 job 內失敗的片進 ``ctx.abandoned``，不再被撈（J4）；每部結果在 ``tag_video`` 內已落盤（J5）。
- 重啟不起任何背景執行緒（I-STATUS）：模組載入不做事，``status()`` 只讀 DB。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

from core.ai_services import tags_state
from core.ai_services.tagging import tag_video_sync
from core.config import load_config
from core.database import VideoRepository
from core.logger import get_logger

logger = get_logger(__name__)

THREAD_NAME = "tags-backfill"

_JOB_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_STOP = threading.Event()
_rerun = False


@dataclass
class _Ctx:
    """一份 job 的上下文；``repo`` 在 job 開始當下建立並沿用（db_path 定死）。"""

    kind: str  # "build" | "rebuild" | "incremental"
    repo: VideoRepository
    abandoned: set = field(default_factory=set)
    released: bool = False


# ── 鎖與承接旗標（只在 _STATE_LOCK 內動） ──────────────────────────────────────

def _try_acquire_job() -> bool:
    if not _JOB_LOCK.acquire(blocking=False):
        return False
    return True


def _begin_job_locked(kind: str) -> None:
    global _rerun
    _STOP.clear()
    _rerun = False
    tags_state.job_begin(kind)
    if kind != "incremental":  # CD-188c-8：手動 job 開始時記「有未完成的補完」
        tags_state.meta_set(tags_state.META_BACKFILL_OPEN, "1")


def _release_job_locked(ctx: Optional[_Ctx], outcome: str) -> None:
    global _rerun
    _rerun = False
    tags_state.job_end(outcome)
    if ctx is not None:
        ctx.released = True
    _JOB_LOCK.release()


def _release_unlaunched(outcome: str) -> None:
    with _STATE_LOCK:
        _release_job_locked(None, outcome)


def _consume_handoff_locked() -> bool:
    global _rerun
    if _rerun:
        _rerun = False
        return True
    return False


def _start_thread(ctx: _Ctx) -> None:
    t = threading.Thread(target=_worker_main, args=(ctx,), name=THREAD_NAME, daemon=True)
    try:
        t.start()
    except BaseException:
        _release_unlaunched("error")
        raise


# ── 公開介面 ──────────────────────────────────────────────────────────────────

def start_build() -> dict:
    """補完全庫／繼續。回 ``{"ok", "status": "started"|"already_running"}``。"""
    return _start(rebuild=False)


def start_rebuild() -> dict:
    """全部重建：與 ``start_build`` 同一條取鎖路徑；取得工作鎖後、起 thread 前清掉全部
    「跑過」記號（I-RESET-LOCK：job 在跑時回 ``already_running``、零寫入）。"""
    return _start(rebuild=True)


def _start(rebuild: bool) -> dict:
    kind = "rebuild" if rebuild else "build"
    with _STATE_LOCK:
        if not _try_acquire_job():
            return {"ok": False, "status": "already_running"}
        try:
            repo = VideoRepository()
            if rebuild:
                repo.reset_all_ai_tagged()
            _begin_job_locked(kind)
        except BaseException:
            _JOB_LOCK.release()  # 取得鎖之後任何例外都必須放掉，否則卡在「執行中」
            raise
        ctx = _Ctx(kind, repo)
    _start_thread(ctx)
    return {"ok": True, "status": "started"}


def request_stop() -> dict:
    """停止：已在飛的跑完，之後不再開始新請求；同時中止排隊中的承接。"""
    global _rerun
    with _STATE_LOCK:
        _STOP.set()
        _rerun = False
    return {"ok": True, "running": _JOB_LOCK.locked()}


def schedule_incremental() -> None:
    """掃描收尾呼叫：不拋例外。tags 沒開 → 什麼都不做；有 job 在跑 → 留承接旗標；
    否則起 ``incremental`` job 跑全部沒跑過的片。"""
    try:
        _schedule_incremental()
    except Exception:
        logger.exception("[tags_backfill] schedule_incremental failed")


def _tags_enabled(config: dict) -> bool:
    tags = (config.get("ai_services") or {}).get("tags")
    return bool(isinstance(tags, dict) and tags.get("enabled"))


def _schedule_incremental() -> None:
    global _rerun
    if not _tags_enabled(load_config()):
        return
    repo = VideoRepository()
    with _STATE_LOCK:
        if not _try_acquire_job():
            _rerun = True
            return
        try:
            _begin_job_locked("incremental")
        except BaseException:
            _JOB_LOCK.release()
            raise
        ctx = _Ctx("incremental", repo)
    _start_thread(ctx)


def _last_success_at(memory: Optional[float]) -> Optional[float]:
    if memory is not None:
        return memory
    try:
        raw = tags_state.meta_get(tags_state.META_LAST_SUCCESS)
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def status() -> dict:
    """進度與狀態：SQL 現算＋記憶體觀察值；不起 thread、不打網路、不寫 DB（I-STATUS）。"""
    total, pending = VideoRepository().count_ai_tag_progress()
    snap = tags_state.snapshot()
    job = snap["job"]
    running = _JOB_LOCK.locked()
    is_open = tags_state.meta_get(tags_state.META_BACKFILL_OPEN) == "1"
    return {
        "running": running,
        "job_kind": job["kind"] if running else None,
        "done": job["done"],
        "skipped": job["skipped"],
        "slow": job["slow"],
        "waiting": job["waiting"],
        "stop_reason": job["stop_reason"],
        "outcome": job["outcome"],
        "pending": pending,
        "total": total,
        "tagged": total - pending,
        "resumable": is_open and pending > 0,
        "unreachable": snap["unreachable"],
        "last_success_at": _last_success_at(snap["last_success_at"]),
    }


# ── 工作 thread ───────────────────────────────────────────────────────────────

def _worker_main(ctx: _Ctx) -> None:
    outcome = "error"
    try:
        outcome = _work_loop(ctx)
    except Exception:
        logger.exception("[tags_backfill] worker crashed")
    finally:
        if not ctx.released:
            with _STATE_LOCK:
                _release_job_locked(ctx, outcome)


def _fetch_pending(ctx: _Ctx) -> list:
    """待處理清單（扣掉本次已放棄的，J4）；測試靠這個名字插 barrier。"""
    return [p for p in ctx.repo.list_ai_pending_paths() if p not in ctx.abandoned]


def _work_loop(ctx: _Ctx) -> str:
    while True:
        pending = _fetch_pending(ctx)
        if pending:
            outcome = _process_batch(ctx, pending)
            if outcome != "ok":
                return outcome
            continue
        finished = _finish_if_drained(ctx)
        if finished is not None:
            return finished


def _finish_if_drained(ctx: _Ctx) -> Optional[str]:
    """待處理＝0 的邊界：被停止 → 結束；有承接 → 回 None 再跑一輪；否則清「未完成」旗標
    並在同一區段釋放工作鎖（J3）。"""
    with _STATE_LOCK:
        if _STOP.is_set():
            _release_job_locked(ctx, "stopped")
            return "stopped"
        if _consume_handoff_locked():
            return None
        tags_state.meta_delete(tags_state.META_BACKFILL_OPEN)
        _release_job_locked(ctx, "drained")
        return "drained"


def _process_batch(ctx: _Ctx, pending: list) -> str:
    for path in pending:
        if _STOP.is_set():
            return "stopped"
        _process_one(ctx, path)
    return "ok"


def _tag_one(path: str):
    """測試接縫：標一部片；正常返回＝成功，拋例外＝失敗。"""
    return tag_video_sync(path)


def _process_one(ctx: _Ctx, path: str) -> None:
    try:
        _tag_one(path)
    except Exception:
        # I-FAIL ③：任何失敗當 skip、不中斷整批（政策表屬 T4b）
        logger.exception("[tags_backfill] tag failed, skipping: %s", path)
        ctx.abandoned.add(path)
        tags_state.job_skip()
        return
    tags_state.job_progress()
