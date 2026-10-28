"""cover_upload.py — 空白卡封面上傳的暫存模組（TASK-183-T5a / CD-183-7）。

流程：upload 端點 → validate_and_normalize_cover（驗證＋正規化成 JPEG）→ store_cover
（寫進資料根 tmp/cover-upload/<token>.jpg，回 token）→ scrape-single 憑 token
resolve_cover_token 取得伺服器端路徑 → 整理成功後 discard_cover_token。

純函式、無 class、不 import web。信任邊界：token 是 client 字串，只有 `_token_path`
會把它轉成路徑，且第一步就用 fullmatch 驗格式；絕不把 client 字串拼進路徑。
"""
import re
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from core.atomic_write import atomic_write
from core.data_root import get_data_root
from core.logger import get_logger

logger = get_logger(__name__)

# 同 web/routers/actress.py 上傳常數（不 import actress.py，router 層模組）
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000
ERR_TOO_LARGE = "圖片太大（檔案上限 10MB、尺寸上限 50M 像素）"
ERR_UNSUPPORTED_FORMAT = "不支援的圖片格式"

_TOKEN_RE = re.compile(r"[0-9a-f]{32}")
_TTL_SECONDS = 24 * 3600
_JPEG_QUALITY = 95


def validate_and_normalize_cover(data: bytes) -> Tuple[Optional[bytes], Optional[Tuple[int, str]]]:
    """像素上限＋真實格式驗證，並正規化成 JPEG。同步（PIL），呼叫端須經 to_thread。

    Returns:
        (jpeg_bytes, None) 或 (None, (status, message))。訊息固定中文，不含 str(e)。
    """
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size  # header-only，不解碼像素
        if w * h > MAX_PIXELS:
            return None, (413, ERR_TOO_LARGE)
        img.verify()
        fmt = img.format
        if fmt not in ("JPEG", "PNG", "WEBP", "GIF"):
            return None, (415, ERR_UNSUPPORTED_FORMAT)
        if fmt == "JPEG":
            return data, None
        # verify() 之後 Image 物件不可再用，必須重新 open 才能 convert
        out = BytesIO()
        Image.open(BytesIO(data)).convert("RGB").save(out, format="JPEG", quality=_JPEG_QUALITY)
        return out.getvalue(), None
    except Exception:
        logger.warning("[cover_upload] 圖片驗證失敗（回 415）", exc_info=True)
        return None, (415, ERR_UNSUPPORTED_FORMAT)


def _upload_dir() -> Path:
    """暫存目錄；只組路徑，不建目錄（store_cover 才延遲建立）。"""
    return get_data_root() / "tmp" / "cover-upload"


def _token_path(token) -> Optional[Path]:
    """token → 暫存檔路徑；本模組唯一把 token 轉成路徑的地方。格式不合回 None。"""
    if not isinstance(token, str) or _TOKEN_RE.fullmatch(token) is None:
        return None
    return _upload_dir() / f"{token}.jpg"


def store_cover(jpeg_bytes: bytes) -> str:
    """把已正規化的 JPEG 位元組原子寫進暫存目錄，回 token（32 hex）。"""
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    with atomic_write(upload_dir / f"{token}.jpg", suffix=".tmp") as f:
        f.write(jpeg_bytes)
    return token


def resolve_cover_token(token) -> Optional[str]:
    """token 有效（格式合法、檔存在、未逾 TTL）回伺服器端路徑字串，否則 None。"""
    path = _token_path(token)
    if path is None:
        return None
    try:
        if time.time() - path.stat().st_mtime > _TTL_SECONDS:
            return None
    except OSError:
        return None
    return str(path)


def discard_cover_token(token) -> None:
    """best-effort 刪暫存檔；失敗只 log。"""
    path = _token_path(token)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("[cover_upload] 刪除暫存封面失敗 %s", path, exc_info=True)


def sweep_expired_covers() -> None:
    """best-effort 清掉逾期的 <32hex>.jpg 與殘留 *.tmp；任何 OSError 只 log。"""
    upload_dir = _upload_dir()
    now = time.time()
    try:
        entries = list(upload_dir.iterdir()) if upload_dir.is_dir() else []
    except OSError:
        logger.warning("[cover_upload] 讀取暫存目錄失敗", exc_info=True)
        return
    for p in entries:
        is_cover = p.suffix == ".jpg" and _TOKEN_RE.fullmatch(p.stem) is not None
        if not (is_cover or p.suffix == ".tmp"):
            continue
        try:
            if now - p.stat().st_mtime > _TTL_SECONDS:
                p.unlink(missing_ok=True)
        except OSError:
            logger.warning("[cover_upload] 清除逾期暫存失敗 %s", p, exc_info=True)
