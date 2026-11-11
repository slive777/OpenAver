"""TASK-198a-T2b — 三個入庫點接線＋大小進增量判定（I3／I4／唯讀／換檔／整理）。

整合 harness 行數遠大於產品碼：要驅動真 VideoScanner／fast_scan_directory、
真 tmp DB、真 trigger，並同時覆蓋 scrape-single／auto-organize 兩 sink 的狀態閘。
"""
from __future__ import annotations

import os
import shutil
import types
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult, resolution_tier
from core.media_probe_worker import MediaProbeWorker
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

UHD_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "uhd_hevc.mp4"
T_NS = 1_700_000_000_000_000_000  # 固定奈秒；DB 種子用 os.stat 讀回（BE-ENV-02）
S1_PLACEHOLDER = 9999  # ≠ uhd_hevc.mp4 的 5182


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """形狀照 tests/unit/test_auto_organize.py:23。"""
    db_path = tmp_path / "test_auto_organize.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    return db_path


@pytest.fixture
def stub_inflow(mocker):
    """形狀照 tests/unit/test_auto_organize.py:32。"""
    return mocker.patch("core.auto_organize.try_inflow_upsert", return_value="not_linked")


def _ok_probe(*, width=1920, height=1080, duration_ms=7_200_000) -> ProbeResult:
    """ProbeResult 13 欄全必填；測試檔小工廠，不改 core/media_probe.py。"""
    return ProbeResult(
        status="ok",
        reason="",
        width=width,
        height=height,
        video_format="AVC",
        duration_ms=duration_ms,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=5_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=(),
        truncated=False,
    )


def _no_video_probe() -> ProbeResult:
    return ProbeResult(
        status="no_video",
        reason="no video track",
        width=None,
        height=None,
        video_format=None,
        duration_ms=None,
        hdr_format=None,
        frame_rate=None,
        overall_bitrate=None,
        container=None,
        audio_langs=(),
        subtitle_langs=(),
        truncated=False,
    )


