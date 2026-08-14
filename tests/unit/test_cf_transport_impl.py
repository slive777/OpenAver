# tests/unit/test_cf_transport_impl.py
"""
TDD-lite tests for windows/cf_transport_impl.py

Import strategy: sys.path.insert + sibling import (matches standalone.py runtime)
Structural guards: grep assertions for core→windows and launcher purity.
"""
import subprocess
import sys
import pathlib
import queue
import threading
import time

import pytest

# ──────────────────────────────────────────────────────────────
# sys.path setup — mirrors standalone.py L22-24
# ──────────────────────────────────────────────────────────────
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
WINDOWS_DIR = str(REPO_ROOT / 'windows')
if WINDOWS_DIR not in sys.path:
    sys.path.insert(0, WINDOWS_DIR)

import cf_transport_impl  # sibling import, same as standalone.py runtime
from cf_transport_impl import PyWebViewCfTransport, _wv_fetch
from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN

# TASK-118a-T1 D-1: fixed constructor shape is dict[str, Window] + optional
# initial_urls seed. All 25 pre-existing single-window `PyWebViewCfTransport(win)`
# construction points become a one-line mechanical rewrite to `_jl_transport(win)`,
# with every assertion left unchanged.
JL_ORIGIN = JAVLIBRARY_ORIGIN


def _jl_transport(win):
    return PyWebViewCfTransport({'javlibrary': win}, {'javlibrary': JL_ORIGIN})


# ──────────────────────────────────────────────────────────────
# FakeWindow
# ──────────────────────────────────────────────────────────────
class FakeEvents:
    """
    Minimal stub for pywebview's EventContainer that supports `+=` handler registration.
    Registered handlers can be fired by calling fire().
    """

    def __init__(self):
        self._handlers: list = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self

    def fire(self):
        for h in self._handlers:
            h()


class FakeEvent:
    """Stub for a threading.Event-like pywebview lifecycle event.

    Defaults to set=True so `_bridge_ready()` reports ready and existing tests
    keep their pre-0.9.9c behavior. Tests that exercise the bridge-not-ready
    path can flip it via .clear()/.set()."""

    def __init__(self, initial: bool = True):
        self._set = initial
        self.wait_calls = 0

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self._set


class FakeWindowEvents:
    """Stub for window.events, with `closed`/`closing` + lifecycle events."""

    def __init__(self):
        self.closed = FakeEvents()
        self.closing = FakeEvents()
        # 0.9.9c/e: bridge-readiness events. Default set=True → bridge ready.
        self._pywebviewready = FakeEvent(initial=True)
        self.shown = FakeEvent(initial=True)
        self.loaded = FakeEvent(initial=True)


class FakeWindow:
    """
    Mock for webview.Window.

    evaluate_js behaviour:
      - With callback: call callback(self._eval_callback_result['default'])
        unless self._never_callback is True (for TimeoutError tests).
      - Without callback: return self._eval_results.get(code[:20], None).

    Records all method calls in self.calls as (method, *args).
    """

    def __init__(self):
        self.calls: list[tuple] = []
        # Sync return values, keyed by first 20 chars of JS code
        self._eval_results: dict = {}
        # Dict result passed to callback; default = clean fetch result
        self._eval_callback_result: dict = {
            'default': {'finalUrl': 'https://www.javlibrary.com/ja/', 'status': 200, 'html': '<html><title>JavLibrary</title></html>'}
        }
        # Set True to make evaluate_js never call the callback (→ TimeoutError)
        self._never_callback: bool = False
        # events stub for CD-70c-2 __init__ binding
        self.events = FakeWindowEvents()
        # D-2: get_current_url() is the source of navigate_and_settle()'s return
        # value. Defaults to tracking the last load_url() target (realistic
        # same-URL case); tests exercising an actual redirect can override
        # self._current_url after triggering navigation.
        self._current_url = None

    def show(self):
        self.calls.append(('show',))

    def hide(self):
        self.calls.append(('hide',))

    def load_url(self, url):
        self.calls.append(('load_url', url))
        self._current_url = url

    def get_current_url(self):
        self.calls.append(('get_current_url',))
        return self._current_url

    def evaluate_js(self, code, callback=None):
        self.calls.append(('evaluate_js', code, callback))
        if callback is not None:
            if not self._never_callback:
                result = self._eval_callback_result.get('default', {})
                callback(result)
            return None
        else:
            # Sync return (is_ready path)
            return self._eval_results.get(code[:20], None)


# ──────────────────────────────────────────────────────────────
# Tests: _wv_fetch
# ──────────────────────────────────────────────────────────────

