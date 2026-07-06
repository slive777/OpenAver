"""
測試 core/nfo_updater.py 的 needs_update() 和 update_nfo_file()
新欄位：director / duration / series / label / plot / rating / mpaa

TDD-lite 策略：先 RED → 實作 GREEN
"""
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import core.path_utils as path_utils
from core.nfo_updater import (
    add_actor,
    add_tags_and_genres,
    get_nfo_path_from_video,
    needs_update,
    update_nfo_file,
    update_nfo_user_tags,
)


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

    # 4. 缺 series → 不再檢查（來源不一定有）
    def test_missing_series_not_checked(self):
        info = make_base_info(series='')
        need, missing = needs_update(info, has_nfo=True)
        assert 'series' not in missing

    # 5. 缺 label → 不再檢查（來源不一定有）
    def test_missing_label_not_checked(self):
        info = make_base_info(label='')
        need, missing = needs_update(info, has_nfo=True)
        assert 'label' not in missing

    # 6. 所有新欄位都有值 → missing 不含新欄位
    def test_all_new_fields_present_not_missing(self):
        info = make_base_info()  # 預設全部有值
        need, missing = needs_update(info, has_nfo=True)
        for field in ('director', 'duration'):
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
        for field in ('director', 'duration'):
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
        """舊格式 info dict（缺新欄位）→ needs_update 回報 director/duration 缺失（series/label 不再檢查）"""
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
        assert 'director' in missing, "舊格式 dict 應缺少 'director'"
        assert 'duration' in missing, "舊格式 dict 應缺少 'duration'"
        # series/label 不再檢查
        assert 'series' not in missing
        assert 'label' not in missing

    def test_new_fields_with_empty_string_still_missing(self):
        """scanner 傳入空字串的新欄位 → director 仍被列為缺失，series/label 不再檢查"""
        info = self._make_scanner_info(director='', series='', label='')
        need, missing = needs_update(info, has_nfo=True)
        assert 'director' in missing
        assert 'series' not in missing
        assert 'label' not in missing

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


# ============================================================
# update_nfo_file() — plot / rating / mpaa（63c-5 / CD-63c-10）
# ============================================================

