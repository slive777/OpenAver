"""
test_user_tags.py - Phase 41b-T1: DB user_tags 欄位 + NFO 讀寫 TDD-lite 測試

涵蓋 TASK-41b-T1.md 的 14 個測試案例
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import patch, MagicMock

import pytest

from core.path_utils import to_file_uri


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db() -> Path:
    """建立 in-memory-style 暫存資料庫，回傳 Path"""
    tmp = tempfile.mktemp(suffix=".db")
    return Path(tmp)


def _make_video(path=None, number="ABC-001", user_tags=None, **kwargs):
    if path is None:
        path = to_file_uri("/test/abc.mp4")
    from core.database import Video
    return Video(
        path=path,
        number=number,
        title="テストタイトル",
        user_tags=user_tags if user_tags is not None else [],
        **kwargs,
    )


# ── 1. DB migration 加 user_tags 欄位 ────────────────────────────────────────

def test_db_migration_adds_user_tags_column():
    """對已有 DB 呼叫 init_db()，PRAGMA table_info(videos) 包含 user_tags"""
    from core.database import init_db
    db_path = _make_db()
    try:
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
        conn.close()
        assert "user_tags" in cols
    finally:
        if db_path.exists():
            db_path.unlink()


def test_db_migration_idempotent():
    """呼叫 init_db() 兩次不拋例外"""
    from core.database import init_db
    db_path = _make_db()
    try:
        init_db(db_path)
        init_db(db_path)  # 第二次不應報錯
    finally:
        if db_path.exists():
            db_path.unlink()


# ── 2. Video model user_tags ──────────────────────────────────────────────────

def test_video_model_user_tags_default_empty_list():
    """Video() 的 user_tags 預設 []"""
    from core.database import Video
    v = Video()
    assert v.user_tags == []


def test_video_to_dict_serializes_user_tags():
    """to_dict() 的 user_tags 是 JSON 字串"""
    from core.database import Video
    v = Video(path=to_file_uri("/test.mp4"), user_tags=["★5", "足"])
    d = v.to_dict()
    assert isinstance(d["user_tags"], str)
    assert json.loads(d["user_tags"]) == ["★5", "足"]


def test_video_from_row_deserializes_user_tags():
    """from_row() 反序列化 user_tags 正確"""
    from core.database import Video, init_db, VideoRepository
    db_path = _make_db()
    try:
        init_db(db_path)
        repo = VideoRepository(db_path)
        v = _make_video(user_tags=["★5", "足"])
        repo.upsert(v)
        fetched = repo.get_by_path(v.path)
        assert fetched is not None
        assert fetched.user_tags == ["★5", "足"]
    finally:
        if db_path.exists():
            db_path.unlink()


def test_video_from_row_user_tags_json_error_fallback():
    """from_row() 遇到非法 JSON user_tags → fallback []"""
    from core.database import Video, init_db
    db_path = _make_db()
    try:
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO videos (path, user_tags) VALUES (?, ?)",
            (to_file_uri("/bad.mp4"), "NOT_JSON")
        )
        conn.commit()
        conn.close()

        from core.database import VideoRepository
        repo = VideoRepository(db_path)
        v = repo.get_by_path(to_file_uri("/bad.mp4"))
        assert v is not None
        assert v.user_tags == []
    finally:
        if db_path.exists():
            db_path.unlink()


def test_video_from_row_user_tags_null_fallback():
    """from_row() 遇到 NULL user_tags → fallback []"""
    from core.database import init_db, VideoRepository
    db_path = _make_db()
    try:
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO videos (path, user_tags) VALUES (?, NULL)",
            (to_file_uri("/null.mp4"),)
        )
        conn.commit()
        conn.close()

        repo = VideoRepository(db_path)
        v = repo.get_by_path(to_file_uri("/null.mp4"))
        assert v is not None
        assert v.user_tags == []
    finally:
        if db_path.exists():
            db_path.unlink()


# ── 3. upsert 保護 ────────────────────────────────────────────────────────────

def test_upsert_preserves_user_tags_on_rescan():
    """upsert 帶空 user_tags 不覆蓋 DB 中已有值"""
    from core.database import init_db, VideoRepository, Video
    db_path = _make_db()
    try:
        init_db(db_path)
        repo = VideoRepository(db_path)

        # 第一次 upsert：設定 user_tags
        v1 = _make_video(user_tags=["★5", "足"])
        repo.upsert(v1)

        # 第二次 upsert：模擬 rescan，user_tags = []
        v2 = _make_video(user_tags=[])
        repo.upsert(v2)

        fetched = repo.get_by_path(v1.path)
        assert fetched is not None
        # user_tags 應保留 ["★5", "足"]，不被空 list 覆蓋
        assert fetched.user_tags == ["★5", "足"]
    finally:
        if db_path.exists():
            db_path.unlink()


# ── 4. update_user_tags() ──────────────────────────────────────────────────────

def test_update_user_tags_updates_only_user_tags():
    """update_user_tags() 只更新 user_tags，不碰其他欄位"""
    from core.database import init_db, VideoRepository
    db_path = _make_db()
    try:
        init_db(db_path)
        repo = VideoRepository(db_path)
        v = _make_video(user_tags=[])
        repo.upsert(v)

        # 更新 user_tags
        success = repo.update_user_tags(v.path, ["new_tag"])
        assert success is True

        fetched = repo.get_by_path(v.path)
        assert fetched.user_tags == ["new_tag"]
        # title 不應改變
        assert fetched.title == "テストタイトル"
    finally:
        if db_path.exists():
            db_path.unlink()


# ── 5. NFO 寫出：generate_nfo() ───────────────────────────────────────────────

def test_generate_nfo_writes_user_tag_elements():
    """傳 user_tags=["★5","足"] 時 NFO 含 <user_tag>★5</user_tag>"""
    from core.organizer import generate_nfo
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False, mode="w") as f:
        nfo_path = f.name
    try:
        generate_nfo(
            number="ABC-001",
            title="テスト",
            output_path=nfo_path,
            user_tags=["★5", "足"],
        )
        content = Path(nfo_path).read_text(encoding="utf-8")
        assert "<user_tag>★5</user_tag>" in content
        assert "<user_tag>足</user_tag>" in content
    finally:
        os.unlink(nfo_path)


def test_generate_nfo_no_user_tags_no_user_tag_elements():
    """不傳 / 傳空 list 時 NFO 不含 <user_tag>"""
    from core.organizer import generate_nfo
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False, mode="w") as f:
        nfo_path = f.name
    try:
        generate_nfo(
            number="ABC-001",
            title="テスト",
            output_path=nfo_path,
        )
        content = Path(nfo_path).read_text(encoding="utf-8")
        assert "<user_tag>" not in content
    finally:
        os.unlink(nfo_path)


# ── 6. NFO 讀入：parse_nfo() ──────────────────────────────────────────────────

def test_parse_nfo_reads_user_tag_elements():
    """NFO 含 <user_tag> 時 VideoInfo.user_tags 正確"""
    from core.gallery_scanner import VideoScanner
    nfo_content = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>テスト</title>
  <num>ABC-001</num>
  <tag>HD</tag>
  <user_tag>★5</user_tag>
  <user_tag>足</user_tag>
</movie>"""
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False, mode="w", encoding="utf-8") as f:
        f.write(nfo_content)
        nfo_path = f.name
    try:
        scanner = VideoScanner()
        info = scanner.parse_nfo(nfo_path)
        assert info is not None
        assert info.user_tags == ["★5", "足"]
    finally:
        os.unlink(nfo_path)


