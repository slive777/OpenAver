"""TASK-198b-T5：撞名補版本標記（I-ORG-1 golden + I-ORG-3/4/5/6/7）。

I-ORG-1 的 GOLDEN 字面取自 HEAD 9918c607、T5 改動前（產品碼未動時即綠）。
"""
import os

import pytest

from core.organizer import organize_file


def _make_config(external_manager, with_suffix):
    """T5 測試用 config。external_manager 必填、無預設值（BE-TEST-06）。"""
    return {
        "create_folder": False,
        "filename_format": "[{num}][{maker}] {title}{suffix}" if with_suffix else "[{num}][{maker}] {title}",
        "download_cover": False,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
        "external_manager": external_manager,
    }


def _make_metadata():
    return {
        "number": "ABF-348",
        "title": "title",
        "actors": [],
        "tags": [],
        "maker": "maker",
        "date": "",
        "cover": "",
        "url": "",
    }


def _golden_run(tmp_path, external_manager, with_suffix, with_part):
    src_name = "ABF-348-4k" + ("-cd1" if with_part else "") + ".mp4"
    src = tmp_path / src_name
    src.write_bytes(b"golden-src")
    uploaded = None
    if external_manager == "off":
        cover_src = tmp_path / "upload.jpg"
        cover_src.write_bytes(b"golden-cover-bytes")
        uploaded = str(cover_src)
    result = organize_file(str(src), _make_metadata(), _make_config(external_manager, with_suffix), uploaded_cover=uploaded)
    assert result["success"] is True, result
    new_name = os.path.basename(result["new_filename"])
    nfo_name = os.path.basename(result["nfo_path"])
    cover_name = os.path.basename(result["cover_path"]) if result.get("cover_path") else None
    return (new_name, nfo_name, cover_name)


GOLDEN = {  # golden 取自 HEAD 9918c607、T5 改動前
    ("off", True, True): ("[ABF-348][maker] title-cd1-4k.mp4", "[ABF-348][maker] title-cd1-4k.nfo", "[ABF-348][maker] title-cd1-4k.jpg"),
    ("off", True, False): ("[ABF-348][maker] title-4k.mp4", "[ABF-348][maker] title-4k.nfo", "[ABF-348][maker] title-4k.jpg"),
    ("off", False, True): ("[ABF-348][maker] title.mp4", "[ABF-348][maker] title.nfo", "[ABF-348][maker] title.jpg"),
    ("off", False, False): ("[ABF-348][maker] title.mp4", "[ABF-348][maker] title.nfo", "[ABF-348][maker] title.jpg"),
    ("jellyfin", True, True): ("[ABF-348][maker] title-4k-cd1.mp4", "[ABF-348][maker] title-4k-cd1.nfo", None),
    ("jellyfin", True, False): ("[ABF-348][maker] title-4k.mp4", "[ABF-348][maker] title-4k.nfo", None),
    ("jellyfin", False, True): ("[ABF-348][maker] title-cd1.mp4", "[ABF-348][maker] title-cd1.nfo", None),
    ("jellyfin", False, False): ("[ABF-348][maker] title.mp4", "[ABF-348][maker] title.nfo", None),
}


@pytest.mark.parametrize("external_manager", ["off", "jellyfin"])
@pytest.mark.parametrize("with_suffix", [True, False])
@pytest.mark.parametrize("with_part", [True, False])
def test_i_org_1_successful_names_unchanged(tmp_path, external_manager, with_suffix, with_part):
    assert _golden_run(tmp_path, external_manager, with_suffix, with_part) == GOLDEN[(external_manager, with_suffix, with_part)]


def _organize_ltx(tmp_path, src_bytes):
    (tmp_path / "[ABF-348][maker] title.mp4").write_bytes(b"orig")
    src = tmp_path / "ABF-348-LTX.mp4"
    src.write_bytes(src_bytes)
    cover_src = tmp_path / "upload.jpg"
    cover_src.write_bytes(b"new-cover")
    result = organize_file(str(src), _make_metadata(), _make_config("off", True), uploaded_cover=str(cover_src))
    assert result["success"] is True, result
    return result


