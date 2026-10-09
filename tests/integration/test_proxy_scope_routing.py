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


# ── 非 scraper 連線（TASK-163a-T4）：封面／劇照／書籤封面／女優照片與四個女優來源 ──────

_RELAY_BASE = 'http://metatube.test:8900'
_RELAY_URL = _RELAY_BASE + '/v1/images/primary/ABC-123?url=https%3A%2F%2Fcdn.example.com%2Fa.jpg'


def _clear_failed_hosts() -> None:
    """organizer._failed_hosts 是模組級狀態：502 會把原址 host 記成失敗，後續格會跳過原址。"""
    import core.organizer as org
    with org._failed_hosts_lock:
        org._failed_hosts.clear()


@pytest.fixture
def metatube_relay_connected():
    from core.metatube.state import metatube_state
    metatube_state.connect(_RELAY_BASE, '', [])
    try:
        yield
    finally:
        metatube_state.disconnect()


@pytest.fixture
def photo_dir(tmp_path, monkeypatch):
    """actress_photo 下載前會 mkdir GFRIENDS_DIR：導到 tmp，不碰真實資料夾。"""
    import core.actress_photo as ap
    monkeypatch.setattr(ap, 'GFRIENDS_DIR', tmp_path / 'gfriends')
    return tmp_path


def _drive_organizer(tmp_path, url, fallback_url=''):
    import core.organizer as org
    _clear_failed_hosts()
    with contextlib.suppress(Exception):
        org.download_image(url, str(tmp_path / 'o.jpg'), fallback_url=fallback_url)


def _drive_wishlist(url, fallback_url=''):
    from core import wishlist_cover_cache as wcc
    with contextlib.suppress(Exception):
        wcc.download_and_save('ABC-123', url, fallback_url)


def _drive_proxy_image(url):
    from fastapi.testclient import TestClient
    from web.app import app
    with contextlib.suppress(Exception):
        TestClient(app).get('/api/proxy-image', params={'url': url})


def _drive_embed(url):
    from web.routers.scanner import _embed_cover
    with contextlib.suppress(Exception):
        _embed_cover(url)


def _drive_actress_photo(url):
    from core.actress_photo import download_actress_photo
    with contextlib.suppress(Exception):
        download_actress_photo('テスト女優', url, 'graphis')


def _drive_graphis():
    from core.scrapers.actress.graphis import scrape_graphis_photo
    with contextlib.suppress(Exception):
        scrape_graphis_photo('テスト')


def _drive_wiki_ja():
    from core.scrapers.actress.wiki_ja import scrape_wiki_ja
    with contextlib.suppress(Exception):
        scrape_wiki_ja('テスト')


def _drive_xcity():
    from core.scrapers.actress.xcity import scrape_xcity
    with contextlib.suppress(Exception):
        scrape_xcity('テスト')


def _drive_gfriends():
    from core.scrapers.actress.gfriends import _check_gfriends_url
    with contextlib.suppress(Exception):
        _check_gfriends_url('7-S1', 'テスト')


def _graphis_photo_host() -> str:
    from core.image_host_policy import download_hosts_for
    return sorted(download_hosts_for('graphis'))[0]


def _sink_table():
    """(sink 名, 驅動函式(tmp_path)->None, 該 sink 一定會連到的 host)。九個進入點。"""
    gh = _graphis_photo_host()
    return [
        ('organizer.download_image',
         lambda p: _drive_organizer(p, 'https://img-org.test/a.jpg'), 'img-org.test'),
        ('wishlist_cover_cache.download_and_save',
         lambda p: _drive_wishlist('https://img-wish.test/a.jpg'), 'img-wish.test'),
        ('GET /api/proxy-image',
         lambda p: _drive_proxy_image('https://pics.dmm.co.jp/a.jpg'), 'pics.dmm.co.jp'),
        ('scanner._embed_cover',
         lambda p: _drive_embed('https://img-embed.test/a.jpg'), 'img-embed.test'),
        ('actress_photo.download_actress_photo',
         lambda p: _drive_actress_photo(f'https://{gh}/a.jpg'), gh),
        ('graphis.scrape_graphis_photo',
         lambda p: _drive_graphis(),
         'graphis.ne.jp'),
        ('wiki_ja.scrape_wiki_ja',
         lambda p: _drive_wiki_ja(),
         'ja.wikipedia.org'),
        ('xcity.scrape_xcity',
         lambda p: _drive_xcity(),
         'xcity.jp'),
        ('gfriends._check_gfriends_url',
         lambda p: _drive_gfriends(),
         'cdn.jsdelivr.net'),
    ]


