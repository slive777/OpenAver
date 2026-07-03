"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.path_utils import to_file_uri


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
    def test_zero_when_not_set(self):
        from core.readonly_producer import _min_size_bytes
        assert _min_size_bytes({}) == 0

    def test_converts_mb_to_bytes(self):
        from core.readonly_producer import _min_size_bytes
        assert _min_size_bytes({"min_size_mb": 2}) == 2 * 1024 * 1024

    def test_truncates_float(self):
        from core.readonly_producer import _min_size_bytes
        # int() truncates
        assert _min_size_bytes({"min_size_mb": 1.9}) == 1 * 1024 * 1024

    def test_zero_explicit(self):
        from core.readonly_producer import _min_size_bytes
        assert _min_size_bytes({"min_size_mb": 0}) == 0


# ---------------------------------------------------------------------------
# _list_source_videos
# ---------------------------------------------------------------------------

FAKE_FILES = [
    {"path": "/src/a.mp4", "mtime": 1.0, "size": 100, "nfo_mtime": 0.0},
    {"path": "/src/b.mkv", "mtime": 2.0, "size": 200, "nfo_mtime": 0.0},
]


class TestListSourceVideos:
    def test_calls_fast_scan_with_normalised_path(self):
        """_list_source_videos must delegate to fast_scan_directory (no direct read)."""
        from core.readonly_producer import _list_source_videos

        with patch("core.readonly_producer.fast_scan_directory", return_value=FAKE_FILES) as mock_scan, \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/src") as mock_coerce:
            result = _list_source_videos("/src", {".mp4", ".mkv"}, 0)

        mock_coerce.assert_called_once_with("/src")
        mock_scan.assert_called_once_with("/src", {".mp4", ".mkv"}, 0)
        assert result == FAKE_FILES

    def test_returns_raw_list_unchanged(self):
        from core.readonly_producer import _list_source_videos

        with patch("core.readonly_producer.fast_scan_directory", return_value=FAKE_FILES), \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/src"):
            result = _list_source_videos("/src", {".mp4"}, 1024)

        assert result is FAKE_FILES

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
# _should_skip  (truth table — 4 cases)
# ---------------------------------------------------------------------------

class TestShouldSkip:
    OUTPUT_URI = "file:///output"
    COVER_URI = "file:///output/movie/cover.jpg"
    SOURCE_URI = "file:///src/a.mp4"

    def test_no_row_returns_false(self):
        """cover_index has no entry for source_uri → rebuild."""
        from core.readonly_producer import _should_skip
        cover_index = {}
        assert _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, {}) is False

    def test_cover_under_output_but_file_missing_returns_false(self):
        """cover is under output but file does not exist on disk → rebuild."""
        from core.readonly_producer import _should_skip
        cover_index = {self.SOURCE_URI: self.COVER_URI}

        with patch("core.readonly_producer.is_path_under_dir", return_value=True), \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/output/movie/cover.jpg"), \
             patch("core.readonly_producer.Path") as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.exists.return_value = False
            mock_path_cls.return_value = mock_path_inst
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, {})

        assert result is False

    def test_cover_not_under_output_returns_false(self):
        """cover is not under this output_uri → rebuild."""
        from core.readonly_producer import _should_skip
        cover_index = {self.SOURCE_URI: "file:///other/cover.jpg"}

        with patch("core.readonly_producer.is_path_under_dir", return_value=False):
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, {})

        assert result is False

    def test_all_conditions_met_returns_true(self):
        """cover under output AND file exists → skip."""
        from core.readonly_producer import _should_skip
        cover_index = {self.SOURCE_URI: self.COVER_URI}

        with patch("core.readonly_producer.is_path_under_dir", return_value=True), \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/output/movie/cover.jpg"), \
             patch("core.readonly_producer.Path") as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.exists.return_value = True
            mock_path_cls.return_value = mock_path_inst
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, {})

        assert result is True

    def test_mapped_cover_reverse_resolved_under_wsl_returns_true(self, tmp_path):
        """Codex Finding 1 regression lock.

        cover_path in cover_index is forward-mapped (as stored by _upsert_db via
        to_file_uri(assets['cover_fs'], path_mappings)). Under CURRENT_ENV='wsl'
        with path_mappings configured, _should_skip must reverse-map the cover
        path back to the real local FS path before calling .exists() — mirroring
        _resolve_movie_dir's reuse-branch pattern (TASK-89a-T5). Without the
        reverse-map, uri_to_fs_path(cover) resolves to a UNC-style path that never
        exists locally, so this test goes RED if the reverse-map call is removed.
        """
        from core.readonly_producer import _should_skip

        # Real local file that the forward-mapped URI should reverse-resolve to.
        real_dir = tmp_path / "movie"
        real_dir.mkdir()
        real_cover = real_dir / "cover.jpg"
        real_cover.write_bytes(b"x")

        # cover_path as stored in DB: forward-mapped to a Windows-style UNC path.
        mapped_cover_uri = "file://///server/share/movie/cover.jpg"
        path_mappings = {"\\\\server\\share": str(tmp_path)}
        cover_index = {self.SOURCE_URI: mapped_cover_uri}

        with patch("core.readonly_producer.is_path_under_dir", return_value=True), \
             patch("core.readonly_producer.CURRENT_ENV", "wsl"), \
             patch(
                 "core.readonly_producer.uri_to_fs_path",
                 return_value="//server/share/movie/cover.jpg",
             ), \
             patch(
                 "core.readonly_producer.reverse_path_mapping",
                 return_value=str(real_cover),
             ) as mock_reverse:
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, path_mappings)

        mock_reverse.assert_called_once_with("//server/share/movie/cover.jpg", path_mappings)
        assert result is True

    def test_mapped_cover_without_reverse_map_would_return_false(self):
        """Same mapped-cover scenario but simulating the pre-fix bug: if the
        reverse-map step is skipped, .exists() is checked against the raw
        (non-reversed) uri_to_fs_path output, which does not exist on disk →
        False. This documents the exact failure mode Finding 1 reported
        (incremental skip broken under WSL + path_mappings).
        """
        from core.readonly_producer import _should_skip

        mapped_cover_uri = "file://///server/share/movie/cover.jpg"
        path_mappings = {"\\\\server\\share": "/mnt/x"}
        cover_index = {self.SOURCE_URI: mapped_cover_uri}

        with patch("core.readonly_producer.is_path_under_dir", return_value=True), \
             patch("core.readonly_producer.CURRENT_ENV", "wsl"), \
             patch(
                 "core.readonly_producer.uri_to_fs_path",
                 return_value="//server/share/movie/cover.jpg",
             ):
            # No patch of reverse_path_mapping: real implementation runs and will
            # not map this bogus UNC path to anything that exists on disk, so the
            # unresolved raw path is used for .exists() — reproducing the bug.
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index, path_mappings)

        assert result is False

    def test_no_path_mappings_or_non_wsl_behaves_as_before(self):
        """Degenerate case: no path_mappings, or not on WSL → no reverse-map
        attempted, behavior identical to pre-fix (plain uri_to_fs_path + exists).
        """
        from core.readonly_producer import _should_skip
        cover_index = {self.SOURCE_URI: self.COVER_URI}

        with patch("core.readonly_producer.is_path_under_dir", return_value=True), \
             patch("core.readonly_producer.CURRENT_ENV", "windows"), \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/output/movie/cover.jpg"), \
             patch("core.readonly_producer.reverse_path_mapping") as mock_reverse, \
             patch("core.readonly_producer.Path") as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.exists.return_value = True
            mock_path_cls.return_value = mock_path_inst
            result = _should_skip(
                self.SOURCE_URI, self.OUTPUT_URI, cover_index, {"\\\\server\\share": "/mnt/x"}
            )

        mock_reverse.assert_not_called()
        assert result is True


