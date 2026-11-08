"""TASK-121a-T6: 四條路徑對同一檔名算出同一組屬性 tag。

比的是屬性 tag 子集合，不是整份 tags（各路徑既有基底不同）。
屬性 tag 清單只從 ATTRIBUTE_TABLE 取 canonical_tag，不在本檔硬編五個字串。
四條路徑必須走真入口：organize_file / scan_file / enrich_single / _write_movie_assets。
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core import readonly_assets, readonly_paths
from core.cover_attributes import ATTRIBUTE_TABLE, effective_tags
from core.database import VideoRepository, init_db
from core.gallery_scanner import VideoScanner
from core.organizer import generate_nfo, organize_file

# 單一來源：未來 ATTRIBUTE_TABLE 加第 6 列，本檔的子集合斷言自動跟上。
_ATTR_TAGS = frozenset(rule.canonical_tag for rule in ATTRIBUTE_TABLE)


def _attr_subset(tags) -> set[str]:
    return set(tags) & _ATTR_TAGS


# ── 整理路徑（照抄 test_organizer_attributes）────────────────────────────────

def _organize_config(**overrides):
    cfg = {
        "create_folder": False,
        "filename_format": "[{num}] {title}{suffix}",
        "download_cover": False,
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
        "external_manager": "off",
    }
    cfg.update(overrides)
    return cfg


def _organize_metadata(**overrides):
    md = {
        "number": "ABC-123",
        "title": "一般標題",
        "actors": [],
        "tags": [],
        "maker": "Studio",
        "date": "2024-01-15",
        "cover": "",
        "url": "",
    }
    md.update(overrides)
    return md


def _run_organize(tmp_path, filename, metadata=None, **config_overrides):
    work = tmp_path / "organize"
    work.mkdir(parents=True, exist_ok=True)
    src = work / filename
    src.write_bytes(b"content")
    md = metadata if metadata is not None else _organize_metadata()
    result = organize_file(str(src), md, _organize_config(**config_overrides))
    assert result["success"] is True, f"organize 失敗: {result.get('error')}"
    return result, md


# ── 掃描路徑（照抄 test_gallery_scanner_attributes）──────────────────────────

def _run_scan(tmp_path, filename, nfo_body=None):
    work = tmp_path / "scan"
    work.mkdir(parents=True, exist_ok=True)
    video = work / filename
    video.write_bytes(b"\x00" * 100)
    if nfo_body is not None:
        video.with_suffix(".nfo").write_text(textwrap.dedent(nfo_body), encoding="utf-8")
    return VideoScanner().scan_file(str(video))


def _genre_parts(info) -> list[str]:
    if not info.genre:
        return []
    return [g.strip() for g in info.genre.split(",") if g.strip()]


# ── 補完路徑（照抄 test_enricher_attributes）─────────────────────────────────

def _scraper_result(number="ABC-123", tags=None, source="javbus", **overrides):
    data = {
        "number": number,
        "title": "タイトル",
        "actors": ["女優A"],
        "cover": "https://example.com/cover.jpg",
        "date": "2024-01-01",
        "maker": "SOD",
        "director": "監督",
        "series": "シリーズ",
        "label": "LABEL",
        "tags": tags if tags is not None else [],
        "sample_images": [],
        "duration": 100,
        "url": "https://example.com/x",
        "source": source,
    }
    data.update(overrides)
    return data


def _enrich_patches(repo_instance):
    return (
        patch("core.enricher.VideoRepository", MagicMock(return_value=repo_instance)),
        patch(
            "core.enricher.download_image",
            side_effect=AssertionError("download_image 不應被呼叫（write_cover=False）"),
        ),
        patch(
            "core.enricher.search_jav",
            side_effect=AssertionError("search_jav 不應被呼叫（已提供 scraper_data）"),
        ),
    )


def _run_enrich(tmp_path, filename, number, tags=None):
    work = tmp_path / "enrich"
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path=db_path)
    video_path = work / filename
    video_path.write_bytes(b"stub")
    nfo_path = video_path.with_suffix(".nfo")
    patches = _enrich_patches(repo)
    with patches[0], patches[1], patches[2]:
        from core.enricher import enrich_single
        result = enrich_single(
            file_path=str(video_path),
            number=number,
            mode="fill_missing",
            write_nfo=True,
            write_cover=False,
            scraper_data=_scraper_result(number=number, tags=list(tags or [])),
        )
    assert result.success is True, f"enrich 失敗: {result.error}"
    nfo_text = nfo_path.read_text(encoding="utf-8")
    nfo_tags = re.findall(r"<tag>(.*?)</tag>", nfo_text)
    return nfo_tags, nfo_text


# ── 唯讀產出路徑（照抄 test_readonly_producer_attributes）────────────────────

def _readonly_config(**overrides):
    cfg = {
        "filename_format": "{num} {title}",
        "max_filename_length": 60,
        "max_title_length": 50,
        "suffix_keywords": [],
        "external_manager": "off",
        "download_sample_images": False,
    }
    cfg.update(overrides)
    return cfg


def _readonly_meta(**overrides):
    md = {
        "number": "ABC-123",
        "title": "一般標題",
        "actors": [],
        "tags": [],
        "maker": "Studio",
        "date": "2024-01-15",
        "cover": "",
        "url": "",
        "sample_images": [],
    }
    md.update(overrides)
    return md


def _run_readonly(tmp_path, filename, meta=None):
    work = tmp_path / "readonly"
    work.mkdir(parents=True, exist_ok=True)
    source_dir = work / "source"
    source_dir.mkdir(exist_ok=True)
    source_path = source_dir / filename
    source_path.write_bytes(b"video")
    movie_dir = work / "output" / "movie"
    md = meta if meta is not None else _readonly_meta()
    cfg = _readonly_config()
    fd = readonly_paths._format_data(md, str(source_path), cfg)
    readonly_assets._write_movie_assets(
        str(movie_dir),
        md,
        fd,
        str(source_path),
        cfg,
        cover_strategy=("none",),
    )
    nfos = list(movie_dir.glob("*.nfo"))
    assert len(nfos) == 1, f"預期恰好一份 NFO，實際 {len(nfos)}: {nfos}"
    nfo_path = nfos[0]
    return md, nfo_path.read_text(encoding="utf-8"), nfo_path


def _four_attr_subsets(tmp_path, filename, *, number, existing_tags=None):
    """跑四條真入口，回傳各路徑的屬性 tag 子集合。"""
    base = list(existing_tags) if existing_tags is not None else []

    _, org_md = _run_organize(
        tmp_path, filename, _organize_metadata(number=number, tags=list(base))
    )
    org = _attr_subset(org_md.get("tags") or [])

    scan_nfo = None
    if base:
        genre_xml = "\n".join(f"          <genre>{t}</genre>" for t in base)
        scan_nfo = f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <movie>
          <title>測試</title>
          <num>{number}</num>
{genre_xml}
        </movie>
        """
    scan_info = _run_scan(tmp_path, filename, scan_nfo)
    scan = _attr_subset(_genre_parts(scan_info))

    enrich_tags, _ = _run_enrich(tmp_path, filename, number, tags=base)
    enrich = _attr_subset(enrich_tags)

    ro_md, _, _ = _run_readonly(
        tmp_path, filename, _readonly_meta(number=number, tags=list(base))
    )
    readonly = _attr_subset(ro_md.get("tags") or [])

    return {
        "organize": org,
        "scan": scan,
        "enrich": enrich,
        "readonly": readonly,
    }


