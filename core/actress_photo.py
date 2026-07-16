"""
actress_photo.py — 女優照片下載 / 儲存 / 讀取 / 刪除 / 影片封面 crop
"""
import io
import os
import threading
import requests
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from collections import OrderedDict

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

# photo_source → 允許的 host 白名單
PHOTO_HOST_WHITELIST: dict[str, set] = {
    "graphis": {
        "www.graphis.ne.jp",
        "graphis.ne.jp",
        "data.graphis.ne.jp",
    },
    "gfriends": {
        "cdn.jsdelivr.net",
        "raw.githubusercontent.com",
        "github.com",
    },
    "wiki": {
        "upload.wikimedia.org",
        "ja.wikipedia.org",
    },
    "minnano": {
        "www.minnano-av.com",
        "minnano-av.com",
    },
}


def validate_photo_url(photo_url: str, photo_source: str) -> bool:
    """
    驗證 photo_url 是否符合來源白名單（SSRF 防禦）。
    scheme 必須是 http/https，host 必須在對應 source 的白名單內。

    公開（原為 `_validate_photo_url`，TASK-100a Codex P2 改公開）：純函式、零
    side effect、不做任何 I/O，故 `set_actress_photo` 路由可以在 CD-4 清焦點
    **之前**先呼叫它擋掉注定失敗的請求——不清白清（見該處註解）。
    """
    try:
        parsed = urlparse(photo_url)
    except Exception as e:
        logger.debug("[actress_photo] urlparse 失敗 url=%s err=%s", photo_url, e)
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    allowed = PHOTO_HOST_WHITELIST.get(photo_source, set())
    return parsed.hostname in allowed


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

    if not validate_photo_url(photo_url, photo_source):
        logger.warning("[actress_photo] URL 不在白名單 source=%s url=%s", photo_source, photo_url)
        return False

    safe_name = sanitize_filename(name)
    GFRIENDS_DIR.mkdir(parents=True, exist_ok=True)

    # 推斷初始副檔名（從 URL fallback，download 後再依 Content-Type 修正）
    url_path = photo_url.split("?")[0]
    url_suffix = Path(url_path).suffix.lower()
    ext = url_suffix if url_suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
    if ext == ".jpeg":
        ext = ".jpg"

    final_path = GFRIENDS_DIR / f"{safe_name}{ext}"
    tmp_path = GFRIENDS_DIR / f".{safe_name}{ext}.download.tmp"

    try:
        headers = _HEADERS.copy()
        referer = REFERER_MAP.get(photo_source, "")
        if referer:
            headers["Referer"] = referer

        # 1. 下載到 tmp
        resp = requests.get(photo_url, headers=headers, timeout=15)

        if resp.status_code != 200:
            logger.warning("[actress_photo] 下載失敗，HTTP %s：%s", resp.status_code, photo_url)
            return False

        # 2. 依 Content-Type 確定副檔名
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            logger.warning("[actress_photo] 非圖片 Content-Type=%s", content_type)
            return False
        ct_ext = CONTENT_TYPE_MAP.get(content_type)
        if ct_ext:
            ext = ct_ext
            if ext == ".jpeg":
                ext = ".jpg"
            final_path = GFRIENDS_DIR / f"{safe_name}{ext}"

        # 3. 寫入 tmp
        tmp_path = GFRIENDS_DIR / f".{safe_name}{ext}.download.tmp"
        tmp_path.write_bytes(resp.content)

        # 4. atomic replace（先安裝新圖）
        os.replace(tmp_path, final_path)

        # 5. 🔴 replace 成功「之後」才刪其他副檔名的舊檔（final_path 除外）。
        # 順序是承重的（spec-100 §3.3 + Codex P1）：原本是「先刪舊檔 → os.replace」，
        # 若 replace 拋例外，舊檔已經沒了、finally 又清掉 tmp → **新舊照片全部消失**，
        # 違反 §3.3 失敗矩陣「寫檔失敗仍保留舊圖、最壞只退回置中裁」的硬保證。
        # 這不是理論上的極端 case：Windows 上防毒即時掃描／檔案總管縮圖快取持有
        # final_path 的 handle 就會讓 os.replace 拋 PermissionError，而 Windows 桌面
        # 版正是本專案的主力使用族群。
        # 同型 bug 已於 TASK-100a-T2 在 web/routers/actress.py 的 _write_actress_photo
        # 修掉（見該處 :538-547 註解），此處是被漏掉的雙胞胎。
        # 成功路徑行為不變（最終同樣只留 final_path 一個檔），兩個 caller
        # （add_favorite / set_actress_photo）皆不受影響。
        for old in GFRIENDS_DIR.glob(f"{safe_name}.*"):
            if old == final_path:
                continue
            try:
                old.unlink()
            except Exception as e:
                logger.warning(
                    "[actress_photo] 刪除舊檔失敗 path=%s err=%s",
                    old, e,
                )

        logger.info("[actress_photo] 下載完成：%s", final_path)
        return True

    except Exception as e:
        logger.warning("[actress_photo] 下載例外 (%s): %s", name, e)
        return False
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception as e:
            logger.debug(
                "[actress_photo] tmp 清理失敗 path=%s err=%s",
                tmp_path, e,
            )


