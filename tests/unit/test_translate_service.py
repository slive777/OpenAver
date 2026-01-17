"""
test_translate_service.py - 翻譯服務抽象層單元測試

測試範圍：
- 工廠函數 create_translate_service()
- 配置默認值處理
- 錯誤處理（未知 provider、未實現 provider）

注意：實際 Ollama API 調用測試放在 tests/smoke/test_translate_live.py
"""

import pytest
from core.translate_service import (
    TranslateService,
    OllamaTranslateService,
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

    def test_factory_gemini_not_implemented(self):
        """Gemini provider 拋出 NotImplementedError"""
        config = {"provider": "gemini", "gemini": {}}

        with pytest.raises(NotImplementedError) as exc_info:
            create_translate_service(config)

        assert "Task 2" in str(exc_info.value)

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
