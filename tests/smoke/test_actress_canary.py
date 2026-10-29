"""Live smoke canary — actress source health check (TASK-118a-T12).

Five independent sources: xcity / wiki_ja / graphis / gfriends / avbase. Each
has its own `test_{source}_canary` function; a dead source never drags down
the other four (owner hard constraint — see TASK-118a-T12 §技術要點).

This file deliberately does NOT import `tests/smoke/_canary_core.py` — owner
decision: the actress line writes its own simple per-source verdict logic
instead of generalizing the video-line quorum core for one more consumer
(TASK-118a-T12 §Test Strategy).

verdict semantics (self-contained here, mirrors `_canary_core.quorum_verdict`
in spirit but is its own independent implementation):
    >=1 pass              -> green (function returns normally, test passes)
    0 pass, >=1 fail       -> pytest.fail
    0 pass, all skip       -> pytest.skip

`usable()` is bound per-source to the exact field the orchestrator cascade
consumes (Opus 修正 ②, TASK-118a-T12) — NOT merely "is the result non-None".
For graphis specifically, `scrape_graphis_photo()` fail-opens its `model.php`
sub-parse (graphis.py:162-165), so a non-None return can still carry an empty
`prof_url`; `orchestrator.py:190` only ever consumes `prof_url`, so that is
what this canary checks too.

avbase (TASK-174-T7) checks birthday + the alias path (`other_names`) on two
evergreen names and probes lazily (only when a name is unusable) via
`curl_cffi` impersonate — bare `requests` is always 403'd by that site.

ZERO production scraper changes — this file only reads the public
scrape/lookup entry points. Must NOT be collected by the standard PR command
(`--ignore=tests/smoke --ignore=tests/e2e -m "not smoke and not e2e"`).
"""
import pytest
import requests

from core.scrapers.actress.xcity import scrape_xcity
from core.scrapers.actress.wiki_ja import scrape_wiki_ja
from core.scrapers.actress.graphis import scrape_graphis_photo
from core.scrapers.actress.gfriends import lookup_gfriends
from core.scrapers.actress.avbase import scrape_avbase
from core.scrapers.actress.orchestrator import _has_meaningful_text
from core.actress_photo import validate_photo_url

pytestmark = pytest.mark.smoke

# Existing evergreen names stay shared by wiki, graphis, and gfriends canaries.
# Xcity checks these names against birthdays recorded on 2026-09-28.
EVERGREEN_NAMES = ["三上悠亜", "波多野結衣", "明日花キララ"]
XCITY_EVERGREEN = [
    ("三上悠亜", "1993-08-16"),
    ("波多野結衣", "1988-05-24"),
    ("明日花キララ", "1988-10-02"),
]
# avbase evergreen (TASK-174-T7): only two names -> a green run is exactly two
# live requests. Birthdays verified against the live site on 2026-10-21.
AVBASE_EVERGREEN = [
    ("三上悠亜", "1993-08-16"),
    ("二階堂麗", "1999-11-30"),
]
# Alias-path oracle: this name's `other_names` must carry the query name itself
# plus this alias, otherwise the avbase alias route is broken.
AVBASE_ALIAS_EXPECTED = ("二階堂麗", "あかね麗")

# Bare `requests` UA gets 403'd by ja.wikipedia.org (research
# finding, TASK-118a-T12 §探測設計) — probes must look like a real browser.
_BROWSER_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

_PROBE_TIMEOUT = 10  # seconds, matches tests/smoke/_probe.py convention

# gfriends probe target MUST be a repo file, not the Content/ directory root —
# jsDelivr 403s directory listings unconditionally (site-liveness-independent),
# so probing the dir root would misreport a healthy CDN as dead (research
# finding, TASK-118a-T12 §探測設計).
_GFRIENDS_PROBE_URL = "https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/README.md"


# ========== Reachability probes (source-level, not per-name) ==========
# Each of the four sources is probed ONCE per test run (not once per
# EVERGREEN_NAMES entry) — reachability doesn't depend on which name is being
# queried, a site isn't down "for one specific name" (TASK-118a-T12 §探測設計,
# deliberately different from the per-number probes on the video canary line).
#
# CONTRACT: every probe below MUST NEVER raise. Any exception (DNS failure,
# connection refused, timeout, TLS error, ...) -> return False (=
# "unreachable" -> skip), never propagate.

def _probe_xcity() -> bool:
    try:
        resp = requests.get(
            "https://xcity.jp/idol/", headers=_BROWSER_UA, timeout=_PROBE_TIMEOUT
        )
        return resp.status_code == 200
    except Exception:
        return False


def _probe_wiki_ja() -> bool:
    try:
        resp = requests.get(
            "https://ja.wikipedia.org/", headers=_BROWSER_UA, timeout=_PROBE_TIMEOUT
        )
        return resp.status_code == 200
    except Exception:
        return False


