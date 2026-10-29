"""tests/unit/test_recent_score.py — TASK-184-T1

get_favorite_actress_stats()：半衰／門檻／現算、別名合併＋parity、異常 mtime。
"""
import pytest

from core.database import Actress, ActressRepository, AliasRepository, Video, VideoRepository
from core.database.actress_library import get_favorite_actress_stats
from core.path_utils import to_file_uri

NOW = 1_800_000_000.0
DAY = 86400.0


@pytest.fixture
def library_db(temp_db, monkeypatch):
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: temp_db)
    return temp_db


def _add(db, tag, actresses, age_days=None, mtime=None):
    m = NOW - age_days * DAY if mtime is None else mtime
    VideoRepository(db).upsert(Video(
        path=to_file_uri(f"/t/{tag}.mp4"), number=tag.upper(), title=tag,
        actresses=actresses, mtime=m))


def _fav(db, *names):
    for n in names:
        ActressRepository(db).save(Actress(name=n))


def test_recent_score_half_life_and_floor(library_db):
    _fav(library_db, "A", "B", "C", "D", "E", "F", "G", "H")
    for i, age in enumerate((15, 45, 75, 105, 135, 165)):
        _add(library_db, f"a{i}", ["A"], age)
    for i in range(150):  # 365～2190 天平均分布
        _add(library_db, f"b{i}", ["B"], 365 + i * (1825 / 149))
    _add(library_db, "c", ["C"], 0)
    _add(library_db, "d", ["D"], 120)
    _add(library_db, "e0", ["E"], 365)  # 0.121 < 門檻
    for i in range(3):
        _add(library_db, f"e{i+1}", ["E"], 1800)
    for n, age in (("F", 10), ("G", 50), ("H", 90)):  # created_at 同日、mtime 分散
        _add(library_db, f"x{n}", [n], age)

    s = get_favorite_actress_stats(now=NOW)
    assert s["A"].score > s["B"].score > 0  # ① 持續追 > 一次性大庫
    assert s["C"].score == pytest.approx(1.0)  # ②
    assert s["D"].score == pytest.approx(0.5)
    assert s["E"].score == 0.0 and s["E"].video_count == 4  # ③
    later = get_favorite_actress_stats(now=NOW + 120 * DAY)  # ④ 現算、非快取
    assert later["D"].score == pytest.approx(0.25)
    assert len({s["F"].score, s["G"].score, s["H"].score}) == 3  # ⑤
    assert s["F"].score > s["G"].score > s["H"].score


def test_recent_stats_alias_merge_and_parity(library_db):
    _fav(library_db, "P", "Q")
    AliasRepository(library_db).add(primary_name="P", aliases=["P2"])
    _add(library_db, "p1", ["P2"], 30)
    _add(library_db, "p2", ["P2"], 60)
    _add(library_db, "p3", ["P", "P2", "Q"], 0)  # 同片掛本名與別名
    _add(library_db, "q1", ["Q"], 90)

    stats = get_favorite_actress_stats(now=NOW)
    assert stats["P"].video_count == 3  # 本名 0 片自己 + 別名合併，同片只算一次
    assert stats["P"].score == pytest.approx(1.0 + 0.5 ** (30 / 120) + 0.5 ** (60 / 120))
    arepo, vrepo = AliasRepository(library_db), ActressRepository(library_db)
    for name, st in stats.items():
        assert st.video_count == vrepo.count_videos_for_actress_names(arepo.resolve(name))


def test_recent_score_abnormal_mtime(library_db):
    _fav(library_db, "R", "S")
    _add(library_db, "r0", ["R"], mtime=0)
    _add(library_db, "r1", ["R"], mtime=1.0)
    _add(library_db, "r2", ["R"], mtime=NOW + 365 * DAY)
    _add(library_db, "s1", ["S"], mtime=NOW + 3600)
    conn = ActressRepository(library_db)._get_connection()
    try:
        conn.execute("UPDATE videos SET mtime=NULL WHERE number='R1'")
        conn.commit()
    finally:
        conn.close()

    s = get_favorite_actress_stats(now=NOW)
    assert s["R"].video_count == 3
    assert s["R"].score == 0.0
    assert s["S"].video_count == 1
    assert s["S"].score == pytest.approx(1.0)
