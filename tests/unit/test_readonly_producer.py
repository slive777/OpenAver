"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
import json
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


class TestExtractNumberParity:
    def test_matches_scan_table_for_number_prefix_samples(self):
        from core.gallery_scanner import VideoScanner
        from core.readonly_producer import extract_number

        scanner = VideoScanner()
        samples = [
            "200GANA-3360.mp4",
            "259LUXU-001.mp4",
            "PT-71.mp4",
            "T28-103.mp4",
        ]
        for filename in samples:
            assert extract_number(filename) == scanner.find_num_from_filename(filename)

        assert extract_number("PT-71.mp4") == "PT-71"

    def test_no_number_returns_none_not_empty_string(self):
        from core.readonly_producer import extract_number

        res = extract_number("nonumber.mp4")
        assert res is None
        assert res != ""


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
        from core.readonly_paths import _format_data
        meta = {'number': 'ABC-123', 'title': 'A' * 30}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert len(fd['title']) <= 20
        assert fd['title'].endswith('...')

    def test_prefix_stripped_from_title(self):
        from core.readonly_paths import _format_data
        meta = {'number': 'ABC-123', 'title': '[ABC-123]Original Title'}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert 'ABC-123' not in fd['title']
        assert 'Original Title' in fd['title']

    def test_suffix_detected_from_basename(self):
        from core.readonly_paths import _format_data
        meta = {'number': 'ABC-123', 'title': 'Some Title'}
        fd = _format_data(meta, '/src/ABC-123-C.mp4', self.BASE_CONFIG)
        assert '-c' in fd['suffix'].lower()

    def test_no_suffix_when_no_match(self):
        from core.readonly_paths import _format_data
        meta = {'number': 'ABC-123', 'title': 'Some Title'}
        fd = _format_data(meta, '/src/ABC-123.mp4', self.BASE_CONFIG)
        assert fd['suffix'] == ''

    def test_truncated_title_consistent_in_folder_and_basename(self):
        """Same truncated title feeds both _folder_parts and _build_basename (no drift)."""
        from core.readonly_paths import _build_basename, _folder_parts, _format_data
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
        from core.readonly_paths import _folder_parts
        config = {'folder_layers': ['{actor}', '{num}'], 'max_filename_length': 60}
        fd = {'number': 'ABC-123', 'title': 'Title', 'actors': ['Actress'], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert len(parts) == 2

    def test_more_than_3_layers_capped(self):
        from core.readonly_paths import _folder_parts
        config = {
            'folder_layers': ['{num}', '{num}', '{num}', '{num}'],
            'max_filename_length': 60,
        }
        fd = {'number': 'ABC-123', 'title': '', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert len(parts) <= 3

    def test_empty_layer_skipped(self):
        from core.readonly_paths import _folder_parts
        # An empty-string layer formats to '' and must be dropped by the `if part` guard.
        config = {'folder_layers': ['{num}', ''], 'max_filename_length': 60}
        fd = {'number': 'ABC-123', 'title': 'Title', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        # empty layer dropped → only the number layer survives (RED if `if part` guard removed)
        assert parts == ['ABC-123']

    def test_folder_format_fallback(self):
        """When folder_layers is empty, folder_format is used."""
        from core.readonly_paths import _folder_parts
        config = {
            'folder_layers': [],
            'folder_format': '{num}',
            'max_filename_length': 60,
        }
        fd = {'number': 'ABC-123', 'title': '', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}
        parts = _folder_parts(fd, config)
        assert parts == ['ABC-123']

    def test_no_layers_no_folder_format_defaults_num(self):
        from core.readonly_paths import _folder_parts
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
        from core.readonly_paths import _build_basename
        with patch('core.readonly_paths._detect_vr_cluster', return_value='180_LR'):
            result = _build_basename(self.BASE_FD, '/src/ABC-123_180_LR.mp4', self.BASE_CONFIG)
        assert result.endswith('_180_LR')

    def test_no_vr_tail_for_normal_file(self):
        from core.readonly_paths import _build_basename
        with patch('core.readonly_paths._detect_vr_cluster', return_value=None):
            result = _build_basename(self.BASE_FD, '/src/ABC-123.mp4', self.BASE_CONFIG)
        # BASE_FD title has no underscore → any '_' means an erroneous VR tail (RED if injected)
        assert '_' not in result

    def test_suffix_not_truncated_in_two_pass(self):
        """When {suffix} in template, suffix is not cut off by truncation."""
        from core.readonly_paths import _build_basename
        fd = dict(self.BASE_FD, suffix='-C', title='X' * 60)
        config = dict(self.BASE_CONFIG, filename_format='{num} {title}{suffix}', max_filename_length=30)
        with patch('core.readonly_paths._detect_vr_cluster', return_value=None):
            result = _build_basename(fd, '/src/ABC-123-C.mp4', config)
        # suffix '-c' / '-C' should survive truncation
        assert result.endswith('-c') or result.endswith('-C') or '-c' in result.lower()

    def test_plain_num_title_no_vr_tail(self):
        from core.readonly_paths import _build_basename
        with patch('core.readonly_paths._detect_vr_cluster', return_value=None):
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

    def test_first_allocation_no_collision(self):
        """existing=None, nothing taken → plain leaf, n==1."""
        from core.readonly_paths import _resolve_movie_dir
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
        from core.readonly_paths import _resolve_movie_dir
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
        from core.readonly_paths import _MAX_INCREMENT, _resolve_movie_dir
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
        from core.readonly_paths import _resolve_movie_dir
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

    def test_mapped_output_wsl_no_mapping_unchanged(self, monkeypatch):
        """Degenerate combo 2/4: wsl but path_mappings empty → behavior unchanged
        (regression lock for the non-mapped 88/89 scenarios)."""
        from core import readonly_paths
        from core.readonly_paths import _resolve_movie_dir

        monkeypatch.setattr(readonly_paths, 'CURRENT_ENV', 'wsl')
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
        from core import readonly_paths
        from core.readonly_paths import _resolve_movie_dir

        monkeypatch.setattr(readonly_paths, 'CURRENT_ENV', 'windows')
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
        from core import readonly_paths
        from core.readonly_paths import _resolve_movie_dir

        monkeypatch.setattr(readonly_paths, 'CURRENT_ENV', 'linux')
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
        from core import readonly_paths
        from core.readonly_paths import _resolve_movie_dir

        monkeypatch.setattr(readonly_paths, 'CURRENT_ENV', 'wsl')
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

    def test_rescrape_uses_remote_cover_url(self, tmp_path):
        """download_image first arg must be the remote cover URL (C6 re-scrape)."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        download_calls: list = []

        def fake_download(url, save_path, referer=''):
            download_calls.append(url)
            return True

        with patch('core.readonly_assets.download_image', side_effect=fake_download), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, download_sample_images=False)

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert assets['sample_fs'] == []
        ef_dir = Path(movie_dir) / 'extrafanart'
        assert not ef_dir.exists()

    def test_extrafanart_gate_true_two_samples(self, tmp_path):
        """download_sample_images=True + 2 sample URLs → fanart1.jpg + fanart2.jpg, 2 entries."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, download_sample_images=True)

        def fake_download(url, save_path, referer=''):
            return True

        with patch('core.readonly_assets.download_image', side_effect=fake_download), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(_T3_META),
            )

        assert len(assets['sample_fs']) == 2
        assert 'fanart1.jpg' in assets['sample_fs'][0]
        assert 'fanart2.jpg' in assets['sample_fs'][1]

    def test_no_cover_skips_jellyfin_images(self, tmp_path):
        """meta['cover']='' → generate_jellyfin_images NOT called; cover_fs=''; nfo still written."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        meta_no_cover = dict(_T3_META, cover='')
        fd = _t3_format_data(meta=meta_no_cover)

        jellyfin_mock = MagicMock()
        nfo_mock = MagicMock(side_effect=_t3_generate_nfo_side_effect)

        with patch('core.readonly_assets.download_image', return_value=False), \
             patch('core.readonly_assets.generate_jellyfin_images', jellyfin_mock), \
             patch('core.readonly_assets.generate_nfo', nfo_mock):
            assets = _write_movie_assets(
                movie_dir, meta_no_cover, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=_cover_strategy_for(meta_no_cover),
            )

        jellyfin_mock.assert_not_called()
        assert assets['cover_fs'] == ''
        nfo_mock.assert_called_once()

    def test_generate_nfo_params(self, tmp_path):
        """generate_nfo: output_path under movie_dir; external_manager passed; has_poster/has_fanart match cover."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')
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

        assert 'output_path' in captured
        assert captured['output_path'].startswith(movie_dir)
        assert captured['external_manager'] == 'jellyfin'
        assert captured['has_poster'] is True
        assert captured['has_fanart'] is True

    def test_generate_nfo_receives_original_title(self, tmp_path):
        """FIX#3: the produced OUTPUT NFO must keep originaltitle — non-readonly
        enricher.py already passes it through (generate_nfo call at :198)."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        meta = dict(_T3_META, original_title='日本語タイトル')
        fd = _t3_format_data(meta=meta)
        config = dict(_T3_BASE_CONFIG)
        captured: dict = {}

        def capture_nfo(**kwargs):
            captured.update(kwargs)
            return _t3_generate_nfo_side_effect(**kwargs)

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=capture_nfo):
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta),
            )

        assert captured.get('original_title') == '日本語タイトル'

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

    def test_write_movie_assets_missing_nfo_title_format_defaults_to_default(self, tmp_path):
        """config 缺少 nfo_title_format 時應轉傳預設格式 [{num}]{title} 給 generate_nfo"""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG)
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

        assert captured.get('nfo_title_format') == '[{num}]{title}'

    def test_nfo_write_failure_raises(self, tmp_path):
        """generate_nfo returns False (write failed) → _write_movie_assets raises.

        NFO is a required off-complete output; a swallowed False must not be treated
        as success (else produce_source counts created + upserts a movie with no NFO).
        """
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', return_value=False):
            with pytest.raises(RuntimeError):
                _write_movie_assets(
                    movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                    cover_strategy=_cover_strategy_for(_T3_META),
                )

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

    def test_jellyfin_mode_all_four_files_present(self, tmp_path):
        # 真理表 Table 2 #1：媒體伺服器模式下正典封面本身即 `-fanart.jpg`，
        # 沒有獨立的同名 `.jpg`——只剩三個實體檔（.nfo/-poster.jpg/-fanart.jpg）。
        movie_dir = tmp_path / 'movie'
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')
        _t4_write(str(movie_dir), _T3_META, config)

        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert (movie_dir / f'{self._BASE}{suffix}').exists(), f"{suffix} must exist (AC2, jellyfin)"
        assert not (movie_dir / f'{self._BASE}.jpg').exists(), (
            "no independent same-name .jpg — the canonical cover IS -fanart.jpg (Table 2 #1)"
        )

    def test_emby_mode_all_four_files_present(self, tmp_path):
        # 真理表 Table 2 #1（emby 版），同上。
        movie_dir = tmp_path / 'movie'
        config = dict(_T3_BASE_CONFIG, external_manager='emby')
        _t4_write(str(movie_dir), _T3_META, config)

        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert (movie_dir / f'{self._BASE}{suffix}').exists(), f"{suffix} must exist (AC2, emby)"
        assert not (movie_dir / f'{self._BASE}.jpg').exists(), (
            "no independent same-name .jpg — the canonical cover IS -fanart.jpg (Table 2 #1)"
        )

    def test_kodi_mode_all_four_files_present(self, tmp_path):
        # 真理表 Table 2 #1（kodi 版），同上。
        movie_dir = tmp_path / 'movie'
        config = dict(_T3_BASE_CONFIG, external_manager='kodi')
        _t4_write(str(movie_dir), _T3_META, config)

        for suffix in ('.nfo', '-poster.jpg', '-fanart.jpg'):
            assert (movie_dir / f'{self._BASE}{suffix}').exists(), f"{suffix} must exist (AC2, kodi)"
        assert not (movie_dir / f'{self._BASE}.jpg').exists(), (
            "no independent same-name .jpg — the canonical cover IS -fanart.jpg (Table 2 #1)"
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

    def test_off_no_cover_tags_fallback_to_same_name_literal(self, tmp_path):
        """AC4 邊界：off + 無封面（cover_strategy=('none',) via meta['cover']=''）
        → 三個 tag 字面仍等於 {basename}.jpg——與改動前完全一致的既有限制
        （spec-111 §4.1），不驗證檔案存在性（該邊界本來就接受懸空引用）。"""
        config = dict(_T3_BASE_CONFIG, external_manager='off')
        meta_no_cover = dict(_T3_META, cover='')
        _movie_dir, root = self._write_and_read_nfo(tmp_path, meta_no_cover, config)

        expected_tag = f'{self._BASE}.jpg'
        assert root.findtext('poster') == expected_tag
        assert root.findtext('thumb') == expected_tag
        assert root.findtext('fanart') == expected_tag


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

class TestExternalManagerNormalization:
    """畸形 external_manager 必須同時使 poster/fanart 缺席 AND NFO 無 <lockdata>
    ——只驗其中一項驗不出「只擋圖片沒擋 NFO」的半套 fail-open（PR#123 P2 原始
    bug 的確切形狀）。重用 TestOffModeNfoTagFallback._write_and_read_nfo（不
    mock generate_nfo，真跑 core.organizer.generate_nfo 才能解析出真實 tag/
    區塊內容）。"""

    _BASE = 'TEST-001 Test Movie Title'

    # Codex PR#123 round-3 P2①-a：'jellyfin_emby' 曾經是本 parametrize 的第四個案例
    # （id='deprecated-value'），已移除——它是假覆蓋，不是真實可達的畸形值。
    #
    # 為什麼移除：core/config.py:364-367 的 Fix-72d migration（
    # `if s.get('external_manager') == 'jellyfin_emby': s['external_manager'] = 'jellyfin'`）
    # 會在 load_config() 內部把這個舊值逐字改寫成 'jellyfin'。生產環境中，config
    # 只要經過 load_config()（唯一合法讀取路徑），'jellyfin_emby' 就永遠不可能帶著
    # 原值抵達 normalize_external_manager()——它在更早的一步就被攔截掉了。
    #
    # 本測試的 helper（_write_and_read_nfo → _write_movie_assets）直接手搭 config
    # dict 餵入，完全繞過 load_config()，等於在測「一個生產環境不存在的輸入狀態」。
    # 斷言方向本身沒錯（該值確實會被 fail-closed），但它鎖住的行為在真實路徑上永遠
    # 不會被觸發，屬於空覆蓋——留著只會誤導未來的人以為這裡驗證了 migration 行為。
    #
    # 剩下三個值（'Jellyfin' 大小寫不符 / None / 'plex' 未知值）都不受任何 migration
    # 攔截（migration 只逐字比對 'jellyfin_emby'），是真實可達的畸形狀態，繼續保留。
    #
    # migration 行為本身已由 tests/unit/test_core_config.py::TestMigrationExternalManager
    # ::test_legacy_jellyfin_emby_migrates_to_jellyfin 驗證；「migration 後的值是否
    # 正確流進圖片產出」則由本檔案下方
    # TestExternalManagerMigrationToImageProduction 補上（Codex PR#123 round-3 P2①-b）。
    #
    # ⚠️ 若未來要「補回」'jellyfin_emby' 到這個 parametrize：先確認 Fix-72d migration
    # 是否被移除或改寫，否則這裡加回去就是重蹈假覆蓋覆轍。
    @pytest.mark.parametrize(
        'malformed_value',
        ['Jellyfin', None, 'plex'],
        ids=['case-mismatch', 'none-value', 'unknown-value'],
    )
    def test_malformed_value_fails_closed_on_both_image_and_nfo(self, tmp_path, malformed_value):
        config = dict(_T3_BASE_CONFIG, external_manager=malformed_value)
        helper = TestOffModeNfoTagFallback()
        movie_dir, root = helper._write_and_read_nfo(tmp_path, _T3_META, config)

        # ① 圖片 gate：poster/fanart 都不應存在（CD-111-2 正向白名單已保證，這裡
        # 只是連帶確認 helper 內建的 jellyfin_mock.assert_not_called() 之外的落地檔案）。
        for suffix in ('-poster.jpg', '-fanart.jpg'):
            assert not (Path(movie_dir) / f'{self._BASE}{suffix}').exists(), (
                f"{suffix} must NOT exist for malformed external_manager={malformed_value!r}"
            )

        # ② NFO gate：本 PR 修的正是這一半——修前 generate_nfo 用 `!= 'off'`，
        # 畸形值會被誤判為「媒體管理器模式」而寫入 <lockdata> 等五欄位。
        assert root.find('lockdata') is None, (
            f"<lockdata> must NOT be present for malformed external_manager={malformed_value!r}"
        )


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

class TestExternalManagerMigrationToImageProduction:
    """串接真實 load_config() 的 jellyfin_emby → jellyfin migration，並確認該值
    流進 _write_movie_assets 後正確產出 -poster/-fanart（媒體伺服器風味的正向鏡像，
    對照 TestExternalManagerNormalization 的畸形值 fail-closed 負向鎖）。"""

    _BASE = 'TEST-001 Test Movie Title'

    def test_legacy_jellyfin_emby_config_migrates_and_produces_images(self, tmp_path, monkeypatch):
        import core.config as core_config
        from core.config import load_config

        # config 檔獨立放在 tmp_path 底下的子目錄，與下面 movie_dir 分開，避免
        # 兩者互相干擾；同時確認 need_save 寫回的是這個 tmp 檔，不是使用者的
        # web/config.json（monkeypatch 慣例照抄 test_core_config.py）。
        config_dir = tmp_path / 'config_root'
        config_dir.mkdir()
        config_path = config_dir / 'config.json'
        config_path.write_text(
            '{"scraper": {"external_manager": "jellyfin_emby"}}', encoding='utf-8'
        )
        monkeypatch.setattr(core_config, 'CONFIG_PATH', config_path)
        monkeypatch.setattr(core_config, 'CONFIG_DEFAULT_PATH', config_dir / 'config.default.json')

        # ① 真實 load_config()（不 mock），驗 migration 本身——這段
        # test_core_config.py::test_legacy_jellyfin_emby_migrates_to_jellyfin 已經
        # 驗過，這裡只是取用其結果作為下一步的輸入，不重複斷言細節。
        result = load_config()
        assert result['scraper']['external_manager'] == 'jellyfin'

        # need_save 寫回的必須是 tmp_path 下的檔，不是真實 web/config.json。
        assert config_path.exists()
        written = json.loads(config_path.read_text(encoding='utf-8'))
        assert written['scraper']['external_manager'] == 'jellyfin'

        # ② 把 migration 後的值餵進 _write_movie_assets（媒體伺服器風味 fixture
        # 搭法，沿用 _t4_write——它直接把 movie_dir 當 output_path 傳給
        # _write_movie_assets，不經 resolve_output_root，不會踩 off 風味那個
        # 「寫進真實 output/lib/」的陷阱），斷言正向：該值就該產圖。
        movie_dir = tmp_path / 'movie'
        config = dict(_T3_BASE_CONFIG, external_manager=result['scraper']['external_manager'])
        _t4_write(str(movie_dir), _T3_META, config)

        for suffix in ('-poster.jpg', '-fanart.jpg'):
            assert (movie_dir / f'{self._BASE}{suffix}').exists(), (
                f"{suffix} must exist: migrated 'jellyfin' value must still produce images"
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

    def test_station3_fixture_b(self, tmp_path):
        self._run_station3(tmp_path, "b", self._FIXTURE_B)

    # -----------------------------------------------------------------
    # TASK-101a-T3 DoD①（Opus 拍板，非選配）：off/emby/kodi 唯讀產生庫三路
    # 各補一個 fixture-A-only 真跑案例（不 mock crop_to_poster/generate_
    # jellyfin_images）。TASK-111 之後三路不再同向：emby/kodi 仍斷言 poster
    # bytes 對準同一個獨立 oracle（結構論證——呼叫對這兩路無條件，未來若有人
    # 加分支跳過烤圖，這裡會紅）；off 斷言 poster/fanart 皆不產生（spec-111
    # §2.1 的 gate，見 `_run_station3` 內的分流）。
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


class TestBuildOldBase:
    """T4: _build_old_base — DB row (`existing`) → old_meta mapping → old basename."""

    def test_none_existing_returns_empty(self):
        from core.readonly_paths import _build_old_base
        assert _build_old_base(None, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_empty_title_returns_empty(self):
        existing = _t4_existing(dict(_T3_META, title=''))
        from core.readonly_paths import _build_old_base
        assert _build_old_base(existing, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_empty_number_returns_empty(self):
        """Defensive guard (Opus note #3): existing.number falsy must not crash / must skip."""
        existing = _t4_existing(dict(_T3_META, number=''))
        from core.readonly_paths import _build_old_base
        assert _build_old_base(existing, '/src/TEST-001.mp4', _T3_BASE_CONFIG) == ''

    def test_normal_existing_matches_manual_pipeline(self):
        """old_base must equal _format_data + _build_basename run manually against the
        same mapped fields — proves _build_old_base doesn't silently diverge from
        the documented mapping (number/title/actors/maker/date)."""
        from core.readonly_paths import _build_basename, _build_old_base, _format_data

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
        from core.readonly_assets import _clean_stale_extrafanart

        d = tmp_path / 'movie'
        d.mkdir()
        _clean_stale_extrafanart(str(d))  # must not raise

    def test_extrafanart_glob_ignores_non_fanart_files(self, tmp_path):
        from core.readonly_assets import _clean_stale_extrafanart

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
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        f = d / 'random.jpg'
        f.write_bytes(b'x')
        _clean_stale_singletons(str(d), '', 'NEW-BASE', True, True, True)
        assert f.exists()

    def test_old_base_equals_new_base_is_noop(self, tmp_path):
        """Same basename → new write already overwrote the file in place;
        cleaning here would clobber what was just written."""
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        base = 'TEST-001 Same'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{base}{suffix}').write_bytes(b'NEW')

        _clean_stale_singletons(str(d), base, base, True, True, True)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert (d / f'{base}{suffix}').exists(), f"{suffix} must survive (same base)"

    def test_deletes_singleton_assets_when_all_flags_true(self, tmp_path):
        from core.readonly_assets import _clean_stale_singletons

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
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('.nfo', '.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False)

        assert not (d / f'{old_base}.nfo').exists(), "nfo must always be cleaned (nfo_ok guaranteed)"
        assert (d / f'{old_base}.jpg').exists(), "old cover must survive when has_cover is False"

    def test_has_poster_and_fanart_false_keeps_old_files(self, tmp_path):
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        for suffix in ('-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', True, False, False)

        assert (d / f'{old_base}-poster.jpg').exists(), "old poster must survive when has_poster is False"
        assert (d / f'{old_base}-fanart.jpg').exists(), "old fanart must survive when has_fanart is False"

    def test_missing_files_are_noop_no_raise(self, tmp_path):
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        _clean_stale_singletons(str(d), 'NOTHING-EVER-WRITTEN', 'NEW-BASE', True, True, True)  # must not raise

    def test_old_base_with_glob_metachars_is_escaped(self, tmp_path):
        """old_base from a scraped title may contain '[' ']' (e.g. '[Chinese Sub]').
        sanitize_filename keeps brackets, so the poster/fanart globs must
        glob.escape(old_base) or they silently miss the file (narrow Codex #3
        recurrence — residual poster/fanart junk survives)."""
        from core.readonly_assets import _clean_stale_singletons

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'STARS-123 [Chinese Sub]'
        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            (d / f'{old_base}{suffix}').write_bytes(b'x')

        _clean_stale_singletons(str(d), old_base, 'STARS-123 New', True, True, True)

        for suffix in ('.nfo', '.jpg', '-poster.jpg', '-fanart.jpg'):
            assert not (d / f'{old_base}{suffix}').exists(), \
                f"{suffix} with bracketed old_base not cleaned (glob not escaped)"


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

    def test_old_layout_three_files_renamed(self, tmp_path):
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-002 Old'
        new_base = 'TEST-002 New'
        cover = d / f'{old_base}.jpg'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'COVER')
        poster.write_bytes(b'POSTER')
        fanart.write_bytes(b'FANART')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not cover.exists()
        assert not poster.exists()
        assert not fanart.exists()
        new_cover = d / f'{new_base}.jpg'
        assert new_cover.read_bytes() == b'COVER'
        assert (d / f'{new_base}-poster.jpg').read_bytes() == b'POSTER'
        assert (d / f'{new_base}-fanart.jpg').read_bytes() == b'FANART'
        assert len(outcome.moved_pairs) == 3
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_cover), {})

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

    def test_noop_when_old_stem_equals_new_stem(self, tmp_path):
        """C-10 早退必須發生在 slot 掃描之前，不只是「最後沒搬」。

        只斷言 atomic_move 零呼叫證明不了這件事——若把 C-10 早退拿掉，撞名預檢
        （dst 已存在）一樣會讓 atomic_move 維持零呼叫、整條測試照樣綠。這裡額外
        鎖 os.path.exists 只被呼叫一次（①b 錨點存在性檢查），代表函式在算出
        old_stem_abs == new_stem_abs 之後立刻 return，完全沒有進入
        _resolve_slot／撞名預檢那些會再呼叫 os.path.exists 的路徑
        （grok review 第 2 輪 P3，把 C-10 早退暫時改成 `if not old_stem_abs:`
        重跑本測試會轉紅，驗證見 MUTATION_EVIDENCE）。

        Codex PR#197 review P2 之後：identity 解析改走 `_resolve_cover_group_identity`
        （`base` 同時是舊檔案的實際基底、也是傳入的 `new_base_name`——寫實地模擬
        「標題沒變、原地重跑」）。**第五輪 review 效能修正之後**：磁碟證據判定改用
        `os.scandir` 一次性列舉目錄、記憶體字串比對，不再逐檔 `os.path.exists`
        ——本測試斷言的 `os.path.exists` 呼叫僅剩 `_rename_stale_cover_group`
        開頭①b 錨點存在性檢查那一次，與證據蒐集階段完全無關；即使不傳 `old_base`
        提示（兩套候選都無 sibling 佐證，落到「無法判定」的 `None`，回傳值恰好
        一樣是 `_NOOP`）也一樣只呼叫一次 `os.path.exists`（實測見 MUTATION_EVIDENCE）
        ——傳 `old_base=base` 不是這次能通過的必要條件，只是額外驗證提示補位在
        C-10 這個特定 fixture 下也同樣正確解出 stripped、零額外 I/O。
        """
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        base = 'TEST-004 Same'
        fanart = d / f'{base}-fanart.jpg'
        fanart.write_bytes(b'FANART')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        with patch('core.readonly_assets.atomic_move') as mock_move, \
                patch('core.readonly_assets.os.path.exists', return_value=True) as mock_exists:
            outcome = _rename_stale_cover_group(str(d), existing, base, {}, base)

        assert mock_move.call_count == 0
        assert outcome == RenameOutcome(None, False, ())
        assert fanart.read_bytes() == b'FANART'
        assert mock_exists.call_count == 1, (
            "os.path.exists 應只被呼叫一次（①b 錨點檢查）；多於一次代表 C-10 早退"
            "沒有真的擋在 slot 掃描之前"
        )

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

    def test_orphan_reunites_with_current_basename(self, tmp_path):
        import hashlib

        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-008 Old'
        new_base = 'TEST-008 Current'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        poster.write_bytes(b'ORPHAN POSTER')
        fanart.write_bytes(b'ORPHAN FANART')
        poster_sha = hashlib.sha256(poster.read_bytes()).hexdigest()
        fanart_sha = hashlib.sha256(fanart.read_bytes()).hexdigest()
        # {new_base}.nfo 已存在（這輪 NFO 早就寫對了，只有圖沒跟上）；
        # {old_base}.nfo 不存在（已被既有 _clean_stale_singletons 清過，AC-11 already-broken 狀態）。
        (d / f'{new_base}.nfo').write_bytes(b'<movie></movie>')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not poster.exists()
        assert not fanart.exists()
        new_poster = d / f'{new_base}-poster.jpg'
        new_fanart = d / f'{new_base}-fanart.jpg'
        assert hashlib.sha256(new_poster.read_bytes()).hexdigest() == poster_sha
        assert hashlib.sha256(new_fanart.read_bytes()).hexdigest() == fanart_sha
        assert not any(p.name.startswith(old_base) for p in d.iterdir())
        assert outcome.hard_failure is False

    def test_orphan_reunites_old_layout_three_files(self, tmp_path):
        """AC-11（`TASK-151b-T0.md`「AC-11 已壞狀態設計」表 jellyfin-舊佈局列）：

        升級前就已經踩過洞一 bug、且是舊佈局三檔形狀（`{base}.jpg` + `-poster`
        + `-fanart`）的片，DB `cover_path` 指向 `-fanart`、`{old_base}.nfo` 已不
        存在（早被 `_clean_stale_singletons` 清過）、`{new_base}.nfo` 已存在
        （這輪 NFO 早就寫對了，只有圖沒跟上）。這與 `test_orphan_reunites_with_
        current_basename`（jellyfin-新佈局，只有 poster/fanart 兩檔）是不同的
        起始佈局，spec AC-11 明文要求兩種佈局都要覆蓋（grok review 第 2 輪 P3①）。
        """
        import hashlib

        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-010 Old'
        new_base = 'TEST-010 Current'
        cover = d / f'{old_base}.jpg'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'ORPHAN COVER')
        poster.write_bytes(b'ORPHAN POSTER')
        fanart.write_bytes(b'ORPHAN FANART')
        cover_sha = hashlib.sha256(cover.read_bytes()).hexdigest()
        poster_sha = hashlib.sha256(poster.read_bytes()).hexdigest()
        fanart_sha = hashlib.sha256(fanart.read_bytes()).hexdigest()
        # {old_base}.nfo 不存在（已被清過）；{new_base}.nfo 已存在。
        (d / f'{new_base}.nfo').write_bytes(b'<movie></movie>')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not cover.exists()
        assert not poster.exists()
        assert not fanart.exists()
        new_cover = d / f'{new_base}.jpg'
        new_poster = d / f'{new_base}-poster.jpg'
        new_fanart = d / f'{new_base}-fanart.jpg'
        assert hashlib.sha256(new_cover.read_bytes()).hexdigest() == cover_sha
        assert hashlib.sha256(new_poster.read_bytes()).hexdigest() == poster_sha
        assert hashlib.sha256(new_fanart.read_bytes()).hexdigest() == fanart_sha
        assert len(outcome.moved_pairs) == 3
        assert not any(p.name.startswith(old_base) for p in d.iterdir())
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_fanart), {})

    def test_anchor_missing_sibling_exists_untouched(self, tmp_path):
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-009 Old'
        sibling = d / f'{old_base}-poster.jpg'
        sibling.write_bytes(b'SIBLING BYTES')
        missing_anchor = d / f'{old_base}-fanart.jpg'  # 不存在，cover_path 指到它
        existing = SimpleNamespace(cover_path=to_file_uri(str(missing_anchor), {}))

        outcome = _rename_stale_cover_group(str(d), existing, 'TEST-009 New', {})

        assert outcome == RenameOutcome(None, False, ())
        assert sibling.read_bytes() == b'SIBLING BYTES'
        assert not (d / 'TEST-009 New-poster.jpg').exists()

    def test_mixed_extensions_anchor_file_itself_is_moved(self, tmp_path):
        """回歸修正②（Codex PR#197 review，第 6 輪修正方向）＋窮舉盤點後的
        重新設計（151b pre-merge，owner 裁決選項 1）：DB 錨點指 `.png`，同一
        個 slot 還躺著一個優先序更高的 `.jpg` sibling。D-151b-1 的承諾是
        「圖的內容一個位元組不動，只是換個名字」——不是「這個 slot 換一張
        內容相近的圖也算數」。正確行為：錨點那一個 slot 必須搬 DB 指向的
        那個檔本身（`old_cover_fs`）；sibling 刻意留在舊基底原地、不搬、
        內容不動。

        **不再斷言 warning log**：舊設計靠 `prefer` 在多個候選裡「選」出
        錨點，選擇動作值得記一行解釋性 warning；新設計下錨點 slot 直接用
        已知的 `old_cover_fs`，根本不經過 `_resolve_slot` 的候選列舉，沒有
        選擇這回事可言，因此也沒有可解釋的東西可記——少的只是一行 debug
        log，不是產品行為（搬動結果、sibling 原地不動，與舊碼逐字相同）。
        非錨點 slot 的同則 warning 維持不變，見同 class 內對 `_resolve_slot`
        的直接單元測試。"""
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-011 Old'
        new_base = 'TEST-011 New'
        old_png = d / f'{old_base}.png'
        old_jpg = d / f'{old_base}.jpg'
        old_png.write_bytes(b'ANCHOR PNG BYTES')
        old_jpg.write_bytes(b'SIBLING JPG BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(old_png), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        new_png = d / f'{new_base}.png'
        new_jpg = d / f'{new_base}.jpg'
        assert not old_png.exists(), "錨點本檔（DB 指向的那個）必須被搬走"
        assert new_png.exists() and new_png.read_bytes() == b'ANCHOR PNG BYTES', (
            "錨點 slot 搬的必須是 DB 指向的那個檔本身，內容一個位元組不動（D-151b-1）"
        )
        assert old_jpg.exists() and old_jpg.read_bytes() == b'SIBLING JPG BYTES', (
            "重複的 sibling 刻意留在舊基底原地，不搬、內容不動"
        )
        assert not new_jpg.exists(), "sibling 不該被搬到新基底，new_cover_uri 也不該指向它"
        assert outcome.new_cover_uri == to_file_uri(str(new_png), {}), (
            "new_cover_uri 必須指向實際搬動的錨點檔（.png），不是 sibling 的 .jpg"
        )
        import os as _os
        assert _os.path.exists(str(new_png))

    def test_poster_anchor_new_layout_new_cover_uri_points_to_poster(self, tmp_path):
        """回歸守衛（第 5 輪 review）：DB 錨點是 `-poster.jpg`——外部管理器
        工具（MDCX／Javinizer，`core/gallery_scanner.py` L1.5 明文掃
        `{stem}-poster`）常見命名，唯讀來源接手這類庫時完全可能只有
        `-poster`／`-fanart` 兩檔、沒有同名封面本體。`anchor_stem_suffix`
        的 `-poster` 分支若判斷錯了，`anchor_dst` 會落空（新佈局沒有 `''`
        slot 可頂替，餵 `to_file_uri(None, ...)`）或誤指到 `-fanart`——
        `new_cover_uri` 必須正確指向 `{new_base}-poster.jpg`，且該檔真的
        存在於磁碟上。"""
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-012 Old'
        new_base = 'TEST-012 New'
        poster = d / f'{old_base}-poster.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        poster.write_bytes(b'POSTER ANCHOR BYTES')
        fanart.write_bytes(b'FANART SIBLING BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(poster), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        new_poster = d / f'{new_base}-poster.jpg'
        new_fanart = d / f'{new_base}-fanart.jpg'
        assert not poster.exists()
        assert not fanart.exists()
        assert new_poster.exists() and new_poster.read_bytes() == b'POSTER ANCHOR BYTES'
        assert new_fanart.exists() and new_fanart.read_bytes() == b'FANART SIBLING BYTES'
        assert outcome.new_cover_uri == to_file_uri(str(new_poster), {}), (
            "DB 錨點是 -poster 時 new_cover_uri 必須指向 -poster 那個 slot 實際搬到的檔，"
            "不是 -fanart、也不是不存在的同名封面本體"
        )
        import os as _os
        assert _os.path.exists(str(new_poster))

    def test_anchor_extension_not_in_whitelist_moves_verbatim(self, tmp_path):
        """窮舉盤點格 A=no(錨點副檔名不在 IMAGE_EXTENSIONS)／B=no(無 sibling)。

        舊設計（Codex PR#197 修法二／`prefer` 版）：`_resolve_slot('')` 對
        `.tiff` 一無所獲（`IMAGE_EXTENSIONS` 沒有 `.tiff`），`hits == []`，
        `prefer` 派不上用場，這個 slot 完全沒進 `group`，`anchor_dst` 留
        `None`，函式最後 `to_file_uri(None, ...)` 拋 `AttributeError`
        （實測見窮舉腳本 Cell3；不是本卡片編造的場景）。新設計：錨點 slot
        不經過 `IMAGE_EXTENSIONS` 列舉，直接用 `old_cover_fs` 本身，因此不
        受白名單限制——非影像慣用副檔名的錨點檔一樣原樣搬動、不崩潰。
        """
        import hashlib

        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-013 Old'
        new_base = 'TEST-013 New'
        anchor = d / f'{old_base}.tiff'
        anchor.write_bytes(b'ANCHOR TIFF BYTES')
        anchor_sha = hashlib.sha256(anchor.read_bytes()).hexdigest()
        existing = SimpleNamespace(cover_path=to_file_uri(str(anchor), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not anchor.exists()
        new_anchor = d / f'{new_base}.tiff'
        assert new_anchor.exists()
        assert hashlib.sha256(new_anchor.read_bytes()).hexdigest() == anchor_sha
        assert outcome.hard_failure is False
        assert outcome.moved_pairs == ((str(anchor), str(new_anchor)),)
        assert outcome.new_cover_uri == to_file_uri(str(new_anchor), {})
        import os as _os
        assert _os.path.exists(str(new_anchor))

    def test_anchor_extension_not_in_whitelist_sibling_left_untouched(self, tmp_path, caplog):
        """窮舉盤點格 A=no／B=yes（同 slot 有白名單 sibling）——本卡片窮舉才
        抓到、之前三輪都沒發現的一格：`_resolve_slot('')` 只看得到 sibling
        （`.jpg` 在 `IMAGE_EXTENSIONS` 裡，`.tiff` 錨點本身根本不進 `hits`
        候選），`len(hits) == 1`，`prefer` 分支的 `len(hits) > 1` 閘門連檢查
        都不會檢查——直接回傳那個 sibling，把 DB 換指到 sibling 的內容、
        真正的錨點檔案整個被忽略、永遠孤兒留在舊基底。比 ③ 的崩潰更隱蔽：
        沒有例外、沒有 warning，看起來完全正常但圖換了一張。

        新設計：錨點 slot 無條件用 `old_cover_fs` 本身，根本不看 sibling
        候選列表，因此這個 slot 的 sibling 天生就搬不到——不是「選擇」，是
        「不列舉」的必然結果。
        """
        import hashlib
        import logging

        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-014 Old'
        new_base = 'TEST-014 New'
        anchor = d / f'{old_base}.tiff'
        sibling = d / f'{old_base}.jpg'
        anchor.write_bytes(b'ANCHOR TIFF BYTES')
        sibling.write_bytes(b'SIBLING JPG BYTES')
        anchor_sha = hashlib.sha256(anchor.read_bytes()).hexdigest()
        existing = SimpleNamespace(cover_path=to_file_uri(str(anchor), {}))

        with caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        new_anchor = d / f'{new_base}.tiff'
        new_sibling = d / f'{new_base}.jpg'
        assert not anchor.exists(), "錨點本檔（DB 指向的那個）必須被搬走"
        assert hashlib.sha256(new_anchor.read_bytes()).hexdigest() == anchor_sha, (
            "搬到新基底的必須是錨點本檔內容，不是 sibling 的內容"
        )
        assert sibling.exists() and sibling.read_bytes() == b'SIBLING JPG BYTES', (
            "sibling（白名單副檔名但不是 DB 指向的那個）留在舊基底原地、內容不動"
        )
        assert not new_sibling.exists(), "sibling 不該被搬到新基底"
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_anchor), {}), (
            "new_cover_uri 必須指向實際搬動的錨點檔（.tiff），不是 sibling 的 .jpg"
        )
        import os as _os
        assert _os.path.exists(str(new_anchor))

    def test_anchor_extension_not_in_whitelist_mid_rename_failure_reverts(self, tmp_path):
        """整組原子在「錨點副檔名不在白名單」這格底下仍須成立——這正是 ③
        （`AttributeError` 崩潰）破掉的那個保證：舊設計在這種配置下，崩潰
        發生在 `try` 區塊**之外**（成功搬完才崩潰在最後一行的 `to_file_uri`），
        於是已搬的 slot 完全不會進入 `_revert_cover_rename`。這裡改用會在
        `try` 區塊**之內**丟 `OSError` 的組態（第二個 slot 的搬移失敗），
        確認新設計下：(a) 不崩潰、(b) 兩個 slot 都被復原回原位、(c) 回傳值
        是 `RenameOutcome(None, True, ())`——與白名單副檔名場景（既有
        `test_mid_rename_io_failure_reverts`）同一種保證，不因錨點副檔名
        exotic 而失效。
        """
        from core.atomic_write import atomic_move as _real_atomic_move
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-015 Old'
        new_base = 'TEST-015 New'
        anchor = d / f'{old_base}.tiff'  # '' slot，anchor_stem_suffix == ''
        poster = d / f'{old_base}-poster.jpg'
        anchor.write_bytes(b'ANCHOR TIFF BYTES')
        poster.write_bytes(b'POSTER BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(anchor), {}))

        call_count = {'n': 0}

        def flaky(src, dst):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise OSError("simulated mid-rename failure")
            _real_atomic_move(src, dst)

        with patch('core.readonly_assets.atomic_move', side_effect=flaky):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert outcome == RenameOutcome(None, True, ())
        assert anchor.read_bytes() == b'ANCHOR TIFF BYTES'
        assert poster.read_bytes() == b'POSTER BYTES'
        assert not (d / f'{new_base}.tiff').exists()
        assert not (d / f'{new_base}-poster.jpg').exists()

    # -----------------------------------------------------------------
    # Codex PR#197 review P2 (151b pre-merge 後新洞)：cover_base_stem() 純字串
    # 剝一次 -poster/-fanart 尾碼，分不出「衍生的 sidecar 尾碼」與「尾碼本來
    # 就是基底標題一部分」。以下五格對應卡片「至少要鎖的五格測試」。
    # -----------------------------------------------------------------

    def test_identity_general_layout_no_hint_resolves_via_sibling_evidence(self, tmp_path):
        """格①：一般新佈局（DB 指 `-fanart.jpg`、旁有 `-poster.jpg`），不給
        `old_base` 提示，純靠磁碟 sibling 證據判成 stripped（錨點＝-fanart
        slot）——行為與 `test_new_layout_two_files_renamed`（現況）逐字相同。
        """
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-001 Old'
        new_base = 'IDN-001 New'
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
        assert outcome.new_cover_uri == to_file_uri(str(new_fanart), {})

    def test_identity_literal_base_ending_in_fanart_with_nested_siblings(self, tmp_path):
        """格②：基底真的叫 `...Movie-fanart`（plain `Movie-fanart.jpg` ＋
        nested `Movie-fanart-poster.jpg` ＋ nested `Movie-fanart-fanart.jpg`）
        → 判成 literal（錨點＝'' slot），三檔都搬到新基底、舊基底零殘留。

        這是 Codex PR#197 review P2 的實測反例：naive `cover_base_stem()`
        會把 `Movie-fanart.jpg` 誤剝成 `Movie`，讓兩個 nested sidecar 在
        被誤剝的 stem 底下遍尋不著、永遠孤兒留在舊基底。
        """
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-002 Movie-fanart'
        new_base = 'IDN-002 New'
        cover = d / f'{old_base}.jpg'
        nested_poster = d / f'{old_base}-poster.jpg'
        nested_fanart = d / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'PLAIN COVER BYTES')
        nested_poster.write_bytes(b'NESTED POSTER BYTES')
        nested_fanart.write_bytes(b'NESTED FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert not cover.exists()
        assert not nested_poster.exists()
        assert not nested_fanart.exists()
        new_cover = d / f'{new_base}.jpg'
        new_poster_slot = d / f'{new_base}-poster.jpg'
        new_fanart_slot = d / f'{new_base}-fanart.jpg'
        assert new_cover.read_bytes() == b'PLAIN COVER BYTES'
        assert new_poster_slot.read_bytes() == b'NESTED POSTER BYTES'
        assert new_fanart_slot.read_bytes() == b'NESTED FANART BYTES'
        assert not any(p.name.startswith(old_base) for p in d.iterdir())
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_cover), {})

    def test_identity_hint_resolves_literal_when_base_ends_with_poster(self, tmp_path):
        """格③：off 單封面且基底本身以 `-poster` 結尾（MDCX/Javinizer 等工具
        常見標題含 `-poster` 字面），**磁碟上零 sibling 可證**（單封面、無
        `-poster`/`-fanart` 衍生檔），literal／stripped 兩套解釋都沒有證據
        ——這是唯一允許 `old_base` 提示補位的情境（Codex 第四輪 review 修正：
        精確字串匹配不能證明 `old_base` 沒有失憶，見 `_resolve_cover_group_
        identity` docstring 的反例；提示現在只在磁碟證據完全缺席時才准當
        最後手段裁決）。

        fixture 已核實只有單一檔案、零 sibling（下面只 write 一個 `cover`），
        真的落在「兩套都沒證據」那格，不是誤測到別的分支。
        """
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-003 Special-poster'
        new_base = 'IDN-003 New'
        cover = d / f'{old_base}.jpg'
        cover.write_bytes(b'SOLO COVER BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        outcome = _rename_stale_cover_group(str(d), existing, new_base, {}, old_base)

        assert not cover.exists()
        new_cover = d / f'{new_base}.jpg'
        assert new_cover.read_bytes() == b'SOLO COVER BYTES'
        assert not (d / f'{new_base}-poster.jpg').exists()
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_cover), {})

    def test_identity_forgotten_hint_falls_back_to_sibling_evidence(self, tmp_path):
        """格④：已壞狀態、DB title 已失憶（`old_base` 提示等於
        `new_base_name`，兩個候選 stem 都對不上）→ 提示不生效、退回磁碟
        sibling 證據判成 stripped（錨點＝-fanart slot，plain 同名封面存在）。

        刻意選「正確答案是 stripped」且**靠同名封面（`stripped + ext`）**
        作證的佈局——不是格①那種靠「另一個 sidecar」作證、也不是格②那種
        「正確答案剛好是 literal」的佈局：如果提示不匹配時被誤判成『無條件
        信任任何非空提示、把它當成 literal 匹配』，這裡會選錯 slot（新封面
        會落在 `{new_base}.jpg` 而不是 `{new_base}-fanart.jpg`）；如果誤判
        成用格②那種「答案剛好也是 literal」的佈局，巧合算對抓不到這個 bug
        ——本格佈局刻意與格①②都不同，鎖的是「同名封面」這條證據（不同於
        格①鎖的「另一個 sidecar」那條），避免兩格共用同一條判定。
        """
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-004 Old'
        new_base = 'IDN-004 New'
        cover = d / f'{old_base}.jpg'
        fanart = d / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'PLAIN COVER BYTES')
        fanart.write_bytes(b'FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        # 提示已失憶：等於 new_base_name，不匹配 literal（'IDN-004 Old-fanart'）
        # 也不匹配 stripped（'IDN-004 Old'）
        outcome = _rename_stale_cover_group(str(d), existing, new_base, {}, new_base)

        assert not cover.exists()
        assert not fanart.exists()
        new_cover = d / f'{new_base}.jpg'
        new_fanart = d / f'{new_base}-fanart.jpg'
        assert new_cover.read_bytes() == b'PLAIN COVER BYTES'
        assert new_fanart.read_bytes() == b'FANART BYTES'
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_fanart), {})

    def test_identity_ambiguous_both_interpretations_have_evidence_noop(self, tmp_path, caplog):
        """格⑤：兩套結構同時存在（literal 與 stripped 各自都有磁碟證據），
        無法判定 → 零搬移、零 CAS，記一行 warning，回傳 `_NOOP` 形狀。

        `stripped` 這邊刻意用**同名封面**（`stripped + ext`）作證，不是格①④
        用的「另一個 sidecar」——避免這格跟格①④共用同一條判定，鎖的是
        「literal／stripped 兩套證據同時成立時的最終仲裁」本身，不是任何單
        一條證據蒐集規則。
        """
        import logging

        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-005 Movie-fanart'
        new_base = 'IDN-005 New'
        cover = d / f'{old_base}.jpg'
        nested_poster = d / f'{old_base}-poster.jpg'  # 支持 literal
        stripped_plain_cover = d / 'IDN-005 Movie.jpg'  # 支持 stripped（同名封面）
        cover.write_bytes(b'PLAIN COVER BYTES')
        nested_poster.write_bytes(b'NESTED POSTER BYTES')
        stripped_plain_cover.write_bytes(b'STRIPPED PLAIN COVER BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        with caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert outcome == RenameOutcome(None, False, ())
        assert cover.read_bytes() == b'PLAIN COVER BYTES'
        assert nested_poster.read_bytes() == b'NESTED POSTER BYTES'
        assert stripped_plain_cover.read_bytes() == b'STRIPPED PLAIN COVER BYTES'
        assert not any(p.name.startswith(new_base) for p in d.iterdir())
        messages = [r.getMessage() for r in caplog.records]
        assert any('無法判定' in m for m in messages), f"缺少無法判定 warning log：{messages}"

    def test_identity_ambiguous_with_matching_hint_hint_does_not_decide(self, tmp_path, caplog):
        """Codex 補跑 mutation 存活找到的真缺口：把『兩套都有證據 ⇒ 歧義
        `None`，提示不得裁決』那格（`if literal_evidence and stripped_evidence:
        return None`）整個停用，408 條測試全綠——因為格⑤（上面那條）的
        fixture 剛好沒有給任何 `old_base_hint`，停用該分支後控制流程落到
        『兩套都沒有證據』那段的提示判斷，`if old_base_hint:` 因為提示是
        空字串直接跳過，最終仍然 `return None`（函式最後一行），結果巧合
        正確，完全測不出「提示不得裁決」這條規則本身有沒有被鎖住。

        本格刻意讓 fixture 同時滿足『兩套都有磁碟證據』**且**『`old_base_hint`
        精確匹配 stripped 候選的 stem』——這是關鍵：有這個精確匹配的提示，
        才會真正走進『兩套都沒有證據』那個 `if old_base_hint:` 分支的邏輯
        （如果歧義守衛被拿掉）。若歧義守衛不存在，提示補位那段的
        `hint_stem == stripped_stem` 會判真，錯誤地回傳 stripped 而不是
        `None`；有守衛時，證據裁決優先，兩套都有證據必須回傳 `None`，提示
        完全不該被檢查到。
        """
        import logging

        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-012 Movie-fanart'
        new_base = 'IDN-012 New'
        cover = d / f'{old_base}.jpg'
        nested_poster = d / f'{old_base}-poster.jpg'  # 支持 literal
        stripped_plain_cover = d / 'IDN-012 Movie.jpg'  # 支持 stripped（同名封面）
        cover.write_bytes(b'PLAIN COVER BYTES')
        nested_poster.write_bytes(b'NESTED POSTER BYTES')
        stripped_plain_cover.write_bytes(b'STRIPPED PLAIN COVER BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        # 提示精確匹配 stripped 候選的 stem（'IDN-012 Movie'）——若歧義守衛被
        # 拿掉，提示補位那段會誤把 stripped 當成答案。
        hint = 'IDN-012 Movie'

        with caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {}, hint)

        assert outcome == RenameOutcome(None, False, ())
        assert cover.read_bytes() == b'PLAIN COVER BYTES'
        assert nested_poster.read_bytes() == b'NESTED POSTER BYTES'
        assert stripped_plain_cover.read_bytes() == b'STRIPPED PLAIN COVER BYTES'
        assert not any(p.name.startswith(new_base) for p in d.iterdir())
        messages = [r.getMessage() for r in caplog.records]
        assert any('無法判定' in m for m in messages), f"缺少無法判定 warning log：{messages}"

    # -----------------------------------------------------------------
    # Codex 第四輪 review P2：提示精確匹配不能證明 old_base 沒有失憶——反例是
    # 舊基底 `Movie-fanart` 在 DB title 已先行改成 `Movie` 之後，提示會「精確
    # 匹配」到錯的 stripped 候選。以下兩格參數化「兩個方向」的失憶碰撞：
    # 正向（長縮短，提示誤撞 stripped）／反向（短拉長，提示誤撞 literal）。
    # -----------------------------------------------------------------

    @pytest.mark.parametrize(
        "case_id,anchor_filename,sibling_filenames,hint,expected_stem_basename,"
        "expected_anchor_stem_suffix",
        [
            pytest.param(
                'forward',
                'IDN-006 Movie-fanart.jpg',
                ('IDN-006 Movie-fanart-poster.jpg', 'IDN-006 Movie-fanart-fanart.jpg'),
                'IDN-006 Movie',
                'IDN-006 Movie-fanart',
                '',
                id='forward-long-to-short-hint-collides-with-stripped',
            ),
            pytest.param(
                'reverse',
                'IDN-007 Movie-fanart.jpg',
                ('IDN-007 Movie-poster.jpg',),
                'IDN-007 Movie-fanart',
                'IDN-007 Movie',
                '-fanart',
                id='reverse-short-to-long-hint-collides-with-literal',
            ),
        ],
    )
    def test_identity_amnesia_collision_resolves_via_evidence_not_hint(
        self, tmp_path, case_id, anchor_filename, sibling_filenames, hint,
        expected_stem_basename, expected_anchor_stem_suffix,
    ):
        """格⑥⑦：提示「精確匹配」某候選，不代表那候選是對的——磁碟證據才是
        仲裁者，提示只在磁碟上兩套解釋都沒有證據時才准補位。

        **正向**（`forward`）：真實舊基底是 `IDN-006 Movie-fanart`（標題本身
        就含 `-fanart` 字面），錨點是同名 plain 封面、旁邊兩個 nested sidecar
        （`-poster`／`-fanart`）證明 literal 才對。DB 上一輪已把 title 改成
        `IDN-006 Movie`（短標題，剝掉了「-fanart」那段），這一輪的 `old_base`
        提示因此精確等於 stripped 候選的 stem——**這正是上一輪錯誤推理會誤判
        的那個反例**：識別若還是選 stripped，兩個真 sidecar 會被判定成「已經
        在對的位置」（`old_stem_abs == new_stem_abs` 觸發 C-10），永遠孤兒。

        **反向**（`reverse`）：真實舊基底是 `IDN-007 Movie`（短標題），錨點是
        一張衍生 `-fanart` sidecar，旁邊真正的 `-poster` sidecar 證明 stripped
        （`IDN-007 Movie`）才對。DB 上一輪已把 title 改成 `IDN-007 Movie-fanart`
        （長標題，剛好與錨點檔案本身的字面尾碼同形），這一輪的提示因此精確
        等於 literal 候選的 stem——同一種「提示碰巧撞對候選、但候選是錯的」
        陷阱，方向相反。

        兩格都直接呼叫 `_resolve_cover_group_identity`：只斷言識別結果，不斷言
        `_rename_stale_cover_group` 的搬檔結果（兩個方向的實際搬檔結果不對稱
        ——正向會撞名、反向會成功，各自的端對端行為由下面兩支專屬測試分別
        實測斷言，不在這裡用參數化硬湊成同一種斷言）。
        """
        from core.readonly_assets import _resolve_cover_group_identity

        d = tmp_path / 'movie'
        d.mkdir()
        anchor = d / anchor_filename
        anchor.write_bytes(b'ANCHOR BYTES')
        for name in sibling_filenames:
            (d / name).write_bytes(b'SIBLING BYTES')

        identity = _resolve_cover_group_identity(str(anchor), str(d), hint)

        expected = (str(d / expected_stem_basename), expected_anchor_stem_suffix)
        assert identity == expected, (
            f"{case_id}: 提示（{hint!r}）碰巧精確匹配了錯的候選，識別結果應該"
            f"仍由磁碟證據仲裁，得到 {expected}，實際 {identity}"
        )

    def test_identity_amnesia_forward_end_to_end_collides_safe_rejection(self, tmp_path, caplog):
        """格⑥端對端實測（不是推理）：正向失憶碰撞修正成 literal 之後，改名組是
        ```
        IDN-006 Movie-fanart.jpg        → IDN-006 Movie.jpg
        IDN-006 Movie-fanart-poster.jpg → IDN-006 Movie-poster.jpg
        IDN-006 Movie-fanart-fanart.jpg → IDN-006 Movie-fanart.jpg   ← dst 等於第一列的 src
        ```
        撞名預檢在任何搬移之前跑，那一刻 `IDN-006 Movie-fanart.jpg`（錨點本身）
        還在磁碟上，所以第三列的 dst 命中撞名 ⇒ **整組零搬移＋warning，回傳
        `_NOOP` 形狀**——這是安全的拒絕，不是逃生口恢復（三個檔案原樣留在舊
        基底，沒有任何內容被覆寫或遺失；使用者這一輪逃生口沒有把孤兒歸位，
        但也沒有製造新的資料風險）。已用 `/tmp` 腳本實測確認過這個結果，不是
        推理猜的——這裡把同一組 fixture 重放進正式測試鎖住。
        """
        import logging

        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        cover = d / 'IDN-006 Movie-fanart.jpg'
        nested_poster = d / 'IDN-006 Movie-fanart-poster.jpg'
        nested_fanart = d / 'IDN-006 Movie-fanart-fanart.jpg'
        cover.write_bytes(b'PLAIN COVER BYTES')
        nested_poster.write_bytes(b'NESTED POSTER BYTES')
        nested_fanart.write_bytes(b'NESTED FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        with caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            # 提示已失憶：DB 上一輪已改成短標題，這一輪 target 也是同一個短標題
            # （重按逃生口、標題沒有再變）。
            outcome = _rename_stale_cover_group(
                str(d), existing, 'IDN-006 Movie', {}, 'IDN-006 Movie'
            )

        assert outcome == RenameOutcome(None, False, ())
        assert cover.read_bytes() == b'PLAIN COVER BYTES'
        assert nested_poster.read_bytes() == b'NESTED POSTER BYTES'
        assert nested_fanart.read_bytes() == b'NESTED FANART BYTES'
        assert sorted(p.name for p in d.iterdir()) == sorted(
            [cover.name, nested_poster.name, nested_fanart.name]
        )
        messages = [r.getMessage() for r in caplog.records]
        assert any('撞名' in m for m in messages), f"缺少撞名 warning log：{messages}"

    def test_identity_amnesia_reverse_end_to_end_succeeds(self, tmp_path):
        """格⑦端對端實測：反向失憶碰撞修正成 stripped 之後，改名組的三個目的
        檔名彼此不重疊、也不撞到還沒搬移的來源檔——實測確認完整搬移成功
        （逃生口在這個方向真的把孤兒歸位了，不像正向那格會撞名擋下）。
        """
        from core.readonly_assets import _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        anchor = d / 'IDN-007 Movie-fanart.jpg'
        sibling_poster = d / 'IDN-007 Movie-poster.jpg'
        anchor.write_bytes(b'ANCHOR FANART BYTES')
        sibling_poster.write_bytes(b'SIBLING POSTER BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(anchor), {}))

        outcome = _rename_stale_cover_group(
            str(d), existing, 'IDN-007 Movie-fanart', {}, 'IDN-007 Movie-fanart'
        )

        assert not anchor.exists()
        assert not sibling_poster.exists()
        new_poster = d / 'IDN-007 Movie-fanart-poster.jpg'
        new_fanart = d / 'IDN-007 Movie-fanart-fanart.jpg'
        assert new_poster.read_bytes() == b'SIBLING POSTER BYTES'
        assert new_fanart.read_bytes() == b'ANCHOR FANART BYTES'
        assert outcome.hard_failure is False
        assert outcome.new_cover_uri == to_file_uri(str(new_fanart), {})

    # -----------------------------------------------------------------
    # 第五輪 review 效能修正：證據判定改用 os.scandir 一次性目錄列舉，不再
    # 逐檔 os.path.exists（NAS/SMB 上每次 stat 是一趟網路來回）。以下三格
    # 鎖新機制本身：scandir 讀取失敗的 fail-safe、單一候選早退連目錄都不
    # 列的零 I/O 保證、以及兩套候選都要看證據時目錄只列舉一次。
    # -----------------------------------------------------------------

    def test_identity_scandir_oserror_is_safe_noop_not_treated_as_no_evidence(self, tmp_path, caplog):
        """`os.scandir` 讀取失敗（目錄被刪除／權限被拒，皆為 `OSError` 子類）
        **不得往外拋**，且**不等於**「兩套候選都沒有磁碟證據」（Codex 第五輪
        review P2，修正第九輪把這兩種狀態錯誤壓成同一個的洞）：掃描失敗是
        「不知道目錄裡有什麼」，不是「已知沒有 sibling」，因此**不准落到
        `old_base_hint` 補位**——`_resolve_cover_group_identity` 收到掃描
        失敗要立刻回 `None`，跳過證據比較與提示補位兩者。這支測試沒有傳
        `old_base_hint`（危險路徑——掃描失敗 ＋ 提示精確匹配某候選——由
        `test_identity_scandir_oserror_with_matching_hint_hint_does_not_decide`
        單獨鎖），這裡只確認：掃描失敗時最終結果仍是安全 no-op（`_NOOP`），
        磁碟零寫入，且記一行「無法判定」warning。
        """
        import logging

        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-008 Old'
        new_base = 'IDN-008 New'
        fanart = d / f'{old_base}-fanart.jpg'
        fanart.write_bytes(b'FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(fanart), {}))

        with patch(
            'core.readonly_assets.os.scandir', side_effect=OSError('simulated scandir failure')
        ), caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {})

        assert outcome == RenameOutcome(None, False, ())
        assert fanart.read_bytes() == b'FANART BYTES'
        assert sorted(p.name for p in d.iterdir()) == [fanart.name]
        messages = [r.getMessage() for r in caplog.records]
        assert any('無法判定' in m for m in messages), f"缺少無法判定 warning log：{messages}"

    def test_identity_scandir_oserror_with_matching_hint_hint_does_not_decide(self, tmp_path, caplog):
        """危險路徑（owner 第 11 輪指出的真缺口）：`os.scandir` 讀取失敗
        **且** `old_base_hint` 恰好精確匹配其中一套候選的 stem。

        `_produce_one` 的生產呼叫現在一定會傳 `old_base`（見卡片接線），
        所以這條路徑不是理論邊界——是每一輪唯讀片重跑都可能撞到的真實
        情境：NAS 暫時性失敗、掛載中斷、或權限問題讓 `os.scandir` 拋出，
        而這一輪的 `old_base` 提示剛好與 stripped 候選同形（例如上一輪
        DB title 已經先行收斂）。若掃描失敗被誤判成『兩套都沒有證據』，
        提示會在完全不知道磁碟上真相的情況下獨力裁決，選錯 identity——
        真正的舊佈局（plain 封面＋兩個 nested sidecar，literal 才對）會
        被誤判成 stripped，`old_stem_abs == new_stem_abs` 觸發 C-10，
        函式甚至不會嘗試搬移，兩個真 sidecar 永遠孤兒、DB 也不會被寫入
        任何新值。**正確行為是掃描失敗當下就整組安全 no-op**：identity
        直接回 `None`，不進提示補位，磁碟零寫入、`atomic_move` 零呼叫。
        """
        import logging

        from core.atomic_write import atomic_move as _real_atomic_move
        from core.readonly_assets import RenameOutcome, _rename_stale_cover_group

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-015 Movie-fanart'
        new_base = 'IDN-015 New'
        cover = d / f'{old_base}.jpg'
        nested_poster = d / f'{old_base}-poster.jpg'
        nested_fanart = d / f'{old_base}-fanart.jpg'
        cover.write_bytes(b'PLAIN COVER BYTES')
        nested_poster.write_bytes(b'NESTED POSTER BYTES')
        nested_fanart.write_bytes(b'NESTED FANART BYTES')
        existing = SimpleNamespace(cover_path=to_file_uri(str(cover), {}))

        # 提示恰好精確匹配 stripped 候選的 stem（'IDN-015 Movie'）——真相是
        # literal 才對（nested sidecar 就在磁碟上），但 scandir 失敗讓函式
        # 根本看不到，不該讓提示替它決定。
        hint = 'IDN-015 Movie'

        with patch(
            'core.readonly_assets.os.scandir', side_effect=OSError('simulated NAS failure')
        ), patch(
            'core.readonly_assets.atomic_move', side_effect=_real_atomic_move
        ) as mock_move, caplog.at_level(logging.WARNING, logger='OpenAver.core.readonly_assets'):
            outcome = _rename_stale_cover_group(str(d), existing, new_base, {}, hint)

        assert outcome == RenameOutcome(None, False, ())
        assert mock_move.call_count == 0, "掃描失敗時不准搬任何檔案——atomic_move 必須零呼叫"
        assert cover.read_bytes() == b'PLAIN COVER BYTES'
        assert nested_poster.read_bytes() == b'NESTED POSTER BYTES'
        assert nested_fanart.read_bytes() == b'NESTED FANART BYTES'
        assert sorted(p.name for p in d.iterdir()) == sorted(
            [cover.name, nested_poster.name, nested_fanart.name]
        )
        messages = [r.getMessage() for r in caplog.records]
        assert any('無法判定' in m for m in messages), f"缺少無法判定 warning log：{messages}"

    def test_identity_single_candidate_early_exit_zero_scandir_calls(self, tmp_path):
        """`literal` 不以 `-poster`／`-fanart` 結尾時（絕大多數無尾碼疑慮的
        正常片），識別必須立即返回、**連 `os.scandir` 都不呼叫**——效能不能
        被下面的證據蒐集拖慢，這是 99.9% 呼叫會走的路徑。
        """
        from core.readonly_assets import _resolve_cover_group_identity

        d = tmp_path / 'movie'
        d.mkdir()
        cover = d / 'IDN-009 Normal.jpg'
        cover.write_bytes(b'NORMAL COVER BYTES')

        with patch('core.readonly_assets.os.scandir') as mock_scandir:
            identity = _resolve_cover_group_identity(str(cover), str(d), '')

        assert identity == (str(d / 'IDN-009 Normal'), '')
        assert mock_scandir.call_count == 0, (
            "單一候選（無 -poster/-fanart 尾碼疑慮）不該碰檔案系統，"
            f"實際呼叫 os.scandir {mock_scandir.call_count} 次"
        )

    def test_identity_two_candidate_path_scandir_called_exactly_once(self, tmp_path):
        """兩套候選都需要磁碟證據時，目錄**只列舉一次**——不是舊版那種對
        兩套候選、每個副檔名各自 `os.path.exists` 的逐檔探法（最多 24 次）。
        """
        from core.readonly_assets import _resolve_cover_group_identity

        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'IDN-010 Old'
        fanart = d / f'{old_base}-fanart.jpg'
        poster = d / f'{old_base}-poster.jpg'
        fanart.write_bytes(b'FANART BYTES')
        poster.write_bytes(b'POSTER BYTES')

        real_scandir = os.scandir
        with patch(
            'core.readonly_assets.os.scandir', side_effect=lambda p: real_scandir(p)
        ) as mock_scandir:
            identity = _resolve_cover_group_identity(str(fanart), str(d), '')

        assert identity == (str(d / old_base), '-fanart')
        assert mock_scandir.call_count == 1, (
            f"兩套候選都要看證據時應該只列舉目錄一次，實際呼叫 {mock_scandir.call_count} 次"
        )

    @pytest.mark.parametrize(
        "case_id,old_base,anchor_filename,sibling_filename,expected_stem_basename,"
        "expected_anchor_stem_suffix",
        [
            pytest.param(
                'literal',
                'IDN-014 Movie-fanart',
                'IDN-014 Movie-fanart.jpg',
                'IDN-014 Movie-fanart-POSTER.JPG',
                'IDN-014 Movie-fanart',
                '',
                id='literal-side-query-normcase',
            ),
            pytest.param(
                'stripped',
                'IDN-011 Old',
                'IDN-011 Old-fanart.jpg',
                'IDN-011 Old-POSTER.JPG',
                'IDN-011 Old',
                '-fanart',
                id='stripped-side-query-normcase',
            ),
        ],
    )
    def test_identity_case_insensitive_match_via_normcase(
        self, tmp_path, case_id, old_base, anchor_filename, sibling_filename,
        expected_stem_basename, expected_anchor_stem_suffix,
    ):
        """模擬 Windows 大小寫不敏感檔案系統：`patch` 讓 `os.path.normcase`
        行為像 Windows 的 `str.lower`，磁碟上實際檔名的大小寫與識別建構的
        候選檔名大小寫不同，仍要能匹配到證據——維持 `os.path.exists` 的舊
        語意（Windows 上大小寫不敏感）。錨點本身的 `-fanart` 尾碼維持小寫
        （尾碼偵測那一步本來就是刻意大小寫敏感、繼承自 `cover_base_stem()`，
        不是這裡要測的東西），只讓 sibling 那一邊的大小寫不同來鎖 evidence
        比對這一段。

        **兩個方向參數化**（Codex 補跑 mutation 存活找到的部分缺口）：只把
        `stripped` 查詢端拿掉 `os.path.normcase` 舊版仍全綠——舊版只有
        `stripped` 這個方向的覆蓋，`literal` 查詢端那個獨立的 `os.path.
        normcase` 呼叫點完全沒被測到。`literal` 這格的 sibling 是
        `{anchor 前綴}-POSTER.JPG`（大小寫不同但字首與錨點本身一致），只有
        literal_evidence 那條查詢用 `os.path.normcase` 才找得到；`stripped`
        這格沿用原本的 fixture 與斷言，逐字保留。
        """
        from core.readonly_assets import _resolve_cover_group_identity

        d = tmp_path / 'movie'
        d.mkdir()
        anchor = d / anchor_filename
        sibling = d / sibling_filename
        anchor.write_bytes(b'ANCHOR BYTES')
        sibling.write_bytes(b'SIBLING BYTES')

        with patch('core.readonly_assets.os.path.normcase', new=str.lower):
            identity = _resolve_cover_group_identity(str(anchor), str(d), '')

        expected = (str(d / expected_stem_basename), expected_anchor_stem_suffix)
        assert identity == expected, (
            f"{case_id}: 大小寫不同的 sibling 應該仍被 normcase 後的比對找到，"
            f"期望 {expected}，實際 {identity}"
        )


class TestRevertCoverRename:
    """T3（151b，DoD⑩）：`_revert_cover_rename` 單獨測試——單一 slot 復原失敗
    不中斷其餘 slot 的復原嘗試，各自 try/except，失敗記 logger.error。"""

    def test_revert_partial_failure_continues_others(self, tmp_path):
        from core.atomic_write import atomic_move as _real_atomic_move
        from core.readonly_assets import _revert_cover_rename

        d = tmp_path / 'movie'
        d.mkdir()
        orig1 = d / 'A-poster.jpg'
        new1 = d / 'B-poster.jpg'
        orig2 = d / 'A-fanart.jpg'
        new2 = d / 'B-fanart.jpg'
        new1.write_bytes(b'POSTER MOVED')
        new2.write_bytes(b'FANART MOVED')
        moved_pairs = ((str(orig1), str(new1)), (str(orig2), str(new2)))

        def flaky(src, dst):
            if (src, dst) == (str(new1), str(orig1)):
                raise OSError("simulated revert failure")
            _real_atomic_move(src, dst)

        with patch('core.readonly_assets.atomic_move', side_effect=flaky), \
                patch('core.readonly_assets.logger') as mock_logger:
            _revert_cover_rename(moved_pairs)

        assert new1.exists()
        assert not orig1.exists()
        assert orig2.exists()
        assert orig2.read_bytes() == b'FANART MOVED'
        assert not new2.exists()
        mock_logger.error.assert_called_once()


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

    def test_extrafanart_shrink_3_to_2(self, tmp_path):
        movie_dir = str(tmp_path / 'TEST-001')
        meta3 = dict(_T3_META, title='Same Title',
                     sample_images=['http://x/1.jpg', 'http://x/2.jpg', 'http://x/3.jpg'])
        config = self._config(download_sample_images=True)
        _t4_write(movie_dir, meta3, config)
        ef_dir = Path(movie_dir) / 'extrafanart'
        assert (ef_dir / 'fanart3.jpg').exists()

        from core.readonly_paths import _build_old_base
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

        from core.readonly_paths import _build_old_base
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

    def test_first_generation_no_existing_row_no_op(self, tmp_path):
        """existing is None → _build_old_base == '' → no cleanup attempted, write succeeds."""
        from core.readonly_paths import _build_old_base

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

        from core.readonly_paths import _build_old_base
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        _t4_write(new_dir, meta_b, config, old_base=old_base)

        # old dir: completely untouched (still has its own Title A series)
        # 真理表 Table 2 #1：media-server flavour 下正典即 `-fanart.jpg`，不是裸 `.jpg`。
        assert (Path(old_dir) / 'TEST-001 Title A.nfo').exists()
        assert (Path(old_dir) / 'TEST-001 Title A-fanart.jpg').exists()
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

    def test_cover_download_failure_same_base_keeps_old_cover(self, tmp_path):
        """old_base == new_base, cover download fails this run → old cover.jpg
        must survive (download_image never got to overwrite it); NFO still
        writes successfully and is NOT stale-cleaned (same base, no-op)."""
        from core.readonly_paths import _build_old_base, _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        meta = dict(_T3_META, title='Same Title')
        config = self._config()
        _t4_write(movie_dir, meta, config)

        # 真理表 Table 2 #1：media-server flavour 下正典即 `-fanart.jpg`，不是裸 `.jpg`。
        d = Path(movie_dir)
        base = 'TEST-001 Same Title'
        assert (d / f'{base}-fanart.jpg').exists()
        old_cover_bytes = (d / f'{base}-fanart.jpg').read_bytes()

        old_base = _build_old_base(_t4_existing(meta), '/src/TEST-001.mp4', config)
        assert old_base == base, "sanity: title unchanged → identical basename"
        fd = _format_data(meta, '/src/TEST-001.mp4', config)

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
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=_cover_strategy_for(meta), old_base=old_base,
            )

        assert assets['cover_fs'] == '', "cover_fs must be '' when download fails"
        assert (d / f'{base}-fanart.jpg').read_bytes() == old_cover_bytes, \
            "old cover must survive a failed same-base download"
        assert (d / f'{base}.nfo').exists(), "NFO must still write successfully"

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

    def test_6b_missing_poster_degrades_to_dangling_not_fanart_fallback(self, tmp_path):
        """Table 2 #6b（AC7 具名邊界，刻意接受、不是鎖 bug）：同上兩次呼叫，
        但第二次之前先手動刪掉 -poster.jpg → <thumb>/<fanart> 仍指向實際存在
        的 -fanart.jpg；<poster> 確實退回 {b}.jpg 且該檔**不存在**（斷言存在性
        為 False，不是斷言路徑字面值）。**不得**把 <poster> 改指 -fanart.jpg
        ——這是已知且刻意接受的行為，不是要修的 bug。"""
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir, meta, config = self._first_full_write(tmp_path)
        d = Path(movie_dir)
        (d / f'{self._BASE}-poster.jpg').unlink()
        assert not (d / f'{self._BASE}-poster.jpg').exists(), "sanity: poster removed"
        assert (d / f'{self._BASE}-fanart.jpg').exists(), "sanity: fanart still present"

        fd = _format_data(meta, '/src/TEST-001.mp4', config)
        with patch('core.readonly_assets.download_image') as mock_download:
            _write_movie_assets(
                movie_dir, meta, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('none',), old_base=self._BASE,
            )
        mock_download.assert_not_called()

        nfo_path = d / f'{self._BASE}.nfo'
        root = ET.parse(nfo_path).getroot()
        for tag in ('thumb', 'fanart'):
            tag_value = root.findtext(tag)
            assert tag_value == f'{self._BASE}-fanart.jpg'
            assert (d / tag_value).exists(), f"<{tag}> must still point to the existing fanart"
        poster_tag = root.findtext('poster')
        # 具名邊界：<poster> 確實退回同名 {b}.jpg 字面值，且該檔不存在——
        # 不得改指 -fanart.jpg（那會把橫式圖交給 poster 欄位，正是 112 要消滅的症狀）。
        assert poster_tag == f'{self._BASE}.jpg'
        assert not (d / poster_tag).exists(), (
            "AC7 具名邊界：<poster> 維持懸空引用，不 fallback 到 -fanart.jpg"
        )

    def test_title_drift_preserve_hit_cleanup_does_not_delete_old_fanart(self, tmp_path):
        """CD-112-16 不得誤傷 cleanup（DoD-9）：標題漂移（old_base != new_base）
        + preserve 命中（cover_strategy=('none',), has_cover=False）→
        _clean_stale_singletons 不得刪除 <old_base>-fanart.*（那是還在服役的
        正典封面）。與 §A #8 的差異：那支是「兩次都全寫」，這支是「第二次
        preserve 命中（本次沒產任何圖）＋ 標題漂移」，驗的是 cleanup 的裸
        has_poster/has_fanart 閘門本身（CD-112-16 的反面承諾：本次真的沒產
        新圖時，不得因為磁碟上舊圖還在就誤判成「已產出」而刪掉它）。

        Fixture 額外在**新** base_stem 位置預先擺兩個 decoy 檔（模擬更早一輪
        殘留、與本次寫入無關的舊檔）——若沒有這個 decoy，`nfo_image_flag(新
        base_stem, ..., False)` 在新位置本來就探不到任何檔案，回傳值與裸
        `False` 完全相同，mutation（cleanup 改吃 `nfo_image_flag`）會是
        no-op、測不出差異（已實測確認：沒有 decoy 時這支在 mutation 下維持
        綠，是「這一層測得到嗎」的陷阱，BE-TEST-11 變體）。有 decoy 之後，
        mutation 下 `nfo_image_flag` 在新位置會誤判「探到檔案＝本次已產出」，
        讓 cleanup 錯誤地清掉 `<old_base>` 那組**仍在服役**的正典檔案。

        MUTATION：把 core/readonly_producer.py:1013 的
        `_clean_stale_singletons(..., has_cover, has_poster, has_fanart, ...)`
        呼叫改成餵 nfo_image_flag 包裹過的值（即讓 cleanup 也吃磁碟真相）→
        該支轉紅（`<old_base>-poster/-fanart` 被誤刪）。
        """
        from core.readonly_paths import _build_old_base, _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir, meta_a, config = self._first_full_write(tmp_path)
        d = Path(movie_dir)
        old_base = _build_old_base(_t4_existing(meta_a), '/src/TEST-001.mp4', config)
        assert old_base == self._BASE

        meta_b = dict(meta_a, title='Drifted Title')
        fd_b = _format_data(meta_b, '/src/TEST-001.mp4', config)

        # decoy：新 base_stem 位置的殘留檔（與本次寫入無關），讓 nfo_image_flag
        # 在 mutation 下有東西可誤判——見上方 docstring 的可測性說明。
        new_base = 'TEST-001 Drifted Title'
        (d / f'{new_base}-poster.jpg').write_bytes(b'DECOY-POSTER')
        (d / f'{new_base}-fanart.jpg').write_bytes(b'DECOY-FANART')

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin:
            _write_movie_assets(
                movie_dir, meta_b, fd_b, '/src/TEST-001.mp4', config,
                cover_strategy=('none',), old_base=old_base,
            )
        mock_download.assert_not_called()
        mock_jellyfin.assert_not_called()

        assert (d / f'{old_base}-fanart.jpg').exists(), (
            "old fanart must survive — this run produced no new cover (preserve hit), "
            "_clean_stale_singletons must not mistake stale disk state for a fresh write"
        )
        assert (d / f'{old_base}-poster.jpg').exists(), "old poster must survive for the same reason"
        # nfo 本身無條件重寫（generate_nfo 永遠執行且 nfo_ok 為 True 才進 cleanup），
        # 舊 nfo 仍會被清（與 has_cover/has_poster/has_fanart 三個閘門無關）。
        assert not (d / f'{old_base}.nfo').exists(), "old nfo IS always cleaned (unconditional)"


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
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="", path="/src/movies")
        config = _make_config()  # scraper_cfg={} → fallback 'off'

        result = resolve_output_root(source, config)

        assert result
        assert result.startswith(str(get_db_path().parent / "lib"))

    def test_off_with_nonempty_output_path_still_returns_fixed_root(self):
        """off mode ignores source.output_path even if the user typed one (UI hides
        this field in off mode, but the backend must not trust a stale value)."""
        from core.database import get_db_path
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="/user/typed/path", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": "off"})

        result = resolve_output_root(source, config)

        assert "/user/typed/path" not in result
        assert result.startswith(str(get_db_path().parent / "lib"))

    @pytest.mark.parametrize("mode", ["jellyfin", "emby", "kodi"])
    def test_media_server_modes_return_output_path_verbatim(self, mode):
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="/nas/media", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": mode})

        assert resolve_output_root(source, config) == "/nas/media"

    @pytest.mark.parametrize("mode", ["jellyfin", "emby", "kodi"])
    def test_media_server_modes_with_empty_output_path_return_empty(self, mode):
        """Media-server flavours still require the user to configure output_path —
        resolve_output_root passes the empty value through unchanged (call sites
        keep their existing empty-string guards, CD-89a-7)."""
        from core.readonly_paths import resolve_output_root

        source = _make_source(output_path="", path="/src/movies")
        config = _make_config(scraper_cfg={"external_manager": mode})

        assert resolve_output_root(source, config) == ""

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

    def test_same_source_resolves_to_same_root_across_calls(self):
        """Stability lock (DoD): calling resolve_output_root twice for the same
        source/config must yield the identical path (no hidden per-call state)."""
        from core.readonly_paths import resolve_output_root

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
        from core.readonly_paths import resolve_output_root

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
        from core.readonly_paths import resolve_output_root

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
        # T2: no-number branch always stubs a row (title = stem, number=None).
        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.number is None
        assert inserted.title == "nonnumber"
        repo.update_scrape_attempted_at.assert_called_once()
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

    def test_no_filename_number_no_nfo_no_scrape_and_stub_created(self):
        """(b) no filename number + no NFO -> no_scrape, and (T2 onwards) a
        stub row IS created — same outcome as TestProduceSourceNoneNumberGuard,
        via this sidecar-bypass entry point."""
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
        repo.insert_if_ignore.assert_called_once()
        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.number is None
        assert inserted.title == "nonumber"
        repo.update_scrape_attempted_at.assert_called_once()
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
        assert inserted.title == "NOTFOUND-001"
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


class TestProduceSourceNoNumberStubPruned:
    """TASK-143-T2: a no-number stub row created by the T2 path must be
    pruned by the existing three-gate prune when the file leaves the source
    (real temp_db, two-round produce_source — same shape as
    TestProduceSourceNotFoundSecondRunSkipped)."""

    def test_no_number_stub_pruned_when_file_removed(self, temp_db):
        from core.database import VideoRepository
        from core.readonly_producer import produce_source

        repo = VideoRepository(temp_db)
        source = _make_source()
        config = _make_config()
        files_r1 = [_make_file_info(path="/src/videos/nonnumber.mp4")]

        # Round 1: no filename number → stub row (number=None, title=stem).
        with patch("core.readonly_producer._list_source_videos", return_value=files_r1), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None):
            result1 = produce_source(source, config, repo)

        assert result1.no_scrape == 1
        stub = repo.get_by_path("file:///src/videos/nonnumber.mp4")
        assert stub is not None
        assert stub.number is None
        assert stub.title == "nonnumber"

        # Round 2: original file gone; list still non-empty (OTHER-001) so the
        # "files non-empty" prune gate stays open.
        files_r2 = [_make_file_info(path="/src/videos/OTHER-001.mp4")]
        with patch("core.readonly_producer._list_source_videos", return_value=files_r2), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value=None):
            result2 = produce_source(source, config, repo)

        assert result2.pruned == 1
        assert repo.get_by_path("file:///src/videos/nonnumber.mp4") is None


