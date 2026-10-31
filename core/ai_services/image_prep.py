"""Cover image → data URI prep for embeddings (CD-186-10)."""

from __future__ import annotations

import base64
import io

from PIL import Image

EMBED_MAX_EDGE = 448


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
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
    except Exception:
        return None
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
