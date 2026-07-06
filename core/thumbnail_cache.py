"""縮圖快取核心邏輯（feature/71 T1，純函式模組）。

以「影片路徑 URI」為 key、扁平 hash 分桶（thumb/<h[:2]>/<h>.webp）、原子寫的
本地 WebP 縮圖快取。對齊 spec-71 D1/D2/D5/D6/D7/D12、plan-71 CD-1/CD-2/CD-3。

設計約束：
- 純函式，無 class。
- 不 import web、不 import config（保持 core 不反向依賴，CD-1）。
- 路徑轉換不疊：URI→fs 一步用 uri_to_fs_path。
- generate 失敗（損圖/讀取/save 失敗）→ logger.warning 後回 False，不拋例外（D6）。
"""
import hashlib
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Iterator, Optional, Tuple

from PIL import Image

from core.database import get_db_path
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path

logger = get_logger(__name__)

# per-thumb-path 鎖註冊表（Codex round-2 P1 修法 A）。
# 讓 generate（讀 cover + 原子寫 thumb）與 invalidate（unlink）對「同一 thumb path」
# 互斥序列化，關閉「enrich 原地覆寫同一 cover.jpg → generate serve 舊內容、stale thumb
# 殘留」的競態。鎖 key = str(thumb_file_for(uri))，generate 的 dst 與 invalidate 的 tf
# 對同一 video_path_uri 必是同一 Path → str 相同 → 同一把鎖。
_thumb_locks: dict = {}              # str(thumb_path) -> threading.Lock
_thumb_locks_guard = threading.Lock()


def _lock_for_thumb(dst) -> threading.Lock:
    """取得 thumb path 對應的鎖（缺則建）。key 用 str(dst) 確保跨 generate/invalidate 一致。"""
    key = str(dst)
    with _thumb_locks_guard:
        lk = _thumb_locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _thumb_locks[key] = lk
        return lk

# 縮圖參數（CD-3 / D2，集中為模組常數供日後調參）
THUMB_WIDTH = 400      # 目標寬度（px）
THUMB_QUALITY = 80     # WebP quality
THUMB_METHOD = 4       # WebP method（壓縮努力）


def _thumb_dir() -> Path:
    """縮圖快取根目錄（= output/thumb/，CD-2/D1）。不負責建檔。"""
    return get_db_path().parent / "thumb"


def thumb_file_for(video_path_uri: str) -> Path:
    """以 video path URI 為 key 推導縮圖檔路徑（純路徑推導，無 I/O）。

    h = sha1(video_path_uri).hexdigest()；回 thumb/<h[:2]>/<h>.webp（D5/D12/CD-2）。
    呼叫端負責傳規範 file URI（web 層用 v.path，DB 已是 file URI）。
    """
    h = hashlib.sha1(video_path_uri.encode("utf-8")).hexdigest()
    return _thumb_dir() / h[:2] / f"{h}.webp"


def generate(cover_fs_path: str, dst: Path) -> bool:
    """從封面 fs path 產出寬 THUMB_WIDTH 的 WebP 縮圖，原子寫到 dst。

    成功回 True；損圖/讀取失敗/save 失敗 → logger.warning 後回 False（不拋，D6）。
    原子寫鏡像 core/config.py:_save_config_unlocked（同目錄 tempfile + os.replace，
    fd 先關再 replace；任何例外清 temp 殘檔）。
    """
    # 整個「讀 cover → 處理 → 原子寫」包進 per-thumb 鎖內，與 invalidate 的 unlink
    # 序列化（Codex round-2 P1 修法 A）。失敗回 False 的語義不變，只是被鎖包住。
    with _lock_for_thumb(dst):
        tmp = None
        try:
            with Image.open(cover_fs_path) as img:
                img = img.convert("RGB")  # 去 alpha/CMYK，WebP 友善
                # 等比縮到寬 THUMB_WIDTH；原圖更窄則不放大
                if img.width > THUMB_WIDTH:
                    new_h = max(1, round(img.height * THUMB_WIDTH / img.width))
                    img = img.resize((THUMB_WIDTH, new_h), Image.LANCZOS)

                dst.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".tmp")
                # fd 必須在 os.replace 前關閉（Windows file-lock）
                with os.fdopen(fd, "wb") as f:
                    img.save(f, "WEBP", quality=THUMB_QUALITY, method=THUMB_METHOD)
                os.replace(tmp, dst)
                tmp = None
            return True
        except Exception as e:
            logger.warning("thumbnail generate failed: cover=%s err=%s", cover_fs_path, e)
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return False


def get_or_create(video_path_uri: str, cover_fs_path: str) -> Optional[Path]:
    """lazy on-miss：thumb 已存在→直接回（hit，零生成）；否則 generate。

    成功回 Path、失敗回 None（web serve miss 路徑用，spec 2.A.8）。
    """
    tf = thumb_file_for(video_path_uri)
    if tf.exists():
        return tf
    if generate(cover_fs_path, tf):
        return tf
    return None


def invalidate(video_path_uri: str) -> None:
    """砍掉某影片的縮圖（缺檔 no-op，不拋）。下次 lazy/prewarm 重生（CD-9/CD-11）。

    unlink 包在 per-thumb 鎖內，與 generate 的「讀 cover + 寫 thumb」序列化
    （Codex round-2 P1 修法 A）。tf 與 generate 的 dst 對同 uri 是同一 Path → 同一把鎖。
    """
    tf = thumb_file_for(video_path_uri)
    with _lock_for_thumb(tf):
        tf.unlink(missing_ok=True)


def clear_all() -> None:
    """清空整個縮圖快取目錄（缺目錄 no-op，CD-11）。"""
    shutil.rmtree(_thumb_dir(), ignore_errors=True)


def iter_missing(videos, path_mappings: dict = None) -> Iterator[Tuple[str, str]]:
    """prewarm 用：yield 出「缺 thumb 且 cover 有效」者（CD-8）。

    產出 (video_path_uri, cover_fs_path)。已有 thumb 或 cover 無效者跳過
    （冪等、只補缺，spec 2.A.2/D3）。用 getattr 容忍物件/屬性缺漏。

    TASK-91-T2b #15：path_mappings 預設 None（等價於裸 uri_to_fs_path），
    不動既有呼叫端測試。
    """
    for v in videos:
        video_path_uri = getattr(v, "path", None)
        if not video_path_uri:
            continue
        if thumb_file_for(video_path_uri).exists():
            continue
        cover_path = getattr(v, "cover_path", None)
        if not cover_path:
            continue
        cover_fs = uri_to_local_fs_path(cover_path, path_mappings)
        if not os.path.exists(cover_fs):
            continue
        yield (video_path_uri, cover_fs)
