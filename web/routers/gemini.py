"""
Gemini API 路由 - 提供測試和模型查詢功能

端點：
- POST /api/gemini/test - 測試 API Key 並獲取可用模型
"""

from core.logger import get_logger
from core.config import load_config
from core.translate_service import LANGUAGE_PROMPTS

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from typing import List

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gemini", tags=["gemini"])

ALLOWED_GEMINI_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
]


class TestRequest(BaseModel):
    """測試 Gemini API Key 請求"""
    api_key: str


class ModelInfo(BaseModel):
    """模型資訊"""
    name: str
    display_name: str
    description: str = ""


class TestResponse(BaseModel):
    """測試響應"""
    success: bool
    models: List[ModelInfo] = []
    count: int = 0
    error: str = ""


class TestTranslateRequest(BaseModel):
    """測試翻譯請求"""
    api_key: str
    model: str = "gemini-flash-lite-latest"


class TestTranslateResponse(BaseModel):
    """測試翻譯響應"""
    success: bool
    translation: str = ""
    error: str = ""  # Google 的原始錯誤訊息


@router.post("/test", response_model=TestResponse)
async def test_gemini_connection(request: TestRequest):
    """
    測試 Gemini API Key 並獲取可用模型

    測試流程：
    1. 調用 Gemini API 獲取模型列表
    2. 以 ALLOWED_GEMINI_MODELS allowlist 過濾（保持 allowlist 定義順序）
    3. 返回模型列表

    Args:
        request: 包含 API Key 的請求

    Returns:
        TestResponse: 包含成功狀態和模型列表
    """
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API Key is required")

    try:
        # 調用 Gemini API 獲取模型列表
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": request.api_key}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()

        data = response.json()

        # 以 allowlist 過濾並保持 allowlist 順序
        api_models = {}
        for model in data.get("models", []):
            name = model.get("name", "").replace("models/", "")
            api_models[name] = model

        allowed_models = []
        for allowed_name in ALLOWED_GEMINI_MODELS:
            if allowed_name in api_models:
                model = api_models[allowed_name]
                allowed_models.append(ModelInfo(
                    name=allowed_name,
                    display_name=model.get("displayName", allowed_name),
                    description=model.get("description", "")[:100]  # 限制長度
                ))

        return TestResponse(
            success=True,
            models=allowed_models,
            count=len(allowed_models)
        )

    except httpx.HTTPStatusError as e:
        error_msg = "Unknown error"

        if e.response.status_code == 400:
            error_msg = "Invalid API Key"
        elif e.response.status_code == 403:
            error_msg = "API Key permission denied"
        elif e.response.status_code == 429:
            error_msg = "Rate limit exceeded"
        else:
            error_msg = f"HTTP {e.response.status_code}"

        return TestResponse(
            success=False,
            error=error_msg
        )

    except httpx.TimeoutException:
        return TestResponse(
            success=False,
            error="Connection timeout"
        )

    except Exception as e:
        logger.error("測試 Gemini 連線失敗: %s", e)
        return TestResponse(
            success=False,
            error="測試 Gemini 連線失敗"
        )



@router.post("/test-translate", response_model=TestTranslateResponse)
async def test_gemini_translate(request: TestTranslateRequest):
    """
    測試 Gemini 實際翻譯功能

    使用安全的測試標題驗證翻譯能力，並返回 Google 的實際錯誤訊息

    Args:
        request: 包含 API Key 和 Model 的請求

    Returns:
        TestTranslateResponse: 包含翻譯結果或 Google 的錯誤訊息
    """
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API Key is required")

    # 使用安全的測試標題（不會觸發內容過濾）
    test_title = "新人女優デビュー"

    config = load_config()
    locale = config.get("general", {}).get("locale", "zh-TW")
    lang_config = LANGUAGE_PROMPTS.get(locale, LANGUAGE_PROMPTS["zh-TW"])
    lang_name = lang_config["name"]

    try:
        # 構建翻譯請求
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"
        headers = {"x-goog-api-key": request.api_key}
        payload = {
            "contents": [{"parts": [{"text": f"請將以下日文翻譯成{lang_name}：{test_title}"}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 50
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        data = response.json()

        # 檢查響應結構
        if "candidates" in data and data["candidates"]:
            # 成功
            translation = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return TestTranslateResponse(
                success=True,
                translation=translation
            )

        elif "error" in data:
            # API 錯誤（返回 Google 的原始錯誤訊息）
            error_msg = data["error"].get("message", "Unknown error")
            return TestTranslateResponse(
                success=False,
                error=error_msg
            )

        elif "promptFeedback" in data:
            # 內容過濾
            block_reason = data.get("promptFeedback", {}).get("blockReason", "UNKNOWN")
            return TestTranslateResponse(
                success=False,
                error=f"內容被過濾: {block_reason}"
            )

        else:
            # 未知響應格式
            return TestTranslateResponse(
                success=False,
                error="未知的響應格式"
            )

    except httpx.HTTPStatusError as e:
        # HTTP 錯誤
        try:
            error_data = e.response.json()
            error_msg = error_data.get("error", {}).get("message", f"HTTP {e.response.status_code}")
        except Exception:
            error_msg = f"HTTP {e.response.status_code}"

        return TestTranslateResponse(
            success=False,
            error=error_msg
        )

    except httpx.TimeoutException:
        return TestTranslateResponse(
            success=False,
            error="連接超時（10秒）"
        )

    except Exception as e:
        logger.error("測試 Gemini 翻譯失敗: %s", e)
        return TestTranslateResponse(
            success=False,
            error="測試 Gemini 翻譯失敗"
        )