# ── 邊界 1（A1=A2=A3=A9）────────────────────────────────────────────────────

def test_b01_uc_attribute_subset_identical_across_four_paths(tmp_path):
    """ABP-999-UC.mp4 → 四條路徑的屬性 tag 子集合都是 {無碼破解, 中文字幕}。"""
    expected = _attr_subset(["無碼破解", "中文字幕"])
    subsets = _four_attr_subsets(tmp_path, "ABP-999-UC.mp4", number="ABP-999")
    assert subsets["organize"] == expected
    assert subsets["scan"] == expected
    assert subsets["enrich"] == expected
    assert subsets["readonly"] == expected
    assert subsets["organize"] == subsets["scan"] == subsets["enrich"] == subsets["readonly"]


# ── 邊界 2（A4 跨路徑複驗）──────────────────────────────────────────────────

def test_b02_cd1_no_attribute_tags_across_four_paths(tmp_path):
    """ABC-123-cd1.mp4 → 四條路徑都不產生任何屬性 tag。"""
    subsets = _four_attr_subsets(tmp_path, "ABC-123-cd1.mp4", number="ABC-123")
    empty = set()
    assert subsets["organize"] == empty
    assert subsets["scan"] == empty
    assert subsets["enrich"] == empty
    assert subsets["readonly"] == empty


