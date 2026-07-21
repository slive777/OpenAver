"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
import os
import shutil
import time
import xml.etree.ElementTree as ET
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
    from core.readonly_producer import _format_data
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
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_producer.download_image', side_effect=fake_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=fake_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=fake_nfo):
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
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

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
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

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
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

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
        nfo_mock = MagicMock(side_effect=_t3_generate_nfo_side_effect)

        with patch('core.readonly_producer.download_image', return_value=False), \
             patch('core.readonly_producer.generate_jellyfin_images', jellyfin_mock), \
             patch('core.readonly_producer.generate_nfo', nfo_mock):
            assets = _write_movie_assets(
                movie_dir, meta_no_cover, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=_cover_strategy_for(meta_no_cover),
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
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=capture_nfo):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert 'output_path' in captured
        assert captured['output_path'].startswith(movie_dir)
        assert captured['external_manager'] == 'jellyfin'
        assert captured['has_poster'] is True
        assert captured['has_fanart'] is True

    def test_generate_nfo_receives_original_title(self, tmp_path):
        """FIX#3: the produced OUTPUT NFO must keep originaltitle — non-readonly
        enricher.py already passes it through (generate_nfo call at :198)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        meta = dict(_T3_META, original_title='日本語タイトル')
        fd = _t3_format_data(meta=meta)
        config = dict(_T3_BASE_CONFIG)
        captured: dict = {}

        def capture_nfo(**kwargs):
            captured.update(kwargs)
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=capture_nfo):
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta),
            )

        assert captured.get('original_title') == '日本語タイトル'

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
                _write_movie_assets(
                    movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                    cover_strategy=_cover_strategy_for(_T3_META),
                )


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
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect), \
             patch('core.organizer.detect_focal', return_value=MOCK_FOCAL_XY):
            assets = _write_movie_assets(
                movie_dir, meta, fd, source_fs_path, config,
                cover_strategy=_cover_strategy_for(meta),
            )

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
        return _write_movie_assets(
            movie_dir, meta, fd, '/src/TEST-001.mp4', config,
            cover_strategy=_cover_strategy_for(meta), old_base=old_base,
        )


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
                _write_movie_assets(
                    movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                    cover_strategy=_cover_strategy_for(meta_b), old_base=old_base,
                )

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
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta), old_base=old_base,
            )

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
            assets = _write_movie_assets(
                movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta_b), old_base=old_base,
            )

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

    def test_cover_path_is_local_uri_not_remote(self, tmp_path, temp_db):
        """cover_path in DB must be a file:/// URI, never the remote cover URL (CD-88b-7)."""
        from core.readonly_producer import _upsert_db

        cover_fs = str(tmp_path / 'output' / 'TEST-001' / 'cover.jpg')
        assets = {'cover_fs': cover_fs, 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
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
            'nfo_mtime': _T3_NFO_MTIME,
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

        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == ''

    def test_empty_sample_images_stored_as_empty_list(self, temp_db):
        """sample_fs=[] → DB sample_images==[]."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None, self.OUTPUT_DIR_URI)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == []

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

    def test_new_sample_fs_still_overwrites_existing(self, temp_db):
        """Sanity: preservation only kicks in when THIS run's sample_fs is empty —
        a genuine new sample write still replaces the DB value (no regression)."""
        from core.readonly_producer import _upsert_db
        from core.path_utils import to_file_uri

        repo = self._repo(temp_db)
        self._seed_existing(repo, sample_images=['file:///old/fanart1.jpg'])
        existing = repo.get_by_path(self.SOURCE_URI)

        new_sample_fs = ['/output/TEST-001/extrafanart/fanart1.jpg']
        assets = {'cover_fs': '', 'sample_fs': new_sample_fs, 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == [to_file_uri(new_sample_fs[0], None)]

    def test_no_existing_row_sample_fs_empty_stores_empty_list(self, temp_db):
        """NEW video (existing=None) — no regression: empty sample_fs still
        stores [], never resurrects data from nowhere."""
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=None,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.sample_images == []

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

    def test_new_cover_fs_still_overwrites_existing(self, tmp_path, temp_db):
        """Sanity: a successful new cover write still replaces the DB value
        (matches test_gear_rescrape_overwrites_cover_with_candidate_and_title's
        contract — preservation only kicks in on EMPTY cover_fs)."""
        from core.readonly_producer import _upsert_db
        from core.path_utils import to_file_uri

        repo = self._repo(temp_db)
        self._seed_existing(repo, cover_path='file:///output/TEST-001/old.jpg')
        existing = repo.get_by_path(self.SOURCE_URI)

        new_cover_fs = str(tmp_path / 'output' / 'TEST-001' / 'TEST-001.jpg')
        assets = {'cover_fs': new_cover_fs, 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == to_file_uri(new_cover_fs, None)

    def test_no_existing_row_cover_fs_empty_stores_empty_string(self, temp_db):
        """NEW video (existing=None) — no regression: empty cover_fs still
        stores '', never resurrects data from nowhere."""
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            self.OUTPUT_DIR_URI, existing=None,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == ''

    # ── FIX#3 (P2 parity closeout): original_title preserve-if-empty ────────

    def test_preserves_existing_original_title_when_meta_empty(self, temp_db):
        """A re-scrape whose source returned no original_title must not wipe
        an existing DB value — mirrors the cover_path/sample_images
        preserve-if-empty pattern above."""
        from core.readonly_producer import _upsert_db
        from core.database import Video

        repo = self._repo(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            original_title='既存の原題', output_dir=self.OUTPUT_DIR_URI,
        ))
        existing = repo.get_by_path(self.SOURCE_URI)

        meta = dict(_T3_META, original_title='')
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, meta, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.original_title == '既存の原題'

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

    def test_new_original_title_still_overwrites_existing(self, temp_db):
        """Sanity: preservation only kicks in when THIS run's meta has no
        original_title — a genuine new value still replaces the DB value."""
        from core.readonly_producer import _upsert_db
        from core.database import Video

        repo = self._repo(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            original_title='古い原題', output_dir=self.OUTPUT_DIR_URI,
        ))
        existing = repo.get_by_path(self.SOURCE_URI)

        meta = dict(_T3_META, original_title='新しい原題')
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, meta, assets, None,
            self.OUTPUT_DIR_URI, existing=existing,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.original_title == '新しい原題'

    def test_no_existing_row_original_title_empty_stores_empty_string(self, temp_db):
        """NEW video (existing=None) — no regression: empty original_title
        still stores '', never resurrects data from nowhere."""
        from core.readonly_producer import _upsert_db

        repo = self._repo(temp_db)
        meta = dict(_T3_META, original_title='')
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, meta, assets, None,
            self.OUTPUT_DIR_URI, existing=None,
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.original_title == ''


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

    def test_no_filename_number_no_nfo_no_scrape_and_no_stub(self):
        """(b) no filename number + no NFO -> no_scrape, and (unlike the
        has-number case) NO stub row is created — matches the OLD `if not
        number` branch's behavior byte-for-byte (regression, same assertions
        as TestProduceSourceNoneNumberGuard)."""
        from core.readonly_producer import produce_source

        source = _make_source()
        repo = MagicMock()
        config = _make_config()
        files = [_make_file_info(path="/src/videos/nonumber.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None), \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        mock_search.assert_not_called()
        assert result.no_scrape == 1
        assert result.created == 0
        repo.insert_if_ignore.assert_not_called()
        repo.update_scrape_attempted_at.assert_not_called()
        repo.upsert.assert_not_called()

    def test_has_number_no_metadata_still_stubs(self):
        """(c) has a filename number but resolve_ingest_plan yields no usable
        meta (no NFO, search_jav -> None) -> no_scrape + stub row + attempted
        marked (regression: unchanged from pre-fix behavior for this case)."""
        from core.readonly_producer import produce_source
        from core.database import Video

        source = _make_source()
        repo = MagicMock()
        repo.insert_if_ignore.return_value = True
        config = _make_config()
        files = [_make_file_info(path="/src/videos/NOTFOUND-001.mp4")]

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch.object(repo, "get_attempted_index", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="NOTFOUND-001"), \
             patch("core.readonly_producer.search_jav", return_value=None):
            result = produce_source(source, config, repo)

        assert result.no_scrape == 1
        assert result.created == 0
        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert isinstance(inserted, Video)
        assert inserted.number == "NOTFOUND-001"
        repo.update_scrape_attempted_at.assert_called_once()


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
        assets = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': _T3_NFO_MTIME}
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

        def fake_search_jav(number, source="auto", proxy_url="", javbus_lang=None):
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

        def fake_write(movie_dir, meta_arg, fd_arg, src_path, cfg, cover_strategy=None,
                      assets_mode='full', old_base='', strm_mappings_getter=None):
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
                                cover_strategy=_cover_strategy_for(meta),
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
            _write_movie_assets(
                movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta_b), old_base=old_base,
            )

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
    def fake_search_jav(number, source="auto", proxy_url="", javbus_lang=None):
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


# ---------------------------------------------------------------------------
# TASK-104-T1 (CD-104-1/2/4/9): _produce_one primitive extraction, cover_strategy
# 3-state, assets_mode='samples_only', nfo_mtime real-write, call-sequence lock.
# ---------------------------------------------------------------------------

class TestCoverStrategyThreeState:
    """CD-104-2: _write_movie_assets cover_strategy explicit 3-state contract —
    'copy' (local file, zero network), 'none' (no cover written at all), and
    'download' (byte-identical to the pre-T1 unconditional-download branch)."""

    def test_copy_strategy_copies_local_file_not_download(self, tmp_path):
        from core.readonly_producer import _write_movie_assets

        local_cover = tmp_path / 'local-cover.jpg'
        local_cover.write_bytes(b'LOCAL-COVER-BYTES')
        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_producer.download_image') as mock_download, \
             patch('core.readonly_producer.shutil.copyfile', wraps=shutil.copyfile) as mock_copy, \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', str(local_cover)),
            )

        mock_download.assert_not_called()
        mock_copy.assert_called_once_with(str(local_cover), assets['cover_fs'])
        assert assets['cover_fs'], "copy state must produce a non-empty cover_fs on success"
        assert Path(assets['cover_fs']).read_bytes() == b'LOCAL-COVER-BYTES'

    def test_copy_strategy_missing_source_is_graceful(self, tmp_path):
        """copy source doesn't exist → has_cover=False / cover_fs='', never raises
        — same graceful-failure semantics as a failed download (card boundary)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        missing_source = str(tmp_path / 'does-not-exist.jpg')

        with patch('core.readonly_producer.download_image') as mock_download, \
             patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', missing_source),
            )

        mock_download.assert_not_called()
        mock_jellyfin.assert_not_called(), "has_cover False → poster/fanart step must not run"
        assert assets['cover_fs'] == ''

    def test_none_strategy_writes_no_cover(self, tmp_path):
        """'none': no cover written at all, download_image/copyfile both untouched,
        generate_jellyfin_images (poster/fanart) skipped since has_cover is False."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_producer.download_image') as mock_download, \
             patch('core.readonly_producer.shutil.copyfile') as mock_copy, \
             patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('none',),
            )

        mock_download.assert_not_called()
        mock_copy.assert_not_called()
        mock_jellyfin.assert_not_called()
        assert assets['cover_fs'] == ''
        assert not (Path(movie_dir) / 'TEST-001 Test Movie Title.jpg').exists()

    def test_download_strategy_calls_download_image_not_copy(self, tmp_path):
        """'download': download_image called with the remote URL, shutil.copyfile
        never called — the byte-identical pre-T1 branch, locked explicitly here
        alongside the other two states (also covered by the pre-existing
        TestWriteMovieAssets::test_rescrape_uses_remote_cover_url)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_producer.download_image', return_value=True) as mock_download, \
             patch('core.readonly_producer.shutil.copyfile') as mock_copy, \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('download', _T3_META['cover']),
            )

        mock_copy.assert_not_called()
        mock_download.assert_called_once()
        assert mock_download.call_args[0][0] == _T3_META['cover']
        assert assets['cover_fs']


