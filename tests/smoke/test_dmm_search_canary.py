"""Live smoke canary — DMM fuzzy search (TASK-175c-T11).

Guards the DMM provider against site-side change AND against our own query
silently breaking: name -> entity resolve (actress / maker), the entity list by
id (including titles that are not released yet), the official maker number
(3DSVR-1774, not the derived DSVR-1774) and the reverse canary (an id that does
not exist must give an empty page, which is the fact that lets the membership
guard stay out of DMM's way).

Verdict: probe unreachable -> skip (reason starts with UNVERIFIED, which means
NOT verified, not passed). After the probe passes, ANY failure is a failure,
including SourceBlocked / SourceUnreachable (BE-PY-03). No retries. The first
403 / 429 / 503 (or a Cloudflare challenge page) stops the whole run: nothing
more is sent and every later cell fails. A reachable site that answers the
probe with zero rows is a failure too, not a skip: DMM answers an empty array to
a non-Taiwan / non-Japan exit IP (BE-ENV-05), but a silent "unverified" would
hide a really broken query, so the message points at the exit IP instead.

Live rules (owner 2026-10-22): DIRECT connection (never the proxy: a foreign
exit IP gets empty arrays), strictly serialized, >= 1.0 s between two requests,
hard cap 20 requests per pytest process. The counter / recorder only measures
and paces: it sits on the session's `HTTPAdapter.send`, the one point every
request actually sent passes through (redirect hops included:
`Session.resolve_redirects()` calls `Session.send()` directly, so a wrapper
around `session.post` / `session.get` would miss them), calls the real send and
returns the response untouched (it never mocks a response). `list_contents` is recorded
beside it (arguments and the raw rows it returned, in memory only) so the cells
can look at what the site really answered.

Self-contained: does not import tests/smoke/_canary_*.py. No site HTML/JSON is
stored; ids and counts come from the live site at run time and assertions only
compare what OUR code produced (ids, numbers, counts, a status string).
"""
import threading
import time

import pytest

pytestmark = pytest.mark.smoke

_MIN_GAP = 1.0  # seconds from the end of one request to the start of the next
_MAX_CALLS = 20
_MIN_ITEMS = 20
_STOP_STATUS = frozenset({403, 429, 503})
# Cloudflare interstitial markers ("challenge-platform" is not one: it is injected into normal pages too)
_CHALLENGE_MARKERS = ("just a moment", "attention required! | cloudflare", "cf-browser-verification", "cf_chl_opt")

_STATE = {"calls": 0, "last_end": None, "min_gap": None, "stopped": None, "overflow": False, "armed": False,
          "actor_ref": None}
_LOG = []  # one dict per request actually sent (each redirect hop is its own entry): method, url, status, t0, t1  (no bodies)
_LISTS = []  # one dict per list_contents call: query_word, filter, limit, offset, rows (raw, in memory only)
_ERRORS = []  # (exception type, url) of every real send that raised after the probe
_CELLS = {}  # test name -> requests that cell sent
_LOCK = threading.Lock()


# ----------------------------------------------------------------------------- recorder / throttle
def _note_error(exc, url):
    """Remember a real exception of a request that was really sent (once per exception object)."""
    if not getattr(exc, "_canary_noted", False):
        _ERRORS.append((type(exc).__name__, url))
        exc._canary_noted = True


def _is_challenge(resp, stream):
    ctype = resp.headers.get("Content-Type", "")
    if resp.status_code != 200 or stream or "html" not in ctype.lower():
        return False  # the GraphQL endpoint answers JSON; only an HTML 200 can be an interstitial
    text = resp.text.lower()
    return any(m in text for m in _CHALLENGE_MARKERS)