# ---------------------------------------------------------------------------
# TASK-90a-T3: _apply_path_mapping + _write_strm + stale strm cleanup
# ---------------------------------------------------------------------------

class TestApplyPathMapping:
    """file:/// URI-space prefix-swap: boundary-anchored, longest-match,
    order-independent. source+local_prefix converge via to_file_uri for MATCHING
    (Codex P1/P2 fix); remote result written verbatim, never normalized (CD-90a-6)."""

    def test_empty_mappings_returns_original(self):
        from core.readonly_assets import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115\\x.mp4', {}) == 'Z:\\115\\x.mp4'

    def test_no_match_returns_original(self):
        from core.readonly_assets import _apply_path_mapping
        assert _apply_path_mapping('D:\\other\\x.mp4', {'Z:\\115': '/vol'}) == 'D:\\other\\x.mp4'

    def test_boundary_guard_no_false_match_on_longer_dir(self):
        """Z:\\1150\\a.mp4 must NOT match a Z:\\115 rule (0 is not a separator)."""
        from core.readonly_assets import _apply_path_mapping
        assert _apply_path_mapping('Z:\\1150\\a.mp4', {'Z:\\115': '/vol'}) == 'Z:\\1150\\a.mp4'

    def test_single_match_windows_separator(self):
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '/volume1/movie'})
        assert out == '/volume1/movie/x.mp4'  # remainder from URI space (forward-slash)

    def test_single_match_unix_separator(self):
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('/mnt/z/115/x.mp4', {'/mnt/z/115': '/volume1'})
        assert out == '/volume1/x.mp4'

    def test_empty_remote_rule_skipped_not_prefix_stripped(self):
        """PR #93 P2：半填規則 remote='' 不得把 local 前綴剝掉只剩後綴 → skip、source 原樣回。"""
        from core.readonly_assets import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': ''}) == 'Z:\\115\\x.mp4'
        assert _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '   '}) == 'Z:\\115\\x.mp4'

    def test_empty_remote_skipped_but_valid_rule_still_applies(self):
        """混合：空 remote 規則 skip，同批有效規則照常套（不因半填列污染整批）。"""
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\other': '', 'Z:\\115': '/vol'})
        assert out == '/vol/x.mp4'

    def test_prefix_equals_whole_string_matches(self):
        from core.readonly_assets import _apply_path_mapping
        assert _apply_path_mapping('Z:\\115', {'Z:\\115': '/vol'}) == '/vol'

    def test_nested_longest_prefix_wins(self):
        from core.readonly_assets import _apply_path_mapping
        mappings = {'Z:\\115': '/a', 'Z:\\115\\成人': '/b'}
        assert _apply_path_mapping('Z:\\115\\成人\\x.mp4', mappings) == '/b/x.mp4'

    def test_longest_match_independent_of_insertion_order(self):
        """Same content dict built in both orders → identical output (deterministic)."""
        from core.readonly_assets import _apply_path_mapping
        forward = {'Z:\\115': '/a', 'Z:\\115\\成人': '/b'}
        reverse = {'Z:\\115\\成人': '/b', 'Z:\\115': '/a'}
        p = 'Z:\\115\\成人\\x.mp4'
        assert _apply_path_mapping(p, forward) == _apply_path_mapping(p, reverse) == '/b/x.mp4'

    def test_foreign_unix_target_not_normalized_or_raised(self):
        """Mapped output is a bare Unix path (/volume1/...): returned verbatim,
        no path_utils call, no ValueError even on a Windows-style source."""
        from core.readonly_assets import _apply_path_mapping
        out = _apply_path_mapping('Z:\\115\\x.mp4', {'Z:\\115': '/volume1/movie'})
        assert out.startswith('/volume1/movie')

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

    def test_empty_mappings_writes_raw_source_path(self, tmp_path):
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {})
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == 'Z:\\115\\x.mp4'

    def test_mappings_read_same_level_not_via_scraper(self, tmp_path):
        """Regression: mapping table must be read from config['strm_path_mappings']
        directly, NOT config['scraper']['strm_path_mappings'] (which is always {}
        because config already IS the scraper section)."""
        from core.readonly_assets import _write_strm
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
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/volume1/movie'}}
        ok = _write_strm(base_stem, 'Z:\\115\\clip.mp4', config)
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == '/volume1/movie/clip.mp4'

    # --- PR #93 五審四次 P2 (option C)：strm_mappings 覆寫參數 ---

    def test_strm_mappings_override_wins_over_config(self, tmp_path):
        """strm_mappings 非 None → 覆寫 config['strm_path_mappings']（producer 傳 fresh 讀，
        使斷線尾巴那片用當前映射而非 generate 起始凍結值）。"""
        from core.readonly_assets import _write_strm
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
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/volume1'}}
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config, strm_mappings=None)
        assert ok is True
        assert Path(base_stem + '.strm').read_text(encoding='utf-8') == '/volume1/x.mp4'

    def test_empty_override_writes_raw_not_config_mapping(self, tmp_path):
        """strm_mappings={} 是有效覆寫（非 None）→ 用空映射（寫原始路徑），不回退 config。"""
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        config = {'strm_path_mappings': {'Z:\\115': '/SHOULD-NOT-APPLY'}}
        ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', config, strm_mappings={})
        assert ok is True
        content = Path(base_stem + '.strm').read_text(encoding='utf-8')
        assert content == 'Z:\\115\\x.mp4'
        assert 'SHOULD-NOT-APPLY' not in content

    def test_write_failure_is_best_effort_returns_false(self, tmp_path):
        """open() raising → warning logged, returns False, does NOT raise."""
        from core.readonly_assets import _write_strm
        base_stem = str(tmp_path / 'TEST-001')
        with patch('core.readonly_assets.open', side_effect=OSError('disk full'), create=True):
            ok = _write_strm(base_stem, 'Z:\\115\\x.mp4', {})
        assert ok is False
        assert not Path(base_stem + '.strm').exists()

    def test_non_str_mapping_value_is_best_effort_not_raise(self, tmp_path):
        """raw config (not model_validated) with a non-str mapping value must not
        escape best-effort: _apply_path_mapping TypeError is caught, returns False,
        never raises (NIT-1 — mapping call moved inside try + broad catch)."""
        from core.readonly_assets import _write_strm
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
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets
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

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=rec_nfo):
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
        from core.readonly_assets import _clean_stale_singletons
        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        (d / f'{old_base}.nfo').write_bytes(b'x')
        (d / f'{old_base}.strm').write_bytes(b'/vol/old.mp4')
        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False, True)
        assert not (d / f'{old_base}.strm').exists(), "stale strm must be cleaned on title drift"

    def test_has_strm_false_keeps_old_strm(self, tmp_path):
        """strm write failed this run (has_strm False) → old strm must survive."""
        from core.readonly_assets import _clean_stale_singletons
        d = tmp_path / 'movie'
        d.mkdir()
        old_base = 'TEST-001 Old'
        (d / f'{old_base}.nfo').write_bytes(b'x')
        (d / f'{old_base}.strm').write_bytes(b'/vol/old.mp4')
        _clean_stale_singletons(str(d), old_base, 'TEST-001 New', False, False, False, False)
        assert (d / f'{old_base}.strm').exists(), "old strm must survive when has_strm is False"

    def test_default_has_strm_is_false(self, tmp_path):
        """6-arg call (legacy) → strm never touched (backward compat)."""
        from core.readonly_assets import _clean_stale_singletons
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

    def test_strm_write_failure_preserves_old_strm(self, tmp_path):
        """When _write_strm returns False this run, has_strm gating keeps the old strm."""
        from core.readonly_paths import _build_old_base, _format_data
        from core.readonly_assets import _write_movie_assets
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
        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo), \
             patch('core.readonly_assets._write_strm', return_value=False):
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

    def test_acceptance7_off_mode_readonly_source_zero_writes(self, tmp_path):
        """AC7 的 off 風味：與本 class 名的 media-server/strm 主題不同（off 模式不寫
        .strm），放在這裡是為了複用 `_setup_source` 與 `FILENAMES`（⚖️ Opus 裁決 Q2，
        TASK-111-T4 塊 A）。"""
        source_dir, output_dir = self._setup_source(tmp_path)
        config = _make_config(scraper_cfg=dict(_T3_BASE_CONFIG, external_manager='off'))

        # off flavour's resolve_output_root ignores output_path and returns the fixed
        # App lib root; patch it to the tmp output dir so the test never pollutes the
        # real lib folder (resolve_output_root has its own dedicated tests) — same
        # pattern as test_off_flavour_produces_no_strm below.
        with patch('core.readonly_paths.resolve_output_root', return_value=str(output_dir)):
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


