"""TASK-188b-T4 / TASK-196-T2: seed_builtin_aliases — empty / user-conflict / v1→v2."""

from __future__ import annotations

import pytest

from core.database import init_db, TagAliasRepository
from core.database.connection import get_connection
from core.similar import canonicalize
from core.similar.ranker_cache import SimilarRankerCache


def _make_db(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    return db


def _add_user_groups(repo: TagAliasRepository) -> None:
    repo.add("护士", ["看護婦・ナース"])
    repo.add("女傭", ["メイド"])
    repo.add("酷", ["制服"])


def _snapshot(repo: TagAliasRepository, primary: str):
    rec = repo.get_by_primary(primary)
    assert rec is not None
    return (list(rec.aliases), rec.source, rec.updated_at)


def _read_marker(db) -> int:
    from core.ai_services import tagging_aliases as ta

    conn = get_connection(db)
    try:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = ?", (ta._META_KEY,)
        ).fetchone()
        return int(row[0]) if row is not None else 0
    finally:
        conn.close()


def _write_marker(db, value: int) -> None:
    from core.ai_services import tagging_aliases as ta

    conn = get_connection(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            (ta._META_KEY, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


def _build_v1_db(repo: TagAliasRepository, db) -> None:
    """Hand-build a v1-shaped library: 25 groups, marker=1, no v2 words."""
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    seed_builtin_aliases(repo)
    for name in ("女醫", "過膝襪", "靴子", "雙馬尾", "潤滑油"):
        assert repo.delete(name) is True
    repo.add("迷你裙", ["ミニスカ"], source="builtin-188")
    repo.add("戀腿癖", ["脚フェチ"], source="builtin-188")
    repo.add("走光", ["パンチラ"], source="builtin-188")
    _write_marker(db, 1)
    assert len(repo.get_all()) == 25
    assert _read_marker(db) == 1
    canonicalize._invalidate_cache()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db)
    canonicalize._invalidate_cache()
    SimilarRankerCache._instance = None
    yield db
    canonicalize._invalidate_cache()
    SimilarRankerCache._instance = None


def test_seed_on_empty_db_builds_27_groups_and_old_spellings_resolve(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    warm = canonicalize.canonicalize(["护士"])
    assert warm == ["护士"]

    result = seed_builtin_aliases(repo)
    assert result["skipped"] is False
    assert result["created"] == 27

    groups = repo.get_all()
    assert len(groups) == 27
    assert all(g.source == "builtin-188" for g in groups)
    assert sum(len(g.aliases) for g in groups) == 41

    for name in ("運動服", "婚紗", "全裸"):
        assert repo.get_by_primary(name) is None

    assert canonicalize.canonicalize(["护士"]) == ["看護婦・ナース"]


def test_seed_never_touches_user_groups_and_skips_only_the_conflicting_alias(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    _add_user_groups(repo)
    g1_before = _snapshot(repo, "护士")
    g2_before = _snapshot(repo, "女傭")
    g3_before = _snapshot(repo, "酷")

    seed_builtin_aliases(repo)

    assert _snapshot(repo, "护士") == g1_before
    assert repo.get_by_primary("看護婦・ナース") is None
    assert _snapshot(repo, "女傭") == g2_before
    assert repo.get_by_primary("女僕") is None
    assert _snapshot(repo, "酷") == g3_before

    school = repo.get_by_primary("校服")
    assert school is not None
    assert school.aliases == ["学生服", "水手服", "セーラー服"]
    assert school.source == "builtin-188"

    assert len(repo.get_all()) == 28


def test_seed_runs_once_never_resurrects_and_version_bump_never_tops_up(
    _isolate, monkeypatch
):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    _add_user_groups(repo)
    g1_before = _snapshot(repo, "护士")
    g2_before = _snapshot(repo, "女傭")
    g3_before = _snapshot(repo, "酷")

    first = seed_builtin_aliases(repo)
    assert first["skipped"] is False
    count_after = len(repo.get_all())

    second = seed_builtin_aliases(repo)
    assert second == {"skipped": True, "created": 0, "topped_up": 0}
    assert len(repo.get_all()) == count_after

    repo.delete("泳裝")
    third = seed_builtin_aliases(repo)
    assert third["skipped"] is True
    assert repo.get_by_primary("泳裝") is None

    assert _snapshot(repo, "护士") == g1_before
    assert _snapshot(repo, "女傭") == g2_before
    assert _snapshot(repo, "酷") == g3_before

    assert repo.remove_alias("校服", "学生服") is True
    school_after_rm = repo.get_by_primary("校服")
    assert "学生服" not in school_after_rm.aliases

    monkeypatch.setattr("core.ai_services.tagging_aliases.SEED_VERSION", 3)
    bumped = seed_builtin_aliases(repo)
    assert bumped["skipped"] is False
    assert bumped["created"] == 0
    assert bumped["topped_up"] == 0

    school_after = repo.get_by_primary("校服")
    assert "学生服" not in school_after.aliases
    assert repo.get_by_primary("泳裝") is None
    assert _snapshot(repo, "护士") == g1_before
    assert _snapshot(repo, "女傭") == g2_before
    assert _snapshot(repo, "酷") == g3_before


def test_v1_upgrade_creates_only_new_word_groups(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    _build_v1_db(repo, db)

    warm = canonicalize.canonicalize(["乳液"])
    assert warm == ["乳液"]

    result = seed_builtin_aliases(repo)
    assert result["skipped"] is False
    assert result["created"] == 5
    assert result["topped_up"] == 0

    expected = {
        "女醫": ["女医", "女醫生"],
        "過膝襪": ["ニーソックス", "長襪"],
        "靴子": ["ブーツ", "高筒靴"],
        "雙馬尾": ["ツインテール"],
        "潤滑油": ["ローション・オイル", "乳液"],
    }
    for name, aliases in expected.items():
        rec = repo.get_by_primary(name)
        assert rec is not None
        assert list(rec.aliases) == aliases
        assert rec.source == "builtin-188"

    assert canonicalize.canonicalize(["乳液"]) == ["潤滑油"]
    assert canonicalize.canonicalize(["女醫生"]) == ["女醫"]
    assert canonicalize.canonicalize(["高筒靴"]) == ["靴子"]

    second = seed_builtin_aliases(repo)
    assert second == {"skipped": True, "created": 0, "topped_up": 0}


def test_v1_upgrade_never_touches_user_edits(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    _build_v1_db(repo, db)

    # Decoys BEFORE upgrade (BE-TEST-11)
    assert repo.delete("泳裝") is True
    assert repo.remove_alias("校服", "学生服") is True
    assert repo.add_alias("OL", "自訂OL別名")[0] is True
    repo.add("學妹", ["JK"])

    before = {
        g.primary_name: (list(g.aliases), g.source, g.updated_at)
        for g in repo.get_all()
    }

    result = seed_builtin_aliases(repo)
    assert result["skipped"] is False
    assert result["created"] == 5
    assert result["topped_up"] == 0

    assert repo.get_by_primary("泳裝") is None
    school = repo.get_by_primary("校服")
    assert school is not None
    assert "学生服" not in school.aliases
    assert repo.get_by_primary("迷你裙") is not None

    after_existing = {
        g.primary_name: (list(g.aliases), g.source, g.updated_at)
        for g in repo.get_all()
        if g.primary_name in before
    }
    assert after_existing == before

    # Phase 2: M3 — owner already exists, must not top-up removed alias
    assert repo.remove_alias("潤滑油", "乳液") is True
    _write_marker(db, 1)
    rerun = seed_builtin_aliases(repo)
    assert rerun["created"] == 0
    assert rerun["topped_up"] == 0
    lube = repo.get_by_primary("潤滑油")
    assert lube is not None
    assert "乳液" not in lube.aliases


def test_v1_upgrade_skips_only_the_occupied_alias(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    _build_v1_db(repo, db)

    # Occupy after v1 helper; user is not 潤滑油's owner
    repo.add("乳液", ["ローション"])
    user_before = _snapshot(repo, "乳液")

    result = seed_builtin_aliases(repo)
    assert result["skipped"] is False
    assert result["created"] == 5
    assert result["topped_up"] == 0

    lube = repo.get_by_primary("潤滑油")
    assert lube is not None
    assert list(lube.aliases) == ["ローション・オイル"]
    assert "乳液" not in lube.aliases
    assert _snapshot(repo, "乳液") == user_before
