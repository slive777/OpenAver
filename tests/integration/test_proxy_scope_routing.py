"""
代理範圍路由 — recording proxy 整合測試（TASK-163a-T3a）

oracle 是兩個真的 TCP recorder 實際收到的連線，不是 mock 呼叫次數：
  POL = 設定頁 Proxy 欄填的位址（被 proxy policy 選中的連線才會到這裡）
  SYS = 系統代理（環境變數）——接住「沒被選中」的連線，這樣測試不會真的連外站

recorder 一律綁 127.0.0.1、對每條連線只記目標 host 然後回 502（BE-TEST-43）。
輔助函式做成模組層純函式，T4 追加非 scraper 連線時直接重用。
"""
import contextlib
import os
import re
import socket
import threading
from unittest.mock import patch

import pytest

from core.config import load_config, save_config

# ── 來源 → host 特徵（用 host 後綴判斷是哪一家）────────────────────────────────

_HOST_OF = {
    'dmm': ('dmm.co.jp', 'dmm.com'),
    'javbus': ('javbus.com',),
    'jav321': ('jav321.com',),
    'javdb': ('javdb.com', 'jdforrepam.com'),
    'd2pass': ('1pondo.tv', 'caribbeancom.com', '10musume.com'),
    'heyzo': ('heyzo.com',),
    'fc2': ('fc2.com',),
    'avsox': ('avsox.click', 'avsox.monster', 'avsox.website'),
}
ALL_SOURCES = tuple(_HOST_OF)

_NUMBER_OF = {
    'dmm': 'SONE-205',
    'javbus': 'SONE-205',
    'jav321': 'SONE-205',
    'javdb': 'SONE-205',
    'd2pass': '012523-001',
    'heyzo': 'HEYZO-0783',
    'fc2': 'FC2-1234567',
    'avsox': '012523-001',
}

_HOST_RE = re.compile(r'^(?:CONNECT\s+([^\s:/]+)(?::\d+)?|[A-Z]+\s+https?://([^\s:/]+))', re.I)


# ── 模組層純函式：recording proxy ─────────────────────────────────────────────

def start_recording_proxy():
    """起一個綁 127.0.0.1 的 recorder。回 (url, hosts_fn, stop_fn)。

    認 `CONNECT host:443`（https）與 absolute-URI `GET http://host/…`（http），
    記下 host、回 502 關線。
    """
    stop = threading.Event()
    hosts: list[str] = []
    lock = threading.Lock()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen(64)
    sock.settimeout(0.2)
    port = sock.getsockname()[1]

    def _loop():
        while not stop.is_set():
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.settimeout(2.0)
                data = b''
                while b'\r\n' not in data and len(data) < 8192:
                    chunk = conn.recv(2048)
                    if not chunk:
                        break
                    data += chunk
                first = data.split(b'\r\n', 1)[0].decode('ascii', errors='replace')
                m = _HOST_RE.match(first)
                if m:
                    with lock:
                        hosts.append((m.group(1) or m.group(2)).lower())
                conn.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            finally:
                with contextlib.suppress(OSError):
                    conn.close()

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()

    def _hosts() -> set[str]:
        with lock:
            return set(hosts)

    def _stop():
        stop.set()
        with contextlib.suppress(OSError):
            sock.close()
        thread.join(timeout=2)

    return f'http://127.0.0.1:{port}', _hosts, _stop


def sources_seen(hosts: set[str]) -> set[str]:
    """把 recorder 看到的 host 歸回是哪幾家來源。"""
    return {
        sid for sid, suffixes in _HOST_OF.items()
        if any(h == s or h.endswith('.' + s) for h in hosts for s in suffixes)
    }


def clear_proxy_env(monkeypatch) -> None:
    """清乾淨所有 *_proxy 環境變數（含 NO_PROXY），避免本機殘留讓結果漂移。"""
    for name in [n for n in os.environ if n.lower().endswith('_proxy')]:
        monkeypatch.delenv(name, raising=False)


def set_system_proxy(monkeypatch, url: str) -> None:
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
        monkeypatch.setenv(name, url)


def write_search_config(*, proxy_url: str, scope: str, dmm_enabled: bool = True) -> None:
    cfg = load_config()
    cfg.setdefault('search', {})
    cfg['search']['proxy_url'] = proxy_url
    cfg['search']['proxy_scope'] = scope
    for s in cfg.get('sources', []):
        if isinstance(s, dict) and s.get('id') == 'dmm':
            s['enabled'] = dmm_enabled
    save_config(cfg)


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def recorders(monkeypatch, temp_config_path):
    """POL／SYS 兩個 recorder；系統代理指向 SYS；rate limit 全關。"""
    clear_proxy_env(monkeypatch)
    pol_url, pol_hosts, pol_stop = start_recording_proxy()
    sys_url, sys_hosts, sys_stop = start_recording_proxy()
    set_system_proxy(monkeypatch, sys_url)

    import core.scrapers.utils as utils_mod
    monkeypatch.setattr(utils_mod, 'rate_limit', lambda *a, **kw: None)
    for mod in ('dmm', 'javbus', 'jav321', 'javdb', 'd2pass', 'heyzo', 'fc2_official', 'avsox'):
        m = __import__(f'core.scrapers.{mod}', fromlist=['x'])
        if hasattr(m, 'rate_limit'):
            monkeypatch.setattr(m, 'rate_limit', lambda *a, **kw: None)

    class _R:
        pol = pol_url
        sys = sys_url

        @staticmethod
        def pol_sources():
            return sources_seen(pol_hosts())

        @staticmethod
        def sys_sources():
            return sources_seen(sys_hosts())

        @staticmethod
        def pol_hosts():
            return pol_hosts()

        @staticmethod
        def sys_hosts():
            return sys_hosts()

    try:
        yield _R
    finally:
        pol_stop()
        sys_stop()


