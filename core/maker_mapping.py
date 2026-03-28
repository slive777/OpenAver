"""
maker_mapping.json shared loader

供 models.py / scraper.py / gallery_scanner.py / search.py 共用。
模組層僅 import stdlib + core.logger（無 core/ 業務模組），避免循環依賴。
JavDB fallback 使用函數內部 lazy import。
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger(__name__)

# 片商對照表檔案路徑（專案根目錄 / maker_mapping.json）
MAKER_MAPPING_FILE: Path = Path(__file__).parent.parent / "maker_mapping.json"

# module-level cache（None = 尚未載入；dict = 已載入的完整 JSON）
_cache: Optional[dict] = None


def _load_raw() -> dict:
    """載入並 cache 整個 JSON（失敗/不存在回傳空 dict）"""
    global _cache
    if _cache is not None:
        return _cache

    if not MAKER_MAPPING_FILE.exists():
        _cache = {}
        return _cache

    try:
        with open(MAKER_MAPPING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        _cache = data
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning("maker_mapping: 無法載入 %s，回傳空 dict（%s）", MAKER_MAPPING_FILE, e)
        _cache = {}

    return _cache


def load_name_mapping() -> Dict[str, str]:
    """
    回傳 name_mapping 層。

    - 新格式（有 _meta + name_mapping + prefix_mapping）→ 回傳 name_mapping dict
    - 舊格式（無 _meta，純平坦 prefix dict）→ 回傳 {}
    - 檔案不存在或 JSON 損毀 → 回傳 {}
    """
    raw = _load_raw()
    if "_meta" in raw and "name_mapping" in raw:
        nm = raw["name_mapping"]
        if isinstance(nm, dict):
            # 過濾掉 _meta 等非 mapping key（防禦）
            return {k: v for k, v in nm.items() if k != "_meta"}
        return {}
    return {}


def load_prefix_mapping() -> Dict[str, str]:
    """
    回傳 prefix_mapping 層。

    - 新格式（有 _meta + prefix_mapping）→ 回傳 prefix_mapping dict
    - 舊格式（無 _meta，純平坦 prefix dict）→ 回傳整個 dict（向下相容）
    - 檔案不存在或 JSON 損毀 → 回傳 {}
    """
    raw = _load_raw()
    if "_meta" in raw and "prefix_mapping" in raw:
        pm = raw["prefix_mapping"]
        if isinstance(pm, dict):
            return {k: v for k, v in pm.items() if k != "_meta"}
        return {}
    # 舊格式：整個 dict，跳過 _meta（萬一有的話）
    return {k: v for k, v in raw.items() if k != "_meta"}


def normalize_maker_name(maker) -> str:
    """
    從 name_mapping 查表；無對照 → 原值。

    - 空字串 → 回傳 ""
    - None → 回傳 ""（型別防禦）
    """
    if not maker:
        return ""
    nm = load_name_mapping()
    return nm.get(maker, maker)


def save_prefix_entry(prefix: str, maker: str) -> None:
    """
    只更新 prefix_mapping 層，不動 name_mapping 層；失敗靜默。

    寫入後使 cache 失效（下次 load 重讀）。
    """
    global _cache

    try:
        raw = _load_raw()

        if "_meta" in raw and "prefix_mapping" in raw:
            # 新格式：只更新 prefix_mapping
            raw["prefix_mapping"][prefix] = maker
        else:
            # 舊格式：直接寫入頂層
            raw[prefix] = maker

        with open(MAKER_MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("maker_mapping: 寫入 %s 失敗，略過（%s）", MAKER_MAPPING_FILE, e)
    finally:
        # 無論成功失敗，讓 cache 失效（下次 load 重讀）
        _cache = None


def get_maker_by_prefix(number: str) -> str:
    """
    從 prefix_mapping 查片商名；prefix miss → JavDB fallback + save_prefix_entry。

    - 無字母前綴（如 "123"、""）→ 回傳 ""
    """
    mapping = load_prefix_mapping()
    match = re.match(r"^([A-Za-z]+)", number)
    if not match:
        return ""

    prefix = match.group(1).upper()
    if prefix in mapping:
        return mapping[prefix]

    # JavDB fallback（lazy import 避免循環依賴）
    try:
        from core.scrapers import JavDBScraper
        scraper = JavDBScraper()
        video = scraper.search(number)
        if video and video.maker and not re.match(r"^\d{4}(-\d{2}){0,2}$", video.maker):
            normalized = normalize_maker_name(video.maker)
            save_prefix_entry(prefix, normalized)
            return normalized
    except Exception as e:
        logger.debug("maker_mapping: JavDB fallback 失敗（%s）", e)

    return ""
