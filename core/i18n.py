"""
core/i18n.py — 多語系翻譯核心模組

提供：
- load_locale(): 載入並快取 locale JSON
- t(): 帶 fallback chain 的翻譯函數
- get_merged_translations(): 深層 merge zh-TW base + overlay（供前端 window.__i18n）
- detect_locale_from_accept_language(): 解析 HTTP Accept-Language header
"""

import json
import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from core.logger import get_logger

logger = get_logger(__name__)

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED_LOCALES = ("zh-TW", "zh-CN", "ja", "en")
FALLBACK_LOCALE = "zh-TW"


@lru_cache(maxsize=8)
def load_locale(locale: str) -> dict:
    """載入並快取一個 locale 的 JSON。找不到時回傳空 dict。"""
    if not locale:
        return {}
    filename = locale.replace("-", "_") + ".json"
    path = LOCALES_DIR / filename
    if not path.exists():
        logger.debug("[i18n] locale 檔案不存在: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[i18n] 無法載入 locale 檔案 %s: %s", path, e)
        return {}


def _nested_get(data: dict, key: str):
    """dot-path 取值；找不到回傳 None。"""
    if not key:
        return None
    parts = key.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _substitute_params(text: str, params: dict) -> str:
    """用 {placeholder} 格式替換參數。缺少的 param 保留原樣。永不拋例外。"""
    if not params:
        return text

    def replacer(match):
        key = match.group(1)
        if key in params:
            return str(params[key])
        return match.group(0)  # 保留 {placeholder} 原樣

    try:
        return re.sub(r"\{(\w+)\}", replacer, text)
    except Exception:
        return text


def t(key: str, locale: str = FALLBACK_LOCALE, **params) -> str:
    """
    Fallback chain: 當前語系 → zh-TW → [key]。
    params 以 {placeholder} 格式填入（缺 param 保留原樣）。
    永不 throw。
    """
    try:
        # 防衛性：locale 為 None 時回退到 FALLBACK_LOCALE
        effective_locale = locale if locale else FALLBACK_LOCALE

        # 嘗試當前語系
        if effective_locale != FALLBACK_LOCALE:
            data = load_locale(effective_locale)
            value = _nested_get(data, key)
            if isinstance(value, str):
                return _substitute_params(value, params)

        # 嘗試 zh-TW fallback
        data = load_locale(FALLBACK_LOCALE)
        value = _nested_get(data, key)
        if isinstance(value, str):
            return _substitute_params(value, params)

        # 所有語系都找不到 → 回傳 [key]
        return f"[{key}]"

    except Exception as e:
        logger.warning("[i18n] t('%s', locale='%s') 發生例外: %s", key, locale, e)
        return f"[{key}]"


def _deep_merge(base: dict, overlay: dict) -> dict:
    """深層 merge：overlay 的值覆蓋 base，但不清除 base 中 overlay 沒有的 key。"""
    result = deepcopy(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def get_merged_translations(locale: str) -> dict:
    """
    回傳 zh-TW base dict 深層合併 locale overlay。
    前端 window.__i18n 直接使用，不需 fallback chain。
    """
    base = load_locale(FALLBACK_LOCALE)
    if locale == FALLBACK_LOCALE:
        return deepcopy(base)
    overlay = load_locale(locale)
    return _deep_merge(base, overlay)


def detect_locale_from_accept_language(accept_language: str) -> str:
    """
    解析 HTTP Accept-Language header，回傳 SUPPORTED_LOCALES 之一。
    尊重 q-value 權重（RFC 7231），高優先語言優先匹配。
    無法解析或對應不到時回傳 "en"。
    """
    if not accept_language or not accept_language.strip():
        return "en"

    # 解析每個語言標籤及其 q-value，按權重降序排列
    entries = []
    for part in accept_language.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if ";q=" in part:
            lang, q = part.split(";q=", 1)
            try:
                weight = float(q.strip())
            except ValueError:
                weight = 0.0
        else:
            lang = part
            weight = 1.0
        entries.append((lang.strip(), weight))
    entries.sort(key=lambda x: x[1], reverse=True)

    # 按權重順序匹配
    for lang, _ in entries:
        if lang in ("zh-tw", "zh-hant"):
            return "zh-TW"
        if lang in ("zh-cn", "zh-hans"):
            return "zh-CN"
        if lang == "zh":
            return "zh-CN"
        if lang == "ja" or lang.startswith("ja-"):
            return "ja"
        if lang == "en" or lang.startswith("en-"):
            return "en"

    return "en"
