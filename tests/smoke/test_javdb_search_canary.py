"""Live smoke canary — JavDB fuzzy search (TASK-175b-T12).

Guards the JavDB provider against site-side change: entity lookup (actor /
maker / code), entity list pages + the membership guard, keyword search, and the
reverse canary (a wrongly-flagged filter silently returns the site-wide latest
page; the guard must classify it NOT_ANSWERABLE instead of showing it).

Verdict: probe unreachable -> skip (reason starts with UNVERIFIED, which means
NOT verified, not passed). After the probe passes, ANY failure is a failure,
including SourceBlocked / SourceUnreachable (BE-PY-03). No retries.

Request budget (pressure on JavDB): an autouse fixture gates `HTTPAdapter.send`
for the JavDB API hosts, so EVERY request really sent counts (mirror-host
fallback and redirects included; it calls the real send, never mocks a
response): >= 2.0 s between two requests, hard cap 26 requests per run. Detail
workers are thereby serialized. Every request goes through the proxy
http://192.168.1.177:8888/ (owner 2026-10-22): the provider is built on a
JavDBScraper whose ProxySettings(url=_PROXY, scope="all") makes `_proxies()` return
that proxy, and the counter refuses to send (fail-closed) when the `proxies` it is
handed are anything else. The first 403 / 429 response of ANY request (the mirror host
included) stops the run: nothing more is sent and every later cell fails (a block is
never "unverified"). Actress names are NOT asserted (owner decision 2026-10-21: names
stay as the detail page gives them).

No site HTML/JSON is stored; ids come from the live site at run time.
"""
import threading
import time

import pytest

pytestmark = pytest.mark.smoke

_PROXY = "http://192.168.1.177:8888/"
_PROXIES = {"http": _PROXY, "https": _PROXY}
_MIN_GAP = 2.0  # seconds between two JavDB requests (end of previous -> start of next)
_MAX_CALLS = 26
_MIN_ITEMS = 20

_STATE = {"calls": 0, "last_end": None, "min_gap": None, "max_gap": None, "stopped": None, "proxies": "n/a"}
_ERRORS = []  # (exception type, endpoint path) of every api_get that raised after the probe
_LOCK = threading.Lock()


_STOP_STATUS = frozenset({403, 429})


def _install_counter(monkeypatch):
    """Gate EVERY request actually sent to a JavDB API host, at the transport layer (BE-TEST-55).

    `api_get` retries the mirror host on a 403 / 429 / transport error by itself, and `requests` follows redirects
    below `get()`: a wrapper around `api_get` would miss both. `HTTPAdapter.send` is the one point every request
    passes through, so the gate sits there (only for JavDB API hosts; other hosts pass untouched): count + budget,
    stop flag, >= _MIN_GAP pacing, proxy check, and ANY 403 / 429 response sets the stop flag. It calls the real send
    and returns the response untouched (never mocks one). A thin wrapper around `api_get` only records the proxy
    assertion and exceptions that end up swallowed upstream.
    """
    from urllib.parse import urlparse

    from requests.adapters import HTTPAdapter

    from core.scrapers import javdb_api
    from core.scrapers.errors import SourceBlocked

    real_send = HTTPAdapter.send
    if getattr(real_send, "_javdb_canary", False):
        return  # already installed by an outer fixture; never stack two gates (double counting)
    hosts = {urlparse(h).netloc for h in javdb_api._API_HOSTS}

    def gated_send(self, request, **kwargs):
        if urlparse(request.url).netloc not in hosts:
            return real_send(self, request, **kwargs)
        with _LOCK:  # holds the whole real send: strictly serialized
            if _STATE["stopped"]:
                blocked = SourceBlocked(f"canary stopped, nothing more is sent: {_STATE['stopped']}")
                blocked._canary_noted = True  # the stop flag already fails the cell; not also a "swallowed error"
                raise blocked
            if _STATE["calls"] >= _MAX_CALLS:
                pytest.fail("超出請求預算")
            # the home IP must never reach JavDB directly: refuse to send unless THIS request carries the proxy
            scheme = urlparse(request.url).scheme
            assert (kwargs.get("proxies") or {}).get(scheme) == _PROXY, (
                "request is not routed through the proxy", request.url, kwargs.get("proxies"))
            _STATE["calls"] += 1
            if _STATE["last_end"] is not None:
                wait = _STATE["last_end"] + _MIN_GAP - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            t0 = time.monotonic()
            if _STATE["last_end"] is not None:
                gap = t0 - _STATE["last_end"]
                _STATE["min_gap"] = gap if _STATE["min_gap"] is None else min(_STATE["min_gap"], gap)
                _STATE["max_gap"] = gap if _STATE["max_gap"] is None else max(_STATE["max_gap"], gap)
            try:
                resp = real_send(self, request, **kwargs)
            except Exception as exc:
                if not getattr(exc, "_canary_noted", False):
                    _ERRORS.append((type(exc).__name__, request.url))
                    exc._canary_noted = True
                _STATE["last_end"] = time.monotonic()
                raise
            _STATE["last_end"] = time.monotonic()
            if resp.status_code in _STOP_STATUS:
                _STATE["stopped"] = f"HTTP {resp.status_code} {request.url}"
            return resp

    gated_send._javdb_canary = True
    monkeypatch.setattr(HTTPAdapter, "send", gated_send)

    real_get = javdb_api.api_get

    def recorded_get(path, params=None, proxies=None):
        assert proxies == _PROXIES, ("request is not routed through the proxy", path, proxies)
        try:
            return real_get(path, params, proxies)
        except Exception as exc:
            if isinstance(exc, SourceBlocked):
                _STATE["stopped"] = _STATE["stopped"] or f"SourceBlocked {path}"  # e.g. every host answered 503
            elif not getattr(exc, "_canary_noted", False):
                _ERRORS.append((type(exc).__name__, path))  # swallowed upstream (verify_page): still fails the cell
            raise

    monkeypatch.setattr(javdb_api, "api_get", recorded_get)


