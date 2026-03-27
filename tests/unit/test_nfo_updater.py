"""
測試 core/nfo_updater.py 的 needs_update() 和 update_nfo_file()
新欄位：director / duration / series / label

TDD-lite 策略：先 RED → 實作 GREEN
"""
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from core.nfo_updater import needs_update, update_nfo_file


# ============================================================
# Helper
# ============================================================

def make_base_info(**kwargs) -> dict:
    """建立最小有效的 info dict（has_nfo=True 的情境，有番號）。
    預設值模擬所有欄位皆有值，可用 kwargs 覆蓋。
    """
    base = {
        'num': 'TEST-001',
        'title': 'テストタイトル',
        'date': '2024-01-01',
        'actor': '女優A',
        'genre': 'ジャンルA',
        'maker': '片商A',
        'director': '監督A',
        'duration': 90,
        'series': 'シリーズA',
        'label': 'labelA',
    }
    base.update(kwargs)
    return base


def write_nfo(tmp_path: Path, content: str, filename: str = "test.nfo") -> str:
    """將 NFO 內容寫入 tmp_path，回傳路徑字串。"""
    nfo = tmp_path / filename
    nfo.write_text(content, encoding="utf-8")
    return str(nfo)


# ============================================================
# needs_update() 測試
# ============================================================

class TestNeedsUpdateNewFields:
    """needs_update() 對新欄位（director/duration/series/label）的判斷"""

    # 1. 缺 director → missing 含 'director'
    def test_missing_director_in_missing_list(self):
        info = make_base_info(director='')
        need, missing = needs_update(info, has_nfo=True)
        assert need is True
        assert 'director' in missing

    # 2. duration=None → missing 含 'duration'
    def test_missing_duration_none_in_missing_list(self):
        info = make_base_info(duration=None)
        need, missing = needs_update(info, has_nfo=True)
        assert need is True
        assert 'duration' in missing

    # 3. duration=0 → 不列入 missing（0 是有效值）
    def test_duration_zero_not_missing(self):
        info = make_base_info(duration=0)
        need, missing = needs_update(info, has_nfo=True)
        assert 'duration' not in missing

    # 4. 缺 series → missing 含 'series'
    def test_missing_series_in_missing_list(self):
        info = make_base_info(series='')
        need, missing = needs_update(info, has_nfo=True)
        assert need is True
        assert 'series' in missing

    # 5. 缺 label → missing 含 'label'
    def test_missing_label_in_missing_list(self):
        info = make_base_info(label='')
        need, missing = needs_update(info, has_nfo=True)
        assert need is True
        assert 'label' in missing

    # 6. 所有新欄位都有值 → missing 不含新欄位
    def test_all_new_fields_present_not_missing(self):
        info = make_base_info()  # 預設全部有值
        need, missing = needs_update(info, has_nfo=True)
        for field in ('director', 'duration', 'series', 'label'):
            assert field not in missing

    # 7. 既有欄位（title/date/actor/genre/maker）檢查不受影響
    def test_existing_fields_still_checked(self):
        # 舊欄位全缺，新欄位全有
        info = make_base_info(
            title='', date='', actor='', genre='', maker=''
        )
        need, missing = needs_update(info, has_nfo=True)
        assert need is True
        for field in ('title', 'date', 'actor', 'genre', 'maker'):
            assert field in missing
        # 新欄位不應出現在 missing（全有值）
        for field in ('director', 'duration', 'series', 'label'):
            assert field not in missing

    # 補充：has_nfo=False → early return，不管欄位
    def test_no_nfo_returns_empty(self):
        info = make_base_info(director='')
        need, missing = needs_update(info, has_nfo=False)
        assert need is False
        assert missing == []

    # 補充：無番號 → early return
    def test_no_num_returns_empty(self):
        info = make_base_info(num='', director='')
        need, missing = needs_update(info, has_nfo=True)
        assert need is False
        assert missing == []



# ============================================================
# scanner.py info dict 格式守衛
# ============================================================

