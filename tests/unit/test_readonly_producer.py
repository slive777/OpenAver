"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.path_utils import to_file_uri
from tests.conftest import MOCK_FOCAL_XY
from core.focal.subprocess_runner import RunnerOutcome


# ---------------------------------------------------------------------------
# Guard test: producer must not contain forbidden names (DoD / CD-88b-1)
# ---------------------------------------------------------------------------

def test_guard_no_forbidden_names():
    """Producer source code must not reference organize_file / enrich_single / scan_file."""
    import core.readonly_producer as mod
    src = inspect.getsource(mod)
    for name in ("organize_file", "enrich_single", "scan_file"):
        assert name not in src, (
            f"core/readonly_producer.py must not import or call '{name}' (CD-88b-1)"
        )


# ---------------------------------------------------------------------------
# _min_size_bytes
# ---------------------------------------------------------------------------

class TestMinSizeBytes:

    def test_converts_mb_to_bytes(self):
        from core.readonly_producer import _min_size_bytes
        assert _min_size_bytes({"min_size_mb": 2}) == 2 * 1024 * 1024


# ---------------------------------------------------------------------------
# _list_source_videos
# ---------------------------------------------------------------------------

class TestListSourceVideos:


    def test_tolerates_file_uri_source_path(self, tmp_path):
        """PR#91 P2-A regression: a file:/// source path must resolve to the real FS
        dir and find the videos (DirectoryConfig.path may be an FS path OR URI).

        RED against the old ``normalize_path(source_path)`` code: on Linux/WSL,
        normalize_path leaves ``file:///...`` literal → fast_scan_directory scans a
        non-existent relative dir → returns []. GREEN after switching to uri_to_fs_path.
        """
        from core.path_utils import to_file_uri
        from core.readonly_producer import _list_source_videos

        video = tmp_path / "ABC-123.mp4"
        video.write_bytes(b"x" * 2048)

        source_uri = to_file_uri(str(tmp_path))
        assert source_uri.startswith("file:///")

        result = _list_source_videos(source_uri, {".mp4"}, 0)

        assert [f["path"] for f in result] == [str(video)]


# ---------------------------------------------------------------------------
# _should_skip  (TASK-89b-T3: single attempted-index signal + force escape hatch)
# ---------------------------------------------------------------------------

class TestShouldSkip:
    SOURCE_URI = "file:///src/a.mp4"


    def test_attempted_positive_but_force_true_returns_false(self):
        """force=True overrides an attempted>0 entry → not skipped (manual re-scrape)."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: 1720000000.0}
        assert _should_skip(self.SOURCE_URI, attempted_index, force=True) is False


# ---------------------------------------------------------------------------
# T-2 tests: _format_data, _folder_parts, _build_basename
# ---------------------------------------------------------------------------

class TestFormatData:
    """Tests for _format_data (organizer off-mode format_data construction)."""

    BASE_CONFIG = {
        'max_title_length': 20,
        'suffix_keywords': ['-C', '-U'],
        'filename_format': '{num} {title}',
        'max_filename_length': 60,
    }

    def test_long_title_truncated(self):
        from core.readonly_paths import _format_data
        meta = {'number': 'ABC-123', 'title': 'A' * 30}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert len(fd['title']) <= 20
        assert fd['title'].endswith('...')


class TestFolderParts:
    """Tests for _folder_parts."""


    def test_empty_layer_skipped(self):
        from core.readonly_paths import _folder_parts
        # An empty-string layer formats to '' and must be dropped by the `if part` guard.
        config = {'folder_layers': ['{num}', ''], 'max_filename_length': 60}
        fd = {'number': 'ABC-123', 'title': 'Title', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        # empty layer dropped → only the number layer survives (RED if `if part` guard removed)
        assert parts == ['ABC-123']


class TestBuildBasename:
    """Tests for _build_basename (off-mode filename stem generation)."""

    BASE_FD = {
        'number': 'ABC-123',
        'title': 'Normal Title',
        'actors': [],
        'maker': '',
        'date': '',
        'suffix': '',
    }
    BASE_CONFIG = {
        'filename_format': '{num} {title}',
        'max_filename_length': 60,
        'suffix_keywords': [],
    }

    def test_vr_tail_present_for_vr_file(self):
        from core.readonly_paths import _build_basename
        with patch('core.readonly_paths._detect_vr_cluster', return_value='180_LR'):
            result = _build_basename(self.BASE_FD, '/src/ABC-123_180_LR.mp4', self.BASE_CONFIG)
        assert result.endswith('_180_LR')


# ---------------------------------------------------------------------------
# TASK-89a-T3: TestResolveMovieDir (replaces TestBuildOwners/TestMovieLeafBase/
# TestMovieDir — see DELETED section note in module history / TASK-89a-T3.md)
# ---------------------------------------------------------------------------

class TestResolveMovieDir:
    """Tests for _resolve_movie_dir: read-and-reuse vs allocate+increment.

    URIs are derived via the REAL to_file_uri (not hand-typed) so the expected
    values track whatever slash-count convention to_file_uri actually produces
    for a bare Unix absolute path on this platform (path-contract compliant —
    no hand-rolled file:/// construction, see CLAUDE.md 路徑處理 禁止清單).
    """

    OUTPUT_ROOT = '/output'
    OUTPUT_URI = to_file_uri(OUTPUT_ROOT, {})
    BASE_CONFIG = {
        'folder_layers': [],
        'folder_format': '',       # no parent layer → leaf sits directly under output_root
        'max_filename_length': 60,
        'filename_format': '{num} {title}',
    }

    def _fd(self, number='ABC-123'):
        return {'number': number, 'title': 'Title', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}

    def _uri(self, leaf):
        return to_file_uri(str(Path(self.OUTPUT_ROOT, leaf)), {})

    def _existing(self, output_dir):
        v = MagicMock()
        v.output_dir = output_dir
        return v

    def _patch_exists(self, exists=False):
        return patch('core.readonly_producer.Path.exists', return_value=exists)

    def test_existing_under_output_root_reused_no_increment(self):
        """existing.output_dir non-empty and under output_uri → reuse verbatim, no increment."""
        from core.readonly_paths import _resolve_movie_dir
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        existing_uri = self._uri('ABC-123')
        existing = self._existing(existing_uri)
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', existing,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd(), self.BASE_CONFIG,
                allocated, {},
            )

        assert output_dir_uri == existing_uri
        assert str(movie_dir) == '/output/ABC-123'
        repo.is_output_dir_taken.assert_not_called()

    def test_b1_multi_format_collision_increments(self):
        """First file (existing=None) allocates ABC-123; DB shows ABC-123 taken (by the
        first file's own committed row) for the second file → second gets ABC-123-2."""
        from core.readonly_paths import _resolve_movie_dir
        repo = MagicMock()
        taken_uri = self._uri('ABC-123')

        def fake_taken(uri, exclude_path):
            return uri == taken_uri  # already committed by file #1

        repo.is_output_dir_taken.side_effect = fake_taken
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mkv', None,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, {},
            )

        assert output_dir_uri == self._uri('ABC-123-2')
        assert str(movie_dir) == '/output/ABC-123-2'


    # -----------------------------------------------------------------
    # TASK-89a-T5 (CD-89a-6 / Codex C3): mapped-output 定位.
    # gotcha: CURRENT_ENV is value-imported into core.readonly_paths (moved
    # here by TASK-151a-T1 along with _resolve_movie_dir), so monkeypatch the
    # USE site (core.readonly_paths.CURRENT_ENV), not core.path_utils.CURRENT_ENV
    # (see TASK-89a-T5.md).
    # -----------------------------------------------------------------

    def test_mapped_output_wsl_with_mapping_reverses_fs_but_not_uri(self, monkeypatch):
        """A main scenario: wsl + non-empty path_mappings + hit → returned fs Path is
        reverse-mapped to the real local path, while the returned URI (stored back to
        DB) stays the original forward-mapped existing.output_dir untouched."""
        from core import readonly_paths
        from core.readonly_paths import _resolve_movie_dir

        monkeypatch.setattr(readonly_paths, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': '//NAS-SERVER/share'}
        output_root_local = '/home/user/nas/lib'
        output_uri = to_file_uri(output_root_local, mappings)
        existing_uri = to_file_uri(str(Path(output_root_local, 'ABC-123')), mappings)
        existing = self._existing(existing_uri)
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', existing,
                output_root_local, output_uri, self._fd(), self.BASE_CONFIG,
                allocated, mappings,
            )

        # fs Path reverse-mapped to the real local (WSL) path — writable target
        assert str(movie_dir) == '/home/user/nas/lib/ABC-123'
        # DB-stored URI stays the original forward-mapped canonical value
        # (must NOT be reverse-mapped, else next-run is_path_under_dir mismatches)
        assert output_dir_uri == existing_uri


# ---------------------------------------------------------------------------
# T-3 tests: _write_movie_assets, _upsert_db
# ---------------------------------------------------------------------------

_T3_META = {
    'number': 'TEST-001',
    'title': 'Test Movie Title',
    'cover': 'https://example.com/cover.jpg',
    'actors': ['Actress A', 'Actress B'],
    'tags': ['tag1', 'tag2'],
    'date': '2024-01-01',
    'maker': 'Test Maker',
    'director': 'Test Director',
    'series': 'Test Series',
    'label': 'Test Label',
    'sample_images': [
        'https://example.com/sample1.jpg',
        'https://example.com/sample2.jpg',
    ],
    'duration': 120,
    '_summary': 'Test summary',
    '_rating': 8.5,
    'url': 'https://example.com/video',
}

_T3_FILE_INFO = {
    'size': 1234567890,
    'mtime': 1704067200.0,
}

# TASK-104-T1 (CD-104-4): _upsert_db full mode now reads assets['nfo_mtime']
# instead of a hardcoded 0.0 — every direct _upsert_db unit-test call below
# must supply this key. A distinctive non-zero value (not 0.0, not equal to
# mtime/size) so a test asserting v.nfo_mtime against it can't pass by accident.
_T3_NFO_MTIME = 1704067333.5

_T3_BASE_CONFIG = {
    'filename_format': '{num} {title}',
    'max_filename_length': 60,
    'max_title_length': 50,
    'suffix_keywords': [],
    'external_manager': 'kodi',
    'download_sample_images': False,
}


def _t3_format_data(meta=None, source_fs_path='/src/TEST-001.mp4', config=None):
    from core.readonly_paths import _format_data
    return _format_data(meta or _T3_META, source_fs_path, config or _T3_BASE_CONFIG)


def _t3_generate_nfo_side_effect(**kwargs):
    """generate_nfo side_effect used by tests that mock it out but still need a
    real file on disk (TASK-104-T1 / CD-104-4: _write_movie_assets now stats the
    NFO it just wrote — `os.stat(nfo_fs)` — so a bare MagicMock/return_value=True
    with no actual write raises FileNotFoundError)."""
    output_path = kwargs.get('output_path', '')
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text('<movie/>', encoding='utf-8')
    return True


def _cover_strategy_for(meta):
    """TASK-104-T1: mirror produce_source's own cover_strategy derivation
    (`('download', meta['cover']) if meta.get('cover') else ('none',)`) so
    pre-existing direct `_write_movie_assets` unit tests keep exercising the
    exact same 'download'/'none' behaviour they always have, now expressed
    through the explicit CD-104-2 3-state contract instead of an implicit
    default inside the writer."""
    return ('download', meta['cover']) if meta.get('cover') else ('none',)


class TestWriteMovieAssets:
    """T-3: write-target containment, re-scrape, extrafanart gate, has_cover=False."""

    def test_write_target_containment(self, tmp_path):
        """All write targets must be under movie_dir; none under source file's dir."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        source_fs_path = '/src/TEST-001.mp4'
        source_dir = str(Path(source_fs_path).parent)
        fd = _t3_format_data(source_fs_path=source_fs_path)

        recorded_paths: list = []

        def fake_download(url, save_path, referer=''):
            recorded_paths.append(save_path)
            return True

        def fake_jellyfin(cover_path, base_stem, **_kw):
            # cover_path is a READ input (source for copy/crop), not a write target — don't record it.
            recorded_paths.append(base_stem + '-poster.jpg')
            recorded_paths.append(base_stem + '-fanart.jpg')
            return {'poster': True, 'fanart': True}

        def fake_nfo(**kwargs):
            recorded_paths.append(kwargs.get('output_path', ''))
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_assets.download_image', side_effect=fake_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=fake_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=fake_nfo):
            _write_movie_assets(
                movie_dir, _T3_META, fd, source_fs_path, _T3_BASE_CONFIG,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert recorded_paths, "No paths were recorded — mocks not called"
        for p in recorded_paths:
            if not p:
                continue
            assert p.startswith(movie_dir), (
                f"Write target {p!r} not under movie_dir {movie_dir!r}"
            )
            assert not p.startswith(source_dir), (
                f"Write target {p!r} leaks into source dir {source_dir!r}"
            )


    def test_write_movie_assets_applies_custom_nfo_title_format(self, tmp_path):
        """config 提供 nfo_title_format 時應轉傳給 generate_nfo"""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, nfo_title_format='{num}-{title}')
        captured: dict = {}

        def capture_nfo(**kwargs):
            captured.update(kwargs)
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=capture_nfo):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert captured.get('nfo_title_format') == '{num}-{title}'


    def test_copy_strategy_same_target_preflight_regression(self, tmp_path):
        """Red-team finding, pre-merge 112b (2026-08-04): 「1) Cover」copy 分支
        原本只有裸 `except OSError:`，`cover_strategy[1]`（copy 來源）與
        `resolve_cover_target()` 算出的 `cover_fs`（正典寫入位置）可能是同一個
        檔案——`shutil.copyfile` 對同檔拋 `SameFileError`（`OSError` 子類），被
        裸 except 吞成 `has_cover=False`，導致 poster/fanart 整段被跳過、DB
        `cover_path` 回空字串，而磁碟上那張封面內容完好無損（使用者看到破圖）。

        這條路徑 pre-112 就已可達；本 branch 的 CD-112-7（curator `-fanart`
        升格為封面來源）多開了一條路——來源只有同 stem 的 `-fanart.jpg`、沒有
        同名 `.jpg` 時，`resolve_cover_target` 的三步規則②會直接把「已存在的
        `-fanart` 候選」選為 cover_fs，與 copy 來源字面相同。

        修法：`_write_cover_copy`（照抄 `generate_jellyfin_images` 的
        `same_target_verdict` preflight 形狀，CD-112b-1）。本測試重現該情境：
        movie_dir 內只放一張 `<base>-fanart.jpg`（無同名 `.jpg`），
        cover_strategy=('copy', 那張 fanart 檔) —— resolve_cover_target 因此
        回傳同一個路徑。

        斷言：
        ① has_cover 為 True → assets['cover_fs'] 非空
        ② 該封面檔案 bytes 與操作前的基準值一致（BE-TEST-10：基準在操作前取）
        ③ poster/fanart 衍生圖確實被產生（證明第 2 段不再因 has_cover=False 被跳過）

        Mutation 自驗（可逆 Edit，驗完已改回）：把 `_write_cover_copy` 內的
        `same_target_verdict` preflight拿掉、只留裸
        `try: shutil.copyfile(...) / except OSError: has_cover = False`
        （即還原成 bug 版本）→ 本測試單獨轉紅（AssertionError：cover_fs 為空 /
        poster 或 fanart 未產生），其餘測試不受影響。
        """
        from core.readonly_paths import _build_basename
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-CD1127')
        os.makedirs(movie_dir, exist_ok=True)
        source_fs_path = '/src/TEST-CD1127.mp4'
        meta = dict(_T3_META, number='TEST-CD1127', maker='Test Maker')
        fd = _t3_format_data(meta=meta, source_fs_path=source_fs_path)
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')

        base = _build_basename(fd, source_fs_path, config)
        base_stem = str(Path(movie_dir) / base)

        # Curator sidecar: ONLY a same-stem -fanart.jpg exists, no same-name
        # .jpg — resolve_cover_target's 3-step rule ② picks this existing
        # -fanart candidate as cover_fs, which is exactly the file being
        # copied FROM (CD-112-7's newly-opened path into the pre-existing bug).
        fixture_path = _T3_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        curator_fanart = base_stem + '-fanart.jpg'
        Path(curator_fanart).write_bytes(fixture_path.read_bytes())
        # Baseline taken BEFORE the operation under test (BE-TEST-10).
        baseline_bytes = Path(curator_fanart).read_bytes()

        with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect), \
             patch('core.organizer.run_detection', return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            assets = _write_movie_assets(
                movie_dir, meta, fd, source_fs_path, config,
                cover_strategy=('copy', curator_fanart),
            )

        assert assets['cover_fs'] != '', (
            "cover_fs must not be empty — SameFileError must not be swallowed "
            "into has_cover=False"
        )
        assert assets['cover_fs'] == curator_fanart, (
            "cover_fs should resolve back to the same file that was already there"
        )
        assert Path(curator_fanart).read_bytes() == baseline_bytes, (
            "cover file bytes must be untouched by the same-file copy attempt"
        )

        poster_path = Path(base_stem + '-poster.jpg')
        fanart_path = Path(base_stem + '-fanart.jpg')
        assert poster_path.exists(), (
            "poster must be generated — has_cover=True must not skip section 2"
        )
        assert fanart_path.exists(), (
            "fanart (== cover_fs here) must exist on disk"
        )

    def test_copy_strategy_same_target_missing_dst_is_not_success(self, tmp_path):
        """Codex PR#125 P2（2026-08-05）：同檔捷徑不得把「檔案已經不在了」報成成功。

        姊妹測試 `test_copy_strategy_same_target_preflight_regression` 鎖的是
        「同檔存在 → 必須宣稱成功」；本測試鎖**反向**：同一條 `src == dst` 捷徑，
        當那個檔案在 `resolve_ingest_plan` 偵測之後、`_write_cover_copy` 執行之前
        被外部刪除時，**不得**回報 `has_cover=True`。

        為什麼這條不是既有 residual：`same_target_verdict` 的五格真值表裡，
        `src == dst` 是唯一一格純字串比較、零 I/O 的——它的 docstring 自己把
        「不驗存在性」列為具名 residual，並寫明「T3 讓唯讀正典變成 `-fanart.jpg`
        之後（字串相等成為常態路徑），這一條必須重新評估」。另外六個
        `same_target_verdict` 呼叫點都在幾行前重新確認過 `dst`；`_write_cover_copy`
        沒有——它的 `src` 來自 `cover_strategy[1]`，那個 `.exists()` 發生在
        `resolve_ingest_plan`、隔了好幾個 I/O hop。T3 §H-5 的六點稽核用
        `grep "same_target_verdict("` 做，**只找得到已經有保護的點**；本函式是
        red-team 在那次稽核之後才加的第 7 個呼叫點（commit `2338c62d`）。

        假成功的傳導後果（CD-112-8 判定為比「假失敗」更糟的那一類）：
        `has_cover=True` → 第 2 段照跑 poster/fanart → `generate_nfo` 收到
        `has_fanart=True` 寫出懸空 `<thumb>`/`<fanart>` → DB 記一個不存在的
        `cover_path`（違反 AC5b/AC7）。

        斷言：
        ① `assets['cover_fs']` 為空字串（不得回傳幻影路徑）
        ② `-poster` / `-fanart` 都沒有被產生（第 2 段被 has_cover 正確擋下）
        ③ 磁碟上仍然沒有那個封面檔（本測試自己沒有把它變出來）

        Mutation 自驗（可逆 Edit，驗完改回）：把 `_write_cover_copy` 的
        `return certain and os.path.exists(dst)` 改回 `return certain`
        → 本測試單獨轉紅（cover_fs 非空 + poster/fanart 被產生），
        姊妹測試 `..._preflight_regression` 維持綠（形狀正確：正向鎖不該一起紅）。
        """
        from core.readonly_paths import _build_basename
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-CD1127')
        os.makedirs(movie_dir, exist_ok=True)
        source_fs_path = '/src/TEST-CD1127.mp4'
        meta = dict(_T3_META, number='TEST-CD1127', maker='Test Maker')
        fd = _t3_format_data(meta=meta, source_fs_path=source_fs_path)
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')

        base = _build_basename(fd, source_fs_path, config)
        base_stem = str(Path(movie_dir) / base)

        # 與姊妹測試同一個佈局，唯一差別：那張 curator -fanart.jpg 已經不在了
        # （模擬 resolve_ingest_plan 偵測到之後被外部程序刪除/改名）。
        # resolve_cover_target 第③步在 jellyfin 風味下仍會算出同一個 -fanart
        # 路徑 → src == dst 字串相等，走的正是那條零 I/O 的捷徑。
        curator_fanart = base_stem + '-fanart.jpg'
        assert not Path(curator_fanart).exists(), "前提：受測檔案一開始就不存在"

        with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect), \
             patch('core.organizer.run_detection', return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            assets = _write_movie_assets(
                movie_dir, meta, fd, source_fs_path, config,
                cover_strategy=('copy', curator_fanart),
            )

        assert assets['cover_fs'] == '', (
            "封面檔已不在磁碟上，cover_fs 必須是空字串——回傳幻影路徑會讓 DB "
            "記一個不存在的 cover_path（AC5b）"
        )
        assert not Path(base_stem + '-poster.jpg').exists(), (
            "has_cover 必須為 False，第 2 段的 poster 產生不得執行"
        )
        assert not Path(curator_fanart).exists(), (
            "-fanart 不得憑空出現——它一開始就不存在，本次也沒有任何來源可複製"
        )


# ---------------------------------------------------------------------------
# TASK-111-T3 群組 1/2 (spec-111 §5 AC1/AC2)：off/jellyfin/emby/kodi 的四檔案矩陣。
# 複用 _t4_write（module-level helper，定義於下方 :1058-1070 一帶——此處先用，
# Python 只在呼叫時才解析函式體，模組載入順序無影響）+ TestCleanStaleSingletons
# 的「四後綴迴圈」斷言 idiom，但套用在真跑 _write_movie_assets 之後的輸出目錄上
# （而不是像 TestCleanStaleSingletons 那樣預先手建假檔案——那是在測清理函式，
# 這裡是在測 writer 本身，task card「現況分析」已澄清兩者不可互相複用 fixture）。
# ---------------------------------------------------------------------------

class TestOffModeAssetMatrix:
    """AC1（off 無 poster/fanart，同名 .jpg + .nfo 都在）與 AC2（jellyfin/emby/
    kodi 三個 flavour 四檔皆在，各自獨立方法——plan 明文不 parametrize）。"""

    _BASE = 'TEST-001 Test Movie Title'

    def test_off_mode_no_poster_fanart_has_nfo_and_cover(self, tmp_path):
        movie_dir = tmp_path / 'movie'
        config = dict(_T3_BASE_CONFIG, external_manager='off')
        _t4_write(str(movie_dir), _T3_META, config)

        for suffix in ('.nfo', '.jpg'):
            assert (movie_dir / f'{self._BASE}{suffix}').exists(), f"{suffix} must exist (AC1)"
        for suffix in ('-poster.jpg', '-fanart.jpg'):
            assert not (movie_dir / f'{self._BASE}{suffix}').exists(), (
                f"{suffix} must NOT exist in off mode (AC1)"
            )


# ---------------------------------------------------------------------------
# TASK-111-T3 群組 3/4 (spec-111 §5 AC4 + 邊界)：off 模式 NFO 的 <poster>/<thumb>/
# <fanart> 字面退回同名封面。刻意不 mock generate_nfo（core.organizer.generate_nfo
# 真的執行）——test_generate_nfo_params 的 side_effect 只寫死 <movie/>，解析不出
# 真實 tag，這裡需要真實文字內容才能驗證 Opus 裁決要求的三件事。
# ---------------------------------------------------------------------------

class TestOffModeNfoTagFallback:
    """Opus 裁決（TASK-111-T3.md）：第 3 組必須同時斷言① tag 字面等於
    {basename}.jpg ② tag 指向的檔案存在 ③ generate_jellyfin_images 未被呼叫——
    只驗②是白鎖（gate mutation 後 off 又會產生 -poster/-fanart，檔案依然存在，
    ②單獨不具 mutation 敏感度）。第 4 組（無封面）只驗字面，不驗存在性（AC4
    邊界：spec-111 §4.1 具名 backlog，接受懸空引用）。"""

    _BASE = 'TEST-001 Test Movie Title'

    def _write_and_read_nfo(self, tmp_path, meta, config):
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'movie')
        fd = _format_data(meta, '/src/TEST-001.mp4', config)
        jellyfin_mock = MagicMock()

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', jellyfin_mock):
            # generate_nfo 不 patch — core.organizer.generate_nfo 真的執行，
            # 才能解析出真實 <poster>/<thumb>/<fanart> tag 內容。
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta),
            )

        # BE-TEST-01 #1: patch 使用端 core.readonly_assets.generate_jellyfin_images
        # （已於上方 with 區塊完成），off 不在 STEM_IMAGE_MODES 白名單，此處必須未被呼叫。
        jellyfin_mock.assert_not_called()
        nfo_path = Path(movie_dir) / f'{self._BASE}.nfo'
        return movie_dir, ET.parse(nfo_path).getroot()

    def test_off_with_cover_tags_fallback_and_files_exist(self, tmp_path):
        """AC4：off + 有封面 → 三個 tag 字面都等於 {basename}.jpg，且都指向
        實際存在的檔案（同名 .jpg）。"""
        config = dict(_T3_BASE_CONFIG, external_manager='off')
        movie_dir, root = self._write_and_read_nfo(tmp_path, _T3_META, config)

        expected_tag = f'{self._BASE}.jpg'
        poster_tag = root.findtext('poster')
        thumb_tag = root.findtext('thumb')
        fanart_tag = root.findtext('fanart')

        # ① tag 字面斷言 — mutation 敏感源：gate 還原後 has_poster=True，這裡會變成
        # '{basename}-poster.jpg'，立刻不等於 expected_tag。
        assert poster_tag == expected_tag, "AC4: <poster> must fall back to same-name cover in off mode"
        assert thumb_tag == expected_tag, "AC4: <thumb> is always same-name (has_poster/has_fanart 無關)"
        assert fanart_tag == expected_tag, "AC4: <fanart> must fall back to same-name cover in off mode"

        # ② tag 指向的檔案實際存在 — 單獨不具 mutation 敏感度，必須與①並存（Opus 裁決）。
        for tag_value in (poster_tag, thumb_tag, fanart_tag):
            assert (Path(movie_dir) / tag_value).exists(), f"tag {tag_value!r} must point to an existing file"


# ---------------------------------------------------------------------------
# Codex PR#123 P2: external_manager 是 load_config() 的未驗證原始值（BE-CONFIG-03,
# 沒過 Pydantic model_validate）。CD-111-2 的正向白名單（`in STEM_IMAGE_MODES`）
# 已正確擋掉畸形值的 poster/fanart，但同一個原始值接著被傳進 generate_nfo
# （core/organizer.py），該處用的是負向 `!= 'off'`——'Jellyfin'（大小寫）/None/
# 'plex'（未知值）這類值會被圖片 gate 擋下，卻仍讓
# NFO 寫入 <lockdata>/<uniqueid type="num">/<sorttitle>/<country>/<language> 五個
# 媒體管理器專用欄位——只 fail-closed 了一半。Opus 裁決：core/config.py 新增
# normalize_external_manager() 公開函式，readonly_producer 在讀 config 值時就地
# 收斂，讓兩個下游 gate（poster/fanart 的正向白名單 + generate_nfo 的負向判斷）
# 吃到同一個已收斂值，同步 fail-closed。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Codex PR#123 round-3 P2①-b（Opus 裁決：TASK-111-T6.md「⚖️ Opus 裁決」段選項 2）。
#
# 現有覆蓋各鎖了半段：test_core_config.py::test_legacy_jellyfin_emby_migrates_to_jellyfin
# 只驗 load_config() 把 'jellyfin_emby' 改寫成 'jellyfin'（config 值本身）；
# TestOffModeAssetMatrix::test_jellyfin_mode_all_four_files_present 只驗手搭
# external_manager='jellyfin' 的 config 能正確產出四檔。兩者中間「migration 後的
# 值真的流進圖片產出」這條線從未被接起來過——本測試補這個缺口，**不重造**上述任一
# 半段已驗過的斷言。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TASK-101a-T2 DoD①④：站3接線——真跑 _write_movie_assets()，generate_jellyfin_images
# 不 mock（既有測試全部 mock 掉它；本測試是唯一不 mock 它的）。
# ---------------------------------------------------------------------------

_T3_FOCAL_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos"


def _t3_write_face_cover(url, save_path, referer=''):
    src = _T3_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    Path(save_path).write_bytes(src.read_bytes())
    return True


def _t3_oracle_poster_bytes(focal_xy):
    """獨立 oracle：不經過 crop_to_poster / generate_jellyfin_images / _write_movie_assets，
    直接呼叫底層 primitive 算出期望 bytes。不可用「呼叫同一站流程兩次自我比對」
    （gotchas-backend.md #9，101a-T1 已踩過）。

    TASK-102c-T1：改吃 focal_xy 參數，不再自己呼叫真 detect_focal——呼叫端須確保
    patch `core.organizer.run_detection` 回傳 `RunnerOutcome(kind="FOUND", focal=同一個值)`，
    否則 production 端與 oracle 端會對不上。
    """
    from core.organizer import _poster_window_ratio
    from core.focal import crop_image_position
    from PIL import Image
    import io as _io

    fixture_path = _T3_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    focal = focal_xy
    with Image.open(fixture_path) as img:
        expected_cropped = crop_image_position(img.convert("RGB"), r_window, focal[0])
    buf = _io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


class TestWriteMovieAssetsStationWiring:
    """DoD①：站3（core/readonly_producer.py _write_movie_assets → generate_jellyfin_images
    → crop_to_poster）接線——真跑完整流程，fixture A（番號驅動）/ B（maker-only 驅動）
    各一次，poster bytes 對獨立 oracle。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}

    def _run_station3(self, tmp_path, tag, fixture, external_manager='jellyfin'):
        from core.readonly_paths import _build_basename
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / f"{fixture['number']}_{tag}")
        source_fs_path = f"/src/{fixture['number']}_{tag}.mp4"
        meta = dict(_T3_META, number=fixture['number'], maker=fixture['maker'])
        fd = _t3_format_data(meta=meta, source_fs_path=source_fs_path)
        config = dict(_T3_BASE_CONFIG, external_manager=external_manager)

        with patch('core.readonly_assets.download_image', side_effect=_t3_write_face_cover), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect), \
             patch('core.organizer.run_detection', return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            assets = _write_movie_assets(
                movie_dir, meta, fd, source_fs_path, config,
                cover_strategy=_cover_strategy_for(meta),
            )

        assert assets['cover_fs'], "station3 應成功下載封面"
        # Opus 追加要求 #1（T6 review）：base_stem 必須從 movie_dir ＋ 測試自己算的
        # basename 正向組出（與 _write_movie_assets:884 同源），不得從 cover_fs 反推
        # （不呼叫 cover_base_stem）——CD-112b-3 剛把產品碼裡唯一一處「從封面路徑反推
        # stem」連根拔掉，測試 helper 不得重建同一形狀，否則測試會與產品碼同向漂移。
        base = _build_basename(fd, source_fs_path, config)
        base_stem = str(Path(movie_dir) / base)
        poster_path = Path(base_stem + '-poster.jpg')
        fanart_path = Path(base_stem + '-fanart.jpg')
        if external_manager == 'off':
            assert not poster_path.exists(), "off 模式不應產生 poster（TASK-111）"
            assert not fanart_path.exists(), "off 模式不應產生 fanart（TASK-111）"
        else:
            assert poster_path.exists(), "station3 應產生 poster"
            expected = _t3_oracle_poster_bytes(MOCK_FOCAL_XY)
            assert poster_path.read_bytes() == expected, "station3 poster 應對準焦點（獨立 oracle 比對）"

    def test_station3_fixture_a(self, tmp_path):
        self._run_station3(tmp_path, "a", self._FIXTURE_A)


    # -----------------------------------------------------------------
    # TASK-101a-T3 DoD①（Opus 拍板，非選配）：off/emby/kodi 唯讀產生庫三路
    # 各補一個 fixture-A-only 真跑案例（不 mock crop_to_poster/generate_
    # jellyfin_images）。TASK-111 之後三路不再同向：emby/kodi 仍斷言 poster
    # bytes 對準同一個獨立 oracle（結構論證——呼叫對這兩路無條件，未來若有人
    # 加分支跳過烤圖，這裡會紅）；off 斷言 poster/fanart 皆不產生（spec-111
    # §2.1 的 gate，見 `_run_station3` 內的分流）。
    # -----------------------------------------------------------------


# ---------------------------------------------------------------------------
# TASK-89a-T4 (Codex #3 / #4): _build_old_base + _clean_stale_extrafanart/_clean_stale_singletons
# ---------------------------------------------------------------------------

def _t4_existing(meta):
    """Build a Video-row-shaped stand-in from a _T3_META-like dict (DB → meta mapping)."""
    from types import SimpleNamespace
    return SimpleNamespace(
        title=meta.get('title', ''),
        number=meta.get('number', ''),
        actresses=meta.get('actors', []),
        maker=meta.get('maker', ''),
        release_date=meta.get('date', ''),
    )


def _t4_real_download(url, save_path, referer=''):
    """Real-file download stub for T4 round-trip tests (mirrors e2e mock)."""
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    Path(save_path).write_bytes(b'FAKE-IMG')
    return True


def _t4_real_jellyfin(cover_fs, base_stem, **_kw):
    """T6 對齊：media-server flavour 下 `-fanart.jpg` 與 `cover_fs` 常態同名（真理表
    Table 2 #1，正典即 fanart）——真實 `generate_jellyfin_images` 的 fanart 步驟在
    同檔情境走 `same_target_verdict` 短路、不覆寫。這個 stub 必須鏡像同一行為，
    否則會就地覆寫剛下載好的封面內容（`_t4_real_jellyfin` 曾無條件覆寫兩個目標，
    在同檔情境下會把 cover 的真實 bytes 換成假的 FAKE-IMG）。poster 目標恆不同名，
    不受影響。"""
    poster_path = base_stem + '-poster.jpg'
    fanart_path = base_stem + '-fanart.jpg'
    Path(poster_path).write_bytes(b'FAKE-IMG')
    if fanart_path != cover_fs:
        Path(fanart_path).write_bytes(b'FAKE-IMG')
    return {'poster': True, 'fanart': True}


def _t4_real_nfo(**kwargs):
    Path(kwargs['output_path']).write_text('<movie/>', encoding='utf-8')
    return True


def _t4_write(movie_dir, meta, config, old_base='', download_side_effect=None):
    """Run the real _write_movie_assets (real file writes) with T4's old_base kwarg."""
    from core.readonly_paths import _format_data
    from core.readonly_assets import _write_movie_assets

    fd = _format_data(meta, '/src/TEST-001.mp4', config)
    with patch('core.readonly_assets.download_image',
               side_effect=download_side_effect or _t4_real_download), \
         patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
        return _write_movie_assets(
            movie_dir, meta, fd, '/src/TEST-001.mp4', config,
            cover_strategy=_cover_strategy_for(meta), old_base=old_base,
        )


class TestRenameStaleCoverGroup:
    """T3（151b，CD-151b-4）：`_rename_stale_cover_group` — 洞一改名機制。

    標題漂移時把舊基底的封面／poster／fanart 搬到新基底；三種既有 DB 語意不變
    （C-8 零寫入、C-10 真 no-op、①b 錨點缺失整組 no-op），純函式測試——不寫 DB，
    不呼叫 `_produce_one`（接線是 T4 的事）。
    """

    def test_new_layout_two_files_renamed(self, tmp_path):
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        new_base = 'TEST-001 New'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        poster.write_bytes(b'POSTER BYTES')
        fanart.write_bytes(b'FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not poster.exists()
        assert not fanart.exists()
        new_poster = d / f'{new_base}-poster.jpg'
        new_fanart = d / f'{new_base}-fanart.jpg'
        assert new_poster.read_bytes() == b'POSTER BYTES'
        assert new_fanart.read_bytes() == b'FANART BYTES'
        assert outcome.hard_failure is False
        assert outcome.moved_pairs == (
            (str(poster), str(new_poster)),
            (str(fanart), str(new_fanart)),
        )
        assert outcome.new_cover_uri == to_file_uri(str(new_fanart), {})


    def test_off_layout_one_file_renamed(self, tmp_path):
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-003 Old'
        new_base = 'TEST-003 New'
        cover = d / f'{old_base}.jpg'
        cover.write_bytes(b'ONLY COVER')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not cover.exists()
        new_cover = d / f'{new_base}.jpg'
        assert new_cover.read_bytes() == b'ONLY COVER'
        assert outcome.moved_pairs == ((str(cover), str(new_cover)),)
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_cover), {})


    def test_noop_when_cover_path_outside_movie_dir(self, tmp_path):
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        movie_dir = tmp_path / 'movie'
        movie_dir.mkdir()
        outside_dir = tmp_path / 'outside_source'
        outside_dir.mkdir()
        outside_cover = outside_dir / 'SRC-001-fanart.jpg'
        outside_cover.write_bytes(b'ORIGINAL SOURCE BYTES')
        before_mtime_ns = outside_cover.stat().st_mtime_ns
        existing = SimpleNamespace(cover_path=to_file_uri(str(outside_cover), {}))

        outcome = _rename_stale_cover_group(str(movie_dir), existing, 'TEST-005 New', {})

        assert outcome == RenameOutcome(None, False, ())
        assert outside_cover.read_bytes() == b'ORIGINAL SOURCE BYTES'
        assert outside_cover.stat().st_mtime_ns == before_mtime_ns, \
            "C-8 必須是零寫入——外部檔案的 mtime 也不能動（不只內容/路徑）"
        assert list(movie_dir.iterdir()) == []

    def test_destination_exists_whole_group_untouched(self, tmp_path, caplog):
        import logging

        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-006 Old'
        new_base = 'TEST-006 New'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        poster.write_bytes(b'REAL COVER BYTES POSTER')
        fanart.write_bytes(b'REAL COVER BYTES FANART')
        decoy = d / f'{new_base}-poster.jpg'
        decoy.write_bytes(b'DECOY')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        with caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert outcome == RenameOutcome(None, False, ())
        assert poster.read_bytes() == b'REAL COVER BYTES POSTER'
        assert fanart.read_bytes() == b'REAL COVER BYTES FANART'
        assert decoy.read_bytes() == b'DECOY'
        assert not (d / f'{new_base}-fanart.jpg').exists()
        messages = [r.getMessage() for r in caplog.records]
        assert any('改名撞名' in m and decoy.name in m for m in messages), (
            f"缺少撞名 warning log（含撞到的檔名 {decoy.name}）：{messages}"
        )

    def test_mid_rename_io_failure_reverts(self, tmp_path):
        from core.atomic_write import atomic_move as _real_atomic_move
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-007 Old'
        new_base = 'TEST-007 New'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        poster.write_bytes(b'REAL COVER BYTES POSTER')
        fanart.write_bytes(b'REAL COVER BYTES FANART')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        call_count = {'n': 0}

        def flaky(src, dst):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise OSError("simulated mid-rename failure")
            _real_atomic_move(src, dst)

        with patch('core.readonly_assets.atomic_move', side_effect=flaky):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert outcome == RenameOutcome(None, True, ())
        assert poster.read_bytes() == b'REAL COVER BYTES POSTER'
        assert fanart.read_bytes() == b'REAL COVER BYTES FANART'
        assert not (d / f'{new_base}-poster.jpg').exists()
        assert not (d / f'{new_base}-fanart.jpg').exists()


    # -----------------------------------------------------------------
    # Codex PR#197 review P2 (151b pre-merge 後新洞)：cover_base_stem() 純字串
    # 剝一次 -poster/-fanart 尾碼，分不出「衍生的 sidecar 尾碼」與「尾碼本來
    # 就是基底標題一部分」。以下五格對應卡片「至少要鎖的五格測試」。
    # -----------------------------------------------------------------


    # -----------------------------------------------------------------
    # Codex 第四輪 review P2：提示精確匹配不能證明 old_base 沒有失憶——反例是
    # 舊基底 `Movie-fanart` 在 DB title 已先行改成 `Movie` 之後，提示會「精確
    # 匹配」到錯的 stripped 候選。以下兩格參數化「兩個方向」的失憶碰撞：
    # 正向（長縮短，提示誤撞 stripped）／反向（短拉長，提示誤撞 literal）。
    # -----------------------------------------------------------------


    # -----------------------------------------------------------------
    # 第五輪 review 效能修正：證據判定改用 os.scandir 一次性目錄列舉，不再
    # 逐檔 os.path.exists（NAS/SMB 上每次 stat 是一趟網路來回）。以下三格
    # 鎖新機制本身：scandir 讀取失敗的 fail-safe、單一候選早退連目錄都不
    # 列的零 I/O 保證、以及兩套候選都要看證據時目錄只列舉一次。
    # -----------------------------------------------------------------


