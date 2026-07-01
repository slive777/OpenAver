"""TASK-88c-T4: off-flavor readonly end-to-end acceptance.

Full-stack integration test wiring T-1 (`/api/gallery/image` output_path
whitelist) + T-2 (`generate_avlist` readonly branch + SSE bridge) + 88b
(`produce_source` real run). Runs the REAL `produce_source` via
`GET /api/gallery/generate`; only the producer's four external side-effects are
mocked at ``core.readonly_producer.*`` (their import landing point):

    search_jav / download_image / generate_jellyfin_images / generate_nfo

The mock side-effects WRITE REAL FILES so the on-disk media-library structure
can be asserted. `produce_source`, `_movie_dir` collision-avoidance, `_upsert_db`,
the SSE thread/queue bridge, and the image-proxy whitelist all run for real
against a real tmp output dir and a real tmp sqlite DB.

Acceptance §6 items covered here: 1, 5, 6, 7, 13, 16, 17 (+ incremental idempotency).
"""
from __future__ import annotations

import os
from pathlib import Path

from core.database import VideoRepository
from core.path_utils import to_file_uri, uri_to_fs_path

# Baseline `videos` schema (Acceptance #7 — no new columns from 88b write path).
_BASELINE_VIDEO_COLUMNS = {
    "id", "path", "number", "title", "original_title", "actresses", "maker",
    "director", "series", "label", "tags", "sample_images", "user_tags",
    "duration", "size_bytes", "cover_path", "release_date", "mtime", "nfo_mtime",
    "created_at", "updated_at",
}

_FAKE_COVER_BYTES = b"\xff\xd8\xff\xe0FAKE-COVER-JPEG"
_FAKE_IMG_BYTES = b"\xff\xd8\xff\xe0FAKE-IMG"


# ---------------------------------------------------------------------------
# Mock side-effects (write real files) — the contract that makes the on-disk
# acceptance assertions meaningful (card §"mock 必須寫真檔").
# ---------------------------------------------------------------------------

def _fake_search_jav(number, source="auto", proxy_url=""):
    """Return a scraped-meta dict per number. NO network."""
    return {
        "number": number,
        "title": f"Title {number}",
        "actors": ["Actress A", "Actress B"],
        "cover": f"http://fake.local/{number}/cover.jpg",  # non-empty → triggers cover download
        "sample_images": [
            f"http://fake.local/{number}/s1.jpg",
            f"http://fake.local/{number}/s2.jpg",
        ],
        "tags": ["Tag1", "Tag2"],
        "date": "2024-01-01",
        "maker": "FakeMaker",
    }


def _fake_download_image(url, dest):
    """side_effect: actually create `dest` (cover or extrafanart) + return True."""
    p = Path(dest)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_FAKE_COVER_BYTES)
    return True


def _fake_generate_jellyfin_images(cover_fs, base_stem):
    """side_effect: create `<base_stem>-poster.jpg` + `-fanart.jpg` + return dict."""
    Path(base_stem + "-poster.jpg").write_bytes(_FAKE_IMG_BYTES)
    Path(base_stem + "-fanart.jpg").write_bytes(_FAKE_IMG_BYTES)
    return {"poster": True, "fanart": True}


def _fake_generate_nfo(**kwargs):
    """side_effect: create the nfo file (minimal XML) + return True.

    producer calls generate_nfo(..., output_path=nfo_fs, ...) entirely by keyword.
    """
    dest = kwargs["output_path"]
    Path(dest).write_text(
        f"<movie><title>{kwargs.get('title', '')}</title>"
        f"<num>{kwargs.get('number', '')}</num></movie>",
        encoding="utf-8",
    )
    return True


