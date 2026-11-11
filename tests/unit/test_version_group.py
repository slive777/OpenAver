"""TASK-198b-T1: core.version_group 多版本分組／預設順序／沿用來源／bulk 反解。"""

import pytest

from core.database import Video
from core.path_utils import to_file_uri, uri_to_local_fs_path
from core.version_group import (
    group_works,
    representative_paths,
    resolve_work,
    resolve_works_bulk,
    version_containing,
    work_key_of_row,
)


def _uri(fs_path: str) -> str:
    return to_file_uri(fs_path)


def _fs(row: Video) -> str:
    return uri_to_local_fs_path(row.path, {})


def _v(
    fs_path: str,
    number=None,
    mtime=0.0,
    nfo_mtime=0.0,
    tags=None,
) -> Video:
    return Video(
        path=_uri(fs_path),
        number=number,
        mtime=mtime,
        nfo_mtime=nfo_mtime,
        tags=list(tags) if tags else [],
    )


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    def get_by_folder_uri_prefix(self, prefix):
        self.calls.append(prefix)
        return [r for r in self._rows if r.path.startswith(prefix)]


def _sig(work):
    if work is None:
        return None
    return [m.path for v in work.versions for m in v.members]


@pytest.mark.parametrize(
    "case",
    ["same_folder_three", "cross_folder", "no_number", "multipart_plus_single"],
)
def test_work_grouping(case):
    if case == "same_folder_three":
        rows = [
            _v("/media/a/ABF-348-LTX.mkv", number="ABF-348"),
            _v("/media/a/ABF-348.mp4", number="ABF-348"),
            _v("/media/a/ABF-348-C.mkv", number="abf-348 "),
        ]
        expect_n_works, expect_n_versions = 1, [3]
    elif case == "cross_folder":
        rows = [
            _v("/media/dirB/ABF-348.mp4", number="ABF-348"),
            _v("/media/dirA/ABF-348.mp4", number="ABF-348"),
        ]
        expect_n_works, expect_n_versions = 2, [1, 1]
    elif case == "no_number":
        rows = [
            _v("/media/a/X.mp4", number=None),
            _v("/media/a/Y.mp4", number="   "),
        ]
        expect_n_works, expect_n_versions = 2, [1, 1]
    else:
        rows = [
            _v("/media/a/ABF-349.mp4", number="ABF-349"),
            _v("/media/a/ABF-349-C-cd2.mkv", number="ABF-349"),
            _v("/media/a/ABF-349-C-cd1.mkv", number="ABF-349"),
        ]
        expect_n_works, expect_n_versions = 1, [2]
    works = group_works(rows, _fs)
    assert len(works) == expect_n_works
    assert [len(w.versions) for w in works] == expect_n_versions
    assert len({work_key_of_row(r, _fs(r)) for r in rows}) == expect_n_works
    if case == "cross_folder":
        assert works[0].versions[0].members[0].path == _uri("/media/dirB/ABF-348.mp4")
    if case == "multipart_plus_single":
        assert works[0].versions[0].part_tokens == ["cd1", "cd2"]