@pytest.fixture(autouse=True)
def _budget(monkeypatch):
    _install_counter(monkeypatch)
    start = len(_ERRORS)
    yield
    if _STATE["stopped"]:
        pytest.fail(f"停手: 第一次被擋 {_STATE['stopped']}（其後不再送出任何請求；被擋不是未驗證）")
    # verify_page swallows detail exceptions; any api_get error after the probe must still fail the cell
    if len(_ERRORS) > start:
        pytest.fail(f"探針後 api_get 拋例外（verify_page 會吞掉，這裡補抓）: {_ERRORS[start:]}")


@pytest.fixture(scope="module", autouse=True)
def _report():
    yield
    print(
        f"\n[javdb canary] http requests={_STATE['calls']} (cap {_MAX_CALLS}) "
        f"min_gap={_STATE['min_gap']} max_gap={_STATE['max_gap']} (floor {_MIN_GAP}s) "
        f"stopped={_STATE['stopped']} proxies={_STATE['proxies']}"
    )


@pytest.fixture(scope="module")
def provider():
    """One provider for the whole module; probes once with check (1)'s resolve."""
    from core.scrapers.errors import SourceBlocked, SourceUnreachable
    from core.search_providers.javdb import JavDBProvider
    from core.search_providers.types import Kind

    from core.proxy_policy import ProxySettings
    from core.scrapers.javdb import JavDBScraper
    from core.scrapers.models import ScraperConfig

    mp = pytest.MonkeyPatch()
    try:  # whatever is raised below (even an unlisted exception), the global patches must be undone
        _install_counter(mp)
        scraper = JavDBScraper(ScraperConfig(proxy_settings=ProxySettings(url=_PROXY, scope="all")))
        p = JavDBProvider(scraper=scraper)
        assert p._proxies() == _PROXIES, p._proxies()  # fail-closed: not the proxy -> never reach the probe
        _STATE["proxies"] = p._proxies()
        try:
            ref = p.resolve(Kind.ACTOR, "三上悠亞")
        except (SourceBlocked, SourceUnreachable, ConnectionError, TimeoutError, OSError) as exc:
            _STATE["stopped"] = None  # blocked/unreachable at the probe is the UNVERIFIED skip (nothing was verified), not a mid-run block
            pytest.skip(f"UNVERIFIED: JavDB unreachable, probe resolve raised {type(exc).__name__}: {exc}")
    finally:
        mp.undo()
    _ERRORS.clear()  # only post-probe errors count
    assert ref is not None, "探針 resolve(ACTOR,'三上悠亞') 查無（站可達但實體查詢失效）"
    return p


@pytest.fixture(scope="module")
def actor_ref(provider):
    from core.search_providers.types import Kind

    mp = pytest.MonkeyPatch()
    _install_counter(mp)
    try:
        return provider.resolve(Kind.ACTOR, "三上悠亞")  # module cache hit, no request
    finally:
        mp.undo()


def _guard(provider, items, ref):
    from core.search_providers import pipeline

    return pipeline.verify_page(provider, items[: pipeline.GUARD_SIZE], ref)


def test_actor_trad_and_romaji_same_id(provider, actor_ref):
    from core.search_providers.types import Kind

    other = provider.resolve(Kind.ACTOR, "Yua Mikami")
    assert other is not None, "resolve(ACTOR,'Yua Mikami') 查無"
    assert other.id == actor_ref.id, (actor_ref.id, other.id)