class TestWvFetch:
    def test_normal_returns_tuple(self):
        """Normal callback → returns (final_url, status, html) tuple."""
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': '<html>ok</html>',
        }
        result = _wv_fetch(win, 'https://www.javlibrary.com/ja/')
        assert isinstance(result, tuple)
        assert len(result) == 3
        final_url, status, html = result
        assert final_url == 'https://www.javlibrary.com/ja/'
        assert status == 200
        assert html == '<html>ok</html>'

    def test_js_error_raises_runtime_error(self):
        """Callback with error key → raises RuntimeError."""
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 0,
            'html': '',
            'error': 'net::ERR_FAILED',
        }
        with pytest.raises(RuntimeError, match='JS fetch error'):
            _wv_fetch(win, 'https://www.javlibrary.com/ja/')

    def test_timeout_raises_timeout_error(self):
        """Callback never called → raises TimeoutError (single-attempt, fast)."""
        win = FakeWindow()
        win._never_callback = True
        with pytest.raises(TimeoutError):
            _wv_fetch(win, 'https://www.javlibrary.com/ja/', timeout=0.05, attempts=1)
        # Exactly 1 evaluate_js call for single-attempt
        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert len(eval_calls) == 1

    def test_non_dict_callback_degrades_gracefully(self):
        """Non-dict passed to callback → put_nowait({}) → returns ('', 0, '')."""
        win = FakeWindow()

        # Override evaluate_js to pass a non-dict to callback
        original_evaluate_js = win.evaluate_js
        def patched_evaluate_js(code, callback=None):
            win.calls.append(('evaluate_js', code, callback))
            if callback is not None:
                callback("not-a-dict")
            return None
        win.evaluate_js = patched_evaluate_js

        result = _wv_fetch(win, 'https://www.javlibrary.com/ja/')
        assert isinstance(result, tuple)
        final_url, status, html = result
        assert final_url == 'https://www.javlibrary.com/ja/'  # falls back to input url
        assert status == 0
        assert html == ''

    def test_retry_then_succeed(self):
        """
        1st attempt: callback never fires → timeout.
        2nd attempt: callback fires with valid result → returns correct tuple.
        Asserts recovery on attempt 2 with no actual wait.
        """
        call_count = [0]
        captured_callbacks: list = []
        GOOD_RESULT = {
            'finalUrl': 'https://www.javlibrary.com/ja/vl_movie.php?v=START492',
            'status': 200,
            'html': '<html><title>START-492</title></html>',
        }

        class RetryFakeWindow(FakeWindow):
            def evaluate_js(self, code, callback=None):
                self.calls.append(('evaluate_js', code, callback))
                call_count[0] += 1
                if callback is not None:
                    if call_count[0] == 1:
                        # 1st attempt: do nothing → timeout
                        captured_callbacks.append(callback)
                    else:
                        # 2nd attempt onwards: call callback with good result
                        callback(GOOD_RESULT)
                return None

        win = RetryFakeWindow()
        result = _wv_fetch(win, 'https://www.javlibrary.com/ja/', timeout=0.05, attempts=3, retry_delay=0)

        assert isinstance(result, tuple)
        final_url, status, html = result
        assert final_url == GOOD_RESULT['finalUrl']
        assert status == 200
        assert html == GOOD_RESULT['html']
        # evaluate_js called exactly twice: 1 timed-out + 1 successful
        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert len(eval_calls) == 2, f"Expected 2 evaluate_js calls, got {len(eval_calls)}"

    def test_all_attempts_exhausted_raises_timeout(self):
        """
        evaluate_js never calls callback → all 3 attempts time out →
        TimeoutError raised, evaluate_js called exactly `attempts` times.
        """
        win = FakeWindow()
        win._never_callback = True
        with pytest.raises(TimeoutError):
            _wv_fetch(win, 'https://www.javlibrary.com/ja/', timeout=0.05, attempts=3, retry_delay=0)
        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert len(eval_calls) == 3, (
            f"Expected 3 evaluate_js calls (one per attempt), got {len(eval_calls)}"
        )

    def test_stale_callback_isolation(self):
        """
        Stale-callback isolation: the 1st attempt's callback fires LATE (injected
        at the start of the 2nd evaluate_js call, into the 1st attempt's queue).
        The 2nd attempt supplies its OWN correct result.
        Assert that the returned html belongs to attempt 2, not the stale result.

        Implementation note: each attempt captures its OWN `result_q` via the
        default-argument closure `_q=result_q`.  The stale callback fires into
        the 1st (abandoned) queue; the 2nd attempt's queue receives the fresh
        result.  This verifies the per-attempt queue isolation design.
        """
        STALE_RESULT = {
            'finalUrl': 'https://www.javlibrary.com/ja/stale',
            'status': 200,
            'html': '<html><title>STALE</title></html>',
        }
        FRESH_RESULT = {
            'finalUrl': 'https://www.javlibrary.com/ja/fresh',
            'status': 200,
            'html': '<html><title>FRESH</title></html>',
        }

        stale_cb_holder: list = []
        call_count = [0]

        class StaleCallbackWindow(FakeWindow):
            def evaluate_js(self, code, callback=None):
                self.calls.append(('evaluate_js', code, callback))
                call_count[0] += 1
                if callback is not None:
                    if call_count[0] == 1:
                        # 1st attempt: store callback, never invoke → timeout
                        stale_cb_holder.append(callback)
                    elif call_count[0] == 2:
                        # 2nd attempt: first fire the stale 1st-attempt callback
                        # (simulates late arrival after the retry started)
                        if stale_cb_holder:
                            stale_cb_holder[0](STALE_RESULT)
                        # Then fire THIS attempt's fresh callback
                        callback(FRESH_RESULT)
                return None

        win = StaleCallbackWindow()
        result = _wv_fetch(win, 'https://www.javlibrary.com/ja/', timeout=0.05, attempts=3, retry_delay=0)

        final_url, status, html = result
        assert html == FRESH_RESULT['html'], (
            f"Expected fresh result html, got: {html!r} (stale callback must not contaminate)"
        )
        assert final_url == FRESH_RESULT['finalUrl']


# ──────────────────────────────────────────────────────────────
# Tests: fetch()
# ──────────────────────────────────────────────────────────────

NORMAL_HTML = '<html><head><title>JavLibrary</title></head><body>content</body></html>'
CF_HTML = '<html><head><title>Just a moment...</title></head><body>cf stuff</body></html>'


