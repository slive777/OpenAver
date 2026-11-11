"""core/version_group.py — 多版本分組原語（TASK-198b-T1，CD-198b 系列）。

`multipart_group.group_rows()`（分集）把同段收成 `VideoGroup`；這一層再按
「同資料夾＋正規化番號」把多個 `VideoGroup` 收成一個 `Work`（一部作品、多個版本）。
「版本」就是既有 `VideoGroup`，不另造型別；`versions[0]` 為預設版本。

`group_works()`／`resolve_*()` 的 `tier_of` 由呼叫端注入（只對各版本
`members[0]` 呼叫）；`None`＝全部視為未探針。本模組不 import 資料庫層，
URI 運算只在檔尾 `resolve_*` 且全走 `core.path_utils`。
"""

import os
from dataclasses import dataclass
from typing import Callable, Dict, Generic, List, Optional, Tuple, TypeVar

from core.cover_attributes import version_kinds
from core.media_probe import RESOLUTION_TIERS
from core.multipart_group import VideoGroup, folder_uri_prefix, group_rows
from core.path_utils import uri_to_fs_path, uri_to_local_fs_path

T = TypeVar("T")


@dataclass
class Work(Generic[T]):
    """一部作品：versions 依預設順序排（versions[0]＝預設版本，長度 >= 1）。"""

    versions: List[VideoGroup[T]]
    data_source: Optional[int]


def _key_for(fs_path: str, number: Optional[str]) -> Tuple[str, ...]:
    num = (number or "").strip().upper()
    if not num:
        return ("path", fs_path)
    return ('num', os.path.dirname(fs_path), num)


def _has_data(group: VideoGroup[T]) -> bool:
    return (getattr(group.members[0], "nfo_mtime", 0) or 0) > 0


def _default_rank_key(
    group: VideoGroup[T], fs_path: str, tier: Optional[str]
) -> Tuple[int, int, int, float, str]:
    kinds = version_kinds(
        os.path.basename(fs_path), getattr(group.members[0], "tags", None) or []
    )
    subtitle_rank = 0 if 'subtitle' in kinds else 1
    tier_rank = -RESOLUTION_TIERS.index(tier) if tier in RESOLUTION_TIERS else 1
    original_rank = 1 if set(kinds) & {"cracked", "ltx", "leaked"} else 0
    mtime_rank = -(getattr(group.members[0], "mtime", 0) or 0)
    return (subtitle_rank, tier_rank, original_rank, mtime_rank, group.members[0].path)


def _build_work(
    groups: List[VideoGroup[T]],
    fs_path_of: Callable[[T], str],
    tier_of: Optional[Callable[[T], Optional[str]]],
) -> Work[T]:
    if len(groups) == 1:
        sole = groups[0]
        return Work(versions=list(groups), data_source=0 if _has_data(sole) else None)
    ranked = []
    for group in groups:
        fs_path = fs_path_of(group.members[0])
        tier = tier_of(group.members[0]) if tier_of is not None else None
        ranked.append((_default_rank_key(group, fs_path, tier), group))
    ranked.sort(key=lambda pair: pair[0])
    versions = [group for _, group in ranked]
    data_source = next((i for i, v in enumerate(versions) if _has_data(v)), None)
    return Work(versions=versions, data_source=data_source)


def group_works(
    rows: List[T],
    fs_path_of: Callable[[T], str],
    tier_of: Optional[Callable[[T], Optional[str]]] = None,
) -> List[Work[T]]:
    if not rows:
        return []
    cached: Dict[int, str] = {}
    for row in rows:
        key = id(row)
        if key not in cached:
            cached[key] = fs_path_of(row)

    def cached_fs_path_of(row: T) -> str:
        return cached[id(row)]

    buckets: Dict[Tuple[str, ...], List[VideoGroup[T]]] = {}
    order: List[Tuple[str, ...]] = []
    for group in group_rows(rows, cached_fs_path_of):
        work_key_value = work_key(group, cached_fs_path_of)
        if work_key_value not in buckets:
            buckets[work_key_value] = []
            order.append(work_key_value)
        buckets[work_key_value].append(group)
    return [_build_work(buckets[k], cached_fs_path_of, tier_of) for k in order]


def work_key(group: VideoGroup[T], fs_path_of: Callable[[T], str]) -> Tuple[str, ...]:
    number = None
    for member in group.members:
        candidate = getattr(member, "number", None)
        if candidate and (not isinstance(candidate, str) or candidate.strip()):
            number = candidate
            break
    return _key_for(fs_path_of(group.members[0]), number)


def work_key_of_row(row: T, fs_path: str) -> Tuple[str, ...]:
    return _key_for(fs_path, getattr(row, "number", None))


def version_containing(work: Work[T], uri: str) -> Optional[int]:
    for index, version in enumerate(work.versions):
        for member in version.members:
            if getattr(member, "path", None) == uri:
                return index
    return None


def representative_paths(work: Work[T]) -> List[str]:
    return [version.members[0].path for version in work.versions]


def resolve_work(
    repo,
    target_uri: str,
    path_mappings: dict,
    folder_source_uri: Optional[str] = None,
    tier_of: Optional[Callable] = None,
) -> Optional[Work]:
    source_uri = target_uri if folder_source_uri is None else folder_source_uri
    folder_fs = os.path.dirname(uri_to_fs_path(source_uri))  # uri-no-reverse: 只取 dirname 拼前綴，隨即 to_file_uri 回 DB namespace，不做磁碟 I/O
    rows = repo.get_by_folder_uri_prefix(folder_uri_prefix(folder_fs, path_mappings))
    fs_path_of = lambda r: uri_to_local_fs_path(r.path, path_mappings)
    for work in group_works(rows, fs_path_of, tier_of):
        if version_containing(work, target_uri) is not None:
            return work
    return None


def resolve_works_bulk(
    repo,
    target_uris: List[str],
    path_mappings: dict,
    tier_of: Optional[Callable] = None,
) -> Dict[str, Optional[Work]]:
    out: Dict[str, Optional[Work]] = {}
    folder_index_cache: Dict[str, dict] = {}
    for target_uri in target_uris:
        if target_uri in out:
            continue
        folder_fs = os.path.dirname(uri_to_fs_path(target_uri))  # uri-no-reverse: 只取 dirname 拼前綴，隨即 to_file_uri 回 DB namespace，不做磁碟 I/O（同 resolve_group）
        prefix = folder_uri_prefix(folder_fs, path_mappings)
        index = folder_index_cache.get(prefix)
        if index is None:
            index = {}
            rows = repo.get_by_folder_uri_prefix(prefix)
            fs_path_of = lambda r: uri_to_local_fs_path(r.path, path_mappings)
            for work in group_works(rows, fs_path_of, tier_of):
                for version in work.versions:
                    for member in version.members:
                        index[member.path] = work
            folder_index_cache[prefix] = index
        out[target_uri] = index.get(target_uri)
    return out


def work_user_tags(work: Work) -> List[str]:
    """整部作品的標籤聯集：依版本順序串接各版本 members[0].user_tags、逐字去重。"""
    return list(dict.fromkeys(
        t for version in work.versions for t in (version.members[0].user_tags or [])
    ))


def reread_work_user_tags(repo, target_uri: str, path_mappings: dict) -> List[str]:
    """寫完後重讀作品聯集：內部重新 resolve_work（不傳 tier_of）；查無作品退回該 uri 那列自己的 user_tags，列也不存在回 []。"""
    work = resolve_work(repo, target_uri, path_mappings)
    if work is None:
        video = repo.get_by_path(target_uri)
        return list(video.user_tags) if video is not None else []
    return work_user_tags(work)
