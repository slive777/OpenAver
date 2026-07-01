"""Unit tests for core/readonly_producer.py (TDD-lite, T-1/T-3 scope).

All filesystem / DB access is mocked — zero real I/O unless explicitly noted
(T-3 DB tests use the temp_db fixture for a real SQLite write path).
"""
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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
             patch("core.readonly_producer.normalize_path", return_value="/src") as mock_norm:
            result = _list_source_videos("/src", {".mp4", ".mkv"}, 0)

        mock_norm.assert_called_once_with("/src")
        mock_scan.assert_called_once_with("/src", {".mp4", ".mkv"}, 0)
        assert result == FAKE_FILES

    def test_returns_raw_list_unchanged(self):
        from core.readonly_producer import _list_source_videos

        with patch("core.readonly_producer.fast_scan_directory", return_value=FAKE_FILES), \
             patch("core.readonly_producer.normalize_path", return_value="/src"):
            result = _list_source_videos("/src", {".mp4"}, 1024)

        assert result is FAKE_FILES


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
        assert _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index) is False

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
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index)

        assert result is False

    def test_cover_not_under_output_returns_false(self):
        """cover is not under this output_uri → rebuild."""
        from core.readonly_producer import _should_skip
        cover_index = {self.SOURCE_URI: "file:///other/cover.jpg"}

        with patch("core.readonly_producer.is_path_under_dir", return_value=False):
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index)

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
            result = _should_skip(self.SOURCE_URI, self.OUTPUT_URI, cover_index)

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
# T-2 tests: _format_data, _folder_parts, _build_basename, _movie_dir
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


class TestBuildOwners:
    """Tests for _build_owners."""

    def test_builds_dir_to_source_map(self):
        from core.readonly_producer import _build_owners
        cover_index = {
            'file:///src/a.mp4': 'file:///output/MovieA/cover.jpg',
        }
        with patch('core.readonly_producer.uri_to_fs_path', side_effect=lambda u: u[7:]):
            owners = _build_owners(cover_index)
        assert '/output/MovieA' in owners
        assert owners['/output/MovieA'] == 'file:///src/a.mp4'

    def test_empty_cover_skipped(self):
        from core.readonly_producer import _build_owners
        cover_index = {'file:///src/a.mp4': ''}
        owners = _build_owners(cover_index)
        assert owners == {}

    def test_none_cover_skipped(self):
        from core.readonly_producer import _build_owners
        cover_index = {'file:///src/a.mp4': None}
        owners = _build_owners(cover_index)
        assert owners == {}


class TestMovieLeafBase:
    """Tests for _movie_leaf_base."""

    def test_empty_stem_returns_number(self):
        from core.readonly_producer import _movie_leaf_base
        # sanitize_filename of an empty stem returns ''
        with patch('core.readonly_producer.uri_to_fs_path', return_value='/'), \
             patch('core.readonly_producer.sanitize_filename', return_value=''):
            result = _movie_leaf_base('ABC-123', 'file:///')
        assert result == 'ABC-123'

    def test_stem_equals_number_normalised(self):
        from core.readonly_producer import _movie_leaf_base
        with patch('core.readonly_producer.uri_to_fs_path', return_value='/src/ABC-123.mp4'), \
             patch('core.readonly_producer.normalize_number', return_value='ABC-123'), \
             patch('core.readonly_producer.sanitize_filename', side_effect=lambda x: x):
            result = _movie_leaf_base('ABC-123', 'file:///src/ABC-123.mp4')
        assert result == 'ABC-123'

    def test_stem_contains_number_returns_stem(self):
        from core.readonly_producer import _movie_leaf_base
        with patch('core.readonly_producer.uri_to_fs_path', return_value='/src/ABC-123-VR.mp4'), \
             patch('core.readonly_producer.normalize_number', return_value='ABC-123-VR'), \
             patch('core.readonly_producer.sanitize_filename', side_effect=lambda x: x):
            result = _movie_leaf_base('ABC-123', 'file:///src/ABC-123-VR.mp4')
        # stem 'ABC-123-VR' contains 'ABC-123'
        assert result == 'ABC-123-VR'

    def test_unrelated_stem_prefixes_number(self):
        from core.readonly_producer import _movie_leaf_base
        with patch('core.readonly_producer.uri_to_fs_path', return_value='/src/random_name.mp4'), \
             patch('core.readonly_producer.normalize_number', return_value='RANDOM_NAME'), \
             patch('core.readonly_producer.sanitize_filename', side_effect=lambda x: x):
            result = _movie_leaf_base('ABC-123', 'file:///src/random_name.mp4')
        assert result == 'ABC-123-random_name'


