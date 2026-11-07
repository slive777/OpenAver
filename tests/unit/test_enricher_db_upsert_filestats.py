"""TASK-195-T1: _db_upsert 補資料後既有 mtime／size_bytes 不歸零。"""
from core.database import Video, VideoRepository, init_db
from core.enricher import _db_upsert
from core.path_utils import to_file_uri


def test_db_upsert_keeps_existing_mtime_and_size(tmp_path):
    db_path = tmp_path / "test_filestats.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    fs_path = str(tmp_path / "SONE-001.mp4")
    path_uri = to_file_uri(fs_path)
    repo.upsert(Video(path=path_uri, number="SONE-001", title="舊", mtime=1700000000.0, size_bytes=123456789))
    seeded = repo.get_by_path(path_uri)
    assert seeded.mtime == 1700000000.0
    assert seeded.size_bytes == 123456789
    _db_upsert(repo, "SONE-001", fs_path, {"title": "新"})
    updated = repo.get_by_path(path_uri)
    assert updated.mtime == 1700000000.0
    assert updated.size_bytes == 123456789
    assert updated.title == "新"
