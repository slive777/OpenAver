"""
actress_photo.py — 女優照片下載 / 儲存 / 讀取 / 刪除 / 影片封面 crop
"""
import io
import requests
from pathlib import Path
from typing import Optional

from core.logger import get_logger
from core.organizer import sanitize_filename

logger = get_logger(__name__)

# 照片存放目錄
GFRIENDS_DIR: Path = Path(__file__).parent.parent / "output" / "Gfriends"

# HTTP 請求基本 headers
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Content-Type → 副檔名對應表
CONTENT_TYPE_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/png": ".png",
    "image/gif": ".gif",
}

# photo_source → Referer 對應表
REFERER_MAP: dict[str, str] = {
    "graphis": "https://www.graphis.ne.jp/",
    "gfriends": "https://github.com/gfriends/gfriends",
    "wiki": "https://ja.wikipedia.org/",
    "minnano": "https://www.minnano-av.com/",
}


def download_actress_photo(name: str, photo_url: str, photo_source: str) -> bool:
    """
    下載女優照片並儲存到 GFRIENDS_DIR。

    Args:
        name: 女優姓名（會經 sanitize_filename 處理）
        photo_url: 照片 URL
        photo_source: 來源識別碼，用於設定 Referer header

    Returns:
        True 表示成功，False 表示任何失敗
    """
    if not photo_url:
        return False

    GFRIENDS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(name)

    # 刪除同名的舊檔（副檔名可能不同）
    for old_file in GFRIENDS_DIR.glob(f"{safe_name}.*"):
        try:
            old_file.unlink()
        except Exception as e:
            logger.warning(f"[actress_photo] 刪除舊檔失敗 {old_file}: {e}")

    try:
        headers = _HEADERS.copy()
        referer = REFERER_MAP.get(photo_source, "")
        if referer:
            headers["Referer"] = referer

        resp = requests.get(photo_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            logger.warning(
                f"[actress_photo] 下載失敗，HTTP {resp.status_code}：{photo_url}"
            )
            return False

        # 推斷副檔名
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        ext = CONTENT_TYPE_MAP.get(content_type)
        if not ext:
            # fallback：從 URL 路徑最後一段取副檔名
            url_path = photo_url.split("?")[0]
            suffix = Path(url_path).suffix.lower()
            ext = suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
        if ext == ".jpeg":
            ext = ".jpg"

        save_path = GFRIENDS_DIR / f"{safe_name}{ext}"
        save_path.write_bytes(resp.content)
        logger.info(f"[actress_photo] 下載完成：{save_path}")
        return True

    except Exception as e:
        logger.warning(f"[actress_photo] 下載例外 ({name}): {e}")
        return False


def get_local_photo_path(name: str) -> Optional[Path]:
    """
    取得女優本地照片路徑。

    Returns:
        找到回 Path，不存在回 None
    """
    safe_name = sanitize_filename(name)
    matches = list(GFRIENDS_DIR.glob(f"{safe_name}.*"))
    return matches[0] if matches else None


def delete_local_photo(name: str) -> bool:
    """
    刪除女優的本地照片（idempotent）。

    Returns:
        True（含無檔案可刪），exception 時回 False
    """
    try:
        safe_name = sanitize_filename(name)
        for file in GFRIENDS_DIR.glob(f"{safe_name}.*"):
            file.unlink()
        return True
    except Exception as e:
        logger.warning(f"[actress_photo] 刪除失敗 ({name}): {e}")
        return False


# ---------------------------------------------------------------------------
# 影片封面 Crop cache（進程生命期 in-memory cache）
# key = (cover_path_str, crop_spec_str) → bytes
# ---------------------------------------------------------------------------

_CROP_CACHE: dict = {}


def crop_video_cover(cover_path: str, crop_spec: str = "v1") -> Optional[bytes]:
    """
    從影片封面圖裁切出女優人像，回傳 JPEG bytes。

    spec v1 裁切規格：
        x: 右半部（50% ~ 100%）
        y: 上 80%（0% ~ 80%）
        → 在右半 x 上 80% 區域取中央 3:4 portrait（width:height = 3:4）
        → 輸出 JPEG quality 85

    Args:
        cover_path: 本機 FS 路徑（非 URI）
        crop_spec: 裁切規格版本，目前只支援 "v1"

    Returns:
        JPEG bytes，失敗回 None（不 raise）
    """
    cache_key = (cover_path, crop_spec)
    if cache_key in _CROP_CACHE:
        return _CROP_CACHE[cache_key]

    try:
        from PIL import Image
    except ImportError:
        logger.warning("[actress_photo] PIL/Pillow 未安裝，無法 crop 影片封面")
        return None

    try:
        img = Image.open(cover_path)
        img_w, img_h = img.size

        if crop_spec == "v1":
            # 右半 50%~100% x，上 0%~80% y
            region_x0 = int(img_w * 0.5)
            region_y0 = 0
            region_x1 = img_w
            region_y1 = int(img_h * 0.8)

            region_w = region_x1 - region_x0
            region_h = region_y1 - region_y0

            # 在此 region 內取最大 3:4 portrait，置中
            # 3:4 → target_w / target_h = 3 / 4
            # 以 region 為限：
            #   target_w = min(region_w, region_h * 3 / 4)
            #   target_h = target_w * 4 / 3
            target_w = min(region_w, int(region_h * 3 / 4))
            target_h = int(target_w * 4 / 3)

            # 置中計算 offset
            cx = region_x0 + (region_w - target_w) // 2
            cy = region_y0 + (region_h - target_h) // 2

            crop_box = (cx, cy, cx + target_w, cy + target_h)
            cropped = img.crop(crop_box)
        else:
            # 未知 spec：回 None
            logger.warning("[actress_photo] 未知 crop_spec: %s", crop_spec)
            return None

        buf = io.BytesIO()
        cropped.convert("RGB").save(buf, format="JPEG", quality=85)
        result = buf.getvalue()
        _CROP_CACHE[cache_key] = result
        return result

    except Exception as e:
        logger.warning("[actress_photo] crop_video_cover 失敗 (%s): %s", cover_path, e)
        return None