# ---------------------------------------------------------------------------
# _build_cover_index
# ---------------------------------------------------------------------------

class TestBuildCoverIndex:
    OUTPUT_URI = "file:///output"

    def _make_repo(self, full_index: dict) -> MagicMock:
        repo = MagicMock()
        repo.get_cover_index.return_value = full_index
        return repo

    def test_filters_out_empty_cover(self):
        from core.readonly_producer import _build_cover_index
        repo = self._make_repo({
            "file:///src/a.mp4": "",
            "file:///src/b.mp4": "file:///output/b/cover.jpg",
        })
        with patch("core.readonly_producer.is_path_under_dir",
                   side_effect=lambda c, o: c.startswith("file:///output")):
            result = _build_cover_index(repo, self.OUTPUT_URI)

        # empty cover must be excluded
        assert "file:///src/a.mp4" not in result
        assert "file:///src/b.mp4" in result

    def test_filters_out_cover_not_under_output(self):
        from core.readonly_producer import _build_cover_index
        repo = self._make_repo({
            "file:///src/a.mp4": "file:///other/cover.jpg",
            "file:///src/b.mp4": "file:///output/b/cover.jpg",
        })
        with patch("core.readonly_producer.is_path_under_dir",
                   side_effect=lambda c, o: c.startswith("file:///output")):
            result = _build_cover_index(repo, self.OUTPUT_URI)

        assert "file:///src/a.mp4" not in result
        assert "file:///src/b.mp4" in result

    def test_empty_db_returns_empty(self):
        from core.readonly_producer import _build_cover_index
        repo = self._make_repo({})
        with patch("core.readonly_producer.is_path_under_dir", return_value=True):
            result = _build_cover_index(repo, self.OUTPUT_URI)
        assert result == {}

    def test_null_cover_filtered(self):
        """None cover_path must be treated as falsy and excluded."""
        from core.readonly_producer import _build_cover_index
        repo = self._make_repo({
            "file:///src/a.mp4": None,
        })
        with patch("core.readonly_producer.is_path_under_dir", return_value=True):
            result = _build_cover_index(repo, self.OUTPUT_URI)
        assert result == {}


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
        from core.readonly_producer import _format_data
        meta = {'number': 'ABC-123', 'title': 'A' * 30}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert len(fd['title']) <= 20
        assert fd['title'].endswith('...')

    def test_prefix_stripped_from_title(self):
        from core.readonly_producer import _format_data
        meta = {'number': 'ABC-123', 'title': '[ABC-123]Original Title'}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert 'ABC-123' not in fd['title']
        assert 'Original Title' in fd['title']

    def test_suffix_detected_from_basename(self):
        from core.readonly_producer import _format_data
        meta = {'number': 'ABC-123', 'title': 'Some Title'}
        fd = _format_data(meta, '/src/ABC-123-C.mp4', self.BASE_CONFIG)
        assert '-c' in fd['suffix'].lower()

    def test_no_suffix_when_no_match(self):
        from core.readonly_producer import _format_data
        meta = {'number': 'ABC-123', 'title': 'Some Title'}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert fd['suffix'] == ''

    def test_truncated_title_consistent_in_folder_and_basename(self):
        """Same truncated title feeds both _folder_parts and _build_basename (no drift)."""
        from core.readonly_producer import _build_basename, _folder_parts, _format_data
        long_title = 'VeryLong' * 5
        meta = {'number': 'ABC-123', 'title': long_title}
        config = {
            'max_title_length': 15,
            'suffix_keywords': [],
            'filename_format': '{num} {title}',
            'max_filename_length': 60,
            'folder_layers': ['{title}'],
        }
        fd = _format_data(meta, '/src/ABC-123.mp4', config)
        folder = _folder_parts(fd, config)
        basename = _build_basename(fd, '/src/ABC-123.mp4', config)
        # folder parts include the title
        assert folder[0] == fd['title']
        # basename also includes the same truncated title
        assert fd['title'] in basename