class TestFetch:
    def test_normal_html_returns_str_not_tuple(self):
        """Normal page → returns str (C1: _wv_fetch unpacked correctly)."""
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': NORMAL_HTML,
        }
        transport = _jl_transport(win)
        result = transport.fetch('https://www.javlibrary.com/ja/')
        assert isinstance(result, str), "fetch() must return str, not tuple (C1 check)"
        assert result == NORMAL_HTML

    def test_cf_challenge_title_raises(self):
        """CF challenge title → raises CfChallengeRequired."""
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': CF_HTML,
        }
        transport = _jl_transport(win)
        with pytest.raises(CfChallengeRequired):
            transport.fetch('https://www.javlibrary.com/ja/')

    def test_timeout_bubbles_through_fetch(self, monkeypatch):
        """_wv_fetch TimeoutError bubbles out of fetch() unmodified."""
        def fake_wv_fetch(window, url, timeout=12.0, attempts=3, retry_delay=0.5):
            raise TimeoutError(f"_wv_fetch timed out after {timeout}s for {url}")

        monkeypatch.setattr(cf_transport_impl, '_wv_fetch', fake_wv_fetch)
        win = FakeWindow()
        transport = _jl_transport(win)
        with pytest.raises(TimeoutError):
            transport.fetch('https://www.javlibrary.com/ja/')

    def test_fetch_does_not_raise_for_footer_terms_page(self):
        """
        Normal content page with footer terms (利用規約/over18 but NO agreeBtn)
        → fetch() returns html without raising.  _is_age_gate only matches agreeBtn,
        so footer-only content is never mis-classified as an age gate.
        """
        age_gate_html = '<html><head><title>JavLibrary</title></head><body>利用規約 over18</body></html>'
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': age_gate_html,
        }
        transport = _jl_transport(win)
        # Should NOT raise — footer terms do not trigger _is_age_gate (no agreeBtn)
        result = transport.fetch('https://www.javlibrary.com/ja/')
        assert isinstance(result, str)

    def test_age_gate_html_raises_cf_challenge_required(self):
        """
        Fallback path: if agreeBtn is present in the fetched HTML (age gate persisted
        despite the proactive over18 cookie), fetch() raises CfChallengeRequired so
        the caller routes into the solve/poll flow instead of returning empty content.
        """
        age_gate_html = (
            '<html><head><title>JavLibrary</title></head>'
            '<body><button id="agreeBtn">同意</button></body></html>'
        )
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': age_gate_html,
        }
        transport = _jl_transport(win)
        with pytest.raises(CfChallengeRequired, match='age gate detected'):
            transport.fetch('https://www.javlibrary.com/ja/')

    def test_fetch_sets_over18_cookie_before_fetch(self):
        """
        Proactive cookie path: fetch() calls evaluate_js with the over18=18 cookie
        string BEFORE calling _wv_fetch.  FakeWindow records all evaluate_js codes;
        the cookie call must appear before the callback-bearing _wv_fetch call.
        """
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': NORMAL_HTML,
        }
        transport = _jl_transport(win)
        transport.fetch('https://www.javlibrary.com/ja/')

        # Collect all evaluate_js call codes
        eval_calls = [(i, c) for i, c in enumerate(win.calls) if c[0] == 'evaluate_js']

        # There must be at least 2: one cookie (no callback) + one _wv_fetch (callback)
        assert len(eval_calls) >= 2, (
            f"Expected at least 2 evaluate_js calls (cookie + fetch), got {len(eval_calls)}"
        )

        # The first evaluate_js must contain 'over18' and have no callback
        first_idx, first_call = eval_calls[0]
        assert 'over18' in first_call[1], (
            f"First evaluate_js must set over18 cookie, got: {first_call[1]!r}"
        )
        assert first_call[2] is None, (
            "Cookie evaluate_js must be a no-callback (sync) call"
        )

        # The second evaluate_js must be the _wv_fetch call (has a callback)
        _, fetch_call = eval_calls[1]
        assert fetch_call[2] is not None, (
            "Second evaluate_js must be the _wv_fetch call (has callback)"
        )

    def test_fetch_bridge_not_ready_raises_cf_no_side_effects(self, monkeypatch):
        """
        Bridge gate (0.9.9c): when _pywebviewready is unset (bridge not ready),
        fetch() must:
          - raise CfChallengeRequired immediately
          - NOT call _wv_fetch (no JS fetch attempted on broken bridge)
          - NOT call evaluate_js (over18 cookie NOT set — bridge gate fires first)
          - record _cf_url = url (so begin_solve can navigate to the right page)
        """
        wv_fetch_calls = []

        def spy_wv_fetch(window, url, **kwargs):
            wv_fetch_calls.append(url)
            return (url, 200, NORMAL_HTML)

        monkeypatch.setattr(cf_transport_impl, '_wv_fetch', spy_wv_fetch)

        win = FakeWindow()
        # Bridge not ready: clear the _pywebviewready event
        win.events._pywebviewready.clear()
        transport = _jl_transport(win)

        url = 'https://www.javlibrary.com/ja/vl_searchbyid.php?keyword=START-578'
        with pytest.raises(CfChallengeRequired):
            transport.fetch(url)

        # _wv_fetch must NOT have been called (bridge gate fires before it)
        assert wv_fetch_calls == [], (
            f"_wv_fetch must not be called when bridge is not ready; got calls: {wv_fetch_calls}"
        )

        # evaluate_js must NOT have been called (over18 cookie path is after bridge gate)
        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert eval_calls == [], (
            f"evaluate_js must not be called when bridge is not ready; got: {eval_calls}"
        )

        # _cf_urls['javlibrary'] must record the challenged URL for begin_solve
        assert transport._cf_urls['javlibrary'] == url, (
            f"_cf_urls['javlibrary'] must be set to {url!r} when bridge not ready; "
            f"got {transport._cf_urls['javlibrary']!r}"
        )

    def test_fetch_cross_origin_raises_challenge_without_wv_fetch(self):
        """
        INV-1 (CD-118a-3) — the most important test in T1: a transport window
        recorded (seeded) at a DIFFERENT origin than the requested URL must
        route into the challenge/navigate flow WITHOUT ever calling _wv_fetch
        (i.e. zero evaluate_js calls — _wv_fetch is evaluate_js(callback=...)).

        mutation: remove the origin gate in fetch() → this test must go red
        (load_calls becomes empty and/or evaluate_js calls appear).
        """
        win = FakeWindow()
        # This window's recorded origin is fc-javten's — a mismatch for the
        # javlibrary URL fetched below under the 'javlibrary' key.
        transport = PyWebViewCfTransport(
            {'javlibrary': win},
            {'javlibrary': 'https://javten.com/'},
        )
        url = 'https://www.javlibrary.com/ja/vl_searchbyid.php?keyword=START-578'

        with pytest.raises(CfChallengeRequired):
            transport.fetch(url, 'javlibrary')

        load_calls = [c for c in win.calls if c[0] == 'load_url']
        assert load_calls and load_calls[-1][1] == url, (
            f"origin mismatch must trigger load_url({url!r}); got {load_calls}"
        )

        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert eval_calls == [], (
            f"_wv_fetch (evaluate_js) must NOT be called on origin mismatch; got {eval_calls}"
        )

    def test_javten_fetch_skips_age_gate_and_over18_cookie(self, monkeypatch):
        """
        CD-118a-5 per-site behaviour table: fetch() for fc-javten must NOT call
        _is_age_gate and must NOT set the over18 cookie (that gate is
        javlibrary-only — applying it to javten risks false-positive matches
        on unrelated markup and an unsolvable CfChallengeRequired loop).

        mutation: make both sites share the same age-gate handling → this test
        must go red.
        """
        age_gate_calls = []
        monkeypatch.setattr(
            cf_transport_impl, '_is_age_gate',
            lambda html: (age_gate_calls.append(html), False)[1],
        )
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://javten.com/',
            'status': 200,
            'html': '<html><head><title>JavTen</title></head><body>content</body></html>',
        }
        transport = PyWebViewCfTransport(
            {'fc-javten': win}, {'fc-javten': 'https://javten.com/'},
        )

        result = transport.fetch('https://javten.com/', 'fc-javten')
        assert isinstance(result, str)

        assert age_gate_calls == [], (
            f"_is_age_gate must not be called for fc-javten; got {age_gate_calls}"
        )
        over18_calls = [c for c in win.calls if c[0] == 'evaluate_js' and 'over18' in c[1]]
        assert over18_calls == [], (
            f"over18 cookie must not be set for fc-javten; got {over18_calls}"
        )

    def test_javlibrary_fetch_still_sets_age_gate_and_cookie(self, monkeypatch):
        """
        Regression lock (reverse of the test above): javlibrary's fetch() must
        keep calling _is_age_gate and setting the over18 cookie — zero
        regression from introducing the per-site behaviour table.
        """
        age_gate_calls = []
        monkeypatch.setattr(
            cf_transport_impl, '_is_age_gate',
            lambda html: (age_gate_calls.append(html), False)[1],
        )
        win = FakeWindow()
        win._eval_callback_result['default'] = {
            'finalUrl': 'https://www.javlibrary.com/ja/',
            'status': 200,
            'html': NORMAL_HTML,
        }
        transport = _jl_transport(win)

        result = transport.fetch('https://www.javlibrary.com/ja/')
        assert isinstance(result, str)

        assert len(age_gate_calls) == 1, (
            f"_is_age_gate must be called exactly once for javlibrary; got {age_gate_calls}"
        )
        over18_calls = [c for c in win.calls if c[0] == 'evaluate_js' and 'over18' in c[1]]
        assert over18_calls, "over18 cookie must be set for javlibrary"


