"""
單一代理選擇點（TASK-163a-T1 / CD-163a-1）。

全站唯一回答「這條連線該走哪個代理」的地方。`proxy_for()` 回 `None` ＝
沒被選到（照系統代理）。規則矩陣是 policy 內**唯一**出現 `scope` 判斷的地方。

不在列舉內的連線（metatube 本體、AI、檢查更新、CF 視窗）永遠不問這裡。
log 紀律：不記代理位址（可能含 user:pass@），要記只記 scope／種類。
頂層只 import pydantic／typing／requests；其餘 lazy（BE-LINT-09 循環面）。
"""
from __future__ import annotations

from typing import Literal, Optional

import requests
from pydantic import BaseModel, ConfigDict, field_validator

Conn = str  # 'source_query' | 'image' | 'actress'

_ALL_SCOPE_CONNS = frozenset({'source_query', 'image', 'actress'})


class ProxySettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = ''
    scope: Literal['dmm', 'all'] = 'dmm'

    @field_validator('url', mode='before')
    @classmethod
    def _strip_url(cls, v):
        return v.strip() if isinstance(v, str) else v


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
