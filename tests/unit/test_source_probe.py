"""core/source_probe.py — 判讀／合併／並行／預算／快照／skipped／不洩漏（TASK-163b-T1）。

全用假 scraper 類別（注入 scraper_class_for）與假 send，不打網路。
"""
import io
import json
import threading
import time

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from core import source_probe as sp
from core.proxy_policy import ProxySettings
from core.source_probe import (
    ProbeOutcome, ProbePlan, ProbeTarget, classify_exception, classify_http,
    merge_outcomes, run_probes,
)

PROXY = 'http://jp.example:8080'
JSD = b'<html><script src="/cdn-cgi/challenge-platform/scripts/jsd/api.js"></script></html>'
SIX_KEYS = {'state', 'reason', 'host', 'status', 'via_proxy', 'advice'}


def make_resp(status=200, headers=None, body=b'<html>ok</html>'):
    r = requests.Response()
    r.status_code = status
    r.headers = CaseInsensitiveDict(headers or {})
    r.raw = io.BytesIO(body)
    r.url = 'https://x.example/'
    return r


def _t(host='h.example', send=None, **kw):
    return ProbeTarget(host=host, send=send or (lambda: make_resp()), **kw)


class FakeScraper:
    """只需 __init__(config) 與 probe_plan(timeout)；不繼承 BaseScraper。"""
    plans = {}
    seen = {}
    source_id = None

    def __init__(self, config):
        type(self).seen[type(self).source_id] = config.proxy_settings

    def probe_plan(self, timeout):
        return type(self).plans.get(type(self).source_id)


@pytest.fixture
def fake_classes(monkeypatch):
    """回 (plans, seen)；scraper_class_for 依 id 回各自的假類別。"""
    plans, seen = {}, {}

    def _cls(sid):
        return type('Fake_' + sid, (FakeScraper,), {'source_id': sid, 'plans': plans, 'seen': seen})

    monkeypatch.setattr('core.source_probe.scraper_class_for', _cls)
    return plans, seen


# ------------------------------------------------------------ 判讀

@pytest.mark.parametrize('label,status,headers,head,ok_404,expect', [
    ('200', 200, {}, b'', False, ('ok', 'ok')),
    ('200_cloudflare_server', 200, {'server': 'cloudflare'}, b'', False, ('ok', 'ok')),
    ('200_jsd_script', 200, {'server': 'cloudflare'}, JSD, False, ('ok', 'ok')),
    ('404_ok404', 404, {}, b'', True, ('ok', 'ok')),
    ('410_ok404', 410, {}, b'', True, ('ok', 'ok')),
    ('404_strict', 404, {}, b'', False, ('blocked', 'http_status')),
    ('500', 500, {}, b'', False, ('blocked', 'http_status')),
    ('500_ok404', 500, {}, b'', True, ('blocked', 'http_status')),
    ('403_plain', 403, {}, b'', False, ('blocked', 'http_status')),
    ('403_cf_server', 403, {'server': 'cloudflare'}, b'', False, ('blocked', 'cf_challenge')),
    ('503_cf_body', 503, {}, b'<title>Just a moment...</title>', False, ('blocked', 'cf_challenge')),
    ('403_jsd_body', 403, {}, JSD, False, ('blocked', 'cf_challenge')),
    ('200_mitigated', 200, {'cf-mitigated': 'challenge'}, b'', False, ('blocked', 'cf_challenge')),
    ('403_mitigated', 403, {'CF-Mitigated': 'Challenge'}, b'', False, ('blocked', 'cf_challenge')),
])
def test_classify_http_by_response_kind(label, status, headers, head, ok_404, expect):
    hdrs = {k.lower(): v for k, v in headers.items()}
    assert classify_http(status, hdrs, head, ok_404) == expect, label


def _conn_err_with(reason):
    inner = type('Inner', (Exception,), {'reason': reason})()
    return requests.exceptions.ConnectionError(inner)


