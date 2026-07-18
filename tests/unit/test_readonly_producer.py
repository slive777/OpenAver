"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.path_utils import to_file_uri
from tests.conftest import MOCK_FOCAL_XY


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
        mock_scan.assert_called_once_with("/src", {".mp4", ".mkv"}, 0, on_skip=None)
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


class TestListSourceVideosOnSkip:
    """TASK-89b-T5 / CD-89b-5: on_skip must be forwarded verbatim to fast_scan_directory."""

    def test_on_skip_forwarded_to_fast_scan_directory(self):
        from core.readonly_producer import _list_source_videos

        def on_skip(path, exc):
            pass

        with patch("core.readonly_producer.fast_scan_directory", return_value=[]) as mock_scan, \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/src"):
            _list_source_videos("/src", {".mp4"}, 0, on_skip=on_skip)

        mock_scan.assert_called_once_with("/src", {".mp4"}, 0, on_skip=on_skip)

    def test_on_skip_defaults_to_none(self):
        """Backward compatible: callers that don't pass on_skip get None forwarded."""
        from core.readonly_producer import _list_source_videos

        with patch("core.readonly_producer.fast_scan_directory", return_value=[]) as mock_scan, \
             patch("core.readonly_producer.uri_to_fs_path", return_value="/src"):
            _list_source_videos("/src", {".mp4"}, 0)

        mock_scan.assert_called_once_with("/src", {".mp4"}, 0, on_skip=None)


# ---------------------------------------------------------------------------
# _should_skip  (TASK-89b-T3: single attempted-index signal + force escape hatch)
# ---------------------------------------------------------------------------

class TestShouldSkip:
    SOURCE_URI = "file:///src/a.mp4"

    def test_no_entry_returns_false(self):
        """attempted_index has no key for source_uri → not skipped (never attempted)."""
        from core.readonly_producer import _should_skip
        assert _should_skip(self.SOURCE_URI, {}) is False

    def test_attempted_zero_returns_false(self):
        """attempted_index has an explicit 0 value → not skipped (treated as never attempted)."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: 0}
        assert _should_skip(self.SOURCE_URI, attempted_index) is False

    def test_attempted_positive_returns_true(self):
        """attempted_index value > 0, force=False (default) → skip."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: 1720000000.0}
        assert _should_skip(self.SOURCE_URI, attempted_index) is True

    def test_attempted_positive_explicit_force_false_returns_true(self):
        """Same as above but force explicitly passed False → skip (no behavior change)."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: 1720000000.0}
        assert _should_skip(self.SOURCE_URI, attempted_index, force=False) is True

    def test_attempted_positive_but_force_true_returns_false(self):
        """force=True overrides an attempted>0 entry → not skipped (manual re-scrape)."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: 1720000000.0}
        assert _should_skip(self.SOURCE_URI, attempted_index, force=True) is False

    def test_no_entry_and_force_true_returns_false(self):
        """force=True with no attempted_index entry at all → still not skipped."""
        from core.readonly_producer import _should_skip
        assert _should_skip(self.SOURCE_URI, {}, force=True) is False

    def test_other_source_entries_do_not_affect_this_source(self):
        """attempted_index carries other sources' entries → only this source_uri's
        own value is consulted (dict lookup, not any-truthy-value-in-dict)."""
        from core.readonly_producer import _should_skip
        attempted_index = {"file:///src/other.mp4": 1720000000.0}
        assert _should_skip(self.SOURCE_URI, attempted_index) is False

    def test_negative_attempted_value_returns_false(self):
        """Defensive: any non-positive attempted value (not just 0) is treated as
        never-attempted — matches the `> 0` comparison verbatim."""
        from core.readonly_producer import _should_skip
        attempted_index = {self.SOURCE_URI: -1}
        assert _should_skip(self.SOURCE_URI, attempted_index) is False


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

        def fake_jellyfin(cover_path, base_stem, **_kw):
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
    patch `core.organizer.detect_focal` 用同一個值，否則 production 端與 oracle 端
    會對不上。
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
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / f"{fixture['number']}_{tag}")
        source_fs_path = f"/src/{fixture['number']}_{tag}.mp4"
        meta = dict(_T3_META, number=fixture['number'], maker=fixture['maker'])
        fd = _t3_format_data(meta=meta, source_fs_path=source_fs_path)
        config = dict(_T3_BASE_CONFIG, external_manager=external_manager)

        with patch('core.readonly_producer.download_image', side_effect=_t3_write_face_cover), \
             patch('core.readonly_producer.generate_nfo', return_value=True), \
             patch('core.organizer.detect_focal', return_value=MOCK_FOCAL_XY):
            assets = _write_movie_assets(movie_dir, meta, fd, source_fs_path, config)

        assert assets['cover_fs'], "station3 應成功下載封面"
        base_stem = assets['cover_fs'][:-len('.jpg')]
        poster_path = Path(base_stem + '-poster.jpg')
        assert poster_path.exists(), "station3 應產生 poster"
        expected = _t3_oracle_poster_bytes(MOCK_FOCAL_XY)
        assert poster_path.read_bytes() == expected, "station3 poster 應對準焦點（獨立 oracle 比對）"

    def test_station3_fixture_a(self, tmp_path):
        self._run_station3(tmp_path, "a", self._FIXTURE_A)

    def test_station3_fixture_b(self, tmp_path):
        self._run_station3(tmp_path, "b", self._FIXTURE_B)

    # -----------------------------------------------------------------
    # TASK-101a-T3 DoD①（Opus 拍板，非選配）：off/emby/kodi 唯讀產生庫三路
    # 各補一個 fixture-A-only 真跑案例（不 mock crop_to_poster/generate_
    # jellyfin_images），斷言 poster bytes 皆等於同一個獨立 oracle——結構論證
    # （readonly_producer.py:659 的呼叫對四路無條件）在此被實測釘死，不只是
    # 「現在為真」，未來若有人在某一路加分支跳過烤圖，這裡會紅。
    # -----------------------------------------------------------------

    def test_station3_off_fixture_a(self, tmp_path):
        self._run_station3(tmp_path, "off", self._FIXTURE_A, external_manager='off')

    def test_station3_emby_fixture_a(self, tmp_path):
        self._run_station3(tmp_path, "emby", self._FIXTURE_A, external_manager='emby')

    def test_station3_kodi_fixture_a(self, tmp_path):
        self._run_station3(tmp_path, "kodi", self._FIXTURE_A, external_manager='kodi')


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


