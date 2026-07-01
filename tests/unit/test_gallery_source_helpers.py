"""Unit tests for iter_gallery_sources / get_gallery_source_paths helpers.

TDD-lite: each test is written to go RED if the helper logic is broken.
"""

from core.config import DirectoryConfig, GalleryConfig, iter_gallery_sources, get_gallery_source_paths


# ---------------------------------------------------------------------------
# Container-type edge cases
# ---------------------------------------------------------------------------

class TestContainerTypes:
    def test_none_returns_empty(self):
        assert iter_gallery_sources(None) == []

    def test_empty_dict_returns_empty(self):
        assert iter_gallery_sources({}) == []

    def test_dict_missing_directories_key_returns_empty(self):
        assert iter_gallery_sources({"other_key": "value"}) == []

    def test_gallery_config_empty_directories_returns_empty(self):
        gc = GalleryConfig()
        assert iter_gallery_sources(gc) == []

    def test_dict_with_empty_directories_returns_empty(self):
        assert iter_gallery_sources({"directories": []}) == []

    def test_dict_with_null_directories_returns_empty(self):
        # key present but value is null (not missing) — `raw or []` guard must hold
        assert iter_gallery_sources({"directories": None}) == []


# ---------------------------------------------------------------------------
# Element-type: str
# ---------------------------------------------------------------------------

class TestStrElement:
    def test_str_coerced_to_directory_config(self):
        result = iter_gallery_sources({"directories": ["/videos"]})
        assert len(result) == 1
        assert isinstance(result[0], DirectoryConfig)
        assert result[0].path == "/videos"

    def test_str_defaults_readonly_false(self):
        result = iter_gallery_sources({"directories": ["/videos"]})
        assert result[0].readonly is False

    def test_str_defaults_output_path_empty(self):
        result = iter_gallery_sources({"directories": ["/videos"]})
        assert result[0].output_path == ""


# ---------------------------------------------------------------------------
# Element-type: dict
# ---------------------------------------------------------------------------

class TestDictElement:
    def test_full_dict_element_preserved(self):
        elem = {"path": "/x", "readonly": True, "output_path": "/out"}
        result = iter_gallery_sources({"directories": [elem]})
        assert len(result) == 1
        dc = result[0]
        assert dc.path == "/x"
        assert dc.readonly is True
        assert dc.output_path == "/out"

    def test_dict_missing_readonly_defaults_false(self):
        elem = {"path": "/x", "output_path": "/out"}
        result = iter_gallery_sources({"directories": [elem]})
        assert result[0].readonly is False

    def test_dict_missing_output_path_defaults_empty(self):
        elem = {"path": "/x", "readonly": True}
        result = iter_gallery_sources({"directories": [elem]})
        assert result[0].output_path == ""

    def test_dict_missing_both_optional_fields(self):
        elem = {"path": "/x"}
        result = iter_gallery_sources({"directories": [elem]})
        dc = result[0]
        assert dc.path == "/x"
        assert dc.readonly is False
        assert dc.output_path == ""


# ---------------------------------------------------------------------------
# Element-type: DirectoryConfig instance
# ---------------------------------------------------------------------------

class TestDirectoryConfigElement:
    def test_directory_config_instance_passed_through(self):
        dc_in = DirectoryConfig(path="/z", readonly=True, output_path="/out2")
        result = iter_gallery_sources({"directories": [dc_in]})
        assert len(result) == 1
        assert result[0] is dc_in

    def test_directory_config_instance_via_gallery_config(self):
        gc = GalleryConfig(directories=["/z"])  # GalleryConfig.directories is List[str]
        result = iter_gallery_sources(gc)
        assert len(result) == 1
        assert result[0].path == "/z"


# ---------------------------------------------------------------------------
# Unknown element types — must be skipped, not crash
# ---------------------------------------------------------------------------

class TestUnknownElementTypes:
    def test_integer_element_skipped(self):
        result = iter_gallery_sources({"directories": [42]})
        assert result == []

    def test_none_element_skipped(self):
        result = iter_gallery_sources({"directories": [None]})
        assert result == []

    def test_unknown_mixed_with_valid_skips_unknown(self):
        result = iter_gallery_sources({"directories": ["/a", 42, None, "/b"]})
        assert len(result) == 2
        assert result[0].path == "/a"
        assert result[1].path == "/b"


# ---------------------------------------------------------------------------
# Mixed list: all three types together, order preserved
# ---------------------------------------------------------------------------

class TestMixedList:
    def test_mixed_str_dict_directoryconfig_order_preserved(self):
        dc = DirectoryConfig(path="/c", readonly=False, output_path="")
        dirs = [
            "/a",
            {"path": "/b", "readonly": True, "output_path": "/out"},
            dc,
        ]
        result = iter_gallery_sources({"directories": dirs})
        assert len(result) == 3
        assert result[0].path == "/a"
        assert result[1].path == "/b"
        assert result[1].readonly is True
        assert result[2] is dc

    def test_order_preserved_multiple_strings(self):
        result = iter_gallery_sources({"directories": ["/z", "/a", "/m"]})
        paths = [d.path for d in result]
        assert paths == ["/z", "/a", "/m"]


# ---------------------------------------------------------------------------
# GalleryConfig container (model instance)
# ---------------------------------------------------------------------------

class TestGalleryConfigContainer:
    def test_gallery_config_with_string_directories(self):
        gc = GalleryConfig(directories=["/foo", "/bar"])
        result = iter_gallery_sources(gc)
        assert len(result) == 2
        assert result[0].path == "/foo"
        assert result[1].path == "/bar"