@pytest.mark.parametrize('exc,expect', [
    (requests.exceptions.ProxyError('boom'), 'proxy'),
    (requests.exceptions.InvalidProxyURL('bad'), 'proxy'),
    (requests.exceptions.InvalidSchema('bad'), 'proxy'),
    (requests.exceptions.ConnectTimeout('t'), 'timeout'),
    (requests.exceptions.ReadTimeout('t'), 'timeout'),
    (requests.exceptions.ConnectionError(sp.ReadTimeoutError(None, None, 'x')), 'timeout'),
    (requests.exceptions.SSLError('s'), 'tls'),
    (_conn_err_with(sp.NameResolutionError('h', None, 'x')), 'dns'),
    (requests.exceptions.ConnectionError('refused'), 'network'),
    (requests.exceptions.ChunkedEncodingError('c'), 'network'),
    (ValueError('x'), 'error'),
    (KeyError('x'), 'error'),
])
def test_classify_exception_by_exception_type(exc, expect):
    assert classify_exception(exc) == expect


def O(state, host='h'):
    return ProbeOutcome(state, state, host, None)


@pytest.mark.parametrize('mode,states,expect_state,expect_host', [
    ('any', ['unreachable', 'blocked', 'ok'], 'ok', 'h2'),
    ('any', ['unreachable', 'blocked'], 'blocked', 'h1'),
    ('all', ['ok', 'blocked', 'unreachable'], 'unreachable', 'h2'),
    ('all', ['ok', 'blocked'], 'blocked', 'h1'),
    ('all', ['ok', 'ok'], 'ok', 'h0'),
])
def test_merge_outcomes_any_takes_best_all_takes_worst(mode, states, expect_state, expect_host):
    outs = [O(s, f'h{i}') for i, s in enumerate(states)]
    merged = merge_outcomes(mode, outs)
    assert (merged.state, merged.host) == (expect_state, expect_host)


# ------------------------------------------------------------ 讀取 / check

def test_check_only_judges_complete_body(fake_classes):
    plans, _ = fake_classes
    calls = []

    def check(pr):
        calls.append(pr.body_complete)
        return False

    plans['javdb'] = ProbePlan([ProbeTarget('j', lambda: make_resp(body=b'{}'),
                                            check=check, read='full_capped')])
    plans['dmm'] = ProbePlan([ProbeTarget('d', lambda: make_resp(body=b'x' * (sp.FULL_LIMIT + 10)),
                                          check=check, read='full_capped')])
    rows = run_probes(ProxySettings(), ['javdb', 'dmm'])
    assert rows['javdb']['reason'] == 'app_rejected'
    assert rows['dmm']['state'] == 'ok'  # 超過上限＝判通、不解析
    assert calls == [True]


class _BrokenBody(io.BytesIO):
    def read(self, *a, **k):
        raise OSError('body broke')


def _broken_resp(status, headers=None):
    r = make_resp(status, headers)
    r.raw = _BrokenBody(b'x')
    return r


class _EndlessBody:
    """永不結束的 body，並記錄被讀了幾次。"""
    def __init__(self):
        self.reads = 0

    def read(self, n=-1, *a, **k):
        self.reads += 1
        if self.reads > 50:
            raise AssertionError('讀超過上限仍不停')
        return b'x' * 8192

    def stream(self, amt=8192, decode_content=None):
        while True:
            yield self.read(amt)

    def close(self):
        pass

    def release_conn(self):
        pass


def _run_one(fake_classes, send):
    plans, _ = fake_classes
    plans['dmm'] = ProbePlan([ProbeTarget('d.example', send)])
    return run_probes(ProxySettings(), ['dmm'])['dmm']


def test_head8k_200_does_not_read_body_failure_is_still_ok(fake_classes):
    row = _run_one(fake_classes, lambda: _broken_resp(200))
    assert (row['state'], row['reason']) == ('ok', 'ok')


def test_head8k_non_2xx_body_read_failure_keeps_status_header_verdict(fake_classes):
    row = _run_one(fake_classes, lambda: _slow_resp(403, {'server': 'cloudflare'}))
    assert (row['state'], row['reason']) == ('blocked', 'cf_challenge')
    row = _run_one(fake_classes, lambda: _slow_resp(403))
    assert (row['state'], row['reason']) == ('blocked', 'http_status')


