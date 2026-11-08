"""Cover badges API Router — /api/cover-badges

端點：
    GET /api/cover-badges/manifest  封面短名屬性表（唯讀，消費 T1 payload）
"""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from core.cover_attributes import manifest_payload

router = APIRouter(prefix="/api/cover-badges", tags=["cover-badges"])


class CoverBadgeRule(BaseModel):
    id: str
    canonical_tag: str
    display_name: str
    match_aliases: List[str]
    display_order: int
    i18n_key: str
    supersedes: List[str] = []


@router.get("/manifest", response_model=List[CoverBadgeRule])
def get_manifest() -> List[CoverBadgeRule]:
    """回傳封面短名屬性表。資料來源為 core.cover_attributes.manifest_payload()。"""
    return manifest_payload()
