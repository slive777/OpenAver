"""TASK-198a-T3：來源 4K 顯示層過濾、探針序列化、片長優先、NFO 寫回路徑不動。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri


# 來源 4K 等價字（測試斷言用；產品碼述詞是 is_source_4k_tag，此處不 import 新符號）
_SOURCE_4K = frozenset({"4k", "uhd", "8k"})


def _ok_probe(*, width=1920, height=1080, duration_ms=7_380_000, video_format="AVC") -> ProbeResult:
    return ProbeResult(
        status="ok",
        reason="",
        width=width,
        height=height,
        video_format=video_format,
        duration_ms=duration_ms,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=5_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=(),
        truncated=False,
    )


def _showcase_config(video_dir: Path) -> dict:
    return {
        "gallery": {
            "directories": [str(video_dir)],
            "path_mappings": {},
            "min_size_mb": 0,
            "thumbnail_width": 400,
        },
        "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"},
        "thumbnail_cache_enabled": False,
    }


def _seed_video(
    repo: VideoRepository,
    *,
    path: str,
    number: str,
    tags: list[str],
    user_tags: list[str] | None = None,
    duration: int = 120,
    mtime: float = 1700000000.0,
    size_bytes: int = 1_000_000,
    title: str = "Truth Title",
    actresses: list[str] | None = None,
    maker: str = "Truth Maker",
    release_date: str = "2024-01-01",
) -> Video:
    video = Video(
        path=path,
        number=number,
        title=title,
        actresses=actresses if actresses is not None else ["女優A"],
        maker=maker,
        release_date=release_date,
        tags=tags,
        user_tags=user_tags or [],
        duration=duration,
        size_bytes=size_bytes,
        mtime=mtime,
    )
    repo.upsert(video)
    return video


def test_source_4k_hidden_and_tier_comes_from_probe(client, tmp_path, mocker):
    """F1：卡片／燈箱看到的 tags 不含來源 4K；resolution_tier 來自探針；user_tags 原樣。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    uri = to_file_uri(str(video_dir / "ABC-100.mp4"), {})
    db_path = tmp_path / "f1.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    mtime, size = 1700000000.0, 1_000_000
    _seed_video(
        repo,
        path=uri,
        number="ABC-100",
        tags=["4K", "UHD", "巨乳"],
        user_tags=["4K"],
        duration=120,
        mtime=mtime,
        size_bytes=size,
    )
    assert repo.update_media_probe(uri, _ok_probe(width=1920, height=1080), mtime, size) is True

    config = _showcase_config(video_dir)
    mocker.patch("web.routers.showcase.get_db_path", return_value=db_path)
    mocker.patch("web.routers.showcase.load_config", return_value=config)

    list_resp = client.get("/api/showcase/videos")
    assert list_resp.status_code == 200
    listed = next(v for v in list_resp.json()["videos"] if v["path"] == uri)
    assert listed.get("tags") == "巨乳"
    assert listed.get("user_tags") == ["4K"]
    assert listed.get("resolution_tier") == "FHD"

    single_resp = client.get("/api/showcase/video", params={"path": uri})
    assert single_resp.status_code == 200
    single = single_resp.json()["video"]
    assert single.get("tags") == "巨乳"
    assert single.get("user_tags") == ["4K"]
    assert single.get("resolution_tier") == "FHD"


def test_db_to_sidecar_nfo_keeps_source_4k_genre(tmp_path):
    """K2：補寫 NFO 仍保留 <genre>4K</genre>（顯示層過濾不得落到寫回路徑）。"""
    video_dir = tmp_path / "nfo_video"
    video_dir.mkdir()
    # 檔名不得含 4K／uhd／8k，否則 effective_tags 會從檔名補回 → mutation 假綠
    video_file = video_dir / "ABC-123.mp4"
    video_file.write_bytes(b"video-bytes")
    db_key = to_file_uri(str(video_file))

    db_file = tmp_path / "k2.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)
    _seed_video(
        repo,
        path=db_key,
        number="ABC-123",
        tags=["4K", "巨乳"],
        title="K2 Title",
        actresses=["女優B"],
        maker="K2 Maker",
        release_date="2024-06-01",
        duration=100,
    )

    with patch("core.enricher.VideoRepository", return_value=repo):
        from core.enricher import enrich_single

        result = enrich_single(
            file_path=str(video_file),
            number="ABC-123",
            mode="db_to_sidecar",
            write_nfo=True,
            write_cover=False,
        )

    assert result.success is True, f"enrich_single 失敗: {result.error}"
    nfo_path = video_dir / "ABC-123.nfo"
    assert nfo_path.exists()
    genres = {el.text for el in ET.parse(nfo_path).getroot().findall("genre")}
    assert "4K" in genres
    assert "巨乳" in genres