def _copy_uhd(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(UHD_FIXTURE, dest)
    return dest


def _stat_key(path: Path) -> tuple[float, int]:
    st = os.stat(path)
    return st.st_mtime, st.st_size


def _seed_video(repo: VideoRepository, path_uri: str, *, number: str, mtime: float, size: int):
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(
            Video(path=path_uri, number=number, title=number, mtime=mtime, size_bytes=size)
        )


def _gallery_config(scan_dirs, output_dir: Path) -> dict:
    """scan_dirs: list[str | dict]。str → 可寫來源；dict 原樣進 directories。"""
    directories = []
    for d in scan_dirs:
        if isinstance(d, dict):
            directories.append(d)
        else:
            directories.append({"path": str(d), "readonly": False, "output_path": ""})
    return {
        "gallery": {
            "directories": directories,
            "output_dir": str(output_dir),
            "output_filename": "gallery_output.html",
            "path_mappings": {},
            "min_size_mb": 0,
            "default_mode": "image",
            "default_sort": "date",
            "default_order": "descending",
            "items_per_page": 90,
        },
        "general": {"theme": "light"},
        "search": {"proxy_url": ""},
        "scraper": {"video_extensions": [".mp4"], "nfo_title_format": "[{num}]{title}"},
    }


def _run_generate(tmp_db, config, *, patch_iter=True):
    """直呼 generate_avlist；VideoScanner／fast_scan_directory 用真的。"""
    from web.routers.scanner import generate_avlist

    dirs = [d["path"] if isinstance(d, dict) else d for d in config["gallery"]["directories"]]
    writable_dirs = [
        (d["path"] if isinstance(d, dict) else d)
        for d in config["gallery"]["directories"]
        if not (isinstance(d, dict) and d.get("readonly"))
    ]

    stack_patches = [
        patch("web.routers.scanner.load_config", return_value=config),
        patch("web.routers.scanner.get_gallery_source_paths", return_value=dirs),
        patch("web.routers.scanner.get_db_path", return_value=tmp_db),
        patch("web.routers.scanner.HTMLGenerator"),
        patch("web.routers.scanner._run_sample_images_cleanup_pass", return_value=0),
        patch(
            "web.routers.scanner.check_cache_needs_update",
            return_value={"need_update": 0, "paths": [], "items": []},
        ),
        patch("web.routers.scanner._emit_notif"),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
        patch("web.routers.scanner._schedule_ai_incremental"),
        patch("web.routers.scanner.maybe_submit_video_focal"),
    ]
    if patch_iter:
        srcs = [
            types.SimpleNamespace(path=p, readonly=False, output_path="")
            for p in writable_dirs
        ]
        stack_patches.append(
            patch("web.routers.scanner.iter_gallery_sources", return_value=srcs)
        )

    with ExitStack() as stack:
        for p in stack_patches:
            stack.enter_context(p)
        list(generate_avlist())


def _install_submit_spy(
    monkeypatch,
    *,
    forward_worker: MediaProbeWorker | None = None,
    real_submit=None,
):
    """class 層級 spy MediaProbeWorker.submit（BE-TEST-38：不 patch trigger 名）。

    real_submit：真正的 unbound submit。同測多次安裝時必須傳入測試開頭保存的
    原始方法——否則第二次會把第一個 spy 存成 _orig，工作被轉送到上一輪 worker
    （第 ③ 段假綠：forward_nv 佇列空、pending 靠舊 key 不符就過）。
    """
    submitted: list[str] = []
    _orig = real_submit if real_submit is not None else MediaProbeWorker.submit

    def fake(self, path_uri, fs_path, expected_mtime, expected_size, db_path=None):
        submitted.append(path_uri)
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


def _drain(worker: MediaProbeWorker) -> None:
    """_process_one 在佇列空時會永遠阻塞——每次呼叫前確認非空。"""
    while not worker._queue.empty():
        worker._process_one()


# ── I3 ───────────────────────────────────────────────────────────────────────


def test_scan_probes_only_this_rounds_changed_rows(tmp_path, monkeypatch):
    """I3：DB 預存 3 列未變＋新放 1 支 → submit 集合恰為 {新檔}。"""
    scan_dir = tmp_path / "lib"
    scan_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    tmp_db = tmp_path / "i3.db"
    init_db(tmp_db)
    repo = VideoRepository(tmp_db)

    existing_uris = []
    for i in range(3):
        p = _copy_uhd(scan_dir / f"ABC-00{i}.mp4")
        os.utime(p, ns=(T_NS + i, T_NS + i))
        mtime, size = _stat_key(p)
        uri = to_file_uri(str(p))
        _seed_video(repo, uri, number=f"ABC-00{i}", mtime=mtime, size=size)
        existing_uris.append(uri)

    new_p = _copy_uhd(scan_dir / "ABC-999.mp4")
    os.utime(new_p, ns=(T_NS + 99, T_NS + 99))
    new_uri = to_file_uri(str(new_p))

    submitted = _install_submit_spy(monkeypatch)
    config = _gallery_config([scan_dir], output_dir)
    _run_generate(tmp_db, config)

    assert set(submitted) == {new_uri}, f"I3 應只 submit 新檔，實際={submitted}"
    for uri in existing_uris:
        assert uri not in submitted


# ── I4 ───────────────────────────────────────────────────────────────────────


def test_nfo_only_change_does_not_reprobe(tmp_path, monkeypatch):
    """I4：同批 A（已讀、只 nfo_mtime 變）＋ B（mtime 變）→ submit 恰為 {B}。"""
    scan_dir = tmp_path / "lib"
    scan_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    tmp_db = tmp_path / "i4.db"
    init_db(tmp_db)
    repo = VideoRepository(tmp_db)

    # A：已讀、磁碟 mtime/size 之後不變；稍後補 .nfo 讓 nfo_mtime 變
    a_path = _copy_uhd(scan_dir / "ABC-AAA.mp4")
    os.utime(a_path, ns=(T_NS, T_NS))
    a_mtime, a_size = _stat_key(a_path)
    a_uri = to_file_uri(str(a_path))
    _seed_video(repo, a_uri, number="ABC-AAA", mtime=a_mtime, size=a_size)
    assert repo.update_media_probe(a_uri, _ok_probe(), a_mtime, a_size) is True

    # B：未讀；種子後改 mtime（秒級差距，float st_mtime 才分辨得出）
    b_path = _copy_uhd(scan_dir / "ABC-BBB.mp4")
    os.utime(b_path, ns=(T_NS + 1_000_000_000, T_NS + 1_000_000_000))
    b_mtime_old, b_size = _stat_key(b_path)
    b_uri = to_file_uri(str(b_path))
    _seed_video(repo, b_uri, number="ABC-BBB", mtime=b_mtime_old, size=b_size)

    # A 只改 NFO；B 改影片 mtime（+50s）
    (scan_dir / "ABC-AAA.nfo").write_text("<movie/>", encoding="utf-8")
    os.utime(b_path, ns=(T_NS + 50_000_000_000, T_NS + 50_000_000_000))

    submitted = _install_submit_spy(monkeypatch)
    _run_generate(tmp_db, _gallery_config([scan_dir], output_dir))

    assert set(submitted) == {b_uri}, f"I4 應只 submit B，實際={submitted}"
    assert a_uri not in submitted


# ── 唯讀 ─────────────────────────────────────────────────────────────────────


def test_readonly_source_is_not_probed(tmp_path, monkeypatch, mocker):
    """唯讀來源零 submit；可寫來源（正向對照）恰收到那一支。"""
    from core.readonly_producer import ProduceResult

    ro_dir = tmp_path / "ro"
    wr_dir = tmp_path / "wr"
    ro_out = tmp_path / "ro_out"
    output_dir = tmp_path / "out"
    for d in (ro_dir, wr_dir, ro_out, output_dir):
        d.mkdir()

    # 唯讀來源也放一支檔（produce_source 被 mock，不會真入庫；防回歸誤掃）
    _copy_uhd(ro_dir / "ABC-RO.mp4")
    wr_path = _copy_uhd(wr_dir / "ABC-WR.mp4")
    os.utime(wr_path, ns=(T_NS, T_NS))
    wr_uri = to_file_uri(str(wr_path))

    tmp_db = tmp_path / "ro.db"
    init_db(tmp_db)

    config = _gallery_config(
        [
            {"path": str(ro_dir), "readonly": True, "output_path": str(ro_out)},
            {"path": str(wr_dir), "readonly": False, "output_path": ""},
        ],
        output_dir,
    )

    mocker.patch(
        "web.routers.scanner.produce_source",
        return_value=ProduceResult(source_path=str(ro_dir), output_path=str(ro_out)),
    )

    submitted = _install_submit_spy(monkeypatch)
    # 不 patch iter_gallery_sources——兩個來源都要出現
    _run_generate(tmp_db, config, patch_iter=False)

    assert set(submitted) == {wr_uri}, f"唯讀不得被讀，實際={submitted}"


# ── 大小變更 ─────────────────────────────────────────────────────────────────


def test_same_mtime_different_size_is_reprobed(tmp_path, monkeypatch):
    """換檔（mtime 同、大小不同）→ submit 一次、探針換新；no_video → pending 不含該列。"""
    # 測試開頭一次保存真正的 unbound submit——同測會裝兩次 spy，不可把上一輪 spy 當 _orig
    real_submit = MediaProbeWorker.submit

    scan_dir = tmp_path / "lib"
    scan_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def _setup():
        # 清目錄與 DB
        for p in scan_dir.iterdir():
            p.unlink()
        db = tmp_path / "size.db"
        if db.exists():
            db.unlink()
        init_db(db)
        repo = VideoRepository(db)

        disk = _copy_uhd(scan_dir / "ABC-123.mp4")
        os.utime(disk, ns=(T_NS, T_NS))
        t, s2 = _stat_key(disk)
        assert s2 != S1_PLACEHOLDER
        uri = to_file_uri(str(disk))

        # DB key=(T,S1)；磁碟已是 (T,S2)
        _seed_video(repo, uri, number="ABC-123", mtime=t, size=S1_PLACEHOLDER)
        assert (
            repo.update_media_probe(
                uri, _ok_probe(width=1920, height=1080, duration_ms=7_200_000), t, S1_PLACEHOLDER
            )
            is True
        )
        return db, repo, uri, t, s2

    # ①② 真探針
    forward = MediaProbeWorker(auto_start=False)
    submitted = _install_submit_spy(
        monkeypatch, forward_worker=forward, real_submit=real_submit
    )
    tmp_db, repo, uri, t, s2 = _setup()
    _run_generate(tmp_db, _gallery_config([scan_dir], output_dir))
    assert submitted.count(uri) == 1, f"① 應 submit 恰一次，實際={submitted}"
    _drain(forward)

    view = repo.get_media_probe_view(uri)
    assert view is not None
    assert view.media_height == 2160
    assert resolution_tier(view.media_width, view.media_height) == "4K"
    assert view.media_duration_ms == 1000
    assert (view.media_probe_mtime, view.media_probe_size) == (t, s2)

    # ③ 同情境、假探針回 no_video → 必須真進 forward_nv 再寫 failed，再斷 pending 不含
    nv_calls = {"n": 0}

    def _counting_no_video(_path):
        nv_calls["n"] += 1
        return _no_video_probe()

    forward_nv = MediaProbeWorker(probe_fn=_counting_no_video, auto_start=False)
    submitted_nv = _install_submit_spy(
        monkeypatch, forward_worker=forward_nv, real_submit=real_submit
    )
    tmp_db2, repo2, uri2, t2, s2b = _setup()
    _run_generate(tmp_db2, _gallery_config([scan_dir], output_dir))
    assert submitted_nv.count(uri2) == 1
    _drain(forward_nv)

    assert nv_calls["n"] == 1, f"③ 假探針應被呼叫恰 1 次，實際={nv_calls['n']}"
    view_nv = repo2.get_media_probe_view(uri2)
    assert view_nv is not None
    assert view_nv.media_probe_status == "failed"
    assert (view_nv.media_probe_mtime, view_nv.media_probe_size) == (t2, s2b)

    gallery = {
        "directories": [{"path": str(scan_dir), "readonly": False, "output_path": ""}],
        "path_mappings": {},
    }
    from core.config import get_configured_gallery_dirs
    from core.readonly_source import readonly_source_prefixes, writable_source_prefixes

    configured, _mappings = get_configured_gallery_dirs({"gallery": gallery})
    assert view_nv.key_matches is True
    pending = repo2.list_media_probe_pending(
        include_readonly=False,
        readonly_prefixes=readonly_source_prefixes(gallery, {}),
        writable_prefixes=writable_source_prefixes(gallery, {}),
        configured_dir_uris=configured,
    )
    pending_paths = {p for p, _m, _s in pending}
    assert uri2 not in pending_paths, f"③ no_video 後 key 相符不應在 pending，實際={pending}"


# ── scrape-single ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sync_status, expect_submit",
    [("synced", True), ("not_linked", False)],
)
def test_scrape_single_submits_media_probe_when_synced(
    client, tmp_path, monkeypatch, sync_status, expect_submit
):
    """整理入庫（搜尋頁）：synced → spy 恰一次；非 synced → 零。"""
    db_path = tmp_path / "scrape_probe.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

    target = str(tmp_path / "lib" / "ABC-001" / "ABC-001.mp4")
    path_mappings: dict = {}
    expected_uri = to_file_uri(target, path_mappings)

    with (
        patch(
            "web.routers.scraper.organize_file",
            return_value={
                "success": True,
                "new_filename": target,
                "new_folder": str(tmp_path / "lib" / "ABC-001"),
                "original_path": "/tmp/ABC-001.mp4",
                "cover_path": "",
            },
        ),
        patch("web.routers.scraper.try_inflow_upsert", return_value=sync_status),
        patch("web.routers.scraper.maybe_submit_video_focal"),
        patch("web.routers.scraper._post_ingest_after_scrape"),
        patch("web.routers.scraper.maybe_submit_media_probe") as spy,
        patch(
            "web.routers.scraper.load_config",
            return_value={
                "gallery": {"directories": [str(tmp_path / "lib")], "path_mappings": {}},
                "scraper": {},
            },
        ),
        patch("web.routers.scraper._readonly_source_error", return_value=None),
    ):
        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/tmp/ABC-001.mp4",
                "number": "ABC-001",
                "metadata": {"title": "T", "number": "ABC-001", "cover": "", "actresses": [], "tags": [], "release": ""},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    if expect_submit:
        spy.assert_called_once()
        assert spy.call_args.args[0] == expected_uri
    else:
        spy.assert_not_called()


