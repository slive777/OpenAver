"""EmbeddingMatrixCache — 圖片相似向量矩陣 singleton（186-T5，CD-186-13）。

形狀照 ``core/similar/ranker_cache.py``：雙重檢查 + RLock + ``invalidate()``。
查詢時不打端點；只載 ``model==index_model ∧ dim==index_dim ∧ dim>0 ∧ cover_path`` 相符的列。

不 import ``similar_state``／``similar_index``（避免循環）。
"""
from __future__ import annotations

import threading
from array import array
from pathlib import Path
from typing import Optional

from core.database import EmbeddingRepository
from core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingMatrixCache:
    _instance: EmbeddingMatrixCache | None = None
    _lock: threading.RLock = threading.RLock()

    def __init__(
        self,
        model: str,
        dim: int,
        vectors: dict[int, array],
        numbers: list[str],
    ) -> None:
        self.model = model
        self.dim = dim
        self.vectors = vectors
        self.numbers = numbers  # 大寫、去重、有有效向量的番號

    @classmethod
    def get(
        cls,
        model: str,
        dim: int,
        db_path: Optional[Path] = None,
    ) -> dict[int, array]:
        """Lazy build + 雙重檢查；期望 (model, dim) 與快取不同就重建。"""
        inst = cls._instance
        if inst is not None and inst.model == model and inst.dim == dim:
            return inst.vectors  # fast path

        with cls._lock:
            inst = cls._instance
            if inst is not None and inst.model == model and inst.dim == dim:
                return inst.vectors

            repo = EmbeddingRepository(db_path)
            rows = repo.load_valid_vectors(model, dim)
            vectors: dict[int, array] = {}
            seen_numbers: set[str] = set()
            numbers: list[str] = []
            for video_id, number, vec in rows:
                vectors[video_id] = vec
                if number:
                    n = number.upper()
                    if n not in seen_numbers:
                        seen_numbers.add(n)
                        numbers.append(n)
            cls._instance = EmbeddingMatrixCache(model, dim, vectors, numbers)
            logger.debug(
                "EmbeddingMatrixCache: built %d vectors for %s dim=%d",
                len(vectors), model, dim,
            )
            return cls._instance.vectors

    @classmethod
    def boosted_numbers(
        cls,
        model: str,
        dim: int,
        db_path: Optional[Path] = None,
    ) -> list[str]:
        """有有效向量的番號（大寫去重）；會確保 cache 已依 (model, dim) 建好。"""
        cls.get(model, dim, db_path)
        inst = cls._instance
        return list(inst.numbers) if inst is not None else []

    @classmethod
    def invalidate(cls) -> None:
        """清空 cache，下次 get() 重建。"""
        with cls._lock:
            cls._instance = None
