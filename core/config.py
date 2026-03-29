"""
core/config.py — 設定載入 / 儲存 / 遷移邏輯

提供：
- CONFIG_PATH, CONFIG_DEFAULT_PATH  — 設定檔路徑常數
- AppConfig（及全部子 schema）     — Pydantic 設定 schema
- load_config()                    — 載入設定，含完整 migration 邏輯
- save_config()                    — 儲存設定至 config.json
"""

import json
from pathlib import Path
from typing import Literal, Optional, List

from pydantic import BaseModel

from core.logger import get_logger
from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS

logger = get_logger(__name__)

# 設定檔路徑（相對於 project root，即此檔案所在 core/ 的上層）
_PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _PROJECT_ROOT / "web" / "config.json"
CONFIG_DEFAULT_PATH = _PROJECT_ROOT / "web" / "config.default.json"


# ============ Pydantic Schema ============

class ScraperConfig(BaseModel):
    create_folder: bool = True
    folder_layers: List[str] = ["{actor}"]
    folder_format: str = "{actor}"
    filename_format: str = "{num} {title}"
    download_cover: bool = True
    cover_filename: str = "poster.jpg"
    create_nfo: bool = True
    max_title_length: int = 50
    max_filename_length: int = 60
    video_extensions: List[str] = list(DEFAULT_VIDEO_EXTENSIONS)
    suffix_keywords: List[str] = ["-cd1", "-cd2", "-4k", "-uc"]
    jellyfin_mode: bool = False


class SearchConfig(BaseModel):
    search_filter: str = ""
    gallery_mode_enabled: bool = True  # Grid 模式開關（toggle 可見 + 女優自動切 Grid）
    uncensored_mode_enabled: bool = False  # 無碼模式 - 只搜尋 AVSOX / FC2
    favorite_folder: str = ""  # 我的最愛資料夾 - 空字串 = 使用系統下載資料夾
    proxy_url: str = ""
    primary_source: str = "javbus"  # 主要搜尋來源: "javbus" | "dmm"


class SourceLinksConfig(BaseModel):
    """各來源連結開關；官方/合法來源預設 true，含盜版連結的站台預設 false"""
    dmm: bool = True
    d2pass: bool = True
    heyzo: bool = True
    fc2: bool = True
    javbus: bool = False
    jav321: bool = False
    javdb: bool = False
    avsox: bool = False


class OllamaConfig(BaseModel):
    """串接結構：Ollama 配置"""
    url: str = "http://localhost:11434"
    model: str = "qwen3:8b"  # 所有翻譯（單片/批次）都用此模型


class GeminiConfig(BaseModel):
    """串接結構：Gemini 配置"""
    api_key: str = ""  # Gemini API Key
    model: str = "gemini-flash-lite-latest"  # 預設使用 latest 別名（自動路由可用版本）


class TranslateConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"  # "ollama" | "gemini"
    batch_size: int = 10  # 批次翻譯大小

    # 嵌套結構
    ollama: OllamaConfig = OllamaConfig()
    gemini: GeminiConfig = GeminiConfig()

    # 舊字段（保留向後兼容）
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None


class GalleryConfig(BaseModel):
    directories: List[str] = []
    output_dir: str = "output"
    output_filename: str = "gallery_output.html"
    path_mappings: dict = {}
    min_size_mb: int = 0
    default_mode: str = "image"
    default_sort: str = "date"
    default_order: str = "descending"
    items_per_page: int = 90


class ShowcaseConfig(BaseModel):
    player: str = ""  # 播放器路徑，空字串使用系統預設


class GeneralConfig(BaseModel):
    default_page: str = "search"  # 預設開啟頁面: search, gallery, showcase
    theme: str = "light"  # 主題模式: light, dark
    sidebar_collapsed: bool = False  # 側邊欄預設收合 (僅影響 Desktop)
    tutorial_completed: bool = False  # 新手引導是否已完成
    font_size: str = "md"  # 全站字體大小: xs, sm, md, lg, xl
    locale: Literal["zh-TW", "zh-CN", "ja", "en"] = "zh-TW"  # 介面語系


class AppConfig(BaseModel):
    scraper: ScraperConfig = ScraperConfig()
    search: SearchConfig = SearchConfig()
    source_links: SourceLinksConfig = SourceLinksConfig()
    translate: TranslateConfig = TranslateConfig()
    gallery: GalleryConfig = GalleryConfig()
    showcase: ShowcaseConfig = ShowcaseConfig()
    general: GeneralConfig = GeneralConfig()


# ============ 載入 / 儲存 ============

