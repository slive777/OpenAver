#!/usr/bin/env python3
"""DMM 出貨表便宜體檢：回答「這張 dmm_prefix_table.json 過期了沒有？」。

手動執行、非 pytest、非 CI gate。無論命中率高低一律 exit 0。

樣本來源：DMM 自己的最新上架清單
  legacySearchPPV(limit, offset, sort: "RELEASE_DATE")（不帶 queryWord）。
回傳的 contents[].id 就是 cid ground truth。

Usage:
    python scripts/dmm_prefix_table_check.py

Exit codes:
    0 — 永遠（成功印報告，或樣本取不到／分母為 0 印失敗訊息）。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

# ── 常數 ──────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent

API_URL = "https://api.video.dmm.co.jp/graphql"

# 與 core/scrapers/dmm.py::_search_content_id 同一個形狀（D3）
_CID_RE = re.compile(r"^((?:h_\d+)|(?:\d+))?([a-z]+)(\d+)$")

SAMPLE_LIMIT = 60
BUCKET_B_THRESHOLD = 0.95

# 不帶 queryWord；只要 id（+ title 可選）。不要查 makerContentId——該欄位在此 query 型別上不存在。
LATEST_QUERY = """
    query LatestPPV($limit: Int!, $offset: Int!, $sort: ContentSearchPPVSort!) {
        legacySearchPPV(limit: $limit, offset: $offset, sort: $sort) {
            result {
                contents {
                    id
                    title
                }
            }
        }
    }