@pytest.mark.parametrize("case", ["a", "b", "c", "d", "e", "e2", "f1-off", "f1-jf", "f2-maker", "f3-uhd"])
def test_i_org_7_marker_import_matrix(tmp_path, case):
    if case == "a":
        existing = tmp_path / "[ABF-348][maker] title.mp4"
        existing.write_bytes(b"orig")
        existing_nfo = tmp_path / "[ABF-348][maker] title.nfo"
        existing_nfo.write_bytes(b"orig-nfo")
        existing_cover = tmp_path / "[ABF-348][maker] title.jpg"
        existing_cover.write_bytes(b"orig-cover")
        orig_video = existing.read_bytes()
        orig_nfo = existing_nfo.read_bytes()
        orig_cover = existing_cover.read_bytes()
        before_names = sorted(os.listdir(tmp_path))
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        cover_src = tmp_path / "upload.jpg"
        cover_src.write_bytes(b"new-cover")
        result = organize_file(str(src), _make_metadata(), _make_config("off", True), uploaded_cover=str(cover_src))
        assert result["success"] is True, result
        assert os.path.basename(result["new_filename"]) == "[ABF-348][maker] title-LTX.mp4"
        assert (tmp_path / "[ABF-348][maker] title-LTX.mp4").exists()
        assert (tmp_path / "[ABF-348][maker] title-LTX.nfo").exists()
        assert (tmp_path / "[ABF-348][maker] title-LTX.jpg").exists()
        assert existing.read_bytes() == orig_video
        assert existing_nfo.read_bytes() == orig_nfo
        assert existing_cover.read_bytes() == orig_cover
    elif case == "b":
        for name, data in [
            ("[ABF-348][maker] title.mp4", b"orig"),
            ("[ABF-348][maker] title-LTX.mkv", b"other-video"),
            ("[ABF-348][maker] title-LTX.nfo", b"other-nfo"),
            ("[ABF-348][maker] title-LTX.jpg", b"other-cover"),
        ]:
            (tmp_path / name).write_bytes(data)
        before_names = sorted(os.listdir(tmp_path))
        before_bytes = {n: (tmp_path / n).read_bytes() for n in before_names}
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        cover_src = tmp_path / "upload.jpg"
        cover_src.write_bytes(b"new-cover")
        result = organize_file(str(src), _make_metadata(), _make_config("off", True), uploaded_cover=str(cover_src))
        assert result.get("duplicate") is True, result
        assert result["success"] is False
        assert src.exists()
        for n in before_names:
            assert (tmp_path / n).read_bytes() == before_bytes[n]
        assert sorted(os.listdir(tmp_path)) == sorted(before_names + ["ABF-348-LTX.mp4", "upload.jpg"])
    elif case == "c":
        existing = tmp_path / "ABF-348.mp4"
        existing.write_bytes(b"orig")
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        config = dict(_make_config("off", True))
        config["filename_format"] = "{num}"
        result = organize_file(str(src), _make_metadata(), config)
        ctrl_dir = tmp_path / "ctrl_c"
        ctrl_dir.mkdir()
        csrc = ctrl_dir / "ABF-348-LTX.mp4"
        csrc.write_bytes(b"src-ltx")
        cconfig = dict(_make_config("off", True))
        cconfig["filename_format"] = "{num}-LTX"
        ctrl = organize_file(str(csrc), _make_metadata(), cconfig)
        assert ctrl["success"] is True, ctrl
        assert result["success"] is True, result
        assert os.path.basename(result["new_filename"]) == os.path.basename(ctrl["new_filename"])
        assert os.path.basename(result["nfo_path"]) == os.path.basename(ctrl["nfo_path"])
        got_side = sorted(n for n in os.listdir(tmp_path) if os.path.isfile(tmp_path / n) and n not in ("ABF-348.mp4", "ABF-348-LTX.mp4"))
        ctrl_side = sorted(n for n in os.listdir(ctrl_dir) if n != "ABF-348-LTX.mp4")
        assert got_side == ctrl_side, (got_side, ctrl_side)
    elif case == "d":
        existing = tmp_path / "ABF-348.mp4"
        existing.write_bytes(b"orig")
        (tmp_path / "ABF-348-LTX.nfo").write_bytes(b"own-nfo")
        (tmp_path / "ABF-348-LTX.jpg").write_bytes(b"own-cover")
        config = dict(_make_config("off", True))
        config["filename_format"] = "{num}"
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        result = organize_file(str(src), _make_metadata(), config)
        ctrl_dir = tmp_path / "ctrl_d"
        ctrl_dir.mkdir()
        csrc = ctrl_dir / "ABF-348-LTX.mp4"
        csrc.write_bytes(b"src-ltx")
        (ctrl_dir / "ABF-348-LTX.nfo").write_bytes(b"own-nfo")
        (ctrl_dir / "ABF-348-LTX.jpg").write_bytes(b"own-cover")
        cconfig = dict(_make_config("off", True))
        cconfig["filename_format"] = "{num}-LTX"
        ctrl = organize_file(str(csrc), _make_metadata(), cconfig)
        assert ctrl["success"] is True, ctrl
        assert result["success"] is True, result
        assert os.path.basename(result["new_filename"]) == os.path.basename(ctrl["new_filename"])
        assert os.path.basename(result["nfo_path"]) == os.path.basename(ctrl["nfo_path"])
        got_side = sorted(n for n in os.listdir(tmp_path) if os.path.isfile(tmp_path / n) and n not in ("ABF-348.mp4", "ABF-348-LTX.mp4", "ABF-348-LTX.nfo", "ABF-348-LTX.jpg"))
        ctrl_side = sorted(n for n in os.listdir(ctrl_dir) if n not in ("ABF-348-LTX.mp4", "ABF-348-LTX.nfo", "ABF-348-LTX.jpg"))
        assert got_side == ctrl_side, (got_side, ctrl_side)
    elif case == "e2":
        existing = tmp_path / "ABF-348.mp4"
        existing.write_bytes(b"orig")
        for name, data in [
            ("abf-348-ltx.mkv", b"other-video"),
            ("abf-348-ltx.nfo", b"other-nfo"),
            ("abf-348-ltx.jpg", b"other-cover"),
        ]:
            (tmp_path / name).write_bytes(data)
        before_names = sorted(os.listdir(tmp_path))
        before_bytes = {n: (tmp_path / n).read_bytes() for n in before_names}
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        config = dict(_make_config("off", True))
        config["filename_format"] = "{num}"
        result = organize_file(str(src), _make_metadata(), config)
        assert result.get("duplicate") is True, result
        assert result["success"] is False
        assert src.exists()
        for n in before_names:
            assert (tmp_path / n).read_bytes() == before_bytes[n]
        assert sorted(os.listdir(tmp_path)) == sorted(before_names + ["ABF-348-LTX.mp4"])
    elif case in ("f1-off", "f1-jf"):
        ext_mode = "jellyfin" if case == "f1-jf" else "off"
        existing = tmp_path / ("ABF-348 タイトル-cd1.mp4" if ext_mode == "off" else "ABF-348-cd1.mp4")
        existing.write_bytes(b"orig")
        orig_video = existing.read_bytes()
        src = tmp_path / "ABF-348-C-cd1.mp4"
        src.write_bytes(b"src-c")
        config = dict(_make_config(ext_mode, False))
        config["filename_format"] = "{num} {title}{suffix}" if ext_mode == "off" else "{num}"
        metadata = _make_metadata()
        metadata["title"] = "タイトル"
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, result
        stem = os.path.splitext(os.path.basename(result["new_filename"]))[0]
        assert "-C" in stem, stem
        assert stem.endswith("-cd1"), stem
        assert existing.read_bytes() == orig_video
    elif case == "f2-maker":
        existing = tmp_path / "[ABF-348][S-Cute] title.mp4"
        existing.write_bytes(b"orig")
        orig_video = existing.read_bytes()
        before_names = sorted(os.listdir(tmp_path))
        src = tmp_path / "ABF-348-C.mp4"
        src.write_bytes(b"src-c")
        config = dict(_make_config("off", True))
        config["filename_format"] = "[{num}][{maker}] {title}"
        metadata = _make_metadata()
        metadata["maker"] = "S-Cute"
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, result
        stem = os.path.splitext(os.path.basename(result["new_filename"]))[0]
        assert "-C" in stem, stem
        assert existing.read_bytes() == orig_video
    elif case == "f3-uhd":
        existing = tmp_path / "[ABF-348][maker] title.mp4"
        existing.write_bytes(b"orig")
        (tmp_path / "[ABF-348][maker] title.nfo").write_bytes(
            b'<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABF-348</num><genre>4K</genre></movie>'
        )
        orig_video = existing.read_bytes()
        orig_nfo = (tmp_path / "[ABF-348][maker] title.nfo").read_bytes()
        src = tmp_path / "ABF-348-uhd.mp4"
        src.write_bytes(b"src-uhd")
        result = organize_file(str(src), _make_metadata(), _make_config("off", True))
        assert result["success"] is True, result
        stem = os.path.splitext(os.path.basename(result["new_filename"]))[0]
        assert "-uhd" in stem.lower(), stem
        assert existing.read_bytes() == orig_video
        assert (tmp_path / "[ABF-348][maker] title.nfo").read_bytes() == orig_nfo
    else:
        existing = tmp_path / "ABF-348.mp4"
        existing.write_bytes(b"orig")
        (tmp_path / "ABF-348-LTX.mkv").write_bytes(b"other-video")
        before_names = sorted(os.listdir(tmp_path))
        before_bytes = {n: (tmp_path / n).read_bytes() for n in before_names}
        src = tmp_path / "ABF-348-LTX.mp4"
        src.write_bytes(b"src-ltx")
        config = dict(_make_config("off", True))
        config["filename_format"] = "{num}"
        result = organize_file(str(src), _make_metadata(), config)
        assert result.get("duplicate") is True, result
        assert result["success"] is False
        assert src.exists()
        for n in before_names:
            assert (tmp_path / n).read_bytes() == before_bytes[n]
        assert sorted(os.listdir(tmp_path)) == sorted(before_names + ["ABF-348-LTX.mp4"])