class TestWriteMovieAssetsStaleCleanup:
    """T4/T5 integration: _write_movie_assets(old_base=...) round-trips against real files.

    Covers DoD: title-drift (Codex #3 lock), extrafanart shrink, same-base
    overwrite-in-place (no pre-delete), user-file protection, first-generation
    no-op, reallocated-new-dir isolation, and (T5 follow-up, Codex PR review P2)
    partial-failure robustness — a failed write must leave the old assets intact.
    """

    def _config(self, **overrides):
        return dict(_T3_BASE_CONFIG, **overrides)

    def test_title_drift_old_series_removed(self, tmp_path):
        """Codex #3 regression lock: title A → title B leaves ONLY the B series."""
        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config(download_sample_images=True)

        _t4_write(movie_dir, meta_a, config)
        d = Path(movie_dir)
        assert (d / 'TEST-001 Title A.nfo').exists()

        from core.readonly_paths import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        assert old_base == 'TEST-001 Title A'

        _t4_write(movie_dir, meta_b, config, old_base=old_base)

        # 真理表 Table 2 #1：media-server flavour（_T3_BASE_CONFIG 預設 'kodi'）下正典
        # 即 `-fanart.jpg`，不再有獨立同名 `.jpg`——迴圈只查三項實體檔。CD-112-16 反面
        # 承諾（「有產新的才刪舊的」）不變：新的三檔必須存在、舊的三檔必須被刪除。
        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'TEST-001 Title A{suffix}').exists(), f"stale {suffix} survived"
            assert (d / f'TEST-001 Title B{suffix}').exists(), f"new {suffix} missing"
        # 額外補：兩者皆不存在獨立的同名 `.jpg`（不是「舊存新不存」）——確保沒有殘留的
        # 舊式獨立封面被誤判成「新格式的 .jpg」。
        assert not (d / 'TEST-001 Title A.jpg').exists(), "no stale standalone same-name cover"
        assert not (d / 'TEST-001 Title B.jpg').exists(), "no new standalone same-name cover either"


    def test_title_unchanged_overwrites_in_place_no_stale_delete(self, tmp_path):
        """old_base == new_base: _clean_stale_singletons must be a no-op (T5
        follow-up) — the same-named file is left for download_image/generate_nfo
        to overwrite directly, never pre-deleted. Deleting first (old behavior)
        would destroy the old asset even when the new write then fails partway."""
        from core.readonly_paths import _build_basename, _build_old_base, _format_data

        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Same Title')
        config = self._config()
        _t4_write(movie_dir, meta, config)

        old_base = _build_old_base(_t4_existing(meta), '/src/TEST-001.mp4', config)
        new_fd = _format_data(meta, '/src/TEST-001.mp4', config)
        new_base = _build_basename(new_fd, '/src/TEST-001.mp4', config)
        assert old_base == new_base, "sanity: title unchanged → identical basename"

        observed = {'cover_present_when_download_called': None}

        def recording_download(url, save_path, referer=''):
            if save_path.endswith('.jpg') and 'extrafanart' not in save_path:
                observed['cover_present_when_download_called'] = Path(save_path).exists()
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'NEW-COVER')
            return True

        _t4_write(movie_dir, meta, config, old_base=old_base, download_side_effect=recording_download)

        assert observed['cover_present_when_download_called'] is True, (
            "same-name old cover must NOT be pre-deleted — download_image overwrites it directly"
        )
        # 真理表 Table 2 #1：media-server flavour 下 download_image 的目標即
        # resolve_cover_target 算出的 cover_fs，也就是 `-fanart.jpg`（不是裸 `.jpg`）。
        assert (Path(movie_dir) / f'{new_base}-fanart.jpg').read_bytes() == b'NEW-COVER'

    def test_user_placed_files_not_deleted(self, tmp_path):
        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        config = self._config(download_sample_images=True)
        _t4_write(movie_dir, meta_a, config)

        d = Path(movie_dir)
        note = d / 'my-note.txt'
        note.write_text('user note')
        random_jpg = d / 'random.jpg'
        random_jpg.write_bytes(b'USER-IMG')
        ef_dir = d / 'extrafanart'
        ef_note = ef_dir / 'my_note.txt'
        ef_note.write_text('user note 2')
        ef_custom = ef_dir / 'custom.jpg'
        ef_custom.write_bytes(b'USER-CUSTOM')

        from core.readonly_paths import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        meta_b = dict(_T3_META, title='Title B')
        _t4_write(movie_dir, meta_b, config, old_base=old_base)

        assert note.exists()
        assert random_jpg.exists()
        assert ef_note.exists()
        assert ef_custom.exists()


    # -----------------------------------------------------------------------
    # T5 follow-up (Codex PR review P2): partial-failure robustness. Stale
    # cleanup must run AFTER the corresponding new write succeeds, never
    # before — a write that fails partway must leave the previous run's
    # assets intact (neither old nor new would otherwise survive).
    # -----------------------------------------------------------------------

    def test_generate_nfo_failure_preserves_old_assets(self, tmp_path):
        """generate_nfo returning False → _write_movie_assets raises, and the
        OLD series (nfo/cover/poster/fanart) must all still be on disk — the
        card keeps its previously-usable asset set rather than losing both."""
        from core.readonly_paths import _build_old_base, _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config()
        _t4_write(movie_dir, meta_a, config)

        # 真理表 Table 2 #1：media-server flavour（首次產出）本來就沒有獨立同名 `.jpg`
        # ——迴圈只查三項（不含裸 `.jpg`）。
        d = Path(movie_dir)
        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'TEST-001 Title A{suffix}').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', return_value=False):
            with pytest.raises(RuntimeError):
                _write_movie_assets(
                    movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                    cover_strategy=_cover_strategy_for(meta_b), old_base=old_base,
                )

        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'TEST-001 Title A{suffix}').exists(), \
                f"old {suffix} must survive when generate_nfo fails"


    def test_cover_download_failure_title_drift_keeps_old_cover_but_cleans_nfo(self, tmp_path):
        """old_base != new_base, cover download fails this run → old cover
        (<old_base>.jpg) must survive (has_cover False gates the delete), but
        old NFO (<old_base>.nfo) IS cleaned since it always writes successfully
        and old_base differs from new_base."""
        from core.readonly_paths import _build_old_base, _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config()
        _t4_write(movie_dir, meta_a, config)

        # 真理表 Table 2 #1：media-server flavour 下正典即 `-fanart.jpg`，不是裸 `.jpg`。
        d = Path(movie_dir)
        assert (d / 'TEST-001 Title A-fanart.jpg').exists()
        assert (d / 'TEST-001 Title A.nfo').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)

        def failing_cover_download(url, save_path, referer=''):
            if save_path.endswith('.jpg') and 'extrafanart' not in save_path:
                return False
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'FAKE-IMG')
            return True

        with patch('core.readonly_assets.download_image', side_effect=failing_cover_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
            assets = _write_movie_assets(
                movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta_b), old_base=old_base,
            )

        assert assets['cover_fs'] == ''
        assert (d / 'TEST-001 Title A-fanart.jpg').exists(), \
            "old cover must survive when has_cover is False (title drift)"
        assert not (d / 'TEST-001 Title A.nfo').exists(), \
            "old nfo must be cleaned (nfo_ok guaranteed, old_base != new_base)"
        assert (d / 'TEST-001 Title B.nfo').exists()


# ---------------------------------------------------------------------------
# TASK-112b-T6 §C-6/§C-7/§C-8：CD-112-16 兩組語意分離的回歸鎖——本 branch
# 唯一自己製造的新 bug（112 之前不存在，見真理表 Table 2 #6a/#6b）。三支測試
# 都不 mock generate_nfo（真跑 core.organizer.generate_nfo 才能解析真實 tag
# 內容）。
# ---------------------------------------------------------------------------

