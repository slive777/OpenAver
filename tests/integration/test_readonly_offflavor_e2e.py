"""TASK-89a-T6: off-flavor readonly end-to-end acceptance (spec-89 §89a.3).

Originally created under TASK-88c-T4 (spec-88 §6); T3/T4/T5 (feature/89-produced-
library) extended it in place as `produce_source`/`_resolve_movie_dir`/
`_upsert_db` were rewritten for the fixed App-managed output root (CD-89a-7).
This file is now the official e2e acceptance suite for spec-89 §89a.3, not §6.

Full-stack integration test wiring T-1 (`/api/gallery/image` output_path
whitelist) + T-2 (`generate_avlist` readonly branch + SSE bridge) + 88b/89a
(`produce_source` real run). Runs the REAL `produce_source` via
`GET /api/gallery/generate`; only the producer's four external side-effects are
mocked at ``core.readonly_producer.*`` (their import landing point):

    search_jav / download_image / generate_jellyfin_images / generate_nfo

The mock side-effects WRITE REAL FILES so the on-disk media-library structure
can be asserted. `produce_source`, `_resolve_movie_dir` allocation/increment
(TASK-89a-T3 — replaces the old `_movie_dir` cover-index model), `_upsert_db`,
the SSE thread/queue bridge, and the image-proxy whitelist all run for real
against a real tmp output dir and a real tmp sqlite DB.

spec-89 §89a.3 acceptance mapping (see TASK-89a-T6 for the full inventory):
    #1 (re-run in place, no duplicate dirs)   → test_incremental_idempotent,
                                                 test_real_readstore_overwrite_title_drift_and_extrafanart_shrink
    #2 (off needs no manually-set output dir) → test_per_movie_assets_and_no_strm,
                                                 test_db_path_cover_sample_pointers
    #3 (rescrape keeps movie-dir memory)      → test_real_readstore_overwrite_title_drift_and_extrafanart_shrink
    #4 (multi-format/multi-source no clobber) → test_same_number_two_sources_collision,
                                                 test_same_source_same_number_two_formats_increment
    #5 (legacy DB upgrade needs no rebuild)   → out of scope for this file (migration-only;
                                                 covered by T1's unit tests — this suite always
                                                 starts from a fresh tmp DB)
`test_same_number_two_sources_collision`'s own docstring records how it replaces
88's collision-hash premise (multi-source now means multi fixed-root, not one
shared root with hash-suffix disambiguation).
"""
from __future__ import annotations

import os
from pathlib import Path

from core.database import Video, VideoRepository
from core.path_utils import to_file_uri, uri_to_fs_path

# Baseline `videos` schema (Acceptance #7 — no new columns from 88b write path).
_BASELINE_VIDEO_COLUMNS = {
    "id", "path", "number", "title", "original_title", "actresses", "maker",
    "director", "series", "label", "tags", "sample_images", "user_tags",
    "duration", "size_bytes", "cover_path", "output_dir", "release_date", "mtime", "nfo_mtime",
    "scrape_attempted_at", "created_at", "updated_at",
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
    """Patch load_config + get_db_path (router AND readonly_producer) + install producer mocks.

    TASK-89a-T2 (CD-89a-7): off-flavor sources no longer write under the
    per-source `output_path` — `resolve_output_root` computes a fixed App-managed
    root via `get_db_path().parent / "lib" / <name>`, calling `core.database.get_db_path`
    through its `core.readonly_producer` import landing point (NOT the router's).
    Both landing points must be patched to the same tmp db_path so the whole run
    stays confined to tmp_path (never touching the real repo's output/ dir).
    """
    monkeypatch.setattr("web.routers.scanner.load_config", lambda: config)
    monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: db_path)
    monkeypatch.setattr("core.readonly_producer.get_db_path", lambda: db_path)
    _install_producer_mocks(monkeypatch)


