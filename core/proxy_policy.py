"""
單一代理選擇點（TASK-163a-T1 / CD-163a-1）。

全站唯一回答「這條連線該走哪個代理」的地方。`proxy_for()` 回 `None` ＝
沒被選到（照系統代理）。規則矩陣是 policy 內**唯一**出現 `scope` 判斷的地方。

不在列舉內的連線（metatube 本體、AI、檢查更新）永遠不問這裡；JavLibrary／FC2-javten
的驗證視窗（Windows 桌面版）經 `cf_window_proxy()` 問同一個矩陣。
log 紀律：不記代理位址（可能含 user:pass@），要記只記 scope／種類。
頂層只 import pydantic／typing／requests；其餘 lazy（BE-LINT-09 循環面）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional
from urllib.parse import unquote, urlsplit

import requests
from pydantic import BaseModel, ConfigDict, field_validator

from core.desktop_env import desktop_kind

Conn = str  # 'source_query' | 'image' | 'actress'

_ALL_SCOPE_CONNS = frozenset({'source_query', 'image', 'actress'})


class ProxySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = ''
    scope: Literal['dmm', 'all'] = 'dmm'

    @field_validator('url', mode='before')
    @classmethod
    def _normalize_url(cls, v):
        """唯一的位址正規化點：所有 `ProxySettings` 都經此建立（config／快照／測試連線），
        所有出口（requests proxies、驗證視窗、探測）只讀 `.url`。
        沒有 `://` 的位址（Clash／v2rayN 常見的 `127.0.0.1:7890`）一律視為 `http://<位址>`。
        不用 `requests.utils.prepend_scheme_if_needed`：`localhost:7890` 會被補成 `localhost:///7890`。"""
        if not isinstance(v, str):
            return v
        v = v.strip()
        if v and '://' not in v:
            v = 'http://' + v
        return v


def settings_from_config(config: dict) -> ProxySettings:
    """唯一讀 `search.proxy_url`／`proxy_scope` 的地方。缺鍵或非法 scope → 'dmm'。"""
    search = (config or {}).get('search') or {}
    url = search.get('proxy_url')
    url = url.strip() if isinstance(url, str) else ''
    scope = search.get('proxy_scope')
    if scope not in ('dmm', 'all'):
        scope = 'dmm'
    return ProxySettings(url=url, scope=scope)


def current_settings() -> ProxySettings:
    from core.config import load_config

    return settings_from_config(load_config())


def source_needs_jp_ip(source_id: Optional[str]) -> bool:
    from core.scrapers.utils import PROXY_SOURCES

    return source_id in PROXY_SOURCES


def proxy_for(
    conn: Conn,
    *,
    source_id: Optional[str] = None,
    url: Optional[str] = None,
    settings: Optional[ProxySettings] = None,
) -> Optional[str]:
    settings = settings if settings is not None else current_settings()
    if not settings.url:
        return None
    if conn == 'source_query' and source_needs_jp_ip(source_id):
        return settings.url
    if settings.scope == 'all' and conn in _ALL_SCOPE_CONNS:
        from core.image_host_policy import is_metatube_relay_url

        if conn == 'image' and url and is_metatube_relay_url(url):
            return None
        return settings.url
    return None


def proxy_kwargs(
    conn: Conn,
    *,
    source_id: Optional[str] = None,
    url: Optional[str] = None,
    settings: Optional[ProxySettings] = None,
) -> dict:
    """空位址／未選中 → `{}`（不是 `{'proxies': None}`）。"""
    addr = proxy_for(conn, source_id=source_id, url=url, settings=settings)
    if not addr:
        return {}
    return {'proxies': {'http': addr, 'https': addr}}


class _ProxiedSession(requests.Session):
    """每個 request 預設帶 `proxies=`；呼叫端自帶則尊重。"""

    def __init__(self, proxies: dict):
        super().__init__()
        self._policy_proxies = proxies

    def request(self, method, url, **kwargs):
        if kwargs.get('proxies') is None:
            kwargs['proxies'] = self._policy_proxies
        return super().request(method, url, **kwargs)


def new_session(
    source_id: Optional[str], *, settings: Optional[ProxySettings] = None
) -> requests.Session:
    kwargs = proxy_kwargs('source_query', source_id=source_id, settings=settings)
    if not kwargs:
        return requests.Session()
    return _ProxiedSession(kwargs['proxies'])


# ---------------------------------------------------------------------------
# 驗證視窗（Chromium / WebView2）用的代理規格（TASK-163b-T7a / CD-163b-14,16,17）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CfWindowProxy:
    """送給 Chromium 的代理規格。`server` 已去除帳密；帳密不進 repr（避免寫進 log）。"""

    server: str
    username: Optional[str] = field(default=None, repr=False)
    password: Optional[str] = field(default=None, repr=False)
    usable: bool = False


_CF_WINDOW_SCHEMES = ('http', 'https', 'socks5', 'socks5h')
_UNPARSEABLE = CfWindowProxy(server='', username=None, password=None, usable=False)


def cf_window_proxy(settings: ProxySettings) -> Optional[CfWindowProxy]:
    """驗證視窗該用的代理規格；`None` ＝ 不套任何參數（照系統代理）。

    全站唯一解析驗證視窗代理字串的地方。fail-closed：位址無法解析或 scheme 不在
    白名單 ⇒ `server=''`、`usable=False`（呼叫端不得退回系統代理或直連）。
    帳密 percent-decode（與 requests 一致）。log 不記位址與帳密。
    """
    address = proxy_for('source_query', source_id='javlibrary', settings=settings)
    if not address:
        return None
    try:
        parts = urlsplit(address)
        scheme = (parts.scheme or '').lower()
        host = parts.hostname
        port = parts.port
    except ValueError:
        return _UNPARSEABLE
    if scheme not in _CF_WINDOW_SCHEMES or not host or not port:
        return _UNPARSEABLE
    if ':' in host:
        host = f'[{host}]'
    if scheme == 'socks5h':
        scheme = 'socks5'  # Chromium 的 socks5:// 本來就由代理解析網域
    has_auth = parts.username is not None or parts.password is not None
    username = unquote(parts.username) if parts.username is not None else None
    password = unquote(parts.password) if parts.password is not None else None
    server = f'{scheme}://{host}:{port}'
    usable = not (scheme.startswith('socks5') and has_auth)
    return CfWindowProxy(server=server, username=username, password=password, usable=usable)


_UNRECORDED = object()
_cf_window_proxy_at_start = _UNRECORDED


def record_cf_window_proxy_at_start(spec: Optional[CfWindowProxy]) -> None:
    """啟動時記下一次本次啟動實際套用的規格（`None` ＝ 沒套用）；之後的呼叫忽略。"""
    global _cf_window_proxy_at_start
    if _cf_window_proxy_at_start is _UNRECORDED:
        _cf_window_proxy_at_start = spec


def cf_window_proxy_restart_needed() -> bool:
    """目前設定的有效規格與啟動時套用的不同 ⇒ 要重開才會生效。非 Windows 桌面恆 False。"""
    if desktop_kind() != 'windows':
        return False
    if _cf_window_proxy_at_start is _UNRECORDED:
        return False
    return cf_window_proxy(current_settings()) != _cf_window_proxy_at_start