class TestFolderParts:
    """Tests for _folder_parts."""

    def test_two_layers(self):
        from core.readonly_producer import _folder_parts
        config = {'folder_layers': ['{actor}', '{num}'], 'max_filename_length': 60}
        fd = {'number': 'ABC-123', 'title': 'Title', 'actors': ['Actress'], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert len(parts) == 2

    def test_more_than_3_layers_capped(self):
        from core.readonly_producer import _folder_parts
        config = {
            'folder_layers': ['{num}', '{num}', '{num}', '{num}'],
            'max_filename_length': 60,
        }
        fd = {'number': 'ABC-123', 'title': '', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert len(parts) <= 3

    def test_empty_layer_skipped(self):
        from core.readonly_producer import _folder_parts
        # An empty-string layer formats to '' and must be dropped by the `if part` guard.
        config = {'folder_layers': ['{num}', ''], 'max_filename_length': 60}
        fd = {'number': 'ABC-123', 'title': 'Title', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        # empty layer dropped → only the number layer survives (RED if `if part` guard removed)
        assert parts == ['ABC-123']

    def test_folder_format_fallback(self):
        """When folder_layers is empty, folder_format is used."""
        from core.readonly_producer import _folder_parts
        config = {
            'folder_layers': [],
            'folder_format': '{num}',
            'max_filename_length': 60,
        }
        fd = {'number': 'ABC-123', 'title': '', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert parts == ['ABC-123']

    def test_no_layers_no_folder_format_defaults_num(self):
        from core.readonly_producer import _folder_parts
        config = {'max_filename_length': 60}
        fd = {'number': 'XYZ-001', 'title': '', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert parts == ['XYZ-001']


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
        from core.readonly_producer import _build_basename
        with patch('core.readonly_producer._detect_vr_cluster', return_value='180_LR'):
            result = _build_basename(self.BASE_FD, '/src/ABC-123_180_LR.mp4', self.BASE_CONFIG)
        assert result.endswith('_180_LR')

    def test_no_vr_tail_for_normal_file(self):
        from core.readonly_producer import _build_basename
        with patch('core.readonly_producer._detect_vr_cluster', return_value=None):
            result = _build_basename(self.BASE_FD, '/src/ABC-123.mp4', self.BASE_CONFIG)
        # BASE_FD title has no underscore → any '_' means an erroneous VR tail (RED if injected)
        assert '_' not in result

    def test_suffix_not_truncated_in_two_pass(self):
        """When {suffix} in template, suffix is not cut off by truncation."""
        from core.readonly_producer import _build_basename
        fd = dict(self.BASE_FD, suffix='-C', title='X' * 60)
        config = dict(self.BASE_CONFIG, filename_format='{num} {title}{suffix}', max_filename_length=30)
        with patch('core.readonly_producer._detect_vr_cluster', return_value=None):
            result = _build_basename(fd, '/src/ABC-123-C.mp4', config)
        # suffix '-c' / '-C' should survive truncation
        assert result.endswith('-c') or result.endswith('-C') or '-c' in result.lower()

    def test_plain_num_title_no_vr_tail(self):
        from core.readonly_producer import _build_basename
        with patch('core.readonly_producer._detect_vr_cluster', return_value=None):
            result = _build_basename(self.BASE_FD, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert result == 'ABC-123 Normal Title'


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
        from core.readonly_producer import _resolve_movie_dir
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
        from core.readonly_producer import _resolve_movie_dir
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

    def test_first_allocation_no_collision(self):
        """existing=None, nothing taken → plain leaf, n==1."""
        from core.readonly_producer import _resolve_movie_dir
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', None,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, {},
            )

        assert output_dir_uri == self._uri('ABC-123')
        assert allocated == {self._uri('ABC-123')}

    def test_existing_outside_new_output_root_reallocates(self):
        """existing.output_dir set but NOT under the (new) output_uri → new allocation branch."""
        from core.readonly_producer import _resolve_movie_dir
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        existing = self._existing(to_file_uri('/old-root/ABC-123', {}))  # stale root, moved output_path
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', existing,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, {},
            )

        assert output_dir_uri == self._uri('ABC-123')
        assert str(movie_dir) == '/output/ABC-123'

    def test_increment_limit_raises(self):
        """Every candidate taken → RuntimeError once n exceeds _MAX_INCREMENT."""
        from core.readonly_producer import _MAX_INCREMENT, _resolve_movie_dir
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = True  # everything taken, forever
        allocated: set = set()

        with self._patch_exists(False), pytest.raises(RuntimeError):
            _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', None,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, {},
            )
        assert repo.is_output_dir_taken.call_count >= _MAX_INCREMENT

    def test_allocated_this_run_blocks_reuse_within_same_run(self):
        """A candidate already recorded in allocated_this_run is treated as taken even
        though repo/disk both say it's free (same-run guard)."""
        from core.readonly_producer import _resolve_movie_dir
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        allocated = {self._uri('ABC-123')}  # pre-seeded as if file #1 already claimed it

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mkv', None,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, {},
            )

        assert output_dir_uri == self._uri('ABC-123-2')

    # -----------------------------------------------------------------
    # TASK-89a-T5 (CD-89a-6 / Codex C3): mapped-output 定位.
    # gotcha: CURRENT_ENV is value-imported into core.readonly_producer,
    # so monkeypatch the USE site (core.readonly_producer.CURRENT_ENV),
    # not core.path_utils.CURRENT_ENV (see TASK-89a-T5.md).
    # -----------------------------------------------------------------

    def test_mapped_output_wsl_with_mapping_reverses_fs_but_not_uri(self, monkeypatch):
        """A main scenario: wsl + non-empty path_mappings + hit → returned fs Path is
        reverse-mapped to the real local path, while the returned URI (stored back to
        DB) stays the original forward-mapped existing.output_dir untouched."""
        import core.readonly_producer as producer_module
        from core.readonly_producer import _resolve_movie_dir

        monkeypatch.setattr(producer_module, 'CURRENT_ENV', 'wsl')
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

    def test_mapped_output_wsl_no_mapping_unchanged(self, monkeypatch):
        """Degenerate combo 2/4: wsl but path_mappings empty → behavior unchanged
        (regression lock for the non-mapped 88/89 scenarios)."""
        import core.readonly_producer as producer_module
        from core.readonly_producer import _resolve_movie_dir

        monkeypatch.setattr(producer_module, 'CURRENT_ENV', 'wsl')
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

        assert str(movie_dir) == '/output/ABC-123'
        assert output_dir_uri == existing_uri

    def test_mapped_output_non_wsl_with_mapping_unchanged(self, monkeypatch):
        """Degenerate combo 3/4: non-wsl env + non-empty path_mappings → no reverse
        (symmetric with to_file_uri's forward mapping only firing in wsl)."""
        import core.readonly_producer as producer_module
        from core.readonly_producer import _resolve_movie_dir

        monkeypatch.setattr(producer_module, 'CURRENT_ENV', 'windows')
        mappings = {'/home/user/nas': '//NAS-SERVER/share'}
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        existing_uri = self._uri('ABC-123')
        existing = self._existing(existing_uri)
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', existing,
                self.OUTPUT_ROOT, self.OUTPUT_URI, self._fd(), self.BASE_CONFIG,
                allocated, mappings,
            )

        assert str(movie_dir) == '/output/ABC-123'
        assert output_dir_uri == existing_uri

    def test_mapped_output_non_wsl_no_mapping_unchanged(self, monkeypatch):
        """Degenerate combo 4/4: non-wsl env + empty path_mappings → no reverse
        (baseline, both guard conditions false)."""
        import core.readonly_producer as producer_module
        from core.readonly_producer import _resolve_movie_dir

        monkeypatch.setattr(producer_module, 'CURRENT_ENV', 'linux')
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

        assert str(movie_dir) == '/output/ABC-123'
        assert output_dir_uri == existing_uri

    def test_new_allocation_branch_not_reverse_mapped(self, monkeypatch):
        """New-allocation branch never runs URI→fs reversal: candidate_fs is already a
        native fs path built via output_root, not derived from an existing URI."""
        import core.readonly_producer as producer_module
        from core.readonly_producer import _resolve_movie_dir

        monkeypatch.setattr(producer_module, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': '//NAS-SERVER/share'}
        output_root_local = '/home/user/nas/lib'
        output_uri = to_file_uri(output_root_local, mappings)
        repo = MagicMock()
        repo.is_output_dir_taken.return_value = False
        allocated: set = set()

        with self._patch_exists(False):
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, 'file:///src/ABC-123.mp4', None,
                output_root_local, output_uri, self._fd('ABC-123'), self.BASE_CONFIG,
                allocated, mappings,
            )

        assert str(movie_dir) == '/home/user/nas/lib/ABC-123'
        assert output_dir_uri == to_file_uri(str(Path(output_root_local, 'ABC-123')), mappings)


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

_T3_BASE_CONFIG = {
    'filename_format': '{num} {title}',
    'max_filename_length': 60,
    'max_title_length': 50,
    'suffix_keywords': [],
    'external_manager': 'kodi',
    'download_sample_images': False,
}


def _t3_format_data(meta=None, source_fs_path='/src/TEST-001.mp4', config=None):
    from core.readonly_producer import _format_data
    return _format_data(meta or _T3_META, source_fs_path, config or _T3_BASE_CONFIG)


class TestWriteMovieAssets:
    """T-3: write-target containment, re-scrape, extrafanart gate, has_cover=False."""

    def test_write_target_containment(self, tmp_path):
        """All write targets must be under movie_dir; none under source file's dir."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        source_fs_path = '/src/TEST-001.mp4'
        source_dir = str(Path(source_fs_path).parent)
        fd = _t3_format_data(source_fs_path=source_fs_path)

        recorded_paths: list = []

        def fake_download(url, save_path, referer=''):
            recorded_paths.append(save_path)
            return True

        def fake_jellyfin(cover_path, base_stem):
            # cover_path is a READ input (source for copy/crop), not a write target — don't record it.
            recorded_paths.append(base_stem + '-poster.jpg')
            recorded_paths.append(base_stem + '-fanart.jpg')
            return {'poster': True, 'fanart': True}

        def fake_nfo(**kwargs):
            recorded_paths.append(kwargs.get('output_path', ''))
            return True   # generate_nfo returns bool; True = write ok

        with patch('core.readonly_producer.download_image', side_effect=fake_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=fake_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=fake_nfo):
            _write_movie_assets(movie_dir, _T3_META, fd, source_fs_path, _T3_BASE_CONFIG)

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

    def test_rescrape_uses_remote_cover_url(self, tmp_path):
        """download_image first arg must be the remote cover URL (C6 re-scrape)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        download_calls: list = []

        def fake_download(url, save_path, referer=''):
            download_calls.append(url)
            return True

        with patch('core.readonly_producer.download_image', side_effect=fake_download), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo'):
            _write_movie_assets(movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG)

        assert download_calls, "download_image was never called"
        assert download_calls[0] == _T3_META['cover'], (
            "First download_image call must be remote cover URL, not a local path"
        )

    def test_extrafanart_gate_false(self, tmp_path):
        """download_sample_images=False → no extrafanart dir, sample_fs==[]."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, download_sample_images=False)

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo'):
            assets = _write_movie_assets(movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config)

        assert assets['sample_fs'] == []
        ef_dir = Path(movie_dir) / 'extrafanart'
        assert not ef_dir.exists()

    def test_extrafanart_gate_true_two_samples(self, tmp_path):
        """download_sample_images=True + 2 sample URLs → fanart1.jpg + fanart2.jpg, 2 entries."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, download_sample_images=True)

        def fake_download(url, save_path, referer=''):
            return True

        with patch('core.readonly_producer.download_image', side_effect=fake_download), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo'):
            assets = _write_movie_assets(movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config)

        assert len(assets['sample_fs']) == 2
        assert 'fanart1.jpg' in assets['sample_fs'][0]
        assert 'fanart2.jpg' in assets['sample_fs'][1]

    def test_no_cover_skips_jellyfin_images(self, tmp_path):
        """meta['cover']='' → generate_jellyfin_images NOT called; cover_fs=''; nfo still written."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        meta_no_cover = dict(_T3_META, cover='')
        fd = _t3_format_data(meta=meta_no_cover)

        jellyfin_mock = MagicMock()
        nfo_mock = MagicMock()

        with patch('core.readonly_producer.download_image', return_value=False), \
             patch('core.readonly_producer.generate_jellyfin_images', jellyfin_mock), \
             patch('core.readonly_producer.generate_nfo', nfo_mock):
            assets = _write_movie_assets(
                movie_dir, meta_no_cover, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG
            )

        jellyfin_mock.assert_not_called()
        assert assets['cover_fs'] == ''
        nfo_mock.assert_called_once()

    def test_generate_nfo_params(self, tmp_path):
        """generate_nfo: output_path under movie_dir; external_manager passed; has_poster/has_fanart match cover."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')
        captured: dict = {}

        def capture_nfo(**kwargs):
            captured.update(kwargs)
            return True   # generate_nfo returns bool; True = write ok

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=capture_nfo):
            _write_movie_assets(movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config)

        assert 'output_path' in captured
        assert captured['output_path'].startswith(movie_dir)
        assert captured['external_manager'] == 'jellyfin'
        assert captured['has_poster'] is True
        assert captured['has_fanart'] is True

    def test_nfo_write_failure_raises(self, tmp_path):
        """generate_nfo returns False (write failed) → _write_movie_assets raises.

        NFO is a required off-complete output; a swallowed False must not be treated
        as success (else produce_source counts created + upserts a movie with no NFO).
        """
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', return_value=False):
            with pytest.raises(RuntimeError):
                _write_movie_assets(movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG)


