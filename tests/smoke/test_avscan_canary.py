"""Live smoke canary — avscan 以圖查番號回應形狀（TASK-193-T4）。

站方改了回應格式或相似度量綱時，owner 跑一次 smoke 就看到「站方改版？」。
單次執行只對站方送 1 張圖。判定：連不上／被限速 → skip（原因以 UNVERIFIED
開頭＝沒驗到，不是通過）；回應形狀不符、空清單 → fail。其他例外不攔。
"""
from pathlib import Path

import pytest

from core.avscan.client import (
    AvscanRateLimited,
    AvscanUnparseable,
    AvscanUnreachable,
    lookup,
)

pytestmark = pytest.mark.smoke

_DEMO_IMAGE = (
    Path(__file__).resolve().parents[2] / "web" / "static" / "img" / "demo" / "ipzz-001.jpg"
)


def test_avscan_live_response_shape():
    image_bytes = _DEMO_IMAGE.read_bytes()
    try:
        results = lookup(image_bytes)
    except AvscanUnparseable:
        pytest.fail("站方改版？avscan 回應形狀與 core/avscan/client.py 的 parse_response 預期不符")
    except (AvscanRateLimited, AvscanUnreachable) as exc:
        retry = getattr(exc, "retry_after", None)
        detail = f" retry_after={retry}" if retry is not None else ""
        pytest.skip(f"UNVERIFIED: {type(exc).__name__}{detail}")
    assert isinstance(results, list) and results, "站方改版？demo 圖查無任何候選"
    assert len(results) <= 5, f"站方改版？回傳 {len(results)} 筆，預期最多 5 筆"
    for item in results:
        assert isinstance(item, dict), "站方改版？候選不是 dict"
        code = item.get("code")
        sim = item.get("similarity")
        match = item.get("match")
        assert isinstance(code, str) and code, "站方改版？code 不是非空 str"
        assert isinstance(sim, (int, float)) and not isinstance(sim, bool), "站方改版？similarity 不是數字"
        assert isinstance(match, dict), "站方改版？match 不是 dict"
        assert match.get("kind") in {"frame", "cover"}, "站方改版？match kind 非預期"
    assert any(
        isinstance(i.get("similarity"), (int, float))
        and not isinstance(i.get("similarity"), bool)
        and i["similarity"] > 1.0
        for i in results
    ), "站方改版？全部 similarity ≤ 1.0，量綱疑似改為 0～1 比率"