class TestUpdateNfoFilePlotRatingMpaa:
    """update_nfo_file() 補入 / 不覆蓋 <plot>/<rating>/<mpaa>（63c-5 US7 parity）"""

    @staticmethod
    def _nfo(*, plot: str = None, rating: str = None, mpaa: str = None,
              premiered: str = None) -> str:
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<movie>',
            '  <title>テスト</title>',
            '  <num>TEST-001</num>',
        ]
        if premiered is not None:
            lines.append(f'  <premiered>{premiered}</premiered>')
        if plot is not None:
            lines.append(f'  <plot>{plot}</plot>')
        if rating is not None:
            lines.append(f'  <rating>{rating}</rating>')
        if mpaa is not None:
            lines.append(f'  <mpaa>{mpaa}</mpaa>')
        lines.append('</movie>')
        return '\n'.join(lines)

    # ── P2-1: fill all three when missing ──

    def test_fill_plot_rating_mpaa_when_all_missing(self, tmp_path):
        """NFO 缺 plot/rating/mpaa + metadata 有 _summary/_rating → 三者全部補入"""
        nfo_path = write_nfo(tmp_path, self._nfo())
        info = make_base_info()
        metadata = {'_summary': 'Test plot summary', '_rating': 4.0}

        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        root = ET.parse(nfo_path).getroot()
        assert root.find('plot') is not None
        # ET round-trips text 1:1（plain text 無需 escape）；XSS escape 另由
        # test_plot_special_chars_safe_in_xml 驗證
        assert root.find('plot').text == 'Test plot summary'
        assert root.find('rating') is not None
        assert root.find('rating').text == '8.0'   # 4.0 × 2
        assert root.find('mpaa') is not None
        assert root.find('mpaa').text == 'JP-18+'
        assert 'plot' in msg
        assert 'rating' in msg
        assert 'mpaa' in msg

    # ── P2-2: rating × 2, format ──

    def test_rating_doubled_and_formatted(self, tmp_path):
        """rating × 2，格式為 X.X（一位小數）"""
        nfo_path = write_nfo(tmp_path, self._nfo())
        info = make_base_info()
        metadata = {'_summary': 'x', '_rating': 3.75}

        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('rating').text == '7.5'

    # ── P2-3: do not overwrite existing plot ──

    def test_existing_plot_not_overwritten(self, tmp_path):
        """現 NFO 已有 <plot> → 不覆蓋"""
        nfo_path = write_nfo(tmp_path, self._nfo(plot='Existing plot'))
        info = make_base_info()
        metadata = {'_summary': 'New summary', '_rating': 3.0}

        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('plot').text == 'Existing plot'

    # ── P2-4: do not overwrite existing rating ──

    def test_existing_rating_not_overwritten(self, tmp_path):
        """現 NFO 已有 <rating> → 不覆蓋"""
        nfo_path = write_nfo(tmp_path, self._nfo(rating='6.0'))
        info = make_base_info()
        metadata = {'_rating': 4.0}

        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('rating').text == '6.0'

    # ── P2-5: do not overwrite existing mpaa ──

    def test_existing_mpaa_not_overwritten(self, tmp_path):
        """現 NFO 已有 <mpaa> → 不覆蓋"""
        nfo_path = write_nfo(tmp_path, self._nfo(mpaa='R'))
        info = make_base_info()
        metadata = {'_summary': 'x', '_rating': 3.0}

        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('mpaa').text == 'R'

    # ── P2-6: mpaa filled even without _summary/_rating (builtin path) ──

    def test_mpaa_filled_for_builtin_metadata_no_summary_rating(self, tmp_path):
        """builtin 來源（無 _summary/_rating）→ mpaa 仍補 JP-18+（無條件補，fill-if-missing）"""
        nfo_path = write_nfo(tmp_path, self._nfo())
        info = make_base_info()
        metadata = {}   # no _summary, no _rating

        updated, msg = update_nfo_file(nfo_path, metadata, info)

        # mpaa should still be filled
        root = ET.parse(nfo_path).getroot()
        assert root.find('mpaa') is not None
        assert root.find('mpaa').text == 'JP-18+'
        # plot and rating should NOT be added (no data)
        assert root.find('plot') is None
        assert root.find('rating') is None

    # ── P2-7: zero rating is not written ──

    def test_zero_rating_not_written(self, tmp_path):
        """_rating=0 → 不寫 <rating>（無效值）"""
        nfo_path = write_nfo(tmp_path, self._nfo())
        info = make_base_info()
        metadata = {'_summary': 'x', '_rating': 0}

        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('rating') is None

    # ── P2-8: injection prevention via ET escaping ──

    def test_plot_special_chars_safe_in_xml(self, tmp_path):
        """<plot> 帶特殊字元時 XML 仍可解析，ET round-trip 還原原始文字（ET 自動 escape on write）"""
        nfo_path = write_nfo(tmp_path, self._nfo())
        info = make_base_info()
        evil = '<script>alert("xss")</script> & "quotes"'
        metadata = {'_summary': evil}

        update_nfo_file(nfo_path, metadata, info)

        # ET write escapes automatically; ET.parse round-trips back to original text
        root = ET.parse(nfo_path).getroot()
        plot_elem = root.find('plot')
        assert plot_elem is not None
        assert plot_elem.text == evil   # ET round-trips unescaped


# ============================================================
# add_actor() 測試（TASK-73c-T1）
# ============================================================

class TestAddActor:
    """add_actor() — 演員新增與去重"""

    def test_add_actor_to_empty_root_returns_true_and_element_exists(self):
        """空 root 新增演員 → return True 且 <actor><name> 存在。"""
        root = ET.fromstring("<movie/>")
        result = add_actor(root, "女優A")
        assert result is True
        names = root.findall('.//actor/name')
        assert len(names) == 1
        assert names[0].text == "女優A"

    def test_add_duplicate_actor_returns_false_and_count_unchanged(self):
        """root 已有同名 actor → return False，<actor> 數量不變。"""
        root = ET.fromstring("<movie><actor><name>女優A</name></actor></movie>")
        result = add_actor(root, "女優A")
        assert result is False
        assert len(root.findall('.//actor')) == 1

    def test_first_actor_name_text_matches(self):
        """root.findall('.//actor/name')[0].text == actor_name。"""
        root = ET.fromstring("<movie/>")
        add_actor(root, "女優B")
        assert root.findall('.//actor/name')[0].text == "女優B"


# ============================================================
# add_tags_and_genres() 測試（TASK-73c-T1）
# ============================================================

