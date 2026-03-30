"""
test_translate_service.py - 翻譯服務抽象層單元測試

測試範圍：
- 工廠函數 create_translate_service()
- 配置默認值處理
- 錯誤處理（未知 provider、未實現 provider）
- 語言 prompt 組裝（TestLanguagePrompts）
- ja 短路機制（TestTranslateSingleJaShortCircuit）

注意：實際 Ollama API 調用測試放在 tests/smoke/test_translate_live.py
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.translate_service import (
    TranslateService,
    OllamaTranslateService,
    GeminiTranslateService,
    create_translate_service
)


# ============ 工廠函數測試 ============

class TestCreateTranslateService:
    """測試工廠函數"""

    def test_factory_ollama(self):
        """Ollama provider 正確創建實例"""
        config = {
            "provider": "ollama",
            "ollama": {
                "url": "http://localhost:11434",
                "model": "qwen3:8b"
            }
        }
        service = create_translate_service(config)

        assert isinstance(service, OllamaTranslateService)
        assert service.ollama_url == "http://localhost:11434"
        assert service.model == "qwen3:8b"

    def test_factory_ollama_default_provider(self):
        """默認 provider 為 ollama"""
        config = {}  # 無 provider 欄位
        service = create_translate_service(config)

        assert isinstance(service, OllamaTranslateService)

    def test_factory_gemini_missing_api_key(self):
        """Gemini provider 缺少 API Key 拋出 ValueError"""
        config = {"provider": "gemini", "gemini": {}}

        with pytest.raises(ValueError) as exc_info:
            create_translate_service(config)

        assert "API Key" in str(exc_info.value)

    def test_factory_unknown_provider(self):
        """未知 provider 拋出 ValueError"""
        config = {"provider": "unknown_provider"}

        with pytest.raises(ValueError) as exc_info:
            create_translate_service(config)

        assert "unknown_provider" in str(exc_info.value)


# ============ OllamaTranslateService 配置測試 ============

class TestOllamaTranslateServiceConfig:
    """測試 Ollama 服務配置處理"""

    def test_default_config(self):
        """默認配置正確設置"""
        service = OllamaTranslateService({})

        assert service.ollama_url == "http://localhost:11434"
        assert service.model == "qwen3:8b"

    def test_custom_url(self):
        """自定義 URL 正確處理"""
        config = {"url": "http://192.168.1.100:11434"}
        service = OllamaTranslateService(config)

        assert service.ollama_url == "http://192.168.1.100:11434"

    def test_url_trailing_slash_removed(self):
        """URL 尾斜線自動移除"""
        config = {"url": "http://localhost:11434/"}
        service = OllamaTranslateService(config)

        assert service.ollama_url == "http://localhost:11434"

    def test_custom_models(self):
        """自定義模型正確設置"""
        config = {
            "model": "llama3:8b"
        }
        service = OllamaTranslateService(config)

        assert service.model == "llama3:8b"


# ============ 抽象類測試 ============

class TestTranslateServiceABC:
    """測試抽象基類"""

    def test_cannot_instantiate_abc(self):
        """無法直接實例化抽象類"""
        with pytest.raises(TypeError):
            TranslateService()

    def test_ollama_is_subclass(self):
        """OllamaTranslateService 是 TranslateService 子類"""
        assert issubclass(OllamaTranslateService, TranslateService)

    def test_service_has_required_methods(self):
        """服務包含必要方法"""
        service = OllamaTranslateService({})

        assert hasattr(service, 'translate_single')
        assert hasattr(service, 'translate_batch')
        assert callable(service.translate_single)
        assert callable(service.translate_batch)


# ============ 語言 prompt 組裝測試 ============

class TestLanguagePrompts:
    """測試各語言 prompt 組裝"""

    def test_ollama_zh_tw_prompt(self):
        """OllamaTranslateService(config, "zh-TW") 的 system_msg 含 '繁體中文'"""
        service = OllamaTranslateService({}, "zh-TW")
        assert service.target_language == "zh-TW"
        # 確認 system prompt 包含繁體中文關鍵字
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("zh-TW", {})
        assert "繁體中文" in prompt_data.get("ollama_system", "")

    def test_ollama_zh_cn_prompt(self):
        """OllamaTranslateService(config, "zh-CN") 的 system_msg 含 '简体中文'"""
        service = OllamaTranslateService({}, "zh-CN")
        assert service.target_language == "zh-CN"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("zh-CN", {})
        assert "简体中文" in prompt_data.get("ollama_system", "")

    def test_ollama_en_prompt(self):
        """OllamaTranslateService(config, "en") 的 system_msg 含 'English'"""
        service = OllamaTranslateService({}, "en")
        assert service.target_language == "en"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("en", {})
        assert "English" in prompt_data.get("ollama_system", "")

    def test_gemini_en_prompt(self):
        """GeminiTranslateService(config, "en") 的 prompt 含 'English'"""
        config = {"api_key": "fake-key-for-test"}
        service = GeminiTranslateService(config, "en")
        assert service.target_language == "en"
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("en", {})
        assert "English" in prompt_data.get("gemini_instruction", "")

    def test_unknown_target_fallback(self):
        """不存在的 target（如 'ko'）fallback 到 zh-TW prompt"""
        service = OllamaTranslateService({}, "ko")
        assert service.target_language == "ko"
        # LANGUAGE_PROMPTS.get("ko", LANGUAGE_PROMPTS["zh-TW"]) 應返回 zh-TW 的資料
        from core.translate_service import LANGUAGE_PROMPTS
        prompt_data = LANGUAGE_PROMPTS.get("ko", LANGUAGE_PROMPTS["zh-TW"])
        assert "繁體中文" in prompt_data.get("ollama_system", "")


# ============ ja 短路測試 ============

class TestTranslateSingleJaShortCircuit:
    """測試 target=ja 時不呼叫 API，回傳原文"""

    @pytest.mark.asyncio
    async def test_ollama_ja_returns_original(self):
        """target=ja 時 Ollama 不呼叫 API，回傳原文"""
        service = OllamaTranslateService({}, "ja")
        original_title = "巨乳の女優がデビュー"

        # 若呼叫 httpx 就會失敗，這裡 mock 確保不被呼叫
        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title

    @pytest.mark.asyncio
    async def test_gemini_ja_returns_original(self):
        """target=ja 時 Gemini 不呼叫 API，回傳原文"""
        config = {"api_key": "fake-key-for-test"}
        service = GeminiTranslateService(config, "ja")
        original_title = "巨乳の女優がデビュー"

        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title