def _probe_graphis() -> bool:
    try:
        resp = requests.get(
            "https://graphis.ne.jp/", headers=_BROWSER_UA, timeout=_PROBE_TIMEOUT
        )
        return resp.status_code == 200
    except Exception:
        return False


def _probe_gfriends() -> bool:
    try:
        resp = requests.get(_GFRIENDS_PROBE_URL, timeout=_PROBE_TIMEOUT)
        return resp.status_code == 200
    except Exception:
        return False


def _probe_avbase() -> bool:
    """HTTP status only — never touches scrape_avbase / any parser.

    Must use curl_cffi impersonate: bare `requests` is always 403 on avbase,
    which would read as "site dead" and turn a real red into a skip.
    """
    try:
        from curl_cffi import requests as cffi_requests

        resp = cffi_requests.get(
            "https://www.avbase.net/", impersonate="chrome", timeout=_PROBE_TIMEOUT
        )
        return resp.status_code == 200
    except Exception:
        return False


# ========== Self-contained verdict (NOT imported from _canary_core) ==========

def _classify(result, usable_fn, probe_reachable: bool) -> str:
    """One EVERGREEN_NAMES entry -> "pass" / "fail" / "skip"."""
    if usable_fn(result):
        return "pass"
    return "fail" if probe_reachable else "skip"


def _verdict(results, source_label: str, probe_desc: str) -> None:
    """Turn a list of "pass"/"fail"/"skip" into a pytest outcome.

    >=1 pass            -> green, just return (test passes)
    0 pass, >=1 fail     -> pytest.fail
    0 pass, all skip     -> pytest.skip

    The skip reason MUST carry `probe_desc` (the probe URL) — Opus 修正 ③:
    this canary's only real failure mode is the probe target itself rotting
    (e.g. the gfriends README.md getting renamed), which would silently and
    permanently skip that source forever while looking "fine". `pytest -rs`
    must be able to surface the URL so a human can tell "probe is broken"
    from "site is broken".
    """
    if "pass" in results:
        return
    if "fail" in results:
        pytest.fail(
            f"{source_label}: 0/{len(results)} pass, probe reachable "
            f"({probe_desc}) — 常青名字全部解析為空，可能站方改版或名字被下架"
        )
    pytest.skip(
        f"{source_label}: probe unreachable — 探測目標 {probe_desc} 連不上，"
        f"可能是站真的掛了，也可能探測目標本身壞了（需人工確認）"
    )


def _run_actress_canary(source_label, probe_fn, probe_desc, fetch_fn, usable_fn) -> None:
    """Shared per-source shape: probe once -> loop names -> classify -> verdict."""
    probe_reachable = probe_fn()
    results = [
        _classify(fetch_fn(name), usable_fn, probe_reachable)
        for name in EVERGREEN_NAMES
    ]
    _verdict(results, source_label, probe_desc)


# ========== Per-source canaries (four independent functions, no parametrize —
# a dead source must not drag down the other three) ==========

def _xcity_usable(result, expected_birth) -> bool:
    return bool(result and result.get("birth") == expected_birth)


def test_xcity_canary():
    probe_reachable = _probe_xcity()
    results = [
        _classify(
            scrape_xcity(name),
            lambda r, eb=expected_birth: _xcity_usable(r, eb),
            probe_reachable,
        )
        for name, expected_birth in XCITY_EVERGREEN
    ]
    _verdict(results, "xcity", "https://xcity.jp/idol/")


def _wiki_ja_usable(result) -> bool:
    """可用 = 文字欄位有東西 且 photo_url 過得了我們自己的白名單（CD-145b-14）。

    對齊 BE-GUARD-01：canary 的判準要跟 sink（core/actress_photo.py 的
    validate_photo_url，換圖端點下載前的真正閘門）逐字相同，不是自己在這裡
    寫一份近似判斷（例如斷言 host 字串），那樣站方換一次 CDN 又要跟著改。
    """
    return bool(
        _has_meaningful_text(result)
        and validate_photo_url((result or {}).get("photo_url", ""), "wiki")
    )


def test_wiki_ja_canary():
    _run_actress_canary(
        "wiki_ja",
        probe_fn=_probe_wiki_ja,
        probe_desc="https://ja.wikipedia.org/",
        fetch_fn=scrape_wiki_ja,
        usable_fn=_wiki_ja_usable,
    )


