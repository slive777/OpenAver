"""
core.metatube.probe — Connection self-test for metatube HTTP providers.

Implements TASK-63a-5 (spec §5.4 / US9):
  - METATUBE_PROBE_CANARIES: known-good movie IDs for each supported provider.
  - probe_provider(): test a single provider with its canary.
  - probe_all(): parallel probe of all providers with ThreadPoolExecutor.

Design decisions (CD-63a-12):
  - probe-404 = failure (opposite of routing-404, MAJOR-3).
    Routing treats MetatubeNotFound as "movie absent from this provider" (not a
    failure).  Probe treats it as "canary 404 = scraper broken" (failure).
    Both semantics are correct in their context; probe catches MetatubeError
    broadly (all subclasses → False).
  - max_workers=10 (intentional departure from core/scraper.py MAX_WORKERS=2).
    scraper MAX_WORKERS=2 targets remote public sites (high latency, rate limits).
    probe targets a single local metatube server; 10 workers keeps total probe
    time ~1s while not overwhelming the local server.
  - Each worker creates its own MetatubeHttpClient (= its own requests.Session).
    No shared Session across threads (CD-63a-6 / Codex P1a).
  - Synchronous function; FastAPI BackgroundTasks wrapping is TASK-63b.
  - probe_all assumes state.connect() was already called (BLOCKER-3).
    It probes from a bulk-true baseline downgrading failed providers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Literal

from core.logger import get_logger
from core.metatube.client import MetatubeHttpClient  # patch target: core.metatube.probe.MetatubeHttpClient
from core.metatube.errors import MetatubeError
from core.metatube.validation import redact_metatube_url
from core.metatube.state import MetatubeConnectionState

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Canary map — known-good movie IDs per provider
# ---------------------------------------------------------------------------

# known-good as of 2026-05-31; source: TASK-63poc-1-provider-reachability.md §4.1
# If a canary starts returning 404, the provider's scraper may have broken upstream.
# Update the value (or remove the key and mark provider as no-canary) when that happens.
METATUBE_PROBE_CANARIES: dict[str, str] = {
    # === 有碼 providers (13) ===
    'JavBus':     'SSIS-001',
    'FANZA':      '1stars00141',   # SSIS-001 returns 500 for FANZA; use internal ID format
    'MGS':        'SIRO-5251',
    'DUGA':       'dandy-0344',
    'AVE':        '4319',
    'DAHLIA':     'dldss339',
    'FALENO':     'fsdss754',
    'Gcolle':     '847256',
    'Getchu':     '4018339',
    'HeyDouga':   '4037-479',
    'JAVFREE':    '243452-1151912',
    'Pcolle':     '156785614478ab480db',
    'TOKYO-HOT':  'n1500',
    # === 無碼 providers (13) ===
    'HEYZO':        'HEYZO-2500',
    '1Pondo':       '020125_001',
    'Caribbeancom': '020125-001',    # dash, not underscore
    'CaribbeancomPR': '020125_001',  # underscore, unlike Caribbeancom
    '10musume':     '053026_01',
    'C0930':        'ki230101',
    'H0930':        'ori1643',
    'H4610':        'tk0047',
    'MURAMURA':     '091522_959',
    'MYWIFE':       '1542',          # runtime=0 is normal (POC §4.1)
    'PACOPACOMAMA': '082107_257',
    'FC2':          '2812904',
    'fc2hub':       '1152468-2725031',
    # Providers without a canary are classified via METATUBE_KNOWN_FAILING below.
}

METATUBE_KNOWN_FAILING: frozenset[str] = frozenset({'JAV321', 'SOD', 'FC2PPVDB', 'KIN8'})


def classify_provider(name: str) -> Literal['canary', 'known_failing', 'unknown']:
    """Classify a provider by canary availability and known-failure list."""
    if name in METATUBE_PROBE_CANARIES:
        return 'canary'
    if name in METATUBE_KNOWN_FAILING:
        return 'known_failing'
    return 'unknown'


# ---------------------------------------------------------------------------
# probe_provider — single provider test
# ---------------------------------------------------------------------------

def probe_provider(client: MetatubeHttpClient, provider: str) -> bool:
    """
    Test a single provider by fetching its canary movie ID.

    Args:
        client:   A MetatubeHttpClient instance (caller creates one per worker).
        provider: Provider name (e.g. 'FANZA').

    Returns:
        True  — get_info returned without raising (canary fetch succeeded).
        False — no canary exists for this provider, or any MetatubeError raised.

    Note (MAJOR-3 / CD-63a-6):
        MetatubeNotFound (HTTP 404) is treated as FAILURE here.
        This is intentionally opposite to routing, where 404 means "movie absent
        from this provider" and is not a mark_failed trigger.
        probe-404 means the canary (a known-good ID) returned 404 → scraper broken.
    """
    canary = METATUBE_PROBE_CANARIES.get(provider)
    if canary is None:
        # No canary = known-broken or unverifiable provider; skip request, return False
        logger.debug('probe_provider: no canary for %r → skip (False)', provider)
        return False

    try:
        client.get_info(provider, canary)
        logger.debug('probe_provider: %r canary %r → OK (True)', provider, canary)
        return True
    except MetatubeError as exc:
        # ANY MetatubeError (including MetatubeNotFound / 404) = probe failure.
        # This is OPPOSITE to routing, where MetatubeNotFound = not a failure.
        # (CD-63a-6 / MAJOR-3)
        logger.debug('probe_provider: %r canary %r → FAIL (%s: %s)', provider, canary, type(exc).__name__, exc)
        return False


# ---------------------------------------------------------------------------
# probe_all — parallel probe of all providers
# ---------------------------------------------------------------------------

def probe_all(
    base_url: str,
    token: str | None,
    state: MetatubeConnectionState,
    provider_names: list[str],
    on_progress: Callable[[int, int], None] | None = None,
    generation: int | None = None,
) -> dict[str, bool]:
    """
    Probe all providers in parallel and update state accordingly.

    Each worker creates its own MetatubeHttpClient (no shared Session).
    Results are collected in the main thread (via as_completed) to serialise
    state mutations and on_progress callbacks — avoids race conditions.
    Canary providers are probed, known-failing providers are marked failed
    without probing, and unknown providers keep the connect() baseline untouched.

    Args:
        base_url:       Metatube server base URL (e.g. 'http://192.168.1.10:8900').
        token:          Optional Bearer token (empty string = no auth).
        state:          MetatubeConnectionState instance to update.
                        Caller MUST have called state.connect() before probe_all
                        (probe downgrades from bulk-true, BLOCKER-3).
        provider_names: List of provider names to probe.
        on_progress:    Optional callback(done: int, total: int).
                        Called once per completed provider in the main thread.

    Returns:
        dict[str, bool] mapping each provider name to its probe result.

    Design note (CD-63a-12):
        max_workers=10 is intentional — probing a single local server differs
        from scraping remote public sites (MAX_WORKERS=2 in core/scraper.py).
    """
    total = len(provider_names)
    results: dict[str, bool] = {}

    if total == 0:
        return results

    logger.info('probe_all: probing %d providers via %s', total, redact_metatube_url(base_url))

    def _worker(name: str) -> tuple[str, bool]:
        """Worker: probe canary providers; others return fixed results without probing."""
        if classify_provider(name) == 'unknown':
            return name, True
        if classify_provider(name) == 'known_failing':
            return name, False
        client = MetatubeHttpClient(base_url, token)
        ok = probe_provider(client, name)
        return name, ok

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_name = {
            executor.submit(_worker, name): name
            for name in provider_names
        }

        done = 0
        for future in as_completed(future_to_name):
            name, ok = future.result()
            results[name] = ok

            # Update state (thread-safe — state uses RLock internally)
            source_id = f'metatube:{name}'
            if classify_provider(name) == 'unknown':
                pass  # unknown: never probed; leave connect() baseline and runtime marks untouched
            elif ok:
                state.mark_available(source_id, generation=generation)
                logger.debug('probe_all: %r → available', source_id)
            else:
                state.mark_failed(source_id, generation=generation)
                logger.debug('probe_all: %r → failed', source_id)
            done += 1

            # Notify progress in main thread (serialised, no race)
            if on_progress is not None:
                on_progress(done, total)

    logger.info('probe_all: completed %d/%d providers', done, total)
    return results