class TestMovieDir:
    """Tests for _movie_dir collision-avoidance."""

    OUTPUT_ROOT = '/output'
    BASE_CONFIG = {
        'folder_layers': [],
        'folder_format': '{num}',
        'max_filename_length': 60,
        'filename_format': '{num} {title}',
    }

    def _fd(self, number='ABC-123'):
        return {'number': number, 'title': 'Title', 'actors': [], 'maker': '', 'date': '', 'suffix': ''}

    def _patch_leaf(self, leaf):
        return patch('core.readonly_producer._movie_leaf_base', return_value=leaf)

    def _patch_exists(self, exists=False):
        return patch('core.readonly_producer.Path.exists', return_value=exists)

    def test_same_number_two_paths_distinct_dirs(self):
        """Same number → same leaf for two source URIs in ONE run → second collides → hashed dir."""
        from core.readonly_producer import _movie_dir
        fd = self._fd('ABC-123')
        owners: dict = {}
        src_a = 'file:///a/ABC-123.mp4'
        src_b = 'file:///b/ABC-123.mp4'

        # both resolve to the SAME leaf → exercises the in-run collision/hash branch
        with patch('core.readonly_producer._movie_leaf_base', return_value='ABC-123'), \
             self._patch_exists(False):
            dir_a = _movie_dir(self.OUTPUT_ROOT, fd, src_a, self.BASE_CONFIG, owners)
            dir_b = _movie_dir(self.OUTPUT_ROOT, fd, src_b, self.BASE_CONFIG, owners)

        assert dir_a.name == 'ABC-123'                 # first source: bare leaf, no hash
        assert dir_b != dir_a                          # collision → hashed (RED if hash branch removed)
        assert dir_b.name.startswith('ABC-123-')       # hash suffix present
        assert owners[str(dir_a)] == src_a             # first owner not overwritten by second

    def test_cross_run_existing_owner_not_overwritten(self):
        """owners pre-seeded with movie_dir→srcA; srcB hashes to new dir, srcA entry unchanged."""
        from core.readonly_producer import _movie_dir
        fd = self._fd('ABC-123')
        src_a = 'file:///a/ABC-123.mp4'
        src_b = 'file:///b/ABC-123.mp4'
        movie_dir_a = str(Path(self.OUTPUT_ROOT, 'ABC-123'))
        owners = {movie_dir_a: src_a}

        with self._patch_leaf('ABC-123'), self._patch_exists(False):
            dir_b = _movie_dir(self.OUTPUT_ROOT, fd, src_b, self.BASE_CONFIG, owners)

        assert str(dir_b) != movie_dir_a
        assert owners[movie_dir_a] == src_a  # not overwritten

    def test_disk_orphan_gets_hashed_dir(self):
        """Candidate exists on disk, owners empty → hash suffix applied."""
        from core.readonly_producer import _movie_dir
        fd = self._fd('ABC-123')
        owners: dict = {}
        src = 'file:///src/ABC-123.mp4'

        with self._patch_leaf('ABC-123'), self._patch_exists(True):
            result = _movie_dir(self.OUTPUT_ROOT, fd, src, self.BASE_CONFIG, owners)

        # The plain candidate exists → hash suffix; result should not be bare 'ABC-123'
        assert result.name != 'ABC-123'

    def test_idempotent_same_source(self):
        """Calling _movie_dir twice with same source_uri → same dir."""
        from core.readonly_producer import _movie_dir
        fd = self._fd('ABC-123')
        owners: dict = {}
        src = 'file:///src/ABC-123.mp4'

        with self._patch_leaf('ABC-123'), self._patch_exists(False):
            dir1 = _movie_dir(self.OUTPUT_ROOT, fd, src, self.BASE_CONFIG, owners)
            dir2 = _movie_dir(self.OUTPUT_ROOT, fd, src, self.BASE_CONFIG, owners)

        assert dir1 == dir2

    def test_leaf_enforcement_different_numbers(self):
        """folder_layers=['{actor}'], same actor, different numbers → different dirs."""
        from core.readonly_producer import _movie_dir
        config = dict(self.BASE_CONFIG, folder_layers=['{actor}'])
        fd_a = {'number': 'ABC-001', 'title': 'T', 'actors': ['Actress A'], 'maker': '', 'date': '', 'suffix': ''}
        fd_b = {'number': 'ABC-002', 'title': 'T', 'actors': ['Actress A'], 'maker': '', 'date': '', 'suffix': ''}
        owners: dict = {}
        src_a = 'file:///src/ABC-001.mp4'
        src_b = 'file:///src/ABC-002.mp4'

        with patch('core.readonly_producer._movie_leaf_base', side_effect=['ABC-001', 'ABC-002']), \
             self._patch_exists(False):
            dir_a = _movie_dir(self.OUTPUT_ROOT, fd_a, src_a, config, owners)
            dir_b = _movie_dir(self.OUTPUT_ROOT, fd_b, src_b, config, owners)

        assert dir_a != dir_b


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


