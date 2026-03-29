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


# ============ help.* key coverage ============

import json
from pathlib import Path

LOCALES_ROOT = Path(__file__).parent.parent.parent / "locales"

# Flat list of all help.* keys that must exist in both zh_TW and en
HELP_KEYS = [
    # hero
    "help.hero.page_title",
    "help.hero.subtitle",
    "help.hero.privacy",
    "help.hero.btn_tutorial",
    "help.hero.btn_check_update",
    "help.hero.btn_check_update_idle",
    "help.hero.update_available_prefix",
    "help.hero.update_available_suffix",
    "help.hero.up_to_date",
    # search
    "help.search.title",
    "help.search.h6_methods",
    "help.search.h6_dragdrop",
    "help.search.h6_grid",
    "help.search.h6_badge",
    "help.search.method_full",
    "help.search.method_partial",
    "help.search.method_series",
    "help.search.method_actress",
    "help.search.drag_auto",
    "help.search.drag_batch",
    "help.search.drag_generate",
    "help.search.grid_switch",
    "help.search.grid_lightbox",
    "help.search.grid_detail",
    "help.search.grid_gallery",
    "help.search.badge_keywords",
    # batch
    "help.batch.title",
    "help.batch.h6_add",
    "help.batch.h6_favorite",
    "help.batch.h6_pause",
    "help.batch.h6_generate_all",
    "help.batch.h6_badge",
    "help.batch.add_folder",
    "help.batch.add_filter",
    "help.batch.add_batch",
    "help.batch.add_progress",
    "help.batch.fav_settings",
    "help.batch.fav_load",
    "help.batch.fav_auto",
    "help.batch.pause_pause",
    "help.batch.pause_resume",
    "help.batch.generate_all",
    "help.batch.badge_suffix",
    # format
    "help.format.title",
    "help.format.h6_default",
    "help.format.h6_fallback",
    "help.format.col_var",
    "help.format.col_desc",
    "help.format.col_example",
    "help.format.col_fallback",
    "help.format.var_num_desc",
    "help.format.var_title_desc",
    "help.format.var_actor_desc",
    "help.format.var_actors_desc",
    "help.format.var_maker_desc",
    "help.format.var_date_desc",
    "help.format.var_year_desc",
    "help.format.var_suffix_desc",
    "help.format.fallback_unknown_title",
    "help.format.fallback_unknown_actor",
    "help.format.fallback_unknown_maker",
    "help.format.fallback_unknown_date",
    "help.format.fallback_unknown_year",
    "help.format.fallback_empty",
    "help.format.default_filename",
    "help.format.default_folder",
    "help.format.fallback_folder_rule",
    "help.format.fallback_filename_rule",
    # gallery
    "help.gallery.title",
    "help.gallery.h6_trigger",
    "help.gallery.h6_features",
    "help.gallery.h6_diff",
    "help.gallery.trigger_count",
    "help.gallery.trigger_consistency",
    "help.gallery.trigger_setting",
    "help.gallery.feat_hero",
    "help.gallery.feat_browse",
    "help.gallery.feat_back",
    "help.gallery.diff_gallery",
    "help.gallery.diff_grid",
    "help.gallery.diff_grid_nav",
    # scanner
    "help.scanner.title",
    "help.scanner.h6_features",
    "help.scanner.h6_output",
    "help.scanner.h6_subtitle",
    "help.scanner.h6_jellyfin",
    "help.scanner.feat_scan",
    "help.scanner.feat_nfo",
    "help.scanner.feat_nfo_fill",
    "help.scanner.feat_terminal",
    "help.scanner.output_html",
    "help.scanner.output_copy",
    "help.scanner.output_darkmode",
    "help.scanner.subtitle_detect",
    "help.scanner.subtitle_move",
    "help.scanner.subtitle_nfo",
    "help.scanner.jellyfin_enable",
    "help.scanner.jellyfin_showcase",
    # showcase
    "help.showcase.title",
    "help.showcase.h6_modes",
    "help.showcase.h6_sort",
    "help.showcase.h6_other",
    "help.showcase.intro",
    "help.showcase.mode_grid",
    "help.showcase.mode_list",
    "help.showcase.mode_table",
    "help.showcase.sort_sort",
    "help.showcase.sort_search",
    "help.showcase.other_lightbox",
    "help.showcase.other_lightbox_detail",
    "help.showcase.other_table_cols",
    "help.showcase.other_gallery",
    "help.showcase.other_per_page",
    # shortcuts
    "help.shortcuts.title",
    "help.shortcuts.h6_search",
    "help.shortcuts.h6_showcase",
    "help.shortcuts.search_hint",
    "help.shortcuts.col_key",
    "help.shortcuts.col_context",
    "help.shortcuts.col_action",
    "help.shortcuts.ctx_lightbox_open",
    "help.shortcuts.ctx_lightbox_closed",
    "help.shortcuts.action_close_lightbox",
    "help.shortcuts.action_prev_next_video",
    "help.shortcuts.search_arrow2_ctx",
    "help.shortcuts.search_arrow2_action",
    "help.shortcuts.showcase_arrow_action",
    "help.shortcuts.showcase_a_action",
    "help.shortcuts.showcase_s_ctx",
    "help.shortcuts.showcase_s_action",
    # scraper
    "help.scraper.title",
    "help.scraper.h6_censored",
    "help.scraper.h6_uncensored",
    "help.scraper.h6_default_source",
    "help.scraper.h6_dmm_fuzzy",
    "help.scraper.h6_proxy_direct",
    "help.scraper.h6_toggle",
    "help.scraper.h6_format",
    "help.scraper.censored_dmm",
    "help.scraper.censored_others",
    "help.scraper.uncensored_d2pass",
    "help.scraper.uncensored_heyzo",
    "help.scraper.uncensored_fc2",
    "help.scraper.uncensored_avsox",
    "help.scraper.default_source_set",
    "help.scraper.default_source_effect",
    "help.scraper.dmm_fuzzy_trigger",
    "help.scraper.dmm_fuzzy_prereq",
    "help.scraper.proxy_direct_vpn",
    "help.scraper.proxy_direct_how",
    "help.scraper.toggle_uncensored",
    "help.scraper.col_source",
    "help.scraper.col_format",
    "help.scraper.col_example",
    # troubleshooting
    "help.troubleshooting.title",
    "help.troubleshooting.h6_crash",
    "help.troubleshooting.h6_display",
    "help.troubleshooting.h6_report",
    "help.troubleshooting.h6_dmm",
    "help.troubleshooting.h6_translate",
    "help.troubleshooting.crash_cause",
    "help.troubleshooting.crash_fix_label",
    "help.troubleshooting.crash_fix_1",
    "help.troubleshooting.crash_fix_2",
    "help.troubleshooting.crash_fix_3",
    "help.troubleshooting.display_cause",
    "help.troubleshooting.display_fix",
    "help.troubleshooting.report_log_path",
    "help.troubleshooting.report_debug_label",
    "help.troubleshooting.report_debug_1",
    "help.troubleshooting.report_debug_2",
    "help.troubleshooting.report_debug_3",
    "help.troubleshooting.dmm_proxy",
    "help.troubleshooting.dmm_direct",
    "help.troubleshooting.translate_ollama",
    "help.troubleshooting.translate_gemini",
    # js
    "help.js.version_load_failed",
    "help.js.check_update_failed",
    "help.js.check_update_network_error",
]

