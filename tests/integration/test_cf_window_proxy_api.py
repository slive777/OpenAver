"""TASK-163b-T7a A1：GET／PUT /api/config 帶 cf_window_proxy_restart_needed。"""
import json

import pytest

from core import proxy_policy
from core.config import load_config

PW = 'pass'


@pytest.fixture
def windows_kind(monkeypatch):
    monkeypatch.setattr(proxy_policy, 'desktop_kind', lambda: 'windows')
    monkeypatch.setattr(proxy_policy, '_cf_window_proxy_at_start', None)


def _full_config_with_proxy(url, scope):
    cfg = load_config()
    cfg['search']['proxy_url'] = url
    cfg['search']['proxy_scope'] = scope
    return cfg


def test_get_config_reports_cf_window_restart_needed(client, windows_kind):
    body = client.get('/api/config').json()
    assert body['cf_window_proxy_restart_needed'] is False       # 設定未改：與啟動規格(None)相同
    assert 'cf_window_proxy_restart_needed' not in body['data']  # 頂層唯讀欄位，不在 data 內
    r = client.put('/api/config', json=_full_config_with_proxy('https://u:%s@h:1' % PW, 'all'))
    assert r.json()['success'] is True
    got = client.get('/api/config').json()
    assert got['cf_window_proxy_restart_needed'] is True


def test_put_config_reports_cf_window_restart_needed(client, windows_kind):
    r = client.put('/api/config', json=_full_config_with_proxy('https://u:%s@h:1' % PW, 'all'))
    body = r.json()
    assert body['success'] is True
    assert body['cf_window_proxy_restart_needed'] is True
    assert PW not in json.dumps(body)
    assert 'h:1' not in json.dumps(body)
    got = client.get('/api/config').json()
    assert got['cf_window_proxy_restart_needed'] is True
    rest = {k: v for k, v in got.items() if k != 'data'}
    assert PW not in json.dumps(rest)
    assert 'h:1' not in json.dumps(rest)
    r = client.put('/api/config', json=_full_config_with_proxy('https://u:%s@h:1' % PW, 'dmm'))
    assert r.json()['cf_window_proxy_restart_needed'] is False
    assert client.get('/api/config').json()['cf_window_proxy_restart_needed'] is False


def test_restart_needed_false_when_not_windows_desktop(client, monkeypatch):
    monkeypatch.setattr(proxy_policy, 'desktop_kind', lambda: None)
    monkeypatch.setattr(proxy_policy, '_cf_window_proxy_at_start', None)
    r = client.put('/api/config', json=_full_config_with_proxy('https://u:%s@h:1' % PW, 'all'))
    assert r.json()['success'] is True
    assert r.json()['cf_window_proxy_restart_needed'] is False
    assert client.get('/api/config').json()['cf_window_proxy_restart_needed'] is False