def _drive_source(sid: str, *, post_reaches_network: bool = False) -> None:
    """用該來源合法的番號打一次 search()；502 被吞或拋出都無所謂。

    jav321 預設只驅動「詳情頁 GET」；要驅動「搜尋 POST」傳 post_reaches_network=True。"""
    from core.scrapers import (
        DMMScraper, JavBusScraper, JAV321Scraper, JavDBScraper,
        D2PassScraper, HEYZOScraper, FC2OfficialScraper, AVSOXScraper,
    )
    cls = {
        'dmm': DMMScraper, 'javbus': JavBusScraper, 'jav321': JAV321Scraper,
        'javdb': JavDBScraper, 'd2pass': D2PassScraper, 'heyzo': HEYZOScraper,
        'fc2': FC2OfficialScraper, 'avsox': AVSOXScraper,
    }[sid]
    if sid == 'jav321' and not post_reaches_network:
        # 搜尋 POST 一被 502 就提早結束、永遠走不到詳情頁 GET。讓 POST 回一頁有結果的 HTML
        # （不經網路），這樣 search() 才會真的對詳情頁發 GET——那條路徑也要被代理範圍涵蓋。
        fake = '<div class="row"><a href="/video/sone00205">x</a></div>'
        with patch('core.scrapers.jav321.post_html', return_value=fake), \
                contextlib.suppress(Exception):
            cls().search(_NUMBER_OF[sid])
        return
    with contextlib.suppress(Exception):
        cls().search(_NUMBER_OF[sid])


def _drive_all() -> None:
    for sid in ALL_SOURCES:
        _drive_source(sid)


# ── 八家來源查詢 ──────────────────────────────────────────────────────────────

def test_scope_dmm_only_dmm_via_policy(recorders):
    """「僅 DMM」：POL 只有 DMM；其餘七家照系統代理（SYS）；DMM 不在 SYS（AC-5c）。"""
    write_search_config(proxy_url=recorders.pol, scope='dmm')
    _drive_all()

    assert recorders.pol_sources() == {'dmm'}, recorders.pol_hosts()
    assert recorders.sys_sources() >= set(ALL_SOURCES) - {'dmm'}, recorders.sys_hosts()
    assert 'dmm' not in recorders.sys_sources()


def test_scope_all_every_source_via_policy(recorders):
    """「所有來源」：八家（含 javdb 網頁＋App 兩通道）全走 POL，系統代理一筆都沒有。"""
    write_search_config(proxy_url=recorders.pol, scope='all')
    _drive_all()

    assert recorders.pol_sources() == set(ALL_SOURCES), recorders.pol_hosts()
    # javdb 兩條通道都要看到：App 資料介面 host 與網頁 host
    assert {'jdforrepam.com', 'javdb.com'} <= recorders.pol_hosts()
    assert recorders.sys_hosts() == set()


def test_blank_proxy_nothing_via_policy(recorders):
    """Proxy 欄空白：POL 一筆都沒有，八家全照系統代理。"""
    write_search_config(proxy_url='', scope='all')
    _drive_all()

    assert recorders.pol_hosts() == set()
    assert recorders.sys_sources() == set(ALL_SOURCES), recorders.sys_hosts()


# ── 女優名搜尋（DMM 開關只看膠囊）─────────────────────────────────────────────

def _run_actress_search() -> None:
    from core.scraper import search_actress
    with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus']), \
            contextlib.suppress(Exception):
        search_actress('三上悠亜', limit=3)


def test_capsule_off_actress_search_never_reaches_dmm(recorders):
    """DMM 膠囊關 ＋ Proxy 欄有填：女優名搜尋不碰 DMM（POL、SYS 都沒有），JavBus 仍被問。"""
    write_search_config(proxy_url=recorders.pol, scope='dmm', dmm_enabled=False)
    _run_actress_search()

    assert 'dmm' not in recorders.pol_sources()
    assert 'dmm' not in recorders.sys_sources()
    assert 'javbus' in recorders.sys_sources(), recorders.sys_hosts()


def test_capsule_on_blank_proxy_actress_search_reaches_dmm(recorders):
    """DMM 膠囊開 ＋ Proxy 欄空白：女優名搜尋照樣問 DMM（走系統代理，AC-5b）。"""
    write_search_config(proxy_url='', scope='dmm', dmm_enabled=True)
    _run_actress_search()

    assert 'dmm' in recorders.sys_sources(), recorders.sys_hosts()
    assert recorders.pol_hosts() == set()


def test_scope_all_jav321_search_post_via_policy(recorders):
    """「所有來源」：Jav321 的搜尋 POST 也走代理（與詳情頁 GET 是兩條不同呼叫）。"""
    write_search_config(proxy_url=recorders.pol, scope='all')
    _drive_source('jav321', post_reaches_network=True)

    assert recorders.pol_sources() == {'jav321'}, recorders.pol_hosts()
    assert recorders.sys_hosts() == set()
