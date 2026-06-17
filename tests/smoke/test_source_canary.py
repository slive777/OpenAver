"""Live smoke canary — 8 source health check (TASK-73b-T3).

Wires the T1 pure decision-core (`classify_one` / `quorum_verdict`) and the T2
evergreen number list (`CANARY_NUMBERS`) into a live smoke suite: one
`test_{source}_canary` per source, each running the real `search()` over its
numbers, adding a reachability probe for Group A, and turning the quorum verdict
into pytest pass / skip / fail.

ZERO production scraper changes. The deterministic judgement logic is covered by
`tests/unit/test_source_canary_logic.py` (runs in CI, no network). This file is
the live shell only — it must NOT be collected by the standard PR command
(`--ignore=tests/smoke -m "not smoke and not e2e"`).

verdict mapping:
  green -> pass (source alive)
  skip  -> pytest.skip (unreachable / known-dead / proxy not configured)
  red   -> pytest.fail (200-but-empty parse, or returned wrong/empty Video)
"""
import pytest

from tests.smoke._canary_core import classify_one, quorum_verdict, GROUP_A
from tests.smoke._canary_numbers import CANARY_NUMBERS
from tests.smoke._probe import _probe_reachable
from core.scrapers import (
    JavBusScraper,
    JAV321Scraper,
    HEYZOScraper,
    D2PassScraper,
    FC2Scraper,
    JavDBScraper,
    AVSOXScraper,
    DMMScraper,
)

pytestmark = pytest.mark.smoke


def _run_canary(source: str, scraper, note: str = "") -> None:
    """Run the canary for one source: loop numbers -> classify -> quorum -> verdict.

    quorum needs every number's result before deciding, so this is a per-source
    loop (NOT pytest.parametrize).

    `note` (optional) prepends a source-specific hint to the skip/fail reason so a
    human reading `pytest -r s` can tell an *expected* skip (avsox known-dead,
    javdb CF-ban) from an incidental one — without touching the pure T1 core.
    """
    results = []
    for number in CANARY_NUMBERS[source]:
        try:
            video = scraper.search(number)
        except TimeoutError as e:
            # Feed the exception instance (not None) so classify_one row 1 -> skip.
            results.append(classify_one(e, None, number, source))
            continue
        probe = _probe_reachable(source, number, scraper) if source in GROUP_A else None
        results.append(classify_one(video, probe, number, source))

    verdict, reason = quorum_verdict(results)
    if verdict == "green":
        return
    hint = f"{note} — " if note else ""
    if verdict == "skip":
        pytest.skip(f"{source}: {hint}{reason}")
    pytest.fail(f"{source}: {hint}{reason}")


# ========== Group A (probe-backed) ==========

def test_javbus_canary():
    _run_canary("javbus", JavBusScraper())


def test_jav321_canary():
    _run_canary("jav321", JAV321Scraper())


def test_heyzo_canary():
    _run_canary("heyzo", HEYZOScraper())


def test_d2pass_canary():
    _run_canary("d2pass", D2PassScraper())


# ========== Group B (quorum-only, no probe) ==========

def test_fc2_canary():
    _run_canary("fc2", FC2Scraper())


def test_javdb_canary():
    # javdb needs curl_cffi (CF bypass). Numbers are deliberately few -> all-skip
    # must not fail (Group B quorum: None probe -> row 6 skip).
    try:
        import curl_cffi  # noqa: F401
    except ImportError:
        pytest.skip("curl_cffi not installed")
    _run_canary("javdb", JavDBScraper(), note="javdb all-skip likely CF-banned")


def test_avsox_canary():
    # Known-dead until US5 (site went SPA + 403). Group B -> None probe -> row 6
    # skip -> quorum skip -> pytest.skip. CANARY_NUMBERS["avsox"] notes known-dead.
    _run_canary("avsox", AVSOXScraper(), note="known-dead until US5")


# ========== dmm (proxy-gated, 4-way) ==========

def test_dmm_canary():
    from core.config import load_config
    from core.scraper import _dmm_proxy_url, _is_dmm_enabled
    from core.scrapers.models import ScraperConfig

    raw = (load_config().get("search") or {}).get("proxy_url") or ""
    if not _is_dmm_enabled(raw):
        pytest.skip("dmm proxy 未設定")
    scraper = DMMScraper(ScraperConfig(proxy_url=_dmm_proxy_url(raw)))
    _run_canary("dmm", scraper)