def get_local_photo_path(name: str) -> Optional[Path]:
    """
    取得女優本地照片路徑。

    正常情況 `{safe}.*` 只會有一個檔（寫入端 os.replace 後即清掉其他副檔名的殘檔）。
    但清舊檔可能失敗（Windows 縮圖快取／防毒鎖住舊檔 → PermissionError → 寫入端
    warn-and-continue，見 :166-175 與 web/routers/actress.py 的 _write_actress_photo）
    ⇒ 目錄同時存在新舊兩個 `{safe}.*`。

    🔴 PR#108 Codex 三審 P2：此時**不可**回 `matches[0]`。`Path.glob` 不排序、回的是
    `os.scandir` 順序，而 NTFS 目錄項是名稱序 B-tree ⇒ Windows 上必為字母序
    （`.gif` < `.jpg` < `.png` < `.webp`）。實測：上傳 PNG 蓋住被鎖的舊 `.jpg`，
    NTFS 20/20 全部解析到**舊 .jpg**（ext4 為 name-hash 序、約 10/20，這正是本 bug
    在 dev/CI 上不會現形的原因）。後果不是暫時性 glitch：回應 URL 是 name-based
    （`/photo/{name}?v=...`，不帶路徑）⇒ 每次 GET 都重新 glob ⇒ 舊圖 bytes 被貼上
    新圖的 `?v=` 指紋讓瀏覽器長期快取，且 detect_focal 會對著舊圖跑偵測。

    取 mtime 最新者＝剛 os.replace 落地的那個（os.replace 保留 temp 檔的 inode 與
    mtime，故新檔的 mtime 必為較新）。次鍵 `p.name` 只讓平手時的結果**確定**（不是
    「解對」——平手時挑的是字母序較後者，仍可能挑到舊檔）；實務上殘檔比新檔老數秒
    到數天，平手在本 bug 情境幾乎不可能（FAT32/exFAT 2s 粒度才有現實機會）。
    單檔（正常路徑）走 fast-path，零 stat 成本、行為與舊版 `matches[0]` 完全一致。

    Returns:
        找到回 Path，不存在回 None
    """
    safe_name = sanitize_filename(name)
    matches = list(GFRIENDS_DIR.glob(f"{safe_name}.*"))
    if len(matches) <= 1:
        return matches[0] if matches else None

    def _freshness(p: Path):
        # 殘檔可能在 glob 與 stat 之間被清掉（良性 TOCTOU）：排到最後，不讓它贏。
        # -inf 而非 -1：st_mtime_ns 對 1970 前的檔案是負值，用 -1 會讓真實檔輸給幽靈檔
        try:
            return (p.stat().st_mtime_ns, p.name)
        except OSError:
            return (float("-inf"), p.name)

    return max(matches, key=_freshness)


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
# 影片封面 Crop cache（進程生命期 in-memory LRU cache）
# key = (cover_path_str, mtime_float, crop_spec_str) → bytes
# 包含 mtime 確保 enrich 重生同路徑封面後不會取到 stale bytes
# ---------------------------------------------------------------------------

_CROP_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()
_CROP_CACHE_MAXSIZE = 256
_CROP_CACHE_LOCK = threading.Lock()


def _cache_get(key: tuple) -> Optional[bytes]:
    """LRU get：命中時將該 entry 搬到末端（最近使用）。thread-safe。"""
    with _CROP_CACHE_LOCK:
        if key in _CROP_CACHE:
            _CROP_CACHE.move_to_end(key)
            return _CROP_CACHE[key]
        return None


def _cache_put(key: tuple, value: bytes) -> None:
    """LRU put：寫入 entry，超過 maxsize 時 evict 最舊的 entry。thread-safe。"""
    with _CROP_CACHE_LOCK:
        _CROP_CACHE[key] = value
        _CROP_CACHE.move_to_end(key)
        while len(_CROP_CACHE) > _CROP_CACHE_MAXSIZE:
            _CROP_CACHE.popitem(last=False)


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
    # 取 mtime 作為 cache key 一部分（防 enrich 重生後拿到 stale bytes）
    try:
        mtime = os.stat(cover_path).st_mtime
    except OSError:
        # 檔案不存在或無法 stat → mtime=None → 跳過 cache，直接走主流程（會 fail 然後回 None）
        mtime = None

    if mtime is not None:
        cache_key: Optional[tuple] = (cover_path, mtime, crop_spec)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    else:
        cache_key = None

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
        if cache_key is not None:
            _cache_put(cache_key, result)
        return result

    except Exception as e:
        logger.warning("[actress_photo] crop_video_cover 失敗 (%s): %s", cover_path, e)
        return None
