"""188c-T1：AI 標籤計數／待處理清單／全清旗標（資料層）。"""
import sqlite3

from core.database import Video, VideoRepository
from core.path_utils import to_file_uri

COVER = to_file_uri("/c.jpg")


def _seed(repo):
    """五列：有封面未跑×2（插入順序與字母序相反）／有封面已跑0標籤／無封面未跑／無封面已跑。"""
    p = {k: to_file_uri(f"/{k}.mp4") for k in ("b_pending", "a_pending", "done", "nocover", "nocover_done")}
    repo.upsert(Video(path=p["b_pending"], title="b", cover_path=COVER))
    repo.upsert(Video(path=p["a_pending"], title="a", cover_path=COVER))
    repo.upsert(Video(path=p["done"], title="d", cover_path=COVER))
    repo.upsert(Video(path=p["nocover"], title="n", cover_path=""))
    repo.upsert(Video(path=p["nocover_done"], title="nd", cover_path=""))
    repo.update_user_tags(p["done"], [], ai_tagged=True)
    repo.update_user_tags(p["nocover_done"], ["X"], ai_tagged=True)
    return p


def test_progress_counts_and_pending_list_follow_cover_and_flag(temp_db):
    repo = VideoRepository(temp_db)
    assert repo.count_ai_tag_progress() == (0, 0)
    p = _seed(repo)
    assert repo.count_ai_tag_progress() == (3, 2)
    assert repo.list_ai_pending_paths() == [p["b_pending"], p["a_pending"]]


def test_reset_all_ai_tagged_clears_flag_only_keeps_user_tags(temp_db):
    repo = VideoRepository(temp_db)
    p = _seed(repo)
    repo.update_user_tags(p["done"], ["待看", "A"], ai_tagged=True)
    repo.update_user_tags(p["a_pending"], ["自己打的"])

    def snapshot():
        conn = sqlite3.connect(str(temp_db))
        try:
            return conn.execute("SELECT path, user_tags FROM videos ORDER BY id").fetchall()
        finally:
            conn.close()

    before = snapshot()
    repo.reset_all_ai_tagged()
    assert snapshot() == before
    total, pending = repo.count_ai_tag_progress()
    assert pending == total
    assert len(repo.list_ai_pending_paths()) == total