# ---------------------------------------------------------------------------
# TASK-89a-T4 (Codex #3 / #4): _build_old_base + _clean_stale_assets
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


def _t4_real_jellyfin(cover_fs, base_stem):
    Path(base_stem + '-poster.jpg').write_bytes(b'FAKE-IMG')
    Path(base_stem + '-fanart.jpg').write_bytes(b'FAKE-IMG')
    return {'poster': True, 'fanart': True}


def _t4_real_nfo(**kwargs):
    Path(kwargs['output_path']).write_text('<movie/>', encoding='utf-8')
    return True


def _t4_write(movie_dir, meta, config, old_base='', download_side_effect=None):
    """Run the real _write_movie_assets (real file writes) with T4's old_base kwarg."""
    from core.readonly_producer import _format_data, _write_movie_assets

    fd = _format_data(meta, '/src/TEST-001.mp4', config)
    with patch('core.readonly_producer.download_image',
               side_effect=download_side_effect or _t4_real_download), \
         patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
        return _write_movie_assets(movie_dir, meta, fd, '/src/TEST-001.mp4', config, old_base=old_base)


class TestBuildOldBase:
    """T4: _build_old_base — DB row (`existing`) → old_meta mapping → old basename."""

    def test_none_existing_returns_empty(self):
        from core.readonly_producer import _build_old_base
        assert _build_old_base(None, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_empty_title_returns_empty(self):
        existing = _t4_existing(dict(_T3_META, title=''))
        from core.readonly_producer import _build_old_base
        assert _build_old_base(existing, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_empty_number_returns_empty(self):
        """Defensive guard (Opus note #3): existing.number falsy must not crash / must skip."""
        existing = _t4_existing(dict(_T3_META, number=''))
        from core.readonly_producer import _build_old_base
        assert _build_old_base(existing, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_normal_existing_matches_manual_pipeline(self):
        """old_base must equal _format_data + _build_basename run manually against the
        same mapped fields — proves _build_old_base doesn't silently diverge from
        the documented mapping (number/title/actors/maker/date)."""
        from core.readonly_producer import _build_basename, _build_old_base, _format_data

        existing = _t4_existing(dict(_T3_META, title='Old Title'))
        source_fs_path = '/src/TEST-001.mp4'
        old_base = _build_old_base(existing, source_fs_path, _T3_BASE_CONFIG)

        expected_meta = {
            'number': existing.number,
            'title': existing.title,
            'actors': existing.actresses,
            'maker': existing.maker,
            'date': existing.release_date,
        }
        expected_fd = _format_data(expected_meta, source_fs_path, _T3_BASE_CONFIG)
        expected = _build_basename(expected_fd, source_fs_path, _T3_BASE_CONFIG)
        assert old_base == expected == 'TEST-001 Old Title'


class TestCleanStaleAssets:
    """T4: _clean_stale_assets — precise, anchored deletion (no bare glob, no rmtree)."""

    def test_empty_old_base_is_noop(self, tmp_path):
        from core.readonly_producer import _clean_stale_assets

        d = tmp_path / 'movie'
        d.mkdir()
        f = d / 'random.jpg'
        f.write_bytes(b'x')
        _clean_stale_assets(str(d), '')
        assert f.exists()

    def test_deletes_singleton_assets_only(self, tmp_path):
        from core.readonly_producer import _clean_stale_assets

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')
        keep = d / 'random.jpg'
        keep.write_bytes(b'keep')

        _clean_stale_assets(str(d), old_base)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'{old_base}{suffix}').exists(), f"{suffix} not cleaned"
        assert keep.exists(), "user-placed file must not be deleted"

    def test_missing_files_are_noop_no_raise(self, tmp_path):
        from core.readonly_producer import _clean_stale_assets

        d = tmp_path / 'movie'
        d.mkdir()
        _clean_stale_assets(str(d), 'NOTHING-EVER-WRITTEN')  # must not raise

    def test_extrafanart_glob_ignores_non_fanart_files(self, tmp_path):
        from core.readonly_producer import _clean_stale_assets

        d = tmp_path / 'movie'
        ef = d / 'extrafanart'
        ef.mkdir(parents=True)
        (ef / 'fanart1.jpg').write_bytes(b'x')
        note = ef / 'my_note.txt'
        note.write_bytes(b'keep')
        custom = ef / 'custom.jpg'
        custom.write_bytes(b'keep')

        _clean_stale_assets(str(d), 'TEST-001 X')

        assert not (ef / 'fanart1.jpg').exists()
        assert note.exists(), "non fanart*.jpg file in extrafanart must survive"
        assert custom.exists(), "non fanart*.jpg-named image must survive"

    def test_old_base_with_glob_metachars_is_escaped(self, tmp_path):
        """old_base from a scraped title may contain '[' ']' (e.g. '[Chinese Sub]').
        sanitize_filename keeps brackets, so the poster/fanart globs must
        glob.escape(old_base) or they silently miss the file (narrow Codex #3
        recurrence — residual poster/fanart junk survives)."""
        from core.readonly_producer import _clean_stale_assets

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'STARS-123 [Chinese Sub]'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_assets(str(d), old_base)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'{old_base}{suffix}').exists(), \
                f"{suffix} with bracketed old_base not cleaned (glob not escaped)"


class TestWriteMovieAssetsStaleCleanup:
    """T4 integration: _write_movie_assets(old_base=...) round-trips against real files.

    Covers DoD: title-drift (Codex #3 lock), extrafanart shrink, no-op-safe
    (clean-before-write ordering), user-file protection, first-generation no-op,
    reallocated-new-dir isolation.
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

        from core.readonly_producer import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        assert old_base == 'TEST-001 Title A'

        _t4_write(movie_dir, meta_b, config, old_base=old_base)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'TEST-001 Title A{suffix}').exists(), f"stale {suffix} survived"
            assert (d / f'TEST-001 Title B{suffix}').exists(), f"new {suffix} missing"

    def test_extrafanart_shrink_3_to_2(self, tmp_path):
        movie_dir = str(tmp_path / 'TEST-001')
        meta3 = dict(_T3_META, title='Same Title',
                     sample_images=['http://x/1.jpg', 'http://x/2.jpg', 'http://x/3.jpg'])
        config = self._config(download_sample_images=True)
        _t4_write(movie_dir, meta3, config)
        ef_dir = Path(movie_dir) / 'extrafanart'
        assert (ef_dir / 'fanart3.jpg').exists()

        from core.readonly_producer import _build_old_base
        old_base = _build_old_base(_t4_existing(meta3), '/src/TEST-001.mp4', config)
        meta2 = dict(_T3_META, title='Same Title',
                     sample_images=['http://x/1.jpg', 'http://x/2.jpg'])
        _t4_write(movie_dir, meta2, config, old_base=old_base)

        assert not (ef_dir / 'fanart3.jpg').exists(), "shrunk sample must not persist"
        assert (ef_dir / 'fanart1.jpg').exists()
        assert (ef_dir / 'fanart2.jpg').exists()

    def test_extrafanart_cleaned_even_when_gate_off_this_run(self, tmp_path):
        """Card boundary #1: samples ON last run, OFF this run → old fanart*.jpg still cleaned."""
        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Same Title',
                    sample_images=['http://x/1.jpg', 'http://x/2.jpg'])
        config_on = self._config(download_sample_images=True)
        _t4_write(movie_dir, meta, config_on)
        ef_dir = Path(movie_dir) / 'extrafanart'
        assert (ef_dir / 'fanart1.jpg').exists()
        assert (ef_dir / 'fanart2.jpg').exists()

        from core.readonly_producer import _build_old_base
        old_base = _build_old_base(_t4_existing(meta), '/src/TEST-001.mp4', config_on)
        config_off = self._config(download_sample_images=False)
        _t4_write(movie_dir, meta, config_off, old_base=old_base)

        assert not (ef_dir / 'fanart1.jpg').exists()
        assert not (ef_dir / 'fanart2.jpg').exists()

    def test_title_unchanged_clean_before_write_no_op_safe(self, tmp_path):
        """old_base == new_base: clean must run BEFORE download so the sequence
        degrades to a plain overwrite, never a delete-after-write race."""
        from core.readonly_producer import _build_basename, _build_old_base, _format_data

        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Same Title')
        config = self._config()
        _t4_write(movie_dir, meta, config)

        old_base = _build_old_base(_t4_existing(meta), '/src/TEST-001.mp4', config)
        new_fd = _format_data(meta, '/src/TEST-001.mp4', config)
        new_base = _build_basename(new_fd, '/src/TEST-001.mp4', config)
        assert old_base == new_base, "sanity: title unchanged → identical basename"

        observed = {'cover_missing_when_download_called': None}

        def recording_download(url, save_path, referer=''):
            if save_path.endswith('.jpg') and 'extrafanart' not in save_path:
                observed['cover_missing_when_download_called'] = not Path(save_path).exists()
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'NEW-COVER')
            return True

        _t4_write(movie_dir, meta, config, old_base=old_base, download_side_effect=recording_download)

        assert observed['cover_missing_when_download_called'] is True, (
            "stale same-name cover must be deleted BEFORE download_image runs"
        )
        assert (Path(movie_dir) / f'{new_base}.jpg').read_bytes() == b'NEW-COVER'

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

        from core.readonly_producer import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        meta_b = dict(_T3_META, title='Title B')
        _t4_write(movie_dir, meta_b, config, old_base=old_base)

        assert note.exists()
        assert random_jpg.exists()
        assert ef_note.exists()
        assert ef_custom.exists()

    def test_first_generation_no_existing_row_no_op(self, tmp_path):
        """existing is None → _build_old_base == '' → no cleanup attempted, write succeeds."""
        from core.readonly_producer import _build_old_base

        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Title A')
        config = self._config()
        old_base = _build_old_base(None, '/src/TEST-001.mp4', config)
        assert old_base == ''

        assets = _t4_write(movie_dir, meta, config, old_base=old_base)
        assert Path(assets['cover_fs']).exists()

    def test_reallocated_new_dir_isolated_old_dir_untouched(self, tmp_path):
        """Card boundary #6: output root moved → new empty movie_dir cleans to a
        no-op (nothing there matches), and the orphaned OLD dir is left untouched
        (89a does not do cross-dir orphan GC — that's spec-89b.4)."""
        old_dir = str(tmp_path / 'old_root' / 'TEST-001')
        new_dir = str(tmp_path / 'new_root' / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config()

        _t4_write(old_dir, meta_a, config)
        assert (Path(old_dir) / 'TEST-001 Title A.nfo').exists()

        from core.readonly_producer import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        _t4_write(new_dir, meta_b, config, old_base=old_base)

        # old dir: completely untouched (still has its own Title A series)
        assert (Path(old_dir) / 'TEST-001 Title A.nfo').exists()
        assert (Path(old_dir) / 'TEST-001 Title A.jpg').exists()
        # new dir: only the new title's files, no cross-dir bleed of the old series
        assert (Path(new_dir) / 'TEST-001 Title B.nfo').exists()
        assert not (Path(new_dir) / 'TEST-001 Title A.nfo').exists()


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
        assets = {'cover_fs': cover_fs, 'sample_fs': []}
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
        assert v.nfo_mtime == 0.0
        assert v.output_dir == self.OUTPUT_DIR_URI

    def test_cover_path_is_local_uri_not_remote(self, tmp_path, temp_db):
        """cover_path in DB must be a file:/// URI, never the remote cover URL (CD-88b-7)."""
        from core.readonly_producer import _upsert_db

        cover_fs = str(tmp_path / 'output' / 'TEST-001' / 'cover.jpg')
        assets = {'cover_fs': cover_fs, 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path.startswith('file:///')
        assert not v.cover_path.startswith('https://')
        assert v.cover_path != _T3_META['cover']

    def test_sample_images_are_local_uris(self, tmp_path, temp_db):
        """sample_images in DB must be local file:/// URIs, not remote URLs."""
        from core.readonly_producer import _upsert_db
        from core.path_utils import to_file_uri

        ef_dir = tmp_path / 'output' / 'TEST-001' / 'extrafanart'
        sample1 = str(ef_dir / 'fanart1.jpg')
        sample2 = str(ef_dir / 'fanart2.jpg')
        assets = {
            'cover_fs': str(tmp_path / 'output' / 'TEST-001' / 'cover.jpg'),
            'sample_fs': [sample1, sample2],
        }
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert len(v.sample_images) == 2
        assert v.sample_images[0] == to_file_uri(sample1, None)
        assert v.sample_images[1] == to_file_uri(sample2, None)
        for si in v.sample_images:
            assert si.startswith('file:///')

    def test_no_cover_stores_empty_string(self, temp_db):
        """cover_fs='' → DB cover_path must be ''."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == ''

    def test_empty_sample_images_stored_as_empty_list(self, temp_db):
        """sample_fs=[] → DB sample_images==[]."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == []


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
        from core.readonly_producer import resolve_output_root

        source = _make_source(output_path="", path="/src/movies")
        config = _make_config()  # scraper_cfg={} → fallback 'off'

        result = resolve_output_root(source, config)

        assert result
        assert result.startswith(str(get_db_path().parent / "lib"))

    def test_off_with_nonempty_output_path_still_returns_fixed_root(self):
        """off mode ignores source.output_path even if the user typed one (UI hides
        this field in off mode, but the backend must not trust a stale value)."""
        from core.database import get_db_path
        from core.readonly_producer import resolve_output_root

        source = _make_source(output_path="/user/typed/path", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": "off"})

        result = resolve_output_root(source, config)

        assert "/user/typed/path" not in result
        assert result.startswith(str(get_db_path().parent / "lib"))

    @pytest.mark.parametrize("mode", ["jellyfin", "emby", "kodi"])
    def test_media_server_modes_return_output_path_verbatim(self, mode):
        from core.readonly_producer import resolve_output_root

        source = _make_source(output_path="/nas/media", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": mode})

        assert resolve_output_root(source, config) == "/nas/media"

    @pytest.mark.parametrize("mode", ["jellyfin", "emby", "kodi"])
    def test_media_server_modes_with_empty_output_path_return_empty(self, mode):
        """Media-server flavours still require the user to configure output_path —
        resolve_output_root passes the empty value through unchanged (call sites
        keep their existing empty-string guards, CD-89a-7)."""
        from core.readonly_producer import resolve_output_root

        source = _make_source(output_path="", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": mode})

        assert resolve_output_root(source, config) == ""

    def test_two_sources_same_basename_do_not_collide(self):
        """B1: two off-mode sources whose folder basename would clash (same leaf
        directory name, different parent path) must resolve to different roots."""
        from core.readonly_producer import resolve_output_root

        config = _make_config()  # off
        source_a = _make_source(path="/mnt/driveA/MyDrive")
        source_b = _make_source(path="/mnt/driveB/MyDrive")

        result_a = resolve_output_root(source_a, config)
        result_b = resolve_output_root(source_b, config)

        assert result_a != result_b

    def test_same_source_resolves_to_same_root_across_calls(self):
        """Stability lock (DoD): calling resolve_output_root twice for the same
        source/config must yield the identical path (no hidden per-call state)."""
        from core.readonly_producer import resolve_output_root

        config = _make_config()  # off
        source = _make_source(path="/mnt/driveA/MyDrive")

        first = resolve_output_root(source, config)
        second = resolve_output_root(source, config)

        assert first == second

    def test_off_fallback_for_empty_basename_after_sanitize(self):
        """A source path whose basename is empty (e.g. a filesystem root, where
        Path(...).name == '') must not produce an empty-string folder name — falls
        back to src-<shortcode>."""
        from core.database import get_db_path
        from core.readonly_producer import resolve_output_root

        config = _make_config()  # off
        source = _make_source(path="/")

        result = resolve_output_root(source, config)

        lib_root = Path(get_db_path().parent, "lib")
        name = Path(result).relative_to(lib_root)
        assert str(name).startswith("src-")
        assert str(name) != "src-"  # a real shortcode must be appended


class TestEmit:
    """Tests for _emit helper."""

    def test_appends_outcome_to_result(self):
        from core.readonly_producer import ProduceResult, _emit

        result = ProduceResult(source_path="/src", output_path="/out")
        _emit(None, result, "file:///src/a.mp4", "skipped")

        assert len(result.outcomes) == 1
        o = result.outcomes[0]
        assert o.source_uri == "file:///src/a.mp4"
        assert o.status == "skipped"
        assert o.movie_dir == ""
        assert o.number == ""
        assert o.error == ""

    def test_calls_on_progress_with_outcome(self):
        from core.readonly_producer import ProduceResult, _emit

        result = ProduceResult(source_path="/src", output_path="/out")
        received = []
        _emit(received.append, result, "file:///src/a.mp4", "created", "/out/Movie", "ABC-123")

        assert len(received) == 1
        assert received[0] is result.outcomes[0]
        assert received[0].movie_dir == "/out/Movie"
        assert received[0].number == "ABC-123"

    def test_no_on_progress_is_noop(self):
        from core.readonly_producer import ProduceResult, _emit

        result = ProduceResult(source_path="/src", output_path="/out")
        # Must not raise
        _emit(None, result, "file:///src/a.mp4", "failed", error="boom")
        assert result.outcomes[0].error == "boom"


class TestProduceSourceGuards:
    """Guard tests for produce_source (CD-88b-6 / Acceptance #11)."""

    def test_not_readonly_returns_aborted(self):
        """source.readonly=False → aborted_reason='not_readonly', counters all 0."""
        from core.readonly_producer import produce_source

        source = _make_source(readonly=False)
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos") as mock_list:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "not_readonly"
        assert result.created == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert result.no_scrape == 0
        mock_list.assert_not_called()

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

    def test_whitespace_output_path_returns_aborted(self):
        """media-server mode + source.output_path='   ' → aborted_reason='no_output_path'."""
        from core.readonly_producer import produce_source

        source = _make_source(output_path="   ")
        repo = MagicMock()
        config = _make_config(scraper_cfg={"external_manager": "jellyfin"})

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()
        mock_search.assert_not_called()

    def test_none_output_path_returns_aborted(self):
        """media-server mode + source.output_path=None → aborted_reason='no_output_path'."""
        from core.readonly_producer import produce_source

        source = _make_source(output_path=None)
        repo = MagicMock()
        config = _make_config(scraper_cfg={"external_manager": "jellyfin"})

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()
        mock_search.assert_not_called()


class TestProduceSourceOffModeNeverAborts:
    """TASK-89a-T2 (CD-89a-7): off flavour resolves to a structural fixed root, so
    produce_source must NEVER abort with no_output_path in off mode — this is the
    symmetric counterpart of TestProduceSourceGuards' three media-server abort tests
    (off + empty/whitespace/None source.output_path all behave identically because
    resolve_output_root ignores source.output_path entirely in off mode)."""

    @pytest.mark.parametrize("output_path", ["", "   ", None])
    def test_off_mode_empty_output_path_does_not_abort(self, output_path):
        from core.readonly_producer import produce_source

        source = _make_source(output_path=output_path)
        repo = MagicMock()
        config = _make_config()  # scraper_cfg={} → external_manager fallback 'off'

        with patch("core.readonly_producer._list_source_videos", return_value=[]) as mock_list, \
             patch("core.readonly_producer._build_cover_index", return_value={}):
            result = produce_source(source, config, repo)

        assert result.aborted_reason != "no_output_path"
        mock_list.assert_called_once()  # guard passed through to the listing step

    @pytest.mark.parametrize("output_path", ["", "   ", None])
    def test_off_mode_effective_output_is_under_lib_root(self, output_path):
        """Sanity check: the resolved root that unblocked the guard is the off fixed
        folder, not a leaked None/whitespace value."""
        from core.database import get_db_path
        from core.readonly_producer import resolve_output_root

        source = _make_source(output_path=output_path)
        config = _make_config()

        effective = resolve_output_root(source, config)
        lib_root = str(get_db_path().parent / "lib")
        assert effective.startswith(lib_root)


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
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri):
            produce_source(source, config, repo)

        mock_list.assert_called_once()
        passed_exts = mock_list.call_args[0][1]
        assert passed_exts == {".mp4", ".m2ts", ".custom"}

    def test_missing_config_falls_back_to_defaults(self):
        """No scraper.video_extensions → _list_source_videos gets the DEFAULT set."""
        from core.readonly_producer import produce_source
        from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS

        source = _make_source()
        repo = MagicMock()
        config = _make_config()  # empty scraper cfg

        with patch("core.readonly_producer._list_source_videos", return_value=[]) as mock_list, \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri):
            produce_source(source, config, repo)

        mock_list.assert_called_once()
        assert mock_list.call_args[0][1] == set(DEFAULT_VIDEO_EXTENSIONS)


class TestProduceSourceNoneNumberGuard:
    """extract_number returns None → no_scrape++, search_jav NOT called (Codex P2b)."""

    def test_none_number_no_search_jav(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [_make_file_info(path="/src/videos/nonnumber.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
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

    def test_none_number_emits_no_scrape_outcome(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [_make_file_info(path="/src/videos/nonnumber.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None):
            result = produce_source(source, config, repo)

        assert len(result.outcomes) == 1
        assert result.outcomes[0].status == "no_scrape"


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

        def fake_should_skip(src_uri, output_uri, cover_index, path_mappings):
            return "SKIP-001" in src_uri or "SKIP-002" in src_uri

        def fake_extract_number(basename):
            if "nonnumber" in basename:
                return None
            return basename.replace(".mp4", "").upper()

        def fake_search_jav(number, source="auto", proxy_url=""):
            if "NOSCRAPE" in number:
                return None
            return {"number": number, "title": "T", "cover": "", "actors": [], "tags": [],
                    "date": "", "maker": "", "director": "", "series": "", "label": "",
                    "sample_images": [], "duration": 0, "url": ""}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/SUCCESS-001"

        with patch("core.readonly_producer._list_source_videos", return_value=self.FILES), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._should_skip", side_effect=fake_should_skip), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", side_effect=fake_extract_number), \
             patch("core.readonly_producer.search_jav", side_effect=fake_search_jav), \
             patch("core.readonly_producer._format_data", return_value={"number": "X", "title": "T", "actors": [], "maker": "", "date": "", "suffix": ""}), \
             patch("core.readonly_producer._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/SUCCESS-001")), \
             patch("core.readonly_producer._write_movie_assets", return_value={"cover_fs": "/output/dest/SUCCESS-001/cover.jpg", "sample_fs": []}), \
             patch("core.readonly_producer._upsert_db"):
            return produce_source(source, config, repo)

    def test_counters(self):
        result = self._run()
        assert result.skipped == 2
        assert result.no_scrape == 2
        assert result.created == 1
        assert result.failed == 0

    def test_outcome_count(self):
        result = self._run()
        assert len(result.outcomes) == 5

    def test_outcome_statuses(self):
        result = self._run()
        statuses = [o.status for o in result.outcomes]
        assert statuses.count("skipped") == 2
        assert statuses.count("no_scrape") == 2
        assert statuses.count("created") == 1


class TestProduceSourceOnProgress:
    """on_progress callback called once per processed file."""

    def test_on_progress_called_per_file(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [
            _make_file_info(path="/src/A.mp4"),
            _make_file_info(path="/src/B.mp4"),
            _make_file_info(path="/src/C.mp4"),
        ]
        received = []

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None):
            produce_source(source, config, repo, on_progress=received.append)

        # 3 files, all become no_scrape (extract_number=None)
        assert len(received) == 3
        assert all(o.status == "no_scrape" for o in received)


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
             patch("core.readonly_producer._build_cover_index", return_value={}), \
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

        def fake_write(movie_dir, meta_arg, fd_arg, src_path, cfg, old_base=''):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("disk full")
            return {"cover_fs": "", "sample_fs": []}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/X"

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_producer._format_data", return_value=fd), \
             patch("core.readonly_producer._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/X")), \
             patch("core.readonly_producer._write_movie_assets", side_effect=fake_write), \
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
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_producer._format_data", return_value=fd), \
             patch("core.readonly_producer._resolve_movie_dir", return_value=(mock_movie_dir, "file:///output/dest/X")), \
             patch("core.readonly_producer._write_movie_assets", side_effect=exc), \
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

    def test_failed_outcome_error_is_fixed_message(self):
        # Raw exception text (paths/errno) must NOT reach the SSE-bound error field.
        result, _ = self._run_with_write_failure(OSError("[Errno 28] No space left on device: '/output/x'"))
        assert result.outcomes[0].error == "生成失敗"
        assert "Errno" not in result.outcomes[0].error
