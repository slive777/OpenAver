"""
OpenAI Compatible API 路由 - 提供模型查詢和翻譯測試功能

端點：
- POST /api/openai/models - 查詢可用模型列表
- POST /api/openai/test   - 翻譯測試
"""

from core.logger import get_logger
from core.config import load_config
from core.translate_service import LANGUAGE_PROMPTS

from fastapi import APIRouter
from pydantic import BaseModel
import httpx
from typing import List, Optional

logger = get_logger(__name__)

router = APIRouter(prefix="/api/openai", tags=["openai"])


class ModelsRequest(BaseModel):
    """查詢模型列表請求"""
    base_url: str
    api_key: str = ""


class ModelsResponse(BaseModel):
    """模型列表響應"""
    success: bool
    models: List[str] = []
    error: str = ""


class TestTranslateRequest(BaseModel):
    """翻譯測試請求"""
    base_url: str
    api_key: str = ""
    model: str


class TestTranslateResponse(BaseModel):
    """翻譯測試響應"""
    success: bool
    translation: str = ""
    error: str = ""


@router.post("/models", response_model=ModelsResponse)
async def fetch_openai_models(request: ModelsRequest):
    """
    查詢 OpenAI Compatible API 可用模型列表

    1. GET {base_url}/models
    2. 取 data[].id 回傳模型 ID 列表
    3. 失敗時 graceful fallback（不拋 HTTPException），回 success=False

    Args:
        request: 包含 base_url 和 api_key 的請求

    Returns:
        ModelsResponse: 包含成功狀態和模型列表
    """
    if not request.base_url.strip():
        return ModelsResponse(success=False, error="missing_base_url")

    base_url = request.base_url.rstrip("/")
    headers = {}
    if request.api_key:
        headers["Authorization"] = f"Bearer {request.api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/models", headers=headers)
            response.raise_for_status()

        data = response.json()
        models = [item["id"] for item in data.get("data", []) if "id" in item]
        models.sort()

        return ModelsResponse(success=True, models=models)

    except httpx.HTTPStatusError as e:
        sc = e.response.status_code
        if sc == 401:
            error_key = "auth_failed"
        elif sc == 403:
            error_key = "forbidden"
        elif sc == 404:
            error_key = "not_found"
        elif sc == 429:
            error_key = "rate_limited"
        else:
            error_key = "http_error"
        logger.warning("[OpenAI] 請求失敗: HTTP %s", sc)
        return ModelsResponse(success=False, error=error_key)

    except httpx.TimeoutException:
        logger.warning("[OpenAI] 查詢模型列表逾時")
        return ModelsResponse(success=False, error="connection_timeout")

    except Exception as e:
        logger.warning("[OpenAI] 查詢模型列表失敗: %s", e)
        return ModelsResponse(success=False, error="connection_failed")


@router.post("/test", response_model=TestTranslateResponse)
async def test_openai_translate(request: TestTranslateRequest):
    """
    測試 OpenAI Compatible API 翻譯功能

    使用安全的測試標題驗證翻譯能力

    Args:
        request: 包含 base_url、api_key 和 model 的請求

    Returns:
        TestTranslateResponse: 包含翻譯結果或錯誤訊息
    """
    if not request.base_url.strip():
        return TestTranslateResponse(success=False, error="missing_base_url")

    if not request.model.strip():
        return TestTranslateResponse(success=False, error="missing_model")

    # 使用安全的測試標題（與 gemini.py 行 191 相同）
    test_title = "新人女優デビュー"

    config = load_config()
    locale = config.get("general", {}).get("locale", "zh-TW")

    # F2: ja short-circuit — 與 translate_service.py 的行為保持一致
    if locale == "ja":
        return TestTranslateResponse(
            success=True,
            translation="ja_skip"
        )

    lang_data = LANGUAGE_PROMPTS.get(locale, LANGUAGE_PROMPTS["zh-TW"])
    instruction = lang_data["gemini_instruction"]
    rules = lang_data["gemini_rules"]

    prompt = f"""你是專業的影視資料庫管理員與翻譯引擎。這是既有日文文字的逐字翻譯任務，{instruction}。

原文：
{test_title}

翻譯要求：
{rules}
"""

    base_url = request.base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if request.api_key:
        headers["Authorization"] = f"Bearer {request.api_key}"

    payload = {
        "model": request.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 100
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

        data = response.json()

        choices = data.get("choices")
        if choices and len(choices) > 0:
            translation = choices[0]["message"]["content"].strip()
            if not translation:
                return TestTranslateResponse(success=False, error="empty_response")
            return TestTranslateResponse(success=True, translation=translation)

        elif "error" in data:
            logger.warning("[OpenAI] 測試翻譯 API 回傳錯誤: %s", data["error"])
            return TestTranslateResponse(success=False, error="api_error")

        else:
            return TestTranslateResponse(success=False, error="unknown_response_format")

    except httpx.HTTPStatusError as e:
        sc = e.response.status_code
        if sc == 401:
            error_key = "auth_failed"
        elif sc == 403:
            error_key = "forbidden"
        elif sc == 404:
            error_key = "not_found"
        elif sc == 429:
            error_key = "rate_limited"
        else:
            error_key = "http_error"
        logger.warning("[OpenAI] 請求失敗: HTTP %s", sc)
        return TestTranslateResponse(success=False, error=error_key)

    except httpx.TimeoutException:
        logger.warning("[OpenAI] 測試翻譯逾時")
        return TestTranslateResponse(success=False, error="connection_timeout")

    except Exception as e:
        logger.error("[OpenAI] 測試翻譯失敗: %s", e)
        return TestTranslateResponse(success=False, error="translate_failed")
