"""
T1e Tests — Fix-1 版本標記測試
測試 core/organizer.py 的 _detect_suffixes(), format_string(), organize_file()
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from core.organizer import _detect_suffixes, format_string, organize_file, crop_to_poster, generate_nfo, extract_chinese_title, download_image


# ============ _detect_suffixes() 測試 ============

class TestDetectSuffixes:
    """_detect_suffixes() 的單元測試"""

    def test_detect_suffixes_basic(self):
        """基本單一關鍵字偵測：SONE-205-CD1.mp4 應匹配 -cd1"""
        result = _detect_suffixes("SONE-205-CD1.mp4", ["-cd1", "-cd2"])
        assert result == "-cd1"

    def test_detect_suffixes_multiple(self):
        """多關鍵字同時偵測：SONE-205-4K-CD1.mp4 應匹配 -cd1 和 -4k"""
        result = _detect_suffixes("SONE-205-4K-CD1.mp4", ["-cd1", "-4k"])
        # 兩個關鍵字都應被匹配，順序依 keywords 列表順序（-cd1 先，-4k 後）
        assert "-cd1" in result
        assert "-4k" in result

    def test_detect_suffixes_case_insensitive(self):
        """大小寫不敏感：SONE-205-4k.mp4 應匹配 -4K（關鍵字大寫）"""
        result = _detect_suffixes("SONE-205-4k.mp4", ["-4K"])
        assert result != ""
        assert "-4k" in result

    def test_detect_suffixes_no_match(self):
        """無匹配：SONE-205.mp4 對 -cd1 應回傳空字串"""
        result = _detect_suffixes("SONE-205.mp4", ["-cd1"])
        assert result == ""

    def test_detect_suffixes_boundary_no_false_positive(self):
        """邊界保護：-cd1 不應匹配 -cd10（避免子字串誤匹配）"""
        result = _detect_suffixes("SONE-205-CD10.mp4", ["-cd1"])
        assert result == ""

    def test_detect_suffixes_boundary_separator(self):
        """
        分隔符邊界：
        - SONE-205-CD1_UC.mp4 中，-cd1 後緊跟 _ 分隔符，應正確匹配 -cd1
        - _UC 使用底線前綴，關鍵字 _uc 應匹配；關鍵字 -uc（連字號前綴）不匹配
        """
        # -cd1 後緊跟 _ 分隔符，邊界正則應通過
        result = _detect_suffixes("SONE-205-CD1_UC.mp4", ["-cd1", "_uc"])
        assert "-cd1" in result
        assert "_uc" in result

    def test_detect_suffixes_order_follows_keywords(self):
        """多 keyword 時，輸出順序按 keyword 列表，不按檔名順序（canonical 化設計）"""
        # keywords ['-cd1', '-4k']，檔名 '-4k-cd1' 反序
        result = _detect_suffixes("ABC-123-4k-cd1.mp4", ["-cd1", "-4k"])
        assert result == "-cd1-4k", f"預期按 keyword 列表順序 '-cd1-4k'，實際 {result!r}"


# ============ format_string() 測試 ============

class TestFormatStringSuffix:
    """format_string() 的 {suffix} 變數測試"""

    def test_format_string_suffix(self):
        """suffix 非空時應出現在輸出中"""
        result = format_string(
            "[{num}] {title}{suffix}",
            {"number": "SONE-205", "title": "title", "suffix": "-4k-cd1"}
        )
        assert result == "[SONE-205] title-4k-cd1"

    def test_format_string_suffix_empty(self):
        """suffix 空字串時，{suffix} 應消失，不留多餘字元"""
        result = format_string(
            "[{num}] {title}{suffix}",
            {"number": "SONE-205", "title": "title", "suffix": ""}
        )
        assert result == "[SONE-205] title"


class TestFormatStringFallback:
    """format_string() use_fallback 參數測試"""

    def test_format_string_fallback_actor(self):
        result = format_string("{actor}", {"actors": []}, use_fallback=True)
        assert result == "未知女優"

    def test_format_string_fallback_maker(self):
        result = format_string("{maker}", {"maker": ""}, use_fallback=True)
        assert result == "未知片商"

    def test_format_string_fallback_year(self):
        result = format_string("{year}", {"date": ""}, use_fallback=True)
        assert result == "未知年份"

    def test_format_string_fallback_date(self):
        result = format_string("{date}", {"date": ""}, use_fallback=True)
        assert result == "未知日期"

    def test_format_string_fallback_title(self):
        result = format_string("{title}", {"title": ""}, use_fallback=True)
        assert result == "未知標題"

    def test_format_string_no_fallback_default(self):
        result = format_string("{actor}", {"actors": []})  # use_fallback=False
        assert result == ""

    def test_format_string_has_value_no_fallback(self):
        result = format_string("{actor}", {"actors": ["三上悠亞"]}, use_fallback=True)
        assert result == "三上悠亞"

    def test_format_string_fallback_month(self):
        result = format_string("{month}", {"date": ""}, use_fallback=True)
        assert result == "未知月份"

    def test_format_string_fallback_day(self):
        result = format_string("{day}", {"date": ""}, use_fallback=True)
        assert result == "未知日"

    def test_format_string_no_fallback_month(self):
        result = format_string("{month}", {"date": ""})  # use_fallback=False
        assert result == ""

    def test_format_string_no_fallback_day(self):
        result = format_string("{day}", {"date": ""})  # use_fallback=False
        assert result == ""


class TestFormatStringDateVariables:
    """format_string() {year}/{month}/{day}/{date} 變數展開測試"""

    def test_full_iso_date_year(self):
        """完整 ISO 日期：{year} = "2015"""
        result = format_string("{year}", {"date": "2015-06-01"})
        assert result == "2015"

    def test_full_iso_date_month(self):
        """完整 ISO 日期：{month} = "06"""
        result = format_string("{month}", {"date": "2015-06-01"})
        assert result == "06"

    def test_full_iso_date_day(self):
        """完整 ISO 日期：{day} = "01"""
        result = format_string("{day}", {"date": "2015-06-01"})
        assert result == "01"

    def test_full_iso_date_date(self):
        """完整 ISO 日期：{date} = "2015-06-01"""
        result = format_string("{date}", {"date": "2015-06-01"})
        assert result == "2015-06-01"

    def test_partial_date_year_month_only(self):
        """部分日期 "2015-06"：{year}="2015" / {month}="06"""
        year_result = format_string("{year}", {"date": "2015-06"})
        month_result = format_string("{month}", {"date": "2015-06"})
        assert year_result == "2015"
        assert month_result == "06"

    def test_partial_date_day_fallback_folder(self):
        """部分日期 "2015-06"：{day} 走 folder fallback = "未知日"""
        result = format_string("{day}", {"date": "2015-06"}, use_fallback=True)
        assert result == "未知日"

    def test_partial_date_day_fallback_filename(self):
        """部分日期 "2015-06"：{day} 走 filename fallback = """""
        result = format_string("{day}", {"date": "2015-06"}, use_fallback=False)
        assert result == ""

    def test_year_only_month_fallback_folder(self):
        """純年份 "2015"：{month} 走 folder fallback = "未知月份"""
        result = format_string("{month}", {"date": "2015"}, use_fallback=True)
        assert result == "未知月份"

    def test_year_only_day_fallback_folder(self):
        """純年份 "2015"：{day} 走 folder fallback = "未知日"""
        result = format_string("{day}", {"date": "2015"}, use_fallback=True)
        assert result == "未知日"

    def test_empty_date_all_fallback_folder(self):
        """空字串：{year}/{month}/{day}/{date} 全部走 folder fallback"""
        assert format_string("{year}", {"date": ""}, use_fallback=True) == "未知年份"
        assert format_string("{month}", {"date": ""}, use_fallback=True) == "未知月份"
        assert format_string("{day}", {"date": ""}, use_fallback=True) == "未知日"
        assert format_string("{date}", {"date": ""}, use_fallback=True) == "未知日期"

    def test_filename_format_ymd_full_date(self):
        """{year}-{month}-{day} + 完整 date → 展開 "2015-06-01"""
        result = format_string("{year}-{month}-{day}", {"date": "2015-06-01"})
        assert result == "2015-06-01"

    def test_filename_format_dmy_full_date(self):
        """{day}_{month}_{year} (DMY) + 完整 date → 展開 "01_06_2015"""
        result = format_string("{day}_{month}_{year}", {"date": "2015-06-01"})
        assert result == "01_06_2015"


