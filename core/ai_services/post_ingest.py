"""入庫後 AI 後處理：決策核心＋入口＋log（189a-T4a）。

公開介面：
- ``run_after_ingest(video_uri, *, route, skip_faces=False, notify=False)``
- ``begin_round()``（本張空殼）
- ``decide``／``title_needs_translation``／``format_log``／``video_label``
- ``Plan``／``Verdict``／``IngestContext``／``ITEMS``

不變式（本張）：
- 入口任何例外都不傳回入庫路（I-HOOK-NEVER-RAISES）。
- 三開關全關且 ``skip_faces=True`` → 不讀 DB、不 log、不交棒（I-HOOK-OFF）。
- 本張不啟動背景工作或交棒佇列，不呼叫任何 AI／對焦／翻譯／標籤／相似 job；
  ``_submit``／``_run_item`` 皆為 no-op，供 T4b 替換本體。
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import Callable

from core.config import load_config
from core.database import VideoRepository
from core.focal import requires_face_detection
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path
from core.scrapers.utils import has_japanese

logger = get_logger(__name__)

ITEMS = ("translate", "similar", "faces", "tags")


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


def _decide_translate(cfg: dict, row) -> Verdict:
    if not _flag_on(cfg, "translate", "enabled"):
        return Verdict(False, "off")
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
) -> Plan:
    return Plan(
        translate=_decide_translate(cfg, row),
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


def _submit(item: str, job: Callable[[], None]) -> None:
    return None


def _run_item(item: str, ctx: IngestContext) -> None:
    return None


def begin_round() -> None:
    """T4b 會在此重置 round 狀態；本張空殼。"""
    return None


def run_after_ingest(
    video_uri: str,
    *,
    route: str,
    skip_faces: bool = False,
    notify: bool = False,
) -> None:
    try:
        _run_after_ingest(
            video_uri, route=route, skip_faces=skip_faces, notify=notify,
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
