"""B2：SimilarRanker 內部狀態與排序不受 user_tags 影響。

被鎖行為現已正確；本檔以行為測試鎖住，不以原始碼字面守衛。
fixture 刻意讓 df 比例落在 hot 門檻之下，rank(top_k=12) 在 Tier 1 填滿——
不得用 random.seed() 掩蓋 fallback 非決定性。
"""

import pytest
from unittest.mock import MagicMock, patch
from core.database import Video
from core.similar.ranker import SimilarRanker
from tests.unit.test_similar_fusion import _build_base_corpus, _fill_vectors, _unit

@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    """`SimilarRanker` 走 `canonicalize()` → `_load_merged_map()`，module-level
    單例未命中時會連真實 DB 讀 `TagAliasRepository`。

    本檔在 127b-T4 之前看起來乾淨，是因為別的檔先把 `_merged_alias_map` 暖好了。
    T4 逐一隔離之後才露出來——**「report 模式沒報你」不等於「你有隔離」**。
    sonnet review 的 Finding 1 已逐字點名本族還有哪些檔沒隔離，這裡一次補齊。

    形狀比照 `test_ranker_cache.py` / `test_similar_api.py` / `test_similar_perf.py`。
    """
    from core.similar.canonicalize import _invalidate_cache

    _mock_alias_repo = MagicMock()
    _mock_alias_repo.get_all.return_value = []
    _invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=_mock_alias_repo):
        yield
    _invalidate_cache()

_TIER1_CANARY_MSG = (
    "Tier 1 已不再填滿 → 排序斷言不再具決定性 → "
    "請重新設計 fixture 的 df 比例，不要用 random seed 掩蓋"
)

_SHARED_TAGS = ["痴女", "中出"]
_N_CORE = 13  # target + 12 候選
_N_PAD = 47
_TOP_K = 12


def _build_corpus(with_user_tags: bool) -> list[Video]:
    """N=60：前 13 部共享兩個 tag（13/60=21.7% ≤ 0.25），後 47 部壓 df。"""
    videos: list[Video] = []
    for i in range(_N_CORE):
        user_tags = ["中字", f"手動{i}"] if with_user_tags else []
        videos.append(
            Video(
                number=f"CORE-{i:03d}",
                tags=_SHARED_TAGS + [f"獨有{i}"],
                user_tags=user_tags,
            )
        )
    for i in range(_N_PAD):
        user_tags = ["中字", f"手動P{i}"] if with_user_tags else []
        videos.append(
            Video(
                number=f"PAD-{i:03d}",
                tags=[f"雜訊{i}"],
                user_tags=user_tags,
            )
        )
    return videos


def test_rank_order_and_scores_equal_with_and_without_user_tags():
    """rank() 的 number 序列相等，且逐項 _score() 相等。"""
    clean_corpus = _build_corpus(False)
    dirty_corpus = _build_corpus(True)
    clean = SimilarRanker(clean_corpus)
    dirty = SimilarRanker(dirty_corpus)
    clean_target = clean_corpus[0]
    dirty_target = dirty_corpus[0]

    clean_out = clean.rank(clean_target, top_k=_TOP_K)
    dirty_out = dirty.rank(dirty_target, top_k=_TOP_K)

    assert [v.number for v in clean_out] == [v.number for v in dirty_out]
    for c_cand, d_cand in zip(clean_out, dirty_out):
        assert clean._score(clean_target, c_cand) == dirty._score(dirty_target, d_cand)


def test_golden_rule_path_matches_pre_188a():
    """規則路排序與分數基線。

    使用者流程：沒有任何 user tag 時，升級後星空前 12 名換了。
    字面值取自 05866a69（188a 之前）；若日後刻意改排序，改這裡必須同時改 CHANGELOG。
    """
    corpus = _build_corpus(False)
    ranker = SimilarRanker(corpus)
    target = corpus[0]
    out = ranker.rank(target, top_k=12)

    assert [v.number for v in out] == [
        "CORE-001",
        "CORE-002",
        "CORE-003",
        "CORE-004",
        "CORE-005",
        "CORE-006",
        "CORE-007",
        "CORE-008",
        "CORE-009",
        "CORE-010",
        "CORE-011",
        "CORE-012",
    ]
    assert [repr(ranker._score(target, v)) for v in out] == ["0.3587779996848771"] * 12


def test_golden_fusion_path_matches_pre_188a():
    """融合路排序基線。

    使用者流程：沒有任何 user tag 時，升級後星空前 12 名換了。
    字面值取自 05866a69（188a 之前）；若日後刻意改排序，改這裡必須同時改 CHANGELOG。
    """
    corpus, target, dim = _build_base_corpus()
    ranker = SimilarRanker(corpus)
    vectors = _fill_vectors(corpus, {1: _unit(dim, 0), 200: _unit(dim, 1)}, dim)
    out = ranker.rank(target, vectors=vectors)

    assert [v.id for v in out] == [105, 100, 5014, 101, 5030, 102, 103, 5000, 104, 5001, 5002, 106]

