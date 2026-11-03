"""入庫後 AI 後處理：決策核心＋入口＋log（189a-T4a）。

公開介面：
- ``run_after_ingest(video_uri, *, route, skip_faces=False, notify=False)``
- ``begin_round()``（本張空殼）
- ``decide``／``title_needs_translation``／``format_log``／``video_label``
- ``Plan``／``Verdict``／``IngestContext``／``ITEMS``

不變式（本張）：
- 入口任何例外都不傳回入庫路（I-HOOK-NEVER-RAISES）。
- 三開關全關且 ``skip_faces=True`` → 不讀 DB、不 log、不交棒（I-HOOK-OFF）。
- 翻譯／相似／標籤各自一條 daemon lane（FIFO、並行度 1、惰性建立），入口只排工作不等結果；
  一項慢或失敗不拖累其他項（I-HOOK-NONBLOCK／I-ITEMS-INDEPENDENT）。人臉項在呼叫端 thread 同步排給既有 worker。
- 掛勾內任何時刻最多一個 job 在改某部片的 NFO：翻譯寫回持 ``hold_nfo_write()``
  （與 ``apply_user_tags`` 同一把鎖，I-NFO-ONE-WRITER）。
- 連不上 AI 服務的側欄通知每輪每項至多一則（I-NOTIFY-PER-ROUND）；``notify=False`` 的路只寫 log。
"""
from __future__ import annotations

import asyncio
import functools
import os
import queue
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from core.ai_services import similar_index, similar_state, tags_backfill_policy, tags_state
from core.ai_services.tagging import TaggingFailure, tag_video_sync
from core.config import load_config
from core.database import VideoRepository
from core.focal import requires_face_detection
from core.focal_trigger import maybe_submit_video_focal
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path
from core.scrapers.utils import has_japanese
from core.title_writeback import apply_title_writeback
from core.translate_service import create_translate_service
from core.user_tags_write import hold_nfo_write

logger = get_logger(__name__)

ITEMS = ("translate", "similar", "faces", "tags")
_TAGS_NOTIFY_KEY = "notif.ai_tags_unreachable"


@dataclass(frozen=True)
class Verdict:
    run: bool
    reason: str = ""


@dataclass(frozen=True)
class Plan:
    translate: Verdict
    similar: Verdict
    faces: Verdict
    tags: Verdict

    def items(self):
        return tuple((name, getattr(self, name)) for name in ITEMS)


@dataclass(frozen=True)
class IngestContext:
    video_uri: str
    route: str
    notify: bool
    cfg: dict
    row: object


def title_needs_translation(row) -> bool:
    return has_japanese(row.title or "") and (row.nfo_mtime or 0) > 0


def video_label(row) -> str:
    if row.number:
        return str(row.number)
    return os.path.basename(row.path or "")


def format_log(route, row, plan: Plan) -> str:
    def _one(v: Verdict) -> str:
        return "run" if v.run else f"skip({v.reason})"

    return (
        f"[post_ingest] route={route} video={video_label(row)} "
        f"translate={_one(plan.translate)} similar={_one(plan.similar)} "
        f"faces={_one(plan.faces)} tags={_one(plan.tags)}"
    )


def _flag_on(cfg: dict, *keys) -> bool:
    cur = cfg
    for key in keys:
        if not isinstance(cur, dict):
            return False
        cur = cur.get(key)
        if cur is None:
            return False
    return bool(cur)


def _decide_translate(cfg: dict, row, skip_translate: bool = False) -> Verdict:
    if not _flag_on(cfg, "translate", "enabled"):
        return Verdict(False, "off")
    if skip_translate:
        return Verdict(False, "preserve_title")
    locale = (cfg.get("general") or {}).get("locale") or "zh-TW"
    if locale == "ja" or not title_needs_translation(row):
        return Verdict(False, "title_in_target_language")
    return Verdict(True)


def _decide_similar(cfg: dict, row, index_ready: bool) -> Verdict:
    if not _flag_on(cfg, "ai_services", "image_similar", "enabled"):
        return Verdict(False, "off")
    if not row.cover_path:
        return Verdict(False, "no_cover")
    if not index_ready:
        return Verdict(False, "index_not_ready")
    return Verdict(True)


