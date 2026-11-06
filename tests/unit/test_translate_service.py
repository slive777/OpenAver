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


    def test_factory_gemini_missing_api_key(self):
        """Gemini provider 缺少 API Key 拋出 ValueError"""
        config = {"provider": "gemini", "gemini": {}}

        with pytest.raises(ValueError) as exc_info:
            create_translate_service(config)

        assert "API Key" in str(exc_info.value)


# ============ OllamaTranslateService 配置測試 ============

class TestOllamaTranslateServiceConfig:
    """測試 Ollama 服務配置處理"""


    def test_url_trailing_slash_removed(self):
        """URL 尾斜線自動移除"""
        config = {"url": "http://localhost:11434/"}
        service = OllamaTranslateService(config)

        assert service.ollama_url == "http://localhost:11434"


# ============ 抽象類測試 ============


# ============ 語言 prompt 組裝測試 ============


# ============ ja 短路測試 ============


# ============ OpenAICompatibleTranslateService 測試 ============

class TestOpenAICompatibleTranslateService:
    """測試 OpenAI Compatible 翻譯服務"""


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


# ============ OllamaTranslateService._clean_output 純字串測試 ============

class TestOllamaCleanOutput:
    """測試 _clean_output 字串清理行為（純邏輯，零 mock）"""

    def setup_method(self):
        self.service = OllamaTranslateService({})


    def test_strip_think_tag(self):
        """<think>...</think> 標籤應被移除，保留後面的翻譯"""
        assert self.service._clean_output('<think>思考過程</think>翻譯結果') == '翻譯結果'

    def test_strip_korean_translation_prefix(self):
        assert self.service._clean_output('번역: 한국어 결과') == '한국어 결과'


# ============ OllamaTranslateService._parse_batch_output 純字串測試 ============

class TestOllamaParseBatchOutput:
    """測試 _parse_batch_output 批次輸出解析（純邏輯，零 mock）"""

    def setup_method(self):
        self.service = OllamaTranslateService({})


# ============ GeminiTranslateService.translate_single 四分支測試 ============

class TestGeminiTranslateSingleBranches:
    """測試 Gemini translate_single 四個回應分支（mock httpx，零真連線）

    mock 模式沿用 TestOpenAICompatibleTranslateService：
    patch("core.translate_service.httpx.AsyncClient", return_value=mock_client_instance)
    mock_client_instance 支援 async with（__aenter__/__aexit__），
    resp 物件有 .raise_for_status()（no-op）與 .json()。
    target_language 使用預設 zh-TW，避免 :230-231 ja 短路。
    """

    def _make_service(self):
        return GeminiTranslateService({"api_key": "fake-key-for-test"}, "zh-TW")

    def _make_mock_client(self, json_data):
        """建立支援 async with 的 httpx mock，回傳指定 json_data"""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = json_data

        mock_client_instance = MagicMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        return mock_client_instance


class TestProperNounRule:
    """172-T6：zh-TW／zh-CN 翻譯 prompt 要求人名、品牌名保留原文"""

    RULE = "人名、品牌名保留原文"

    def _check_cloud(self, lang, rule4):
        from core.translate_service import LANGUAGE_PROMPTS, build_cloud_translate_prompt
        rules = LANGUAGE_PROMPTS[lang]["gemini_rules"]
        prompt = build_cloud_translate_prompt("新人女優デビュー", lang)
        assert self.RULE in rules
        assert self.RULE in prompt
        assert rule4 in rules
        assert rules.index(rule4) < rules.index(self.RULE)
        assert rule4 in prompt
        assert prompt.index(rule4) < prompt.index(self.RULE)

    def _check_ollama(self, lang, lang_name):
        from core.translate_service import LANGUAGE_PROMPTS
        system = LANGUAGE_PROMPTS[lang]["ollama_system"]
        assert self.RULE in system
        assert lang_name in system
        assert "人名、品牌名除外" in system

    def test_zh_tw_gemini_rules_keep_proper_nouns(self):
        self._check_cloud("zh-TW", "4. 只輸出翻譯結果，不要額外說明")

    def test_korean_prompt_targets_korean(self):
        from core.translate_service import LANGUAGE_PROMPTS, build_cloud_translate_prompt

        assert "한국어" in LANGUAGE_PROMPTS["ko"]["ollama_system"]
        prompt = build_cloud_translate_prompt("新人女優デビュー", "ko")
        assert "한국어" in prompt
        assert "인명" in prompt


    def test_zh_tw_ollama_system_keep_proper_nouns(self):
        self._check_ollama("zh-TW", "繁體中文")
