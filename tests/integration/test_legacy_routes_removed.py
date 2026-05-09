"""
tests/integration/test_legacy_routes_removed.py

56b-T3: 驗證 /clip-lab 路由已完全移除。
- GET /clip-lab → 404
- OpenAPI schema 不含 /clip-lab path（含 include_in_schema=False 也不會出現）
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from web.app import app
    return TestClient(app)


def test_get_clip_lab_returns_404(client):
    """GET /clip-lab 應該回 404（router 已刪除）"""
    response = client.get("/clip-lab")
    assert response.status_code == 404, (
        f"預期 /clip-lab 回 404，實際 {response.status_code}（router 是否仍掛載？）"
    )


def test_openapi_schema_no_clip_lab(client):
    """OpenAPI schema 不應出現 /clip-lab path 或 clip-lab tag"""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    paths = schema.get("paths", {})
    for path in paths:
        assert "/clip-lab" not in path, (
            f"OpenAPI schema 仍含 clip-lab 相關 path：{path}"
        )

    # tags list（router 原 tag="clip-lab"）也不應出現
    schema_str = str(schema)
    assert '"clip-lab"' not in schema_str, "OpenAPI schema 仍含 'clip-lab' tag"
