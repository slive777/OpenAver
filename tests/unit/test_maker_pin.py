"""TASK-200c-T1: NFO 內 `<openaver_manual_maker>` 標記的手動片商讀取端。

四支真檔 oracle：scan_file（四列 parametrize）、補完、重刮、更新。

所有測試都隔離片商對照表（patch 使用端 binding）：
名稱表放一個別名、前綴表放 MIAA→Moodyz／SONE→S1，
不依賴真的 maker_mapping.json（BE-TEST-01／29）。
"""
import hashlib

import pytest

from core.database import Video, VideoRepository
from core.gallery_scanner import VideoScanner
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')

NAME_MAPPING = {
    "エスワン ナンバーワンスタイル": "S1",
    "ムーディーズ": "Moodyz",
}
PREFIX_MAPPING = {
    "MIAA": "Moodyz",
    "SONE": "S1",
}


@pytest.fixture(autouse=True)
def _isolate_maker_mapping(monkeypatch):
    """整個測試期間有效（refresh_one 內的 VideoScanner 是函式內才建立）。"""
    monkeypatch.setattr("core.gallery_scanner.load_name_mapping", lambda: dict(NAME_MAPPING))
    monkeypatch.setattr("core.gallery_scanner.load_prefix_mapping", lambda: dict(PREFIX_MAPPING))


def _write_video(folder, number="MIAA-456"):
    folder.mkdir(parents=True, exist_ok=True)
    mp4 = folder / f"{number}.mp4"
    mp4.write_bytes(b'x')
    return mp4


def _write_nfo(mp4, number, studio, title="我的標題", pinned=False, actors=()):
    marker = '<openaver_manual_maker>1</openaver_manual_maker>' if pinned else ''
    actor_xml = ''.join(f'<actor><name>{a}</name></actor>' for a in actors)
    nfo = mp4.with_suffix('.nfo')
    nfo.write_text(
        f'<movie><title>{title}</title><num>{number}</num>'
        f'<studio>{studio}</studio>{actor_xml}{marker}</movie>',
        encoding='utf-8',
    )
    return nfo


@pytest.mark.parametrize(
    ('studio', 'pinned', 'expected'),
    [
        ("我的片商", True, "我的片商"),
        ("我的片商", False, "Moodyz"),
        ("エスワン ナンバーワンスタイル", True, "エスワン ナンバーワンスタイル"),
        ("", True, "Moodyz"),
    ],
    ids=["pinned", "unpinned", "alias", "pinned_empty"],
)
def test_scan_file_maker_pin(tmp_path, studio, pinned, expected):
    """使用者改過的片商經「更新片庫」後不被名稱表／前綴表蓋掉。

    pinned：手動值原樣；unpinned：今天行為（前綴表）；alias：連別名也不轉標準名；
    pinned_empty：標記在但片商被清空 → 仍由前綴表補回。
    """
    mp4 = _write_video(tmp_path / "lib")
    _write_nfo(mp4, "MIAA-456", studio, pinned=pinned)
    assert VideoScanner().scan_file(str(mp4)).maker == expected


def test_fill_missing_enrich_keeps_pinned_nfo_and_db(tmp_path, isolate_reconcile_db):
    """按 🔍 補完：來源資料被併入（director 被補），但手動片商／女優與 NFO 原樣保留。"""
    from core.enricher import enrich_single

    mp4 = _write_video(tmp_path / "lib")
    nfo = _write_nfo(mp4, "MIAA-456", "我的片商", pinned=True, actors=["A"])
    before = hashlib.sha256(nfo.read_bytes()).hexdigest()

    repo = VideoRepository(isolate_reconcile_db)
    uri = to_file_uri(str(mp4))
    repo.upsert(Video(path=uri, number='MIAA-456', title='我的標題',
                      maker='我的片商', actresses=['A']))

    result = enrich_single(
        str(mp4), 'MIAA-456', mode='fill_missing', overwrite_existing=False,
        write_cover=False,
        scraper_data={'title': '別的標題', 'maker': 'Other', 'actors': ['Z'],
                      'director': 'Dir', 'source': 'test'},
    )

    assert result.success
    assert 'director' in result.fields_filled
    row = repo.get_by_path(uri)
    assert row.director == 'Dir'
    assert row.maker == '我的片商'
    assert row.actresses == ['A']
    assert hashlib.sha256(nfo.read_bytes()).hexdigest() == before


def test_refresh_full_rescrape_returns_source_maker(tmp_path, isolate_reconcile_db):
    """進階重新刮削：NFO 整份重產、標記消失，DB 與其後 scan_file 都回到來源片商。"""
    from core.enricher import enrich_single

    mp4 = _write_video(tmp_path / "lib", number="ZZXX-001")
    nfo = _write_nfo(mp4, "ZZXX-001", "我的片商", title="舊標題", pinned=True)

    repo = VideoRepository(isolate_reconcile_db)
    uri = to_file_uri(str(mp4))
    repo.upsert(Video(path=uri, number='ZZXX-001', title='舊標題', maker='我的片商'))

    result = enrich_single(
        str(mp4), 'ZZXX-001', mode='refresh_full', overwrite_existing=True,
        write_cover=False,
        scraper_data={'title': '來源標題', 'actors': ['B'], 'maker': 'Src',
                      'source': 'test'},
    )

    assert result.success
    text = nfo.read_text(encoding='utf-8')
    assert 'openaver_manual_maker' not in text
    assert repo.get_by_path(uri).maker == 'Src'
    assert VideoScanner().scan_file(str(mp4)).maker == 'Src'


def test_refresh_one_keeps_pinned_maker(tmp_path, isolate_reconcile_db, mocker):
    """彈窗「更新」：refresh_one 重讀真檔後 DB 片商仍是手動值（不是 Moodyz）。"""
    from core.video_refresh import refresh_one

    mocker.patch('core.media_probe.is_available', return_value=False)
    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')

    folder = tmp_path / "library"
    mp4 = _write_video(folder)
    _write_nfo(mp4, "MIAA-456", "我的片商", pinned=True)

    repo = VideoRepository(isolate_reconcile_db)
    uri = to_file_uri(str(mp4))
    repo.upsert(Video(path=uri, number='MIAA-456', maker='我的片商'))

    config = {
        'gallery': {
            'directories': [
                {'path': str(folder), 'readonly': False, 'output_path': ''},
            ],
            'path_mappings': {},
        },
        'scraper': {'nfo_title_format': '[{num}]{title}'},
    }

    result = refresh_one(repo, repo.get_by_path(uri), config, {})

    assert result['success']
    assert repo.get_by_path(uri).maker == '我的片商'
