"""女優臉部頭像的衍生快取；來源照片只供讀取。"""
import hashlib
import threading
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from core.actress_face import avatar_stamp
from core.atomic_write import atomic_write
from core.database import get_db_path
from core.focal.face_judge import crop_window, parse_face_box
from core.logger import get_logger

logger = get_logger(__name__)
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for_name(digest: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(digest)
        if lock is None:
            lock = threading.Lock()
            _locks[digest] = lock
        return lock


def _digest(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()


def _avatar_dir() -> Path:
    return get_db_path().parent / "actress_avatar"


def _remove_other_stamps(digest: str, keep: Optional[Path]) -> None:
    for old in (_avatar_dir() / digest[:2]).glob(f"{digest}-*.webp"):
        if old != keep:
            try:
                old.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("avatar cleanup failed: path=%s err=%s", old, exc)


def build(photo_path, face_box) -> bytes:
    """依轉正後的臉框裁切，回傳 WebP 位元組。"""
    box = parse_face_box(face_box)
    if box is None:
        raise ValueError("invalid face box")
    with Image.open(photo_path) as src:
        img = ImageOps.exif_transpose(src).convert("RGB")
        x0, y0, side = crop_window(img.width, img.height, *box)
        img = img.crop((x0, y0, x0 + side, y0 + side))
        out = min(128, side)
        if out != side:
            img = img.resize((out, out), Image.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, "WEBP", quality=85, method=4)
        return buffer.getvalue()


def get_or_create(actress, photo_path) -> Optional[Path]:
    """回傳快取頭像；產生或寫入失敗時回 None。"""
    try:
        digest = _digest(actress.name)
        with _lock_for_name(digest):
            dst = _avatar_dir() / digest[:2] / f"{digest}-{avatar_stamp(actress)}.webp"
            if dst.exists():
                return dst
            data = build(photo_path, actress.face_box)
            dst.parent.mkdir(parents=True, exist_ok=True)
            with atomic_write(dst) as f:
                f.write(data)
            _remove_other_stamps(digest, dst)
            return dst
    except Exception as exc:
        logger.warning("avatar generate failed: photo=%s err=%s", photo_path, exc)
        return None


def invalidate(name) -> None:
    """刪除同名女優的所有頭像。"""
    digest = _digest(name)
    with _lock_for_name(digest):
        _remove_other_stamps(digest, None)