# ---------------------------------------------------------------------------
# get_gallery_source_paths — thin wrapper equivalence
# ---------------------------------------------------------------------------

class TestGetGallerySourcePaths:
    def test_returns_list_of_strings(self):
        paths = get_gallery_source_paths({"directories": ["/a", "/b"]})
        assert paths == ["/a", "/b"]

    def test_bit_exact_equivalence_with_old_string_list(self):
        """get_gallery_source_paths must produce the same list as a raw str directories list."""
        old_style = ["/a", "/b"]
        result = get_gallery_source_paths({"directories": old_style})
        assert result == old_style

    def test_none_returns_empty_list(self):
        assert get_gallery_source_paths(None) == []

    def test_empty_dict_returns_empty_list(self):
        assert get_gallery_source_paths({}) == []

    def test_matches_iter_gallery_sources_paths(self):
        cfg = {"directories": ["/x", "/y"]}
        via_iter = [d.path for d in iter_gallery_sources(cfg)]
        via_helper = get_gallery_source_paths(cfg)
        assert via_helper == via_iter

    def test_dict_element_path_extracted(self):
        cfg = {"directories": [{"path": "/x", "readonly": True, "output_path": ""}]}
        assert get_gallery_source_paths(cfg) == ["/x"]

    def test_directory_config_element_path_extracted(self):
        dc = DirectoryConfig(path="/z", readonly=False, output_path="")
        cfg = {"directories": [dc]}
        assert get_gallery_source_paths(cfg) == ["/z"]


# ---------------------------------------------------------------------------
# DirectoryConfig model: field defaults & combinations
# ---------------------------------------------------------------------------

class TestDirectoryConfigModel:
    def test_default_readonly_false(self):
        dc = DirectoryConfig(path="/p")
        assert dc.readonly is False

    def test_default_output_path_empty(self):
        dc = DirectoryConfig(path="/p")
        assert dc.output_path == ""

    def test_readonly_true_with_empty_output_path_valid(self):
        dc = DirectoryConfig(path="/p", readonly=True, output_path="")
        assert dc.readonly is True
        assert dc.output_path == ""

    def test_readonly_false_with_nonempty_output_path_valid(self):
        dc = DirectoryConfig(path="/p", readonly=False, output_path="/out")
        assert dc.readonly is False
        assert dc.output_path == "/out"


# ---------------------------------------------------------------------------
# Robustness / security hardening (P1 + P2 findings)
# ---------------------------------------------------------------------------

class TestRobustness:
    """Verify that iter_gallery_sources DROPS entries without a usable non-empty string path
    and coerces null/wrong-type optional fields instead of crashing.

    P1: empty/missing path must not yield '' which becomes file:/// (universal allowlist bypass).
    P2: path=null must not raise ValidationError (dict key present with None value).
    """

    def test_dict_missing_path_key_skipped(self):
        """Dict entry with no 'path' key is dropped entirely."""
        dirs = [{"readonly": True}, {"path": "/valid"}]
        result = iter_gallery_sources({"directories": dirs})
        assert len(result) == 1
        assert result[0].path == "/valid"

    def test_dict_path_none_skipped_no_exception(self):
        """{'path': None} must be silently skipped — not raise ValidationError (P2)."""
        result = iter_gallery_sources({"directories": [{"path": None}]})
        assert result == []

    def test_dict_path_empty_string_skipped(self):
        """{'path': ''} must be silently skipped (P1: empty path → file:/// bypass)."""
        result = iter_gallery_sources({"directories": [{"path": ""}]})
        assert result == []

    def test_str_empty_string_skipped(self):
        """Bare empty string element must be silently skipped."""
        result = iter_gallery_sources({"directories": [""]})
        assert result == []

    def test_dict_readonly_none_coerced_to_false(self):
        """readonly=null must NOT crash; coerced to False."""
        result = iter_gallery_sources({"directories": [{"path": "/x", "readonly": None}]})
        assert len(result) == 1
        assert result[0].readonly is False

    def test_dict_output_path_none_coerced_to_empty(self):
        """output_path=null must NOT crash; coerced to ''."""
        result = iter_gallery_sources({"directories": [{"path": "/x", "output_path": None}]})
        assert len(result) == 1
        assert result[0].output_path == ""

    def test_dict_readonly_wrong_type_coerced_to_false(self):
        """readonly with wrong type (str) is coerced to False, not passed to Pydantic."""
        result = iter_gallery_sources({"directories": [{"path": "/x", "readonly": "true"}]})
        assert len(result) == 1
        assert result[0].readonly is False

    def test_mixed_bad_and_good_entries_only_good_emitted(self):
        """Mix of bad entries (missing/null/empty path) plus valid ones — only valid survive."""
        dirs = [
            {"readonly": True},           # missing path
            {"path": None},               # null path
            {"path": ""},                 # empty path
            "",                            # bare empty string
            {"path": "/good1"},
            "/good2",
        ]
        result = iter_gallery_sources({"directories": dirs})
        assert len(result) == 2
        assert result[0].path == "/good1"
        assert result[1].path == "/good2"

    def test_get_gallery_source_paths_never_yields_empty_or_none(self):
        """get_gallery_source_paths must never include '' or None in its output."""
        dirs = [
            {"path": None},
            {"path": ""},
            "",
            {"readonly": False},
            {"path": "/ok"},
        ]
        paths = get_gallery_source_paths({"directories": dirs})
        assert "" not in paths
        assert None not in paths
        assert paths == ["/ok"]
