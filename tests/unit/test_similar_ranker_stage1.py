from core.database import Video
from core.similar.canonicalize import canonicalize
from core.similar.ranker import SimilarRanker


def _v(tags: list[str], number: str | None = None) -> Video:
    return Video(number=number, tags=tags)


# --- __init__ 邊界 ---

def test_init_empty_corpus():
    r = SimilarRanker([])
    assert r._canon_tags == []
    assert r._idf_table == {}
    assert r._inverted_index == {}
    assert r._retrieve([]) == []
    assert r._retrieve(["any"]) == []


def test_init_corpus_all_empty_tags():
    r = SimilarRanker([_v([]), _v([])])
    assert r._canon_tags == [[], []]
    assert r._idf_table == {}
    assert r._inverted_index == {}
    assert r._retrieve(["x"]) == []


def test_init_corpus_all_hot_tag():
    # 30 部都共有一個 non-stopword tag "common"（df/N = 1.0 > 0.25 → IDF=0），各自再加一個 unique rare tag
    corpus = [_v(["common", f"rare_{i}"]) for i in range(30)]
    r = SimilarRanker(corpus)
    assert r._idf_table["common"] == 0.0
    # hot tag 不入索引
    assert "common" not in r._inverted_index
    # rare 入索引（每個 rare tag 出現一次）
    for i in range(30):
        assert r._inverted_index[f"rare_{i}"] == [i]
    # target 只剩 hot tag → []
    assert r._retrieve(["common"]) == []


# --- _retrieve 邊界 ---

def test_retrieve_empty_target_tags():
    corpus = [_v(["a", "b"]), _v(["c"])]
    r = SimilarRanker(corpus)
    assert r._retrieve([]) == []


def test_retrieve_all_oov():
    corpus = [_v(["a"]), _v(["b"])]
    r = SimilarRanker(corpus)
    target_tags = canonicalize(["x", "y"])
    assert r._retrieve(target_tags) == []


def test_retrieve_corpus_only_target_with_exclude():
    # 加 padding 讓 target 的 tags 在 IDF 中為 rare（df/n <= 0.25），
    # 否則「corpus = [target]」單部影片會讓所有 tag 變 hot，無法驗 exclude 行為
    target = _v(["rare1", "rare2"])
    padding = [_v([f"pad_{i}"]) for i in range(20)]
    r = SimilarRanker(padding + [target])
    target_canon = canonicalize(target.tags)
    # exclude=target → 排除自己 → []（corpus 中只有 target 含 rare1/rare2）
    assert r._retrieve(target_canon, exclude=target) == []
    # exclude=None → 不排除 → 回 target 自己
    assert r._retrieve(target_canon, exclude=None) == [target]


def test_retrieve_target_only_hot_tags():
    # 30 部都有 "common"（hot），各自一個 unique rare
    corpus = [_v(["common", f"r{i}"]) for i in range(30)]
    r = SimilarRanker(corpus)
    target_canon = canonicalize(["common"])
    assert r._retrieve(target_canon) == []


def test_retrieve_happy_path():
    # corpus: 20 部，target 與其中 5 部有 useful tag overlap
    corpus = []
    # 5 部含 "rareA"（命中）
    for i in range(5):
        corpus.append(_v(["rareA", f"unique_a_{i}"], number=f"HIT-{i}"))
    # 15 部含 "rareB" / "rareC"（不重疊 target）
    for i in range(15):
        corpus.append(_v(["rareB", f"unique_b_{i}"], number=f"MISS-{i}"))
    r = SimilarRanker(corpus)
    target_canon = canonicalize(["rareA"])
    result = r._retrieve(target_canon, top_n=100)
    assert len(result) == 5
    assert all(v.number.startswith("HIT-") for v in result)


def test_retrieve_top_n_limits():
    # 100 部 corpus：5 部含命中 tag_x，95 部各自 unique padding
    # 確保 tag_x df/n = 5/100 = 0.05 <= 0.25 → 不是 hot
    corpus = [_v(["tag_x", f"u{i}"]) for i in range(5)]
    corpus += [_v([f"pad_{i}"]) for i in range(95)]
    r = SimilarRanker(corpus)
    target_canon = canonicalize(["tag_x"])
    result = r._retrieve(target_canon, top_n=3)
    assert len(result) == 3


# --- useful_tags 過濾正確性 ---

def test_hot_tag_not_in_inverted_index():
    # 100 部，"freq" 出現 80 次（df/N=0.8 > 0.25 → IDF=0），"rareTag" 出現 5 次
    corpus = []
    for i in range(80):
        corpus.append(_v(["freq", f"u{i}"]))
    for i in range(5):
        corpus.append(_v(["rareTag", f"v{i}"]))
    for i in range(15):
        corpus.append(_v([f"w{i}"]))
    r = SimilarRanker(corpus)
    assert r._idf_table["freq"] == 0.0
    assert "freq" not in r._inverted_index


def test_rare_tag_in_inverted_index_with_correct_indexes():
    corpus = []
    for i in range(80):
        corpus.append(_v(["freq", f"u{i}"]))
    for i in range(5):
        corpus.append(_v(["rareTag", f"v{i}"]))
    for i in range(15):
        corpus.append(_v([f"w{i}"]))
    r = SimilarRanker(corpus)
    assert r._idf_table["rareTag"] > 0
    # rareTag 在 corpus index 80..84
    assert r._inverted_index["rareTag"] == [80, 81, 82, 83, 84]


def test_idf_weighted_score_orders_higher_idf_first():
    # 兩個 candidate：
    #   cand_high：含 target 的兩個 useful tags（IDF sum 較大）
    #   cand_low：只含 target 的一個 useful tag
    # 加 padding 讓 IDF 都 > 0
    corpus = []
    # padding 100 部讓 rare1 / rare2 都很稀有
    for i in range(100):
        corpus.append(_v([f"pad_{i}"]))
    cand_low = _v(["rare1", "noise_low"], number="LOW")
    cand_high = _v(["rare1", "rare2", "noise_high"], number="HIGH")
    corpus.append(cand_low)
    corpus.append(cand_high)
    r = SimilarRanker(corpus)
    target_canon = canonicalize(["rare1", "rare2"])
    result = r._retrieve(target_canon, top_n=10)
    # cand_high 的 IDF sum (rare1+rare2) > cand_low (rare1) → 排在前面
    assert result[0].number == "HIGH"
    assert result[1].number == "LOW"


def test_per_video_duplicate_tag_only_counted_once():
    # 同一 video tags 重複（canonicalize 會去重）+ padding 讓 "rare" 確實 rare
    corpus = [_v(["rare", "rare", "rare"])] + [_v([f"pad_{i}"]) for i in range(20)]
    r = SimilarRanker(corpus)
    # canonicalize 已去重，inverted index 中 rare 只對應 index 0 一次
    assert r._inverted_index["rare"] == [0]
