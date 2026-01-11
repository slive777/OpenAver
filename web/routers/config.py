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
    auto_search_on_drop: bool = True
    search_filter: str = ""


class TranslateConfig(BaseModel):
    enabled: bool = False
    provider: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"


class GalleryConfig(BaseModel):
    directories: List[str] = []
    output_dir: str = "output"
    output_filename: str = "gallery_output.html"
    path_mappings: dict = {}
    min_size_kb: int = 0
    default_mode: str = "image"
    default_sort: str = "date"
    default_order: str = "descending"
    items_per_page: int = 90


class ShowcaseConfig(BaseModel):
    player: str = ""  # 播放器路徑，空字串使用系統預設


class GeneralConfig(BaseModel):
    default_page: str = "search"  # 預設開啟頁面: search, gallery, showcase
    theme: str = "light"  # 主題模式: light, dark


class AppConfig(BaseModel):
    scraper: ScraperConfig = ScraperConfig()
    search: SearchConfig = SearchConfig()
    translate: TranslateConfig = TranslateConfig()
    gallery: GalleryConfig = GalleryConfig()
    showcase: ShowcaseConfig = ShowcaseConfig()
    general: GeneralConfig = GeneralConfig()


def load_config() -> dict:
    """載入設定，包含自動遷移邏輯"""
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

        # Save migrated config
        if need_save:
            save_config(raw_config)

        return raw_config
    # 返回預設設定
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
                        {"role": "user", "content": "/no_think\n翻譯：テスト"}
                    ],
                    "stream": False
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
