"""
翻譯服務抽象層 - 支援多個提供商

設計模式：策略模式
目的：解耦翻譯邏輯，便於擴展新提供商（Gemini）

使用方式：
    from core.translate_service import create_translate_service
    
    config = {"provider": "ollama", "ollama": {"url": "http://localhost:11434"}}
    service = create_translate_service(config)
    
    # 單片翻譯
    result = await service.translate_single("日文標題")
    
    # 批次翻譯
    results = await service.translate_batch(["標題1", "標題2", ...])
"""

from abc import ABC, abstractmethod
from core.logger import get_logger

logger = get_logger(__name__)
from typing import List, Dict, Optional
import httpx
import re


class TranslateService(ABC):
    """翻譯服務抽象基類"""

    @abstractmethod
    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """
        翻譯單個標題

        Args:
            title: 日文標題
            context: 上下文信息（演員、番號等），可選

        Returns:
            繁體中文翻譯
        """
        pass

    @abstractmethod
    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """
        批次翻譯多個標題

        Args:
            titles: 日文標題列表
            context: 上下文信息，可選

        Returns:
            繁體中文翻譯列表（長度必須與輸入一致）
        """
        pass


class OllamaTranslateService(TranslateService):
    """Ollama 翻譯服務實現"""

    def __init__(self, config: Dict):
        """
        初始化 Ollama 服務

        Args:
            config: Ollama 配置字典
                {
                    "url": "http://localhost:11434",
                    "model": "qwen3:8b"  # 所有翻譯都用此模型
                }
        """
        self.ollama_url = (config.get("url") or "http://localhost:11434").rstrip("/")
        self.model = config.get("model") or "qwen3:8b"

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """
        單片翻譯

        適用場景：用戶查看第 1 片時立即翻譯
        """
        prompt = f"""將以下日文AV標題翻譯成繁體中文。保留原本的色情語氣，女優名保留日文。只輸出翻譯結果。

{title}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "options": {
                            "num_predict": 500,
                            "temperature": 0.3
                        }
                    }
                )

            if resp.status_code != 200:
                raise Exception(f"Ollama API error: {resp.status_code}")

            data = resp.json()
            result = data.get("message", {}).get("content", "").strip()

            # 清理輸出
            result = self._clean_output(result)

            return result if result else ""

        except Exception as e:
            logger.error(f"[Ollama] Single translation failed: {e}")
            return ""

    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """
        批次翻譯 - 逐片翻譯確保穩定性

        適用場景：後台翻譯第 2-10 片
        """
        if not titles:
            return []

        results = []
        for title in titles:
            result = await self.translate_single(title, context)
            results.append(result)

        return results

    def _clean_output(self, text: str) -> str:
        """清理翻譯輸出"""
        text = text.strip().strip('"').strip("'")
        text = re.sub(r'^翻譯[：:]\\s*', '', text)
        text = re.sub(r'^中文[：:]\\s*', '', text)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return text.strip()

    def _parse_batch_output(self, content: str) -> List[str]:
        """解析批次翻譯輸出"""
        translations = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 移除編號前綴（支援 1. / 1) / 1、）
            match = re.match(r'^\d+[.)、]\s*(.+)$', line)
            if match:
                text = match.group(1).strip()
                translations.append(self._clean_output(text))
            elif line and not re.match(r'^[\d.)、\s]+$', line):
                # 沒有編號但有內容的行也接受
                translations.append(self._clean_output(line))
        return translations


class GeminiTranslateService(TranslateService):
    """Google Gemini API 翻譯服務實現"""

    def __init__(self, config: Dict):
        """
        初始化 Gemini 服務

        Args:
            config: Gemini 配置字典
                {
                    "api_key": "AIza...",
                    "model": "gemini-flash-lite-latest"
                }
        """
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-flash-lite-latest")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

        if not self.api_key:
            raise ValueError("Gemini API Key is required")

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """
        單片翻譯

        適用場景：用戶手動點擊翻譯按鈕
        性能：約 0.87 秒
        """
        prompt = f"""你是專業的影視資料庫管理員與翻譯引擎。這是既有日文文字的逐字翻譯任務，請將以下標題翻譯為繁體中文。

原文：
{title}

