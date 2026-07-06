"""Unit tests for core.thumbnail_cache (feature/71 T1).

純函式縮圖快取模組測試。覆蓋 TASK-71-T1「邊界條件」全 10 項。
隔離策略：monkeypatch core.thumbnail_cache._thumb_dir → tmp_path，
避免污染真 output/thumb/。
"""
import hashlib
import os
import types

import pytest
from PIL import Image

import core.thumbnail_cache as tc


@pytest.fixture
def thumb_dir(tmp_path, monkeypatch):
    """把 _thumb_dir 導向 tmp_path/thumb，隔離真實 output/。"""
    d = tmp_path / "thumb"
    monkeypatch.setattr(tc, "_thumb_dir", lambda: d)
    return d


def _make_jpg(path, w=1280, h=720, color=(120, 30, 200)):
    """造一張可控尺寸 JPEG 測試圖。"""
    Image.new("RGB", (w, h), color).save(str(path), "JPEG")
    return path


# ── 1. hash 決定性 ──────────────────────────────────────────────
def test_thumb_file_for_deterministic(thumb_dir):
    uri = "file:///mnt/c/movies/ABC-123.mp4"
    p1 = tc.thumb_file_for(uri)
    p2 = tc.thumb_file_for(uri)
    assert p1 == p2


def test_thumb_file_for_distinct_uris_distinct_paths(thumb_dir):
    a = tc.thumb_file_for("file:///x/A.mp4")
    b = tc.thumb_file_for("file:///x/B.mp4")
    assert a != b


# ── 2. 分桶路徑格式 thumb/<h[:2]>/<h>.webp ──────────────────────
def test_thumb_file_for_bucket_format(thumb_dir):
    uri = "file:///mnt/c/movies/ABC-123.mp4"
    h = hashlib.sha1(uri.encode("utf-8")).hexdigest()
    p = tc.thumb_file_for(uri)
    assert p == thumb_dir / h[:2] / f"{h}.webp"
    assert p.parent.name == h[:2]
    assert p.stem == h
    assert p.suffix == ".webp"


# ── 3. generate 產出合法 WEBP 且小於原圖 ────────────────────────
def test_generate_produces_valid_webp_smaller(thumb_dir, tmp_path):
    cover = _make_jpg(tmp_path / "cover.jpg", 1280, 720)
    dst = thumb_dir / "ab" / "abc.webp"
    assert tc.generate(str(cover), dst) is True
    assert dst.exists()
    with Image.open(str(dst)) as img:
        assert img.format == "WEBP"
        assert img.width == tc.THUMB_WIDTH
    assert dst.stat().st_size < cover.stat().st_size


# ── 4. 原圖更窄不放大 ───────────────────────────────────────────
def test_generate_does_not_upscale_narrow_source(thumb_dir, tmp_path):
    cover = _make_jpg(tmp_path / "narrow.jpg", 300, 200)
    dst = thumb_dir / "cd" / "cde.webp"
    assert tc.generate(str(cover), dst) is True
    with Image.open(str(dst)) as img:
        assert img.format == "WEBP"
        assert img.width == 300  # 不放大


# ── 5. 原子寫無殘留 temp 檔 ─────────────────────────────────────
def test_generate_no_temp_leftover(thumb_dir, tmp_path):
    cover = _make_jpg(tmp_path / "cover.jpg")
    dst = thumb_dir / "ef" / "efg.webp"
    assert tc.generate(str(cover), dst) is True
    assert dst.exists()
    assert list(dst.parent.glob("*.tmp")) == []