def test_actor_list_first_page_passes_guard(provider, actor_ref):
    from core.search_providers.types import Window

    page = provider.list_entity(actor_ref, Window(0, _MIN_ITEMS))
    assert len(page.items) >= _MIN_ITEMS, f"actor list parsed {len(page.items)} items, expected >= {_MIN_ITEMS}"
    verdict = _guard(provider, page.items, actor_ref)
    assert verdict.passed is True, verdict


@pytest.fixture(scope="module")
def maker_ref(provider):
    from core.search_providers.types import Kind

    mp = pytest.MonkeyPatch()
    _install_counter(mp)
    try:
        return provider.resolve(Kind.MAKER, "カリビアンコム")
    finally:
        mp.undo()


def test_maker_resolves(maker_ref):
    assert maker_ref is not None, "resolve(MAKER,'カリビアンコム') 查無"


def test_maker_list_first_page_passes_guard(provider, maker_ref):
    from core.search_providers.types import Window

    assert maker_ref is not None, "resolve(MAKER,'カリビアンコム') 查無"
    page = provider.list_entity(maker_ref, Window(0, _MIN_ITEMS))
    assert len(page.items) >= _MIN_ITEMS, f"maker list parsed {len(page.items)} items, expected >= {_MIN_ITEMS}"
    verdict = _guard(provider, page.items, maker_ref)
    assert verdict.passed is True, verdict


def test_code_prefix_resolves(provider):
    from core.search_providers.types import Kind

    assert provider.resolve(Kind.CODE, "MIDV") is not None, "resolve(CODE,'MIDV') 查無"


def test_keyword_search_has_results(provider):
    from core.search_providers.types import Window

    page = provider.search_keyword("温泉", Window(0, _MIN_ITEMS))
    assert len(page.items) >= 1, "search_keyword('温泉') 0 筆"


def test_reverse_wrong_filter_is_not_answerable(provider, maker_ref):
    """Real maker id + deliberately wrong flag ('t') -> site silently returns the site-wide latest page.
    The guard must refuse it (NOT_ANSWERABLE), not show it as the maker's works."""
    from core.scrapers import javdb_api
    from core.search_providers import javdb
    from core.search_providers.types import Outcome

    assert maker_ref is not None, "resolve(MAKER,'カリビアンコム') 查無"
    rows = javdb_api.api_list_tags(f"0:t:{maker_ref.id}", 1, proxies=provider._proxies())
    items = javdb.parse_list_rows(rows)
    if len(items) < _MIN_ITEMS:
        pytest.fail(
            f"前提失效：錯誤 flag 只回 {len(items)} 筆（<{_MIN_ITEMS}），站方可能不再靜默回全站最新，金絲雀需重新設計"
        )
    verdict = _guard(provider, items, maker_ref)
    assert verdict.passed is False, verdict
    assert verdict.outcome is Outcome.NOT_ANSWERABLE, verdict.outcome


def test_actor_alt_names_japanese_canonical_for_trad_and_romaji(provider, actor_ref):
    """175d: both the Traditional-Chinese and the romaji spelling must give the SAME Japanese-canonical candidate list
    (it contains 三上悠亜 and no pure-ASCII token), so the relay can ask metatube with the Japanese name.

    Data comes from the live site through the module cache the probe (and test_actor_trad_and_romaji_same_id) filled,
    so this cell costs 0-1 requests; clear_resolve_cache() is deliberately not called (it would add requests).
    """
    from core.search_providers.types import Kind

    trad = provider.alt_names(Kind.ACTOR, "三上悠亞")
    romaji = provider.alt_names(Kind.ACTOR, "Yua Mikami")
    assert "三上悠亜" in trad, f"alt_names(ACTOR,'三上悠亞') 缺日文正名: {trad}"
    assert not [t for t in trad if t.isascii()], f"alt_names 出現純 ASCII token: {trad}"
    assert romaji == trad, (trad, romaji)


def test_skip_format_check_finds_nonstandard_numbers(provider, monkeypatch):
    """183: with skip_format_check the typed string goes to the App data channel as-is.

    Only the App channel is exercised: the HTML fallback goes through curl_cffi (not HTTPAdapter.send), so it would
    be neither counted nor paced here -> swapped for a no-op. A made-up number must come back None, never another film.
    """
    from core.proxy_policy import ProxySettings
    from core.scrapers.javdb import JavDBScraper
    from core.scrapers.models import ScraperConfig

    monkeypatch.setattr(JavDBScraper, "search_via_html", lambda self, n: None)
    scraper = JavDBScraper(
        ScraperConfig(proxy_settings=ProxySettings(url=_PROXY, scope="all")), skip_format_check=True,
    )
    for number in ("MKD-S85", "XXX-AV-20433", "S2MBD-011"):
        video = scraper.search(number)
        assert video is not None, f"search({number!r}) 查無（旗標 True 應照原樣問到 javdb）"
        assert video.number == number, (number, video.number)
    assert scraper.search("ZZQ-X77") is None
