"""AI services endpoints for embeddings samples and consistency test (186-T3 / 187-T1).

- GET  /api/ai/sample/embeddings
- POST /api/ai/similar/test
- GET  /api/ai/similar/status      (186-T4b)
- POST /api/ai/similar/index       (186-T4b)
- POST /api/ai/similar/index/stop  (186-T4b)
- GET  /api/ai/sample/faces        (187-T1)
- POST /api/ai/faces/test          (187-T1)
- GET  /api/ai/faces/status        (187a-T4b)
- POST /api/ai/faces/recompute     (187a-T4b, resume)
- POST /api/ai/faces/recompute/stop
- POST /api/ai/faces/rebuild
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter
from pydantic import BaseModel

from core.ai_services import faces_recompute, faces_state, similar_index, similar_state
from core.ai_services.samples import (
    DIFF_MAX,
    DIM_MAX,
    DIM_MIN,
    FACES_EXPECT_CENTER,
    FACES_MIN_FACES,
    FACES_TOLERANCE,
    SAME_MIN,
    get_faces_sample_input,
    get_sample_inputs,
    run_consistency_test,
    run_faces_test,
)
from core.ai_services.faces_config import active_in
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

_FACES_SAMPLE_STEPS = [
    "POST {base}/v1/faces with inputs[0] (allow cold-start; first call may be slow).",
    "Response faces is an array; highest-score box center within expect.tolerance of expect.center per axis.",
    "Response model is a non-empty string.",
]


class SimilarTestRequest(BaseModel):
    """Optional overrides. Absent (None) → stored config; present → use given value."""

    url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class FacesTestRequest(BaseModel):
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


def _resolve_faces_cfg(body: FacesTestRequest, config: dict) -> SimpleNamespace:
    stored = (config.get("ai_services") or {}).get("faces") or {}
    url = stored.get("url", "") if body.url is None else body.url
    model = stored.get("model", "") if body.model is None else body.model
    stored_key = read_secret(config, "ai_services.faces.api_key")
    if body.api_key is None:
        api_key = stored_key
    else:
        api_key = resolve_secret(body.api_key, stored_key)
    return SimpleNamespace(url=url or "", api_key=api_key or "", model=model or "")

def _norm_url(url: str) -> str:
    """比對用正規化：去空白、scheme／host 小寫、去尾端 ``/``（path 大小寫保留）。"""
    parts = urlsplit((url or "").strip())
    return parts._replace(
        scheme=parts.scheme.lower(), netloc=parts.netloc.lower(), path=parts.path.rstrip("/")
    ).geturl()


def _is_stored_target(cfg: SimpleNamespace, config: dict) -> bool:
    """受測的 url＋model 是否等於已存設定（body 缺席的欄位即用已存值，故視為相同）。"""
    stored = (config.get("ai_services") or {}).get("image_similar") or {}
    return (
        _norm_url(cfg.url) == _norm_url(stored.get("url", "") or "")
        and (cfg.model or "").strip() == (stored.get("model", "") or "").strip()
    )


def _observe_test_result(result) -> None:
    """測試結果 → 記憶體觀察值（不寫 DB／設定）。成功記模型並解除 unreachable；失敗記 kind／check。"""
    if result.ok and result.model is not None and result.dim is not None:
        similar_state.observe_success(result.model, result.dim)
    elif not result.ok:
        similar_state.observe_failure(result.kind, result.check)


def _is_stored_faces_target(cfg: SimpleNamespace, config: dict) -> bool:
    """受測 url＋model 是否等於已存人臉設定（api_key 不比；body 缺席即用已存值）。"""
    stored = (config.get("ai_services") or {}).get("faces") or {}
    return (
        _norm_url(cfg.url) == _norm_url(stored.get("url", "") or "")
        and (cfg.model or "").strip() == (stored.get("model", "") or "").strip()
    )


def _observe_faces_test_result(result) -> None:
    """記憶體觀察值（不寫 DB／設定、不觸發重算）。成功清 degraded／通知旗標。"""
    if result.ok and result.model:
        faces_state.observe_success(result.model)
    elif not result.ok:
        faces_state.observe_failure(result.kind, result.check)


def _faces_status() -> dict:
    """純讀：DB＋記憶體＋app_meta，不打端點。"""
    config = load_config()
    out = faces_recompute.status()
    snap = faces_state.snapshot()
    active = active_in(config)
    last = snap["last_success_at"]
    if last is None:
        raw = faces_state.meta_get(faces_state.META_LAST_SUCCESS)
        try:
            last = float(raw) if raw else None
        except ValueError:
            last = None
    degraded = bool(snap["degraded"])
    out["using"] = "external" if (active and not degraded) else "local"
    out["observed"] = snap["observed_model"] is not None or last is not None
    out["last_success_at"] = last
    if active and degraded:
        out["degraded"] = True
        out["degraded_kind"] = snap["kind"]
        out["degraded_check"] = snap["check"]
    return out


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

    Does not write DB or config (CD-186-7). Only when the tested url+model equal
    the stored settings does the result update the in-memory observation (CD-186-11).
    """
    req = body or SimilarTestRequest()
    config = await asyncio.to_thread(load_config)
    cfg = _resolve_similar_cfg(req, config)
    result = await asyncio.to_thread(run_consistency_test, cfg)
    if _is_stored_target(cfg, config):
        await asyncio.to_thread(_observe_test_result, result)
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


