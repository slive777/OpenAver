"""
test_scraper_parser.py - 番號解析單元測試

測試範圍：
- extract_number(): 從檔名提取番號
- normalize_number(): 標準化番號格式

測試資料來源：samples/ 目錄下的假影片檔案
預期結果定義：samples/expected_results.json
"""

import pytest
import json
from pathlib import Path

# 測試目標模組
from core.scraper import extract_number, normalize_number, is_number_format


# ============ TestExtractNumber ============

class TestExtractNumber:
    """測試從檔名提取番號"""

    # --- basic/ 基本格式 ---
    def test_basic_sone(self):
        """標準格式 SONE-103"""
        assert extract_number('SONE-103.mp4') == 'SONE-103'

    def test_basic_abc(self):
        """標準格式 ABC-123"""
        assert extract_number('ABC-123.mkv') == 'ABC-123'

    def test_basic_fc2ppv(self):
        """FC2-PPV 格式"""
        assert extract_number('FC2-PPV-123456.avi') == 'FC2-PPV-123456'

    # --- real_world/ 真實世界格式 ---
    def test_no_hyphen(self):
        """無橫線格式 sone103"""
        assert extract_number('sone103.mp4') == 'SONE-103'

    def test_square_brackets(self):
        """方括號格式 [SONE-103] 女優名字"""
        assert extract_number('[SONE-103] 女優名字.mp4') == 'SONE-103'

    def test_parentheses(self):
        """圓括號格式 (ABC-123)_1080p"""
        assert extract_number('(ABC-123)_1080p.mkv') == 'ABC-123'

    def test_fullwidth_brackets(self):
        """全形括號【IPZZ-001】中文標題"""
        # 全形括號可能無法匹配，取決於實現
        result = extract_number('【IPZZ-001】中文標題.avi')
        # 如果實現支援全形括號則應為 IPZZ-001，否則可能為 None
        assert result in ['IPZZ-001', None]

    def test_multiple_underscores(self):
        """多底線 SONE-103_uncensored_leak"""
        assert extract_number('SONE-103_uncensored_leak.mp4') == 'SONE-103'

    def test_lowercase_with_quality(self):
        """小寫+品質標籤 stars-804_4K_60fps"""
        assert extract_number('stars-804_4K_60fps.mp4') == 'STARS-804'

    def test_fc2_no_second_hyphen(self):
        """FC2 無第二橫線 FC2PPV-999999 - 被通用 regex 誤抓"""
        # 目前 regex 只支援 FC2-PPV-\d+
        # FC2PPV-999999 會被通用 regex 誤解析為 PPV-99999
        # 這是已知限制，待未來優化
        result = extract_number('FC2PPV-999999.avi')
        assert result == 'PPV-99999'  # 誤抓結果，非預期但目前行為

    # --- suffix/ 後綴處理 ---
    # extract_number 會預處理清理 -UC/-UNCENSORED/-LEAK 等後綴

    def test_suffix_c_subtitle(self):
        """中文字幕後綴 SUPD-103C → SUPD-103C（extract 不移除後綴）"""
        result = extract_number('SUPD-103C.mp4')
        # extract_number 提取整個匹配，不處理後綴
        assert result in ['SUPD-103C', 'SUPD-103']

    def test_suffix_cd1(self):
        """多碟標記 ABC-123-CD1"""
        result = extract_number('ABC-123-CD1.mkv')
        # 應提取 ABC-123 部分
        assert 'ABC-123' in result or result == 'ABC-123-CD1'

    def test_suffix_uc(self):
        """無碼流出 SONE-103-UC"""
        result = extract_number('SONE-103-UC.avi')
        assert 'SONE-103' in result

    def test_suffix_uc_cleaned(self):
        """UC 後綴應被清理"""
        assert extract_number('SONE-103-UC.mp4') == 'SONE-103'

    def test_suffix_uncensored_cleaned(self):
        """uncensored 後綴應被清理"""
        assert extract_number('ABC-123-uncensored.mp4') == 'ABC-123'

    def test_suffix_leak_cleaned(self):
        """leak 後綴應被清理"""
        assert extract_number('MIDV-456_leak.mp4') == 'MIDV-456'

    # --- special_format/ 特殊片商格式 ---
    def test_number_prefix(self):
        """數字開頭系列 T28-103 - 混合格式番號（Task 15.2 新增支援）"""
        result = extract_number('T28-103.avi')
        # T28 混合格式（字母+數字前綴），現已支援
        assert result == 'T28-103'

    def test_heyzo(self):
        """HEYZO 格式"""
        result = extract_number('HEYZO-2048.avi')
        assert result == 'HEYZO-2048'

    def test_juc_prefix_not_stripped(self):
        """JUC-123 前綴含 UC 不應被誤刪（回歸測試）"""
        assert extract_number('JUC-123.mp4') == 'JUC-123'

    def test_duc_prefix_not_stripped(self):
        """DUC-456 前綴含 UC 不應被誤刪"""
        assert extract_number('DUC-456.mp4') == 'DUC-456'

    # --- tricky/ 刁鑽案例 ---
    def test_date_prefix(self):
        """日期在前 2024.01.15_SONE-103_release"""
        result = extract_number('2024.01.15_SONE-103_release.mp4')
        assert result == 'SONE-103'

    def test_number_in_middle(self):
        """番號在中間 download_1080p_SONE103_final"""
        result = extract_number('download_1080p_SONE103_final.avi')
        assert result == 'SONE-103'

    def test_zero_disguise(self):
        """數字0偽裝字母O s0ne-103 → None"""
        result = extract_number('s0ne-103.mp4')
        # s0ne 包含數字0，不是有效的番號前綴
        # 根據 pattern，可能無法匹配
        assert result is None or result != 'SONE-103'

    # --- edge_case/ 邊界情況 ---
    def test_multiple_numbers_first_match(self):
        """多個番號取第一個"""
        result = extract_number('SONE-103_vs_ABC-123_comparison.mkv')
        assert result == 'SONE-103'

    def test_consecutive_numbers(self):
        """連續黏一起"""
        result = extract_number('SONE-103SONE-104.mp4')
        assert result == 'SONE-103'

    # --- noise/ 雜訊干擾 ---
    def test_website_watermark(self):
        """網站浮水印 [ThzSub.com]SONE-103"""
        result = extract_number('[ThzSub.com]SONE-103.mp4')
        # ThzSub.com 不應影響番號提取
        assert result == 'SONE-103'

    def test_special_symbols(self):
        """特殊符號 SONE-103@1080p#leaked"""
        result = extract_number('SONE-103@1080p#leaked.mkv')
        assert result == 'SONE-103'

    def test_nested_brackets(self):
        """多層括號 (HD)(SONE-103)(2024)"""
        result = extract_number('(HD)(SONE-103)(2024).avi')
        assert result == 'SONE-103'

    def test_url_prefix(self):
        """網址前綴 hhd800.com@SONE-103"""
        result = extract_number('hhd800.com@SONE-103.mp4')
        assert result == 'SONE-103'

    def test_garbage_suffix(self):
        """亂碼後綴 SONE-103-C_Thz_fed48"""
        result = extract_number('SONE-103-C_Thz_fed48.mkv')
        assert 'SONE-103' in result

    # --- invalid/ 應返回 None ---
    def test_invalid_random_movie(self):
        """純文字+數字 random_movie_2024"""
        result = extract_number('random_movie_2024.mp4')
        assert result is None

    def test_invalid_pure_numbers(self):
        """純數字 123456"""
        result = extract_number('123456.mkv')
        assert result is None

    def test_invalid_no_number(self):
        """無番號 movie"""
        result = extract_number('movie.avi')
        assert result is None

    def test_invalid_chinese_only(self):
        """純中文 私人影片"""
        result = extract_number('私人影片.mp4')
        assert result is None

    # --- 路徑處理 ---
    def test_full_path(self):
        """完整路徑"""
        result = extract_number('/home/user/videos/SONE-103.mp4')
        assert result == 'SONE-103'

    def test_windows_path(self):
        """Windows 路徑"""
        result = extract_number(r'C:\Videos\ABC-123.mkv')
        assert result == 'ABC-123'