# ── 邊界 3（A8 全面版）──────────────────────────────────────────────────────

def test_b03_no_token_equivalent_to_identity_effective_tags(tmp_path):
    """ABC-123.mp4（無 token、既有 tags 不含中文字幕）→ 四條路徑與未接入等價。

    等價基準是「effective_tags() 對該輸入是 identity」這個事實，
    不是拿改動後四條路徑自己的輸出當 expected。
    """
    filename = "ABC-123.mp4"
    original = ["巨乳", "OL"]
    # 等價基準：identity 事實。若這條先紅，後面的路徑等價沒有推導起點。
    assert effective_tags(filename, original) == original

    result, org_md = _run_organize(
        tmp_path / "org_a8", filename, _organize_metadata(tags=list(original))
    )
    assert org_md["tags"] == original
    actual_org = Path(result["nfo_path"]).read_text(encoding="utf-8")
    expected_dir = tmp_path / "org_a8_expected"
    expected_dir.mkdir()
    expected_path = expected_dir / Path(result["nfo_path"]).name
    assert generate_nfo(
        number="ABC-123",
        title="一般標題",
        original_title="一般標題",
        actors=[],
        tags=list(original),
        date="2024-01-15",
        maker="Studio",
        url="",
        has_subtitle=False,
        has_vr=False,
        output_path=str(expected_path),
        has_poster=False,
        has_fanart=False,
        external_manager="off",
    ) is True
    assert actual_org == expected_path.read_text(encoding="utf-8")

    scan_info = _run_scan(
        tmp_path,
        filename,
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <movie>
          <title>測試</title>
          <num>ABC-123</num>
          <genre>巨乳</genre>
          <genre>OL</genre>
        </movie>
        """,
    )
    assert _genre_parts(scan_info) == original

    enrich_tags, enrich_nfo = _run_enrich(
        tmp_path, filename, "ABC-123", tags=original
    )
    # identity：tags 原樣寫進 NFO，且 has_subtitle 對無 token 檔名為 False，
    # writer 不會再塞屬性 tag。不拿 enrich_single 自己的輸出當 expected。
    assert enrich_tags == original
    assert _attr_subset(enrich_tags) == set()
    for name in _ATTR_TAGS:
        assert f"<tag>{name}</tag>" not in enrich_nfo, name
        assert f"<genre>{name}</genre>" not in enrich_nfo, name

    ro_md, ro_nfo, ro_nfo_path = _run_readonly(
        tmp_path, filename, _readonly_meta(tags=list(original))
    )
    assert ro_md["tags"] == original
    expected_ro_dir = tmp_path / "ro_a8_expected"
    expected_ro_dir.mkdir()
    expected_ro_path = expected_ro_dir / ro_nfo_path.name
    assert generate_nfo(
        number="ABC-123",
        title="一般標題",
        original_title="",
        actors=[],
        tags=list(original),
        date="2024-01-15",
        maker="Studio",
        url="",
        output_path=str(expected_ro_path),
        has_poster=False,
        has_fanart=False,
        director="",
        duration=None,
        series="",
        label="",
        summary="",
        rating=None,
        external_manager="off",
    ) is True
    assert ro_nfo == expected_ro_path.read_text(encoding="utf-8")


# ── 邊界 4（清單來源）───────────────────────────────────────────────────────


# ── 邊界 5（videos.tags 寫入點粗顆粒守衛）────────────────────────────────────


@pytest.mark.parametrize(
    "filename",
    ["SNIS-542-U.ltx.mp4", "SNIS-542_LTX.mp4"],
)
def test_ltx_attribute_subset_identical_across_four_paths(tmp_path, filename):
    expected = {"無碼破解", "LTX"}
    number = "SNIS-542"
    subsets = _four_attr_subsets(tmp_path, filename, number=number)
    assert subsets["organize"] == expected
    assert subsets["scan"] == expected
    assert subsets["enrich"] == expected
    assert subsets["readonly"] == expected
    assert subsets["organize"] == subsets["scan"] == subsets["enrich"] == subsets["readonly"]
