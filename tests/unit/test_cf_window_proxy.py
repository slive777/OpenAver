"""TASK-163b-T7a A1：驗證視窗的代理規格（core 層，純 Linux 可測）。"""
import pytest

from core import proxy_policy
from core.desktop_env import desktop_kind
from core.proxy_policy import (
    CfWindowProxy,
    ProxySettings,
    cf_window_proxy,
    cf_window_proxy_restart_needed,
    record_cf_window_proxy_at_start,
)


def _spec(server, username=None, password=None, usable=True):
    return CfWindowProxy(server=server, username=username, password=password, usable=usable)


# (url, scope, expected)
_TABLE = [
    ('http://h:1', 'all', _spec('http://h:1')),
    ('https://h:2', 'all', _spec('https://h:2')),
    ('https://u:p@h:1', 'all', _spec('https://h:1', 'u', 'p')),
    ('https://u:p%40ss@h:3', 'all', _spec('https://h:3', 'u', 'p@ss')),
    ('socks5://h:4', 'all', _spec('socks5://h:4')),
    ('socks5h://h:5', 'all', _spec('socks5://h:5')),
    ('socks5://u:p@h:6', 'all', _spec('socks5://h:6', 'u', 'p', usable=False)),
    ('socks5h://u:p@h:7', 'all', _spec('socks5://h:7', 'u', 'p', usable=False)),
    ('http://[::1]:8', 'all', _spec('http://[::1]:8')),
    # 無法解析：fail-closed，server 為空字串、usable=False
    ('h:1', 'all', _spec('', usable=False)),
    ('://', 'all', _spec('', usable=False)),
    ('http://', 'all', _spec('', usable=False)),
    ('http://h', 'all', _spec('', usable=False)),
    ('ftp://h:1', 'all', _spec('', usable=False)),
    # 沒被選到
    ('http://h:1', 'dmm', None),
    ('', 'all', None),
    ('', 'dmm', None),
]


@pytest.mark.parametrize('url,scope,expected', _TABLE)
def test_cf_window_proxy_scope_and_credentials_table(url, scope, expected):
    got = cf_window_proxy(ProxySettings(url=url, scope=scope))
    assert got == expected
    if got is not None:
        assert '@' not in got.server
        assert 'p%40ss' not in got.server and 'p@ss' not in got.server


def test_cf_window_proxy_repr_hides_credentials():
    got = cf_window_proxy(ProxySettings(url='https://zeduser:secretpw@h:1', scope='all'))
    assert 'secretpw' not in repr(got)
    assert 'zeduser' not in repr(got)


@pytest.fixture
def windows_desktop(monkeypatch):
    monkeypatch.setattr(proxy_policy, 'desktop_kind', lambda: 'windows')


def _set_state(monkeypatch, start, url, scope):
    monkeypatch.setattr(proxy_policy, '_cf_window_proxy_at_start', start)
    monkeypatch.setattr(proxy_policy, 'current_settings',
                        lambda: ProxySettings(url=url, scope=scope))


def test_restart_needed_follows_effective_spec(monkeypatch, windows_desktop):
    # ① 啟動時沒套用，現在存成「所有來源＋位址」
    _set_state(monkeypatch, None, 'http://h:1', 'all')
    assert cf_window_proxy_restart_needed() is True
    # ② 啟動時套用 X，存成同一個位址（先改別的再改回也是同一個有效規格）
    x = cf_window_proxy(ProxySettings(url='http://h:1', scope='all'))
    _set_state(monkeypatch, x, 'http://other:9', 'all')
    assert cf_window_proxy_restart_needed() is True
    _set_state(monkeypatch, x, 'http://h:1', 'all')
    assert cf_window_proxy_restart_needed() is False
    # ③ 「僅 DMM」與「欄位空白」之間切換：有效規格都是 None
    _set_state(monkeypatch, None, 'http://h:1', 'dmm')
    assert cf_window_proxy_restart_needed() is False
    _set_state(monkeypatch, None, '', 'all')
    assert cf_window_proxy_restart_needed() is False
    # 啟動時套用 X，之後改成「僅 DMM」→ 要重開才會移除
    _set_state(monkeypatch, x, 'http://h:1', 'dmm')
    assert cf_window_proxy_restart_needed() is True


@pytest.mark.parametrize('kind', ['mac', None])
def test_restart_needed_false_unless_windows_desktop(monkeypatch, kind):
    monkeypatch.setattr(proxy_policy, 'desktop_kind', lambda: kind)
    _set_state(monkeypatch, None, 'http://h:1', 'all')
    assert cf_window_proxy_restart_needed() is False


def test_restart_needed_false_on_mac_even_with_registered_transport(monkeypatch):
    from core import cf_transport

    prev = cf_transport.get_cf_transport()
    cf_transport.register_cf_transport(object())
    try:
        monkeypatch.setattr(proxy_policy, 'desktop_kind', lambda: 'mac')
        _set_state(monkeypatch, None, 'http://h:1', 'all')
        assert cf_window_proxy_restart_needed() is False
    finally:
        cf_transport.register_cf_transport(prev)


def test_restart_needed_false_when_start_spec_never_recorded(monkeypatch, windows_desktop):
    monkeypatch.setattr(proxy_policy, '_cf_window_proxy_at_start', proxy_policy._UNRECORDED)
    monkeypatch.setattr(proxy_policy, 'current_settings',
                        lambda: ProxySettings(url='http://h:1', scope='all'))
    assert cf_window_proxy_restart_needed() is False


def test_record_at_start_writes_once_and_records_none(monkeypatch, windows_desktop):
    monkeypatch.setattr(proxy_policy, '_cf_window_proxy_at_start', proxy_policy._UNRECORDED)
    monkeypatch.setattr(proxy_policy, 'current_settings',
                        lambda: ProxySettings(url='http://h:1', scope='all'))
    record_cf_window_proxy_at_start(None)           # 啟動時沒套用 = 記下 None
    assert cf_window_proxy_restart_needed() is True
    x = cf_window_proxy(ProxySettings(url='http://h:1', scope='all'))
    record_cf_window_proxy_at_start(x)              # 第二次忽略
    assert cf_window_proxy_restart_needed() is True


@pytest.mark.parametrize('env,platform,expected', [
    ('1', 'win32', 'windows'),
    ('1', 'darwin', 'mac'),
    ('1', 'linux', None),
    ('0', 'win32', None),
    (None, 'win32', None),
    (None, 'darwin', None),
])
def test_desktop_kind_truth_table(monkeypatch, env, platform, expected):
    if env is None:
        monkeypatch.delenv('OPENAVER_STANDALONE', raising=False)
    else:
        monkeypatch.setenv('OPENAVER_STANDALONE', env)
    monkeypatch.setattr('sys.platform', platform)
    assert desktop_kind() == expected