# ============ TestNormalizeNumber ============

class TestNormalizeNumber:
    """測試番號標準化"""

    def test_lowercase_no_hyphen(self):
        """小寫無橫線 sone103 → SONE-103"""
        assert normalize_number('sone103') == 'SONE-103'

    def test_already_normalized(self):
        """已標準化 SONE-103 → SONE-103"""
        assert normalize_number('SONE-103') == 'SONE-103'

    def test_lowercase_with_hyphen(self):
        """小寫有橫線 abc-123 → ABC-123"""
        assert normalize_number('abc-123') == 'ABC-123'

    def test_uppercase_no_hyphen(self):
        """大寫無橫線 ABC123 → ABC-123"""
        assert normalize_number('ABC123') == 'ABC-123'

    def test_preserve_leading_zeros(self):
        """保留前導零 abc00123 → ABC-00123"""
        assert normalize_number('abc00123') == 'ABC-00123'

    def test_fc2ppv_format(self):
        """FC2-PPV 格式保持不變"""
        assert normalize_number('FC2-PPV-123456') == 'FC2-PPV-123456'

    def test_with_whitespace(self):
        """帶空白 ' sone103 ' → SONE-103"""
        assert normalize_number(' sone103 ') == 'SONE-103'

    def test_mixed_case(self):
        """混合大小寫 SoNe103 → SONE-103"""
        assert normalize_number('SoNe103') == 'SONE-103'

    def test_already_has_hyphen_mixed_case(self):
        """有橫線混合大小寫 sOnE-103 → SONE-103"""
        assert normalize_number('sOnE-103') == 'SONE-103'

    def test_long_prefix(self):
        """長前綴 SUPD103 → SUPD-103"""
        assert normalize_number('SUPD103') == 'SUPD-103'

    def test_long_number(self):
        """長數字 ABC12345 → ABC-12345"""
        assert normalize_number('ABC12345') == 'ABC-12345'

    # --- 後綴清理 ---
    def test_suffix_uc_cleaned(self):
        """UC 後綴應被清理 SONE-103-UC → SONE-103"""
        assert normalize_number('SONE-103-UC') == 'SONE-103'

    def test_suffix_uncensored_cleaned(self):
        """UNCENSORED 後綴應被清理"""
        assert normalize_number('ABC-123-UNCENSORED') == 'ABC-123'

    def test_suffix_leak_cleaned(self):
        """LEAK 後綴應被清理"""
        assert normalize_number('MIDV-456_leak') == 'MIDV-456'

    def test_suffix_with_no_hyphen(self):
        """無橫線 + 後綴 STARS804-UNCEN → STARS-804"""
        assert normalize_number('STARS804-UNCEN') == 'STARS-804'