# ── auto-organize ────────────────────────────────────────────────────────────


def _ao_make_config(fav_dir):
    return {
        "search": {"favorite_folder": str(fav_dir)},
        "scraper": {"video_extensions": [".mp4"]},
        "gallery": {
            "min_size_mb": 0,
            "path_mappings": {},
            "directories": [],
        },
        "translate": {"enabled": False},
    }


@pytest.mark.parametrize(
    "sync_status, expect_submit",
    [("synced", True), ("not_linked", False)],
)
def test_auto_organize_submits_media_probe_when_synced(
    tmp_path, isolated_db, mocker, stub_inflow, sync_status, expect_submit
):
    """定時整理：synced → 恰一次且帶 prefixes；not_linked → 零。"""
    from core.auto_organize import run_one_round

    fav = tmp_path / "fav"
    fav.mkdir()
    (fav / "ABC-123.mp4").write_bytes(b"x" * 1024)
    config = _ao_make_config(fav)
    target = str(tmp_path / "lib" / "ABC-123" / "ABC-123.mp4")
    expected_uri = to_file_uri(target, {})

    stub_inflow.return_value = sync_status
    mocker.patch(
        "core.auto_organize.smart_search",
        return_value=[{"number": "ABC-123", "title": "T"}],
    )
    mocker.patch(
        "core.auto_organize.organize_file",
        return_value={
            "success": True,
            "original_path": None,
            "new_folder": str(tmp_path / "lib" / "ABC-123"),
            "new_filename": target,
            "cover_path": "/cover/x.jpg",
            "nfo_path": str(tmp_path / "lib" / "ABC-123" / "ABC-123.nfo"),
            "error": None,
            "used_fallbacks": [],
        },
    )
    mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])
    mocker.patch("core.auto_organize.post_ingest.run_after_ingest")
    spy = mocker.patch("core.auto_organize.maybe_submit_media_probe")

    result = run_one_round(config)
    assert result.get("folder_not_configured") is not True

    if expect_submit:
        spy.assert_called_once()
        assert spy.call_args.args[0] == expected_uri
        assert "readonly_prefixes" in spy.call_args.kwargs
        assert "writable_prefixes" in spy.call_args.kwargs
    else:
        spy.assert_not_called()