def _gate_session_adapters(session):
    """Gate EVERY request this scraper's own session actually sends: count, budget, stop flag, pacing, direct check, record.

    The gate is on each mounted adapter's `send` (not on `session.post` / `session.get`): redirect hops go
    Session.resolve_redirects() -> Session.send() -> adapter.send() and never touch post()/get(), so they would bypass them.

    Layered on top, an outer wrapper around the WHOLE `session.request` only records exceptions (no counting, no pacing):
    requests reads the body AFTER adapter.send returned, so a body transfer error / read timeout would never reach
    `_ERRORS`; DMM turns it into SourceUnreachable and `_detail_or_shallow` swallows it into a shallow card - the cell
    would still pass.
    """
    from requests.utils import select_proxy

    from core.scrapers.errors import SourceBlocked

    def gate(real_send):
        def gated_send(request, **kwargs):
            with _LOCK:  # holds the whole real send: detail workers of verify_page / run_window are serialized
                if _STATE["stopped"]:
                    blocked = SourceBlocked(f"canary stopped, nothing more is sent: {_STATE['stopped']}")
                    blocked._canary_noted = True  # the stop flag already fails the cell; not also a "swallowed error"
                    raise blocked
                if _STATE["calls"] >= _MAX_CALLS:
                    _STATE["overflow"] = True
                    pytest.fail(f"超出請求預算 (cap {_MAX_CALLS})")
                # DMM must be reached directly (a proxy exit outside Taiwan / Japan gets empty arrays): refuse to send
                # unless THIS request selects no proxy at all
                assert select_proxy(request.url, kwargs.get("proxies") or {}) is None and session.trust_env is False, (
                    "DMM request is not direct", request.url, kwargs.get("proxies"))
                _STATE["calls"] += 1
                if _STATE["last_end"] is not None:
                    wait = _STATE["last_end"] + _MIN_GAP - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                t0 = time.monotonic()
                if _STATE["last_end"] is not None:
                    gap = t0 - _STATE["last_end"]
                    _STATE["min_gap"] = gap if _STATE["min_gap"] is None else min(_STATE["min_gap"], gap)
                try:
                    resp = real_send(request, **kwargs)
                except Exception as exc:
                    _note_error(exc, request.url)
                    _STATE["last_end"] = time.monotonic()
                    raise
                _STATE["last_end"] = time.monotonic()
                _LOG.append({"method": request.method, "url": request.url, "status": resp.status_code,
                             "t0": t0, "t1": _STATE["last_end"]})
                if resp.status_code in _STOP_STATUS or _is_challenge(resp, kwargs.get("stream")):
                    _STATE["stopped"] = f"HTTP {resp.status_code} {request.method} {request.url}"
                return resp

        return gated_send

    for adapter in list(session.adapters.values()):
        adapter.send = gate(adapter.send)

    real_request = session.request

    def recorded_request(method, url, *args, **kwargs):
        try:
            return real_request(method, url, *args, **kwargs)
        except Exception as exc:  # recorded for the cell guard, then re-raised untouched
            _note_error(exc, url)
            raise

    session.request = recorded_request


def _record_list_contents(scraper):
    """Instance-level wrapper: remember (arguments, raw rows) of every list_contents call; the real function runs."""
    real = scraper.list_contents

    def recorded(query_word=None, filter=None, *, limit, offset):
        rec = {"query_word": query_word, "filter": filter, "limit": limit, "offset": offset, "rows": None}
        _LISTS.append(rec)
        result = real(query_word, filter, limit=limit, offset=offset)  # transport errors propagate untouched
        rec["rows"] = result.rows
        return result

    scraper.list_contents = recorded


def _filter_ids(rec):
    """[(filter key, id)] of a recorded list_contents call (empty for a keyword search)."""
    flt = rec["filter"] or {}
    return [(key, str(item["id"])) for key, spec in flt.items() for item in spec["ids"]]


def _build_scraper():
    from core.proxy_policy import ProxySettings
    from core.scrapers.dmm import DMMScraper
    from core.scrapers.models import ScraperConfig

    # url="" -> direct; proxy_settings=None would read the owner's live config and bring their DMM proxy in
    scraper = DMMScraper(ScraperConfig(proxy_settings=ProxySettings(url="")))
    scraper._session.trust_env = False  # an HTTPS_PROXY in the environment must not turn "direct" into a foreign exit
    _gate_session_adapters(scraper._session)
    _record_list_contents(scraper)
    return scraper


@pytest.fixture(scope="module", autouse=True)
def _report():
    yield
    gap = _STATE["min_gap"]
    print(
        f"\n[dmm canary] requests={_STATE['calls']} (cap {_MAX_CALLS}) "
        f"min_gap={'n/a' if gap is None else f'{gap:.3f}s'} (floor {_MIN_GAP}s) "
        f"stopped={_STATE['stopped']} overflow={_STATE['overflow']} direct=True "
        f"per_cell={_CELLS}"
    )