def _off_root(src_path: Path, db_path: Path) -> Path:
    """Compute the fixed off-flavor output root for a source (mirrors resolve_output_root's
    off branch) — used by assertions since off mode ignores DirectoryConfig.output_path."""
    from core.readonly_producer import _derive_source_name
    return db_path.parent / "lib" / _derive_source_name(str(src_path))


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
        # TASK-89a-T2 (CD-89a-7): off mode IGNORES this — kept only to prove the
        # backend never trusts a stale/manually-typed output_path in off mode
        # (see the "decoy" assertion in test_per_movie_assets_and_no_strm).
        decoy_output_path = tmp_path / "decoy-output-path-must-be-ignored"
        decoy_output_path.mkdir()
        html_out = tmp_path / "htmlout"
        db_path = tmp_path / "test.db"
        config = _make_config(
            [{"path": str(src), "output_path": str(decoy_output_path), "readonly": True}],
            html_out,
            download_samples=download_samples,
        )
        _wire(monkeypatch, config, db_path)
        output = _off_root(src, db_path)  # the ACTUAL fixed off-flavor root
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
        # CD-89a-7: the manually-configured (decoy) output_path must be untouched —
        # off mode ignores source.output_path entirely.
        assert list(Path(tmp_path / "decoy-output-path-must-be-ignored").iterdir()) == []

    def test_db_path_cover_sample_pointers(self, tmp_path, monkeypatch, client, parse_sse_events):
        """#6: DB path == source URI; cover_path/sample_images under the fixed off-flavor root."""
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
# TASK-89a-T6: producer-origin signal contract lock (89a → 89b handoff).
#
# spec-89 §89b.1's "missing NFO/cover" false-positive fix (89b's job, NOT this
# task) will filter `check_missing()` rows with `if v.output_dir: continue` —
# i.e. `output_dir != ''` IS the producer-origin signal 89b will consume.
# T6 deliberately does NOT add a surface for it (OPUS decision — see
# TASK-89a-T6.md "producer-origin 曝露決策": `output_dir` is already a plain,
# unfiltered `Video` field with zero existing callers that would justify a
# property/helper). This test instead locks the CONTRACT end-to-end: after
# off-flavor generation, every produced row's `output_dir` is actually
# non-empty (not just "the code path exists on paper") — so if a future
# change to `_upsert_db`/`_resolve_movie_dir` regresses it back to `''`,
# 89b's filter silently stops working, and this test catches it first.
# ---------------------------------------------------------------------------

def test_produced_rows_expose_nonempty_output_dir_signal(tmp_path, monkeypatch, client, parse_sse_events):
    """Locks the 89a→89b handoff contract: off-generated rows' `output_dir`
    is non-empty, a `file:///` URI, and lives under the source's fixed
    off-flavor output root — the exact signal 89b's `check_missing()` will
    later filter on (`if v.output_dir: continue`).
    """
    numbers = ["MNO-040", "MNO-041"]
    src = _make_source_dir(tmp_path / "src", "movies", numbers)
    db_path = tmp_path / "test.db"
    config = _make_config(
        [{"path": str(src), "output_path": "", "readonly": True}],
        tmp_path / "htmlout",
    )
    _wire(monkeypatch, config, db_path)
    _run_generate(client, parse_sse_events)

    output_root = _off_root(src, db_path)
    output_root_uri = to_file_uri(str(output_root), {})

    repo = VideoRepository(str(db_path))
    produced = [v for v in repo.get_all() if v.number in numbers]
    assert len(produced) == len(numbers), "expected one DB row per produced movie"
    for v in produced:
        assert v.output_dir, f"produced row {v.number} has empty output_dir — 89b filter signal broken"
        assert v.output_dir.startswith("file:///"), f"output_dir not a file:// URI: {v.output_dir}"
        assert v.output_dir.startswith(output_root_uri), (
            f"output_dir {v.output_dir} not under the fixed off-flavor root {output_root_uri}"
        )

    # Contrast: a row NOT produced by the off-flavor pipeline keeps the Video
    # dataclass default output_dir='' — proves the assertions above actually
    # discriminate producer vs. non-producer rows, not vacuously true for any row.
    non_producer_uri = to_file_uri(str(tmp_path / "not-produced.mp4"), {})
    repo.upsert(Video(path=non_producer_uri, number="NOTPROD-1"))
    non_producer = repo.get_by_path(non_producer_uri)
    assert non_producer is not None
    assert non_producer.output_dir == "", "sanity: non-producer row must keep empty output_dir"


# ---------------------------------------------------------------------------
# Case: samples OFF (gated extrafanart behavior)
# ---------------------------------------------------------------------------