class TestAddTagsAndGenres:
    """add_tags_and_genres() — tag/genre 獨立去重"""

    def test_empty_root_add_three_tags_returns_three(self):
        """空 root 加 3 個 tag → return 3，<tag> × 3、<genre> × 3。"""
        root = ET.fromstring("<movie/>")
        count = add_tags_and_genres(root, ["東方", "魔法", "戀愛"])
        assert count == 3
        assert len(root.findall('tag')) == 3
        assert len(root.findall('genre')) == 3

    def test_existing_tag_not_duplicated_count_zero(self):
        """root 已有 <tag>東方</tag> 再加「東方」→ count == 0，<tag>東方</tag> 僅 1 個。"""
        root = ET.fromstring("<movie><tag>東方</tag><genre>東方</genre></movie>")
        count = add_tags_and_genres(root, ["東方"])
        assert count == 0
        assert len(root.findall('tag')) == 1

    def test_existing_genre_but_no_tag_adds_tag_not_genre(self):
        """root 已有 <genre>東方</genre>（無 <tag>）再加「東方」→ <tag> 新增 1（count==1），<genre> 不重複（仍 1 個）。"""
        root = ET.fromstring("<movie><genre>東方</genre></movie>")
        count = add_tags_and_genres(root, ["東方"])
        # tag should be added (was not in existing_tags)
        assert count == 1
        assert len(root.findall('tag')) == 1
        # genre should NOT be duplicated (already in existing_genres)
        assert len(root.findall('genre')) == 1

    def test_empty_and_whitespace_strings_skipped(self):
        """加 ["", "  "] → count == 0。"""
        root = ET.fromstring("<movie/>")
        count = add_tags_and_genres(root, ["", "  "])
        assert count == 0
        assert len(root.findall('tag')) == 0
        assert len(root.findall('genre')) == 0


# ============================================================
# update_nfo_user_tags() 測試（TASK-73c-T1）
# ============================================================

class TestUpdateNfoUserTags:
    """update_nfo_user_tags() — user_tag 清空再寫入"""

    def test_replace_existing_user_tags_with_new_list(self, tmp_path):
        """含 2 個 <user_tag> 的 NFO + ["new1","new2","new3"] → return True，讀回 <user_tag> 恰 3 個。"""
        nfo = tmp_path / "test.nfo"
        nfo.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><title>test</title>'
            '<user_tag>old1</user_tag>'
            '<user_tag>old2</user_tag>'
            '</movie>',
            encoding="utf-8",
        )
        result = update_nfo_user_tags(str(nfo), ["new1", "new2", "new3"])
        assert result is True
        root = ET.parse(str(nfo)).getroot()
        user_tags = root.findall('user_tag')
        assert len(user_tags) == 3
        texts = [e.text for e in user_tags]
        assert "new1" in texts
        assert "new2" in texts
        assert "new3" in texts

    def test_empty_list_clears_all_user_tags(self, tmp_path):
        """傳 [] → 所有 <user_tag> 被清除。"""
        nfo = tmp_path / "test.nfo"
        nfo.write_text(
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><user_tag>a</user_tag><user_tag>b</user_tag></movie>',
            encoding="utf-8",
        )
        result = update_nfo_user_tags(str(nfo), [])
        assert result is True
        root = ET.parse(str(nfo)).getroot()
        assert len(root.findall('user_tag')) == 0

    def test_nonexistent_path_returns_false(self, tmp_path):
        """不存在路徑 → return False。"""
        result = update_nfo_user_tags(str(tmp_path / "no_such.nfo"), ["tag"])
        assert result is False

    def test_malformed_xml_returns_false(self, tmp_path):
        """畸形 XML → return False（ParseError 被 except Exception 捕捉）。"""
        nfo = tmp_path / "bad.nfo"
        nfo.write_bytes(b'<movie><title>test</title><unclosed>')
        result = update_nfo_user_tags(str(nfo), ["tag"])
        assert result is False


# ============================================================
# update_nfo_file() 補欄分支測試（TASK-73c-T1）
# ============================================================

