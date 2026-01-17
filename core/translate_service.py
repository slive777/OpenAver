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
        self.ollama_url = config.get("url", "http://localhost:11434").rstrip("/")
        self.model = config.get("model", "qwen3:8b")

    async def translate_single(self, title: str, context: Optional[Dict] = None) -> str:
        """
        單片翻譯（使用 qwen3:8b）

        適用場景：用戶查看第 1 片時立即翻譯
        """
        system_prompt = """你是專業的日文翻譯。請將以下 AV 影片標題翻譯成繁體中文。

規則：
- 保持簡潔，不超過 50 字
- 女優名保留日文
- 術語參考：
  * 中出し → 內射
  * 潮吹き → 潮吹
  * デビュー → 出道
  * 新人 → 新人（保留）
  * 巨乳 → 巨乳（保留）"""

        user_prompt = f"翻譯：{title}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": {"thinking": False}
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
            print(f"[ERROR] Single translation failed: {e}")
            return ""

    async def translate_batch(self, titles: List[str], context: Optional[Dict] = None) -> List[str]:
        """
        批次翻譯（使用統一的 model）

        適用場景：後台翻譯第 2-10 片
        實驗數據：batch=10，耗時 5.35 秒，對齊率 100%
        """
        n = len(titles)

        if n == 0:
            return []

        system_prompt = """You are a professional Japanese-to-Chinese translator for adult video titles.

Rules:
- Translate to Traditional Chinese (Taiwan style)
- Keep actress names in original Japanese
- Concise output, max 50 characters per title
- Output format: one translation per line, numbered (1. translation)

Adult terminology:
- デビュー → 出道
- 中出し → 內射
- 潮吹き → 潮吹
- 巨乳 → 巨乳
- 新人 → 新人
- AV解禁 → AV解禁"""

        user_prompt = f"""Translate the following {n} Japanese AV titles to Traditional Chinese:

{chr(10).join(f'{i+1}. {t}' for i, t in enumerate(titles))}

Output format: numbered list, one translation per line."""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 2048,
                            "num_ctx": 4096
                        }
                    }
                )

            if resp.status_code != 200:
                raise Exception(f"Ollama API error: {resp.status_code}")

            data = resp.json()
            content = data.get("message", {}).get("content", "")

            # 解析輸出（移除編號前綴）
            translations = self._parse_batch_output(content)

            # 驗證對齊率（關鍵！）
            if len(translations) != n:
                print(f"[WARN] Batch translation misalignment: expected {n}, got {len(translations)}")
                # 補齊或截斷
                while len(translations) < n:
                    translations.append("")
                translations = translations[:n]

            return translations

        except Exception as e:
            print(f"[ERROR] Batch translation failed: {e}")
            # 失敗時返回空字符串列表
            return [""] * n

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
        ValueError: 未知的 provider
        NotImplementedError: provider 尚未實現
    """
    provider = config.get("provider", "ollama")

    if provider == "ollama":
        ollama_config = config.get("ollama", {})
        return OllamaTranslateService(ollama_config)

    elif provider == "gemini":
        # Task 2 將實現 GeminiTranslateService
        raise NotImplementedError(
            "Gemini provider will be implemented in Task 2. "
            "Please set provider to 'ollama' in config.json"
        )

    else:
        raise ValueError(f"Unknown translate provider: {provider}")
