"""TASK-a205-T2 — 唯讀來源入庫也讀（開關 opt-in）＋唯讀資料夾零寫入。

I-P1（test_trigger_readonly_follows_switch）：開關 off×唯讀→0、on×唯讀→1、
off×可寫→1（開關不得影響可寫列）。
I-P2（test_readonly_ingest_probes_only_new_rows）：兩輪 produce_source，第二輪
submit 集合恰為新列（既有幾千部未讀唯讀列不被一次排進去）。
I-P3（test_readonly_ingest_zero_writes_to_source）：來源資料夾快照前後相等
（含資料夾自己）＋ worker 確實把新列讀成 ok（防空轉）。

唯讀列走 stub 路徑（檔名抽不出番號、旁邊無 NFO／封面）與本地 NFO sidecar
路徑（檔名即番號、旁邊有本地 NFO）；探針用自己的
probe_fn，不讓 produce_source 走到 search_jav。
"""
from __future__ import annotations

import os
import stat
import types

import pytest

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.media_probe_worker import MediaProbeWorker
from core.path_utils import to_file_uri


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """形狀照 tests/integration/test_media_probe_ingest.py 的同名 fixture。

    開關存 app_meta（預設 DB），測試必須先把預設 DB 指向這顆 tmp DB 再碰開關，
    否則 G1 擋（打到真實 output/openaver.db）；teardown 先歸 off 再還原 patch。
    """
    import core.media_probe_backfill as backfill

    db_path = tmp_path / "ro_probe.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    backfill.set_include_readonly(False)
    yield db_path
    backfill.set_include_readonly(False)


def _install_submit_spy(monkeypatch, *, forward_worker=None, real_submit=None):
    """class 層 spy MediaProbeWorker.submit（BE-TEST-66：保存原始 unbound）。

    同測多次安裝時 real_submit 傳測試開頭保存的原始方法（BE-TEST-38 形狀），
    否則第二次會把第一個 spy 存成 _orig，工作被轉送到上一輪 worker。
    """
    submitted = []
    _orig = real_submit if real_submit is not None else MediaProbeWorker.submit

    def fake(self, path_uri, fs_path, expected_mtime, expected_size, db_path=None):
        submitted.append((path_uri, fs_path, expected_mtime, expected_size, db_path))
        if forward_worker is not None:
            _orig(
                forward_worker,
                path_uri,
                fs_path,
                expected_mtime,
                expected_size,
                db_path=db_path,
            )

    monkeypatch.setattr(MediaProbeWorker, "submit", fake)
    return submitted


def _ok_probe() -> ProbeResult:
    return ProbeResult(
        status="ok",
        reason="",
        width=1920,
        height=1080,
        video_format="AVC",
        duration_ms=7_200_000,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=5_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=(),
        truncated=False,
    )


def _write_clip(path):
    path.write_bytes(b"x" * 512)


def _ro_config(ro_dir, out_dir):
    return {
        "gallery": {
            "directories": [
                {"path": str(ro_dir), "readonly": True, "output_path": str(out_dir)}
            ],
            "path_mappings": {},
            "min_size_mb": 0,
        },
        "scraper": {"video_extensions": [".mp4"]},
    }


def _ro_source(ro_dir, out_dir):
    return types.SimpleNamespace(
        path=str(ro_dir), readonly=True, output_path=str(out_dir)
    )


# ── I-P1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "switch_on, subdir, expect_count",
    [
        (False, "ro", 0),
        (True, "ro", 1),
        (False, "rw", 1),
    ],
)
def test_trigger_readonly_follows_switch(
    tmp_path, monkeypatch, isolated_db, switch_on, subdir, expect_count
):
    """I-P1：off×唯讀→0、on×唯讀→1、off×可寫→1。"""
    import core.media_probe_backfill as backfill
    import core.media_probe_trigger as trigger

    ro_dir = tmp_path / "ro"
    wr_dir = tmp_path / "rw"
    ro_dir.mkdir()
    wr_dir.mkdir()
    target_dir = ro_dir if subdir == "ro" else wr_dir
    target = target_dir / "plain-clip-a.mp4"
    _write_clip(target)
    target_uri = to_file_uri(str(target))

    repo = VideoRepository(isolated_db)
    repo.upsert(Video(path=target_uri, title="片", mtime=1.0, size_bytes=512))

    backfill.set_include_readonly(switch_on)
    assert backfill.get_include_readonly() is switch_on

    submitted = _install_submit_spy(monkeypatch)
    trigger.maybe_submit_media_probe(
        target_uri,
        db_path=isolated_db,
        readonly_prefixes=[to_file_uri(str(ro_dir))],
        writable_prefixes=[to_file_uri(str(wr_dir))],
        path_mappings={},
    )
    assert len(submitted) == expect_count


# ── I-P2 ─────────────────────────────────────────────────────────────────────