def test_i_org_3_marker_name_taken_is_duplicate(tmp_path):
    first = _organize_ltx(tmp_path, b"first-ltx")
    assert first["success"] is True
    first_video = os.path.basename(first["new_filename"])
    first_nfo = os.path.basename(first["nfo_path"])
    first_cover = os.path.basename(first["cover_path"]) if first.get("cover_path") else None
    before_names = sorted(os.listdir(tmp_path))
    before_bytes = {n: (tmp_path / n).read_bytes() for n in before_names if (tmp_path / n).is_file()}
    src2 = tmp_path / "ABF-348-LTX.mp4"
    src2.write_bytes(b"second-ltx")
    after_src_bytes = src2.read_bytes()
    cover_src = tmp_path / "upload2.jpg"
    cover_src.write_bytes(b"new-cover-2")
    result = organize_file(str(src2), _make_metadata(), _make_config("off", True), uploaded_cover=str(cover_src))
    assert result.get("duplicate") is True, result
    assert result["success"] is False
    assert src2.exists()
    assert src2.read_bytes() == after_src_bytes
    assert (tmp_path / first_video).read_bytes() == before_bytes[first_video]
    assert (tmp_path / first_nfo).read_bytes() == before_bytes[first_nfo]
    if first_cover is not None:
        assert (tmp_path / first_cover).read_bytes() == before_bytes[first_cover]
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == sorted(before_names + ["ABF-348-LTX.mp4", "upload2.jpg"])


