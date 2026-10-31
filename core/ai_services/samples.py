"""Consistency-test samples A/B and assertions (CD-186-7)."""

from __future__ import annotations

import base64
import io
import math
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw

from core.ai_services.embeddings import EmbedResult, EndpointError, embed
from core.ai_services.image_prep import cover_to_data_uri
from core.data_root import get_project_root

SAME_MIN = 0.99
DIFF_MAX = 0.9
DIM_MIN = 128
DIM_MAX = 4096

# Sample A: tracked demo cover (right-half via cover_to_data_uri).
_SAMPLE_A_REL = "web/static/img/demo/sone-103.jpg"

# Sample B: deterministic synthetic PNG — fixed size / bg / primitives, no RNG.
# kind: "rect"(x0,y0,x1,y1,rgb) | "ellipse"(…) | "polygon"(points, rgb)
B_SIZE = 448
B_BG = (32, 48, 160)
B_SHAPES: tuple = (
    ("rect", 36, 36, 200, 200, (220, 48, 48)),
    ("ellipse", 220, 180, 412, 412, (240, 220, 48)),
    ("polygon", ((224, 24), (400, 168), (48, 168)), (48, 200, 72)),
)
B_PNG_COMPRESS_LEVEL = 6

_cache_a: str | None = None
_cache_b: str | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    return math.sumprod(a, b)


def check_consistency(
    a1: EmbedResult, a2: EmbedResult, b: EmbedResult
) -> tuple[bool, str | None]:
    """Pure assertions over three embed results. Order fixed by CD-186-7."""
    if not (
        a1.dim == a2.dim == b.dim and DIM_MIN <= a1.dim <= DIM_MAX
    ):
        return False, "dim_mismatch"
    same = _cosine(a1.vector, a2.vector)
    if same < SAME_MIN:
        return False, "unstable"
    diff = _cosine(a1.vector, b.vector)
    if not (diff < DIFF_MAX):
        return False, "not_discriminative"
    if not (a1.model == a2.model == b.model):
        return False, "model_flapping"
    return True, None


def _render_sample_b_png_bytes() -> bytes:
    img = Image.new("RGB", (B_SIZE, B_SIZE), B_BG)
    draw = ImageDraw.Draw(img)
    for shape in B_SHAPES:
        kind = shape[0]
        if kind == "rect":
            _, x0, y0, x1, y1, fill = shape
            draw.rectangle((x0, y0, x1, y1), fill=fill)
        elif kind == "ellipse":
            _, x0, y0, x1, y1, fill = shape
            draw.ellipse((x0, y0, x1, y1), fill=fill)
        elif kind == "polygon":
            _, points, fill = shape
            draw.polygon(list(points), fill=fill)
        else:
            raise ValueError(f"unknown shape kind: {kind}")
    buf = io.BytesIO()
    # Fixed save params (DoD 5): no optimize, no pnginfo, fixed compress_level.
    img.save(
        buf,
        format="PNG",
        compress_level=B_PNG_COMPRESS_LEVEL,
        optimize=False,
    )
    return buf.getvalue()


def sample_b_data_uri() -> str:
    """Lazy module-level cache of synthetic sample B (PNG data URI)."""
    global _cache_b
    if _cache_b is None:
        raw = _render_sample_b_png_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        _cache_b = f"data:image/png;base64,{b64}"
    return _cache_b


def sample_a_data_uri() -> str:
    """Lazy module-level cache of sample A (demo cover → JPEG data URI)."""
    global _cache_a
    if _cache_a is None:
        path = get_project_root() / _SAMPLE_A_REL
        uri = cover_to_data_uri(str(path))
        if uri is None:
            raise FileNotFoundError(f"sample A unreadable: {path}")
        _cache_a = uri
    return _cache_a


def get_sample_inputs() -> tuple[str, str]:
    """Return cached (A, B) data URIs; builds on first call."""
    return sample_a_data_uri(), sample_b_data_uri()


@dataclass
class ConsistencyResult:
    ok: bool
    kind: str | None = None
    check: str | None = None
    model: str | None = None
    dim: int | None = None
    cos_same: float | None = None
    cos_diff: float | None = None
    elapsed_ms: int = 0


def run_consistency_test(cfg) -> ConsistencyResult:
    """A (first=True) → A → B; stop on first EndpointError."""
    t0 = time.perf_counter()
    try:
        a_uri, b_uri = get_sample_inputs()
        a1 = embed(cfg, a_uri, first=True)
        a2 = embed(cfg, a_uri, first=False)
        b = embed(cfg, b_uri, first=False)
    except EndpointError as e:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return ConsistencyResult(
            ok=False, kind=e.kind, check=e.check, elapsed_ms=elapsed
        )

    elapsed = int((time.perf_counter() - t0) * 1000)
    ok, failed = check_consistency(a1, a2, b)
    cos_same = cos_diff = None
    if a1.dim == a2.dim == b.dim:
        cos_same = _cosine(a1.vector, a2.vector)
        cos_diff = _cosine(a1.vector, b.vector)
    return ConsistencyResult(
        ok=ok,
        kind=None if ok else "contract",
        check=failed,
        model=a1.model,
        dim=a1.dim,
        cos_same=cos_same,
        cos_diff=cos_diff,
        elapsed_ms=elapsed,
    )
