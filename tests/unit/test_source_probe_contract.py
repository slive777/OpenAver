"""163b-T4a：後端 reason code ↔ 前端映射表 ↔ zh_TW 的跨檔契約。"""
import json
import re
from pathlib import Path

from core.source_probe import REASON_CODES

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / 'web/static/js/pages/settings/source-probe-logic.js'
ZH_TW = ROOT / 'locales/zh_TW.json'


def _map_body(name: str) -> str:
    src = LOGIC.read_text(encoding='utf-8')
    m = re.search(r'export const %s = \{\n(.*?)\n\};' % name, src, re.S)
    assert m, f'{name} not found in source-probe-logic.js'
    return m.group(1)


def _cells(name: str) -> dict:
    return dict(re.findall(r"^\s+(\w+): '([\w.]+)',$", _map_body(name), re.M))


def _zh_has(key: str) -> bool:
    node = json.loads(ZH_TW.read_text(encoding='utf-8'))
    for part in key.split('.'):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, str) and node != ''


def test_every_reason_code_has_a_frontend_mapping():
    missing = REASON_CODES - set(_cells('REASON_KEY_MAP'))
    assert not missing, f'REASON_KEY_MAP 缺格: {sorted(missing)}'


def test_reason_map_values_exist_in_zh_tw():
    bad = [v for v in _cells('REASON_KEY_MAP').values() if not _zh_has(v)]
    assert not bad, f'zh_TW 缺 key: {bad}'


def test_state_map_and_fixed_keys_exist_in_zh_tw():
    states = _cells('STATE_KEY_MAP')
    assert set(states) == {'ok', 'blocked', 'unreachable', 'skipped'}
    keys = list(states.values()) + [
        'settings.sources.probe_reason_generic',
        'settings.sources.probe_btn',
        'settings.sources.probe_summary',
        'settings.sources.probe_failed',
        'settings.sources.probe_line',
        'settings.sources.probe_line_advice',
        'settings.sources.probe_line_host',
        'settings.sources.probe_line_host_advice',
        'settings.sources.probe_tip',
    ]
    bad = [k for k in keys if not _zh_has(k)]
    assert not bad, f'zh_TW 缺 key: {bad}'


def test_advice_map_values_exist_in_zh_tw():
    cells = _cells('ADVICE_KEY_MAP')
    assert cells, 'ADVICE_KEY_MAP 沒有任何格'
    bad = [v for v in cells.values() if not _zh_has(v)]
    assert not bad, f'zh_TW 缺 key: {bad}'