@pytest.mark.parametrize("src_name,nfo_genres", [
    ("ABF-348-C.mp4", ["中文字幕"]),
    ("ABF-348.mp4", []),
    ("ABF-348.mp4", ["LTX"]),
    ("ABF-348-C.mp4", ["中文字幕", "4K"]),
])
def test_i_org_4_5_same_kind_or_unmarked_is_duplicate(tmp_path, src_name, nfo_genres):
    if nfo_genres:
        existing = tmp_path / "[ABF-348][maker] title.mp4"
        existing.write_bytes(b"orig")
        genre_xml = "".join(f"<genre>{g}</genre>" for g in nfo_genres)
        (tmp_path / "[ABF-348][maker] title.nfo").write_bytes(
            f'<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABF-348</num>{genre_xml}</movie>'.encode("utf-8")
        )
    else:
        existing = tmp_path / "[ABF-348][maker] title.mp4"
        existing.write_bytes(b"orig")
    before_names = sorted(os.listdir(tmp_path))
    before_bytes = {n: (tmp_path / n).read_bytes() for n in before_names}
    src = tmp_path / src_name
    src.write_bytes(b"src-new")
    config = _make_config("off", True)
    result = organize_file(str(src), _make_metadata(), config)
    assert result.get("duplicate") is True, result
    assert result["success"] is False
    assert src.exists()
    for n in before_names:
        assert (tmp_path / n).read_bytes() == before_bytes[n]
    assert sorted(os.listdir(tmp_path)) == sorted(before_names + [src_name])


def test_i_org_6_marker_before_part_token(tmp_path):
    existing = tmp_path / "ABF-348-cd1.mp4"
    existing.write_bytes(b"orig")
    orig_video = existing.read_bytes()
    src = tmp_path / "ABF-348-LTX-cd1.mp4"
    src.write_bytes(b"src-ltx")
    config = dict(_make_config("jellyfin", True))
    config["filename_format"] = "{num}"
    result = organize_file(str(src), _make_metadata(), config)
    assert result["success"] is True, result
    stem = os.path.splitext(os.path.basename(result["new_filename"]))[0]
    assert stem.endswith("-LTX-cd1"), stem
    assert existing.read_bytes() == orig_video
