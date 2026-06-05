"""
core/config.py — 設定載入 / 儲存 / 遷移邏輯

提供：
- CONFIG_PATH, CONFIG_DEFAULT_PATH  — 設定檔路徑常數
- AppConfig（及全部子 schema）     — Pydantic 設定 schema
- load_config()                    — 載入設定，含完整 migration 邏輯
- save_config()                    — 儲存設定至 config.json
"""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Literal, Optional, List

from pydantic import BaseModel, Field

from core.logger import get_logger
from core.source_config import SourceConfig, get_builtin_sources
from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS

logger = get_logger(__name__)

# 設定檔路徑（相對於 project root，即此檔案所在 core/ 的上層）
_PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _PROJECT_ROOT / "web" / "config.json"
CONFIG_DEFAULT_PATH = _PROJECT_ROOT / "web" / "config.default.json"

# 66 TASK-66b-T1（CD-66b-1）：process-wide config.json 寫入序列化鎖。
# async-offload 把 def 路由移到 threadpool thread 後，event loop 的隱式互斥消失，
# load_config→mutate→save_config 的 RMW 變成真並發 → lost-update（Race A）。
# 必須是 threading.Lock（非 asyncio.Lock）：def 路由跑在 threadpool thread，
# asyncio.Lock 保護不到；且 plain Lock（非 RLock）—— public locked / private
# unlocked 嚴格分層，鎖內絕不二次 acquire（mutator 契約禁呼 public API）。
_config_write_lock = threading.Lock()


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
    download_sample_images: bool = False


class SearchConfig(BaseModel):
    search_filter: str = ""
    uncensored_mode_enabled: bool = False  # deprecated: read via core.source_settings.is_uncensored_mode_effective()
    favorite_folder: str = ""  # 我的最愛資料夾 - 空字串 = 使用系統下載資料夾
    proxy_url: str = ""


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


class OpenAIConfig(BaseModel):
    """串接結構：OpenAI Compatible 配置"""
    base_url: str = ""   # e.g. "https://api.openai.com/v1"
    api_key: str = ""    # 可為空（本地 LLM 不需要）
    model: str = "gpt-4o-mini"
    use_custom_model: bool = False


class MetatubeConfig(BaseModel):
    """串接結構：Metatube HTTP server 配置（CD-63b-3）"""
    enabled: bool = False  # 使用者在 Settings › Advanced 啟用 metatube（CD-63b-3）
    url: str = ""    # metatube server URL (persisted; runtime connected state NOT stored here)
    token: str = ""  # API token（空字串 = 不需驗證）
    allow_lan: bool = False  # 允許連線至 LAN IP（TASK-63e-1：startup 重連沿用用戶當初的選擇）


class TranslateConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"  # "ollama" | "gemini" | "openai"
    batch_size: int = 10  # 批次翻譯大小

    # 嵌套結構
    ollama: OllamaConfig = OllamaConfig()
    gemini: GeminiConfig = GeminiConfig()
    openai: OpenAIConfig = OpenAIConfig()

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
    sources: list[SourceConfig] = Field(default_factory=get_builtin_sources)
    advanced_search_enabled: bool = False  # 進階搜尋 picker（TASK-61c-7）；Pydantic default 自動補缺漏
    metatube: MetatubeConfig = MetatubeConfig()  # CD-63b-3；Pydantic default 自動補缺漏（no migration needed）


# ============ 載入 / 儲存 ============

