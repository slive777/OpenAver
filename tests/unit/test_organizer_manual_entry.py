"""TASK-183-T4：空白卡手填標題（metadata.manual_entry）不被檔名提取的片名蓋掉。"""
from core.organizer import organize_file

_CONFIG = {
    "create_folder": False,
    "filename_format": "{num} {title}",
    "download_cover": False,
    "create_nfo": False,
    "max_title_length": 50,
    "max_filename_length": 120,
    "suffix_keywords": [],
}


def _run(tmp_path, sub, extra):
    d = tmp_path / sub
    d.mkdir()
    src = d / "JURA-1113 - 複製.mp4"
    src.write_bytes(b"dummy")
    meta = {"number": "JURA-1113", "title": "手動標題", "actors": [], "tags": [],
            "maker": "", "date": "", "cover": "", "url": "", **extra}
    return organize_file(str(src), meta, _CONFIG)


def test_manual_entry_title_beats_filename_extraction(tmp_path):
    r = _run(tmp_path, "manual", {"manual_entry": True})
    assert r["success"]
    assert "手動標題" in r["new_filename"] and "複製" not in r["new_filename"]
    assert r["title_source"] == "original"

    r = _run(tmp_path, "plain", {})
    assert r["success"]
    assert "複製" in r["new_filename"]
    assert r["title_source"] == "extracted"
