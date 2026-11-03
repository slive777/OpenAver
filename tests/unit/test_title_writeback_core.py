"""core 入口冒煙：T4b 要用的鎖入口與寫回本體可直接呼叫（189a-T2）。"""
from core import user_tags_write
from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from core.title_writeback import apply_title_writeback
from core.user_tags_write import hold_nfo_write


def test_core_entrypoints_callable(tmp_path):
    db = tmp_path / "t.db"; init_db(db)
    mp4 = tmp_path / "AI-001.mp4"; mp4.write_bytes(b"x")
    mp4.with_suffix(".nfo").write_text("<movie><title>t</title></movie>", encoding="utf-8")
    uri = to_file_uri(str(mp4)); repo = VideoRepository(db)
    repo.upsert(Video(path=uri, number="AI-001", title="あいう", nfo_mtime=1.0))
    with hold_nfo_write():
        assert user_tags_write._LOCK.locked()
    assert not user_tags_write._LOCK.locked()
    r = apply_title_writeback(repo, repo.get_by_path(uri), "翻譯", None, {"gallery": {}}, {})
    assert r["success"] is True and repo.get_by_path(uri).title == "翻譯"