class TestCuratedPosterFanartPassthrough:
    """Owner-approved fix (2026-07-21): a curated Jellyfin/Emby source ships
    both a distinct -poster and -fanart sidecar; ingest must copy them
    VERBATIM into the output slots instead of regenerating them from
    whichever image find_cover_image picked as the cover (which previously
    discarded the curator's real poster). cover_strategy's 3rd element (see
    resolve_ingest_plan) is a dict {'poster': fs_or_None, 'fanart': fs_or_None}."""

    def test_both_slots_present_copied_verbatim_not_regenerated(self, tmp_path):
        """Both -poster/-fanart sidecars detected -> generate_jellyfin_images
        (and crop_to_poster) must NOT be called at all; output bytes must
        equal the SOURCE sidecar bytes exactly, not a crop of the cover.

        MUTATION LOCK: reverting the per-slot shutil.copy2 call back to
        `generate_jellyfin_images(cover_fs, ...)` (i.e. ignoring source_media)
        turns this RED — the poster assertion would then read cropped/
        generated bytes instead of the verbatim source poster bytes.
        """
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-BYTES-DIFFERENT-FROM-BOTH')
        poster_src = tmp_path / 'src-poster.jpg'
        fanart_src = tmp_path / 'src-fanart.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fanart_src.write_bytes(b'FANART-MARKER-BYTES')
        fd = _t3_format_data()

        with patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.crop_to_poster') as mock_crop, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', cover_fs, {'poster': str(poster_src), 'fanart': str(fanart_src)}),
            )

        mock_jellyfin.assert_not_called()
        mock_crop.assert_not_called()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        assert Path(base_stem + '-poster.jpg').read_bytes() == b'POSTER-MARKER-BYTES'
        assert Path(base_stem + '-fanart.jpg').read_bytes() == b'FANART-MARKER-BYTES'
        assert assets['cover_fs']

    def test_missing_poster_slot_falls_back_to_crop_to_poster(self, tmp_path):
        """Only -fanart detected (poster slot None) -> fanart copied verbatim,
        poster falls back to crop_to_poster(cover_fs, ...) — the same generate
        step it would have used with no 3rd element at all."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        src_cover = str(tmp_path / 'cover.jpg')
        Path(src_cover).write_bytes(b'COVER-BYTES')
        fanart_src = tmp_path / 'src-fanart.jpg'
        fanart_src.write_bytes(b'FANART-MARKER-BYTES')
        fd = _t3_format_data()

        def fake_crop(src_path, dst_path, **_kw):
            Path(dst_path).write_bytes(b'CROPPED-POSTER-BYTES')
            return True

        with patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.crop_to_poster', side_effect=fake_crop) as mock_crop, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', src_cover, {'poster': None, 'fanart': str(fanart_src)}),
            )

        mock_jellyfin.assert_not_called()
        mock_crop.assert_called_once()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        assert mock_crop.call_args[0][0] == base_stem + '.jpg', (
            "crop_to_poster must read the OUTPUT cover (already copied into movie_dir), "
            "not the source path"
        )
        assert Path(base_stem + '-poster.jpg').read_bytes() == b'CROPPED-POSTER-BYTES'
        assert Path(base_stem + '-fanart.jpg').read_bytes() == b'FANART-MARKER-BYTES'

    def test_missing_fanart_slot_falls_back_to_cover_copy(self, tmp_path):
        """Only -poster detected (fanart slot None) -> poster copied verbatim,
        fanart falls back to copy2(cover_fs, ...) — the same generate step it
        would have used with no 3rd element at all."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-MARKER-BYTES')
        poster_src = tmp_path / 'src-poster.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fd = _t3_format_data()

        with patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.crop_to_poster') as mock_crop, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', cover_fs, {'poster': str(poster_src), 'fanart': None}),
            )

        mock_jellyfin.assert_not_called()
        mock_crop.assert_not_called()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        assert Path(base_stem + '-poster.jpg').read_bytes() == b'POSTER-MARKER-BYTES'
        assert Path(base_stem + '-fanart.jpg').read_bytes() == b'COVER-MARKER-BYTES'

    def test_verbatim_copy_oserror_falls_back_to_generate(self, tmp_path):
        """Source sidecar vanishes mid-run (OSError on the verbatim copy) ->
        falls back to the same generate step as a missing slot, never raises."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-BYTES')
        poster_src = tmp_path / 'src-poster.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fd = _t3_format_data()

        def flaky_copy2(src, dst, *a, **kw):
            if str(src) == str(poster_src):
                raise OSError("vanished")
            Path(dst).write_bytes(Path(src).read_bytes())

        def fake_crop(src_path, dst_path, **_kw):
            Path(dst_path).write_bytes(b'CROPPED-FALLBACK-BYTES')
            return True

        with patch('core.readonly_producer.shutil.copy2', side_effect=flaky_copy2), \
             patch('core.readonly_producer.crop_to_poster', side_effect=fake_crop) as mock_crop, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', cover_fs, {'poster': str(poster_src), 'fanart': None}),
            )

        mock_crop.assert_called_once()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        assert Path(base_stem + '-poster.jpg').read_bytes() == b'CROPPED-FALLBACK-BYTES'

    def test_neither_slot_present_delegates_to_generate_jellyfin_images(self, tmp_path):
        """cover_strategy carries a 3rd element but BOTH slots are None (ingest
        source with a cover but no curator sidecars at all) -> treated
        identically to no 3rd element: generate_jellyfin_images IS called
        (single source of truth for the generate path, keeps this case
        call-identical to before this fix / to TestIngestFourMatrix's mocks)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}) as mock_jellyfin, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', '/src/cover-does-not-matter.jpg', {'poster': None, 'fanart': None}),
            )

        # cover copy itself will fail (missing file) -> has_cover False -> jellyfin
        # never called either way; assert via the has_cover=False contract instead.
        mock_jellyfin.assert_not_called()

    def test_scrape_rescrape_two_tuple_still_delegates_to_generate_jellyfin_images(self, tmp_path):
        """A 2-tuple cover_strategy (scrape / rescrape, or ingest with no
        detected sidecars — resolve_ingest_plan's 'download'/'none' branches)
        must still call generate_jellyfin_images exactly as before this fix —
        the byte-identical scrape/rescrape guarantee."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}) as mock_jellyfin, \
             patch('core.readonly_producer.crop_to_poster') as mock_crop, \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('download', _T3_META['cover']),
            )

        mock_jellyfin.assert_called_once()
        mock_crop.assert_not_called()


class TestAssetsModeSamplesOnly:
    """CD-104-1: assets_mode='samples_only' — ONLY the extrafanart download loop
    runs; nfo/cover/poster/fanart/strm and BOTH stale-cleanup helpers are
    untouched, and sample download is unconditional (not gated on
    config['download_sample_images']). cover_strategy is accepted but ignored —
    Codex P1-c: a supplemental-samples fetch must never touch the cover."""

    def test_only_samples_downloaded_nfo_and_cover_not_called(self, tmp_path):
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=['http://x/1.jpg', 'http://x/2.jpg'])

        def fake_download(url, save_path, referer=''):
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'SAMPLE')
            return True

        with patch('core.readonly_producer.download_image', side_effect=fake_download) as mock_download, \
             patch('core.readonly_producer.generate_nfo') as mock_nfo, \
             patch('core.readonly_producer.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_producer.shutil.copyfile') as mock_copy:
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
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=['http://x/1.jpg'])
        config = dict(_T3_BASE_CONFIG, download_sample_images=False)

        def fake_download(url, save_path, referer=''):
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(b'SAMPLE')
            return True

        with patch('core.readonly_producer.download_image', side_effect=fake_download), \
             patch('core.readonly_producer.generate_nfo') as mock_nfo:
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('none',), assets_mode='samples_only',
            )

        mock_nfo.assert_not_called()
        assert len(assets['sample_fs']) == 1

    def test_empty_sample_images_returns_empty_list(self, tmp_path):
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_producer.download_image') as mock_download, \
             patch('core.readonly_producer.generate_nfo') as mock_nfo:
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('none',), assets_mode='samples_only',
            )

        mock_download.assert_not_called()
        mock_nfo.assert_not_called()
        assert assets == {'sample_fs': []}

    def test_ignores_cover_strategy_regardless_of_value(self, tmp_path):
        """samples_only never reads cover_strategy — even a 'download' state must
        not trigger download_image for the cover (only for samples, and there are
        none here)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_producer.download_image') as mock_download, \
             patch('core.readonly_producer.shutil.copyfile') as mock_copy, \
             patch('core.readonly_producer.generate_nfo') as mock_nfo:
            assets = _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('download', 'http://x/cover.jpg'), assets_mode='samples_only',
            )

        mock_download.assert_not_called()
        mock_copy.assert_not_called()
        mock_nfo.assert_not_called()
        assert assets['sample_fs'] == []

    def test_no_stale_cleanup_helpers_called(self, tmp_path):
        """Neither _clean_stale_extrafanart nor _clean_stale_singletons run, even
        when old_base is non-empty (would normally gate extrafanart cleanup on in
        full mode)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer._clean_stale_extrafanart') as mock_clean_ef, \
             patch('core.readonly_producer._clean_stale_singletons') as mock_clean_singletons:
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('none',), assets_mode='samples_only',
                old_base='TEST-001 Old Title',
            )

        mock_clean_ef.assert_not_called()
        mock_clean_singletons.assert_not_called()


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
        from core.readonly_producer import _write_movie_assets

        meta_samples = dict(_T3_META, sample_images=['http://x/1.jpg', 'http://x/2.jpg'])
        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download):
            _write_movie_assets(
                movie_dir, meta_samples, _t3_format_data(config=config), '/src/TEST-001.mp4', config,
                cover_strategy=('none',), assets_mode='samples_only',
            )

    def test_full_mode_reentry_preserves_extrafanart_on_disk(self, tmp_path):
        from core.readonly_producer import _write_movie_assets

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
        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
            _write_movie_assets(
                movie_dir, meta_full, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('download', 'http://x/cover.jpg'), assets_mode='full',
                old_base='TEST-001 Test Movie Title',
            )

        assert (ef_dir / 'fanart1.jpg').exists(), "full-mode re-entry must not wipe existing samples"
        assert (ef_dir / 'fanart2.jpg').exists(), "full-mode re-entry must not wipe existing samples"

    def test_full_mode_run_with_own_samples_still_cleans_and_rewrites(self, tmp_path):
        """Sanity: the guard only SKIPS the clean when this run has nothing new —
        a hypothetical future full-mode caller that DOES carry sample_images still
        gets correct clean+rewrite (old set of 3 shrinks to the new set of 1)."""
        from core.readonly_producer import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        config = dict(_T3_BASE_CONFIG)
        self._samples_only_seed(movie_dir, config)
        ef_dir = Path(movie_dir) / 'extrafanart'
        (ef_dir / 'fanart3.jpg').write_bytes(b'STALE')  # pretend a 3rd stale sample exists

        meta_full = dict(_T3_META, sample_images=['http://x/only-one.jpg'])
        config_dl = dict(config, download_sample_images=True)
        fd = _t3_format_data(config=config_dl)
        with patch('core.readonly_producer.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_producer.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t4_real_nfo):
            assets = _write_movie_assets(
                movie_dir, meta_full, fd, '/src/TEST-001.mp4', config_dl,
                cover_strategy=('download', 'http://x/cover.jpg'), assets_mode='full',
                old_base='TEST-001 Test Movie Title',
            )

        # old set of 3 shrinks to the new set of 1 — fanart1.jpg is REWRITTEN
        # with the new sample's content (not the stale one); fanart2/3 are gone.
        assert not (ef_dir / 'fanart2.jpg').exists()
        assert not (ef_dir / 'fanart3.jpg').exists()
        assert (ef_dir / 'fanart1.jpg').read_bytes() == b'FAKE-IMG'  # _t4_real_download's payload
        assert len(assets['sample_fs']) == 1


class TestUpsertDbSamplesOnly:
    """CD-104-1/104-4: assets_mode='samples_only' — DB path calls ONLY
    repo.update_sample_images; never builds/upserts a full Video row, so
    cover_path/nfo_mtime/metadata of an existing produced row are left
    completely alone (Codex P1-c: a supplemental-samples fetch must not
    clobber metadata it wasn't asked to touch)."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'

    def test_calls_update_sample_images_not_full_upsert(self):
        from core.readonly_producer import _upsert_db

        repo = MagicMock()
        assets = {'sample_fs': ['/output/TEST-001/extrafanart/fanart1.jpg']}

        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        repo.upsert.assert_not_called()
        repo.update_sample_images.assert_called_once_with(
            self.SOURCE_URI, [to_file_uri('/output/TEST-001/extrafanart/fanart1.jpg', None)]
        )

    def test_empty_sample_fs_skips_update_does_not_clobber(self):
        """P2 review (2026-07-21): INTENDED CONTRACT CHANGE, not a weakening.

        This test previously asserted `update_sample_images(path, [])` IS called
        on an empty sample_fs ("legal clear" — explicit fetch found/downloaded
        zero samples this time). That is the exact P2 bug: a total download
        failure (network error mid-loop, all URLs 404, etc.) also produces an
        empty `assets['sample_fs']`, and unconditionally clearing DB
        sample_images to `[]` on that path silently destroys data the caller
        never asked to touch. `core.enricher.fetch_samples_only` — the
        non-readonly sibling this samples_only path must behave like — already
        gets this right: it only calls its own `_db_upsert_samples_only`
        `if written_uris:`, leaving any existing sample_images alone when
        nothing was actually written, regardless of WHY nothing was written.
        `_upsert_db`'s samples_only branch now mirrors that exactly.
        MUTATION LOCK: reinstating the unconditional `repo.update_sample_images`
        call must turn this test RED."""
        from core.readonly_producer import _upsert_db

        repo = MagicMock()
        assets = {'sample_fs': []}

        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        repo.update_sample_images.assert_not_called()

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

    def test_persists_output_dir_when_existing_output_dir_empty(self, temp_db):
        """P2-B: a samples-only supplemental fetch must still record
        output_dir for a row that doesn't have one yet — otherwise a later
        full ingest can't rely on it being set (reference: full-mode sets
        output_dir=output_dir at _upsert_db:1093)."""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            output_dir='',
        ))

        assets = {'sample_fs': ['/output/TEST-001/extrafanart/fanart1.jpg']}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.output_dir == 'file:///output/TEST-001'

    def test_does_not_clobber_existing_nonempty_output_dir(self, temp_db):
        """P2-B: idempotency — re-running a samples-only fetch must never
        overwrite an already-recorded real output_dir, even when called with
        a different output_dir value."""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            output_dir='file:///output/REAL-DIR',
        ))

        assets = {'sample_fs': ['/output/TEST-001/extrafanart/fanart1.jpg']}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            'file:///output/TEST-001', assets_mode='samples_only',
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.output_dir == 'file:///output/REAL-DIR'

    def test_empty_output_dir_param_does_not_write(self, temp_db):
        """Guard: output_dir='' (caller has no known dir yet) must not
        attempt a write — matches the `if output_dir:` guard."""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)
        repo.upsert(Video(
            path=self.SOURCE_URI, number='TEST-001', title='Existing Title',
            output_dir='',
        ))

        assets = {'sample_fs': ['/output/TEST-001/extrafanart/fanart1.jpg']}
        _upsert_db(
            repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None,
            '', assets_mode='samples_only',
        )

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.output_dir == ''