class TestUpsertDb:
    """T-3: DB field correctness, cover_path local URI, sample_images local URIs."""

    SOURCE_URI = 'file:///src/TEST-001.mp4'

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

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None)

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

    def test_cover_path_is_local_uri_not_remote(self, tmp_path, temp_db):
        """cover_path in DB must be a file:/// URI, never the remote cover URL (CD-88b-7)."""
        from core.readonly_producer import _upsert_db

        cover_fs = str(tmp_path / 'output' / 'TEST-001' / 'cover.jpg')
        assets = {'cover_fs': cover_fs, 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None)

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

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None)

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

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None)

        v = repo.get_by_path(self.SOURCE_URI)
        assert v.cover_path == ''

    def test_empty_sample_images_stored_as_empty_list(self, temp_db):
        """sample_fs=[] → DB sample_images==[]."""
        from core.readonly_producer import _upsert_db

        assets = {'cover_fs': '', 'sample_fs': []}
        repo = self._repo(temp_db)

        _upsert_db(repo, self.SOURCE_URI, _T3_FILE_INFO, _T3_META, assets, None)

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
        """source.output_path='' → aborted_reason='no_output_path', search_jav not called."""
        from core.readonly_producer import produce_source

        source = _make_source(output_path="")
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()        # early return blocked all downstream work
        mock_search.assert_not_called()

    def test_whitespace_output_path_returns_aborted(self):
        """source.output_path='   ' → aborted_reason='no_output_path'."""
        from core.readonly_producer import produce_source

        source = _make_source(output_path="   ")
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()
        mock_search.assert_not_called()

    def test_none_output_path_returns_aborted(self):
        """source.output_path=None → aborted_reason='no_output_path'."""
        from core.readonly_producer import produce_source

        source = _make_source(output_path=None)
        repo = MagicMock()
        config = _make_config()

        with patch("core.readonly_producer._list_source_videos") as mock_list, \
             patch("core.readonly_producer.search_jav") as mock_search:
            result = produce_source(source, config, repo)

        assert result.aborted_reason == "no_output_path"
        mock_list.assert_not_called()
        mock_search.assert_not_called()


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
             patch("core.readonly_producer._build_owners", return_value={}), \
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
             patch("core.readonly_producer._build_owners", return_value={}), \
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
        config = _make_config()

        def fake_should_skip(src_uri, output_uri, cover_index):
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
             patch("core.readonly_producer._build_owners", return_value={}), \
             patch("core.readonly_producer._should_skip", side_effect=fake_should_skip), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", side_effect=fake_extract_number), \
             patch("core.readonly_producer.search_jav", side_effect=fake_search_jav), \
             patch("core.readonly_producer._format_data", return_value={"number": "X", "title": "T", "actors": [], "maker": "", "date": "", "suffix": ""}), \
             patch("core.readonly_producer._movie_dir", return_value=mock_movie_dir), \
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
             patch("core.readonly_producer._build_owners", return_value={}), \
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
             patch("core.readonly_producer._build_owners", return_value={}), \
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

        def fake_write(movie_dir, meta_arg, fd_arg, src_path, cfg):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("disk full")
            return {"cover_fs": "", "sample_fs": []}

        mock_movie_dir = MagicMock()
        mock_movie_dir.__str__ = lambda self: "/output/dest/X"

        with patch("core.readonly_producer._list_source_videos", return_value=files), \
             patch("core.readonly_producer._build_cover_index", return_value={}), \
             patch("core.readonly_producer._build_owners", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_producer._format_data", return_value=fd), \
             patch("core.readonly_producer._movie_dir", return_value=mock_movie_dir), \
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
             patch("core.readonly_producer._build_owners", return_value={}), \
             patch("core.readonly_producer._should_skip", return_value=False), \
             patch("core.readonly_producer.normalize_path", return_value="/output/dest"), \
             patch("core.readonly_producer.to_file_uri", side_effect=_fake_to_file_uri), \
             patch("core.readonly_producer.extract_number", return_value="MOCK-001"), \
             patch("core.readonly_producer.search_jav", return_value=meta), \
             patch("core.readonly_producer._format_data", return_value=fd), \
             patch("core.readonly_producer._movie_dir", return_value=mock_movie_dir), \
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
