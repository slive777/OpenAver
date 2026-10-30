"""圖片相似索引工作核心（186-T4a，CD-186-9／-10／-11／-12）。

公開介面（T4b／T5 依賴）：``start_build()``、``request_stop()``、``schedule_incremental()``、
``status()``、``set_notification_sink(fn)``。入口（HTTP）在 T4b；這裡全是 core 邏輯。

併發模型（不變式 I1／I5／I13 的承載）：

- ``_JOB_LOCK`` 以 ``acquire(blocking=False)`` 取得，最多一份工作（建立或增量）。
- ``_STATE_LOCK`` 是短暫的互斥：「取得／釋放工作鎖」與「承接旗標 ``_rerun``」只在它裡面
  動。工作結束前的最後一次檢查（待處理＝0、沒有被停止、沒有排隊中的承接）與釋放工作鎖
  在**同一個** ``_STATE_LOCK`` 區段內完成；掃描端的「嘗試取得，失敗就排隊承接」也在同一把
  鎖內 ⇒ 掃描要嘛看到鎖已釋放（自己開新工作）、要嘛把旗標留給仍在跑的那份工作消化。
- ``request_stop()`` 在同一把鎖內設停止旗標並清掉排隊中的承接；停止後工作不會自行重開。
- 不在重啟時啟動任何 thread（I6）：模組載入不做任何事，``status()`` 只讀 DB。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable, Optional

from core.ai_services import embeddings, samples, similar_state
from core.ai_services.embeddings import EndpointError
from core.ai_services.image_prep import cover_to_data_uri
from core.config import load_config
from core.database import EmbeddingRepository
from core.database.embeddings import pack_vector
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path

logger = get_logger(__name__)

NOTIFY_KEY = "notif.ai_similar_unreachable"
THREAD_NAME = "similar-index"

_JOB_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_STOP = threading.Event()
_rerun = False
_notification_sink: Optional[Callable[..., None]] = None


@dataclass
class _Ctx:
    """一份工作的不可變上下文；``repo`` 在工作開始當下建立並沿用（db_path 定死）。"""

    kind: str  # "build" | "incremental"
    repo: EmbeddingRepository
    cfg: SimpleNamespace
    path_mappings: dict
    model: str
    dim: int
    first: bool = False
    released: bool = False


def set_notification_sink(fn: Callable[..., None]) -> None:
    """core 不能 import web：由 web/app.py 註冊 ``emit_notification``（BE-LINT-09）。"""
    global _notification_sink
    _notification_sink = fn


# ── 鎖與承接旗標（只在 _STATE_LOCK 內動） ──────────────────────────────────────

def _try_acquire_job() -> bool:
    if not _JOB_LOCK.acquire(blocking=False):
        return False
    return True


def _begin_job_locked(kind: str) -> None:
    global _rerun
    _STOP.clear()
    _rerun = False
    similar_state.job_begin(kind)


def _release_job_locked(ctx: Optional[_Ctx], outcome: str) -> None:
    global _rerun
    _rerun = False
    similar_state.job_end(outcome)
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


# ── 設定 ──────────────────────────────────────────────────────────────────────

def _image_cfg(config: dict) -> dict:
    return (config.get("ai_services") or {}).get("image_similar") or {}


def _endpoint_cfg(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(
        url=raw.get("url", ""), api_key=raw.get("api_key", ""), model=raw.get("model", "")
    )


def _path_mappings(config: dict) -> dict:
    return (config.get("gallery") or {}).get("path_mappings") or {}


def _start_thread(ctx: _Ctx) -> None:
    t = threading.Thread(target=_worker_main, args=(ctx,), name=THREAD_NAME, daemon=True)
    try:
        t.start()
    except BaseException:
        _release_unlaunched("error")
        raise


# ── 公開介面 ──────────────────────────────────────────────────────────────────

def start_build() -> dict:
    """建立／繼續／重建索引。同一次呼叫內先跑一致性測試（I2），過了才定模型並起 thread。

    回傳 ``{"ok", "status": "started"|"already_running"|"test_failed", "kind"?, "check"?}``。
    會阻塞到一致性測試結束（可達 90 秒以上）→ 呼叫端須 ``asyncio.to_thread``。
    """
    with _STATE_LOCK:
        if not _try_acquire_job():
            return {"ok": False, "status": "already_running"}
        _begin_job_locked("build")
    try:
        ctx, failure = _prepare_build()
    except BaseException:
        _release_unlaunched("error")
        raise
    if ctx is None:
        _release_unlaunched("test_failed")
        return failure
    _start_thread(ctx)
    return {"ok": True, "status": "started"}


def _prepare_build() -> tuple:
    """跑一致性測試；過了才定模型（``begin_index``）。回 ``(ctx, None)`` 或 ``(None, 失敗 dict)``。"""
    config = load_config()
    cfg = _endpoint_cfg(_image_cfg(config))
    repo = EmbeddingRepository()
    test = samples.run_consistency_test(cfg)
    if not test.ok:
        similar_state.observe_failure(test.kind, test.check)
        return None, {"ok": False, "status": "test_failed", "kind": test.kind, "check": test.check}
    similar_state.observe_success(test.model, test.dim)
    repo.begin_index(test.model, test.dim)
    return _Ctx("build", repo, cfg, _path_mappings(config), test.model, test.dim), None


def request_stop() -> dict:
    """停止：最多再完成當下那一張。同時中止排隊中的承接（I13 例外）。"""
    global _rerun
    with _STATE_LOCK:
        _STOP.set()
        _rerun = False
    return {"ok": True, "running": _JOB_LOCK.locked()}


def schedule_incremental() -> None:
    """掃描結束後呼叫：不拋例外。條件與承接見 I9／I13。
    ``db_path`` 在呼叫當下定死（repository 建構時解析）。"""
    try:
        _schedule_incremental()
    except Exception:
        logger.exception("[similar_index] schedule_incremental failed")


def _schedule_incremental() -> None:
    global _rerun
    config = load_config()
    if not _image_cfg(config).get("enabled"):
        return
    repo = EmbeddingRepository()
    with _STATE_LOCK:
        if not _try_acquire_job():
            _rerun = True  # I13：有工作在跑（含收尾）→ 由它在邊界承接
            return
        try:
            ctx = _prepare_incremental(repo, config)
        except BaseException:
            _JOB_LOCK.release()  # 取得鎖之後任何例外都必須放掉，否則卡在「執行中」
            raise
        if ctx is None:
            _JOB_LOCK.release()
            return
    _start_thread(ctx)


def _prepare_incremental(repo: EmbeddingRepository, config: dict) -> Optional[_Ctx]:
    state = repo.get_index_state()
    if not _incremental_allowed(state):
        return None
    _begin_job_locked("incremental")
    return _Ctx(
        "incremental", repo, _endpoint_cfg(_image_cfg(config)), _path_mappings(config),
        state["model"], state["dim"], first=True,
    )


def _incremental_allowed(state: dict) -> bool:
    """I9（含 2026-10-31 細化）：index_model 已設、索引已完成('1')、模型沒變。"""
    if not state["model"] or state["dim"] is None or state["complete"] != "1":
        return False
    return not similar_state.model_changed(state["model"], state["dim"])


def status() -> dict:
    """進度與狀態（讀 DB＋記憶體觀察值；不依賴 thread-local 連線）。"""
    repo = EmbeddingRepository()
    state = repo.get_index_state()
    counts = repo.counts(state["model"], state["dim"])
    snap = similar_state.snapshot()
    running = _JOB_LOCK.locked()
    return {
        "running": running,
        "job_kind": snap["job"]["kind"] if running else None,
        "done": snap["job"]["done"],
        "indexed": counts["indexed"],
        "total": counts["total"],
        "pending": counts["pending"],
        "unreadable": counts["unreadable"],
        "unreachable": snap["unreachable"],
        "kind": snap["kind"],
        "check": snap["check"],
        "model": state["model"],
        "last_success_at": state["last_success_at"],
        "model_changed": similar_state.model_changed(state["model"], state["dim"]),
        "complete": state["complete"] == "1",
    }


# ── 工作 thread ───────────────────────────────────────────────────────────────

def _worker_main(ctx: _Ctx) -> None:
    outcome = "error"
    try:
        outcome = _work_loop(ctx)
    except Exception:
        logger.exception("[similar_index] worker crashed")
    finally:
        if not ctx.released:
            with _STATE_LOCK:
                _release_job_locked(ctx, outcome)


def _fetch_pending(ctx: _Ctx) -> list:
    """取待處理清單（只有 ``(video_id, cover_path)``，I11）；測試靠這個名字插 barrier。"""
    return ctx.repo.pending(ctx.model, ctx.dim)


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
    """待處理＝0 的邊界：被停止 → 結束；有排隊的承接 → 回 None 再跑一輪；
    否則（建立工作）寫 ``index_complete='1'`` 並在同一區段釋放工作鎖。"""
    with _STATE_LOCK:
        if _STOP.is_set():
            _release_job_locked(ctx, "stopped")
            return "stopped"
        if _consume_handoff_locked():
            return None
        if ctx.kind == "build":
            ctx.repo.mark_complete()
        _release_job_locked(ctx, "drained")
        return "drained"


def _process_batch(ctx: _Ctx, pending: list) -> str:
    for video_id, cover_path in pending:
        if _STOP.is_set():
            return "stopped"
        outcome = _process_one(ctx, video_id, cover_path)
        if outcome != "ok":
            return outcome
        similar_state.job_progress()
    return "ok"


def _cover_data_uri(ctx: _Ctx, cover_path: str) -> Optional[str]:
    try:
        return cover_to_data_uri(uri_to_local_fs_path(cover_path, ctx.path_mappings))
    except Exception:
        return None


def _process_one(ctx: _Ctx, video_id: int, cover_path: str) -> str:
    uri = _cover_data_uri(ctx, cover_path)
    if uri is None:  # 封面讀不到：本機檔案問題，不算端點錯誤（I7）
        ctx.repo.write_unreadable(video_id, ctx.model, cover_path)
        return "ok"
    first, ctx.first = ctx.first, False
    try:
        result = embeddings.embed(ctx.cfg, uri, first=first)
    except EndpointError as e:
        return _on_endpoint_error(ctx, e)
    similar_state.observe_success(result.model, result.dim)
    index_model, index_dim = ctx.model, ctx.dim
    if result.model != index_model or result.dim != index_dim:
        return "model_changed"
    ctx.repo.write_vector(video_id, result.model, result.dim, pack_vector(result.vector), cover_path)
    return "ok"


def _on_endpoint_error(ctx: _Ctx, err: EndpointError) -> str:
    similar_state.observe_failure(err.kind, err.check)
    if ctx.kind == "incremental" and err.kind == "unreachable":
        _notify_unreachable()
    return "error"


def _notify_unreachable() -> None:
    sink = _notification_sink
    if sink is None:
        return
    try:
        sink("warn", NOTIFY_KEY, task_type="ai_similar")
    except Exception:
        logger.exception("[similar_index] notification sink failed")
