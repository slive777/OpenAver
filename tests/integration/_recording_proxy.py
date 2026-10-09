"""
recording proxy 共用輔助（TASK-163a-T3a 起；163b-T2 搬出供兩個測試檔共用）

模組層純函式：真的 TCP recorder 只記目標 host 然後回 502（BE-TEST-43）。
"""
import contextlib
import os
import re
import socket
import threading

from core.config import load_config, save_config

# ── 來源 → host 特徵（用 host 後綴判斷是哪一家）────────────────────────────────

HOST_OF = {
    'dmm': ('dmm.co.jp', 'dmm.com'),
    'javbus': ('javbus.com',),
    'jav321': ('jav321.com',),
    'javdb': ('javdb.com', 'jdforrepam.com'),
    'd2pass': ('1pondo.tv', 'caribbeancom.com', '10musume.com'),
    'heyzo': ('heyzo.com',),
    'fc2': ('fc2.com',),
    'avsox': ('avsox.click', 'avsox.monster', 'avsox.website'),
}
ALL_SOURCES = tuple(HOST_OF)

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
        sid for sid, suffixes in HOST_OF.items()
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
