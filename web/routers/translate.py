"""
翻譯 API 路由
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, List
import httpx

from web.routers.config import load_config
from core.translate_service import create_translate_service
from core.scrapers.utils import has_japanese

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str
    mode: str = "translate"  # "translate" (日文→中文) 或 "optimize" (清理中文)
    actors: Optional[List[str]] = None
    number: Optional[str] = None


class BatchTranslateRequest(BaseModel):
    """批次翻譯請求模型"""
    titles: List[str] = Field(default=[], max_length=100)
    batch_size: int = Field(default=10, ge=1, le=20)



# 全局翻譯服務實例（單例模式）
_translate_service = None


def get_translate_service():
    """
    獲取翻譯服務實例（單例）

    使用單例模式避免重複初始化 Ollama 連線

    Returns:
        TranslateService 實例
    """
    global _translate_service
    if _translate_service is None:
        config = load_config()
        translate_config = config.get("translate", {})
        _translate_service = create_translate_service(translate_config)
    return _translate_service


def reset_translate_service():
    """重置翻譯服務實例（配置改變時調用）"""
    global _translate_service
    _translate_service = None


@router.post("/translate")
async def translate_title(request: TranslateRequest) -> dict:
    """翻譯或優化標題（支援 Ollama/Gemini）"""
    import re

    config = load_config()
    translate_config = config.get("translate", {})

    if not translate_config.get("enabled", False):
        return {"success": False, "error": "翻譯功能未啟用"}

    # === 新增：日文檢測，只對 translate 模式生效 ===
    if request.mode == "translate" and not has_japanese(request.text):
        return {
            "skipped": True,
            "reason": "no_japanese",
            "original": request.text
        }

    # === translate 模式：使用 translate service（支援 Ollama/Gemini）===
    if request.mode == "translate":
        try:
            translate_service = get_translate_service()
            context = {
                "actors": request.actors or [],
                "number": request.number or ""
            }
            result = await translate_service.translate_single(request.text, context)

            if not result:
                return {"success": False, "error": "翻譯結果為空"}

            return {
                "success": True,
                "result": result,
                "mode": request.mode
            }

        except ValueError as e:
            # API Key 未設定等配置錯誤
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # === optimize 模式：使用 Ollama 清理標題 ===
    # 兼容嵌套結構和舊扁平結構
    ollama_config = translate_config.get("ollama", {})
    ollama_url = ollama_config.get("url", translate_config.get("ollama_url", "http://localhost:11434")).rstrip("/")
    ollama_model = ollama_config.get("model", translate_config.get("ollama_model", "qwen3:8b"))

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

            # 清理輸出
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


@router.post("/translate-batch")
async def translate_batch(request: BatchTranslateRequest):
    """
    批次翻譯多個標題

    使用抽象層，支援 Ollama/Gemini 提供商
    一次翻譯最多 10-20 個標題

    實驗數據（Ollama translategemma:12b）：
    - Batch=10: 5.35 秒，對齊率 100%
    - Batch=15: 7.60 秒，對齊率 100%

    Request Body:
        {
            "titles": ["日文標題1", "日文標題2", ...],
            "batch_size": 10  // 可選，默認 10
        }

    Response:
        {
            "translations": ["繁中翻譯1", "繁中翻譯2", ...],
            "count": 10,       // 成功翻譯數量
            "errors": []       // 失敗的索引列表
        }

    Example:
        curl -X POST http://localhost:8080/api/translate-batch \\
             -H "Content-Type: application/json" \\
             -d '{"titles": ["痴漢願望の女", "芸能人 白石茉莉奈"]}'
    """
    try:
        # 獲取翻譯服務（單例）
        translate_service = get_translate_service()

        # 獲取配置的批次大小（預留：可從 config 讀取默認值）
        config = load_config()
        default_batch_size = config.get("translate", {}).get("batch_size", 10)

        # 限制批次大小（防止超時），優先使用請求參數
        batch_size = min(request.batch_size or default_batch_size, 20)

        # 過濾出包含日文的標題
        japanese_indices = []
        japanese_titles = []
        for i, title in enumerate(request.titles):
            if has_japanese(title):
                japanese_indices.append(i)
                japanese_titles.append(title)

        # 初始化結果列表（預設為原文）
        results = list(request.titles)

        # 只翻譯日文標題
        if japanese_titles:
            translations = []
            for i in range(0, len(japanese_titles), batch_size):
                batch = japanese_titles[i:i+batch_size]
                batch_results = await translate_service.translate_batch(batch)
                translations.extend(batch_results)

            # 將翻譯結果放回對應位置
            for idx, trans in zip(japanese_indices, translations):
                if trans:  # 只有成功翻譯才替換
                    results[idx] = trans

        # 統計
        success_count = len([t for i, t in enumerate(results) if i in japanese_indices and t != request.titles[i]])
        skipped_count = len(request.titles) - len(japanese_indices)
        error_indices = [i for i in japanese_indices if results[i] == request.titles[i]]

        return {
            "translations": results,
            "count": success_count,
            "skipped": skipped_count,
            "errors": error_indices
        }

    except Exception as e:
        print(f"[ERROR] Batch translation API failed: {e}")
        import traceback
        traceback.print_exc()

        # 返回錯誤響應（不拋出異常，避免前端報錯）
        return {
            "translations": list(request.titles),
            "count": 0,
            "skipped": 0,
            "errors": list(range(len(request.titles))),
            "error_message": str(e)
        }

