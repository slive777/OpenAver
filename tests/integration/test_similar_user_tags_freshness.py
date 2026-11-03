"""I-FRESH oracle：燈箱改 user_tags 後再開星空，分數立刻反映新標籤（188a-T3）。

真路由＋真 SQLite（tmp_path）；不 mock SimilarRankerCache／VideoRepository 行為。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from core.similar.ranker_cache import SimilarRankerCache
from web.routers.collection import user_tags_router
from web.routers.similar import router as similar_router

_NUM_T = "FRESH-001"
_NUM_X = "FRESH-002"


def _make_video(idx: int, number: str, tags: list[str], maker: str = "MakerF") -> Video:
    return Video(
        path=to_file_uri(f"/fake/fresh_{idx:03d}.mp4"),
        number=number,
        title=f"Fresh {idx}",
        maker=maker,
        series=None,
        actresses=[],
        tags=tags,
        release_date="2023-01-01",
        duration=90,
        cover_path="",
        mtime=float(idx),
    )


@pytest.fixture(autouse=True)
def _isolate_ranker_and_alias_cache():
    from core.similar.canonicalize import _invalidate_cache

    SimilarRankerCache._instance = None
    _invalidate_cache()
    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    with patch("core.database.TagAliasRepository", return_value=mock_alias_repo):
        yield
    SimilarRankerCache._instance = None
    _invalidate_cache()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    rows = [
        _make_video(1, _NUM_T, ["rareA", "rareT"]),
        _make_video(2, _NUM_X, ["rareA", "xOnly"]),
    ]
    rows += [
        _make_video(10 + i, f"PAD-{i:03d}", [f"pad{i}"], maker=f"MakerP{i}")
        for i in range(40)
    ]
    repo.upsert_batch(rows)

    class _Repo(VideoRepository):
        def __init__(self, _=None):
            super().__init__(db_path)

    monkeypatch.setattr("web.routers.similar.VideoRepository", _Repo)
    monkeypatch.setattr("core.similar.ranker_cache.VideoRepository", _Repo)
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: db_path)
    monkeypatch.setattr("web.routers.similar.load_config", lambda: {})
    monkeypatch.setattr("web.routers.collection.load_config", lambda: {})

    app = FastAPI()
    app.include_router(similar_router)
    app.include_router(user_tags_router)
    yield TestClient(app), repo


def _x_score(client: TestClient):
    data = client.get(f"/api/similar-covers/by-number/{_NUM_T}?limit=12").json()
    return {r["number"]: r["cosine_score"] for r in data["results"]}.get(_NUM_X)


def _post_user_tag(client: TestClient, repo: VideoRepository, number: str, *, add=(), remove=()):
    path = repo.get_by_number(number).path
    resp = client.post(
        "/api/user-tags",
        json={"file_path": path, "add": list(add), "remove": list(remove)},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_user_tag_edit_is_visible_without_restart(client):
    """燈箱替 T／X 貼上同一標籤後再開星空，X 分數上升；拿掉後回到原值。"""
    client, repo = client

    # ① 先暖快取，取得基線 s0（X 必須已在結果內）
    s0 = _x_score(client)
    assert s0 is not None

    # ② 兩邊各貼「校服」
    for number in (_NUM_T, _NUM_X):
        _post_user_tag(client, repo, number, add=["校服"])

    # ③ 再開星空：共有稀有 user tag 拉高 X 分數
    s1 = _x_score(client)
    assert s1 is not None
    assert s1 > s0

    # ④ 兩邊各拿掉「校服」
    for number in (_NUM_T, _NUM_X):
        _post_user_tag(client, repo, number, remove=["校服"])

    # ⑤ 分數回到基線
    s2 = _x_score(client)
    assert s2 == pytest.approx(s0)
