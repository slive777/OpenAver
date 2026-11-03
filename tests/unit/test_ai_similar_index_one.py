"""189a-T3: 相似索引單片入口 ``index_one``（覆寫／讀不到／索引未建）。helper 沿用 186-T4a 的 Env。"""
from __future__ import annotations

from core.ai_services import similar_index, similar_state
from core.database.embeddings import pack_vector
from tests.unit.test_ai_similar_index import Env, _build_and_join, _fresh_state, _vec_bytes  # noqa: F401, PLC2701


def _uri(env: Env, vid: int) -> str:
    return env.vrepo.get_by_id(vid).path


def test_index_one_overwrites_vector_and_cache(tmp_path, monkeypatch):
    """重刮換封面後：目標片向量被覆寫、星空快取讀到新向量，另一部片不動。"""
    env = Env(tmp_path, monkeypatch, "one_over")
    a, b = env.add_video(), env.add_video()
    _build_and_join()
    old = _vec_bytes(env)
    similar_state.fusion_vectors(env.cfg, env.db)  # 暖 cache：載入舊向量
    env.fake.salt = "-new"
    assert similar_index.index_one(_uri(env, a)) == "indexed"
    new = _vec_bytes(env)
    assert new[a] != old[a] and new[b] == old[b]
    vectors = similar_state.fusion_vectors(env.cfg, env.db)
    assert vectors is not None and pack_vector(list(vectors[a])) == new[a]


def test_index_one_unreadable_counts_as_tried(tmp_path, monkeypatch):
    """入庫的新片封面檔不在 → 記成試過了：設定頁「還有 N 部」少 1、不打端點。"""
    env = Env(tmp_path, monkeypatch, "one_unread")
    env.add_video()
    _build_and_join()
    vid = env.add_video()
    (env.tmp / f"c{env.n}.jpg").unlink()
    state = env.repo.get_index_state()
    assert env.repo.counts(state["model"], state["dim"])["pending"] == 1
    covers = env.fake.covers
    assert similar_index.index_one(_uri(env, vid)) == "unreadable"
    counts = env.repo.counts(state["model"], state["dim"])
    assert (env.fake.covers, counts["pending"], counts["unreadable"]) == (covers, 0, 1)


def test_index_one_requires_built_index(tmp_path, monkeypatch):
    """索引還沒建就入庫：不寫單片向量，之後「建立索引」的一致性測試不被繞過。"""
    env = Env(tmp_path, monkeypatch, "one_notready")
    vid = env.add_video()
    assert similar_index.index_one(_uri(env, vid)) == "index_not_ready"
    assert (env.rows(), env.fake.covers) == (0, 0)