class TestCleanStaleExtrafanart:
    """T5 follow-up: _clean_stale_extrafanart — precise fanart*.jpg glob, no old_base."""

    def test_noop_when_no_extrafanart_dir(self, tmp_path):
        from core.readonly_producer import _clean_stale_extrafanart

        d = tmp_path / 'movie'
        d.mkdir()
        _clean_stale_extrafanart(str(d))  # must not raise

    def test_extrafanart_glob_ignores_non_fanart_files(self, tmp_path):
        from core.readonly_producer import _clean_stale_extrafanart

        d = tmp_path / 'movie'
        ef = d / 'extrafanart'
        ef.mkdir(parents=True)
        (ef / 'fanart1.jpg').write_bytes(b'x')
        note = ef / 'my_note.txt'
        note.write_bytes(b'keep')
        custom = ef / 'custom.jpg'
        custom.write_bytes(b'keep')

        _clean_stale_extrafanart(str(d))

        assert not (ef / 'fanart1.jpg').exists()
        assert note.exists(), "non fanart*.jpg file in extrafanart must survive"
        assert custom.exists(), "non fanart*.jpg-named image must survive"


class TestCleanStaleSingletons:
    """T5 follow-up (Codex PR review P2): _clean_stale_singletons — anchored deletion,
    gated on old_base != new_base and on each asset's this-run write success."""

    def test_empty_old_base_is_noop(self, tmp_path):
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        f = d / 'random.jpg'
        f.write_bytes(b'x')
        _clean_stale_singletons(str(d), '', 'NEW-BASE', True, True, True)
        assert f.exists()

    def test_old_base_equals_new_base_is_noop(self, tmp_path):
        """Same basename → new write already overwrote the file in place;
        cleaning here would clobber what was just written."""
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        base = 'TEST-001 Same'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{base}{suffix}').write_bytes(b'NEW')

        _clean_stale_singletons(str(d), base, base, True, True, True)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'{base}{suffix}').exists(), f"{suffix} must survive (same base)"

    def test_deletes_singleton_assets_when_all_flags_true(self, tmp_path):
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')
        keep = d / 'random.jpg'
        keep.write_bytes(b'keep')

        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', True, True, True)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'{old_base}{suffix}').exists(), f"{suffix} not cleaned"
        assert keep.exists(), "user-placed file must not be deleted"

    def test_has_cover_false_keeps_old_cover(self, tmp_path):
        """Cover download failed this run → old cover must survive; nfo still
        cleaned since generate_nfo already succeeded (function is only called
        once nfo_ok is True)."""
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('.nfo', '.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False)

        assert not (d / f'{old_base}.nfo').exists(), "nfo must always be cleaned (nfo_ok guaranteed)"
        assert (d / f'{old_base}.jpg').exists(), "old cover must survive when has_cover is False"

    def test_has_poster_and_fanart_false_keeps_old_files(self, tmp_path):
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', True, False, False)

        assert (d / f'{old_base}-poster.jpg').exists(), "old poster must survive when has_poster is False"
        assert (d / f'{old_base}-fanart.jpg').exists(), "old fanart must survive when has_fanart is False"

    def test_missing_files_are_noop_no_raise(self, tmp_path):
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        _clean_stale_singletons(str(d), 'NOTHING-EVER-WRITTEN', 'NEW-BASE', True, True, True)  # must not raise

    def test_old_base_with_glob_metachars_is_escaped(self, tmp_path):
        """old_base from a scraped title may contain '[' ']' (e.g. '[Chinese Sub]').
        sanitize_filename keeps brackets, so the poster/fanart globs must
        glob.escape(old_base) or they silently miss the file (narrow Codex #3
        recurrence — residual poster/fanart junk survives)."""
        from core.readonly_producer import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'STARS-123 [Chinese Sub]'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'STARS-123 New', True, True, True)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'{old_base}{suffix}').exists(), \
                f"{suffix} with bracketed old_base not cleaned (glob not escaped)"


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

    def test_title_unchanged_overwrites_in_place_no_stale_delete(self, tmp_path):
        """old_base == new_base: _clean_stale_singletons must be a no-op (T5
        follow-up) — the same-named file is left for download_image/generate_nfo
        to overwrite directly, never pre-deleted. Deleting first (old behavior)
        would destroy the old asset even when the new write then fails partway."""
        from core.readonly_producer import _build_basename, _build_old_base, _format_data

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
        from core.readonly_producer import _build_old_base, _format_data, _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config()
        _t4_write(movie_dir, meta_a, config)

        d = Path(movie_dir)
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'TEST-001 Title A{suffix}').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)

        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', return_value=False):
            with pytest.raises(RuntimeError):
                _write_movie_assets(movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config, old_base=old_base)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'TEST-001 Title A{suffix}').exists(), \
                f"old {suffix} must survive when generate_nfo fails"

    def test_cover_download_failure_same_base_keeps_old_cover(self, tmp_path):
        """old_base == new_base, cover download fails this run → old cover.jpg
        must survive (download_image never got to overwrite it); NFO still
        writes successfully and is NOT stale-cleaned (same base, no-op)."""
        from core.readonly_producer import _build_old_base, _format_data, _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Same Title')
        config = self._config()
        _t4_write(movie_dir, meta, config)

        d = Path(movie_dir)
        base = 'TEST-001 Same Title'
        assert (d / f'{base}.jpg').exists()
        old_cover_bytes = (d / f'{base}.jpg').read_bytes()

        old_base = _build_old_base(_t4_existing(meta), '/src/TEST-001.mp4', config)
        assert old_base == base, "sanity: title unchanged → identical basename"
        fd = _format_data(meta, '/src/TEST-001.mp4', config)

        def failing_cover_download(url, save_path, referer=''):
            if save_path.endswith('.jpg') and 'extrafanart' not in save_path:
                return False
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'FAKE-IMG')
            return True

        with patch('core.readonly_producer.download_image', side_effect=failing_cover_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
            assets = _write_movie_assets(movie_dir, meta, fd, '/src/TEST-001.mp4', config, old_base=old_base)

        assert assets['cover_fs'] == '', "cover_fs must be '' when download fails"
        assert (d / f'{base}.jpg').read_bytes() == old_cover_bytes, \
            "old cover must survive a failed same-base download"
        assert (d / f'{base}.nfo').exists(), "NFO must still write successfully"

    def test_cover_download_failure_title_drift_keeps_old_cover_but_cleans_nfo(self, tmp_path):
        """old_base != new_base, cover download fails this run → old cover
        (<old_base>.jpg) must survive (has_cover False gates the delete), but
        old NFO (<old_base>.nfo) IS cleaned since it always writes successfully
        and old_base differs from new_base."""
        from core.readonly_producer import _build_old_base, _format_data, _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')
        config = self._config()
        _t4_write(movie_dir, meta_a, config)

        d = Path(movie_dir)
        assert (d / 'TEST-001 Title A.jpg').exists()
        assert (d / 'TEST-001 Title A.nfo').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)

        def failing_cover_download(url, save_path, referer=''):
            if save_path.endswith('.jpg') and 'extrafanart' not in save_path:
                return False
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'FAKE-IMG')
            return True

        with patch('core.readonly_producer.download_image', side_effect=failing_cover_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
            assets = _write_movie_assets(movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config, old_base=old_base)

        assert assets['cover_fs'] == ''
        assert (d / 'TEST-001 Title A.jpg').exists(), \
            "old cover must survive when has_cover is False (title drift)"
        assert not (d / 'TEST-001 Title A.nfo').exists(), \
            "old nfo must be cleaned (nfo_ok guaranteed, old_base != new_base)"
        assert (d / 'TEST-001 Title B.nfo').exists()


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

    def test_scrape_attempted_at_set(self, temp_db):
        """89b-T2: _upsert_db writes scrape_attempted_at > 0 (success path marks 'attempted')."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.scrape_attempted_at > 0


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

    def test_reachable_true_is_default_and_does_not_abort(self):
        """Default reachable=True (backward compat) does not trip the new guard."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos", return_value=[]) as mock_list:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == ""
        mock_list.assert_called_once()
        repo.get_attempted_index.assert_called_once()

    def test_reachable_empty_directory_distinguishable_from_unreachable(self):
        """reachable=True but empty listing → aborted_reason='' (not 'unreachable'),
        even though both cases have all-zero counters. This is the DoD's core
        "unreachable vs empty dir" distinction — must assert aborted_reason, not
        just the counters (which look identical in both cases)."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos", return_value=[]):
            reachable_empty = produce_source(source, config, repo, reachable=True)
        with patch("core.readonly_producer._list_source_videos") as mock_list:
            unreachable = produce_source(source, config, repo, reachable=False)

        assert reachable_empty.aborted_reason == ""
        assert unreachable.aborted_reason == "unreachable"
        # both are "zero outcomes" but semantically distinct
        assert reachable_empty.outcomes == unreachable.outcomes == []
        mock_list.assert_not_called()


class TestProduceSourceSkippedPaths:
    """TASK-89b-T5 / CD-89b-5: on_skip callback populates ProduceResult.skipped_paths."""

    def test_on_skip_triggered_by_fast_scan_directory_populates_skipped_paths(self):
        """fast_scan_directory's on_skip(path, exc) call must land in result.skipped_paths."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        def fake_list_source_videos(source_path, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None:
                on_skip("/src/videos/broken_dir", PermissionError("denied"))
            return []

        with patch("core.readonly_producer._list_source_videos", side_effect=fake_list_source_videos):
            result = produce_source(source, config, repo, reachable=True)

        assert result.skipped_paths == ["/src/videos/broken_dir"]

    def test_skipped_paths_defaults_empty_when_no_skips(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos", return_value=[]):
            result = produce_source(source, config, repo)

        assert result.skipped_paths == []

    def test_skipped_paths_independent_from_outcomes(self):
        """skipped_paths (FS-layer skip) and outcomes with status='skipped' (DB-layer
        skip, CD-89b-3) are independent — a skipped_paths entry never appears in outcomes
        because it never entered the files loop (TASK-89b-T5 §5.4)."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        def fake_list_source_videos(source_path, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None:
                on_skip("/src/videos/broken_dir", OSError("unreadable"))
            return []  # nothing entered the loop → outcomes stays empty

        with patch("core.readonly_producer._list_source_videos", side_effect=fake_list_source_videos):
            result = produce_source(source, config, repo)

        assert result.skipped_paths == ["/src/videos/broken_dir"]
        assert result.outcomes == []


class TestProduceSourceThreeSignalMatrix:
    """TASK-89b-T5 §5.5: three signals (reachable / bool(outcomes) / skipped_paths)
    must each be independently derivable from ProduceResult, purely as data — no
    prune/gate logic is invoked here (that's T6's job)."""

    def test_unreachable_signal(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos"):
            result = produce_source(source, config, repo, reachable=False)

        # reachable signal
        assert result.aborted_reason == "unreachable"
        # outcomes-non-empty signal
        assert bool(result.outcomes) is False
        # skipped_paths signal
        assert result.skipped_paths == []

    def test_reachable_but_empty_outcomes_signal(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos", return_value=[]):
            result = produce_source(source, config, repo, reachable=True)

        assert result.aborted_reason != "unreachable"
        assert bool(result.outcomes) is False
        assert result.skipped_paths == []

    def test_reachable_with_skipped_paths_signal(self):
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        config = _make_config()

        def fake_list_source_videos(source_path, extensions, min_size_bytes, on_skip=None):
            if on_skip is not None:
                on_skip("/src/videos/partial", OSError("boom"))
            return []

        with patch("core.readonly_producer._list_source_videos", side_effect=fake_list_source_videos):
            result = produce_source(source, config, repo, reachable=True)

        assert result.aborted_reason != "unreachable"
        assert bool(result.outcomes) is False
        assert result.skipped_paths != []  # this single signal should flip a future gate to False


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
             patch.object(repo, "get_attempted_index", return_value={}):
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
             patch.object(repo, "get_attempted_index", return_value={}), \
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
             patch.object(repo, "get_attempted_index", return_value={}), \
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
        # 89b-T2 regression lock: no-number branch must NOT write to DB at all.
        repo.insert_if_ignore.assert_not_called()
        repo.update_scrape_attempted_at.assert_not_called()
        repo.upsert.assert_not_called()

    def test_none_number_emits_no_scrape_outcome(self):
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
             patch("core.readonly_producer.extract_number", return_value=None):
            result = produce_source(source, config, repo)

        assert len(result.outcomes) == 1
        assert result.outcomes[0].status == "no_scrape"


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
        assert inserted.title == "NOTFOUND-001.mp4"  # basename, WITH extension
        # minimal row: no cover/folder-related fields populated
        assert inserted.cover_path == ''
        assert inserted.output_dir == ''
        assert inserted.sample_images == []

        repo.update_scrape_attempted_at.assert_called_once()
        call_args = repo.update_scrape_attempted_at.call_args[0]
        assert call_args[0] == "file:///src/videos/NOTFOUND-001.mp4"
        assert call_args[1] > 0

    def test_idempotent_second_notfound_no_duplicate_row(self):
        """Two NOT-FOUND runs on the same file: insert_if_ignore is called each time
        (2nd call returns False per repo contract, i.e. no duplicate row), but
        update_scrape_attempted_at is unconditionally called every time."""
        repo = MagicMock()
        repo.insert_if_ignore.side_effect = [True, False]

        self._run(repo)
        self._run(repo)

        assert repo.insert_if_ignore.call_count == 2
        assert repo.update_scrape_attempted_at.call_count == 2


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


class TestProduceSourceNotFoundThenSuccessTitleOverwrite:
    """89b-T2 Finding-1 regression lock: NOT-FOUND placeholder title (basename) must
    be overwritten by title from a later successful scrape (upsert has no CASE-WHEN
    guard on title — generic overwrite). Uses a real temp DB (not MagicMock) so the
    ON CONFLICT(path) DO UPDATE semantics are actually exercised."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'

    def test_placeholder_title_overwritten_by_real_title(self, temp_db):
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)

        # Step 1: NOT-FOUND creates the placeholder row.
        created = repo.insert_if_ignore(Video(path=self.SOURCE_URI, number="TEST-001", title="TEST-001.mp4"))
        repo.update_scrape_attempted_at(self.SOURCE_URI, time.time())
        assert created is True

        v1 = repo.get_by_path(self.SOURCE_URI)
        assert v1.title == "TEST-001.mp4"

        # Step 2: a later successful scrape upserts the real title over the same path.
        assets = {'cover_fs': '', 'sample_fs': []}
        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, 'file:///output/TEST-001')

        v2 = repo.get_by_path(self.SOURCE_URI)
        assert v2.title == _T3_META['title']
        assert v2.title != "TEST-001.mp4"


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

        def fake_search_jav(number, source="auto", proxy_url=""):
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
             patch.object(repo, "get_attempted_index", return_value={}), \
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

        def fake_write(movie_dir, meta_arg, fd_arg, src_path, cfg, old_base='', strm_mappings_getter=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("disk full")
            return {"cover_fs": "", "sample_fs": []}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/X"

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
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
             patch.object(repo, "get_attempted_index", return_value={}), \
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

    def test_thumbnail_cache_invalidated_for_each_pruned_path(self):
        this_run_files = [_make_file_info(path="/src/videos/EXIST-001.mp4")]
        get_all_rows = [self.ROW_EXIST, self.ROW_GONE_ATTEMPTED, self.ROW_GONE_PRODUCED]

        result, repo, mock_thumb = self._run(get_all_rows=get_all_rows, this_run_files=this_run_files)

        assert mock_thumb.invalidate.call_count == 2
        invalidated = {c.args[0] for c in mock_thumb.invalidate.call_args_list}
        assert invalidated == {self.ROW_GONE_ATTEMPTED.path, self.ROW_GONE_PRODUCED.path}

    def test_get_all_and_delete_by_paths_called_once_per_source(self):
        """Boundary condition: prune runs once after the loop, not per-file (non-N+1)."""
        this_run_files = [_make_file_info(path="/src/videos/EXIST-001.mp4")]
        get_all_rows = [self.ROW_EXIST, self.ROW_GONE_ATTEMPTED]

        result, repo, mock_thumb = self._run(get_all_rows=get_all_rows, this_run_files=this_run_files)

        assert repo.get_all.call_count == 1
        assert repo.delete_by_paths.call_count == 1

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

    def test_candidates_empty_skips_delete_by_paths_call(self):
        """When no row qualifies as a candidate, delete_by_paths must not be invoked
        at all (not called with an empty list)."""
        this_run_files = [_make_file_info(path="/src/videos/EXIST-001.mp4")]
        get_all_rows = [self.ROW_EXIST, self.ROW_NEVER_ATTEMPTED, self.ROW_OTHER_SOURCE]

        result, repo, mock_thumb = self._run(get_all_rows=get_all_rows, this_run_files=this_run_files)

        repo.get_all.assert_called_once()
        repo.delete_by_paths.assert_not_called()
        mock_thumb.invalidate.assert_not_called()

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

    def test_empty_mappings_returns_original(self):
        from core.readonly_producer import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115\\x.mp4', {}) == 'Z:\\115\\x.mp4'

    def test_no_match_returns_original(self):
        from core.readonly_producer import _apply_path_mapping
        assert _apply_path_mapping('D:\\other\\x.mp4', {'Z:\\115': '/vol'}) == 'D:\\other\\x.mp4'

    def test_boundary_guard_no_false_match_on_longer_dir(self):
        """Z:\\1150\\a.mp4 must NOT match a Z:\\115 rule (0 is not a separator)."""
        from core.readonly_producer import _apply_path_mapping
        assert _apply_path_mapping('Z:\\1150\\a.mp4', {'Z:\\115': '/vol'}) == 'Z:\\1150\\a.mp4'

    def test_single_match_windows_separator(self):
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '/volume1/movie'})
        assert out == '/volume1/movie/x.mp4'  # remainder from URI space (forward-slash)

    def test_single_match_unix_separator(self):
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('/mnt/z/115/x.mp4', {'/mnt/z/115': '/volume1'})
        assert out == '/volume1/x.mp4'

    def test_empty_remote_rule_skipped_not_prefix_stripped(self):
        """PR #93 P2：半填規則 remote='' 不得把 local 前綴剝掉只剩後綴 → skip、source 原樣回。"""
        from core.readonly_producer import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': ''}) == 'Z:\\115\\x.mp4'
        assert _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '   '}) == 'Z:\\115\\x.mp4'

    def test_empty_remote_skipped_but_valid_rule_still_applies(self):
        """混合：空 remote 規則 skip，同批有效規則照常套（不因半填列污染整批）。"""
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\other': '', 'Z:\\115': '/vol'})
        assert out == '/vol/x.mp4'

    def test_prefix_equals_whole_string_matches(self):
        from core.readonly_producer import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115', {'Z:\\115': '/vol'}) == '/vol'

    def test_nested_longest_prefix_wins(self):
        from core.readonly_producer import _apply_path_mapping
        mappings = {'Z:\\115': '/a', 'Z:\\115\\成人': '/b'}
        assert _apply_path_mapping('Z:\\115\\成人\\x.mp4', mappings) == '/b/x.mp4'

    def test_longest_match_independent_of_insertion_order(self):
        """Same content dict built in both orders → identical output (deterministic)."""
        from core.readonly_producer import _apply_path_mapping
        forward = {'Z:\\115': '/a', 'Z:\\115\\成人': '/b'}
        reverse = {'Z:\\115\\成人': '/b', 'Z:\\115': '/a'}
        p = 'Z:\\115\\成人\\x.mp4'
        assert _apply_path_mapping(p, forward) == _apply_path_mapping(p, reverse) == '/b/x.mp4'

    def test_foreign_unix_target_not_normalized_or_raised(self):
        """Mapped output is a bare Unix path (/volume1/...): returned verbatim,
        no path_utils call, no ValueError even on a Windows-style source."""
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '/volume1/movie'})
        assert out.startswith('/volume1/movie')

    def test_trailing_separator_in_local_prefix_still_matches(self):
        """Codex P2: a local_prefix carrying a trailing separator ('/mnt/z/115/')
        must still match — the URI form is rstrip'd of '/'. Raw-string compare
        would have missed (source lacks the doubled sep) and returned unchanged."""
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('/mnt/z/115/x.mp4', {'/mnt/z/115/': '/vol'})
        assert out == '/vol/x.mp4'

    def test_cross_namespace_windows_prefix_matches_wsl_source(self):
        """Codex P1: a Windows-DISPLAY prefix ('C:\\115', as pathToDisplay prefills)
        must match a WSL-NATIVE source ('/mnt/c/115/x.mp4') — both converge to
        file:///C:/115 in URI space. Raw-string compare would have silently missed
        and written the un-mapped source. Host-independent (green on Linux CI + WSL:
        to_file_uri's /mnt & drive-letter branches are not env-gated)."""
        from core.readonly_producer import _apply_path_mapping
        out = _apply_path_mapping('/mnt/c/115/x.mp4', {'C:\\115': '/volume1'})
        assert out == '/volume1/x.mp4'


