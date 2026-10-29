"""「常收女優」可用性與保留鍵分流（TASK-184-T3b）；輸入皆為我方結構，不連外網。"""
import pytest

from core.database import init_db
from core.recent_rules import RECENT_ACTRESSES_KEY, FavStat
from core.search_providers.types import MakerSearchResult

API, REST = "/api/search/recent-actresses", "/api/search"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    init_db(db)
    monkeypatch.setattr("web.routers.search.get_db_path", lambda: db)
    monkeypatch.setattr("core.database.get_db_path", lambda: db)
    state = {"dmm": True, "stats": {}}
    monkeypatch.setattr("core.scraper.is_source_enabled", lambda sid: sid == "dmm" and state["dmm"])
    monkeypatch.setattr("core.database.actress_library.get_favorite_actress_stats", lambda *a, **k: state["stats"])
    return state


def test_recent_available_inputs(client, env):
    def avail(dmm, stats):
        env.update(dmm=dmm, stats={s.name: s for s in stats})
        return client.get(API).json()
    ok, zero = FavStat("A", 3, 2.0), FavStat("B", 99, 0.0)
    assert avail(True, [ok, zero]) == {"success": True, "available": True, "key": RECENT_ACTRESSES_KEY}
    assert avail(False, [ok])["available"] is False
    assert avail(True, [])["available"] is False
    assert avail(True, [zero])["available"] is False


def test_recent_search_branch(client, env, monkeypatch):
    calls = []
    out = {"r": MakerSearchResult([{"number": "AAA-001", "title": "t"}], False, None)}
    monkeypatch.setattr("web.routers.search.search_recent_actresses", lambda **kw: calls.append(kw) or out["r"])
    maker = []
    monkeypatch.setattr("web.routers.search.search_maker_latest",
                        lambda *a, **kw: maker.append(a) or MakerSearchResult([], False, "maker_not_found"))
    body = client.get(REST, params={"maker_key": RECENT_ACTRESSES_KEY, "maker": "常收女優"}).json()
    assert (body["success"], body["mode"], body["has_more"], body["maker_key"]) == (True, "maker", False, RECENT_ACTRESSES_KEY)
    assert len(calls) == 1 and not maker
    out["r"] = MakerSearchResult([], False, "recent_region_empty")
    body = client.get(REST, params={"maker_key": RECENT_ACTRESSES_KEY, "maker": "常收女優"}).json()
    assert (body["success"], body["error_code"]) == (False, "recent_region_empty")
    client.get(REST, params={"maker_key": "s1", "maker": "S1"})
    assert len(calls) == 2 and len(maker) == 1
