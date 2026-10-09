"""
web/routers/source_probe.py — TASK-163b-T1
==========================================
POST /api/sources/probe — 設定頁「測試連線」。

收請求體（畫面上未儲存的代理位址、範圍、亮著的來源 id）→ 組成 ProxySettings 快照
→ 交給 core.source_probe.run_probes → 包成 {"results": ...}。
本檔不含任何判讀；絕不使用已儲存的設定。刻意「不揭露」於 capabilities（F14）。
"""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.logger import get_logger
from core.proxy_policy import ProxySettings
from core.source_probe import run_probes

logger = get_logger('source_probe')
router = APIRouter(prefix="/api", tags=["source_probe"])


class SourceProbeRequest(BaseModel):
    proxy_url: str = ''
    proxy_scope: Literal['dmm', 'all'] = 'dmm'
    source_ids: list[str] = Field(max_length=64)


@router.post("/sources/probe")
def probe_sources(body: SourceProbeRequest):
    snap = ProxySettings(url=body.proxy_url, scope=body.proxy_scope)
    return {"results": run_probes(snap, body.source_ids)}