翻譯要求：
1. 這是純粹的資料庫翻譯任務，不生成新內容
2. 使用繁體中文
3. 保持簡潔，不超過50字
4. 只輸出翻譯結果，不要額外說明
"""

        try:
            url = f"{self.base_url}/models/{self.model}:generateContent"
            headers = {"x-goog-api-key": self.api_key}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 100
                },
                "safetySettings": [
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_NONE"
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_NONE"
                    }
                ]
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()

            data = resp.json()

            # Step 1: 檢查 promptFeedback（最優先）
            if "promptFeedback" in data:
                feedback = data["promptFeedback"]
                if "blockReason" in feedback:
                    block_reason = feedback["blockReason"]
                    safety_ratings = feedback.get("safetyRatings", [])
                    logger.warning(f"[Gemini] Prompt 被過濾: {block_reason}")
                    if safety_ratings:
                        logger.warning(f"[Gemini] 安全評級: {safety_ratings}")
                    return ""

            # Step 2: 檢查 candidates 是否存在
            if "candidates" not in data or not data["candidates"]:
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    logger.error(f"[Gemini] API Error: {error_msg}")
                else:
                    logger.warning("[Gemini] No candidates in response")
                return ""

            candidate = data["candidates"][0]

            # Step 3: 檢查 finishReason
            finish_reason = candidate.get("finishReason", "")
            if finish_reason and finish_reason != "STOP":
                logger.warning(f"[Gemini] 異常終止: finishReason={finish_reason}")
                if finish_reason == "SAFETY":
                    safety_ratings = candidate.get("safetyRatings", [])
                    logger.warning(f"[Gemini] 安全過濾觸發: {safety_ratings}")
                return ""

            # Step 4: 安全訪問 content 字段
            try:
                translation = candidate["content"]["parts"][0]["text"].strip()
                return translation
            except (KeyError, IndexError, TypeError) as e:
                logger.error(f"[Gemini] 響應格式錯誤: {e}")
                logger.debug(f"[Gemini] Candidate 結構: {candidate}")
                return ""

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.error("[Gemini] Invalid API Key or request")
            elif e.response.status_code == 429:
                logger.warning("[Gemini] API quota exceeded")
            else:
                logger.error(f"[Gemini] API error: {e.response.status_code}")
            return ""
        except Exception as e:
            logger.error(f"[Gemini] Single translation failed: {e}")
            return ""

    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """
        批次翻譯 - Gemini 逐片翻譯避免安全過濾

        Gemini 一次翻譯多個 AV 標題容易觸發安全過濾，
        因此改為循環調用 translate_single()，每次只翻譯一片。

        適用場景：批次翻譯 10 片
        性能：約 8.7 秒 / 10 片（比原方案慢，但穩定可用）
        """
        if not titles:
            return []

        # 逐片翻譯，避免安全過濾
        results = []
        for title in titles:
            result = await self.translate_single(title, context)
            results.append(result)

        return results

    def _parse_batch_result(self, result_text: str) -> List[str]:
        """解析批次翻譯結果"""
        lines = result_text.strip().split('\n')
        translations = []

        for line in lines:
            line = line.strip()

            # 跳過空行和說明文字
            if not line or line.startswith('以下') or line.startswith('翻譯'):
                continue

            # 解析序號格式：1. xxx 或 1、xxx 或 1) xxx
            if line and line[0].isdigit():
                for sep in ['. ', '、', ') ', '．']:
                    if sep in line:
                        parts = line.split(sep, 1)
                        if len(parts) == 2:
                            translations.append(parts[1].strip())
                            break
            # 列表符號
            elif line.startswith('*') or line.startswith('-'):
                translations.append(line[1:].strip())

        return translations


def create_translate_service(config: Dict) -> TranslateService:
    """
    創建翻譯服務實例（工廠函數）

    Args:
        config: translate 配置字典
            {
                "provider": "ollama" | "gemini",
                "ollama": {...},
                "gemini": {...}
            }

    Returns:
        TranslateService 實例

    Raises:
        ValueError: 未知的 provider 或配置錯誤
    """
    provider = config.get("provider", "ollama")

    if provider == "ollama":
        ollama_config = config.get("ollama", {})
        return OllamaTranslateService(ollama_config)

    elif provider == "gemini":
        gemini_config = config.get("gemini", {})
        return GeminiTranslateService(gemini_config)

    else:
        raise ValueError(f"Unknown translate provider: {provider}")
