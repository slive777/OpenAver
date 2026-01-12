"""
翻譯 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import httpx

from web.routers.config import load_config

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str
    mode: str = "translate"  # "translate" (日文→中文) 或 "optimize" (清理中文)
    actors: Optional[List[str]] = None
    number: Optional[str] = None


@router.post("/translate")
async def translate_title(request: TranslateRequest) -> dict:
    """翻譯或優化標題"""
    import re

    config = load_config()
    translate_config = config.get("translate", {})

    if not translate_config.get("enabled", False):
        return {"success": False, "error": "翻譯功能未啟用"}

    ollama_url = translate_config.get("ollama_url", "http://localhost:11434").rstrip("/")
    ollama_model = translate_config.get("ollama_model", "qwen3:8b")

    # 根據模式建構 prompt（參考 jav_scraper.py）
    if request.mode == "translate":
        # 建構上下文
        context_parts = []
        if request.actors:
            context_parts.append(f"演員: {', '.join(request.actors[:3])}")
        context = "\n".join(context_parts) if context_parts else ""
        context_section = f"\n影片資訊：\n{context}\n" if context else ""

        system_prompt = """你是專業的日文翻譯，專門翻譯成人影片標題。
規則：
1. 翻譯成繁體中文
2. 保持標題簡潔，不超過50字
3. 保留專有名詞（如人名）
4. 不要添加任何解釋或評論
5. 只輸出翻譯結果"""
        user_prompt = f"{context_section}\n翻譯以下日文標題為繁體中文：\n{request.text}"
    else:  # optimize
        # 建構需要移除的內容提示
        remove_hints = []
        if request.actors:
            remove_hints.append(f"女優名：{', '.join(request.actors)}")
        if request.number:
            remove_hints.append(f"番號：{request.number}")
        hints_text = "、".join(remove_hints) if remove_hints else ""

        system_prompt = """你是標題編輯，專門清理影片標題。
規則：
1. 移除來源標記（如 Hayav, Jable, MissAV, FC2, Streaming Free 等）
2. 移除女優名稱和番號
3. 移除「中文字幕」等標記
4. 保留核心片名
5. 只輸出結果，不要解釋"""
        user_prompt = f"清理以下標題，移除{hints_text}及來源標記，保留核心片名：\n{request.text}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": ollama_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "options": {
                        "thinking": False  # 禁用 Qwen3 thinking 模式，加速回應
                    }
                }
            )
            resp.raise_for_status()
            data = resp.json()

            # 提取回應內容
            result = data.get("message", {}).get("content", "").strip()

            if not result:
                return {"success": False, "error": "翻譯結果為空"}

            # 清理輸出（參考 jav_scraper.py）
            result = result.strip().strip('"').strip("'")
            result = re.sub(r'^翻譯[：:]\s*', '', result)
            result = re.sub(r'^中文[：:]\s*', '', result)
            result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL)
            result = result.strip()

            return {
                "success": True,
                "result": result,
                "mode": request.mode
            }

    except httpx.TimeoutException:
        return {"success": False, "error": "Ollama 連線逾時"}
    except httpx.ConnectError:
        return {"success": False, "error": "無法連線到 Ollama"}
    except Exception as e:
        return {"success": False, "error": str(e)}
