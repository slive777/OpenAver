"""test_dir_candidate_forms.py — `_dir_candidate_forms` URI-idempotency (PR#91 P2-D).

`_dir_candidate_forms` backs BOTH the /api/gallery/image and /api/gallery/video
directory allowlists. DirectoryConfig.path may be an FS path OR a file:/// URI
(schema「FS 路徑或 URI」). A URI input must yield the SAME candidate URI as the
equivalent FS input — never a double-wrapped `file:///file:///…` (which the
pre-fix `to_file_uri(os.path.normpath(raw_dir))` produced for URI input).

Pure function; each call uses a distinct raw_dir so the module-level TTL cache
(keyed on raw_dir) never cross-contaminates between assertions.
"""

import os

from core.path_utils import is_path_under_dir, to_file_uri
from web.routers.scanner import _dir_candidate_forms


class TestDirCandidateFormsUriIdempotent:
    def test_uri_input_not_double_wrapped(self, tmp_path):
        """URI-form dir → candidate URIs contain no 'file:///file:///' double-wrap."""
        d = tmp_path / "srcU1"
        d.mkdir()
        uri = to_file_uri(str(d), {})

        forms = _dir_candidate_forms(uri, {})

        assert forms, "expected at least one candidate form"
        for f in forms:
            assert f.startswith("file:///")
            # no double-wrap in any form (actual pre-fix bug was file:///file:/…)
            assert not f.removeprefix("file:///").startswith("file:")

    def test_uri_and_fs_input_agree(self, tmp_path):
        """URI-form and FS-form of the same dir produce matching candidate URIs."""
        d = tmp_path / "srcU2"
        d.mkdir()

        fs_forms = set(_dir_candidate_forms(str(d), {}))
        uri_forms = set(_dir_candidate_forms(to_file_uri(str(d), {}), {}))

        assert fs_forms == uri_forms

    def test_uri_dir_matches_child_file(self, tmp_path):
        """A file under a URI-form source dir is recognised as under one candidate form."""
        d = tmp_path / "srcU3"
        d.mkdir()
        child = d / "movie.mp4"
        child.write_bytes(b"x")

        forms = _dir_candidate_forms(to_file_uri(str(d), {}), {})
        child_uri = to_file_uri(os.path.realpath(str(child)), {})

        assert any(is_path_under_dir(child_uri, f) for f in forms)

    def test_fs_input_still_dual_form(self, tmp_path):
        """FS input keeps working (normpath + realpath dual-form preserved)."""
        d = tmp_path / "srcU4"
        d.mkdir()

        forms = _dir_candidate_forms(str(d), {})
        expected = to_file_uri(os.path.realpath(str(d)), {})

        assert expected in forms