def _install_producer_mocks(monkeypatch):
    """Patch the four externals at their producer import landing point.

    Target MUST be ``core.readonly_producer.*`` (the import landing point), NOT
    ``core.organizer.*`` / ``core.scraper.*`` — patching the source modules would
    miss the already-bound references and let real network/IO run (§8 risk 6).
    """
    monkeypatch.setattr("core.readonly_producer.search_jav", _fake_search_jav)
    monkeypatch.setattr("core.readonly_producer.download_image", _fake_download_image)
    monkeypatch.setattr("core.readonly_producer.generate_jellyfin_images", _fake_generate_jellyfin_images)
    monkeypatch.setattr("core.readonly_producer.generate_nfo", _fake_generate_nfo)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_source_dir(base: Path, name: str, numbers: list[str]) -> Path:
    """Create a source dir with one tiny fake .mp4 per number."""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    for num in numbers:
        (d / f"{num}.mp4").write_bytes(b"FAKE-VIDEO-BYTES")
    return d


def _make_config(sources: list[dict], html_out: Path, download_samples: bool = False) -> dict:
    """Build a readonly + off-flavor gallery config with the given sources.

    Each `sources` element: {"path": str, "output_path": str, "readonly": bool}.
    folder_layers=[] → per-movie subdir is the movie leaf directly under output_root.
    """
    return {
        "gallery": {
            "directories": sources,
            "path_mappings": {},
            "min_size_mb": 0,
            "output_dir": str(html_out),  # absolute → stays out of the repo tree
            "output_filename": "gallery_output.html",
        },
        "scraper": {
            "external_manager": "off",
            "folder_layers": [],
            "folder_format": "",
            "filename_format": "{num}",
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "download_sample_images": download_samples,
        },
        "search": {"proxy_url": ""},
        "general": {"theme": "light"},
    }


def _wire(monkeypatch, config: dict, db_path: Path):
    """Patch load_config + get_db_path in the scanner router; install producer mocks."""
    monkeypatch.setattr("web.routers.scanner.load_config", lambda: config)
    monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
    _install_producer_mocks(monkeypatch)


