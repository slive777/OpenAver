"""
Gallery Scanner — 負責掃描資料夾、解析檔名與讀取 NFO 元資料。

與 gallery_generator.py 的分工：scanner 專注於檔案系統遍歷、檔名解析
（parse_filename）、NFO 讀取（parse_nfo）及寫入 SQLite（scan_to_sqlite）；
generator 則負責靜態 HTML 的輸出。VideoScanner 是主要入口，
核心方法為 parse_filename、parse_nfo、scan_file、scan_to_sqlite。
"""

import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields as dataclass_fields
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from core.cover_attributes import effective_tags
from core.focal import requires_face_detection
from core.focal_trigger import maybe_submit_video_focal
from core.logger import get_logger
from core.maker_mapping import load_name_mapping, load_prefix_mapping
from core.nfo_read import (
    nfo_actor_names,
    nfo_first_text,
    nfo_merged_tags,
    nfo_runtime_minutes,
    nfo_series_name,
    nfo_text,
    nfo_title_record,
)
from core.nfo_stat import NFO_MTIME_REFRESH, nfo_mtime_or_none
from core.nfo_title_format import resolve_title_body
from core.nfo_utils import sanitize_nfo_bytes
from core.path_utils import normalize_path, to_file_uri, uri_to_fs_path, uri_to_local_fs_path
from core.plot_nfo import plot_present
from core.scrapers.utils import FC2_TOKEN_PATTERN, normalize_number_impl
from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS, ZERO_SIZE_EXTENSIONS

logger = get_logger(__name__)

# Jellyfin BaseItem.SupportedImageExtensions minus .svg.
# Jellyfin's list is global (logo/clearart/banner too); extrafanart is stills,
# which are never SVG. Serving user-disk .svg via /api/gallery/image would let
# a direct navigation execute script on this origin, and this project has no CSP.
# Same split as DEFAULT_VIDEO_EXTENSIONS vs SAFE_PROXY_EXTENSIONS: discoverable
# is not the same as servable.
_EXTRAFANART_IMAGE_EXTS = frozenset({
    '.png', '.jpg', '.jpeg', '.webp', '.tbn', '.gif',
})