@pytest.mark.parametrize(
    "case",
    [
        "subtitle_beats_tier",
        "tier_without_subtitle",
        "unprobed_last",
        "original_beats_ltx",
        "mtime_newest",
    ],
)
def test_default_order(case):
    if case == "subtitle_beats_tier":
        rows = [
            _v("/media/ord/ABF-348-LTX.mkv", number="ABF-348", mtime=300, nfo_mtime=10),
            _v("/media/ord/ABF-348.mp4", number="abf-348 ", mtime=200, nfo_mtime=10),
            _v("/media/ord/ABF-348.x-C.mkv", number="ABF-348", mtime=100, nfo_mtime=10),
        ]
        tiers = {rows[0].path: "4K", rows[1].path: "4K", rows[2].path: "SD"}
        expect_order = [rows[2].path]
    elif case == "tier_without_subtitle":
        rows = [
            _v("/media/ord2/ABF-348-UHD.mkv", number="ABF-348", mtime=200, nfo_mtime=10),
            _v("/media/ord2/ABF-348.mp4", number="ABF-348", mtime=100, nfo_mtime=10),
        ]
        tiers = {rows[0].path: "FHD", rows[1].path: "4K"}
        expect_order = [rows[1].path]
    elif case == "unprobed_last":
        rows = [
            _v("/media/ord3/ABF-348-BAK.mkv", number="ABF-348", mtime=300, nfo_mtime=10),
            _v("/media/ord3/ABF-348-ALT.mkv", number="ABF-348", mtime=200, nfo_mtime=10),
            _v("/media/ord3/ABF-348.mp4", number="ABF-348", mtime=100, nfo_mtime=10),
        ]
        tiers = {rows[0].path: "weird", rows[2].path: "FHD"}
        expect_order = [rows[2].path]
    elif case == "original_beats_ltx":
        rows = [
            _v("/media/ord4/ABF-348-LTX.mkv", number="ABF-348", mtime=200, nfo_mtime=10),
            _v("/media/ord4/ABF-348.mp4", number="ABF-348", mtime=100, nfo_mtime=10),
        ]
        tiers = {rows[0].path: "FHD", rows[1].path: "FHD"}
        expect_order = [rows[1].path]
    else:
        rows = [
            _v("/media/ord5/ABF-348-B.mkv", number="ABF-348", mtime=None, nfo_mtime=10),
            _v("/media/ord5/ABF-348-A.mkv", number="ABF-348", mtime=0, nfo_mtime=10),
            _v("/media/ord5/ABF-348.mp4", number="ABF-348", mtime=300, nfo_mtime=10),
        ]
        tiers = {r.path: "FHD" for r in rows}
        expect_order = [rows[2].path, rows[1].path, rows[0].path]
    works = group_works(rows, _fs, tier_of=lambda r: tiers.get(r.path))
    assert len(works) == 1
    got = [v.members[0].path for v in works[0].versions]
    assert got[: len(expect_order)] == expect_order


@pytest.mark.parametrize(
    ("nfo_default", "nfo_second", "expected"),
    [(100, 200, 0), (0, 50, 1), (0, 0, None)],
)
def test_data_source(nfo_default, nfo_second, expected, monkeypatch):
    rows = [
        _v("/media/ds/ABF-348.mp4", number="ABF-348", mtime=100, nfo_mtime=nfo_second),
        _v("/media/ds/ABF-348-C.mkv", number="ABF-348", mtime=200, nfo_mtime=nfo_default),
    ]
    works = group_works(rows, _fs, tier_of=lambda r: "FHD")
    assert works[0].data_source == expected

    import core.version_group as vg

    kinds_calls = []
    real_kinds = vg.version_kinds

    def counting_kinds(*args, **kwargs):
        kinds_calls.append(1)
        return real_kinds(*args, **kwargs)

    monkeypatch.setattr(vg, "version_kinds", counting_kinds)
    tier_calls = []

    def counting_tier(row):
        tier_calls.append(row)
        return "FHD"

    solo = [_v("/media/s/SOLO-001.mp4", number="SOLO-001", nfo_mtime=nfo_default)]
    solo_works = group_works(solo, _fs, tier_of=counting_tier)
    assert tier_calls == []
    assert kinds_calls == []
    assert solo_works[0].data_source == (0 if nfo_default else None)


def test_resolve_works_bulk():
    rows = [
        _v("/media/a/ABF-348.mp4", number="ABF-348"),
        _v("/media/a/ABF-348-C.mkv", number="ABF-348"),
        _v("/media/a/SOLO-001.mp4", number="SOLO-001"),
        _v("/media/b/XYZ-9.mp4", number="XYZ-9"),
    ]
    targets = [r.path for r in rows] + [_uri("/media/a/NOT-THERE.mp4")]
    repo = _FakeRepo(rows)
    bulk = resolve_works_bulk(repo, targets, {})
    assert len(repo.calls) == 2
    for uri in targets:
        assert _sig(bulk[uri]) == _sig(resolve_work(_FakeRepo(rows), uri, {}))
    work = bulk[rows[0].path]
    assert representative_paths(work) == [v.members[0].path for v in work.versions]
    idx = version_containing(work, rows[1].path)
    assert rows[1].path in [m.path for m in work.versions[idx].members]
    assert version_containing(work, targets[-1]) is None