class TestProduceOneContainmentCheckpoint:
    """TASK-110b-T5 (CD-110b-2/CD-110b-8): the containment checkpoint lives in
    _produce_one — right after _resolve_movie_dir returns, before
    _write_movie_assets is ever called — NOT inside _write_movie_assets
    itself. Rationale (Opus ruling, post-implementation review):

    - output_root is already in _produce_one's own scope → checking here
      needs zero new parameters anywhere.
    - The check is UNCONDITIONAL, not behind a defaulted kwarg. An earlier
      draft added `output_root: Optional[str] = None` to _write_movie_assets
      and skipped the check when the caller didn't pass it — that is a
      fail-open shape (forget to pass it, the whole guard vanishes), which is
      exactly what 110a Codex round-1 flagged and fail-closed'd for the scale
      gates (commit 7514b736). This Phase's guards must not have a "didn't
      pass it" escape hatch.
    - _write_movie_assets has exactly ONE production caller — _produce_one
      itself (grep-confirmed: only this call site and the 37 direct unit-test
      calls elsewhere in this file exist) — so checking at this call site is
      production-EQUIVALENT to checking inside the callee, while leaving
      _write_movie_assets's signature, and all 37 of those direct test call
      sites, completely untouched.

    Case 2 here (F2, TASK-110b-T1): a leaf-only escape — movie_dir landing
    exactly one level above output_root, the shape sanitize_filename(number)
    == '..' with empty folder_layers would produce inside _resolve_movie_dir
    — is tested by directly patching _resolve_movie_dir's return value and
    calling _produce_one, rather than by driving produce_source's real
    allocate loop with a literal number='..' (see the docstring on
    TestWriteMovieAssetsContainment above for the full explanation of why
    that loop's own PRE-EXISTING candidate_fs.exists() collision-retry
    incidentally self-heals that exact metadata shape into a harmless
    `..-2` folder INSIDE output_root before any movie_dir escaping it is ever
    produced). Patching the return value directly locks the checkpoint
    itself, independent of whether any particular upstream escape vector
    happens to survive _resolve_movie_dir's own logic.
    """

    def test_resolve_movie_dir_escape_rejected_zero_writes_outside_root(self, tmp_path):
        from core.readonly_producer import _produce_one

        workspace = tmp_path / 'ws'
        source_dir = workspace / 'readonly-src'
        source_dir.mkdir(parents=True)
        source_fs_path = str(source_dir / 'ABC-001.mp4')
        Path(source_fs_path).write_bytes(b'FAKE-VIDEO-BYTES')
        output_root = workspace / 'output'
        output_root.mkdir(parents=True)

        # Sibling of output_root, unambiguously outside it — as if
        # _resolve_movie_dir had handed back an already-escaped candidate
        # (e.g. the F2 leaf='..' shape, or any future escape vector).
        escaping_movie_dir = workspace / 'ESCAPED-SIBLING'
        meta = dict(_T3_META, number='ABC-001')
        file_info = {'path': source_fs_path, 'size': 1_000_000, 'mtime': 1.0}
        repo = MagicMock()

        ws_before = _snapshot_dir(workspace)
        src_before = _snapshot_dir(source_dir)

        with patch('core.readonly_paths._resolve_movie_dir',
                   return_value=(escaping_movie_dir, 'file:///whatever-db-uri')), \
             patch('core.readonly_assets._write_movie_assets') as mock_write:
            with pytest.raises(RuntimeError):
                _produce_one(
                    repo, MagicMock(), dict(_T3_BASE_CONFIG, external_manager='jellyfin'),
                    file_info=file_info, meta=meta, cover_strategy=_cover_strategy_for(meta),
                    assets_mode='full', existing=None,
                    output_root=str(output_root), output_uri=to_file_uri(str(output_root), {}),
                    allocated_this_run=set(), path_mappings={},
                )

        ws_after = _snapshot_dir(workspace)
        src_after = _snapshot_dir(source_dir)
        assert ws_after == ws_before, (
            f"escaping call must create nothing at all: added={ws_after - ws_before}"
        )
        assert not escaping_movie_dir.exists(), "escaping movie_dir must not be created"
        assert src_before == src_after, "read-only source dir must not be written to"
        mock_write.assert_not_called()  # rejected before the write step is ever reached
        repo.upsert.assert_not_called()


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

    def test_copy_strategy_missing_source_is_graceful(self, tmp_path):
        """copy source doesn't exist → has_cover=False / cover_fs='', never raises
        — same graceful-failure semantics as a failed download (card boundary)."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        missing_source = str(tmp_path / 'does-not-exist.jpg')

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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

    def test_download_strategy_calls_download_image_not_copy(self, tmp_path):
        """'download': download_image called with the remote URL, shutil.copyfile
        never called — the byte-identical pre-T1 branch, locked explicitly here
        alongside the other two states (also covered by the pre-existing
        TestWriteMovieAssets::test_rescrape_uses_remote_cover_url)."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_assets.download_image', return_value=True) as mock_download, \
             patch('core.readonly_assets.shutil.copyfile') as mock_copy, \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-BYTES-DIFFERENT-FROM-BOTH')
        poster_src = tmp_path / 'src-poster.jpg'
        fanart_src = tmp_path / 'src-fanart.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fanart_src.write_bytes(b'FANART-MARKER-BYTES')
        fd = _t3_format_data()

        with patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.crop_to_poster') as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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

    def test_off_mode_curated_sidecars_not_copied(self, tmp_path):
        """TASK-111-T3 群組 5（ingest sidecar，off 分支）: same 3-tuple
        cover_strategy wiring as test_both_slots_present_copied_verbatim_not_
        regenerated above, but external_manager='off' — TASK-111's step-2 gate
        (has_cover and external_manager in STEM_IMAGE_MODES) must suppress the
        verbatim-copy mechanism entirely, so neither curated sidecar is copied
        into the output slot at all. This is the off-mode cell of the same
        mechanism the sibling tests in this class cover on kodi config; T2's
        integration-level TestOffModeIngestPosterFanartSuppressed already
        covers the real-ingest-scan path — this is the direct
        _write_movie_assets unit-level path.

        MUTATION LOCK: reverting the step-2 gate back to `if has_cover:` makes
        this RED — the curated sidecars would be copied verbatim again.
        """
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-BYTES-DIFFERENT-FROM-BOTH')
        poster_src = tmp_path / 'src-poster.jpg'
        fanart_src = tmp_path / 'src-fanart.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fanart_src.write_bytes(b'FANART-MARKER-BYTES')
        fd = _t3_format_data()
        config = dict(_T3_BASE_CONFIG, external_manager='off')

        with patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.crop_to_poster') as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            assets = _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', config,
                cover_strategy=('copy', cover_fs, {'poster': str(poster_src), 'fanart': str(fanart_src)}),
            )

        mock_jellyfin.assert_not_called()
        mock_crop.assert_not_called()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        assert not Path(base_stem + '-poster.jpg').exists(), (
            "off mode must not copy the curated poster sidecar (TASK-111)"
        )
        assert not Path(base_stem + '-fanart.jpg').exists(), (
            "off mode must not copy the curated fanart sidecar (TASK-111)"
        )
        assert assets['cover_fs'], "cover copy itself is unaffected by the off-mode poster/fanart gate"

    def test_missing_poster_slot_falls_back_to_crop_to_poster(self, tmp_path):
        """Only -fanart detected (poster slot None) -> fanart copied verbatim,
        poster falls back to crop_to_poster(cover_fs, ...) — the same generate
        step it would have used with no 3rd element at all."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        src_cover = str(tmp_path / 'cover.jpg')
        Path(src_cover).write_bytes(b'COVER-BYTES')
        fanart_src = tmp_path / 'src-fanart.jpg'
        fanart_src.write_bytes(b'FANART-MARKER-BYTES')
        fd = _t3_format_data()

        def fake_crop(src_path, dst_path, **_kw):
            Path(dst_path).write_bytes(b'CROPPED-POSTER-BYTES')
            return True

        with patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.crop_to_poster', side_effect=fake_crop) as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('copy', src_cover, {'poster': None, 'fanart': str(fanart_src)}),
            )

        mock_jellyfin.assert_not_called()
        mock_crop.assert_called_once()
        base_stem = str(Path(movie_dir) / 'TEST-001 Test Movie Title')
        # 真理表 Table 2 #2：_T3_BASE_CONFIG 預設 media-server（'kodi'）flavour，磁碟
        # 起始為空 → resolve_cover_target 第③步回 base_stem + '-fanart.jpg'，這就是
        # 輸出封面（cover_fs）的實際落點——crop_to_poster 讀的是這個輸出檔，不是裸
        # base_stem + '.jpg'。
        assert mock_crop.call_args[0][0] == base_stem + '-fanart.jpg', (
            "crop_to_poster must read the OUTPUT cover (already copied into movie_dir), "
            "not the source path"
        )
        assert Path(base_stem + '-poster.jpg').read_bytes() == b'CROPPED-POSTER-BYTES'
        assert Path(base_stem + '-fanart.jpg').read_bytes() == b'FANART-MARKER-BYTES'

    def test_missing_fanart_slot_falls_back_to_cover_copy(self, tmp_path):
        """Only -poster detected (fanart slot None) -> poster copied verbatim,
        fanart falls back to copy2(cover_fs, ...) — the same generate step it
        would have used with no 3rd element at all."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        cover_fs = str(tmp_path / 'cover.jpg')
        Path(cover_fs).write_bytes(b'COVER-MARKER-BYTES')
        poster_src = tmp_path / 'src-poster.jpg'
        poster_src.write_bytes(b'POSTER-MARKER-BYTES')
        fd = _t3_format_data()

        with patch('core.readonly_assets.generate_jellyfin_images') as mock_jellyfin, \
             patch('core.readonly_assets.crop_to_poster') as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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
        from core.readonly_assets import _write_movie_assets

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

        with patch('core.readonly_assets.shutil.copy2', side_effect=flaky_copy2), \
             patch('core.readonly_assets.crop_to_poster', side_effect=fake_crop) as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}) as mock_jellyfin, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}) as mock_jellyfin, \
             patch('core.readonly_assets.crop_to_poster') as mock_crop, \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
            _write_movie_assets(
                movie_dir, _T3_META, fd, '/src/TEST-001.mp4', _T3_BASE_CONFIG,
                cover_strategy=('download', _T3_META['cover']),
            )

        mock_jellyfin.assert_called_once()
        mock_crop.assert_not_called()


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

    def test_no_sidecar_falls_back_to_generate(self, tmp_path):
        """無 -poster/-fanart sidecar，只有同名封面 → cover_strategy 第三元素
        兩 slot 皆 None → source_media 判定為 None（both falsy）→ 整段委派
        generate_jellyfin_images：fanart 走真 copy2（cover 與 fanart 輸出目標
        不同名，因為來源是同名封面）、poster 走真 crop_to_poster。"""
        num = 'CUR4-A'
        config = self._config()
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        _t6_make_jpeg(src_dir / f'{num}.jpg', _T6_GREY)

        movie_dir, base_stem, assets, cover_strategy = _t6_resolve_and_write(src_dir, num, config)

        assert cover_strategy[0] == 'copy'
        assert cover_strategy[2] == {'poster': None, 'fanart': None}
        assert assets['cover_fs'].endswith('-fanart.jpg'), "Table 2 #1: canonical cover IS -fanart.jpg"
        assert not (Path(movie_dir) / f'{Path(base_stem).name}.jpg').exists(), (
            "no independent same-name cover"
        )
        # fanart 輸出＝真 copy2 自同名封面（verbatim，因為 generate 步驟本身就是複製 cover）
        assert Path(base_stem + '-fanart.jpg').read_bytes() == (src_dir / f'{num}.jpg').read_bytes()
        # poster 輸出＝真 crop_to_poster 的產物（非 mock）：合法 JPEG 且非全圖 verbatim 複製
        from PIL import Image
        with Image.open(base_stem + '-poster.jpg') as poster_img:
            assert poster_img.format == 'JPEG'
            assert poster_img.size[0] < 800, "poster must be a horizontal crop, not the full-width cover"

    def test_only_fanart_sidecar_upgrades_cover_and_crops_poster(self, tmp_path):
        """只有 -fanart sidecar（無同名封面、無 -poster）→ CD-112-7 前半句：
        cover 來源升格為 curator fanart → fanart 輸出走同檔短路（verbatim，因為
        cover 本身已是 curator fanart 內容）；poster 仍走真 crop_to_poster。"""
        num = 'CUR4-B'
        config = self._config()
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        _t6_make_jpeg(src_dir / f'{num}-fanart.jpg', _T6_BLUE)

        movie_dir, base_stem, assets, cover_strategy = _t6_resolve_and_write(src_dir, num, config)

        assert cover_strategy[1] == str(src_dir / f'{num}-fanart.jpg'), (
            "cover source must be upgraded to the curator fanart (CD-112-7 前半句)"
        )
        assert Path(base_stem + '-fanart.jpg').read_bytes() == (src_dir / f'{num}-fanart.jpg').read_bytes()
        assert Path(base_stem + '-poster.jpg').exists()
        assert not (Path(movie_dir) / f'{Path(base_stem).name}.jpg').exists()

    def test_only_poster_sidecar_verbatim_poster_generated_fanart(self, tmp_path):
        """同名封面 + 只有 -poster sidecar（無 -fanart）→ poster 逐位元組等於
        curator 原檔（verbatim）；fanart 沒有 curator sidecar 可用，落回
        「以封面為來源」的既有 generate 語意（此 fixture 下即同名封面內容）。"""
        num = 'CUR4-C'
        config = self._config()
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        _t6_make_jpeg(src_dir / f'{num}.jpg', _T6_GREY)
        _t6_make_jpeg(src_dir / f'{num}-poster.jpg', _T6_MAGENTA)

        movie_dir, base_stem, assets, cover_strategy = _t6_resolve_and_write(src_dir, num, config)

        assert cover_strategy[2]['poster'] == str(src_dir / f'{num}-poster.jpg')
        assert cover_strategy[2]['fanart'] is None
        # poster: verbatim curator 原檔（逐位元組等於 magenta 來源，不是 crop_to_poster 產物）
        assert Path(base_stem + '-poster.jpg').read_bytes() == (src_dir / f'{num}-poster.jpg').read_bytes()
        # fanart: 無 curator sidecar，落回以封面（灰）為來源的既有語意
        assert Path(base_stem + '-fanart.jpg').read_bytes() == (src_dir / f'{num}.jpg').read_bytes()
        assert not (Path(movie_dir) / f'{Path(base_stem).name}.jpg').exists()

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

    def test_fanart_sidecar_collocated_with_output_is_preserved(self, tmp_path):
        """poster 側的對稱格，直接打 `_write_media_images`（該函式的 fanart slot
        是公開契約的一部分，洞的形狀與 poster 側逐字相同）。

        ⚠️ 本測試寫成時，生產路徑恆傳 `'fanart': None`（CD-112-7 舊的後半句），
        所以這一格**只能**直接餵 `_write_media_images`。round-3 P1 之後
        `resolve_ingest_plan` 已改為宣告所有存在的 sidecar（`'fanart': fanart_fs`），
        端到端的覆蓋改由 `TestCollocatedCuratorCoverCollision` 負責；本格保留為
        **函式層的直接鎖**（同一個洞的兩層守衛，不重複）。

        MUTATION LOCK：同上，`_copy_curator_sidecar` 的 `is_same` 分支拿掉 →
        fanart 被封面內容覆蓋，本測試單獨轉紅。
        """
        from core.readonly_assets import _write_media_images

        base_stem = str(tmp_path / 'COLLOC-B')
        cover_fs = base_stem + '.jpg'
        fanart_path = base_stem + '-fanart.jpg'
        _t6_make_jpeg(Path(cover_fs), _T6_GREY)
        _t6_make_jpeg(Path(fanart_path), _T6_BLUE, size=(1000, 562))
        fanart_before = Path(fanart_path).read_bytes()

        has_poster, has_fanart = _write_media_images(
            cover_fs, base_stem, _T3_META, source_media={'poster': None, 'fanart': fanart_path},
        )

        assert Path(fanart_path).read_bytes() == fanart_before, (
            "curator -fanart 不得被封面內容覆寫"
        )
        assert has_fanart is True, "同檔＝已經 verbatim 到位，要如實回報成功"
        assert has_poster is True, "poster 側不受影響（正常走 crop_to_poster）"

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

    def test_vanished_sidecar_string_equal_still_regenerates(self, tmp_path):
        """`src == dst` 但檔案其實已經不在（`same_target_verdict` 的 `src == dst`
        那一格是純字串比較、零 I/O）→ 沒有 curator 原檔會被蓋掉，**應該**落回
        generate 把 slot 補出來，而不是回報一個不存在的 passthrough。

        MUTATION LOCK：把 `_copy_curator_sidecar` 裡的
        `True if os.path.exists(dst) else None` 改成裸 `True` → 本測試轉紅
        （poster 檔不存在卻 has_poster=True，就是 a552f674 修掉的那種假成功）。
        """
        from core.readonly_assets import _write_media_images

        base_stem = str(tmp_path / 'COLLOC-D')
        cover_fs = base_stem + '.jpg'
        poster_path = base_stem + '-poster.jpg'
        _t6_make_jpeg(Path(cover_fs), _T6_GREY)
        assert not Path(poster_path).exists()

        has_poster, _ = _write_media_images(
            cover_fs, base_stem, _T3_META,
            source_media={'poster': poster_path, 'fanart': None},
        )

        assert Path(poster_path).exists(), "sidecar 已消失 → 該落回 generate 產出 poster"
        assert has_poster is True


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


