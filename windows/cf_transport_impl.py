# windows/cf_transport_impl.py
"""
PyWebView implementation of the CfTransport Protocol.

Provides:
  _wv_fetch(window, url, timeout, attempts, retry_delay)  — module-level helper (column 0)
  PyWebViewCfTransport             — CfTransport implementation

Design:
  - _wv_fetch uses queue.Queue(1) + evaluate_js(callback) bridge: non-blocking
    from the GUI thread's perspective.  Only the FastAPI threadpool worker
    blocks on result_q.get(timeout=...).
  - fetch() unpacks the tuple (C1 contract) and detects CF challenge.
  - begin_solve() is non-blocking: show → load_url only (no evaluate_js — CF page would block 20s; over18 set in fetch()/is_ready()).
  - is_ready() is a fast non-blocking check: reads title + head HTML slice.
  - No blocking wait loop (C2: POC wait_for_ready is NOT ported here).
  - TASK-118a-T1: multi-site support lives entirely inside this class (per-site
    dicts: self._wins / self._dead / self._cf_urls / self._origins).  The
    core/cf_transport.py Protocol registration model stays a single global
    transport object (CD-118a-2) — only this implementation is per-site aware.
    navigate_and_settle() is the one new primitive; its sole write point for
    self._origins is _navigate() (D-0), which every load_url() call in this
    class routes through (constructor seeding is the other write point).

Import note:
  standalone.py uses sibling import: from cf_transport_impl import PyWebViewCfTransport
  (windows/ has no __init__.py; WINDOWS_DIR is already in sys.path via standalone.py L22-24)
"""
from __future__ import annotations

import json
import queue
import time
from typing import Any, TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    import webview

from bs4 import BeautifulSoup

from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import (
    _is_age_gate,  # noqa: PLC2701 — core/scrapers/javlibrary.py 模組 docstring 已明文設計為 module-level、供 windows/cf_transport_impl.py 直接 import（"T4 的 windows/cf_transport_impl.py 可直接 from core.scrapers.javlibrary import"），是刻意設計的跨模組共用判斷式，非意外洩漏
    _is_cf_challenge,  # noqa: PLC2701 — 同上（core/scrapers/javlibrary.py:15 docstring 明文設計）：cf challenge 偵測與 age gate 偵測共用同一套 HTML 判斷邏輯，PyWebView transport 層需要重用而非重寫一份
)
from core.logger import get_logger

logger = get_logger(__name__)

# TASK-118a-T1 D-3: bounded wait for pywebview's JS bridge inside navigate_and_settle().
# Module-level constant so tests can monkeypatch it down to avoid a real 10s wait.
NAVIGATE_BRIDGE_TIMEOUT_S = 10.0

# TASK-118a-T1 D-4: per-site behaviour table. javlibrary's age gate (#adultwarningmask,
# agreeBtn) is JL-specific markup — applying it to fc-javten would misclassify javten
# pages that happen to share an element id and permanently loop CfChallengeRequired.
# Unknown keys are NOT in this table; callers must fail-closed (CfTransportUnavailable),
# never silently fall back to True/False here.
_SITE_AGE_GATE = {'javlibrary': True, 'fc-javten': False}


# ──────────────────────────────────────────────────────────────
# Module-level helper (column 0)
# ──────────────────────────────────────────────────────────────

