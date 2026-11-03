"""user_tags_write.py — 共用 user_tags 寫入（DB + NFO），鎖內讀→算→寫。

TASK-188b-T2a：從 web.routers.collection.post_user_tags 步驟 2–5 抽出。
燈箱／助理與之後 AI 標記共用同一條寫入路徑。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List

from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path
from core.readonly_paths import resolve_owning_output_root

logger = get_logger(__name__)

_LOCK = threading.Lock()


@contextmanager
def hold_nfo_write():
    """持有 NFO 寫入鎖（與 apply_user_tags 同一把 _LOCK）；不可重入，勿在內層再呼叫 apply_user_tags。"""
    with _LOCK:
        yield


@dataclass
class ApplyResult:
    ok: bool
    error: str = ""
    user_tags: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    nfo_updated: bool = False
    readonly_no_output: bool = False
    nfo_write_blocked: bool = False


def _merge_user_tags(existing: List[str], add: List[str], remove: List[str]) -> List[str]:
    """去重合併（remove 優先），與今天 post_user_tags 逐式相同。"""
    seen_add = set()
    unique_add = []
    for t in add:
        if t not in seen_add:
            seen_add.add(t)
            unique_add.append(t)
    after_add = existing + [t for t in unique_add if t not in existing]
    return [t for t in after_add if t not in remove]


def _write_nfo(
    *,
    nfo_writer: Callable,
    is_readonly: bool,
    video,
    local_fs_path: str,
    path_mappings: dict,
    merged: List[str],
) -> tuple[bool, bool]:
    """兩個 NFO 分支（唯讀輸出夾／一般 sidecar）。回 (nfo_updated, nfo_exists)。"""
    nfo_updated = False
    nfo_exists = False
    if is_readonly:
        # 樁列（從未成功 produce、輸出夾沒有東西）直接跳過，nfo_updated 維持 False
        if video.output_dir:
            try:
                out_fs = Path(uri_to_local_fs_path(video.output_dir, path_mappings))
                nfo_candidates = list(out_fs.glob("*.nfo"))
                # 份數不是恰好一份時不猜（full-mode produce 是 holistic，正常恰有一份）
                if len(nfo_candidates) == 1:
                    nfo_updated = nfo_writer(str(nfo_candidates[0]), merged)
            except Exception as e:
                logger.warning("[user-tags] 唯讀輸出夾 NFO 寫入失敗（忽略）: %s", e)
    else:
        try:
            nfo_path = str(Path(local_fs_path).with_suffix(".nfo"))
            nfo_exists = Path(nfo_path).exists()
            nfo_updated = nfo_writer(nfo_path, merged)
        except Exception as e:
            logger.warning("[user-tags] NFO 寫入失敗（忽略）: %s", e)
    return nfo_updated, nfo_exists


def apply_user_tags(
    repo,
    file_path,
    local_fs_path,
    config,
    *,
    add,
    remove,
    ai_tagged=False,
    nfo_writer=None,
    add_filter=None,
) -> ApplyResult:
    """讀現有標籤→合併→寫 DB→寫 NFO（鎖內）。

    nfo_writer：None → core.nfo_updater.update_nfo_user_tags；
    路由傳入 update_nfo_user_tags 以保住既有 patch 目標名。
    add_filter：None 或 callable(video) -> list[str]；鎖內以最新 video 呼叫，
    回傳值併入 add。它自己拋例外時原樣往外拋（此時尚未寫 DB）。
    """
    if nfo_writer is None:
        from core.nfo_updater import update_nfo_user_tags as nfo_writer

    path_mappings = config.get("gallery", {}).get("path_mappings", {}) or {}

    with _LOCK:
        video = repo.get_by_path(file_path)
        if video is None:
            return ApplyResult(ok=False, error="找不到影片紀錄")

        existing = list(video.user_tags)
        to_add = list(add) + (list(add_filter(video)) if add_filter is not None else [])
        merged = _merge_user_tags(existing, to_add, remove)
        added = [t for t in merged if t not in existing]

        updated = repo.update_user_tags(file_path, merged, ai_tagged=ai_tagged)
        if not updated:
            return ApplyResult(ok=False, error="DB 更新失敗")

        if ai_tagged and merged == existing:
            return ApplyResult(
                ok=True,
                user_tags=merged,
                added=[],
                nfo_updated=False,
                readonly_no_output=False,
                nfo_write_blocked=False,
            )

        # Surgical NFO update — 唯讀來源改寫輸出夾那份，來源零寫入（CD-143-4）
        is_readonly = resolve_owning_output_root(file_path, config) is not None
        nfo_updated, nfo_exists = _write_nfo(
            nfo_writer=nfo_writer,
            is_readonly=is_readonly,
            video=video,
            local_fs_path=local_fs_path,
            path_mappings=path_mappings,
            merged=merged,
        )

        # readonly_no_output 是**導出的**，不是逐個失敗分支去設的（Codex PR #179 round 2）。
        # 上一輪的修法是「例外路徑補一個 readonly_no_output = True」，下一輪就被找到第四種
        # 失敗形狀：輸出夾恰有一份 NFO 但它壞掉／glob 之後消失時，`update_nfo_user_tags`
        # 是 **catch 後回 False**（`core/nfo_updater.py:50`）不是 raise ⇒ 三個分支一個都沒中，
        # 而標籤其實只進了 DB。列舉失敗分支這個形狀本身會一直生出下一個洞。
        #
        # 這個旗標要講的事情只有一句：**唯讀來源的片，媒體伺服器讀的那份 NFO 這次沒有更新。**
        # 那就直接從結果導出。`update_nfo_user_tags` 的 False 只有「檔案不存在」與「解析／
        # 寫入失敗」兩種來源（沒有「不需要改所以回 False」），所以不會誤報。
        readonly_no_output = is_readonly and not nfo_updated
        nfo_write_blocked = (not is_readonly) and nfo_exists and not nfo_updated
        return ApplyResult(
            ok=True,
            user_tags=merged,
            added=added,
            nfo_updated=nfo_updated,
            readonly_no_output=readonly_no_output,
            nfo_write_blocked=nfo_write_blocked,
        )
