"""TASK-204-T2b：巢狀池子緒繼承取消旗標（真執行緒池，不套 sync_executor）。"""
import threading

import pytest

from core import search_cancel
from core.search_providers.pipeline import run_window
from core.search_providers.types import Enriched, WorkItem


def _make_items():
    return [
        WorkItem(f"T2B-{i:03d}", f"title {i}", f"http://x/{i}.jpg", "2026-01-01", None, "fake")
        for i in range(1, 4)
    ]


class _CancelSeeingProvider:
    def __init__(self, seen, sent):
        self._seen = seen
        self._sent = sent

    def enrich(self, item, ref):
        self._seen.append(search_cancel.current())
        search_cancel.checkpoint()
        self._sent.append(item.number)
        return Enriched(
            card={"number": item.number, "title": item.title, "actors": ["x"]},
            belongs=None,
        )


def test_pipeline_children_inherit_cancel_flag():
    ev = threading.Event()
    ev.set()
    seen, sent = [], []
    with search_cancel.bound(ev):
        with pytest.raises(search_cancel.SearchCancelled) as ei:
            run_window(_CancelSeeingProvider(seen, sent), _make_items(), delay=0)
    assert not isinstance(ei.value, Exception)
    assert sent == []
    assert seen and all(x is ev for x in seen)

    ev2 = threading.Event()
    seen2, sent2 = [], []
    with search_cancel.bound(ev2):
        result = run_window(_CancelSeeingProvider(seen2, sent2), _make_items(), delay=0)
    assert len(result.cards) == 3
    assert sorted(sent2) == ["T2B-001", "T2B-002", "T2B-003"]
    assert seen2 and all(x is ev2 for x in seen2)

    assert search_cancel.current() is None