def _wv_fetch(
    window: webview.Window,
    url: str,
    timeout: float = 12.0,
    attempts: int = 3,
    retry_delay: float = 0.5,
) -> tuple[str, int, str]:
    """
    Execute fetch(url) inside the WebView (same-origin, credentials:include)
    and return (final_url, http_status, html_text).

    Mechanism:
      evaluate_js(script, callback) is non-blocking + Promise-aware.
      We bridge via queue.Queue(1): the callback puts the result in,
      the worker thread blocking-gets with timeout.

    Retries up to `attempts` times if the callback is never called (hang),
    using a fresh queue + callback each attempt so stale callbacks from a
    hung earlier attempt land in their own abandoned queue and never
    contaminate a later attempt's result.

    Raises:
        TimeoutError:   all attempts timed out (callback never fired).
        RuntimeError:   JS-layer error (e.g. network failure) — not retried.
    """
    js_url = json.dumps(url)
    js_code = (
        f"(async()=>{{"
        f"  try {{"
        f"    const r = await fetch({js_url}, {{credentials:'include'}});"
        f"    const html = await r.text();"
        f"    return {{finalUrl: r.url, status: r.status, html: html}};"
        f"  }} catch(e) {{"
        f"    return {{finalUrl: {js_url}, status: 0, html: '', error: e.toString()}};"
        f"  }}"
        f"}})()"
    )

    last_timeout_err: TimeoutError | None = None

    for attempt in range(1, attempts + 1):
        # Fresh queue + fresh callback each attempt — stale callbacks from a
        # prior hung attempt will put into their own abandoned queue (harmless).
        result_q: queue.Queue[dict] = queue.Queue(maxsize=1)

        def _cb(result: Any, _q: queue.Queue = result_q) -> None:
            """pywebview Promise callback — called in pywebview's internal thread."""
            try:
                _q.put_nowait(result if isinstance(result, dict) else {})
            except queue.Full:
                pass  # guard against duplicate callbacks (extremely rare)

        window.evaluate_js(js_code, callback=_cb)

        try:
            data = result_q.get(timeout=timeout)
        except queue.Empty:
            last_timeout_err = TimeoutError(
                f"_wv_fetch timed out after {timeout}s for {url} (attempt {attempt}/{attempts})"
            )
            if attempt < attempts:
                logger.info(
                    "_wv_fetch: attempt %d/%d timed out for %s — retrying",
                    attempt, attempts, url,
                )
                if retry_delay > 0:
                    time.sleep(retry_delay)
            continue

        # Got data — check for JS/network error (not a hang; don't retry)
        final_url = data.get("finalUrl") or url
        status = data.get("status") or 0
        html = data.get("html") or ""

        if js_err := data.get("error"):
            raise RuntimeError(f"JS fetch error: {js_err}")

        if attempt > 1:
            logger.info(
                "_wv_fetch succeeded on attempt %d/%d for %s",
                attempt, attempts, url,
            )
        return final_url, status, html

    # All attempts exhausted
    logger.warning(
        "_wv_fetch exhausted %d attempts (%.0fs each) for %s",
        attempts, timeout, url,
    )
    raise last_timeout_err  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────
# Transport implementation
# ──────────────────────────────────────────────────────────────