@pytest.mark.parametrize(
    "case",
    [
        "probe_ok",
        "key_mismatch",
        "never_probed",
        "multipart",
    ],
)
def test_duration_prefers_probe_and_falls_back_to_source(client, tmp_path, mocker, case):
    """片長：探針 ok 用實際分鐘；key 不符／未讀過退回來源；分集多段維持來源；source_duration 恆為來源。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    db_path = tmp_path / f"dur_{case}.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    mtime, size = 1700000100.0, 2_000_000

    if case == "multipart":
        # 同資料夾同 stem 的 cd1/cd2 → group_rows 合成一張卡；第一段 probe 60 分不得蓋掉來源 120
        uri = to_file_uri(str(video_dir / "DUR-MP-cd1.mp4"), {})
        uri2 = to_file_uri(str(video_dir / "DUR-MP-cd2.mp4"), {})
        _seed_video(
            repo, path=uri, number="DUR-MP", tags=["巨乳"],
            duration=120, mtime=mtime, size_bytes=size,
        )
        _seed_video(
            repo, path=uri2, number="DUR-MP", tags=["巨乳"],
            duration=120, mtime=mtime + 1.0, size_bytes=size,
        )
        assert repo.update_media_probe(
            uri, _ok_probe(duration_ms=3_600_000), mtime, size
        ) is True
        expect_duration = 120
        expect_tier = "FHD"
        expect_media_duration_min = None
    else:
        uri = to_file_uri(str(video_dir / f"DUR-{case}.mp4"), {})
        _seed_video(
            repo,
            path=uri,
            number=f"DUR-{case}",
            tags=["巨乳"],
            duration=120,
            mtime=mtime,
            size_bytes=size,
        )

        if case == "probe_ok":
            assert repo.update_media_probe(
                uri, _ok_probe(duration_ms=7_380_000), mtime, size
            ) is True
            expect_duration = 123
            expect_tier = "FHD"
            expect_media_duration_min = 123
        elif case == "key_mismatch":
            assert repo.update_media_probe(
                uri, _ok_probe(duration_ms=7_380_000), mtime, size
            ) is True
            # upsert 改 mtime：探針欄保留、key 對不上（真實流程，不用 raw SQL）
            repo.upsert(
                Video(
                    path=uri,
                    number=f"DUR-{case}",
                    title="Truth Title",
                    actresses=["女優A"],
                    maker="Truth Maker",
                    release_date="2024-01-01",
                    tags=["巨乳"],
                    duration=120,
                    size_bytes=size,
                    mtime=mtime + 99.0,
                )
            )
            expect_duration = 120
            expect_tier = None
            expect_media_duration_min = None
        else:
            expect_duration = 120
            expect_tier = None
            expect_media_duration_min = None

    config = _showcase_config(video_dir)
    mocker.patch("web.routers.showcase.get_db_path", return_value=db_path)
    mocker.patch("web.routers.showcase.load_config", return_value=config)

    resp = client.get("/api/showcase/videos")
    assert resp.status_code == 200
    item = next(v for v in resp.json()["videos"] if v["path"] == uri)
    if case == "multipart":
        assert item.get("part_tokens") == ["cd1", "cd2"]
    assert item.get("source_duration") == 120
    assert item.get("duration") == expect_duration
    assert item.get("resolution_tier") == expect_tier
    assert item.get("media_duration_min") == expect_media_duration_min


@pytest.mark.parametrize("sink", ["insights", "tags_top"])
def test_insights_and_tags_top_exclude_source_4k(client, tmp_path, mocker, sink):
    """F2／F3：分析頁與 tags/top 都不含來源 4K 類；limit 在剔除後套用。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    db_path = tmp_path / f"sink_{sink}.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    seeds = [
        (["4K", "巨乳", "OL"], "A-001"),
        (["4k", "巨乳"], "A-002"),
        (["UHD", "女教師"], "A-003"),
        (["8K", "痴女"], "A-004"),
        (["巨乳", "OL"], "A-005"),
    ]
    for tags, number in seeds:
        uri = to_file_uri(str(video_dir / f"{number}.mp4"), {})
        _seed_video(repo, path=uri, number=number, tags=tags, duration=90)

    if sink == "insights":
        config = _showcase_config(video_dir)
        mocker.patch("web.routers.insights.get_db_path", return_value=db_path)
        mocker.patch("web.routers.insights.load_config", return_value=config)
        resp = client.get("/api/insights/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        for record in data.get("records", []):
            for tag in record.get("tags") or []:
                assert str(tag).strip().lower() not in _SOURCE_4K, tag
    else:
        mocker.patch("web.routers.tags.get_db_path", return_value=db_path)
        # limit=3：剔除後仍應湊滿 3 筆（若 SQL 先 LIMIT 再剔除會少一筆）
        resp = client.get("/api/tags/top", params={"min_count": 1, "limit": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        items = data.get("items") or []
        tags = [item["tag"] for item in items]
        for tag in tags:
            assert str(tag).strip().lower() not in _SOURCE_4K, tag
        assert len(items) == 3
        # total_unique_tags 同樣不計 4K 類
        total = data.get("total_unique_tags")
        assert total is not None
        # 種子非 4K 類：巨乳、OL、女教師、痴女 → 4
        assert total == 4
        # 排序仍 count DESC, tag ASC：巨乳(3) > OL(2) > 女教師/痴女(1)
        assert tags[0] == "巨乳"
        assert items[0]["count"] == 3
