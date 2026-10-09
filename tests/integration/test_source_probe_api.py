"""POST /api/sources/probe — 端點層（TASK-163b-T1）。假 scraper 經 scraper_class_for 注入。"""
import io
import json

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from core.proxy_policy import ProxySettings
from core.source_probe import ProbePlan, ProbeTarget

A = 'http://jp-a.example:8080'
SIX_KEYS = {'state', 'reason', 'host', 'status', 'via_proxy', 'advice'}


def _resp(status=200):
    r = requests.Response()
    r.status_code = status
    r.headers = CaseInsensitiveDict()
    r.raw = io.BytesIO(b'ok')
    return r


@pytest.fixture
def seen(monkeypatch):
    seen_cfg = {}

    def _cls(sid):
        class Fake:
            def __init__(self, config):
                seen_cfg[sid] = config.proxy_settings

            def probe_plan(self, timeout):
                return ProbePlan([ProbeTarget(sid + '.example', lambda: _resp())])

        return Fake

    monkeypatch.setattr('core.source_probe.scraper_class_for', _cls)
    return seen_cfg


def test_probe_endpoint_uses_request_snapshot_not_live_config(client, seen, monkeypatch):
    def _no_live():
        raise AssertionError('探測路徑讀了已儲存的設定')

    monkeypatch.setattr('core.proxy_policy.current_settings', _no_live)
    ids = ['dmm', 'javbus', 'javlibrary', 'metatube:x', 'zzz']
    resp = client.post('/api/sources/probe',
                       json={'proxy_url': A, 'proxy_scope': 'all', 'source_ids': ids})
    assert resp.status_code == 200
    results = resp.json()['results']
    assert list(results) == ids
    assert all(set(r) == SIX_KEYS for r in results.values())
    snap = ProxySettings(url=A, scope='all')
    assert seen == {'dmm': snap, 'javbus': snap}
    assert results['dmm']['via_proxy'] is True and results['javbus']['via_proxy'] is True
    assert results['javlibrary']['state'] == 'skipped'


def test_probe_endpoint_default_scope_is_dmm_and_blank_url_not_via_proxy(client, seen):
    resp = client.post('/api/sources/probe', json={'source_ids': ['dmm']})
    assert resp.status_code == 200
    assert seen['dmm'] == ProxySettings(url='', scope='dmm')
    assert resp.json()['results']['dmm']['via_proxy'] is False


def test_probe_endpoint_validation(client, seen):
    ok = client.post('/api/sources/probe', json={'source_ids': ['dmm'] * 64})
    assert ok.status_code == 200
    too_many = client.post('/api/sources/probe', json={'source_ids': ['dmm'] * 65})
    assert too_many.status_code == 422
    bad_scope = client.post('/api/sources/probe',
                            json={'proxy_scope': 'nope', 'source_ids': ['dmm']})
    assert bad_scope.status_code == 422


def test_probe_endpoint_does_not_leak_proxy_credentials(client, monkeypatch):
    secret = 'http://user:pass@127.0.0.1:1'

    def _cls(sid):
        class Fake:
            def __init__(self, config):
                pass

            def probe_plan(self, timeout):
                def send():
                    raise requests.exceptions.ProxyError(f'proxy {secret} failed')
                return ProbePlan([ProbeTarget('d.example', send)])
        return Fake

    monkeypatch.setattr('core.source_probe.scraper_class_for', _cls)
    resp = client.post('/api/sources/probe',
                       json={'proxy_url': secret, 'source_ids': ['dmm']})
    assert resp.json()['results']['dmm']['reason'] == 'proxy'
    assert 'pass' not in json.dumps(resp.json())