# ── 6. 損圖 / 讀取失敗 → False（不拋、不留殘檔、dst 不建立） ────
def test_generate_corrupt_image_returns_false(thumb_dir, tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    dst = thumb_dir / "gh" / "ghi.webp"
    assert tc.generate(str(bad), dst) is False
    assert not dst.exists()
    if dst.parent.exists():
        assert list(dst.parent.glob("*.tmp")) == []


def test_generate_missing_source_returns_false(thumb_dir, tmp_path):
    dst = thumb_dir / "ij" / "ijk.webp"
    assert tc.generate(str(tmp_path / "nope.jpg"), dst) is False
    assert not dst.exists()


# ── 7. invalidate ───────────────────────────────────────────────
def test_invalidate_missing_is_noop(thumb_dir):
    # 從未生成過 → 不拋、無副作用
    tc.invalidate("file:///never/generated.mp4")


def test_invalidate_removes_existing(thumb_dir, tmp_path):
    uri = "file:///x/movie.mp4"
    cover = _make_jpg(tmp_path / "cover.jpg")
    tf = tc.thumb_file_for(uri)
    assert tc.generate(str(cover), tf) is True
    assert tf.exists()
    tc.invalidate(uri)
    assert not tf.exists()


# ── 8. clear_all ────────────────────────────────────────────────
def test_clear_all_missing_dir_is_noop(thumb_dir):
    assert not thumb_dir.exists()
    tc.clear_all()  # 不拋


def test_clear_all_removes_everything(thumb_dir, tmp_path):
    cover = _make_jpg(tmp_path / "cover.jpg")
    tf = tc.thumb_file_for("file:///x/a.mp4")
    assert tc.generate(str(cover), tf) is True
    assert thumb_dir.exists()
    tc.clear_all()
    assert not thumb_dir.exists()


# ── 9. get_or_create ────────────────────────────────────────────
def test_get_or_create_miss_then_hit(thumb_dir, tmp_path, monkeypatch):
    uri = "file:///x/movie.mp4"
    cover = _make_jpg(tmp_path / "cover.jpg")

    # miss → 生成
    p1 = tc.get_or_create(uri, str(cover))
    assert p1 is not None
    assert p1.exists()

    # hit → 不重新生成（spy generate）
    calls = []
    orig = tc.generate
    monkeypatch.setattr(tc, "generate", lambda *a, **k: calls.append(1) or orig(*a, **k))
    p2 = tc.get_or_create(uri, str(cover))
    assert p2 == p1
    assert calls == []  # generate 未被呼叫


def test_get_or_create_corrupt_cover_returns_none(thumb_dir, tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    assert tc.get_or_create("file:///x/bad.mp4", str(bad)) is None


# ── 10. iter_missing 跳過已存在 thumb 與無效 cover ──────────────
def test_iter_missing_yields_only_missing_with_valid_cover(thumb_dir, tmp_path):
    cover_a = _make_jpg(tmp_path / "a.jpg")
    cover_c = _make_jpg(tmp_path / "c.jpg")

    uri_a = "file:///x/a.mp4"
    uri_b = "file:///x/b.mp4"
    uri_c = "file:///x/c.mp4"

    # A: 已有 thumb（cover 有效但 thumb 已存在 → 跳過）
    tf_a = tc.thumb_file_for(uri_a)
    assert tc.generate(str(cover_a), tf_a) is True

    # B: 缺 thumb 但 cover 不存在 → 跳過
    # C: 缺 thumb 且 cover 有效 → yield

    def cover_uri(p):
        # 造可被 uri_to_fs_path 還原的 file URI
        return "file://" + str(p) if str(p).startswith("/") else "file:///" + str(p)

    videos = [
        types.SimpleNamespace(path=uri_a, cover_path=cover_uri(cover_a)),
        types.SimpleNamespace(path=uri_b, cover_path=cover_uri(tmp_path / "missing.jpg")),
        types.SimpleNamespace(path=uri_c, cover_path=cover_uri(cover_c)),
    ]

    result = list(tc.iter_missing(videos))
    assert len(result) == 1
    yielded_uri, yielded_cover = result[0]
    assert yielded_uri == uri_c
    assert os.path.exists(yielded_cover)


def test_iter_missing_skips_no_cover(thumb_dir):
    videos = [
        types.SimpleNamespace(path="file:///x/n.mp4", cover_path=None),
        types.SimpleNamespace(path="file:///x/m.mp4"),  # 無 cover_path 屬性
    ]
    assert list(tc.iter_missing(videos)) == []


# ── TASK-91-T2b #15: iter_missing WSL+UNC path_mappings 反解 ──────
def test_iter_missing_reverse_maps_wsl_unc_path_mappings(thumb_dir, tmp_path, monkeypatch):
    """cover_path 為 mapped UNC URI，path_mappings 命中時 yield 出的
    cover_fs_path 應為反解後的本機路徑（真的存在、可 open()），而非裸
    uri_to_fs_path() 產生的映射端 UNC 字串（該路徑在磁碟上不存在）。"""
    import core.path_utils as path_utils

    monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

    nas_dir = tmp_path / "nas"
    nas_dir.mkdir()
    cover = _make_jpg(nas_dir / "cover.jpg")
    mappings = {str(nas_dir): "//NAS/share"}

    uri = "file:///x/wsl_unc.mp4"
    videos = [
        types.SimpleNamespace(path=uri, cover_path="file://///NAS/share/cover.jpg"),
    ]

    result = list(tc.iter_missing(videos, mappings))
    assert len(result) == 1
    yielded_uri, yielded_cover = result[0]
    assert yielded_uri == uri
    assert yielded_cover == str(cover), (
        f"應反解為本機路徑 {cover}，實際 {yielded_cover}"
    )
    assert "//NAS/share" not in yielded_cover


def test_iter_missing_default_none_path_mappings_equivalent_to_before(thumb_dir, tmp_path):
    """#15 邊界：path_mappings 預設 None → 與改動前裸 uri_to_fs_path 呼叫等價
    （保護既有兩個呼叫點 tc.iter_missing(videos) 不用改就能繼續 GREEN）。"""
    cover = _make_jpg(tmp_path / "plain.jpg")
    uri = "file:///x/plain.mp4"
    videos = [types.SimpleNamespace(path=uri, cover_path="file://" + str(cover))]

    result = list(tc.iter_missing(videos))  # 不傳 path_mappings
    assert len(result) == 1
    assert result[0][0] == uri
    assert os.path.exists(result[0][1])


# ── 11. per-thumb 鎖 key 一致性（Codex round-2 P1 修法 A）────────
def test_lock_for_thumb_same_path_same_lock(thumb_dir):
    """同一 video_path_uri → thumb_file_for 回同 Path → str 相同 → 同一把鎖。

    這保證 generate(dst) 與 invalidate(tf) 對同 uri 序列化（關閉原地覆寫競態）。
    """
    uri = "file:///x/movie.mp4"
    tf = tc.thumb_file_for(uri)
    lk1 = tc._lock_for_thumb(tf)
    lk2 = tc._lock_for_thumb(tc.thumb_file_for(uri))
    assert lk1 is lk2


def test_lock_for_thumb_distinct_paths_distinct_locks(thumb_dir):
    """不同 thumb path → 不同鎖（不會誤序列化無關縮圖）。"""
    a = tc.thumb_file_for("file:///x/A.mp4")
    b = tc.thumb_file_for("file:///x/B.mp4")
    assert tc._lock_for_thumb(a) is not tc._lock_for_thumb(b)