def _load_config_unlocked() -> dict:
    """載入設定（含 migration / first-init），**不取鎖** —— caller 須已持有 _config_write_lock。

    migration 的寫回必須走 _save_config_unlocked（同樣不取鎖），否則在已持鎖的
    critical section 內再 acquire 同一 threading.Lock → 自我死鎖（CD-66b-1）。
    """
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

            # Task T2：確保 openai 嵌套存在（OpenAI Compatible 支援遷移）
            if 'openai' not in t:
                t['openai'] = {
                    'base_url': '',
                    'api_key': '',
                    'model': 'gpt-4o-mini'
                }
                need_save = True
                logger.info("[Config] 遷移配置：添加 OpenAI Compatible 支持")

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

        # 確保 scraper.download_sample_images 存在（Task 38e 拆分 extrafanart 下載）
        s = raw_config.get('scraper', {})
        if 'download_sample_images' not in s:
            s['download_sample_images'] = False
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

        # Migration: primary_source 一次性移除（feature/65 CD-plan-65-7）
        # 欄位已徹底移除；load_config() 直接 return raw dict（不 model_validate），
        # 故舊 config.json 殘留的 primary_source key 不會被 Pydantic 自動剝除 → 顯式 strip。
        if 'search' not in raw_config or not isinstance(raw_config.get('search'), dict):
            raw_config['search'] = {}
        search_section = raw_config['search']
        if 'primary_source' in search_section:
            del search_section['primary_source']
            need_save = True

        # Migration: sources 段（TASK-61a-2）— US1-critical，fail-open
        # 缺段 → 8 builtin 全 enabled（不讀 source_links，CD-61-6）；
        # uncensored_mode_enabled=true 升級 → 4 有碼初始 disabled（CD-61-7）；
        # 合法既有段 → 冪等不動；損壞 → 備份 sources_bak + 重設全 enabled + warning。
        try:
            from core.scrapers.utils import CENSORED_SOURCES

            def _default_sources() -> list:
                return [s.model_dump() for s in get_builtin_sources()]

            def _is_valid_sources(value) -> bool:
                if not isinstance(value, list) or not value:
                    return False
                for item in value:
                    if not isinstance(item, dict):
                        return False
                    if not isinstance(item.get('id'), str):
                        return False
                    if not isinstance(item.get('enabled'), bool):
                        return False
                    # Full schema validation: catch any field-level corruption
                    # (e.g. wrong types, missing required fields) that id/enabled
                    # checks above cannot detect. On any error → treat segment as
                    # corrupt → existing fallback regenerates 8 builtin + backs up.
                    try:
                        SourceConfig.model_validate(item)
                    except Exception:
                        return False
                return True

            if 'sources' not in raw_config:
                # 缺段：生成 8 builtin 全 enabled
                new_sources = _default_sources()
                # uncensored 轉換（僅缺段升級時觸發，冪等）
                if raw_config.get('search', {}).get('uncensored_mode_enabled') is True:
                    for item in new_sources:
                        if item.get('id') in CENSORED_SOURCES:
                            item['enabled'] = False
                raw_config['sources'] = new_sources
                need_save = True
            elif _is_valid_sources(raw_config.get('sources')):
                # 合法既有段：冪等，不動
                pass
            else:
                # 損壞：備份原值（不覆寫首次備份）+ 重設全 enabled
                if 'sources_bak' not in raw_config:
                    raw_config['sources_bak'] = raw_config.get('sources')
                logger.warning(
                    "[Config] sources 段格式不合法，已備份至 sources_bak 並重設為預設值"
                )
                raw_config['sources'] = _default_sources()
                need_save = True
        except Exception as exc:  # fail-open：絕不讓啟動失敗
            logger.warning("[Config] sources migration 發生例外，套用安全預設：%s", exc)
            try:
                raw_config['sources'] = [s.model_dump() for s in get_builtin_sources()]
            except Exception:
                raw_config['sources'] = []
            need_save = True

        # Save migrated config（已持鎖 → 用 unlocked 版避免自我死鎖）
        if need_save:
            _save_config_unlocked(raw_config)

        return raw_config
    # 返回預設設定（沒有 default 檔案時）
    return AppConfig().model_dump()


def load_config() -> dict:
    """載入設定，包含自動遷移邏輯和首次啟動初始化（process-wide 序列化）"""
    with _config_write_lock:
        return _load_config_unlocked()


def _save_config_unlocked(config: dict) -> None:
    """原子寫 config.json，**不取鎖** —— caller 須已持有 _config_write_lock。

    tempfile.mkstemp 在 CONFIG_PATH 同目錄（同卷）建臨時檔 → fd 寫完關閉後
    os.replace（POSIX/Windows 皆原子）。任何例外都清掉 temp 殘檔後 re-raise，
    避免半寫的 *.tmp 殘留。fd 必須在 os.replace 前關閉（Windows file-lock）。
    """
    fd, tmp = tempfile.mkstemp(dir=CONFIG_PATH.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        # fd 已由 with 區塊關閉 → 安全 replace
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        # 清掉殘留 temp（best-effort）後 re-raise
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_config(config: dict) -> None:
    """儲存設定（原子寫 + process-wide 序列化）"""
    with _config_write_lock:
        _save_config_unlocked(config)


def mutate_config(mutator: Callable[[dict], None]) -> None:
    """在單一 critical section 內 read-modify-write config.json（消除 RMW 競態）。

    load → mutator(cfg)（原地修改 dict）→ save 全程持 _config_write_lock，
    兩個並發 mutate_config 不再讀到同一 v0 → 無 lost-update（Race A）。

    mutator 契約：`mutator(cfg: dict) -> None`，僅做純記憶體 dict 操作；
    **不得**呼叫任何 public locked API（load_config / save_config /
    mutate_config / reset_config_file）—— 會在已持鎖時二次 acquire → 自我死鎖。
    """
    with _config_write_lock:
        cfg = _load_config_unlocked()
        mutator(cfg)
        _save_config_unlocked(cfg)


def reset_config_file() -> None:
    """刪除 config.json（恢復原廠）—— 在鎖內檢查 + 刪除，無 exists/unlink TOCTOU。"""
    with _config_write_lock:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
