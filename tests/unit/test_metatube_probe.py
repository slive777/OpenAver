"""
tests/unit/test_metatube_probe.py — TDD-lite tests for core.metatube.probe.

Mock strategy:
  - probe_provider: pass MagicMock client directly (no patch needed).
  - probe_all: patch 'core.metatube.probe.MetatubeHttpClient' (使用端！).
    Patching the definition side (core.metatube.client.MetatubeHttpClient) would
    leave probe.py's binding unchanged → mock silently fails (gotchas #1/#3).
"""

import pytest
from unittest.mock import patch

from core.metatube.errors import (
    MetatubeNotFound,
)
from core.metatube.probe import (
    probe_all,
)
from core.metatube.state import MetatubeConnectionState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_state():
    """New MetatubeConnectionState, pre-connected with a set of providers."""
    s = MetatubeConnectionState()
    s.connect('http://localhost:8900', '', ['FANZA', 'HEYZO', 'JAV321', 'JavBus'])
    return s


# ---------------------------------------------------------------------------
# canary map completeness
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# probe_provider — success path
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# probe_provider — 404 = failure (MAJOR-3 / probe-404 vs routing-404)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# probe_provider — other MetatubeError subclasses
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# probe_provider — no canary (JAV321 / SOD / FC2PPVDB / KIN8)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# probe_all — mock patch target: core.metatube.probe.MetatubeHttpClient
# ---------------------------------------------------------------------------


def test_probe_all_mixed_results_correct_state(fresh_state):
    """
    probe_all with mixed results correctly updates state:
    - FANZA succeeds (200) → mark_available
    - HEYZO fails (404) → mark_failed
    """
    with patch('core.metatube.probe.MetatubeHttpClient') as MockClient:
        def get_info_side_effect(provider, movie_id):
            if provider == 'FANZA':
                return {'id': '1stars00141'}
            raise MetatubeNotFound(f"404 for {provider}")

        MockClient.return_value.get_info.side_effect = get_info_side_effect

        result = probe_all(
            'http://localhost:8900', '', fresh_state, ['FANZA', 'HEYZO']
        )

    assert result['FANZA'] is True
    assert result['HEYZO'] is False
    assert fresh_state.is_available('metatube:FANZA') is True
    assert fresh_state.is_available('metatube:HEYZO') is False


# ============================================================
# 憑證不得進 probe 的 log（Codex PR review 三審 P1）
# ============================================================

def test_probe_all_unknown_provider_stays_available_and_is_not_probed():
    """unknown 來源不發請求、仍可用；同輪 canary 照舊被探測。"""
    import core.metatube.probe as probe

    state = MetatubeConnectionState()
    state.connect('http://localhost:8900', '', ['AVBASE', 'FC2DB', 'HEYZO'])
    progress = []
    with patch('core.metatube.probe.MetatubeHttpClient') as MockClient:
        MockClient.return_value.get_info.return_value = {'id': 'x'}
        result = probe.probe_all(
            'http://localhost:8900', '', state, ['AVBASE', 'FC2DB', 'HEYZO'],
            on_progress=lambda done, total: progress.append((done, total)),
        )
        probed = [c.args[0] for c in MockClient.return_value.get_info.call_args_list]

    assert result == {'AVBASE': True, 'FC2DB': True, 'HEYZO': True}
    assert probed == ['HEYZO']
    assert state.is_available('metatube:AVBASE') is True
    assert state.is_available('metatube:FC2DB') is True
    assert state.is_available('metatube:HEYZO') is True
    assert len(progress) == 3 and progress[-1] == (3, 3)


def test_probe_all_known_failing_providers_still_marked_failed():
    """已知失敗 4 來源：分類正確、不發請求、結果 False 且不可用。"""
    import core.metatube.probe as probe

    failing = ['JAV321', 'SOD', 'FC2PPVDB', 'KIN8']
    for name in failing:
        assert probe.classify_provider(name) == 'known_failing'
    for name in probe.METATUBE_PROBE_CANARIES:
        assert probe.classify_provider(name) == 'canary'
    assert probe.classify_provider('AVBASE') == 'unknown'

    state = MetatubeConnectionState()
    state.connect('http://localhost:8900', '', failing)
    with patch('core.metatube.probe.MetatubeHttpClient') as MockClient:
        result = probe.probe_all('http://localhost:8900', '', state, failing)
        MockClient.return_value.get_info.assert_not_called()

    assert result == {name: False for name in failing}
    for name in failing:
        assert state.is_available(f'metatube:{name}') is False


def test_probe_all_does_not_wash_runtime_failure_of_unknown_provider():
    """runtime 已標失敗的 unknown 來源，probe_all 不洗成可用。"""
    import core.metatube.probe as probe

    state = MetatubeConnectionState()
    state.connect('http://localhost:8900', '', ['AVBASE'])
    state.mark_failed('metatube:AVBASE')
    with patch('core.metatube.probe.MetatubeHttpClient') as MockClient:
        probe.probe_all('http://localhost:8900', '', state, ['AVBASE'])
        MockClient.return_value.get_info.assert_not_called()

    assert state.is_available('metatube:AVBASE') is False


def test_probe_all_log_does_not_leak_userinfo(caplog):
    """`probe_all()` 的 info log 記的是 redacted target，不是原始 base_url。"""
    import logging

    from core.metatube.probe import probe_all

    secret_url = 'http://admin:S3cr3tPass@10.0.0.5:8900'
    with caplog.at_level(logging.INFO, logger='OpenAver.core.metatube.probe'):
        with patch('core.metatube.probe.MetatubeHttpClient') as mock_cls:
            mock_cls.return_value.get_info.return_value = {'number': 'X'}
            probe_all(secret_url, '', MetatubeConnectionState(), ['FANZA'])

    assert 'probe_all: probing' in caplog.text   # 正向：這條 log 真的跑到了
    assert '10.0.0.5:8900' in caplog.text
    for secret in ('S3cr3tPass', 'admin@'):
        assert secret not in caplog.text, f"probe_all log 洩漏 {secret!r}"


