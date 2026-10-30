"""
OpenAI Compatible API 路由 - 提供模型查詢和翻譯測試功能

端點：
- POST /api/openai/models - 查詢可用模型列表
- POST /api/openai/test   - 翻譯測試
"""

from core.logger import get_logger
from core.config import load_config
from core.secret_fields import read_secret, resolve_secret
from core.translate_service import build_cloud_translate_prompt
from core.cloud_translate import CLOUD_TRANSLATE_TIMEOUT, TranslateError, settings_error_key
from core.openai_client import (
    OPENAI_OFFICIAL_BASE_URL,
    default_official_model,
    pick_official_models,
    request_translation,
)

from fastapi import APIRouter
from pydantic import BaseModel
import asyncio
import httpx
from typing import List

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


class OfficialModelsRequest(BaseModel):
    api_key: str = ""


class OfficialModelsResponse(BaseModel):
    success: bool
    models: List[str] = []
    default_model: str = ""
    error: str = ""


class OfficialTestTranslateRequest(BaseModel):
    api_key: str = ""
    model: str = ""


def _resolve_openai_official_key(request_key: str, config: dict) -> str:
    return resolve_secret(
        request_key, read_secret(config, "translate.openai_official.api_key")
    )


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

    config = await asyncio.to_thread(load_config)
    key = resolve_secret(request.api_key, read_secret(config, "translate.openai.api_key"))
    key = (key or "").strip()

    base_url = request.base_url.rstrip("/")
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

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

    except httpx.LocalProtocolError:
        # 金鑰含非法字元（如換行）：例外字串會帶出金鑰，不 log、不回傳
        logger.warning("[OpenAI] API Key 格式不合法")
        return ModelsResponse(success=False, error="auth_failed")

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

    config = await asyncio.to_thread(load_config)
    key = resolve_secret(request.api_key, read_secret(config, "translate.openai.api_key"))
    locale = config.get("general", {}).get("locale", "zh-TW")

    # F2: ja short-circuit — 與 translate_service.py 的行為保持一致
    if locale == "ja":
        return TestTranslateResponse(
            success=True,
            translation="ja_skip"
        )

    prompt = build_cloud_translate_prompt(test_title, locale)

    try:
        translation = await request_translation(
            request.base_url,
            key,
            request.model,
            prompt,
            timeout=CLOUD_TRANSLATE_TIMEOUT,
        )
        return TestTranslateResponse(success=True, translation=translation)
    except TranslateError as e:
        return TestTranslateResponse(success=False, error=settings_error_key(e.kind))
    except Exception as e:
        # 只記型別名：例外字串可能含金鑰
        logger.error("[OpenAI] 測試翻譯失敗: %s", type(e).__name__)
        return TestTranslateResponse(success=False, error="translate_failed")


@router.post("/official/models", response_model=OfficialModelsResponse)
async def fetch_openai_official_models(request: OfficialModelsRequest):
    """查詢官方 OpenAI 模型，過濾後回 luna／terra／mini 清單。"""
    config = await asyncio.to_thread(load_config)
    key = (_resolve_openai_official_key(request.api_key, config) or "").strip()
    if not key:
        return OfficialModelsResponse(success=False, error="missing_key")

    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{OPENAI_OFFICIAL_BASE_URL.rstrip('/')}/models",
                headers=headers,
            )
            response.raise_for_status()

        data = response.json()
        raw = [
            (item["id"], item.get("created"))
            for item in data.get("data", [])
            if isinstance(item, dict) and "id" in item
        ]
        models = pick_official_models(raw)
        return OfficialModelsResponse(
            success=True,
            models=models,
            default_model=default_official_model(models),
        )

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
        logger.warning("[OpenAI Official] 請求失敗: HTTP %s", sc)
        return OfficialModelsResponse(success=False, error=error_key)

    except httpx.TimeoutException:
        logger.warning("[OpenAI Official] 查詢模型列表逾時")
        return OfficialModelsResponse(success=False, error="connection_timeout")

    except httpx.LocalProtocolError:
        logger.warning("[OpenAI Official] API Key 格式不合法")
        return OfficialModelsResponse(success=False, error="auth_failed")

    except Exception as e:
        logger.warning("[OpenAI Official] 查詢模型列表失敗: %s", type(e).__name__)
        return OfficialModelsResponse(success=False, error="connection_failed")


@router.post("/official/test", response_model=TestTranslateResponse)
async def test_openai_official_translate(request: OfficialTestTranslateRequest):
    """測試官方 OpenAI 翻譯；與真翻譯共用 request_translation 路徑。"""
    if not request.model.strip():
        return TestTranslateResponse(success=False, error="missing_model")

    config = await asyncio.to_thread(load_config)
    key = (_resolve_openai_official_key(request.api_key, config) or "").strip()
    if not key:
        return TestTranslateResponse(success=False, error="missing_key")

    locale = config.get("general", {}).get("locale", "zh-TW")
    if locale == "ja":
        return TestTranslateResponse(success=True, translation="ja_skip")

    test_title = "新人女優デビュー"
    prompt = build_cloud_translate_prompt(test_title, locale)

    try:
        translation = await request_translation(
            OPENAI_OFFICIAL_BASE_URL,
            key,
            request.model,
            prompt,
            timeout=CLOUD_TRANSLATE_TIMEOUT,
        )
        return TestTranslateResponse(success=True, translation=translation)
    except TranslateError as e:
        return TestTranslateResponse(success=False, error=settings_error_key(e.kind))
    except Exception as e:
        logger.error("[OpenAI Official] 測試翻譯失敗: %s", type(e).__name__)
        return TestTranslateResponse(success=False, error="translate_failed")
