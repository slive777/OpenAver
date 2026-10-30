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

from core import gemini_client, openai_client
from core.anthropic_client import (
    DEFAULT_CLAUDE_MODEL,
    request_translation,
)
from core.cloud_translate import CLOUD_TRANSLATE_TIMEOUT, TranslateError, build_error


# ============ 語言 Prompt 模板 ============

LANGUAGE_PROMPTS = {
    "zh-TW": {
        "name": "繁體中文",
        "ollama_system": "你是日翻中翻譯機。輸入日文，輸出繁體中文。禁止輸出任何日文假名（の、は、が、で、に等；人名、品牌名除外）。人名、品牌名保留原文。",
        "ollama_example": "義父の隣で夫に電話させながら人妻を寝取る → 在公公旁邊讓人妻一邊打電話給丈夫一邊被睡走",
        "gemini_instruction": "請將以下標題翻譯為繁體中文",
        "gemini_rules": "1. 這是純粹的資料庫翻譯任務，不生成新內容\n2. 使用繁體中文\n3. 保持簡潔，不超過50字\n4. 只輸出翻譯結果，不要額外說明\n5. 人名、品牌名保留原文",
    },
    "zh-CN": {
        "name": "簡體中文",
        "ollama_system": "你是日翻中翻译机。输入日文，输出简体中文。禁止输出任何日文假名（の、は、が、で、に等；人名、品牌名除外）。人名、品牌名保留原文。",
        "ollama_example": "義父の隣で夫に電話させながら人妻を寝取る → 在公公旁边让人妻一边打电话给丈夫一边被睡走",
        "gemini_instruction": "请将以下标题翻译为简体中文",
        "gemini_rules": "1. 这是纯粹的资料库翻译任务，不生成新内容\n2. 使用简体中文\n3. 保持简洁，不超过50字\n4. 只输出翻译结果，不要额外说明\n5. 人名、品牌名保留原文",
    },
    "en": {
        "name": "English",
        "ollama_system": "You are a Japanese-to-English translator. Input Japanese, output English. Keep proper nouns. Be concise.",
        "ollama_example": "義父の隣で夫に電話させながら人妻を寝取る → Seducing a Married Woman While She Calls Her Husband Next to Her Father-in-Law",
        "gemini_instruction": "Translate the following title to English",
        "gemini_rules": "1. This is a database translation task, do not generate new content\n2. Use natural English\n3. Keep it concise, under 80 characters\n4. Output only the translation, no explanations",
    },
}


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

    async def translate_or_raise(self, title: str, context: Optional[Dict] = None) -> str:
        """翻譯單個標題；失敗拋 TranslateError（供 API 層分辨原因）。

        預設實作包 translate_single：回空字串視為 empty_response。
        """
        result = await self.translate_single(title, context)
        if not result:
            raise TranslateError("empty_response", None, "", "translation is empty")
        return result

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

    def __init__(self, config: Dict, target_language: str = "zh-TW"):
        """
        初始化 Ollama 服務

        Args:
            config: Ollama 配置字典
                {
                    "url": "http://localhost:11434",
                    "model": "qwen3:8b"  # 所有翻譯都用此模型
                }
            target_language: 目標語言代碼（zh-TW / zh-CN / en / ja）
        """
        self.ollama_url = (config.get("url") or "http://localhost:11434").rstrip("/")
        self.model = config.get("model") or "qwen3:8b"
        self.target_language = target_language

    async def translate_or_raise(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；ja 短路；失敗拋 TranslateError（請求內容與改前逐字相同）。"""
        # ja 短路：不呼叫 API，直接回傳原文
        if self.target_language == "ja":
            return title

        lang_data = LANGUAGE_PROMPTS.get(self.target_language, LANGUAGE_PROMPTS["zh-TW"])
        system_msg = lang_data["ollama_system"]
        example = lang_data["ollama_example"]
        prompt = f"""範例：{example}

請翻譯：{title}"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_msg},
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
        except TranslateError:
            raise
        except httpx.TimeoutException as e:
            raise build_error(
                "Ollama", "connection_timeout", None, type(e).__name__, "request timed out"
            ) from None
        except httpx.ConnectError as e:
            raise build_error(
                "Ollama", "connection_failed", None, type(e).__name__, "cannot connect"
            ) from None
        except Exception as e:
            raise build_error(
                "Ollama", "api_error", None, type(e).__name__, str(e)
            ) from None

        if not result:
            raise build_error("Ollama", "empty_response", None, "", "translation is empty")
        return result

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """
        單片翻譯

        適用場景：用戶查看第 1 片時立即翻譯；任何失敗回空字串。
        """
        try:
            return await self.translate_or_raise(title, context)
        except TranslateError as e:
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

    def __init__(self, config: Dict, target_language: str = "zh-TW"):
        """
        初始化 Gemini 服務

        Args:
            config: Gemini 配置字典
                {
                    "api_key": "AIza...",
                    "model": "gemini-flash-lite-latest"
                }
            target_language: 目標語言代碼（zh-TW / zh-CN / en / ja）
        """
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-flash-lite-latest")
        self.target_language = target_language

        if not self.api_key:
            raise ValueError("Gemini API Key is required")

    async def translate_or_raise(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；ja 短路；失敗拋 TranslateError。"""
        # ja 短路：不呼叫 API，直接回傳原文
        if self.target_language == "ja":
            return title

        prompt = build_cloud_translate_prompt(title, self.target_language)

        try:
            return await gemini_client.request_translation(
                self.api_key,
                self.model,
                prompt,
                timeout=CLOUD_TRANSLATE_TIMEOUT,
            )
        except TranslateError:
            raise
        except Exception as e:
            # 只記型別名：例外字串可能含金鑰
            raise build_error(
                "Gemini", "api_error", None, type(e).__name__, "translation request failed"
            ) from None

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯（用戶手動點擊）；任何失敗回空字串。"""
        try:
            return await self.translate_or_raise(title, context)
        except TranslateError:
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


class OpenAICompatibleTranslateService(TranslateService):
    """OpenAI Compatible API 翻譯服務實現（支援 OpenAI、Perplexity、OpenRouter、本地 LLM 等）"""

    def __init__(self, config: Dict, target_language: str = "zh-TW"):
        """
        初始化 OpenAI Compatible 服務

        Args:
            config: OpenAI Compatible 配置字典
                {
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-xxx",  # 可為空（本地 LLM 不需要）
                    "model": "gpt-4o-mini"
                }
            target_language: 目標語言代碼（zh-TW / zh-CN / en / ja）
        """
        self.base_url = (config.get("base_url") or "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model") or "gpt-4o-mini"
        self.target_language = target_language

    async def translate_or_raise(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；ja 短路；失敗拋 TranslateError。"""
        # ja 短路：不呼叫 API，直接回傳原文
        if self.target_language == "ja":
            return title

        prompt = build_cloud_translate_prompt(title, self.target_language)

        try:
            return await openai_client.request_translation(
                self.base_url,
                self.api_key,
                self.model,
                prompt,
                timeout=CLOUD_TRANSLATE_TIMEOUT,
            )
        except TranslateError:
            raise
        except Exception as e:
            # 只記型別名：例外字串可能含金鑰
            raise build_error(
                "OpenAI", "api_error", None, type(e).__name__, "translation request failed"
            ) from None

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；任何失敗回空字串。"""
        try:
            return await self.translate_or_raise(title, context)
        except TranslateError:
            return ""

    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """
        批次翻譯 - 逐片翻譯確保穩定性
        """
        if not titles:
            return []

        results = []
        for title in titles:
            result = await self.translate_single(title, context)
            results.append(result)

        return results


def build_cloud_translate_prompt(title: str, target_language: str) -> str:
    """組出與現行 Gemini／OpenAI 逐字相同的雲端翻譯 prompt。"""
    lang_data = LANGUAGE_PROMPTS.get(target_language, LANGUAGE_PROMPTS["zh-TW"])
    instruction = lang_data["gemini_instruction"]
    rules = lang_data["gemini_rules"]
    return f"""你是專業的影視資料庫管理員與翻譯引擎。這是既有日文文字的逐字翻譯任務，{instruction}。

原文：
{title}

翻譯要求：
{rules}
"""


class ClaudeTranslateService(TranslateService):
    """Anthropic Claude Messages API 翻譯服務"""

    def __init__(self, config: Dict, target_language: str = "zh-TW"):
        """
        Args:
            config: Claude 配置字典
                {
                    "api_key": "sk-ant-...",
                    "model": "claude-haiku-5-5"
                }
            target_language: 目標語言代碼（zh-TW / zh-CN / en / ja）
        """
        self.api_key = config.get("api_key", "")
        self.model = config.get("model") or DEFAULT_CLAUDE_MODEL
        self.target_language = target_language

        if not self.api_key:
            raise ValueError("Claude API Key is required")

    async def translate_or_raise(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；ja 短路；失敗拋 TranslateError（AnthropicError 為其子類）。"""
        if self.target_language == "ja":
            return title

        prompt = build_cloud_translate_prompt(title, self.target_language)

        try:
            return await request_translation(
                self.api_key,
                self.model,
                prompt,
                timeout=30,
            )
        except TranslateError:
            raise
        except Exception as e:
            # 只記型別名：例外字串可能含金鑰
            raise build_error(
                "Claude", "api_error", None, type(e).__name__, "translation request failed"
            ) from None

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """單片翻譯；任何失敗回空字串。"""
        try:
            return await self.translate_or_raise(title, context)
        except TranslateError:
            return ""

    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """批次翻譯 - 逐片呼叫 translate_single。"""
        if not titles:
            return []

        results = []
        for title in titles:
            result = await self.translate_single(title, context)
            results.append(result)

        return results


def create_translate_service(config: Dict, target_language: str = "zh-TW") -> TranslateService:
    """
    創建翻譯服務實例（工廠函數）

    Args:
        config: translate 配置字典
            {
                "provider": "ollama" | "gemini" | "openai" | "claude" | "openai_official",
                "ollama": {...},
                "gemini": {...},
                "claude": {...},
                "openai": {...},
                "openai_official": {...}
            }
        target_language: 目標語言代碼（zh-TW / zh-CN / en / ja），預設 zh-TW

    Returns:
        TranslateService 實例

    Raises:
        ValueError: 未知的 provider 或配置錯誤
    """
    provider = config.get("provider", "ollama")

    if provider == "ollama":
        ollama_config = config.get("ollama", {})
        return OllamaTranslateService(ollama_config, target_language)

    elif provider == "gemini":
        gemini_config = config.get("gemini", {})
        return GeminiTranslateService(gemini_config, target_language)

    elif provider == "openai":
        openai_config = config.get("openai", {})
        return OpenAICompatibleTranslateService(openai_config, target_language)

    elif provider == "openai_official":
        from core.openai_client import OPENAI_OFFICIAL_BASE_URL

        official = config.get("openai_official", {}) or {}
        return OpenAICompatibleTranslateService(
            {
                "base_url": OPENAI_OFFICIAL_BASE_URL,
                "api_key": official.get("api_key", ""),
                "model": official.get("model", ""),
            },
            target_language,
        )

    elif provider == "claude":
        claude_config = config.get("claude", {})
        return ClaudeTranslateService(claude_config, target_language)

    else:
        raise ValueError(f"Unknown translate provider: {provider}")