# ──────────────────────────────────────────────────────────────
# Tests: begin_solve()
# ──────────────────────────────────────────────────────────────

class TestBeginSolve:
    def test_calls_show_then_load_url_no_blocking_eval(self):
        """begin_solve → show() + load_url(origin) only — NO evaluate_js.

        ROOT-CAUSE FIX (0.9.9c): setting the over18 cookie via evaluate_js right
        after load_url to a CF-challenged origin blocks ~20s on _pywebviewready and
        raises WebViewException, stranding the bridge. over18 is set in
        fetch()/is_ready() instead. begin_solve must stay show + navigate only.

        Note: this test passes `_cf_url=None` (default), so begin_solve falls back to
        the origin argument; when `_cf_url` is set it takes priority — see
        TestBeginSolveTargetsCfUrl.
        """
        win = FakeWindow()
        transport = _jl_transport(win)
        origin = 'https://www.javlibrary.com/ja/'
        transport.begin_solve(origin)

        method_calls = [c[0] for c in win.calls]
        assert 'show' in method_calls
        assert 'load_url' in method_calls
        assert 'evaluate_js' not in method_calls, (
            "begin_solve must not call evaluate_js — it blocks on a CF page and "
            "strands the pywebview bridge (0.9.9b repro)"
        )

        # Check order: show before load_url
        show_idx = next(i for i, c in enumerate(win.calls) if c[0] == 'show')
        load_idx = next(i for i, c in enumerate(win.calls) if c[0] == 'load_url')
        assert show_idx < load_idx

        # load_url gets the origin
        load_call = next(c for c in win.calls if c[0] == 'load_url')
        assert load_call[1] == origin

    def test_returns_immediately(self):
        """begin_solve() must return immediately (no blocking)."""
        import time
        win = FakeWindow()
        transport = _jl_transport(win)
        start = time.monotonic()
        transport.begin_solve('https://www.javlibrary.com/ja/')
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"begin_solve blocked for {elapsed:.2f}s (should return immediately)"


# ──────────────────────────────────────────────────────────────
# Tests: is_ready()
# ──────────────────────────────────────────────────────────────

READY_TITLE = 'JavLibrary'
READY_HEAD = '<html><head><title>JavLibrary</title></head>'
CF_TITLE = 'Just a moment'
CF_HEAD = '<html><head><title>Just a moment</title></head><body>cf</body>'
AGE_GATE_TITLE = 'JavLibrary'
# 真實同意閘（含 agreeBtn）→ is_ready 應回 False
AGE_GATE_HEAD = '<html><head><title>JavLibrary</title></head><body><button id="agreeBtn">同意</button></body>'
# 正常內容頁 footer（含 利用規約/18歳/over18 但無 agreeBtn）→ is_ready 應回 True
CONTENT_FOOTER_HEAD = '<html><head><title>JavLibrary</title></head><body>利用規約 18歳 over18</body>'


class FakeWindowIsReady(FakeWindow):
    """
    FakeWindow variant that maps specific document.title and
    document.documentElement.outerHTML.slice(0, 4000) JS codes
    to configured return values.
    """

    def __init__(self, title: str, head: str):
        super().__init__()  # inherits self.events = FakeWindowEvents()
        self._title = title
        self._head = head

    def evaluate_js(self, code, callback=None):
        self.calls.append(('evaluate_js', code, callback))
        if callback is not None:
            # _wv_fetch path (not relevant for is_ready tests)
            if not self._never_callback:
                result = self._eval_callback_result.get('default', {})
                callback(result)
            return None
        # Sync returns (is_ready path)
        if 'document.title' in code:
            return self._title
        if 'outerHTML' in code:
            return self._head
        return None


