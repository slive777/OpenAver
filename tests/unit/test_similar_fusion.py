"""186-T5: 星空融合 RRF／fusion_vectors 閘（CD-186-13／-14／-15）。"""
from __future__ import annotations

import random
from array import array
from contextlib import closing
from unittest.mock import MagicMock, patch

import pytest

from core.database import EmbeddingRepository, Video, VideoRepository, init_db
from core.database import connection as db_connection
from core.database.embeddings import pack_vector
from core.path_utils import to_file_uri
from core.similar.ranker import SimilarRanker


@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    from core.similar.canonicalize import _invalidate_cache
    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    _invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=mock_alias_repo):
        yield
    _invalidate_cache()


@pytest.fixture(autouse=True)
def _reset_fusion_module_state(monkeypatch):
    """BE-TEST-38：EmbeddingMatrixCache／similar_state 觀察值歸零。"""
    from core.ai_services import embedding_cache, similar_state
    monkeypatch.setattr(embedding_cache.EmbeddingMatrixCache, "_instance", None)
    for name, val in (
        ("observed_model", None), ("observed_dim", None), ("unreachable", False),
        ("last_error_kind", None), ("last_error_check", None),
        ("job", {"kind": None, "done": 0, "outcome": None}),
    ):
        monkeypatch.setattr(similar_state, name, val)
    yield
    monkeypatch.setattr(embedding_cache.EmbeddingMatrixCache, "_instance", None)


def _v(*, id=None, tags=None, actresses=None, series=None, maker="", number=None):
    return Video(
        id=id, number=number or (f"N-{id}" if id is not None else None),
        tags=tags or [], actresses=actresses or [], series=series, maker=maker,
    )


def _unit(dim, axis):
    v = [0.0] * dim
    v[axis % dim] = 1.0
    return array("f", v)


def _ids(videos):
    return [v.id for v in videos]


def _build_base_corpus():
    """padding + target + 12 Tier1 + 1-shared（BE-TEST-11 鑑別）。"""
    dim = 16
    padding = [_v(id=5000 + i, tags=[f"pad_{i}", f"padx_{i}"], actresses=[f"P{i}"]) for i in range(40)]
    target = _v(id=1, number="T-001", tags=["rareA", "rareB", "rareC"], actresses=["Alice"], maker="MakerT")
    tier1 = [
        _v(id=100 + i, number=f"T1-{i:03d}", tags=["rareA", "rareB", f"t1u_{i}"], actresses=[f"Act{i}"], maker=f"M{i}")
        for i in range(12)
    ]
    one_shared = _v(id=200, number="ONE-001", tags=["rareA", "only_one_cold"], actresses=["Bob"], maker="MakerT")
    return padding + [target] + tier1 + [one_shared], target, dim


def _fill_vectors(corpus, base, dim, start_axis=2):
    for i, c in enumerate(corpus):
        if c.id is not None and c.id not in base:
            base[c.id] = _unit(dim, (i + start_axis) % dim)
    return base


def test_fusion_off_is_identical():
    """R1：沒開圖片相似或新片沒向量，升級後星空卻變了。"""
    corpus, target, dim = _build_base_corpus()
    ranker = SimilarRanker(corpus)
    vectors_with_t = _fill_vectors(corpus, {1: _unit(dim, 0), 200: _unit(dim, 1)}, dim)
    random.seed(42)
    fused = _ids(ranker.rank(target, vectors=vectors_with_t))
    random.seed(42)
    assert fused != _ids(ranker.rank(target))
    random.seed(7)
    a = _ids(ranker.rank(target))
    random.seed(7)
    b = _ids(ranker.rank(target, vectors=None))
    random.seed(7)
    c = _ids(ranker.rank(target, vectors={200: _unit(dim, 1)}))
    assert a == b == c


def test_fusion_same_actress_not_higher():
    """R1：點魔杖，星空被同一位女優洗版。"""
    corpus, target, dim = _build_base_corpus()
    same_act = [_v(id=400 + i, number=f"SA-{i:03d}", tags=[f"sa_{i}a", f"sa_{i}b"], actresses=["Alice"]) for i in range(5)]
    visual_ok = _v(id=350, number="VIS-OK", tags=["vis_ok_a", "vis_ok_b"], actresses=["Zoe"])
    corpus = corpus + same_act + [visual_ok]
    ranker = SimilarRanker(corpus)
    tvec = _unit(dim, 0)
    vectors = _fill_vectors(corpus, {1: tvec, 350: array("f", tvec), **{400 + i: array("f", tvec) for i in range(5)}}, dim, 3)
    random.seed(11)
    today = ranker.rank(target)
    random.seed(11)
    fused = ranker.rank(target, vectors=vectors)
    assert _ids(fused) != _ids(today)

    def sa(vs):
        return [v for v in vs if (set(target.actresses) & set(v.actresses)) and not (v.series and v.series == target.series)]

    assert len(sa(fused)) <= len(sa(today))
    assert {400, 401, 402, 403, 404}.isdisjoint({v.id for v in fused})