class TestWriteStrm:
    """_write_strm: media-server sidecar, single-line utf-8 no-BOM, best-effort,
    same-level strm_path_mappings read."""

    def test_writes_mapped_content_single_line_no_bom(self, tmp_path):
        from core.readonly_producer import _write_strm
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

    def test_empty_mappings_writes_raw_source_path(self, tmp_path):
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {})
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == 'Z:\\115\\x.mp4'

    def test_mappings_read_same_level_not_via_scraper(self, tmp_path):
        """Regression: mapping table must be read from config['strm_path_mappings']
        directly, NOT config['scraper']['strm_path_mappings'] (which is always {}
        because config already IS the scraper section)."""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        # A nested 'scraper' key must be ignored; the top-level mapping applies.
        config = {
            'strm_path_mappings': {'Z:\\115': '/volume1'},
            'scraper': {'strm_path_mappings': {'Z:\\115': '/WRONG'}},
        }
        _write_strm(base_stem, 'Z:\\115\\x.mp4', config)
        content = Path(base_stem + '.strm').read_text(encoding='utf-8')
        assert content == '/volume1/x.mp4'
        assert 'WRONG' not in content

    def test_foreign_target_written_verbatim(self, tmp_path):
        """Bare Unix mapped target on any host → written as-is, function returns True."""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/volume1/movie'}}
        ok = _write_strm(base_stem, 'Z:\\115\\clip.mp4', config)
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == '/volume1/movie/clip.mp4'

    # --- PR #93 五審四次 P2 (option C)：strm_mappings 覆寫參數 ---

    def test_strm_mappings_override_wins_over_config(self, tmp_path):
        """strm_mappings 非 None → 覆寫 config['strm_path_mappings']（producer 傳 fresh 讀，
        使斷線尾巴那片用當前映射而非 generate 起始凍結值）。"""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/OLD'}}  # 凍結舊值
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config,
                         strm_mappings={'Z:\\115': '/NEW'})  # fresh 覆寫
        assert ok is True
        content = Path(base_stem + '.strm').read_text(encoding='utf-8')
        assert content == '/NEW/x.mp4'
        assert 'OLD' not in content

    def test_strm_mappings_none_uses_config_legacy(self, tmp_path):
        """strm_mappings=None（預設）→ 沿用 config 讀（rewrite_strm / 既有呼叫不受影響）。"""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/volume1'}}
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config, strm_mappings=None)
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == '/volume1/x.mp4'

    def test_empty_override_writes_raw_not_config_mapping(self, tmp_path):
        """strm_mappings={} 是有效覆寫（非 None）→ 用空映射（寫原始路徑），不回退 config。"""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/SHOULD-NOT-APPLY'}}
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config, strm_mappings={})
        assert ok is True
        content = Path(base_stem + '.strm').read_text(encoding='utf-8')
        assert content == 'Z:\\115\\x.mp4'
        assert 'SHOULD-NOT-APPLY' not in content

    def test_write_failure_is_best_effort_returns_false(self, tmp_path):
        """open() raising → warning logged, returns False, does NOT raise."""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        with patch('core.readonly_producer.open', side_effect=OSError('disk full'), create=True):
            ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {})
        assert ok is False
        assert not Path(base_stem + '.strm').exists()

    def test_non_str_mapping_value_is_best_effort_not_raise(self, tmp_path):
        """raw config (not model_validated) with a non-str mapping value must not
        escape best-effort: _apply_path_mapping TypeError is caught, returns False,
        never raises (NIT-1 — mapping call moved inside try + broad catch)."""
        from core.readonly_producer import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        # hand-edited config.json could carry a non-str value; None → str concat TypeError
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {'strm_path_mappings': {'Z:\\115': None}})
        assert ok is False