def _snapshot(root: Path) -> dict:
    """Recursive {relpath: (size, mtime_ns)} snapshot for zero-write diffing."""
    snap: dict = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            fp = Path(dirpath) / f
            st = fp.stat()
            snap[str(fp.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return snap


def _all_extensions(root: Path) -> set[str]:
    exts: set[str] = set()
    for _dirpath, _dirs, files in os.walk(root):
        for f in files:
            exts.add(os.path.splitext(f)[1].lower())
    return exts


def _run_generate(client, parse_sse_events):
    resp = client.get("/api/gallery/generate")
    assert resp.status_code == 200
    return parse_sse_events(resp.text)


def _done_event(events: list) -> dict:
    for e in events:
        if e.get("type") == "done":
            return e
    raise AssertionError("no done event in SSE stream")


# ---------------------------------------------------------------------------
# Case 1/5/6/7/13/16: happy path (single source, ~5 movies, samples ON)
# ---------------------------------------------------------------------------

class TestOffFlavorHappyPath:
    def _setup(self, tmp_path, monkeypatch, download_samples=True):
        numbers = ["ABC-001", "ABC-002", "ABC-003", "ABC-004", "ABC-005"]
        src = _make_source_dir(tmp_path / "src", "movies", numbers)
        output = tmp_path / "output"
        output.mkdir()
        html_out = tmp_path / "htmlout"
        db_path = tmp_path / "test.db"
        config = _make_config(
            [{"path": str(src), "output_path": str(output), "readonly": True}],
            html_out,
            download_samples=download_samples,
        )
        _wire(monkeypatch, config, db_path)
        return numbers, src, output, db_path

    def test_per_movie_assets_and_no_strm(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#5/#6: each movie → subdir with .nfo + cover + -poster + -fanart + extrafanart; NO .strm."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        _run_generate(client, parse_sse_events)

        for num in numbers:
            movie_dir = output / num
            assert movie_dir.is_dir(), f"missing movie dir for {num}"
            assert (movie_dir / f"{num}.nfo").exists(), f"missing nfo {num}"
            assert (movie_dir / f"{num}.jpg").exists(), f"missing cover {num}"
            assert (movie_dir / f"{num}-poster.jpg").exists(), f"missing poster {num}"
            assert (movie_dir / f"{num}-fanart.jpg").exists(), f"missing fanart {num}"
            # samples ON → extrafanart/fanart1.jpg
            assert (movie_dir / "extrafanart" / "fanart1.jpg").exists(), f"missing extrafanart {num}"

        # Acceptance #5: off-flavor produces NO .strm anywhere under output.
        assert ".strm" not in _all_extensions(output)

    def test_db_path_cover_sample_pointers(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#6: DB path == source URI; cover_path/sample_images under output_path."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        _run_generate(client, parse_sse_events)

        repo = VideoRepository(str(db_path))
        output_uri = to_file_uri(str(output), {})
        for num in numbers:
            src_uri = to_file_uri(str(src / f"{num}.mp4"), {})
            v = repo.get_by_path(src_uri)
            assert v is not None, f"no DB row for {num}"
            assert v.path == src_uri  # streaming key = source URI
            assert v.cover_path.startswith(output_uri), f"cover not under output: {v.cover_path}"
            assert v.sample_images, f"expected samples for {num}"
            for s in v.sample_images:
                assert s.startswith(output_uri), f"sample not under output: {s}"

    def test_schema_no_new_columns(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#7: videos table column set unchanged (no schema drift from 88b write path)."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        _run_generate(client, parse_sse_events)

        repo = VideoRepository(str(db_path))
        conn = repo._get_connection()
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(videos)")}
        finally:
            conn.close()
        assert cols == _BASELINE_VIDEO_COLUMNS

    def test_source_dir_zero_write(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#1: source dir recursive snapshot identical before/after generate."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        before = _snapshot(src)
        _run_generate(client, parse_sse_events)
        after = _snapshot(src)
        assert before == after, "source directory was modified (zero-write violated)"

    def test_sse_readonly_stats_four_numbers(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#13: done event readonly_stats four numbers match landed movie count."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        events = _run_generate(client, parse_sse_events)
        stats = _done_event(events)["readonly_stats"]

        # actual landed = per-movie subdirs that contain an nfo
        landed = sum(1 for num in numbers if (output / num / f"{num}.nfo").exists())
        assert landed == len(numbers)
        assert stats["created"] == landed
        assert stats["skipped"] == 0
        assert stats["no_scrape"] == 0
        assert stats["failed"] == 0

    def test_cover_via_image_proxy_200_and_bytes(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#16 (chains T-1): DB cover_path → /api/gallery/image → 200 + real bytes; outside → 403."""
        numbers, src, output, db_path = self._setup(tmp_path, monkeypatch)
        _run_generate(client, parse_sse_events)

        repo = VideoRepository(str(db_path))
        src_uri = to_file_uri(str(src / f"{numbers[0]}.mp4"), {})
        cover_uri = repo.get_by_path(src_uri).cover_path
        # frontend/showcase convention: proxy receives the fs path (file:/// stripped)
        cover_fs = uri_to_fs_path(cover_uri)

        r = client.get("/api/gallery/image", params={"path": cover_fs})
        assert r.status_code == 200, r.text
        assert r.content == _FAKE_COVER_BYTES

        # Reverse lock: a .jpg outside any source/output dir → 403 (whitelist not degraded).
        outside = tmp_path / "outside" / "x.jpg"
        outside.parent.mkdir()
        outside.write_bytes(_FAKE_COVER_BYTES)
        r403 = client.get("/api/gallery/image", params={"path": str(outside)})
        assert r403.status_code == 403


# ---------------------------------------------------------------------------
# Case: samples OFF (gated extrafanart behavior)
# ---------------------------------------------------------------------------

def test_samples_off_no_extrafanart(tmp_path, monkeypatch, client, parse_sse_events):
    """download_sample_images=False → no extrafanart dir, DB sample_images empty."""
    numbers = ["DEF-010", "DEF-011"]
    src = _make_source_dir(tmp_path / "src", "movies", numbers)
    output = tmp_path / "output"
    output.mkdir()
    db_path = tmp_path / "test.db"
    config = _make_config(
        [{"path": str(src), "output_path": str(output), "readonly": True}],
        tmp_path / "htmlout",
        download_samples=False,
    )
    _wire(monkeypatch, config, db_path)
    _run_generate(client, parse_sse_events)

    repo = VideoRepository(str(db_path))
    for num in numbers:
        assert (output / num / f"{num}.nfo").exists()
        assert not (output / num / "extrafanart").exists()
        src_uri = to_file_uri(str(src / f"{num}.mp4"), {})
        assert repo.get_by_path(src_uri).sample_images == []


# ---------------------------------------------------------------------------
# Case 17: same-number across two sources → two distinct leaf subdirs
# ---------------------------------------------------------------------------

def test_same_number_two_sources_collision(tmp_path, monkeypatch, client, parse_sse_events):
    """#17: two readonly sources each with ABC-123.mp4 → two non-overwriting leaf dirs."""
    src_a = _make_source_dir(tmp_path / "srcA", "a", ["ABC-123"])
    src_b = _make_source_dir(tmp_path / "srcB", "b", ["ABC-123"])
    output = tmp_path / "output"
    output.mkdir()
    db_path = tmp_path / "test.db"
    config = _make_config(
        [
            {"path": str(src_a), "output_path": str(output), "readonly": True},
            {"path": str(src_b), "output_path": str(output), "readonly": True},
        ],
        tmp_path / "htmlout",
    )
    _wire(monkeypatch, config, db_path)
    events = _run_generate(client, parse_sse_events)

    # Two distinct leaf subdirs under output_root, both named ABC-123*
    leaf_dirs = sorted(p.name for p in output.iterdir() if p.is_dir())
    abc_dirs = [d for d in leaf_dirs if d.startswith("ABC-123")]
    assert len(abc_dirs) == 2, f"expected 2 distinct leaf dirs, got {abc_dirs}"
    assert "ABC-123" in abc_dirs
    hashed = [d for d in abc_dirs if d != "ABC-123"]
    assert len(hashed) == 1 and hashed[0].startswith("ABC-123-"), abc_dirs

    # Each complete + non-overwriting (distinct dirs, each with its own nfo + cover).
    # Filenames are derived from the number ("{num}" template), not the (hashed) leaf dir.
    for d in abc_dirs:
        assert (output / d / "ABC-123.nfo").exists(), f"missing nfo in {d}"
        assert (output / d / "ABC-123.jpg").exists(), f"missing cover in {d}"

    stats = _done_event(events)["readonly_stats"]
    assert stats["created"] == 2

    # Both source URIs present in DB, pointing at distinct output covers.
    repo = VideoRepository(str(db_path))
    uri_a = to_file_uri(str(src_a / "ABC-123.mp4"), {})
    uri_b = to_file_uri(str(src_b / "ABC-123.mp4"), {})
    va, vb = repo.get_by_path(uri_a), repo.get_by_path(uri_b)
    assert va is not None and vb is not None
    assert va.cover_path != vb.cover_path


# ---------------------------------------------------------------------------
# Case (bonus): incremental idempotency
# ---------------------------------------------------------------------------

def test_incremental_idempotent(tmp_path, monkeypatch, client, parse_sse_events):
    """Run generate twice → second run all skipped, output not rewritten, DB row count stable."""
    numbers = ["GHI-020", "GHI-021", "GHI-022"]
    src = _make_source_dir(tmp_path / "src", "movies", numbers)
    output = tmp_path / "output"
    output.mkdir()
    db_path = tmp_path / "test.db"
    config = _make_config(
        [{"path": str(src), "output_path": str(output), "readonly": True}],
        tmp_path / "htmlout",
    )
    _wire(monkeypatch, config, db_path)

    events1 = _run_generate(client, parse_sse_events)
    assert _done_event(events1)["readonly_stats"]["created"] == len(numbers)

    out_snap = _snapshot(output)
    repo = VideoRepository(str(db_path))
    count1 = repo.count()

    events2 = _run_generate(client, parse_sse_events)
    stats2 = _done_event(events2)["readonly_stats"]
    assert stats2["created"] == 0
    assert stats2["skipped"] == len(numbers)

    assert _snapshot(output) == out_snap, "output rewritten on idempotent re-run"
    assert VideoRepository(str(db_path)).count() == count1


# ---------------------------------------------------------------------------
# PR#91 P2-D: DirectoryConfig.path as a file:/// URI (schema「FS 路徑或 URI」).
# A URI source path must be handled idempotently everywhere it is converted:
#   - generate_avlist configured_dir_uris (post-loop) → readonly rows must NOT
#     be double-wrapped-and-filtered out of the generated gallery list.
#   - get_video / get_image allowlists (_dir_candidate_forms) → a file under a
#     URI source must PASS (not 403 from a file:///file:/// double-wrap).
# RED against the pre-fix code (to_file_uri / normalize_path on a URI input).
# ---------------------------------------------------------------------------

class TestUriSourcePathIdempotent:
    def test_readonly_rows_appear_in_generated_list_uri_source(
        self, tmp_path, monkeypatch, client, parse_sse_events
    ):
        """URI source path → readonly-generated rows land in the gallery list.

        done.video_count is the DB row set filtered by configured_dir_uris; the
        pre-fix double-wrap (to_file_uri('file:///…') = 'file:///file:///…')
        filters every readonly row out → video_count == 0 (RED).
        """
        numbers = ["URI-001", "URI-002", "URI-003"]
        src = _make_source_dir(tmp_path / "src", "movies", numbers)
        output = tmp_path / "output"
        output.mkdir()
        db_path = tmp_path / "test.db"
        # Source `path` stored as a file:/// URI (not an FS path).
        config = _make_config(
            [{"path": to_file_uri(str(src), {}), "output_path": str(output), "readonly": True}],
            tmp_path / "htmlout",
        )
        _wire(monkeypatch, config, db_path)

        events = _run_generate(client, parse_sse_events)
        done = _done_event(events)

        # readonly producer still created every movie (source scanning already
        # URI-safe via _list_source_videos), ...
        assert done["readonly_stats"]["created"] == len(numbers)
        # ... and the post-loop configured_dir_uris filter keeps them in the list.
        assert done["video_count"] == len(numbers)

    def test_video_proxy_allows_file_under_uri_source(self, tmp_path, monkeypatch, client):
        """A video under a URI-form source dir passes the get_video allowlist (not 403)."""
        from urllib.parse import quote

        src = _make_source_dir(tmp_path / "src", "movies", ["URI-100"])
        video_file = src / "URI-100.mp4"

        test_config = {
            "gallery": {
                "directories": [to_file_uri(str(src), {})],  # URI source path
                "path_mappings": {},
            },
            "scraper": {"video_extensions": [".mp4"]},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)

        path_arg = to_file_uri(str(video_file), {})
        resp = client.get(f"/api/gallery/video?path={quote(path_arg)}")
        assert resp.status_code == 200, resp.text
        assert resp.content == b"FAKE-VIDEO-BYTES"

    def test_image_proxy_allows_file_under_uri_source(self, tmp_path, monkeypatch, client):
        """A cover under a URI-form source dir passes the get_image allowlist (not 403);
        an outside .jpg still 403 (whitelist not degraded)."""
        src = tmp_path / "src"
        src.mkdir()
        cover = src / "cover.jpg"
        cover.write_bytes(_FAKE_COVER_BYTES)

        test_config = {
            "gallery": {
                "directories": [{"path": to_file_uri(str(src), {}), "output_path": ""}],
                "path_mappings": {},
            },
            "scraper": {},
        }
        monkeypatch.setattr("web.routers.scanner.load_config", lambda: test_config)

        r = client.get("/api/gallery/image", params={"path": str(cover)})
        assert r.status_code == 200, r.text
        assert r.content == _FAKE_COVER_BYTES

        outside = tmp_path / "outside" / "x.jpg"
        outside.parent.mkdir()
        outside.write_bytes(_FAKE_COVER_BYTES)
        r403 = client.get("/api/gallery/image", params={"path": str(outside)})
        assert r403.status_code == 403