def test_fusion_brings_visual_neighbor():
    """R1：建完索引後星空跟沒建一樣。"""
    corpus, target, dim = _build_base_corpus()
    visual = _v(id=300, number="VIS-001", tags=["vis_only_x", "vis_only_y"], actresses=["Carol"])
    corpus = corpus + [visual]
    ranker = SimilarRanker(corpus)
    tvec = _unit(dim, 0)
    vectors = _fill_vectors(corpus, {1: tvec, 300: array("f", tvec)}, dim, 3)
    rule = ranker._rule_path_for_fusion(target)
    assert 300 not in {c.id for c in rule} and len(rule) >= 12
    random.seed(21)
    today_ids = set(_ids(ranker.rank(target)))
    random.seed(21)
    fused_ids = set(_ids(ranker.rank(target, vectors=vectors)))
    assert 300 not in today_ids and 300 in fused_ids


def test_fusion_gate_requires_all_conditions(tmp_path, monkeypatch):
    """R1：重建到一半星空已用半套向量。"""
    from core.ai_services import similar_state
    from core.ai_services.embedding_cache import EmbeddingMatrixCache

    db = tmp_path / "gate.db"
    init_db(db)
    monkeypatch.setattr(db_connection, "get_db_path", lambda: db)
    cover = to_file_uri(str(tmp_path / "c.jpg"))
    (tmp_path / "c.jpg").write_bytes(b"x")
    vid = VideoRepository(db).upsert(Video(
        path=to_file_uri(str(tmp_path / "v.mp4")), number="GATE-001", cover_path=cover,
    ))
    repo = EmbeddingRepository(db)
    dim = 8
    repo.begin_index("model-X", dim)
    repo.write_vector(vid, "model-X", dim, pack_vector([1.0] + [0.0] * (dim - 1)), cover)
    repo.mark_complete()
    cfg = {"ai_services": {"image_similar": {"enabled": True, "url": "http://x", "api_key": "", "model": "m"}}}
    off = {"ai_services": {"image_similar": {**cfg["ai_services"]["image_similar"], "enabled": False}}}
    assert similar_state.fusion_vectors(off, db) is None

    def set_complete(val):
        with closing(db_connection.get_connection(db)) as conn:
            conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", ("ai.similar.index_complete", val))
            conn.commit()
        EmbeddingMatrixCache.invalidate()

    set_complete("0")
    assert similar_state.fusion_vectors(cfg, db) is None
    set_complete("1")
    similar_state.observe_success("other-model", dim)
    EmbeddingMatrixCache.invalidate()
    assert similar_state.fusion_vectors(cfg, db) is None
    similar_state.observe_success("model-X", dim)
    EmbeddingMatrixCache.invalidate()
    got = similar_state.fusion_vectors(cfg, db)
    assert got is not None and vid in got and len(got[vid]) == dim
    assert similar_state.format_similar_model_id(fused=False) == "rule-based:v1"
    assert similar_state.format_similar_model_id("model-X", fused=True) == "rule-based:v1+rrf:model-X"
    long_name = "m" * 200
    assert similar_state.format_similar_model_id(long_name, fused=True) == "rule-based:v1+rrf:" + long_name[:128]

    # 雙讀競態：若 gate 讀到 complete='1' 後狀態被改成新模型＋'0'，不得改用新模型向量。
    # 單執行緒以 get_index_state 第 2 次回傳新模型模擬；修法後只讀一次 → 仍用 model-X。
    EmbeddingMatrixCache.invalidate()
    calls = {"n": 0}
    good = {"model": "model-X", "dim": dim, "complete": "1", "last_success_at": None}
    rebuilt = {"model": "model-Y", "dim": dim, "complete": "0", "last_success_at": None}

    def flaky_state(self):
        calls["n"] += 1
        return good if calls["n"] == 1 else rebuilt

    monkeypatch.setattr(EmbeddingRepository, "get_index_state", flaky_state)
    got2 = similar_state.fusion_vectors(cfg, db)
    assert calls["n"] == 1
    assert got2 is not None and vid in got2 and abs(got2[vid][0] - 1.0) < 1e-5