class TestCd112_16NfoRegressionLock:
    _BASE = 'TEST-001 Same Title'

    def _first_full_write(self, tmp_path):
        """第一次：全新片、media-server flavour（_T3_BASE_CONFIG 預設
        'kodi'）→ 正典落 -fanart.jpg，has_poster=has_fanart=True。"""
        movie_dir = str(tmp_path / 'movie')
        meta = dict(_T3_META, title='Same Title')
        config = dict(_T3_BASE_CONFIG)
        _t4_write(movie_dir, meta, config)
        return movie_dir, meta, config

    def test_6a_second_call_preserve_hit_tags_point_to_existing_files(self, tmp_path):
        """Table 2 #6a（AC7 回歸鎖，**必須是兩次呼叫的形狀**——單次產出驗不到，
        第一次的 has_fanart 本來就是 True）：第二次對同一片跑 ovw=False 的補
        資料（cover_strategy=('none',) 模擬 preserve 命中）→ 重寫後的 NFO 三
        tag 全部指向實際存在的檔案（nfo_image_flag 探磁碟真相，不是裸
        has_poster/has_fanart）。

        MUTATION：把 core/readonly_producer.py:976-977 的
        `nfo_image_flag(base_stem, '-poster'/'-fanart', has_poster/has_fanart)`
        換回裸 `has_poster`/`has_fanart` → 這一支單獨轉紅（第二次 NFO 的
        <poster>/<fanart> 退回 {b}.jpg，該檔不存在）；off 情境與首次產出情境
        維持綠。
        """
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir, meta, config = self._first_full_write(tmp_path)
        d = Path(movie_dir)
        for suffix in ('-poster.jpg', '-fanart.jpg'):
            assert (d / f'{self._BASE}{suffix}').exists(), "sanity: first write produced both"

        fd = _format_data(meta, '/src/TEST-001.mp4', config)
        with patch('core.readonly_assets.download_image') as mock_download:
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('none',), old_base=self._BASE,
            )
        mock_download.assert_not_called()

        nfo_path = d / f'{self._BASE}.nfo'
        root = ET.parse(nfo_path).getroot()
        for tag in ('thumb', 'fanart', 'poster'):
            tag_value = root.findtext(tag)
            assert tag_value, f"<{tag}> must not be empty"
            assert (d / tag_value).exists(), (
                f"<{tag}>={tag_value!r} must point to an existing file after re-entry "
                "(CD-112-16 回歸鎖，Table 2 #6a)"
            )


class TestUpsertDb:
    """T-3: DB field correctness, cover_path local URI, sample_images local URIs."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'
    OUTPUT_DIR_URI = 'file:///output/TEST-001'  # non-empty (T3 contract: '' would CASE-WHEN no-op)

    def _repo(self, temp_db):
        from core.database import VideoRepository
        return VideoRepository(temp_db)

    def test_db_fields_correct(self, tmp_path, temp_db):
        """After _upsert_db, get_by_path returns Video with all expected fields."""
        from core.readonly_producer import _upsert_db
        from core.path_utils import to_file_uri

        cover_fs = str(tmp_path / 'output' / 'TEST-001' / 'TEST-001 Test Movie Title.jpg')
        assets = {'cover_fs': cover_fs, 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v is not None
        assert v.path == self.SOURCE_URI
        assert v.number == _T3_META['number']
        assert v.title == _T3_META['title']
        assert v.size_bytes == _T3_FILE_INFO['size']
        assert v.cover_path == to_file_uri(cover_fs, None)
        assert v.cover_path != _T3_META['cover']  # must not be the remote URL (CD-88b-7)
        assert v.actresses == _T3_META['actors']
        assert v.tags == _T3_META['tags']
        assert v.mtime == _T3_FILE_INFO['mtime']
        assert v.nfo_mtime == _T3_NFO_MTIME
        assert v.output_dir == self.OUTPUT_DIR_URI


    def test_scrape_attempted_at_set(self, temp_db):
        """89b-T2: _upsert_db writes scrape_attempted_at > 0 (success path marks 'attempted')."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.scrape_attempted_at > 0

    def test_original_title_written_from_meta(self, temp_db):
        """FIX#3: original_title must round-trip from meta into the DB row —
        the non-readonly path (core.enricher) already does this
        (_nfo_to_meta:65 / upsert:652); readonly_producer previously dropped
        it entirely (zero occurrences), silently wiping the field."""
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        meta = dict(_T3_META, original_title='日本語タイトル')
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, meta, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.original_title == '日本語タイトル'

    def test_readonly_upsert_has_plot_follows_summary(self, temp_db):
        """187b-T3：full 分支 has_plot 跟 meta['_summary']；空字串 → False。"""
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}

        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO,
            dict(_T3_META, _summary='有簡介'), assets, None, self.OUTPUT_DIR_URI,
        )
        assert repo.get_by_path(self.SOURCE_URI).has_plot is True

        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO,
            dict(_T3_META, _summary=''), assets, None, self.OUTPUT_DIR_URI,
        )
        assert repo.get_by_path(self.SOURCE_URI).has_plot is False