def test_head8k_endless_200_body_is_ok_and_unread(fake_classes):
    body = _EndlessBody()

    def send():
        r = make_resp(200)
        r.raw = body
        return r

    assert _run_one(fake_classes, send)['state'] == 'ok'
    assert body.reads == 0


def test_full_capped_stream_read_timeout_is_timeout(fake_classes):
    class _Slow(_BrokenBody):
        def stream(self, amt=8192, decode_content=None):  # requests 走 stream 分支才會包裝
            raise sp.ReadTimeoutError(None, None, 'slow')

    def send():
        r = make_resp(200)
        r.raw = _Slow(b'')
        return r

    plans, _ = fake_classes
    plans['javdb'] = ProbePlan([ProbeTarget('j', send, read='full_capped')])
    row = run_probes(ProxySettings(), ['javdb'])['javdb']
    assert (row['state'], row['reason']) == ('unreachable', 'timeout')


def _slow_resp(status, headers=None):
    class _Slow(_BrokenBody):
        def stream(self, amt=8192, decode_content=None):
            raise sp.ReadTimeoutError(None, None, 'slow')

    r = make_resp(status, headers)
    r.raw = _Slow(b'')
    return r


@pytest.mark.parametrize('status,headers', [
    (200, {'cf-mitigated': 'challenge'}),
    (403, {'cf-mitigated': 'challenge'}),
])
def test_full_capped_challenge_header_wins_over_body_read_timeout(fake_classes, status, headers):
    plans, _ = fake_classes
    plans['javdb'] = ProbePlan([ProbeTarget('j', lambda: _slow_resp(status, headers), read='full_capped')])
    row = run_probes(ProxySettings(), ['javdb'])['javdb']
    assert (row['state'], row['reason']) == ('blocked', 'cf_challenge')


def test_full_capped_non_2xx_body_timeout_keeps_http_verdict(fake_classes):
    plans, _ = fake_classes
    plans['javdb'] = ProbePlan([ProbeTarget('j', lambda: _slow_resp(500), read='full_capped')])
    row = run_probes(ProxySettings(), ['javdb'])['javdb']
    assert (row['state'], row['reason']) == ('blocked', 'http_status')


# ------------------------------------------------------------ 並行 / 預算

def test_run_probes_targets_run_in_parallel(fake_classes):
    plans, _ = fake_classes
    n = 6
    barrier = threading.Barrier(n, timeout=5)

    def send():
        barrier.wait()
        return make_resp()

    ids = ['dmm', 'javbus', 'jav321', 'javdb', 'd2pass', 'heyzo']
    for sid in ids:
        plans[sid] = ProbePlan([ProbeTarget(sid + '.example', send)])
    rows = run_probes(ProxySettings(), ids)
    assert {r['state'] for r in rows.values()} == {'ok'}


def test_run_probes_budget_bounds_response_time(fake_classes, monkeypatch):
    plans, _ = fake_classes
    monkeypatch.setattr('core.source_probe.PROBE_BUDGET_S', 1)
    gate = threading.Event()

    def slow():
        gate.wait(3)
        return make_resp()

    ids = ['dmm', 'javbus', 'jav321', 'javdb', 'd2pass', 'heyzo', 'fc2', 'avsox']
    for sid in ids:
        plans[sid] = ProbePlan([ProbeTarget(sid + '.example', slow)])
    t0 = time.monotonic()
    rows = run_probes(ProxySettings(), ids)
    assert time.monotonic() - t0 < 2
    assert set(rows) == set(ids)
    assert {(r['state'], r['reason']) for r in rows.values()} == {('unreachable', 'timeout')}


def test_run_probes_all_mode_names_the_host_that_did_not_return(fake_classes, monkeypatch):
    plans, _ = fake_classes
    monkeypatch.setattr('core.source_probe.PROBE_BUDGET_S', 1)
    gate = threading.Event()
    plans['javbus'] = ProbePlan([
        ProbeTarget('fast.example', lambda: make_resp()),
        ProbeTarget('stuck.example', lambda: (gate.wait(3), make_resp())[1]),
    ], mode='all')
    row = run_probes(ProxySettings(), ['javbus'])['javbus']
    assert (row['state'], row['reason'], row['host']) == ('unreachable', 'timeout', 'stuck.example')