class PyWebViewCfTransport:
    """
    CfTransport implementation backed by a dedicated hidden PyWebView window.

    The window stays hidden at rest.  begin_solve() shows it so the user can
    complete the CF challenge + age gate.  is_ready() polls state without
    blocking; when ready it auto-hides the window.
    """

    def __init__(
        self,
        windows: dict[str, webview.Window],
        initial_urls: dict[str, str] | None = None,
    ) -> None:
        # TASK-118a-T1 D-1: per-site dicts. Constructor shape is fixed — no
        # single-window / dict polymorphism (that convenience is the next
        # person's bug).
        self._wins: dict[str, webview.Window] = dict(windows)
        self._dead: dict[str, bool] = {key: False for key in self._wins}
        self._cf_urls: dict[str, str | None] = {key: None for key in self._wins}
        # D-0: _origins is seeded here from initial_urls (reflecting where each
        # window already is at construction time) AND written by _navigate()
        # (the only other write point) — never anywhere else.
        self._origins: dict[str, str | None] = {key: None for key in self._wins}
        for key, url in (initial_urls or {}).items():
            if key in self._origins:
                self._origins[key] = self._origin(url)

        # Backstop: if a window is genuinely destroyed (crash / OS-forced / app
        # teardown) despite the closing-intercept in standalone.py, mark that
        # site dead so subsequent calls fail-fast instead of raising opaque
        # errors on a dead window. Bound per-key so one dead window does not
        # affect other sites.
        for key, win in self._wins.items():
            try:
                win.events.closed += self._make_on_closed(key)
            except Exception:
                logger.warning("cf_transport: could not bind events.closed (site=%s)", key)
            logger.info(
                "[CF-DIAG] PyWebViewCfTransport window registered (site=%s, uid=%s)",
                key, getattr(win, 'uid', '?'),
            )

    @staticmethod
    def _origin(url: str) -> str:
        """scheme://netloc of *url* — pure string comparison, never asks the page.

        Case-folded: scheme and host are case-insensitive per RFC 3986, so a
        redirect that comes back with an upper-case host must NOT read as a
        different origin (that would cost one spurious re-navigate + CF popup).
        """
        parts = urlsplit(url)
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}"

    def _record_origin(self, key: str, url: str) -> None:
        """SOLE writer of self._origins after construction (D-0).

        Two callers, because two different moments genuinely know where the
        window is: _navigate() knows where we *told* it to go, and
        navigate_and_settle() knows where it *actually landed* once the bridge
        reports ready.  Recording only the former is a bug: the javten search
        step is a redirect chain we do not control (it even drops to http://
        mid-flight before upgrading back), so if it ever settles on a different
        host than the one we requested, the origin gate in fetch() would miss on
        the very next call and pop the CF window on every single query — the
        exact symptom CD-118a-18 exists to prevent.
        """
        self._origins[key] = self._origin(url)

    def _require_window(self, key: str) -> webview.Window:
        """Fail-closed for unknown site keys (D-4): CfTransportUnavailable, never KeyError."""
        try:
            return self._wins[key]
        except KeyError:
            raise CfTransportUnavailable(f"CF transport window for site '{key}' is not available") from None

    def _navigate(self, key: str, url: str) -> None:
        """The ONLY function that calls load_url() in this class (D-0).

        Every navigation — begin_solve()'s show+navigate, fetch()'s
        gate-miss branch, and navigate_and_settle() — routes through here so
        self._origins[key] has a single source of truth: it always reflects
        the last URL this window was actually told to load.
        """
        self._wins[key].load_url(url)
        self._record_origin(key, url)

    def _make_on_closed(self, key: str):
        def _on_closed() -> None:
            # [CF-DIAG] If this line ever appears in the log, edgechromium's `closed`
            # event DID fire (70c's Layer 2). If the window dies but this never logs,
            # Layer 2 is inert and the death only surfaces as a WebViewException /
            # TimeoutError on the next fetch (caught by the bridge-gate in fetch()/is_ready()).
            logger.info("[CF-DIAG] window 'closed' event fired (site=%s) → _dead=True (Layer 2 active)", key)
            self._dead[key] = True
        return _on_closed

    # ------------------------------------------------------------------
    # Bridge-readiness helpers (0.9.9c root-cause work)
    # ------------------------------------------------------------------

    def _bridge_ready(self, key: str) -> bool:
        """True if pywebview's JS bridge is ready so evaluate_js won't block.

        evaluate_js is decorated `@_pywebview_ready_call` → `_pywebviewready.wait(20)`
        (pywebview window.py). load_url() CLEARS `_pywebviewready` (window.py:285),
        and a CF-challenge page does not re-fire it within 20s → evaluate_js blocks
        ~20s then raises WebViewException, stranding the bridge (the 0.9.9b repro).
        Reading the Event non-blocking lets us avoid that block entirely.

        On platforms/tests without the event (older pywebview / FakeWindow) default
        True to preserve behavior.
        """
        try:
            return bool(self._wins[key].events._pywebviewready.is_set())
        except Exception:
            return True

    def _wait_bridge_ready(self, key: str, timeout: float) -> bool:
        """Blocking (bounded) wait for the bridge-ready Event itself — NOT evaluate_js.

        Used only by navigate_and_settle() (D-3): after load_url(), the bridge
        clears, and for fc-javten we must navigate on every query (the internal
        id can't be avoided) so we can't reuse fetch()'s "not ready → raise
        immediately" gate without popping the CF window on every single query.
        Waiting on the Event directly does not touch evaluate_js at all, so it
        cannot strand the bridge the way 0.9.9c did.
        """
        try:
            return bool(self._wins[key].events._pywebviewready.wait(timeout))
        except Exception:
            return True

    def _event_states(self, key: str) -> str:
        """Non-blocking snapshot of the window's pywebview lifecycle events (diag)."""
        def g(name: str):
            try:
                return getattr(self._wins[key].events, name).is_set()
            except Exception:
                return '?'
        return f"[ready={g('_pywebviewready')} shown={g('shown')} loaded={g('loaded')}]"

    # ------------------------------------------------------------------
    # CfTransport Protocol
    # ------------------------------------------------------------------

    def fetch(self, url: str, cache_key: str = 'javlibrary') -> str:
        """
        Fetch url via same-origin WebView request and return HTML string.

        Raises CfChallengeRequired if the returned page is a CF challenge or a
        persisting age gate (agreeBtn detected despite the proactive over18 cookie).

        The over18 cookie is set proactively before every fetch so the 18+ age gate
        is never served on cold-start (cookie-governed, not a human step).  Mirrors
        the idiom in is_ready().  If the gate somehow persists (race / unexpected
        markup), the fallback _is_age_gate check routes into the solve/poll flow
        exactly like a CF challenge.

        cache_key selects the per-site window (D-4 per-site table decides
        whether the age gate applies).  Unknown keys fail closed with
        CfTransportUnavailable.
        """
        key = cache_key
        win = self._require_window(key)

        if self._dead.get(key, False):
            logger.info("[CF-DIAG] fetch → _dead[%s]=True, raising unavailable (url=%s)", key, url)
            raise CfTransportUnavailable(
                f"CF window for site '{key}' was unexpectedly destroyed (crash / forced close); "
                "restart OpenAver to use this source again"
            )

        logger.debug("[CF-DIAG] fetch start %s (site=%s, url=%s)", self._event_states(key), key, url)

        # INV-1 (CD-118a-3): pure string-level origin gate, checked BEFORE the bridge
        # gate — it never asks the page anything. If this window isn't currently on
        # the same origin as `url` (including "never navigated" → _origins[key] is
        # None), _wv_fetch must NOT be sent this call: navigate there instead and
        # route into the solve/poll flow, exactly like a CF challenge.
        if self._origins.get(key) != self._origin(url):
            logger.info(
                "[CF-DIAG] fetch → origin mismatch (site=%s, have=%r, want=%r) → navigate + route to solve (url=%s)",
                key, self._origins.get(key), self._origin(url), url,
            )
            self._navigate(key, url)
            self._cf_urls[key] = url
            raise CfChallengeRequired(f'origin mismatch for {url} (site={key})')

        # Bridge gate (0.9.9c): if pywebview's JS bridge is not ready, evaluate_js
        # would block ~20s on _pywebviewready.wait(20) then raise WebViewException
        # (the stranded-bridge bug). A not-ready bridge means the window is on a
        # CF/loading page → route into the solve flow instead of blocking → 無結果.
        if not self._bridge_ready(key):
            logger.info("[CF-DIAG] fetch → bridge not ready (_pywebviewready unset) → route to solve (site=%s, url=%s)", key, url)
            self._cf_urls[key] = url
            raise CfChallengeRequired(f'bridge not ready (CF likely) for {url}')

        # Set over18 cookie before fetching so the 18+ age gate is never served
        # (the gate is cookie-governed, not a human step). Mirrors is_ready().
        # CD-118a-5: JavLibrary-only — fc-javten has no age gate, and applying
        # this cookie/detector there is pure risk (false positives on unrelated
        # markup), not a safety net.
        if _SITE_AGE_GATE.get(key, False):
            win.evaluate_js(
                "document.cookie='over18=18; path=/';"
            )

        t0 = time.monotonic()
        try:
            final_url, status, html = _wv_fetch(win, url)  # C1: unpack correctly
        except Exception as e:
            # [CF-DIAG] zero behavior change: surface the failure TYPE + elapsed so
            # the 40-min repro distinguishes dead-window (WebViewException, ~20s)
            # from silent death (TimeoutError, 12s×3). Re-raise unchanged.
            logger.info(
                "[CF-DIAG] fetch raised %s after %.1fs (site=%s, url=%s)",
                type(e).__name__, time.monotonic() - t0, key, url,
            )
            raise

        # Detect CF challenge via title
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        title = title_tag.string if title_tag else ""
        title = title or ""

        if _is_cf_challenge(title, html):
            logger.info("[CF-DIAG] fetch → CF challenge detected (site=%s, title=%r, url=%s)", key, (title or "")[:80], url)
            self._cf_urls[key] = url
            raise CfChallengeRequired(f'CF challenge detected for {url}')

        # Fallback: if the age gate still shows despite the cookie (race / unexpected
        # agreeBtn id), route into the solve/poll flow so begin_solve re-sets the
        # cookie (and the user can click if needed) — same recovery path as CF.
        # JavLibrary-only (D-4); fc-javten never runs this check.
        if _SITE_AGE_GATE.get(key, False) and _is_age_gate(html):
            logger.info("[CF-DIAG] fetch → age gate persisted despite over18 cookie (site=%s, url=%s)", key, url)
            raise CfChallengeRequired(f'age gate detected (cookie did not suppress) for {url}')

        logger.debug("[CF-DIAG] fetch ok (site=%s, status=%s, len=%d, url=%s)", key, status, len(html), url)
        return html

    def begin_solve(self, origin_url: str, cache_key: str = 'javlibrary') -> None:
        """
        Non-blocking: show the window, navigate to the CF-challenged URL (or origin
        as fallback), so the user sees the actual Cloudflare Turnstile challenge
        immediately.  Returns immediately — does NOT wait for the user to solve.

        0.9.9g: navigates to self._cf_urls[key] (the exact URL that triggered CF)
        when available, rather than origin_url.  JavLibrary's homepage (/ja/) is
        NOT behind CF but the search endpoint (/ja/vl_searchbyid.php?...) is; using
        the remembered search URL ensures CF shows right away.
        """
        key = cache_key
        win = self._require_window(key)

        if self._dead.get(key, False):
            logger.info("[CF-DIAG] begin_solve → _dead[%s]=True, raising unavailable", key)
            raise CfTransportUnavailable(
                f"CF window for site '{key}' was unexpectedly destroyed (crash / forced close); "
                "restart OpenAver to use this source again"
            )
        target = self._cf_urls.get(key) or origin_url
        logger.info("[CF-DIAG] begin_solve → show + load_url (site=%s, target=%s) %s", key, target, self._event_states(key))
        win.show()
        self._navigate(key, target)
        # ROOT-CAUSE FIX (0.9.9c): deliberately NO evaluate_js here. Setting the
        # over18 cookie via evaluate_js right after navigating to a (CF-challenged)
        # origin blocks ~20s on _pywebviewready.wait(20) and raises WebViewException,
        # which strands the bridge so EVERY later fetch/is_ready also throws (the
        # 0.9.9b "permanent break, must restart" repro). The over18 cookie is set in
        # fetch() and is_ready() once the page is actually ready. begin_solve stays
        # purely show + navigate (both non-blocking @_shown_call; `shown` stays set).

    def is_ready(self, cache_key: str = 'javlibrary') -> bool:
        """
        Non-blocking fast check: has the user passed the CF challenge?

        Only checks for CF challenge (title / hidden field markers).
        The 18+ age gate (#adultwarningmask) is a CLIENT-SIDE overlay present in
        every page's HTML and hidden by the site's own JS when the over18 cookie
        equals 18 (the value the site's 同意する button writes — CDP-verified; our
        earlier over18=1 did not satisfy that check, so the mask kept showing). It
        never blocks the fetched HTML/parse — content is always present behind it —
        so we set over18=18 purely so the visible solve window doesn't show the mask.
        JavLibrary-only (D-4/CD-118a-5); fc-javten has no age gate.

        Sets over18 cookie on every call (idempotent, prevents age gate re-appear)
        for sites that have one.  When first ready, auto-hides the window.

        cache_key selects the per-site window — only that site's window is
        touched; only that site's window is hidden when ready.
        """
        key = cache_key
        win = self._require_window(key)

        if self._dead.get(key, False):
            logger.info("[CF-DIAG] is_ready → _dead[%s]=True, raising unavailable", key)
            raise CfTransportUnavailable(
                f"CF window for site '{key}' was unexpectedly destroyed (crash / forced close); "
                "restart OpenAver to use this source again"
            )

        # Bridge gate (0.9.9c): if pywebview's bridge is not ready the page is still
        # on CF / loading. evaluate_js would block ~20s and throw → report not-ready
        # without blocking.
        if not self._bridge_ready(key):
            logger.debug("[CF-DIAG] is_ready=False (bridge not ready, site=%s) %s", key, self._event_states(key))
            return False

        site_has_age_gate = _SITE_AGE_GATE.get(key, False)

        # 1. Set over18 cookie every time (idempotent) — JavLibrary-only.
        if site_has_age_gate:
            win.evaluate_js(
                "document.cookie='over18=18; path=/';"
            )

        # 2. Read title (sync form: no callback → evaluate_js returns synchronously)
        title = win.evaluate_js("document.title") or ""

        # 3. Read head HTML (truncated to avoid serialising large pages)
        head = win.evaluate_js(
            "document.documentElement.outerHTML.slice(0, 4000)"
        ) or ""

        # 4. Evaluate readiness.
        # Positive "loaded-page" guard: real pages always have a non-empty
        #   <title>.  An empty title means the page is still navigating
        #   (evaluate_js returned None/"" before the DOM is ready), so we keep
        #   the window open and let the poll loop retry rather than
        #   misreporting ready and hiding the window prematurely.
        # CF challenge: never ready, user must wait for Turnstile. Shared
        #   across sites (_is_cf_challenge, CD-118a-5).
        # Age-gate (agreeBtn): JavLibrary-only. not ready, window stays visible
        #   so user can click the agree button. over18 cookie (step 1) prevents
        #   re-appearance in most cases; if the interstitial still shows,
        #   _is_age_gate (agreeBtn-only, narrow) catches it and keeps the
        #   window open. Normal content pages that contain "利用規約"/"18歳"/
        #   "over18" in the footer are NOT caught because the narrowed
        #   _is_age_gate only matches agreeBtn.
        cf = _is_cf_challenge(title, head)
        ag = _is_age_gate(head) if site_has_age_gate else False
        ready = bool(title.strip()) and not cf and not ag

        # [CF-DIAG] The CF-loop detector. After the user solves the challenge, this
        # should flip to ready=True within a poll or two. If cf=True keeps logging
        # for minutes (the user already solved), that's the aged-session CF-loop
        # from premise-revision §A — distinct from a dead window (which raises
        # CfTransportUnavailable above instead of reaching here).
        _lvl = logger.info if (ready or cf) else logger.debug
        _lvl("[CF-DIAG] is_ready=%s (site=%s, cf=%s, age_gate=%s, title=%r) %s", ready, key, cf, ag, (title or "")[:80], self._event_states(key))

        # 5. Auto-hide when first ready — only this site's window.
        if ready:
            win.hide()

        return ready

    def navigate_and_settle(self, url: str, cache_key: str) -> str:
        """
        TASK-118a-T1 / CD-118a-18: navigate this site's window to *url*, wait
        (bounded) for pywebview's bridge to become ready, then return the
        settled final URL — WITHOUT ever calling evaluate_js before the
        bridge is ready.

        Exists because fc-javten's search step can't use fetch(): the
        redirect chain Mixed-Content-blocks mid-flight, and the internal id
        it resolves to is required (every other value 404s), so this
        navigation cannot be skipped even though it clears the bridge event
        on every single query.

        Three outcomes:
          1. Bridge ready, page is NOT a CF challenge → return the final URL
             (get_current_url(), NOT evaluate_js — D-2: doesn't touch the JS
             bridge at all, and keeps evaluate_js usage limited to exactly
             the title/head reads below).
          2. Bridge ready, page IS a CF challenge → record self._cf_urls[key]
             and raise CfChallengeRequired (do NOT return the URL).
          3. Bridge never becomes ready within NAVIGATE_BRIDGE_TIMEOUT_S →
             raise CfChallengeRequired.

        over18 cookie / _is_age_gate are NOT applied here (CD-118a-5): those
        are javlibrary-only, and navigate_and_settle is fc-javten-only in
        practice (javlibrary never calls it — its window parks on its origin
        at startup and only ever uses fetch()).
        """
        key = cache_key
        win = self._require_window(key)

        if self._dead.get(key, False):
            logger.info("[CF-DIAG] navigate_and_settle → _dead[%s]=True, raising unavailable", key)
            raise CfTransportUnavailable(
                f"CF window for site '{key}' was unexpectedly destroyed (crash / forced close); "
                "restart OpenAver to use this source again"
            )

        logger.info("[CF-DIAG] navigate_and_settle → load_url (site=%s, url=%s)", key, url)
        self._navigate(key, url)

        # D-3: wait on the bridge-ready Event itself (bounded) — never evaluate_js
        # before this returns True.
        if not self._wait_bridge_ready(key, NAVIGATE_BRIDGE_TIMEOUT_S):
            logger.info(
                "[CF-DIAG] navigate_and_settle → bridge never became ready within %.1fs (site=%s, url=%s)",
                NAVIGATE_BRIDGE_TIMEOUT_S, key, url,
            )
            self._cf_urls[key] = url
            raise CfChallengeRequired(f'navigate_and_settle: bridge not ready within {NAVIGATE_BRIDGE_TIMEOUT_S}s for {url} (site={key})')

        final_url = win.get_current_url() or url
        # D-0 (T1 review): the window is now settled on final_url, which a
        # redirect may have moved to a different origin than the one we asked
        # for. Re-record so fetch()'s origin gate compares against reality —
        # otherwise the very next fetch() misses the gate and pops the CF
        # window even though Cloudflare never challenged anything.
        self._record_origin(key, final_url)

        # Bridge is ready now — safe to evaluate_js, limited to the same
        # title/head challenge-detection reads as is_ready() (no over18 cookie,
        # no _is_age_gate: those are javlibrary-only per CD-118a-5).
        title = win.evaluate_js("document.title") or ""
        head = win.evaluate_js("document.documentElement.outerHTML.slice(0, 4000)") or ""

        if _is_cf_challenge(title, head):
            logger.info(
                "[CF-DIAG] navigate_and_settle → CF challenge detected (site=%s, title=%r, url=%s)",
                key, (title or "")[:80], final_url,
            )
            self._cf_urls[key] = final_url
            raise CfChallengeRequired(f'navigate_and_settle: CF challenge detected for {url} (site={key})')

        logger.debug("[CF-DIAG] navigate_and_settle ok (site=%s, final_url=%s)", key, final_url)
        return final_url