def test_parse_nfo_no_user_tag_returns_empty_list():
    """NFO 無 <user_tag> 時 user_tags = []"""
    from core.gallery_scanner import VideoScanner
    nfo_content = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>テスト</title>
  <num>ABC-001</num>
  <tag>HD</tag>
</movie>"""
    with tempfile.NamedTemporaryFile(suffix=".nfo", delete=False, mode="w", encoding="utf-8") as f:
        f.write(nfo_content)
        nfo_path = f.name
    try:
        scanner = VideoScanner()
        info = scanner.parse_nfo(nfo_path)
        assert info is not None
        assert info.user_tags == []
    finally:
        os.unlink(nfo_path)


# ── 7. refresh_full 不覆蓋 user_tags ─────────────────────────────────────────

def test_refresh_full_does_not_overwrite_user_tags():
    """mock scraper，呼叫 enrich_single(mode='refresh_full') 後 DB user_tags 不變"""
    from core.database import init_db, VideoRepository
    from core.enricher import enrich_single

    db_path = _make_db()
    try:
        init_db(db_path)
        repo = VideoRepository(db_path)

        # 建立測試影片（暫存檔案）
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        # 預先設定 user_tags
        from core.path_utils import to_file_uri
        path_uri = to_file_uri(video_path)
        v = _make_video(path=path_uri, user_tags=["★5", "足"])
        repo.upsert(v)

        scraper_data = {
            "number": "ABC-001",
            "title": "新タイトル",
            "original_title": "New Title",
            "actors": ["女優A"],
            "cover": "https://example.com/cover.jpg",
            "date": "2024-01-01",
            "maker": "SOD",
            "director": "",
            "series": "",
            "label": "",
            "tags": ["tag1"],
            "sample_images": [],
            "duration": 90,
            "url": "https://example.com/ABC-001",
            "source": "javbus",
        }

        with patch("core.database.connection.get_db_path", return_value=db_path), \
             patch("core.enricher.VideoRepository", return_value=repo):
            enrich_single(
                file_path=path_uri,
                number="ABC-001",
                mode="refresh_full",
                write_nfo=False,
                write_cover=False,
                scraper_data=scraper_data,
            )

        fetched = repo.get_by_path(path_uri)
        assert fetched is not None
        # user_tags 應保留，不被 refresh_full 覆蓋
        assert fetched.user_tags == ["★5", "足"]
    finally:
        if db_path.exists():
            db_path.unlink()
        if os.path.exists(video_path):
            os.unlink(video_path)


# ── 8. _write_nfo() 傳 user_tags ─────────────────────────────────────────────

def test_write_nfo_passes_user_tags_to_generate_nfo():
    """_write_nfo() 傳入 user_tags 後 NFO 含對應元素"""
    from core.enricher import _write_nfo
    from core.database import init_db, VideoRepository

    db_path = _make_db()
    try:
        init_db(db_path)
        repo = VideoRepository(db_path)

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        from core.path_utils import to_file_uri
        path_uri = to_file_uri(video_path)
        v = _make_video(path=path_uri, user_tags=["評5", "時間印"])
        repo.upsert(v)

        meta = {
            "title": "テスト",
            "original_title": "",
            "actresses": [],
            "tags": [],
            "release_date": "2024-01-01",
            "maker": "SOD",
            "url": "",
            "director": "",
            "duration": None,
            "series": "",
            "label": "",
        }

        with patch("core.database.connection.get_db_path", return_value=db_path), \
             patch("core.enricher.VideoRepository", return_value=repo):
            _write_nfo(
                fs_path=video_path,
                number="ABC-001",
                meta=meta,
                write_nfo=True,
                overwrite_existing=True,
                has_subtitle=False,
            )

        nfo_path = str(Path(video_path).with_suffix(".nfo"))
        try:
            content = Path(nfo_path).read_text(encoding="utf-8")
            assert "<user_tag>評5</user_tag>" in content
            assert "<user_tag>時間印</user_tag>" in content
        finally:
            if os.path.exists(nfo_path):
                os.unlink(nfo_path)
    finally:
        if db_path.exists():
            db_path.unlink()
        if os.path.exists(video_path):
            os.unlink(video_path)


# ── T5: organize_file 分離 + scrape_single DB upsert ─────────────────────────

def test_organize_file_separates_user_tags_in_nfo():
    """T5-RED1: organize_file 呼叫 generate_nfo 時 user_tags 分開寫 <user_tag>，不混入 <tag>"""
    import tempfile, os
    from pathlib import Path
    from unittest.mock import patch, MagicMock

    # 建立假影片檔案
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    from core.organizer import generate_nfo as real_generate_nfo
    captured_nfo_path = []

    def fake_generate_nfo(**kwargs):
        path = kwargs.get('output_path', '')
        captured_nfo_path.append(path)
        return real_generate_nfo(**kwargs)

    try:
        metadata = {
            'number': 'ABC-001',
            'title': 'テスト',
            'original_title': '',
            'actors': [],
            'tags': ['HD', '單體作品'],
            'user_tags': ['★5', '足'],
            'date': '2024-01-01',
            'maker': 'SOD',
            'url': '',
            'director': '',
            'duration': None,
            'series': '',
            'label': '',
            'cover': '',
            'sample_images': [],
        }

        scraper_config = {
            'output_dir': tempfile.gettempdir(),
            'folder_name_template': '{number}',
        }

        with patch('core.organizer.shutil.move') as mock_move, \
             patch('core.organizer.download_image') as mock_dl, \
             patch('core.organizer.generate_nfo', side_effect=fake_generate_nfo):
            mock_move.return_value = None

            from core.organizer import organize_file
            result = organize_file(video_path, metadata, scraper_config)

        assert len(captured_nfo_path) > 0, "generate_nfo 沒被呼叫"
        nfo_path = captured_nfo_path[0]
        assert os.path.exists(nfo_path), f"NFO 不存在: {nfo_path}"

        content = Path(nfo_path).read_text(encoding='utf-8')

        assert '<user_tag>★5</user_tag>' in content, "★5 應在 <user_tag>"
        assert '<user_tag>足</user_tag>' in content, "足 應在 <user_tag>"
        assert '<tag>★5</tag>' not in content, "★5 不應在 <tag>"
        assert '<tag>足</tag>' not in content, "足 不應在 <tag>"

        if os.path.exists(nfo_path):
            os.unlink(nfo_path)
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)


def test_organize_file_no_user_tags_no_regression():
    """T5-RED2: metadata 無 user_tags 時，NFO 不含 <user_tag>（不回歸）"""
    import tempfile, os
    from pathlib import Path
    from unittest.mock import patch

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    from core.organizer import generate_nfo as real_generate_nfo
    captured_nfo_path = []

    def fake_generate_nfo(**kwargs):
        path = kwargs.get('output_path', '')
        captured_nfo_path.append(path)
        return real_generate_nfo(**kwargs)

    try:
        metadata = {
            'number': 'ABC-001',
            'title': 'テスト',
            'original_title': '',
            'actors': [],
            'tags': ['HD'],
            # 無 user_tags key
            'date': '2024-01-01',
            'maker': 'SOD',
            'url': '',
            'director': '',
            'duration': None,
            'series': '',
            'label': '',
            'cover': '',
            'sample_images': [],
        }

        scraper_config = {
            'output_dir': tempfile.gettempdir(),
            'folder_name_template': '{number}',
        }

        with patch('core.organizer.shutil.move'), \
             patch('core.organizer.download_image'), \
             patch('core.organizer.generate_nfo', side_effect=fake_generate_nfo):

            from core.organizer import organize_file
            organize_file(video_path, metadata, scraper_config)

        assert len(captured_nfo_path) > 0, "generate_nfo 沒被呼叫"
        nfo_path = captured_nfo_path[0]
        assert os.path.exists(nfo_path), f"NFO 不存在: {nfo_path}"

        content = Path(nfo_path).read_text(encoding='utf-8')
        assert '<user_tag>' not in content, "無 user_tags 時不應有 <user_tag>"

        if os.path.exists(nfo_path):
            os.unlink(nfo_path)
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)


def test_scrape_single_upserts_user_tags_to_db():
    """T5-RED3: scrape_single 成功後，VideoRepository.update_user_tags 被呼叫"""
    import tempfile, os
    from unittest.mock import patch, MagicMock
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        fake_result = {
            'success': True,
            'duplicate': False,
            'new_filename': video_path,
            'new_folder': tempfile.gettempdir(),
            'original_path': video_path,
            'cover_path': '',
            'nfo_path': '',
        }

        mock_repo = MagicMock()
        mock_repo.get_by_path.return_value = None  # DB 中無現有記錄

        with patch('web.routers.scraper.organize_file', return_value=fake_result), \
             patch('web.routers.scraper.VideoRepository', return_value=mock_repo), \
             patch('web.routers.scraper.load_config', return_value={'scraper': {}}):
            from web.app import app
            client = TestClient(app)
            resp = client.post('/api/scrape-single', json={
                'file_path': video_path,
                'number': 'ABC-001',
                'metadata': {
                    'number': 'ABC-001',
                    'title': 'テスト',
                    'tags': ['HD'],
                    'user_tags': ['★5'],
                    'cover': '',
                },
            })

        assert resp.status_code == 200
        mock_repo.update_user_tags.assert_called_once()
        call_args = mock_repo.update_user_tags.call_args
        assert '★5' in call_args[0][1], f"update_user_tags 的 user_tags 應含 '★5'，實際: {call_args}"
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)


def test_scrape_single_wsl_mapped_dir_user_tags_uses_mapped_namespace(monkeypatch):
    """TASK-91b-T1（axis-B 子形狀 ii，scraper.py:180 live bug 回歸）。

    WSL + gallery.path_mappings 下，organize_file 產出的 new_filename 是裸本機路徑
    （非 DB URI）。scrape_single 必須用 to_file_uri(new_filename, path_mappings) 建
    DB key（forward-map），才能命中既有 mapped 命名空間 DB row；否則
    repo.get_by_path 落非 mapped key → miss → 既有 user_tags 被靜默遺失（不會產生
    幽靈 row，update_user_tags 是純 UPDATE，0 行生效）。

    修前 RED：get_by_path/update_user_tags 收到 unmapped file:///mnt/nas/share/...
    key，existing_user_tags 恆 []，merged 只有新值、遺失既有 '★5'。
    修後 GREEN：兩者收到 mapped file:///...NAS/share/... key，merged 為既有 ∪ 新值。
    """
    import core.path_utils as path_utils_module
    from fastapi.testclient import TestClient
    # gotcha: CURRENT_ENV 是 core.path_utils 的 module-global，to_file_uri/
    # uri_to_local_fs_path 皆在同模組內查找，patch 該模組單一 binding 即可
    # （scraper.py 只 import 函式、未 import CURRENT_ENV 本身，無需雙重 patch）。
    monkeypatch.setattr(path_utils_module, 'CURRENT_ENV', 'wsl')

    # 注意：local prefix 不可用 /mnt/X（to_file_uri 會先吃 WSL-mount 規則、
    # 不會進 path_mappings fallback 分支），故用 /home/user/nas/share（比照
    # test_readonly_producer.py 既有 WSL+mapping 測試慣例）。
    path_mappings = {"/home/user/nas/share": "//NAS/share"}
    new_filename = "/home/user/nas/share/ABC-002/ABC-002.mp4"
    mapped_uri = to_file_uri(new_filename, path_mappings)
    # sanity: 映射確實改變命名空間（否則本測試無意義，測不出 bug）
    unmapped_uri = to_file_uri(new_filename)
    assert mapped_uri != unmapped_uri

    existing_video = MagicMock()
    existing_video.user_tags = ["★5"]

    def _get_by_path(path_uri):
        if path_uri == mapped_uri:
            return existing_video
        return None

    mock_repo = MagicMock()
    mock_repo.get_by_path.side_effect = _get_by_path

    fake_result = {
        'success': True,
        'duplicate': False,
        'new_filename': new_filename,
        'new_folder': '/home/user/nas/share/ABC-002',
        'original_path': new_filename,
        'cover_path': '',
        'nfo_path': '',
    }
    fake_config = {'scraper': {}, 'gallery': {'path_mappings': path_mappings}}

    with patch('web.routers.scraper.organize_file', return_value=fake_result), \
         patch('web.routers.scraper.VideoRepository', return_value=mock_repo), \
         patch('web.routers.scraper.load_config', return_value=fake_config):
        from web.app import app
        client = TestClient(app)
        resp = client.post('/api/scrape-single', json={
            'file_path': new_filename,
            'number': 'ABC-002',
            'metadata': {
                'number': 'ABC-002',
                'title': 'テスト',
                'tags': ['HD'],
                'user_tags': ['時間印'],
                'cover': '',
            },
        })

    assert resp.status_code == 200
    mock_repo.get_by_path.assert_called_once_with(mapped_uri)
    mock_repo.update_user_tags.assert_called_once()
    call_args = mock_repo.update_user_tags.call_args
    assert call_args[0][0] == mapped_uri, (
        f"update_user_tags 的 path 應落 mapped 命名空間 {mapped_uri!r}，"
        f"實際: {call_args[0][0]!r}"
    )
    merged = call_args[0][1]
    assert set(merged) == {"★5", "時間印"}, f"既有 tags 應與新值聯集，實際: {merged}"


# ── NFO updater ───────────────────────────────────────────────────────────────

class TestUserTagsNfoUpdater:
    """update_nfo_user_tags 邊界條件測試"""

    def test_nfo_update_user_tags_returns_false_when_no_nfo(self, tmp_path):
        """update_nfo_user_tags：NFO 不存在 → 回傳 False，不建立空殼 NFO"""
        from core.nfo_updater import update_nfo_user_tags
        nonexistent_nfo = str(tmp_path / "NONEXISTENT.nfo")
        result = update_nfo_user_tags(nonexistent_nfo, ["★5"])
        assert result is False
