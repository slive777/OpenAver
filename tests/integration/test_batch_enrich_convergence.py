"""
test_batch_enrich_convergence.py — TASK-147b-T2

端到端整合：POST /api/batch-enrich（mode=fill_missing）真的跑
core.enricher.enrich_single，寫入真實 tmp SQLite 的 scrape_attempted_at，
之後 GET /api/gallery/missing-check 不再列出該筆。

刻意不 mock web.routers.scraper.enrich_single（既有 test_batch_* 那樣做會
測不到 T1 改的任何一行）。只在更底層 stub search_jav / download_image /
thumbnail_cache.invalidate。

兩個 get_db_path import binding 都要指向同一個 tmp DB：
- core.database.connection.get_db_path（VideoRepository() 無參數建構用）
- web.routers.scanner.get_db_path（missing-check 用）
漏一處會假綠。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri


# ── helpers（模組層；不要寫成測試 class 的方法）──────────────────────────────


def parse_sse(text: str) -> list:
    """解析 SSE 文字，回傳事件 dict 列表。"""
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def result_items(text: str) -> list:
    return [e for e in parse_sse(text) if e.get("type") == "result-item"]


def make_tmp_db(tmp_path: Path, videos: list) -> Path:
    """建立測試用 SQLite，插入指定影片列。回傳 db_path。"""
    db_path = tmp_path / "convergence.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch(videos)
    return db_path


def patch_dual_get_db_path(db_path: Path):
    """同時 patch enricher 與 scanner 兩處 get_db_path binding，指向同一 tmp DB。

    回傳 context manager（可 with 疊用）。呼叫端必須兩處都 patch，否則
    batch 寫 A 庫、missing-check 讀 B 庫 → 收斂斷言假綠。
    """
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch("core.database.connection.get_db_path", return_value=db_path)
    )
    stack.enter_context(
        patch("web.routers.scanner.get_db_path", return_value=db_path)
    )
    return stack


def read_scrape_attempted_at(db_path: Path, path_uri: str) -> float:
    """裸 sqlite3 讀回 scrape_attempted_at，不經 repo mock。"""
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT scrape_attempted_at FROM videos WHERE path = ?",
            (path_uri,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, f"DB 找不到 path={path_uri!r}"
    return float(row[0] or 0)


def missing_check_paths(client, db_path: Path) -> set:
    """呼叫 missing-check，回傳 items 裡的 file_path 集合。"""
    with patch("web.routers.scanner.get_db_path", return_value=db_path):
        resp = client.get("/api/gallery/missing-check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    return {item["file_path"] for item in data["data"]["items"]}


def write_video_file(tmp_path: Path, stem: str) -> Path:
    video_dir = tmp_path / "videos"
    video_dir.mkdir(exist_ok=True)
    path = video_dir / f"{stem}.mp4"
    path.write_bytes(b"fake video bytes")
    return path


def make_text_complete_video(
    path_uri: str,
    number: str,
    *,
    title: str = "使用者自己改過的標題",
    cover_path: str = "",
    nfo_mtime: float = 0.0,
    scrape_attempted_at: float = 0.0,
    director: str = "テスト監督",
    maker: str = "SOD",
) -> Video:
    """文字 8 欄齊全、預設缺封面的 Video 列。"""
    return Video(
        path=path_uri,
        number=number,
        title=title,
        original_title=title,
        actresses=["女優A"],
        maker=maker,
        director=director,
        series="テストシリーズ",
        label="LABEL",
        tags=["タグ"],
        sample_images=[],
        duration=120,
        cover_path=cover_path,
        release_date="2024-01-01",
        nfo_mtime=nfo_mtime,
        scrape_attempted_at=scrape_attempted_at,
        output_dir="",
    )


def scraper_hit_without_cover(number: str) -> dict:
    """外站有回應但沒給封面——仍會走 _db_upsert 寫 scrape_attempted_at。"""
    return {
        "number": number,
        "title": "外站標題不該覆寫既有",
        "actors": ["女優A"],
        "cover": "",
        "date": "2024-01-01",
        "maker": "SOD",
        "director": "テスト監督",
        "series": "テストシリーズ",
        "label": "LABEL",
        "tags": ["タグ"],
        "sample_images": [],
        "duration": 120,
        "url": f"https://example.com/{number}",
        "source": "javbus",
    }


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _stub_external_deps(mocker):
    """三個外部依賴邊界：預設 search_jav=None；各測試可 re-patch 覆蓋。"""
    mocker.patch("core.enricher.search_jav", return_value=None)
    mocker.patch("core.enricher.download_image", return_value=True)
    mocker.patch("core.thumbnail_cache.invalidate")


# ── tests ────────────────────────────────────────────────────────────────────


class TestBatchEnrichConvergence:
    """CD-147b-1b / 4b：batch-enrich → 真實 SQLite → missing-check 收斂。"""

    def test_text_complete_cover_missing_converges_after_batch(
        self, client, tmp_path, mocker,
    ):
        """文字齊全＋缺封面；外站有回應但沒封面 → 跑過 batch-enrich 後
        missing-check 不再列出該筆（無論外站是否真的給出封面）。"""
        number = "CNV-001"
        stem = "complete_cover_missing"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        video = make_text_complete_video(path_uri, number)
        db_path = make_tmp_db(tmp_path, [video])

        mocker.patch(
            "core.enricher.search_jav",
            return_value=scraper_hit_without_cover(number),
        )

        # 跑前：應在待補清單
        assert path_uri in missing_check_paths(client, db_path)

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{"file_path": path_uri, "number": number}],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": True,
            })

        assert resp.status_code == 200
        items = result_items(resp.text)
        assert len(items) == 1
        assert items[0]["success"] is True
        # 必須是外站來源，不能停在 "db"：否則「呼叫 search_jav 但丟掉回傳值」
        # 會落進 CD-147b-1b fallback，success／attempted／missing-check 同分假綠。
        # 用 != "db"（而非 == "javbus"）——鎖的是「吃進 merge／_db_upsert」這條路，
        # 不跟 stub 的 source 字串耦合。
        assert items[0]["source_used"] != "db", (
            f"search_jav 回傳值必須被吃進 source_used（外站路徑），"
            f"實際 source_used={items[0].get('source_used')!r}"
        )

        # 真讀 SQLite：scrape_attempted_at 必須非零（_db_upsert 路徑）
        attempted = read_scrape_attempted_at(db_path, path_uri)
        assert attempted > 0, f"scrape_attempted_at 應非零，實際={attempted!r}"

        assert path_uri not in missing_check_paths(client, db_path)


    def test_text_missing_not_found_early_returns_and_converges(
        self, client, tmp_path, mocker,
    ):
        """外站查無＋文字欄本來就有缺（missing 非空）→ 早退 success=False、
        reason='not_found'；scrape_attempted_at 仍寫入，missing-check 不再列出。"""
        number = "CNV-002"
        stem = "text_missing_offline"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        # director 空 → missing 非空；cover 也空（觸發查詢）
        video = make_text_complete_video(
            path_uri, number, director="", cover_path="",
        )
        db_path = make_tmp_db(tmp_path, [video])

        mocker.patch("core.enricher.search_jav", return_value=None)

        assert path_uri in missing_check_paths(client, db_path)

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{"file_path": path_uri, "number": number}],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": True,
            })

        assert resp.status_code == 200
        items = result_items(resp.text)
        assert len(items) == 1
        assert items[0]["success"] is False
        assert items[0]["reason"] == "not_found"

        attempted = read_scrape_attempted_at(db_path, path_uri)
        assert attempted > 0

        assert path_uri not in missing_check_paths(client, db_path)


    def test_noop_success_counts_as_failed_in_done_summary(
        self, client, tmp_path, mocker,
    ):
        """CD-147b-5／147b-T4：success=True 但四項皆空（已有 .nfo、文字齊、
        外站無封面）→ result-item.success 仍 True；done.summary 記
        success=0／failed=1（tally 對齊前端 didEnrichSomething）。"""
        number = "CNV-005"
        stem = "noop_existing_nfo"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        video = make_text_complete_video(path_uri, number)
        db_path = make_tmp_db(tmp_path, [video])

        # 已有 .nfo + overwrite_existing 預設 False → nfo_written=False
        nfo_path = video_path.with_suffix(".nfo")
        nfo_path.write_text(
            '<?xml version="1.0"?><movie><title>existing</title></movie>',
            encoding="utf-8",
        )

        mocker.patch(
            "core.enricher.search_jav",
            return_value=scraper_hit_without_cover(number),
        )

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{"file_path": path_uri, "number": number}],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": True,
            })

        assert resp.status_code == 200
        events = parse_sse(resp.text)
        items = [e for e in events if e.get("type") == "result-item"]
        assert len(items) == 1
        assert items[0]["success"] is True
        assert items[0].get("nfo_written") is False
        assert items[0].get("cover_written") is False
        assert items[0].get("fields_filled") == []

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        summary = done_events[0]["summary"]
        assert summary["success"] == 0
        assert summary["failed"] == 1

    def test_fields_filled_only_counts_as_success_in_done_summary(
        self, client, tmp_path, mocker,
    ):
        """CD-147b-5：僅 fields_filled 非空（已有 .nfo、無封面寫入）→
        summary.success == 1（鎖住 helper 的 or fields_filled 分支）。"""
        number = "CNV-006"
        stem = "fields_filled_only"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        # maker 空 → _merge_meta 會填入 fields_filled=['maker']
        video = make_text_complete_video(path_uri, number, maker="")
        db_path = make_tmp_db(tmp_path, [video])

        nfo_path = video_path.with_suffix(".nfo")
        nfo_path.write_text(
            '<?xml version="1.0"?><movie><title>existing</title></movie>',
            encoding="utf-8",
        )

        mocker.patch(
            "core.enricher.search_jav",
            return_value=scraper_hit_without_cover(number),
        )

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{"file_path": path_uri, "number": number}],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": True,
            })

        assert resp.status_code == 200
        events = parse_sse(resp.text)
        items = [e for e in events if e.get("type") == "result-item"]
        assert len(items) == 1
        assert items[0]["success"] is True
        assert items[0].get("nfo_written") is False
        assert items[0].get("cover_written") is False
        assert items[0].get("fields_filled") == ["maker"]

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["summary"]["success"] == 1
        assert done_events[0]["summary"]["failed"] == 0


# ── TASK-197-T2：一鍵補完「從 0」首擊 ─────────────────────────────────────────


def _first_hit_card(number: str) -> dict:
    """完整 card dict（真實 to_legacy_dict 鍵集合：不含 original_title）。"""
    return {
        "number": number,
        "title": "外站完整標題",
        "actors": ["女優A", "女優B"],
        "cover": "https://example.com/cover.jpg",
        "date": "2024-06-01",
        "maker": "IDEA POCKET",
        "director": "監督X",
        "series": "系列Y",
        "label": "LABEL-Z",
        "tags": ["巨乳", "美少女", "戲服"],
        "sample_images": [],
        "duration": 150,
        "url": f"https://example.com/{number}",
        "source": "dmm",
    }


def _from_zero_shell(path_uri: str, number: str, *, stem: str, cover_path: str = "") -> Video:
    """從 0 的殼：duration／original_title 空、tags 非空、title＝檔名佔位。"""
    return Video(
        path=path_uri,
        number=number,
        title=stem,
        original_title="",
        actresses=[],
        maker="",
        director="",
        series="",
        label="",
        tags=["既有標籤"],
        sample_images=[],
        duration=None,
        cover_path=cover_path,
        release_date="",
        nfo_mtime=0.0,
        scrape_attempted_at=0.0,
        output_dir="",
    )


class TestBatchEnrichFirstHit:
    """CD-197-1／2／11：router → enricher → search_jav(first_hit) 接線。"""

    def test_no_nfo_item_adopts_whole_first_hit_card(
        self, client, tmp_path, mocker,
    ):
        """(a) category=nfo → 整包採用；真的跑 search_jav(first_hit=True) 補鍵。"""
        import xml.etree.ElementTree as ET

        from core.scraper import search_jav as real_search_jav

        number = "ABC-123"
        stem = "ABC-123-C"  # 檔名帶 -C；DB number 不含 -C
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        video = _from_zero_shell(path_uri, number, stem=stem, cover_path="/fake/cover.jpg")
        db_path = make_tmp_db(tmp_path, [video])

        card = _first_hit_card(number)
        assert "original_title" not in card

        search_kwargs: list = []

        def _spy_search_jav(*args, **kwargs):
            search_kwargs.append(kwargs)
            return real_search_jav(*args, **kwargs)

        def _smart(*_a, **_kw):
            # 每次現造，避免 pop/_setdefault 污染
            c = _first_hit_card(number)
            c["_mode"] = "exact"
            return [c]

        mocker.patch("core.enricher.search_jav", side_effect=_spy_search_jav)
        mocker.patch("core.scraper.smart_search", side_effect=_smart)
        mocker.patch("core.scraper.is_uncensored_mode_effective", return_value=False)
        mocker.patch("core.scraper.load_config", return_value={})
        # 實作前 first_hit 被忽略會落到 fan-out；隔離外站，讓 RED 落在值斷言
        mocker.patch("core.scraper.get_enabled_source_ids", return_value=[])

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{
                    "file_path": path_uri,
                    "number": number,
                    "category": "nfo",
                }],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": False,
            })

        assert resp.status_code == 200
        items = result_items(resp.text)
        assert len(items) == 1
        assert items[0]["success"] is True

        assert search_kwargs, "enricher.search_jav 應被呼叫"
        assert search_kwargs[0].get("first_hit") is True

        nfo_path = video_path.with_suffix(".nfo")
        assert nfo_path.exists()
        root = ET.parse(nfo_path).getroot()
        assert root.findtext("runtime") == "150"
        assert root.findtext("website") == f"https://example.com/{number}"
        assert root.findtext("originaltitle") == "外站完整標題"
        genres = [e.text for e in root.findall("genre")]
        tags = [e.text for e in root.findall("tag")]
        all_labels = set(genres) | set(tags)
        for t in ("巨乳", "美少女", "戲服"):
            assert t in all_labels
        assert "中文字幕" in all_labels

    @pytest.mark.parametrize(
        "mode,category,expect_first_hit",
        [
            ("fill_missing", "both", True),
            ("fill_missing", "cover", False),
            ("fill_missing", None, False),
            ("fill_missing", "garbage", False),
            ("refresh_full", "both", False),
        ],
        ids=[
            "fill_missing_both",
            "fill_missing_cover",
            "fill_missing_omitted",
            "fill_missing_garbage",
            "refresh_full_both",
        ],
    )
    def test_dispatch_only_for_no_nfo_categories(
        self, client, tmp_path, mocker, mode, category, expect_first_hit,
    ):
        """(b) 只有 fill_missing＋{both,nfo} 才改寫 mode／first_hit。"""
        import xml.etree.ElementTree as ET

        from core.enricher import enrich_single as real_enrich_single

        number = "DSP-001"
        stem = "DSP-001"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        # 八欄齊、duration／original_title 空、tags 非空——fill_missing 不會補 runtime
        video = Video(
            path=path_uri,
            number=number,
            title="既有標題",
            original_title="",
            actresses=["女優A"],
            maker="SOD",
            director="テスト監督",
            series="テストシリーズ",
            label="LABEL",
            tags=["タグ"],
            sample_images=[],
            duration=None,
            cover_path="",
            release_date="2024-01-01",
            nfo_mtime=0.0,
            scrape_attempted_at=0.0,
            output_dir="",
        )
        db_path = make_tmp_db(tmp_path, [video])

        card = _first_hit_card(number)
        enrich_calls: list = []

        def _spy_enrich(*args, **kwargs):
            enrich_calls.append(kwargs)
            return real_enrich_single(*args, **kwargs)

        mocker.patch("web.routers.scraper.enrich_single", side_effect=_spy_enrich)
        mocker.patch("web.routers.scraper.search_jav", return_value=card)
        mocker.patch("core.enricher.search_jav", return_value=card)

        item = {"file_path": path_uri, "number": number}
        if category is not None:
            item["category"] = category

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [item],
                "mode": mode,
                "write_nfo": True,
                "write_cover": False,
            })

        assert resp.status_code == 200
        assert enrich_calls, "enrich_single 應被呼叫"
        # 實作前未傳 first_hit → None；bool(None) is False，讓「預期 False」的 row 先綠
        got_first_hit = bool(enrich_calls[0].get("first_hit"))
        assert got_first_hit is expect_first_hit
        if expect_first_hit:
            assert enrich_calls[0].get("mode") == "refresh_full"
        else:
            assert enrich_calls[0].get("mode") == mode

        nfo_path = video_path.with_suffix(".nfo")
        if mode == "fill_missing" and not expect_first_hit and nfo_path.exists():
            root = ET.parse(nfo_path).getroot()
            runtime = root.findtext("runtime")
            assert runtime in (None, ""), (
                f"fill_missing 不得寫入殼沒有的 runtime，實際={runtime!r}"
            )

    def test_no_nfo_not_found_converges(self, client, tmp_path, mocker):
        """(c) category=nfo ＋ 查無 → not_found 收斂，missing-check 不再列出。"""
        number = "NFH-001"
        stem = "NFH-001"
        video_path = write_video_file(tmp_path, stem)
        path_uri = to_file_uri(str(video_path))
        video = _from_zero_shell(path_uri, number, stem=stem, cover_path="")
        db_path = make_tmp_db(tmp_path, [video])

        # autouse 已 stub search_jav=None；明確再設一次
        mocker.patch("core.enricher.search_jav", return_value=None)

        assert path_uri in missing_check_paths(client, db_path)

        with patch_dual_get_db_path(db_path):
            resp = client.post("/api/batch-enrich", json={
                "items": [{
                    "file_path": path_uri,
                    "number": number,
                    "category": "nfo",
                }],
                "mode": "fill_missing",
                "write_nfo": True,
                "write_cover": False,
            })

        assert resp.status_code == 200
        items = result_items(resp.text)
        assert len(items) == 1
        assert items[0]["success"] is False
        assert items[0]["reason"] == "not_found"

        attempted = read_scrape_attempted_at(db_path, path_uri)
        assert attempted > 0

        assert path_uri not in missing_check_paths(client, db_path)