def test_samples_off_no_extrafanart(tmp_path, monkeypatch, client, parse_sse_events):
    """download_sample_images=False → no extrafanart dir, DB sample_images empty."""
    numbers = ["DEF-010", "DEF-011"]
    src = _make_source_dir(tmp_path / "src", "movies", numbers)
    db_path = tmp_path / "test.db"
    config = _make_config(
        # CD-89a-7: off mode ignores output_path — omitted here (UI hides this field
        # in off mode, so the realistic value is "").
        [{"path": str(src), "output_path": "", "readonly": True}],
        tmp_path / "htmlout",
        download_samples=False,
    )
    _wire(monkeypatch, config, db_path)
    _run_generate(client, parse_sse_events)

    output = _off_root(src, db_path)
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
    """#17: two readonly sources each with ABC-123.mp4 → two non-overwriting leaf dirs.

    TASK-89a-T2 (CD-89a-7) note: before this task, off-flavor sources shared a
    single user-configured `output_path`, so `_movie_dir`'s collision-avoidance
    hash-suffix was the mechanism that kept the two sources' same-number movies
    apart (one clean `ABC-123`, one hashed `ABC-123-<hash>`) under one tree.
    Now each off-flavor source resolves to its OWN distinct fixed root
    (`resolve_output_root` derives the name from the source's own path — CD-89a-7
    Option B), so the two sources never share a root at all: each gets a clean
    `ABC-123` leaf under its own tree, with no hash suffix involved. This test now
    asserts non-collision at the SOURCE level rather than the leaf-hash level.
    """
    src_a = _make_source_dir(tmp_path / "srcA", "a", ["ABC-123"])
    src_b = _make_source_dir(tmp_path / "srcB", "b", ["ABC-123"])
    db_path = tmp_path / "test.db"
    config = _make_config(
        [
            {"path": str(src_a), "output_path": "", "readonly": True},
            {"path": str(src_b), "output_path": "", "readonly": True},
        ],
        tmp_path / "htmlout",
    )
    _wire(monkeypatch, config, db_path)
    events = _run_generate(client, parse_sse_events)

    root_a = _off_root(src_a, db_path)
    root_b = _off_root(src_b, db_path)
    assert root_a != root_b, "two distinct sources must resolve to distinct off-flavor roots"

    # Each source gets its OWN clean (non-hashed) ABC-123 leaf — no cross-source collision.
    for root in (root_a, root_b):
        assert (root / "ABC-123").is_dir(), f"missing ABC-123 leaf dir under {root}"
        assert (root / "ABC-123" / "ABC-123.nfo").exists(), f"missing nfo under {root}"
        assert (root / "ABC-123" / "ABC-123.jpg").exists(), f"missing cover under {root}"

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
# TASK-89a-T3 (CD-89a-3): same source, same number, two different file
# extensions → increment allocation must give each its OWN movie dir
# (ABC-123 / ABC-123-2), never overwrite one with the other's assets.
# ---------------------------------------------------------------------------

