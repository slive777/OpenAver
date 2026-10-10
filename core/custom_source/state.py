"""自訂來源驗收狀態：config.json 持久化（只走 mutate_config）、五態推導、操作世代、單飛行。

key 缺席＝沒有任何狀態，不補預設（讀取原語不寫檔）。
鎖序單向：state lock（LOCK）→ config 鎖；mutate_config 的 callback 內不取 LOCK。
"""
import threading
import time

from core.config import load_config, mutate_config

KEY = "custom_sources"
MAX_CASES = 20
MAX_MISMATCHES = 3
MAX_VALUE_CHARS = 120
STATUSES = ("passed", "failed")

LOCK = threading.RLock()
_gens = {}
_running_id = None


def _entries(cfg):
    value = cfg.get(KEY) if isinstance(cfg, dict) else None
    return value if isinstance(value, dict) else {}


def read_all():
    """回傳 {id: entry} 的淺拷貝；key 缺席或型別不對回 {}。不寫檔。"""
    return dict(_entries(load_config()))


def read_entry(source_id):
    return _entries(load_config()).get(source_id)


def get_gen(source_id):
    with LOCK:
        return _gens.get(source_id, 0)


def bump_gen(source_id):
    with LOCK:
        _gens[source_id] = _gens.get(source_id, 0) + 1
        return _gens[source_id]


def get_running_id():
    with LOCK:
        return _running_id


def try_begin_verify(source_id):
    global _running_id
    with LOCK:
        if _running_id is not None:
            return False
        _running_id = source_id
        return True


def end_verify(source_id):
    global _running_id
    with LOCK:
        if _running_id == source_id:
            _running_id = None


def _clip(value):
    return str(value)[:MAX_VALUE_CHARS]


def _clip_case(case):
    case = case if isinstance(case, dict) else {}
    mismatches = case.get("mismatches")
    kept = []
    for m in (mismatches if isinstance(mismatches, list) else [])[:MAX_MISMATCHES]:
        m = m if isinstance(m, dict) else {}
        kept.append({
            "key": _clip(m.get("key", "")),
            "expected": _clip(m.get("expected", "")),
            "actual": _clip(m.get("actual", "")),
            "url": _clip(m.get("url", "")),
        })
    return {
        "index": case.get("index"),
        "number": case.get("number"),
        "passed": bool(case.get("passed")),
        "mismatches": kept,
    }


def _clip_result(result):
    result = result if isinstance(result, dict) else {}
    cases = result.get("cases")
    return {
        "total": result.get("total", 0),
        "failed": result.get("failed", 0),
        "cases": [_clip_case(c) for c in (cases if isinstance(cases, list) else [])[:MAX_CASES]],
    }


def record_result(source_id, sha256, status, result, gen_seen):
    """寫入驗收結果；gen 與 gen_seen 不同則不寫、回 False（世代圍欄，無略過後門）。"""
    if status not in STATUSES:
        raise ValueError("status must be 'passed' or 'failed'")
    with LOCK:
        if _gens.get(source_id, 0) != gen_seen:
            return False
        verified_at = int(time.time())
        clipped = _clip_result(result)

        def _apply(cfg):
            entries = cfg.get(KEY)
            if not isinstance(entries, dict):
                entries = cfg[KEY] = {}
            old = entries.get(source_id)
            keep = (
                status == "passed"
                and isinstance(old, dict)
                and old.get("sha256") == sha256
                and bool(old.get("enabled"))
            )
            entries[source_id] = {
                "sha256": sha256,
                "status": status,
                "verified_at": verified_at,
                "enabled": keep,
                "last_result": clipped,
            }

        mutate_config(_apply)
        return True


class _Abort(Exception):
    """callback 內判定不合格時中止 mutate_config（例外發生在落盤之前，不寫檔）。"""


def set_enabled(source_id, enabled, current_sha):
    """僅在紀錄存在、status==passed、sha256==current_sha 時寫入；否則不寫檔、回 False。"""

    def _apply(cfg):
        entry = _entries(cfg).get(source_id)
        if not (
            isinstance(entry, dict)
            and entry.get("status") == "passed"
            and entry.get("sha256") == current_sha
        ):
            raise _Abort
        entry["enabled"] = bool(enabled)

    with LOCK:
        try:
            mutate_config(_apply)
        except _Abort:
            return False
        return True


def clear(source_id):
    with LOCK:
        if read_entry(source_id) is None:
            return False
        mutate_config(lambda cfg: _entries(cfg).pop(source_id, None))
        return True


def derive_status(loaded, entry, running_id):
    """load_failed → verifying → unverified → passed/failed（紀錄壞一律 unverified）。"""
    if loaded.spec is None or loaded.error is not None:
        return "load_failed"
    if running_id == loaded.id:
        return "verifying"
    if not isinstance(entry, dict) or entry.get("sha256") != loaded.sha256:
        return "unverified"
    if entry.get("status") not in STATUSES:
        return "unverified"
    return entry["status"]


def effective_enabled(entry, status):
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("enabled")) and status == "passed"
