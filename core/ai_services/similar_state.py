"""圖片相似的記憶體觀察值與「融合閘」狀態半（186-T4a，CD-186-11／-13）。

只放「最近一次跟端點互動看到什麼」：``observed_model``／``observed_dim``（最後一次
成功回應的模型）、``unreachable``、``last_error_*``、``job``（本輪索引工作進度）。
全是記憶體、重啟即歸零；索引本身的真理在 DB（``EmbeddingRepository``）。
向量矩陣屬 T5（``embedding_cache``），這裡只回「閘開不開」的 bool。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from core.database import EmbeddingRepository

_lock = threading.Lock()

observed_model: Optional[str] = None
observed_dim: Optional[int] = None
unreachable: bool = False
last_error_kind: Optional[str] = None
last_error_check: Optional[str] = None
job: dict = {"kind": None, "done": 0, "outcome": None}


def observe_success(model: str, dim: int) -> None:
    """端點回了合法向量：記下模型、解除 unreachable、清錯誤。"""
    global observed_model, observed_dim, unreachable, last_error_kind, last_error_check
    with _lock:
        observed_model, observed_dim = model, int(dim)
        unreachable = False
        last_error_kind = last_error_check = None


def observe_failure(kind: Optional[str], check: Optional[str]) -> None:
    """端點出錯：``kind == 'unreachable'`` 才算連不上；契約不符只記 check。"""
    global unreachable, last_error_kind, last_error_check
    with _lock:
        unreachable = kind == "unreachable"
        last_error_kind, last_error_check = kind, check


def snapshot() -> dict:
    with _lock:
        return {
            "observed_model": observed_model,
            "observed_dim": observed_dim,
            "unreachable": unreachable,
            "kind": last_error_kind,
            "check": last_error_check,
            "job": dict(job),
        }


def job_begin(kind: str) -> None:
    global job
    with _lock:
        job = {"kind": kind, "done": 0, "outcome": None}


def job_progress() -> None:
    with _lock:
        job["done"] += 1


def job_end(outcome: str) -> None:
    with _lock:
        job["outcome"] = outcome


def model_changed(index_model: Optional[str], index_dim: Optional[int]) -> bool:
    """觀察到的模型跟索引模型不同（觀察值或索引模型任一為空＝沒資訊，視為沒變）。"""
    with _lock:
        if observed_model is None or index_model is None:
            return False
        return (observed_model, observed_dim) != (index_model, index_dim)


def fusion_gate_from_state(config: dict, state: dict) -> bool:
    """CD-186-13 狀態半的純判斷：enabled ∧ model 已設 ∧ complete=='1' ∧ 觀察值相容。

    ``state`` 須是呼叫端已讀好的 ``get_index_state()`` 結果；本函式不再讀 DB。
    """
    cfg = (config.get("ai_services") or {}).get("image_similar") or {}
    if not cfg.get("enabled"):
        return False
    if not state["model"] or state["complete"] != "1":
        return False
    return not model_changed(state["model"], state["dim"])


def fusion_gate_open(config: dict, db_path: Optional[Path] = None) -> bool:
    """CD-186-13 的狀態半：enabled ∧ index_model 已設 ∧ index_complete=='1' ∧ 觀察值相容。"""
    cfg = (config.get("ai_services") or {}).get("image_similar") or {}
    if not cfg.get("enabled"):
        return False
    return fusion_gate_from_state(config, EmbeddingRepository(db_path).get_index_state())


def format_similar_model_id(index_model: Optional[str] = None, *, fused: bool = False) -> str:
    """CD-186-15：融合未參與＝``rule-based:v1``；參與＝``rule-based:v1+rrf:<model[:128]>``。"""
    if fused and index_model:
        return f"rule-based:v1+rrf:{index_model[:128]}"
    return "rule-based:v1"


def fusion_vectors(config: dict, db_path: Optional[Path] = None):
    """CD-186-13：閘開時回 ``dict[int, array]``；否則 ``None``。

    ``enabled`` 為假時必須在碰任何 DB 之前就回 ``None``。
    索引狀態只讀一次：同一份 ``state`` 同時判斷閘與決定載哪個 (model, dim)。
    """
    cfg = (config.get("ai_services") or {}).get("image_similar") or {}
    if not cfg.get("enabled"):
        return None
    state = EmbeddingRepository(db_path).get_index_state()
    if not fusion_gate_from_state(config, state):
        return None
    from core.ai_services.embedding_cache import EmbeddingMatrixCache
    return EmbeddingMatrixCache.get(state["model"], state["dim"], db_path)