def _decide_faces(row, skip_faces: bool, cover_exists: bool) -> Verdict:
    if skip_faces:
        return Verdict(False, "own_trigger")
    if not requires_face_detection(row.number or "", row.maker or ""):
        return Verdict(False, "not_uncensored")
    if not row.cover_path or not cover_exists:
        return Verdict(False, "no_cover")
    return Verdict(True)


def _decide_tags(cfg: dict, row) -> Verdict:
    if not _flag_on(cfg, "ai_services", "tags", "enabled"):
        return Verdict(False, "off")
    if not row.cover_path:
        return Verdict(False, "no_cover")
    return Verdict(True)


def decide(
    cfg: dict,
    row,
    *,
    skip_faces: bool,
    index_ready: bool,
    cover_exists: bool,
    skip_translate: bool = False,
) -> Plan:
    return Plan(
        translate=_decide_translate(cfg, row, skip_translate),
        similar=_decide_similar(cfg, row, index_ready),
        faces=_decide_faces(row, skip_faces, cover_exists),
        tags=_decide_tags(cfg, row),
    )


def _index_ready() -> bool:
    from core.ai_services import similar_index
    from core.database import EmbeddingRepository

    return similar_index._incremental_allowed(EmbeddingRepository().get_index_state())


def _cover_exists(row, cfg: dict) -> bool:
    return os.path.exists(
        uri_to_local_fs_path(
            row.cover_path,
            (cfg.get("gallery") or {}).get("path_mappings") or {},
        )
    )


class _Lane:
    def __init__(self, item: str):
        self.item = item
        self.queue = queue.Queue()
        self.thread = None


_LANES: dict[str, _Lane] = {}
_LANES_LOCK = threading.Lock()


def _get_lane(item: str) -> _Lane:
    with _LANES_LOCK:
        lane = _LANES.get(item)
        if lane is None:
            lane = _LANES[item] = _Lane(item)
        if lane.thread is None:
            lane.thread = threading.Thread(
                target=_lane_main, args=(lane,), name=f"post-ingest-{item}", daemon=True,
            )
            lane.thread.start()
        return lane


def _lane_main(lane: _Lane) -> None:
    while True:
        job = lane.queue.get()
        if job is None:
            return
        try:
            job()
        except Exception:
            logger.exception("[post_ingest] lane job crashed item=%s", lane.item)
        finally:
            lane.queue.task_done()


def _submit(item: str, job: Callable[[], None]) -> None:
    lane = _get_lane(item)
    lane.queue.put(job)


def _path_mappings(ctx: IngestContext) -> dict:
    return (ctx.cfg.get("gallery") or {}).get("path_mappings") or {}


_REFUSAL_MARKERS = ("無法翻譯", "無法提供", "抱歉", "i can't", "i cannot", "i'm sorry", "sorry")


def _bad_translation(source: str, translated: str) -> bool:
    s, t = source.strip(), translated.strip()
    if not t: return True
    t = t.replace("’", "'")
    if t == s or has_japanese(t) or "\n" in t:
        return True
    if len(t) > max(2 * len(s), len(s) + 40):
        return True
    return any(m in t.lower() for m in _REFUSAL_MARKERS)


def _row_stale(fresh, row) -> bool:
    """入隊後這列被改過（或不見了）→ 不能拿舊譯文蓋回去。"""
    if fresh is None:
        return True
    return any(
        getattr(fresh, f) != getattr(row, f) for f in ("title", "original_title", "nfo_mtime")
    )


def _job_translate(ctx: IngestContext) -> Optional[str]:
    locale = (ctx.cfg.get("general") or {}).get("locale") or "zh-TW"
    service = create_translate_service(ctx.cfg.get("translate") or {}, locale)
    translated = asyncio.run(service.translate_or_raise(
        ctx.row.title,
        {"actors": ctx.row.actresses or [], "number": ctx.row.number or ""},
    ))
    if _bad_translation(ctx.row.title, translated):
        return "bad_translation"
    mappings = _path_mappings(ctx)
    with hold_nfo_write():
        repo = VideoRepository()
        fresh = repo.get_by_path(ctx.video_uri)
        if _row_stale(fresh, ctx.row):
            return "stale_row"
        result = apply_title_writeback(
            repo, fresh, translated, None, ctx.cfg, mappings,
        )
    if not result.get("success"):
        return result.get("error") or "write_failed"
    return None


