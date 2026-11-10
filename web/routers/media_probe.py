"""影片資訊讀取提醒端點（TASK-198a-T5，CD-198a-8）。

薄委派 ``core.media_probe_backfill``；狀態只在 ``app_meta``（不經 config）。
全部 ``def``（BE-ASYNC-01）。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import media_probe_backfill
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/media-probe", tags=["media_probe"])


class MediaProbeSettingsBody(BaseModel):
    dismissed: Optional[bool] = None
    include_readonly: Optional[bool] = None


def _internal_error(what: str) -> JSONResponse:
    logger.exception("media_probe %s failed", what)
    return JSONResponse(status_code=500, content={"error": "操作失敗"})


@router.get("/status")
def get_status():
    try:
        return media_probe_backfill.status()
    except Exception:
        return _internal_error("status")


@router.post("/settings")
def post_settings(body: MediaProbeSettingsBody):
    try:
        if body.dismissed is not None:
            media_probe_backfill.set_dismissed(body.dismissed)
        if body.include_readonly is not None:
            media_probe_backfill.set_include_readonly(body.include_readonly)
        return media_probe_backfill.status()
    except Exception:
        return _internal_error("settings")


@router.post("/start")
def post_start():
    try:
        return media_probe_backfill.start()
    except Exception:
        return _internal_error("start")
