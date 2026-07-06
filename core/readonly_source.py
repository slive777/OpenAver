"""
唯讀來源判定 — 純資料流層（無 IO、無 load_config、無 UI 文案）。

供 (a) scraper `_readonly_source_error`（單檔端點 guard）與 (b) showcase video
payload 的 `is_readonly_source` 旗標共用同一段比對邏輯（CD-90b-9 Codex 修正）。

模組定位：leaf-consumer，同時 import `iter_gallery_sources`（core.config）+
`coerce_to_file_uri`/`is_path_under_dir`（core.path_utils）。config 與 path_utils
互不 import、亦不 import 本模組 → 無循環。
"""

from core.config import iter_gallery_sources
from core.path_utils import is_path_under_dir, to_file_uri, uri_to_fs_path


def _canonical_source_prefix(path: str, path_mappings) -> str:
    """把 config 來源路徑 canonical 成與 DB row 同命名空間的 file:/// URI 前綴。

    PR #93 Codex P2-f：不能用 coerce_to_file_uri —— 它對「已是 file:/// URI」的來源
    原樣回、**不套 path_mappings**；但 producer 存 DB row 的 path 是用掃描 FS 路徑走
    to_file_uri(..., mappings) → mapped 命名空間（WSL 下 /mnt/nas/ro → //NAS/share/ro）。
    於是 file:/// URI 型唯讀來源的前綴（unmapped）對不上 DB path（mapped）→ 唯讀 guard /
    showcase 旗標 / switch purge 全 miss。改走 uri_to_fs_path → to_file_uri(mappings)：
    - URI 型：strip 回 FS path，再 to_file_uri 帶 mappings → 落 mapped 命名空間（對齊 DB）。
    - FS-path 型：uri_to_fs_path 近似 pass-through（normalize），等價原 coerce（無回歸）。
    - 非 WSL / 無 mapping：to_file_uri 的 mapping 分支不觸發，round-trip 回同一 URI 形。
    """
    return to_file_uri(uri_to_fs_path(path), path_mappings)  # uri-no-reverse: native config source path, no DB-mapped namespace


def is_path_readonly(file_uri: str, readonly_prefixes, writable_prefixes=None) -> bool:
    """純比對、無 IO：由**最具體（最長匹配前綴）的來源**決定歸屬 → 唯讀勝才 True。

    巢狀 overlap 兩方向都要對（PR #93 Codex P2）：
    - 唯讀父 D:/media + 可寫子 D:/media/local，片在子夾 → 可寫子更具體 → False（可寫）
    - 可寫父 D:/media + 唯讀子 D:/media/cloud，片在子夾 → 唯讀子更具體 → True（唯讀）
    「任一可寫壓任一唯讀」只對第一種、會把第二種（使用者明確標唯讀的子夾）誤判可寫
    （上一輪修法的反向回歸）。改以命中前綴的字串長度近似巢狀深度：coerce_to_file_uri
    不替一般路徑加尾斜線，長度差對應深度差。打平（同長度同時屬兩表＝設定自相矛盾）偏可寫。

    file_uri / readonly_prefixes / writable_prefixes 皆須為呼叫端已 coerce 的 file:/// URI。
    writable_prefixes 預設 None → 無可寫前綴，退回純唯讀比對（相容既有呼叫）。
    """
    best_ro = max((len(p) for p in readonly_prefixes if is_path_under_dir(file_uri, p)), default=-1)
    if best_ro < 0:
        return False
    best_wr = max((len(p) for p in (writable_prefixes or []) if is_path_under_dir(file_uri, p)), default=-1)
    return best_ro > best_wr


def readonly_source_prefixes(gallery_config, path_mappings) -> list:
    """枚舉唯讀來源、coerce 成 file:/// URI 前綴集（每 request 算一次）。

    iter_gallery_sources → 過濾 s.readonly and s.path → _canonical_source_prefix（P2-f：
    走 uri_to_fs_path→to_file_uri(mappings)，讓 file:/// URI 型來源也套映射對齊 DB）；
    拋 ValueError 的髒來源 skip（mirror showcase _get_configured_dirs）。
    """
    prefixes = []
    for source in iter_gallery_sources(gallery_config):
        if not source.readonly or not source.path:
            continue
        try:
            prefixes.append(_canonical_source_prefix(source.path, path_mappings))
        except ValueError:
            continue
    return prefixes


def writable_source_prefixes(gallery_config, path_mappings) -> list:
    """枚舉可寫（非唯讀）來源、coerce 成 file:/// URI 前綴集（每 request 算一次）。

    供 is_path_readonly 的 override 語意用（可寫來源巢狀在唯讀夾下時，其片不算唯讀）。
    鏡射 readonly_source_prefixes，僅 filter 反過來（not source.readonly）；同走
    _canonical_source_prefix（P2-f）；拋 ValueError 的髒來源同樣 skip。
    """
    prefixes = []
    for source in iter_gallery_sources(gallery_config):
        if source.readonly or not source.path:
            continue
        try:
            prefixes.append(_canonical_source_prefix(source.path, path_mappings))
        except ValueError:
            continue
    return prefixes