def test_readonly_ingest_probes_only_new_rows(tmp_path, monkeypatch, isolated_db):
    """I-P2：開關 off 跑一次（M 部 stub，零 submit）→ 開關 on＋1 stub 新檔＋1
    本地 NFO 新檔（走 _produce_one 成功路徑）→ 第二輪 submit 集合恰為這兩列
    （≠ 全部未讀列）。"""
    import core.media_probe_backfill as backfill
    from core.readonly_producer import extract_number, produce_source

    ro_dir = tmp_path / "ro-src"
    out_dir = tmp_path / "ro-out"
    ro_dir.mkdir()
    out_dir.mkdir()

    first = [ro_dir / "plain-clip-a.mp4", ro_dir / "plain-clip-b.mp4"]
    for p in first:
        _write_clip(p)
    assert extract_number("plain-clip-a.mp4") is None
    assert extract_number("plain-clip-b.mp4") is None

    monkeypatch.setattr("core.readonly_producer.maybe_submit_video_focal", lambda *a, **k: None)
    submitted = _install_submit_spy(monkeypatch)
    repo = VideoRepository(isolated_db)
    source = _ro_source(ro_dir, out_dir)

    result1 = produce_source(source, _ro_config(ro_dir, out_dir), repo)
    assert result1.no_scrape == 2
    assert len(submitted) == 0

    backfill.set_include_readonly(True)
    assert backfill.get_include_readonly() is True
    new_clip = ro_dir / "plain-clip-c.mp4"
    _write_clip(new_clip)
    assert extract_number("plain-clip-c.mp4") is None
    new_uri = to_file_uri(str(new_clip))

    nfo_clip = ro_dir / "ABC-123.mp4"
    _write_clip(nfo_clip)
    (ro_dir / "ABC-123.nfo").write_text(
        '<?xml version="1.0"?><movie><title>t</title><num>ABC-123</num><id>ABC-123</id></movie>',
        encoding="utf-8",
    )
    assert extract_number("ABC-123.mp4") == "ABC-123"
    nfo_uri = to_file_uri(str(nfo_clip))

    produce_source(source, _ro_config(ro_dir, out_dir), repo)
    assert {rec[0] for rec in submitted} == {new_uri, nfo_uri}


# ── I-P3 ─────────────────────────────────────────────────────────────────────


def _snapshot(root) -> set:
    """來源資料夾全集合（含自己）：(relpath, 型別, size, mtime_ns)，用 lstat。"""
    out = set()
    st = os.lstat(root)
    out.add((".", "dir", st.st_size, st.st_mtime_ns))
    for base, dirs, files in os.walk(root):
        for d in dirs:
            p = os.path.join(base, d)
            s = os.lstat(p)
            kind = "dir" if stat.S_ISDIR(s.st_mode) else "file"
            out.add((os.path.relpath(p, root), kind, s.st_size, s.st_mtime_ns))
        for f in files:
            p = os.path.join(base, f)
            s = os.lstat(p)
            kind = "dir" if stat.S_ISDIR(s.st_mode) else "file"
            out.add((os.path.relpath(p, root), kind, s.st_size, s.st_mtime_ns))
    return out


def test_readonly_ingest_zero_writes_to_source(tmp_path, monkeypatch, isolated_db):
    """I-P3：開關 on，入庫＋worker 處理後來源快照前後相等、無新增，且新列確實 ok。"""
    import core.media_probe_backfill as backfill
    from core.readonly_producer import extract_number, produce_source

    ro_dir = tmp_path / "ro-src"
    out_dir = tmp_path / "ro-out"
    ro_dir.mkdir()
    out_dir.mkdir()

    clip = ro_dir / "plain-clip-a.mp4"
    _write_clip(clip)
    assert extract_number("plain-clip-a.mp4") is None
    clip_uri = to_file_uri(str(clip))

    backfill.set_include_readonly(True)
    assert backfill.get_include_readonly() is True

    monkeypatch.setattr("core.readonly_producer.maybe_submit_video_focal", lambda *a, **k: None)
    real_submit = MediaProbeWorker.submit
    worker = MediaProbeWorker(probe_fn=lambda _path: _ok_probe(), auto_start=False)
    submitted = _install_submit_spy(monkeypatch, forward_worker=worker, real_submit=real_submit)
    repo = VideoRepository(isolated_db)

    before = _snapshot(str(ro_dir))
    produce_source(_ro_source(ro_dir, out_dir), _ro_config(ro_dir, out_dir), repo)
    assert [rec[0] for rec in submitted] == [clip_uri]

    assert not worker._queue.empty()
    while not worker._queue.empty():
        worker._process_one()

    view = repo.get_media_probe_view(clip_uri)
    assert view is not None
    assert view.media_probe_status == "ok"

    after = _snapshot(str(ro_dir))
    assert after == before