# Keys whose zh_TW values must contain HTML markup
HELP_HTML_KEYS = [
    "help.search.method_full",
    "help.search.method_partial",
    "help.search.method_series",
    "help.search.method_actress",
    "help.search.grid_lightbox",
    "help.search.grid_gallery",
    "help.search.badge_keywords",
    "help.batch.add_folder",
    "help.batch.add_filter",
    "help.batch.add_batch",
    "help.batch.add_progress",
    "help.batch.fav_settings",
    "help.batch.badge_suffix",
    "help.format.default_filename",
    "help.format.default_folder",
    "help.gallery.feat_hero",
    "help.gallery.feat_browse",
    "help.gallery.feat_back",
    "help.gallery.diff_gallery",
    "help.gallery.diff_grid",
    "help.gallery.diff_grid_nav",
    "help.scanner.output_html",
    "help.scanner.output_copy",
    "help.scanner.output_darkmode",
    "help.scanner.subtitle_detect",
    "help.scanner.subtitle_move",
    "help.scanner.jellyfin_enable",
    "help.scanner.jellyfin_showcase",
    "help.showcase.intro",
    "help.showcase.mode_grid",
    "help.showcase.mode_list",
    "help.showcase.mode_table",
    "help.showcase.sort_sort",
    "help.showcase.sort_search",
    "help.showcase.other_lightbox",
    "help.showcase.other_per_page",
    "help.scraper.censored_dmm",
    "help.scraper.censored_others",
    "help.scraper.uncensored_d2pass",
    "help.scraper.uncensored_heyzo",
    "help.scraper.uncensored_fc2",
    "help.scraper.uncensored_avsox",
    "help.scraper.default_source_set",
    "help.scraper.dmm_fuzzy_prereq",
    "help.scraper.proxy_direct_how",
    "help.scraper.toggle_uncensored",
    "help.troubleshooting.crash_cause",
    "help.troubleshooting.crash_fix_label",
    "help.troubleshooting.display_cause",
    "help.troubleshooting.display_fix",
    "help.troubleshooting.report_log_path",
    "help.troubleshooting.report_debug_label",
    "help.troubleshooting.report_debug_1",
    "help.troubleshooting.report_debug_3",
    "help.troubleshooting.dmm_proxy",
    "help.troubleshooting.dmm_direct",
    "help.troubleshooting.translate_ollama",
    "help.troubleshooting.translate_gemini",
]


