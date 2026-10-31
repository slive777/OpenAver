"""Cover image → data URI prep for embeddings (CD-186-10) and faces (CD-187a-5)."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

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