def test_run_probes_unexpected_exception_is_error_not_ok(fake_classes):
    plans, _ = fake_classes

    def boom():
        raise ZeroDivisionError('program bug')

    plans['dmm'] = ProbePlan([ProbeTarget('d.example', boom)])
    row = run_probes(ProxySettings(), ['dmm'])['dmm']
    assert (row['state'], row['reason']) == ('unreachable', 'error')


def test_run_probes_scraper_construction_failure_is_error(monkeypatch):
    def _bad(sid):
        raise RuntimeError('ctor')

    monkeypatch.setattr('core.source_probe.scraper_class_for', _bad)
    row = run_probes(ProxySettings(), ['dmm'])['dmm']
    assert (row['state'], row['reason']) == ('unreachable', 'error')


# ------------------------------------------------------------ 快照 / via_proxy / advice / skipped

def test_run_probes_gives_every_scraper_the_request_snapshot(fake_classes):
    plans, seen = fake_classes
    snap = ProxySettings(url=PROXY, scope='all')
    for sid in ('dmm', 'javbus'):
        plans[sid] = ProbePlan([ProbeTarget(sid, lambda: make_resp())])
    run_probes(snap, ['dmm', 'javbus'])
    assert seen == {'dmm': snap, 'javbus': snap}


@pytest.mark.parametrize('snap,expect', [
    (ProxySettings(url='', scope='dmm'), {'dmm': False, 'javbus': False}),
    (ProxySettings(url='', scope='all'), {'dmm': False, 'javbus': False}),
    (ProxySettings(url=PROXY, scope='dmm'), {'dmm': True, 'javbus': False}),
    (ProxySettings(url=PROXY, scope='all'), {'dmm': True, 'javbus': True}),
])
def test_run_probes_via_proxy_follows_policy(fake_classes, snap, expect):
    plans, _ = fake_classes
    for sid in expect:
        plans[sid] = ProbePlan([ProbeTarget(sid, lambda: make_resp())])
    rows = run_probes(snap, list(expect))
    assert {sid: rows[sid]['via_proxy'] for sid in expect} == expect


def test_run_probes_advice_only_when_blocked_and_source_needs_jp_ip(fake_classes):
    plans, _ = fake_classes
    for sid in ('dmm', 'javbus'):
        plans[sid] = ProbePlan([ProbeTarget(sid, lambda: make_resp(403))])
    plans['jav321'] = ProbePlan([ProbeTarget('jav321', lambda: make_resp())])
    plans['javdb'] = ProbePlan([ProbeTarget('javdb', lambda: (_ for _ in ()).throw(
        requests.exceptions.ConnectionError('x')))])
    plans['d2pass'] = ProbePlan([ProbeTarget('d2pass', lambda: (_ for _ in ()).throw(
        requests.exceptions.ConnectionError('x')))])
    rows = run_probes(ProxySettings(url=PROXY), ['dmm', 'javbus', 'jav321', 'javdb'])
    assert rows['dmm']['advice'] == 'jp_ip'
    assert rows['javbus']['state'] == 'blocked' and rows['javbus']['advice'] is None
    assert rows['jav321']['advice'] is None
    assert rows['javdb']['state'] == 'unreachable' and rows['javdb']['advice'] is None


def test_run_probes_skips_manual_only_and_metatube(fake_classes, monkeypatch):
    """dev／NAS（desktop_kind 為 None）：兩家驗證視窗來源恆 skipped/windows_verifier。"""
    monkeypatch.setattr('core.source_probe.desktop_kind', lambda: None)
    ids = ['javlibrary', 'fc-javten', 'metatube:x', 'zzz', 'dmm']
    rows = run_probes(ProxySettings(url=PROXY, scope='all'), ids)  # dmm: 假類別無 plan
    assert {i: (rows[i]['state'], rows[i]['reason']) for i in ids} == {
        'javlibrary': ('skipped', 'windows_verifier'),
        'fc-javten': ('skipped', 'windows_verifier'),
        'metatube:x': ('skipped', 'self_hosted'),
        'zzz': ('skipped', 'unknown'),
        'dmm': ('skipped', 'unprobeable'),
    }
    for r in rows.values():
        assert set(r) == SIX_KEYS
        assert (r['host'], r['status'], r['via_proxy'], r['advice']) == (None, None, False, None)