class TestUpsertDbFullModeExistingPreservation:
    """P1/P2 grok-review (pre-merge 2026-07-21): full mode's `existing` param
    mirrors core.enricher._db_upsert's PRESERVATION PATTERN — when THIS run's
    assets are empty, fall back to the existing DB row instead of clobbering it.
    Covers a full-mode RE-ENTRY of an already-produced video (gear rescrape /
    放大鏡 ingest / batch-enrich — all `assets_mode='full'`, and ingest/rescrape
    always pass `meta['sample_images']==[]` per CD-104-3, so `assets['sample_fs']`
    is always `[]` too on that path).

    MUTATION LOCK: reverting either preservation branch back to the old
    unconditional read (`assets['cover_fs']`/`assets['sample_fs']` verbatim,
    ignoring `existing`) turns the corresponding test below RED."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'
    OUTPUT_DIR_URI = 'file:///output/TEST-001'

    def _repo(self, temp_db):
        from core.database import VideoRepository
        return VideoRepository(temp_db)

    def _seed_existing(self, repo, cover_path='', sample_images=None):
        from core.database import Video
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            cover_path=cover_path, sample_images=sample_images or [],
            output_dir=self.OUTPUT_DIR_URI,
        ))

    # ── Finding #1 (P1): sample_images preserved on empty sample_fs ─────────

    def test_preserves_existing_sample_images_when_sample_fs_empty(self, temp_db):
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        old_samples = ['file:///output/TEST-001/extrafanart/fanart1.jpg',
                       'file:///output/TEST-001/extrafanart/fanart2.jpg']
        self._seed_existing(repo, sample_images=old_samples)
        existing = repo.get_by_path(self.SOURCE_URI)

        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == old_samples, (
            "full-mode re-entry with no new samples must preserve existing sample_images"
        )


    # ── Finding #2 (P2): cover_path preserved on empty cover_fs ─────────────

    def test_preserves_existing_cover_path_when_cover_fs_empty(self, temp_db):
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        self._seed_existing(repo, cover_path='file:///output/TEST-001/TEST-001.jpg')
        existing = repo.get_by_path(self.SOURCE_URI)

        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == 'file:///output/TEST-001/TEST-001.jpg', (
            "cover_strategy ('none',) / failed download must not clear an existing cover"
        )


    # ── FIX#3 (P2 parity closeout): original_title preserve-if-empty ────────


    def test_produce_one_preserves_original_title_in_nfo_and_db_when_rescrape_empty(self, temp_db, tmp_path):
        """FIX P1 (Codex PR#113 round-6): a re-produce whose meta has an EMPTY
        original_title must preserve the existing value in BOTH the on-disk output
        NFO's <originaltitle> AND the DB row. The round-5 fix preserved it only in
        _upsert_db, so _write_movie_assets→generate_nfo still wrote <originaltitle>
        as '' → on-disk data loss + NFO/DB drift. This drives the FULL _produce_one
        path with REAL generate_nfo and asserts the written file itself.

        MUTATION LOCK: removing the `meta['original_title'] = effective_original_title(...)`
        helper call (the synthesis in _produce_one) turns the NFO assertion below RED
        (DB stays green via _upsert_db's own effective_original_title call — which is
        exactly why the NFO assertion is the load-bearing one here)."""
        import xml.etree.ElementTree as ET
        from core.readonly_producer import _produce_one
        from core.database import Video
        from core.path_utils import to_file_uri

        repo = self._repo(temp_db)
        file_info = {'path': '/src/TEST-001.mp4', 'size': 1234567890, 'mtime': 1704067200.0}
        src_uri = to_file_uri(file_info['path'], {})
        repo.upsert(Video(
            path=src_uri, number='TEST-001', title='Existing Title',
            original_title='既存の原題',
        ))
        existing = repo.get_by_path(src_uri)

        meta = dict(_T3_META, original_title='')  # re-scrape source returned no original_title
        output_root = str(tmp_path / 'output')
        movie_dir, _assets = _produce_one(
            repo, None, _T3_BASE_CONFIG,
            file_info=file_info, meta=meta, cover_strategy=('none',),
            assets_mode='full', existing=existing,
            output_root=output_root, output_uri=to_file_uri(output_root, {}),
            allocated_this_run=set(), path_mappings={},
        )

        # DB row preserved
        assert repo.get_by_path(src_uri).original_title == '既存の原題'
        # On-disk output NFO preserved (the actual P1 — must not be clobbered to '')
        nfo_files = list(Path(movie_dir).glob('*.nfo'))
        assert len(nfo_files) == 1, f"expected exactly one NFO, got {nfo_files}"
        root = ET.parse(nfo_files[0]).getroot()
        assert root.findtext('originaltitle') == '既存の原題'


# ---------------------------------------------------------------------------
# T-4 tests: _emit helper + produce_source orchestrator
# ---------------------------------------------------------------------------

def _fake_to_file_uri(p, m=None):  # path-contract-ok
    """Fake to_file_uri for mocking in tests. path-contract-ok: this IS the mock target."""
    return "file:///" + p.lstrip("/")  # path-contract-ok


def _make_source(readonly=True, output_path="/output/dest", path="/src/videos"):
    """Return a MagicMock with source attributes."""
    src = MagicMock()
    src.readonly = readonly
    src.output_path = output_path
    src.path = path
    return src


def _make_config(scraper_cfg=None, gallery_cfg=None):
    return {
        "gallery": gallery_cfg or {},
        "scraper": scraper_cfg or {},
    }


def _make_file_info(path="/src/videos/ABC-123.mp4", size=1_000_000, mtime=1.0):
    return {"path": path, "size": size, "mtime": mtime, "nfo_mtime": 0.0}


class TestResolveOutputRoot:
    """TASK-89a-T2 (CD-89a-7): resolve_output_root(source, config) truth table.

    off (or unknown) → fixed App-managed folder under get_db_path().parent/"lib".
    jellyfin/emby/kodi → source.output_path verbatim (may be empty).
    """

    def test_off_with_empty_output_path_returns_fixed_root(self):
        from core.database import get_db_path
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="", path="/src/movies")
        config = _make_config()  # scraper_cfg={} → fallback 'off'

        result = resolve_output_root(source, config)

        assert result
        assert result.startswith(str(get_db_path().parent / "lib"))


    @pytest.mark.parametrize("mode", ["jellyfin", ])
    def test_media_server_modes_return_output_path_verbatim(self, mode):
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="/nas/media", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": mode})

        assert resolve_output_root(source, config) == "/nas/media"


    def test_two_sources_same_basename_do_not_collide(self):
        """B1: two off-mode sources whose folder basename would clash (same leaf
        directory name, different parent path) must resolve to different roots."""
        from core.readonly_paths import resolve_output_root

        config = _make_config()  # off
        source_a = _make_source(path="/mnt/driveA/MyDrive")
        source_b = _make_source(path="/mnt/driveB/MyDrive")

        result_a = resolve_output_root(source_a, config)
        result_b = resolve_output_root(source_b, config)

        assert result_a != result_b


class TestProduceSourceGuards:
    """Guard tests for produce_source (CD-88b-6 / Acceptance #11)."""


    def test_empty_output_path_returns_aborted(self):
        """media-server mode + source.output_path='' → aborted_reason='no_output_path',
        search_jav not called.

        TASK-89a-T2 (CD-89a-7): this guard is now flavour-dependent — off mode gets a
        structural fixed root and never aborts on empty output_path (see
        TestProduceSourceOffModeNeverAborts below), so this abort-path regression
        test must pin a media-server flavour to keep exercising the "still required"
        branch.
        """
        from core.readonly_producer import produce_source

        source = _make_source(output_path="")
        repo = MagicMock()
        config = _make_config(scraper_cfg={"external_manager": "jellyfin"})

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()        # early return blocked all downstream work
        mock_search.assert_not_called()


class TestProduceSourceUnreachable:
    """TASK-89b-T5 / CD-89b-5: reachable=False guard, placed before get_attempted_index()."""

    def test_unreachable_returns_aborted_reason(self):
        """reachable=False → aborted_reason='unreachable', zero counters, no DB/IO."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos") as mock_list:
            result = produce_source(source, config, repo, reachable=False)

        assert result.aborted_reason == "unreachable"
        assert result.created == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert result.no_scrape == 0
        assert result.outcomes == []
        mock_list.assert_not_called()
        repo.get_attempted_index.assert_not_called()


class TestProduceSourceOffModeNeverAborts:
    """TASK-89a-T2 (CD-89a-7): off flavour resolves to a structural fixed root, so
    produce_source must NEVER abort with no_output_path in off mode — this is the
    symmetric counterpart of TestProduceSourceGuards' three media-server abort tests
    (off + empty/whitespace/None source.output_path all behave identically because
    resolve_output_root ignores source.output_path entirely in off mode)."""

    @pytest.mark.parametrize("output_path", ["", ])
    def test_off_mode_empty_output_path_does_not_abort(self, output_path):
        from core.readonly_producer import produce_source

        source = _make_source(output_path=output_path)
        repo = MagicMock()
        config = _make_config()  # scraper_cfg={} → external_manager fallback 'off'

        with patch("core.readonly_producer._list_source_videos", return_value=[]) as mock_list, \
             patch.object(repo, "get_attempted_index", return_value={}):
            result = produce_source(source, config, repo)

        assert result.aborted_reason != "no_output_path"
        mock_list.assert_called_once()  # guard passed through to the listing step


class TestProduceSourceVideoExtensions:
    """produce_source honors user-configured scraper.video_extensions (PR#91 ④)."""

    def test_configured_extensions_passed_to_list(self):
        """A custom video_extensions config → _list_source_videos gets that exact set."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        # Custom, non-default extension list (normalized to a set by get_video_extensions)
        config = _make_config(scraper_cfg={"video_extensions": ["mp4", ".m2ts", "CUSTOM"]})

        with patch("core.readonly_producer._list_source_videos", return_value=[]) as mock_list, \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri):
            produce_source(source, config, repo)

        mock_list.assert_called_once()
        passed_exts = mock_list.call_args[0][1]
        assert passed_exts == {".mp4", ".m2ts", ".custom"}


class TestProduceSourceNoneNumberGuard:
    """extract_number returns None → no_scrape++, search_jav NOT called (Codex P2b)."""

    def test_none_number_no_search_jav(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [_make_file_info(path="/src/videos/nonnumber.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None) as mock_extract, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.no_scrape == 1
        assert result.created == 0
        mock_extract.assert_called_once()
        mock_search.assert_not_called()
        # T2: no-number branch always stubs a row (title = stem, number=None).
        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.number is None
        assert inserted.title == "nonnumber"
        repo.update_scrape_attempted_at.assert_called_once()
        repo.upsert.assert_not_called()


class TestProduceSourceSidecarNfoBypassesFilenameNumberBail:
    """Codex PR#113 P2 #1: a curated file whose FILENAME has no extractable
    number but whose adjacent .nfo sidecar carries <num>/<id>/<uniqueid> must
    still ingest — the old `if not number: continue` bailed BEFORE
    resolve_ingest_plan ever got a chance to read the NFO. MUTATION LOCK:
    reverting to that early bail must turn test_nfo_number_ingests_despite_no_filename_number
    RED (result.created goes 1 -> 0, result.no_scrape goes 0 -> 1)."""

    def test_nfo_number_ingests_despite_no_filename_number(self, tmp_path):
        """(a) no filename number + valid NFO with <num> -> INGESTS (created==1,
        no_scrape==0), zero network (search_jav never called)."""
        from core.readonly_producer import produce_source

        source_dir = tmp_path / 'src'
        source_dir.mkdir()
        output_dir = tmp_path / 'output'
        output_dir.mkdir()
        video = source_dir / 'nonumber.mp4'  # extract_number(basename) -> None
        video.write_bytes(b'FAKE-VIDEO-BYTES')
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SIDECAR-001</num><title>T</title></movie>', encoding='utf-8')

        source = _make_source(readonly=True, output_path=str(output_dir), path=str(source_dir))
        config = _make_config()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        repo.get_by_path.return_value = None
        repo.is_output_dir_taken.return_value = False
        repo.get_all.return_value = []

        files = [{'path': str(video), 'size': 1_000_000, 'mtime': 1.0, 'nfo_mtime': 0.0}]

        with patch('core.readonly_producer._list_source_videos', return_value=files), \
             patch('core.readonly_producer.search_jav') as mock_search:
            result = produce_source(source, config, repo)

        mock_search.assert_not_called()
        assert result.no_scrape == 0, f"expected 0 no_scrape, got {result.no_scrape} (created={result.created})"
        assert result.created == 1, f"expected NFO-driven ingest, got created={result.created}"
        repo.upsert.assert_called_once()
        upserted = repo.upsert.call_args[0][0]
        assert upserted.number == 'SIDECAR-001'


class TestProduceSourceNotFoundAttempted:
    """89b-T2: produce_source NOT-FOUND branch (search_jav→None, :637-641) writes a
    minimal placeholder row (insert_if_ignore) + marks scrape_attempted_at
    (update_scrape_attempted_at). Fixes Codex Finding-1 (showcase card '未知標題')."""

    def _run(self, repo, files=None):
        from core.readonly_producer import produce_source

        source = _make_source()
        config = _make_config()
        files = files if files is not None else [_make_file_info(path="/src/videos/NOTFOUND-001.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="NOTFOUND-001"), \
             patch("core.readonly_producer.search_jav", return_value=None):
            return produce_source(source, config, repo)

    def test_creates_minimal_row_and_marks_attempted(self):
        from core.database import Video

        repo = MagicMock()
        repo.insert_if_ignore.return_value = True

        result = self._run(repo)

        assert result.no_scrape == 1

        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert isinstance(inserted, Video)
        assert inserted.path == "file:///src/videos/NOTFOUND-001.mp4"
        assert inserted.number == "NOTFOUND-001"
        assert inserted.title == "NOTFOUND-001"
        # minimal row: no cover/folder-related fields populated
        assert inserted.cover_path == ''
        assert inserted.output_dir == ''
        assert inserted.sample_images == []

        repo.update_scrape_attempted_at.assert_called_once()
        call_args = repo.update_scrape_attempted_at.call_args[0]
        assert call_args[0] == "file:///src/videos/NOTFOUND-001.mp4"
        assert call_args[1] > 0


class TestProduceSourceNotFoundSecondRunSkipped:
    """TASK-89b-T3 DoD regression lock: a NOT-FOUND source (T2 marks
    scrape_attempted_at on the placeholder row) must be skipped on the very
    next produce_source call for the same file — real (unmocked) _should_skip
    reads the real get_attempted_index() from a real temp DB, so search_jav
    is never invoked a second time for it (CD-89b-3 cost-avoidance)."""

    def test_second_produce_source_call_skips_without_calling_search_jav(self, temp_db):
        from core.database import VideoRepository
        from core.readonly_producer import produce_source

        repo = VideoRepository(temp_db)
        source = _make_source()
        config = _make_config()
        files = [_make_file_info(path="/src/videos/NOTFOUND-001.mp4")]

        # Round 1: search_jav → None, T2 branch writes the placeholder row +
        # marks scrape_attempted_at (real DB write, _should_skip not mocked).
        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="NOTFOUND-001"), \
             patch("core.readonly_producer.search_jav", return_value=None) as mock_search_1:
            result1 = produce_source(source, config, repo)

        assert result1.no_scrape == 1
        assert result1.skipped == 0
        mock_search_1.assert_called_once()

        # Round 2: attempted_index (real repo.get_attempted_index() read) now
        # shows this source_uri as attempted>0 → real _should_skip returns
        # True, loop continues before ever reaching search_jav.
        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="NOTFOUND-001"), \
             patch("core.readonly_producer.search_jav") as mock_search_2:
            result2 = produce_source(source, config, repo)

        assert result2.skipped == 1
        assert result2.no_scrape == 0
        mock_search_2.assert_not_called()


class TestProduceSourceMixedStats:
    """5-file run: 2 skipped, 1 None-number, 1 search_jav→None, 1 success → check all counters."""

    FILES = [
        _make_file_info(path="/src/SKIP-001.mp4"),    # → skipped (cover exists)
        _make_file_info(path="/src/SKIP-002.mp4"),    # → skipped (cover exists)
        _make_file_info(path="/src/nonnumber.mp4"),   # → no_scrape (extract_number=None)
        _make_file_info(path="/src/NOSCRAPE-001.mp4"),  # → no_scrape (search_jav=None)
        _make_file_info(path="/src/SUCCESS-001.mp4"),   # → created
    ]

    def _run(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_by_path.return_value = None
        config = _make_config()

        def fake_should_skip(src_uri, attempted_index, force=False):
            return "SKIP-001" in src_uri or "SKIP-002" in src_uri

        def fake_extract_number(basename):
            if "nonnumber" in basename:
                return None
            return basename.replace(".mp4", "").upper()

        def fake_search_jav(number, source="auto", javbus_lang=None):
            if "NOSCRAPE" in number:
                return None
            return {"number": number, "title": "T", "cover": "", "actors": [], "tags": [],
                    "date": "", "maker": "", "director": "", "series": "", "label": "",
                    "sample_images": [], "duration": 0, "url": ""}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/SUCCESS-001"

        with patch("core.readonly_producer._list_source_videos", return_value=self.FILES), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", side_effect=fake_should_skip), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", side_effect=fake_extract_number), \
             patch("core.readonly_producer.search_jav", side_effect=fake_search_jav), \
             patch("core.readonly_paths._format_data", return_value={"number": "X", "title": "T", "actors": [], "maker": "", "date": "", "suffix": ""}), \
             patch("core.readonly_paths._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/SUCCESS-001")), \
             patch("core.readonly_assets._write_movie_assets", return_value={"cover_fs": "/output/dest/SUCCESS-001/cover.jpg", "sample_fs": []}), \
             patch("core.readonly_producer._upsert_db"):
            return produce_source(source, config, repo)

    def test_counters(self):
        result = self._run()
        assert result.skipped == 2
        assert result.no_scrape == 2
        assert result.created == 1
        assert result.failed == 0


class TestProduceSourceShouldAbort:
    """should_abort returning True on 3rd file → loop stops, len(outcomes)==2."""

    def test_abort_stops_loop(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [
            _make_file_info(path="/src/A.mp4"),
            _make_file_info(path="/src/B.mp4"),
            _make_file_info(path="/src/C.mp4"),
            _make_file_info(path="/src/D.mp4"),
        ]
        call_count = [0]

        def abort_on_third():
            call_count[0] += 1
            return call_count[0] >= 3  # abort on 3rd call (before 3rd file)

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None):
            result = produce_source(source, config, repo, should_abort=abort_on_third)

        assert len(result.outcomes) == 2


class TestProduceSourceExceptionDoesNotAbort:
    """Single-file exception doesn't abort loop: 2nd file raises, 3rd still processed."""

    def test_exception_on_second_file_third_still_processed(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_by_path.return_value = None
        config = _make_config()
        files = [
            _make_file_info(path="/src/A-001.mp4"),
            _make_file_info(path="/src/B-002.mp4"),  # will raise
            _make_file_info(path="/src/C-003.mp4"),
        ]

        meta = {"number": "X", "title": "T", "cover": "", "actors": [], "tags": [],
                "date": "", "maker": "", "director": "", "series": "", "label": "",
                "sample_images": [], "duration": 0, "url": ""}
        fd = {"number": "X", "title": "T", "actors": [], "maker": "", "date": "", "suffix": ""}

        call_count = [0]

        def fake_write(movie_dir, meta_arg, fd_arg, src_path, cfg, cover_strategy=None,
                      assets_mode='full', old_base='', strm_mappings_getter=None, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("disk full")
            return {"cover_fs": "", "sample_fs": [], "nfo_mtime": _T3_NFO_MTIME}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/X"

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_paths._format_data", return_value=fd), \
             patch("core.readonly_paths._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/X")), \
             patch("core.readonly_assets._write_movie_assets", side_effect=fake_write), \
             patch("core.readonly_producer._upsert_db"):
            result = produce_source(source, config, repo)

        assert result.failed == 1
        assert result.created == 2  # files 1 and 3 succeed
        statuses = [o.status for o in result.outcomes]
        assert statuses == ["created", "failed", "created"]


class TestProduceSourceFailureContract:
    """Required-asset failure → failed (not created), no upsert, fixed error message (P1/P2)."""

    def _run_with_write_failure(self, exc):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_by_path.return_value = None
        config = _make_config()
        files = [_make_file_info(path="/src/A-001.mp4")]
        meta = {"number": "X", "title": "T", "cover": "u", "actors": [], "tags": [],
                "date": "", "maker": "", "director": "", "series": "", "label": "",
                "sample_images": [], "duration": 0, "url": ""}
        fd = {"number": "X", "title": "T", "actors": [], "maker": "", "date": "", "suffix": ""}
        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/X"
        upsert_mock = MagicMock()

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_paths._format_data", return_value=fd), \
             patch("core.readonly_paths._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/X")), \
             patch("core.readonly_assets._write_movie_assets", side_effect=exc), \
             patch("core.readonly_producer._upsert_db", upsert_mock):
            result = produce_source(source, config, repo)
        return result, upsert_mock

    def test_required_asset_failure_counts_failed_and_skips_upsert(self):
        # NFO/required-asset write failure surfaces as RuntimeError from _write_movie_assets.
        result, upsert_mock = self._run_with_write_failure(RuntimeError("NFO write failed: /x"))
        assert result.failed == 1
        assert result.created == 0
        upsert_mock.assert_not_called()                 # never claim generated when NFO missing
        assert result.outcomes[0].status == "failed"


# ---------------------------------------------------------------------------
# T6 tests: DB-row-only prune (CD-89b-6)
# ---------------------------------------------------------------------------

class TestProduceSourcePrune:
    """TASK-89b-T6 (CD-89b-6): prune candidate推導 at the tail of produce_source.

    Gate = files (this-run list) non-empty AND result.skipped_paths empty
    (reachable is implicitly True — the unreachable guard already returned
    upstream). Candidates come from repo.get_all(), filtered to rows under
    the source root, with scrape_attempted_at>0 or output_dir set, and not
    present in this-run's URI set.
    """

    def _run(self, *, get_all_rows, this_run_files=None, on_skip_paths=None,
              delete_return=None, source_path="/src/videos"):
        from core.readonly_producer import produce_source

        source = _make_source(path=source_path)
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        repo.get_all.return_value = get_all_rows
        if delete_return is not None:
            repo.delete_by_paths.side_effect = None
            repo.delete_by_paths.return_value = delete_return
        else:
            repo.delete_by_paths.side_effect = lambda paths: len(paths)

        config = _make_config()
        files = this_run_files if this_run_files is not None else []

        def fake_list_source_videos(src_path, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None and on_skip_paths:
                for p in on_skip_paths:
                    on_skip(p, OSError("unreadable"))
            return files

        with patch("core.readonly_producer._list_source_videos", side_effect=fake_list_source_videos), \
             patch("core.readonly_producer._should_skip", return_value=True), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.thumbnail_cache") as mock_thumb:
            result = produce_source(source, config, repo)
        return result, repo, mock_thumb

    # -- fixture rows shared across tests --
    ROW_EXIST = SimpleNamespace(path="file:///src/videos/EXIST-001.mp4", scrape_attempted_at=1000.0, output_dir="")
    ROW_GONE_ATTEMPTED = SimpleNamespace(path="file:///src/videos/GONE-001.mp4", scrape_attempted_at=1000.0, output_dir="")
    ROW_GONE_PRODUCED = SimpleNamespace(path="file:///src/videos/PRODUCED-001.mp4", scrape_attempted_at=0, output_dir="/output/dest/x")
    ROW_NEVER_ATTEMPTED = SimpleNamespace(path="file:///src/videos/NEVER-001.mp4", scrape_attempted_at=0, output_dir="")
    ROW_OTHER_SOURCE = SimpleNamespace(path="file:///src/other/OTHER-001.mp4", scrape_attempted_at=1000.0, output_dir="x")

    def test_cross_source_and_attempted_produced_filter(self):
        """Only rows under this source's root, with attempted>0 or output_dir set,
        and absent from this-run's file list, become prune candidates. Rows under a
        different source root (ROW_OTHER_SOURCE) and rows that are neither attempted
        nor produced (ROW_NEVER_ATTEMPTED) must survive."""
        this_run_files = [_make_file_info(path="/src/videos/EXIST-001.mp4")]
        get_all_rows = [
            self.ROW_EXIST, self.ROW_GONE_ATTEMPTED, self.ROW_GONE_PRODUCED,
            self.ROW_NEVER_ATTEMPTED, self.ROW_OTHER_SOURCE,
        ]

        result, repo, mock_thumb = self._run(get_all_rows=get_all_rows, this_run_files=this_run_files)

        repo.delete_by_paths.assert_called_once()
        deleted = repo.delete_by_paths.call_args[0][0]
        assert set(deleted) == {self.ROW_GONE_ATTEMPTED.path, self.ROW_GONE_PRODUCED.path}
        assert result.pruned == 2


    def test_gate_false_when_skipped_paths_nonempty_no_prune(self):
        """partial-scan suppression: skipped_paths non-empty → zero DB/IO for prune,
        even though candidates would otherwise exist."""
        this_run_files = [_make_file_info(path="/src/videos/EXIST-001.mp4")]
        get_all_rows = [self.ROW_EXIST, self.ROW_GONE_ATTEMPTED]

        result, repo, mock_thumb = self._run(
            get_all_rows=get_all_rows, this_run_files=this_run_files,
            on_skip_paths=["/src/videos/broken_dir"],
        )

        repo.get_all.assert_not_called()
        repo.delete_by_paths.assert_not_called()
        mock_thumb.invalidate.assert_not_called()
        assert result.pruned == 0
        assert result.skipped_paths == ["/src/videos/broken_dir"]

    def test_gate_false_when_files_empty_no_prune(self):
        """Empty this-run list (e.g. truly empty source directory) → do not prune;
        cannot distinguish 'genuinely emptied' from 'scan came back oddly empty'."""
        get_all_rows = [self.ROW_GONE_ATTEMPTED]

        result, repo, mock_thumb = self._run(get_all_rows=get_all_rows, this_run_files=[])

        repo.get_all.assert_not_called()
        repo.delete_by_paths.assert_not_called()
        assert result.pruned == 0


    def test_should_abort_midloop_does_not_prune_untouched_files(self):
        """Anti-misdelete lock (CD-89b-6 §2, 本次列表用 files 非 outcomes).

        When should_abort breaks the loop mid-way, files that were enumerated but
        never processed are STILL present on disk and STILL in the raw `files`
        scan list — so their DB rows must NOT be pruned. If the prune derived its
        this-run set from processed/emitted outcomes instead of `files`, those
        untouched-but-present files would be misclassified as vanished and
        deleted — silent data loss. The other prune tests can't catch this
        because they patch _should_skip=True (every file gets emitted, so
        outcomes == files); only a should_abort mid-loop break makes
        outcomes ⊊ files. Mutating the prune to use processed items → this RED.
        """
        from core.readonly_producer import produce_source

        source = _make_source(path="/src/videos")
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        # A, B, C all still exist on disk AND have (attempted) rows in the DB.
        rows = [
            SimpleNamespace(path="file:///src/videos/A-001.mp4", scrape_attempted_at=1000.0, output_dir=""),
            SimpleNamespace(path="file:///src/videos/B-002.mp4", scrape_attempted_at=1000.0, output_dir=""),
            SimpleNamespace(path="file:///src/videos/C-003.mp4", scrape_attempted_at=1000.0, output_dir=""),
        ]
        repo.get_all.return_value = rows
        repo.delete_by_paths.side_effect = lambda paths: len(paths)

        config = _make_config()
        files = [
            _make_file_info(path="/src/videos/A-001.mp4"),
            _make_file_info(path="/src/videos/B-002.mp4"),
            _make_file_info(path="/src/videos/C-003.mp4"),
        ]

        def fake_list_source_videos(src_path, extensions, min_size_bytes, on_skip=None):
            return files

        # should_abort is checked at the top of each iteration: let A through
        # (call 1 → False), then break before B/C are ever touched (call 2 → True).
        abort_calls = {"n": 0}

        def fake_should_abort():
            abort_calls["n"] += 1
            return abort_calls["n"] > 1

        with patch("core.readonly_producer._list_source_videos", side_effect=fake_list_source_videos), \
             patch("core.readonly_producer._should_skip", return_value=True), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.thumbnail_cache") as mock_thumb:
            result = produce_source(source, config, repo, should_abort=fake_should_abort)

        # B and C were never processed but ARE in `files` → this_run_uris covers
        # all three → zero candidates → zero deletion. No data loss on abort.
        repo.delete_by_paths.assert_not_called()
        mock_thumb.invalidate.assert_not_called()
        assert result.pruned == 0
        assert result.pruned == 0


# ---------------------------------------------------------------------------
# TASK-90a-T3: _apply_path_mapping + _write_strm + stale strm cleanup
# ---------------------------------------------------------------------------

class TestApplyPathMapping:
    """file:/// URI-space prefix-swap: boundary-anchored, longest-match,
    order-independent. source+local_prefix converge via to_file_uri for MATCHING
    (Codex P1/P2 fix); remote result written verbatim, never normalized (CD-90a-6)."""


    def test_single_match_windows_separator(self):
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '/volume1/movie'})
        assert out == '/volume1/movie/x.mp4'  # remainder from URI space (forward-slash)


    def test_trailing_separator_in_local_prefix_still_matches(self):
        """Codex P2: a local_prefix carrying a trailing separator ('/mnt/z/115/')
        must still match — the URI form is rstrip'd of '/'. Raw-string compare
        would have missed (source lacks the doubled sep) and returned unchanged."""
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('/mnt/z/115/x.mp4', {'/mnt/z/115/': '/vol'})
        assert out == '/vol/x.mp4'

    def test_cross_namespace_windows_prefix_matches_wsl_source(self):
        """Codex P1: a Windows-DISPLAY prefix ('C:\\115', as pathToDisplay prefills)
        must match a WSL-NATIVE source ('/mnt/c/115/x.mp4') — both converge to
        file:///C:/115 in URI space. Raw-string compare would have silently missed
        and written the un-mapped source. Host-independent (green on Linux CI + WSL:
        to_file_uri's /mnt & drive-letter branches are not env-gated)."""
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('/mnt/c/115/x.mp4', {'C:\\115': '/volume1'})
        assert out == '/volume1/x.mp4'


class TestWriteStrm:
    """_write_strm: media-server sidecar, single-line utf-8 no-BOM, best-effort,
    same-level strm_path_mappings read."""

    def test_writes_mapped_content_single_line_no_bom(self, tmp_path):
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001 Title')
        config = {'strm_path_mappings': {'Z:\\115': '/volume1/movie'}}
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config)
        assert ok is True
        strm = Path(base_stem + '.strm')
        assert strm.exists()
        raw = strm.read_bytes()
        assert not raw.startswith(b'\xef\xbb\xbf'), "must not write a UTF-8 BOM"
        content = strm.read_text(encoding='utf-8')
        assert not content.startswith('﻿')
        assert '\n' not in content, "strm must be a single line"
        assert content == '/volume1/movie/x.mp4'


    # --- PR #93 五審四次 P2 (option C)：strm_mappings 覆寫參數 ---


    def test_write_failure_is_best_effort_returns_false(self, tmp_path):
        """open() raising → warning logged, returns False, does NOT raise."""
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        with patch('core.readonly_assets.open', side_effect=OSError('disk full'), create=True):
            ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {})
        assert ok is False
        assert not Path(base_stem + '.strm').exists()


class TestWriteMovieAssetsStrmDrift:
    """Integration: title drift under a media-server flavour removes the old strm
    and leaves only the new one (Emby double-entry prevention)."""

    def test_title_drift_removes_old_strm_keeps_new(self, tmp_path):
        from core.readonly_paths import _build_old_base
        movie_dir = str(tmp_path / 'TEST-001')
        config = dict(_T3_BASE_CONFIG, external_manager='emby',
                      strm_path_mappings={'/src': '/volume1'})
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')

        _t4_write(movie_dir, meta_a, config)
        d = Path(movie_dir)
        assert (d / 'TEST-001 Title A.strm').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        _t4_write(movie_dir, meta_b, config, old_base=old_base)

        assert not (d / 'TEST-001 Title A.strm').exists(), "old strm must be removed on title drift"
        assert (d / 'TEST-001 Title B.strm').exists(), "new strm must be present"


# ---------------------------------------------------------------------------
# TASK-90a-T6: media-server strm 整合驗收 (spec-90 §90a.4 acceptance 1/2/7 + regression)
#
# End-to-end through the REAL produce_source path: real main loop, real
# _resolve_movie_dir (folder allocation), real _write_movie_assets + _write_strm
# (real file writes), real _upsert_db (captured via repo.upsert), real to_file_uri /
# extract_number / _format_data. Only the external scrape (search_jav) and image I/O
# (download_image / generate_jellyfin_images / generate_nfo) are mocked — the same
# boundary every existing e2e test uses. _list_source_videos is patched to return
# file_info dicts pointing at REAL files under the tmp source dir, so the zero-write
# acceptance (7) is still real: the true _write_movie_assets(fi["path"], ...) runs
# against the real source path.
#
# Acceptance 3 (Emby/Jellyfin live scan) is inherently manual — see the TASK card's
# manual checklist; it has no pure-automation form here.
# ---------------------------------------------------------------------------


def _e2e_search_jav_factory():
    """Return a search_jav stub yielding per-number meta (cover + 1 sample)."""
    def fake_search_jav(number, source="auto", javbus_lang=None):
        return {
            'number': number,
            'title': f'Title {number}',
            'cover': f'https://example.com/{number}/cover.jpg',
            'actors': ['Actress A'],
            'tags': ['tag1'],
            'date': '2024-01-01',
            'maker': 'Maker',
            'director': 'Director',
            'series': 'Series',
            'label': 'Label',
            'sample_images': [f'https://example.com/{number}/s1.jpg'],
            'duration': 120,
            '_summary': 'summary',
            '_rating': 8.0,
            'url': f'https://example.com/{number}',
        }
    return fake_search_jav


def _e2e_run_produce_source(source_dir, output_dir, config, filenames, strm_mappings_getter=None):
    """Run the REAL produce_source against real source files in source_dir.

    Returns (result, repo). repo is a MagicMock whose .upsert captured the Video
    rows. _list_source_videos is patched to return file_info dicts for the real
    files (so _write_movie_assets/_write_strm run against the real source paths).

    strm_mappings_getter forwarded to produce_source (PR #93 五審四次 P2, option C).
    """
    from core.readonly_producer import produce_source

    source = _make_source(
        readonly=True,
        output_path=str(output_dir),
        path=str(source_dir),
    )
    repo = MagicMock()
    repo.get_attempted_index.return_value = {}
    repo.get_by_path.return_value = None
    repo.is_output_dir_taken.return_value = False  # else _resolve_movie_dir loops forever
    repo.get_all.return_value = []

    files = [
        {'path': str(source_dir / fn), 'size': 1_000_000, 'mtime': 1.0, 'nfo_mtime': 0.0}
        for fn in filenames
    ]

    with patch('core.readonly_producer._list_source_videos', return_value=files), \
         patch('core.readonly_producer.search_jav', side_effect=_e2e_search_jav_factory()), \
         patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
         patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
        result = produce_source(source, config, repo, strm_mappings_getter=strm_mappings_getter)
    return result, repo


def _snapshot_dir(root: Path) -> set:
    """Set of every path (files + dirs) under root, for before/after comparison."""
    return {str(p) for p in root.rglob('*')}


def _movie_dirs(output_dir: Path) -> list:
    """The per-movie asset folders (parents of each written .nfo).

    The producer nests each movie under folder layers (e.g. output/<num>/<num>/),
    so the leaf asset folder is the parent of the .nfo, not an immediate subdir.
    """
    return sorted({p.parent for p in output_dir.rglob('*.nfo')})


class TestProduceSourceMediaServerStrmE2E:
    """spec-90 §90a.4 acceptance 1/2/7 + regression, end-to-end through produce_source."""

    FILENAMES = ['SSIS-001.mp4', 'MIDE-002.mp4']

    def _setup_source(self, tmp_path):
        """Create a real read-only source dir with two real video files."""
        source_dir = tmp_path / 'readonly-src'
        source_dir.mkdir()
        for fn in self.FILENAMES:
            (source_dir / fn).write_bytes(b'FAKE-VIDEO-BYTES')
        output_dir = tmp_path / 'output'
        output_dir.mkdir()
        return source_dir, output_dir

    # -- Acceptance 1: every movie folder has strm + nfo + cover ------------------

    def test_acceptance1_each_movie_dir_has_strm_nfo_cover(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(_T3_BASE_CONFIG, external_manager='jellyfin'))

        result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2, f"expected 2 created, got {result.created} (failed={result.failed})"
        dirs = _movie_dirs(output_dir)
        assert len(dirs) == 2, f"expected 2 movie folders, got {[d.name for d in dirs]}"
        for d in dirs:
            strms = list(d.glob('*.strm'))
            nfos = list(d.glob('*.nfo'))
            covers = list(d.glob('*.jpg'))  # base .jpg + -poster.jpg + -fanart.jpg
            assert len(strms) == 1, f"{d.name}: expected exactly 1 .strm, got {strms}"
            assert len(nfos) == 1, f"{d.name}: expected exactly 1 .nfo, got {nfos}"
            assert any(c.name.endswith('-poster.jpg') for c in covers), f"{d.name}: no poster"
            assert any(c.name.endswith('-fanart.jpg') for c in covers), f"{d.name}: no fanart"
            # 真理表 Table 2 #1（反向鎖）：正典封面本身就是 `-fanart.jpg`，沒有第三張
            # 獨立的同名 base cover——只有 poster + fanart 兩個 `.jpg` 檔。
            assert len(covers) == 2, f"{d.name}: expected exactly poster+fanart, got {[c.name for c in covers]}"

    # -- Acceptance 2: strm content = mapped path (raw when no rule) --------------

    def test_acceptance2_strm_content_no_mapping_is_raw_source_path(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        # jellyfin flavour, NO mapping rule → strm = the raw source FS path.
        config = _make_config(scraper_cfg=dict(_T3_BASE_CONFIG, external_manager='jellyfin'))

        result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2
        strm_contents = {}
        for d in _movie_dirs(output_dir):
            strm = d.glob('*.strm').__next__()
            raw = strm.read_bytes()
            assert not raw.startswith(b'\xef\xbb\xbf'), "strm must not have a UTF-8 BOM"
            content = strm.read_text(encoding='utf-8')
            assert '\n' not in content, "strm must be a single line"
            strm_contents[d.name] = content
        # each strm points at the real source file's raw path (unchanged, un-normalized)
        expected = {str(source_dir / fn) for fn in self.FILENAMES}
        assert set(strm_contents.values()) == expected, (
            f"strm contents {strm_contents} must equal raw source paths {expected}"
        )

    def test_acceptance2_strm_content_with_mapping_is_prefix_swapped(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        # A mapping rule: local source root → playback-side /volume1 prefix.
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG,
            external_manager='jellyfin',
            strm_path_mappings={str(source_dir): '/volume1'},
        ))

        result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2
        contents = {d.glob('*.strm').__next__().read_text(encoding='utf-8')
                    for d in _movie_dirs(output_dir)}
        # prefix str(source_dir) swapped for /volume1, remainder appended verbatim,
        # NOT normalized (CD-90a-6: bare Unix target survives on any host).
        expected = {f'/volume1/{fn}' for fn in self.FILENAMES}
        assert contents == expected, f"mapped strm contents {contents} != {expected}"

    # -- PR #93 五審四次 P2 (option C): fresh strm mapping getter per file ---------


    # -- Acceptance 7: zero writes into the read-only source dir ------------------

    def test_acceptance7_readonly_source_zero_writes(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG,
            external_manager='jellyfin',
            strm_path_mappings={str(source_dir): '/volume1'},
        ))

        before = _snapshot_dir(source_dir)
        result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)
        after = _snapshot_dir(source_dir)

        assert result.created == 2, "sanity: run must actually produce (else zero-write is vacuous)"
        assert before == after, (
            f"read-only source dir was modified: added={after - before}, removed={before - after}"
        )
        # and the output actually got written (proves the run wrote SOMEWHERE, just not source)
        assert _movie_dirs(output_dir), "output dir empty — run did not write assets anywhere"


    # -- Regression: DB path = source path, strm does not touch streaming key -----

    def test_regression_upsert_path_is_source_uri_not_output_or_strm(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG,
            external_manager='jellyfin',
            strm_path_mappings={str(source_dir): '/volume1'},
        ))

        result, repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2
        upserted = [call.args[0] for call in repo.upsert.call_args_list]
        assert len(upserted) == 2, f"expected 2 upserts, got {len(upserted)}"
        upserted_paths = {v.path for v in upserted}
        # streaming key = the SOURCE file URI (spec §90a.2.2), never the output folder
        # or the strm's mapped /volume1 target.
        expected_paths = {to_file_uri(str(source_dir / fn)) for fn in self.FILENAMES}
        assert upserted_paths == expected_paths, (
            f"DB path {upserted_paths} must equal source URIs {expected_paths}"
        )
        for v in upserted:
            assert str(output_dir) not in v.path, "DB path must not point into the output folder"
            assert '/volume1' not in v.path, "DB path must not be the strm's mapped playback path"
            # output_dir column DOES record where it was produced (that's fine, separate field)
            assert v.output_dir, "output_dir column should be recorded (non-empty file:/// URI)"

    # -- off comparison: media-server-only, off flavour writes NO strm -----------

    def test_off_flavour_produces_no_strm(self, tmp_path):
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(_T3_BASE_CONFIG, external_manager='off'))

        # off flavour's resolve_output_root ignores output_path and returns the fixed
        # App lib root; patch it to the tmp output dir so the test never pollutes the
        # real lib folder (resolve_output_root has its own dedicated tests).
        with patch('core.readonly_paths.resolve_output_root', return_value=str(output_dir)):
            result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2, f"off run must still produce (created={result.created})"
        dirs = _movie_dirs(output_dir)
        assert len(dirs) == 2
        for d in dirs:
            assert not list(d.glob('*.strm')), f"off flavour must not write a .strm in {d.name}"
            # but the off assets are still there (nfo + cover) — strm is the only delta
            assert list(d.glob('*.nfo')), f"off flavour still writes nfo in {d.name}"


# ---------------------------------------------------------------------------
# TASK-110b-T5 (CD-110b-2/CD-110b-8): containment checkpoint wired into
# _write_movie_assets from _produce_one's output_root. End-to-end through the
# REAL produce_source pipeline (real tmp filesystem, real _resolve_movie_dir/
# _write_movie_assets — nothing about the containment path itself is mocked)
# so a rejection is proven by an actual before/after directory snapshot diff,
# not by asserting an exception was raised (feedback_reproduce_over_reasoning).
# ---------------------------------------------------------------------------