class TestIsReady:
    def test_ready_page_returns_true_and_hides(self):
        """Ready page → True, window.hide() called."""
        win = FakeWindowIsReady(READY_TITLE, READY_HEAD)
        transport = _jl_transport(win)
        result = transport.is_ready()
        assert result is True
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert len(hide_calls) == 1, "hide() should be called once when ready"

    def test_cf_challenge_returns_false_no_hide(self):
        """CF challenge page → False, no hide()."""
        win = FakeWindowIsReady(CF_TITLE, CF_HEAD)
        transport = _jl_transport(win)
        result = transport.is_ready()
        assert result is False
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert len(hide_calls) == 0, "hide() must NOT be called when not ready"

    def test_content_footer_terms_returns_true_and_hides(self):
        """
        FIX-1 回歸（收窄語義版）：正常內容頁 footer 含 利用規約/18歳/over18
        但**無 agreeBtn** → is_ready() 應回 True 並 hide 視窗。

        narrow _is_age_gate 只看 agreeBtn，footer 字不再誤判 False，
        用戶過了 CF 後不會卡在等待循環。
        """
        win = FakeWindowIsReady(AGE_GATE_TITLE, CONTENT_FOOTER_HEAD)
        transport = _jl_transport(win)
        result = transport.is_ready()
        assert result is True, (
            "正常內容頁 footer 含 利用規約/18歳/over18 但無 agreeBtn，"
            "is_ready() 應回 True（footer 字不觸發 age-gate 偵測）"
        )
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert len(hide_calls) == 1, "is_ready()=True 時應 hide() 視窗"

    def test_real_age_gate_with_agree_btn_returns_false_no_hide(self):
        """
        spec-70b §2.3 point 5 契約：真實同意閘（含 agreeBtn）→ is_ready() 回 False，
        視窗不 hide，讓用戶手動點同意按鈕。
        """
        win = FakeWindowIsReady(AGE_GATE_TITLE, AGE_GATE_HEAD)
        transport = _jl_transport(win)
        result = transport.is_ready()
        assert result is False, (
            "真實 age-gate 同意頁（含 agreeBtn）is_ready() 應回 False，"
            "保留彈窗讓用戶點同意（spec-70b §2.3 point 5）"
        )
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert len(hide_calls) == 0, "age-gate 時不應 hide()，彈窗須保留"

    def test_blank_or_navigating_page_returns_false_no_hide(self):
        """
        FIX-P2A: 導航中頁面（document.title 回空字串）→ is_ready() 回 False，
        視窗不 hide，避免慢載入時誤判 ready 並提前關閉彈窗。
        """
        # Empty title simulates page still navigating (evaluate_js returns "" or None)
        win = FakeWindowIsReady("", READY_HEAD)
        transport = _jl_transport(win)
        result = transport.is_ready()
        assert result is False, (
            "導航中/空 title 頁面 is_ready() 應回 False（loaded-page guard）"
        )
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert len(hide_calls) == 0, "空 title 時不應 hide()，視窗須保留"

    def test_every_call_sets_over18_cookie(self):
        """Every is_ready() call sets over18 cookie (idempotent)."""
        win = FakeWindowIsReady(READY_TITLE, READY_HEAD)
        transport = _jl_transport(win)
        transport.is_ready()
        transport.is_ready()

        over18_calls = [
            c for c in win.calls
            if c[0] == 'evaluate_js' and 'over18' in c[1]
        ]
        assert len(over18_calls) >= 2, "over18 cookie should be set on every is_ready() call"

    def test_evaluate_js_none_degrades_gracefully(self):
        """evaluate_js returning None (window not ready) → no exception, returns bool."""
        class NoneWindow(FakeWindow):
            def evaluate_js(self, code, callback=None):
                self.calls.append(('evaluate_js', code, callback))
                if callback is not None:
                    return None
                return None  # Always None

        win = NoneWindow()
        transport = _jl_transport(win)
        # Should not raise; returns a bool (True or False — both are acceptable)
        result = transport.is_ready()
        assert isinstance(result, bool), "is_ready() must return bool even when evaluate_js returns None"

    def test_is_ready_bridge_not_ready_returns_false_no_evaluate_js(self):
        """
        Bridge gate (0.9.9c): when _pywebviewready is unset (bridge not ready),
        is_ready() must:
          - return False immediately (no blocking ~20s on evaluate_js)
          - NOT call evaluate_js at all (bridge gate fires before over18 cookie + title check)
          - NOT call hide() (window stays visible — CF/loading page still active)
        """
        win = FakeWindowIsReady(READY_TITLE, READY_HEAD)
        # Bridge not ready: clear the _pywebviewready event
        win.events._pywebviewready.clear()
        transport = _jl_transport(win)

        result = transport.is_ready()

        assert result is False, (
            "is_ready() must return False when bridge is not ready (bridge gate)"
        )

        # evaluate_js must NOT have been called
        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert eval_calls == [], (
            f"evaluate_js must not be called when bridge is not ready; got: {eval_calls}"
        )

        # hide() must NOT have been called (window stays visible)
        hide_calls = [c for c in win.calls if c[0] == 'hide']
        assert hide_calls == [], (
            f"hide() must not be called when bridge is not ready; got: {hide_calls}"
        )

    def test_is_ready_only_checks_named_site_window(self):
        """
        is_ready(key) must only touch that site's window: no reads on the other
        site's window, and only that site's window gets hide()d when ready.
        """
        jl_win = FakeWindowIsReady(CF_TITLE, CF_HEAD)  # javlibrary still on CF (not ready)
        javten_win = FakeWindowIsReady('JavTen', '<html><head><title>JavTen</title></head>')
        transport = PyWebViewCfTransport(
            {'javlibrary': jl_win, 'fc-javten': javten_win},
            {'javlibrary': JL_ORIGIN, 'fc-javten': 'https://javten.com/'},
        )

        result = transport.is_ready('fc-javten')
        assert result is True

        assert jl_win.calls == [], (
            f"javlibrary window must not be touched by is_ready('fc-javten'); got {jl_win.calls}"
        )
        hide_calls = [c for c in javten_win.calls if c[0] == 'hide']
        assert len(hide_calls) == 1, "is_ready('fc-javten')=True must hide only the fc-javten window"


# ──────────────────────────────────────────────────────────────
# Structural guards
# ──────────────────────────────────────────────────────────────