class TestUpdateNfoFileFillBranches:
    """update_nfo_file() date / actor 補欄 fill-only-if-missing 分支"""

    @staticmethod
    def _write_nfo(tmp_path: Path, xml_content: str, filename: str = "movie.nfo") -> str:
        nfo = tmp_path / filename
        nfo.write_text(xml_content, encoding="utf-8")
        return str(nfo)

    def test_fill_date_when_info_has_no_date(self, tmp_path):
        """NFO 無 <premiered>，info={}，metadata={'date':'2024-01-01'} → <premiered> 寫入，changed==True，訊息含 'date'。"""
        nfo_path = self._write_nfo(
            tmp_path,
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><title>テスト</title><num>TEST-001</num></movie>',
        )
        info = {}
        metadata = {"date": "2024-01-01"}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        assert "date" in msg
        root = ET.parse(nfo_path).getroot()
        premiered = root.find('premiered')
        assert premiered is not None
        assert premiered.text == "2024-01-01"

    def test_existing_date_in_info_not_overwritten(self, tmp_path):
        """NFO 已有 <premiered>2023-05-01</premiered>，info['date']='2023-05-01' → <premiered> 不改。"""
        nfo_path = self._write_nfo(
            tmp_path,
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><title>テスト</title><num>TEST-001</num>'
            '<premiered>2023-05-01</premiered></movie>',
        )
        info = {"date": "2023-05-01"}
        metadata = {"date": "2024-01-01"}
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        assert root.find('premiered').text == "2023-05-01"

    def test_fill_actors_when_info_has_no_actor(self, tmp_path):
        """NFO 無 <actor>，info={}，metadata={'actors':['女優A','女優B']} → 兩個 <actor><name> 加入。"""
        nfo_path = self._write_nfo(
            tmp_path,
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><title>テスト</title><num>TEST-001</num></movie>',
        )
        info = {}
        metadata = {"actors": ["女優A", "女優B"]}
        updated, msg = update_nfo_file(nfo_path, metadata, info)

        assert updated is True
        root = ET.parse(nfo_path).getroot()
        names = [e.text for e in root.findall('.//actor/name')]
        assert "女優A" in names
        assert "女優B" in names
        assert len(names) == 2

    def test_existing_actor_in_info_no_new_actor_added(self, tmp_path):
        """NFO 已有 <actor><name>女優A</name></actor>，info={'actor':[{'name':'女優A'}]} → 無新 actor 加入。"""
        nfo_path = self._write_nfo(
            tmp_path,
            '<?xml version="1.0" encoding="utf-8"?>'
            '<movie><title>テスト</title><num>TEST-001</num>'
            '<actor><name>女優A</name></actor></movie>',
        )
        # info['actor'] is truthy → the fill branch is skipped entirely
        info = {"actor": [{"name": "女優A"}]}
        metadata = {"actors": ["女優A", "女優B"]}
        update_nfo_file(nfo_path, metadata, info)

        root = ET.parse(nfo_path).getroot()
        names = [e.text for e in root.findall('.//actor/name')]
        # Only the original actor should be present — the fill branch was skipped
        assert names == ["女優A"]


# ============================================================
# TASK-91-T4: get_nfo_path_from_video path_mappings 反解測試
# ============================================================

class TestGetNfoPathPathMappingReverse:
    """get_nfo_path_from_video 改用 uri_to_local_fs_path 後的行為驗證。

    場景 C：WSL + UNC path_mappings 下，NFO 存在性判斷需拿到真正可 exists() 的
    本機路徑，而非裸 uri_to_fs_path 產生的非法 WSL 路徑（恆 False）。
    """

    def test_wsl_mapping_hit(self, tmp_path, monkeypatch):
        """WSL + mapping 命中：video_path 經反解對應到真實存在的 NFO。"""
        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        nfo_file = nas_dir / "movie.nfo"
        nfo_file.write_text("<movie></movie>", encoding="utf-8")

        mappings = {str(nas_dir): "//NAS/share"}
        video_path = "file://///NAS/share/movie.mp4"

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        result = get_nfo_path_from_video(video_path, mappings)
        assert result == str(nfo_file)

        # 裸呼叫（無 mapping）在同一 WSL 環境下應回 None：
        # 證明是 mapping 讓它解得到，而非其他因素（mutation-sensitive）
        result_no_mapping = get_nfo_path_from_video(video_path)
        assert result_no_mapping is None

    def test_non_wsl_equivalent(self, tmp_path, monkeypatch):
        """非 WSL 環境：mapping 存在也不生效，行為與改動前字面等價。"""
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        video_path_str = str(video_dir / "movie.mp4")
        nfo_file = video_dir / "movie.nfo"
        nfo_file.write_text("<movie></movie>", encoding="utf-8")

        mappings = {str(video_dir): "//NAS/share"}
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "linux")

        result = get_nfo_path_from_video(video_path_str, mappings)
        assert result == str(nfo_file)

        # NFO 不存在 → None
        missing_path = str(video_dir / "missing.mp4")
        assert get_nfo_path_from_video(missing_path, mappings) is None

    def test_no_mapping_equivalent(self, tmp_path):
        """無 mapping（None）：行為與改動前字面等價。"""
        video_dir = tmp_path / "videos2"
        video_dir.mkdir()
        video_path_str = str(video_dir / "movie.mp4")
        nfo_file = video_dir / "movie.nfo"
        nfo_file.write_text("<movie></movie>", encoding="utf-8")

        result = get_nfo_path_from_video(video_path_str, None)
        assert result == str(nfo_file)

        missing_path = str(video_dir / "missing.mp4")
        assert get_nfo_path_from_video(missing_path, None) is None

    def test_default_none_caller_unchanged(self, tmp_path):
        """既有呼叫端形狀（不傳 path_mappings）維持零回歸。"""
        video_dir = tmp_path / "videos3"
        video_dir.mkdir()
        video_path_str = str(video_dir / "movie.mp4")
        nfo_file = video_dir / "movie.nfo"
        nfo_file.write_text("<movie></movie>", encoding="utf-8")

        result = get_nfo_path_from_video(video_path_str)
        assert result == str(nfo_file)

        missing_path = str(video_dir / "missing.mp4")
        assert get_nfo_path_from_video(missing_path) is None
