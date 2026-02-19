"""
Gemini API 路由 - 提供測試和模型查詢功能

端點：
- POST /api/gemini/test - 測試 API Key 並獲取可用模型
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from typing import List

logger = logging.getLogger(__name__)

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
    error: str = ""  # Google 的原始錯誤訊息


@router.post("/test", response_model=TestResponse)
async def test_gemini_connection(request: TestRequest):
    """
    測試 Gemini API Key 並獲取可用模型

    測試流程：
    1. 調用 Gemini API 獲取模型列表
    2. 過濾出 Flash 系列模型
    3. 排序（latest 優先）
    4. 返回模型列表

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

        # 過濾 Flash 系列模型
        flash_models = []
        for model in data.get("models", []):
            name = model.get("name", "").replace("models/", "")

            # 只保留 flash 系列，排除 pro 和 embedding
            if is_flash_model(name):
                flash_models.append(ModelInfo(
                    name=name,
                    display_name=model.get("displayName", name),
                    description=model.get("description", "")[:100]  # 限制長度
                ))

        # 排序：lite-latest 優先（最推薦），其他 latest 次之
        flash_models.sort(key=lambda m: (
            0 if "lite-latest" in m.name else (1 if "latest" in m.name else 2),
            m.name
        ))

        return TestResponse(
            success=True,
            models=flash_models,
            count=len(flash_models)
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


def is_flash_model(model_name: str) -> bool:
    """
    判斷是否為 flash 系列模型

    過濾規則：
    - 必須包含 "flash"
    - 排除 "pro" 系列
    - 排除 "embedding" 模型

    Args:
        model_name: 模型名稱

    Returns:
        bool: 是否為 flash 系列
    """
    name_lower = model_name.lower()

    # 必須包含 flash
    if "flash" not in name_lower:
        return False

    # 排除 pro 系列
    if "pro" in name_lower:
        return False

    # 排除 embedding 模型
    if "embedding" in name_lower:
        return False

    return True


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

    try:
        # 構建翻譯請求
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"
        headers = {"x-goog-api-key": request.api_key}
        payload = {
            "contents": [{"parts": [{"text": f"請將以下日文翻譯成繁體中文：{test_title}"}]}],
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
