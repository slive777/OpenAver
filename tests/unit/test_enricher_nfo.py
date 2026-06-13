"""63c-5: enricher summary/rating crossing — _scraper_to_meta / _merge_meta / _write_nfo（CD-63c-5）。"""
from unittest.mock import patch

from core.enricher import _scraper_to_meta, _merge_meta, _write_nfo


# ─── _scraper_to_meta crossing point（_ 前綴 → canonical）───

def test_scraper_to_meta_crosses_summary_rating():
    meta = _scraper_to_meta({"_summary": "plot text", "_rating": 3.5, "title": "T"})
    assert meta["summary"] == "plot text"
    assert meta["rating"] == 3.5
    # crossing 後不再有 _ 前綴鍵
    assert "_summary" not in meta
    assert "_rating" not in meta


def test_scraper_to_meta_defaults_no_metatube():
    meta = _scraper_to_meta({})
    assert meta["summary"] == ""
    assert meta["rating"] is None


# ─── _merge_meta 透傳 ───

def test_merge_meta_carries_summary_rating_from_supplement():
    base = {"title": "T"}  # DB/NFO base 無 summary
    supplement = _scraper_to_meta({"_summary": "plot", "_rating": 4.0})
    merged, _ = _merge_meta(base, supplement)
    assert merged["summary"] == "plot"
    assert merged["rating"] == 4.0


def test_merge_meta_base_summary_not_overwritten():
    base = {"summary": "kept", "rating": 2.0}
    supplement = {"summary": "new", "rating": 5.0}
    merged, _ = _merge_meta(base, supplement)
    assert merged["summary"] == "kept"  # fill-if-empty：base 有值不覆蓋
    assert merged["rating"] == 2.0


# ─── _write_nfo 讀 canonical key 傳 generate_nfo ───

def test_write_nfo_passes_canonical_summary_rating(tmp_path):
    fs_path = str(tmp_path / "vid.mp4")
    meta = {"summary": "plot text", "rating": 3.5, "title": "T"}
    with patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(fs_path, "ABC-123", meta, write_nfo=True,
                   overwrite_existing=True, has_subtitle=False, user_tags=[])
    _, kwargs = mock_gen.call_args
    assert kwargs["summary"] == "plot text"
    assert kwargs["rating"] == 3.5


def test_write_nfo_builtin_defaults(tmp_path):
    """builtin meta（無 summary/rating 鍵）→ generate_nfo(summary='', rating=None)。"""
    fs_path = str(tmp_path / "vid.mp4")
    meta = {"title": "T"}
    with patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(fs_path, "ABC-123", meta, write_nfo=True,
                   overwrite_existing=True, has_subtitle=False, user_tags=[])
    _, kwargs = mock_gen.call_args
    assert kwargs["summary"] == ""
    assert kwargs["rating"] is None


def test_write_nfo_meta_has_no_underscore_keys(tmp_path):
    """regression：_write_nfo 收到的 meta 不含 _summary/_rating（whitelist 已在
    _scraper_to_meta crossing 截斷）。"""
    meta = _scraper_to_meta({"_summary": "x", "_rating": 1.0})
    assert "_summary" not in meta and "_rating" not in meta


# ─── 72b-T6：_write_nfo 傳 external_manager / has_poster / has_fanart ───────

def test_write_nfo_passes_external_manager_to_generate_nfo(tmp_path):
    """T6: _write_nfo(external_manager='jellyfin') → generate_nfo 收到相同值。"""
    fs_path = str(tmp_path / "SONE-205.mp4")
    meta = {"title": "T"}
    with patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(fs_path, "SONE-205", meta, write_nfo=True,
                   overwrite_existing=True, has_subtitle=False, user_tags=[],
                   external_manager="jellyfin")
    _, kwargs = mock_gen.call_args
    assert kwargs["external_manager"] == "jellyfin"


def test_write_nfo_passes_has_poster_has_fanart(tmp_path):
    """T6: _write_nfo(has_poster=True, has_fanart=True) → generate_nfo 收到 True/True（kodi 亦同）。"""
    fs_path = str(tmp_path / "SONE-205.mp4")
    meta = {"title": "T"}
    with patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(fs_path, "SONE-205", meta, write_nfo=True,
                   overwrite_existing=True, has_subtitle=False, user_tags=[],
                   external_manager="kodi", has_poster=True, has_fanart=True)
    _, kwargs = mock_gen.call_args
    assert kwargs["has_poster"] is True
    assert kwargs["has_fanart"] is True
    assert kwargs["external_manager"] == "kodi"


def test_write_nfo_off_mode_default_has_poster_fanart_false(tmp_path):
    """T6: off 模式（default）→ generate_nfo has_poster/has_fanart=False（byte-identical）。"""
    fs_path = str(tmp_path / "SONE-205.mp4")
    meta = {"title": "T"}
    with patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(fs_path, "SONE-205", meta, write_nfo=True,
                   overwrite_existing=True, has_subtitle=False, user_tags=[])
    _, kwargs = mock_gen.call_args
    assert kwargs.get("external_manager", "off") == "off"
    assert kwargs.get("has_poster", False) is False
    assert kwargs.get("has_fanart", False) is False