def test_same_source_same_number_two_formats_increment(tmp_path, monkeypatch, client, parse_sse_events):
    """One readonly source with ABC-123.mp4 AND ABC-123.mkv (same number, two source
    files) → both land, in two distinct dirs (ABC-123, ABC-123-2), each with its own
    nfo/cover; DB has two rows with two distinct output_dir values."""
    src = tmp_path / "src" / "movies"
    src.mkdir(parents=True)
    (src / "ABC-123.mp4").write_bytes(b"FAKE-VIDEO-BYTES-MP4")
    (src / "ABC-123.mkv").write_bytes(b"FAKE-VIDEO-BYTES-MKV")
    db_path = tmp_path / "test.db"
    config = _make_config(
        [{"path": str(src), "output_path": "", "readonly": True}],
        tmp_path / "htmlout",
    )
    _wire(monkeypatch, config, db_path)

    events = _run_generate(client, parse_sse_events)
    stats = _done_event(events)["readonly_stats"]
    assert stats["created"] == 2
    assert stats["failed"] == 0

    output = _off_root(src, db_path)
    assert (output / "ABC-123").is_dir()
    assert (output / "ABC-123-2").is_dir()
    # Both files scrape to the SAME number (ABC-123) → the filename inside each leaf
    # dir is "ABC-123.nfo"/"ABC-123.jpg" regardless of the leaf's own (incremented) name.
    for leaf in ("ABC-123", "ABC-123-2"):
        assert (output / leaf / "ABC-123.nfo").exists(), f"missing nfo under {leaf}"
        assert (output / leaf / "ABC-123.jpg").exists(), f"missing cover under {leaf}"

    repo = VideoRepository(str(db_path))
    uri_mp4 = to_file_uri(str(src / "ABC-123.mp4"), {})
    uri_mkv = to_file_uri(str(src / "ABC-123.mkv"), {})
    v_mp4, v_mkv = repo.get_by_path(uri_mp4), repo.get_by_path(uri_mkv)
    assert v_mp4 is not None and v_mkv is not None
    assert v_mp4.output_dir != v_mkv.output_dir
    assert v_mp4.output_dir and v_mkv.output_dir  # neither is empty (CASE-WHEN no-op guard)
    assert {uri_to_fs_path(v_mp4.output_dir), uri_to_fs_path(v_mkv.output_dir)} == {
        str(output / "ABC-123"), str(output / "ABC-123-2"),
    }


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
# TASK-89a-T4 (T3 carry-forward): real read-store overwrite.
#
# test_incremental_idempotent above never actually exercises the read-store /
# stale-cleanup code path: on its second run `_should_skip`'s attempted-index
# check (TASK-89b-T3) holds for every file, so everything is skipped before
# `_resolve_movie_dir`/`_write_movie_assets` ever run. This test constructs the
# narrower case the card calls for: zero out `scrape_attempted_at` for the row
# via `repo.update_scrape_attempted_at(src_uri, 0)` (simulating "never
# attempted") while leaving the DB row's `output_dir` alone, so the second run
# walks the real read-and-reuse branch of `_resolve_movie_dir` and lands in
# `_write_movie_assets`'s stale-asset cleanup (TASK-89a-T4 / Codex #3) for real,
# against the actual SSE endpoint + a real sqlite DB — not mocked internals.
# ---------------------------------------------------------------------------

def _fake_search_jav_round1(number, source="auto", proxy_url=""):
    """Round 1: title A, 3 sample images (for the extrafanart-shrink assertion)."""
    return {
        "number": number,
        "title": f"Title {number}",
        "actors": ["Actress A", "Actress B"],
        "cover": f"http://fake.local/{number}/cover.jpg",
        "sample_images": [
            f"http://fake.local/{number}/s1.jpg",
            f"http://fake.local/{number}/s2.jpg",
            f"http://fake.local/{number}/s3.jpg",
        ],
        "tags": ["Tag1", "Tag2"],
        "date": "2024-01-01",
        "maker": "FakeMaker",
    }


def _fake_search_jav_round2(number, source="auto", proxy_url=""):
    """Round 2: DIFFERENT title (maker corrected it), only 2 sample images."""
    return {
        "number": number,
        "title": f"Title-B {number}",
        "actors": ["Actress A", "Actress B"],
        "cover": f"http://fake.local/{number}/cover.jpg",
        "sample_images": [
            f"http://fake.local/{number}/s1.jpg",
            f"http://fake.local/{number}/s2.jpg",
        ],
        "tags": ["Tag1", "Tag2"],
        "date": "2024-01-01",
        "maker": "FakeMaker",
    }


def _expected_basename(meta, source_fs_path, scraper_cfg):
    """Compute the actual basename the pipeline would produce for `meta` — avoids
    hand-typing a filename string that could silently drift from real behavior."""
    from core.readonly_producer import _build_basename, _format_data
    fd = _format_data(meta, source_fs_path, scraper_cfg)
    return _build_basename(fd, source_fs_path, scraper_cfg)


