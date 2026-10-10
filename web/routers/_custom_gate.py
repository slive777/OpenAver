"""自訂來源路由層 gate 轉譯：reason 碼 → 「哪一條沒過」的中文句（不重寫判斷）。"""
from typing import Optional, Tuple

from core.scraper import normalize_number
from core.source_config import validate_source_id

REASON_TEXT = {
    "not_loaded": "找不到這個自訂來源",
    "load_failed": "這個自訂來源的檔案載入失敗，請到設定頁檢查",
    "verifying": "這個自訂來源正在驗收中，請稍後再試",
    "unverified": "這個自訂來源尚未通過驗收，請先驗收",
    "failed": "這個自訂來源驗收沒有通過（站方可能改版了），請到設定頁重跑驗收",
    "disabled": "這個自訂來源尚未啟用，請到設定頁打開",
    "pattern_mismatch": "這個番號不符合此自訂來源接受的格式",
}


def refusal_for(source: str, number: str) -> Optional[Tuple[str, str]]:
    """custom:<id> 沒過 gate → (reason, 句)；可用 → None。"""
    if not validate_source_id(source):
        return "not_loaded", REASON_TEXT["not_loaded"]
    from core.custom_source import gate  # lazy：AC-165-8
    result = gate.check_usable(source.split(":", 1)[1], normalize_number(number))
    if result.ok:
        return None
    return result.reason, REASON_TEXT.get(result.reason, REASON_TEXT["not_loaded"])
