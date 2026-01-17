"""
Gemini API 路由 - 提供測試和模型查詢功能

端點：
- POST /api/gemini/test - 測試 API Key 並獲取可用模型
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from typing import List

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

        # 排序：latest 在前
        flash_models.sort(key=lambda m: (
            0 if "latest" in m.name else 1,
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
        return TestResponse(
            success=False,
            error=str(e)
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
