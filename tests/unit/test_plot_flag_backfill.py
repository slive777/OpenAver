"""has_plot 回填 pass + update_plot_flag（187b-T2b）— 真 sqlite＋真 NFO。"""
from pathlib import Path

from core.database import Video, VideoRepository, get_connection
from core.database.version_tracker import get_showcase_revision
from core.path_utils import to_file_uri
from core.plot_nfo import read_plot_flag as _real_read

OLD_STAMP = "2000-01-01 00:00:00"
_WITH = "<?xml version='1.0'?><movie><title>t</title><plot>有</plot></movie>"
_WITHOUT = "<?xml version='1.0'?><movie><title>t</title><plot></plot></movie>"


def _row(repo, path):
    conn = get_connection(repo.db_path)
    try:
        cur = conn.execute("SELECT * FROM videos WHERE path = ?", (path,))
        cols = [c[0] for c in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row, strict=True)) if row else None
    finally:
        conn.close()


def _raw(repo, sql, params=()):
    conn = get_connection(repo.db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _seed(repo, path, *, nfo_mtime=100.0, output_dir=""):
    repo.upsert(Video(path=path, number="P-1", title="t",
                      nfo_mtime=nfo_mtime, output_dir=output_dir))
    _raw(repo, "UPDATE videos SET updated_at = ? WHERE path = ?", (OLD_STAMP, path))


def _nfo(path: Path, body: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_backfill_pass_states(temp_db, tmp_path, monkeypatch):
    from core.plot_flag_backfill import run_plot_flag_backfill_pass

    lib, src = tmp_path / "lib", tmp_path / "ro_src"
    lib.mkdir(); src.mkdir()
    reads = []
    monkeypatch.setattr(
        "core.plot_flag_backfill.read_plot_flag",
        lambda p: reads.append(str(p)) or _real_read(p),
    )
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: temp_db)

    def mp4(dir_, name, body=None, as_dir=False):
        f = dir_ / f"{name}.mp4"; f.write_bytes(b"v")
        n = f.with_suffix(".nfo")
        if as_dir:
            n.mkdir()
        elif body is not None:
            _nfo(n, body)
        return to_file_uri(str(f))

    uri_yes = mp4(lib, "YES", _WITH)
    uri_no = mp4(lib, "NO", _WITHOUT)
    uri_bad = mp4(lib, "BAD", as_dir=True)
    assert _real_read(lib / "BAD.nfo") is None
    uri_zero = mp4(lib, "ZERO", _WITH)
    # 唯讀：來源旁無 plot、輸出夾有（相反）→ 以輸出夾為準
    uri_ro = mp4(src, "RO", _WITHOUT)
    out = tmp_path / "ro_out" / "RO"; _nfo(out / "RO.nfo", _WITH)
    # 多候選
    uri_amb = mp4(src, "AMB")
    amb = tmp_path / "ro_out" / "AMB"
    _nfo(amb / "AMB.nfo", _WITH); _nfo(amb / "extra.nfo", _WITH)

    repo = VideoRepository(temp_db)
    _seed(repo, uri_yes); _seed(repo, uri_no); _seed(repo, uri_bad)
    _seed(repo, uri_zero, nfo_mtime=0.0)
    _seed(repo, uri_ro, output_dir=to_file_uri(str(out)))
    _seed(repo, uri_amb, output_dir=to_file_uri(str(amb)))
    for u in (uri_yes, uri_no, uri_bad, uri_zero, uri_ro, uri_amb):
        assert _row(repo, u)["has_plot"] is None

    config = {
        "gallery": {"directories": [
            str(lib),
            {"path": str(src), "readonly": True, "output_path": str(tmp_path / "ro_out")},
        ], "path_mappings": {}},
        "scraper": {"external_manager": "jellyfin"},
    }
    before = _row(repo, uri_yes)
    assert run_plot_flag_backfill_pass(repo, config, {}) == 3
    assert _row(repo, uri_yes)["has_plot"] == 1
    assert _row(repo, uri_no)["has_plot"] == 0
    assert _row(repo, uri_ro)["has_plot"] == 1
    assert _row(repo, uri_bad)["has_plot"] is None
    assert _row(repo, uri_amb)["has_plot"] is None
    assert _row(repo, uri_zero)["has_plot"] is None
    after = _row(repo, uri_yes)
    keep = set(before) - {"has_plot"}
    assert {k: before[k] for k in keep} == {k: after[k] for k in keep}
    assert after["updated_at"] == OLD_STAMP and after["nfo_mtime"] == 100.0
    assert not any("ZERO.nfo" in r for r in reads)
    # 冪等：移走仍 NULL 的候選後，已確認列不再讀
    _raw(repo, "DELETE FROM videos WHERE path IN (?, ?, ?)",
         (uri_bad, uri_amb, uri_zero))
    reads.clear()
    assert run_plot_flag_backfill_pass(repo, config, {}) == 0
    assert reads == []


def test_revision_bump_and_update_plot_flag(temp_db, tmp_path, monkeypatch):
    from core.plot_flag_backfill import run_plot_flag_backfill_pass

    lib = tmp_path / "lib"; lib.mkdir()
    p = lib / "REV.mp4"; p.write_bytes(b"v")
    _nfo(p.with_suffix(".nfo"), _WITH)
    uri = to_file_uri(str(p))
    repo = VideoRepository(temp_db)
    _seed(repo, uri)
    config = {"gallery": {"directories": [str(lib)], "path_mappings": {}}, "scraper": {}}
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: temp_db)

    before_rev = get_showcase_revision()
    assert run_plot_flag_backfill_pass(repo, config, {}) == 1
    assert get_showcase_revision() > before_rev

    before = _row(repo, uri)
    assert repo.update_plot_flag(uri, True, 999.0) is True
    after = _row(repo, uri)
    assert after["has_plot"] == 1 and after["nfo_mtime"] == 999.0
    keep = set(before) - {"has_plot", "nfo_mtime"}
    assert {k: before[k] for k in keep} == {k: after[k] for k in keep}
    assert after["updated_at"] == OLD_STAMP
    assert repo.update_plot_flag(to_file_uri(str(lib / "MISSING.mp4")), True, 1.0) is False
