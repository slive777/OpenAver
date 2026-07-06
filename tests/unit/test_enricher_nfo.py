"""63c-5: enricher summary/rating crossing — _scraper_to_meta / _merge_meta / _write_nfo（CD-63c-5）。"""
from unittest.mock import patch, MagicMock

from core.enricher import _scraper_to_meta, _merge_meta, _write_nfo
from core.path_utils import to_file_uri, uri_to_fs_path


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


# ─── TASK-91b-T1：_write_nfo user_tags is None 分支 WSL+UNC 回歸（axis-B 子形狀 i）───

def test_write_nfo_user_tags_none_wsl_mapped_uses_mapped_namespace(tmp_path, monkeypatch):
    """`_write_nfo` 的 `user_tags is None` fallback 分支（enricher.py 原 :184）若用反解後
    的本機路徑 `fs_path` 建 DB key，在 WSL+path_mappings 下會落非 mapped 命名空間 →
    `get_by_path` miss → 既有 user_tags 讀回 []（清空語意）。修法：新增
    `fs_path_for_db` 參數，DB key 改用它建（未傳時 fallback `fs_path`，向後相容）。

    修前 RED：get_by_path 收到用 `fs_path`（反解後的本機磁碟路徑）建的 unmapped key，
    miss，generate_nfo 收到 user_tags=[]（既有 '評5' 被清空）。
    修後 GREEN：get_by_path 收到用 `fs_path_for_db`（未反解、round-trip 回原 DB URI）
    建的 mapped key，命中既有 record，generate_nfo 收到 user_tags=['評5']。

    `fs_path_for_db` 語意比照 `enrich_single`（enricher.py:363）：
    `uri_to_fs_path(file_path)`（file_path 是既有 DB URI，只 strip prefix、不反解 mapping）
    —— 與 `fs_path = uri_to_local_fs_path(file_path, path_mappings)`（反解到本機磁碟路徑）
    是同一來源、兩種分流用途；DB round-trip 不需第二引數 `path_mappings`
    （round-trip 本身即回到原 mapped URI）。
    """
    import core.path_utils as path_utils_module
    # gotcha：CURRENT_ENV 是 core.path_utils 的 module-global，_write_nfo 內
    # `to_file_uri` 在同模組查找，patch 該模組單一 binding 即可。
    monkeypatch.setattr(path_utils_module, 'CURRENT_ENV', 'wsl')

    path_mappings = {"/home/user/nas/share": "//NAS/share"}
    local_path = "/home/user/nas/share/ABC-003/ABC-003.mp4"
    mapped_uri = to_file_uri(local_path, path_mappings)  # 既有 DB row 的 canonical URI
    fs_path_for_db = uri_to_fs_path(mapped_uri)  # DB round-trip 用值（不反解 mapping）
    # sanity：round-trip 回同一 mapped URI（不需 path_mappings 第二引數）
    assert to_file_uri(fs_path_for_db) == mapped_uri

    fs_path = str(tmp_path / "ABC-003.mp4")  # 磁碟 I/O 用值：反解後的本機路徑（與 DB 值不同）

    existing_video = MagicMock()
    existing_video.user_tags = ["評5"]

    def _get_by_path(path_uri):
        if path_uri == mapped_uri:
            return existing_video
        return None

    mock_repo = MagicMock()
    mock_repo.get_by_path.side_effect = _get_by_path

    meta = {"title": "T"}
    with patch("core.enricher.VideoRepository", return_value=mock_repo), \
         patch("core.enricher.generate_nfo") as mock_gen:
        mock_gen.return_value = True
        _write_nfo(
            fs_path=fs_path,
            number="ABC-003",
            meta=meta,
            write_nfo=True,
            overwrite_existing=True,
            has_subtitle=False,
            user_tags=None,
            fs_path_for_db=fs_path_for_db,
        )

    mock_repo.get_by_path.assert_called_once_with(mapped_uri)
    _, kwargs = mock_gen.call_args
    assert kwargs["user_tags"] == ["評5"], (
        f"既有 user_tags 不應被 WSL+mapped 命名空間 miss 清空，實際: {kwargs['user_tags']}"
    )
