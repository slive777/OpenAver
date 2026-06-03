"""多來源結果 merger（pure function）— epic §5.1.1 / CD-61-9.

職責：把多個 scraper 回傳的 `Video` 合併成單一 `Video`。

合併契約（§5.1.1）：
1. **文字/meta 整包贏**：依 `user_order` 找第一個存在於 candidates 的來源作為
   text_source，整包採用其 title / actresses / tags / series / maker / director
   與 meta（date / duration / rating / votes）。text_source 為空的欄位才往
   `user_order` 後續來源 fallback（避免主來源缺欄時整片清空）。
2. **封面跟 user_order**：`cover_url` / `sample_images` 改依 `user_order` 找第一個
   該欄非空的來源；cover_url 與 sample_images 各自獨立解析（可來自不同來源）。

本模組是 PURE：不 import config、不認識任何來源偏好設定、不做 to_legacy_dict /
maker-prefix fallback / _source 注入（那些由 caller `search_jav()` 負責）。
caller 透過 user_order 的排序編碼來源偏好。
"""
from __future__ import annotations

from typing import Optional

from core.scrapers.models import Video

# 文字欄位（整包來自 text_source，空值往後 fallback）
_TEXT_FIELDS = ('title', 'actresses', 'tags', 'series', 'maker', 'director')
# meta 欄位（同樣整包來自 text_source，空值往後 fallback）
# 注意：`label` 不在 §5.1.1 表列，但既有 merge 會 backfill（feeds NFO），保留 parity（61a-6 review B1）
_STR_META_FIELDS = ('date', 'label')
# None-sentinel meta 欄位（0 / 0.0 視為有值）
_OPTIONAL_META_FIELDS = ('duration', 'rating', 'votes')


def _is_empty(value: object, none_sentinel: bool) -> bool:
    """欄位空值判定。none_sentinel=True 用 `is None`（保 0 / 0.0），否則 falsy。"""
    if none_sentinel:
        return value is None
    return not value


def _ordered_candidates(
    candidates: dict[str, Video], order: list[str]
) -> list[Video]:
    """依 order 排出 candidates 中存在的來源，order 未涵蓋的接在後面（insertion order）。"""
    seen: set[str] = set()
    result: list[Video] = []
    for sid in order:
        if sid in candidates and sid not in seen:
            result.append(candidates[sid])
            seen.add(sid)
    for sid, video in candidates.items():
        if sid not in seen:
            result.append(video)
            seen.add(sid)
    return result


def _first_non_empty(videos: list[Video], field: str, none_sentinel: bool):
    """從已排序的 videos 中取第一個該欄非空的值；全空回 None（caller 自處理）。"""
    for video in videos:
        value = getattr(video, field)
        if not _is_empty(value, none_sentinel):
            return value
    return None


def merge_results(
    candidates: dict[str, Video],
    user_order: list[str],
) -> Optional[Video]:
    """合併多來源結果為單一 `Video`。

    Args:
        candidates: `source_id -> Video`（即 search_jav 的 all_data 原形）。
        user_order: 文字/meta 與封面欄位的偏好順序（caller 已把 primary 排到最前）。

    Returns:
        合併後的 `Video`；`candidates` 為空時回 `None`（防禦性，caller 應已 guard）。
    """
    if not candidates:
        return None

    # text/meta：依 user_order 排序的 candidate 序列
    text_ordered = _ordered_candidates(candidates, user_order)
    text_source = text_ordered[0]  # 第一個存在來源 = base（整包贏）

    updates: dict[str, object] = {}

    # 文字 + str-meta：text_source 為空才往後 fallback
    for field in (*_TEXT_FIELDS, *_STR_META_FIELDS):
        if _is_empty(getattr(text_source, field), none_sentinel=False):
            fallback = _first_non_empty(text_ordered, field, none_sentinel=False)
            if fallback is not None:
                updates[field] = fallback

    # None-sentinel meta：duration / rating / votes
    for field in _OPTIONAL_META_FIELDS:
        if _is_empty(getattr(text_source, field), none_sentinel=True):
            fallback = _first_non_empty(text_ordered, field, none_sentinel=True)
            if fallback is not None:
                updates[field] = fallback

    # 封面欄位：依 user_order 找第一個該欄非空（各欄獨立解析，可來自不同來源）
    cover_ordered = _ordered_candidates(candidates, user_order)
    for field in ('cover_url', 'sample_images'):
        value = _first_non_empty(cover_ordered, field, none_sentinel=False)
        if value is not None:
            updates[field] = value

    return text_source.model_copy(update=updates) if updates else text_source
