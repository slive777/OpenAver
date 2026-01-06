"""
設定 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import json

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


class AppConfig(BaseModel):
    scraper: ScraperConfig = ScraperConfig()
    search: SearchConfig = SearchConfig()
    translate: TranslateConfig = TranslateConfig()


def load_config() -> dict:
    """載入設定"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
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