@pytest.fixture(autouse=True)
def _cell_guard(request):
    """Per cell: count its requests; after the run, a stop / overflow / swallowed error that appeared DURING this cell fails it."""
    calls0, errors0 = _STATE["calls"], len(_ERRORS)
    was_stopped, was_overflow = bool(_STATE["stopped"]), _STATE["overflow"]
    yield
    _CELLS[request.node.name] = _STATE["calls"] - calls0
    if not _STATE["armed"]:
        return
    if _STATE["overflow"] and not was_overflow:
        pytest.fail(f"超出請求預算 (cap {_MAX_CALLS})")
    if _STATE["stopped"] and not was_stopped:
        pytest.fail(f"停手: 第一次被擋 {_STATE['stopped']}（其後不再送出任何請求；被擋不是未驗證）")
    if len(_ERRORS) > errors0:
        # verify_page / _detail_or_shallow / the probes swallow per-request exceptions; a real error after the probe must still fail
        pytest.fail(f"探針後 adapter.send 拋例外（上層會吞掉，這裡補抓）: {_ERRORS[errors0:]}")


def _require_live():
    """First line of every cell: once a block was seen nothing else is sent and the cell fails (never skips)."""
    if _STATE["stopped"]:
        pytest.fail(f"停手: 先前已被擋 {_STATE['stopped']}，本格不送任何請求")


# ----------------------------------------------------------------------------- probe
@pytest.fixture(scope="module")
def provider():
    """One provider (one direct session) for the whole module; probes once with D1's resolve."""
    import requests

    from core.scrapers.errors import SourceBlocked, SourceUnreachable
    from core.search_providers.dmm import DMMProvider
    from core.search_providers.types import Kind

    p = DMMProvider(scraper=_build_scraper())
    try:
        ref = p.resolve(Kind.ACTOR, "三上悠亜")
    except (SourceBlocked, SourceUnreachable, requests.RequestException, ConnectionError, TimeoutError, OSError) as exc:
        pytest.skip(f"UNVERIFIED: DMM unreachable/blocked, probe resolve raised {type(exc).__name__}: {exc}")
    _ERRORS.clear()  # only post-probe errors count
    _STATE["armed"] = True
    _CELLS["probe(d1)"] = _STATE["calls"]
    if ref is None:
        probe_rows = _LISTS[-1]["rows"] if _LISTS else None
        if probe_rows == []:
            pytest.fail(
                "探針 list_contents('三上悠亜') 站可達但 0 筆（三上悠亜有 340+ 部，不是資料變動）："
                "BE-ENV-05 — 先確認本機出口 IP 是否台灣／日本，再懷疑程式"
            )
        pytest.fail(f"探針 resolve(ACTOR,'三上悠亜') 查無（站有回 {len(probe_rows or [])} 筆但比不出她：實體查詢失效）")
    _STATE["actor_ref"] = ref
    return p


@pytest.fixture(scope="module")
def actor_ref(provider):
    return _STATE["actor_ref"]


# ----------------------------------------------------------------------------- cells
def test_d1_actor_resolves_to_known_id(actor_ref):
    """D1: typing an actress name must find her DMM id, else DMM falls back to title keywords (no pre-orders)."""
    _require_live()
    assert actor_ref.id == "1030262", actor_ref


def test_actor_list_first_page_passes_guard(provider, actor_ref):
    """D2: the list by actress id parses and the membership guard accepts it (else DMM's entity list is skipped silently).

    The guard takes only the window's first title: every DMM detail costs ~4-5 requests and `belongs` is computed from
    the list facts, so one title is enough to prove the guard connects (and keeps the run inside the 20-request cap).
    """
    _require_live()
    from core.search_providers import pipeline
    from core.search_providers.types import Window

    page = provider.list_entity(actor_ref, Window(0, _MIN_ITEMS))
    assert len(page.items) >= _MIN_ITEMS, f"actor list parsed {len(page.items)} items, expected >= {_MIN_ITEMS}"
    verdict = pipeline.verify_page(provider, page.items[:1], actor_ref)
    assert verdict.passed is True, verdict


def test_d3_maker_list_includes_unreleased_titles(provider):
    """D3: the S1 capsule must list pre-orders (releaseStatus PRE_ORDER); depends on S1 having an unreleased title today."""
    _require_live()
    from collections import Counter

    from core.search_providers.types import Kind, Window

    ref = provider.resolve(Kind.MAKER, "S1")
    assert ref is not None, "resolve(MAKER,'S1') 查無"
    mark = len(_LISTS)
    page = provider.list_entity(ref, Window(0, _MIN_ITEMS))
    assert len(page.items) >= _MIN_ITEMS, f"maker list parsed {len(page.items)} items, expected >= {_MIN_ITEMS}"
    maker_calls = [rec for rec in _LISTS[mark:] if any(key == "makerIds" for key, _ in _filter_ids(rec))]
    assert maker_calls, "list_entity 沒有以 makerIds 篩選呼叫 list_contents"
    statuses = Counter(row.get("releaseStatus") for row in maker_calls[-1]["rows"])
    assert "PRE_ORDER" in statuses, f"S1 第一頁沒有預購片，releaseStatus 分佈={dict(statuses)}（資料相依：確認 S1 當下是否真的無預購）"