class TestWriteMovieAssetsStrm:
    """_write_movie_assets strm fork: written for media-server flavours, skipped for off."""

    def test_media_server_flavour_writes_strm(self, tmp_path):
        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Title A')
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin',
                      strm_path_mappings={'/src': '/volume1'})
        _t4_write(movie_dir, meta, config)
        strm = Path(movie_dir) / 'TEST-001 Title A.strm'
        assert strm.exists()
        assert strm.read_text(encoding='utf-8') == '/volume1/TEST-001.mp4'

    def test_off_flavour_writes_no_strm(self, tmp_path):
        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Title A')
        config = dict(_T3_BASE_CONFIG, external_manager='off')
        _t4_write(movie_dir, meta, config)
        assert not (Path(movie_dir) / 'TEST-001 Title A.strm').exists()

    def test_getter_evaluated_after_nfo_at_write_time(self, tmp_path):
        """五審五次 Codex：strm_mappings_getter 在 NFO 等資產寫完後、_write_strm 前一刻才求值
        （非片處理開頭 snapshot）。否則求值後、封面/NFO 寫檔期間存的新映射會被漏掉。"""
        from core.readonly_producer import _format_data, _write_movie_assets
        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Title A')
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin',
                      strm_path_mappings={'/src': '/FROZEN'})
        fd = _format_data(meta, '/src/TEST-001.mp4', config)

        order = []

        def rec_nfo(*a, **k):
            order.append('nfo')
            return _t4_real_nfo(*a, **k)

        def getter():
            order.append('getter')
            return {'/src': '/FRESH'}

        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=rec_nfo):
            _write_movie_assets(movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                                strm_mappings_getter=getter)

        # getter 在 nfo 之後才被呼叫（求值延到 _write_strm 前一刻）
        assert order == ['nfo', 'getter'], order
        # 且 .strm 用 getter 的 fresh 映射，非 config 凍結值
        strm = Path(movie_dir) / 'TEST-001 Title A.strm'
        assert strm.read_text(encoding='utf-8') == '/FRESH/TEST-001.mp4'