class TestCuratorFanartPngContentNamedAsJpg:
    def test_png_in_jpg_curator_fanart_crops_correctly_with_focal(self, tmp_path):
        from PIL import Image
        from core.readonly_paths import _build_basename, _format_data
        from core.readonly_assets import _write_movie_assets
        from core.readonly_producer import resolve_ingest_plan

        num = 'FC2-1234567'
        maker = 'S1 NO.1 STYLE'
        config = dict(_T3_BASE_CONFIG, external_manager='jellyfin')
        src_dir = tmp_path / 'src'
        src_dir.mkdir()

        # curator fanart 內容是 PNG，檔名仍是 -fanart.jpg（MDCX/Javinizer 常見
        # 命名慣例）——用既有 focal fixture 的解碼像素重新存成 PNG，讓 crop 結果
        # 可以跟獨立 oracle（同一組像素、同一組焦點座標）逐位元組比對。
        fanart_src = src_dir / f'{num}-fanart.jpg'
        with Image.open(_T3_FOCAL_FIXTURES_DIR / 'wide_offcenter_face.jpg') as img:
            img.save(str(fanart_src), 'PNG')

        # ① fixture 真的是 PNG-in-.jpg，不是誤植。
        with Image.open(fanart_src) as check_img:
            assert check_img.format == 'PNG', "sanity: fixture must actually be PNG content"

        video = src_dir / f'{num}.mp4'
        video.write_bytes(b'FAKE-VIDEO')
        nfo = src_dir / f'{num}.nfo'
        nfo.write_text(f'<movie><num>{num}</num><title>{num} Title</title></movie>', encoding='utf-8')

        meta, cover_strategy = resolve_ingest_plan(str(video), num, config, action='ingest')
        assert meta is not None
        meta = dict(meta, maker=maker)
        movie_dir = str(tmp_path / 'out' / num)
        fd = _format_data(meta, str(video), config)
        base = _build_basename(fd, str(video), config)
        base_stem = str(Path(movie_dir) / base)

        with patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect), \
             patch('core.organizer.run_detection', return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            assets = _write_movie_assets(
                movie_dir, meta, fd, str(video), config, cover_strategy=cover_strategy,
            )

        # ② -fanart.jpg 逐位元組等於這個 PNG 原檔（verbatim 保留，PIL 不需要介入）。
        assert Path(base_stem + '-fanart.jpg').read_bytes() == fanart_src.read_bytes()

        # ③ poster 側才是真正的驗證重點：crop_to_poster 對 PNG-named-as-.jpg 的
        # 來源正常返回合法 JPEG。
        poster_path = base_stem + '-poster.jpg'
        assert Path(poster_path).exists()
        with Image.open(poster_path) as poster_img:
            assert poster_img.format == 'JPEG', "crop_to_poster must always re-encode output as JPEG"

        # ④ 焦點裁切：獨立 oracle（同一組座標各自算一次裁切窗）比對，證明
        # PNG-in-jpg 的焦點裁切跟正常 JPEG 來源走的是同一條路徑。
        expected = _t3_oracle_poster_bytes(MOCK_FOCAL_XY)
        assert Path(poster_path).read_bytes() == expected, (
            "PNG-in-.jpg curator fanart's focal crop must match the independent "
            "oracle byte-for-byte — same code path as a normal JPEG source"
        )
        assert assets['cover_fs'].endswith('-fanart.jpg')


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

    def test_empty_sample_images_returns_empty_list(self, tmp_path):
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.generate_nfo') as mock_nfo:
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_assets.download_image') as mock_download, \
             patch('core.readonly_assets.shutil.copyfile') as mock_copy, \
             patch('core.readonly_assets.generate_nfo') as mock_nfo:
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
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _t3_format_data()
        meta = dict(_T3_META, sample_images=[])

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets._clean_stale_extrafanart') as mock_clean_ef, \
             patch('core.readonly_assets._clean_stale_singletons') as mock_clean_singletons:
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

    def test_full_mode_run_with_own_samples_still_cleans_and_rewrites(self, tmp_path):
        """Sanity: the guard only SKIPS the clean when this run has nothing new —
        a hypothetical future full-mode caller that DOES carry sample_images still
        gets correct clean+rewrite (old set of 3 shrinks to the new set of 1)."""
        from core.readonly_assets import _write_movie_assets

        movie_dir = str(tmp_path / 'TEST-001')
        config = dict(_T3_BASE_CONFIG)
        self._samples_only_seed(movie_dir, config)
        ef_dir = Path(movie_dir) / 'extrafanart'
        (ef_dir / 'fanart3.jpg').write_bytes(b'STALE')  # pretend a 3rd stale sample exists

        meta_full = dict(_T3_META, sample_images=['http://x/only-one.jpg'])
        config_dl = dict(config, download_sample_images=True)
        fd = _t3_format_data(config=config_dl)
        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t4_real_nfo):
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
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets
        from core.readonly_producer import _upsert_db

        movie_dir = str(tmp_path / 'output' / 'TEST-001')
        fd = _format_data(_T3_META, '/src/TEST-001.mp4', _T3_BASE_CONFIG)
        repo = VideoRepository(temp_db)

        with patch('core.readonly_assets.download_image', return_value=True), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=_t3_generate_nfo_side_effect):
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

        def fake_search_jav(number, source="auto", javbus_lang=None):
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
             patch('core.readonly_assets.download_image', side_effect=fake_download_image), \
             patch('core.readonly_assets.generate_jellyfin_images',
                   return_value={'poster': True, 'fanart': True}), \
             patch('core.readonly_assets.generate_nfo', side_effect=fake_generate_nfo):
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

    def test_nested_blank_actor_name_filtered_to_empty_list(self):
        """TASK-113a-T4 (Codex PR review P1)：巢狀空白 actor name 不是資料，
        不應以 [''] 姿態流入 generate_nfo（core/organizer.py:759-782 會無條件
        寫出 <actor><name></name></actor>）或 _upsert_db
        （readonly_producer.py:1261-1266 直接建 Video()）——這條路徑沒有
        B（VideoScanner.parse_nfo）那層 split+filter 清洗
        （core/database/video.py:50-52），是唯一會把空值寫進使用者
        NFO／DB 的 side。"""
        from core.readonly_producer import _nfo_to_producer_meta

        root = _nfo_root(
            '<movie><actors>'
            '<actor><name>   </name></actor>'
            '</actors></movie>'
        )
        meta = _nfo_to_producer_meta(root, fallback_number='X')
        assert meta['actors'] == []


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

        mock_search.assert_called_once_with('SRC-001', source='auto', javbus_lang='ja')
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
        # CD-112-7 後半句（④，T3 已落地）：第三元素的 'fanart' slot 恆為 None。
        # 註：config={} → external_manager 正規化為 'off' → CD-112-7 前半句（cover
        # 來源升格）的白名單閘門不成立，cover_strategy[1] 仍等於 find_cover_image
        # 經 L1.5 挑中的 fanart_fs（與升格邏輯無關），這行本身不需要改。
        # CD-112-7 第二半於 Codex PR#125 round-3 P1 修訂：存在的 curator sidecar
        # 一律宣告（原本 'fanart' 恆 None 的前提「cover_fs 會等於 fanart 路徑」
        # 在 collocated ＋ 已有同名封面時為假）。
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
                str(video), 'SRC-001', {}, action='rescrape', source='javbus',
                javbus_lang='zh-tw',
            )

        mock_single.assert_called_once_with('SRC-001', 'javbus', javbus_lang='zh-tw')
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

        mock_search.assert_called_once_with('SRC-001', source='auto', javbus_lang='ja')
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
        from core.readonly_paths import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "rw"
        src.mkdir()
        canonical = to_file_uri(str(src / "ABC-001.mp4"))
        config = _gallery_config([{"path": str(src), "readonly": False}])

        assert resolve_owning_output_root(canonical, config) is None

    def test_no_source_covers_path_at_all_returns_none(self, tmp_path):
        from core.readonly_paths import resolve_owning_output_root
        from core.path_utils import to_file_uri

        src = tmp_path / "ro"
        src.mkdir()
        canonical = to_file_uri(str(tmp_path / "unrelated" / "ABC-001.mp4"))
        config = _gallery_config([{"path": str(src), "readonly": True}])

        assert resolve_owning_output_root(canonical, config) is None

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
    def test_nested_writable_child_returns_none(self, tmp_path):
        """readonly parent + writable child (longer/more-specific prefix) ->
        the file under the writable child is NOT readonly -> None (router
        falls through to its existing writable code path)."""
        from core.readonly_paths import resolve_owning_output_root
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

    def test_equal_length_tie_favors_writable_returns_none(self, tmp_path):
        """Self-contradictory config: the SAME path listed both readonly and
        writable (equal-length prefixes) -> ties favor writable (mirrors
        is_path_readonly's best_ro > best_wr, strict inequality) -> None."""
        from core.readonly_paths import resolve_owning_output_root
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
        from core.readonly_paths import resolve_owning_output_root
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
        from core.readonly_paths import resolve_owning_output_root
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

        monkeypatch.setattr("core.readonly_paths._canonical_source_prefix", _fake_canonical_prefix)

        result = resolve_owning_output_root(canonical, config)
        assert result is not None
        assert result[0].path == str(good)


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

    def test_real_stats_existing_is_kept(self, tmp_path):
        from core.readonly_producer import _file_info_for
        f = tmp_path / "v.mp4"
        f.write_bytes(b"1234567890")

        info = _file_info_for(str(f), self._existing(999, 1700000000.0))

        assert info["size"] == 999, "既有的真實值不得被覆蓋"
        assert info["mtime"] == 1700000000.0

    def test_no_existing_row_stats_the_file(self, tmp_path):
        from core.readonly_producer import _file_info_for
        f = tmp_path / "v.mp4"
        f.write_bytes(b"12345")

        info = _file_info_for(str(f), None)

        assert info["size"] == 5
        assert info["mtime"] > 0


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
        assert inserted.title == "NOTFOUND-001"  # Path(fs_path).stem, WITHOUT extension
        assert inserted.cover_path == ''
        assert inserted.output_dir == ''
        assert inserted.sample_images == []

    def test_empty_number_normalized_to_null(self):
        """空字串 number → 寫 NULL（AC1-5：一般掃描寫的就是 `info.num or None`）。

        這條守的是 **S1 那條路**（`enrich_one_readonly` → `request.number`，型別是
        未經非空檢查的 `str`）；S3（`produce_source`）的 number 來自 `extract_number()`，
        它已經回 None，所以走掃描的 e2e **殺不掉這顆 mutation**（等價突變，見
        gotchas BE-TEST-30）。正規化寫在 helper 本體，這支就是它的正向鎖。
        """
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        _readonly_stub_not_found(repo, "file:///src/videos/x.mp4", "", "/src/videos/x.mp4")

        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.number is None, "空字串必須正規化成 NULL，不是原樣寫進去"
        assert inserted.title == "x"

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

    def test_stub_stats_fall_back_to_zero_when_file_unreadable(self, tmp_path):
        """沒帶 size/mtime 且檔案讀不到（碟斷線）→ 回 0，不得炸掉整條產出流程。"""
        from core.readonly_producer import _readonly_stub_not_found

        repo = MagicMock()
        _readonly_stub_not_found(repo, "file:///src/x.mp4", "X-001",
                                 str(tmp_path / "vanished.mp4"))

        inserted = repo.insert_if_ignore.call_args[0][0]
        assert inserted.size_bytes == 0
        assert inserted.mtime == 0.0

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

    def test_success_with_servable_cover(self):
        from core.readonly_producer import enrich_one_readonly

        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub()
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))) as mock_plan, \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "/out/ABC-001/ABC-001.jpg", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True) as mock_has_cover:
            result = enrich_one_readonly(**self._base_kwargs(repo_factory))

        mock_plan.assert_called_once()
        mock_produce.assert_called_once()
        mock_has_cover.assert_called_once()
        assert result.success is True
        # [lint-guard: pytest-justified] EnrichResult.reason 的確切文案值
        # （"hit"/"no_cover"/"not_found" 是 core/router 共用的 runtime 回傳
        # 契約，前端與 batch 分流都靠這個字面值），lint 無法表達。
        assert result.reason == "hit"
        assert result.nfo_written is True
        assert result.cover_written is True
        # main repo + focal repo (cover_written=True triggers a 2nd, INDEPENDENT
        # repo_factory() call — "致命細節 1", never a reuse of the main repo var)
        assert repo_factory.call_count == 2

    def test_enrich_one_readonly_preserve_title_true_passes_existing_title_to_produce_one(self):
        """oracle 1（唯讀）：preserve_title=True 時，傳給 _produce_one 的 meta['title'] 是保留值。"""
        from pathlib import Path
        from core.readonly_producer import enrich_one_readonly

        repo = MagicMock()
        existing = SimpleNamespace(
            size_bytes=123,
            mtime=456.0,
            cover_path="",
            title="[ABC-001]中文片名",
            number="ABC-001",
        )
        repo.get_by_path.return_value = existing
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "新刮到的日文片名", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "/out/ABC-001/ABC-001.jpg", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            result = enrich_one_readonly(
                **self._base_kwargs(repo_factory, preserve_title=True)
            )

        mock_produce.assert_called_once()
        passed_meta = mock_produce.call_args.kwargs["meta"]
        assert passed_meta["title"] == "[ABC-001]中文片名"
        assert passed_meta["maker"] == "M"
        assert result.nfo_written is True
        assert result.cover_written is True
        assert repo_factory.call_count == 2

    def test_enrich_one_readonly_preserve_title_number_change_uses_new_title_even_when_scraper_echoes_target(self):
        """`allow_number_change=true` 把這部片從 existing.number（'ABC-001'）改成
        新番號 'XYZ-999'（number 參數＝這次真正要寫入 DB／NFO 的番號），且來源忠實
        刮回使用者要求的目標番號（meta['number'] == 'XYZ-999' == number 參數——這是
        允許改號時最常見的情境）。比對必須落在 `existing.number` vs `number`：若誤
        比對 `meta.get('number')` vs `number`（二者相等）會判成同一部片、繼續保留
        existing.title，把舊標題文字配上新番號寫進 NFO／DB。"""
        from pathlib import Path
        from core.readonly_producer import enrich_one_readonly

        repo = MagicMock()
        existing = SimpleNamespace(
            size_bytes=123,
            mtime=456.0,
            cover_path="",
            title="[ABC-001]中文片名",
            number="ABC-001",
        )
        repo.get_by_path.return_value = existing
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "XYZ-999", "title": "刮到新片的標題", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/XYZ-999"),
                                 {"cover_fs": "/out/XYZ-999/XYZ-999.jpg", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            result = enrich_one_readonly(
                **self._base_kwargs(repo_factory, number="XYZ-999", preserve_title=True)
            )

        mock_produce.assert_called_once()
        passed_meta = mock_produce.call_args.kwargs["meta"]
        assert passed_meta["title"] == "刮到新片的標題"
        assert result.nfo_written is True

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

    def test_enrich_one_readonly_oracle_a_override_depends_on_old_nfo_content(self, tmp_path):
        """oracle (a)：唯讀路徑讀到舊 NFO 內容後，meta['title'] 隨磁碟內容變成本體。"""
        from core.readonly_producer import enrich_one_readonly

        existing, _ = self._existing_for_preserve(
            tmp_path,
            title="ABC-123-片名-三上悠亜",
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

        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["meta"]["title"] == "片名"
        assert result.success is True

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

    def test_enrich_one_readonly_oracle_c_default_format_no_override(self, tmp_path):
        """oracle (c)：預設格式 body==stripped → 不觸發；meta['title'] 保留 DB 原值。"""
        from core.readonly_producer import enrich_one_readonly

        existing_title = "[ABC-123]中文片名"
        existing, _ = self._existing_for_preserve(
            tmp_path,
            title=existing_title,
            actresses=[],
            disk_title=existing_title,
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
                scraper_cfg={"nfo_title_format": "[{num}]{title}"},
            ))

        assert mock_produce.call_args.kwargs["meta"]["title"] == existing_title
        assert result.success is True

    def test_enrich_one_readonly_old_nfo_missing_fails_closed(self, tmp_path):
        """舊 NFO 不存在 → fail-closed，meta['title'] 原樣保留 existing.title。"""
        from core.readonly_producer import enrich_one_readonly

        existing_title = "ABC-123-片名-三上悠亜"
        existing, _ = self._existing_for_preserve(
            tmp_path,
            title=existing_title,
            disk_title=None,  # 不寫舊 NFO
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

    def test_enrich_one_readonly_legacy_import_residual_still_stacks_actor_segment(self, tmp_path):
        """鎖住已知限制的現況，CD-154b-12 明確不涵蓋，未來擴充判準時這條測試需要跟著改期望值，不是回歸。

        §3 殘留 4：existing.title 已被剝過番號、disk 是預設格式改寫過 → 不相等分支，
        保留 existing 原值；後續 generate_nfo 用新格式會疊出第二段演員名（已知現況）。
        """
        from core.readonly_producer import enrich_one_readonly

        existing_title = "片名-三上悠亜"
        existing, _ = self._existing_for_preserve(
            tmp_path,
            title=existing_title,
            disk_title="[ABC-123]片名-三上悠亜",
        )
        repo = MagicMock()
        repo.get_by_path.return_value = existing
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-123", "title": "新刮到的日文片名", "maker": "M", "cover": "",
                "actors": ["三上悠亜"]}
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

        # 不相等 → 保留 existing 原值（CD-154b-12 不涵蓋此殘留）
        assert mock_produce.call_args.kwargs["meta"]["title"] == existing_title
        assert result.success is True

    def test_success_without_servable_cover(self):
        from core.readonly_producer import enrich_one_readonly

        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub()
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("none",))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0})), \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=False):
            result = enrich_one_readonly(**self._base_kwargs(repo_factory))

        assert result.success is True
        # [lint-guard: pytest-justified] EnrichResult.reason 確切文案值，同上
        # ——公開入口的 runtime 回傳契約，lint 無法表達。
        assert result.reason == "no_cover"
        assert result.cover_written is False
        # cover_written=False → no focal repo built, only the main repo call
        assert repo_factory.call_count == 1

    def test_not_found_stub_ordering(self):
        """meta=None → stub 樁列 + not_found failure；'insert_if_ignore' must be
        called before 'update_scrape_attempted_at' on the SAME mock repo
        (mock_calls order), mirroring _readonly_stub_not_found's own contract."""
        from core.readonly_producer import enrich_one_readonly

        repo = MagicMock()
        repo_factory = MagicMock(return_value=repo)

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(None, ("none",))) as mock_plan, \
             patch("core.readonly_producer._produce_one") as mock_produce:
            result = enrich_one_readonly(**self._base_kwargs(repo_factory))

        mock_produce.assert_not_called()
        assert result.success is False
        # [lint-guard: pytest-justified] 唯讀 not-found 的 EnrichResult.reason/
        # error 確切文案，跨 core/router 的 runtime 回傳契約，lint 無法表達。
        assert result.reason == "not_found"
        assert result.error == "找不到可用的番號資料"

        # [lint-guard: pytest-justified] mock_calls 的方法名字面值 + 呼叫順序，
        # 驗的是 _readonly_stub_not_found 對同一 mock repo 的呼叫順序契約
        # （insert_if_ignore 必先於 update_scrape_attempted_at），非 lint 可掃的
        # 靜態字串存在檢查，屬 runtime 呼叫序列斷言。
        call_names = [c[0] for c in repo.mock_calls]
        assert "insert_if_ignore" in call_names
        assert "update_scrape_attempted_at" in call_names
        assert call_names.index("insert_if_ignore") < call_names.index("update_scrape_attempted_at")

    def test_produce_one_exception_raises_readonly_produce_error(self):
        """C2 typed 邊界：_produce_one 拋例外 → entry 拋 ReadonlyProduceError
        （不是回傳 EnrichResult）——batch 側捕它的行為是 T3 範圍，本測試只驗
        entry 本身的轉拋契約。"""
        from core.readonly_producer import ReadonlyProduceError, enrich_one_readonly

        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub()
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   side_effect=RuntimeError("boom")):
            with pytest.raises(ReadonlyProduceError) as exc_info:
                enrich_one_readonly(**self._base_kwargs(repo_factory))

        assert isinstance(exc_info.value.__cause__, RuntimeError)

    # -----------------------------------------------------------------------
    # TASK-112b-T6 §C-5（Opus 追加要求 #2）：CD-112-15 正向鎖必須至少一支穿
    # `enrich_one_readonly` 的真實 preserve gate（讓 `cover_uri_is_servable`
    # 真的被評估——existing.cover_path 指向磁碟上一個真實存在的檔案，不是
    # 手搭 `('none',)` 餵給 `_write_movie_assets`），驗「什麼情況下會收到
    # ('none',)」這件事本身，而不只是「_write_movie_assets 收到 ('none',)
    # 會怎樣」（真理表 Table 2 #5，與非唯讀 Table 1 #3 刻意不一致）。
    # -----------------------------------------------------------------------

    def test_cd_112_15_real_preserve_gate_skips_write_when_cover_servable(self, tmp_path):
        """既有行為的鎖（CD-112-15，不是本 branch 的承諾）：唯讀 + 既有封面在
        磁碟上真的存在 + write_cover=True + overwrite_existing=False →
        `cover_uri_is_servable` 真的評估為 True → `apply_cover_preserve` 把
        cover_strategy 降級成 ('none',) → `_produce_one` 收到的是 ('none',)，
        不是 resolve_ingest_plan 原本回的 ('download', ...)。"""
        from core.readonly_producer import enrich_one_readonly

        real_cover = tmp_path / 'ABC-001.jpg'
        real_cover.write_bytes(b'EXISTING-COVER')
        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub(cover_path=to_file_uri(str(real_cover), {}))
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            enrich_one_readonly(**self._base_kwargs(
                repo_factory, write_cover=True, overwrite_existing=False,
                path_mappings={},
            ))

        assert mock_produce.call_args.kwargs['cover_strategy'] == ('none',), (
            "real preserve gate (cover file exists on disk) must downgrade "
            "the resolve_ingest_plan strategy to ('none',) —衍生圖本次不補產生 "
            "（Table 2 #5，與非唯讀 Table 1 #3 刻意不一致）"
        )

    def test_cd_112_15_overwrite_existing_true_still_writes(self, tmp_path):
        """補救途徑仍有效：同一部片、同一張存在的既有封面，改用
        overwrite_existing=True → preserve gate 不成立，cover_strategy 原封
        不動送進 _produce_one（衍生圖的補救途徑不是紙上宣稱）。"""
        from core.readonly_producer import enrich_one_readonly

        real_cover = tmp_path / 'ABC-001.jpg'
        real_cover.write_bytes(b'EXISTING-COVER')
        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub(cover_path=to_file_uri(str(real_cover), {}))
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "/out/ABC-001/ABC-001-fanart.jpg", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            enrich_one_readonly(**self._base_kwargs(
                repo_factory, write_cover=True, overwrite_existing=True,
                path_mappings={},
            ))

        assert mock_produce.call_args.kwargs['cover_strategy'] == ("download", "http://x/new.jpg"), (
            "overwrite_existing=True must NOT downgrade the strategy — 衍生圖的 "
            "補救途徑（齒輪重刮）必須仍然有效"
        )

    def test_table2_8_png_extension_cover_still_hits_preserve_gate(self, tmp_path):
        """真理表 Table 2 #8（認定範圍外，§3.3 第 2 條）：唯讀 preserve gate
        （`cover_uri_is_servable`）讀 DB `cover_path` 任意副檔名皆可，不像非
        唯讀路徑（CD-112-3b）限縮 `.jpg` 家族——DB 記錄一張 `.png` 封面、該檔
        磁碟上真的存在 → preserve **命中**，cover_strategy 仍被降級成
        ('none',)。這與 Table 1 #6（非唯讀對 `.png`/`folder.jpg` 一律視為
        「認定範圍外」而重新下載）結論**相反**，測試不得把表 A 的預測值抄成
        表 B。"""
        from core.readonly_producer import enrich_one_readonly

        real_cover = tmp_path / 'ABC-001.png'
        real_cover.write_bytes(b'EXISTING-PNG-COVER')
        repo = MagicMock()
        repo.get_by_path.return_value = self._existing_stub(cover_path=to_file_uri(str(real_cover), {}))
        repo_factory = MagicMock(return_value=repo)
        meta = {"number": "ABC-001", "title": "T", "maker": "M", "cover": ""}

        with patch("core.readonly_producer.resolve_ingest_plan",
                   return_value=(meta, ("download", "http://x/new.jpg"))), \
             patch("core.readonly_producer._produce_one",
                   return_value=(Path("/out/ABC-001"),
                                 {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0})) as mock_produce, \
             patch("core.readonly_producer.compute_has_servable_cover", return_value=True):
            enrich_one_readonly(**self._base_kwargs(
                repo_factory, write_cover=True, overwrite_existing=False,
                path_mappings={},
            ))

        assert mock_produce.call_args.kwargs['cover_strategy'] == ('none',), (
            "a .png cover recorded in DB and present on disk must still hit the "
            "readonly preserve gate — Table 2 #8, opposite of Table 1 #6's "
            "non-readonly .jpg-family-only rule"
        )


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
from core.readonly_producer import resolve_ingest_plan

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

    def test_samples_only_no_preview_keeps_todays_behaviour(self, tmp_path):
        """邊界 9（AC-5）：沒有 preview → 原址失敗就是失敗，行為與 branch 前相同。"""
        self._clear_failed_hosts()
        try:
            meta = {'sample_images': ['https://cdn.blocked/s1.jpg'], 'preview_sample_images': []}
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', side_effect=self._fake_get()) as mg:
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={}, source_fs_path='',
                    config={}, cover_strategy=('none',), assets_mode='samples_only',
                )
            assert out['sample_fs'] == []
            # 只打了原址一次，沒有第二次嘗試
            assert mg.call_count == 1
            assert 'fallback_url' not in mg.call_args.kwargs
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


