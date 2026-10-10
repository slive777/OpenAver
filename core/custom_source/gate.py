"""自訂來源 gate：七種 reason 的唯一判斷處；單次讀檔、通過時回同一份快照。"""
from dataclasses import dataclass
from typing import Optional

from core.custom_source import registry, state
from core.custom_source.interpret import accepts_number
from core.custom_source.registry import LoadedSource
from core.custom_source.state import derive_status, effective_enabled

REASONS = (
    "not_loaded", "load_failed", "verifying", "unverified",
    "failed", "disabled", "pattern_mismatch",
)


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: Optional[str] = None
    loaded: Optional[LoadedSource] = None


def judge(loaded, entry, running_id, number=None):
    """給定已載入快照與紀錄，回 (status, GateResult)；views 與 check_usable 共用。"""
    status = derive_status(loaded, entry, running_id)
    if status == "load_failed":
        return status, GateResult(False, "load_failed")
    if status == "verifying":
        return status, GateResult(False, "verifying")
    if status == "unverified":
        return status, GateResult(False, "unverified")
    if status == "failed":
        return status, GateResult(False, "failed")
    if not effective_enabled(entry, status):
        return status, GateResult(False, "disabled")
    if number is not None and not accepts_number(loaded.spec, number):
        return status, GateResult(False, "pattern_mismatch")
    return status, GateResult(True, None, loaded)


def check_usable(source_id, number=None):
    loaded = registry.load_one(source_id)
    if loaded is None:
        return GateResult(False, "not_loaded")
    _, result = judge(loaded, state.read_entry(loaded.id), state.get_running_id(), number)
    return result
