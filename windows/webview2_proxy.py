"""驗證視窗（JavLibrary／FC2-javten）走 Proxy 欄的 WebView2 套用器（TASK-163b-T7a / CD-163b-15）。

把 pywebview 的 `webview.platforms.edgechromium.WebView2` 換成 Python 子類，只對
「建立時標題屬於 `title_to_key`」的視窗：①UserDataFolder 換成專屬目錄 ②在
AdditionalBrowserArguments 加 `--proxy-server=` ③（有帳密時）原生初始化完成後掛
`BasicAuthenticationRequested`。主視窗完全不碰。

fail-closed（I-B）：無法確認套用時 `install` 回 `False`，呼叫端不建立兩個驗證視窗，
絕不退回系統代理或直連。視窗只有在「參數套用 + 原生初始化成功 + 帳密 handler 就緒」
三者皆成後才經 `on_ready(key)` 確認可用。

本模組頂層不 import `webview.platforms.edgechromium`（它 import clr，Linux 上會炸）；
`install` 內才 lazy import，且 `proxy is None` 時連 lazy import 都不做。
log 只記 key 與 scheme，不記位址與帳密。
"""
from __future__ import annotations

import os
import shutil
import threading
from typing import Callable, Optional
from urllib.parse import urlsplit

from core.logger import get_logger

logger = get_logger(__name__)

UDF_SUBDIR = 'cf-proxy'
_PROXY_ARG = '--proxy-server='


# ---------------------------------------------------------------------------
# 純函式
# ---------------------------------------------------------------------------

def build_browser_args(existing: Optional[str], server: str) -> str:
    """保留既有參數，且結果恰有一個 `--proxy-server=`。"""
    tokens = [t for t in (existing or '').split() if not t.startswith(_PROXY_ARG)]
    tokens.append(_PROXY_ARG + server)
    return ' '.join(tokens)


def udf_dir(udf_root: str) -> str:
    return os.path.join(udf_root, UDF_SUBDIR)


def match_window_key(title: Optional[str], title_to_key: dict) -> Optional[str]:
    if not isinstance(title, str):
        return None
    return title_to_key.get(title)


def split_server(server: str) -> tuple[str, int]:
    parts = urlsplit(server)
    return (parts.hostname or '').lower(), parts.port or 0


def is_proxy_challenge(uri: str, proxy_host: str, proxy_port: int) -> bool:
    """帳密挑戰只在 `uri` 的 host:port 等於代理時才回應（網站自己的 401 不回應）。"""
    try:
        parts = urlsplit(str(uri))
        host = (parts.hostname or '').lower()
        port = parts.port
    except ValueError:
        return False
    return bool(host) and host == proxy_host and port == proxy_port


# ---------------------------------------------------------------------------
# 延遲綁定的確認 holder（I-B'-5）
# ---------------------------------------------------------------------------

class ReadyHolder:
    """`on_ready` 的延遲綁定：transport 未建好時先暫存 key，`bind` 時補呼叫；
    每個 key 的 `confirm_ready` 恰一次。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transport = None
        self._early: set[str] = set()
        self._done: set[str] = set()

    def __call__(self, key: str) -> None:
        with self._lock:
            if key in self._done:
                return
            if self._transport is None:
                self._early.add(key)
                return
            self._done.add(key)
            transport = self._transport
        transport.confirm_ready(key)

    def bind(self, transport) -> None:
        with self._lock:
            self._transport = transport
            replay = []
            for key in sorted(self._early):
                if key not in self._done:
                    self._done.add(key)
                    replay.append(key)
            self._early.clear()
        for key in replay:
            transport.confirm_ready(key)


# ---------------------------------------------------------------------------
# 套用器
# ---------------------------------------------------------------------------

def _make_proxied_class(base, proxy, udf: str, title_to_key: dict, on_ready: Callable[[str], None]):
    proxy_host, proxy_port = split_server(proxy.server)
    scheme = proxy.server.split('://', 1)[0]
    has_auth = proxy.username is not None or proxy.password is not None
    state: dict[int, str] = {}

    def _window_key(control) -> Optional[str]:
        try:
            parent = control.Parent
            title = parent.Text if parent is not None else None
        except Exception:
            return None
        return match_window_key(title, title_to_key)

    def _hook_auth(core) -> None:
        def _on_auth(sender, args) -> None:
            if not is_proxy_challenge(args.Uri, proxy_host, proxy_port):
                return
            args.Response.UserName = proxy.username or ''
            args.Response.Password = proxy.password or ''

        core.BasicAuthenticationRequested += _on_auth

    def _make_init_done(key: str):
        def _on_init_done(sender, args) -> None:
            if not getattr(args, 'IsSuccess', False):
                logger.warning("CF window '%s': native init failed, stays unavailable", key)
                return
            if has_auth:
                try:
                    _hook_auth(sender.CoreWebView2)
                except Exception as e:  # noqa: BLE001
                    logger.warning("CF window '%s': auth hook failed, stays unavailable (%s)", key, type(e).__name__)
                    return  # auth-hook-failed-no-confirm
            try:
                on_ready(key)
            except Exception as e:  # noqa: BLE001
                logger.warning("CF window '%s': confirm failed (%s)", key, type(e).__name__)
                return
            logger.info("CF window '%s': proxy applied (scheme=%s, auth=%s)", key, scheme, has_auth)
        return _on_init_done

    class ProxiedWebView2(base):
        def EnsureCoreWebView2Async(self, env):
            key = _window_key(self)
            if key is None:
                return base.EnsureCoreWebView2Async(self, env)
            previous = state.get(id(self))
            if previous == 'failed':
                return None
            if previous == 'applied':
                return base.EnsureCoreWebView2Async(self, env)
            try:
                props = self.CreationProperties
                props.UserDataFolder = udf
                props.AdditionalBrowserArguments = build_browser_args(
                    props.AdditionalBrowserArguments, proxy.server)
            except Exception as e:  # noqa: BLE001
                state[id(self)] = 'failed'
                logger.warning("CF window '%s': proxy args could not be applied (%s)", key, type(e).__name__)
                return None  # step1-failed-skip-base
            state[id(self)] = 'applied'
            self.CoreWebView2InitializationCompleted += _make_init_done(key)
            return base.EnsureCoreWebView2Async(self, env)

    return ProxiedWebView2


def install(proxy, udf_root: str, title_to_key: dict, on_ready: Callable[[str], None]) -> bool:
    """Returns True when nothing is needed (`proxy is None`) or the applier is in place;
    False when a proxy exists but cannot be confirmed applied (caller must not build the
    verification windows)."""
    if proxy is None:
        return True
    if not getattr(proxy, 'server', ''):
        return False
    target = udf_dir(udf_root)
    try:
        shutil.rmtree(str(target), ignore_errors=True)
        os.makedirs(target, exist_ok=True)
        if not os.path.isdir(target):
            return False
    except OSError as e:
        logger.warning("CF window proxy: UDF dir unavailable (%s)", type(e).__name__)
        return False
    try:
        from webview.platforms import edgechromium as ec
        base = ec.WebView2
        if not isinstance(base, type) or not hasattr(base, 'EnsureCoreWebView2Async'):
            logger.warning("CF window proxy: WebView2 class shape unexpected")
            return False
        ec.WebView2 = _make_proxied_class(base, proxy, target, title_to_key, on_ready)
    except Exception as e:  # noqa: BLE001
        logger.warning("CF window proxy: applier not installed (%s)", type(e).__name__)
        return False
    return True
