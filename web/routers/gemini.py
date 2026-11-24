"""
Gemini API 路由 - 提供測試和模型查詢功能

端點：
- POST /api/gemini/test - 測試 API Key 並獲取可用模型
"""

from core.logger import get_logger
from core.config import load_config
from core.secret_fields import read_secret, resolve_secret
from core.cloud_translate import CLOUD_TRANSLATE_TIMEOUT, TranslateError, settings_error_key
from core.gemini_client import list_models, pick_gemini_models, request_translation
from core.translate_service import build_cloud_translate_prompt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
import httpx
from typing import List

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gemini", tags=["gemini"])

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
    error: str = ""  # error key（settings.status.gemini_<key>）


@router.post("/test", response_model=TestResponse)
async def test_gemini_connection(request: TestRequest):
    """
    測試 Gemini API Key 並獲取可用模型

    測試流程：
    1. 調用 Gemini API 獲取模型列表
    2. 篩選並排序支援的模型
    3. 返回模型列表

    Args:
        request: 包含 API Key 的請求

    Returns:
        TestResponse: 包含成功狀態和模型列表
    """
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API Key is required")

    config = await asyncio.to_thread(load_config)
    key = resolve_secret(request.api_key, read_secret(config, "translate.gemini.api_key")).strip()

    try:
        # 抓取所有頁並篩選支援的模型
        models = await list_models(key, timeout=30.0)
        picked = pick_gemini_models(models)
        result = []
        for model in picked:
            name = model["name"].removeprefix("models/")
            result.append(ModelInfo(
                name=name,
                display_name=model.get("displayName", name),
                description=model.get("description", "")[:100]
            ))
        return TestResponse(success=True, models=result, count=len(result))

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

    except httpx.LocalProtocolError:
        # 金鑰含空白／換行 → h11 拒送；str(e) 內含金鑰，不可 log／回傳
        return TestResponse(
            success=False,
            error="Invalid API Key"
        )

    except Exception as e:
        logger.error("測試 Gemini 連線失敗: %s", e)
        return TestResponse(
            success=False,
            error="測試 Gemini 連線失敗"
        )



@router.post("/test-translate", response_model=TestTranslateResponse)
async def test_gemini_translate(request: TestTranslateRequest):
    """測試 Gemini 翻譯；與搜尋頁真翻譯共用 request_translation 路徑。"""
    config = await asyncio.to_thread(load_config)
    key = resolve_secret(request.api_key, read_secret(config, "translate.gemini.api_key"))

    if not key:
        return TestTranslateResponse(success=False, error="missing_key")

    locale = config.get("general", {}).get("locale", "zh-TW")
    if locale == "ja":
        return TestTranslateResponse(success=True, translation="ja_skip")

    # 安全的測試標題（不會觸發內容過濾）
    test_title = "新人女優デビュー"
    prompt = build_cloud_translate_prompt(test_title, locale)

    try:
        translation = await request_translation(
            key, request.model, prompt, timeout=CLOUD_TRANSLATE_TIMEOUT
        )
        return TestTranslateResponse(success=True, translation=translation)
    except TranslateError as e:
        return TestTranslateResponse(
            success=False,
            error=settings_error_key(e.kind),
        )
    except Exception as e:
        # 不記 str(e)：例外訊息可能夾帶金鑰
        logger.error("[Gemini] 測試翻譯失敗: %s", type(e).__name__)
        return TestTranslateResponse(success=False, error="translate_failed")