class TestWriteMovieAssetsContainment:
    """Scraped metadata containing '..' in the folder_layers template (`parts`)
    must never let movie_dir land outside output_root — this is case 1 (multi-
    layer actor escape) below, end-to-end through produce_source's REAL
    _resolve_movie_dir allocate loop AND the real containment checkpoint
    (which lives in _produce_one, right after _resolve_movie_dir returns —
    see TestProduceOneContainmentCheckpoint below for why it is NOT inside
    _write_movie_assets: that function has exactly one production caller,
    _produce_one, so checking at that call site is production-equivalent and
    needs no new parameter on _write_movie_assets at all).

    Case 2 (F2: the leaf itself, sanitize_filename(format_data['number']))
    is deliberately tested SEPARATELY (TestProduceOneContainmentCheckpoint
    below), by patching _resolve_movie_dir to directly return an escaping
    movie_dir, rather than through produce_source's real allocate loop: a
    leaf-only '..' with empty folder_layers always resolves (via realpath, at
    OS-syscall time) to output_root's own parent — which, for any real
    configured output root, reliably already exists — so
    _resolve_movie_dir's PRE-EXISTING candidate_fs.exists() collision-retry
    silently deflects it into a harmless literal `..-2` sibling folder INSIDE
    output_root before ever producing a movie_dir that would trip the
    checkpoint (empirically confirmed: running that exact metadata/config
    combo through produce_source yields `created=1`, not a rejection — no
    real escape occurs in that configuration). That self-healing is real but
    incidental (it depends on collision-retry behaviour this task must not
    touch or rely on) — it must not be mistaken for this task's containment
    guarantee. Patching _resolve_movie_dir's return value directly proves F2's
    "leaf is already inside movie_dir, one checkpoint suffices" holds even
    with nothing upstream offering any protection at all (e.g. a future
    refactor of _resolve_movie_dir's collision logic, or the read-and-reuse
    branch, whose own existing is_path_under_dir gate is a DIFFERENT,
    already-landed mechanism) — it locks the checkpoint itself, independent
    of whether any particular escape vector can survive the allocate loop.

    workspace/l1/l2/output gives two levels of headroom above output_dir, so
    case 1's 2-level-then-descend escape lands inside `workspace` — the
    region snapshotted here for containment — instead of splattering the real
    pytest tmp root above it.
    """

    FILENAME = 'ABC-001.mp4'

    def _setup(self, tmp_path):
        workspace = tmp_path / 'ws'
        source_dir = workspace / 'readonly-src'
        source_dir.mkdir(parents=True)
        (source_dir / self.FILENAME).write_bytes(b'FAKE-VIDEO-BYTES')
        output_dir = workspace / 'l1' / 'l2' / 'output'
        output_dir.mkdir(parents=True)
        return workspace, source_dir, output_dir

    def _run(self, tmp_path, meta_overrides, scraper_overrides=None):
        workspace, source_dir, output_dir = self._setup(tmp_path)
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG, external_manager='jellyfin',
            **(scraper_overrides or {}),
        ))
        source = _make_source(readonly=True, output_path=str(output_dir), path=str(source_dir))
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        repo.get_by_path.return_value = None
        repo.is_output_dir_taken.return_value = False
        repo.get_all.return_value = []
        files = [{'path': str(source_dir / self.FILENAME), 'size': 1_000_000, 'mtime': 1.0, 'nfo_mtime': 0.0}]

        def fake_search_jav(number, source="auto", javbus_lang=None):
            meta = {
                'number': number,
                'title': 'Normal Title',
                'cover': 'https://example.com/cover.jpg',
                'actors': ['Actress A'],
                'tags': [], 'date': '2024-01-01', 'maker': 'Maker',
                'director': '', 'series': '', 'label': '',
                'sample_images': [], 'duration': 120,
                '_summary': '', '_rating': None, 'url': '',
            }
            meta.update(meta_overrides)
            return meta

        workspace_before = _snapshot_dir(workspace)
        source_before = _snapshot_dir(source_dir)

        from core.readonly_producer import produce_source
        with patch('core.readonly_producer._list_source_videos', return_value=files), \
             patch('core.readonly_producer.search_jav', side_effect=fake_search_jav), \
             patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
            result = produce_source(source, config, repo)

        workspace_after = _snapshot_dir(workspace)
        source_after = _snapshot_dir(source_dir)
        return result, repo, output_dir, workspace_before, workspace_after, source_before, source_after

    def test_multi_layer_actor_escape_rejected_zero_writes_outside_root(self, tmp_path):
        """Case 1: actors=['..', '..'] behind a 2-layer folder_layers template
        (both layers resolve to actors[0] via format_string's {actor} token) —
        the allocate branch's `parts` carries the escape."""
        result, repo, output_dir, ws_before, ws_after, src_before, src_after = self._run(
            tmp_path,
            meta_overrides={'actors': ['..', '..']},
            scraper_overrides={'folder_layers': ['{actor}', '{actor}']},
        )

        assert result.created == 0, "escaping metadata must not be counted as created"
        assert result.failed == 1, "rejection must be a single-file failure, not an abort"
        new_paths = ws_after - ws_before
        outside_output = {p for p in new_paths if not p.startswith(str(output_dir))}
        assert outside_output == set(), f"escaped writes outside output_root: {outside_output}"
        assert src_before == src_after, "read-only source dir must not be written to"
        repo.upsert.assert_not_called()

    def test_normal_metadata_with_dot_in_title_still_produces(self, tmp_path):
        """Negative control: a legit title containing a single '.' (not '..')
        must not false-positive the containment checkpoint."""
        result, repo, output_dir, ws_before, ws_after, src_before, src_after = self._run(
            tmp_path,
            meta_overrides={'title': 'Vol. 2 Special Edition'},
        )

        assert result.created == 1, f"expected 1 created, got {result.created} (failed={result.failed})"
        dirs = _movie_dirs(output_dir)
        assert len(dirs) == 1
        assert src_before == src_after, "read-only source dir must not be written to"
        repo.upsert.assert_called_once()

    def test_unc_bare_share_root_movie_dir_allowed(self, monkeypatch):
        """UNC bare share root output_root：movie_dir 在同一共用根底下時必須放行。

        TASK-147a-T2 / CD-147a-7：直接呼叫 _produce_one() 的 containment checkpoint
        （mock _resolve_movie_dir 回傳值，不跑完整 allocate loop），用 Windows-style
        mock harness 真的驅動 is_fs_path_under_dir——不得 mock 該函式本身。
        斷言不再 raise RuntimeError，且 _write_movie_assets 有被呼叫到。
        """
        import ntpath
        import types
        import core.path_utils as path_utils
        from core.readonly_producer import _produce_one
        from tests.unit.test_path_utils import _PartialOsPathProxy

        fake_os = types.SimpleNamespace(path=_PartialOsPathProxy(
            realpath=ntpath.realpath,
            normcase=ntpath.normcase,
            sep=ntpath.sep,
        ))
        monkeypatch.setattr(path_utils, 'os', fake_os)

        output_root = r'\\server\share'
        movie_dir = r'\\server\share\ABC-001'
        meta = dict(_T3_META, number='ABC-001')
        file_info = {'path': '/src/ABC-001.mp4', 'size': 1_000_000, 'mtime': 1.0}
        repo = MagicMock()

        with patch('core.readonly_paths._resolve_movie_dir',
                   return_value=(movie_dir, 'file:///whatever-db-uri')), \
             patch('core.readonly_assets._write_movie_assets',
                   return_value={'nfo_mtime': 1.0, 'cover_fs': '', 'sample_fs': []}) as mock_write, \
             patch('core.readonly_producer._upsert_db'):
            _produce_one(
                repo, MagicMock(), dict(_T3_BASE_CONFIG, external_manager='jellyfin'),
                file_info=file_info, meta=meta, cover_strategy=_cover_strategy_for(meta),
                assets_mode='full', existing=None,
                output_root=output_root, output_uri='file:///unc-dummy',
                allocated_this_run=set(), path_mappings={},
            )

        mock_write.assert_called_once()


# ---------------------------------------------------------------------------
# TASK-99b-T1: post-loop bulk focal pass (CD-99b-1/2/7/8, spec §3.10)
#
# Real sqlite temp DB (CD-99b-6, no repo mock) + real produce_source loop
# (real file writes for cover/nfo via the same _t4_real_* stubs as the T6
# media-server e2e suite above). Only maybe_submit_video_focal is faked
# (fire-and-forget collection, per TASK-99b-T1 card) — requires_face_detection
# and get_empty_focal_candidates run for real against the real DB.
# ---------------------------------------------------------------------------


def _focal_setup_source(tmp_path, filenames):
    """Create a real read-only source dir with real (empty-content) video files."""
    source_dir = tmp_path / 'focal-src'
    source_dir.mkdir()
    for fn in filenames:
        (source_dir / fn).write_bytes(b'FAKE-VIDEO-BYTES')
    output_dir = tmp_path / 'focal-output'
    output_dir.mkdir()
    return source_dir, output_dir


def _focal_run_produce_source(source_dir, output_dir, repo, filenames, *, should_abort=None):
    """Run the REAL produce_source against a REAL VideoRepository(temp_db).

    Mirrors _e2e_run_produce_source (T6 suite) but takes a real repo instance
    instead of a MagicMock, so get_empty_focal_candidates / get_by_path /
    get_all all hit the real temp DB — required by CD-99b-6 for the focal
    pass under test.
    """
    from core.readonly_producer import produce_source

    source = _make_source(readonly=True, output_path=str(output_dir), path=str(source_dir))
    files = [
        {'path': str(source_dir / fn), 'size': 1_000_000, 'mtime': 1.0, 'nfo_mtime': 0.0}
        for fn in filenames
    ]
    config = _make_config(scraper_cfg=dict(_T3_BASE_CONFIG))

    with patch('core.readonly_producer._list_source_videos', return_value=files), \
         patch('core.readonly_producer.search_jav', side_effect=_e2e_search_jav_factory()), \
         patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
         patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
        result = produce_source(source, config, repo, should_abort=should_abort)
    return result


class TestProduceSourceFocalTrigger:
    """TASK-99b-T1 DoD ①③④⑤⑦⑧⑨ (DoD ② has its own class below — needs a
    pre-seeded skipped row, different setup shape than a fresh e2e run)."""

    def test_new_uncensored_file_submitted_with_correct_args(self, tmp_path, temp_db):
        """DoD ①: a newly-produced no-mosaic file (SIRO-* → shirouto/amateur gate
        True) is picked up by the post-loop bulk pass and submitted with the
        right (number, maker, path_uri, cover_fs, db_path) — not just 'submitted
        with anything'."""
        from core.database import VideoRepository
        from core.path_utils import to_file_uri

        source_dir, output_dir = _focal_setup_source(tmp_path, ['SIRO-001.mp4'])
        repo = VideoRepository(temp_db)

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(source_dir, output_dir, repo, ['SIRO-001.mp4'])

        assert result.created == 1
        mock_submit.assert_called_once()
        args, kwargs = mock_submit.call_args
        number, maker, path_uri, cover_fs = args
        assert number == 'SIRO-001'
        assert maker == 'Maker'
        assert path_uri == to_file_uri(str(source_dir / 'SIRO-001.mp4'))
        assert cover_fs, "cover_fs must not be empty — a cover was actually downloaded"
        assert kwargs.get('db_path') == repo.db_path  # DoD ⑧


    def test_abort_midloop_zero_submits_and_candidates_never_queried(self, tmp_path, temp_db):
        """DoD ⑤: should_abort flips True after the 2nd file → the ENTIRE bulk
        focal pass is skipped for this run — not just 'nothing submitted'.
        Asserting only submit-call-count==0 would pass even if a broken
        implementation still queried candidates (e.g. none matched the gate by
        coincidence); this test also spies get_empty_focal_candidates itself
        (card's 'may 1 fikang' warning) to close that hole. Prune must still run
        despite the abort (CD-99b-8: gate focal only, never `return`)."""
        from core.database import VideoRepository

        filenames = ['SIRO-010.mp4', 'SIRO-011.mp4', 'SIRO-012.mp4']
        source_dir, output_dir = _focal_setup_source(tmp_path, filenames)
        repo = VideoRepository(temp_db)
        # Spy (not stub) get_all / get_empty_focal_candidates so the real
        # prune / candidate-query behaviour is unchanged but call counts are
        # observable.
        real_get_all = repo.get_all
        real_get_candidates = repo.get_empty_focal_candidates
        get_all_spy = MagicMock(side_effect=real_get_all)
        get_candidates_spy = MagicMock(side_effect=real_get_candidates)
        repo.get_all = get_all_spy
        repo.get_empty_focal_candidates = get_candidates_spy

        call_count = [0]

        def abort_after_two():
            call_count[0] += 1
            return call_count[0] > 2  # let files 1 and 2 through, break before file 3

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(
                source_dir, output_dir, repo, filenames, should_abort=abort_after_two)

        assert result.created == 2, "sanity: abort happened mid-loop, not before any work"
        mock_submit.assert_not_called()
        get_candidates_spy.assert_not_called()  # bulk query itself must not run once aborted
        get_all_spy.assert_called_once()  # prune must still run despite the focal-pass abort


class TestProduceSourceFocalTriggerBulkGate:
    """TASK-99b-T1 DoD ② (CD-99b-2): the bulk gate must catch EXISTING rows that
    _should_skip lets through (already scraped, still empty-focal, never
    detected) — not just rows freshly upserted this run. This is the whole
    reason a per-item hook is insufficient (0.12's existing readonly libraries
    are all `skipped`, never `created`)."""

    def test_should_skip_row_still_gets_submitted_by_bulk_pass(self, tmp_path, temp_db):
        from core.database import VideoRepository, Video
        from core.path_utils import to_file_uri

        filenames = ['SIRO-040.mp4']
        source_dir, output_dir = _focal_setup_source(tmp_path, filenames)
        video_uri = to_file_uri(str(source_dir / 'SIRO-040.mp4'))

        # Real cover file so maybe_submit_video_focal's own os.path.exists guard
        # (irrelevant here since it's mocked, but keeps the fixture realistic)
        # would pass if it were the real function.
        cover_path = output_dir / 'SIRO-040-cover.jpg'
        cover_path.write_bytes(b'FAKE-IMG')
        cover_uri = to_file_uri(str(cover_path))

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=video_uri, number='SIRO-040', maker='Maker', title='Existing',
            cover_path=cover_uri, scrape_attempted_at=1000.0,
        ))
        # auto_focal='' and focal_attempted_at is NULL by dataclass default —
        # exactly the "existing readonly library, never focal-attempted" shape.

        # No _should_skip patch on purpose: the seeded scrape_attempted_at above
        # makes the REAL attempted_index path skip this row, so the natural skip
        # (and its URI derivation) is exercised rather than assumed.
        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(source_dir, output_dir, repo, filenames)

        assert result.skipped == 1, "sanity: the per-file loop really did skip it (not created)"
        mock_submit.assert_called_once()
        args = mock_submit.call_args[0]
        assert args[0] == 'SIRO-040'
        assert args[2] == video_uri


# ---------------------------------------------------------------------------
# TASK-104-T1 (CD-104-1/2/4/9): _produce_one primitive extraction, cover_strategy
# 3-state, assets_mode='samples_only', nfo_mtime real-write, call-sequence lock.
# ---------------------------------------------------------------------------

