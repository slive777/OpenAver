"""External faces detection entry (CD-187a-1 / -4 / -6 / -15).

Never raises: unexpected errors log and return ``None`` (local path takes over).
``None`` also means external not applicable (disabled / unreadable cover).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import NamedTuple, Optional

from core.ai_services import faces, faces_state
from core.ai_services.embeddings import EndpointError
from core.ai_services.faces_config import active_in
from core.ai_services.image_prep import cover_to_faces_data_uri
from core.config import load_config
from core.focal.detector import select_focal_from_boxes
from core.logger import get_logger

logger = get_logger(__name__)


class ExternalResult(NamedTuple):
    """External detect outcome. ``None`` from ``detect`` means not applicable."""

    kind: str  # "FOUND" | "NO_FACE" | "FAILED"
    focal: Optional[tuple[float, float]] = None
    model: Optional[str] = None
    failure: Optional[str] = None


def observe_model(model: str) -> None:
    """T4 recompute hook; no-op until faces_recompute lands."""
    return


def _faces_cfg_object(cfg: dict) -> SimpleNamespace:
    faces_cfg = (cfg.get("ai_services") or {}).get("faces") or {}
    return SimpleNamespace(
        url=(faces_cfg.get("url") or ""),
        api_key=(faces_cfg.get("api_key") or ""),
    )


def _prepare(fs_path: str) -> tuple[dict, str, tuple[int, int]] | None:
    """Config + preprocess. ``None`` = external not applicable."""
    cfg = load_config()
    if not active_in(cfg):
        return None
    prepared = cover_to_faces_data_uri(fs_path)
    if prepared is None:
        return None
    uri, size = prepared
    return cfg, uri, size


def _failure_label(err: EndpointError) -> str:
    if err.kind == "unreachable" and err.check == "timeout":
        return "external_timeout"
    if err.kind == "unreachable":
        return "external_unreachable"
    return "external_contract"


def _ask_endpoint(
    cfg: dict, uri: str, profile: str
) -> tuple[object, None] | tuple[None, EndpointError]:
    """Call ``faces.detect``; return ``(FacesResult, None)`` or ``(None, EndpointError)``."""
    try:
        result = faces.detect(_faces_cfg_object(cfg), uri, profile=profile)
        return result, None
    except EndpointError as e:
        return None, e


def _to_external_result(
    faces_result, work_w: int, work_h: int, ratio: float, profile: str
) -> ExternalResult:
    """Map boxes → FOUND/NO_FACE and update faces_state on the success path."""
    focal = select_focal_from_boxes(faces_result.boxes, work_w, work_h, ratio)
    model = faces_result.model
    if focal is None:
        kind = "NO_FACE"
        out = ExternalResult(kind=kind, focal=None, model=model, failure=None)
    else:
        kind = "FOUND"
        out = ExternalResult(kind=kind, focal=focal, model=model, failure=None)
    if profile != "warmup":
        faces_state.observe_success(model)
        observe_model(model)
    return out


def _record_endpoint_error(
    err: EndpointError, profile: str, *, notify: bool
) -> ExternalResult:
    faces_state.observe_failure(err.kind, err.check)
    if notify and profile == "background" and faces_state.note_failure():
        faces_state.emit_unreachable()
    return ExternalResult(
        kind="FAILED",
        focal=None,
        model=None,
        failure=_failure_label(err),
    )


def detect(
    fs_path: str,
    ratio: float,
    profile: str = "background",
    *,
    notify: bool = True,
) -> ExternalResult | None:
    """Ask the faces endpoint for a cover. Never raises.

    Returns ``None`` when external is off or the cover cannot be read.
    ``notify=False`` skips sidebar emit on failure (recompute path, CD-187a-15).
    """
    try:
        prepared = _prepare(fs_path)
        if prepared is None:
            return None
        cfg, uri, size = prepared
        work_w, work_h = size
        faces_result, err = _ask_endpoint(cfg, uri, profile)
        if err is not None:
            return _record_endpoint_error(err, profile, notify=notify)
        return _to_external_result(faces_result, work_w, work_h, ratio, profile)
    except Exception:
        logger.exception("[faces_detect] unexpected error; falling back to local")
        return None


def detect_focal_only(
    fs_path: str, ratio: float, profile: str = "sync"
) -> tuple[float, float] | None:
    """Convenience for callers that only need a focal point (T6)."""
    result = detect(fs_path, ratio, profile=profile)
    if result is None or result.kind != "FOUND" or result.focal is None:
        return None
    return result.focal