class TestCleanStaleStrm:
    """Stale strm cleanup: title-drift removes <old_base>.strm only when has_strm."""

    def test_has_strm_true_removes_old_strm(self, tmp_path):
        from core.readonly_producer import _clean_stale_singletons
        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        (d / f'{old_base}.nfo').write_bytes(b'x')
        (d / f'{old_base}.strm').write_bytes(b'/vol/old.mp4')
        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False, True)
        assert not (d / f'{old_base}.strm').exists(), "stale strm must be cleaned on title drift"

    def test_has_strm_false_keeps_old_strm(self, tmp_path):
        """strm write failed this run (has_strm False) → old strm must survive."""
        from core.readonly_producer import _clean_stale_singletons
        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        (d / f'{old_base}.nfo').write_bytes(b'x')
        (d / f'{old_base}.strm').write_bytes(b'/vol/old.mp4')
        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False, False)
        assert (d / f'{old_base}.strm').exists(), "old strm must survive when has_strm is False"

    def test_default_has_strm_is_false(self, tmp_path):
        """6-arg call (legacy) → strm never touched (backward compat)."""
        from core.readonly_producer import _clean_stale_singletons
        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        (d / f'{old_base}.nfo').write_bytes(b'x')
        (d / f'{old_base}.strm').write_bytes(b'/vol/old.mp4')
        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False)
        assert (d / f'{old_base}.strm').exists()