def _job_similar(ctx: IngestContext) -> Optional[str]:
    outcome = similar_index.index_one(ctx.video_uri)
    if outcome == "indexed":
        return None
    if outcome == "unreachable" and ctx.notify:
        if similar_state.note_failure():
            similar_index._notify_unreachable()
    return outcome


def _is_unreachable_failure(e: BaseException) -> bool:
    return tags_backfill_policy.stop_reason(e) not in (None, "disabled")


def _job_tags(ctx: IngestContext) -> Optional[str]:
    try:
        tag_video_sync(ctx.video_uri, config=ctx.cfg)
    except TaggingFailure as e:
        if ctx.notify and _is_unreachable_failure(e):
            if tags_state.note_hook_failure():
                tags_state.emit(_TAGS_NOTIFY_KEY)
        return e.reason
    return None


def _job_faces(ctx: IngestContext) -> Optional[str]:
    cover_fs = uri_to_local_fs_path(ctx.row.cover_path, _path_mappings(ctx))
    maybe_submit_video_focal(
        ctx.row.number, ctx.row.maker, ctx.video_uri, cover_fs,
        cover_path_uri=ctx.row.cover_path,
    )
    return None


def _run_item(item: str, ctx: IngestContext) -> None:
    try:
        reason = None
        try:
            if item == "translate":
                reason = _job_translate(ctx)
            elif item == "similar":
                reason = _job_similar(ctx)
            elif item == "tags":
                reason = _job_tags(ctx)
            elif item == "faces":
                reason = _job_faces(ctx)
        except Exception as e:
            reason = type(e).__name__
        if reason is not None:
            logger.warning(
                "[post_ingest] %s failed reason=%s video=%s",
                item, reason, video_label(ctx.row),
            )
    except Exception:
        logger.exception("[post_ingest] run_item failed item=%s", item)


def begin_round() -> None:
    """新一輪（定時整理開跑前呼叫）：重置通知旗標，每項可再發一則。絕不拋。"""
    try:
        tags_state.new_round()
        similar_state.new_round()
    except Exception:
        logger.exception("[post_ingest] begin_round failed")


def run_after_ingest(
    video_uri: str,
    *,
    route: str,
    skip_faces: bool = False,
    notify: bool = False,
    skip_translate: bool = False,
) -> None:
    try:
        _run_after_ingest(
            video_uri, route=route, skip_faces=skip_faces, notify=notify,
            skip_translate=skip_translate,
        )
    except Exception:
        logger.exception(
            "[post_ingest] run_after_ingest failed video=%s", video_uri,
        )


def _run_after_ingest(
    video_uri: str,
    *,
    route: str,
    skip_faces: bool,
    notify: bool,
    skip_translate: bool = False,
) -> None:
    cfg = load_config()
    translate_on = _flag_on(cfg, "translate", "enabled")
    similar_on = _flag_on(cfg, "ai_services", "image_similar", "enabled")
    tags_on = _flag_on(cfg, "ai_services", "tags", "enabled")
    if skip_faces and not (translate_on or similar_on or tags_on):
        return
    row = VideoRepository().get_by_path(video_uri)
    if row is None:
        logger.warning(
            "[post_ingest] route=%s video=%s skip(row_missing)",
            route,
            os.path.basename(video_uri),
        )
        return
    index_ready = (
        _index_ready() if similar_on and row.cover_path else False
    )
    cover_exists = (
        _cover_exists(row, cfg) if (not skip_faces) and row.cover_path else False
    )
    plan = decide(
        cfg, row,
        skip_faces=skip_faces,
        index_ready=index_ready,
        cover_exists=cover_exists,
        skip_translate=skip_translate,
    )
    logger.info("%s", format_log(route, row, plan))
    ctx = IngestContext(
        video_uri=video_uri, route=route, notify=notify, cfg=cfg, row=row,
    )
    for name, verdict in plan.items():
        if not verdict.run:
            continue
        try:
            if name == "faces":
                _run_item("faces", ctx)
            else:
                _submit(name, functools.partial(_run_item, name, ctx))
        except Exception:
            logger.exception(
                "[post_ingest] item failed item=%s video=%s", name, video_uri,
            )
