"""189a-T8：三個 AI 補跑狀態端點的回應 key 集合快照（遷移前後都不得變）。

只碰公開入口：TestClient 打端點；人臉降級形狀靠 ``snapshot`` 接縫＋設定接縫，
不 setattr 任何狀態內部欄位。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.ai_services import faces_state
from web.app import app

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

TAGS_KEYS = {
    "running", "job_kind", "done", "skipped", "slow", "waiting", "stop_reason", "outcome",
    "pending", "total", "tagged", "resumable", "unreachable", "last_success_at",
}
SIMILAR_KEYS = {
    "running", "job_kind", "done", "indexed", "total", "pending", "unreadable",
    "unreachable", "kind", "check", "model", "last_success_at", "model_changed", "complete",
}
FACES_KEYS = {
    "running", "job_kind", "processed", "total", "pending", "unreadable", "stopped_reason",
    "kind", "check", "target_model", "rebuild_count", "using", "observed", "last_success_at",
}
FACES_DEGRADED_KEYS = FACES_KEYS | {"degraded", "degraded_kind", "degraded_check"}


def test_status_endpoints_keep_their_keys(monkeypatch):
    """使用者升級後打開設定頁／AI 助理 → 三個補跑狀態仍讀得到全部既有欄位、不多不少。"""
    monkeypatch.setattr(
        "web.routers.ai_services.load_config",
        lambda: {"ai_services": {"faces": {"enabled": True, "url": "http://127.0.0.1:1"}}},
    )
    c = TestClient(app)  # 不進 lifespan：只打純讀端點
    assert set(c.get("/api/ai/tags/backfill/status").json()) == TAGS_KEYS
    assert set(c.get("/api/ai/similar/status").json()) == SIMILAR_KEYS

    real = faces_state.snapshot
    monkeypatch.setattr(faces_state, "snapshot", lambda: {**real(), "degraded": False})
    assert set(c.get("/api/ai/faces/status").json()) == FACES_KEYS

    monkeypatch.setattr(
        faces_state, "snapshot",
        lambda: {**real(), "degraded": True, "kind": "unreachable", "check": "x"},
    )
    assert set(c.get("/api/ai/faces/status").json()) == FACES_DEGRADED_KEYS
