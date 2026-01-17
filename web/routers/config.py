"""
設定 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import json
import httpx

router = APIRouter(prefix="/api", tags=["config"])

# 設定檔路徑
CONFIG_PATH = Path(__file__).parent.parent / "config.json"
CONFIG_DEFAULT_PATH = Path(__file__).parent.parent / "config.default.json"


class ScraperConfig(BaseModel):
    create_folder: bool = True
    folder_format: str = "{num}"
    filename_format: str = "{num} {title}"
    download_cover: bool = True
    cover_filename: str = "poster.jpg"
    create_nfo: bool = True
    max_title_length: int = 80
    max_filename_length: int = 200
    video_extensions: List[str] = [".mp4", ".avi", ".mkv", ".wmv", ".rmvb", ".flv", ".mov", ".m4v", ".ts"]


class SearchConfig(BaseModel):
    search_filter: str = ""
    gallery_mode_enabled: bool = False  # 女優畫廊模式 (Beta) - 預設關閉
    favorite_folder: str = ""  # 我的最愛資料夾 - 空字串 = 使用系統下載資料夾


class OllamaConfig(BaseModel):
    """串接結構：Ollama 配置"""
    url: str = "http://localhost:11434"
    model: str = "qwen3:8b"  # 所有翻譯（單片/批次）都用此模型


class TranslateConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"

    # Task 1.2, 1.3 新增字段
    auto_progressive: bool = True
    progressive_first: bool = True
    progressive_range: List[int] = [2, 10]
    batch_size: int = 10

    # 嵌套結構
    ollama: OllamaConfig = OllamaConfig()

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


class AppConfig(BaseModel):
    scraper: ScraperConfig = ScraperConfig()
    search: SearchConfig = SearchConfig()
    translate: TranslateConfig = TranslateConfig()
    gallery: GalleryConfig = GalleryConfig()
    showcase: ShowcaseConfig = ShowcaseConfig()
    general: GeneralConfig = GeneralConfig()


def load_config() -> dict:
    """載入設定，包含自動遷移邏輯和首次啟動初始化"""
    # 首次啟動：從 config.default.json 初始化
    if not CONFIG_PATH.exists() and CONFIG_DEFAULT_PATH.exists():
        import shutil
        shutil.copy2(CONFIG_DEFAULT_PATH, CONFIG_PATH)
        print(f"[Config] 首次啟動，已從 config.default.json 初始化設定")

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

            # 遷移 ollama_url -> ollama.url
            if 'ollama_url' in t and 'ollama' not in t:
                t['ollama'] = {
                    'url': t.get('ollama_url', 'http://localhost:11434'),
                    'model': t.get('ollama_model', 'qwen3:8b')
                }
                # 刪除舊字段
                t.pop('ollama_url', None)
                t.pop('ollama_model', None)
                need_save = True

            # 移除舊的 batch_model 字段（Task 1.3.1 清理）
            if 'ollama' in t and isinstance(t['ollama'], dict) and 'batch_model' in t['ollama']:
                del t['ollama']['batch_model']
                need_save = True

            # 補充缺少的新字段
            defaults = {
                'auto_progressive': True,
                'progressive_first': True,
                'progressive_range': [2, 10],
                'batch_size': 10
            }
            for key, default_value in defaults.items():
                if key not in t:
                    t[key] = default_value
                    need_save = True

            # 確保 ollama 嵌套存在
            if 'ollama' not in t:
                t['ollama'] = {
                    'url': 'http://localhost:11434',
                    'model': 'qwen3:8b'
                }
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


@router.get("/config")
async def get_config() -> dict:
    """取得所有設定"""
    return {"success": True, "data": load_config()}


@router.put("/config")
async def update_config(config: AppConfig) -> dict:
    """更新所有設定"""
    try:
        save_config(config.model_dump())
        return {"success": True, "message": "設定已儲存"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/config")
async def reset_config() -> dict:
    """恢復原廠設定 - 刪除 config.json"""
    try:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        return {"success": True, "message": "已恢復預設設定"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/tutorial-status")
async def get_tutorial_status() -> dict:
    """取得新手引導完成狀態"""
    config = load_config()
    completed = config.get("general", {}).get("tutorial_completed", False)
    return {"success": True, "completed": completed}


@router.post("/tutorial-completed")
async def mark_tutorial_completed() -> dict:
    """標記新手引導已完成（僅在點擊完成時呼叫）"""
    config = load_config()
    if "general" not in config:
        config["general"] = {}
    config["general"]["tutorial_completed"] = True
    save_config(config)
    return {"success": True}


@router.post("/tutorial-reset")
async def reset_tutorial() -> dict:
    """重置新手引導狀態（供設定頁使用）"""
    config = load_config()
    if "general" not in config:
        config["general"] = {}
    config["general"]["tutorial_completed"] = False
    save_config(config)
    return {"success": True}


@router.get("/version")
async def get_version() -> dict:
    """取得版本資訊"""
    from core.version import VERSION_INFO
    return {"success": True, **VERSION_INFO}


@router.get("/config/format-variables")
async def get_format_variables() -> dict:
    """取得可用的格式變數"""
    return {
        "variables": [
            {"name": "{num}", "description": "番號", "example": "SONE-205"},
            {"name": "{title}", "description": "標題", "example": "新人出道..."},
            {"name": "{actor}", "description": "演員（第一位）", "example": "三上悠亜"},
            {"name": "{actors}", "description": "所有演員", "example": "三上悠亜, 明日花"},
            {"name": "{maker}", "description": "片商", "example": "S1"},
            {"name": "{date}", "description": "發行日期", "example": "2024-01-15"},
            {"name": "{year}", "description": "年份", "example": "2024"},
        ]
    }


@router.get("/ollama/models")
async def get_ollama_models(url: str) -> dict:
    """取得 Ollama 可用模型列表"""
    try:
        # 確保 URL 格式正確
        url = url.rstrip('/')
        api_url = f"{url}/api/tags"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url)
            resp.raise_for_status()
            data = resp.json()

            models = [m['name'] for m in data.get('models', [])]
            return {"success": True, "models": models}

    except httpx.TimeoutException:
        return {"success": False, "error": "連線逾時"}
    except httpx.ConnectError:
        return {"success": False, "error": "無法連線到 Ollama"}
    except Exception as e:
        return {"success": False, "error": str(e)}


class OllamaTestRequest(BaseModel):
    url: str
    model: str


@router.post("/ollama/test")
async def test_ollama_model(request: OllamaTestRequest) -> dict:
    """測試 Ollama 模型是否能正常回應"""
    try:
        url = request.url.rstrip('/')

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/chat",
                json={
                    "model": request.model,
                    "messages": [
                        {"role": "system", "content": "你是翻譯助手"},
                        {"role": "user", "content": "翻譯：テスト"}
                    ],
                    "stream": False,
                    "options": {
                        "thinking": False  # 禁用 Qwen3 thinking 模式，加速測試
                    }
                }
            )
            resp.raise_for_status()
            data = resp.json()

            result = data.get("message", {}).get("content", "").strip()
            if result:
                return {"success": True, "result": f"回應：{result}"}
            else:
                return {"success": False, "error": "模型無回應"}

    except httpx.TimeoutException:
        return {"success": False, "error": "連線逾時"}
    except httpx.ConnectError:
        return {"success": False, "error": "無法連線到 Ollama"}
    except Exception as e:
        return {"success": False, "error": str(e)}
