"""Integration tests for AI tags HTTP endpoints (TASK-188b-T9a)."""

from __future__ import annotations

import pytest
from PIL import Image

from core.ai_services.image_prep import poster_to_jpeg_bytes
from core.ai_services.tagging import TaggingFailure, TagOutcome
from core.ai_services.tagging_vocab import load_builtin
from core.config import load_config, save_config
from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from tests.unit._custom_source_fake import finalize_root  # noqa: PLC2701 — 卡片指定沿用 custom_sources 的 finalize_root


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    save_config(load_config())
    finalize_root(root)
    return root


def _make_repo(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    init_db(db)
    repo = VideoRepository(db)
    monkeypatch.setattr("web.routers.ai_tags.VideoRepository", lambda *a, **k: repo)
    return repo


@pytest.mark.parametrize(
    "case",
    ["success", "unreachable", "disabled_real"],
    ids=["success", "unreachable", "disabled_real"],
)
def test_tag_video_endpoint_failure_reason_in_body_not_500(client, tmp_path, monkeypatch, case):
    file_uri = to_file_uri(str(tmp_path / "clip.mp4"))

    if case == "disabled_real":
        resp = client.post("/api/ai/tags/videos", json={"file_path": file_uri})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["reason"] == "disabled"
        return

    received: list[str] = []

    if case == "success":

        async def fake(file_path, **kw):
            received.append(file_path)
            return TagOutcome(
                added=["校服"],
                refused=False,
                user_tags=["★4", "校服"],
                nfo_updated=True,
            )

    else:

        async def fake(file_path, **kw):
            received.append(file_path)
            raise TaggingFailure("unreachable", "auth_failed")

    monkeypatch.setattr("web.routers.ai_tags.tag_video", fake)
    resp = client.post("/api/ai/tags/videos", json={"file_path": file_uri})
    assert resp.status_code == 200
    body = resp.json()
    if case == "success":
        assert body["success"] is True
        assert body["added"] == ["校服"]
        assert body["user_tags"] == ["★4", "校服"]
        assert received == [file_uri]
    else:
        assert body == {
            "success": False,
            "reason": "unreachable",
            "detail": "auth_failed",
        }


def test_poster_endpoint_serves_same_bytes_as_model_input(client, tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, monkeypatch)

    jpg = tmp_path / "cover.jpg"
    img = Image.new("RGB", (1600, 900), (30, 30, 220))
    red = Image.new("RGB", (int(1600 * 0.4), 900), (220, 30, 30))
    img.paste(red, (0, 0))
    img.save(jpg, format="JPEG", quality=95)
    cover_uri = to_file_uri(str(jpg))
    video_uri = to_file_uri(str(tmp_path / "with-cover.mp4"))

    repo.upsert(
        Video(
            path=video_uri,
            number="T9A-001",
            cover_path=cover_uri,
            crop_mode="manual",
            auto_focal="0.2000,0.5000",
        )
    )
    stored = repo.get_by_path(video_uri)
    assert stored is not None
    if stored.crop_mode != "manual" or stored.auto_focal != "0.2000,0.5000":
        assert repo.update_manual_focal(video_uri, "0.2000,0.5000", cover_uri)
        stored = repo.get_by_path(video_uri)
    assert stored.crop_mode == "manual"
    assert stored.auto_focal == "0.2000,0.5000"

    expected = poster_to_jpeg_bytes(str(jpg), "manual", "0.2000,0.5000")
    default_bytes = poster_to_jpeg_bytes(str(jpg), "default", "")
    assert expected is not None
    assert default_bytes is not None
    assert expected != default_bytes

    resp = client.get("/api/ai/tags/poster", params={"file_path": video_uri})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == expected

    no_cover_uri = to_file_uri(str(tmp_path / "no-cover.mp4"))
    repo.upsert(Video(path=no_cover_uri, number="T9A-002", cover_path=""))
    resp = client.get("/api/ai/tags/poster", params={"file_path": no_cover_uri})
    assert resp.status_code == 404
    assert resp.json()["reason"] == "no_cover"

    missing_uri = to_file_uri(str(tmp_path / "missing.mp4"))
    resp = client.get("/api/ai/tags/poster", params={"file_path": missing_uri})
    assert resp.status_code == 404
    assert resp.json()["reason"] == "not_found"


@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "builtin_conflict",
        "duplicate",
        "not_ready",
        "delete_missing",
        "delete_builtin",
    ],
    ids=[
        "ok",
        "builtin_conflict",
        "duplicate",
        "not_ready",
        "delete_missing",
        "delete_builtin",
    ],
)
def test_vocab_write_error_codes_map_to_http_status(client, env, case):
    builtin = load_builtin()[0]

    if case == "ok":
        resp = client.post(
            "/api/ai/tags/vocab",
            json={"name": "JK", "definition": "女高中生"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        listed = client.get("/api/ai/tags/vocab")
        assert listed.status_code == 200
        items = listed.json()["items"]
        custom = next(i for i in items if i["name"] == "JK")
        assert custom["source"] == "custom"
        for item in items:
            assert "model_name" not in item
        return

    if case == "builtin_conflict":
        resp = client.post(
            "/api/ai/tags/vocab",
            json={"name": builtin.model_name, "definition": ""},
        )
        assert resp.status_code == 400
        assert resp.json()["reason"] == "name_conflict_builtin"
        return

    if case == "duplicate":
        first = client.post(
            "/api/ai/tags/vocab",
            json={"name": "JK", "definition": "女高中生"},
        )
        assert first.status_code == 200
        resp = client.post(
            "/api/ai/tags/vocab",
            json={"name": "JK", "definition": "again"},
        )
        assert resp.status_code == 409
        assert resp.json()["reason"] == "name_exists"
        return

    if case == "not_ready":
        (env / ".layout.json").unlink()
        resp = client.post(
            "/api/ai/tags/vocab",
            json={"name": "JK", "definition": "女高中生"},
        )
        assert resp.status_code == 409
        assert resp.json()["reason"] == "data_root_not_ready"
        return

    if case == "delete_missing":
        resp = client.delete("/api/ai/tags/vocab/不存在")
        assert resp.status_code == 404
        assert resp.json()["reason"] == "not_found"
        return

    # delete_builtin
    resp = client.delete(f"/api/ai/tags/vocab/{builtin.name}")
    assert resp.status_code == 400
    assert resp.json()["reason"] == "builtin"
