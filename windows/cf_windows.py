"""CF 驗證視窗的建立與關閉守衛（自 standalone.py 複製，plan-168d CD-7）。

``build_cf_windows`` 只建兩個隱藏視窗與 transport handle，**不**把 transport 登記成全域；
殼把 handle 交給 ``CfShellAgent``（cf_shell.py）。必須在 ``webview.start()`` 之前呼叫（CD-70c-1）。
sibling import（``webview2_proxy`` / ``cf_transport_impl``）沿用 standalone 寫法，WINDOWS_DIR 已在 sys.path。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable

import webview
from webview2_proxy import ReadyHolder, install as install_webview2_proxy   # sibling import（同 cf_transport_impl）

from core import client_connect, client_settings, proxy_policy
from core.i18n import t
from core.data_root import get_data_root
from core.desktop_env import desktop_kind
from core.proxy_policy import cf_window_proxy, record_cf_window_proxy_at_start


def window_titles(locale=None):
    """兩個驗證視窗的標題 (jl, javten)；locale=None 讀托盤語系，取不到退 zh-TW。

    build_cf_windows 入口只算一次，同一組字串餵 create_window 與 title_to_key（套用器靠標題認視窗）。
    """
    if locale is None:
        try:
            locale = client_settings.tray_locale()
        except Exception:                                            # noqa: BLE001
            locale = 'zh-TW'
    return t('desktop.cf_window.jl_title', locale), t('desktop.cf_window.javten_title', locale)


CF_SHELL_SUPPORTED = {'win32': True, 'darwin': True}


def cf_shell_supported() -> bool:
    """這個平台能不能跑 CF 殼（呼叫時才讀 sys.platform，測試可 patch）。"""
    return bool(CF_SHELL_SUPPORTED.get(sys.platform, False))


@dataclass
class CfWindowSet:
    transport: Any = None
    jl_win: Any = None
    javten_win: Any = None
    proxy_ok: bool = True
    proxy_spec: Any = None
    local_direct: bool = False


def fetch_client_cf(server_url, token, server_origin):
    """向伺服器抓代理設定並套本機位址例外（CD-8/9）；殼的 client／dev 本機接線共用，不拋例外。

    回 ``(ok, reason, effective_settings, local_direct, server_remote)``。失敗時 ``ok=False``、
    ``reason`` 只會是 ``'unauthorized'`` 或 ``'unreachable'``、設定為 ``None``——絕不回預設設定
    （抓不到＝不建窗，fail-closed）。
    """
    r = client_connect.fetch_proxy_settings(server_url, token)
    if not r.get("ok") or r.get("settings") is None:
        reason = "unauthorized" if r.get("reason") == "unauthorized" else "unreachable"
        return False, reason, None, False, False
    server_remote = proxy_policy.is_remote_origin(server_origin)
    eff_settings, local_direct = proxy_policy.client_cf_settings(r["settings"], server_remote)
    return True, None, eff_settings, local_direct, server_remote


def cf_status_static(reason):
    """沒有 agent 的情境（離線啟動、抓不到代理設定）給連線頁的靜態狀態。"""
    return {"state": "not_ready", "reason": reason, "proxy_note": None, "sites": []}


def attach_close_guards(win_set: CfWindowSet, is_quitting: Callable[[], bool]) -> None:
    """關閉驗證視窗＝隱藏而非銷毀（hidden != destroyed，CD-70c-2 / CD-118a-4b）；結束 App 時放行。"""
    def _make(win):
        def _on_closing():
            if not is_quitting():
                win.hide()
                return False
            return None
        return _on_closing

    for win in (win_set.jl_win, win_set.javten_win):
        if win is not None:
            win.events.closing += _make(win)


def _prepare_cf_window_proxy(logger, settings, titles):
    """Windows desktop only: decide whether the CF windows run through the Proxy field.

    Returns (proxy, holder, ok). `proxy` is the CfWindowProxy to apply (None = nothing to
    apply); `holder` is the late-bound confirmation callback; `ok=False` means a proxy is
    configured but cannot be confirmed applied -> caller must NOT build the windows
    (fail-closed: never fall back to the system proxy or a direct connection).
    macOS / non-desktop: (None, None, True) and the webview2_proxy module is never touched.
    """
    if desktop_kind() != 'windows':
        return None, None, True
    holder = ReadyHolder()
    try:
        proxy = cf_window_proxy(settings)
    except Exception as e:                                           # noqa: BLE001
        logger.warning("CF window proxy spec unavailable, CF windows disabled: %s", type(e).__name__)
        return None, holder, False
    title_to_key = {titles[0]: 'javlibrary', titles[1]: 'fc-javten'}
    try:
        udf_root = str(get_data_root() / 'webview')
        ok = install_webview2_proxy(proxy, udf_root, title_to_key, holder)
    except Exception as e:                                           # noqa: BLE001
        logger.warning("CF window proxy install failed: %s", type(e).__name__)
        ok = False
    record_cf_window_proxy_at_start(proxy)
    if proxy is not None:
        logger.info("CF window proxy: scheme=%s usable=%s installed=%s",
                    proxy.server.split('://', 1)[0] or '?', proxy.usable, ok)
    return proxy, holder, ok


def build_cf_windows(logger, settings, local_direct: bool = False) -> CfWindowSet:
    """Create the two hidden CF-verification windows and build the CF transport handle.

    TASK-163b-T7a: extracted out of main() so main() stays under the 200-line function
    limit now that proxy wiring lives here. Must still run BEFORE webview.start()
    (CD-70c-1). Returns a CfWindowSet; the transport is NOT registered here (it is handed
    to the shell agent instead); a window may be None when its creation failed.
    """
    # CD-70c-1: JavLibrary CF transport — create + build BEFORE webview.start()
    # so that _transport is set before first render (eliminates SSR race where
    # cf_transport_available=false was injected on the initial page load).
    # pywebview 6.2.1: create_window(hidden=True) before start() is supported;
    # the native window is only shown after the GUI loop starts via _create_children.
    jl_win = None
    javten_win = None
    transport = None
    proxy = None
    proxy_ok = True
    titles = window_titles()
    try:
        from cf_transport_impl import PyWebViewCfTransport   # sibling import（WINDOWS_DIR 已在 sys.path）
        from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN
        # TASK-163b-T7a: Windows desktop + Proxy field "all sources" -> both windows run through
        # the proxy (blank-started, pending until the applier confirms). proxy is None => unchanged.
        proxy, holder, proxy_ok = _prepare_cf_window_proxy(logger, settings, titles)
        jl_url = None if proxy is not None else JAVLIBRARY_ORIGIN
        initial_urls = {} if proxy is not None else {'javlibrary': JAVLIBRARY_ORIGIN}
        pending = {'javlibrary', 'fc-javten'} if proxy is not None else set()
        # NOTE (P3-6, follow-up): the JL window loads JAVLIBRARY_ORIGIN at launch — so the
        # app connects to javlibrary.com on every startup, even when the source is disabled.
        # This is required by the same-origin fetch design (the hidden window must be parked
        # on the origin for cookie-bearing fetch). A lazy-navigate refactor is a follow-up branch.
        # T11: jl 要有自己的 try（對稱於下方 javten），否則 JL 建立失敗會跳過 transport 建立
        # 連 fc-javten 一起灰掉 —— 理由與守衛見 test_jl_create_window_in_own_try_without_register。
        try:
            if proxy_ok:
                jl_win = webview.create_window(
                    titles[0], jl_url, width=1200, height=820, hidden=True,
                )
        except Exception as e:                                       # noqa: BLE001
            logger.warning("javlibrary CF 視窗建立失敗，該來源不可用（FC2-javten 不受影響）：%s", e)
        # TASK-118a-T1 / CD-118a-4: the fc-javten window is created eagerly here too
        # (same non-lazy precedent as jl_win — both windows exist before webview.start()),
        # but parked on about:blank instead of javten.com. It only navigates there on
        # first use (navigate_and_settle in the search flow), so this does NOT add a
        # second "connects to an external site on every startup" side effect on top of
        # the existing JL one (P3-6, unchanged, still a separate follow-up).
        try:
            if proxy_ok:
                javten_win = webview.create_window(
                    titles[1],
                    None,
                    width=1200, height=820,
                    hidden=True,
                )
        except Exception as e:                                       # noqa: BLE001
            logger.warning("fc-javten CF 視窗建立失敗，該來源不可用（JavLibrary 不受影響）：%s", e)
        # D-0/D-1: only javlibrary is seeded in initial_urls — its window already sits
        # on JAVLIBRARY_ORIGIN. fc-javten is NOT seeded (its window is on about:blank);
        # the origin gate (INV-1) will route its first fetch()/search into
        # navigate_and_settle instead, which is the only writer of self._origins after
        # construction.
        _built = (('javlibrary', jl_win), ('fc-javten', javten_win))
        cf_wins = {k: w for k, w in _built if w is not None}
        # 空 cf_wins 也照樣建 transport：per-site 呼叫一律經 _require_window fail-closed，而空 transport
        # 回報的狀態更準 —— available_sites()=[] 讓膠囊灰化並說「請重新啟動」；沒有 transport 的話
        # cf_transport_available=false，訊息會變成「僅限桌面應用程式」，那在桌面版上根本不成立。
        transport = PyWebViewCfTransport(cf_wins, initial_urls, pending=pending)
        if holder is not None:
            holder.bind(transport)
        logger.info("CF transport built (%s)", ', '.join(cf_wins) or '無可用視窗')
    except Exception as e:
        logger.warning(f"CF transport init failed (JavLibrary/FC2-javten may be unavailable): {e}")
    return CfWindowSet(transport=transport, jl_win=jl_win, javten_win=javten_win,
                       proxy_ok=proxy_ok, proxy_spec=proxy, local_direct=local_direct)