def test_graphis_canary():
    _run_actress_canary(
        "graphis",
        probe_fn=_probe_graphis,
        probe_desc="https://graphis.ne.jp/",
        # graphis fail-opens its model.php sub-parse — the photo cascade
        # (orchestrator.py:190) only ever consumes `prof_url`, so that is the
        # only field this canary treats as "usable" (Opus 修正 ②).
        fetch_fn=scrape_graphis_photo,
        usable_fn=lambda result: bool(result and result.get("prof_url")),
    )


def test_graphis_pool_canary(monkeypatch):
    """185: Graphis 條目搜尋／條目頁解析／名字比對（只打活站，無捏造輸入）。"""
    import random
    import re
    import time

    from core.scrapers.actress import graphis_pool as gp

    if not _probe_graphis():
        pytest.skip("Graphis 無法連線 (https://graphis.ne.jp/)")
    monkeypatch.setattr(gp, "proxy_kwargs", lambda *a, **k: {})  # BE-TEST-55 恆直連

    def _eid(url):
        return re.search(r"/model/([^/]+)/", url).group(1)

    gp._SEARCH_CACHE.clear()
    gp._ENTRY_CACHE.clear()
    try:
        names = {"miru", "坂道みる"}
        pool = gp._assemble_pool("miru", names, time.time() + 12, random.Random(0))
        assert pool is not None, "miru 條目搜尋失敗（站方改版或被擋）"
        ids = {_eid(u) for u in pool}
        assert {"260904_miru3", "200403_miru-sakamichi2"} <= ids, f"缺 miru 條目: {ids}"
        assert "080801_emiru-momose_daily" not in ids, f"混入他人條目: {ids}"
        assert len(pool) >= 10, f"池過小: {len(pool)}"
        bad = [u for u in pool if not gp.is_collectible_url(u, _eid(u))]
        assert not bad, f"不合白名單: {bad}"
        assert any(re.search(r"/photo/\d{3}/pic\.jpg$", u) for u in pool), \
            "池內無任何 photo/NNN/pic.jpg（條目頁解析失效，只剩底圖）"

        empty = gp._assemble_pool("河北彩伽", {"河北彩伽"}, time.time() + 12, random.Random(0))
        assert empty == [], f"河北彩伽應為空池（None=搜尋失敗）: {empty!r}"

        monkeypatch.setattr(gp, "_names_for", lambda pk, qn: set(names))
        cands = gp.graphis_candidates("miru", "miru", "wiki", set(), budget_s=8.0)
        assert 1 <= len(cands) <= 6, f"完整入口候選數異常: {cands}"
        assert all(gp.is_collectible_url(u, _eid(u)) for u in cands), cands
    finally:
        gp._SEARCH_CACHE.clear()
        gp._ENTRY_CACHE.clear()


def test_gfriends_canary():
    _run_actress_canary(
        "gfriends",
        probe_fn=_probe_gfriends,
        probe_desc=_GFRIENDS_PROBE_URL,
        # lookup_gfriends returns a bare URL string (or None) — not a dict
        # like the other three sources.
        fetch_fn=lookup_gfriends,
        usable_fn=lambda result: bool(result),
    )


def _avbase_usable(result, expected_birth) -> bool:
    return bool(result and result.get("birth") == expected_birth)


def _assert_avbase_alias(name, result) -> None:
    """Independent of the quorum verdict: a green 三上悠亜 must not hide a dead alias path."""
    alias_name, alias = AVBASE_ALIAS_EXPECTED
    if name != alias_name or not result:
        return
    others = result.get("other_names") or []
    missing = [n for n in (alias_name, alias) if n not in others]
    if missing:
        pytest.fail(
            f"avbase: 別名路徑壞了 (not birthday) — {alias_name} 的 other_names "
            f"缺少 {missing}，實得 {others}"
        )


def test_avbase_canary():
    probe_cache = []  # lazy: probed at most once, only when a name is unusable

    def _reachable() -> bool:
        if not probe_cache:
            probe_cache.append(_probe_avbase())
        return probe_cache[0]

    results = []
    alias_missing = False  # alias sample returned None (not a dict)
    for name, expected_birth in AVBASE_EVERGREEN:
        result = scrape_avbase(name)
        _assert_avbase_alias(name, result)
        alias_missing = alias_missing or (name == AVBASE_ALIAS_EXPECTED[0] and not result)
        usable = _avbase_usable(result, expected_birth)
        results.append("pass" if usable else _classify(result, lambda r: False, _reachable()))
    _verdict(results, "avbase", "https://www.avbase.net/")
    # Quorum is green here (>=1 pass). A dead alias sample must still be red
    # when the site is reachable; unreachable keeps the quorum outcome.
    if alias_missing and _reachable():
        pytest.fail(
            f"avbase: 別名樣本 {AVBASE_ALIAS_EXPECTED[0]} 查無（站可達）— "
            "常青別名樣本可能被改名/合併/刪除，別名路徑無法驗證"
        )