@router.get("/similar/status")
async def similar_status():
    """索引進度與狀態（讀 DB＋記憶體觀察值）。"""
    return await asyncio.to_thread(similar_index.status)


@router.post("/similar/index")
async def similar_index_start():
    """建立／繼續／重建索引；內含一致性測試（可達 90 秒以上），業務失敗在 body、HTTP 200。"""
    return await asyncio.to_thread(similar_index.start_build)


@router.post("/similar/index/rebuild")
async def similar_index_rebuild():
    """刪除並重建索引：先跑一致性測試（可達 90 秒以上），沒過什麼都不刪；業務失敗在 body、HTTP 200。"""
    return await asyncio.to_thread(similar_index.start_rebuild)


@router.post("/similar/index/stop")
async def similar_index_stop():
    """停止索引工作（閒置時為 no-op）。"""
    return await asyncio.to_thread(similar_index.request_stop)


@router.get("/sample/faces")
async def sample_faces():
    """Return preprocessed faces sample data URI plus expect thresholds and steps."""
    uri = await asyncio.to_thread(get_faces_sample_input)
    return {
        "inputs": [uri],
        "expect": {
            "center": list(FACES_EXPECT_CENTER),
            "tolerance": FACES_TOLERANCE,
            "min_faces": FACES_MIN_FACES,
        },
        "steps": list(_FACES_SAMPLE_STEPS),
    }


@router.post("/faces/test")
async def faces_test(body: FacesTestRequest | None = None):
    """Run faces consistency test against stored or overridden endpoint settings.

    Does not write DB or config (CD-187a-19). Only when url+model equal the stored settings
    does the result update the in-memory observation; never triggers a recompute (NC-4).
    """
    req = body or FacesTestRequest()
    config = await asyncio.to_thread(load_config)
    cfg = _resolve_faces_cfg(req, config)
    result = await asyncio.to_thread(run_faces_test, cfg)
    if _is_stored_faces_target(cfg, config):
        await asyncio.to_thread(_observe_faces_test_result, result)
    out: dict = {"ok": result.ok, "elapsed_ms": result.elapsed_ms}
    if result.kind is not None:
        out["kind"] = result.kind
    if result.check is not None:
        out["check"] = result.check
    if result.model is not None:
        out["model"] = result.model
    return out


@router.get("/faces/status")
async def faces_status():
    """重新對焦進度＋端點使用狀態（純讀，不打端點）。"""
    return await asyncio.to_thread(_faces_status)


@router.post("/faces/recompute")
async def faces_recompute_resume():
    """繼續未完成的重新對焦（不重算已算的）。"""
    return await asyncio.to_thread(faces_recompute.resume)


@router.post("/faces/recompute/stop")
async def faces_recompute_stop():
    """停止重新對焦（閒置時為 no-op）。"""
    return await asyncio.to_thread(faces_recompute.request_stop)


@router.post("/faces/rebuild")
async def faces_rebuild():
    """刪除並重新對焦：先跑一致性測試，沒過什麼都不刪；業務失敗在 body、HTTP 200。"""
    return await asyncio.to_thread(faces_recompute.start_rebuild)