def test_d4_official_number_not_derived(provider):
    """D4: '3DSVR 1774' must show the official 3DSVR-1774 (the derived DSVR-1774 may scrape a different title)."""
    _require_live()
    from core.search_providers.types import Window

    page = provider.search_keyword("3DSVR 1774", Window(0, _MIN_ITEMS))
    numbers = [item.number for item in page.items]
    assert "3DSVR-1774" in numbers, numbers
    assert "DSVR-1774" not in numbers, numbers


def test_reverse_nonexistent_id_returns_empty_page(provider):
    """D5 (reverse): an id that does not exist gives an EMPTY page, not 'the site-wide latest'.

    If this ever stops holding the membership guard must be added to DMM's entity list, otherwise the user lands on
    somebody else's titles. The empty page must come with proof that the request really went out and returned no rows.
    """
    _require_live()
    from core.search_providers.types import EntityRef, Kind, Window

    before, mark = _STATE["calls"], len(_LISTS)
    page = provider.list_entity(EntityRef(Kind.ACTOR, "999999999", "不存在"), Window(0, _MIN_ITEMS))
    if page.items:
        pytest.fail(f"前提失效：不存在的 ID 回了 {len(page.items)} 筆（站方不再回空頁；DMM 實體清單需要補守衛）")
    assert page.items == []
    assert _STATE["calls"] - before >= 1, "list_entity 沒有真的發出請求（空頁不是站方答的）"
    sent = [rec for rec in _LISTS[mark:] if any(i == "999999999" for _, i in _filter_ids(rec))]
    assert sent, "沒有記錄到以 999999999 篩選的 list_contents 呼叫"
    assert sent[-1]["rows"] == [], f"站方原始 rows 不是空陣列: {len(sent[-1]['rows'] or [])} 筆"


def test_d6_renamed_actress_names_resolve_to_same_id(provider):
    """D6 (175d): 二階堂麗 and あかね麗 are one actress; both names must find the SAME DMM actress id.

    The probe cache is cleared before every test (conftest), so each name costs a real request (counter delta >= 2).
    """
    _require_live()
    from core.search_providers.types import Kind

    before = _STATE["calls"]
    new_name = provider.resolve(Kind.ACTOR, "二階堂麗")
    old_name = provider.resolve(Kind.ACTOR, "あかね麗")
    assert _STATE["calls"] - before >= 2, f"兩個名字沒有各發出請求（快取命中會讓這格變空殼）: {_STATE['calls'] - before}"
    assert new_name is not None and old_name is not None, (new_name, old_name)
    assert new_name.id == old_name.id, (new_name.id, old_name.id)


# releaseStatus five values seen live on 2026-10-29 (in core/ only PRE_ORDER has our own semantics; the rest are site names)
_KNOWN_RELEASE_STATUS = frozenset({"PRE_ORDER", "PRE_RELEASE", "LATEST_RELEASE", "NEW_RELEASE", "SEMI_NEW_RELEASE"})


def test_recent_or_list_first_page(provider, actor_ref):
    """184-T3b: one OR query over two actresses returns a first page our parser can use (rows, dates, actress lists)."""
    _require_live()
    from collections import Counter
    from datetime import datetime, timezone

    from core.search_providers.types import Kind, Window

    second = provider.resolve(Kind.ACTOR, "二階堂麗")
    assert second is not None, "resolve(ACTOR,'二階堂麗') 查無"
    mark = len(_LISTS)
    page = provider.list_actors_page([actor_ref, second], Window(0, 100), datetime.now(timezone.utc), set())
    rec = _LISTS[mark:][-1]
    assert rec["filter"]["actressIds"]["op"] == "OR", rec["filter"]
    assert rec["rows"], "OR 列表第一頁 rows 為空"
    bad = []
    for row in rec["rows"]:
        try:
            datetime.fromisoformat(row["deliveryStartAt"])
        except (KeyError, TypeError, ValueError):
            bad.append(row.get("id"))
    assert not bad, f"deliveryStartAt 無法解析: {bad}"
    assert all(isinstance(row.get("actresses"), list) for row in rec["rows"])
    statuses = Counter(row.get("releaseStatus") for row in rec["rows"])
    print(f"\n[recent canary] rows={len(rec['rows'])} kept={len(page.items)} releaseStatus={dict(statuses)}")
    assert set(statuses) & _KNOWN_RELEASE_STATUS, f"releaseStatus 分佈={dict(statuses)}"