_SINK_IDS = [s[0] for s in _sink_table()]


@pytest.mark.parametrize('scope', ['dmm', 'all', 'blank'])
@pytest.mark.parametrize('idx', range(len(_SINK_IDS)), ids=_SINK_IDS)
def test_every_sink_follows_scope(recorders, photo_dir, idx, scope):
    """九個非 scraper 進入點：all → 只走 POL；dmm／Proxy 欄空白 → 只走系統代理。"""
    _, drive, host = _sink_table()[idx]
    write_search_config(
        proxy_url='' if scope == 'blank' else recorders.pol,
        scope='all' if scope == 'all' else 'dmm',
    )
    drive(photo_dir)

    if scope == 'all':
        assert host in recorders.pol_hosts(), (recorders.pol_hosts(), recorders.sys_hosts())
        assert host not in recorders.sys_hosts()
    else:
        assert host in recorders.sys_hosts(), (recorders.pol_hosts(), recorders.sys_hosts())
        assert host not in recorders.pol_hosts()


@pytest.mark.parametrize('scope', ['dmm', 'all'])
@pytest.mark.parametrize('position', ['wishlist_primary', 'organizer_fallback', 'proxy_image'])
def test_metatube_relay_never_via_policy_proxy(
    recorders, metatube_relay_connected, photo_dir, position, scope
):
    """metatube 中轉圖（區網）任何模式都不進外部代理；同一格的非中轉圖在 all 才走 POL。"""
    write_search_config(proxy_url=recorders.pol, scope=scope)
    plain_host = 'img-plain.test'
    plain = f'https://{plain_host}/a.jpg'
    if position == 'wishlist_primary':
        _drive_wishlist(_RELAY_URL, plain)
    elif position == 'organizer_fallback':
        _drive_organizer(photo_dir, plain, fallback_url=_RELAY_URL)
    else:
        plain_host = 'pics.dmm.co.jp'
        _drive_proxy_image(_RELAY_URL)
        _drive_proxy_image(f'https://{plain_host}/a.jpg')

    relay_host = 'metatube.test'
    assert relay_host in recorders.sys_hosts(), (recorders.pol_hosts(), recorders.sys_hosts())
    assert relay_host not in recorders.pol_hosts()
    if scope == 'all':
        assert plain_host in recorders.pol_hosts(), (recorders.pol_hosts(), recorders.sys_hosts())
        assert plain_host not in recorders.sys_hosts()
    else:
        assert plain_host in recorders.sys_hosts(), (recorders.pol_hosts(), recorders.sys_hosts())
        assert plain_host not in recorders.pol_hosts()


def test_excluded_connections_never_asked_policy(recorders):
    """「所有來源」：metatube 本體與 AI（Ollama）連線永遠照系統代理，Proxy 欄的位址一筆都收不到。"""
    from core.metatube.client import MetatubeHttpClient
    from fastapi.testclient import TestClient
    from web.app import app

    write_search_config(proxy_url=recorders.pol, scope='all')
    with contextlib.suppress(Exception):
        MetatubeHttpClient(_RELAY_BASE).list_providers()
    with contextlib.suppress(Exception):
        TestClient(app).get('/api/ollama/models', params={'url': 'http://ollama.test:11434'})

    assert {'metatube.test', 'ollama.test'} <= recorders.sys_hosts(), recorders.sys_hosts()
    assert recorders.pol_hosts() == set()