@dataclass
class VideoInfo:
    """影片資訊資料結構"""
    path: str = ""
    title: str = ""
    originaltitle: str = ""
    actor: str = ""
    num: str = ""
    maker: str = ""
    date: str = ""
    genre: str = ""
    size: int = 0
    mtime: int = 0
    img: str = ""
    director: str = ""
    duration: Optional[int] = None
    series: str = ""
    label: str = ""
    sample_images: List[str] = field(default_factory=list)
    user_tags: List[str] = field(default_factory=list)
    nfo_thumb: Optional[str] = None  # 暫存用途，不序列化進 DB/cache
    has_plot: Optional[bool] = None  # 暫存：掃描寫 True/False；不進 to_dict（同 nfo_thumb）

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "originaltitle": self.originaltitle,
            "actor": self.actor,
            "num": self.num,
            "maker": self.maker,
            "date": self.date,
            "genre": self.genre,
            "size": self.size,
            "mtime": self.mtime,
            "img": self.img,
            "director": self.director,
            "duration": self.duration,
            "series": self.series,
            "label": self.label,
            "sample_images": self.sample_images,
            "user_tags": self.user_tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'VideoInfo':
        known = {f.name for f in dataclass_fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# 支援的影片副檔名（from core.video_extensions Single Source of Truth）
VIDEO_EXTENSIONS = set(DEFAULT_VIDEO_EXTENSIONS)

# 支援的圖片副檔名（按優先順序排列，JPG 優先）
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

# 預設緩存檔案名稱
DEFAULT_CACHE_FILE = "gallery_cache.json"


_NAS_SYSTEM_DIR_NAMES = {'#recycle', '#snapshot', '@eadir'}


def is_nas_system_dir_name(name: str) -> bool:
    """CD-159-1／CD-159-2 共用：NAS（Synology）系統目錄判斷，索引層（scan_recursive）
    與顯示層（browse_dir）共用同一份規則，避免各自維護排除清單而漂移。"""
    return name.lower() in _NAS_SYSTEM_DIR_NAMES or name.startswith('@')


def fast_scan_directory(
    directory: str,
    extensions: set,
    min_size_bytes: int = 0,
    on_skip: Optional[Callable[[str, Exception], None]] = None,
) -> List[dict]:
    """快速掃描目錄，一次取得所有檔案資訊

    使用 os.scandir() 替代 glob() + stat()，大幅減少系統呼叫次數
    同時收集 NFO 檔案的 mtime，用於偵測 NFO 更新

    Args:
        directory: 要掃描的根目錄
        extensions: 目標副檔名集合（含點）
        min_size_bytes: 最小檔案大小（bytes）
        on_skip: 可選 callback，簽名 (path, exception) -> None。
            每當內部 entry 或外層目錄因 OSError/PermissionError 被跳過時呼叫。
            用於讓呼叫端捕捉「因長路徑/權限而無法存取」的檔案，因為這類 entry
            根本不會進入回傳 results，僅透過 callback 讓呼叫端知道它們存在。
            callback 本身拋的例外會被吞掉，不影響掃描進度。
    """
    logger.debug(f"[FastScan] 掃描目錄: {directory}")
    results = []
    def _safe_on_skip(p: str, exc: Exception) -> None:
        if on_skip is None:
            return
        try:
            on_skip(p, exc)
        except Exception:  # noqa: S110 — callback errors must not abort the scan
            # callback 本身出錯不得影響掃描
            pass

    def _count_extrafanart_images(parent_dir: str) -> int:
        """數 `<parent_dir>/extrafanart/` 裡的合格劇照張數（TASK-118b-T9）。

        **這裡刻意複製 scan_file() 的定位方式，而不是自己找那個目錄**：
        `Path(parent) / 'extrafanart'` ＋ `.is_dir()` 與 scan_file()（見該函式內的
        `extrafanart_dir = video_path.parent / 'extrafanart'`）是**逐字相同的表達式**，
        所以「哪個目錄算數」在兩端由構造保證一致——不管底下的檔案系統大小寫敏不敏感、
        那個目錄是不是 symlink。

        走訪端曾用 `entry.name` 比對過兩版（精確 → `.lower()`），兩版都在某一類檔案系統上
        與 scan_file() 分岔：精確比對讓大小寫不敏感的 FS（NTFS／APFS）上的 `Extrafanart`
        走訪端數 0、DB 數 N；`.lower()` 則讓大小寫敏感的 FS（ext4）上的 `Extrafanart`
        走訪端數 N、DB 數 0。**兩種分岔的症狀都是「每次產生都重掃該片且永遠對不上」**。
        用同一句表達式就沒有第三種寫錯的方式。

        張數本身的過濾（副檔名／隱藏檔／size>0）同樣不另抄——直接呼叫
        `VideoScanner._iter_extrafanart_images()`，與撿取端同源。
        """
        extrafanart_dir = Path(parent_dir) / 'extrafanart'
        try:
            if not extrafanart_dir.is_dir():
                return 0
            return sum(1 for _ in VideoScanner._iter_extrafanart_images(extrafanart_dir))
        except OSError as e:
            _safe_on_skip(str(extrafanart_dir), e)
            return 0

    def scan_recursive(path: str):
        # 每層目錄各自獨立（新的區域變數），天然不會跨目錄污染。
        extrafanart_image_count = 0
        try:
            with os.scandir(path) as entries:
                dir_files = []
                dir_nfos = {}

                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if is_nas_system_dir_name(entry.name):
                                continue
                            scan_recursive(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(entry.name)[1].lower()
                            stem = os.path.splitext(entry.name)[0]

                            if ext == '.nfo':
                                # 記錄 NFO 的 mtime
                                _NFO_MTIME_POLICY = NFO_MTIME_REFRESH
                                mt = nfo_mtime_or_none(
                                    entry,
                                    on_error=lambda e, entry=entry: _safe_on_skip(entry.path, e),
                                )
                                if mt is not None:
                                    dir_nfos[stem] = mt
                            elif ext in extensions:
                                stat = entry.stat()
                                if min_size_bytes <= 0 or ext in ZERO_SIZE_EXTENSIONS or stat.st_size >= min_size_bytes:
                                    dir_files.append({
                                        'path': entry.path,
                                        'mtime': stat.st_mtime,
                                        'size': stat.st_size,
                                        'stem': stem
                                    })
                    except (OSError, PermissionError) as e:
                        # entry.path 是 os.DirEntry 的純拼接屬性，通常不會拋
                        _safe_on_skip(entry.path, e)

                # 只有「這層真的有影片」才去問 extrafanart/ 在不在（沒有影片的目錄
                # 一次 syscall 都不多花）。放在 entry 迴圈**之後**：此時 dir_files 已定，
                # 而定位方式與 scan_file() 同源，不依賴走訪順序或 entry 名稱比對。
                if dir_files:
                    extrafanart_image_count = _count_extrafanart_images(path)

                # 將 NFO mtime 加入對應的影片資訊
                for f in dir_files:
                    f['nfo_mtime'] = dir_nfos.get(f['stem'], 0)
                    # 同目錄下所有影片本來就共用同一個 extrafanart/（scan_file()
                    # 也是用 video_path.parent / 'extrafanart' 算路徑，既有行為）
                    # ——均等掛給本層每部片，不是只掛給其中一部（TASK-118b-T9）。
                    f['sample_image_count'] = extrafanart_image_count
                    del f['stem']  # 不需要保留 stem
                    results.append(f)

        except (OSError, PermissionError) as e:
            _safe_on_skip(path, e)

    scan_recursive(directory)
    logger.debug(f"[FastScan] 找到 {len(results)} 個檔案")
    return results


class VideoScanner:
    """影片掃描器"""

    # 番號識別正則表達式 (從 galleryHtml.cs 移植)
    NUM_PATTERNS = [
        # FC2-PPV
        (rf'^(.*[\W_])?(?P<fc2>{FC2_TOKEN_PATTERN})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: normalize_number_impl(m.group('fc2'))),

        # 一本道/加勒比 (n1234, k1234)
        (r'^(.*[\W_])?([nk]\d{4})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: m.group(2).upper()),

        # 加勒比/一本道 日期格式 (123456-01, 123456_789)
        (r'^(.*[\W_])?(\d{6}[_-]\d{2,3})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: m.group(2)),

        # 素人系列 (200GANA-1234, 259LUXU-1234)
        (r'^(.*[\W_])?(\d{3}[a-zA-Z]{3,5})-?(\d+)([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: f"{m.group(2).upper()}-{m.group(3)}"),

        # 一般番號 (ABC-123, ABCD-12345)
        (r'^(.*[\W_]|\d+)?([a-zA-Z]{2,7})-?(\d{2,5})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: f"{m.group(2).upper()}-{m.group(3)}"),

        # 含數字前綴的番號 (1PONDO, 7SNIS)
        (r'^(.*[\W_]|\d+)?([a-zA-Z][a-zA-Z0-9]{1,6})-(\d{2,5})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: f"{m.group(2).upper()}-{m.group(3)}"),

        # HEYZO
        (r'^(.*[\W_])?HEYZO([\W_].*[\W_])?(\d{4})([\W_].*|[a-z]+|F?HD.*)?$',
         lambda m: f"HEYZO-{m.group(3)}"),
    ]

    def __init__(self, path_mappings: dict = None, nfo_title_format: str = '[{num}]{title}'):
        self.path_mappings = path_mappings or {}
        self.nfo_title_format = nfo_title_format
        self.prefix_mapping = load_prefix_mapping()
        self.name_mapping = load_name_mapping()
        # key: dir path str → (sorted videos list, sorted images list)
        self._dir_scan_cache: Dict[str, Tuple[List[str], List[str]]] = {}

    def normalize_maker(self, num: str, maker: str) -> str:
        """根據 name mapping 和番號前綴正規化片商名稱

        Step 1: name mapping（直接對照片商名，不依賴 num）
        Step 2: prefix mapping（從番號前綴查詢，作為 fallback）
        """
        # Step 1: name mapping（不依賴 num）
        if maker and maker in self.name_mapping:
            return self.name_mapping[maker]

        # Step 2: prefix mapping（fallback）
        if not num or not self.prefix_mapping:
            return maker

        # 提取番號前綴（移除數字部分）
        # 例如：SSIS-123 -> SSIS, FC2PPV-1234567 -> FC2PPV
        prefix_match = re.match(r'^([A-Za-z]+)', num)
        if prefix_match:
            prefix = prefix_match.group(1).upper()
            if prefix in self.prefix_mapping:
                return self.prefix_mapping[prefix]

        return maker

    def find_num_from_filename(self, filename: str) -> str:
        """從檔名提取番號"""
        # 移除副檔名
        name = Path(filename).stem

        for pattern, extractor in self.NUM_PATTERNS:
            match = re.match(pattern, name, re.IGNORECASE)
            if match:
                return extractor(match)

        return ""

    def parse_filename(self, filename: str) -> VideoInfo:
        """從檔名取出番號與標題。

        139-T2 起只做這兩件事——原本那套「命名格式樣板」解析（會填 actor/maker/date/genre）
        已整條刪除，它從來沒有被執行過。要從檔名抽那幾個欄位是新功能，不是修 bug。
        """
        name = Path(filename).stem
        info = VideoInfo()

        # 從檔名提取番號
        if not info.num:
            info.num = self.find_num_from_filename(filename)

        # 如果還是沒有標題，用檔名
        if not info.title:
            info.title = name

        return info

    def parse_nfo(self, nfo_path: str) -> Optional[VideoInfo]:
        """讀取 NFO 檔案"""
        try:
            raw = Path(nfo_path).read_bytes()
            raw = sanitize_nfo_bytes(raw)
            root = ET.fromstring(raw)

            info = VideoInfo()

            # 原始標題
            info.originaltitle = nfo_text(root, 'originaltitle')

            # 番號
            info.num = nfo_first_text(root, ('num', 'id'))

            # 片商
            info.maker = nfo_first_text(root, ('maker', 'studio'))

            # 日期
            info.date = nfo_first_text(root, ('release', 'premiered', 'year'))

            # 演員
            actors = nfo_actor_names(root)
            info.actor = ','.join(actors)

            # 標題（需在番號/片商/日期/演員之後，resolve_title_body 依賴這些值）
            raw_title = nfo_text(root, 'title')
            record = nfo_title_record(root)
            info.title = resolve_title_body(raw_title, info.num, actors, info.maker, info.date, self.nfo_title_format, record)

            # 類型/標籤
            info.genre = ','.join(nfo_merged_tags(root))

            # 用戶自訂標籤
            user_tags = []
            for ut_elem in root.findall('user_tag'):
                if ut_elem.text:
                    user_tags.append(ut_elem.text.strip())
            info.user_tags = user_tags

            # 時長 (runtime)
            info.duration = nfo_runtime_minutes(root)

            # 導演
            info.director = nfo_text(root, 'director')

            # 系列 (set/name)
            info.series = nfo_series_name(root)

            # 廠牌/標籤 (label)
            info.label = nfo_text(root, 'label')
            info.has_plot = plot_present(nfo_text(root, 'plot'))

            # <thumb> 元素（相對路徑/絕對路徑/URL，供 find_cover_image L3 使用）
            info.nfo_thumb = nfo_text(root, 'thumb') or None

            return info

        except Exception as e:
            logger.warning(f"  [!] NFO 讀取失敗: {nfo_path} - {e}")
            return None

    def _scan_dir(self, video_dir: Path) -> Tuple[List[str], List[str]]:
        """一次 scandir 取得目錄下所有影片和圖片，結果 cache 避免重複 IO。

        Returns:
            (sorted_videos, sorted_images) — 各自排序後的路徑字串列表
        """
        key = str(video_dir)
        if key in self._dir_scan_cache:
            return self._dir_scan_cache[key]

        videos: List[str] = []
        images: List[str] = []
        try:
            with os.scandir(video_dir) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        videos.append(entry.path)
                    elif ext in IMAGE_EXTENSIONS:
                        images.append(entry.path)
            videos.sort()
            images.sort()
        except OSError as e:
            logger.warning(f"  [!] 掃描目錄失敗: {video_dir} - {e}")
            videos, images = [], []

        self._dir_scan_cache[key] = (videos, images)
        return videos, images

    def _resolve_thumb_path(self, thumb_val: str, nfo_dir: Path) -> Optional[str]:
        """解析 NFO <thumb> 值為當前環境可用的 FS 路徑。

        5-case 跨平台辨識（不使用 Path.is_absolute()）：
          1. URL (http:// / https://) → None（跳過）
          2. file:/// URI → uri_to_fs_path()
          3. Windows drive letter (path[1] == ':') → normalize_path()
          4. UNC (\\\\... 或 //...) → normalize_path()（WSL backslash 會拋 ValueError）
          5. POSIX 絕對 (/) 或相對 → 直接或 nfo_dir / val

        Returns:
            FS 路徑字串（Path.is_file() 驗證存在），或 None
        """
        if not thumb_val:
            return None

        # Case 1: URL → skip
        if thumb_val.startswith(('http://', 'https://')):
            return None

        try:
            # Case 2: file:/// URI
            if thumb_val.startswith('file://'):
                fs = uri_to_fs_path(thumb_val)  # uri-no-reverse: third-party NFO <thumb> value, unrelated to path_mappings namespace
            # Case 3: Windows drive letter
            elif len(thumb_val) >= 2 and thumb_val[1] == ':':
                fs = normalize_path(thumb_val)
            # Case 4: UNC 路徑（backslash 或 forward-slash）
            elif thumb_val.startswith(('\\\\', '//')):
                fs = normalize_path(thumb_val)
            # Case 5: POSIX 絕對路徑
            elif thumb_val.startswith('/'):
                fs = thumb_val
            # Case 5: 相對路徑
            # 注意：third-party Windows-authored NFO 的相對路徑可能用 backslash
            # 例如 "covers\poster.jpg"，在 POSIX 必須先轉 forward slash 才能正確拼接。
            # 這裡的 replace('\\', '/') 是處理 NFO 第三方內容字串的標準化，
            # 不是 FS 路徑轉換（CLAUDE.md 禁止清單禁的是對 FS 路徑用 replace，性質不同）。
            else:
                fs = str(nfo_dir / thumb_val.replace('\\', '/'))
        except ValueError:
            # WSL 環境下 backslash UNC 會拋 ValueError → fall through
            return None

        return fs if Path(fs).is_file() else None

    def find_cover_image(self, video_path: str, nfo_thumb: Optional[str] = None) -> str:
        """尋找封面圖片（5 層 fallback）

        L1:   同名圖片（{stem}{ext}）
        L1.5: 外部管理器命名（{stem}-fanart / {stem}-poster，MDCX/Javinizer/jellyfin/emby）
        L2:   標準名稱（fanart/poster/cover/folder）
        L3:   NFO <thumb> 跨平台路徑解析
        L4:   安全 fallback — 僅在 mp4==1 AND 0<img<=2 雙條件下回傳 sorted 第一張
        """
        video_path = Path(video_path)
        video_dir = video_path.parent
        video_stem = video_path.stem

        # L1: 同名圖片
        for ext in IMAGE_EXTENSIONS:
            img_path = video_dir / f"{video_stem}{ext}"
            if img_path.exists():
                return str(img_path)

        # L1.5: {stem}-fanart / {stem}-poster（外部管理器工具慣用命名：MDCX/Javinizer + OpenAver jellyfin/emby 輸出）
        #       -fanart 優先（全圖橫版，showcase 顯示一致），-poster 次之
        for suffix in ['-fanart', '-poster']:
            for ext in IMAGE_EXTENSIONS:
                img_path = video_dir / f"{video_stem}{suffix}{ext}"
                if img_path.exists():
                    return str(img_path)

        # L2: 標準名稱
        for name in ['fanart', 'poster', 'cover', 'folder']:
            for ext in IMAGE_EXTENSIONS:
                img_path = video_dir / f"{name}{ext}"
                if img_path.exists():
                    return str(img_path)

        # L3: NFO <thumb>
        if nfo_thumb:
            resolved = self._resolve_thumb_path(nfo_thumb, video_dir)
            if resolved:
                return resolved

        # L4: 安全 fallback — 雙條件：mp4==1 AND 0<img<=2
        videos, images = self._scan_dir(video_dir)
        if len(videos) == 1 and 0 < len(images) <= 2:
            return images[0]  # sorted first

        return ""

    @staticmethod
    def _iter_extrafanart_images(extrafanart_dir: Path):
        """Yield extrafanart/ children that Jellyfin would treat as images.

        Non-recursive; file + image suffix + size > 0. Hidden names (``.`` prefix)
        are an extra filter we add on top of Jellyfin: macOS SMB writes
        ``._fanart1.jpg`` AppleDouble sidecars (suffix ``.jpg``, ~4KB, non-empty)
        that would otherwise surface as a broken thumbnail on NAS / network
        drives.
        """
        for img_path in extrafanart_dir.iterdir():
            if not img_path.is_file():
                continue
            if img_path.name.startswith('.'):
                continue
            if img_path.suffix.lower() not in _EXTRAFANART_IMAGE_EXTS:
                continue
            try:
                if img_path.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            yield img_path

    def scan_file(self, video_path: str, base_path: str = None) -> VideoInfo:
        """掃描單一影片檔案"""
        t_start = time.time()
        video_path = Path(video_path)
        video_name = video_path.name
        logger.debug(f"[Scan] {video_name} 開始")

        # 基本檔案資訊
        info = VideoInfo()

        # 路徑處理
        if base_path:
            # 相對路徑
            try:
                rel_path = video_path.relative_to(base_path)
                info.path = str(rel_path).replace('\\', '/')
            except ValueError:
                info.path = str(video_path).replace('\\', '/')
        else:
            # 絕對路徑 (file:// 格式) - 使用統一的 to_file_uri()
            info.path = to_file_uri(str(video_path), self.path_mappings)

        # 檔案大小和修改時間
        try:
            stat = video_path.stat()
            info.size = stat.st_size
            info.mtime = int(stat.st_mtime * 10000000 + 116444736000000000)  # 轉換為 FileTime
        except OSError:
            pass

        # 嘗試讀取 NFO
        nfo_path = video_path.with_suffix('.nfo')
        t_nfo_check = time.time()
        info.has_plot = False  # 無 NFO／parse 失敗＝已確認沒有（CD-187b-2）
        if nfo_path.exists():
            logger.debug(f"[Scan]   nfo_exists: {t_nfo_check - t_start:.2f}s")
            nfo_info = self.parse_nfo(str(nfo_path))
            t_parse = time.time()
            logger.debug(f"[Scan]   parse_nfo: {t_parse - t_nfo_check:.2f}s")
            if nfo_info:
                info.title = nfo_info.title or info.title
                info.originaltitle = nfo_info.originaltitle or info.originaltitle
                info.actor = nfo_info.actor or info.actor
                info.num = nfo_info.num or info.num
                info.maker = nfo_info.maker or info.maker
                info.date = nfo_info.date or info.date
                info.genre = nfo_info.genre or info.genre
                info.director = nfo_info.director or info.director
                info.duration = nfo_info.duration if nfo_info.duration is not None else info.duration
                info.series = nfo_info.series or info.series
                info.label = nfo_info.label or info.label
                info.user_tags = nfo_info.user_tags or []
                info.nfo_thumb = nfo_info.nfo_thumb
                info.has_plot = nfo_info.has_plot

        # 如果 NFO 沒有資料，從檔名解析
        if not info.title or not info.num:
            filename_info = self.parse_filename(video_path.name)
            info.title = info.title or filename_info.title
            info.num = info.num or filename_info.num

        # 根據番號前綴正規化片商名稱
        info.maker = self.normalize_maker(info.num, info.maker)

        # 新增：檔名屬性後綴 → tag（CD-6 掃描列）
        _existing = [g.strip() for g in info.genre.split(',') if g.strip()] if info.genre else []
        _merged = effective_tags(video_path.name, _existing)
        info.genre = ','.join(_merged)

        # 尋找封面圖片
        img_path = self.find_cover_image(str(video_path), nfo_thumb=info.nfo_thumb)
        if img_path:
            if base_path:
                try:
                    rel_img = Path(img_path).relative_to(base_path)
                    info.img = str(rel_img).replace('\\', '/')
                except ValueError:
                    info.img = img_path.replace('\\', '/')
            else:
                info.img = to_file_uri(img_path, self.path_mappings)

        # 掃描 extrafanart/ 目錄（sample images）
        extrafanart_dir = video_path.parent / 'extrafanart'
        if extrafanart_dir.is_dir():
            try:
                for img_path in sorted(self._iter_extrafanart_images(extrafanart_dir)):
                    if base_path:
                        try:
                            rel_img = img_path.relative_to(base_path)
                            info.sample_images.append(str(rel_img).replace('\\', '/'))
                        except ValueError:
                            info.sample_images.append(str(img_path).replace('\\', '/'))
                    else:
                        info.sample_images.append(to_file_uri(str(img_path), self.path_mappings))
            except OSError as e:
                logger.warning(f"  [!] extrafanart 掃描失敗: {extrafanart_dir} - {e}")

        t_end = time.time()
        logger.debug(f"[Scan] {video_name} 完成 ({t_end - t_start:.2f}s)")

        return info

    def scan_to_sqlite(self, directory: str, db_path: 'Path' = None,
                       min_size_mb: int = 0,
                       progress_callback: callable = None,
                       video_extensions: set = None) -> dict:
        """掃描目錄並寫入 SQLite

        Args:
            directory: 要掃描的資料夾路徑
            db_path: SQLite 資料庫路徑（預設為 output/openaver.db）
            min_size_mb: 最小檔案大小 (MB)
            progress_callback: 進度回調函數，簽名: (current, total, filename) -> None
            video_extensions: 影片副檔名集合（預設使用 VIDEO_EXTENSIONS）

        Returns:
            dict: {'inserted': int, 'updated': int, 'deleted': int, 'total': int}
        """
        from core.database import VideoRepository, Video, init_db, get_db_path

        directory = Path(directory)
        if not directory.exists():
            raise ValueError(f"資料夾不存在: {directory}")

        # 初始化資料庫
        if db_path is None:
            db_path = get_db_path()
        init_db(db_path)

        repo = VideoRepository(db_path)
        min_size_bytes = min_size_mb * 1024 * 1024
        extensions = video_extensions if video_extensions is not None else VIDEO_EXTENSIONS

        # 步驟 1: 快速掃描檔案取得 mtime
        logger.info("[*] 快速掃描目錄中...")
        file_infos = fast_scan_directory(str(directory), extensions, min_size_bytes)
        logger.info(f"[*] 找到 {len(file_infos)} 個影片檔案")

        # 步驟 2: 從 SQLite 取得現有 mtime 索引
        # 注意：資料庫中的 path 是 file:/// 格式
        db_index = repo.get_mtime_index()  # {path: (mtime, nfo_mtime, sample_count)}

        # 建立 file:/// 路徑到原始路徑的映射，以及原始路徑到 mtime 的映射
        # scan_file 會產生 file:/// 格式的路徑（使用 core.path_utils.to_file_uri）

        # 步驟 3: 比對決定需要處理的檔案
        needs_scan = []
        current_file_uris = set()

        for file_info in file_infos:
            fs_path = file_info['path']
            file_uri = to_file_uri(fs_path, self.path_mappings)
            current_file_uris.add(file_uri)

            db_entry = db_index.get(file_uri)
            if db_entry is None:
                # 新檔案
                needs_scan.append(file_info)
            elif (
                db_entry[0] != file_info['mtime']
                or db_entry[1] != file_info.get('nfo_mtime', 0)
                # extrafanart/ 劇照張數變更（新增/刪除）也要觸發重掃（TASK-118b-T9）。
                # db_entry[2] 可能是 get_mtime_index() 的哨兵值（壞資料，見該函式
                # docstring）——此時恆不等於任何真實張數，同樣會落入這個分支。
                or db_entry[2] != file_info.get('sample_image_count', 0)
            ):
                # mtime、nfo_mtime 或劇照張數變更
                needs_scan.append(file_info)

        # 步驟 4: 清理已刪除的檔案（比對 file:/// 格式的路徑）
        deleted_paths = set(db_index.keys()) - current_file_uris
        deleted_count = repo.delete_by_paths(list(deleted_paths))
        if deleted_count > 0:
            logger.info(f"[*] 清理 {deleted_count} 個已刪除檔案")

        # 步驟 5: 掃描並寫入
        videos_to_upsert = []
        total_needs_scan = len(needs_scan)

        for i, file_info in enumerate(needs_scan, 1):
            video_name = os.path.basename(file_info['path'])

            # 回報進度
            if progress_callback:
                progress_callback(i, total_needs_scan, video_name)

            logger.info(f"[{i}/{total_needs_scan}] 處理: {video_name}")

            try:
                video_info = self.scan_file(file_info['path'], None)
                video = Video.from_video_info(video_info)
                video.mtime = file_info['mtime']
                video.nfo_mtime = file_info.get('nfo_mtime', 0)
                videos_to_upsert.append(video)
            except Exception as e:
                logger.warning(f"  [!] 錯誤: {e}")

        # 批次寫入
        inserted, updated = repo.upsert_batch(videos_to_upsert)
        logger.info(f"[*] 完成: 新增 {inserted}, 更新 {updated}, 刪除 {deleted_count}")

        # 掃描 focal trigger（TASK-98b-T2 / Codex PR#105 P2）：與 web/routers/scanner.py
        # 對稱——涵蓋本次掃描 in-scope 的所有空焦點無碼片，不只 upsert batch
        # （needs_scan）。既有、未變動、auto_focal='' 的列（不在 videos_to_upsert 內）
        # 也要補，否則「重掃一次自動補焦既有庫」形同虛設。current_file_uris 是本次
        # 掃描的完整 DB-key URI 集合（:685-690 同一套 to_file_uri(fs_path,
        # self.path_mappings) 推導），bulk 查詢，不另建 URI、不 N+1。
        # focal 是純副作用（安全退化：無 focal → render 退 baseline 右裁），任何例外都
        # 不得中止掃描——包整個 loop（含 get_empty_focal_candidates），log warning 後續
        # 走 cleanup + return。web/routers/scanner.py 的對稱塊已在 per-directory try
        # 內，此處為 method top-level 需自帶防護。
        try:
            focal_candidates = repo.get_empty_focal_candidates(list(current_file_uris))
            for c_path, c_number, c_maker, c_cover_path in focal_candidates:
                if requires_face_detection(c_number, c_maker):
                    cover_fs = uri_to_local_fs_path(c_cover_path, self.path_mappings)
                    maybe_submit_video_focal(c_number, c_maker, c_path, cover_fs, db_path=repo.db_path, cover_path_uri=c_cover_path)
        except Exception:
            logger.warning("[*] focal trigger 批次排程失敗（不影響掃描結果）", exc_info=True)

        # §b1 AC#2: sample_images 孤兒清理 pass（CLI / 直接呼叫路徑覆蓋）
        _run_sample_images_cleanup_pass(repo, self.path_mappings)

        try:
            from core.config import load_config
            from core.plot_flag_backfill import run_plot_flag_backfill_pass
            run_plot_flag_backfill_pass(repo, load_config(), self.path_mappings)
        except Exception:
            logger.warning("[*] has_plot backfill pass failed（不影響掃描結果）", exc_info=True)

        return {
            'inserted': inserted,
            'updated': updated,
            'deleted': deleted_count,
            'total': repo.count()
        }

    def scan_directory(self, directory: str, recursive: bool = True,
                       relative_path: bool = True,
                       min_size_mb: int = 0,
                       cache: Dict[str, dict] = None,
                       progress_callback: callable = None,
                       video_extensions: set = None) -> Tuple[List[VideoInfo], dict]:
        """掃描資料夾

        Args:
            directory: 要掃描的資料夾路徑
            recursive: 是否遞迴掃描子資料夾
            relative_path: 是否使用相對路徑
            min_size_mb: 最小檔案大小 (MB)
            cache: 緩存字典，用於增量更新
            progress_callback: 進度回調函數，簽名: (current, total, filename) -> None
            video_extensions: 影片副檔名集合（預設使用 VIDEO_EXTENSIONS）

        Returns:
            Tuple[List[VideoInfo], dict]: (影片列表, 統計資訊)
            統計資訊包含: cache_hits, cache_misses, deleted
        """
        directory = Path(directory)
        if not directory.exists():
            raise ValueError(f"資料夾不存在: {directory}")

        videos = []
        base_path = str(directory) if relative_path else None
        min_size_bytes = min_size_mb * 1024 * 1024
        use_cache = cache is not None
        extensions = video_extensions if video_extensions is not None else VIDEO_EXTENSIONS

        # 使用 fast_scan_directory 一次取得所有檔案資訊
        # 這大幅減少對 NAS 的系統呼叫次數
        logger.info("[*] 快速掃描目錄中...")
        all_files = fast_scan_directory(str(directory), extensions, min_size_bytes)
        logger.info(f"[*] 找到 {len(all_files)} 個影片檔案")

        # 統計緩存命中
        cache_hits = 0
        cache_misses = 0
        current_paths = set()

        # 批次比對緩存
        for i, file_info in enumerate(all_files, 1):
            path_key = file_info['path']
            file_mtime = file_info['mtime']
            nfo_mtime = file_info.get('nfo_mtime', 0)
            current_paths.add(path_key)

            # 檢查緩存（同時比對影片和 NFO 的 mtime）
            cached = cache.get(path_key) if use_cache else None
            cache_valid = (cached and
                           cached.get('mtime') == file_mtime and
                           cached.get('nfo_mtime', 0) == nfo_mtime)

            video_name = os.path.basename(path_key)

            # 回報進度
            if progress_callback:
                progress_callback(i, len(all_files), video_name)

            if cache_valid:
                # 緩存命中，直接使用
                info = VideoInfo.from_dict(cached['info'])
                videos.append(info)
                cache_hits += 1
            else:
                # 緩存未命中，重新解析
                logger.info(f"[{i}/{len(all_files)}] 處理: {video_name}")
                try:
                    info = self.scan_file(path_key, base_path)
                    videos.append(info)
                    cache_misses += 1

                    # 更新緩存（包含 NFO mtime）
                    if use_cache:
                        cache[path_key] = {
                            'mtime': file_mtime,
                            'nfo_mtime': nfo_mtime,
                            'info': info.to_dict()
                        }
                except Exception as e:
                    logger.warning(f"  [!] 錯誤: {e}")

        # 清理已刪除檔案的緩存
        deleted_count = 0
        if use_cache:
            deleted_keys = [k for k in cache.keys() if k not in current_paths]
            for k in deleted_keys:
                del cache[k]
            deleted_count = len(deleted_keys)
            if deleted_keys:
                logger.info(f"[*] 清理 {deleted_count} 個已刪除檔案的緩存")

        # 顯示緩存統計
        if use_cache:
            logger.info(f"[*] 緩存: 命中 {cache_hits}, 新增/更新 {cache_misses}")

        stats = {
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'deleted': deleted_count
        }
        return videos, stats


def _validate_sample_images(sample_images: list, video_path: str = "", path_mappings: dict = None) -> list:
    """驗證 sample_images 中的 file:/// URI 對應磁碟檔案存在性。
    不存在的項目剔除；uri_to_fs_path 轉換失敗也視為不存在（但 log warning）。
    非 file:/// 且非 http:// / https:// 格式（相對路徑、絕對 FS 路徑等）原樣保留 —
    cleanup pass 只管 file:/// URI 的磁碟失效情境。
    http:// / https:// 遠端 URL 為 Codex P1 修前 scraper URL 污染，一律清除。

    TASK-91-T2b #16：path_mappings 預設 None，WSL+UNC mapping 環境下反解成真正
    能 open() 的本機路徑再判斷存在性（減少誤刪合法映射端 sample_images）。
    """
    valid = []
    non_file_purged = 0
    for uri in sample_images:
        # 清除 scraper 遠端 URL 污染（pre-fix bug 寫入的 http:// / https://）
        if uri.startswith('http://') or uri.startswith('https://'):
            non_file_purged += 1
            continue
        # 只 validate file:/// URI；其他格式（migration 帶入的相對路徑、
        # 舊絕對 FS 路徑等）原樣保留，不做磁碟檢查
        if not uri.startswith('file:///'):
            valid.append(uri)
            continue
        try:
            fs = uri_to_local_fs_path(uri, path_mappings)
        except Exception as e:
            logger.warning(
                "uri_to_fs_path failed for sample_image; treating as missing. "
                "video=%s uri=%r error=%s: %s",
                video_path, uri, type(e).__name__, e,
            )
            continue
        if os.path.exists(fs):
            valid.append(uri)
        else:
            logger.debug(
                "sample_image missing on disk; removing from DB. video=%s uri=%r fs=%s",
                video_path, uri, fs,
            )
    if non_file_purged > 0:
        logger.info(
            "[sample_images cleanup] %s: purged %d non-file:// URI entries",
            video_path, non_file_purged,
        )
    return valid


def _run_sample_images_cleanup_pass(repo, path_mappings: dict = None) -> int:
    """一次性孤兒清理 pass：驗證所有 Video row 的 sample_images URI，
    不存在的剔除，寫回 DB。回傳清理的 row 數。
    共用於 scan_to_sqlite() + generate_avlist() 兩個流程（Canonical Decision #4）。
    """
    all_videos = repo.get_all()
    cleaned_count = 0
    for video in all_videos:
        if not video.sample_images:
            continue
        validated = _validate_sample_images(video.sample_images, video_path=video.path, path_mappings=path_mappings)
        if validated != video.sample_images:
            removed = len(video.sample_images) - len(validated)
            logger.info(
                "cleanup: removing %d orphan sample_images from video=%s",
                removed, video.path,
            )
            repo.update_sample_images(video.path, validated)
            cleaned_count += 1
    if cleaned_count > 0:
        logger.info("cleanup pass done: %d videos had orphan sample_images cleaned", cleaned_count)
    return cleaned_count


def main():
    """測試用"""
    import sys
    from core.logger import setup_logging
    setup_logging()

    if len(sys.argv) < 2:
        print("用法: python scanner.py <資料夾路徑>")
        sys.exit(1)

    scanner = VideoScanner()
    videos, stats = scanner.scan_directory(sys.argv[1])

    logger.info(f"\n=== 掃描結果 ({len(videos)} 部) ===")
    logger.info(f"統計: 緩存命中 {stats['cache_hits']}, 新增/更新 {stats['cache_misses']}")
    for v in videos[:10]:  # 只顯示前 10 部
        logger.info(f"  {v.num or 'N/A'}: {v.title[:50]}...")
        if v.actor:
            logger.info(f"    演員: {v.actor}")


if __name__ == "__main__":
    main()