def test_real_readstore_overwrite_title_drift_and_extrafanart_shrink(
    tmp_path, monkeypatch, client, parse_sse_events
):
    """Zero out `scrape_attempted_at` (bypass `_should_skip`'s attempted-index
    check) → re-scrape with a corrected title + fewer samples → asserts the
    SECOND run truly walks the read-store branch (same output_dir, not
    re-allocated) and TASK-89a-T4's stale cleanup (old title-A series + shrunk
    extrafanart removed, only title-B series left).
    """
    numbers = ["JKL-030"]
    num = numbers[0]
    # CD-89a-7: off flavour IGNORES source.output_path entirely — it always
    # resolves to the fixed App-managed `get_db_path().parent/"lib"/<name>` root
    # (see `_off_root` below / `resolve_output_root`'s off branch). A decoy
    # output_path is passed only to prove the backend doesn't accidentally use it.
    src = _make_source_dir(tmp_path / "src", "movies", numbers)
    decoy_output_path = tmp_path / "decoy-output-path-must-be-ignored"
    decoy_output_path.mkdir()
    db_path = tmp_path / "test.db"
    # filename_format must include {title} — default _make_config uses "{num}"
    # only, which would make old_base == new_base regardless of title drift.
    config = _make_config(
        [{"path": str(src), "output_path": str(decoy_output_path), "readonly": True}],
        tmp_path / "htmlout",
        download_samples=True,
    )
    config["scraper"]["filename_format"] = "{num} {title}"
    _wire(monkeypatch, config, db_path)
    monkeypatch.setattr("core.readonly_producer.search_jav", _fake_search_jav_round1)
    output = _off_root(src, db_path)  # the ACTUAL fixed off-flavor root

    source_fs_path = str(src / f"{num}.mp4")
    meta_a = _fake_search_jav_round1(num)
    meta_b = _fake_search_jav_round2(num)
    old_base = _expected_basename(meta_a, source_fs_path, config["scraper"])
    new_base = _expected_basename(meta_b, source_fs_path, config["scraper"])
    assert old_base != new_base, "sanity: round1/round2 metas must produce different basenames"

    # --- Round 1: normal creation ---
    events1 = _run_generate(client, parse_sse_events)
    stats1 = _done_event(events1)["readonly_stats"]
    assert stats1["created"] == 1

    movie_dir = output / num
    assert (movie_dir / f"{old_base}.nfo").exists()
    assert (movie_dir / f"{old_base}.jpg").exists()
    assert (movie_dir / f"{old_base}-poster.jpg").exists()
    assert (movie_dir / f"{old_base}-fanart.jpg").exists()
    assert (movie_dir / "extrafanart" / "fanart3.jpg").exists()

    repo = VideoRepository(str(db_path))
    src_uri = to_file_uri(source_fs_path, {})
    row1 = repo.get_by_path(src_uri)
    assert row1 is not None
    output_dir_before = row1.output_dir
    assert row1.title == meta_a["title"]

    # --- Bypass `_should_skip`'s attempted-index check (TASK-89b-T3): zero out
    # scrape_attempted_at for this row directly, simulating "never attempted".
    # output_dir / all other DB fields are left completely untouched, and the
    # cover file on disk is NOT deleted — the new skip model no longer looks
    # at the filesystem at all. ---
    repo.update_scrape_attempted_at(src_uri, 0)

    # --- Round 2: search_jav now returns a corrected title + fewer samples ---
    monkeypatch.setattr("core.readonly_producer.search_jav", _fake_search_jav_round2)
    events2 = _run_generate(client, parse_sse_events)
    stats2 = _done_event(events2)["readonly_stats"]

    # Proves the read-store branch (not the skip branch) was actually walked.
    assert stats2["created"] == 1, "must NOT be skipped — scrape_attempted_at was zeroed"
    assert stats2["skipped"] == 0

    row2 = repo.get_by_path(src_uri)
    assert row2 is not None
    assert row2.output_dir == output_dir_before, (
        "read-store reuse: same movie_dir must be reused, not re-allocated"
    )
    assert row2.title == meta_b["title"]

    # TASK-89a-T4: old title-A series fully gone, only title-B series remains.
    assert not (movie_dir / f"{old_base}.nfo").exists(), "stale title-A nfo survived"
    assert not (movie_dir / f"{old_base}.jpg").exists(), "stale title-A cover survived"
    assert not (movie_dir / f"{old_base}-poster.jpg").exists(), "stale title-A poster survived"
    assert not (movie_dir / f"{old_base}-fanart.jpg").exists(), "stale title-A fanart survived"
    assert (movie_dir / f"{new_base}.nfo").exists()
    assert (movie_dir / f"{new_base}.jpg").exists()
    assert (movie_dir / f"{new_base}-poster.jpg").exists()
    assert (movie_dir / f"{new_base}-fanart.jpg").exists()

    # extrafanart 3→2: shrunk sample must not persist.
    ef_dir = movie_dir / "extrafanart"
    assert not (ef_dir / "fanart3.jpg").exists(), "shrunk extrafanart sample survived"
    assert (ef_dir / "fanart1.jpg").exists()
    assert (ef_dir / "fanart2.jpg").exists()


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
