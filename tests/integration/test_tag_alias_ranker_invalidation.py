"""
tests/integration/test_tag_alias_ranker_invalidation.py
Integration tests — tag alias CRUD 後 SimilarRankerCache invalidation（58-P1）

Verifies that each of the 4 write endpoints in /api/tag-aliases triggers
SimilarRankerCache.invalidate(), and that an invalidate() failure is
non-blocking (endpoint still returns 200).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import init_db, TagAliasRepository
from core.similar.ranker_cache import SimilarRankerCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(primary_name, aliases=None):
    record = MagicMock()
    record.primary_name = primary_name
    record.aliases = aliases or []
    record.source = "manual"
    record.created_at = datetime(2026, 4, 13)
    record.updated_at = None
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure cache is clean before and after each test."""
    SimilarRankerCache._instance = None
    yield
    SimilarRankerCache._instance = None


@pytest.fixture
def app_with_real_db(tmp_path, monkeypatch):
    """
    App + TestClient backed by a real SQLite DB.
    Patches VideoRepository inside ranker_cache so corpus rebuilds from our
    test DB (which has 0 videos — ranker still builds, just empty corpus).
    """
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # Patch ranker_cache VideoRepository to use our test DB
    from core.database import VideoRepository
    monkeypatch.setattr(
        "core.similar.ranker_cache.VideoRepository",
        lambda: VideoRepository(db_path),
    )

    # Patch tag_alias router to use our test DB
    monkeypatch.setattr(
        "web.routers.tag_alias.init_db",
        lambda *a, **kw: init_db(db_path),
    )
    monkeypatch.setattr(
        "web.routers.tag_alias.TagAliasRepository",
        lambda *a, **kw: TagAliasRepository(db_path),
    )

    from web.routers.tag_alias import router as tag_alias_router
    app = FastAPI()
    app.include_router(tag_alias_router)
    client = TestClient(app)
    return client, db_path


# ---------------------------------------------------------------------------
# Tests — 4 write endpoints each invalidate cache
# ---------------------------------------------------------------------------

class TestTagAliasCRUDInvalidatesRankerCache:
    """Each write endpoint must invalidate SimilarRankerCache."""

    def test_create_alias_group_invalidates_cache(self, app_with_real_db):
        """POST /api/tag-aliases — creates group → cache invalidated."""
        client, db_path = app_with_real_db

        # Warm the cache first
        first = SimilarRankerCache.get()
        assert first is not None

        resp = client.post("/api/tag-aliases", json={
            "primary_name": "巨乳",
            "aliases": ["Big Tits"],
        })
        assert resp.status_code == 200, resp.text

        second = SimilarRankerCache.get()
        assert second is not first, \
            "POST /api/tag-aliases must invalidate SimilarRankerCache"

    def test_delete_alias_group_invalidates_cache(self, app_with_real_db):
        """DELETE /api/tag-aliases/{name} — deletes group → cache invalidated."""
        client, db_path = app_with_real_db

        # Seed a group first
        client.post("/api/tag-aliases", json={"primary_name": "女僕", "aliases": []})

        # Warm cache after seed
        SimilarRankerCache._instance = None
        first = SimilarRankerCache.get()
        assert first is not None

        resp = client.delete("/api/tag-aliases/女僕")
        assert resp.status_code == 200, resp.text

        second = SimilarRankerCache.get()
        assert second is not first, \
            "DELETE /api/tag-aliases/{name} must invalidate SimilarRankerCache"

    def test_add_alias_invalidates_cache(self, app_with_real_db):
        """POST /api/tag-aliases/{name}/alias — adds alias → cache invalidated."""
        client, db_path = app_with_real_db

        # Seed a group first
        client.post("/api/tag-aliases", json={"primary_name": "高畫質", "aliases": []})

        # Warm cache after seed
        SimilarRankerCache._instance = None
        first = SimilarRankerCache.get()
        assert first is not None

        resp = client.post("/api/tag-aliases/高畫質/alias", json={"alias": "HD"})
        assert resp.status_code == 200, resp.text

        second = SimilarRankerCache.get()
        assert second is not first, \
            "POST /api/tag-aliases/{name}/alias must invalidate SimilarRankerCache"

    def test_remove_alias_invalidates_cache(self, app_with_real_db):
        """DELETE /api/tag-aliases/{name}/alias/{alias} — removes alias → cache invalidated."""
        client, db_path = app_with_real_db

        # Seed a group with an alias
        client.post("/api/tag-aliases", json={"primary_name": "單體作品", "aliases": ["Solo"]})

        # Warm cache after seed
        SimilarRankerCache._instance = None
        first = SimilarRankerCache.get()
        assert first is not None

        resp = client.delete("/api/tag-aliases/單體作品/alias/Solo")
        assert resp.status_code == 200, resp.text

        second = SimilarRankerCache.get()
        assert second is not first, \
            "DELETE /api/tag-aliases/{name}/alias/{alias} must invalidate SimilarRankerCache"


# ---------------------------------------------------------------------------
# Non-blocking: invalidate() failure must not break write endpoints
# ---------------------------------------------------------------------------

class TestTagAliasRankerInvalidateNonBlocking:
    """SimilarRankerCache.invalidate() raising must not break write endpoints."""

    def test_create_still_200_when_invalidate_raises(self, app_with_real_db):
        """POST /api/tag-aliases still returns 200 even if SimilarRankerCache.invalidate raises."""
        client, db_path = app_with_real_db

        with patch(
            "web.routers.tag_alias.SimilarRankerCache.invalidate",
            side_effect=RuntimeError("simulated invalidate failure"),
        ):
            resp = client.post("/api/tag-aliases", json={
                "primary_name": "測試標籤",
                "aliases": [],
            })

        assert resp.status_code == 200, (
            f"POST /api/tag-aliases must still return 200 when SimilarRankerCache.invalidate raises; "
            f"got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["success"] is True