class TestStructuralGuards:
    def test_no_core_importing_windows(self):
        """core/ must not import from windows/ (one-way dependency)."""
        result = subprocess.run(
            ['grep', '-rn', r'import windows|from windows', str(REPO_ROOT / 'core')],
            capture_output=True, text=True
        )
        # grep returns exit code 0 if found, 1 if not found
        assert result.returncode == 1 or result.stdout.strip() == '', \
            f"FAIL: core/ imports windows:\n{result.stdout}"

    def test_launcher_has_no_transport_register(self):
        """launcher.py must not import cf_transport_impl or register_cf_transport."""
        launcher_path = str(REPO_ROOT / 'windows' / 'launcher.py')
        result = subprocess.run(
            ['grep', '-n', 'cf_transport_impl|register_cf_transport', launcher_path],
            capture_output=True, text=True
        )
        assert result.returncode == 1 or result.stdout.strip() == '', \
            f"FAIL: launcher.py references transport:\n{result.stdout}"

    def test_wv_fetch_is_module_level(self):
        """_wv_fetch must be defined at module level (column 0), not inside a class."""
        impl_path = REPO_ROOT / 'windows' / 'cf_transport_impl.py'
        result = subprocess.run(
            ['grep', '-n', '^def _wv_fetch', str(impl_path)],
            capture_output=True, text=True
        )
        assert result.returncode == 0 and result.stdout.strip() != '', \
            "FAIL: _wv_fetch not found at module level (column 0)"

    def test_javlibrary_module_does_not_call_navigate_and_settle(self):
        """javlibrary.py must never call navigate_and_settle — that primitive is fc-javten only."""
        javlibrary_path = str(REPO_ROOT / 'core' / 'scrapers' / 'javlibrary.py')
        result = subprocess.run(
            ['grep', '-n', 'navigate_and_settle', javlibrary_path],
            capture_output=True, text=True
        )
        assert result.returncode == 1 or result.stdout.strip() == '', \
            f"FAIL: javlibrary.py references navigate_and_settle:\n{result.stdout}"


# ──────────────────────────────────────────────────────────────
# CD-70c-2 Layer 2: dead-flag fail-fast tests
# ──────────────────────────────────────────────────────────────

class TestDeadFlagFailFast:
    """
    CD-70c-2 Layer 2 backstop: once the transport is dead (window destroyed),
    fetch / begin_solve / is_ready must each raise CfTransportUnavailable immediately
    rather than operating on a dead window.
    """

    def test_on_closed_handler_sets_dead(self):
        """_on_closed() handler sets _dead=True (backstop fire path)."""
        win = FakeWindow()
        transport = _jl_transport(win)
        assert transport._dead['javlibrary'] is False, "_dead['javlibrary'] must start as False"
        # Fire the closed event as if the window was destroyed
        win.events.closed.fire()
        assert transport._dead['javlibrary'] is True, "_on_closed should set _dead['javlibrary']=True"

    def test_fetch_raises_when_dead(self):
        """fetch() raises CfTransportUnavailable when _dead['javlibrary']=True."""
        win = FakeWindow()
        transport = _jl_transport(win)
        transport._dead['javlibrary'] = True
        with pytest.raises(CfTransportUnavailable, match="restart OpenAver"):
            transport.fetch('https://www.javlibrary.com/ja/')

    def test_begin_solve_raises_when_dead(self):
        """begin_solve() raises CfTransportUnavailable when _dead['javlibrary']=True (guard before show())."""
        win = FakeWindow()
        transport = _jl_transport(win)
        transport._dead['javlibrary'] = True
        with pytest.raises(CfTransportUnavailable, match="restart OpenAver"):
            transport.begin_solve('https://www.javlibrary.com/ja/')
        # show() must NOT have been called (dead guard must be before show())
        show_calls = [c for c in win.calls if c[0] == 'show']
        assert not show_calls, "show() must not be called after dead guard raises"

    def test_is_ready_raises_when_dead(self):
        """is_ready() raises CfTransportUnavailable when _dead['javlibrary']=True."""
        win = FakeWindowIsReady(READY_TITLE, READY_HEAD)
        transport = _jl_transport(win)
        transport._dead['javlibrary'] = True
        with pytest.raises(CfTransportUnavailable, match="restart OpenAver"):
            transport.is_ready()

    def test_dead_via_on_closed_then_fetch_raises(self):
        """Full path: window closed event fires → _dead=True → fetch raises."""
        win = FakeWindow()
        transport = _jl_transport(win)
        # Simulate window being destroyed by OS / crash
        win.events.closed.fire()
        with pytest.raises(CfTransportUnavailable):
            transport.fetch('https://www.javlibrary.com/ja/')

    def test_dead_window_isolated_per_site(self):
        """
        _dead must be per-site: killing site A's window must not affect site B.

        mutation: make _dead a single shared bool again → this test must go red
        (fc-javten's fetch/is_ready would start raising CfTransportUnavailable too).
        """
        win_a = FakeWindow()
        win_b = FakeWindowIsReady(READY_TITLE, READY_HEAD)
        transport = PyWebViewCfTransport(
            {'javlibrary': win_a, 'fc-javten': win_b},
            {'javlibrary': JL_ORIGIN, 'fc-javten': 'https://javten.com/'},
        )

        win_a.events.closed.fire()
        assert transport._dead['javlibrary'] is True
        assert transport._dead['fc-javten'] is False

        with pytest.raises(CfTransportUnavailable):
            transport.fetch(JL_ORIGIN, 'javlibrary')

        # fc-javten must remain fully operable despite javlibrary's window dying
        result = transport.fetch('https://javten.com/', 'fc-javten')
        assert isinstance(result, str)
        assert transport.is_ready('fc-javten') is True


# ──────────────────────────────────────────────────────────────
# Tests: 0.9.9g begin_solve navigates to CF-challenged URL
# ──────────────────────────────────────────────────────────────