class TestCoverStrategyThreeState:
    """CD-104-2: _write_movie_assets cover_strategy explicit 3-state contract —
    'copy' (local file, zero network), 'none' (no cover written at all), and
    'download' (byte-identical to the pre-T1 unconditional-download branch)."""

    def test_copy_strategy_copies_local_file_not_download(self, tmp_path):
        from core.readonly_assets import _write_movie_assets

        local_cover = tmp_path / 'local-cover.jpg'
        local_cover.write_bytes(b'LOCAL-COVER-BYTES')
        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.shutil.copyfile', wraps=shutil.copyfile) as mock_copy, \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', str(local_cover)),
            )

        mock_download.assert_not_called()
        mock_copy.assert_called_once_with(str(local_cover), assets['cover_fs'])
        assert assets['cover_fs'], "copy state must produce a non-empty cover_fs on success"
        assert Path(assets['cover_fs']).read_bytes() == b'LOCAL-COVER-BYTES'


    def test_none_strategy_writes_no_cover(self, tmp_path):
        """'none': no cover written at all, download_image/copyfile both untouched,
        generate_jellyfin_images (poster/fanart) skipped since has_cover is False."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.shutil.copyfile') as mock_copy, \
             patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('none',),
            )

        mock_download.assert_not_called()
        mock_copy.assert_not_called()
        mock_jellyfin.assert_not_called()
        assert assets['cover_fs'] == ''
        assert not (Path(movie_dir) / 'TEST-001 Test Movie Title.jpg').exists()


# ---------------------------------------------------------------------------
# TASK-112b-T6 §C-2: curator 四格（無 sidecar／只有 fanart／只有 poster／
# poster+fanart 齊全）× media-server flavour——真跑 resolve_ingest_plan（真實
# find_cover_image 掃描，不 mock VideoScanner）+ _write_movie_assets（不 mock
# crop_to_poster/generate_jellyfin_images），對應真理表 Table 2 #1/#2/#3。
# ---------------------------------------------------------------------------

# 三張互異的真實可解碼小圖（landscape 800x538，ratio<1.0，落在 crop_to_poster
# 的「有碼橫向」分支；番號用非 FC2 值，requires_face_detection 恆 False，
# 不觸發人臉偵測，裁切結果 deterministic）。色碼沿用 T3 §H-10 手動驗證的配色
# （灰=同名封面／藍=curator fanart／洋紅=curator poster）。
_T6_GREY = (128, 128, 128)
_T6_BLUE = (0, 0, 255)
_T6_MAGENTA = (255, 0, 255)


def _t6_make_jpeg(path, color, size=(800, 538)):
    from PIL import Image
    Image.new('RGB', size, color=color).save(str(path), 'JPEG')


def _t6_resolve_and_write(src_dir, num, config, out_root=None):
    """真跑 resolve_ingest_plan（真實磁碟掃描）→ 真跑 _write_movie_assets（不
    mock crop_to_poster/generate_jellyfin_images），回傳 (movie_dir, base_stem,
    assets, cover_strategy) 供逐格斷言。

    輸出根目錄（out_root）刻意與 src_dir **分開**（預設 src_dir 的手足目錄，
    不是子目錄）——AC10「來源磁碟零寫入」的快照斷言只有在輸出不巢狀在來源
    底下時才有意義（否則 output/ 子目錄本身就會讓 before/after 快照不同，
    誤判成寫入了來源）。"""
    from core.readonly_paths import _build_basename, _format_data
    from core.readonly_assets import _write_movie_assets
    from core.readonly_producer import resolve_ingest_plan

    video = src_dir / f'{num}.mp4'
    video.write_bytes(b'FAKE-VIDEO')
    nfo = src_dir / f'{num}.nfo'
    nfo.write_text(f'<movie><num>{num}</num><title>{num} Title</title></movie>', encoding='utf-8')

    meta, cover_strategy = resolve_ingest_plan(str(video), num, config, action='ingest')
    assert meta is not None, "sanity: NFO-based ingest must produce meta"

    out_root = out_root if out_root is not None else src_dir.parent / 'out'
    movie_dir = str(Path(out_root) / num)
    fd = _format_data(meta, str(video), config)
    base = _build_basename(fd, str(video), config)
    base_stem = str(Path(movie_dir) / base)

    with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
        assets = _write_movie_assets(
            movie_dir, meta, fd, str(video), config, cover_strategy=cover_strategy,
        )
    return movie_dir, base_stem, assets, cover_strategy


class TestCuratorFourCellsMediaServer:
    """真理表 Table 2 #1/#2/#3：curator sidecar 四種組合 × jellyfin flavour，
    真跑完整鏈路（resolve_ingest_plan → _write_movie_assets → 真實
    crop_to_poster/generate_jellyfin_images），驗輸出實體檔與 bytes。"""

    def _config(self):
        return dict(_T3_BASE_CONFIG, external_manager='jellyfin')


    def test_poster_and_fanart_both_present_verbatim_both(self, tmp_path):
        """CD-112-7 直接鎖定格（plan §7.3 DoD-2 點名，mutation 目標＝
        core/readonly_producer.py:1422 的第三元素）：-poster + -fanart 兩個
        sidecar 皆備、無同名封面 → poster 逐位元組等於 curator 原 poster、
        fanart 逐位元組等於 curator 原 fanart、輸出夾無重複封面、
        assets['cover_fs'] 指向 -fanart.jpg。

        MUTATION：把 core/readonly_producer.py:1422 的
        `{'poster': poster_fs, 'fanart': None}` 改回 `None`（初版寫法，CD-112-7
        落地前）→ 這一支單獨轉紅（poster 退化成 crop_to_poster 的裁切輸出，
        不再逐位元組等於 curator 原 poster），
        test_only_fanart_sidecar_upgrades_cover_and_crops_poster 維持綠（見
        該測試 mutation 形狀分析，§F 記錄）。
        """
        num = 'CUR4-D'
        config = self._config()
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        _t6_make_jpeg(src_dir / f'{num}-poster.jpg', _T6_MAGENTA)
        _t6_make_jpeg(src_dir / f'{num}-fanart.jpg', _T6_BLUE)
        # _t6_resolve_and_write 內部會（重新，同路徑同內容）建立 video/nfo——
        # 先在這裡建好，快照才能在「來源已完整」之後、被測操作之前取得
        # （BE-TEST-10），避免把 helper 自己建 fixture 的動作誤判成寫入來源。
        (src_dir / f'{num}.mp4').write_bytes(b'FAKE-VIDEO')
        (src_dir / f'{num}.nfo').write_text(
            f'<movie><num>{num}</num><title>{num} Title</title></movie>', encoding='utf-8',
        )

        # AC10：來源磁碟遞迴快照在被測操作之前取得。
        source_before = _snapshot_dir(src_dir)

        movie_dir, base_stem, assets, cover_strategy = _t6_resolve_and_write(src_dir, num, config)

        source_after = _snapshot_dir(src_dir)
        assert source_after == source_before, (
            "AC10: readonly ingest must never write into the source directory"
        )

        # CD-112-7 第二半於 Codex PR#125 round-3 P1 修訂：存在的 curator sidecar
        # 一律宣告在第三元素（原本 'fanart' 恆 None，前提是「cover_fs 會等於
        # fanart 路徑」——collocated ＋ 已有同名封面時該前提為假，generate 分支
        # 會把同名封面複製到 curator fanart 上。見 TestCollocatedCuratorCoverCollision）。
        # 本格的四條**行為**斷言（poster verbatim／fanart verbatim／輸出無重複
        # 封面／cover_fs 指向 -fanart）修訂前後逐字不變。
        assert cover_strategy[2] == {
            'poster': str(src_dir / f'{num}-poster.jpg'),
            'fanart': str(src_dir / f'{num}-fanart.jpg'),
        }
        assert Path(base_stem + '-poster.jpg').read_bytes() == (src_dir / f'{num}-poster.jpg').read_bytes(), (
            "poster must be the curator's own sidecar verbatim, not a crop of the cover"
        )
        assert Path(base_stem + '-fanart.jpg').read_bytes() == (src_dir / f'{num}-fanart.jpg').read_bytes()
        assert not (Path(movie_dir) / f'{Path(base_stem).name}.jpg').exists(), (
            "no independent same-name cover — no third copy of the image"
        )
        assert assets['cover_fs'].endswith('-fanart.jpg')


# ---------------------------------------------------------------------------
# TASK-112b-T6 §C-3（DoD-3）：⑧ 的直接鎖＝真理表 Table 2 #1——唯讀 + media-
# server + 全新片 → has_fanart=True 且 -fanart.jpg 就是正典封面本身、NFO 三
# tag（thumb/fanart/poster）皆指向實際存在的檔案。不 mock generate_nfo（真跑
# core.organizer.generate_nfo 才能解析真實 tag 內容）。
# ---------------------------------------------------------------------------

class TestMediaServerNfoTagsPointToExistingFiles:
    _BASE = 'TEST-001 Test Movie Title'

    def test_jellyfin_tags_point_to_existing_files(self, tmp_path):
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'movie')
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')
        fd = _format_data(_T3_META, '/src/TEST-001.mp4', config)

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert assets['cover_fs'].endswith('-fanart.jpg'), "canonical cover IS -fanart.jpg (Table 2 #1)"
        nfo_path = Path(movie_dir) / f'{self._BASE}.nfo'
        root = ET.parse(nfo_path).getroot()
        for tag in ('thumb', 'fanart', 'poster'):
            tag_value = root.findtext(tag)
            assert tag_value, f"<{tag}> must not be empty"
            assert (Path(movie_dir) / tag_value).exists(), (
                f"<{tag}>={tag_value!r} must point to an existing file"
            )


class TestWriteMediaImagesFanartPreflightSamefileGuard:
    """⑧ 的 fanart preflight（`_write_media_images:763`）專屬守衛（Opus 追加
    要求 #5 沿用 T5 標準）：mutation 實測「只拿掉 preflight」在常態同檔路徑
    （cover_fs 與 fanart_path 字串相等）下靠 `shutil.SameFileError` backstop
    仍維持綠（見 TASK-112b-T6.md §F「每組 mutation 的實測形狀」記錄），preflight
    真正不可替代的是 `os.path.samefile` 拋出未知 `OSError` 那一格——這需要
    cover_fs 與 fanart_path 字串**不同**才會真的呼叫到 `os.path.samefile`
    （字串相等時 `same_target_verdict` 在呼叫它之前就已短路）。形狀照抄
    `test_enricher.py::TestWriteExternalImagesPreflightSamefileGuard`，但在
    本檔內自己寫一份，不 import。"""

    def test_samefile_oserror_fails_closed_no_corruption(self, tmp_path, monkeypatch):
        from core.readonly_assets import _write_media_images

        base_stem = str(tmp_path / 'TEST-001 Title')
        fanart_path = Path(base_stem + '-fanart.jpg')
        _t6_make_jpeg(fanart_path, _T6_BLUE)
        before_bytes = fanart_path.read_bytes()

        # cover_fs 故意落在與 fanart_path 不同名的位置（模擬 resolve_cover_target
        # 命中既有 same-name 候選的情境）——字串不同，same_target_verdict 才會
        # 真的呼叫 os.path.samefile，preflight 的 fail-closed 承諾才測得到。
        cover_fs = str(tmp_path / 'TEST-001 Title.jpg')
        _t6_make_jpeg(Path(cover_fs), _T6_GREY)

        def _raise(a, b):
            raise OSError("boom（模擬權限被拒／網路磁碟逾時）")

        monkeypatch.setattr(os.path, 'samefile', _raise)

        has_poster, has_fanart = _write_media_images(
            cover_fs, base_stem, _T3_META, source_media={'poster': None, 'fanart': None},
        )

        assert fanart_path.read_bytes() == before_bytes, (
            "既有 -fanart.jpg 的 bytes 不得被清空/改動（基準值在操作之前取得，BE-TEST-10）"
        )
        assert has_fanart is False, "未知 OSError → fail-closed，不得宣稱成功"
        assert has_poster is False, "poster 側同一組 monkeypatch 也命中 fail-closed"


# ---------------------------------------------------------------------------
# Codex PR#125 round-2 P1（2026-08-05）：curator sidecar 與輸出 slot **是同一個
# 檔**（唯讀來源的輸出根落回來源片目錄、且 basename 落回來源 stem）。舊碼先
# copy2 再說 → `SameFileError` 被寬 except 吞成「複製失敗」→ 落回 generate 分支，
# 而那個分支比的是 `cover_fs` vs slot（**另一對**，正當地「不同檔」）→
# `crop_to_poster` 把機器封面裁在使用者親手挑的直式海報上。
#
# 傷害面：OpenAver 自己的畫面看不出來（`find_cover_image` L1.5 先撿 `-fanart`），
# 100% 落在 Jellyfin/Emby/Kodi——正是 AC5 curator 邊界「逐位元組保留 curator
# 原檔」與 prd.md 技術決策 #6「衍生產物不回寫原檔」要保護的那個表面。
#
# 這是**本 branch 的回歸**而非既有 bug：`_write_cover_copy` 學會同檔情境
# （2338c62d / a552f674）之前，封面步驟在這個佈局下回 `has_cover=False`，
# `_write_media_images` 根本到不了。
# ---------------------------------------------------------------------------

class TestCollocatedCuratorSidecarPassthrough:
    """curator sidecar 就是輸出 slot 本身 → 視為「已經 verbatim 到位」的成功
    passthrough，不得落回 generate。"""

    def _collocated_config(self):
        # filename_format='{num}' 讓 _build_basename 產出的 base 等於來源檔 stem，
        # 加上 movie_dir == src_dir，poster_path 才會與 curator sidecar 同路徑。
        return dict(_T3_BASE_CONFIG, external_manager='jellyfin', filename_format='{num}')

    def test_poster_sidecar_collocated_with_output_is_preserved(self, tmp_path):
        """端到端（真跑 resolve_ingest_plan → _write_movie_assets，真
        crop_to_poster）：輸出目錄 == 來源目錄、base == 來源 stem →
        curator `-poster.jpg` 必須逐位元組原封不動。

        MUTATION LOCK：把 `_copy_curator_sidecar` 的 `is_same` 分支拿掉（讓它
        直接 `shutil.copy2` 再靠寬 except 吞 `SameFileError` 回 None）→ 本測試
        單獨轉紅（poster 變成灰色封面的裁切產物）。
        """
        from core.readonly_paths import _build_basename, _format_data
        from core.readonly_assets import _write_movie_assets
        from core.readonly_producer import resolve_ingest_plan

        num = 'COLLOC-A'
        config = self._collocated_config()
        src_dir = tmp_path / num
        src_dir.mkdir()
        video = src_dir / f'{num}.mp4'
        video.write_bytes(b'FAKE-VIDEO')
        (src_dir / f'{num}.nfo').write_text(
            f'<movie><num>{num}</num><title>{num} Title</title></movie>', encoding='utf-8',
        )
        _t6_make_jpeg(src_dir / f'{num}.jpg', _T6_GREY)
        _t6_make_jpeg(src_dir / f'{num}-poster.jpg', _T6_MAGENTA, size=(379, 538))
        # 基準值在被測操作之前取得（BE-TEST-10）
        poster_before = (src_dir / f'{num}-poster.jpg').read_bytes()

        meta, cover_strategy = resolve_ingest_plan(str(video), num, config, action='ingest')
        fd = _format_data(meta, str(video), config)
        base = _build_basename(fd, str(video), config)
        assert base == num, "sanity: 這個 fixture 的前提就是 base 落回來源 stem"
        base_stem = str(src_dir / base)
        assert cover_strategy[2]['poster'] == str(src_dir / f'{num}-poster.jpg')

        with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                str(src_dir), meta, fd, str(video), config, cover_strategy=cover_strategy,
            )

        assert (src_dir / f'{num}-poster.jpg').read_bytes() == poster_before, (
            "curator 親手挑的直式海報不得被 crop_to_poster 就地覆寫"
            "（AC5 curator 邊界＝逐位元組保留原檔；prd.md 技術決策 #6 承重牆）"
        )
        assert Path(base_stem + '-poster.jpg').exists()


    def test_collocated_sidecar_samefile_oserror_fails_closed(self, tmp_path):
        """為什麼 sidecar 側需要 preflight，而不是「catch `SameFileError` 就好」：
        `shutil.copyfile` 內部的 `_samefile` **把 `OSError` 吞掉當成 False**，
        所以在 `os.path.samefile` 會拋例外的檔案系統上（權限被拒／部分網路
        磁碟——正是 `same_target_verdict` 存在的理由），`copy2` 會照樣以 `'wb'`
        開啟目的檔、把它正在讀的那個檔清空。

        MUTATION LOCK（三個，形狀已實測）：
        ① preflight 整段拿掉 → `copy2` 把 hardlink 的目的檔清空 → 轉紅。
        ② `not certain` 分支的 `return False` 改成 `return None`（落回
           generate）→ 真的 `crop_to_poster` 把封面裁在同一個 inode 上 → 轉紅。
           ⚠️ 這一格**只有在 `samefile` 對 sidecar 那一對拋、對 cover 那一對
           正常**時才驗得到（兩對都拋的話，generate 分支自己的 fail-closed 會
           把結果遮成一樣，mutation 變無感——BE-TEST-11）。
        ③ `crop_to_poster` 不 mock，讓毀損是**真的**發生在真檔案上，斷言才有牙。
        """
        from core.readonly_assets import _write_media_images

        # sidecar 與目的檔的**字串不同、inode 相同**（hardlink）——MDCX/Javinizer
        # 把 `-poster.jpg` 做成別處檔案的 hardlink 就是這個形狀，也是
        # `same_target_verdict` 當初的存在理由。
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        src_poster = str(src_dir / 'COLLOC-C-poster.jpg')

        base_stem = str(tmp_path / 'COLLOC-C')
        cover_fs = base_stem + '.jpg'
        poster_path = base_stem + '-poster.jpg'
        _t6_make_jpeg(Path(cover_fs), _T6_GREY)
        _t6_make_jpeg(Path(poster_path), _T6_MAGENTA, size=(379, 538))
        os.link(poster_path, src_poster)
        poster_before = Path(poster_path).read_bytes()

        real_samefile = os.path.samefile

        def _raise_for_sidecar_only(a, b):
            # 只有「sidecar ↔ 目的檔」那一對拋（模擬 sidecar 落在權限被拒／
            # 逾時的網路磁碟）；cover ↔ 目的檔那一對照常回答。
            if src_poster in (a, b):
                raise OSError("boom（模擬權限被拒／網路磁碟逾時）")
            return real_samefile(a, b)

        monkey = patch.object(os.path, 'samefile', _raise_for_sidecar_only)
        monkey.start()
        try:
            has_poster, _ = _write_media_images(
                cover_fs, base_stem, _T3_META,
                source_media={'poster': src_poster, 'fanart': None},
            )
        finally:
            monkey.stop()

        assert Path(poster_path).read_bytes() == poster_before, (
            "未知 OSError → fail-closed，既有 curator 檔不得被清空/改動"
            "（基準值在操作之前取得，BE-TEST-10）"
        )
        assert has_poster is False, "不確定就不得宣稱成功（CD-112-8 安全／誠實分離）"


# ---------------------------------------------------------------------------
# TASK-112b-T6 §C-10（DoD-11，R9）：curator -fanart 內容是 PNG（副檔名仍是
# .jpg，MDCX/Javinizer 常見）→ CD-112-7 讓這張圖升格成正典封面，OpenAver
# 自己也要讀得到——驗正常出圖（PIL 開得起來、輸出合法 JPEG）與焦點裁切
# （座標平移邏輯與正常 JPEG 來源一致，用獨立 oracle 比對，不是推理）。
# ---------------------------------------------------------------------------

class TestCollocatedCuratorCoverCollision:
    """Codex PR#125 round-3 P1：collocated 佈局下，封面**主**複製不得覆寫
    curator 的另一張原檔。

    情境：來源同時有 `{stem}.jpg` 與 `{stem}-fanart.jpg`（**兩張都是 curator
    原檔、內容不同**），輸出根落回來源目錄。此時翻面的兩半會互相打架——
    `find_cover_image` 的 L1 挑到同名封面，於是 CD-112-7 把 curator `-fanart`
    升格為複製**來源**；而 `resolve_cover_target` 的第①步看到同名封面已經在
    磁碟上，就把它當成**目標**回傳。兩者不同檔 → `copyfile(fanart → 同名)`
    把第二張 curator 原檔永久毀掉（實測 800×538 紅 → 1200×675 藍，md5 變成
    fanart 的）。

    這是**本 branch 的回歸**而非既有債：`curator_cover_source`（那個升格）由
    `c4bb5508`（112b-T3）引入；在它之前來源與目標是同一個檔、複製是 no-op。

    Collision policy：`_write_cover_copy` 在 `dst` 已存在時一律不覆寫、直接把
    既有檔當封面回報成功。這與 `resolve_cover_target` 第①②步的「**沿用**」
    語意一致——那兩步只在「正典位置已經有封面」時才回傳既有路徑。
    `('copy', …)` 全庫只有一個生產者（ingest 分支），而 ingest 的契約本來就是
    local-first / reuse-first；刻意覆寫的逃生口（齒輪重刮）走
    `('download', url)` → `download_image`，永遠不經過本函式。

    MUTATION LOCK：拿掉 `_write_cover_copy` 的 `if os.path.exists(dst): return True`
    → 本測試單獨轉紅（同名封面 md5 變成 fanart 的），其餘測試維持綠。
    """

    def test_curator_same_name_cover_is_not_overwritten_by_promoted_fanart(self, tmp_path):
        from core.readonly_paths import _build_basename, _format_data
        from core.readonly_assets import _write_movie_assets
        from core.readonly_producer import resolve_ingest_plan

        num = 'COLLIDE-A'
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin', filename_format='{num}')
        src_dir = tmp_path / num
        src_dir.mkdir()
        video = src_dir / f'{num}.mp4'
        video.write_bytes(b'FAKE-VIDEO')
        (src_dir / f'{num}.nfo').write_text(
            f'<movie><num>{num}</num><title>{num} Title</title></movie>', encoding='utf-8',
        )
        # 兩張 curator 原檔，內容刻意不同（顏色 + 尺寸都不同才看得出誰蓋了誰）
        _t6_make_jpeg(src_dir / f'{num}.jpg', _T6_GREY, size=(800, 538))
        _t6_make_jpeg(src_dir / f'{num}-fanart.jpg', _T6_MAGENTA, size=(1200, 675))
        # 基準值在被測操作之前取得（BE-TEST-10）
        same_before = (src_dir / f'{num}.jpg').read_bytes()
        fanart_before = (src_dir / f'{num}-fanart.jpg').read_bytes()
        assert same_before != fanart_before, "sanity: 兩張原檔內容必須不同"

        meta, cover_strategy = resolve_ingest_plan(str(video), num, config, action='ingest')
        assert cover_strategy[1] == str(src_dir / f'{num}-fanart.jpg'), (
            "sanity: CD-112-7 應把 curator -fanart 升格為複製來源"
        )
        fd = _format_data(meta, str(video), config)
        base = _build_basename(fd, str(video), config)
        assert base == num, "sanity: 這個 fixture 的前提就是 base 落回來源 stem"

        with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                str(src_dir), meta, fd, str(video), config, cover_strategy=cover_strategy,
            )

        assert (src_dir / f'{num}.jpg').read_bytes() == same_before, (
            "curator 的同名封面原檔不得被升格後的 -fanart 覆寫"
            "（prd.md 技術決策 #6 承重牆：衍生產物不回寫原檔）"
        )
        assert (src_dir / f'{num}-fanart.jpg').read_bytes() == fanart_before, (
            "curator 的 -fanart 原檔同樣不得被動到"
        )
        assert assets['cover_fs'] == str(src_dir / f'{num}.jpg'), (
            "resolver 第①步選中的既有同名封面就是正典，記帳要指向它"
        )


class TestAssetsModeSamplesOnly:
    """CD-104-1: assets_mode='samples_only' — ONLY the extrafanart download loop
    runs; nfo/cover/poster/fanart/strm and BOTH stale-cleanup helpers are
    untouched, and sample download is unconditional (not gated on
    config['download_sample_images']). cover_strategy is accepted but ignored —
    Codex P1-c: a supplemental-samples fetch must never touch the cover."""

    def test_only_samples_downloaded_nfo_and_cover_not_called(self, tmp_path):
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=['http://x/1.jpg', 'http://x/2.jpg'])

        def fake_download(url, save_path, referer=''):
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'SAMPLE')
            return True

        with patch('core.readonly_assets.download_image', side_effect=fake_download) as mock_download, \
             patch('core.readonly_assets.generate_nfo') as mock_nfo, \
             patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.shutil.copyfile') as mock_copy:
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('none',), assets_mode='samples_only',
            )

        mock_nfo.assert_not_called()
        mock_jellyfin.assert_not_called()
        mock_copy.assert_not_called()
        assert mock_download.call_count == 2
        assert len(assets['sample_fs']) == 2
        assert 'cover_fs' not in assets, "samples_only must not fabricate a cover_fs key"
        assert 'nfo_mtime' not in assets, "samples_only must not fabricate an nfo_mtime key"
        assert not (Path(movie_dir) / 'TEST-001 Test Movie Title.nfo').exists()
        assert not (Path(movie_dir) / 'TEST-001 Test Movie Title.jpg').exists()

    def test_unconditional_regardless_of_download_sample_images_flag(self, tmp_path):
        """samples_only downloads samples even when config['download_sample_images']
        is False — explicit fetch intent, not gated on the generic scrape flag."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=['http://x/1.jpg'])
        config = dict(_T3_BASE_CONFIG, download_sample_images=False)

        def fake_download(url, save_path, referer=''):
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'SAMPLE')
            return True

        with patch('core.readonly_assets.download_image', side_effect=fake_download), \
             patch('core.readonly_assets.generate_nfo') as mock_nfo:
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('none',), assets_mode='samples_only',
            )

        mock_nfo.assert_not_called()
        assert len(assets['sample_fs']) == 1


class TestWriteMovieAssetsFullModeReentryPreservesExtrafanart:
    """P1 grok-review (pre-merge 2026-07-21): a full-mode RE-ENTRY of an
    already-produced video (gear rescrape / 放大鏡 ingest / batch-enrich, all
    `assets_mode='full'`) must NOT wipe extrafanart/ samples fetched by an
    earlier 補劇照 (`assets_mode='samples_only'`) call. Full-mode ingest/rescrape
    always pass `meta['sample_images'] == []` (CD-104-3: samples are
    intentionally left empty on ingest/rescrape, fetched on-demand only via
    samples_only) — so old_base is non-empty (an already-produced video always
    has a prior row) while this run itself has nothing to write into
    extrafanart/. A bare `if old_base:` extrafanart-clean would therefore
    delete the dir with nothing to replace it, destroying prior 補劇照 output.

    MUTATION LOCK: reverting the `and meta.get('sample_images')` guard on the
    `if old_base:` line back to a bare `if old_base:` turns
    test_full_mode_reentry_preserves_extrafanart_on_disk RED (files deleted)."""

    def _samples_only_seed(self, movie_dir, config):
        """Seed extrafanart/ the way a prior 補劇照 call would (samples_only mode)."""
        from core.readonly_assets import _write_movie_assets

        meta_samples = dict(_T3_META, sample_images=['http://x/1.jpg', 'http://x/2.jpg'])
        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download):
            _write_movie_assets(
                movie_dir, meta_samples, _t3_format_data(config=config), '/src/TEST-001.mp4', config,
                cover_strategy=('none',), assets_mode='samples_only',
            )

    def test_full_mode_reentry_preserves_extrafanart_on_disk(self, tmp_path):
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        config = dict(_T3_BASE_CONFIG)
        self._samples_only_seed(movie_dir, config)

        ef_dir = Path(movie_dir) / 'extrafanart'
        assert (ef_dir / 'fanart1.jpg').exists()
        assert (ef_dir / 'fanart2.jpg').exists()

        # full-mode RE-ENTRY: meta['sample_images'] always [] on ingest/rescrape
        # (CD-104-3); old_base non-empty because this video was already produced.
        meta_full = dict(_T3_META, sample_images=[])
        fd = _t3_format_data(config=config)
        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
            _write_movie_assets(
                movie_dir, meta_full, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('download', 'http://x/cover.jpg'), assets_mode='full',
                old_base='TEST-001 Test Movie Title',
            )

        assert (ef_dir / 'fanart1.jpg').exists(), "full-mode re-entry must not wipe existing samples"
        assert (ef_dir / 'fanart2.jpg').exists(), "full-mode re-entry must not wipe existing samples"


class TestUpsertDbSamplesOnly:
    """CD-104-1/104-4: assets_mode='samples_only' — DB path calls ONLY
    repo.update_sample_images; never builds/upserts a full Video row, so
    cover_path/nfo_mtime/metadata of an existing produced row are left
    completely alone (Codex P1-c: a supplemental-samples fetch must not
    clobber metadata it wasn't asked to touch)."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'


    def test_empty_sample_fs_leaves_existing_sample_images_row_untouched(self, temp_db):
        """Real-DB round trip of the P2 fix: an existing row's sample_images
        survive a samples_only call whose assets['sample_fs'] came back empty
        (e.g. every download in this fetch attempt failed) — the exact
        "total failure clobbers to []" bug this task fixes."""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            sample_images=['file:///output/TEST-001/extrafanart/fanart1.jpg'],
            output_dir='file:///output/TEST-001',
        ))

        assets = {'sample_fs': []}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == ['file:///output/TEST-001/extrafanart/fanart1.jpg']

    def test_does_not_touch_cover_path_or_nfo_mtime_of_existing_row(self, temp_db):
        """Real-DB round trip: an existing produced row's cover_path/nfo_mtime/
        title survive a samples_only _upsert_db call completely untouched."""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            cover_path='file:///output/TEST-001/cover.jpg', nfo_mtime=12345.0,
            output_dir='file:///output/TEST-001',
        ))

        assets = {'sample_fs': ['/output/TEST-001/extrafanart/fanart1.jpg']}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == 'file:///output/TEST-001/cover.jpg'
        assert v.nfo_mtime == 12345.0
        assert v.title == 'Existing Title'
        assert len(v.sample_images) == 1

    # ── FIX P2-B: samples_only must still persist output_dir ────────────────


class TestMissingCheckExclusionInvariant:
    """CD-104-4 regression lock: web/routers/scanner.py::check_missing excludes
    any row where `produced (output_dir truthy) or tried (scrape_attempted_at>0)`
    — BEFORE it ever looks at nfo_mtime/cover_path — so changing what nfo_mtime
    _upsert_db writes must NOT change which rows missing-check surfaces (CD-89b-4:
    the missing-check exclusion signal is output_dir/scrape_attempted_at, never
    nfo_mtime).

    check_missing itself is a FastAPI route body (web/routers/scanner.py:990),
    not an importable pure function, and this task's file allowlist doesn't
    include that module — so the exclusion predicate is replicated verbatim
    below (web/routers/scanner.py:1007-1009: `if produced or tried: continue`)
    rather than imported, and exercised against rows _upsert_db actually
    produces with two different nfo_mtime values."""

    @staticmethod
    def _missing_check_excludes(v) -> bool:
        """Verbatim copy of the exclusion predicate at
        web/routers/scanner.py:1007-1009."""
        produced = bool(v.output_dir)
        tried = (v.scrape_attempted_at or 0) > 0
        return produced or tried


# ---------------------------------------------------------------------------
# TASK-104-T2 (CD-104-3b): _nfo_to_producer_meta — NFO -> producer-meta adapter.
# All-keys alignment, round-trip edges (title bracket-strip / rating ÷2),
# mutation lock against core.enricher._nfo_to_meta's different key shape.
# ---------------------------------------------------------------------------

def _nfo_root(xml: str):
    return ET.fromstring(xml)


class TestNfoToProducerMeta:
    def test_all_keys_present_and_aligned(self):
        from core.readonly_producer import _nfo_to_producer_meta

        xml = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>[ABC-123]My Title</title>
  <originaltitle>元のタイトル</originaltitle>
  <num>ABC-123</num>
  <studio>MakerCo</studio>
  <label>LabelCo</label>
  <director>DirName</director>
  <set><name>SeriesName</name></set>
  <premiered>2024-05-01</premiered>
  <runtime>120</runtime>
  <plot>A summary.</plot>
  <rating>8.4</rating>
  <website>https://example.com/v</website>
  <actor><name>Actress A</name><role></role></actor>
  <actor><name>Actress B</name><role></role></actor>
  <tag>Tag1</tag>
  <tag>Tag2</tag>
  <genre>Tag1</genre>
  <genre>Tag2</genre>
</movie>"""
        root = _nfo_root(xml)
        meta = _nfo_to_producer_meta(root, fallback_number='FALLBACK-000')

        assert set(meta.keys()) == {
            'number', 'title', 'original_title', 'actors', 'tags', 'date',
            'maker', 'director', 'series', 'label', 'duration', 'url',
            '_summary', '_rating', 'cover', 'sample_images',
            # TASK-126-T4b（CD-126-2）：本地 NFO 沒有代理可言，但這兩個鍵必須存在——
            # 否則下游 `.get()` 的預設值會散落在四個地方。值恆為空。
            'preview_cover_url', 'preview_sample_images',
        }
        assert meta['number'] == 'ABC-123'
        assert meta['title'] == 'My Title'
        assert meta['original_title'] == '元のタイトル'
        assert meta['actors'] == ['Actress A', 'Actress B']
        assert meta['tags'] == ['Tag1', 'Tag2']
        assert meta['date'] == '2024-05-01'
        assert meta['maker'] == 'MakerCo'
        assert meta['director'] == 'DirName'
        assert meta['series'] == 'SeriesName'
        assert meta['label'] == 'LabelCo'
        assert meta['duration'] == 120
        assert meta['url'] == 'https://example.com/v'
        assert meta['_summary'] == 'A summary.'
        assert meta['_rating'] == pytest.approx(4.2)
        assert meta['cover'] == ''
        assert meta['sample_images'] == []

    # ── FIX#3: original_title extraction (P2 parity closeout) ───────────────


    def test_nfo_to_producer_meta_applies_custom_nfo_title_format(self):
        """AC-b7：認得其他工具用自訂格式產生的 NFO → 讀出片名本體。"""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie>'
            '<title>ABC-123-片名-三上悠亜</title>'
            '<actor><name>三上悠亜</name></actor>'
            '</movie>'
        )
        meta = _nfo_to_producer_meta(
            root, fallback_number='ABC-123', nfo_title_format='{num}-{title}-{actor}'
        )
        assert meta['title'] == '片名'

    def test_nfo_to_producer_meta_respects_external_title_edit(self):
        """AC-b11：記錄行存在但 <title> 被外部改過 → 以外部改過的內容為準。"""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie>'
            '<title>外部改過的片名</title>'
            '<actor><name>三上悠亜</name></actor>'
            '<openaver_title_record>'
            '<written>ABC-123-片名-三上悠亜</written>'
            '<body>片名</body>'
            '</openaver_title_record>'
            '</movie>'
        )
        meta = _nfo_to_producer_meta(
            root, fallback_number='ABC-123', nfo_title_format='{num}-{title}-{actor}'
        )
        assert meta['title'] == '外部改過的片名'