def load_config() -> dict:
    """載入設定，包含自動遷移邏輯和首次啟動初始化"""
    # 首次啟動：從 config.default.json 初始化
    if not CONFIG_PATH.exists() and CONFIG_DEFAULT_PATH.exists():
        import shutil
        shutil.copy2(CONFIG_DEFAULT_PATH, CONFIG_PATH)
        logger.info("[Config] 首次啟動，已從 config.default.json 初始化設定")

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)

        need_save = False

        # Migration: avlist -> gallery
        if 'avlist' in raw_config and 'gallery' not in raw_config:
            raw_config['gallery'] = raw_config.pop('avlist')
            need_save = True

        # Migration: viewer -> showcase
        if 'viewer' in raw_config and 'showcase' not in raw_config:
            raw_config['showcase'] = raw_config.pop('viewer')
            need_save = True

        # Migration: min_size_kb -> min_size_mb (KB 轉 MB)
        if 'gallery' in raw_config:
            g = raw_config['gallery']
            if 'min_size_kb' in g and 'min_size_mb' not in g:
                # KB -> MB (四捨五入可接受)
                g['min_size_mb'] = int(round(g.get('min_size_kb', 0) / 1024))
                del g['min_size_kb']
                need_save = True

        # Migration: translate 扁平結構 -> 嵌套結構
        if 'translate' in raw_config:
            t = raw_config['translate']

            # 遷移 ollama_url -> ollama.url（優先使用舊值）
            if 'ollama_url' in t or 'ollama_model' in t:
                # 確保 ollama 嵌套存在
                if 'ollama' not in t:
                    t['ollama'] = {}

                # 優先使用舊字段的值來更新嵌套結構（檢查非空）
                if 'ollama_url' in t:
                    url = t.pop('ollama_url')
                    if url:  # 檢查不是 None
                        t['ollama']['url'] = url.rstrip('/')
                    need_save = True
                if 'ollama_model' in t:
                    model = t.pop('ollama_model')
                    if model:  # 檢查不是 None
                        t['ollama']['model'] = model
                    need_save = True

            # 移除舊的 batch_model 字段（Task 1.3.1 清理）
            if 'ollama' in t and isinstance(t['ollama'], dict) and 'batch_model' in t['ollama']:
                del t['ollama']['batch_model']
                need_save = True

            # 移除廢棄的漸進式翻譯字段（Task 1.3.4 簡化）
            deprecated_fields = ['auto_progressive', 'progressive_first', 'progressive_range']
            for field in deprecated_fields:
                if field in t:
                    del t[field]
                    need_save = True

            # 確保 batch_size 存在
            if 'batch_size' not in t:
                t['batch_size'] = 10
                need_save = True

            # 確保 ollama 嵌套存在
            if 'ollama' not in t:
                t['ollama'] = {
                    'url': 'http://localhost:11434',
                    'model': 'qwen3:8b'
                }
                need_save = True

            # Task 2.4：確保 gemini 嵌套存在（Gemini 支持遷移）
            if 'gemini' not in t:
                t['gemini'] = {
                    'api_key': '',
                    'model': 'gemini-flash-lite-latest'
                }
                need_save = True
                logger.info("[Config] 遷移配置：添加 Gemini 支持")

        # Migration: folder_format → folder_layers（舊版只存 folder_format）
        s = raw_config.get('scraper', {})
        if 'folder_layers' not in s and 'folder_format' in s:
            fmt = s['folder_format'].replace('\\', '/')
            s['folder_layers'] = [p.strip() for p in fmt.split('/') if p.strip()]
            need_save = True

        # 確保 scraper.suffix_keywords 存在（Fix-1 版本標記）
        s = raw_config.get('scraper', {})
        if 'suffix_keywords' not in s:
            s['suffix_keywords'] = ['-cd1', '-cd2', '-4k', '-uc']
            need_save = True

        # 確保 scraper.jellyfin_mode 存在（Fix-6 Jellyfin 圖片模式）
        s = raw_config.get('scraper', {})
        if 'jellyfin_mode' not in s:
            s['jellyfin_mode'] = False
            need_save = True

        # Migration: source_links 區段新增 + 深層合併保證（T18b-pre）
        sl_defaults = SourceLinksConfig().model_dump()
        if 'source_links' not in raw_config or not isinstance(raw_config.get('source_links'), dict):
            # 層 1：整個區段缺少，或值不是 dict（如 null）→ 補整個預設 dict
            raw_config['source_links'] = sl_defaults
            need_save = True
        else:
            # 層 2：區段存在但個別 key 缺少 → 逐一補缺少的 key
            sl = raw_config['source_links']
            for key, default_val in sl_defaults.items():
                if key not in sl:
                    sl[key] = default_val
                    need_save = True

        # Migration: primary_source 補齊（Phase 36 T4）
        if 'search' not in raw_config or not isinstance(raw_config.get('search'), dict):
            raw_config['search'] = {}
        search_section = raw_config['search']
        if 'primary_source' not in search_section:
            search_section['primary_source'] = 'javbus'
            need_save = True

        # Save migrated config
        if need_save:
            save_config(raw_config)

        return raw_config
    # 返回預設設定（沒有 default 檔案時）
    return AppConfig().model_dump()


def save_config(config: dict) -> None:
    """儲存設定"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
