"""TASK-198b-T3: 跟作品走的寫入（精選、使用者標籤、AI 標籤回應）。

三版本同資料夾同番號 ABF-348：
  ABF-348.mp4（4K，有 NFO）、ABF-348-C.mkv（中字，有 NFO）、ABF-348-LTX.mkv（無 NFO）。
預設順序由 T1 規則決定（中字→4K 原版→LTX），測試只斷言成員、不斷言 work_user_tags 內順序。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.ai_services.tagging_vocab import load_builtin
from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri

_MINIMAL_NFO = b"""<?xml version='1.0' encoding='utf-8'?>
<movie>
  <title>ABF-348</title>
</movie>
"""


@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    """canonicalize 的模組級 alias map 冷時會連真 DB → 每支測試前後隔離。"""
    from core.similar import canonicalize

    mock_repo = MagicMock()
    mock_repo.get_all.return_value = []
    canonicalize._invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=mock_repo):
        yield
    canonicalize._invalidate_cache()


@pytest.fixture(autouse=True)
def _isolate_tags_state(monkeypatch):
    """tag_video 會呼叫 tags_state.observe_*（寫 app_meta）→ 不得碰真實預設 DB（G1）。

    meta_set 換成 no-op，並把模組層觀察值歸零（BE-TEST-38）。
    """
    from core.ai_services import tags_state

    monkeypatch.setattr(tags_state, "meta_set", lambda key, value: None)
    for name, val in (
        ("unreachable", False), ("last_success_at", None), ("last_persist_mono", None),
        ("notified", False), ("notification_sink", None),
    ):
        monkeypatch.setattr(tags_state._STATE, name, val)


def _nfo_user_tags(nfo: Path) -> set:
    import xml.etree.ElementTree as ET

    return {e.text for e in ET.parse(str(nfo)).getroot().findall("user_tag")}


def _seed_work(tmp_path, monkeypatch, *, cover_for=None, ltx_tags=(), c_tags=(), uhd_tags=()):
    """三版本＋兩份 NFO＋tmp DB 一列一版本＋TestClient。回 dict 供測試用。"""
    from PIL import Image

    db_path = tmp_path / "test_work_level_writes.db"
    init_db(db_path)

    items = {
        "uhd": ("ABF-348.mp4", uhd_tags, True),
        "c": ("ABF-348-C.mkv", c_tags, True),
        "ltx": ("ABF-348-LTX.mkv", ltx_tags, False),
    }
    mp4 = {k: tmp_path / name for k, (name, _, _) in items.items()}
    for p in mp4.values():
        p.write_bytes(b"fake-video")
    nfo = {}
    for key, (name, _, has_nfo) in items.items():
        if has_nfo:
            n = (tmp_path / name).with_suffix(".nfo")
            n.write_bytes(_MINIMAL_NFO)
            nfo[key] = n

    uris = {k: to_file_uri(str(mp4[k])) for k in mp4}
    covers = {}
    if cover_for is not None:
        jpg = tmp_path / "ABF-348-poster.jpg"
        Image.new("RGB", (300, 400), (120, 80, 200)).save(jpg, format="JPEG")
        covers[cover_for] = to_file_uri(str(jpg))
    repo = VideoRepository(db_path)
    for key, (_, tags, _) in items.items():
        repo.upsert(Video(
            path=uris[key],
            number="ABF-348",
            title="ABF-348",
            user_tags=list(tags),
            cover_path=covers.get(key, ""),
        ))

    ai_config = {
        "gallery": {"path_mappings": {}},
        "ai_services": {"tags": {"enabled": True, "provider": "ollama", "model": "m"}},
        "translate": {"ollama": {"url": ""}},
    }
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: db_path)
    monkeypatch.setattr("web.routers.collection.load_config", lambda: ai_config)
    monkeypatch.setattr("web.routers.ai_tags.VideoRepository", lambda *a, **k: repo)
    monkeypatch.setattr("core.ai_services.tagging.VideoRepository", lambda *a, **k: repo)
    monkeypatch.setattr("core.ai_services.tagging.load_config", lambda: ai_config)

    from web.app import app
    client = TestClient(app)
    return {"client": client, "repo": repo, "uris": uris, "nfo": nfo, "db_path": db_path}


def _ratings(repo, uris):
    return {k: repo.get_by_path(u).user_rating for k, u in uris.items()}


def _tags(repo, uris):
    return {k: list(repo.get_by_path(u).user_tags) for k, u in uris.items()}


def test_pick_and_unpick_apply_to_every_version_of_the_work(tmp_path, monkeypatch):
    """使用者在中字版按取消精選 → 三版的星一起沒了；再按精選 → 三版都亮。"""
    seed = _seed_work(tmp_path, monkeypatch)
    client, repo, uris = seed["client"], seed["repo"], seed["uris"]

    repo.set_user_rating_bulk(list(uris.values()), 0)
    assert repo.set_user_rating_bulk([uris["ltx"]], 1) == {uris["ltx"]: True}
    assert _ratings(repo, uris) == {"uhd": 0, "c": 0, "ltx": 1}

    resp = client.post("/api/user-rating", json={"file_path": uris["c"], "picked": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert _ratings(repo, uris) == {"uhd": 0, "c": 0, "ltx": 0}

    resp = client.post("/api/user-rating", json={"paths": [uris["c"], uris["uhd"]], "picked": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["results"] == [
        {"path": uris["c"], "ok": True},
        {"path": uris["uhd"], "ok": True},
    ]
    assert data["changed"] == 1
    assert _ratings(repo, uris) == {"uhd": 1, "c": 1, "ltx": 1}


def test_user_tags_follow_the_work_without_creating_nfo(tmp_path, monkeypatch):
    """使用者在 4K 版加「想看」→ 三版都有、回應 work_user_tags 含聯集；LTX 版不新增 NFO。"""
    seed = _seed_work(
        tmp_path, monkeypatch, uhd_tags=["★4"], c_tags=["珍藏"], ltx_tags=[],
    )
    client, repo, uris, nfo = seed["client"], seed["repo"], seed["uris"], seed["nfo"]

    assert _tags(repo, uris) == {"uhd": ["★4"], "c": ["珍藏"], "ltx": []}
    before = {p.name for p in tmp_path.glob("*.nfo")}
    assert before == {"ABF-348.mp4".replace(".mp4", ".nfo"), "ABF-348-C.nfo"}

    resp = client.post("/api/user-tags", json={"file_path": uris["uhd"], "add": ["想看"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert set(data["user_tags"]) == {"★4", "想看"}
    assert "珍藏" not in data["user_tags"]
    assert set(data["work_user_tags"]) == {"★4", "想看", "珍藏"}
    after = {p.name for p in tmp_path.glob("*.nfo")}
    assert after == before
    assert "想看" in _nfo_user_tags(nfo["uhd"])
    assert "想看" in _nfo_user_tags(nfo["c"])
    for key in uris:
        assert "想看" in repo.get_by_path(uris[key]).user_tags

    resp = client.post("/api/user-tags", json={"file_path": uris["uhd"], "remove": ["想看"]})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    for key in uris:
        assert "想看" not in repo.get_by_path(uris[key]).user_tags

    import web.routers.collection as collection_mod

    real_apply = collection_mod.apply_user_tags

    def _fake_apply(repo_arg, file_path_arg, *args, **kwargs):
        res = real_apply(repo_arg, file_path_arg, *args, **kwargs)
        if file_path_arg != uris["uhd"] and res.ok:
            res.readonly_no_output = True
        return res

    monkeypatch.setattr(collection_mod, "apply_user_tags", _fake_apply)
    resp = client.post("/api/user-tags", json={"file_path": uris["uhd"], "add": ["想看"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert set(data["user_tags"]) == {"★4", "想看"}
    assert data["nfo_updated"] is True
    assert data["readonly_no_output"] is True
    assert data["nfo_write_blocked"] is False


def test_ai_tag_reply_carries_work_user_tags_and_marks_only_current_version(tmp_path, monkeypatch):
    """使用者在中字版按 AI 標籤 → 回應 work_user_tags 含新字與 LTX 版「想看」；只有中字版記 ai_tagged_at。"""
    seed = _seed_work(tmp_path, monkeypatch, cover_for="c", ltx_tags=["想看"])
    client, repo, uris = seed["client"], seed["repo"], seed["uris"]

    assert _tags(repo, uris)["ltx"] == ["想看"]
    for key in uris:
        assert repo.get_ai_tagged_at(uris[key]) is None

    item = load_builtin()[0]
    reply = '{"tags":[{"tag":"%s","confidence":"high"}]}' % item.model_name
    calls: list = []

    async def fake(conn, system, user_text, poster_uri):
        calls.append((conn, system, user_text, poster_uri))
        return reply

    monkeypatch.setattr("core.ai_services.tagging.vision_chat", fake)

    resp = client.post("/api/ai/tags/videos", json={"file_path": uris["c"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(calls) == 1
    assert item.name in body["work_user_tags"]
    assert "想看" in body["work_user_tags"]
    assert repo.get_ai_tagged_at(uris["c"]) is not None
    assert repo.get_ai_tagged_at(uris["uhd"]) is None
    assert repo.get_ai_tagged_at(uris["ltx"]) is None
