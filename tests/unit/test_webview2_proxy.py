"""TASK-163b-T7a A2：windows/webview2_proxy.py 與 standalone._build_cf_windows 接線（純 Linux，全假物件）。

sibling import 形式照 tests/unit/test_cf_transport_impl.py（standalone 也是這樣取模組）。
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest
import webview

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_DIR = str(REPO_ROOT / 'windows')
if WINDOWS_DIR not in sys.path:
    sys.path.insert(0, WINDOWS_DIR)

import standalone  # noqa: E402
import webview2_proxy  # noqa: E402
from cf_transport_impl import PyWebViewCfTransport  # noqa: E402
from core.cf_transport import CfTransportUnavailable  # noqa: E402
from core.proxy_policy import CfWindowProxy  # noqa: E402
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN  # noqa: E402

EDGE_MODULE = 'webview.platforms.edgechromium'


# ---------------------------------------------------------------------------
# 假 .NET 控制項
# ---------------------------------------------------------------------------
class FakeEvt:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        for h in list(self.handlers):
            h(*args)


class FakeProps:
    def __init__(self):
        self.UserDataFolder = 'MAIN-CACHE'
        self.AdditionalBrowserArguments = '--disable-features=ElasticOverscroll'


class FailingProps:
    AdditionalBrowserArguments = '--disable-features=ElasticOverscroll'

    @property
    def UserDataFolder(self):
        return 'x'

    @UserDataFolder.setter
    def UserDataFolder(self, value):
        raise OSError('cannot set')


class FakeCore:
    def __init__(self, fail_auth=False):
        self._fail_auth = fail_auth
        self._auth = FakeEvt()

    @property
    def BasicAuthenticationRequested(self):
        return self._auth

    @BasicAuthenticationRequested.setter
    def BasicAuthenticationRequested(self, value):
        if self._fail_auth:
            raise RuntimeError('hook failed')
        self._auth = value


class FakeBase:
    """長得像 .NET WebView2 控制項。"""

    props_factory = FakeProps
    fail_auth = False

    def __init__(self, title='OpenAver'):
        self.Parent = types.SimpleNamespace(Text=title)
        self.CreationProperties = self.props_factory()
        self.CoreWebView2InitializationCompleted = FakeEvt()
        self.CoreWebView2 = FakeCore(fail_auth=self.fail_auth)
        self.base_calls = []

    def EnsureCoreWebView2Async(self, env):
        self.base_calls.append(env)
        return 'task'


class NoParentBase(FakeBase):
    def __init__(self):
        super().__init__()
        self.Parent = None


JL_TITLE = standalone.JL_WINDOW_TITLE
JT_TITLE = standalone.JAVTEN_WINDOW_TITLE
TITLE_TO_KEY = {JL_TITLE: 'javlibrary', JT_TITLE: 'fc-javten'}


def _proxy(server='http://proxyhost:8080', username=None, password=None, usable=True):
    return CfWindowProxy(server=server, username=username, password=password, usable=usable)


@pytest.fixture
def fake_edge(monkeypatch):
    """注入假 edgechromium（兩處都要設，否則 `from webview.platforms import edgechromium` 取不到）。"""
    import webview.platforms
    fake = types.ModuleType(EDGE_MODULE)
    fake.WebView2 = FakeBase
    monkeypatch.setitem(sys.modules, EDGE_MODULE, fake)
    monkeypatch.setattr(webview.platforms, 'edgechromium', fake, raising=False)
    return fake


class _Win:
    """最小假 pywebview.Window。"""

    def __init__(self, title='', url=''):
        self.title = title
        self.url = url
        self.calls = []
        self.uid = 'fake'
        self.events = types.SimpleNamespace(closed=FakeEvt(), closing=FakeEvt())

    def load_url(self, url):
        self.calls.append(('load_url', url))

    def hide(self):
        self.calls.append(('hide',))


def _install(tmp_path, proxy, calls=None, base=FakeBase, fake_edge=None, on_ready=None):
    fake_edge.WebView2 = base
    return webview2_proxy.install(proxy, str(tmp_path / 'udf'), TITLE_TO_KEY,
                                  on_ready or (lambda key: (calls if calls is not None else []).append(key)))


# ---------------------------------------------------------------------------
# 純函式
# ---------------------------------------------------------------------------
def test_build_browser_args_keeps_existing_and_has_exactly_one_proxy_flag():
    out = webview2_proxy.build_browser_args('--disable-features=ElasticOverscroll', 'http://h:1')
    assert out.split().count('--proxy-server=http://h:1') == 1
    assert '--disable-features=ElasticOverscroll' in out.split()
    again = webview2_proxy.build_browser_args(out, 'socks5://h:2')
    assert [t for t in again.split() if t.startswith('--proxy-server=')] == ['--proxy-server=socks5://h:2']
    assert webview2_proxy.build_browser_args(None, 'http://h:1') == '--proxy-server=http://h:1'


def test_udf_dir_is_under_root_and_differs_from_main_cache():
    assert webview2_proxy.udf_dir('/data/webview') == os.path.join('/data/webview', 'cf-proxy')
    assert webview2_proxy.udf_dir('/data/webview') != '/home/u/.pywebview/main'


def test_match_window_key_only_hits_the_two_verification_titles():
    assert webview2_proxy.match_window_key(JL_TITLE, TITLE_TO_KEY) == 'javlibrary'
    assert webview2_proxy.match_window_key(JT_TITLE, TITLE_TO_KEY) == 'fc-javten'
    assert webview2_proxy.match_window_key('OpenAver', TITLE_TO_KEY) is None
    assert webview2_proxy.match_window_key(None, TITLE_TO_KEY) is None


@pytest.mark.parametrize('uri,host,port,expected', [
    ('http://proxyhost:8080/', 'proxyhost', 8080, True),
    ('http://PROXYHOST:8080', 'proxyhost', 8080, True),
    ('http://proxyhost:9999/', 'proxyhost', 8080, False),
    ('https://www.javlibrary.com/', 'proxyhost', 8080, False),
    ('http://[::1]:3128', '::1', 3128, True),
    ('garbage', 'proxyhost', 8080, False),
])
def test_is_proxy_challenge(uri, host, port, expected):
    assert webview2_proxy.is_proxy_challenge(uri, host, port) is expected


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------
def test_install_without_proxy_changes_nothing(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, EDGE_MODULE, raising=False)
    assert webview2_proxy.install(None, str(tmp_path / 'udf'), TITLE_TO_KEY, lambda k: None) is True
    assert EDGE_MODULE not in sys.modules
    assert not (tmp_path / 'udf').exists()


def test_install_clears_only_its_own_udf_dir(tmp_path, fake_edge):
    root = tmp_path / 'udf'
    (root / 'cf-proxy' / 'Default').mkdir(parents=True)
    (root / 'cf-proxy' / 'Default' / 'stale').write_text('x')
    (root / 'other.txt').write_text('keep')
    assert _install(tmp_path, _proxy(), fake_edge=fake_edge) is True
    assert (root / 'other.txt').read_text() == 'keep'
    assert root.is_dir()
    assert (root / 'cf-proxy').is_dir()
    assert not (root / 'cf-proxy' / 'Default').exists()


def test_install_returns_false_when_udf_dir_cannot_be_created(tmp_path, fake_edge):
    blocker = tmp_path / 'udf'
    blocker.write_text('a file, not a dir')
    assert _install(tmp_path, _proxy(), fake_edge=fake_edge) is False
    assert fake_edge.WebView2 is FakeBase


def test_install_returns_false_when_edge_module_cannot_be_imported(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, EDGE_MODULE, None)   # import 會拋 ImportError
    assert webview2_proxy.install(_proxy(), str(tmp_path / 'udf'), TITLE_TO_KEY, lambda k: None) is False


def test_install_returns_false_on_unexpected_class_shape(tmp_path, fake_edge):
    fake_edge.WebView2 = object()          # 不是類別
    assert webview2_proxy.install(_proxy(), str(tmp_path / 'udf'), TITLE_TO_KEY, lambda k: None) is False

    class NoMethod:
        pass

    fake_edge.WebView2 = NoMethod
    assert webview2_proxy.install(_proxy(), str(tmp_path / 'udf'), TITLE_TO_KEY, lambda k: None) is False


def test_install_returns_false_when_server_is_empty(tmp_path, fake_edge):
    assert _install(tmp_path, _proxy(server='', usable=False), fake_edge=fake_edge) is False
    assert fake_edge.WebView2 is FakeBase


# ---------------------------------------------------------------------------
# 子類行為（I-A / I-B'）
# ---------------------------------------------------------------------------
def _applied(tmp_path, fake_edge, proxy=None, base=FakeBase, ready=None):
    ready = ready if ready is not None else []
    assert _install(tmp_path, proxy or _proxy(), ready, base=base, fake_edge=fake_edge) is True
    return fake_edge.WebView2, ready


def test_main_window_is_not_touched(tmp_path, fake_edge):
    cls, ready = _applied(tmp_path, fake_edge)
    ctl = cls('OpenAver')
    ctl.EnsureCoreWebView2Async(None)
    assert ctl.base_calls == [None]
    assert ctl.CreationProperties.UserDataFolder == 'MAIN-CACHE'
    assert ctl.CreationProperties.AdditionalBrowserArguments == '--disable-features=ElasticOverscroll'
    assert ctl.CoreWebView2InitializationCompleted.handlers == []
    assert ready == []


def test_window_without_parent_is_treated_as_not_ours(tmp_path, fake_edge):
    cls, _ = _applied(tmp_path, fake_edge, base=NoParentBase)
    ctl = cls()
    ctl.EnsureCoreWebView2Async(None)
    assert ctl.CreationProperties.UserDataFolder == 'MAIN-CACHE'
    assert ctl.CoreWebView2InitializationCompleted.handlers == []


def test_verification_window_gets_udf_and_proxy_args(tmp_path, fake_edge):
    cls, _ = _applied(tmp_path, fake_edge, proxy=_proxy('socks5://px:1080'))
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async('env')
    assert ctl.base_calls == ['env']
    udf = ctl.CreationProperties.UserDataFolder
    assert udf == os.path.join(str(tmp_path / 'udf'), 'cf-proxy')
    assert udf != 'MAIN-CACHE'
    args = ctl.CreationProperties.AdditionalBrowserArguments.split()
    assert args.count('--proxy-server=socks5://px:1080') == 1
    assert '--disable-features=ElasticOverscroll' in args


def test_step1_failure_never_calls_base(tmp_path, fake_edge):
    class FailBase(FakeBase):
        props_factory = FailingProps

    cls, ready = _applied(tmp_path, fake_edge, base=FailBase)
    ctl = cls(JL_TITLE)
    assert ctl.EnsureCoreWebView2Async(None) is None
    assert ctl.base_calls == []
    assert ctl.CoreWebView2InitializationCompleted.handlers == []
    assert ctl.EnsureCoreWebView2Async(None) is None      # 第二次也不得放行到基底
    assert ctl.base_calls == []
    assert ready == []


def test_native_init_failure_never_confirms(tmp_path, fake_edge):
    cls, ready = _applied(tmp_path, fake_edge)
    ctl = cls(JT_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=False, InitializationException='boom'))
    assert ready == []


def test_native_init_success_without_auth_confirms_once(tmp_path, fake_edge):
    cls, ready = _applied(tmp_path, fake_edge)
    ctl = cls(JT_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=True))
    assert ready == ['fc-javten']


def test_override_applies_once_per_instance(tmp_path, fake_edge):
    cls, _ = _applied(tmp_path, fake_edge, proxy=_proxy(username='u', password='p'))
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.EnsureCoreWebView2Async(None)
    args = ctl.CreationProperties.AdditionalBrowserArguments.split()
    assert len([a for a in args if a.startswith('--proxy-server=')]) == 1
    assert len(ctl.CoreWebView2InitializationCompleted.handlers) == 1


def test_auth_hook_failure_never_confirms_and_never_loads_url(tmp_path, fake_edge):
    class AuthFailBase(FakeBase):
        fail_auth = True

    holder = webview2_proxy.ReadyHolder()
    win = _Win(JL_TITLE, 'about:blank')
    transport = PyWebViewCfTransport({'javlibrary': win}, {}, pending={'javlibrary'})
    holder.bind(transport)
    fake_edge.WebView2 = AuthFailBase
    assert webview2_proxy.install(_proxy(username='u', password='p'), str(tmp_path / 'udf'),
                                  TITLE_TO_KEY, holder) is True
    ctl = fake_edge.WebView2(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=True))
    assert transport.available_sites() == []
    assert [c for c in win.calls if c[0] == 'load_url'] == []


def test_auth_handler_answers_only_proxy_challenges(tmp_path, fake_edge):
    cls, ready = _applied(tmp_path, fake_edge, proxy=_proxy('http://proxyhost:8080', 'user', 'pw'))
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=True))
    assert ready == ['javlibrary']
    (handler,) = ctl.CoreWebView2.BasicAuthenticationRequested.handlers
    resp = types.SimpleNamespace(UserName=None, Password=None)
    handler(None, types.SimpleNamespace(Uri='http://proxyhost:8080/', Response=resp))
    assert (resp.UserName, resp.Password) == ('user', 'pw')


def test_auth_handler_ignores_challenges_from_other_hosts(tmp_path, fake_edge):
    cls, _ = _applied(tmp_path, fake_edge, proxy=_proxy('http://proxyhost:8080', 'user', 'pw'))
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=True))
    (handler,) = ctl.CoreWebView2.BasicAuthenticationRequested.handlers
    resp = types.SimpleNamespace(UserName=None, Password=None)
    handler(None, types.SimpleNamespace(Uri='https://www.javlibrary.com/login', Response=resp))
    assert (resp.UserName, resp.Password) == (None, None)


# ---------------------------------------------------------------------------
# 與真 transport 串起來的 oracle（I-B' ①②⑤⑥）
# ---------------------------------------------------------------------------
def _wired(tmp_path, fake_edge, proxy=None):
    holder = webview2_proxy.ReadyHolder()
    wins = {'javlibrary': _Win(JL_TITLE, 'about:blank'), 'fc-javten': _Win(JT_TITLE, 'about:blank')}
    transport = PyWebViewCfTransport(wins, {}, pending={'javlibrary', 'fc-javten'})
    holder.bind(transport)
    assert webview2_proxy.install(proxy or _proxy(), str(tmp_path / 'udf'), TITLE_TO_KEY, holder) is True
    return transport, wins, fake_edge.WebView2


def test_oracle_unavailable_before_native_init_completes(tmp_path, fake_edge):
    transport, wins, cls = _wired(tmp_path, fake_edge)
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)                 # CoreWebView2InitializationCompleted 尚未觸發
    assert transport.available_sites() == []
    for call in (
        lambda: transport.fetch('https://www.javlibrary.com/ja/', 'javlibrary'),
        lambda: transport.begin_solve('https://www.javlibrary.com/', 'javlibrary'),
        lambda: transport.is_ready('javlibrary'),
        lambda: transport.navigate_and_settle('https://javten.com/', 'fc-javten'),
    ):
        with pytest.raises(CfTransportUnavailable):
            call()
    assert all(not [c for c in w.calls if c[0] == 'load_url'] for w in wins.values())


def test_oracle_all_success_confirms_exactly_once(tmp_path, fake_edge):
    transport, wins, cls = _wired(tmp_path, fake_edge, _proxy(username='u', password='p'))
    ctl = cls(JL_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    ok = types.SimpleNamespace(IsSuccess=True)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, ok)
    ctl.CoreWebView2InitializationCompleted.fire(ctl, ok)       # 重複事件不得重複確認
    assert transport.available_sites() == ['javlibrary']
    assert all(not [c for c in w.calls if c[0] == 'load_url'] for w in wins.values())
    assert wins['javlibrary'].url == 'about:blank'


def test_oracle_close_before_confirm_does_not_revive(tmp_path, fake_edge):
    transport, wins, cls = _wired(tmp_path, fake_edge)
    ctl = cls(JT_TITLE)
    ctl.EnsureCoreWebView2Async(None)
    wins['fc-javten'].events.closed.fire()
    ctl.CoreWebView2InitializationCompleted.fire(ctl, types.SimpleNamespace(IsSuccess=True))
    assert transport.available_sites() == []


# ---------------------------------------------------------------------------
# ReadyHolder 四格
# ---------------------------------------------------------------------------
class _T:
    def __init__(self):
        self.confirmed = []

    def confirm_ready(self, key):
        self.confirmed.append(key)


def test_ready_holder_replays_confirmation_that_arrived_before_bind():
    h, t = webview2_proxy.ReadyHolder(), _T()
    h('javlibrary')
    h('fc-javten')
    assert t.confirmed == []
    h.bind(t)
    assert sorted(t.confirmed) == ['fc-javten', 'javlibrary']


def test_ready_holder_confirms_once_when_after_bind_and_when_repeated():
    h, t = webview2_proxy.ReadyHolder(), _T()
    h.bind(t)
    h('javlibrary')
    h('javlibrary')
    assert t.confirmed == ['javlibrary']
    h2, t2 = webview2_proxy.ReadyHolder(), _T()
    h2('fc-javten')
    h2('fc-javten')
    h2.bind(t2)
    h2('fc-javten')
    assert t2.confirmed == ['fc-javten']


def test_ready_holder_never_confirmed_means_nothing_available():
    h = webview2_proxy.ReadyHolder()
    t = PyWebViewCfTransport({'javlibrary': _Win()}, {}, pending={'javlibrary'})
    h.bind(t)
    assert t.available_sites() == []


# ---------------------------------------------------------------------------
# standalone._build_cf_windows 接線
# ---------------------------------------------------------------------------
class _FakeWebview:
    def __init__(self):
        self.created = []

    def create_window(self, title, url, **kwargs):
        w = _Win(title, url)
        self.created.append((title, url, kwargs, w))
        return w


@pytest.fixture
def build_env(monkeypatch, tmp_path):
    import core.cf_transport as cft
    env = types.SimpleNamespace(registered=[], installs=[], records=[], webview=_FakeWebview(), logger=_Logger())
    monkeypatch.setattr(standalone, 'webview', env.webview)
    monkeypatch.setattr(standalone, 'get_data_root', lambda: tmp_path)
    monkeypatch.setattr(standalone, 'current_settings', lambda: 'settings')
    monkeypatch.setattr(standalone, 'record_cf_window_proxy_at_start', lambda spec: env.records.append(spec))
    monkeypatch.setattr(cft, 'register_cf_transport', lambda t: env.registered.append(t))
    env.install_result = True
    env.tmp = tmp_path

    def fake_install(proxy, udf_root, title_to_key, on_ready):
        env.installs.append((proxy, udf_root, title_to_key, on_ready))
        return env.install_result

    monkeypatch.setattr(standalone, 'install_webview2_proxy', fake_install)

    def setup(kind, spec):
        monkeypatch.setattr(standalone, 'desktop_kind', lambda: kind)
        monkeypatch.setattr(standalone, 'cf_window_proxy', lambda s: spec)

    env.setup = setup
    return env


class _Logger:
    def info(self, *a, **k):
        pass

    warning = error = debug = info


def test_no_proxy_path_is_unchanged(build_env):
    build_env.setup('windows', None)
    jl, jt = standalone._build_cf_windows(build_env.logger)
    urls = {t: u for t, u, _, _ in build_env.webview.created}
    assert urls == {JL_TITLE: JAVLIBRARY_ORIGIN, JT_TITLE: 'about:blank'}
    (transport,) = build_env.registered
    assert transport._pending == set()
    assert transport._origins['javlibrary'] == transport._origin(JAVLIBRARY_ORIGIN)
    assert transport.available_sites() == ['fc-javten', 'javlibrary']
    assert build_env.records == [None]
    assert jl is not None and jt is not None


def test_applied_proxy_windows_start_on_blank_and_unseeded(build_env):
    build_env.setup('windows', _proxy())
    standalone._build_cf_windows(build_env.logger)
    urls = {t: u for t, u, _, _ in build_env.webview.created}
    assert urls == {JL_TITLE: 'about:blank', JT_TITLE: 'about:blank'}
    (transport,) = build_env.registered
    assert transport._origins['javlibrary'] is None
    assert transport._pending == {'javlibrary', 'fc-javten'}
    assert transport.available_sites() == []
    proxy, udf_root, title_to_key, on_ready = build_env.installs[0]
    assert proxy == _proxy()
    assert udf_root == str(build_env.tmp / 'webview')       # 資料根底下，不在 repo
    on_ready('javlibrary')
    assert transport.available_sites() == ['javlibrary']
    assert build_env.records == [_proxy()]


def test_title_map_covers_every_created_window(build_env):
    build_env.setup('windows', _proxy())
    standalone._build_cf_windows(build_env.logger)
    created_titles = {t for t, _, _, _ in build_env.webview.created}
    title_to_key = build_env.installs[0][2]
    assert set(title_to_key) == created_titles
    assert set(title_to_key.values()) == {'javlibrary', 'fc-javten'}


def test_install_failure_creates_no_verification_windows(build_env):
    build_env.install_result = False
    build_env.setup('windows', _proxy())
    jl, jt = standalone._build_cf_windows(build_env.logger)
    assert build_env.webview.created == []
    assert (jl, jt) == (None, None)
    (transport,) = build_env.registered
    assert transport.available_sites() == []
    assert build_env.records == [_proxy()]       # install 失敗仍記錄


def test_mac_never_touches_proxy_machinery(build_env, monkeypatch):
    build_env.setup('mac', _proxy())
    called = []
    monkeypatch.setattr(standalone, 'cf_window_proxy', lambda s: called.append(1))
    standalone._build_cf_windows(build_env.logger)
    assert build_env.installs == [] and build_env.records == [] and called == []
    urls = {t: u for t, u, _, _ in build_env.webview.created}
    assert urls == {JL_TITLE: JAVLIBRARY_ORIGIN, JT_TITLE: 'about:blank'}
    (transport,) = build_env.registered
    assert transport._pending == set()


def test_unreadable_proxy_spec_fails_closed(build_env, monkeypatch):
    build_env.setup('windows', None)

    def boom(s):
        raise RuntimeError('config broken')

    monkeypatch.setattr(standalone, 'cf_window_proxy', boom)
    standalone._build_cf_windows(build_env.logger)
    assert build_env.webview.created == []
    (transport,) = build_env.registered
    assert transport.available_sites() == []
