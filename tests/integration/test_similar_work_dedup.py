"""TASK-198b-T4 oracle：相似片去重——結果不含查詢片同番號列、同一作品只佔一格。

真路由＋真 SQLite（tmp_path）；不 mock SimilarRankerCache／VideoRepository 行為。
語料：A 跨資料夾複本（先 upsert → by-number 的 target，E4 情境）＋ A 同資料夾 3 版本
＋ B 同資料夾 2 版本（標籤與 A 高度相似）＋ 1 筆 number=None 近似列 ＋ 40 筆墊檔。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from core.similar.ranker_cache import SimilarRankerCache
from web.routers.similar import router as similar_router

_NUM_A = "DEDUPT4-001"
_NUM_B = "DEDUPT4-002"
_SHARED = ["dedupraret4", "dedupbraret4", "dedupgammaret4"]


def _make_video(path: str, number, tags: list[str], maker: str = "DedupMaker") -> Video:
    return Video(
        path=to_file_uri(path),
        number=number,
        title=f"Dedup {path}",
        maker=maker,
        series=None,
        actresses=[],
        tags=tags,
        release_date="2023-01-01",
        duration=90,
        cover_path="",
        mtime=1.0,
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
    db_path = tmp_path / "work_dedup.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    rows = [
        _make_video("/fake/dedup_other/A-copy.mp4", _NUM_A, list(_SHARED)),
        _make_video("/fake/dedup/A.mp4", _NUM_A, list(_SHARED)),
        _make_video("/fake/dedup/A-C.mp4", _NUM_A, list(_SHARED)),
        _make_video("/fake/dedup/A-LTX.mp4", _NUM_A, list(_SHARED)),
        _make_video("/fake/dedup/B.mp4", _NUM_B, _SHARED + ["dedupdeltaret4b"]),
        _make_video("/fake/dedup/B-C.mp4", _NUM_B, _SHARED + ["dedupdeltaret4b"]),
        _make_video("/fake/dedup/NONENUM.mp4", None, ["dedupraret4", "dedupbraret4", "dedupnonet4"]),
    ]
    rows += [
        _make_video(
            f"/fake/dedup/pad_{i:03d}.mp4",
            f"T4PAD-{i:03d}",
            [f"t4padtag{i:03d}"],
            maker=f"T4PadMaker{i}",
        )
        for i in range(40)
    ]
    repo.upsert_batch(rows)

    class _Repo(VideoRepository):
        def __init__(self, _=None):
            super().__init__(db_path)

    monkeypatch.setattr("web.routers.similar.VideoRepository", _Repo)
    monkeypatch.setattr("core.similar.ranker_cache.VideoRepository", _Repo)
    monkeypatch.setattr("web.routers.similar.load_config", lambda: {})

    app = FastAPI()
    app.include_router(similar_router)
    yield TestClient(app)


def _norm(number) -> str:
    return (number or "").strip().upper()


def _results(client: TestClient):
    resp = client.get(f"/api/similar-covers/by-number/{_NUM_A}?limit=5")
    assert resp.status_code == 200
    return resp.json()["results"]


def test_similar_never_returns_same_number_rows(client):
    results = _results(client)
    assert results, "正向對照：結果不應被剔光"
    assert any(_norm(r["number"]) == _norm(_NUM_B) for r in results), "正向對照：B 應在結果裡"
    assert not any(_norm(r["number"]) == _norm(_NUM_A) for r in results)


def test_similar_one_card_per_work_and_fills_limit(client):
    results = _results(client)
    assert len(results) == 5
    assert sum(1 for r in results if _norm(r["number"]) == _norm(_NUM_B)) == 1