class TestBeginSolveTargetsCfUrl:
    """
    0.9.9g: begin_solve must navigate to the exact URL that triggered CF
    (self._cf_urls[key]) so the user sees the real Turnstile challenge
    immediately, rather than the homepage which has no CF challenge.
    """

    CF_SEARCH_URL = 'https://www.javlibrary.com/ja/vl_searchbyid.php?keyword=START-578'
    ORIGIN_URL = 'https://www.javlibrary.com/ja/'

    def test_begin_solve_navigates_to_remembered_cf_url(self):
        """When _cf_urls['javlibrary'] is set, begin_solve navigates to it (not origin)."""
        win = FakeWindow()
        transport = _jl_transport(win)
        # Simulate a CF fetch having recorded the challenged URL
        transport._cf_urls['javlibrary'] = self.CF_SEARCH_URL

        transport.begin_solve(self.ORIGIN_URL)

        load_calls = [c for c in win.calls if c[0] == 'load_url']
        assert len(load_calls) == 1
        assert load_calls[0][1] == self.CF_SEARCH_URL, (
            f"begin_solve must navigate to _cf_urls['javlibrary'] ({self.CF_SEARCH_URL!r}), "
            f"not origin ({self.ORIGIN_URL!r}); got {load_calls[0][1]!r}"
        )

    def test_begin_solve_falls_back_to_origin_when_no_cf_url(self):
        """When _cf_urls['javlibrary'] is None (fresh transport), begin_solve falls back to origin."""
        win = FakeWindow()
        transport = _jl_transport(win)
        assert transport._cf_urls['javlibrary'] is None

        transport.begin_solve(self.ORIGIN_URL)

        load_calls = [c for c in win.calls if c[0] == 'load_url']
        assert len(load_calls) == 1
        assert load_calls[0][1] == self.ORIGIN_URL, (
            f"begin_solve must fall back to origin when _cf_urls['javlibrary'] is None; "
            f"got {load_calls[0][1]!r}"
        )

    def test_fetch_cf_detected_records_cf_url(self, monkeypatch):
        """fetch() with CF title → raises CfChallengeRequired AND records _cf_urls['javlibrary']."""
        search_url = self.CF_SEARCH_URL

        def fake_wv_fetch(window, url, **kwargs):
            return (url, 200, CF_HTML)

        monkeypatch.setattr(cf_transport_impl, '_wv_fetch', fake_wv_fetch)
        win = FakeWindow()
        transport = _jl_transport(win)

        with pytest.raises(CfChallengeRequired):
            transport.fetch(search_url)

        assert transport._cf_urls['javlibrary'] == search_url, (
            f"_cf_urls['javlibrary'] must be set to the CF-challenged URL ({search_url!r}); "
            f"got {transport._cf_urls['javlibrary']!r}"
        )


# ──────────────────────────────────────────────────────────────
# Tests: navigate_and_settle() (TASK-118a-T1 / CD-118a-18)
# ──────────────────────────────────────────────────────────────

class FakeWindowNavigate(FakeWindow):
    """
    FakeWindow variant for navigate_and_settle(): supports sync evaluate_js
    reads for document.title / outerHTML (same convention as FakeWindowIsReady),
    on top of the base class's load_url()/get_current_url()/show()/hide().
    """

    def __init__(self, title: str = 'JavTen', head: str = '<html><head><title>JavTen</title></head>'):
        super().__init__()
        self._title = title
        self._head = head

    def evaluate_js(self, code, callback=None):
        self.calls.append(('evaluate_js', code, callback))
        if callback is not None:
            if not self._never_callback:
                result = self._eval_callback_result.get('default', {})
                callback(result)
            return None
        if 'document.title' in code:
            return self._title
        if 'outerHTML' in code:
            return self._head
        return None


class FakeEventLogging(FakeEvent):
    """FakeEvent that logs wait() calls into a shared list, so a test can assert
    ordering between the bridge-ready wait and subsequent evaluate_js reads."""

    def __init__(self, initial: bool, log: list):
        super().__init__(initial)
        self._log = log

    def wait(self, timeout=None):
        self._log.append(('bridge_wait', timeout))
        return super().wait(timeout)


class RealDelayedEvent:
    """Thin wrapper over a real threading.Event, used only for the
    "bridge becomes ready after a short delay" blocking test — FakeEvent's
    wait() is intentionally non-blocking (instant), so it can't model a
    background thread calling set() a few milliseconds later."""

    def __init__(self, initial: bool = False):
        self._evt = threading.Event()
        if initial:
            self._evt.set()

    def is_set(self):
        return self._evt.is_set()

    def set(self):
        self._evt.set()

    def clear(self):
        self._evt.clear()

    def wait(self, timeout=None):
        return self._evt.wait(timeout)


