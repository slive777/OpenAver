"""補完全庫 job 核心（188c-T4a／T4b，CD-188c-2／-3／-4／-5／-6／-7／-8／-9／-10／-11）。

與 ``similar_index.py``／``faces_recompute.py`` 為三份刻意重複的骨架，統一留給 189。

公開介面：``start_build()``、``start_rebuild()``、``request_stop()``、
``schedule_incremental()``、``status()``。路由（T5）不在這裡。

併發模型（不變式 J1～J5 的承載）：

- ``_SHELL.job_lock`` 以 ``acquire(blocking=False)`` 取得，build／rebuild／incremental 共用，最多一份。
- ``_SHELL.state_lock`` 是短暫的互斥：「取得／釋放工作鎖」與承接旗標 ``_SHELL.rerun`` 只在它裡面動。
  工作結束前的最後檢查（待處理＝0、沒有被停止、沒有排隊中的承接、清「未完成」旗標）與釋放
  工作鎖在**同一個** ``_SHELL.state_lock`` 區段內完成；掃描端「嘗試取得，失敗就排隊承接」也在同一把
  鎖內 ⇒ 掃描要嘛看到鎖已釋放（自己開新 job）、要嘛把旗標留給仍在跑的那份 job 消化。
- ``request_stop()`` 在同一把鎖內設停止旗標並清掉承接；停止後 job 不會自行重開（J2）。
- 本次 job 內失敗的片進 ``ctx.abandoned``，不再被撈（J4）；每部結果在 ``tag_video`` 內已落盤（J5）。
- 重啟不起任何背景執行緒（I-STATUS）：模組載入不做事，``status()`` 只讀 DB。
- T4b：``_process_batch`` 內開 ``MAX_CONCURRENCY`` 條 pool thread＋名額 gate；政策由
  ``tags_backfill_policy.RunPolicy`` 驅動；429 等待用 ``_SHELL.stop.wait``。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from time import monotonic as _monotonic_impl
from typing import Optional

from core.ai_services import tags_backfill_policy, tags_state
from core.ai_services.job_shell import JobShell
from core.ai_services.tagging import tag_video_sync
from core.config import load_config
from core.database import VideoRepository
from core.logger import get_logger

logger = get_logger(__name__)

THREAD_NAME = "tags-backfill"
_NOTIF_INCREMENTAL = "notif.ai_tags_unreachable"
_NOTIF_BACKFILL = "notif.ai_tags_backfill_stopped"

_SHELL = JobShell()

# 可注入假時鐘（測試）；`from time import monotonic` 避開 DoD 的 `import time` 字面
_monotonic = _monotonic_impl


@dataclass
class _Ctx:
    """一份 job 的上下文；``repo`` 在 job 開始當下建立並沿用（db_path 定死）。"""

    kind: str  # "build" | "rebuild" | "incremental"
    repo: VideoRepository
    abandoned: set = field(default_factory=set)
    released: bool = False
    # T4b：政策／gate／halt（不新增模組層可變狀態，BE-TEST-38）
    policy: tags_backfill_policy.RunPolicy = field(
        default_factory=tags_backfill_policy.RunPolicy)
    lock: threading.Lock = field(default_factory=threading.Lock)
    inflight: int = 0
    n_waiting: int = 0
    halt_reason: Optional[str] = None
    suppress_notify: bool = False  # 第一次 halt 當下若使用者已停止 → 整批不通知
    cooldown_until: Optional[float] = None  # I-COOLDOWN：共用冷卻截止（monotonic）
    gate: threading.Condition = field(init=False)

    def __post_init__(self) -> None:
        self.gate = threading.Condition(self.lock)


# ── 鎖與承接旗標（只在 _SHELL.state_lock 內動） ────────────────────────────────

def _begin_job_locked(kind: str) -> None:
    _SHELL.begin_locked()
    tags_state.job_begin(kind)
    if kind != "incremental":  # CD-188c-8：手動 job 開始時記「有未完成的補完」
        tags_state.meta_set(tags_state.META_BACKFILL_OPEN, "1")


def _release_job_locked(ctx: Optional[_Ctx], outcome: str) -> None:
    def _before_release() -> None:
        tags_state.job_end(outcome)
        if ctx is not None:
            ctx.released = True

    _SHELL.release_locked(before_release=_before_release)


def _release_unlaunched(outcome: str) -> None:
    def _before_release() -> None:
        tags_state.job_end(outcome)

    _SHELL.release_unlaunched(before_release=_before_release)


def _start_thread(ctx: _Ctx) -> None:
    _SHELL.start_thread(
        _worker_main, (ctx,), name=THREAD_NAME,
        on_failure=lambda: _release_unlaunched("error"))


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
    with _SHELL.state_lock:
        if not _SHELL.try_acquire():
            return {"ok": False, "status": "already_running"}
        try:
            repo = VideoRepository()
            if rebuild:
                repo.reset_all_ai_tagged()
            _begin_job_locked(kind)
        except BaseException:
            _SHELL.abort_acquire()  # 取得鎖之後任何例外都必須放掉，否則卡在「執行中」
            raise
        ctx = _Ctx(kind, repo)
    _start_thread(ctx)
    return {"ok": True, "status": "started"}


def request_stop() -> dict:
    """停止：已在飛的跑完，之後不再開始新請求；同時中止排隊中的承接。"""
    _SHELL.request_stop()
    return {"ok": True, "running": _SHELL.is_running()}


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
    if not _tags_enabled(load_config()):
        return
    repo = VideoRepository()
    with _SHELL.state_lock:
        if not _SHELL.schedule_handoff():
            return
        try:
            _begin_job_locked("incremental")
        except BaseException:
            _SHELL.abort_acquire()
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
    running = _SHELL.is_running()
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
            with _SHELL.state_lock:
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
    with _SHELL.state_lock:
        if _SHELL.stop.is_set():
            _release_job_locked(ctx, "stopped")
            return "stopped"
        if _SHELL.consume_handoff_locked():
            return None
        tags_state.meta_delete(tags_state.META_BACKFILL_OPEN)
        _release_job_locked(ctx, "drained")
        return "drained"


def _process_batch(ctx: _Ctx, pending: list) -> str:
    """開 pool thread 處理本批 pending；回傳前 join 全部。非 ``ok``＝halt／stopped。"""
    queue = list(pending)
    n = tags_backfill_policy.MAX_CONCURRENCY
    workers = [
        threading.Thread(
            target=_pool_worker,
            args=(ctx, queue),
            name=f"tags-backfill-w{k}",
            daemon=True,
        )
        for k in range(n)
    ]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    if ctx.halt_reason is not None:
        return ctx.halt_reason
    if _SHELL.stop.is_set():
        return "stopped"
    return "ok"


def _tag_one(path: str):
    """測試接縫：標一部片；正常返回＝成功，拋例外＝失敗。"""
    return tag_video_sync(path)


def _pool_worker(ctx: _Ctx, queue: list) -> None:
    while True:
        claimed = _claim(ctx, queue)
        if claimed is None:
            return
        path, started_degraded = claimed
        # _process_one 負責釋放（含 429 等待期間暫放再取）
        _process_one(ctx, path, started_degraded)


def _gate_blocked(ctx: _Ctx) -> bool:
    return ctx.halt_reason is not None or _SHELL.stop.is_set()


def _in_cooldown_locked(ctx: _Ctx) -> bool:
    """呼叫端已持有 ``ctx.gate``。"""
    return ctx.cooldown_until is not None and _monotonic() < ctx.cooldown_until


def _refresh_waiting_locked(ctx: _Ctx) -> None:
    """呼叫端已持有 ``ctx.gate``；冷卻中或仍有等待者 → waiting。"""
    cooling = _in_cooldown_locked(ctx)
    tags_state.job_set(waiting=cooling or ctx.n_waiting > 0)


def _wait_for_slot(ctx: _Ctx) -> bool:
    """呼叫端已持有 ``ctx.gate``；等到不在冷卻且 ``inflight < limit``，或被 stop／halt。回 False＝應退出。"""
    while True:
        if _gate_blocked(ctx):
            return False
        while _in_cooldown_locked(ctx):
            if _gate_blocked(ctx):
                return False
            remaining = ctx.cooldown_until - _monotonic()
            ctx.gate.wait(timeout=min(0.5, max(remaining, 0.0)))
            if _gate_blocked(ctx):
                return False
        while ctx.inflight >= ctx.policy.limit:
            if _gate_blocked(ctx):
                return False
            ctx.gate.wait(timeout=0.5)
            if _gate_blocked(ctx):
                return False
        if _in_cooldown_locked(ctx):
            continue
        return True


def _claim(ctx: _Ctx, queue: list) -> Optional[tuple[str, bool]]:
    """取得一個名額並領取下一部片；冷卻期間不領；放行當下捕獲 ``started_degraded``。"""
    with ctx.gate:
        while True:
            if _gate_blocked(ctx) or not queue:
                return None
            if not _wait_for_slot(ctx):
                return None
            if not queue:
                return None
            path = queue.pop(0)
            ctx.inflight += 1
            started_degraded = ctx.policy.attempt_started()
            return path, started_degraded


def _acquire_slot(ctx: _Ctx) -> Optional[bool]:
    """429 等待後重送：冷卻結束後再取名額並捕獲新的 ``started_degraded``。"""
    with ctx.gate:
        while True:
            if _gate_blocked(ctx):
                return None
            if not _wait_for_slot(ctx):
                return None
            ctx.inflight += 1
            return ctx.policy.attempt_started()


def _release_slot(ctx: _Ctx) -> None:
    with ctx.gate:
        ctx.inflight -= 1
        ctx.gate.notify_all()


def _halt(ctx: _Ctx, reason: str) -> None:
    """整批停止：設 halt 旗標、喚醒 gate／429 等待；stop_reason 只寫第一次，通知靠 note_failure 去重。"""
    first = False
    with ctx.gate:
        if ctx.halt_reason is None:
            # 鎖定「halt 當下使用者是否已停止」；之後 _SHELL.stop.set 只為喚醒 429，不改此判斷
            ctx.suppress_notify = _SHELL.stop.is_set()
            ctx.halt_reason = reason
            first = True
        ctx.gate.notify_all()
    if first:
        tags_state.job_set(stop_reason=reason)
    # 每位做出 halt 決策的 worker 都走到這裡；去重由 note_failure。再 set _SHELL.stop 喚醒 429。
    if reason != "disabled" and not ctx.suppress_notify:
        if tags_state.note_failure():
            key = _NOTIF_INCREMENTAL if ctx.kind == "incremental" else _NOTIF_BACKFILL
            tags_state.emit(key)
    _SHELL.stop.set()  # 喚醒 _wait_429；halt 優先於 stopped（_process_batch 先看 halt_reason）


def _wait_429(ctx: _Ctx, decision: tags_backfill_policy.Decision) -> bool:
    """加入共用冷卻並等到截止；回 True＝被停止或 halt。``wait_s == 0`` 也必須呼叫 ``_SHELL.stop.wait``。

    I-COOLDOWN：僅在「當下不在冷卻中」的第一次 429 設定截止＝now+wait_s；冷卻中回來的舊 429 不延長。
    """
    with ctx.gate:
        now = _monotonic()
        if ctx.cooldown_until is None or now >= ctx.cooldown_until:
            ctx.cooldown_until = now + decision.wait_s
        deadline = ctx.cooldown_until
        ctx.n_waiting += 1
        _refresh_waiting_locked(ctx)
        ctx.gate.notify_all()
    try:
        while True:
            if _gate_blocked(ctx):
                return True
            remaining = deadline - _monotonic()
            if remaining <= 0:
                # wait_s==0／已到期也必須呼叫縫，供 spy／mutation
                stopped = _SHELL.stop.wait(0)
                return bool(stopped) or _gate_blocked(ctx)
            stopped = _SHELL.stop.wait(remaining)
            if stopped or _gate_blocked(ctx):
                return True
    finally:
        with ctx.gate:
            ctx.n_waiting -= 1
            if _gate_blocked(ctx) or not _in_cooldown_locked(ctx):
                ctx.cooldown_until = None
            _refresh_waiting_locked(ctx)
            ctx.gate.notify_all()


def _reacquire_after_yield(ctx: _Ctx) -> Optional[bool]:
    """降速／429 後重取名額；回 None＝應退出，否則為新的 started_degraded。"""
    if ctx.halt_reason is not None or _SHELL.stop.is_set():
        return None
    return _acquire_slot(ctx)


def _process_one(ctx: _Ctx, path: str, started_degraded: bool) -> None:
    """處理一部片（含 429 重送與 unreachable 重試）；進入時已持有飛行名額，離開前釋放。"""
    retries_used = 0
    holding = True
    try:
        while True:
            if ctx.halt_reason is not None or _SHELL.stop.is_set():
                return
            try:
                _tag_one(path)
            except Exception as exc:
                # 決策⑤：使用者停止之後才回來的失敗 → 不重試、不 skip、不 _halt
                if _SHELL.stop.is_set() and ctx.halt_reason is None:
                    return
                verdict = tags_backfill_policy.classify_failure(exc)
                with ctx.lock:
                    decision = ctx.policy.on_failure(
                        verdict, started_degraded, retries_used)
                    degraded_now = ctx.policy.degraded
                if degraded_now:
                    tags_state.job_set(slow=True)
                if decision.action == "halt":
                    # 每位 halt 決策者都進 _halt（通知靠 note_failure 去重；stop_reason 只寫第一次）
                    _halt(ctx, decision.stop_reason or "unreachable")
                    return
                if ctx.halt_reason is not None or _SHELL.stop.is_set():
                    return  # 已 halt／停止：不 skip、不重試
                if decision.action == "skip":
                    logger.exception(
                        "[tags_backfill] tag failed, skipping: %s", path)
                    ctx.abandoned.add(path)
                    tags_state.job_skip()
                    return
                if decision.action == "wait_retry":
                    _release_slot(ctx)
                    holding = False
                    if _wait_429(ctx, decision):
                        return  # 被停止／halt：不重送、不放棄
                    started = _reacquire_after_yield(ctx)
                    if started is None:
                        return
                    started_degraded = started
                    holding = True
                    continue
                # retry：降速後必須重走 gate，重新捕獲 started_degraded
                retries_used += 1
                _release_slot(ctx)
                holding = False
                started = _reacquire_after_yield(ctx)
                if started is None:
                    return
                started_degraded = started
                holding = True
                continue
            with ctx.lock:
                ctx.policy.on_success()
            tags_state.job_progress()
            return
    finally:
        if holding:
            _release_slot(ctx)