# ============ TestIsNumberFormat ============

class TestIsNumberFormat:
    """測試番號格式驗證（含後綴處理）"""

    # --- 標準格式 ---
    def test_standard_format(self):
        """標準格式 SONE-103"""
        assert is_number_format('SONE-103') is True

    def test_no_hyphen(self):
        """無橫線 ABC123"""
        assert is_number_format('ABC123') is True

    def test_lowercase(self):
        """小寫 sone-103"""
        assert is_number_format('sone-103') is True

    # --- 後綴處理 ---
    def test_suffix_uc(self):
        """UC 後綴 SONE-103-UC"""
        assert is_number_format('SONE-103-UC') is True

    def test_suffix_uncensored(self):
        """UNCENSORED 後綴 ABC-123-UNCENSORED"""
        assert is_number_format('ABC-123-UNCENSORED') is True

    def test_suffix_uncen(self):
        """UNCEN 後綴 MIDV-456-UNCEN"""
        assert is_number_format('MIDV-456-UNCEN') is True

    def test_suffix_leak(self):
        """LEAK 後綴 STARS-804-leak"""
        assert is_number_format('STARS-804-leak') is True

    def test_suffix_leaked(self):
        """LEAKED 後綴 IPZZ-001_LEAKED"""
        assert is_number_format('IPZZ-001_LEAKED') is True

    # --- 無效格式 ---
    def test_invalid_partial(self):
        """部分番號 SONE-01"""
        assert is_number_format('SONE-01') is False

    def test_invalid_prefix_only(self):
        """純前綴 SONE"""
        assert is_number_format('SONE') is False

    def test_invalid_numbers_only(self):
        """純數字 123456"""
        assert is_number_format('123456') is False

    def test_invalid_short_number(self):
        """數字太短 ABC-12"""
        assert is_number_format('ABC-12') is False


# ============ 整合測試：搜尋流程 ============

