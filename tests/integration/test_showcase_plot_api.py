"""test_showcase_plot_api.py — GET/POST /api/showcase/video/plot（TASK-187b-T4）

真 sqlite（tmp_db）＋真檔案系統（tmp_path NFO）＋TestClient；只 mock 注入失敗。
環境準備沿用 test_title_writeback_api 的形狀（_wire 改 patch showcase_plot）。
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri

import test_readonly_offflavor_e2e as _e2e
import test_title_writeback_api as _title

JP_PLOT = "日本語の劇情\n第二行 & 記号"
ZH_PLOT = "翻譯後的中文簡介 & 符號"
ZH_PLOT_WS = "翻譯後的中文簡介\n& 符號"  # 與 ZH_PLOT 只差空白／換行（正規化後相同）

_SEED_NFO = f"""<?xml version='1.0' encoding='utf-8'?>
<movie>
  <title>[ABC-123]タイトル</title>
  <originaltitle></originaltitle>
  <num>ABC-123</num>
  <plot>{JP_PLOT}</plot>
  <rating>7.5</rating>
  <website>https://example.invalid/a&amp;b=1</website>
  <actor><name>女優A</name></actor>
  <actor><name>女優B</name></actor>
</movie>
"""


def _wire(monkeypatch, tmp_db, config):
    """兩處 patch 缺一不可（BE-TEST-41）＋唯讀判定的預設輸出根。"""
    monkeypatch.setattr("web.routers.showcase_plot.get_db_path", lambda: tmp_db)
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: tmp_db)
    monkeypatch.setattr("web.routers.showcase_plot.load_config", lambda: config)
    from web.app import app
    return TestClient(app)


def _video(uri, **kw):
    base = dict(
        path=uri, number="ABC-123", title="タイトル", original_title="",
        actresses=["女優A"], maker="Mk", release_date="2024-03-05",
        nfo_mtime=1.0, size_bytes=10, has_plot=True,
    )
    base.update(kw)
    return Video(**base)


def _plain_env(monkeypatch, tmp_db, tmp_path, *, nfo_text=_SEED_NFO, **video_kw):
    lib = tmp_path / "lib"
    lib.mkdir(exist_ok=True)
    mp4 = lib / "ABC-123.mp4"
    mp4.write_bytes(b"fake-video")
    nfo = lib / "ABC-123.nfo"
    nfo.write_text(nfo_text, encoding="utf-8")
    os.utime(nfo, (1_000_000, 1_000_000))
    uri = to_file_uri(str(mp4))
    repo = VideoRepository(tmp_db)
    repo.upsert(_video(uri, **video_kw))
    return _wire(monkeypatch, tmp_db, _title._plain_config(lib)), repo, uri, nfo


@pytest.fixture
def tmp_db(tmp_path):
    db = tmp_path / "plot_wb.db"
    init_db(db)
    return db


def _snap(root):
    return _e2e._snapshot(root)


def _get(client, uri):
    return client.get("/api/showcase/video/plot", params={"file_path": uri})


def _post(client, uri, plot, **extra):
    body = {"file_path": uri, "plot": plot}
    body.update(extra)
    return client.post("/api/showcase/video/plot", json=body)


def _nfo_texts(nfo: Path) -> dict:
    root = ET.fromstring(nfo.read_bytes())
    return {c.tag: (c.text or "") for c in root}


def _row_plot(repo, uri):
    r = repo.get_by_path(uri)
    return (r.has_plot, r.nfo_mtime)


# ── (b) GET＋POST 往返＋unchanged 零寫入 ──────────────────────────────────────

def test_plot_roundtrip_and_unchanged_zero_write(monkeypatch, tmp_db, tmp_path):
    client, repo, uri, nfo = _plain_env(monkeypatch, tmp_db, tmp_path)

    # GET：保留內部換行、無 originalplot
    got = _get(client, uri).json()
    assert got["success"] is True
    assert got["plot"] == JP_PLOT
    assert got["original_plot"] == "" and got["has_original"] is False
    assert "\n" in got["plot"]

    # 首次翻譯
    data = _post(client, uri, ZH_PLOT).json()
    assert data["success"] is True and data["unchanged"] is False
    assert data["plot"] == ZH_PLOT
    assert data["original_plot"] == JP_PLOT and data["has_original"] is True
    texts = _nfo_texts(nfo)
    assert texts["plot"] == ZH_PLOT and texts["originalplot"] == JP_PLOT
    # 無雙重 escape
    assert "&amp;amp;" not in nfo.read_text(encoding="utf-8")
    row = repo.get_by_path(uri)
    assert row.has_plot in (True, 1) or row.has_plot == 1
    assert row.nfo_mtime == nfo.stat().st_mtime

    # GET 往返：送入的 & 原樣回來
    got2 = _get(client, uri).json()
    assert got2["plot"] == ZH_PLOT and got2["original_plot"] == JP_PLOT

    # unchanged：譯文只差空白／換行 → 零寫入（NFO bytes／mtime_ns／DB nfo_mtime）
    before_bytes = nfo.read_bytes()
    before_mtime_ns = nfo.stat().st_mtime_ns
    before_db = _row_plot(repo, uri)
    data = _post(client, uri, ZH_PLOT_WS).json()
    assert data["success"] is True and data["unchanged"] is True
    assert nfo.read_bytes() == before_bytes
    assert nfo.stat().st_mtime_ns == before_mtime_ns
    assert _row_plot(repo, uri) == before_db

    # 復原：original_plot:"" → 元素消失
    data = _post(client, uri, JP_PLOT, original_plot="").json()
    assert data["success"] is True and data["unchanged"] is False
    assert data["original_plot"] == "" and data["has_original"] is False
    assert "originalplot" not in _nfo_texts(nfo)
    assert _nfo_texts(nfo)["plot"] == JP_PLOT


# ── (c) 唯讀來源：只寫輸出夾 ─────────────────────────────────────────────────

def test_readonly_writes_output_nfo_only(monkeypatch, tmp_db, tmp_path):
    # setup 兩份都是 _SEED_NFO；改寫來源旁那份，讓 mutation 3 能轉紅
    client, repo, src, out, uri = _title.setup_readonly_title_env(
        tmp_db, tmp_path, monkeypatch,
    )
    # 重新 wire 到 showcase_plot（title helper 的 _wire patch 的是 showcase）
    config = {
        "gallery": {"directories": [{"path": str(src), "readonly": True,
                                     "output_path": str(tmp_path / "ro_out")}],
                    "path_mappings": {}},
        "scraper": {"external_manager": "jellyfin"},
    }
    client = _wire(monkeypatch, tmp_db, config)

    src_nfo = src / "ABC-123.nfo"
    out_nfo = out / "ABC-123.nfo"
    # 來源旁 plot 與輸出夾不同（陷阱：兩份同內容會讓 mutation 3 恆綠）
    src_nfo.write_text(
        _SEED_NFO.replace(JP_PLOT, "來源旁獨有的簡介"),
        encoding="utf-8",
    )
    assert _nfo_texts(src_nfo)["plot"] != _nfo_texts(out_nfo)["plot"]

    out_plot_before = _nfo_texts(out_nfo)["plot"]
    before = _snap(src)
    data = _post(client, uri, ZH_PLOT).json()
    assert data["success"] is True
    assert _snap(src) == before
    assert _nfo_texts(out_nfo)["plot"] == ZH_PLOT
    assert _nfo_texts(out_nfo)["originalplot"] == out_plot_before
    assert _nfo_texts(src_nfo)["plot"] == "來源旁獨有的簡介"


# ── (d) 錯誤碼表驅動 ─────────────────────────────────────────────────────────

def test_error_codes_and_db_untouched(monkeypatch, tmp_db, tmp_path):
    client, repo, uri, nfo = _plain_env(monkeypatch, tmp_db, tmp_path)

    def _assert_fail(resp, code, *, check_repo=None, check_uri=None,
                     db_before=None, nfo_before=None):
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False and data["error"] == code
        if db_before is not None:
            assert _row_plot(check_repo or repo, check_uri or uri) == db_before
        if nfo_before is not None:
            assert nfo.read_bytes() == nfo_before

    # not_found：片不在 DB
    ghost = to_file_uri(str(tmp_path / "lib" / "GHOST.mp4"))
    _assert_fail(_post(client, ghost, ZH_PLOT), "not_found")
    _assert_fail(_get(client, ghost), "not_found")

    # no_nfo：一般來源 NFO 不存在
    nfo.unlink()
    _assert_fail(_post(client, uri, ZH_PLOT), "no_nfo")
    _assert_fail(_get(client, uri), "no_nfo")
    nfo.write_text(_SEED_NFO, encoding="utf-8")
    os.utime(nfo, (1_000_000, 1_000_000))

    # plot_empty：請求空白 plot
    before_db, before_nfo = _row_plot(repo, uri), nfo.read_bytes()
    _assert_fail(_post(client, uri, "   "), "plot_empty",
                 db_before=before_db, nfo_before=before_nfo)

    # plot_empty：NFO 無／空 <plot>
    empty_plot = _SEED_NFO.replace(f"<plot>{JP_PLOT}</plot>", "<plot></plot>")
    nfo.write_text(empty_plot, encoding="utf-8")
    _assert_fail(_get(client, uri), "plot_empty")
    nfo.write_text(_SEED_NFO, encoding="utf-8")
    os.utime(nfo, (1_000_000, 1_000_000))

    # nfo_write_failed：注入失敗 → DB 不動（須在改 load_config 的唯讀案例前）
    before_db, before_nfo = _row_plot(repo, uri), nfo.read_bytes()
    real = Path.write_bytes

    def guarded(self, data):
        if Path(self) == nfo:
            raise PermissionError("denied")
        return real(self, data)

    monkeypatch.setattr(Path, "write_bytes", guarded)
    _assert_fail(_post(client, uri, ZH_PLOT), "nfo_write_failed",
                 db_before=before_db, nfo_before=before_nfo)
    monkeypatch.setattr(Path, "write_bytes", real)

    # db_write_failed：update_plot_flag 拋例外
    def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(VideoRepository, "update_plot_flag", boom)
    data = _post(client, uri, ZH_PLOT).json()
    assert data["success"] is False and data["error"] == "db_write_failed"

    # nfo_ambiguous：唯讀輸出夾兩份（最後做，避免覆寫 load_config）
    amb_root = tmp_path / "amb"
    amb_root.mkdir()
    _c2, repo2, src, _out, uri2 = _title.setup_readonly_title_env(
        tmp_db, amb_root, monkeypatch, output_nfos=2,
    )
    config = {
        "gallery": {"directories": [{"path": str(src), "readonly": True,
                                     "output_path": str(amb_root / "ro_out")}],
                    "path_mappings": {}},
        "scraper": {"external_manager": "jellyfin"},
    }
    c2 = _wire(monkeypatch, tmp_db, config)
    before2 = _row_plot(repo2, uri2)
    resp = _post(c2, uri2, ZH_PLOT)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False and data["error"] == "nfo_ambiguous"
    assert _row_plot(repo2, uri2) == before2