def _get_nested(d: dict, dotted_key: str):
    """從 dict 取得 dot-notation key，找不到回傳 None"""
    keys = dotted_key.split(".")
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _get_all_leaf_keys(d: dict, prefix: str = "") -> list:
    """動態讀取 dict 中所有 leaf key（dot-notation 格式）"""
    keys = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_get_all_leaf_keys(v, full))
        else:
            keys.append(full)
    return keys


class TestHelpI18nKeyCompleteness:
    """確認 zh_TW.json 和 en.json 都含有所有 help.* key"""

    def test_all_help_keys_exist_in_zh_tw(self):
        zh_tw = json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        missing = [k for k in HELP_KEYS if not _get_nested(zh_tw, k)]
        assert not missing, f"Missing {len(missing)} help keys in zh_TW.json: {missing[:10]}"

    def test_all_help_keys_exist_in_en(self):
        en = json.loads((LOCALES_ROOT / "en.json").read_text(encoding="utf-8"))
        missing = [k for k in HELP_KEYS if not _get_nested(en, k)]
        assert not missing, f"Missing {len(missing)} help keys in en.json: {missing[:10]}"

    def test_html_keys_contain_markup_in_zh_tw(self):
        """含 HTML markup 的 key，zh_TW 版本確實含有 HTML tag"""
        zh_tw = json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        bad = []
        for key in HELP_HTML_KEYS:
            value = _get_nested(zh_tw, key)
            if not value:
                bad.append(f"{key}: missing")
            elif not any(tag in value for tag in ("<strong>", "<code>", "<kbd", "<a ")):
                bad.append(f"{key}: no HTML markup")
        assert not bad, f"HTML markup issues: {bad[:10]}"


# ============ All locales key completeness ============

class TestAllLocalesKeyCompleteness:
    """所有 locale 應包含 zh_TW 的每個 leaf key。

    開發期：missing keys 只 warn 不 fail（milestone 才同步其他 locale）。
    Milestone：同步後 warning 消失，表示四語系完整一致。
    """

    def test_zh_cn_has_all_keys(self):
        self._check_locale("zh_CN.json")

    def test_ja_has_all_keys(self):
        self._check_locale("ja.json")

    def test_en_has_all_keys(self):
        self._check_locale("en.json")

    def _check_locale(self, locale_file):
        import warnings
        locale_path = LOCALES_ROOT / locale_file
        if not locale_path.exists():
            pytest.skip(f"{locale_file} not yet created")
        zh_tw = json.loads((LOCALES_ROOT / "zh_TW.json").read_text(encoding="utf-8"))
        locale_data = json.loads(locale_path.read_text(encoding="utf-8"))
        all_keys = _get_all_leaf_keys(zh_tw)
        missing = [k for k in all_keys if _get_nested(locale_data, k) is None]
        if missing:
            warnings.warn(
                f"{locale_file} missing {len(missing)} keys (sync at milestone): {missing[:5]}",
                stacklevel=2,
            )