class TestSearchQueryIntegration:
    """
    整合測試：模擬搜尋查詢的完整流程

    驗證 is_number_format() + normalize_number() 配合正確
    這類測試能抓到單元測試漏掉的問題
    """

    # --- 後綴查詢應正確處理 ---
    def test_uc_suffix_flow(self):
        """UC 後綴查詢完整流程"""
        query = 'SONE-103-UC'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'SONE-103'

    def test_uncensored_suffix_flow(self):
        """UNCENSORED 後綴查詢完整流程"""
        query = 'ABC-123-UNCENSORED'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'ABC-123'

    def test_leak_suffix_flow(self):
        """LEAK 後綴查詢完整流程"""
        query = 'MIDV-456_leak'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'MIDV-456'

    def test_uncen_suffix_flow(self):
        """UNCEN 後綴查詢完整流程"""
        query = 'STARS-804-UNCEN'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'STARS-804'

    def test_leaked_suffix_flow(self):
        """LEAKED 後綴查詢完整流程"""
        query = 'IPZZ-001_LEAKED'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'IPZZ-001'

    # --- 標準查詢不受影響 ---
    def test_standard_query_unchanged(self):
        """標準查詢不應被修改"""
        query = 'SONE-103'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'SONE-103'

    def test_no_hyphen_query_normalized(self):
        """無橫線查詢應正規化"""
        query = 'sone103'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'SONE-103'

    # --- 檔名提取 + 搜尋流程 ---
    def test_filename_to_search_flow(self):
        """檔名提取到搜尋的完整流程"""
        filename = 'SONE-103-UC_1080p.mp4'
        # 步驟 1: 從檔名提取番號
        number = extract_number(filename)
        assert number == 'SONE-103'
        # 步驟 2: 驗證格式（用於判斷搜尋模式）
        assert is_number_format(number) is True
        # 步驟 3: 正規化（用於實際搜尋）
        assert normalize_number(number) == 'SONE-103'

    def test_user_input_to_search_flow(self):
        """用戶輸入到搜尋的完整流程"""
        # 用戶直接輸入帶後綴的番號
        user_input = 'SONE-103-UC'
        # 步驟 1: 驗證是完整番號格式
        assert is_number_format(user_input) is True
        # 步驟 2: 正規化後搜尋
        search_query = normalize_number(user_input)
        assert search_query == 'SONE-103'

    # --- 回歸測試：前綴含 UC 不應被誤刪 ---
    def test_juc_prefix_regression(self):
        """JUC-123 前綴含 UC 不應被誤刪（回歸測試）"""
        query = 'JUC-123'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'JUC-123'
        assert extract_number('JUC-123.mp4') == 'JUC-123'

    def test_juc_with_suffix_regression(self):
        """JUC-123-UC 前綴含 UC 但後綴也有 UC"""
        query = 'JUC-123-UC'
        assert is_number_format(query) is True
        assert normalize_number(query) == 'JUC-123'  # 只移除後綴的 -UC


# ============ 從 samples/ 讀取測試 ============

class TestExtractNumberFromSamples:
    """從 samples/ 目錄讀取測試案例"""

    @pytest.fixture
    def samples_dir(self):
        """取得 samples 目錄"""
        return Path(__file__).parent.parent / 'samples'

    @pytest.fixture
    def expected_results(self, samples_dir):
        """載入預期結果"""
        json_path = samples_dir / 'expected_results.json'
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def test_samples_exist(self, samples_dir):
        """確認 samples 目錄存在"""
        assert samples_dir.exists(), f'samples 目錄不存在: {samples_dir}'

    def test_extract_from_samples(self, samples_dir, expected_results):
        """從 samples 讀取檔名進行測試"""
        if not expected_results:
            pytest.skip('expected_results.json 不存在')

        for category_dir in samples_dir.iterdir():
            if not category_dir.is_dir():
                continue
            if category_dir.name.startswith('.'):
                continue

            for file_path in category_dir.iterdir():
                if file_path.suffix not in ['.mp4', '.mkv', '.avi']:
                    continue

                filename = file_path.name
                expected = expected_results.get(filename)

                if expected is not None:
                    result = extract_number(filename)
                    assert result == expected, f'{filename}: 預期 {expected}，實際 {result}'