class TestWriteMovieAssetsStrmDrift:
    """Integration: title drift under a media-server flavour removes the old strm
    and leaves only the new one (Emby double-entry prevention)."""

    def test_title_drift_removes_old_strm_keeps_new(self, tmp_path):
        from core.readonly_producer import _build_old_base
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

    def test_strm_write_failure_preserves_old_strm(self, tmp_path):
        """When _write_strm returns False this run, has_strm gating keeps the old strm."""
        from core.readonly_producer import _build_old_base, _format_data, _write_movie_assets
        movie_dir = str(tmp_path / 'TEST-001')
        config = dict(_T3_BASE_CONFIG, external_manager='kodi',
                      strm_path_mappings={'/src': '/volume1'})
        meta_a = dict(_T3_META, title='Title A')
        meta_b = dict(_T3_META, title='Title B')

        _t4_write(movie_dir, meta_a, config)
        d = Path(movie_dir)
        assert (d / 'TEST-001 Title A.strm').exists()

        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)
        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo), \
             patch('core.readonly_producer._write_strm', return_value=False):
            _write_movie_assets(movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config, old_base=old_base)

        assert (d / 'TEST-001 Title A.strm').exists(), \
            "old strm must survive when this run's strm write failed (has_strm False)"


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
    def fake_search_jav(number, source="auto", proxy_url=""):
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
         patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
         patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
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
            # the base cover (neither poster nor fanart) is present too
            assert any(
                not c.name.endswith('-poster.jpg') and not c.name.endswith('-fanart.jpg')
                for c in covers
            ), f"{d.name}: no base cover .jpg"

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

    def test_option_c_getter_supplies_fresh_mapping_over_frozen(self, tmp_path):
        """凍結 config 帶舊映射、getter 回新映射 → .strm 用新映射（斷線尾巴那片不 stale）。"""
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG,
            external_manager='jellyfin',
            strm_path_mappings={str(source_dir): '/OLD-FROZEN'},  # generate 起始凍結值
        ))
        fresh_getter = lambda: {str(source_dir): '/NEW-FRESH'}  # noqa: E731 — 測試用簡短 getter

        result, _repo = _e2e_run_produce_source(
            source_dir, output_dir, config, self.FILENAMES, strm_mappings_getter=fresh_getter)

        assert result.created == 2
        contents = {d.glob('*.strm').__next__().read_text(encoding='utf-8')
                    for d in _movie_dirs(output_dir)}
        assert contents == {f'/NEW-FRESH/{fn}' for fn in self.FILENAMES}, contents
        assert all('OLD-FROZEN' not in c for c in contents)

    def test_option_c_no_getter_uses_frozen_config_mapping(self, tmp_path):
        """getter=None（既有呼叫/rewrite/測試）→ 用凍結 config 映射、不重讀 config、行為不變。"""
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(
            _T3_BASE_CONFIG,
            external_manager='jellyfin',
            strm_path_mappings={str(source_dir): '/FROZEN-ONLY'},
        ))

        result, _repo = _e2e_run_produce_source(
            source_dir, output_dir, config, self.FILENAMES)  # 無 getter

        assert result.created == 2
        contents = {d.glob('*.strm').__next__().read_text(encoding='utf-8')
                    for d in _movie_dirs(output_dir)}
        assert contents == {f'/FROZEN-ONLY/{fn}' for fn in self.FILENAMES}, contents

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
        with patch('core.readonly_producer.resolve_output_root', return_value=str(output_dir)):
            result, _repo = _e2e_run_produce_source(source_dir, output_dir, config, self.FILENAMES)

        assert result.created == 2, f"off run must still produce (created={result.created})"
        dirs = _movie_dirs(output_dir)
        assert len(dirs) == 2
        for d in dirs:
            assert not list(d.glob('*.strm')), f"off flavour must not write a .strm in {d.name}"
            # but the off assets are still there (nfo + cover) — strm is the only delta
            assert list(d.glob('*.nfo')), f"off flavour still writes nfo in {d.name}"


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
         patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
         patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
         patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
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

    def test_censored_file_not_submitted(self, tmp_path, temp_db):
        """DoD ③: a censored number (SSIS-*, non-whitelisted maker) is an empty-focal
        candidate too (auto_focal just written as '') but requires_face_detection
        gates it out — zero submit calls."""
        from core.database import VideoRepository

        source_dir, output_dir = _focal_setup_source(tmp_path, ['SSIS-002.mp4'])
        repo = VideoRepository(temp_db)

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(source_dir, output_dir, repo, ['SSIS-002.mp4'])

        assert result.created == 1
        mock_submit.assert_not_called()

    def test_cover_already_on_disk_when_submit_is_called(self, tmp_path, temp_db):
        """DoD ④ (順序陷阱鎖): by the time maybe_submit_video_focal is invoked, the
        produced cover file must already exist on disk — proving the pass truly
        runs AFTER the per-file loop (assets already written), not mid-loop
        before _write_movie_assets. A hook mis-placed before asset-writing would
        still 'not raise' (maybe_submit_video_focal is mocked here) but the
        real-file assertion below is what actually pins the ordering."""
        from core.database import VideoRepository

        source_dir, output_dir = _focal_setup_source(tmp_path, ['SIRO-003.mp4'])
        repo = VideoRepository(temp_db)

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(source_dir, output_dir, repo, ['SIRO-003.mp4'])

        assert result.created == 1
        mock_submit.assert_called_once()
        cover_fs = mock_submit.call_args[0][3]
        assert cover_fs and os.path.exists(cover_fs), (
            "cover file must already be on disk when the focal pass submits — "
            "proves post-loop placement, not just 'no exception was raised'"
        )

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

    def test_abort_mid_candidate_loop_stops_after_first_submit(self, tmp_path, temp_db):
        """Codex P1 (CD-99b-8 二次修): should_abort flips True only AFTER the
        bulk query has started and the FIRST candidate has already been
        submitted — the loop-top gate (not just the :912 entry gate) must stop
        the remaining candidates from being submitted. Without a per-iteration
        check, a cancel that lands mid-candidate-loop (candidates can reach the
        thousands, each iteration costs an os.path.exists syscall against a
        possibly-slow readonly mount) would still queue everything after the
        point of cancellation into the single-threaded FIFO focal worker."""
        from core.database import VideoRepository

        filenames = ['SIRO-050.mp4', 'SIRO-051.mp4', 'SIRO-052.mp4']
        source_dir, output_dir = _focal_setup_source(tmp_path, filenames)
        repo = VideoRepository(temp_db)

        call_count = [0]

        def abort_after_first_candidate():
            call_count[0] += 1
            # Calls 1-3: per-file loop (all 3 files processed, not aborted).
            # Call 4: post-loop entry gate (:912, not aborted — bulk query runs).
            # Call 5: top of candidate-loop iteration 1 (not aborted — 1st
            # candidate gets submitted). Call 6+: abort flips True, so the
            # candidate-loop-top gate breaks before candidate 2 is submitted.
            return call_count[0] > 5

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(
                source_dir, output_dir, repo, filenames, should_abort=abort_after_first_candidate)

        assert result.created == 3, "sanity: all 3 files processed before the candidate loop is reached"
        assert mock_submit.call_count == 1, (
            "only the first candidate may be submitted — the candidate-loop-top "
            "gate must stop the remaining 2 once should_abort flips True mid-loop"
        )

    def test_get_empty_focal_candidates_exception_does_not_abort_generation(self, tmp_path, temp_db):
        """DoD ⑦: bulk-query failure is a pure side-effect failure — result.created
        must be unaffected, only a logger.warning(exc_info=True) is left behind."""
        from core.database import VideoRepository

        source_dir, output_dir = _focal_setup_source(tmp_path, ['SIRO-020.mp4'])
        repo = VideoRepository(temp_db)
        repo.get_empty_focal_candidates = MagicMock(side_effect=RuntimeError("boom"))

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit, \
             patch('core.readonly_producer.logger') as mock_logger:
            result = _focal_run_produce_source(source_dir, output_dir, repo, ['SIRO-020.mp4'])

        assert result.created == 1, "focal bulk-query failure must not affect the generation result"
        mock_submit.assert_not_called()
        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args.kwargs.get('exc_info') is True

    def test_this_run_uris_share_namespace_with_upsert_key(self, tmp_path, temp_db):
        """DoD ⑨: the URI the focal pass computes from `files` (this_run_uris) must
        be the exact same key _upsert_db wrote the row under — otherwise the
        bulk query would silently miss every candidate while looking perfectly
        fine (namespace-mismatch bug class, HANDOFF §3.2)."""
        from core.database import VideoRepository
        from core.path_utils import to_file_uri

        source_dir, output_dir = _focal_setup_source(tmp_path, ['SIRO-030.mp4'])
        repo = VideoRepository(temp_db)

        with patch('core.readonly_producer.maybe_submit_video_focal') as mock_submit:
            result = _focal_run_produce_source(source_dir, output_dir, repo, ['SIRO-030.mp4'])

        assert result.created == 1
        expected_uri = to_file_uri(str(source_dir / 'SIRO-030.mp4'))
        row = repo.get_by_path(expected_uri)
        assert row is not None, "produce_source's upsert key must match the focal pass's own URI derivation"
        # The real assertion for CD-99b-6/HANDOFF §3.2: get_empty_focal_candidates
        # actually FOUND this row via the focal pass's own URI derivation (not
        # just that _upsert_db wrote it under expected_uri — a namespace
        # mismatch between the two would leave the row present but the bulk
        # query would silently return zero candidates for it).
        mock_submit.assert_called_once()
        assert mock_submit.call_args[0][2] == expected_uri


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
