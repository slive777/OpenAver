"""書籤封面快取（feature/140 T3，純函式模組）。

以正規化番號為 key、扁平 hash 分桶（wishlist_cover/<h[:2]>/<h>.webp）、
原子寫的本地封面快取。仿 core.thumbnail_cache 的形狀。

設計約束：
- 純函式，無 class。
- 不 import web、不 import config（保持 core 不反向依賴）。
- 下載失敗（網路例外 / 非 200 / 內容過小）→ logger.warning 後回 False，不拋例外（I2）。
- 不走 actress_photo SSRF 白名單（JAV host 會被 fail-closed）。
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import requests
from PIL import Image

from core.atomic_write import atomic_write
from core.database import get_db_path
from core.logger import get_logger
from core.proxy_policy import proxy_kwargs
from core.organizer import build_download_headers
from core.scraper import normalize_number

logger = get_logger(__name__)

# 轉檔參數：與 `core/thumbnail_cache.py:49-50` 的縮圖同組值。封面是全尺寸圖、
# 不縮放（書籤卡與燈箱都要用），只做格式正規化。
COVER_QUALITY = 80
COVER_METHOD = 4


def cover_file_for(number: str) -> Path:
    """以正規化番號推導封面檔路徑（純路徑推導，無 I/O）。

    h = sha1(normalize_number(number)).hexdigest()；
    回 wishlist_cover/<h[:2]>/<h>.webp。呼叫端不得假設本函式會建目錄。
    """
    h = hashlib.sha1(normalize_number(number).encode("utf-8")).hexdigest()
    return get_db_path().parent / "wishlist_cover" / h[:2] / f"{h}.webp"


def _fetch_image_bytes(url: str, timeout: float = 30) -> bytes | None:
    """下載封面 bytes；失敗回 None（不拋）。"""
    if not url:
        return None
    headers = build_download_headers(url)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, **proxy_kwargs('image', url=url))
    except requests.RequestException:
        logger.warning("wishlist cover fetch failed: url=%s", url)
        return None
    if resp.status_code == 200 and len(resp.content) > 1000:
        return resp.content
    return None


def _save_as_webp(number: str, data: bytes, dest: Path) -> bool:
    """把下載到的 bytes 轉成 WebP 原子寫進 dest。**解不開回 False，不留檔。**

    落地檔副檔名是 `.webp`、`/api/wishlist/cover` 也固定回 `image/webp`
    ⇒ **內容必須真的是 WebP**（Codex review 第 2 輪）。外站給的多半是 JPEG/PNG。
    （全庫其他三處都不是原樣落地：`thumbnail_cache` 真轉 WebP、`actress_photo`
    依 Content-Type 決定副檔名、`organizer` 真存 JPEG。）

    **刻意不做「解不開就寫原始 bytes」的逃生口**：對解不開的資料而言，
    寫下去的產物**本來就是破圖**，只是多騙一個 `cover_available: true`。
    解不開就回 False，書籤那一列照樣留著（I2 不變式），前端走既有的破圖 fallback。

    `except` 只包**解碼／轉碼**階段：`atomic_write()` 的寫檔失敗（磁碟滿／權限／
    Windows 防毒鎖 `os.replace`）**照原樣往上拋**，由 T4 的 POST handler 收成
    `cover_available: false`——那是它的職責，不是在這裡吞掉。
    """
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")  # 強制解碼；去 alpha/CMYK，WebP 友善
    except Exception as e:
        logger.warning(
            "wishlist cover decode failed: number=%s bytes=%d err=%s", number, len(data), e
        )
        return False

    # 解得開才建目錄——兩個 URL 都不可解時不留下空資料夾
    dest.parent.mkdir(parents=True, exist_ok=True)
    with img:
        with atomic_write(dest) as f:
            img.save(f, "WEBP", quality=COVER_QUALITY, method=COVER_METHOD)
    return True


def download_and_save(number: str, cover_url: str, fallback_url: str = "") -> bool:
    """下載封面、轉成 WebP 原子寫到 cover_file_for(number)。

    先試 cover_url，**下載失敗或轉不成 WebP** 都會再試 fallback_url（非空時）。
    兩個 URL 都不成 → logger.warning 後回 False（不拋，I2）。

    ⚠️ 「轉不成也要試 fallback」是 Codex review 第 2 輪的要求：主圖拿得到但解不開
    （CDN 回了一頁 HTML、或格式 Pillow 不認得）時，備援那張往往是好的。
    """
    dest = cover_file_for(number)

    # 🔴 Codex PR#175 P2：去重。`add_wishlist()` 傳的是
    # `(preview_cover_url or cover, cover)`，而 `preview_cover_url` **只有 metatube 會填**
    # （全部內建 scraper 都留空，`core/scrapers/models.py` 的 default 就是 `''`）⇒ 沒接
    # metatube 的人，兩個參數恆為同一個網址。圖床連不上時這個迴圈會對**同一個 URL 打兩次**、
    # 各等一次 30 秒 timeout ⇒ 使用者按下加入書籤要轉 60 秒而不是 30 秒。
    seen = set()
    for url in (cover_url, fallback_url):
        if not url or url in seen:
            continue
        seen.add(url)
        data = _fetch_image_bytes(url)
        if data is None:
            continue
        if _save_as_webp(number, data, dest):
            return True

    logger.warning(
        "wishlist cover unavailable: number=%s cover_url=%s fallback_url=%s",
        number,
        cover_url,
        fallback_url,
    )
    return False


def remove(number: str) -> None:
    """刪掉某番號的封面檔（缺檔 no-op，不拋）。"""
    cover_file_for(number).unlink(missing_ok=True)


def remove_best_effort(number: str) -> None:
    """刪封面檔，失敗只記 log。

    🔴 Codex PR#175 P2：`wishlist_cover_cache.remove()` 的 docstring 寫「不拋」，但它是
    `Path.unlink(missing_ok=True)`——那只吞 `FileNotFoundError`。`PermissionError`／
    `OSError`（Windows 檔案鎖／防毒正在掃那張圖／唯讀掛載）會整個穿透出去，而本 app 只
    註冊了 `RequestValidationError` 的 handler（`web/app.py:209`）⇒ 變成 500。

    問題在於**DB 那筆已經 commit 了**：回 500 會讓前端把樂觀移除整個回滾，於是畫面上
    跳出一張「資料庫裡其實已經不存在」的幽靈卡、計數還加一，要重新整理才會消失。
    ⇒ 刪檔一律 best-effort，回應只反映 DB 的權威狀態。留下來的孤兒 webp 是 spec §5
    已接受的方向（單人本機、幾十 KB 一張，不做 GC）。
    """
    try:
        remove(number)
    except OSError:
        logger.warning("wishlist 封面刪除失敗（DB 已刪，留下孤兒檔）: number=%s", number, exc_info=True)