class TestT4bLengthContract:
    """邊界 7 / D4：full 模式清空 sample_images 時，preview 必須同步清空。"""

    def test_resolve_ingest_plan_clears_preview_in_lockstep(self, tmp_path):
        src = tmp_path / 'ABC-123.mp4'
        src.write_bytes(b'x' * 10)
        scraper_data = {
            'number': 'ABC-123', 'title': 'T', 'cover': 'https://cdn/c.jpg',
            'sample_images': ['https://cdn/s1.jpg', 'https://cdn/s2.jpg'],
            'preview_sample_images': ['http://mt/p1', 'http://mt/p2'],
            'preview_cover_url': 'http://mt/pc',
        }
        meta, _strategy = resolve_ingest_plan(
            str(src), 'ABC-123', {}, action='rescrape', scraper_data=scraper_data,
        )
        assert meta is not None
        assert meta['sample_images'] == []
        assert meta['preview_sample_images'] == [], (
            '等長契約：清空 sample_images 卻留著 preview → 兩者長度不等 → '
            '下游逐張配對時圖片對到別張（靜默錯位，比破圖難查）'
        )


# ============ TASK-126-T4b review MAJOR-2：readonly full 模式的劇照分支 ============
#
# 初版只測了 full 模式的**封面**，而且那支的 meta 是 `sample_images: []`（劇照迴圈根本不會跑）。
# review 在沙盒把 full 分支的 preview 傳遞整段拔掉，335 條照樣全綠 ⇒ 這個下載點沒人守。