"""


# ── 純函式：拆 cid／分桶／天數／報告 ───────────────────────────────────────────


def parse_cid(cid: str) -> tuple[str, str, str] | None:
    """拆 cid → (observed_dmm_prefix, prefix, num)；正則不匹配回 None（inconclusive）。"""
    m = _CID_RE.match(cid.lower().strip())
    if not m:
        return None
    return (m.group(1) or "", m.group(2), m.group(3))


@dataclass
class Classification:
    bucket_a_prefixes: list[str] = field(default_factory=list)
    bucket_a_missing: list[tuple[str, str]] = field(default_factory=list)  # (prefix, sample_cid)
    bucket_a_denom: int = 0
    bucket_b_denom: int = 0
    bucket_b_correct: int = 0
    inconclusive_count: int = 0
    default_rule_count: int = 0


def classify_cids(cids: list[str], prefix_map: dict[str, str]) -> Classification:
    """兩桶分類。

    桶 A 分母＝observed_dmm_prefix 非空的 distinct prefix；
    observed 為空者不進任何一桶；正則不匹配落 inconclusive。
    """
    result = Classification()
    # prefix → (observed_dmm_prefix, sample_cid)；只收 need-prefix 的
    need: dict[str, tuple[str, str]] = {}

    for cid in cids:
        parsed = parse_cid(cid)
        if parsed is None:
            result.inconclusive_count += 1
            continue
        observed, prefix, _num = parsed
        if not observed:
            # observed_dmm_prefix 為空 → 預設規則即可，不進任何一桶（D3 / DoD 4）
            result.default_rule_count += 1
            continue
        if prefix not in need:
            need[prefix] = (observed, cid)

    result.bucket_a_prefixes = sorted(need.keys())
    # 桶 A 分母：只數 need-prefix 的 distinct prefix
    result.bucket_a_denom = len(need)

    for prefix, (observed, sample_cid) in sorted(need.items()):
        if prefix not in prefix_map:
            result.bucket_a_missing.append((prefix, sample_cid))
        else:
            result.bucket_b_denom += 1
            if prefix_map[prefix] == observed:
                result.bucket_b_correct += 1

    return result


def days_since_crawl(meta: dict, today: date) -> int:
    """距今天數讀 _meta.crawl_date，不是 _meta.corrected（D6）。"""
    return (today - date.fromisoformat(meta["crawl_date"])).days


def format_report(
    *,
    cids: list[str],
    prefix_map: dict[str, str],
    crawl_date: str,
    today: date,
    fetch_failed: bool = False,
) -> str:
    """組報告文字。樣本空／fetch 失敗／桶 A 分母 0 → 不印任何百分比。"""
    if fetch_failed or not cids:
        return "樣本取得失敗，體檢無法進行"

    result = classify_cids(cids, prefix_map)

    # 桶 A 分母為 0 → 不印百分比（D5 / DoD 3）；不得除以零
    if result.bucket_a_denom == 0:
        return "樣本不可用，體檢無法進行"

    lines: list[str] = []
    lines.append(f"DMM 出貨表體檢（{today.isoformat()}）")
    lines.append("=" * 32)
    lines.append(
        f"樣本來源：DMM 最新上架（legacySearchPPV sort=RELEASE_DATE，"
        f"limit={SAMPLE_LIMIT}），共 {len(cids)} 筆"
    )
    lines.append(
        f"可進桶：{result.bucket_a_denom} 個 distinct 前綴需查表"
        f"（inconclusive {result.inconclusive_count} 筆；"
        f"observed 為空不進桶 {result.default_rule_count} 筆）"
    )
    lines.append("")
    lines.append("【桶 A - 涵蓋率缺口（主要指標）】")
    lines.append(f"需要前綴的 distinct 前綴：{result.bucket_a_denom} 個")
    if result.bucket_a_missing:
        lines.append(f"不在出貨表裡：{len(result.bucket_a_missing)} 個")
        for prefix, sample_cid in result.bucket_a_missing:
            lines.append(f"  {prefix} → {sample_cid}")
    else:
        lines.append("不在出貨表裡：0 個（全部都在表裡）")
    lines.append("")
    lines.append("【桶 B - 正確率（次要指標）】")
    if result.bucket_b_denom == 0:
        lines.append("分母（表內前綴）：0 — 無表內前綴可驗，略過正確率")
    else:
        rate = result.bucket_b_correct / result.bucket_b_denom
        pct = rate * 100.0
        lines.append(
            f"分母（表內前綴）：{result.bucket_b_denom} 個"
        )
        lines.append(
            f"正確（表值 == observed_dmm_prefix）："
            f"{result.bucket_b_correct} 個（{pct:.1f}%）"
        )
        verdict = "達標" if rate >= BUCKET_B_THRESHOLD else "未達標"
        lines.append(f"門檻 {BUCKET_B_THRESHOLD * 100:.0f}%：{verdict}")
    lines.append("")
    days = days_since_crawl({"crawl_date": crawl_date}, today)
    lines.append(f"出貨表距上次更新：{days} 天（crawl_date={crawl_date}）")
    return "\n".join(lines)


# ── I/O：取樣／讀表 ────────────────────────────────────────────────────────────


def _ensure_repo_on_path() -> None:
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def fetch_latest_cids(limit: int = SAMPLE_LIMIT) -> tuple[list[str] | None, bool]:
    """打一次 legacySearchPPV（不帶 queryWord）。

    回 (cids, fetch_failed)。
    非 200／任何 requests 例外／結構壞掉 → (None, True)；成功但空清單 → ([], False)
    （兩者在 format_report 都走「樣本取得失敗」）。
    """
    _ensure_repo_on_path()
    import requests
    from core.scrapers.dmm import DMMScraper

    # 代理由 proxy policy 依設定頁決定（Proxy 欄＋範圍）；沒填就直連／照系統代理。
    scraper = DMMScraper()
    payload = {
        "query": LATEST_QUERY,
        "variables": {
            "limit": limit,
            "offset": 0,
            "sort": "RELEASE_DATE",
        },
    }
    try:
        resp = scraper._session.post(
            API_URL, json=payload, timeout=scraper.config.timeout
        )
    except requests.RequestException:
        # 不只 Timeout/ConnectionError：ChunkedEncodingError、TooManyRedirects
        # （DMM 把沒 VPN 的請求重導到封鎖頁就是這一種）同樣是「這次量不到」，
        # 不是「表過期了」。全部收斂成 (None, True)，否則會 traceback ＋ 非零離開，
        # 破壞 CD-134-8 要求的「腳本自己失敗 vs 表過期」可分辨輸出（Codex P3）。
        return None, True
    if resp.status_code != 200:
        return None, True
    try:
        data = resp.json()
        contents = (
            (data.get("data") or {})
            .get("legacySearchPPV", {})
            .get("result", {})
            .get("contents")
            or []
        )
    except (ValueError, AttributeError, TypeError):
        return None, True
    cids = [c["id"] for c in contents if isinstance(c, dict) and c.get("id")]
    return cids, False


def load_prefix_map() -> dict[str, str]:
    """重用 DMMScraper._prefix_map()（Q2 決議）；不自己展平 JSON。"""
    _ensure_repo_on_path()
    from core.scrapers.dmm import DMMScraper

    return DMMScraper()._prefix_map()


def load_meta() -> dict:
    """讀 dmm_prefix_table.json 的 _meta（只要 crawl_date）。"""
    _ensure_repo_on_path()
    from core.scrapers.dmm import SHIPPED_TABLE_FILE

    raw = json.loads(SHIPPED_TABLE_FILE.read_text(encoding="utf-8"))
    return raw["_meta"]


def run_check(
    *,
    fetch_samples: Callable[[], list[str] | None] | None = None,
    load_prefix_map: Callable[[], dict[str, str]] | None = None,
    load_meta: Callable[[], dict] | None = None,
    today: date | None = None,
) -> None:
    """組報告、print、sys.exit(0)。永遠 exit 0（D1 / DoD 6）。"""
    today = today or date.today()

    prefix_loader = load_prefix_map or globals()["load_prefix_map"]
    meta_loader = load_meta or globals()["load_meta"]

    fetch_failed = False
    if fetch_samples is not None:
        cids_or_none = fetch_samples()
        if cids_or_none is None:
            cids: list[str] = []
            fetch_failed = True
        else:
            cids = cids_or_none
            # 空清單由 format_report 的 `not cids` 守衛處理（D5 硬條件）
    else:
        cids_fetched, fetch_failed = fetch_latest_cids()
        cids = cids_fetched or []

    # 出貨表本身讀不起來時也必須 exit 0（D1 / DoD 6）——這兩個 loader 是真的會拋的：
    #   `_prefix_map()` 對跨片商撞名**刻意**拋 ValueError（不吞，那是設計）；
    #   `_meta` / `crawl_date` 缺欄位是 KeyError。
    # 讓它們冒出去 ⇒ traceback ＋ 非零離開 ⇒ 使用者分不出「腳本壞了」與「表過期」
    # （與 2026-08-29 Codex P3 攔 requests 例外是同一條契約）。
    try:
        prefix_map = prefix_loader()
        meta = meta_loader()
        crawl_date = meta["crawl_date"]
    except Exception as exc:  # noqa: BLE001 — 契約是「無論如何印得出東西」，不挑例外類型
        print(
            "出貨表讀取失敗，體檢無法進行："
            f"{type(exc).__name__}: {exc}\n"
            "（這是腳本／出貨表自己的問題，不代表表過期了。）"
        )
        sys.exit(0)

    report = format_report(
        cids=cids,
        prefix_map=prefix_map,
        crawl_date=crawl_date,
        today=today,
        fetch_failed=fetch_failed,
    )
    print(report)
    sys.exit(0)


def main() -> None:
    run_check()


if __name__ == "__main__":
    main()
