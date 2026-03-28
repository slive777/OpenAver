"""
設定 API 路由

端點：
- GET    /api/config                    — 取得所有設定
- PUT    /api/config                    — 更新所有設定
- DELETE /api/config                    — 恢復原廠設定（刪除 config.json）
- GET    /api/tutorial-status           — 取得新手引導完成狀態
- POST   /api/tutorial-completed        — 標記新手引導已完成
- POST   /api/tutorial-reset            — 重置新手引導狀態
- PUT    /api/config/general/{field}    — 更新 general 區塊單一欄位（sidebar_collapsed/theme/font_size）
- GET    /api/version                   — 取得應用程式版本資訊
- GET    /api/config/format-variables   — 取得刮削路徑/檔名格式可用變數
- GET    /api/ollama/models             — 取得 Ollama 可用模型列表
- POST   /api/ollama/test               — 測試 Ollama 模型是否能正常回應
- POST   /api/proxy/test                — 測試 Proxy 連線（透過 DMM 驗證）
"""

from fastapi import APIRouter
from pydantic import BaseModel
import httpx

from core.logger import get_logger
from core import config as _core_config
from core.config import (
    AppConfig,
    ScraperConfig,
    SearchConfig,
    OllamaConfig,
    GeminiConfig,
    TranslateConfig,
    GalleryConfig,
    ShowcaseConfig,
    GeneralConfig,
    load_config,
    save_config,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["config"])

# Import reset function (避免循環導入，在需要時才導入)
def _reset_translate_service():
    """延遲導入並調用 reset_translate_service()"""
    from web.routers.translate import reset_translate_service
    reset_translate_service()


@router.get("/config")
async def get_config() -> dict:
    """取得所有設定"""
    return {"success": True, "data": load_config()}


@router.put("/config")
async def update_config(config: AppConfig) -> dict:
    """更新所有設定"""
    try:
        save_config(config.model_dump())
        _reset_translate_service()  # 重置翻譯服務，讓新配置生效
        return {"success": True, "message": "設定已儲存"}
    except Exception as e:
        logger.error("儲存設定失敗: %s", e)
        return {"success": False, "error": "儲存設定失敗"}


@router.delete("/config")
async def reset_config() -> dict:
    """恢復原廠設定 - 刪除 config.json"""
    try:
        if _core_config.CONFIG_PATH.exists():
            _core_config.CONFIG_PATH.unlink()
        _reset_translate_service()  # 清除舊服務實例
        return {"success": True, "message": "已恢復預設設定"}
    except Exception as e:
        logger.error("恢復預設設定失敗: %s", e)
        return {"success": False, "error": "恢復預設設定失敗"}


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


class GeneralFieldRequest(BaseModel):
    value: str | bool


@router.put("/config/general/{field}")
async def update_general_field(field: str, request: GeneralFieldRequest) -> dict:
    """更新 general 區塊單一欄位（輕量端點，供 UI toggle 即時同步）"""
    allowed = {"sidebar_collapsed", "theme", "font_size"}
    if field not in allowed:
        return {"success": False, "error": f"不允許更新欄位: {field}"}
    try:
        config = load_config()
        if "general" not in config:
            config["general"] = {}
        config["general"][field] = request.value
        save_config(config)
        return {"success": True}
    except Exception as e:
        logger.error("更新設定欄位失敗: %s", e)
        return {"success": False, "error": "更新設定欄位失敗"}


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
            {"name": "{suffix}", "description": "版本標記（自動偵測）", "example": "-4k"},
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
        logger.error("取得 Ollama 模型列表失敗: %s", e)
        return {"success": False, "error": "取得模型列表失敗"}


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
                        {"role": "user", "content": "將以下日文翻譯成繁體中文，只輸出翻譯結果：新人女優デビュー"}
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": 500,  # think mode 需要足夠 token（翻譯本身 ~20 tok，其餘供推理）
                        "temperature": 0.3
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
        logger.error("測試 Ollama 模型失敗: %s", e)
        return {"success": False, "error": "測試模型失敗"}


class ProxyTestRequest(BaseModel):
    proxy_url: str


@router.post("/proxy/test")
def test_proxy(request: ProxyTestRequest) -> dict:
    """測試 Proxy 連線（透過 DMM GraphQL endpoint 驗證）"""
    import requests

    is_direct = request.proxy_url.strip().lower() == 'direct'
    if is_direct:
        proxies = {}
        success_message = "直連測試成功（DMM 可達）"
        non_jp_message = "直連可達，但 DMM 回傳 403（非日本 IP，建議使用 Proxy）"
    else:
        proxies = {'http': request.proxy_url, 'https': request.proxy_url}
        success_message = "Proxy 連線成功（DMM 可達）"
        non_jp_message = "Proxy 連線成功，但 DMM 回傳 403（可能非日本 IP）"

    try:
        resp = requests.post(
            "https://api.video.dmm.co.jp/graphql",
            json={"query": "{ __typename }"},
            headers={"Content-Type": "application/json"},
            proxies=proxies,
            timeout=10
        )
        if resp.status_code == 200:
            return {"success": True, "reason": "ok", "message": success_message}
        elif resp.status_code == 403:
            return {"success": False, "reason": "non_jp", "message": non_jp_message}
        else:
            return {"success": False, "reason": "unexpected_status", "message": f"DMM 回傳異常狀態碼: {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 連線逾時"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 無法連線到目標主機"}
    except Exception:
        return {"success": False, "reason": "unreachable", "message": "連線失敗: 請檢查輸入格式"}
