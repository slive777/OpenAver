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

Import note:
  standalone.py uses sibling import: from cf_transport_impl import PyWebViewCfTransport
  (windows/ has no __init__.py; WINDOWS_DIR is already in sys.path via standalone.py L22-24)
"""
from __future__ import annotations

import json
import queue
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    import webview

from bs4 import BeautifulSoup

from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import (
    _is_age_gate,
    _is_cf_challenge,
)
from core.logger import get_logger

logger = get_logger(__name__)


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

    def __init__(self, jl_window: webview.Window) -> None:
        self._win = jl_window
        self._dead = False
        self._cf_url = None  # 0.9.9g: the exact URL that triggered CF, so begin_solve shows the real challenge
        # Backstop: if the window is genuinely destroyed (crash / OS-forced / app
        # teardown) despite the closing-intercept in standalone.py, mark dead so
        # subsequent calls fail-fast instead of raising opaque errors on a dead window.
        try:
            self._win.events.closed += self._on_closed
        except Exception:
            logger.warning("cf_transport: could not bind events.closed (JL window)")
        logger.info("[CF-DIAG] PyWebViewCfTransport created (uid=%s)", getattr(jl_window, 'uid', '?'))

    def _on_closed(self) -> None:
        # [CF-DIAG] If this line ever appears in the log, edgechromium's `closed`
        # event DID fire (70c's Layer 2). If the window dies but this never logs,
        # Layer 2 is inert and the death only surfaces as a WebViewException /
        # TimeoutError on the next fetch (caught by the bridge-gate in fetch()/is_ready()).
        logger.info("[CF-DIAG] JL window 'closed' event fired → _dead=True (Layer 2 active)")
        self._dead = True

    # ------------------------------------------------------------------
    # Bridge-readiness helpers (0.9.9c root-cause work)
    # ------------------------------------------------------------------

    def _bridge_ready(self) -> bool:
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
            return bool(self._win.events._pywebviewready.is_set())
        except Exception:
            return True

    def _event_states(self) -> str:
        """Non-blocking snapshot of the window's pywebview lifecycle events (diag)."""
        def g(name: str):
            try:
                return getattr(self._win.events, name).is_set()
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
        """
        if self._dead:
            logger.info("[CF-DIAG] fetch → _dead=True, raising unavailable (url=%s)", url)
            raise CfTransportUnavailable("JavLibrary CF window was unexpectedly destroyed (crash / forced close); restart OpenAver to use JavLibrary again")

        logger.debug("[CF-DIAG] fetch start %s (url=%s)", self._event_states(), url)

        # Bridge gate (0.9.9c): if pywebview's JS bridge is not ready, evaluate_js
        # would block ~20s on _pywebviewready.wait(20) then raise WebViewException
        # (the stranded-bridge bug). A not-ready bridge means the window is on a
        # CF/loading page → route into the solve flow instead of blocking → 無結果.
        if not self._bridge_ready():
            logger.info("[CF-DIAG] fetch → bridge not ready (_pywebviewready unset) → route to solve (url=%s)", url)
            self._cf_url = url
            raise CfChallengeRequired(f'bridge not ready (CF likely) for {url}')

        # Set over18 cookie before fetching so the 18+ age gate is never served
        # (the gate is cookie-governed, not a human step). Mirrors is_ready().
        self._win.evaluate_js(
            "document.cookie='over18=18; path=/';"
        )

        t0 = time.monotonic()
        try:
            final_url, status, html = _wv_fetch(self._win, url)  # C1: unpack correctly
        except Exception as e:
            # [CF-DIAG] zero behavior change: surface the failure TYPE + elapsed so
            # the 40-min repro distinguishes dead-window (WebViewException, ~20s)
            # from silent death (TimeoutError, 12s×3). Re-raise unchanged.
            logger.info(
                "[CF-DIAG] fetch raised %s after %.1fs (url=%s)",
                type(e).__name__, time.monotonic() - t0, url,
            )
            raise

        # Detect CF challenge via title
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        title = title_tag.string if title_tag else ""
        title = title or ""

        if _is_cf_challenge(title, html):
            logger.info("[CF-DIAG] fetch → CF challenge detected (title=%r, url=%s)", (title or "")[:80], url)
            self._cf_url = url
            raise CfChallengeRequired(f'CF challenge detected for {url}')

        # Fallback: if the age gate still shows despite the cookie (race / unexpected
        # agreeBtn id), route into the solve/poll flow so begin_solve re-sets the
        # cookie (and the user can click if needed) — same recovery path as CF.
        if _is_age_gate(html):
            logger.info("[CF-DIAG] fetch → age gate persisted despite over18 cookie (url=%s)", url)
            raise CfChallengeRequired(f'age gate detected (cookie did not suppress) for {url}')

        logger.debug("[CF-DIAG] fetch ok (status=%s, len=%d, url=%s)", status, len(html), url)
        return html

    def begin_solve(self, origin_url: str, cache_key: str = 'javlibrary') -> None:
        """
        Non-blocking: show the window, navigate to the CF-challenged URL (or origin
        as fallback), so the user sees the actual Cloudflare Turnstile challenge
        immediately.  Returns immediately — does NOT wait for the user to solve.

        0.9.9g: navigates to self._cf_url (the exact URL that triggered CF) when
        available, rather than origin_url.  JavLibrary's homepage (/ja/) is NOT
        behind CF but the search endpoint (/ja/vl_searchbyid.php?...) is; using
        the remembered search URL ensures CF shows right away.
        """
        if self._dead:
            logger.info("[CF-DIAG] begin_solve → _dead=True, raising unavailable")
            raise CfTransportUnavailable("JavLibrary CF window was unexpectedly destroyed (crash / forced close); restart OpenAver to use JavLibrary again")
        target = self._cf_url or origin_url
        logger.info("[CF-DIAG] begin_solve → show + load_url (target=%s) %s", target, self._event_states())
        self._win.show()
        self._win.load_url(target)
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

        Sets over18 cookie on every call (idempotent, prevents age gate re-appear).
        When first ready, auto-hides the window.
        """
        if self._dead:
            logger.info("[CF-DIAG] is_ready → _dead=True, raising unavailable")
            raise CfTransportUnavailable("JavLibrary CF window was unexpectedly destroyed (crash / forced close); restart OpenAver to use JavLibrary again")

        # Bridge gate (0.9.9c): if pywebview's bridge is not ready the page is still
        # on CF / loading. evaluate_js would block ~20s and throw → report not-ready
        # without blocking.
        if not self._bridge_ready():
            logger.debug("[CF-DIAG] is_ready=False (bridge not ready) %s", self._event_states())
            return False

        # 1. Set over18 cookie every time (idempotent)
        self._win.evaluate_js(
            "document.cookie='over18=18; path=/';"
        )

        # 2. Read title (sync form: no callback → evaluate_js returns synchronously)
        title = self._win.evaluate_js("document.title") or ""

        # 3. Read head HTML (truncated to avoid serialising large pages)
        head = self._win.evaluate_js(
            "document.documentElement.outerHTML.slice(0, 4000)"
        ) or ""

        # 4. Evaluate readiness.
        # Positive "loaded-page" guard: real JavLibrary pages always have a
        #   non-empty <title>.  An empty title means the page is still
        #   navigating (evaluate_js returned None/""  before the DOM is ready),
        #   so we keep the window open and let the poll loop retry rather than
        #   misreporting ready and hiding the window prematurely.
        # CF challenge: never ready, user must wait for Turnstile.
        # Age-gate (agreeBtn): not ready, window stays visible so user can click
        #   the agree button. over18 cookie (step 1) prevents re-appearance in
        #   most cases; if the interstitial still shows, _is_age_gate (agreeBtn-
        #   only, narrow) catches it and keeps the window open. Normal content
        #   pages that contain "利用規約"/"18歳"/"over18" in the footer are NOT
        #   caught because the narrowed _is_age_gate only matches agreeBtn.
        cf = _is_cf_challenge(title, head)
        ag = _is_age_gate(head)
        ready = bool(title.strip()) and not cf and not ag

        # [CF-DIAG] The CF-loop detector. After the user solves the challenge, this
        # should flip to ready=True within a poll or two. If cf=True keeps logging
        # for minutes (the user already solved), that's the aged-session CF-loop
        # from premise-revision §A — distinct from a dead window (which raises
        # CfTransportUnavailable above instead of reaching here).
        _lvl = logger.info if (ready or cf) else logger.debug
        _lvl("[CF-DIAG] is_ready=%s (cf=%s, age_gate=%s, title=%r) %s", ready, cf, ag, (title or "")[:80], self._event_states())

        # 5. Auto-hide when first ready
        if ready:
            self._win.hide()

        return ready
