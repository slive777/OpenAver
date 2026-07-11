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
    def test_missing_file_returns_empty_dict(self, locales_dir):
        result = load_locale("zh-TW")
        assert result == {}

    def test_loads_valid_json(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        result = load_locale("zh-TW")
        assert result == {"nav": {"search": "搜尋"}}

    def test_hyphen_to_underscore_filename(self, locales_dir):
        """zh-TW → zh_TW.json"""
        _write_locale(locales_dir, "zh-TW", {"key": "value"})
        result = load_locale("zh-TW")
        assert result["key"] == "value"

    def test_returns_cached_result(self, locales_dir):
        """lru_cache 應快取結果（同一物件）"""
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        r1 = load_locale("en")
        r2 = load_locale("en")
        assert r1 is r2  # 相同 object（來自 cache）


# ============ t() fallback chain ============

class TestTFallbackChain:
    def test_returns_value_in_current_locale(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        result = t("nav.search", locale="en")
        assert result == "Search"

    def test_falls_back_to_zh_tw_when_key_missing_in_locale(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋", "help": "說明"}})
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        # en 沒有 nav.help，應 fallback 到 zh-TW
        result = t("nav.help", locale="en")
        assert result == "說明"

    def test_returns_bracketed_key_when_missing_everywhere(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {}})
        _write_locale(locales_dir, "en", {})
        result = t("nav.nonexistent", locale="en")
        assert result == "[nav.nonexistent]"

    def test_returns_bracketed_key_when_zh_tw_also_missing(self, locales_dir):
        # zh-TW 連 key 都沒有
        result = t("some.missing.key", locale="zh-TW")
        assert result == "[some.missing.key]"

    def test_default_locale_is_zh_tw(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        result = t("nav.search")  # 不指定 locale
        assert result == "搜尋"


# ============ t() param substitution ============

class TestTParamSubstitution:
    def test_substitutes_params(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"count": "找到 {count} 個結果"}})
        result = t("msg.count", locale="zh-TW", count=5)
        assert result == "找到 5 個結果"

    def test_substitutes_multiple_params(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"greet": "你好，{name}！共 {count} 項"}})
        result = t("msg.greet", locale="zh-TW", name="Alice", count=3)
        assert result == "你好，Alice！共 3 項"

    def test_preserves_placeholder_when_param_missing(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"count": "找到 {count} 個結果"}})
        # 不傳 count，應保留 {count} 原樣
        result = t("msg.count", locale="zh-TW")
        assert result == "找到 {count} 個結果"

    def test_partial_param_preserved(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"detail": "{a} 和 {b}"}})
        result = t("msg.detail", locale="zh-TW", a="X")
        assert result == "X 和 {b}"

    def test_never_raises_with_weird_key(self, locales_dir):
        # 奇怪的 key 不拋例外
        result = t("", locale="zh-TW")
        assert isinstance(result, str)

    def test_never_raises_with_none_locale(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        # None locale 應優雅處理（fallback to zh-TW）
        try:
            result = t("nav.search", locale=None)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"t() raised an exception: {e}")

    def test_never_raises_with_extra_params(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        # 多餘的 params 不拋例外
        result = t("nav.search", locale="zh-TW", extra_param="ignored")
        assert result == "搜尋"

    def test_never_raises_with_numeric_params(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"msg": {"n": "{n} 項"}})
        result = t("msg.n", locale="zh-TW", n=42)
        assert result == "42 項"


# ============ get_merged_translations ============

class TestGetMergedTranslations:
    def test_merged_has_zh_tw_keys_as_base(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋", "help": "說明"}})
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        merged = get_merged_translations("en")
        # zh-TW 有 help，en 沒有，merged 應保留 zh-TW 的 help
        assert merged["nav"]["help"] == "說明"

    def test_merged_overlays_current_locale_values(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        _write_locale(locales_dir, "en", {"nav": {"search": "Search"}})
        merged = get_merged_translations("en")
        # en 覆蓋了 search
        assert merged["nav"]["search"] == "Search"

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

    def test_zh_tw_locale_returns_itself(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        merged = get_merged_translations("zh-TW")
        assert merged["nav"]["search"] == "搜尋"

    def test_unsupported_locale_returns_zh_tw_base(self, locales_dir):
        _write_locale(locales_dir, "zh-TW", {"nav": {"search": "搜尋"}})
        # 不支援的 locale（無對應 JSON）→ 回傳 zh-TW 全集
        merged = get_merged_translations("fr")
        assert merged["nav"]["search"] == "搜尋"


# ============ detect_locale_from_accept_language ============

class TestDetectLocaleFromAcceptLanguage:
    def test_detect_zh_tw(self):
        assert detect_locale_from_accept_language("zh-TW,zh;q=0.9") == "zh-TW"

    def test_detect_zh_tw_from_hant(self):
        assert detect_locale_from_accept_language("zh-Hant,en;q=0.8") == "zh-TW"

    def test_detect_zh_tw_with_quality(self):
        assert detect_locale_from_accept_language("zh-TW;q=0.9,en;q=0.8") == "zh-TW"

    def test_detect_zh_cn_from_zh_cn(self):
        assert detect_locale_from_accept_language("zh-CN,zh;q=0.9") == "zh-CN"

    def test_detect_zh_cn_from_hans(self):
        assert detect_locale_from_accept_language("zh-Hans,en;q=0.8") == "zh-CN"

    def test_detect_zh_cn_from_zh(self):
        """zh（無 TW/Hant 限定）→ zh-CN"""
        assert detect_locale_from_accept_language("zh") == "zh-CN"

    def test_detect_zh_cn_from_zh_no_region(self):
        assert detect_locale_from_accept_language("zh,en;q=0.8") == "zh-CN"

    def test_detect_ja(self):
        assert detect_locale_from_accept_language("ja,en;q=0.9") == "ja"

    def test_detect_ja_with_region(self):
        assert detect_locale_from_accept_language("ja-JP,ja;q=0.9,en;q=0.8") == "ja"

    def test_detect_en_from_en(self):
        assert detect_locale_from_accept_language("en,fr;q=0.9") == "en"

    def test_detect_en_as_default_for_unknown(self):
        assert detect_locale_from_accept_language("fr,de;q=0.9") == "en"

    def test_detect_empty_string_returns_en(self):
        assert detect_locale_from_accept_language("") == "en"

    def test_detect_none_like_empty(self):
        """空字串 → en（預設）"""
        assert detect_locale_from_accept_language("") == "en"

    def test_zh_tw_takes_priority_over_zh_cn_when_both_present(self):
        """zh-TW 出現時，即使也有 zh-CN，以 zh-TW 優先（任何含 zh-TW 的 header）"""
        result = detect_locale_from_accept_language("zh-TW;q=0.9,zh-CN;q=0.8,en;q=0.7")
        assert result == "zh-TW"