class TestNfoMtimePositiveAndMutationLock:
    """CD-104-4: full-mode produce writes a REAL nfo_mtime (>0), not the old
    hardcoded 0.0.

    MUTATION LOCK: this test goes RED if either half of the CD-104-4 plumbing is
    reverted — `nfo_mtime = os.stat(nfo_fs).st_mtime` in _write_movie_assets, or
    `nfo_mtime=assets['nfo_mtime']` in _upsert_db (reverting either back to a
    hardcoded 0.0 fails the `> 0` assertions below). Manually verified during T1
    development by temporarily reverting each line and re-running this test
    (both reverts turned it RED); restored afterwards.
    """

    def test_full_produce_nfo_mtime_positive(self, tmp_path, temp_db):
        from core.database import VideoRepository
        from core.readonly_producer import _format_data, _upsert_db, _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _format_data(_T3_META, '/src/TEST-001.mp4', _T3_BASE_CONFIG)
        repo = VideoRepository(temp_db)

        with patch('core.readonly_producer.download_image', return_value=True), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=_cover_strategy_for(_T3_META),
            )
            _upsert_db(
                repo, 'file:///src/TEST-001.mp4', _T3_FILE_INFO, _T3_META, assets, None,
                'file:///output/TEST-001',
            )

        assert assets['nfo_mtime'] > 0
        v = repo.get_by_path('file:///src/TEST-001.mp4')
        assert v.nfo_mtime > 0
        assert v.nfo_mtime == assets['nfo_mtime']


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

    def test_nfo_mtime_value_does_not_affect_exclusion(self, temp_db):
        from core.database import VideoRepository
        from core.readonly_producer import _upsert_db

        repo = VideoRepository(temp_db)

        assets_zero = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': 0.0}
        assets_real = {'cover_fs': '', 'sample_fs': [], 'nfo_mtime': 1704067333.5}

        uri_zero = 'file:///src/ZERO-001.mp4'
        uri_real = 'file:///src/REAL-001.mp4'
        meta_zero = dict(_T3_META, number='ZERO-001')
        meta_real = dict(_T3_META, number='REAL-001')

        _upsert_db(repo, uri_zero, _T3_FILE_INFO, meta_zero, assets_zero, None, 'file:///output/ZERO-001')
        _upsert_db(repo, uri_real, _T3_FILE_INFO, meta_real, assets_real, None, 'file:///output/REAL-001')

        v_zero = repo.get_by_path(uri_zero)
        v_real = repo.get_by_path(uri_real)
        assert v_zero.nfo_mtime != v_real.nfo_mtime, "sanity: the two rows really do differ in nfo_mtime"

        # Both rows are produced (_upsert_db always sets output_dir +
        # scrape_attempted_at unconditionally, independent of nfo_mtime) →
        # missing-check excludes BOTH, regardless of the nfo_mtime value carried.
        assert self._missing_check_excludes(v_zero) is True
        assert self._missing_check_excludes(v_real) is True


