"""enrich_contract.py — enrich 記帳合約的中性原子（無 side-effect、無網路、無寫檔）。

依賴僅 `os` / `dataclasses` / `typing` / `core.path_utils`（repo 走 duck typing 由呼叫端傳入、
不 import `core.database`）。**不 import** `core.enricher` / `core.readonly_producer`（避免循環依賴；
本模組是被它們共用的底層）。

存在理由（feature/105）：enrich「寫完後記帳 has_servable_cover」的判斷原本被手抄多份，
enricher 那份含磁碟複驗（正確），唯讀那份漏了（Bug 1 破圖）。把單一原子收斂於此，
三呼叫點物理共用同一份磁碟真相，消除鏡射漂移。
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from core.path_utils import uri_to_local_fs_path


@dataclass
class EnrichResult:
    success: bool
    nfo_written: bool
    cover_written: bool
    extrafanart_written: int
    fields_filled: List[str]
    source_used: str
    error: Optional[str]
    reason: Optional[str] = None


def enrich_success(*, nfo_written, cover_written, extrafanart_written,
                   fields_filled, source_used,
                   has_servable_cover=None, reason=None) -> EnrichResult:
    """成功 EnrichResult 建構器（feature/105，CD-105-7）。

    六個成功構造（enricher tail / fetch_samples_only / 唯讀 enrich-single /
    唯讀 samples ×2 / batch 唯讀）物理共用此份，消除「成功回報 shape 漏鏡射」漂移。

    reason 派生單一住此：`has_servable_cover is not None`（有封面站）→ 派生
    'hit'/'no_cover'（覆蓋 reason 參數）；為 None（samples 站）→ 用顯式 reason 參數。
    `success=True`／`error=None` 恆定。其餘欄位（nfo_written / extrafanart_written /
    fields_filled / source_used）builder 不計算，原樣塞入——刻意差異全由呼叫端實參表達
    （CD-105-6-4：不開第二套函式）。keyword-only 避免位置錯位。
    """
    if has_servable_cover is not None:
        reason = "hit" if has_servable_cover else "no_cover"
    return EnrichResult(
        success=True,
        error=None,
        nfo_written=nfo_written,
        cover_written=cover_written,
        extrafanart_written=extrafanart_written,
        fields_filled=fields_filled,
        source_used=source_used,
        reason=reason,
    )


def cover_uri_is_servable(cover_uri, path_mappings) -> bool:
    """封面 URI 是否「前端 /thumb 真的服務得到」的最小磁碟真相原子。

    `bool(cover_uri)`（DB 有記 cover_path）**且** 該封面實體檔在磁碟上實際存在
    （uri_to_local_fs_path 反解後 os.path.exists）。cover_uri 為空 → 短路 False，
    不呼叫 os.path.exists。
    """
    return bool(cover_uri) and os.path.exists(uri_to_local_fs_path(cover_uri, path_mappings))


def should_preserve_cover(write_cover, overwrite_existing, cover_exists) -> bool:
    """純政策：這次是否「不寫封面、保留既有」。cover_exists 由呼叫端各自算
    （非唯讀 with_suffix('.jpg') 來源旁；唯讀 cover_uri_is_servable 走 DB
    cover_path + path-mapping）——政策共用、封面定位各異（spec §5 末項）。"""
    return (not write_cover) or (cover_exists and not overwrite_existing)


def apply_cover_preserve(strategy, write_cover, overwrite_existing, cover_exists):
    """gate→strategy 接線：命中保留 → ('none',)（不產出檔案）；否則原 strategy。"""
    return ('none',) if should_preserve_cover(write_cover, overwrite_existing, cover_exists) else strategy


def effective_original_title(meta, existing) -> str:
    """重刮回空原文標題時保留 DB 既有值。meta 有非空 original_title → 用之；
    否則回退 existing.original_title（existing 為 None → '')。唯一 preserve 邏輯，
    非唯讀 enricher 與唯讀 producer 皆呼叫此份（方案 A：唯一 preserve 在 helper）。"""
    return meta.get('original_title') or (existing.original_title if existing else '')


def compute_has_servable_cover(repo, path_uri, path_mappings) -> bool:
    """寫完 + commit 後重讀 DB 最終 cover_path，再確認實體封面檔是否服務得到。

    reason=hit 必須是「前端 /thumb 真的服務得到」。/thumb（scanner.py get_thumb）
    有兩道 gate，兩道都過才服務得到，reason=hit 必須同時鏡射：
      gate 1（scanner.py:1276-1277）：DB cover_path 非空，否則 404。
      gate 2（scanner.py:1290/1300/1332-1333）：cache miss 或 disabled 時要讀
        實體封面檔（uri_to_local_fs_path 反解後 generate / fallback FileResponse），
        檔不在 → 404。（cache hit 於 :1263 直接 serve WebP 不碰實體檔，見下方 false-negative）
    故不能只查 DB cover_path 非空（只鏡射 gate 1，Codex PR #98 P2）：DB 有記
    cover_path、但該實體封面檔已被刪/移／path_mapping 失效解不到時，/thumb 於
    cache miss/disabled 會 404 → 飛入破圖，卻誤計 hit。
    亦不能用磁碟 sidecar 真相（Path(fs_path).with_suffix('.jpg')）判：磁碟有 .jpg
    但 DB cover_path 空（散落 sidecar 未入 DB／db·nfo-sourced 命中跳過 :514
    _db_upsert）會漏 gate 1（Codex P1，v0.11.9）。故重讀 DB 最終 cover_path，
    並用 /thumb 同一組解析（uri_to_local_fs_path + 同 path_mappings）確認實體檔存在。
    此重讀應在所有寫檔 + _db_upsert + nfo_mtime UPDATE 之後（同步、已 commit），
    故看到的是最終 DB 狀態。
    已知並接受的 false-negative（安全方向）：cache hit（stale WebP 已快取）但實體
    封面檔已刪時，/thumb 仍能從快取 serve（:1263），此處卻判 no_cover。代價是「服務
    得到的封面不飛入」（不破圖）；反向 false-positive（判 hit 卻 404 破圖）代價更高，
    故偏保守。

    Args:
        repo: VideoRepository（呼叫端建構、已完成寫入/upsert）。
        path_uri: DB row 的 key（canonical file:/// URI），必須與 upsert 寫入時同一 key。
        path_mappings: WSL 反解用；與 /thumb 同一組解析。
    """
    row = repo.get_by_path(path_uri)
    return cover_uri_is_servable(row.cover_path if row else "", path_mappings)