class TestNavigateAndSettle:
    """
    navigate_and_settle(url, key) — CD-118a-18: navigate the site's window,
    wait (bounded) for the pywebview bridge, then return the settled URL.
    Never calls evaluate_js before the bridge is ready (0.9.9c).
    """

    JAVTEN_URL = 'https://javten.com/search?kw=4938117'

    def test_navigate_and_settle_no_evaluate_js_before_bridge_ready(self, monkeypatch):
        """
        Bridge never becomes ready → navigate_and_settle raises, and evaluate_js
        (the title/head challenge reads) must never have been called.

        mutation: change navigate_and_settle to call evaluate_js right after
        navigating (not waiting for the Event) → this test must go red.
        """
        monkeypatch.setattr(cf_transport_impl, 'NAVIGATE_BRIDGE_TIMEOUT_S', 0.05)
        win = FakeWindowNavigate()
        win.events._pywebviewready = FakeEvent(initial=False)
        transport = PyWebViewCfTransport({'fc-javten': win}, None)

        with pytest.raises(CfChallengeRequired):
            transport.navigate_and_settle(self.JAVTEN_URL, 'fc-javten')

        eval_calls = [c for c in win.calls if c[0] == 'evaluate_js']
        assert eval_calls == [], (
            f"evaluate_js must not be called when the bridge never becomes ready; got {eval_calls}"
        )

    def test_navigate_and_settle_waits_for_bridge_then_returns_url(self, monkeypatch):
        """
        Bridge becomes ready ~50ms after navigation (a background thread calls
        set() on a real threading.Event) → navigate_and_settle must wait for it
        and return the settled URL, and must NEVER call show()/begin_solve.

        mutation: replace the bounded wait with fetch()'s "not ready → raise
        immediately" snapshot gate → this test must go red (it would raise
        instead of returning, since the event isn't set() yet at call time).
        """
        monkeypatch.setattr(cf_transport_impl, 'NAVIGATE_BRIDGE_TIMEOUT_S', 2.0)
        win = FakeWindowNavigate(title='JavTen', head='<html><head><title>JavTen</title></head>')
        win.events._pywebviewready = RealDelayedEvent(initial=False)
        transport = PyWebViewCfTransport({'fc-javten': win}, None)

        def _delayed_set():
            time.sleep(0.05)
            win.events._pywebviewready.set()

        threading.Thread(target=_delayed_set, daemon=True).start()

        result = transport.navigate_and_settle(self.JAVTEN_URL, 'fc-javten')

        assert result == self.JAVTEN_URL, (
            f"navigate_and_settle must return the settled URL once the bridge "
            f"becomes ready; got {result!r}"
        )
        show_calls = [c for c in win.calls if c[0] == 'show']
        assert show_calls == [], (
            "navigate_and_settle must never call show()/begin_solve; "
            f"got show() calls: {show_calls}"
        )

    def test_navigate_and_settle_records_landed_origin_not_requested_origin(self, monkeypatch):
        """
        The search step is a redirect chain we do not control. If it settles on a
        DIFFERENT origin than the one we requested, the origin bookkeeping must
        follow the window, not our request — otherwise the very next fetch() misses
        the INV-1 gate and pops the CF window although Cloudflare never challenged.

        User-visible symptom if this regresses: every single fc-javten query opens
        the CF window (the exact thing CD-118a-18 exists to prevent).

        mutation: record the origin from the requested url only (drop the
        _record_origin(key, final_url) call after get_current_url()) → this test
        must go red with CfChallengeRequired.
        """
        monkeypatch.setattr(cf_transport_impl, 'NAVIGATE_BRIDGE_TIMEOUT_S', 0.05)
        landed = 'https://www.javten.com/video/12345/id4938117/slug'
        win = FakeWindowNavigate()
        win.events._pywebviewready = FakeEvent(initial=True)
        transport = PyWebViewCfTransport({'fc-javten': win}, None)

        # requested host javten.com → settles on www.javten.com (cross-origin redirect)
        win.get_current_url = lambda: landed
        result = transport.navigate_and_settle(self.JAVTEN_URL, 'fc-javten')
        assert result == landed

        # The follow-up fetch() of the settled page must pass the origin gate:
        # no re-navigation, no CF challenge — it must actually reach _wv_fetch.
        fetched = []
        monkeypatch.setattr(
            cf_transport_impl, '_wv_fetch',
            lambda w, u: (fetched.append(u), (u, 200, '<html><title>ok</title><body>x</body></html>'))[1],
        )
        loads_before = len([c for c in win.calls if c[0] == 'load_url'])

        transport.fetch(landed, 'fc-javten')

        assert fetched == [landed], (
            "fetch() of the settled URL must reach _wv_fetch; the origin gate "
            f"compared against a stale origin instead. _wv_fetch calls: {fetched}"
        )
        loads_after = len([c for c in win.calls if c[0] == 'load_url'])
        assert loads_after == loads_before, (
            "fetch() must not re-navigate after navigate_and_settle already "
            f"settled there; load_url calls went {loads_before} → {loads_after}"
        )

    def test_origin_comparison_is_case_insensitive(self, monkeypatch):
        """
        RFC 3986: scheme and host are case-insensitive. A redirect returning an
        upper-case host must not read as a different origin (one spurious
        re-navigate + CF popup per query otherwise).

        mutation: drop the .lower() calls in _origin() → this test must go red.
        """
        win = FakeWindow()
        transport = PyWebViewCfTransport({'fc-javten': win}, {'fc-javten': 'https://javten.com/'})

        fetched = []
        monkeypatch.setattr(
            cf_transport_impl, '_wv_fetch',
            lambda w, u: (fetched.append(u), (u, 200, '<html><title>ok</title><body>x</body></html>'))[1],
        )

        upper = 'HTTPS://JAVTEN.COM/video/1/id2/slug'
        transport.fetch(upper, 'fc-javten')

        assert fetched == [upper], (
            "an upper-case-host URL is the same origin as the recorded "
            f"lower-case one; _wv_fetch calls: {fetched}"
        )

    def test_navigate_and_settle_raises_when_bridge_never_ready(self, monkeypatch):
        """Bridge never becomes ready within the (monkeypatched, tiny) timeout → raises CfChallengeRequired."""
        monkeypatch.setattr(cf_transport_impl, 'NAVIGATE_BRIDGE_TIMEOUT_S', 0.05)
        win = FakeWindowNavigate()
        win.events._pywebviewready = FakeEvent(initial=False)
        transport = PyWebViewCfTransport({'fc-javten': win}, None)

        with pytest.raises(CfChallengeRequired):
            transport.navigate_and_settle(self.JAVTEN_URL, 'fc-javten')

    def test_navigate_and_settle_detects_challenge_after_bridge_ready(self):
        """
        T1's most important navigate_and_settle test: bridge becomes ready, but
        the settled page IS a CF challenge → navigate_and_settle must raise
        CfChallengeRequired, record _cf_urls[key], and NOT return the URL — and
        the title/head reads that decided this must all happen AFTER the
        bridge-ready wait (spy-verified via a shared call log), never before.

        mutation: remove the challenge check (keep only "raise if bridge never
        ready") → this test must go red (no raise; the URL would be returned).
        """
        win = FakeWindowNavigate(title='Just a moment', head='<html><head><title>Just a moment</title></head>')
        win.events._pywebviewready = FakeEventLogging(True, win.calls)
        transport = PyWebViewCfTransport({'fc-javten': win}, None)

        with pytest.raises(CfChallengeRequired):
            transport.navigate_and_settle(self.JAVTEN_URL, 'fc-javten')

        wait_idxs = [i for i, c in enumerate(win.calls) if c[0] == 'bridge_wait']
        eval_idxs = [i for i, c in enumerate(win.calls) if c[0] == 'evaluate_js']
        assert wait_idxs, "the bridge-ready wait must have happened"
        assert eval_idxs, "title/head reads must have happened (they decide the challenge verdict)"
        assert all(i > wait_idxs[0] for i in eval_idxs), (
            f"evaluate_js reads must happen AFTER the bridge-ready wait "
            f"(wait at {wait_idxs[0]}, evaluate_js at {eval_idxs}); call log: {win.calls}"
        )

        assert transport._cf_urls['fc-javten'] == self.JAVTEN_URL, (
            f"_cf_urls['fc-javten'] must record the challenged URL; "
            f"got {transport._cf_urls['fc-javten']!r}"
        )
