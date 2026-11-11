"""TASK-188b-T2a: POST /api/user-tags 的 ai_tagged 行為鎖。

① 不帶 ai_tagged → 回應與副作用與今天相同（含一律重寫 NFO）。
② 帶 ai_tagged:true → 記跑過；沒新字跳過 NFO；有新字照寫。
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri

_MINIMAL_NFO = b"""<?xml version='1.0' encoding='utf-8'?>
<movie>
  <title>AI-001</title>
</movie>
"""

# 2020-01-01 00:00:00 UTC in ns — 固定舊值，避免「兩次讀值一樣」假綠
_FIXED_MTIME_NS = 1577836800_000_000_000


def _prepare_client_with_tagged_video(tmp_path, monkeypatch, *, number="AI-001"):
    """模組層純函式：真 mp4＋同名 .nfo＋tmp DB 一列 user_tags=["★4"]＋TestClient。"""
    db_path = tmp_path / "test_user_tags_ai.db"
    init_db(db_path)

    mp4 = tmp_path / f"{number}.mp4"
    mp4.write_bytes(b"fake-video")
    nfo = mp4.with_suffix(".nfo")
    nfo.write_bytes(_MINIMAL_NFO)

    file_uri = to_file_uri(str(mp4))
    repo = VideoRepository(db_path)
    repo.upsert(Video(
        path=file_uri,
        number=number,
        title=number,
        user_tags=["★4"],
    ))

    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: db_path)
    monkeypatch.setattr(
        "web.routers.collection.load_config",
        lambda: {"gallery": {"path_mappings": {}}},
    )

    from web.app import app
    client = TestClient(app)
    return client, repo, file_uri, nfo, db_path


def test_post_without_ai_tagged_matches_legacy_response_and_always_rewrites_nfo(
    tmp_path, monkeypatch,
):
    """行為①：不帶 ai_tagged → 回應鍵集合與今天相同；合併無變化仍重寫 NFO。"""
    client, repo, file_uri, nfo, _db = _prepare_client_with_tagged_video(tmp_path, monkeypatch)

    resp = client.post("/api/user-tags", json={
        "file_path": file_uri,
        "add": ["足"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {
        "success", "user_tags", "nfo_updated", "readonly_no_output", "nfo_write_blocked",
        "work_user_tags",
    }
    assert data["success"] is True
    assert "足" in data["user_tags"]
    assert "★4" in data["user_tags"]
    assert data["nfo_updated"] is True
    assert data["readonly_no_output"] is False
    assert data["nfo_write_blocked"] is False
    assert repo.get_ai_tagged_at(file_uri) is None

    # 鑑別力：再 POST 已存在的標籤（合併無變化）→ 仍重寫 NFO
    resp2 = client.post("/api/user-tags", json={
        "file_path": file_uri,
        "add": ["★4"],
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["nfo_updated"] is True
    assert repo.get_ai_tagged_at(file_uri) is None


def test_ai_tagged_post_records_ran_and_skips_nfo_when_nothing_new(
    tmp_path, monkeypatch,
):
    """行為②：ai_tagged:true 記跑過；沒新字跳過 NFO；有新字照寫。"""
    client, repo, file_uri, nfo, _db = _prepare_client_with_tagged_video(tmp_path, monkeypatch)

    os.utime(nfo, ns=(_FIXED_MTIME_NS, _FIXED_MTIME_NS))
    assert nfo.stat().st_mtime_ns == _FIXED_MTIME_NS

    before_tags = list(repo.get_by_path(file_uri).user_tags)

    resp = client.post("/api/user-tags", json={
        "file_path": file_uri,
        "add": [],
        "ai_tagged": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert repo.get_ai_tagged_at(file_uri) is not None
    assert data["user_tags"] == before_tags
    assert data["nfo_updated"] is False
    assert data["readonly_no_output"] is False
    assert data["nfo_write_blocked"] is False
    assert nfo.stat().st_mtime_ns == _FIXED_MTIME_NS

    # 有新字照寫
    resp2 = client.post("/api/user-tags", json={
        "file_path": file_uri,
        "add": ["X"],
        "ai_tagged": True,
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert "X" in data2["user_tags"]
    assert data2["nfo_updated"] is True
    nfo_text = Path(nfo).read_text(encoding="utf-8")
    assert "<user_tag>X</user_tag>" in nfo_text