class TestScannerInfoDictNewFields:
    """確保 scanner.py 建構的 info dict 包含新欄位，不造成永久 needs_update"""

    def _make_scanner_info(self, **overrides) -> dict:
        """模擬 scanner.py 三處 info dict 建構（含新欄位）。"""
        base = {
            'title': 'テストタイトル',
            'date': '2024-01-01',
            'actor': '女優A',
            'genre': 'ジャンルA',
            'maker': '片商A',
            'num': 'TEST-001',
            'director': '監督A',
            'duration': 90,
            'series': 'シリーズA',
            'label': 'labelA',
        }
        base.update(overrides)
        return base

    def test_full_info_dict_not_missing_new_fields(self):
        """scanner 完整 info dict（含新欄位）→ needs_update 不回報新欄位缺失"""
        info = self._make_scanner_info()
        need, missing = needs_update(info, has_nfo=True)
        for field in ('director', 'duration', 'series', 'label'):
            assert field not in missing, f"新欄位 '{field}' 不應在 missing 中"

    def test_old_style_info_dict_missing_new_fields(self):
        """舊格式 info dict（缺新欄位）→ needs_update 回報新欄位缺失（驗證修正前的問題）"""
        old_style = {
            'title': 'テストタイトル',
            'date': '2024-01-01',
            'actor': '女優A',
            'genre': 'ジャンルA',
            'maker': '片商A',
            'num': 'TEST-001',
            # 缺 director, duration, series, label
        }
        need, missing = needs_update(old_style, has_nfo=True)
        assert need is True
        for field in ('director', 'series', 'label'):
            assert field in missing, f"舊格式 dict 應缺少 '{field}'"
        assert 'duration' in missing, "舊格式 dict 應缺少 'duration'"

    def test_new_fields_with_empty_string_still_missing(self):
        """scanner 傳入空字串的新欄位 → 仍被列為缺失"""
        info = self._make_scanner_info(director='', series='', label='')
        need, missing = needs_update(info, has_nfo=True)
        assert 'director' in missing
        assert 'series' in missing
        assert 'label' in missing

    def test_duration_none_from_db_still_missing(self):
        """DB 中 duration=None（未抓到）→ needs_update 列為缺失"""
        info = self._make_scanner_info(duration=None)
        need, missing = needs_update(info, has_nfo=True)
        assert 'duration' in missing

    def test_duration_zero_from_db_not_missing(self):
        """DB 中 duration=0（有效值）→ needs_update 不列為缺失"""
        info = self._make_scanner_info(duration=0)
        need, missing = needs_update(info, has_nfo=True)
        assert 'duration' not in missing


# ============================================================
# update_nfo_file() 測試
# ============================================================

