"""AI services endpoints for embeddings samples and consistency test (186-T3).

- GET  /api/ai/sample/embeddings
- POST /api/ai/similar/test
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.ai_services.samples import (
    DIFF_MAX,
    DIM_MAX,
    DIM_MIN,
    SAME_MIN,
    get_sample_inputs,
    run_consistency_test,
)
from core.config import load_config
from core.logger import get_logger
from core.secret_fields import read_secret, resolve_secret

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai_services"])

# Agent-facing steps for the same assertions the test button runs (docs land in T7).
_SAMPLE_STEPS = [
    "POST {base}/v1/embeddings with inputs[0] (allow cold-start; first call may be slow).",
    "POST again with inputs[0]; cosine(v1, v2) must be >= expect.same_min.",
    "POST with inputs[1]; cosine(v1, v_b) must be < expect.diff_max.",
    "All three responses share the same model string and dim in [dim_min, dim_max].",
]


class SimilarTestRequest(BaseModel):
    """Optional overrides. Absent (None) → stored config; present → use given value."""

    url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


def _resolve_similar_cfg(body: SimilarTestRequest, config: dict) -> SimpleNamespace:
    stored = (config.get("ai_services") or {}).get("image_similar") or {}
    url = stored.get("url", "") if body.url is None else body.url
    model = stored.get("model", "") if body.model is None else body.model
    stored_key = read_secret(config, "ai_services.image_similar.api_key")
    if body.api_key is None:
        api_key = stored_key
    else:
        api_key = resolve_secret(body.api_key, stored_key)
    return SimpleNamespace(url=url or "", api_key=api_key or "", model=model or "")


@router.get("/sample/embeddings")
async def sample_embeddings():
    """Return preprocessed sample A/B data URIs plus expect thresholds and steps."""
    a, b = await asyncio.to_thread(get_sample_inputs)
    return {
        "inputs": [a, b],
        "expect": {
            "same_min": SAME_MIN,
            "diff_max": DIFF_MAX,
            "dim_min": DIM_MIN,
            "dim_max": DIM_MAX,
        },
        "steps": list(_SAMPLE_STEPS),
    }


@router.post("/similar/test")
async def similar_test(body: SimilarTestRequest | None = None):
    """Run consistency test against stored or overridden endpoint settings.

    Does not write DB or config (CD-186-7; observation hook deferred to T4).
    """
    req = body or SimilarTestRequest()
    config = await asyncio.to_thread(load_config)
    cfg = _resolve_similar_cfg(req, config)
    result = await asyncio.to_thread(run_consistency_test, cfg)
    out: dict = {"ok": result.ok, "elapsed_ms": result.elapsed_ms}
    if result.kind is not None:
        out["kind"] = result.kind
    if result.check is not None:
        out["check"] = result.check
    if result.model is not None:
        out["model"] = result.model
    if result.dim is not None:
        out["dim"] = result.dim
    return out