# ------------------------------------------------------------ 驗證視窗來源：skipped 環境表／判讀

class _FakeTransport:
    def __init__(self, sites):
        self._sites = sites

    def available_sites(self):
        return list(self._sites)


class _NoSitesTransport:
    """沒有 available_sites 屬性：get_cf_available_sites() 回 None（判不出來）。"""


@pytest.fixture
def transport_env(monkeypatch):
    """造 get_cf_available_sites() 的 []／部分／全／None；結束還原模組全域。"""
    import core.cf_transport as cft
    saved = cft._transport

    def _set(transport):
        cft._transport = transport

    try:
        yield _set
    finally:
        cft._transport = saved


BOTH = ('javlibrary', 'fc-javten')
SNAP_ALL = ProxySettings(url=PROXY, scope='all')
SNAP_DMM = ProxySettings(url=PROXY, scope='dmm')
SNAP_AUTH_ALL = ProxySettings(url='socks5://u:p@h.example:1', scope='all')
SNAP_AUTH_DMM = ProxySettings(url='socks5://u:p@h.example:1', scope='dmm')
SNAP_NOSCHEME_ALL = ProxySettings(url='h.example:1', scope='all')
SNAP_SOCKS_ALL = ProxySettings(url='socks5://h.example:1', scope='all')


@pytest.mark.parametrize('label,kind,transport,snap,expect', [
    ('dev', None, _FakeTransport(BOTH), SNAP_ALL, ('windows_verifier',) * 2),
    ('dev_no_transport', None, None, SNAP_ALL, ('windows_verifier',) * 2),
    ('mac_all_sites', 'mac', _FakeTransport(BOTH), SNAP_ALL, ('mac_system_proxy',) * 2),
    ('mac_no_transport', 'mac', None, SNAP_ALL, ('mac_system_proxy',) * 2),
    ('win_empty', 'windows', _FakeTransport(()), SNAP_ALL, ('verifier_not_started',) * 2),
    ('win_no_transport', 'windows', None, SNAP_ALL, ('verifier_not_started',) * 2),
    ('win_unknown_sites', 'windows', _NoSitesTransport(), SNAP_ALL, ('verifier_not_started',) * 2),
    ('win_only_javlibrary', 'windows', _FakeTransport(('javlibrary',)), SNAP_ALL,
     (None, 'verifier_not_started')),
    ('win_only_javten', 'windows', _FakeTransport(('fc-javten',)), SNAP_ALL,
     ('verifier_not_started', None)),
    ('win_all_http', 'windows', _FakeTransport(BOTH), SNAP_ALL, (None, None)),
    ('win_all_socks_noauth', 'windows', _FakeTransport(BOTH), SNAP_SOCKS_ALL, (None, None)),
    ('win_all_socks_auth', 'windows', _FakeTransport(BOTH), SNAP_AUTH_ALL,
     ('proxy_auth_unsupported',) * 2),
    ('win_scope_dmm_socks_auth', 'windows', _FakeTransport(BOTH), SNAP_AUTH_DMM, (None, None)),
    ('win_blank_proxy', 'windows', _FakeTransport(BOTH), ProxySettings(url='', scope='all'),
     (None, None)),
    ('win_noscheme_address_is_http', 'windows', _FakeTransport(BOTH), SNAP_NOSCHEME_ALL,
     (None, None)),
    ('win_not_started_beats_auth', 'windows', _FakeTransport(()), SNAP_AUTH_ALL,
     ('verifier_not_started',) * 2),
])
def test_skip_reason_environment_table(monkeypatch, transport_env, label, kind, transport, snap, expect):
    monkeypatch.setattr('core.source_probe.desktop_kind', lambda: kind)
    transport_env(transport)
    got = tuple(sp.skip_reason(sid, snap) for sid in BOTH)
    assert got == expect, label


