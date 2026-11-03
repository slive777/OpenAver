"""Cover image → data URI prep for embeddings (CD-186-10) and faces (CD-187a-5)."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

from core.focal.detector import parse_focal
from core.logger import get_logger

logger = get_logger(__name__)

EMBED_MAX_EDGE = 448
FACES_MAX_EDGE = 650


def _encode_jpeg_data_uri(im: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def cover_to_data_uri(fs_path: str) -> str | None:
    """Right-half crop, long edge ≤448, JPEG q=90 → data URI.

    Unreadable path / non-image → ``None`` (never raises).
    """
    if not fs_path:
        return None
    try:
        with Image.open(fs_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w <= 0 or h <= 0:
                return None
            # x ∈ [50%, 100%], full height
            left = w // 2
            im = im.crop((left, 0, w, h))
            cw, ch = im.size
            long_edge = max(cw, ch)
            if long_edge > EMBED_MAX_EDGE:
                scale = EMBED_MAX_EDGE / float(long_edge)
                nw = max(1, int(round(cw * scale)))
                nh = max(1, int(round(ch * scale)))
                im = im.resize((nw, nh), Image.Resampling.LANCZOS)
            return _encode_jpeg_data_uri(im, 90)
    except Exception:
        return None


def cover_to_faces_data_uri(fs_path: str) -> tuple[str, tuple[int, int]] | None:
    """Full frame, EXIF-transpose, long edge ≤650, JPEG q=90 → data URI + size.

    Unreadable path / non-image → ``None`` (never raises).
    """
    if not fs_path:
        return None
    try:
        with Image.open(fs_path) as im:
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            w, h = im.size
            if w <= 0 or h <= 0:
                return None
            long_edge = max(w, h)
            if long_edge > FACES_MAX_EDGE:
                scale = FACES_MAX_EDGE / float(long_edge)
                nw = max(1, int(round(w * scale)))
                nh = max(1, int(round(h * scale)))
                im = im.resize((nw, nh), Image.Resampling.LANCZOS)
            size = im.size
            uri = _encode_jpeg_data_uri(im, 90)
    except Exception:
        return None
    return uri, size


def read_exif_orientation(fs_path: str) -> int:
    """EXIF Orientation (1-8) of the file; unreadable / absent / out of range → 1."""
    try:
        with Image.open(fs_path) as im:
            value = int(im.getexif().get(0x0112, 1))
    except Exception:
        return 1
    return value if 1 <= value <= 8 else 1


def upright_focal_to_raw(
    focal: tuple[float, float], orientation: int
) -> tuple[float, float]:
    """Normalized point on the EXIF-upright image → normalized point on the raw pixels.

    The faces endpoint sees the transposed image (``cover_to_faces_data_uri``), so its
    coordinates are upright; ``crop_to_poster`` crops raw pixels. Inverse of PIL's
    ``ImageOps.exif_transpose`` for Orientation 1-8 (unknown → identity).
    """
    u, v = focal
    if orientation == 2:
        return (1 - u, v)
    if orientation == 3:
        return (1 - u, 1 - v)
    if orientation == 4:
        return (u, 1 - v)
    if orientation == 5:
        return (v, u)
    if orientation == 6:
        return (v, 1 - u)
    if orientation == 7:
        return (1 - v, 1 - u)
    if orientation == 8:
        return (1 - v, u)
    return (u, v)


POSTER_CROP_RATIO = 0.71   # 與 theme.css --poster-crop-ratio 同值（測試從 CSS 檔對帳）
FOCAL_X_DEADZONE = 0.62    # 同 web/static/js/shared/focal.js
TAGS_MAX_EDGE = 800


def _usable_focal(crop_mode, auto_focal):
    if crop_mode not in ("manual", "auto"):
        return None
    focal = parse_focal(auto_focal)
    if focal is None:
        return None
    if crop_mode == "auto" and focal[0] >= FOCAL_X_DEADZONE:
        return None
    return focal


def poster_crop_box(w, h, crop_mode, auto_focal):
    win_w = round(POSTER_CROP_RATIO * h)
    if w <= win_w:  # 直式：全寬、上下置中；y0 夾到 >=0
        y0 = max(round((h - w / POSTER_CROP_RATIO) / 2), 0)
        return (0, y0, w, h - y0)
    x0 = w - win_w
    focal = _usable_focal(crop_mode, auto_focal)
    if focal is not None:
        x0 = max(min(int(w * focal[0]) - win_w // 2, w - win_w), 0)
    return (x0, 0, x0 + win_w, h)


def poster_to_jpeg_bytes(fs_path, crop_mode, auto_focal):
    if not fs_path:
        return None
    try:
        with Image.open(fs_path) as im:
            upright = ImageOps.exif_transpose(im)
            upright = upright.convert("RGB")
            w, h = upright.size
            if w <= 0 or h <= 0:
                return None
            box = poster_crop_box(w, h, crop_mode, auto_focal)
            x0, y0, x1, y1 = box
            if x1 <= x0 or y1 <= y0:
                return None
            cropped = upright.crop(box)
            cw, ch = cropped.size
            long_edge = max(cw, ch)
            if long_edge > TAGS_MAX_EDGE:
                scale = TAGS_MAX_EDGE / float(long_edge)
                nw = max(1, int(round(cw * scale)))
                nh = max(1, int(round(ch * scale)))
                cropped = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("poster_to_jpeg_bytes failed for %s: %s", fs_path, e)
        return None


def poster_to_data_uri(fs_path, crop_mode="default", auto_focal=""):
    jpeg = poster_to_jpeg_bytes(fs_path, crop_mode, auto_focal)
    if jpeg is None:
        return None
    b64 = base64.b64encode(jpeg).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

