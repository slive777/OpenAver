from collections import defaultdict

from core.database import Video
from core.similar.canonicalize import canonicalize
from core.similar.idf import build_idf, IDF_HOT_THRESHOLD  # noqa: F401  # 留給 T5/T6 同檔擴充使用


class SimilarRanker:
    def __init__(self, corpus: list[Video]) -> None:
        self._corpus: list[Video] = corpus
        # CD-57a-3：建構期預先 canonicalize，rank() / _retrieve() 不重做
        self._canon_tags: list[list[str]] = [canonicalize(v.tags) for v in corpus]
        # CD-57a-9：IDF 只看 v.tags（_canon_tags），不含 user_tags
        self._idf_table: dict[str, float] = build_idf(self._canon_tags)
        self._inverted_index: dict[str, list[int]] = {}
        for i, tags in enumerate(self._canon_tags):
            # set() 去 per-video 重複；canonicalize 已去重，這裡是 belt-and-suspenders
            for t in set(tags):
                # 嚴格 > 0：hot tag (IDF=0) 與 OOV 都不入索引
                if self._idf_table.get(t, 0.0) > 0:
                    self._inverted_index.setdefault(t, []).append(i)

    def _retrieve(
        self,
        target_tags: list[str],
        exclude: Video | None = None,
        top_n: int = 100,
    ) -> list[Video]:
        useful = [t for t in target_tags if self._idf_table.get(t, 0.0) > 0]
        if not useful:
            return []
        scores: dict[int, float] = defaultdict(float)
        for t in useful:
            idf = self._idf_table[t]
            for i in self._inverted_index.get(t, []):
                scores[i] += idf
        # 用 object identity 排除 target 自身（id=None / number 重複場景皆穩）
        if exclude is not None:
            filtered = [(i, s) for i, s in scores.items() if self._corpus[i] is not exclude]
        else:
            filtered = list(scores.items())
        filtered.sort(key=lambda kv: kv[1], reverse=True)
        return [self._corpus[i] for i, _ in filtered[:top_n]]