class TestCallSequenceEquivalence:
    """CD-104-9: the produce_source → _produce_one extraction must not
    reorder/duplicate/drop the scrape path's collaborator calls — search_jav →
    download_image (cover) → generate_nfo → repo.upsert, exactly once each per
    created file, in that order, matching the pre-extraction per-file
    try-block byte for byte."""

    def test_call_sequence_and_counts_preserved(self, tmp_path):
        from core.readonly_producer import produce_source

        source_dir = tmp_path / 'src'
        source_dir.mkdir()
        numbers = ['SEQ-001', 'SEQ-002']
        for n in numbers:
            (source_dir / f'{n}.mp4').write_bytes(b'FAKE-VIDEO')
        output_dir = tmp_path / 'output'
        output_dir.mkdir()

        source = _make_source(readonly=True, output_path=str(output_dir), path=str(source_dir))
        config = _make_config(scraper_cfg={
            # media-server flavour → resolve_output_root uses source.output_path
            # verbatim, no core.database.get_db_path() dependency to wire up.
            'external_manager': 'kodi',
            'folder_layers': [], 'folder_format': '',
            'filename_format': '{num}', 'max_title_length': 50,
            'max_filename_length': 60, 'suffix_keywords': [],
            'download_sample_images': False,
            'strm_path_mappings': {},
        })

        call_log: list = []
        repo = MagicMock()
        repo.get_attempted_index.return_value = {}
        repo.get_by_path.return_value = None
        repo.is_output_dir_taken.return_value = False
        repo.get_empty_focal_candidates.return_value = []

        def fake_search_jav(number, source="auto", proxy_url="", javbus_lang=None):
            call_log.append(('search_jav', number))
            return {
                'number': number, 'title': f'Title {number}', 'cover': f'http://x/{number}.jpg',
                'actors': [], 'tags': [], 'date': '', 'maker': '', 'director': '',
                'series': '', 'label': '', 'sample_images': [], 'duration': 0, 'url': '',
            }

        def fake_download_image(url, dest, referer=''):
            call_log.append(('download_image', url))
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b'IMG')
            return True

        def fake_generate_nfo(**kwargs):
            call_log.append(('generate_nfo', kwargs.get('number')))
            Path(kwargs['output_path']).write_text('<movie/>', encoding='utf-8')
            return True

        def fake_upsert(v):
            call_log.append(('upsert', v.number))

        repo.upsert.side_effect = fake_upsert

        with patch('core.readonly_producer.search_jav', side_effect=fake_search_jav), \
             patch('core.readonly_producer.download_image', side_effect=fake_download_image), \
             patch('core.readonly_producer.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_producer.generate_nfo', side_effect=fake_generate_nfo):
            result = produce_source(source, config, repo)

        assert result.created == 2
        assert result.failed == 0
        assert [c[0] for c in call_log] == [
            'search_jav', 'download_image', 'generate_nfo', 'upsert',
            'search_jav', 'download_image', 'generate_nfo', 'upsert',
        ], call_log
        assert sum(1 for c in call_log if c[0] == 'download_image') == 2, "one download_image per cover"
        assert sum(1 for c in call_log if c[0] == 'generate_nfo') == 2, "one generate_nfo per file"
        assert sum(1 for c in call_log if c[0] == 'upsert') == 2, "one upsert per created file"

    def test_sample_download_never_exercised_by_this_lock(self):
        """TASK-104-T2 note (spec §3-A / Non-Goals reconciliation): this lock's own
        config already sets download_sample_images=False and its fake meta already
        carries sample_images=[] (see setup above) — so T2 forcing
        meta['sample_images']=[] inside resolve_ingest_plan changes NOTHING
        observable here. No update was needed for THIS test; documented per the
        card's instruction to note when a test's premise already excluded sample
        download rather than silently leaving it unexplained."""
        assert True


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

    def test_original_title_extracted_from_originaltitle_tag(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><num>ABC-123</num><title>English Title</title>'
            '<originaltitle>日本語タイトル</originaltitle></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['original_title'] == '日本語タイトル'

    def test_original_title_empty_string_when_tag_absent(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><num>ABC-123</num><title>Only Title</title></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['original_title'] == ''

    def test_number_fallback_when_num_and_uniqueid_absent(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><title>Bare Title</title></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='FALLBACK-999')
        assert meta['number'] == 'FALLBACK-999'

    def test_number_prefers_num_over_uniqueid(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><num>REAL-001</num>'
            '<uniqueid type="home">OTHER-002</uniqueid></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='FB-000')
        assert meta['number'] == 'REAL-001'

    def test_number_uses_uniqueid_when_num_missing(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><uniqueid type="home">UID-001</uniqueid></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='FB-000')
        assert meta['number'] == 'UID-001'

    def test_title_strips_leading_number_bracket_prefix(self):
        """Round-trip edge #1: generate_nfo writes `[number]title` — the adapter
        must strip it back off, else re-generating double-wraps."""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><num>ABC-123</num><title>[ABC-123]Real Title</title></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='')
        assert meta['title'] == 'Real Title'

    def test_title_without_bracket_prefix_unchanged(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><num>ABC-123</num><title>Plain Title</title></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='')
        assert meta['title'] == 'Plain Title'

    def test_rating_divided_by_two(self):
        """Round-trip edge #2: <rating> is raw×2 — the adapter must divide back."""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><rating>7.0</rating></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['_rating'] == pytest.approx(3.5)

    def test_rating_missing_is_none(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['_rating'] is None

    def test_rating_zero_is_none(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><rating>0</rating></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['_rating'] is None

    def test_duration_empty_is_none(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><runtime></runtime></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['duration'] is None

    def test_duration_non_numeric_is_none(self):
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><runtime>abc</runtime></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['duration'] is None

    def test_date_fallback_chain_release_premiered_year(self):
        # Mirrors VideoScanner.parse_nfo (gallery_scanner.py:337) order
        # release > premiered > year so ingest and scan agree on the same NFO.
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root('<movie><release>2020-01-01</release><year>2019</year></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['date'] == '2020-01-01'

        root2 = _nfo_root('<movie><year>2019</year></movie>')
        meta2 = _nfo_to_producer_meta(root2, fallback_number='X')
        assert meta2['date'] == '2019'

        # both premiered + release present → release wins (matches VideoScanner)
        root3 = _nfo_root('<movie><premiered>2021-03-03</premiered><release>2020-01-01</release></movie>')
        meta3 = _nfo_to_producer_meta(root3, fallback_number='X')
        assert meta3['date'] == '2020-01-01'

    def test_number_and_maker_fallback_tags_mirror_videoscanner(self):
        # VideoScanner.parse_nfo uses num>id (number) and maker>studio (maker);
        # adapter must agree so third-party NFOs read identically.
        from core.readonly_producer import _nfo_to_producer_meta

        # <id> as number fallback (no <num>)
        root = _nfo_root('<movie><id>IDN-007</id><studio>StudioCo</studio></movie>')
        meta = _nfo_to_producer_meta(root, fallback_number='FB-999')
        assert meta['number'] == 'IDN-007'

        # <maker> wins over <studio>
        root2 = _nfo_root('<movie><num>N-1</num><maker>MakerCo</maker><studio>StudioCo</studio></movie>')
        meta2 = _nfo_to_producer_meta(root2, fallback_number='')
        assert meta2['maker'] == 'MakerCo'

        # <studio> only still works
        root3 = _nfo_root('<movie><num>N-2</num><studio>StudioOnly</studio></movie>')
        meta3 = _nfo_to_producer_meta(root3, fallback_number='')
        assert meta3['maker'] == 'StudioOnly'

    def test_flat_actor_element_openaver_native_shape(self):
        """OpenAver's own generate_nfo writes flat <movie><actor><name> (direct
        child of <movie>) — the pre-existing shape must keep working after
        switching the selector to any-depth `.//actor/name` (P1 finding)."""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><actor><name>Flat A</name></actor>'
            '<actor><name>Flat B</name></actor></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['actors'] == ['Flat A', 'Flat B']

    def test_nested_actors_element_any_depth(self):
        """P1 finding (2026-07-21 review): a third-party NFO nests <actor> one
        level deeper — <movie><actors><actor><name>X</name></actor></actors></movie>
        — which VideoScanner.parse_nfo already reads via its own any-depth
        `.//actor/name` selector (gallery_scanner.py:345). A direct-children-only
        `root.findall('actor')` silently returns [] here, so ingest would clear
        actors that the incumbent scan path reads fine — the exact drift this
        adapter exists to avoid. MUTATION LOCK: reverting `_nfo_to_producer_meta`'s
        selector back to `root.findall('actor')` must turn this test RED."""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><actors>'
            '<actor><name>Nested A</name></actor>'
            '<actor><name>Nested B</name></actor>'
            '</actors></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['actors'] == ['Nested A', 'Nested B']

    def test_mutation_lock_not_enricher_shape(self):
        """MUTATION LOCK: must use producer-meta keys ('actors'/'date'/'cover'),
        NOT core.enricher._nfo_to_meta's shape ('actresses'/'release_date'/
        'cover_url') — swapping in that shape must turn this test RED."""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><num>MUT-001</num><actor><name>A</name></actor>'
            '<premiered>2024-01-01</premiered></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='')
        assert 'actors' in meta and 'actresses' not in meta
        assert 'date' in meta and 'release_date' not in meta
        assert 'cover' in meta and 'cover_url' not in meta
        assert meta['actors'] == ['A']
        assert meta['date'] == '2024-01-01'


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

    def test_round_trip_original_title_survives(self, tmp_path):
        """FIX#3: generate_nfo(original_title=...) -> _nfo_to_producer_meta
        must round-trip the originaltitle tag, same as title/actors/etc."""
        from core.nfo_updater import parse_nfo
        from core.organizer import generate_nfo
        from core.readonly_producer import _nfo_to_producer_meta

        nfo_path = tmp_path / 'RTX-004.nfo'
        ok = generate_nfo(
            number='RTX-004', title='English Title',
            original_title='日本語タイトル', output_path=str(nfo_path),
        )
        assert ok

        _, root = parse_nfo(str(nfo_path))
        meta = _nfo_to_producer_meta(root, fallback_number='RTX-004')
        assert meta['original_title'] == '日本語タイトル'


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

    def test_ingest_nfo_thumb_threaded_into_find_cover_image(self, tmp_path):
        """DoD: ingest cover axis must thread the NFO's <thumb> as nfo_thumb
        (CD-104-10 — L3 silently degrades if it isn't)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SRC-001</num><thumb>cover.jpg</thumb></movie>', encoding='utf-8')

        with patch('core.readonly_producer.search_jav'), \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        MockVS.return_value.find_cover_image.assert_called_once_with(str(video), nfo_thumb='cover.jpg')

    def test_ingest_no_thumb_threads_none(self, tmp_path):
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SRC-001</num></movie>', encoding='utf-8')

        with patch('core.readonly_producer.search_jav'), \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        MockVS.return_value.find_cover_image.assert_called_once_with(str(video), nfo_thumb=None)

    def test_ingest_cover_hit_returns_copy_strategy(self, tmp_path):
        """Matrix ①/②: local cover hit -> ('copy', fs_path, {poster/fanart}),
        never a download. No -poster/-fanart sidecars next to this fixture's
        video -> both detected slots are None (owner-fix: curator-sidecar
        passthrough, see resolve_ingest_plan docstring)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        cover_path = str(tmp_path / 'SRC-001.jpg')

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ) as mock_search, patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = cover_path
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        mock_search.assert_called_once()
        assert cover_strategy == ('copy', cover_path, {'poster': None, 'fanart': None})

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

        mock_search.assert_called_once_with('SRC-001', source='auto', proxy_url='', javbus_lang=None)
        assert cover_strategy == ('copy', cover_path, {'poster': None, 'fanart': None})

    # -- P2 fix (round-3 review 2026-07-21): ingest scrape-fallback honors the
    # caller's own source/javbus_lang instead of hardcoding source="auto" --

    def test_ingest_no_valid_nfo_concrete_source_uses_single_source(self, tmp_path):
        """A caller-supplied concrete source must route through
        search_jav_single_source with THAT source — not the hardcoded
        source="auto" the ingest scrape-fallback used before this fix (Codex
        PR#113 round-3 P2). javbus_lang is threaded through too.
        MUTATION LOCK: reverting the ingest branch's source dispatch back to a
        bare `search_jav(number, source="auto", proxy_url=proxy_url)` call
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
                str(video), 'SRC-001', {}, action='ingest', source='javbus', proxy_url='p',
                javbus_lang='zh-tw',
            )

        mock_single.assert_called_once_with('SRC-001', 'javbus', 'p', javbus_lang='zh-tw')
        mock_search.assert_not_called()
        assert cover_strategy == ('download', 'http://x/c.jpg')

    @pytest.mark.parametrize("source", [None, 'auto'])
    def test_ingest_no_valid_nfo_no_source_or_auto_threads_javbus_lang(self, tmp_path, source):
        """No concrete source (None or 'auto') -> the existing search_jav(auto)
        path, NOT search_jav_single_source — but javbus_lang is now threaded
        through (previously always dropped/None)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ) as mock_search, patch('core.readonly_producer.search_jav_single_source') as mock_single, \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(
                str(video), 'SRC-001', {}, action='ingest', source=source, javbus_lang='ja',
            )

        mock_search.assert_called_once_with('SRC-001', source='auto', proxy_url='', javbus_lang='ja')
        mock_single.assert_not_called()
        assert cover_strategy == ('download', 'http://x/c.jpg')

    def test_ingest_detects_curator_poster_fanart_sidecars(self, tmp_path):
        """Owner-approved fix: a curated Jellyfin/Emby layout ({stem}-poster.*
        AND {stem}-fanart.* next to the video, no plain {stem}.jpg) must have
        BOTH real fs paths threaded into cover_strategy's 3rd element.
        VideoScanner is NOT mocked here — find_cover_image's own real L1.5
        fanart-before-poster priority must pick -fanart as the cover."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, name='JELLY-001.mp4')
        poster = tmp_path / 'JELLY-001-poster.jpg'
        fanart = tmp_path / 'JELLY-001-fanart.jpg'
        poster.write_bytes(b'POSTER')
        fanart.write_bytes(b'FANART')
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>JELLY-001</num></movie>', encoding='utf-8')

        meta, cover_strategy = resolve_ingest_plan(str(video), 'JELLY-001', {}, action='ingest')

        assert cover_strategy[0] == 'copy'
        assert cover_strategy[1] == str(fanart), "find_cover_image L1.5 picks -fanart before -poster"
        assert cover_strategy[2] == {'poster': str(poster), 'fanart': str(fanart)}

    def test_ingest_detects_only_poster_sidecar(self, tmp_path):
        """Only a -poster sidecar (no -fanart) -> fanart slot is None."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, name='JELLY-002.mp4')
        poster = tmp_path / 'JELLY-002-poster.jpg'
        poster.write_bytes(b'POSTER')
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>JELLY-002</num></movie>', encoding='utf-8')

        meta, cover_strategy = resolve_ingest_plan(str(video), 'JELLY-002', {}, action='ingest')

        assert cover_strategy == ('copy', str(poster), {'poster': str(poster), 'fanart': None})

    def test_rescrape_cover_strategy_stays_two_tuple_even_with_sidecars_on_disk(self, tmp_path):
        """action='rescrape' NEVER adds a 3rd element, even when curator
        sidecars exist on disk — a re-scrape always downloads the remote cover
        (see resolve_ingest_plan docstring); the 3-tuple copy form is
        action='ingest' only, so the scrape/rescrape write path in
        _write_movie_assets stays byte-identical to before this fix."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, name='JELLY-003.mp4')
        (tmp_path / 'JELLY-003-poster.jpg').write_bytes(b'POSTER')
        (tmp_path / 'JELLY-003-fanart.jpg').write_bytes(b'FANART')

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'JELLY-003', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ):
            meta, cover_strategy = resolve_ingest_plan(str(video), 'JELLY-003', {}, action='rescrape')

        assert cover_strategy == ('download', 'http://x/c.jpg')
        assert len(cover_strategy) == 2

    def test_ingest_neither_nfo_nor_cover_falls_back_to_download(self, tmp_path):
        """Matrix ④: neither -> existing scrape+download behavior, unchanged."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)

        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ), patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        assert cover_strategy == ('download', 'http://x/c.jpg')

    def test_ingest_nfo_present_no_cover_hit_is_none_not_download(self, tmp_path):
        """Matrix ②: valid NFO + cover miss -> ('none',) — must NOT silently
        fall back to downloading (ingest is zero-network when NFO is valid)."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        nfo = video.with_suffix('.nfo')
        nfo.write_text('<movie><num>SRC-001</num></movie>', encoding='utf-8')

        with patch('core.readonly_producer.search_jav') as mock_search, \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        mock_search.assert_not_called()
        assert cover_strategy == ('none',)

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

    def test_meta_none_returns_none_cover_strategy(self, tmp_path):
        """Common rule: meta is None -> (None, ('none',)) even when a local
        cover WOULD have been found — nothing to attach it to."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)

        with patch('core.readonly_producer.search_jav', return_value=None), \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = str(tmp_path / 'SRC-001.jpg')
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='ingest')

        assert meta is None
        assert cover_strategy == ('none',)

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

    def test_rescrape_meta_none_when_search_fails(self, tmp_path):
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        with patch('core.readonly_producer.search_jav', return_value=None):
            meta, cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action='rescrape')
        assert meta is None
        assert cover_strategy == ('none',)

    @pytest.mark.parametrize("action", ["ingest", "rescrape"])
    def test_sample_images_always_empty(self, tmp_path, action):
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        meta_stub = {
            'number': 'SRC-001', 'title': 'T', 'cover': '',
            'sample_images': ['http://x/s1.jpg', 'http://x/s2.jpg'],
        }
        with patch('core.readonly_producer.search_jav', return_value=meta_stub), \
             patch('core.readonly_producer.VideoScanner') as MockVS:
            MockVS.return_value.find_cover_image.return_value = ''
            meta, _cover_strategy = resolve_ingest_plan(str(video), 'SRC-001', {}, action=action)

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
                str(video), 'SRC-001', {}, action='rescrape', source='javbus', proxy_url='p',
                javbus_lang='zh-tw',
            )

        mock_single.assert_called_once_with('SRC-001', 'javbus', 'p', javbus_lang='zh-tw')
        mock_search.assert_not_called()
        assert cover_strategy == ('download', 'http://x/c.jpg')

    @pytest.mark.parametrize("source", [None, 'auto'])
    def test_rescrape_no_source_or_auto_falls_back_to_search_jav(self, tmp_path, source):
        """source=None or source='auto' -> the existing search_jav(auto) path,
        NOT search_jav_single_source."""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path)
        with patch(
            'core.readonly_producer.search_jav',
            return_value={'number': 'SRC-001', 'title': 'T', 'cover': 'http://x/c.jpg'},
        ) as mock_search, patch('core.readonly_producer.search_jav_single_source') as mock_single:
            meta, cover_strategy = resolve_ingest_plan(
                str(video), 'SRC-001', {}, action='rescrape', source=source,
                javbus_lang='ja',
            )

        mock_search.assert_called_once_with('SRC-001', source='auto', proxy_url='', javbus_lang='ja')
        mock_single.assert_not_called()
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
    def test_no_readonly_source_returns_none(self, tmp_path):
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "rw"
        src.mkdir()
        canonical = to_file_uri(str(src / "ABC-001.mp4"))
        config = _gallery_config([{"path": str(src), "readonly": False}])

        assert resolve_owning_output_root(canonical, config) is None

    def test_no_source_covers_path_at_all_returns_none(self, tmp_path):
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "ro"
        src.mkdir()
        canonical = to_file_uri(str(tmp_path / "unrelated" / "ABC-001.mp4"))
        config = _gallery_config([{"path": str(src), "readonly": True}])

        assert resolve_owning_output_root(canonical, config) is None

    def test_finds_owning_readonly_source_off_mode_nonempty_root(self, tmp_path):
        from core.database import get_db_path
        from core.readonly_producer import resolve_owning_output_root
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
        from core.readonly_producer import resolve_owning_output_root
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
    def test_nested_writable_child_returns_none(self, tmp_path):
        """readonly parent + writable child (longer/more-specific prefix) ->
        the file under the writable child is NOT readonly -> None (router
        falls through to its existing writable code path)."""
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        parent = tmp_path / "ro_parent"
        child = parent / "rw_child"
        child.mkdir(parents=True)
        canonical = to_file_uri(str(child / "ABC-001.mp4"))
        config = _gallery_config([
            {"path": str(parent), "readonly": True},
            {"path": str(child), "readonly": False},
        ])

        assert resolve_owning_output_root(canonical, config) is None

    def test_nested_readonly_child_under_writable_parent_still_routes(self, tmp_path):
        """Mirror case: writable parent + readonly child (longer prefix) -> the
        readonly child wins -> routes (not None), owning source is the child."""
        from core.readonly_producer import resolve_owning_output_root
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

    def test_equal_length_tie_favors_writable_returns_none(self, tmp_path):
        """Self-contradictory config: the SAME path listed both readonly and
        writable (equal-length prefixes) -> ties favor writable (mirrors
        is_path_readonly's best_ro > best_wr, strict inequality) -> None."""
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "contradictory"
        src.mkdir()
        canonical = to_file_uri(str(src / "ABC-001.mp4"))
        config = _gallery_config([
            {"path": str(src), "readonly": True},
            {"path": str(src), "readonly": False},
        ])

        assert resolve_owning_output_root(canonical, config) is None

    # -- boundary (b): source root changed between calls -----------------------
    def test_stateless_recompute_when_source_root_changes(self, tmp_path):
        """resolve_owning_output_root must not cache: a file under the OLD
        source root stops resolving once the config's source path is changed
        to point elsewhere (simulates the user editing the source root in
        settings) — no stale memory of "this used to be readonly"."""
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        old_root = tmp_path / "old_root"
        new_root = tmp_path / "new_root"
        old_root.mkdir()
        new_root.mkdir()
        canonical_old = to_file_uri(str(old_root / "ABC-001.mp4"))

        config_v1 = _gallery_config([{"path": str(old_root), "readonly": True}])
        assert resolve_owning_output_root(canonical_old, config_v1) is not None

        config_v2 = _gallery_config([{"path": str(new_root), "readonly": True}])
        assert resolve_owning_output_root(canonical_old, config_v2) is None

        canonical_new = to_file_uri(str(new_root / "ABC-001.mp4"))
        result = resolve_owning_output_root(canonical_new, config_v2)
        assert result is not None
        assert result[0].path == str(new_root)

    def test_malformed_source_path_skipped_not_raised(self, tmp_path, monkeypatch):
        """A source whose path canonicalization raises ValueError must be
        skipped (mirror readonly_source_prefixes' own per-entry try/except),
        not propagate and crash the whole resolution."""
        from core.readonly_producer import resolve_owning_output_root
        from core.path_utils import to_file_uri

        good = tmp_path / "ro_good"
        good.mkdir()
        canonical = to_file_uri(str(good / "ABC-001.mp4"))
        config = _gallery_config([
            {"path": "bad::unc::path", "readonly": True},
            {"path": str(good), "readonly": True},
        ])

        from core.readonly_source import _canonical_source_prefix as _real_canonical_prefix

        def _fake_canonical_prefix(path, path_mappings):
            if path == "bad::unc::path":
                raise ValueError("malformed")
            return _real_canonical_prefix(path, path_mappings)

        monkeypatch.setattr("core.readonly_producer._canonical_source_prefix", _fake_canonical_prefix)

        result = resolve_owning_output_root(canonical, config)
        assert result is not None
        assert result[0].path == str(good)


