"""
tests/unit/test_i18n.py — core.i18n unit tests

TDD-lite: 測試先於實作，覆蓋所有邊界條件。
使用 tmp_path + monkeypatch 來 mock LOCALES_DIR，不依賴真實 locale files。
"""

import json
import pytest
from pathlib import Path

import core.i18n as core_i18n
from core.i18n import (
    load_locale,
    t,
    get_merged_translations,
    detect_locale_from_accept_language,
)


# ============ helpers ============

def _write_locale(locales_dir: Path, locale_code: str, data: dict) -> None:
    """寫入 locale JSON 檔案（locale code 轉底線格式，如 zh-TW → zh_TW.json）"""
    filename = locale_code.replace("-", "_") + ".json"
    (locales_dir / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def locales_dir(tmp_path):
    """建立暫時 locales 目錄，並 patch LOCALES_DIR"""
    d = tmp_path / "locales"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def patch_locales_dir(locales_dir, monkeypatch):
    """每個 test 都 patch LOCALES_DIR，並清除 lru_cache"""
    monkeypatch.setattr(core_i18n, "LOCALES_DIR", locales_dir)
    # 清除 lru_cache，確保每個 test 獨立
    load_locale.cache_clear()
    yield
    load_locale.cache_clear()


# ============ load_locale ============

class TestLoadLocale:


    def test_hyphen_to_underscore_filename(self, locales_dir):
        """zh-TW → zh_TW.json"""
        _write_locale(locales_dir, "zh-TW", {"key": "value"})
        result = load_locale("zh-TW")
        assert result["key"] == "value"


# ============ t() fallback chain ============

class TestTFallbackChain:

    def test_falls_back_to_zh_tw_when_key_missing_in_locale(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋", "help": "說明"}})
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        # en 沒有 nav.help，應 fallback 到 zh-TW
        result = t("nav.help", locale="en")
        assert result == "說明"


# ============ t() param substitution ============

class TestTParamSubstitution:
    def test_substitutes_params(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"count": "找到 {count} 個結果"}})
        result = t("msg.count", locale="zh-TW", count=5)
        assert result == "找到 5 個結果"


# ============ get_merged_translations ============

class TestGetMergedTranslations:


    def test_deep_merge_not_shallow(self, locales_dir):
        """深層 merge：overlay 只覆蓋有設值的 key，不清除同層其他 key"""
        _write_locale(locales_dir, "zh-TW", {
            "nav": {"search": "搜尋", "scanner": "列表生成", "help": "說明"}
        })
        _write_locale(locales_dir, "ja", {
            "nav": {"search": "検索"}  # 只有 search，scanner 和 help 保留 zh-TW
        })
        merged = get_merged_translations("ja")
        assert merged["nav"]["search"] == "検索"
        assert merged["nav"]["scanner"] == "列表生成"
        assert merged["nav"]["help"] == "說明"


# ============ detect_locale_from_accept_language ============

class TestDetectLocaleFromAcceptLanguage:


    def test_zh_tw_takes_priority_over_zh_cn_when_both_present(self):
        """zh-TW 出現時，即使也有 zh-CN，以 zh-TW 優先（任何含 zh-TW 的 header）"""
        result = detect_locale_from_accept_language("zh-TW;q=0.9,zh-CN;q=0.8,en;q=0.7")
        assert result == "zh-TW"

    def test_korean_header_selects_korean(self):
        assert detect_locale_from_accept_language("en-US;q=0.8,ko-KR;q=1.0") == "ko"