class TestNfoToProducerMetaRoundTrip:
    """CD-104-3b DoD: generate_nfo -> _nfo_to_producer_meta round-trip."""

    def test_round_trip_core_fields_survive(self, tmp_path):
        from core.nfo_updater import parse_nfo
        from core.organizer import generate_nfo
        from core.readonly_producer import _nfo_to_producer_meta

        nfo_path = tmp_path / 'RTX-001.nfo'
        ok = generate_nfo(
            number='RTX-001',
            title='Original Title',
            actors=['Actress A', 'Actress B'],
            tags=['TagA', 'TagB'],
            date='2023-06-15',
            maker='MakerX',
            url='https://example.com/rtx-001',
            output_path=str(nfo_path),
            director='DirectorX',
            duration=95,
            series='SeriesX',
            label='LabelX',
            summary='Summary text.',
            rating=4.3,
        )
        assert ok

        _, root = parse_nfo(str(nfo_path))
        assert root is not None
        meta = _nfo_to_producer_meta(root, fallback_number='RTX-001')

        assert meta['number'] == 'RTX-001'
        assert meta['title'] == 'Original Title'
        assert meta['actors'] == ['Actress A', 'Actress B']
        assert meta['date'] == '2023-06-15'
        assert meta['maker'] == 'MakerX'
        assert meta['tags'] == ['TagA', 'TagB']
        assert meta['series'] == 'SeriesX'
        assert meta['label'] == 'LabelX'
        assert meta['duration'] == 95
        assert meta['_summary'] == 'Summary text.'
        assert meta['_rating'] == pytest.approx(4.3)

    def test_round_trip_title_does_not_double_wrap_on_regenerate(self, tmp_path):
        """The exact round-trip edge this task exists for: regenerating an NFO
        from the adapter's own output must NOT double-wrap [num][num]title."""
        from core.nfo_updater import parse_nfo
        from core.organizer import generate_nfo
        from core.readonly_producer import _nfo_to_producer_meta

        nfo_path = tmp_path / 'RTX-002.nfo'
        generate_nfo(number='RTX-002', title='Plain Title', output_path=str(nfo_path))
        _, root = parse_nfo(str(nfo_path))
        meta = _nfo_to_producer_meta(root, fallback_number='RTX-002')
        assert meta['title'] == 'Plain Title'  # NOT '[RTX-002]Plain Title'

        nfo_path2 = tmp_path / 'RTX-002-again.nfo'
        generate_nfo(number=meta['number'], title=meta['title'], output_path=str(nfo_path2))
        _, root2 = parse_nfo(str(nfo_path2))
        title_elem = root2.find('title')
        assert title_elem.text == '[RTX-002]Plain Title'
        assert title_elem.text.count('[RTX-002]') == 1

    def test_round_trip_rating_survives_multiply_then_divide(self, tmp_path):
        from core.nfo_updater import parse_nfo
        from core.organizer import generate_nfo
        from core.readonly_producer import _nfo_to_producer_meta

        nfo_path = tmp_path / 'RTX-003.nfo'
        generate_nfo(number='RTX-003', title='T', output_path=str(nfo_path), rating=3.7)
        _, root = parse_nfo(str(nfo_path))
        meta = _nfo_to_producer_meta(root, fallback_number='RTX-003')
        assert meta['_rating'] == pytest.approx(3.7)


# ---------------------------------------------------------------------------
# TASK-104-T2 (CD-104-3a): resolve_ingest_plan — metadata/cover two-axis
# decision. ingest local-first branches, rescrape always-remote branch,
# malformed-NFO fallback (特有邊界), sample_images always [].
# ---------------------------------------------------------------------------

class TestResolveIngestPlan:
    def _touch_video(self, tmp_path, name='SRC-001.mp4'):
        p = tmp_path / name
        p.write_bytes(b'FAKE')
        return p

    def test_ingest_valid_nfo_uses_nfo_metadata_zero_network(self, tmp_path):
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SRC-001</num><title>[SRC-001]T</title></movie>', encoding='utf-8')

        with patch('core.readonly_producer.search_jav') as mock_search, \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        mock_search.assert_not_called()
        assert meta['number'] == 'SRC-001'
        assert meta['title'] == 'T'
        assert cover_strategy == ('none',)
        assert meta['sample_images'] == []


    def test_ingest_cover_only_no_nfo_calls_search_jav(self, tmp_path):
        """Matrix ③: cover-only (no .nfo) -> search_jav CALLED for metadata,
        but the cover itself is copied locally, never downloaded."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        cover_path = str(tmp_path / 'SRC-001.jpg')

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': ''},
        ) as mock_search, patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = cover_path
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        mock_search.assert_called_once_with('SRC-001', source='auto', javbus_lang=None)
        assert cover_strategy == ('copy', cover_path, {'poster': None, 'fanart': None})

    # -- P2 fix (round-3 review 2026-07-21): ingest scrape-fallback honors the
    # caller's own source/javbus_lang instead of hardcoding source="auto" --

    def test_ingest_no_valid_nfo_concrete_source_uses_single_source(self, tmp_path):
        """A caller-supplied concrete source must route through
        search_jav_single_source with THAT source — not the hardcoded
        source="auto" the ingest scrape-fallback used before this fix (Codex
        PR#113 round-3 P2). javbus_lang is threaded through too.
        MUTATION LOCK: reverting the ingest branch's source dispatch back to a
        bare `search_jav(number, source="auto")` call
        makes this test RED (mock_single never called; cover_strategy would
        still coincidentally match, but mock_single.assert_called_once_with
        below fails)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        with patch('core.readonly_producer.search_jav') as mock_search, \
             patch(
                 'core.readonly_producer.search_jav_single_source',
                 return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
             ) as mock_single, \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(
                str(video), 'SRC-001', {}, action='ingest', source='javbus',
                javbus_lang='zh-tw',
            )

        mock_single.assert_called_once_with('SRC-001', 'javbus', javbus_lang='zh-tw')
        mock_search.assert_not_called()
        assert cover_strategy == ('download', 'http://x/c.jpg')


    def test_ingest_malformed_nfo_falls_back_to_scrape_not_locked_to_none(self, tmp_path):
        """特有邊界 #1: .nfo exists but parse_nfo fails (bad XML, root=None) ->
        treated as no usable NFO. Metadata retries search_jav; the cover branch
        must key on valid_nfo, NOT the bare nfo_path.exists() check — else a
        malformed sidecar would withhold metadata AND lock cover into
        ('none',) with no fallback."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('NOT VALID XML <<<', encoding='utf-8')

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ) as mock_search, patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        mock_search.assert_called_once()
        assert meta is not None
        assert cover_strategy == ('download', 'http://x/c.jpg')
        MockVS.return_value.find_cover_image.assert_called_once_with(str(video), nfo_thumb=None)


    def test_rescrape_always_downloads_ignores_local_cover(self, tmp_path):
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SRC-001</num></movie>', encoding='utf-8')

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/new.jpg'},
        ) as mock_search, patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = str(tmp_path / 'local.jpg')
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='rescrape')

        mock_search.assert_called_once()
        MockVS.return_value.find_cover_image.assert_not_called()
        assert cover_strategy == ('download', 'http://x/new.jpg')
        assert meta['sample_images'] == []


    # -- TASK-104-T3: rescrape scraper_data / source candidate widening ------

    def test_rescrape_scraper_data_used_verbatim_zero_network(self, tmp_path):
        """When the router already fetched a candidate (javlibrary detail_url
        confirm flow), resolve_ingest_plan must use it AS-IS — no search_jav /
        search_jav_single_source call at all."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        scraper_data = {'number': 'SRC-001', 'title': 'Candidate T', 'cover': 'http://x/candidate.jpg'}

        with patch('core.readonly_producer.search_jav') as mock_search, \
             patch('core.readonly_producer.search_jav_single_source') as mock_single:
            meta, cover_strategy = resolve_ingest_plan(
                str(video), 'SRC-001', {}, action='rescrape', scraper_data=scraper_data,
            )

        mock_search.assert_not_called()
        mock_single.assert_not_called()
        assert meta['title'] == 'Candidate T'
        assert cover_strategy == ('download', 'http://x/candidate.jpg')
        assert meta['sample_images'] == []

    def test_rescrape_concrete_source_uses_single_source(self, tmp_path):
        """No scraper_data + a concrete (non-auto) source -> search_jav_single_source,
        NOT search_jav (explicit source pick must not go through the auto merger)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        with patch('core.readonly_producer.search_jav') as mock_search, \
             patch(
                 'core.readonly_producer.search_jav_single_source',
                 return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
             ) as mock_single:
            meta, cover_strategy = resolve_ingest_plan(
                str(video), 'SRC-001', {}, action='rescrape', source='javbus',
                javbus_lang='zh-tw',
            )

        mock_single.assert_called_once_with('SRC-001', 'javbus', javbus_lang='zh-tw', skip_format_check=False)
        mock_search.assert_not_called()
        assert cover_strategy == ('download', 'http://x/c.jpg')


# ---------------------------------------------------------------------------
# TASK-104-T3 (CD-104-5): resolve_owning_output_root — innermost readonly
# source resolver + writable-override + empty-output-root passthrough.
# ---------------------------------------------------------------------------

def _gallery_config(directories, path_mappings=None, scraper_cfg=None):
    """Build a full app-config dict (the shape resolve_owning_output_root and
    resolve_output_root both expect: config['gallery']/config['scraper'])."""
    return {
        "gallery": {
            "directories": directories,
            "path_mappings": path_mappings or {},
        },
        "scraper": scraper_cfg or {},
    }


class TestResolveOwningOutputRoot:


    def test_finds_owning_readonly_source_off_mode_nonempty_root(self, tmp_path):
        from core.database import get_db_path
        from core.readonly_paths import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "ro"
        src.mkdir()
        canonical = to_file_uri(str(src / "ABC-001.mp4"))
        config = _gallery_config([{"path": str(src), "readonly": True}])  # off (default)

        result = resolve_owning_output_root(canonical, config)

        assert result is not None
        source, output_root, output_uri = result
        assert source.path == str(src)
        assert output_root.startswith(str(get_db_path().parent / "lib"))
        assert output_uri.startswith("file:///")

    # -- boundary (a): media-server flavour, output_path not yet configured --
    def test_empty_output_root_returns_source_with_empty_strings(self, tmp_path):
        """media-server flavour + no output_path configured (first-time /
        never-configured) -> (source, '', '') so the router can still name the
        owning source in its own error message, but must reject the write."""
        from core.readonly_paths import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "ro"
        src.mkdir()
        canonical = to_file_uri(str(src / "ABC-001.mp4"))
        config = _gallery_config(
            [{"path": str(src), "readonly": True, "output_path": ""}],
            scraper_cfg={"external_manager": "jellyfin"},
        )

        result = resolve_owning_output_root(canonical, config)

        assert result is not None
        source, output_root, output_uri = result
        assert output_root == ""
        assert output_uri == ""

    # -- boundary (c): nested writable override --------------------------------

    def test_nested_readonly_child_under_writable_parent_still_routes(self, tmp_path):
        """Mirror case: writable parent + readonly child (longer prefix) -> the
        readonly child wins -> routes (not None), owning source is the child."""
        from core.readonly_paths import resolve_owning_output_root
        from core.path_utils import to_file_uri

        parent = tmp_path / "rw_parent"
        child = parent / "ro_child"
        child.mkdir(parents=True)
        canonical = to_file_uri(str(child / "ABC-001.mp4"))
        config = _gallery_config([
            {"path": str(parent), "readonly": False},
            {"path": str(child), "readonly": True},
        ])

        result = resolve_owning_output_root(canonical, config)

        assert result is not None
        source, _output_root, _output_uri = result
        assert source.path == str(child)


    # -- boundary (b): source root changed between calls -----------------------


class TestFileInfoFor:
    """Codex PR #179 round 3：樁列的 0 不得被 ⚙ 重刮沿用。"""

    def _existing(self, size, mtime):
        from core.database import Video
        return Video(path="file:///x.mp4", size_bytes=size, mtime=mtime)

    def test_zero_stats_existing_is_restatted(self, tmp_path):
        from core.readonly_producer import _file_info_for
        f = tmp_path / "v.mp4"
        f.write_bytes(b"1234567890")

        info = _file_info_for(str(f), self._existing(0, 0.0))

        assert info["size"] == 10, "樁列的 0 必須被現場量到的值取代"
        assert info["mtime"] > 0


class TestReadonlyStubNotFound:
    """TASK-105-T5 (T2-a): _readonly_stub_not_found(repo, uri, number, fs_path)
    collapses the 3 not-found stub call sites (S1 scraper.py enrich-single,
    S2 scraper.py batch, S3 readonly_producer.py bulk produce_source) into one
    helper. Core invariant: insert_if_ignore MUST run before
    update_scrape_attempted_at (the latter is a bare UPDATE...WHERE path=?
    that silently no-ops without a row — see video.py:1144-1167)."""


    def test_stub_carries_file_stats_from_scan(self):
        """掃描端已經有 size/mtime，樁列要帶著走（不重複 stat）。"""
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        _readonly_stub_not_found(
            repo, "file:///src/x.mp4", "X-001", "/src/does-not-exist.mp4",
            size_bytes=4242, mtime=1700000000.0,
        )

        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.size_bytes == 4242
        assert inserted.mtime == 1700000000.0


# ---------------------------------------------------------------------------
# TASK-109-T2 (AC7): enrich_one_readonly — the public entry point, callable
# directly without going through HTTP. `resolve_ingest_plan` / `_produce_one` /
# `compute_has_servable_cover` are mocked (patched at their core.readonly_producer
# module-global binding — the module IS the definition site here, unlike the
# router's use-site patches); `apply_cover_preserve` / `cover_uri_is_servable` /
# `enrich_success` run for real (thin contract helpers, same pattern as
# test_readonly_enrich_contract_parity.py's runner C).
# ---------------------------------------------------------------------------

class TestEnrichOneReadonlyEntryPoint:
    def _base_kwargs(self, repo_factory, **overrides):
        kwargs = dict(
            repo_factory=repo_factory,
            ro_source=SimpleNamespace(name="ro_src"),
            output_root="/out",
            output_uri="file:///out",
            canonical="file:///src/videos/ABC-001.mp4",
            file_path="file:///src/videos/ABC-001.mp4",
            number="ABC-001",
            scraper_cfg={},
            path_mappings={},
            action="ingest",
            scraper_data=None,
            scrape_source=None,
            javbus_lang=None,
            write_cover=True,
            overwrite_existing=False,
        )
        kwargs.update(overrides)
        return kwargs

    def _existing_stub(self, cover_path=""):
        return SimpleNamespace(size_bytes=123, mtime=456.0, cover_path=cover_path)


    def _existing_for_preserve(self, tmp_path, *, title, number="ABC-123",
                               actresses=None, disk_title=None, record_body=None,
                               output_name="out"):
        """Build existing stub + optional real old NFO under output_dir for CD-154b-12."""
        from core import readonly_paths
        from core.path_utils import to_file_uri

        out_dir = tmp_path / output_name
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = SimpleNamespace(
            size_bytes=123,
            mtime=456.0,
            cover_path="",
            title=title,
            number=number,
            actresses=actresses if actresses is not None else ["三上悠亜"],
            maker="",
            release_date="",
            output_dir=to_file_uri(str(out_dir)),
        )
        if disk_title is not None:
            src_fs = str(tmp_path / "src" / f"{number}.mp4")
            old_base = readonly_paths._build_old_base(existing, src_fs, {})
            assert old_base, "fixture requires non-empty old_base"
            record_xml = ""
            if record_body is not None:
                record_xml = (
                    "  <openaver_title_record>\n"
                    f"    <written>{disk_title}</written>\n"
                    f"    <body>{record_body}</body>\n"
                    "  </openaver_title_record>\n"
                )
            (out_dir / f"{old_base}.nfo").write_text(
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                "<movie>\n"
                f"  <title>{disk_title}</title>\n"
                f"  <num>{number}</num>\n"
                f"{record_xml}"
                "</movie>\n",
                encoding="utf-8",
            )
        return existing, out_dir


    def test_enrich_one_readonly_oracle_b_disk_mismatch_keeps_existing_verbatim(self, tmp_path):
        """oracle (b)：DB 是使用者自訂標題、舊 NFO 是自訂格式舊標題 → meta 保留自訂值。

        若拿掉 disk≠DB 判斷，磁碟會反推出 '片名' 覆寫使用者自訂標題。
        """
        from core.readonly_producer import enrich_one_readonly

        existing_title = "我的自訂標題"
        existing, _ = self._existing_for_preserve(
            tmp_path,
            title=existing_title,
            disk_title="ABC-123-片名-三上悠亜",
        )
        repo = MagicMock()
        repo.get_by_path.return_value = existing
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-123", "title": "新刮到的日文片名", "maker": "M", "cover": ""}
        src = tmp_path / "src"
        src.mkdir()
        video = src / "ABC-123.mp4"
        video.write_bytes(b"\x00")
        file_uri = to_file_uri(str(video))

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-123"),
                                 {"cover_fs": "/out/ABC-123/ABC-123.jpg", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            result = enrich_one_readonly(**self._base_kwargs(
                repo_factory,
                canonical=file_uri,
                file_path=file_uri,
                number="ABC-123",
                preserve_title=True,
                scraper_cfg={"nfo_title_format": "{num}-{title}-{actor}"},
            ))

        assert mock_produce.call_args.kwargs["meta"]["title"] == existing_title
        assert result.success is True


    # -----------------------------------------------------------------------
    # TASK-112b-T6 §C-5（Opus 追加要求 #2）：CD-112-15 正向鎖必須至少一支穿
    # `enrich_one_readonly` 的真實 preserve gate（讓 `cover_uri_is_servable`
    # 真的被評估——existing.cover_path 指向磁碟上一個真實存在的檔案，不是
    # 手搭 `('none',)` 餵給 `_write_movie_assets`），驗「什麼情況下會收到
    # ('none',)」這件事本身，而不只是「_write_movie_assets 收到 ('none',)
    # 會怎樣」（真理表 Table 2 #5，與非唯讀 Table 1 #3 刻意不一致）。
    # -----------------------------------------------------------------------


# ============ TASK-126-T4b：代理網址走到 readonly 的下載點 ============
#
# 本 task 的整個風險是「函式對了但值沒走到」——那種缺口在單測層是**綠的**
# （T4a 的 283 條照樣全過）。所以這幾條一律從 `_write_movie_assets` 這個
# **caller 入口**打進去，不是直接呼叫 `download_image`。
#
# mock 目標是**使用端 binding**（`core.readonly_producer.requests` 底下的
# `core.organizer.requests.get`）——`download_image` 是
# `from core.organizer import download_image` 進來的（BE-TEST-01）。

from unittest.mock import patch as _t4b_patch

from core.readonly_assets import _write_movie_assets

_T4B_DIRECT = b'DIRECT' + b'\x00' * 2000
_T4B_PROXY = b'PROXY' + b'\x00' * 2000


class _T4bReadonlyBase:
    """每支測試前後清 process 級失敗記憶（T4a review：它不分呼叫端，會跨測試污染）。"""

    def _clear_failed_hosts(self):
        import core.organizer as org
        with org._failed_hosts_lock:
            org._failed_hosts.clear()

    def _resp(self, content):
        m = MagicMock()
        m.status_code = 200
        m.content = content
        return m

    def _fake_get(self, proxy_host='mt.example'):
        """原址一律 ConnectTimeout，代理一律成功。"""
        import requests as _rq

        def _side(url, **kwargs):
            if proxy_host in url:
                return self._resp(_T4B_PROXY)
            raise _rq.exceptions.ConnectTimeout('blocked')
        return _side


class TestT4bReadonlySamplesOnlyFallback(_T4bReadonlyBase):
    """邊界 3：readonly samples_only（補劇照）入口 → 原址不通時走代理。"""

    def test_samples_only_uses_preview_fallback(self, tmp_path):
        self._clear_failed_hosts()
        try:
            meta = {
                'sample_images': ['https://cdn.blocked/s1.jpg', 'https://cdn.blocked/s2.jpg'],
                'preview_sample_images': [
                    'http://mt.example/v1/images/primary/MGS/N-1?url=s1',
                    'http://mt.example/v1/images/primary/MGS/N-1?url=s2',
                ],
            }
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', side_effect=self._fake_get()):
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={}, source_fs_path='',
                    config={}, cover_strategy=('none',), assets_mode='samples_only',
                )
            assert len(out['sample_fs']) == 2, '兩張劇照都應該經由代理落地'
            for p in out['sample_fs']:
                assert open(p, 'rb').read() == _T4B_PROXY
        finally:
            self._clear_failed_hosts()


    def test_short_preview_does_not_truncate(self, tmp_path):
        """邊界 8：preview 比 sample 短 → 缺的格當 '' ，**不得少下載**。"""
        self._clear_failed_hosts()
        try:
            meta = {
                'sample_images': ['https://cdn.ok/s1.jpg', 'https://cdn.ok/s2.jpg', 'https://cdn.ok/s3.jpg'],
                'preview_sample_images': ['http://mt.example/v1/images/primary/MGS/N-1?url=s1'],
            }
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', return_value=self._resp(_T4B_DIRECT)) as mg:
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={}, source_fs_path='',
                    config={}, cover_strategy=('none',), assets_mode='samples_only',
                )
            assert len(out['sample_fs']) == 3, 'zip 截斷會讓這裡變成 1'
            assert mg.call_count == 3
        finally:
            self._clear_failed_hosts()


class TestT4bReadonlyFullCoverFallback(_T4bReadonlyBase):
    """邊界 2：readonly full 模式封面 → CD-126-9（fallback 從 meta 取，不動 tuple）。"""

    def test_full_cover_uses_preview_fallback_from_meta(self, tmp_path):
        self._clear_failed_hosts()
        try:
            meta = {
                'number': 'N-1', 'title': 'T', 'actors': [], 'tags': [],
                'sample_images': [], 'preview_sample_images': [],
                'preview_cover_url': 'http://mt.example/v1/images/primary/MGS/N-1?url=cover',
            }
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', side_effect=self._fake_get()):
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={'number': 'N-1'},
                    source_fs_path=str(tmp_path / 'src.mp4'), config={},
                    cover_strategy=('download', 'https://cdn.blocked/cover.jpg'),
                    assets_mode='full',
                )
            assert out.get('has_cover') is True or out.get('cover_fs'), '封面應經由代理落地'
        finally:
            self._clear_failed_hosts()


# ============ TASK-126-T4b review MAJOR-2：readonly full 模式的劇照分支 ============
#
# 初版只測了 full 模式的**封面**，而且那支的 meta 是 `sample_images: []`（劇照迴圈根本不會跑）。
# review 在沙盒把 full 分支的 preview 傳遞整段拔掉，335 條照樣全綠 ⇒ 這個下載點沒人守。


# ===========================================================================
# TASK-143-T3 (CD-143-6): resolve_ingest_plan maker normalization
# ===========================================================================