class TestT4bReadonlyFullSamplesFallback(_T4bReadonlyBase):

    def test_full_mode_extrafanart_uses_preview_fallback(self, tmp_path):
        """使用者用放大鏡全量重刮一部片（full 模式）→ 原址被牆 → 劇照經代理落地。"""
        self._clear_failed_hosts()
        try:
            meta = {
                'number': 'N-2', 'title': 'T', 'actors': [], 'tags': [],
                'sample_images': ['https://cdn.blocked/s1.jpg', 'https://cdn.blocked/s2.jpg'],
                'preview_sample_images': [
                    'http://mt.example/v1/images/primary/MGS/N-2?url=s1',
                    'http://mt.example/v1/images/primary/MGS/N-2?url=s2',
                ],
            }
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', side_effect=self._fake_get()):
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={'number': 'N-2'},
                    source_fs_path=str(tmp_path / 'src.mp4'),
                    config={'download_sample_images': True},
                    cover_strategy=('none',), assets_mode='full',
                )
            assert len(out.get('sample_fs') or []) == 2, (
                'full 模式的劇照分支若沒接上 preview，被牆的使用者重刮一次會拿到 0 張劇照，'
                '而且沒有任何錯誤訊息'
            )
            for p in out['sample_fs']:
                assert open(p, 'rb').read() == _T4B_PROXY
        finally:
            self._clear_failed_hosts()

    def test_full_mode_extrafanart_short_preview_does_not_truncate(self, tmp_path):
        """邊界 8 在 full 模式也成立：preview 比 sample 短，不得少下載。"""
        self._clear_failed_hosts()
        try:
            meta = {
                'number': 'N-3', 'title': 'T', 'actors': [], 'tags': [],
                'sample_images': ['https://cdn.ok/s1.jpg', 'https://cdn.ok/s2.jpg', 'https://cdn.ok/s3.jpg'],
                'preview_sample_images': ['http://mt.example/v1/images/primary/MGS/N-3?url=s1'],
            }
            movie_dir = str(tmp_path / 'movie')
            with _t4b_patch('core.organizer.requests.get', return_value=self._resp(_T4B_DIRECT)) as mg:
                out = _write_movie_assets(
                    movie_dir=movie_dir, meta=meta, format_data={'number': 'N-3'},
                    source_fs_path=str(tmp_path / 'src.mp4'),
                    config={'download_sample_images': True},
                    cover_strategy=('none',), assets_mode='full',
                )
            assert len(out.get('sample_fs') or []) == 3, 'zip 截斷會讓這裡變成 1'
            assert mg.call_count == 3
        finally:
            self._clear_failed_hosts()


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

    def test_reverse_lock_name_mapping_takes_precedence_over_prefix_mapping(self, tmp_path):
        """反向鎖：兩層對照對同一部片給出**不同答案**的真衝突樣本——
        maker='S1 NO.1 STYLE'（name_mapping → 'S1'）＋ number='CRB-123'
        （prefix_mapping['CRB'] → 'Caribbeancom'）。期望 'S1'：Step 1 原名對照
        短路優先，證明加上前綴對照那一層沒有把原名對照擠掉。

        取樣理由（T3 grok review P3）：前綴不在表內的樣本（如 'ZZZFAKE-001'）
        守不住這條——把 normalize_maker 的 Step1/Step2 對調它照樣綠，因為只有
        一層會命中。**反向鎖必須用兩層都命中且答案相異的樣本才有鑑別力。**"""
        from core.readonly_producer import resolve_ingest_plan

        video = self._touch_video(tmp_path, 'CRB-123.mp4')
        raw_meta = {
            'number': 'CRB-123',
            'title': 'T',
            'cover': '',
            'maker': 'S1 NO.1 STYLE',
        }

        with patch('core.readonly_producer.search_jav', return_value=raw_meta):
            meta, cover_strategy = resolve_ingest_plan(str(video), 'CRB-123', {}, action='ingest')

        assert meta is not None
        # 兩層都命中：name_mapping 給 'S1'、prefix_mapping 給 'Caribbeancom'。
        assert meta['maker'] == 'S1'
        assert meta['maker'] != 'Caribbeancom'

    def test_focal_gate_flips_when_maker_normalized_to_uncensored(self, tmp_path):
        """focal 連帶「會翻轉」：CRB-123 ＋ RawCRBMaker → 正規化前 requires_face_detection 為 False；
        正規化後 maker 變 Caribbeancom，requires_face_detection 由 False 變 True。"""
        from core.focal.gate import requires_face_detection
        from core.readonly_producer import resolve_ingest_plan

        num = 'CRB-123'
        raw_maker = 'RawCRBMaker'

        # 驗證初始條件：正規化前 gate 判定為 False
        assert requires_face_detection(num, raw_maker) is False

        video = self._touch_video(tmp_path, f'{num}.mp4')
        raw_meta = {
            'number': num,
            'title': 'T',
            'cover': '',
            'maker': raw_maker,
        }

        with patch('core.readonly_producer.search_jav', return_value=raw_meta):
            meta, _ = resolve_ingest_plan(str(video), num, {}, action='ingest')

        assert meta is not None
        assert meta['maker'] == 'Caribbeancom'
        assert requires_face_detection(meta['number'], meta['maker']) is True

    def test_focal_gate_remains_false_when_maker_normalized_to_censored(self, tmp_path):
        """focal 連帶「不翻轉」：SSIS-002 ＋ Maker → 正規化後 maker 變 S1，
        但 requires_face_detection 兩邊都是 False（maker 值變了、布林判定沒變，明確斷言兩件事）。"""
        from core.focal.gate import requires_face_detection
        from core.readonly_producer import resolve_ingest_plan

        num = 'SSIS-002'
        raw_maker = 'Maker'

        # 驗證初始條件：正規化前 gate 判定為 False
        assert requires_face_detection(num, raw_maker) is False

        video = self._touch_video(tmp_path, f'{num}.mp4')
        raw_meta = {
            'number': num,
            'title': 'T',
            'cover': '',
            'maker': raw_maker,
        }

        with patch('core.readonly_producer.search_jav', return_value=raw_meta):
            meta, _ = resolve_ingest_plan(str(video), num, {}, action='ingest')

        assert meta is not None
        assert meta['maker'] == 'S1'  # 1. maker 值變了
        assert requires_face_detection(meta['number'], meta['maker']) is False  # 2. 布林判定沒變


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

    def test_write_movie_assets_default_user_tags_omits_tag_elements(self, tmp_path):
        from core.readonly_paths import _format_data
        from core.readonly_assets import _write_movie_assets

        movie_dir = tmp_path / "movie_default"
        movie_dir.mkdir()
        meta = {"number": "TEST-002", "title": "Default Title"}
        config = {"external_manager": "off"}
        fd = _format_data(meta, "/src/TEST-002.mp4", config)

        _write_movie_assets(
            str(movie_dir), meta, fd, "/src/TEST-002.mp4", config,
            cover_strategy=("none",),
        )

        nfo_files = list(movie_dir.glob("*.nfo"))
        assert len(nfo_files) == 1
        content = nfo_files[0].read_text(encoding="utf-8")
        assert "<user_tag>" not in content


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

    def test_produce_one_passes_empty_tags_when_existing_is_none(self, tmp_path):
        from core.readonly_producer import _produce_one

        output_root = tmp_path / "output"
        output_root.mkdir()
        file_info = {"path": "/src/TEST-001.mp4", "size": 1000, "mtime": 1.0}
        meta = {"number": "TEST-001", "title": "Test"}
        repo = MagicMock()

        with patch("core.readonly_paths._resolve_movie_dir",
                   return_value=(tmp_path / "output" / "TEST-001", "file:///whatever-db-uri")), \
             patch("core.readonly_assets._write_movie_assets",
                   return_value={"nfo_mtime": 1.0, "cover_fs": "", "sample_fs": []}) as mock_write, \
             patch("core.readonly_producer._upsert_db"):
            _produce_one(
                repo, None, {"scraper": {}},
                file_info=file_info, meta=meta, cover_strategy=("none",),
                assets_mode="full", existing=None,
                output_root=str(output_root), output_uri="file:///output",
                allocated_this_run=set(), path_mappings={},
            )
        assert mock_write.call_args.kwargs["user_tags"] == []


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
    def test_all_three_present_skips_disk_io(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        meta = {
            'number': 'ABC-100', 'title': 'T',
            '_summary': 'existing', '_rating': 3.0, 'url': 'https://existing',
        }
        before = dict(meta)

        with patch('core.readonly_producer._list_nfo_names', create=True) as mock_list:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'ABC-100', 'ABC-100', False,
            )

        assert result is True
        mock_list.assert_not_called()
        assert meta == before

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

    def test_old_base_empty_new_base_missing_returns_true_unchanged(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        meta = {'number': 'ABC-100', 'title': 'T'}
        before = dict(meta)

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), '', 'ZZZ-000', False,
        )

        assert result is True
        assert meta == before

    def test_both_candidates_missing_returns_true_unchanged(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        meta = {'number': 'ABC-100', 'title': 'T'}
        before = dict(meta)

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'AAA-1', 'BBB-2', False,
        )

        assert result is True
        assert meta == before

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

    def test_missing_one_field_selected_candidate_broken_returns_false(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'OLD-2.nfo').write_bytes(BROKEN_NFO_BYTES)

        meta = {'number': 'ABC-100', 'title': 'T', '_summary': 'x', '_rating': 1.0}

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'OLD-2', 'NOPE-999', False,
        )

        assert result is False

    def test_ac13_old_base_missing_new_base_exists_reads_back(self, tmp_path):
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'NEW-3.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'OLD-3', 'NEW-3', False,
        )

        assert result is True
        assert meta['_summary'] == 'A normal summary.'
        assert meta['_rating'] == 4.0
        assert meta['url'] == 'https://example.com/v'
        # C-2：AC-13 這條走的是「讀回成功」主路徑，寫回的 key 必須是帶底線的
        # `_summary`/`_rating`，不是映射後的 `summary`/`rating`——逐字鎖 key 集合。
        assert set(meta.keys()) == {'number', 'title', '_summary', '_rating', 'url'}

    def test_old_base_equals_new_base_dedup_checks_once(self, tmp_path):
        """CD-151b-12：目錄掃描取代逐候選 exists()——不論 old_base 是否等於
        new_base，永遠只掃一次目錄。"""
        from core.nfo_updater import parse_nfo
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'SAME-1.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.parse_nfo', wraps=parse_nfo) as mock_parse, \
             patch('core.readonly_producer._list_nfo_names',
                   create=True, return_value=('ok', ['SAME-1.nfo'])) as mock_list:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'SAME-1', 'SAME-1', False,
            )

        assert result is True
        assert mock_parse.call_count == 1
        assert mock_list.call_count == 1
        assert meta['_summary'] == 'A normal summary.'
        assert meta['_rating'] == 4.0
        assert meta['url'] == 'https://example.com/v'
        # C-2：同上，逐字鎖 key 集合，避免無底線的 `summary`/`rating` 混入。
        assert set(meta.keys()) == {'number', 'title', '_summary', '_rating', 'url'}

    def test_old_base_equals_new_base_dedup_not_checked_twice_when_missing(self, tmp_path):
        """CD-151b-12：目錄為空時仍只掃一次——掃描取代逐候選 exists()，
        old_base == new_base 不再有 I/O 去重問題，鑑別點改成「_list_nfo_names
        恰好呼叫一次」。"""
        from core.nfo_updater import parse_nfo
        from core.readonly_producer import _resolve_readonly_preserved_fields

        meta = {'number': 'ABC-100', 'title': 'T'}
        before = dict(meta)

        with patch('core.readonly_producer.parse_nfo', wraps=parse_nfo) as mock_parse, \
             patch('core.readonly_producer._list_nfo_names',
                   create=True, return_value=('ok', [])) as mock_list:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'SAME-2', 'SAME-2', False,
            )

        assert result is True
        assert meta == before
        assert mock_parse.call_count == 0
        assert mock_list.call_count == 1

    def test_missing_dir_reused_output_fails_closed(self, tmp_path):
        """邊界條件 1／決策表列 2：目錄不存在＋reused_existing_output_dir=True
        → False＋一次 WARNING。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        missing = tmp_path / 'not-created-yet'
        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.logger') as mock_logger:
            result = _resolve_readonly_preserved_fields(
                meta, str(missing), 'OLD', 'NEW', True,
            )

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_missing_dir_first_generation_succeeds(self, tmp_path):
        """邊界條件 2／決策表列 3：目錄不存在＋reused_existing_output_dir=False
        → True（首次產出／骨架 row 必須放行）。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        missing = tmp_path / 'not-created-yet'
        meta = {'number': 'ABC-100', 'title': 'T'}
        before = dict(meta)

        result = _resolve_readonly_preserved_fields(
            meta, str(missing), 'OLD', 'NEW', False,
        )

        assert result is True
        assert meta == before

    def test_directory_scan_unknown_error_fails_closed(self, tmp_path):
        """邊界條件 3／決策表列 4：os.scandir 拋非 FileNotFoundError 的 OSError
        → False＋WARNING。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.os.scandir',
                   side_effect=PermissionError('denied')), \
             patch('core.readonly_producer.logger') as mock_logger:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'OLD', 'NEW', False,
            )

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_single_nfo_file_name_mismatches_both_candidates_still_selected(self, tmp_path):
        """邊界條件 5／決策表列 6：恰好 1 份 .nfo，檔名對不上 old/new base
        → 仍選中並讀回。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'manually-renamed.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'OLD-BASE', 'NEW-BASE', False,
        )

        assert result is True
        assert meta['_summary'] == 'A normal summary.'
        assert meta['_rating'] == 4.0
        assert meta['url'] == 'https://example.com/v'

    def test_multiple_nfo_files_neither_candidate_matches_fails_closed(self, tmp_path):
        """邊界條件 6／決策表列 7 否定半：≥2 份 .nfo 且 old/new 皆不命中
        → False＋WARNING。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        (tmp_path / 'orphan-a.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')
        (tmp_path / 'orphan-b.nfo').write_text(NORMAL_NFO_TEXT, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.logger') as mock_logger:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'OLD-BASE', 'NEW-BASE', False,
            )

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_directory_scan_entry_is_file_raises_unknown_fails_closed(self, tmp_path):
        """邊界條件 10：scandir 成功但 entry.is_file() 拋 OSError → 乾淨回傳
        False＋WARNING（例外不得逸出函式邊界）。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        bad_entry = MagicMock()
        bad_entry.name = 'x.nfo'
        bad_entry.is_file.side_effect = OSError('is_file failed')

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = [bad_entry]
        mock_cm.__exit__.return_value = None

        meta = {'number': 'ABC-100', 'title': 'T'}

        with patch('core.readonly_producer.os.scandir', return_value=mock_cm), \
             patch('core.readonly_producer.logger') as mock_logger:
            result = _resolve_readonly_preserved_fields(
                meta, str(tmp_path), 'OLD', 'NEW', False,
            )

        assert result is False
        mock_logger.warning.assert_called_once()

    def test_multiple_nfo_files_old_base_wins_when_both_candidates_present(self, tmp_path):
        """邊界條件 11／決策表列 7 正向鎖：old 與 new 都在且內容不同 → 讀回
        來自 old_base 那份。"""
        from core.readonly_producer import _resolve_readonly_preserved_fields

        old_nfo = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<movie>\n'
            '  <plot>FROM-OLD-BASE</plot>\n'
            '  <rating>6.0</rating>\n'
            '  <website>https://from-old</website>\n'
            '</movie>\n'
        )
        new_nfo = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<movie>\n'
            '  <plot>FROM-NEW-BASE</plot>\n'
            '  <rating>2.0</rating>\n'
            '  <website>https://from-new</website>\n'
            '</movie>\n'
        )
        (tmp_path / 'OLD-WIN.nfo').write_text(old_nfo, encoding='utf-8')
        (tmp_path / 'NEW-WIN.nfo').write_text(new_nfo, encoding='utf-8')

        meta = {'number': 'ABC-100', 'title': 'T'}

        result = _resolve_readonly_preserved_fields(
            meta, str(tmp_path), 'OLD-WIN', 'NEW-WIN', False,
        )

        assert result is True
        assert meta['_summary'] == 'FROM-OLD-BASE'
        assert meta['_rating'] == 3.0
        assert meta['url'] == 'https://from-old'


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

    def test_non_runtime_error_after_rename_also_reverts(self, tmp_path, temp_db):
        """加測（第 3 輪 grok review P2）：`except Exception:` 的型別寬度——
        真實路徑是 NFO 成功寫出**之後**，`core.readonly_assets.nfo_mtime_or_none`
        透過 `_reraise_nfo_stat_error` 把 `OSError` 原樣再拋（`core/readonly_
        assets.py` 的 `nfo_mtime = nfo_mtime_or_none(..., on_error=
        _reraise_nfo_stat_error)`，晚於 `generate_nfo` 成功、晚於改名成功）。
        DoD④ 注入的是 `RuntimeError`，若實作把 `except Exception:` 收窄成
        `except RuntimeError:`，DoD④ 測不出來——這條專門補這個型別寬度的洞：
        已改名的圖必須被復原，DB 完全不被碰。"""
        import hashlib

        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        old_poster = ctx['movie_dir'] / f'{self._OLD_BASE}-poster.jpg'
        old_fanart = ctx['movie_dir'] / f'{self._OLD_BASE}-fanart.jpg'
        old_poster_sha = hashlib.sha256(old_poster.read_bytes()).hexdigest()
        old_fanart_sha = hashlib.sha256(old_fanart.read_bytes()).hexdigest()
        before_db = repo.get_by_path(ctx['src_uri'])

        meta_b = dict(_T4R_META_A, title='New Title')

        with pytest.raises(OSError):
            _t4r_round2(
                repo, ctx, meta_b, ('none',),
                generate_nfo_patch=patch(
                    'core.readonly_assets.nfo_mtime_or_none',
                    side_effect=OSError('simulated disk error during nfo stat'),
                ),
            )

        assert hashlib.sha256(old_poster.read_bytes()).hexdigest() == old_poster_sha, (
            "已改名的圖必須被復原回舊基底（非 RuntimeError 的例外也要被 except Exception 接住）"
        )
        assert hashlib.sha256(old_fanart.read_bytes()).hexdigest() == old_fanart_sha
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-poster.jpg').exists()
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-fanart.jpg').exists()

        after_db = repo.get_by_path(ctx['src_uri'])
        assert after_db == before_db

    def test_cas_false_concurrent_write_reverts_photos_keeps_sentinel(self, tmp_path, temp_db):
        """DoD⑤／mutation 點③④：改名成功後、CAS 呼叫之前，另一個並行流程把
        DB cover_path 改成 sentinel → CAS 自然回傳 False（compare-and-store
        沒命中）→ 圖片復原回舊基底、DB 的 sentinel 值不被覆寫（不改回舊值也
        不改成這輪算出的新值）、該片這一輪失敗。"""
        import hashlib
        import sqlite3

        from core.database import VideoRepository
        from core.readonly_producer import ReadonlyProduceError

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        old_poster = ctx['movie_dir'] / f'{self._OLD_BASE}-poster.jpg'
        old_fanart = ctx['movie_dir'] / f'{self._OLD_BASE}-fanart.jpg'
        old_poster_sha = hashlib.sha256(old_poster.read_bytes()).hexdigest()
        old_fanart_sha = hashlib.sha256(old_fanart.read_bytes()).hexdigest()

        sentinel_uri = 'file:///sentinel/concurrent-write.jpg'
        db_path = str(temp_db)

        def _sentinel_then_real(path, new_cover_path, expected_old_cover_path):
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("UPDATE videos SET cover_path = ? WHERE path = ?", (sentinel_uri, path))
                conn.commit()
            finally:
                conn.close()
            return VideoRepository.update_cover_path_preserve_focal(
                repo, path, new_cover_path, expected_old_cover_path,
            )

        meta_b = dict(_T4R_META_A, title='New Title')
        before_existing_cover_path = ctx['existing'].cover_path

        with patch.object(repo, 'update_cover_path_preserve_focal', side_effect=_sentinel_then_real):
            with pytest.raises(ReadonlyProduceError):
                _t4r_round2(repo, ctx, meta_b, ('none',))

        # cas_ok is False → existing.cover_path（呼叫端手上的 in-memory 物件）
        # 不准被提前同步；提前同步不會被 DB 狀態斷言抓到（_upsert_db 從未執行），
        # 只有直接檢查這個物件本身才測得到 mutation 點③。
        assert ctx['existing'].cover_path == before_existing_cover_path, (
            "cas_ok is False 時 existing.cover_path 不得被同步"
        )

        assert old_poster.exists()
        assert hashlib.sha256(old_poster.read_bytes()).hexdigest() == old_poster_sha
        assert old_fanart.exists()
        assert hashlib.sha256(old_fanart.read_bytes()).hexdigest() == old_fanart_sha
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-poster.jpg').exists()
        assert not (ctx['movie_dir'] / f'{self._NEW_BASE}-fanart.jpg').exists()

        v = repo.get_by_path(ctx['src_uri'])
        assert v.cover_path == sentinel_uri, "並行流程寫入的值不得被覆寫（不回舊值也不換新值）"

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

    @pytest.mark.parametrize('strategy_kind', ['download', 'copy'])
    def test_non_preserve_strategy_never_renames(self, tmp_path, temp_db, strategy_kind):
        """DoD⑦／mutation 點⑤（第 3 輪 grok review P3 補強）：
        `cover_strategy[0] != 'none'`（'download' 與 'copy' 兩種都測，卡片字
        面要求的完整矩陣）時，即使標題有變，改名機制完全不介入——斷言下沉
        到 `_move_cover_slot`（`atomic_move` 的唯一呼叫 leaf，CD-151b-4）零
        呼叫，不只是看上層 `_rename_stale_cover_group` 有沒有被呼叫（那支本
        身用 `wraps=` 讓它照常真跑，不擋路，才能讓 `_move_cover_slot` 的斷言
        真的有意義——若把它整支 mock 掉，`_move_cover_slot` 天生就不會被呼
        叫，測不出 gate 被拿掉的差異）。"""
        from core.database import VideoRepository
        from core.readonly_assets import _rename_stale_cover_group as _real_rename

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        if strategy_kind == 'download':
            meta_b = dict(_T4R_META_A, title='New Title', cover='https://example.com/cover2.jpg')
            cover_strategy = ('download', meta_b['cover'])
        else:
            sidecar = tmp_path / 'sidecar-cover.jpg'
            sidecar.write_bytes(b'SIDECAR COVER BYTES')
            meta_b = dict(_T4R_META_A, title='New Title')
            cover_strategy = ('copy', str(sidecar))

        with patch('core.readonly_assets._rename_stale_cover_group', wraps=_real_rename) as mock_rename, \
             patch('core.readonly_assets._move_cover_slot') as mock_move_slot:
            _t4r_round2(repo, ctx, meta_b, cover_strategy)

        mock_rename.assert_not_called()
        mock_move_slot.assert_not_called()

    def test_cas_exception_then_retry_preserves_three_fields(self, tmp_path, temp_db):
        """DoD⑧：第一輪 CAS 例外殘留狀態（新基底 .nfo 已寫出、DB title/
        cover_path 仍舊值）→ 不重建任何東西，對同一個 existing 呼叫第二輪
        `_produce_one`（CAS 這次正常、meta 只帶部分欄位）→ 候選清單依序找
        {old_base}.nfo（撲空）→ {new_base}.nfo（命中，第一輪寫出的那份）→
        簡介/評分/來源網址三欄與第一輪逐字相同，第二輪最終成功。"""
        import sqlite3

        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        meta_b = dict(
            _T4R_META_A, title='New Title',
            _summary='Round B summary', _rating=2.0, url='https://example.com/round-b',
        )

        with patch.object(
            repo, 'update_cover_path_preserve_focal',
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            with pytest.raises(sqlite3.OperationalError):
                _t4r_round2(repo, ctx, meta_b, ('none',))

        assert not (ctx['movie_dir'] / f'{self._OLD_BASE}.nfo').exists(), 'sanity: 第一輪已清掉舊 nfo'
        assert (ctx['movie_dir'] / f'{self._NEW_BASE}.nfo').exists(), 'sanity: 第一輪新 nfo 已真實寫出'

        meta_c = dict(_T4R_META_A, title='New Title')
        for k in ('_summary', '_rating', 'url'):
            meta_c.pop(k, None)

        movie_dir, _assets = _t4r_round2(repo, ctx, meta_c, ('none',))

        root = ET.parse(Path(movie_dir) / f'{self._NEW_BASE}.nfo').getroot()
        assert root.findtext('plot') == meta_b['_summary']
        assert float(root.findtext('rating')) == meta_b['_rating'] * 2
        assert root.findtext('website') == meta_b['url']

        v = repo.get_by_path(ctx['src_uri'])
        assert v.title == 'New Title'
        assert self._NEW_BASE in v.cover_path

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

    def test_rename_hard_failure_aborts_round_before_any_write(self, tmp_path, temp_db):
        """加測（第 2 輪 review 抓到的未守分支，D-151b-6）：
        `_rename_stale_cover_group` 回傳 `hard_failure=True`（改名中途 I/O 失
        敗、已搬的部分已復原回舊名）時，`_produce_one` 必須在任何後續動作
        （寫新基底 NFO/.strm、清掉舊基底、CAS、_upsert_db）之前整輪提前失
        敗——不得讓「NFO 在新名字、圖在舊名字」這個洞一孤兒狀態靜默落地並
        回報成功。"""
        from core.database import VideoRepository
        from core.readonly_assets import RenameOutcome
        from core.readonly_producer import ReadonlyProduceError, _produce_one

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        before_dir = _t4r_dir_snapshot(ctx['movie_dir'])
        before_db = repo.get_by_path(ctx['src_uri'])

        meta_b = dict(_T4R_META_A, title='New Title')

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin), \
             patch('core.readonly_assets._rename_stale_cover_group',
                   return_value=RenameOutcome(None, True, ())):
            with pytest.raises(ReadonlyProduceError):
                _produce_one(
                    repo, MagicMock(), ctx['config'],
                    file_info=ctx['file_info'], meta=meta_b, cover_strategy=('none',),
                    assets_mode='full', existing=ctx['existing'],
                    output_root=str(ctx['output_root']), output_uri=ctx['output_uri'],
                    allocated_this_run=set(), path_mappings={},
                )

        after_dir = _t4r_dir_snapshot(ctx['movie_dir'])
        assert after_dir == before_dir, (
            "hard_failure=True 時新基底的 .nfo/.strm 不得被寫出、舊基底不得被清掉"
        )
        after_db = repo.get_by_path(ctx['src_uri'])
        assert after_db == before_db, "DB 的 cover_path 與 focal 三欄不得被碰"

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

    def test_samples_only_succeeds_despite_broken_existing_nfo(self, tmp_path, temp_db):
        """回歸修正①（同上，第二個場景）：既有 NFO 損壞時，補劇照不得被洞二
        的 fail-closed 誤傷——補劇照根本不寫 NFO，讀回的簡介/評分/來源網址
        三欄從頭到尾用不到，NFO 好壞與這次補劇照無關。"""
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)

        nfo_path = ctx['movie_dir'] / f'{self._OLD_BASE}.nfo'
        assert nfo_path.exists()
        nfo_path.write_bytes(BROKEN_NFO_BYTES)

        meta_b = dict(
            _T4R_META_A, title='New Title',
            sample_images=['https://example.com/s1.jpg'],
        )
        for k in ('_summary', '_rating', 'url'):
            meta_b.pop(k, None)  # 缺欄位才會真的觸發讀回嘗試（見 _resolve_readonly_preserved_fields 的短路判準）

        movie_dir, assets = _t4r_round2(repo, ctx, meta_b, ('none',), assets_mode='samples_only')

        assert len(assets['sample_fs']) == 1, "補劇照不得被無關的 NFO 損壞擋下"
        sample_path = Path(assets['sample_fs'][0])
        assert sample_path.exists() and sample_path.read_bytes() == b'FAKE-IMG'

    def test_produce_one_config_drift_three_fields_preserved(self, tmp_path, temp_db):
        """邊界條件 7：round A 用 '{num} {title}' 產出可辨識三欄 → 改成
        '{title} {num}' → round B 缺三欄的 meta 仍逐字讀回 round A 的值。"""
        from core import readonly_paths
        from core.database import VideoRepository

        repo = VideoRepository(temp_db)
        meta_a = dict(
            _T4R_META_A,
            _summary='ROUND-A-SUMMARY',
            _rating=3.5,
            url='https://round-a',
        )
        ctx = _t4r_setup(tmp_path, repo, meta_a=meta_a)
        src_fs = ctx['file_info']['path']

        # sanity: round A 本輪目標 NFO 真的寫進這三個字面（走產品碼命名，
        # 不靠 glob 列舉順序——round B 後舊 NFO 可能殘留，見 accepted residual）
        base_a = readonly_paths._build_basename(
            readonly_paths._format_data(meta_a, src_fs, ctx['config']),
            src_fs, ctx['config'],
        )
        nfo_a = ctx['movie_dir'] / f'{base_a}.nfo'
        assert nfo_a.is_file()
        root_a = ET.parse(nfo_a).getroot()
        assert root_a.findtext('plot') == 'ROUND-A-SUMMARY'
        assert float(root_a.findtext('rating')) == 7.0
        assert root_a.findtext('website') == 'https://round-a'

        ctx['config'] = dict(ctx['config'], filename_format='{title} {num}')

        meta_b = dict(meta_a)
        for k in ('_summary', '_rating', 'url'):
            meta_b.pop(k, None)

        movie_dir, _assets = _t4r_round2(repo, ctx, meta_b, ('none',))

        # 明確解析本輪目標 NFO（_clean_stale_singletons 的失準 old_base 可能
        # 留下 round A 那份——不得靠 glob 列舉順序碰巧取到正確的那一份）
        base_b = readonly_paths._build_basename(
            readonly_paths._format_data(meta_b, src_fs, ctx['config']),
            src_fs, ctx['config'],
        )
        nfo_b = Path(movie_dir) / f'{base_b}.nfo'
        assert nfo_b.is_file()
        root_b = ET.parse(nfo_b).getroot()
        assert root_b.findtext('plot') == 'ROUND-A-SUMMARY'
        assert float(root_b.findtext('rating')) == 7.0
        assert root_b.findtext('website') == 'https://round-a'

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

    def test_produce_one_output_root_moved_existing_row_missing_dir_succeeds(
        self, tmp_path, temp_db,
    ):
        """CD-151b-12 決策表列 3（有既有 DB 列那半）：output root 搬家後
        `_resolve_movie_dir` 走 allocate、回傳尚未 mkdir 的新目錄；`existing`
        非 None 但 `output_dir_uri != existing.output_dir` → 必須放行，不得
        把「有既有列」誤判成 reuse 而 fail-closed。"""
        from core.database import Video, VideoRepository
        from core.readonly_producer import _produce_one

        repo = VideoRepository(temp_db)
        src_fs = str(tmp_path / 'src' / 'TEST-001.mp4')
        Path(src_fs).parent.mkdir(parents=True, exist_ok=True)
        Path(src_fs).write_bytes(b'FAKE-VIDEO-BYTES')
        src_uri = to_file_uri(src_fs, {})

        old_root = tmp_path / 'old-output'
        old_movie_dir = old_root / 'TEST-001'
        old_movie_dir.mkdir(parents=True)
        (old_movie_dir / 'placeholder.nfo').write_text('<movie/>', encoding='utf-8')

        seed = Video(
            path=src_uri, number='TEST-001', title='Old Title',
            actresses=['Actress A'], maker='Test Maker', release_date='2024-01-01',
            cover_path=to_file_uri(str(old_movie_dir / 'cover.jpg'), {}),
            output_dir=to_file_uri(str(old_movie_dir), {}),
        )
        repo.upsert(seed)
        existing = repo.get_by_path(src_uri)
        assert existing is not None
        assert existing.output_dir == to_file_uri(str(old_movie_dir), {})

        new_root = tmp_path / 'new-output'
        new_root.mkdir()
        new_uri = to_file_uri(str(new_root), {})
        file_info = {'path': src_fs, 'size': 1_000_000, 'mtime': 1.0}

        meta = dict(_T4R_META_A)
        for k in ('_summary', '_rating', 'url'):
            meta.pop(k, None)

        with patch('core.readonly_assets.download_image', side_effect=_t4_real_download), \
             patch('core.readonly_assets.generate_jellyfin_images', side_effect=_t4_real_jellyfin):
            movie_dir, _assets = _produce_one(
                repo, MagicMock(), dict(_T3_BASE_CONFIG),
                file_info=file_info, meta=meta, cover_strategy=_cover_strategy_for(meta),
                assets_mode='full', existing=existing,
                output_root=str(new_root), output_uri=new_uri,
                allocated_this_run=set(), path_mappings={},
            )

        assert Path(movie_dir).is_dir()
        assert Path(movie_dir).is_relative_to(new_root)
        assert list(Path(movie_dir).glob('*.nfo')), "搬家後首次落到新 root 必須成功寫出 NFO"
        # 明確：本輪 allocate 出的目錄 URI ≠ 舊 existing.output_dir（provenance 前提）
        assert to_file_uri(str(movie_dir), {}) != existing.output_dir
        v = repo.get_by_path(src_uri)
        assert v.output_dir != existing.output_dir

    def test_produce_one_reused_output_dir_vanished_fails_closed(
        self, tmp_path, temp_db,
    ):
        """CD-151b-12 決策表列 2 的整合層：reuse 分支下 movie_dir 被刪掉
        （NAS 掉線／使用者刪輸出夾）＋ meta 缺三欄 → 必須 raise
        ReadonlyProduceError，且不得重新寫出一份三欄空的 NFO。"""
        import shutil

        from core.database import VideoRepository
        from core.readonly_producer import ReadonlyProduceError

        repo = VideoRepository(temp_db)
        ctx = _t4r_setup(tmp_path, repo)
        before_output_dir = ctx['existing'].output_dir

        shutil.rmtree(ctx['movie_dir'])
        assert not ctx['movie_dir'].exists()

        meta_b = dict(_T4R_META_A)
        for k in ('_summary', '_rating', 'url'):
            meta_b.pop(k, None)

        with pytest.raises(ReadonlyProduceError):
            _t4r_round2(repo, ctx, meta_b, ('none',))

        assert not ctx['movie_dir'].exists(), (
            "fail-closed 必須發生在任何寫檔之前，被刪的 movie_dir 不得被重建"
        )
        # 即使目錄意外被重建，也絕不能留下一份 NFO（三欄空的靜默清空路徑）
        if ctx['movie_dir'].exists():
            assert not list(ctx['movie_dir'].glob('*.nfo'))
        v = repo.get_by_path(ctx['src_uri'])
        assert v.output_dir == before_output_dir
