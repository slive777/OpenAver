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
    OpenAICompatibleTranslateService,
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


# ============ OpenAICompatibleTranslateService 測試 ============

class TestOpenAICompatibleTranslateService:
    """測試 OpenAI Compatible 翻譯服務"""

    def test_trailing_slash_removed(self):
        """base_url 尾斜線自動移除"""
        service = OpenAICompatibleTranslateService({"base_url": "http://host/v1/"})
        assert service.base_url == "http://host/v1"

    def test_trailing_slash_removed_multiple(self):
        """多重尾斜線自動移除"""
        service = OpenAICompatibleTranslateService({"base_url": "http://host/v1///"})
        assert service.base_url == "http://host/v1"

    def test_default_model(self):
        """預設 model 為 gpt-4o-mini"""
        service = OpenAICompatibleTranslateService({})
        assert service.model == "gpt-4o-mini"

    def test_custom_model(self):
        """自定義 model 正確設置"""
        service = OpenAICompatibleTranslateService({"model": "llama3"})
        assert service.model == "llama3"

    def test_api_key_empty_by_default(self):
        """api_key 預設為空字串"""
        service = OpenAICompatibleTranslateService({})
        assert service.api_key == ""

    @pytest.mark.asyncio
    async def test_ja_short_circuit(self):
        """target=ja 時不呼叫 HTTP，直接回傳原文"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "ja"
        )
        original_title = "テスト"

        with patch("httpx.AsyncClient") as mock_client:
            result = await service.translate_single(original_title)
            mock_client.assert_not_called()

        assert result == original_title

    @pytest.mark.asyncio
    async def test_api_key_empty_no_auth_header(self):
        """api_key 為空時不送 Authorization header"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "api_key": "", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "新人女演員出道"}}]
        }
        mock_response.raise_for_status = MagicMock()

        captured_headers = {}

        async def mock_post(url, headers=None, json=None):
            captured_headers.update(headers or {})
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("新人女優デビュー")

        assert "Authorization" not in captured_headers
        assert result == "新人女演員出道"

    @pytest.mark.asyncio
    async def test_api_key_present_auth_header(self):
        """api_key 有值時送 Authorization: Bearer xxx"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "api_key": "sk-test123", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "新人女演員出道"}}]
        }
        mock_response.raise_for_status = MagicMock()

        captured_headers = {}

        async def mock_post(url, headers=None, json=None):
            captured_headers.update(headers or {})
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            await service.translate_single("新人女優デビュー")

        assert captured_headers.get("Authorization") == "Bearer sk-test123"

    @pytest.mark.asyncio
    async def test_translate_single_url_no_double_slash(self):
        """POST URL 無雙斜線（base_url 無尾斜線後拼接 /chat/completions）"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://host/v1/", "model": "m"},
            "zh-TW"
        )

        captured_url = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}]
        }
        mock_response.raise_for_status = MagicMock()

        async def mock_post(url, headers=None, json=None):
            captured_url["url"] = url
            return mock_response

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=mock_post)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            await service.translate_single("テスト")

        assert captured_url["url"] == "http://host/v1/chat/completions"
        assert "//" not in captured_url["url"].replace("://", "")

    @pytest.mark.asyncio
    async def test_translate_single_success(self):
        """mock 200 + OpenAI format → 回翻譯結果"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "gpt-4o-mini"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "  新人女演員出道  "}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("新人女優デビュー")

        assert result == "新人女演員出道"

    @pytest.mark.asyncio
    async def test_translate_single_http_error(self):
        """mock 401 → 回 ''，不拋例外"""
        import httpx as _httpx

        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error = _httpx.HTTPStatusError(
            "401 Unauthorized",
            request=MagicMock(),
            response=mock_response
        )

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(side_effect=http_error)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_translate_single_bad_response(self):
        """mock 200 + {error: ...}（無 choices）→ 回 ''"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "model not found"}
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance):
            result = await service.translate_single("テスト")

        assert result == ""

    @pytest.mark.asyncio
    async def test_translate_batch(self):
        """mock translate_single → batch 循環正確"""
        service = OpenAICompatibleTranslateService(
            {"base_url": "http://localhost/v1", "model": "m"},
            "zh-TW"
        )

        call_count = 0
        side_effects = ["翻譯A", "翻譯B"]

        async def mock_translate_single(title, context=None):
            nonlocal call_count
            result = side_effects[call_count]
            call_count += 1
            return result

        service.translate_single = mock_translate_single

        results = await service.translate_batch(["タイトルA", "タイトルB"])

        assert len(results) == 2
        assert results[0] == "翻譯A"
        assert results[1] == "翻譯B"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_translate_batch_empty(self):
        """空列表 → 回空列表"""
        service = OpenAICompatibleTranslateService({}, "zh-TW")
        results = await service.translate_batch([])
        assert results == []


class TestFactoryOpenAI:
    """測試 factory openai branch"""

    def test_factory_openai(self):
        """create_translate_service 回傳 OpenAICompatibleTranslateService"""
        config = {
            "provider": "openai",
            "openai": {"base_url": "http://localhost/v1", "model": "gpt-4o-mini"}
        }
        service = create_translate_service(config)
        assert isinstance(service, OpenAICompatibleTranslateService)

    def test_factory_openai_inherits_translate_service(self):
        """OpenAICompatibleTranslateService 是 TranslateService 子類"""
        assert issubclass(OpenAICompatibleTranslateService, TranslateService)

    def test_factory_openai_empty_base_url_no_error(self):
        """base_url 為空時 factory 層不拋錯（讓 translate_single 在 HTTP 階段失敗）"""
        config = {"provider": "openai", "openai": {"base_url": "", "model": "m"}}
        service = create_translate_service(config)
        assert isinstance(service, OpenAICompatibleTranslateService)
        assert service.base_url == ""