# ============ organize_file() 整合測試 ============

def _make_config(tmp_path: Path, suffix_keywords=None) -> dict:
    """建立測試用 config dict，使用 tmp_path 作為輸出目錄"""
    if suffix_keywords is None:
        suffix_keywords = ["-cd1", "-cd2", "-4k", "-uc"]
    return {
        "create_folder": False,           # 測試時不建子資料夾，簡化路徑計算
        "filename_format": "[{num}] {title}{suffix}",
        "download_cover": False,          # 不真正下載封面
        "cover_filename": "poster.jpg",
        "create_nfo": False,              # 不生成 NFO，避免依賴
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": suffix_keywords,
    }


def _make_metadata(number: str = "SONE-205", title: str = "Test Title") -> dict:
    """建立測試用 metadata dict"""
    return {
        "number": number,
        "title": title,
        "actors": [],
        "tags": [],
        "maker": "S1",
        "date": "2024-01-15",
        "cover": "",   # 空字串，跳過下載
        "url": "",
    }


class TestOrganizeDuplicateDetection:
    """organize_file() 覆蓋偵測測試"""

    def test_organize_duplicate_detection(self, tmp_path):
        """
        目標路徑已存在時：
        - result['duplicate'] == True
        - result['success'] == False
        - 原始檔案未被覆蓋（兩個檔案都應存在）
        """
        # 建立原始檔案
        src_file = tmp_path / "SONE-205.mp4"
        src_file.write_bytes(b"source content")

        # 建立目標同名檔案（模擬已存在）
        # format_string 會產生 "[SONE-205] Test Title" -> 去掉 suffix（空）
        # create_folder=False，所以目標在同一目錄
        target_file = tmp_path / "[SONE-205] Test Title.mp4"
        target_file.write_bytes(b"existing content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        result = organize_file(str(src_file), metadata, config)

        assert result.get("duplicate") is True
        assert result["success"] is False
        # 原始檔案應仍存在（未被移動）
        assert src_file.exists(), "原始檔案不應被移動或刪除"
        # 目標檔案內容不應被覆蓋
        assert target_file.read_bytes() == b"existing content"

    def test_organize_suffix_in_filename(self, tmp_path):
        """
        CD1 和 CD2 兩個檔案分別 organize 後應產生不同目標路徑。
        """
        # 建立 CD1 檔案
        cd1_file = tmp_path / "SONE-205-CD1.mp4"
        cd1_file.write_bytes(b"cd1 content")

        # 建立 CD2 檔案
        cd2_file = tmp_path / "SONE-205-CD2.mp4"
        cd2_file.write_bytes(b"cd2 content")

        config = _make_config(tmp_path)
        metadata = _make_metadata()

        result1 = organize_file(str(cd1_file), metadata, config)
        result2 = organize_file(str(cd2_file), metadata, config)

        assert result1["success"] is True, f"CD1 organize 失敗：{result1.get('error')}"
        assert result2["success"] is True, f"CD2 organize 失敗：{result2.get('error')}"

        # 兩個輸出路徑應不同
        assert result1["new_filename"] != result2["new_filename"], \
            "CD1 和 CD2 產生了相同的目標路徑"

        # CD1 應帶 -cd1 後綴，CD2 應帶 -cd2 後綴
        assert "-cd1" in Path(result1["new_filename"]).name
        assert "-cd2" in Path(result2["new_filename"]).name


class TestOrganizeTruncateSuffix:
    """organize_file() 長標題時 suffix 不應被截斷"""

    def test_suffix_not_truncated_by_max_chars(self, tmp_path):
        """
        長標題超過 max_filename_length 時，suffix 仍應保留。
        例：max_filename_length=30，title 很長，suffix="-cd1" 不應被截掉。
        """
        # 建立檔案
        src = tmp_path / "SONE-205-CD1.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}][{maker}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 40,  # 故意很短，迫使截斷
            "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
        }
        metadata = {
            "number": "SONE-205",
            "title": "超級無敵長的標題名稱會被截斷但後綴應該保留",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        new_name = Path(result["new_filename"]).name
        # suffix -cd1 必須在檔名中保留
        assert "-cd1" in new_name, f"suffix -cd1 被截斷: {new_name}"

    def test_small_max_filename_length_with_suffix(self, tmp_path):
        """
        回歸測試：max_filename_length 極小時，檔名長度不應超限。
        max_filename_length=12, suffix=-cd1, ext=.mp4 → stem+ext 應 <= 12
        """
        src = tmp_path / "SONE-205-CD1.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 12,
            "suffix_keywords": ["-cd1", "-cd2"],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        new_name = Path(result["new_filename"]).name
        assert len(new_name) <= 12, (
            f"檔名長度 {len(new_name)} 超過 max_filename_length=12: {new_name}"
        )

    @pytest.mark.parametrize("max_len", [6, 7, 8])
    def test_suffix_longer_than_budget(self, tmp_path, max_len):
        """
        極端邊界：max_filename_length 比 suffix+ext 還小時，
        檔名長度仍不應超過 max_filename_length。
        """
        src = tmp_path / "SONE-205-CD1.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": max_len,
            "suffix_keywords": ["-cd1"],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        new_name = Path(result["new_filename"]).name
        assert len(new_name) <= max_len, (
            f"檔名長度 {len(new_name)} 超過 max_filename_length={max_len}: {new_name}"
        )


class TestOrganizeFallback:
    """organize_file() fallback 資料夾建立與 used_fallbacks 欄位測試"""

    def test_organize_fallback_creates_folder(self, tmp_path):
        # actors=[]，folder="{actor}" → 建立 "未知女優/" 子資料夾
        # 不能用 _make_config，需 create_folder=True + folder_layers
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{actor}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": [], "tags": [], "maker": "S1",
            "date": "2024-01-15", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result["new_folder"] is not None
        folder_name = Path(result["new_folder"]).name
        assert folder_name == "未知女優"

    def test_organize_filename_no_fallback(self, tmp_path):
        # actors=[]，filename="{actor}" → 檔名不含 "未知女優"
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": False,
            "filename_format": "[{num}][{actor}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": [], "tags": [], "maker": "S1",
            "date": "2024-01-15", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        new_name = Path(result["new_filename"]).name
        assert "未知女優" not in new_name
        assert "[SONE-205]" in new_name

    def test_organize_used_fallbacks_field(self, tmp_path):
        # actors=[], date="" + create_folder=True + folder 含 {actor}/{year}
        # → used_fallbacks 包含 ['女優', '日期']
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{actor}", "{year}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": [], "tags": [], "maker": "S1",
            "date": "", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert result["used_fallbacks"] == ["女優", "日期"]

    def test_organize_no_fallbacks_when_complete(self, tmp_path):
        # 所有欄位有值 → used_fallbacks == []
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = _make_config(tmp_path)
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": ["三上悠亞"], "tags": [], "maker": "S1",
            "date": "2024-01-15", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert result["used_fallbacks"] == []

    def test_organize_fallback_amateur_no_actress(self, tmp_path):
        """素人片（CHN-180）有 title/maker/date 但無演員 — 僅女優觸發 fallback"""
        src = tmp_path / "CHN-180.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{actor}"],
            "filename_format": "[{num}][{maker}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "CHN-180",
            "title": "新・素人娘、お貸しします。 VOL.83",
            "actors": [],
            "tags": ["素人", "美乳"],
            "maker": "プレステージ",
            "date": "2023-05-12",
            "cover": "",
            "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        # 僅女優觸發 fallback（maker/date/title 都有值）
        assert result["used_fallbacks"] == ["女優"]
        # 資料夾名為 fallback 值
        folder_name = Path(result["new_folder"]).name
        assert folder_name == "未知女優"
        # 檔名不含 fallback（檔名不啟用 fallback）
        filename_only = Path(result["new_filename"]).name
        assert "未知女優" not in filename_only
        # 檔名包含片商（有值，正常顯示）
        assert "プレステージ" in filename_only

    def test_organize_used_fallbacks_create_folder_false(self, tmp_path):
        """create_folder=false 時不應有任何 fallback 報告"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = _make_config(tmp_path)  # create_folder=False
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": [], "tags": [], "maker": "",
            "date": "", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert result["used_fallbacks"] == [], (
            f"create_folder=false 時 used_fallbacks 應為空，實際: {result['used_fallbacks']}"
        )

    def test_partial_date_year_only_warns_for_month(self, tmp_path):
        """date='2015'（僅年），folder 含 {month} → used_fallbacks 包含 '日期'（len < 7）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{year}", "{month}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": ["三上悠亞"], "tags": [], "maker": "S1",
            "date": "2015", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert "日期" in result["used_fallbacks"], (
            f"date='2015' + {{month}} 應 append '日期'，實際 used_fallbacks: {result['used_fallbacks']}"
        )

    def test_partial_date_year_month_warns_for_day(self, tmp_path):
        """date='2015-06'（年月），folder 含 {day} → used_fallbacks 包含 '日期'（len < 10）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{year}", "{month}", "{day}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": ["三上悠亞"], "tags": [], "maker": "S1",
            "date": "2015-06", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert "日期" in result["used_fallbacks"], (
            f"date='2015-06' + {{day}} 應 append '日期'，實際 used_fallbacks: {result['used_fallbacks']}"
        )

    def test_partial_date_year_month_no_false_alarm(self, tmp_path):
        """date='2015-06'（年月），folder 只含 {year}{month}（無 {day}）→ 無 '日期' fallback"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{year}", "{month}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": ["三上悠亞"], "tags": [], "maker": "S1",
            "date": "2015-06", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert "日期" not in result["used_fallbacks"], (
            f"date='2015-06' 對 {{year}}{{month}} 不應 append '日期'，實際 used_fallbacks: {result['used_fallbacks']}"
        )

    def test_full_date_no_warn(self, tmp_path):
        """date='2015-06-15'（完整），folder 含 {year}{month}{day} → used_fallbacks 不含 '日期'"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")
        config = {
            "create_folder": True,
            "folder_layers": ["{year}", "{month}", "{day}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205", "title": "Test Title",
            "actors": ["三上悠亞"], "tags": [], "maker": "S1",
            "date": "2015-06-15", "cover": "", "url": "",
        }
        result = organize_file(str(src), metadata, config)
        assert result["success"] is True
        assert "日期" not in result["used_fallbacks"], (
            f"date='2015-06-15' 完整日期不應 append '日期'，實際 used_fallbacks: {result['used_fallbacks']}"
        )


# ============ organize_file() 錯誤處理測試 (T4 安全修正) ============

class TestOrganizeErrorHandling:
    """organize_file() 錯誤訊息安全性測試 — 確認固定訊息，不洩漏內部細節"""

    def test_permission_error_returns_fixed_message(self, tmp_path):
        """
        os.makedirs 拋出 PermissionError 時：
        - result['success'] == False（保持預設值）
        - result['error'] 是固定中文訊息，不含 traceback 或 exception 字串
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": True,
            "folder_layers": ["{actor}"],
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": ["三上悠亞"],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        with patch("core.organizer.os.makedirs", side_effect=PermissionError("access denied")):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"] == "無法建立資料夾，請確認目標路徑的寫入權限"
        # 確認不含原始 exception 字串（安全規範）
        assert "access denied" not in (result["error"] or "")
        assert "PermissionError" not in (result["error"] or "")

    def test_general_exception_returns_fixed_message(self, tmp_path):
        """
        shutil.move 拋出一般 Exception 時：
        - result['success'] == False（保持預設值）
        - result['error'] 是固定訊息 '檔案整理失敗，請查看日誌'，不含原始 exception 字串
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        secret_msg = "internal disk error XYZ-9999"
        with patch("core.organizer.shutil.move", side_effect=OSError(secret_msg)):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert result["error"] == "檔案整理失敗，請查看日誌"
        # 確認不含原始 exception 字串（安全規範）
        assert secret_msg not in (result["error"] or "")
        assert "OSError" not in (result["error"] or "")

    def test_normalize_path_error_no_leak(self, tmp_path):
        """
        normalize_path 拋出 ValueError 時：
        - result['error'] 為固定中文訊息，不含原始路徑細節
        """
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"test")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        with patch("core.organizer.normalize_path",
                   side_effect=ValueError(r"WSL 環境不支援 SMB 路徑: \\192.168.1.177\share")):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is False
        assert "192.168.1.177" not in (result["error"] or "")
        assert result["error"] == "路徑格式不支援，請確認路徑設定"


# ============ Jellyfin 圖片模式測試 (Fix-6) ============

def _make_test_image(tmp_path, width, height, name="cover.jpg"):
    """建立指定尺寸的純色 JPEG 測試圖片"""
    img_path = tmp_path / name
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    img.save(str(img_path), "JPEG")
    return img_path


def _mock_download_image_write_jpeg(url, save_path, referer=''):
    """Mock download_image：寫出一個 800x538 JPEG 到 save_path（標準橫向封面尺寸）"""
    img = Image.new("RGB", (800, 538), color=(200, 100, 50))
    img.save(save_path, "JPEG")
    return True


def _make_jellyfin_config(jellyfin_mode):
    return {
        "create_folder": False,
        "filename_format": "[{num}] {title}",
        "download_cover": True,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": [],
        "jellyfin_mode": jellyfin_mode,
    }


class TestCropToPoster:
    """crop_to_poster() 裁切邏輯單元測試"""

    def test_crop_to_poster_landscape(self, tmp_path):
        """800×538 橫向 → 裁切右側，產生直向 poster (w < h)"""
        src = _make_test_image(tmp_path, 800, 538, "cover.jpg")
        dst = tmp_path / "poster.jpg"

        result = crop_to_poster(str(src), str(dst))

        assert result is True
        assert dst.exists()
        with Image.open(dst) as img:
            w, h = img.size
        assert w < h, f"橫向圖片應裁切為直向，實際尺寸: {w}×{h}"

    def test_crop_to_poster_square(self, tmp_path):
        """500×500 方形 → 置中裁切，ratio ≈ 2:3"""
        src = _make_test_image(tmp_path, 500, 500, "cover_sq.jpg")
        dst = tmp_path / "poster_sq.jpg"

        result = crop_to_poster(str(src), str(dst))

        assert result is True
        assert dst.exists()
        with Image.open(dst) as img:
            w, h = img.size
        ratio = h / w
        assert 1.4 <= ratio <= 1.6, f"方形裁切後比例應約 1.5，實際: {ratio:.3f} ({w}×{h})"

    def test_crop_to_poster_portrait(self, tmp_path):
        """380×538 直向 → 直接複製，不裁切（尺寸應不變）"""
        src = _make_test_image(tmp_path, 380, 538, "cover_pt.jpg")
        dst = tmp_path / "poster_pt.jpg"

        result = crop_to_poster(str(src), str(dst))

        assert result is True
        assert dst.exists()
        with Image.open(dst) as img:
            w, h = img.size
        assert (w, h) == (380, 538), f"直向圖片應直接複製（不裁切），實際尺寸: {w}×{h}"


class TestOrganizeJellyfinMode:
    """organize_file() jellyfin_mode 開/關 的整合測試"""

    def test_organize_jellyfin_mode_on(self, tmp_path):
        """jellyfin_mode=True → 產生 cover + fanart + poster 共 3 個圖片檔"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_jellyfin_config(jellyfin_mode=True)
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("cover_path") is not None, "未產生 cover_path"
        assert result.get("fanart_path") is not None, "jellyfin_mode=True 應產生 fanart_path"
        assert result.get("poster_path") is not None, "jellyfin_mode=True 應產生 poster_path"
        assert Path(result["fanart_path"]).exists(), "fanart 檔案不存在"
        assert Path(result["poster_path"]).exists(), "poster 檔案不存在"

    def test_organize_jellyfin_mode_off(self, tmp_path):
        """jellyfin_mode=False → 只產生主封面，不產生 fanart/poster"""
        src = tmp_path / "SONE-205-B.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_jellyfin_config(jellyfin_mode=False)
        metadata = {
            "number": "SONE-205",
            "title": "Test Title B",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("cover_path") is not None, "應產生主封面 cover_path"
        assert result.get("fanart_path") is None, "jellyfin_mode=False 不應產生 fanart_path"
        assert result.get("poster_path") is None, "jellyfin_mode=False 不應產生 poster_path"


class TestNfoPosterTag:
    """generate_nfo() <poster> tag 正確性測試"""

    def test_nfo_poster_tag_fixed(self, tmp_path):
        """不論 jellyfin_mode，<poster> 不再指向 .png（舊 bug 確認修復）"""
        nfo_path = tmp_path / "SONE-205.nfo"

        result = generate_nfo(
            number="SONE-205",
            title="Test Title",
            output_path=str(nfo_path),
            has_poster=False,
            has_fanart=False,
        )

        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<poster>SONE-205.jpg</poster>" in content, \
            f"<poster> 應指向 .jpg（不帶後綴），實際內容包含: {[l for l in content.split(chr(10)) if 'poster' in l.lower()]}"
        assert ".png" not in content, "<poster> 不應包含 .png（T6c 修復）"

    def test_nfo_jellyfin_mode_tags(self, tmp_path):
        """jellyfin_mode=True → <poster> 指向 -poster.jpg，<fanart> 指向 -fanart.jpg"""
        nfo_path = tmp_path / "SONE-205.nfo"

        result = generate_nfo(
            number="SONE-205",
            title="Test Title",
            output_path=str(nfo_path),
            has_poster=True,
            has_fanart=True,
        )

        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<poster>SONE-205-poster.jpg</poster>" in content, \
            f"jellyfin_mode 時 <poster> 應指向 -poster.jpg"
        assert "<fanart>SONE-205-fanart.jpg</fanart>" in content, \
            f"jellyfin_mode 時 <fanart> 應指向 -fanart.jpg"


# ============ Config suffix_keywords 持久化測試 ============

class TestConfigSuffixKeywordsPersistence:
    """suffix_keywords 設定的 save → reload 持久化測試"""

    def test_config_suffix_keywords_persistence(self, client, temp_config_path):
        """
        PUT /api/config 儲存 suffix_keywords 後，GET /api/config 取得的值應不變。
        """
        # 取得當前設定
        response = client.get("/api/config")
        assert response.status_code == 200
        cfg = response.json()["data"]

        # 修改 suffix_keywords
        custom_keywords = ["-cd1", "-cd2", "-4k", "-uc", "-hd"]
        cfg["scraper"]["suffix_keywords"] = custom_keywords

        # 儲存
        put_response = client.put("/api/config", json=cfg)
        assert put_response.status_code == 200
        assert put_response.json()["success"] is True

        # 重新取得，驗證值不變
        get_response = client.get("/api/config")
        assert get_response.status_code == 200
        saved_keywords = get_response.json()["data"]["scraper"]["suffix_keywords"]
        assert saved_keywords == custom_keywords

        # 也直接驗證檔案內容
        with open(temp_config_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data["scraper"]["suffix_keywords"] == custom_keywords


# ============ extract_chinese_title() 測試 ============

class TestExtractChineseTitle:
    def test_mixed_title(self):
        result = extract_chinese_title("Beauty Girl ABP-001 美少女初登場.mp4", "ABP-001")
        assert result == "Beauty Girl 美少女初登場"

    def test_jp_or_zh_only(self):
        result = extract_chinese_title("美少女初登場.mp4", "ABP-001")
        assert result == "美少女初登場"

    def test_english_only(self):
        result = extract_chinese_title("Beauty Girl.mp4", "ABP-001")
        assert result is None

    def test_empty_and_none(self):
        assert extract_chinese_title("", "ABP-001") is None
        assert extract_chinese_title(None, "ABP-001") is None

    def test_with_actors_removal(self):
        # 結尾帶有演員名，會被移除
        result = extract_chinese_title("ABP-001 美少女 三上悠亞.mp4", "ABP-001", actors=["三上悠亞"])
        assert result == "美少女"


class TestExtractChineseTitleSubtitleMarkers:
    """spec-48a.md §a2 行為對照表 — 字幕標記 edge cases

    T2 是 strip_subtitle_markers helper 的第一個實際使用場景。
    本 class 的七個 case 不只驗證 T2 的 wiring，也間接守護 T1 helper
    的 'bracket 先剝、長 pattern 優先' 順序契約：若該順序回歸，
    case #6 的 【中文字幕】 剝除會殘留『中文字幕』四個字 → has_chinese=True
    → 誤判為中文片名回傳 → 斷言 fail（預期 None）。
    """

    @pytest.mark.parametrize("filename, number, expected", [
        ("ABC-123 純中文片名.mp4", "ABC-123", "純中文片名"),           # 1. 真片名保留
        ("ABC-123 エロいやつ.mp4", "ABC-123", None),                   # 2. 純日文，無中文 → None
        ("ABC-123 [中字] 正妹の中文版.mp4", "ABC-123", "正妹の中文版"), # 3. 剝字幕後真片名保留
        ("[中字] ABC-123.mp4", "ABC-123", None),                       # 4. 修前: [中字]，修後: None
        ("ABC-123-中字.mp4", "ABC-123", None),                         # 5. 修前: 殘留 -中字，修後: None
        ("ABC-123【中文字幕】.mp4", "ABC-123", None),                  # 6. 字幕 bracket → None（守護順序契約）
        ("ABC-123.mp4", "ABC-123", None),                              # 7. 無字幕無中文 → None
        # 8-9. Codex 指出的 orphan 分隔符殘留 — 剝除 marker 後不應留下尾端 -/_
        ("ABC-123 正妹の中文版-中字.mp4", "ABC-123", "正妹の中文版"),
        ("ABC-123 正妹の中文版_中文字幕.mp4", "ABC-123", "正妹の中文版"),
    ])
    def test_subtitle_marker_cases(self, filename, number, expected):
        result = extract_chinese_title(filename, number)
        assert result == expected, (
            f"extract_chinese_title({filename!r}, {number!r}) = {result!r}，"
            f"期望 {expected!r}"
        )


# ============ generate_nfo() 補充測試 ============

class TestGenerateNfoAdditional:
    def test_essential_tags_exist(self, tmp_path):
        nfo_path = tmp_path / "test.nfo"
        result = generate_nfo(
            number="TEST-001",
            title="測試標題",
            actors=["女優A", "女優B"],
            output_path=str(nfo_path)
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<title>[TEST-001]測試標題</title>" in content
        assert "<num>TEST-001</num>" in content
        assert "<name>女優A</name>" in content
        assert "<name>女優B</name>" in content


# ============ download_image() 測試 ============

class TestDownloadImage:
    @patch("core.organizer.requests.get")
    def test_download_success(self, mock_get, tmp_path):
        mock_resp = mock_get.return_value
        mock_resp.status_code = 200
        mock_resp.content = b"fake_image_data_that_is_long_enough_to_pass_the_length_check_which_is_1000_bytes_" * 15
        
        save_path = tmp_path / "cover.jpg"
        result = download_image("http://example.com/cover.jpg", str(save_path))
        
        assert result is True
        assert save_path.exists()
        assert save_path.read_bytes() == mock_resp.content
        mock_get.assert_called_once()

    @patch("core.organizer.requests.get")
    def test_download_fail_status(self, mock_get, tmp_path):
        mock_resp = mock_get.return_value
        mock_resp.status_code = 404
        
        save_path = tmp_path / "cover.jpg"
        result = download_image("http://example.com/cover.jpg", str(save_path))
        
        assert result is False
        assert not save_path.exists()

    @patch("core.organizer.requests.get")
    def test_download_exception(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("network error")

        save_path = tmp_path / "cover.jpg"
        result = download_image("http://example.com/cover.jpg", str(save_path))

        assert result is False
        assert not save_path.exists()


# ============ generate_nfo() 新欄位測試 (T5b) ============

class TestGenerateNfoNewFields:
    """generate_nfo() 新增 director/duration/series/uniqueid 欄位測試"""

    def test_nfo_director_filled(self, tmp_path):
        """director 有值 → <director>イナバール</director>"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            director="イナバール",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<director>イナバール</director>" in content

    def test_nfo_director_empty(self, tmp_path):
        """director 空字串 → <director></director>（保留空標籤）"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            director="",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<director></director>" in content

    def test_nfo_duration_filled(self, tmp_path):
        """duration=119 → <runtime>119</runtime>"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            duration=119,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<runtime>119</runtime>" in content

    def test_nfo_duration_none(self, tmp_path):
        """duration=None → <runtime></runtime>（保留空標籤）"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            duration=None,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<runtime></runtime>" in content

    def test_nfo_duration_zero(self, tmp_path):
        """duration=0 → <runtime>0</runtime>（0 是有效值，不能當 falsy 跳過）"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            duration=0,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<runtime>0</runtime>" in content

    def test_nfo_series_filled(self, tmp_path):
        """series 有值 → <set><name>ハプニングバーNTR</name></set>"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            series="ハプニングバーNTR",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<set><name>ハプニングバーNTR</name></set>" in content

    def test_nfo_series_empty(self, tmp_path):
        """series 空字串 → <set></set>（保留空標籤，Kodi/Emby 相容）"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            series="",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<set></set>" in content

    def test_nfo_uniqueid(self, tmp_path):
        """uniqueid 永遠存在 → <uniqueid type="home" default="true">SNOS-143</uniqueid>"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert '<uniqueid type="home" default="true">SNOS-143</uniqueid>' in content

    def test_nfo_director_special_chars(self, tmp_path):
        """director 含特殊字元 → html.escape 正確轉義"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            director="A&B<C>",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<director>A&amp;B&lt;C&gt;</director>" in content
        assert "<director>A&B<C></director>" not in content

    def test_nfo_label_filled(self, tmp_path):
        """label 有值 → <label>S1</label>"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            label="S1",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<label>S1</label>" in content

    def test_nfo_label_empty(self, tmp_path):
        """label 空字串 → <label></label>（保留空標籤）"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            label="",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<label></label>" in content

    def test_nfo_label_special_chars(self, tmp_path):
        """label 含特殊字元 → html.escape 正確轉義"""
        nfo_path = tmp_path / "SNOS-143.nfo"
        result = generate_nfo(
            number="SNOS-143",
            title="テスト",
            output_path=str(nfo_path),
            label="A&B<C>",
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<label>A&amp;B&lt;C&gt;</label>" in content
        assert "<label>A&B<C></label>" not in content


# ============ organize_file() extrafanart 測試 (T5b) ============

class TestOrganizeExtrafanart:
    """organize_file() extrafanart/ 目錄建立與下載測試（由 download_sample_images 控制）"""

    def _make_jellyfin_config_with_nfo(self, jellyfin_mode: bool, create_folder: bool = True,
                                       download_sample_images: bool = None) -> dict:
        # 向後相容：若未指定 download_sample_images，沿用 jellyfin_mode 的值（舊行為）
        if download_sample_images is None:
            download_sample_images = jellyfin_mode
        return {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "jellyfin_mode": jellyfin_mode,
            "download_sample_images": download_sample_images,
        }

    def _make_metadata_with_samples(self, sample_images=None) -> dict:
        return {
            "number": "SNOS-143",
            "title": "テスト",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
            "sample_images": sample_images if sample_images is not None else [
                "http://fake/sample1.jpg",
                "http://fake/sample2.jpg",
            ],
        }

    def test_extrafanart_created_in_jellyfin_mode(self, tmp_path):
        """jellyfin_mode=True + download_sample_images=True + create_folder=True + sample_images → extrafanart/ 建立 + fanart1.jpg 存在"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=True,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # create_folder=True → 影片在 per-video 子目錄內，extrafanart 也在該子目錄下
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert extrafanart_dir.exists(), "extrafanart/ 目錄應被建立"
        assert (extrafanart_dir / "fanart1.jpg").exists(), "fanart1.jpg 應被下載"
        assert (extrafanart_dir / "fanart2.jpg").exists(), "fanart2.jpg 應被下載"

    def test_extrafanart_empty_list_no_dir(self, tmp_path):
        """jellyfin_mode=True + sample_images=[] → 不建立 extrafanart/ 目錄"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True)
        metadata = self._make_metadata_with_samples(sample_images=[])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        extrafanart_dir = tmp_path / "extrafanart"
        assert not extrafanart_dir.exists(), "sample_images=[] 時不應建立 extrafanart/ 目錄"

    def test_extrafanart_not_in_normal_mode(self, tmp_path):
        """jellyfin_mode=False → 不下載 sample images，不建立 extrafanart/"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=False)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        extrafanart_dir = tmp_path / "extrafanart"
        assert not extrafanart_dir.exists(), "jellyfin_mode=False 時不應建立 extrafanart/ 目錄"

    def test_extrafanart_single_failure_continues(self, tmp_path):
        """其中一張下載失敗，其他張繼續下載，organize 仍 success=True"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=True,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples([
            "http://fake/s1.jpg",
            "http://fake/s2_fail.jpg",
            "http://fake/s3.jpg",
        ])

        call_count = [0]

        def mock_download_partial(url, save_path, referer=''):
            call_count[0] += 1
            if "s2_fail" in url:
                raise Exception("模擬下載失敗")
            _mock_download_image_write_jpeg(url, save_path, referer)
            return True

        with patch("core.organizer.download_image", side_effect=mock_download_partial):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"單張失敗不應導致整體失敗: {result.get('error')}"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert extrafanart_dir.exists(), "extrafanart/ 應被建立"
        assert (extrafanart_dir / "fanart1.jpg").exists(), "fanart1.jpg 應成功下載"
        assert not (extrafanart_dir / "fanart2.jpg").exists(), "fanart2.jpg 應失敗（不存在）"
        assert (extrafanart_dir / "fanart3.jpg").exists(), "fanart3.jpg 應繼續下載成功"

    def test_extrafanart_independent_of_cover(self, tmp_path):
        """cover 下載失敗，extrafanart 仍獨立下載（不依賴 cover_path）"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=True,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg"])

        def mock_download_cover_fail(url, save_path, referer=''):
            # cover 下載失敗，sample image 下載成功
            if "cover" in url:
                return False
            _mock_download_image_write_jpeg(url, save_path, referer)
            return True

        with patch("core.organizer.download_image", side_effect=mock_download_cover_fail):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("cover_path") is None, "cover 下載失敗，cover_path 應為 None"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert extrafanart_dir.exists(), "cover 失敗不影響 extrafanart/ 建立"
        assert (extrafanart_dir / "fanart1.jpg").exists(), "cover 失敗不影響 sample image 下載"

    def test_extrafanart_skipped_without_create_folder(self, tmp_path):
        """download_sample_images=True + create_folder=False → 不建立 extrafanart/（防止多片互蓋）"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=False,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        extrafanart_dir = tmp_path / "extrafanart"
        assert not extrafanart_dir.exists(), (
            "create_folder=False 時不應建立 extrafanart/（多片共用目錄會互相覆蓋 fanart1.jpg）"
        )

    def test_extrafanart_with_sample_dl_without_jellyfin(self, tmp_path):
        """jellyfin_mode=False, download_sample_images=True, create_folder=True → extrafanart 建立（解耦驗證）"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=False, create_folder=True,
                                                     download_sample_images=True)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert extrafanart_dir.exists(), "download_sample_images=True 時應建立 extrafanart/ 目錄"
        assert (extrafanart_dir / "fanart1.jpg").exists(), "fanart1.jpg 應被下載"
        assert (extrafanart_dir / "fanart2.jpg").exists(), "fanart2.jpg 應被下載"
        # jellyfin_mode=False → 不產生 poster/fanart
        assert result.get("poster_path") is None, "jellyfin_mode=False 時不應產生 poster"
        assert result.get("fanart_path") is None, "jellyfin_mode=False 時不應產生 fanart"

    def test_extrafanart_skipped_when_sample_dl_off(self, tmp_path):
        """jellyfin_mode=True, download_sample_images=False, create_folder=True → 無 extrafanart，但 poster/fanart 存在"""
        src = tmp_path / "SNOS-143.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_jellyfin_config_with_nfo(jellyfin_mode=True, create_folder=True,
                                                     download_sample_images=False)
        metadata = self._make_metadata_with_samples(["http://fake/s1.jpg", "http://fake/s2.jpg"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        video_dir = Path(result["new_folder"])
        extrafanart_dir = video_dir / "extrafanart"
        assert not extrafanart_dir.exists(), "download_sample_images=False 時不應建立 extrafanart/ 目錄"
        # jellyfin_mode=True → 應產生 poster/fanart
        assert result.get("poster_path") is not None, "jellyfin_mode=True 時應產生 poster"
        assert result.get("fanart_path") is not None, "jellyfin_mode=True 時應產生 fanart"


# ============ find_subtitle_files() 測試 (T37d-1) ============

from core.organizer import find_subtitle_files


class TestFindSubtitleFiles:
    """find_subtitle_files() 的單元測試"""

    def test_find_srt_same_name(self, tmp_path):
        """同名 .srt 找到"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "aaa.srt"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) in result

    def test_find_ass_same_name(self, tmp_path):
        """同名 .ass 找到"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "aaa.ass"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) in result

    def test_find_ssa_same_name(self, tmp_path):
        """同名 .ssa 找到"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "aaa.ssa"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) in result

    def test_find_lang_suffix_srt(self, tmp_path):
        """帶語言後綴 .cht.srt 找到"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "aaa.cht.srt"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) in result

    def test_find_multiple_subtitles(self, tmp_path):
        """多個字幕（.srt + .cht.srt）都回傳"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub1 = tmp_path / "aaa.srt"
        sub1.write_text("subtitle 1")
        sub2 = tmp_path / "aaa.cht.srt"
        sub2.write_text("subtitle 2")

        result = find_subtitle_files(str(video))

        assert str(sub1) in result
        assert str(sub2) in result
        assert len(result) == 2

    def test_exclude_different_name_srt(self, tmp_path):
        """不同名字幕 bbb.srt 不包含"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "bbb.srt"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) not in result
        assert result == []

    def test_exclude_underscore_suffix(self, tmp_path):
        """底線分隔 aaa_chs.srt 不包含"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")
        sub = tmp_path / "aaa_chs.srt"
        sub.write_text("subtitle content")

        result = find_subtitle_files(str(video))

        assert str(sub) not in result
        assert result == []

    def test_no_subtitles_returns_empty(self, tmp_path):
        """無字幕回傳空列表"""
        video = tmp_path / "aaa.mp4"
        video.write_bytes(b"fake")

        result = find_subtitle_files(str(video))

        assert result == []

    def test_nonexistent_video_returns_empty(self, tmp_path):
        """影片路徑不存在回傳空列表"""
        nonexistent = str(tmp_path / "nonexistent.mp4")

        result = find_subtitle_files(nonexistent)

        assert result == []


# ============ organize_file() 字幕搬移測試 (T37d-1) ============

class TestOrganizeSubtitle:
    """organize_file() 字幕偵測 + 搬移整合測試"""

    def _make_config(self, tmp_path, create_folder=False):
        return {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }

    def _make_metadata(self):
        return {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

    def test_subtitle_moves_with_video(self, tmp_path):
        """organize 成功搬移後，字幕跟隨（字幕在目標目錄，名稱正確）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # 影片搬移了（同目錄重命名）
        target_dir = Path(result["new_filename"]).parent
        # 字幕應出現在目標目錄，並以新檔名命名
        new_video_stem = Path(result["new_filename"]).stem
        expected_sub = target_dir / f"{new_video_stem}.srt"
        assert expected_sub.exists(), f"字幕應搬移到 {expected_sub}"
        # 原字幕不應在原位（已搬移）
        assert not sub.exists(), "原始字幕應已搬離原位置"

    def test_subtitle_with_lang_suffix_moves_correctly(self, tmp_path):
        """帶語言後綴的字幕搬移後名稱正確（new-name.cht.srt）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.cht.srt"
        sub.write_text("subtitle cht")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        target_dir = Path(result["new_filename"]).parent
        new_video_stem = Path(result["new_filename"]).stem
        expected_sub = target_dir / f"{new_video_stem}.cht.srt"
        assert expected_sub.exists(), f"帶語言後綴的字幕應搬移到 {expected_sub}"

    def test_subtitle_not_moved_on_duplicate(self, tmp_path):
        """organize 影片 duplicate → 字幕留原處不搬"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"source content")
        # 建立已存在的目標檔（造成 duplicate）
        existing_target = tmp_path / "[SONE-205] Test Title.mp4"
        existing_target.write_bytes(b"existing content")
        # 字幕
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = self._make_config(tmp_path)
        metadata = self._make_metadata()

        result = organize_file(str(src), metadata, config)

        assert result.get("duplicate") is True
        assert result["success"] is False
        # 字幕應仍在原處
        assert sub.exists(), "duplicate 時字幕不應被搬移"

    def test_subtitle_move_failure_warning_continues(self, tmp_path):
        """字幕搬移失敗 → warning，後續繼續（封面/NFO 正常產生）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }

        import shutil as _shutil_real
        _real_move = _shutil_real.move

        def selective_move(src_path, dst_path):
            if str(src_path).endswith(".srt"):
                raise OSError("字幕搬移模擬失敗")
            return _real_move(src_path, dst_path)

        with patch("core.organizer.shutil.move", side_effect=selective_move), \
             patch("core.organizer.download_image", return_value=False):
            result = organize_file(str(src), metadata, config)

        # 影片整理應仍成功（字幕失敗不影響）
        assert result["success"] is True, f"字幕失敗不應影響 organize 成功: {result.get('error')}"

    def test_check_subtitle_true_no_file_has_subtitle_true(self, tmp_path):
        """check_subtitle() 回傳 True 但無字幕檔 → has_subtitle = True，NFO 有中文字幕 tag"""
        # 檔名含 "-C" → check_subtitle 回傳 True
        src = tmp_path / "SONE-205-C.mp4"
        src.write_bytes(b"fake mp4")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # NFO 應包含中文字幕 tag
        if result.get("nfo_path"):
            nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
            assert "中文字幕" in nfo_content, "check_subtitle=True 時 NFO 應包含中文字幕 tag"

    def test_find_subtitle_true_has_subtitle_true(self, tmp_path):
        """find_subtitle_files() 找到字幕 → has_subtitle = True（即使 check_subtitle() 為 False）"""
        # 檔名無字幕標記（check_subtitle 為 False），但有 .srt 檔
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # NFO 應包含中文字幕 tag（因為有字幕檔）
        if result.get("nfo_path"):
            nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
            assert "中文字幕" in nfo_content, "有字幕檔時 NFO 應包含中文字幕 tag"

    def test_explicit_false_with_sidecar_subtitle(self, tmp_path):
        """has_subtitle=False 但有 sidecar 字幕 → has_subtitle 應為 True，NFO 有 tag"""
        # 檔名無字幕標記（check_subtitle 為 False），metadata 明確傳 has_subtitle=False
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")
        # sidecar 字幕與影片同目錄
        sub = tmp_path / "SONE-205.srt"
        sub.write_text("subtitle content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "SONE-205",
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
            "has_subtitle": False,  # 上游明確設為 False
        }

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        # sidecar 字幕存在 → 應覆寫上游 False → NFO 必須包含中文字幕 tag
        assert result.get("nfo_path"), "NFO 應被建立"
        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "中文字幕" in nfo_content, \
            "has_subtitle=False 但有 sidecar 字幕時，NFO 應包含中文字幕 tag"
