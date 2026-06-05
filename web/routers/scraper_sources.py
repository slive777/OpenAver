"""Scraper Sources Router — GET /api/scraper-sources（TASK-61c-5）

向 AI agent 揭露「目前 Runtime Auto Pool」的來源快照：
enabled=True AND is_beta=False AND manual_only=False AND available=True
（Always-On Rule 3，CD-61-18 + CD-61-10）。

過濾複用 `core.source_settings.get_enabled_source_ids(availability_map)`
（已涵蓋 enabled + manual_only + available gate），端點僅在其結果之上
額外排除 `is_beta`，不重寫 gate 邏輯。

`total_enabled` = 實際回傳（已揭露）的來源數，**非** cap basis
（cap counter「已啟用 N / 10」含斷線 metatube，是 UI 概念，與本揭露快照不同）。
本端點是給 AI 的「目前實際會 fan-out 的來源」快照。
"""
from fastapi import APIRouter

from core.config import load_config
from core.logger import get_logger
from core.metatube.state import metatube_state
from core.source_config import SourceConfig, render_name
from core.source_settings import get_enabled_source_ids

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scraper-sources"])


@router.get("/scraper-sources")
def get_scraper_sources() -> dict:
    """查詢目前 auto 搜尋實際 fan-out 的啟用來源清單。

    過濾 = Rule 3：enabled=True AND is_beta=False AND manual_only=False
    AND available=True。停用 / Parts Bin（未 promote 的 metatube）/
    Manual-Only / BETA 來源不會出現在此清單。

    Response:
        {
          "sources": [
            {id, display_name, type, enabled, order, is_censored}, ...
          ],
          "total_enabled": int  # = 已揭露（實際回傳）的來源數
        }
    """
    # 63c-2：注入 MetatubeConnectionState availability map（CD-63c-7）。斷線 / probe-failed
    # 的 metatube provider → 不在 map（或值 False）→ get_enabled_source_ids gate 排除，
    # 與 63c-1 routing factory 對齊（揭露的來源 == 實際可 fan-out 的來源）。builtin bypass gate。
    availability_map = metatube_state.availability_map()

    ids = set(get_enabled_source_ids(availability_map))  # enabled + !manual_only + available gate
    config = load_config()

    out: list[dict] = []
    for s in config.get("sources", []):
        if not isinstance(s, dict):
            continue
        if s.get("id") not in ids:  # 已套用 enabled / manual_only / available gate
            continue
        if s.get("is_beta"):  # Rule 3 額外排除 BETA
            continue
        try:
            sc = SourceConfig(**s)  # 重算 is_censored + render_name（不信任 stored key）
        except Exception:  # noqa: BLE001 — malformed source dict：skip，不 500
            logger.warning("scraper-sources：跳過 malformed source dict (id=%r)", s.get("id"))
            continue
        out.append(
            {
                "id": sc.id,
                "display_name": render_name(sc),
                "type": sc.type,
                "enabled": sc.enabled,
                "order": sc.order,
                "is_censored": sc.is_censored,
            }
        )

    out.sort(key=lambda x: x["order"])
    return {"sources": out, "total_enabled": len(out)}