def test_skip_reason_uses_request_snapshot(monkeypatch, transport_env):
    """畫面上的新代理（請求體快照）決定結果；已儲存的設定被讀到就炸。"""
    import core.proxy_policy as pp
    monkeypatch.setattr('core.source_probe.desktop_kind', lambda: 'windows')
    transport_env(_FakeTransport(BOTH))

    def _boom(*a, **k):
        raise AssertionError('不得讀已儲存的設定')

    monkeypatch.setattr(pp, 'current_settings', _boom)
    assert sp.skip_reason('javlibrary', SNAP_AUTH_ALL) == 'proxy_auth_unsupported'
    assert sp.skip_reason('javlibrary', SNAP_ALL) is None


CF_SERVER = {'server': 'cloudflare'}


@pytest.mark.parametrize('label,status,headers,body,flag,expect', [
    ('mitigated_200', 200, {'cf-mitigated': 'challenge'}, b'x', True, ('ok', 'ok')),
    ('mitigated_403', 403, {'cf-mitigated': 'challenge'}, b'x', True, ('ok', 'ok')),
    ('body_just_a_moment_403', 403, {}, b'<title>Just a moment...</title>', True, ('ok', 'ok')),
    ('body_jsd_503', 503, {}, JSD, True, ('ok', 'ok')),
    ('plain_cf_403', 403, CF_SERVER, b'<html>error 1015</html>', True, ('blocked', 'cf_challenge')),
    ('plain_403', 403, {}, b'forbidden', True, ('blocked', 'http_status')),
    ('server_500', 500, {}, b'x', True, ('blocked', 'http_status')),
    ('ok_200', 200, {}, b'x', True, ('ok', 'ok')),
    ('flag_off_mitigated', 200, {'cf-mitigated': 'challenge'}, b'x', False, ('blocked', 'cf_challenge')),
    ('flag_off_body', 403, {}, b'just a moment', False, ('blocked', 'cf_challenge')),
])
def test_verifier_cf_challenge_override_table(label, status, headers, body, flag, expect):
    t = ProbeTarget('h.example', lambda: make_resp(status, headers, body), cf_challenge_ok=flag)
    out = sp.probe_target(t)
    assert (out.state, out.reason) == expect, label


@pytest.mark.parametrize('exc,reason', [
    (requests.exceptions.ProxyError('x'), 'proxy'),
    (requests.exceptions.ConnectTimeout('x'), 'timeout'),
    (requests.exceptions.ConnectionError('x'), 'network'),
])
def test_verifier_target_connection_failures_stay_unreachable(exc, reason):
    def send():
        raise exc
    out = sp.probe_target(ProbeTarget('h.example', send, cf_challenge_ok=True))
    assert (out.state, out.reason) == ('unreachable', reason)


def test_run_probes_dedupes_ids_and_every_id_has_a_result(fake_classes):
    plans, _ = fake_classes
    hits = []
    plans['dmm'] = ProbePlan([ProbeTarget('d', lambda: hits.append(1) or make_resp())])
    rows = run_probes(ProxySettings(), ['dmm', 'dmm', 'zzz'])
    assert list(rows) == ['dmm', 'zzz'] and len(hits) == 1


# ------------------------------------------------------------ 不洩漏

def test_run_probes_response_never_contains_exception_text(fake_classes):
    plans, _ = fake_classes
    secret = 'http://user:pass@127.0.0.1:1'

    def send():
        raise requests.exceptions.ProxyError(f'Cannot connect to proxy {secret}')

    plans['dmm'] = ProbePlan([ProbeTarget('d.example', send)])
    rows = run_probes(ProxySettings(url=secret), ['dmm'])
    blob = json.dumps(rows)
    assert rows['dmm']['reason'] == 'proxy'
    assert 'pass' not in blob and 'Cannot connect' not in blob and '127.0.0.1' not in blob
    assert rows['dmm']['reason'] in sp.REASON_CODES