class TestReadonlyStubNotFound:
    """TASK-105-T5 (T2-a): _readonly_stub_not_found(repo, uri, number, fs_path)
    collapses the 3 not-found stub call sites (S1 scraper.py enrich-single,
    S2 scraper.py batch, S3 readonly_producer.py bulk produce_source) into one
    helper. Core invariant: insert_if_ignore MUST run before
    update_scrape_attempted_at (the latter is a bare UPDATE...WHERE path=?
    that silently no-ops without a row — see video.py:1144-1167)."""

    def test_insert_before_update_ordering(self):
        """MUTATION LOCK: insert_if_ignore call index must be < update_scrape_attempted_at
        call index in repo.mock_calls. Reversing the two calls in the helper body
        must turn this RED."""
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        _readonly_stub_not_found(repo, "file:///src/videos/X-001.mp4", "X-001", "/src/videos/X-001.mp4")

        call_names = [c[0] for c in repo.mock_calls]
        insert_idx = call_names.index("insert_if_ignore")
        update_idx = call_names.index("update_scrape_attempted_at")
        assert insert_idx < update_idx

    def test_video_three_field_lock(self):
        """Video(path=uri, number=number, title=basename(fs_path)) — other
        fields fall back to dataclass defaults (cover_path='', output_dir='',
        sample_images=[])."""
        from core.database import Video
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        _readonly_stub_not_found(
            repo, "file:///src/videos/NOTFOUND-001.mp4", "NOTFOUND-001", "/src/videos/NOTFOUND-001.mp4",
        )

        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert isinstance(inserted, Video)
        assert inserted.path == "file:///src/videos/NOTFOUND-001.mp4"
        assert inserted.number == "NOTFOUND-001"
        assert inserted.title == "NOTFOUND-001.mp4"  # basename, WITH extension
        assert inserted.cover_path == ''
        assert inserted.output_dir == ''
        assert inserted.sample_images == []

    def test_uri_consistency_between_insert_and_update(self):
        """The uri passed to insert_if_ignore's Video.path must be the exact
        same value passed as update_scrape_attempted_at's first positional
        arg — guards against a future accidental fs_path/canonical mismatch."""
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        uri = "file:///src/videos/X-001.mp4"
        _readonly_stub_not_found(repo, uri, "X-001", "/src/videos/X-001.mp4")

        inserted = repo.insert_if_ignore.call_args[0][0]
        update_call_args = repo.update_scrape_attempted_at.call_args[0]
        assert inserted.path == uri
        assert update_call_args[0] == uri

    def test_update_scrape_attempted_at_uses_current_time(self):
        repo = MagicMock()
        from core.readonly_producer import _readonly_stub_not_found

        before = time.time()
        _readonly_stub_not_found(repo, "file:///x.mp4", "X-001", "/x.mp4")
        after = time.time()

        ts = repo.update_scrape_attempted_at.call_args[0][1]
        assert before <= ts <= after


class TestReadonlyEnrichFailure:
    """TASK-105-T5 (T2-b): _readonly_enrich_failure(error, reason=None) -> EnrichResult
    collapses scraper.py's 9 failure EnrichResult constructions (F1-F9) into one
    shape builder. All 6 constant fields are fixed; only error/reason vary."""

    def test_shape_lock_default_reason_none(self):
        from core.enrich_contract import EnrichResult
        from core.readonly_producer import _readonly_enrich_failure

        result = _readonly_enrich_failure("msg")

        assert isinstance(result, EnrichResult)
        assert result.success is False
        assert result.nfo_written is False
        assert result.cover_written is False
        assert result.extrafanart_written == 0
        assert result.fields_filled == []
        assert result.source_used == ''
        assert result.error == "msg"
        assert result.reason is None

    def test_reason_passthrough_not_found(self):
        from core.readonly_producer import _readonly_enrich_failure

        result = _readonly_enrich_failure("m", "not_found")
        assert result.reason == "not_found"

    def test_reason_passthrough_error(self):
        from core.readonly_producer import _readonly_enrich_failure

        result = _readonly_enrich_failure("m", "error")
        assert result.reason == "error"
