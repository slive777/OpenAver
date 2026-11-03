"""TASK-188b-T4: seed_builtin_aliases — empty / user-conflict / once+bump."""

from __future__ import annotations

import pytest

from core.database import init_db, TagAliasRepository
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


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    db = _make_db(tmp_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db)
    canonicalize._invalidate_cache()
    SimilarRankerCache._instance = None
    yield db
    canonicalize._invalidate_cache()
    SimilarRankerCache._instance = None


def test_seed_on_empty_db_builds_25_groups_and_old_spellings_resolve(_isolate):
    from core.ai_services.tagging_aliases import seed_builtin_aliases

    db = _isolate
    repo = TagAliasRepository(db)
    warm = canonicalize.canonicalize(["护士"])
    assert warm == ["护士"]

    result = seed_builtin_aliases(repo)
    assert result["skipped"] is False
    assert result["created"] == 25

    groups = repo.get_all()
    assert len(groups) == 25
    assert all(g.source == "builtin-188" for g in groups)
    assert sum(len(g.aliases) for g in groups) == 35

    for name in ("運動服", "婚紗", "全裸", "野外・露出"):
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

    assert len(repo.get_all()) == 26


def test_seed_runs_once_never_resurrects_and_version_bump_only_tops_up(_isolate, monkeypatch):
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

    monkeypatch.setattr("core.ai_services.tagging_aliases.SEED_VERSION", 2)
    bumped = seed_builtin_aliases(repo)
    assert bumped["skipped"] is False
    assert bumped["topped_up"] >= 1
    assert bumped["created"] == 0

    school_after = repo.get_by_primary("校服")
    assert "学生服" in school_after.aliases
    assert repo.get_by_primary("泳裝") is None
    assert _snapshot(repo, "护士") == g1_before
    assert _snapshot(repo, "女傭") == g2_before
    assert _snapshot(repo, "酷") == g3_before