class TestResolveIngestPlanMakerNormalization:
    """TASK-143-T3: resolve_ingest_plan 尾端片商正規化對齊（NFO 分支 ＋ 爬蟲分支）。"""

    def _touch_video(self, tmp_path, name='SRC-001.mp4'):
        p = tmp_path / name
        p.write_bytes(b'FAKE')
        return p

    def test_nfo_branch_name_mapping_applied(self, tmp_path):
        """NFO 分支：sidecar NFO 的 <maker> 為 'S1 NO.1 STYLE'（name_mapping key）
        → resolve_ingest_plan 回傳之 meta['maker'] 被正規化為 'S1'。"""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, 'S1-001.mp4')
        nfo = video.with_suffix('.nfo')
        nfo.write_text(
            '<movie><num>S1-001</num><title>T</title><maker>S1 NO.1 STYLE</maker></movie>',
            encoding='utf-8',
        )

        meta, cover_strategy = resolve_ingest_plan(str(video), 'S1-001', {}, action='ingest')

        assert meta is not None
        assert meta['maker'] == 'S1'

    def test_scrape_branch_prefix_mapping_applied(self, tmp_path):
        """爬蟲分支：search_jav 回傳 number='SSIS-001'、maker='Raw Maker Name'（不在 name_mapping）
        → 透過 prefix_mapping['SSIS'] == 'S1' 正規化為 'S1'。"""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, 'SSIS-001.mp4')
        raw_meta = {
            'number': 'SSIS-001',
            'title': 'T',
            'cover': '',
            'maker': 'Raw Maker Name',
        }

        with patch('core.readonly_producer.search_jav', return_value=raw_meta):
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SSIS-001', {}, action='ingest')

        assert meta is not None
        assert meta['maker'] == 'S1'


# ---------------------------------------------------------------------------
# TASK-143-T5: Readonly NFO user_tags threading
# ---------------------------------------------------------------------------

class TestWriteMovieAssetsUserTags:
    def test_write_movie_assets_writes_user_tags_to_nfo(self, tmp_path):
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = tmp_path / "movie"
        movie_dir.mkdir()
        meta = {"number": "TEST-001", "title": "Test Title"}
        config = {"external_manager": "off"}
        fd = _format_data(meta, "/src/TEST-001.mp4", config)

        _write_movie_assets(
            str(movie_dir), meta, fd, "/src/TEST-001.mp4", config,
            cover_strategy=("none",), user_tags=["★4"],
        )

        nfo_files = list(movie_dir.glob("*.nfo"))
        assert len(nfo_files) == 1
        content = nfo_files[0].read_text(encoding="utf-8")
        assert "<user_tag>★4</user_tag>" in content


class TestProduceOneUserTags:
    def test_produce_one_passes_existing_user_tags_to_write_movie_assets(self, tmp_path):
        from core.database import Video
        from core.readonly_producer import _produce_one

        output_root = tmp_path / "output"
        output_root.mkdir()
        file_info = {"path": "/src/TEST-001.mp4", "size": 1000, "mtime": 1.0}
        meta = {"number": "TEST-001", "title": "Test"}
        existing = Video(path="file:///src/TEST-001.mp4", number="TEST-001", title="Test", user_tags=["custom"])
        repo = MagicMock()

        with patch("core.readonly_paths._resolve_movie_dir",
                   return_value=(tmp_path / "output" / "TEST-001", "file:///whatever-db-uri")), \
             patch("core.readonly_assets._write_movie_assets",
                   return_value={"nfo_mtime": 1.0, "cover_fs": "", "sample_fs": []}) as mock_write, \
             patch("core.readonly_producer._upsert_db"):
            _produce_one(
                repo, None, {"scraper": {}},
                file_info=file_info, meta=meta, cover_strategy=("none",),
                assets_mode="full", existing=existing,
                output_root=str(output_root), output_uri="file:///output",
                allocated_this_run=set(), path_mappings={},
            )
        assert mock_write.call_args.kwargs["user_tags"] == ["custom"]


# ---------------------------------------------------------------------------
# TASK-151b-T2 (CD-151b-3): _resolve_readonly_preserved_fields — 洞二讀回
# ---------------------------------------------------------------------------

NORMAL_NFO_TEXT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<movie>\n'
    '  <plot>A normal summary.</plot>\n'
    '  <rating>8.0</rating>\n'
    '  <website>https://example.com/v</website>\n'
    '</movie>\n'
)

BROKEN_NFO_TEXT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<movie>\n'
    '  <title>ABC-100 New Title</title>\n'
    '  <plot>truncated content with no closing tag'
)
BROKEN_NFO_BYTES = BROKEN_NFO_TEXT.encode("utf-8")


class TestResolveReadonlyPreservedFields:

    def test_missing_one_field_old_base_nfo_reads_back_rating_halved(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'ABC-100.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {
            'number': 'ABC-100', 'title': 'T',
            '_summary': 'existing summary', 'url': 'https://existing',
        }

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'ABC-100', 'XYZ-999', False,
        )

        assert result is True
        assert meta['_rating'] == 4.0
        assert meta['_summary'] == 'existing summary'
        assert meta['url'] == 'https://existing'
        # C-2：寫回的 key 必須是帶底線的 `_rating`，不是映射後的 `rating`——
        # 逐字鎖 meta 的 key 集合，避免「多寫了一個 `rating`」被漏測。
        assert set(meta.keys()) == {'number', 'title', '_summary', 'url', '_rating'}


    def test_old_base_broken_fails_closed_does_not_try_new_base(self, tmp_path):
        from core.nfo_updater import parse_nfo
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'OLD-1.nfo').write_bytes(BROKEN_NFO_BYTES)
        (tmp_path / 'NEW-1.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.parse_nfo', wraps=parse_nfo) as mock_parse:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'OLD-1', 'NEW-1', False,
            )

        assert result is False
        assert mock_parse.call_count == 1
        called_path = mock_parse.call_args.args[0]
        assert called_path.endswith('OLD-1.nfo')


# ---------------------------------------------------------------------------
# TASK-151b-T4 (CD-151b-1): _produce_one 接線整合測試 — 讀回／改名／DB CAS
# 三個機制串起來的整輪行為。全部直接呼叫 _produce_one（不經
# enrich_one_readonly），真實 tmp_path 檔案 + 真實 VideoRepository(temp_db)，
# 只 mock download_image / generate_jellyfin_images（避免網路／真圖片處理），
# generate_nfo 刻意不 mock——用真實實作寫出含 plot/rating/website 的 NFO，
# 讓「讀回」測試真的有內容可讀。
# ---------------------------------------------------------------------------

_T4R_META_A = {
    'number': 'TEST-001',
    'title': 'Old Title',
    'cover': 'https://example.com/cover.jpg',
    'actors': ['Actress A'],
    'tags': ['tag1'],
    'date': '2024-01-01',
    'maker': 'Test Maker',
    'director': '',
    'series': '',
    'label': '',
    'sample_images': [],
    'duration': 100,
    '_summary': 'Round A summary',
    '_rating': 4.0,
    'url': 'https://example.com/round-a',
}


def _t4r_dir_snapshot(root: Path) -> dict:
    """相對路徑 → sha256，用於「呼叫前後輸出資料夾逐位元組相同」斷言。"""
    import hashlib

    out = {}
    for p in sorted(root.rglob('*')):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _t4r_setup(tmp_path, repo, meta_a=None, config=None):
    """Round A：真實 _produce_one 呼叫，建立 old_base 的基線（DB row + 磁碟檔案）。"""
    from core.readonly_producer import _produce_one

    cfg = config or dict(_T3_BASE_CONFIG)
    meta_a = dict(meta_a or _T4R_META_A)
    src_fs = str(tmp_path / 'src' / 'TEST-001.mp4')
    Path(src_fs).parent.mkdir(parents=True, exist_ok=True)
    Path(src_fs).write_bytes(b'FAKE-VIDEO-BYTES')
    output_root = tmp_path / 'output'
    output_root.mkdir()
    output_uri = to_file_uri(str(output_root), {})
    file_info = {'path': src_fs, 'size': 1_000_000, 'mtime': 1.0}

    with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
         patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin):
        movie_dir, _assets = _produce_one(
            repo, MagicMock(), cfg,
            file_info=file_info, meta=dict(meta_a), cover_strategy=_cover_strategy_for(meta_a),
            assets_mode='full', existing=None,
            output_root=str(output_root), output_uri=output_uri,
            allocated_this_run=set(), path_mappings={},
        )

    src_uri = to_file_uri(src_fs, {})
    existing = repo.get_by_path(src_uri)
    return {
        'output_root': output_root,
        'output_uri': output_uri,
        'file_info': file_info,
        'src_uri': src_uri,
        'existing': existing,
        'movie_dir': Path(movie_dir),
        'config': cfg,
        'meta_a': meta_a,
    }


def _t4r_round2(repo, ctx, meta, cover_strategy, *, download_side_effect=None,
                 generate_nfo_patch=None, assets_mode='full'):
    """後續一輪真實 _produce_one 呼叫，沿用 ctx['existing']（呼叫端自行決定是否
    在呼叫之間重新 repo.get_by_path 刷新它——DoD⑧ 刻意不刷新）。`assets_mode`
    預設 'full'；補劇照回歸測試傳 'samples_only'。"""
    from contextlib import ExitStack

    from core.readonly_producer import _produce_one

    with ExitStack() as stack:
        stack.enter_context(patch(
            'core.readonly_assets.download_image',
            side_effect=download_side_effect or _t4_real_download,
        ))
        stack.enter_context(patch(
            'core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin,
        ))
        if generate_nfo_patch is not None:
            stack.enter_context(generate_nfo_patch)
        return _produce_one(
            repo, MagicMock(), ctx['config'],
            file_info=ctx['file_info'], meta=dict(meta), cover_strategy=cover_strategy,
            assets_mode=assets_mode, existing=ctx['existing'],
            output_root=str(ctx['output_root']), output_uri=ctx['output_uri'],
            allocated_this_run=set(), path_mappings={},
        )


class TestProduceOneReadonlyRename:
    """TASK-151b-T4：`_produce_one` 接線（CD-151b-1）——DoD①-⑨。"""

    _OLD_BASE = 'TEST-001 Old Title'
    _NEW_BASE = 'TEST-001 New Title'

    def test_fail_closed_leaves_output_dir_byte_identical(self, tmp_path, temp_db):
        """DoD①／mutation 點①：AC-4b 第三種形狀（標題變更＋只缺一欄＋既有
        NFO 壞掉）→ 整輪失敗，呼叫前後輸出資料夾逐位元組相同（D-151b-10
        不變式：讀回必須排在任何改名／寫檔之前）。"""
        from core.database import VideoRepository
        from core.readonly_producer import ReadonlyProduceError

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        nfo_path = ctx['movie_dir'] / f'{self._OLD_BASE}.nfo'
        assert nfo_path.exists(), 'sanity: round A 寫出的舊 NFO 應存在'
        nfo_path.write_bytes(BROKEN_NFO_BYTES)

        meta_b = dict(_T4R_META_A, title='New Title')
        meta_b.pop('_summary', None)  # 只缺一欄

        before = _t4r_dir_snapshot(ctx['movie_dir'])

        with pytest.raises(ReadonlyProduceError):
            _t4r_round2(repo, ctx, meta_b, ('none',))

        after = _t4r_dir_snapshot(ctx['movie_dir'])
        assert after == before

    def test_produce_one_rename_and_preserve_end_to_end(self, tmp_path, temp_db):
        """DoD②：正常情境（無讀回失敗）下 AC-1/AC-2 的端到端斷言在
        `_produce_one` 層級成立——封面改名到新基底、簡介/評分/來源網址讀回
        舊值、DB title/cover_path 更新。"""
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        meta_b = dict(_T4R_META_A, title='New Title')
        for k in ('_summary', '_rating', 'url'):
            meta_b.pop(k, None)

        movie_dir, assets = _t4r_round2(repo, ctx, meta_b, ('none',))

        d = Path(movie_dir)
        assert d == ctx['movie_dir']
        assert not any(p.name.startswith(self._OLD_BASE) for p in d.iterdir()), (
            "old_base 檔案（含 nfo）必須零殘留"
        )
        nfo_path = d / f'{self._NEW_BASE}.nfo'
        assert nfo_path.exists()
        root = ET.parse(nfo_path).getroot()
        assert root.findtext('plot') == _T4R_META_A['_summary']
        assert float(root.findtext('rating')) == _T4R_META_A['_rating'] * 2
        assert root.findtext('website') == _T4R_META_A['url']

        v = repo.get_by_path(ctx['src_uri'])
        assert v.title == 'New Title'
        assert v.cover_path.startswith('file:///')
        assert self._NEW_BASE in v.cover_path
        assert self._OLD_BASE not in v.cover_path

    def test_upsert_after_produce_one_preserves_focal_fields(self, tmp_path, temp_db):
        """DoD③：手動對焦座標（模擬使用者已拖曳過遮罩）在標題漂移＋封面改名
        這一輪之後不被重置——CAS 先同步 cover_path，`_upsert_db` 的
        CASE WHEN 比對才會判定「封面沒變」而保留 auto_focal/crop_mode。"""
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        manual_focal = '0.3148,0.2000'
        ok = repo.update_manual_focal(ctx['src_uri'], manual_focal, ctx['existing'].cover_path)
        assert ok is True
        existing_with_focal = repo.get_by_path(ctx['src_uri'])
        assert existing_with_focal.crop_mode == 'manual'
        assert existing_with_focal.auto_focal == manual_focal
        ctx['existing'] = existing_with_focal
        before_cover_path = existing_with_focal.cover_path
        before_focal_attempted_at = existing_with_focal.focal_attempted_at

        meta_b = dict(_T4R_META_A, title='New Title')

        _t4r_round2(repo, ctx, meta_b, ('none',))

        v = repo.get_by_path(ctx['src_uri'])
        assert v.cover_path != before_cover_path, (
            "sanity: 封面確實改名（cover_path 真的變了），否則這條測不出這支要鎖的機制"
        )
        assert v.crop_mode == 'manual'
        assert v.auto_focal == manual_focal
        assert v.focal_attempted_at == before_focal_attempted_at

    def test_write_movie_assets_failure_reverts_rename_no_db_write(self, tmp_path, temp_db):
        """DoD④／mutation 點②：`_write_movie_assets`（NFO 寫入）失敗 → 已搬動
        的圖片復原、輸出資料夾逐位元組回到呼叫前狀態、DB 完全沒被寫入
        （CAS 從未被呼叫）。"""
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        meta_b = dict(_T4R_META_A, title='New Title')
        before_dir = _t4r_dir_snapshot(ctx['movie_dir'])
        before_db = repo.get_by_path(ctx['src_uri'])

        with patch.object(repo, 'update_cover_path_preserve_focal') as mock_cas:
            with pytest.raises(RuntimeError):
                _t4r_round2(
                    repo, ctx, meta_b, ('none',),
                    generate_nfo_patch=patch('core.readonly_assets.generate_nfo', return_value=False),
                )
        mock_cas.assert_not_called()

        after_dir = _t4r_dir_snapshot(ctx['movie_dir'])
        assert after_dir == before_dir
        after_db = repo.get_by_path(ctx['src_uri'])
        assert after_db == before_db


    def test_cas_operational_error_reverts_photos_db_unchanged(self, tmp_path, temp_db):
        """DoD⑥：CAS 拋出 sqlite3.OperationalError（無並行流程介入）→ 圖片復原
        （sha256 相同）、DB cover_path/title/focal 三欄與呼叫前逐字相同、原例外
        原樣往外傳。明確不斷言新基底 .nfo 被復原（accepted residual）。"""
        import hashlib
        import sqlite3

        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        old_poster = ctx['movie_dir'] / f'{self._OLD_BASE}-poster.jpg'
        old_fanart = ctx['movie_dir'] / f'{self._OLD_BASE}-fanart.jpg'
        old_poster_sha = hashlib.sha256(old_poster.read_bytes()).hexdigest()
        old_fanart_sha = hashlib.sha256(old_fanart.read_bytes()).hexdigest()
        before_db = repo.get_by_path(ctx['src_uri'])

        meta_b = dict(_T4R_META_A, title='New Title')

        with patch.object(
            repo, 'update_cover_path_preserve_focal',
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            with pytest.raises(sqlite3.OperationalError):
                _t4r_round2(repo, ctx, meta_b, ('none',))

        assert hashlib.sha256(old_poster.read_bytes()).hexdigest() == old_poster_sha
        assert hashlib.sha256(old_fanart.read_bytes()).hexdigest() == old_fanart_sha
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-poster.jpg').exists()
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-fanart.jpg').exists()
        # 明確不斷言的部分（CD-151b-1「CAS 失敗後的最終狀態」accepted residual）：
        # 新基底 .nfo 已經真實寫出，不要求也不能要求被復原。
        assert (ctx['movie_dir'] / f'{self._NEW_BASE}.nfo').exists()

        after_db = repo.get_by_path(ctx['src_uri'])
        assert after_db.cover_path == before_db.cover_path
        assert after_db.title == before_db.title
        assert after_db.auto_focal == before_db.auto_focal
        assert after_db.crop_mode == before_db.crop_mode
        assert after_db.focal_attempted_at == before_db.focal_attempted_at


    def test_ac11_escape_hatch_end_to_end_orphan_reclaimed(self, tmp_path, temp_db):
        """DoD⑨（AC-11 端到端逃生口驗收）：已壞狀態情境（DB 標題已是新標題、
        cover_path 指向舊基底、磁碟上舊名三張圖仍在——升級前就已經踩過洞一
        bug 留下的孤兒，舊佈局三檔形狀）——直接呼叫 `_produce_one`（不是直接
        呼叫 `_rename_stale_cover_group`），這一輪標題不再變 → 孤兒圖被改名
        歸位、舊名零殘留、DB cover_path 更新為新值、`_produce_one` 本身成功
        回傳。"""
        import hashlib

        from core.database import Video, VideoRepository
        from core.readonly_producer import _produce_one

        repo = VideoRepository(temp_db)
        src_fs = str(tmp_path / 'src' / 'TEST-001.mp4')
        Path(src_fs).parent.mkdir(parents=True, exist_ok=True)
        Path(src_fs).write_bytes(b'FAKE-VIDEO-BYTES')
        output_root = tmp_path / 'output'
        output_root.mkdir()
        output_uri = to_file_uri(str(output_root), {})
        movie_dir = output_root / 'TEST-001'
        movie_dir.mkdir()

        old_base = 'TEST-001 Old Title'
        new_base = 'TEST-001 Current Title'

        cover = movie_dir / f'{old_base}.jpg'
        poster = movie_dir / f'{old_base}-poster.jpg'
        fanart = movie_dir / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'ORPHAN COVER')
        poster.write_bytes(b'ORPHAN POSTER')
        fanart.write_bytes(b'ORPHAN FANART')
        cover_sha = hashlib.sha256(cover.read_bytes()).hexdigest()
        poster_sha = hashlib.sha256(poster.read_bytes()).hexdigest()
        fanart_sha = hashlib.sha256(fanart.read_bytes()).hexdigest()
        # {new_base}.nfo 已存在（上一輪 NFO 早就寫對了，只有圖沒跟上）；
        # {old_base}.nfo 不存在（已被既有 _clean_stale_singletons 清過）。
        (movie_dir / f'{new_base}.nfo').write_bytes(b'<movie></movie>')

        src_uri = to_file_uri(src_fs, {})
        seed = Video(
            path=src_uri, number='TEST-001', title='Current Title',
            actresses=['Actress A'], maker='Test Maker', release_date='2024-01-01',
            cover_path=to_file_uri(str(cover), {}), output_dir=to_file_uri(str(movie_dir), {}),
        )
        repo.upsert(seed)
        existing = repo.get_by_path(src_uri)
        assert existing.cover_path == to_file_uri(str(cover), {})

        meta = {
            'number': 'TEST-001', 'title': 'Current Title', 'actors': ['Actress A'],
            'tags': [], 'date': '2024-01-01', 'maker': 'Test Maker', 'director': '',
            'series': '', 'label': '', 'sample_images': [], 'duration': 100,
            '_summary': 's', '_rating': 3.0, 'url': 'https://example.com/u',
        }
        file_info = {'path': src_fs, 'size': 1_000_000, 'mtime': 1.0}
        config = dict(_T3_BASE_CONFIG)

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin):
            result_movie_dir, _assets = _produce_one(
                repo, MagicMock(), config,
                file_info=file_info, meta=meta, cover_strategy=('none',),
                assets_mode='full', existing=existing,
                output_root=str(output_root), output_uri=output_uri,
                allocated_this_run=set(), path_mappings={},
            )

        assert Path(result_movie_dir) == movie_dir
        assert not cover.exists()
        assert not poster.exists()
        assert not fanart.exists()
        new_cover = movie_dir / f'{new_base}.jpg'
        new_poster = movie_dir / f'{new_base}-poster.jpg'
        new_fanart = movie_dir / f'{new_base}-fanart.jpg'
        assert hashlib.sha256(new_cover.read_bytes()).hexdigest() == cover_sha
        assert hashlib.sha256(new_poster.read_bytes()).hexdigest() == poster_sha
        assert hashlib.sha256(new_fanart.read_bytes()).hexdigest() == fanart_sha
        assert not any(p.name.startswith(old_base) for p in movie_dir.iterdir())

        v = repo.get_by_path(src_uri)
        assert v.cover_path == to_file_uri(str(new_cover), {})


    def test_samples_only_does_not_trigger_rename_or_readback(self, tmp_path, temp_db):
        """回歸修正①（Codex PR#197 review，第 4 輪）：`assets_mode='samples_only'`
        （補劇照）＋ 來源標題與 DB 不同 ＋ `cover_strategy=('none',)` → 洞一改
        名與洞二讀回都不得介入——`samples_only` 的既有承諾是「只碰
        extrafanart，不碰 metadata/cover」。修前：封面會被搬到新基底，但
        `_write_movie_assets` 在 samples_only 早退不寫 NFO、`_upsert_db` 也不
        更新 title ⇒ NFO 舊名、圖新名、DB 標題舊、cover_path 新——方向反過來
        的孤兒，比原本要修的 bug 更糟。"""
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)
        before_cover_path = ctx['existing'].cover_path
        before_title = ctx['existing'].title

        meta_b = dict(
            _T4R_META_A, title='New Title',
            sample_images=['https://example.com/s1.jpg', 'https://example.com/s2.jpg'],
        )

        movie_dir, assets = _t4r_round2(repo, ctx, meta_b, ('none',), assets_mode='samples_only')

        d = Path(movie_dir)
        assert (d / f'{self._OLD_BASE}.nfo').exists(), "舊基底 NFO 不得被清掉"
        assert (d / f'{self._OLD_BASE}-poster.jpg').exists()
        assert (d / f'{self._OLD_BASE}-fanart.jpg').exists()
        assert not (d / f'{self._NEW_BASE}.nfo').exists(), "samples_only 不寫 NFO，新基底不該出現任何檔"
        assert not (d / f'{self._NEW_BASE}-poster.jpg').exists()
        assert not (d / f'{self._NEW_BASE}-fanart.jpg').exists()

        v = repo.get_by_path(ctx['src_uri'])
        assert v.title == before_title, "samples_only 不得更新 title"
        assert v.cover_path == before_cover_path, "samples_only 不得改名／同步 cover_path"
        assert len(v.sample_images) == 2, "補劇照本身要正常成功、劇照要真的抓回來"


    def test_produce_one_first_generation_missing_dir_meta_incomplete_succeeds(
        self, tmp_path, temp_db,
    ):
        """邊界條件 8：existing=None、輸出目錄尚未建立、meta 缺三欄 →
        `_produce_one` 整輪正常成功（決策表列 3 的整合層）。"""
        from core.database import VideoRepository
        from core.readonly_producer import _produce_one

        repo = VideoRepository(temp_db)
        src_fs = str(tmp_path / 'src' / 'TEST-001.mp4')
        Path(src_fs).parent.mkdir(parents=True, exist_ok=True)
        Path(src_fs).write_bytes(b'FAKE-VIDEO-BYTES')
        output_root = tmp_path / 'output'
        output_root.mkdir()
        output_uri = to_file_uri(str(output_root), {})
        file_info = {'path': src_fs, 'size': 1_000_000, 'mtime': 1.0}

        meta = dict(_T4R_META_A)
        for k in ('_summary', '_rating', 'url'):
            meta.pop(k, None)

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin):
            movie_dir, assets = _produce_one(
                repo, MagicMock(), dict(_T3_BASE_CONFIG),
                file_info=file_info, meta=meta, cover_strategy=_cover_strategy_for(meta),
                assets_mode='full', existing=None,
                output_root=str(output_root), output_uri=output_uri,
                allocated_this_run=set(), path_mappings={},
            )

        assert Path(movie_dir).is_dir()
        assert list(Path(movie_dir).glob('*.nfo')), "首次產出必須寫出 NFO"
        v = repo.get_by_path(to_file_uri(src_fs, {}))
        assert v is not None
        assert v.number == 'TEST-001'


