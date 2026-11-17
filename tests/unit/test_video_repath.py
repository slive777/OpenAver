"""Scanner-form URI matching for video repath."""
import pytest

from core.video_repath import scan_form_uri


@pytest.mark.parametrize(
    ("new_uri", "sources", "entries", "expected"),
    [
        ("file:///d:/av/abf-348.mkv", ["file:///D:/AV"],
         {"file:///D:/AV": ["ABF-348.mkv"]}, "file:///D:/AV/ABF-348.mkv"),
        ("file:///d:/av/abf.mkv", ["file:///D:/AV"],
         {"file:///D:/AV": ["ABF.mkv", "Abf.mkv"]}, None),
        ("file:///d:/cafe\u0301/abf.mkv", ["file:///D:/Café"],
         {"file:///D:/Café": ["ABF.mkv"]}, "file:///D:/Café/ABF.mkv"),
        ("file:///tmp/av/abf.mkv", ["file:///tmp/av"],
         {"file:///tmp/av": ["ABF.mkv"]}, None),
        ("file:////tmp/ABF.mkv", ["file:////"],
         {"file:///": ["tmp"], "file:////tmp": ["ABF.mkv"]}, "file:////tmp/ABF.mkv"),
        ("file:///tmp/av/ABF.mkv", ["file:///tmp/av"],
         {"file:///tmp/av": ["ABF.mkv"]}, "file:///tmp/av/ABF.mkv"),
    ],
)
def test_scan_form_uri_table(new_uri, sources, entries, expected):
    """輸入路徑以掃描器的來源與檔名原字面存入，拒絕歧義。"""
    assert scan_form_uri(new_uri, sources, entries.get) == expected