class TestUpdateNfoFileNewFields:
    """update_nfo_file() 補入 / 不覆蓋 director/runtime/set/label"""

    # --- NFO template 工廠 ---

    @staticmethod
    def _minimal_nfo(*, title: str = "テストタイトル",
                      runtime: str = None,
                      director: str = None,
                      set_name: str = None,
                      label: str = None) -> str:
        """產生最小 NFO XML 字串，各新欄位可選。"""
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<movie>',
            f'  <title>{title}</title>',
            '  <num>TEST-001</num>',
        ]
        if runtime is not None:
            lines.append(f'  <runtime>{runtime}</runtime>')
        if director is not None:
            lines.append(f'  <director>{director}</director>')
        if set_name is not None:
            lines.append(f'  <set><name>{set_name}</name></set>')
        if label is not None:
            lines.append(f'  <label>{label}</label>')
        lines.append('</movie>')
        return '\n'.join(lines)

    # 8. 舊 NFO 缺 director/runtime/set/label → 補齊後 XML 含所有新 tag
    def test_fill_all_missing_new_fields(self, tmp_path):
        nfo_xml = self._minimal_nfo()  # 不含任何新欄位
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(director='', duration=None, series='', label='')
        metadata = {
            'director': '新監督',
            'duration': 120,
            'series': '新シリーズ',
            'label': '新label',
        }
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        # 驗證 XML 結構
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.find('director') is not None
        assert root.find('director').text == '新監督'
        assert root.find('runtime') is not None
        assert root.find('runtime').text == '120'
        assert root.find('set/name') is not None
        assert root.find('set/name').text == '新シリーズ'
        assert root.find('label') is not None
        assert root.find('label').text == '新label'

    # 9. 已有 director 的 NFO + metadata 有 director → 不覆蓋
    def test_existing_director_not_overwritten(self, tmp_path):
        nfo_xml = self._minimal_nfo(director='既存監督')
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(director='既存監督')
        metadata = {'director': '新監督'}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        # 不應修改
        root = ET.parse(nfo_path).getroot()
        assert root.find('director').text == '既存監督'

    # 10. 已有 <runtime> 的 NFO → 不覆蓋
    def test_existing_runtime_not_overwritten(self, tmp_path):
        nfo_xml = self._minimal_nfo(runtime='90')
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(duration=90)
        metadata = {'duration': 200}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('runtime').text == '90'

    # 11. 已有 <set><name> 的 NFO → 不覆蓋
    def test_existing_set_name_not_overwritten(self, tmp_path):
        nfo_xml = self._minimal_nfo(set_name='既存シリーズ')
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(series='既存シリーズ')
        metadata = {'series': '新シリーズ'}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('set/name').text == '既存シリーズ'

    # 12. duration=0 → 寫入 <runtime>0</runtime>
    def test_duration_zero_written_as_runtime(self, tmp_path):
        nfo_xml = self._minimal_nfo()  # 沒有 <runtime>
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(duration=None)  # info 沒有 duration
        metadata = {'duration': 0}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        root = ET.parse(nfo_path).getroot()
        runtime_elem = root.find('runtime')
        assert runtime_elem is not None
        assert runtime_elem.text == '0'

    # 13. <set> 巢狀結構正確（set/name 路徑可找到）
    def test_set_name_nested_structure_correct(self, tmp_path):
        nfo_xml = self._minimal_nfo()
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(series='')
        metadata = {'series': 'ネストシリーズ'}
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        name_elem = root.find('set/name')
        assert name_elem is not None
        assert name_elem.text == 'ネストシリーズ'

    # 14. metadata 無 series → 不建立空 <set>
    def test_no_series_in_metadata_no_set_created(self, tmp_path):
        nfo_xml = self._minimal_nfo()
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(series='')
        metadata = {}  # 沒有 series
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('set') is None

    # 15. <runtime> 寫入整數字串（非浮點數）
    def test_runtime_written_as_integer_string(self, tmp_path):
        nfo_xml = self._minimal_nfo()
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(duration=None)
        metadata = {'duration': 119}
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        runtime_text = root.find('runtime').text
        assert runtime_text == '119'
        assert '.' not in runtime_text  # 不是浮點數格式

    # 補充：已有 label 的 NFO → 不覆蓋
    def test_existing_label_not_overwritten(self, tmp_path):
        nfo_xml = self._minimal_nfo(label='既存label')
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(label='既存label')
        metadata = {'label': '新label'}
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('label').text == '既存label'

    # 補充：既有欄位（title/maker）邏輯不受影響
    def test_existing_logic_not_broken(self, tmp_path):
        """既有的 title/maker 補全邏輯不應受新欄位影響"""
        nfo_xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="utf-8"?>
            <movie>
              <title></title>
              <num>TEST-001</num>
            </movie>
        """)
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(title='', maker='')
        metadata = {
            'title': '新タイトル',
            'maker': '新片商',
        }
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        root = ET.parse(nfo_path).getroot()
        assert root.find('title').text == '新タイトル'
        assert root.find('studio').text == '新片商'

    # 補充：<set> 已存在但缺 <name> → 補入 <name>，不重建 <set>
    def test_set_exists_without_name_fills_name(self, tmp_path):
        nfo_xml = textwrap.dedent("""\
            <?xml version="1.0" encoding="utf-8"?>
            <movie>
              <title>テスト</title>
              <num>TEST-001</num>
              <set></set>
            </movie>
        """)
        nfo_path = write_nfo(tmp_path, nfo_xml)
        info = make_base_info(series='')
        metadata = {'series': '補完シリーズ'}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        root = ET.parse(nfo_path).getroot()
        name_elem = root.find('set/name')
        assert name_elem is not None
        assert name_elem.text == '補完シリーズ'
        # <set> 只存在一個
        assert len(root.findall('set')) == 1
