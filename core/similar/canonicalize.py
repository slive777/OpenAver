from typing import Iterable

from core.logger import get_logger

logger = get_logger(__name__)

_HARDCODED_ALIAS_MAP: dict[str, str] = {
    "中出": "中出し",
    "内射": "中出し",
    "中出射精": "中出し",
    "單體作品": "単体作品",
    "単體作品": "単体作品",
    "デジモ": "數位馬賽克",
    "スレンダー": "苗條",
    "苗条": "苗條",
    "3P・4P": "多P",
    "3P": "多P",
    "4P": "多P",
    "キス・接吻": "口交",
    "接吻": "口交",
    "キス": "口交",
    "高画質": "高畫質",
    "ハイビジョン": "高畫質",
    "独占配信": "DMM獨家",
    "中文字幕版": "中文字幕",
}

_STOPWORDS: frozenset[str] = frozenset({
    "単体作品",
    "高畫質",
    "DMM獨家",
    "數位馬賽克",
    "薄馬賽克",
    "中文字幕",
    "4K",
    "偶像藝人",
    "DVD多士爐",
    "高解析度",
    "ブルーレイ",
    "Blu-ray",
})

# module-level cache — None = not loaded yet
_merged_alias_map: dict[str, str] | None = None


def _load_merged_map() -> dict[str, str]:
    """
    Lazy-load DB tag_aliases and merge with hardcoded map.
    DB entries override hardcoded entries (DB 優先).
    Falls back to hardcoded-only on any DB error.
    Result is cached in _merged_alias_map until _invalidate_cache() is called.
    """
    global _merged_alias_map
    if _merged_alias_map is not None:
        return _merged_alias_map

    # lazy import — must stay inside function to avoid circular import
    # and to avoid triggering DB connection at module import time
    from core.database import TagAliasRepository

    try:
        repo = TagAliasRepository()
        records = repo.get_all()
        # flatten: {primary_name: "X", aliases: ["Y", "Z"]} → {"Y": "X", "Z": "X"}
        db_flat: dict[str, str] = {}
        for record in records:
            for alias in record.aliases:
                if alias:
                    db_flat[alias] = record.primary_name
        # DB 後 merge → DB 優先
        merged = {**_HARDCODED_ALIAS_MAP, **db_flat}
    except Exception:
        logger.warning("[canonicalize] DB load 失敗，fallback hardcoded-only")
        merged = dict(_HARDCODED_ALIAS_MAP)

    _merged_alias_map = merged
    return _merged_alias_map


def _invalidate_cache() -> None:
    """清 module-level alias map cache，下次 canonicalize() 重新從 DB 讀取。"""
    global _merged_alias_map
    _merged_alias_map = None


def canonicalize(tags: Iterable[str]) -> list[str]:
    alias_map = _load_merged_map()
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if not tag:
            continue
        canonical = alias_map.get(tag, tag)
        if canonical in _STOPWORDS:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def canonical_video_tags(video) -> list[str]:
    """刮削 tags 在前、user_tags 在後，經 canonicalize 去重／別名／停用詞。

    只收 str 元素（AI／scrape 可能寫入 dict 等非字串）；其餘略過。
    """
    tags = [t for t in (video.tags or []) if isinstance(t, str)]
    user_tags = [t for t in (video.user_tags or []) if isinstance(t, str)]
    return canonicalize([*tags, *user_tags])


def alias_key(name: str) -> str:
    """只解析別名、不濾停用詞，與 canonicalize 同一份 map。"""
    return _load_merged_map().get(name, name)
