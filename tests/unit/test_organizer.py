"""
T1e Tests — Fix-1 版本標記測試
測試 core/organizer.py 的 _detect_suffixes(), format_string(), organize_file()
"""
import io
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from core.organizer import _detect_suffixes, format_string, organize_file, crop_to_poster, generate_nfo, extract_chinese_title, download_image, truncate_to_chars, truncate_title, _detect_vr_cluster, _is_multipart_kw, _poster_window_ratio
from core.focal import requires_face_detection
from core.scrapers.utils import normalize_number_impl
from tests.conftest import MOCK_FOCAL_XY


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
    # T4 遷移：image block 改由 external_manager 控制；jellyfin_mode=True → 'jellyfin'
    return {
        "create_folder": False,
        "filename_format": "[{num}] {title}",
        "download_cover": True,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": [],
        "external_manager": "jellyfin" if jellyfin_mode else "off",
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


# ============ crop_to_poster 焦點化測試 (TASK-101a-T1) ============

_FOCAL_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "actress_photos"


def _pad_to_square_with_white_bars(src_path, dst_path):
    """把矩形圖上下 pad 白邊成正方形（測試內即時合成，不進 repo，Opus 裁決見 TASK card）。"""
    with Image.open(src_path) as img:
        w, h = img.size
        assert w > h, "本 helper 只處理橫向圖上下 pad 成方形"
        square = Image.new("RGB", (w, w), (255, 255, 255))
        top = (w - h) // 2
        square.paste(img.convert("RGB"), (0, top))
        square.save(str(dst_path), "JPEG", quality=95)


class TestPosterWindowRatioInvariant:
    """DoD①：CD-3 不變式——_poster_window_ratio() 的窗比例恆小於畫面比例 a=w/h
    （分支2/3 定義域內），production 與本測試共用同一個 helper（Opus 裁決）。

    mutation 驗：把 helper 內分支2 公式改成 int(h*1.5)/h（必然 >a）→ 本測試必須紅；
    還原後綠。
    """

    def test_branch2_window_ratio_below_frame_ratio(self):
        """分支2定義域 a=w/h ∈ (0.714, 1.0]，抽樣驗證 a > r_window 恆成立。"""
        h = 1000
        samples = [0.715, 0.75, 0.8, 0.9, 0.95, 1.0]
        for a in samples:
            w = int(round(h * a))
            ratio = h / w
            assert 1.0 <= ratio < 1.4, f"抽樣點應落在分支2定義域，實際 ratio={ratio}"
            r_window = _poster_window_ratio(w, h)
            assert r_window is not None
            frame_ratio = w / h
            assert frame_ratio > r_window, (
                f"a={frame_ratio:.4f} 應大於 r_window={r_window:.4f}（w={w}, h={h}）"
            )

    def test_branch3_window_ratio_below_frame_ratio(self):
        """分支3定義域 a=w/h > 1.0，取合理上界 3.0 分段抽樣驗證 a > r_window 恆成立。"""
        h = 1000
        samples = [1.01, 1.2, 1.487, 1.8, 2.0, 2.5, 3.0]
        for a in samples:
            w = int(round(h * a))
            ratio = h / w
            assert ratio < 1.0, f"抽樣點應落在分支3定義域，實際 ratio={ratio}"
            r_window = _poster_window_ratio(w, h)
            assert r_window is not None
            frame_ratio = w / h
            assert frame_ratio > r_window, (
                f"a={frame_ratio:.4f} 應大於 r_window={r_window:.4f}（w={w}, h={h}）"
            )

    def test_branch1_returns_none(self):
        """分支1（h/w>=1.4，已直向）helper 回 None，不參與偵測/平移。"""
        assert _poster_window_ratio(380, 538) is None  # ratio=1.416
        assert _poster_window_ratio(700, 1050) is None  # ratio=1.5


class TestCropToPosterFocalWiring:
    """DoD②：無碼真圖 poster 對準臉——gate 兩支路徑（fixture A/B）各一，
    分支2/分支3 各一（4 組合）。TASK-102c-T1：改 mock `core.organizer.detect_focal`
    成固定偏心值（MOCK_FOCAL_XY），只驗 consumer（crop_to_poster）收到焦點座標後
    正確平移窗口的 wiring；真的「pigo 對真圖偵出正確焦點」能力已搬到
    test_focal_detector.py::TestDetectFocal（Layer 1，真跑）。

    每組合兩個斷言：
    - 正向：輸出 bytes 等於「測試內獨立以『只平移既有窗』契約（整數 crop_w + focal 平移 x0）裁切存檔」的期望值。
    - 反向：輸出 bytes 與「同圖不傳 number/maker 的原碼輸出」不同（證明焦點真的平移了窗）。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}  # 番號驅動，maker 非白名單
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}  # maker-only 驅動，白名單原樣照抄

    def _assert_focal_applied(self, src_path, tmp_path, tag, **kwargs):
        dst = tmp_path / f"poster_{tag}.jpg"
        baseline_dst = tmp_path / f"poster_{tag}_baseline.jpg"

        # TASK-102c-T1：mock core.organizer.detect_focal（consumer binding）成固定偏心值，
        # 避免真跑 pigo（~4-5s/呼叫）。baseline 呼叫不傳 number/maker，gate=False，不會
        # 呼叫 detect_focal，不受此 patch 影響。
        with patch("core.organizer.detect_focal", return_value=MOCK_FOCAL_XY):
            result = crop_to_poster(str(src_path), str(dst), **kwargs)
        assert result is True
        assert dst.exists()

        with Image.open(src_path) as img:
            w, h = img.size
        r_window = _poster_window_ratio(w, h)
        assert r_window is not None

        focal = MOCK_FOCAL_XY

        with Image.open(src_path) as img:
            # 101a P2-1（Codex PR#110）：oracle 改為「只平移既有窗」的真實契約——用與退化路
            # 完全相同的整數 crop_w，只把 x0 平移到臉；不再經 crop_image_position 的 float
            # ratio→px round-trip（該 helper 會 ±1px 改窗寬、已被 crop_to_poster 棄用）。
            crop_w = int(h / 1.5) if (h / w) >= 1.0 else (w - int(w / 1.9))
            x0 = max(min(int(w * focal[0]) - crop_w // 2, w - crop_w), 0)
            expected_cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
        expected_path = tmp_path / f"poster_{tag}_expected.jpg"
        expected_cropped.save(str(expected_path), "JPEG", quality=95, subsampling=0)
        assert dst.read_bytes() == expected_path.read_bytes(), "輸出應與獨立計算的期望裁切位元相同"

        baseline_result = crop_to_poster(str(src_path), str(baseline_dst))
        assert baseline_result is True
        assert dst.read_bytes() != baseline_dst.read_bytes(), "焦點裁切應與原碼（不傳 number/maker）輸出不同"

    def test_branch3_fixture_a(self, tmp_path):
        """分支3（900×598 橫向）+ fixture A（番號驅動）。"""
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        self._assert_focal_applied(src, tmp_path, "b3a", **self._FIXTURE_A)

    def test_branch3_fixture_b(self, tmp_path):
        """分支3（900×598 橫向）+ fixture B（maker-only 驅動）。"""
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        self._assert_focal_applied(src, tmp_path, "b3b", **self._FIXTURE_B)

    def test_branch2_fixture_a(self, tmp_path):
        """分支2（900×900 上下 pad 白邊，即時合成）+ fixture A（番號驅動）。"""
        src = tmp_path / "square_face.jpg"
        _pad_to_square_with_white_bars(_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg", src)
        self._assert_focal_applied(src, tmp_path, "b2a", **self._FIXTURE_A)

    def test_branch2_fixture_b(self, tmp_path):
        """分支2（900×900 上下 pad 白邊，即時合成）+ fixture B（maker-only 驅動）。"""
        src = tmp_path / "square_face.jpg"
        _pad_to_square_with_white_bars(_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg", src)
        self._assert_focal_applied(src, tmp_path, "b2b", **self._FIXTURE_B)


class TestCropToPosterByteForByteRegression:
    """DoD④：真正的零回歸哨兵（非 TestCropToPoster 三個既有測試，見 plan §C-1 修訂框一）。

    同一測試內兩次呼叫自我比對（不需 git 取舊產物）：有碼 / 無臉 / number='' 三路，
    分支2（方形）與分支3（橫向）各至少覆蓋一次。
    """

    def test_censored_gate_false_branch3_rectangular(self, tmp_path):
        """fallback-on-None（分支3橫向，純色合成圖）：新舊簽名輸出位元相同。

        ⚠️ 誠實描述：來源是純色圖，pigo 本來就偵測不到臉，此測試**證不出**
        「gate 正確回 False」——「gate=False」與「gate 被繞過但偵測無結果」兩條路殊途
        同歸、輸出同 bytes（若把 gate 換成 `if True:` 此測試仍綠）。此測試只是
        no-face fallback 路徑的額外覆蓋，忠實驗證 gate wiring 見下方
        `test_censored_real_face_gate_false_branch3`（真臉圖，gate 被繞過會真的平移）。
        """
        src = _make_test_image(tmp_path, 800, 538, "cover.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a)) is True
        assert crop_to_poster(str(src), str(dst_b), number="SSIS-001", maker="S1 NO.1 STYLE") is True
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_censored_gate_false_branch2_square(self, tmp_path):
        """fallback-on-None（分支2方形，純色合成圖）：新舊簽名輸出位元相同。

        ⚠️ 誠實描述：同上——純色圖證不出「gate 正確回 False」，只是 no-face fallback
        路徑的額外覆蓋。忠實驗證見下方 `test_censored_real_face_gate_false_branch2`。
        """
        src = _make_test_image(tmp_path, 500, 500, "cover_sq.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a)) is True
        assert crop_to_poster(str(src), str(dst_b), number="SSIS-001", maker="S1 NO.1 STYLE") is True
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_censored_real_face_gate_false_branch3(self, tmp_path):
        """有碼（gate False，真臉分支3，忠實測試）：wide_offcenter_face.jpg 真臉圖 +
        SSIS-001/S1 NO.1 STYLE（實測 gate → False）輸出須等於**獨立計算**的既有裁切算式
        期望值。

        ⚠️ 不能用「呼叫兩次 crop_to_poster 自我比對」（一次不傳 number/maker 當 baseline）：
        對「gate 被整個繞過」（如 mutation `if True:`）這種 mutation，baseline 那次呼叫
        同樣會被同一個 mutation 影響、一樣被平移，兩次呼叫依然相等 → 結構性瞎眼、測試
        不會紅（本 task P2 review 踩過一次）。改成與**不經過 crop_to_poster** 的獨立算式
        比對，才能在 gate 被繞過時偵測到分歧。
        """
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        dst = tmp_path / "poster.jpg"
        assert crop_to_poster(str(src), str(dst), number="SSIS-001", maker="S1 NO.1 STYLE") is True

        with Image.open(src) as img:
            w, h = img.size
            ratio = h / w
            assert ratio < 1.0, "fixture 應落在分支3（橫向）"
            x0 = int(w / 1.9)
            expected_cropped = img.convert("RGB").crop((x0, 0, w, h))
        expected_path = tmp_path / "expected.jpg"
        expected_cropped.save(str(expected_path), "JPEG", quality=95, subsampling=0)
        assert dst.read_bytes() == expected_path.read_bytes(), (
            "gate=False 時輸出應等於既有分支3裁切算式（右裁 x0=int(w/1.9)），"
            "若不同代表 gate 沒有正確擋下偵測"
        )

    def test_censored_real_face_gate_false_branch2(self, tmp_path):
        """有碼（gate False，真臉分支2，忠實測試）：同圖 pad 成方形 + 同 gate False 組合，
        輸出須等於**獨立計算**的既有裁切算式期望值（理由同 branch3 版 docstring）。
        """
        src = tmp_path / "square_face_gate_false.jpg"
        _pad_to_square_with_white_bars(_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg", src)
        dst = tmp_path / "poster.jpg"
        assert crop_to_poster(str(src), str(dst), number="SSIS-001", maker="S1 NO.1 STYLE") is True

        with Image.open(src) as img:
            w, h = img.size
            ratio = h / w
            assert 1.0 <= ratio < 1.4, "fixture 應落在分支2（方形）"
            crop_w = int(h / 1.5)
            x0 = (w - crop_w) // 2
            expected_cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
        expected_path = tmp_path / "expected.jpg"
        expected_cropped.save(str(expected_path), "JPEG", quality=95, subsampling=0)
        assert dst.read_bytes() == expected_path.read_bytes(), (
            "gate=False 時輸出應等於既有分支2裁切算式（置中 crop_w=int(h/1.5)），"
            "若不同代表 gate 沒有正確擋下偵測"
        )

    def test_no_face_real_photo_branch3(self, tmp_path):
        """無臉（分支3）：gate True 但 detect_focal 回 None → 落回原碼（fallback wiring）。

        TASK-102c-T1 方案 A：mock `core.organizer.detect_focal` 成 `return_value=None`，
        只驗 organizer 收到 None 後的 fallback wiring。「pigo 對這張圖真的判定無臉」
        的能力已搬到 test_focal_detector.py::TestDetectFocal::
        test_detect_focal_no_face_real_photo_returns_none（Layer 1 回歸，真跑）。
        """
        src = _FOCAL_FIXTURES_DIR / "no_face_detected.jpg"
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a)) is True
        with patch("core.organizer.detect_focal", return_value=None) as mock_detect:
            assert crop_to_poster(str(src), str(dst_b), number="FC2-1234567") is True
        # 反例回 None 與「gate 被跳過、detect_focal 根本沒被呼叫」輸出同 bytes，
        # 光比對 bytes 證不出 wiring；必須額外斷言 mock 真的被呼叫過一次
        # （Codex PR#110 二審 P2-1）。
        mock_detect.assert_called_once()
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_no_face_synthetic_branch2(self, tmp_path):
        """無臉（補充，合成純色圖，分支2）：gate True 但無臉 → 落回原碼。"""
        src = _make_test_image(tmp_path, 500, 500, "cover_sq.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a)) is True
        assert crop_to_poster(str(src), str(dst_b), number="FC2-1234567", maker="") is True
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_no_face_synthetic_branch3(self, tmp_path):
        """無臉（補充，合成純色圖，分支3）：gate True 但無臉 → 落回原碼。"""
        src = _make_test_image(tmp_path, 800, 538, "cover.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a)) is True
        assert crop_to_poster(str(src), str(dst_b), number="FC2-1234567", maker="") is True
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_empty_number_explicit_equals_omitted_branch2(self, tmp_path):
        """number='' 顯式空值 vs 完全不傳（用預設值）：分支2 行為一致。"""
        src = _make_test_image(tmp_path, 500, 500, "cover_sq.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a), number="", maker="") is True
        assert crop_to_poster(str(src), str(dst_b)) is True
        assert dst_a.read_bytes() == dst_b.read_bytes()

    def test_empty_number_explicit_equals_omitted_branch3(self, tmp_path):
        """number='' 顯式空值 vs 完全不傳（用預設值）：分支3 行為一致。"""
        src = _make_test_image(tmp_path, 800, 538, "cover.jpg")
        dst_a = tmp_path / "a.jpg"
        dst_b = tmp_path / "b.jpg"
        assert crop_to_poster(str(src), str(dst_a), number="", maker="") is True
        assert crop_to_poster(str(src), str(dst_b)) is True
        assert dst_a.read_bytes() == dst_b.read_bytes()


class TestCropToPosterFocalCropWidth:
    """CD-5「只平移既有窗，不改窗寬」——焦點路徑的 crop 寬度必須與退化路的整數窗寬
    完全相同，不因 crop_image_position 的 float ratio→px round-trip 少 1px（Codex PR#110 P2-1）。

    521×521 是踩雷案例：退化路 int(521/1.5)=347，但舊碼經 crop_image_position 得
    int(521*(347/521))=346（少 1px，海報寬度/比例與 fallback 不一致）。
    """

    def test_focal_crop_width_matches_legacy_branch2_square(self, tmp_path):
        """分支2 方形 521×521：焦點窗寬須 == 退化窗寬 347（不是 crop_image_position 的 346）。"""
        src = _make_test_image(tmp_path, 521, 521, "cover_sq.jpg")
        dst = tmp_path / "poster.jpg"

        # 焦點固定置中（0.5），gate 用真正無碼番號（FC2-1234567 實測 gate → True）。
        with patch('core.organizer.detect_focal', return_value=(0.5, 0.5)):
            assert crop_to_poster(str(src), str(dst), number="FC2-1234567") is True

        with Image.open(dst) as out:
            assert out.size == (347, 521), (
                f"焦點裁窗寬應等於退化路整數窗寬 347（int(521/1.5)），實得 {out.size[0]}；"
                "若為 346 代表走了 crop_image_position 的 float round-trip、改了窗寬"
            )

class TestCropToPosterBranch1NoDetection:
    """DoD⑤：分支1（h/w>=1.4，narrow_face_top.jpg 真圖且真有臉）仍 copy2 不裁，
    且完全不觸發人臉偵測（結構保證：分支1提早 return，不進入 gate/偵測邏輯）。

    patch target 必須是 core.organizer.detect_focal（consumer binding，
    見 gotchas-backend.md §測試 Mock Patch Target；patch core.focal.detect_focal 改不到）。
    """

    def test_branch1_copy2_no_detection_even_with_gate_true(self, tmp_path):
        src = _FOCAL_FIXTURES_DIR / "narrow_face_top.jpg"
        dst = tmp_path / "poster.jpg"

        with patch('core.organizer.detect_focal') as mock_detect_focal:
            result = crop_to_poster(str(src), str(dst), number="FC2-1234567")

        assert result is True
        assert dst.exists()
        assert dst.read_bytes() == src.read_bytes(), "分支1應 copy2 直接複製，輸出應與來源位元相同"
        assert mock_detect_focal.call_count == 0, "分支1不應觸發人臉偵測"


_CD7_VERDICT_NEUTRAL_CASES = [
    "fc2-1234567",
    "FC2PPV-1234567",
    "fc2ppv1234567",
    "n0762",
    "heyzo-1234",
    "kin8-1234",
    "gcolle-123456",
    "siro-1234",
    "SSIS-001",
    "4SSIS-296",
    "7IPZ-001",
    "3ABW-001",
    "1sdms00808",
    "ABC-123-UC",
    "  sone-103  ",
    "h0930-1234",
    "022509-995",
]


class TestNormalizeNumberGateVerdictNeutral:
    """DoD⑥：CD-7 verdict-neutral——補 normalize_number_impl 不改變 gate 判定（17 案）。

    🔴 左邊必須是 raw（未 normalize），不可寫成
    gate(normalize(raw)) == gate(normalize(normalize(raw)))——那只測 normalize 冪等性
    （normalize 本來就冪等，恆真空殼），證不出「補 normalize 這個動作」本身不改 verdict。
    """

    @pytest.mark.parametrize("raw", _CD7_VERDICT_NEUTRAL_CASES)
    def test_verdict_neutral(self, raw):
        assert requires_face_detection(raw, '') == requires_face_detection(normalize_number_impl(raw), '')


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


def _make_ext_config(external_manager: str, create_folder: bool = False,
                     download_sample_images: bool = False) -> dict:
    """T4 測試用：依 external_manager 模式建立 config dict"""
    return {
        "create_folder": create_folder,
        "filename_format": "[{num}] {title}",
        "download_cover": True,
        "cover_filename": "poster.jpg",
        "create_nfo": True,
        "max_title_length": 50,
        "max_filename_length": 60,
        "suffix_keywords": [],
        "external_manager": external_manager,
        "download_sample_images": download_sample_images,
    }


def _make_ext_metadata(number: str = "SONE-205", cover: str = "http://fake/cover.jpg") -> dict:
    """T4 測試用：標準 metadata"""
    return {
        "number": number,
        "title": "Test Title",
        "actors": [],
        "tags": [],
        "maker": "S1",
        "date": "2024-01-15",
        "cover": cover,
        "url": "",
    }


class TestExternalManagerImageNaming:
    """T4：organize_file() external_manager 三態圖片命名分岐"""

    # ── A. jellyfin 模式 ──────────────────────────────────────────────

    def test_jellyfin_produces_stem_poster_fanart(self, tmp_path):
        """jellyfin → {stem}-poster.jpg + {stem}-fanart.jpg 存在，不存在裸名"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("jellyfin")
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("cover_path") is not None, "cover_path 應存在"
        assert result.get("fanart_path") is not None, "jellyfin 應產生 fanart_path"
        assert result.get("poster_path") is not None, "jellyfin 應產生 poster_path"

        # 確認帶 stem 的命名
        fanart = Path(result["fanart_path"])
        poster = Path(result["poster_path"])
        assert fanart.name.endswith("-fanart.jpg"), f"fanart 應帶 stem 前綴，實際: {fanart.name}"
        assert poster.name.endswith("-poster.jpg"), f"poster 應帶 stem 前綴，實際: {poster.name}"
        assert fanart.exists(), "fanart 檔案應存在"
        assert poster.exists(), "poster 檔案應存在"

        # 確認裸名不存在
        assert not (tmp_path / "fanart.jpg").exists(), "裸名 fanart.jpg 不應出現（jellyfin）"
        assert not (tmp_path / "poster.jpg").exists(), "裸名 poster.jpg 不應出現（jellyfin）"

    def test_emby_produces_stem_poster_fanart(self, tmp_path):
        """emby → {stem}-poster.jpg + {stem}-fanart.jpg 存在（等價 jellyfin/kodi）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("emby")
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("fanart_path") is not None, "emby 應產生 fanart_path"
        assert result.get("poster_path") is not None, "emby 應產生 poster_path"

        fanart = Path(result["fanart_path"])
        poster = Path(result["poster_path"])
        assert fanart.name.endswith("-fanart.jpg"), f"fanart 應帶 stem 前綴，實際: {fanart.name}"
        assert poster.name.endswith("-poster.jpg"), f"poster 應帶 stem 前綴，實際: {poster.name}"
        assert fanart.exists(), "fanart 檔案應存在"
        assert poster.exists(), "poster 檔案應存在"

    # ── B. kodi 模式 ──────────────────────────────────────────────────────

    def test_kodi_produces_stem_poster_fanart(self, tmp_path):
        """kodi → stem 命名（{stem}-poster.jpg / {stem}-fanart.jpg），無論 create_folder。"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("kodi")  # create_folder=False
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("fanart_path") is not None, "kodi 應產生 fanart_path"
        assert result.get("poster_path") is not None, "kodi 應產生 poster_path"

        fanart = Path(result["fanart_path"])
        poster = Path(result["poster_path"])
        assert fanart.name.endswith("-fanart.jpg"), f"kodi fanart 應帶 stem，實際: {fanart.name}"
        assert poster.name.endswith("-poster.jpg"), f"kodi poster 應帶 stem，實際: {poster.name}"
        assert fanart.exists(), "fanart 檔案應存在"
        assert poster.exists(), "poster 檔案應存在"

        # 裸名不存在
        target_dir = Path(result["cover_path"]).parent
        assert not (target_dir / "fanart.jpg").exists(), "裸名 fanart.jpg 不應出現（kodi）"
        assert not (target_dir / "poster.jpg").exists(), "裸名 poster.jpg 不應出現（kodi）"

    # ── C. off 模式 ──────────────────────────────────────────────────────

    def test_off_produces_only_cover(self, tmp_path):
        """off（或 key 不存在）→ 只有主封面，無 poster/fanart"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("off")
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("cover_path") is not None, "off 模式應產生主封面"
        assert result.get("fanart_path") is None, "off 模式不應產生 fanart_path"
        assert result.get("poster_path") is None, "off 模式不應產生 poster_path"

        # target_dir 下只有 {stem}.jpg，無任何 poster/fanart
        target_dir = Path(result["cover_path"]).parent
        assert not (target_dir / "fanart.jpg").exists(), "off 模式不應有裸名 fanart.jpg"
        assert not (target_dir / "poster.jpg").exists(), "off 模式不應有裸名 poster.jpg"
        stem = Path(result["cover_path"]).stem
        assert not (target_dir / f"{stem}-fanart.jpg").exists(), "off 模式不應有 stem-fanart.jpg"
        assert not (target_dir / f"{stem}-poster.jpg").exists(), "off 模式不應有 stem-poster.jpg"

    def test_off_key_missing_defaults_to_off(self, tmp_path):
        """external_manager key 不存在時預設 off，不產 poster/fanart"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        # 不含 external_manager key
        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        }
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("fanart_path") is None, "key 不存在應預設 off，不產 fanart"
        assert result.get("poster_path") is None, "key 不存在應預設 off，不產 poster"

    # ── G. cover 下載失敗不 crash ────────────────────────────────────────

    def test_jellyfin_cover_fail_no_crash(self, tmp_path):
        """jellyfin + cover 下載失敗 → 不進入圖片 block，success 仍 True"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("jellyfin")
        metadata = _make_ext_metadata(cover="")  # 無 cover URL

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, "cover 下載失敗不應 crash"
        assert result.get("cover_path") is None, "無 cover URL → cover_path 應為 None"
        assert result.get("fanart_path") is None, "無 cover → 不應產 fanart"
        assert result.get("poster_path") is None, "無 cover → 不應產 poster"


class TestExternalManagerNfoF3:
    """T4：NFO F3 欄位跟隨 external_manager 模式"""

    def _make_nfo_metadata(self, number: str = "SONE-205") -> dict:
        return {
            "number": number,
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "https://example.com/video",
        }

    def test_jellyfin_nfo_has_f3_fields(self, tmp_path):
        """jellyfin → 產出的 NFO 含 F3 欄位（<country>Japan + <lockdata>）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("jellyfin")
        metadata = self._make_nfo_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("nfo_path") is not None, "NFO 應被產出"

        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "<country>Japan</country>" in nfo_content, \
            "jellyfin NFO 應含 <country>Japan</country>"
        assert "<lockdata>true</lockdata>" in nfo_content, \
            "jellyfin NFO 應含 <lockdata>true</lockdata>"

    def test_kodi_nfo_has_f3_fields(self, tmp_path):
        """kodi → 產出的 NFO 含 F3 欄位（<country>Japan + <lockdata>）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("kodi")
        metadata = self._make_nfo_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("nfo_path") is not None, "NFO 應被產出"

        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "<country>Japan</country>" in nfo_content, \
            "kodi NFO 應含 <country>Japan</country>"
        assert "<lockdata>true</lockdata>" in nfo_content, \
            "kodi NFO 應含 <lockdata>true</lockdata>"

    def test_off_nfo_no_f3_fields(self, tmp_path):
        """off → 產出的 NFO 不含 F3 欄位（<country> / <lockdata> 不應出現）"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("off")
        metadata = self._make_nfo_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("nfo_path") is not None, "NFO 應被產出"

        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert "<country>Japan</country>" not in nfo_content, \
            "off NFO 不應含 <country>Japan</country>"
        assert "<lockdata>true</lockdata>" not in nfo_content, \
            "off NFO 不應含 <lockdata>true</lockdata>"


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

    def test_7letter_prefix_generic_cleanup_no_residual(self):
        """TASK-caps 回歸鎖：core/organizer.py:112 通用番號清理 cap {2,7}。

        番號 PARATHD-02976（7 字母前綴）出現在檔名，但 number 參數（ABC-999）
        故意不匹配它 —— 所以必須靠通用 `[A-Za-z]{2,7}-?\\d{3,5}` cleanup 移除。
        cap={2,7} → 完整剝除，片名為 '純中文標題'。
        cap={2,6}（回歸）→ 只吃到 'ARATHD-02976'，殘留首字 'P' → 'P純中文標題'。
        此案在 {2,6} 下會 FAIL，鎖住 cap 對齊不被誤縮。
        """
        result = extract_chinese_title("PARATHD-02976 純中文標題.mp4", "ABC-999")
        assert result == "純中文標題"


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
        # T4 遷移：image block 改由 external_manager 控制；jellyfin_mode=True → 'jellyfin'
        return {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "external_manager": "jellyfin" if jellyfin_mode else "off",
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


# ============ Issue #31 — Windows trailing-dot truncation ============

class TestTruncateWindowsTrailingDot:
    """Issue #31: 截斷後尾端 `...` 在 Windows 會被 NTFS 剝除，導致 shutil.move WinError 3"""

    def test_truncate_to_chars_strips_trailing_dots_on_windows(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = truncate_to_chars("僕が不在の5日間、彼女が他の男と朝から晩までヤリまくっていた胸糞映像 吉高寧々", 40)
        assert not result.endswith('.'), f"Windows: 截斷結果不應以 . 結尾, got {result!r}"
        assert not result.endswith(' '), f"Windows: 截斷結果不應以空格結尾, got {result!r}"

    def test_truncate_to_chars_keeps_ellipsis_on_posix(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'linux')
        result = truncate_to_chars("a" * 100, 40)
        assert result.endswith('...'), f"Non-Windows: 應保留 ... 後綴, got {result!r}"
        assert len(result) == 40

    def test_truncate_to_chars_no_change_when_under_limit(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = truncate_to_chars("short", 60)
        assert result == "short"

    def test_truncate_title_strips_trailing_dots_on_windows(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        result = truncate_title("a" * 100, 30)
        assert not result.endswith('.'), f"Windows truncate_title 結果不應以 . 結尾, got {result!r}"

    def test_truncate_title_keeps_ellipsis_on_posix(self, monkeypatch):
        monkeypatch.setattr('core.organizer.sys.platform', 'darwin')
        result = truncate_title("a" * 100, 30)
        assert result.endswith('...')

    def test_truncate_strips_trailing_space_before_dots_on_windows(self, monkeypatch):
        # 文字剛好截在空格 + ... → "foo ..."  Windows 會剝成 "foo"
        monkeypatch.setattr('core.organizer.sys.platform', 'win32')
        # 構造一個截斷後變 "xxxxx ..." 的字串
        text = "x" * 36 + " " + "yyy"  # 長度 40, 截到 max=40 不變; 設 max=39 → "xxxx..." 結尾無空格
        # 直接驗證：任何長度都不應以 . 或空格結尾
        for limit in (10, 20, 39, 50):
            r = truncate_to_chars(text, limit)
            if len(text) > limit and limit > 3:
                assert not r.endswith('.') and not r.endswith(' '), \
                    f"limit={limit}: got {r!r}"


# ============ _detect_vr_cluster() 測試 ============

class TestDetectVrCluster:
    """_detect_vr_cluster() 的單元測試（TDD-lite RED→GREEN）

    命中列：回傳 raw 子字串（原樣大小寫）
    None 列：回傳 None（守零變化）
    """

    # ---- 命中列（unique 單獨成立）----

    def test_hit_unique_plus_ambiguous_full(self):
        """SIVR-123_8K_60fps_180_180x180_3dh_LR → 180_180x180_3dh_LR（unique 3dh + ambiguous 180/LR 共存）"""
        result = _detect_vr_cluster("SIVR-123_8K_60fps_180_180x180_3dh_LR")
        assert result == "180_180x180_3dh_LR"

    def test_hit_mkx200_lr(self):
        """KAVR-001_mkx200_LR → mkx200_LR（unique mkx200 + ambiguous LR）"""
        result = _detect_vr_cluster("KAVR-001_mkx200_LR")
        assert result == "mkx200_LR"

    def test_hit_180_sbs(self):
        """WAVR-456_4096x2048_180_sbs → 180_sbs（ambiguous ×2 共現）"""
        result = _detect_vr_cluster("WAVR-456_4096x2048_180_sbs")
        assert result == "180_sbs"

    def test_hit_180_lr(self):
        """NAME_180_LR → 180_LR（最主流：ambiguous ×2 共現）"""
        result = _detect_vr_cluster("NAME_180_LR")
        assert result == "180_LR"

    def test_hit_mixed_case(self):
        """KAVR-001_MKX200_lr → MKX200_lr（混大小寫原樣回傳，不正規化）"""
        result = _detect_vr_cluster("KAVR-001_MKX200_lr")
        assert result == "MKX200_lr"

    def test_hit_4k_nonvr_prefix_excluded(self):
        """MOVIE-4k_180_3dh_LR → 180_3dh_LR（4k 非 VR token，cluster 從 180 起）"""
        result = _detect_vr_cluster("MOVIE-4k_180_3dh_LR")
        assert result == "180_3dh_LR"

    def test_hit_bracket_square(self):
        """NAME_[180_LR] → 180_LR（bracket 當分隔符，cluster 不含外圍括號）"""
        result = _detect_vr_cluster("NAME_[180_LR]")
        assert result == "180_LR"

    def test_hit_bracket_paren(self):
        """KAVR-001_(mkx200_lr) → mkx200_lr（paren 當分隔符，cluster 不含外圍括號）"""
        result = _detect_vr_cluster("KAVR-001_(mkx200_lr)")
        assert result == "mkx200_lr"

    # ---- None 列（守零變化）----

    def test_none_isolated_180(self):
        """MIRD-180 → None（孤立裸 180，真番號，無共現 VR token）"""
        result = _detect_vr_cluster("MIRD-180")
        assert result is None

    def test_none_isolated_360(self):
        """REBD-360 → None（孤立裸 360，真番號）"""
        result = _detect_vr_cluster("REBD-360")
        assert result is None

    def test_none_isolated_lr(self):
        """title_LR → None（孤立裸 LR，無共現）"""
        result = _detect_vr_cluster("title_LR")
        assert result is None

    def test_none_vr_num_no_token(self):
        """SIVR-999 → None（VR 番號但無 VR token；SIVR/999 皆非集合成員）"""
        result = _detect_vr_cluster("SIVR-999")
        assert result is None

    def test_none_color_edition_no_false_lr(self):
        """ABP-123 [color edition] → None（不誤中 lr：color 非 VR 成員）"""
        result = _detect_vr_cluster("ABP-123 [color edition]")
        assert result is None

    def test_none_1080_not_180(self):
        """STARS-1080 → None（不誤中 180：1080 是獨立 token，exact match 不命中）"""
        result = _detect_vr_cluster("STARS-1080")
        assert result is None

    def test_none_bare_vr_tag(self):
        """[VR] → None（裸 vr 不是訊號；嚴禁進集合）"""
        result = _detect_vr_cluster("[VR]")
        assert result is None

    # ---- 含副檔名也應一致 ----

    def test_with_extension_mp4(self):
        """NAME_180_LR.mp4（含副檔名）→ 180_LR（splitext 去掉 ext）"""
        result = _detect_vr_cluster("NAME_180_LR.mp4")
        assert result == "180_LR"

    def test_none_with_extension(self):
        """MIRD-180.mp4（含副檔名）→ None"""
        result = _detect_vr_cluster("MIRD-180.mp4")
        assert result is None

    # --- 防禦性 / branch 補洞（review advisory）---
    def test_empty_string(self):
        """空字串 → None（splitext('') → finditer 無命中 → 不炸）"""
        assert _detect_vr_cluster("") is None

    def test_unique_only_no_ambiguous(self):
        """單一 unique token、零 ambiguous（unique-only branch）→ 原樣保留"""
        assert _detect_vr_cluster("fisheye") == "fisheye"
        assert _detect_vr_cluster("KAVR-001_mkx200") == "mkx200"

    def test_duplicate_ambiguous_satisfies_cooccurrence(self):
        """兩個相同 ambiguous token（len(ambiguous)>=2）→ 成立"""
        assert _detect_vr_cluster("NAME_180_180") == "180_180"

    # ---- Codex P2 修正（Finding 2）：連續 run 偵測 ----

    def test_none_scattered_ambiguous_across_words(self):
        """TITLE_180_some_words_LR.mp4 → None
        （散落 ambiguous 被 non-VR token 隔開，不構成連續 run，不應共現）"""
        result = _detect_vr_cluster("TITLE_180_some_words_LR.mp4")
        assert result is None, (
            f"散落 ambiguous 跨文字不共現，應為 None，實際：{result!r}"
        )

    def test_none_ambiguous_with_nonvr_between(self):
        """MOVIE_180_4k_LR.mp4 → None
        （4k 是 non-VR token，夾在 180 與 LR 之間斷開 run；散落不共現）"""
        result = _detect_vr_cluster("MOVIE_180_4k_LR.mp4")
        assert result is None, (
            f"non-VR token（4k）夾斷 run，兩端散落 ambiguous 不共現，應為 None，實際：{result!r}"
        )

    def test_partial_run_unique_isolated_lr(self):
        """A_180x180_word_LR → 180x180
        （unique 180x180 自成一個 confirmed run；孤立 LR 因中間夾了 non-VR 'word' 不在同 run）"""
        result = _detect_vr_cluster("A_180x180_word_LR")
        assert result == "180x180", (
            f"只有 unique 180x180 那個 run confirmed，孤立 LR 跨字不算，期望 '180x180'，實際：{result!r}"
        )

    # ---- Codex P2 二次修正（Finding 2, P3）：多 confirmed run 只取第一個 ----

    def test_multiple_confirmed_runs_returns_first(self):
        """A_180_LR_title_3dh → '180_LR'（只取第一個 confirmed run，不跨 non-VR title 到第二 run）

        Repro：run1=[180,LR]（ambiguous×2，confirmed），non-VR token 'title' 斷開，
        run2=[3dh]（unique，confirmed）；舊邏輯跨 span → '180_LR_title_3dh'（含 junk）。
        修正後只取 first confirmed run → '180_LR'。
        """
        result = _detect_vr_cluster("A_180_LR_title_3dh")
        assert result == "180_LR", (
            f"多個 confirmed run 應只取第一個，期望 '180_LR'，實際：{result!r}"
        )
        # 含副檔名同結果
        result_ext = _detect_vr_cluster("A_180_LR_title_3dh.mp4")
        assert result_ext == "180_LR", (
            f"含副檔名：多個 confirmed run 應只取第一個，期望 '180_LR'，實際：{result_ext!r}"
        )


# ============ organize_file() VR 檔名端到端測試 ============

class TestOrganizeVrFilename:
    """organize_file() VR tail 端到端測試（TDD-lite，T2 DoD）

    驗證：
    - VR cluster 正確接到檔名尾（_{cluster}）
    - suffix × VR 順序 = base + suffix + _vr
    - 超長截斷時 VR cluster 完整不被切
    - 無 VR token 檔案 byte 級零變化（reserve=0）
    - 一般 2D 檔 byte 級零變化
    - 既有 suffix 路徑不回歸（-cd1/-cd2，無 VR，reserve=0 不影響）
    """

    # ---- DoD Row 1: VR 檔名尾正確接 _{cluster} ----

    def test_vr_tail_appended_no_suffix(self, tmp_path):
        """NAME_180_LR.mp4（無 suffix keyword）→ filename 尾帶 _180_LR"""
        src = tmp_path / "NAME_180_LR.mp4"
        src.write_bytes(b"vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
        }
        metadata = {
            "number": "VR-001",
            "title": "VR Test Title",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        assert new_name.endswith("_180_LR.mp4"), (
            f"VR tail _180_LR 未接到尾：{new_name}"
        )

    # ---- DoD Row 2: suffix × VR 順序（base + suffix + _vr） ----

    def test_suffix_before_vr_tail(self, tmp_path):
        """MOVIE-4k_180_3dh_LR.mp4（suffix=-4k, VR cluster=180_3dh_LR）
        → 輸出順序 = base + -4k + _180_3dh_LR（suffix 在 VR 之前）"""
        src = tmp_path / "MOVIE-4k_180_3dh_LR.mp4"
        src.write_bytes(b"vr 4k content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 80,
            "suffix_keywords": ["-4k", "-cd1", "-uc"],
        }
        metadata = {
            "number": "MOVIE-001",
            "title": "Some Title",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        stem = Path(new_name).stem  # 不含副檔名

        # suffix -4k 必須出現
        assert "-4k" in stem, f"suffix -4k 未在檔名中：{new_name}"
        # VR tail _180_3dh_LR 必須在最後
        assert stem.endswith("_180_3dh_LR"), (
            f"VR tail _180_3dh_LR 未在 stem 最尾：{stem}"
        )
        # 順序：-4k 出現位置在 _180 之前
        idx_suffix = stem.index("-4k")
        idx_vr = stem.index("_180_3dh_LR")
        assert idx_suffix < idx_vr, (
            f"suffix(-4k) 應在 VR tail(_180_3dh_LR) 之前：{stem}"
        )

    # ---- DoD Row 3: 超長截斷 VR cluster 完整不被切 ----

    def test_long_title_vr_cluster_preserved(self, tmp_path):
        """超長 title + _180_3dh_LR.mp4：base 被 max_filename_length 截，VR cluster 完整"""
        src = tmp_path / "VR-999_180_3dh_LR.mp4"
        src.write_bytes(b"long vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 30,  # 故意很短，迫使截斷
            "suffix_keywords": ["-4k"],
        }
        metadata = {
            "number": "VR-999",
            "title": "超級無敵長的標題名稱會被截斷但VR尾應完整保留",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        stem = Path(new_name).stem
        # VR cluster 必須完整保留（_180_3dh_LR 原樣）
        assert stem.endswith("_180_3dh_LR"), (
            f"VR cluster _180_3dh_LR 被截斷：{stem}"
        )
        # 核心：reserve budget 真的生效——整個檔名（含 ext）不得超出 max_filename_length。
        # 沒有這行，「不扣 reserve 直接 overflow」也會讓上面的 endswith 通過（假測試）。
        assert len(new_name) <= 30, (
            f"reserve budget 未生效，檔名 {len(new_name)} 字超出 max_filename_length=30：{new_name!r}"
        )
        # base 確實被壓縮：超長標題不可能完整出現（證明 reserve 扣掉了 base 預算）
        assert "超級無敵長的標題名稱會被截斷但VR尾應完整保留" not in stem, (
            f"base 未被截斷，reserve 未壓縮 base：{stem}"
        )

    def test_vr_cluster_preserved_when_base_budget_zero(self, tmp_path):
        """退化邊界（CD-68-7 base_budget==0）：max_filename_length 短到 base 預算歸零，
        VR cluster 仍完整保留、檔名不超限（reserve 在 base_budget==0 子分支也生效）"""
        src = tmp_path / "VR-1_180_3dh_LR.mp4"
        src.write_bytes(b"x")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 16,  # ext(.mp4=4)+vr_tail(_180_3dh_LR=11)=15，base 預算 ~1
            "suffix_keywords": ["-4k"],
        }
        metadata = {
            "number": "VR-1",
            "title": "X" * 80,
            "actors": [], "tags": [], "maker": "M", "date": "2024-01-15",
            "cover": "", "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        assert Path(new_name).stem.endswith("_180_3dh_LR"), (
            f"VR cluster 在 base_budget==0 退化時被切：{new_name}"
        )
        assert len(new_name) <= 16, (
            f"base_budget==0 子分支 reserve 未生效，超限：{new_name!r}"
        )

    # ---- DoD Row 4: 無 VR token，byte 級零變化（SIVR-999.mp4，else 分支） ----

    def test_no_vr_token_byte_identical(self, tmp_path):
        """SIVR-999.mp4（無 VR token、無 suffix）→ reserve=0，
        輸出名與未改動前完全相同（byte 級零變化）"""
        src = tmp_path / "SIVR-999.mp4"
        src.write_bytes(b"no vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": ["-cd1", "-cd2", "-4k"],
        }
        metadata = {
            "number": "SIVR-999",
            "title": "Some Title",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        # reserve=0 → 與 T2 改動前的預期完全相同（byte-identical path）
        # expected = "[{num}] {title}" truncated to max_chars, no vr_tail
        expected_stem = truncate_to_chars("[SIVR-999] Some Title", 60 - len(".mp4"))
        expected_name = expected_stem + ".mp4"
        assert new_name == expected_name, (
            f"零變化失敗：got {new_name!r}, expected {expected_name!r}"
        )

    # ---- DoD Row 5: 一般 2D 檔 byte 級零變化 ----

    def test_2d_file_byte_identical(self, tmp_path):
        """一般 2D 檔（無 VR token）→ reserve=0，輸出名與改動前完全相同"""
        src = tmp_path / "ABP-123.mp4"
        src.write_bytes(b"2d content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": ["-cd1", "-4k"],
        }
        metadata = {
            "number": "ABP-123",
            "title": "Normal Title",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        expected_stem = truncate_to_chars("[ABP-123] Normal Title", 60 - len(".mp4"))
        expected_name = expected_stem + ".mp4"
        assert new_name == expected_name, (
            f"2D 零變化失敗：got {new_name!r}, expected {expected_name!r}"
        )

    # ---- DoD Row 6: 既有 suffix 路徑不回歸（無 VR，reserve=0） ----

    def test_existing_suffix_no_regression(self, tmp_path):
        """既有 -cd1/-cd2 suffix（無 VR）→ reserve=0，行為完全不回歸"""
        cd1 = tmp_path / "SONE-205-CD1.mp4"
        cd1.write_bytes(b"cd1 content")
        cd2 = tmp_path / "SONE-205-CD2.mp4"
        cd2.write_bytes(b"cd2 content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": ["-cd1", "-cd2", "-4k"],
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

        result1 = organize_file(str(cd1), metadata, config)
        result2 = organize_file(str(cd2), metadata, config)

        assert result1["success"] is True, f"CD1 失敗: {result1.get('error')}"
        assert result2["success"] is True, f"CD2 失敗: {result2.get('error')}"

        name1 = Path(result1["new_filename"]).name
        name2 = Path(result2["new_filename"]).name

        # suffix 保留
        assert "-cd1" in name1, f"CD1 suffix 消失：{name1}"
        assert "-cd2" in name2, f"CD2 suffix 消失：{name2}"
        # 沒有意外 VR tail（無 VR token）
        assert "_180" not in name1 and "_LR" not in name1, f"CD1 意外多了 VR tail：{name1}"
        assert "_180" not in name2 and "_LR" not in name2, f"CD2 意外多了 VR tail：{name2}"

    # ---- Codex PR P2 回歸：退化 config 最終長度上限保護 ----

    def test_degenerate_max_len_vr_tail_bounded(self, tmp_path):
        """退化 config（max_filename_length < ext + vr_tail）最終檔名不得超出上限。

        SIVR-1_180_3dh_LR.mp4：
          vr_tail = _180_3dh_LR（11 chars）
          ext     = .mp4（4 chars）
          vr_tail + ext = 15 chars
          max_filename_length = 10 < 15  → 退化（連 ext+vr_tail 都裝不下）

        修前行為：filename_base = '' + '_180_3dh_LR' = '_180_3dh_LR'（11）
                  new_filename  = '_180_3dh_LR.mp4'（15）> 10  → overflow
        修後行為：最終 cap 截到 max_chars=6 → len(new_filename) <= 10
        """
        src = tmp_path / "SIVR-1_180_3dh_LR.mp4"
        src.write_bytes(b"degenerate vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": 10,   # < ext(4) + vr_tail(11) = 15 → 退化
            "suffix_keywords": ["-cd1", "-cd2"],
        }
        metadata = {
            "number": "SIVR-1",
            "title": "Title",
            "actors": [],
            "tags": [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result["new_filename"]).name
        assert len(new_name) <= 10, (
            f"退化 config overflow 未被 cap：len={len(new_name)}，filename={new_name!r}"
        )


# ============ generate_nfo() VR tag/genre 去重測試 (T3) ============

class TestGenerateNfoVrTagDedup:
    """generate_nfo() has_vr 參數 + tag/genre VR 去重邏輯測試（TASK-68-T3）

    邊界條件來源：68-T3.md 邊界條件表 + plan-68.md CD-68-8/9
    """

    def test_has_vr_true_no_vr_in_tags_adds_canonical(self, tmp_path):
        """has_vr=True + tags 無 VR → 補 canonical <tag>VR</tag> + <genre>VR</genre>（各恰一個）"""
        nfo_path = tmp_path / "SIVR-123.nfo"
        result = generate_nfo(
            number="SIVR-123",
            title="テスト",
            tags=["巨乳", "單體"],
            output_path=str(nfo_path),
            has_vr=True,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert content.count("<tag>VR</tag>") == 1, \
            f"has_vr=True + 無 VR tags → 應含恰一個 <tag>VR</tag>，content={content!r}"
        assert content.count("<genre>VR</genre>") == 1, \
            f"has_vr=True + 無 VR tags → 應含恰一個 <genre>VR</genre>，content={content!r}"

    def test_has_vr_true_scraper_already_has_vr_no_duplicate(self, tmp_path):
        """has_vr=True + scraper tags 已有 VR → 不重複補 canonical（各恰一個）"""
        nfo_path = tmp_path / "KAVR-001.nfo"
        result = generate_nfo(
            number="KAVR-001",
            title="テスト",
            tags=["VR", "單體"],
            output_path=str(nfo_path),
            has_vr=True,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert content.count("<tag>VR</tag>") == 1, \
            f"scraper 已有 VR + has_vr=True → 應仍只有一個 <tag>VR</tag>（不重複）"
        assert content.count("<genre>VR</genre>") == 1, \
            f"scraper 已有 VR + has_vr=True → 應仍只有一個 <genre>VR</genre>（不重複）"

    def test_has_vr_true_lowercase_space_variant_no_duplicate(self, tmp_path):
        """has_vr=True + tags=[' vr ','x']（小寫+空白變體）→ case-insensitive 去重，不補 canonical"""
        nfo_path = tmp_path / "WAVR-456.nfo"
        result = generate_nfo(
            number="WAVR-456",
            title="テスト",
            tags=[" vr ", "x"],
            output_path=str(nfo_path),
            has_vr=True,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        # 不可額外補 canonical VR，count 不爆（tag 與 genre 各最多一個 VR 相關 entry）
        # ` vr ` 由 tags 迴圈寫出（html.escape 後原樣），不補第二個 <tag>VR</tag>
        assert content.count("<tag>VR</tag>") == 0, \
            f"小寫/空白 vr 已在 tags → 不應額外補 canonical <tag>VR</tag>"
        assert content.count("<genre>VR</genre>") == 0, \
            f"小寫/空白 vr 已在 tags → 不應額外補 canonical <genre>VR</genre>"
        # 正向：scraper 原始變體仍原樣由 tags 迴圈寫出（去重只擋 canonical，不吞 scraper 條目）
        assert "<tag> vr </tag>" in content, \
            "scraper 原始 ' vr ' 變體應原樣寫出（spec §3 邊界表：該變體由 tags 迴圈寫出）"
        assert "<genre> vr </genre>" in content, \
            "scraper 原始 ' vr ' 變體 genre 應原樣寫出"

    def test_has_vr_false_no_vr_in_tags_no_vr_written(self, tmp_path):
        """has_vr=False + tags 無 VR → NFO 完全無 VR tag/genre（不多補）"""
        nfo_path = tmp_path / "ABP-123.nfo"
        result = generate_nfo(
            number="ABP-123",
            title="テスト",
            tags=["巨乳"],
            output_path=str(nfo_path),
            has_vr=False,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert "<tag>VR</tag>" not in content, \
            "has_vr=False + 無 VR tags → NFO 不應含 <tag>VR</tag>"
        assert "<genre>VR</genre>" not in content, \
            "has_vr=False + 無 VR tags → NFO 不應含 <genre>VR</genre>"

    def test_has_vr_false_scraper_vr_preserved(self, tmp_path):
        """has_vr=False + scraper tags 含 VR → scraper VR 照寫（不可斷言『無 VR』）"""
        nfo_path = tmp_path / "STARS-999.nfo"
        result = generate_nfo(
            number="STARS-999",
            title="テスト",
            tags=["VR", "x"],
            output_path=str(nfo_path),
            has_vr=False,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        # scraper 給的 VR 必須照 tags 路徑寫出（各一）
        assert content.count("<tag>VR</tag>") == 1, \
            "has_vr=False + scraper VR → scraper VR tag 應照寫"
        assert content.count("<genre>VR</genre>") == 1, \
            "has_vr=False + scraper VR → scraper VR genre 應照寫"

    def test_has_vr_true_with_subtitle_coexist(self, tmp_path):
        """has_vr=True + has_subtitle=True → VR 與中文字幕 tag/genre 共存（互不干擾）"""
        nfo_path = tmp_path / "SIVR-VR-C.nfo"
        result = generate_nfo(
            number="SIVR-VR-C",
            title="VR 中字",
            tags=["巨乳"],
            output_path=str(nfo_path),
            has_vr=True,
            has_subtitle=True,
        )
        assert result is True
        content = nfo_path.read_text(encoding="utf-8")
        assert content.count("<tag>VR</tag>") == 1, \
            "has_vr=True + has_subtitle=True → 應含恰一個 <tag>VR</tag>"
        assert content.count("<genre>VR</genre>") == 1, \
            "has_vr=True + has_subtitle=True → 應含恰一個 <genre>VR</genre>"
        assert "<tag>中文字幕</tag>" in content, \
            "has_subtitle=True 時 <tag>中文字幕</tag> 應仍存在（VR 不干擾中字）"
        assert "<genre>中文字幕</genre>" in content, \
            "has_subtitle=True 時 <genre>中文字幕</genre> 應仍存在"

    def test_has_vr_false_no_vr_nfo_byte_identical(self, tmp_path):
        """has_vr=False（預設）一般檔 → NFO 與未加 has_vr 前 byte 完全相同（CD-68-9）

        兩次呼叫使用同一 output_path（basename 相同），保證 <poster>/<thumb>/<fanart> 不因
        檔名不同而差異——此測試純粹驗證 has_vr=False 不在 NFO 內容裡新增任何 VR 相關行。
        """
        dir_before = tmp_path / "before"
        dir_after = tmp_path / "after"
        dir_before.mkdir()
        dir_after.mkdir()
        # 兩次用同一 NFO 檔名（basename 相同 → poster/thumb/fanart tag 相同）
        nfo_path_before = dir_before / "ABP-555.nfo"
        nfo_path_after = dir_after / "ABP-555.nfo"

        # 「未加 has_vr 前」：不傳 has_vr（使用預設值）
        generate_nfo(
            number="ABP-555",
            title="一般標題",
            tags=["巨乳", "OL"],
            actors=["女優A"],
            date="2024-03-01",
            maker="Studio",
            output_path=str(nfo_path_before),
        )
        # 「加了 has_vr=False」：明確傳 False
        generate_nfo(
            number="ABP-555",
            title="一般標題",
            tags=["巨乳", "OL"],
            actors=["女優A"],
            date="2024-03-01",
            maker="Studio",
            output_path=str(nfo_path_after),
            has_vr=False,
        )
        content_before = nfo_path_before.read_text(encoding="utf-8")
        content_after = nfo_path_after.read_text(encoding="utf-8")
        assert content_before == content_after, \
            f"has_vr=False 應與不傳時完全相同（零變化）\nbefore={content_before!r}\nafter={content_after!r}"


# ============ organize_file() VR 端到端串接測試 (T4) ============

class TestVrEndToEnd:
    """organize_file(create_nfo=True) 端到端 wiring 測試（TASK-68-T4）

    核心 gap：T2 用 create_nfo=False，T3 直呼 generate_nfo——
    未有任何測試同時驗「VR tail 檔名」+「NFO 恰一個 <tag>VR</tag>」。

    本 class 補上這條端到端鏈路：一次 organize_file 呼叫，
    同時斷言 (a) 檔名 stem tail、(b) NFO VR tag count==1 + genre count==1、
    (c) NFO sidecar 檔名 stem 與影片對齊（GB sidecar 跟隨）。
    """

    # ---- 共用 helper ----

    def _base_config(self, tmp_path=None, max_filename_length=60, suffix_keywords=None):
        return {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": max_filename_length,
            "suffix_keywords": suffix_keywords or [],
        }

    def _base_metadata(self, number, title, tags=None):
        return {
            "number": number,
            "title": title,
            "actors": [],
            "tags": tags or [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

    # ---- T4 DoD: VR 檔（KAVR-001_mkx200_LR.mp4）端到端 ----

    def test_vr_file_filename_tail_and_nfo_vr_tag(self, tmp_path):
        """KAVR-001_mkx200_LR.mp4 + tags=['單體']（無 VR）→
        (a) 檔名 stem 結尾 _mkx200_LR
        (b) NFO 含恰一個 <tag>VR</tag> + 一個 <genre>VR</genre>
        (c) NFO sidecar 檔名 stem 與影片 stem 對齊（prove GB sidecar 跟隨）
        """
        src = tmp_path / "KAVR-001_mkx200_LR.mp4"
        src.write_bytes(b"vr content")

        config = self._base_config(tmp_path)
        metadata = self._base_metadata("KAVR-001", "VR Test Title", tags=["單體"])

        result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        # (a) 檔名 stem 結尾 _mkx200_LR
        new_path = Path(result["new_filename"])
        stem = new_path.stem
        assert stem.endswith("_mkx200_LR"), (
            f"VR tail _mkx200_LR 未接到 stem 尾：{stem!r}"
        )

        # (b) NFO 含恰一個 <tag>VR</tag> + 一個 <genre>VR</genre>
        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        assert Path(nfo_path).exists(), f"NFO 檔不存在：{nfo_path}"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO 應含恰一個 <tag>VR</tag>，count={nfo_content.count('<tag>VR</tag>')}"
        )
        assert nfo_content.count("<genre>VR</genre>") == 1, (
            f"NFO 應含恰一個 <genre>VR</genre>，count={nfo_content.count('<genre>VR</genre>')}"
        )

        # (c) NFO sidecar 檔名 stem 與影片 stem 對齊（VR tail 隨行，prove GB）
        nfo_stem = Path(nfo_path).stem
        assert nfo_stem == stem, (
            f"NFO sidecar stem({nfo_stem!r}) 應與影片 stem({stem!r}) 完全對齊"
        )
        assert nfo_stem.endswith("_mkx200_LR"), (
            f"NFO sidecar stem 應帶 VR tail：{nfo_stem!r}"
        )

    def test_vr_file_scraper_already_has_vr_no_duplicate(self, tmp_path):
        """KAVR-001_mkx200_LR.mp4 + scraper tags=['VR', '單體']
        → NFO <tag>VR</tag> 恰一個（去重驗端到端不重複）
        """
        src = tmp_path / "KAVR-001_mkx200_LR.mp4"
        src.write_bytes(b"vr content")

        config = self._base_config(tmp_path)
        metadata = self._base_metadata("KAVR-001", "VR Test", tags=["VR", "單體"])

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        nfo_content = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"scraper 已有 VR + has_vr=True → 應仍只有一個 <tag>VR</tag>（端到端去重）"
        )
        assert nfo_content.count("<genre>VR</genre>") == 1, (
            f"scraper 已有 VR + has_vr=True → 應仍只有一個 <genre>VR</genre>（端到端去重）"
        )

    # ---- T4 DoD: 無 VR 檔（SIVR-999.mp4）端到端 ----

    def test_no_vr_file_no_tail_no_canonical_vr_in_nfo(self, tmp_path):
        """SIVR-999.mp4（無 VR token）+ create_nfo=True →
        (a) 檔名無 VR tail
        (b) NFO 無 canonical <tag>VR</tag>（has_vr=False 端到端）
        """
        src = tmp_path / "SIVR-999.mp4"
        src.write_bytes(b"no vr content")

        config = self._base_config(tmp_path)
        metadata = self._base_metadata("SIVR-999", "Some 2D Title", tags=["單體"])

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        # (a) 檔名無 VR tail
        new_path = Path(result["new_filename"])
        stem = new_path.stem
        assert not stem.endswith(("_LR", "_180", "_mkx200", "_3dh", "_sbs")), (
            f"無 VR token 檔案不應有 VR tail：{stem!r}"
        )

        # (b) NFO 無 canonical <tag>VR</tag>（has_vr=False 路徑端到端）
        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "nfo_path 不應為 None"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        assert "<tag>VR</tag>" not in nfo_content, (
            f"SIVR-999（無 VR token）NFO 不應含 canonical <tag>VR</tag>"
        )
        assert "<genre>VR</genre>" not in nfo_content, (
            f"SIVR-999（無 VR token）NFO 不應含 canonical <genre>VR</genre>"
        )

    # ---- Codex P2 修正（Finding 1）：中文標題 VR token 雙寫 ----

    def test_chinese_title_vr_no_double_write(self, tmp_path):
        """ABC-123 中文標題_180_LR.mp4 + create_nfo=True + extracted_title 路徑
        → 檔名 stem 僅有單一 _180_LR（不雙寫 _180_LR_180_LR）
        且 NFO sidecar stem 也單一 tail、<tag>VR</tag> count==1。

        Codex P2（Finding 1）：extract_chinese_title 保留 VR token 在 title，
        之後 vr_tail 再接一次 → _180_LR_180_LR 雙寫。
        """
        src = tmp_path / "ABC-123 中文標題_180_LR.mp4"
        src.write_bytes(b"zh title vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 80,
            "suffix_keywords": [],
        }
        # metadata title 空字串 → 迫使走 extracted_title 路徑（title_source=='extracted'）
        metadata = {
            "number": "ABC-123",
            "title": "",         # 空 → 不走 original 路徑
            "translated_title": "",  # 空 → 不走 translated 路徑
            "actors": [],
            "tags": ["單體"],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        # title_source 應為 extracted（確認走了 extract 路徑）
        assert result.get("title_source") == "extracted", (
            f"應走 extracted 路徑，實際 title_source={result.get('title_source')!r}"
        )

        new_path = Path(result["new_filename"])
        stem = new_path.stem

        # 關鍵斷言：stem 中 _180_LR 恰好出現一次（不雙寫）
        assert stem.count("_180_LR") == 1, (
            f"_180_LR 應恰好出現 1 次（不雙寫），實際 stem：{stem!r}，count={stem.count('_180_LR')}"
        )
        # stem 應以 _180_LR 結尾
        assert stem.endswith("_180_LR"), (
            f"VR tail 應在 stem 最末，實際 stem：{stem!r}"
        )

        # NFO sidecar：stem 對齊 + <tag>VR</tag> count==1
        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        nfo_stem = Path(nfo_path).stem
        assert nfo_stem == stem, (
            f"NFO sidecar stem({nfo_stem!r}) 應與影片 stem({stem!r}) 對齊"
        )
        assert nfo_stem.count("_180_LR") == 1, (
            f"NFO sidecar stem _180_LR 也應單一，實際：{nfo_stem!r}"
        )
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO <tag>VR</tag> 應恰一個，count={nfo_content.count('<tag>VR</tag>')}"
        )

    # ---- Codex P2 二次修正（Finding 1, P2）：bracket/paren 包 cluster 不雙寫 ----

    def test_chinese_title_bracket_vr_no_double_write(self, tmp_path):
        """ABC-123 中文標題_[180_LR].mp4 + create_nfo=True + extracted_title 路徑
        → 檔名 stem 僅有單一 _180_LR（不雙寫 _[180_LR]_180_LR）
        且 stem 中不含 '[180_LR]'、NFO <tag>VR</tag> count==1。

        Codex P2 二次修正（Finding 1, P2）：_detect_vr_cluster 回傳 '180_LR'（不含 bracket），
        但 extract_chinese_title 萃取的 title 保留 '[180_LR]'，舊 endswith 不命中 →
        bracket 殘留在 title + vr_tail 再接 → 雙寫。
        修正：regex 匹配可選 bracket 包裝。
        """
        src = tmp_path / "ABC-123 中文標題_[180_LR].mp4"
        src.write_bytes(b"zh bracket vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 80,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "ABC-123",
            "title": "",
            "translated_title": "",
            "actors": [],
            "tags": ["單體"],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        assert result.get("title_source") == "extracted", (
            f"應走 extracted 路徑，實際 title_source={result.get('title_source')!r}"
        )

        stem = Path(result["new_filename"]).stem

        # 關鍵：stem 中 _180_LR 恰一次（不雙寫）
        assert stem.count("_180_LR") == 1, (
            f"_180_LR 應恰好出現 1 次（不雙寫），實際 stem：{stem!r}"
        )
        # stem 中不應含原始 bracket 形式
        assert "[180_LR]" not in stem, (
            f"stem 中不應含 '[180_LR]'（bracket 殘留），實際 stem：{stem!r}"
        )
        # 不應有雙寫形式
        assert "_180_LR_180_LR" not in stem, (
            f"stem 中不應有 _180_LR_180_LR（雙寫），實際 stem：{stem!r}"
        )
        # stem 以 _180_LR 結尾
        assert stem.endswith("_180_LR"), (
            f"VR tail 應在 stem 最末，實際 stem：{stem!r}"
        )

        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO <tag>VR</tag> 應恰一個，count={nfo_content.count('<tag>VR</tag>')}"
        )

    def test_chinese_title_paren_vr_no_double_write(self, tmp_path):
        """ABC-123 中文標題_(180_LR).mp4 + create_nfo=True + extracted_title 路徑
        → 檔名 stem 僅有單一 _180_LR（不雙寫 _(180_LR)_180_LR）
        且 stem 中不含 '(180_LR)'、NFO <tag>VR</tag> count==1。

        Codex P2 二次修正（Finding 1, P2）：同 bracket case，paren 版本。
        """
        src = tmp_path / "ABC-123 中文標題_(180_LR).mp4"
        src.write_bytes(b"zh paren vr content")

        config = {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 80,
            "suffix_keywords": [],
        }
        metadata = {
            "number": "ABC-123",
            "title": "",
            "translated_title": "",
            "actors": [],
            "tags": ["單體"],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        assert result.get("title_source") == "extracted", (
            f"應走 extracted 路徑，實際 title_source={result.get('title_source')!r}"
        )

        stem = Path(result["new_filename"]).stem

        assert stem.count("_180_LR") == 1, (
            f"_180_LR 應恰好出現 1 次（不雙寫），實際 stem：{stem!r}"
        )
        assert "(180_LR)" not in stem, (
            f"stem 中不應含 '(180_LR)'（paren 殘留），實際 stem：{stem!r}"
        )
        assert "_180_LR_180_LR" not in stem, (
            f"stem 中不應有 _180_LR_180_LR（雙寫），實際 stem：{stem!r}"
        )
        assert stem.endswith("_180_LR"), (
            f"VR tail 應在 stem 最末，實際 stem：{stem!r}"
        )

        nfo_path = result.get("nfo_path")
        assert nfo_path is not None, "create_nfo=True 時 nfo_path 不應為 None"
        nfo_content = Path(nfo_path).read_text(encoding="utf-8")
        assert nfo_content.count("<tag>VR</tag>") == 1, (
            f"NFO <tag>VR</tag> 應恰一個，count={nfo_content.count('<tag>VR</tag>')}"
        )


# ============ spec §4 DoD 補洞：Row 3/8 檔名端到端 ============

class TestVrCrossCheck:
    """spec §4 DoD 表 cross-check 補洞（T4）

    Row 3（WAVR-456_4096x2048_180_sbs.mp4）和 Row 8（KAVR-001_MKX200_lr.mp4）
    只有 T1 偵測層覆蓋，T2/T3/T4 無 organize_file 檔名層驗證。
    本 class 補上 organize_file 層的斷言，使 spec §4 全表每列在組裝層都有覆蓋。
    """

    def _base_config(self, max_filename_length=80):
        return {
            "create_folder": False,
            "filename_format": "[{num}] {title}{suffix}",
            "download_cover": False,
            "create_nfo": False,
            "max_title_length": 50,
            "max_filename_length": max_filename_length,
            "suffix_keywords": [],
        }

    def _base_metadata(self, number, title, tags=None):
        return {
            "number": number,
            "title": title,
            "actors": [],
            "tags": tags or [],
            "maker": "Studio",
            "date": "2024-01-15",
            "cover": "",
            "url": "",
        }

    def test_row3_wavr_180_sbs_filename_tail(self, tmp_path):
        """spec §4 Row 3: WAVR-456_4096x2048_180_sbs.mp4 → 檔名 stem 結尾 _180_sbs

        T1 只驗偵測，T2 沒有此 case 的 organize_file 層，T4 補上。
        """
        src = tmp_path / "WAVR-456_4096x2048_180_sbs.mp4"
        src.write_bytes(b"wavr content")

        config = self._base_config()
        metadata = self._base_metadata("WAVR-456", "VR Title")

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        stem = Path(result["new_filename"]).stem
        assert stem.endswith("_180_sbs"), (
            f"spec §4 Row 3: WAVR-456 VR tail 應為 _180_sbs，實際 stem：{stem!r}"
        )

    def test_row8_mixed_case_filename_tail_preserve_raw(self, tmp_path):
        """spec §4 Row 8: KAVR-001_MKX200_lr.mp4 → 檔名 stem 結尾 _MKX200_lr（原樣大小寫）

        T1 只驗偵測，T2 沒有此 case 的 organize_file 層，T4 補上。
        重點：原始大小寫不正規化（MKX200 大寫保留，lr 小寫保留）。
        """
        src = tmp_path / "KAVR-001_MKX200_lr.mp4"
        src.write_bytes(b"mixed case vr content")

        config = self._base_config()
        metadata = self._base_metadata("KAVR-001", "Mixed Case VR")

        result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"

        stem = Path(result["new_filename"]).stem
        assert stem.endswith("_MKX200_lr"), (
            f"spec §4 Row 8: VR tail 大小寫應原樣（_MKX200_lr），實際 stem：{stem!r}"
        )


# ============ TestOrganizeMultipart — 72b-T5 多段整合測試 ============

class TestIsMultipartKw:
    """_is_multipart_kw() 單元測試"""

    def test_cd1_with_dash(self):
        assert _is_multipart_kw('-cd1') is True

    def test_cd2_with_dash(self):
        assert _is_multipart_kw('-cd2') is True

    def test_dvd1_with_dash(self):
        assert _is_multipart_kw('-dvd1') is True

    def test_part2_no_prefix(self):
        assert _is_multipart_kw('part2') is True

    def test_pt1_with_underscore(self):
        assert _is_multipart_kw('_pt1') is True

    def test_disc1(self):
        assert _is_multipart_kw('-disc1') is True

    def test_4k_not_multipart(self):
        assert _is_multipart_kw('-4k') is False

    def test_uc_not_multipart(self):
        assert _is_multipart_kw('_uc') is False

    def test_empty_string(self):
        assert _is_multipart_kw('') is False

    def test_separator_only(self):
        assert _is_multipart_kw('-') is False

    def test_cd10_not_multipart(self):
        """cd10 數字>9 → 不算多段 token（與 _MULTIPART_RE 一致）"""
        assert _is_multipart_kw('-cd10') is False

    def test_cd1_no_prefix(self):
        """無前導分隔符的 'cd1' 也應識別為多段"""
        assert _is_multipart_kw('cd1') is True


class TestOrganizeMultipart:
    """organize_file() 多段（multipart）整合測試（TASK-72b-T5）

    涵蓋：
    A  cd1 外部模式 → 正常 NFO、part_tail 在 stem 末
    B  cd2 外部模式 → 跳 NFO、保留封面/poster/fanart、success True
    C  長標題 + cd1 → 不超 max_filename_length 且 -cd1 不被截
    D  防 {suffix} 雙寫（-cd1-cd1 negative）
    E  off 模式 byte-identical（cd2 也照產 NFO）
    F  VR + cd1 → 順序 {vr_tail}-cd1
    G  kodi cd2 → 保留封面
    H  邊界：apartment1（前緣字母不誤命中）
    """

    # ---- 共用 helper ----

    def _ext_config(self, tmp_path=None, ext_mode='jellyfin', max_len=60,
                    suffix_keywords=None, filename_format=None, create_nfo=True):
        cfg = {
            'create_folder': False,
            'filename_format': filename_format or '[{num}] {title}{suffix}',
            'download_cover': True,
            'cover_filename': 'poster.jpg',
            'create_nfo': create_nfo,
            'max_title_length': 50,
            'max_filename_length': max_len,
            'suffix_keywords': suffix_keywords if suffix_keywords is not None
                               else ['-cd1', '-cd2', '-4k', '-uc'],
            'external_manager': ext_mode,
        }
        return cfg

    def _base_metadata(self, number='MIRD-151', title='Test Title', cover='http://fake/cover.jpg'):
        return {
            'number': number,
            'title': title,
            'actors': [],
            'tags': [],
            'maker': 'Studio',
            'date': '2024-01-15',
            'cover': cover,
            'url': '',
        }

    # ---- A: cd1 外部模式 → 正常 NFO、part_tail 在末 ----

    def test_cd1_external_nfo_written_and_part_tail(self, tmp_path):
        """A：外部模式 cd1 → NFO 產出（nfo_path not None），stem 以 -cd1 結尾"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'cd1 content')

        config = self._ext_config()
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result.get('nfo_path') is not None, 'cd1 應產 NFO（nfo_path not None）'
        assert not result.get('skipped_nfo_multipart'), 'cd1 不應設 skipped_nfo_multipart'

        stem = Path(result['new_filename']).stem
        import re
        assert re.search(r'-cd1$', stem), f'stem 應以 -cd1 結尾，實際：{stem!r}'

        # NFO sidecar stem 也應帶 -cd1
        nfo_stem = Path(result['nfo_path']).stem
        assert re.search(r'-cd1$', nfo_stem), f'NFO stem 應以 -cd1 結尾，實際：{nfo_stem!r}'

    # ---- B: cd2 外部模式 → 跳 NFO、保留封面/poster/fanart ----

    def test_cd2_external_skip_nfo_keep_cover(self, tmp_path):
        """B：外部模式 cd2 → nfo_path None、skipped_nfo_multipart True、success True、封面保留"""
        src = tmp_path / 'MIRD-151-cd2.mp4'
        src.write_bytes(b'cd2 content')

        config = self._ext_config()
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result['nfo_path'] is None, 'cd2 外部模式應跳過 NFO（nfo_path None）'
        assert result.get('skipped_nfo_multipart') is True, '應設 skipped_nfo_multipart=True'

        # 封面/poster/fanart 照常
        assert result.get('cover_path') is not None, 'cd2 應保留 cover'
        assert result.get('fanart_path') is not None, 'cd2 應保留 fanart'
        assert result.get('poster_path') is not None, 'cd2 應保留 poster'

        # 目標目錄下無 .nfo 檔
        stem = Path(result['new_filename']).stem
        nfo_candidate = tmp_path / (stem + '.nfo')
        assert not nfo_candidate.exists(), f'.nfo 不應存在：{nfo_candidate}'

        # stem 以 -cd2 結尾
        import re
        assert re.search(r'-cd2$', stem), f'stem 應以 -cd2 結尾，實際：{stem!r}'

    # ---- C: 長標題 + cd1 → 不超 max_filename_length 且 part token 不被截 ----

    def test_long_title_cd1_budget_preserved(self, tmp_path):
        """C：超長 title + cd1 + max=40 → 長度 <= 40、stem 仍以 -cd1 結尾"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'long title cd1')

        config = self._ext_config(max_len=40)
        metadata = self._base_metadata(title='超級無敵長的標題名稱會被截斷但part_token應完整保留不被切掉')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result['new_filename']).name
        assert len(new_name) <= 40, f'檔名長度 {len(new_name)} 超過 max=40：{new_name!r}'

        stem = Path(result['new_filename']).stem
        import re
        assert re.search(r'-cd1$', stem), f'stem 應以 -cd1 結尾（token 不被截），實際：{stem!r}'

    def test_degenerate_max_len_cd1_no_crash(self, tmp_path):
        """C 退化：max_filename_length 極小（6）→ 不 crash、長度不超 max"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'degenerate')

        config = self._ext_config(max_len=6)
        metadata = self._base_metadata(title='Title')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result['new_filename']).name
        assert len(new_name) <= 6, f'檔名長度 {len(new_name)} 超過 max=6：{new_name!r}'

    # ---- D: 防 {suffix} 雙寫 ----

    def test_no_double_cd1_suffix_and_part_tail(self, tmp_path):
        """D：預設 config（suffix_keywords 含 -cd1）+ 外部模式 + cd1 → -cd1 恰一次，無 -cd1-cd1"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'no double')

        # 預設 config：suffix_keywords 含 -cd1，filename_format 含 {suffix}
        config = self._ext_config(suffix_keywords=['-cd1', '-cd2', '-4k', '-uc'])
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result['new_filename']).name
        assert '-cd1-cd1' not in new_name, f'出現雙寫 -cd1-cd1：{new_name!r}'
        assert new_name.count('-cd1') == 1, f'-cd1 應恰出現一次，實際：{new_name!r}'

    def test_version_token_kept_part_tail_not_doubled(self, tmp_path):
        """D 加碼：-4k-cd1 檔 + suffix_keywords 含 -4k/-cd1 → stem 含 -4k（version），-cd1 恰一次"""
        src = tmp_path / 'MIRD-151-4k-cd1.mp4'
        src.write_bytes(b'4k cd1')

        config = self._ext_config(suffix_keywords=['-cd1', '-cd2', '-4k', '-uc'])
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        new_name = Path(result['new_filename']).name
        assert '-4k' in new_name, f'version token -4k 應保留：{new_name!r}'
        assert '-cd1-cd1' not in new_name, f'-cd1 不應雙寫：{new_name!r}'
        assert new_name.count('-cd1') == 1, f'-cd1 應恰一次：{new_name!r}'

    def test_config_suffix_keywords_not_mutated(self, tmp_path):
        """D 不 mutate：organize_file 呼叫後 config['suffix_keywords'] 原樣"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'no mutate')

        config = self._ext_config(suffix_keywords=['-cd1', '-cd2', '-4k'])
        original_kws = list(config['suffix_keywords'])  # 拷貝備用
        metadata = self._base_metadata(cover='')

        organize_file(str(src), metadata, config)

        assert config['suffix_keywords'] == original_kws, (
            f'config["suffix_keywords"] 被 mutate，原：{original_kws!r}，後：{config["suffix_keywords"]!r}'
        )

    # ---- E: off 模式 byte-identical ----

    def test_off_mode_cd1_nfo_written_via_suffix(self, tmp_path):
        """E：off 模式 cd1 → NFO 照產（-cd1 經 {suffix} 路徑，不跳）"""
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'off cd1')

        # off 模式（或 key 不存在）= _make_config 的預設
        config = _make_config(tmp_path)  # no external_manager key → off
        config['create_nfo'] = True
        metadata = _make_metadata(number='MIRD-151')

        result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result.get('nfo_path') is not None, 'off 模式 cd1 應產 NFO'
        assert not result.get('skipped_nfo_multipart'), 'off 模式不應設 skipped_nfo_multipart'
        # -cd1 經 {suffix} 路徑進檔名
        assert '-cd1' in Path(result['new_filename']).name

    def test_off_mode_cd2_nfo_written_no_skip(self, tmp_path):
        """E：off 模式 cd2 → NFO 照產（不跳），無 skipped_nfo_multipart flag"""
        src = tmp_path / 'MIRD-151-cd2.mp4'
        src.write_bytes(b'off cd2')

        config = _make_config(tmp_path)
        config['create_nfo'] = True
        metadata = _make_metadata(number='MIRD-151')

        result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result.get('nfo_path') is not None, 'off 模式 cd2 應照產 NFO（不跳）'
        assert 'skipped_nfo_multipart' not in result, 'off 模式不應設 skipped_nfo_multipart key'
        assert '-cd2' in Path(result['new_filename']).name

    # ---- F: VR + cd1 → 順序 {base}{vr_tail}-cd1 ----

    def test_vr_and_cd1_order(self, tmp_path):
        """F：VR cluster + cd1 → stem 形如 ...{vr_tail}-cd1，-cd1 最末"""
        # ABC-123_180_LR-cd1.mp4 → vr_tail=_180_LR，part_tail=-cd1
        src = tmp_path / 'ABC-123_180_LR-cd1.mp4'
        src.write_bytes(b'vr cd1')

        config = self._ext_config(suffix_keywords=['-cd1', '-4k'])
        metadata = self._base_metadata(number='ABC-123')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        stem = Path(result['new_filename']).stem
        import re
        # -cd1 在最末
        assert re.search(r'-cd1$', stem), f'stem 應以 -cd1 結尾，實際：{stem!r}'
        # vr_tail 在 -cd1 之前
        assert '_180_LR' in stem, f'stem 應含 _180_LR（vr_tail），實際：{stem!r}'
        idx_vr = stem.index('_180_LR')
        idx_cd = stem.index('-cd1')
        assert idx_vr < idx_cd, f'vr_tail 應在 -cd1 之前，實際：{stem!r}'

    # ---- G: kodi cd2 → 保留封面 ----

    def test_kodi_cd2_keep_cover(self, tmp_path):
        """G：kodi 模式 cd2 + create_folder=False → 跳 NFO + stem 命名 poster/fanart（72c 修正後）"""
        src = tmp_path / 'MIRD-151-cd2.mp4'
        src.write_bytes(b'kodi cd2')

        config = self._ext_config(ext_mode='kodi')  # create_folder=False → stem 命名
        metadata = self._base_metadata()

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result['nfo_path'] is None, 'kodi cd2 應跳 NFO'
        assert result.get('skipped_nfo_multipart') is True
        # kodi 固定 stem 命名（collision-free）
        assert result.get('poster_path') is not None, 'kodi cd2 應保留 poster'
        assert result.get('fanart_path') is not None, 'kodi cd2 應保留 fanart'
        poster_name = Path(result['poster_path']).name
        fanart_name = Path(result['fanart_path']).name
        assert poster_name.endswith('-poster.jpg'), f'kodi+flat poster 應帶 stem，實際：{poster_name!r}'
        assert fanart_name.endswith('-fanart.jpg'), f'kodi+flat fanart 應帶 stem，實際：{fanart_name!r}'

    # ---- H: 邊界 negative — apartment1 不誤命中 ----

    def test_apartment1_not_multipart(self, tmp_path):
        """H：apartment1.mp4 — part1 前緣為字母 → part_match None → 正常產 NFO、無 part_tail"""
        src = tmp_path / 'apartment1.mp4'
        src.write_bytes(b'apartment')

        config = self._ext_config(suffix_keywords=[])
        metadata = self._base_metadata(number='FAKE-001')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        assert result.get('nfo_path') is not None, 'apartment1 不應觸發 skip_nfo'
        assert not result.get('skipped_nfo_multipart'), 'apartment1 不應設 skipped_nfo_multipart'
        # 檔名不應帶任何 part_tail
        stem = Path(result['new_filename']).stem
        assert not stem.endswith('-cd1'), f'apartment1 不應接 -cd1 part_tail：{stem!r}'

    # ---- I: P1-A 修正 — extracted_title 殘留多段 token 不雙寫（Codex P1-A）----

    def test_chinese_title_part2_hd_no_dup_token(self, tmp_path):
        """I-1：中文標題含 -part2[HD] 的 part2 檔案（jellyfin 模式）→
        輸出 stem 中 part2 token 恰一次，且嚴格落在 stem 最末（無 ...-part2[HD]-part2 雙寫）。
        涵蓋 POC Q2 典型輸入形狀：bracket 包裝版本標記殘留在 extracted_title。
        """
        import re
        # part2 檔：[ABC-123]某中文標題-part2[HD].mp4
        src = tmp_path / '[ABC-123]某中文標題-part2[HD].mp4'
        src.write_bytes(b'part2 hd content')

        config = self._ext_config(
            suffix_keywords=['-cd1', '-cd2', '-part1', '-part2', '-4k'],
            filename_format='[{num}] {title}{suffix}',
        )
        metadata = self._base_metadata(number='ABC-123', title='Some Japanese Title')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        stem = Path(result['new_filename']).stem

        # part2 token 恰好出現一次（無雙寫）
        assert stem.count('part2') == 1, (
            f'part2 token 應恰好出現一次，實際：{stem!r}'
        )
        # part2 token 嚴格在 stem 末尾（Jellyfin stacking 要求）
        assert re.search(r'-part2$', stem), (
            f'stem 應以 -part2 結尾，實際：{stem!r}'
        )

    def test_chinese_title_part1_no_dup_token(self, tmp_path):
        """I-2：part1 版本同類型驗證 → part1 恰一次且在 stem 末。"""
        import re
        src = tmp_path / '[ABC-123]某中文標題-part1.mp4'
        src.write_bytes(b'part1 content')

        config = self._ext_config(
            suffix_keywords=['-cd1', '-cd2', '-part1', '-part2', '-4k'],
            filename_format='[{num}] {title}{suffix}',
        )
        metadata = self._base_metadata(number='ABC-123', title='Some Japanese Title')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        stem = Path(result['new_filename']).stem

        assert stem.count('part1') == 1, (
            f'part1 token 應恰好出現一次，實際：{stem!r}'
        )
        assert re.search(r'-part1$', stem), (
            f'stem 應以 -part1 結尾，實際：{stem!r}'
        )

    def test_clean_title_cd1_no_op(self, tmp_path):
        """I-3：乾淨番號（scraped 非多段標題）+ 外部模式 cd1 → 輸出與修前 byte-identical
        （_strip_part_token no-op：title 內無多段 token → 組裝後 filename_base 無 token 可剝）。
        """
        import re
        src = tmp_path / 'MIRD-151-cd1.mp4'
        src.write_bytes(b'clean cd1')

        config = self._ext_config(suffix_keywords=['-cd1', '-cd2', '-4k', '-uc'])
        # 使用非多段 scraped 標題
        metadata = self._base_metadata(number='MIRD-151', title='Test Title')

        with patch('core.organizer.download_image', side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result['success'] is True, f"organize 失敗: {result.get('error')}"
        stem = Path(result['new_filename']).stem

        # -cd1 恰好一次（不被雙剝或漏寫）
        assert stem.count('cd1') == 1, (
            f'cd1 token 應恰好一次（no-op），實際：{stem!r}'
        )
        # 嚴格在末尾
        assert re.search(r'-cd1$', stem), (
            f'stem 應以 -cd1 結尾，實際：{stem!r}'
        )


# ══════════════════════════════════════════════════════════════════════════════
# 72c-simplify：kodi == jellyfin (emby)（stem 長格式，無 per-folder 切換）
# ══════════════════════════════════════════════════════════════════════════════


class TestKodiStemNamingOrganize:
    """kodi 模式固定使用 stem 長格式，與 jellyfin/emby 行為完全相同"""

    def _make_kodi_config(self, create_folder: bool, folder_layers=None) -> dict:
        cfg = {
            "create_folder": create_folder,
            "filename_format": "[{num}] {title}",
            "download_cover": True,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
            "external_manager": "kodi",
        }
        if folder_layers is not None:
            cfg["folder_layers"] = folder_layers
        return cfg

    def _make_kodi_metadata(self, number: str = "SONE-205", actors=None) -> dict:
        return {
            "number": number,
            "title": "Test Title",
            "actors": actors or [],
            "tags": [],
            "maker": "S1",
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }

    def test_O1_kodi_create_folder_false_stem_named(self, tmp_path):
        """O1：kodi + create_folder=False → stem 命名，NFO <poster> 對得上 stem。"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_kodi_config(create_folder=False)
        metadata = self._make_kodi_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        fanart = Path(result["fanart_path"])
        poster = Path(result["poster_path"])

        assert fanart.name.endswith("-fanart.jpg"), f"kodi+flat fanart 應帶 stem，實際: {fanart.name}"
        assert poster.name.endswith("-poster.jpg"), f"kodi+flat poster 應帶 stem，實際: {poster.name}"
        assert fanart.exists()
        assert poster.exists()

        # 裸短名不存在
        assert not (tmp_path / "poster.jpg").exists(), "不應存在裸 poster.jpg"
        assert not (tmp_path / "fanart.jpg").exists(), "不應存在裸 fanart.jpg"

        # NFO <poster> tag 與磁碟檔名一致
        assert result.get("nfo_path") is not None
        nfo = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert f"<poster>{poster.name}</poster>" in nfo, \
            f"NFO <poster> 應指向 {poster.name}"

    def test_O2_kodi_create_folder_true_actor_layer_stem_named(self, tmp_path):
        """O2：kodi + create_folder=True + folder_layers=['{actor}'] → 仍使用 stem 命名（不再短名）。"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = self._make_kodi_config(create_folder=True, folder_layers=["{actor}"])
        metadata = self._make_kodi_metadata(actors=["三上悠亞"])

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        fanart = Path(result["fanart_path"])
        poster = Path(result["poster_path"])

        assert fanart.name.endswith("-fanart.jpg"), f"kodi+actor fanart 應帶 stem，實際: {fanart.name}"
        assert poster.name.endswith("-poster.jpg"), f"kodi+actor poster 應帶 stem，實際: {poster.name}"

        # 裸短名不存在
        actor_dir = Path(result["new_folder"])
        assert not (actor_dir / "poster.jpg").exists(), "actor 資料夾不應有裸 poster.jpg"
        assert not (actor_dir / "fanart.jpg").exists(), "actor 資料夾不應有裸 fanart.jpg"

        # NFO tag 一致
        assert result.get("nfo_path") is not None
        nfo = Path(result["nfo_path"]).read_text(encoding="utf-8")
        assert f"<poster>{poster.name}</poster>" in nfo

    def test_kodi_equals_jellyfin_same_filenames(self, tmp_path):
        """kodi 輸出 == jellyfin 輸出（相同 stem 命名 + 相同 NFO poster/fanart tag）。"""
        src_k = tmp_path / "SONE-205.mp4"
        src_j = tmp_path / "SONE-205B.mp4"
        src_k.write_bytes(b"kodi")
        src_j.write_bytes(b"jf")

        cfg_k = self._make_kodi_config(create_folder=False)
        cfg_j = _make_ext_config("jellyfin")
        meta_k = self._make_kodi_metadata("SONE-205")
        meta_j = _make_ext_metadata("SONE-205B")

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            res_k = organize_file(str(src_k), meta_k, cfg_k)
            res_j = organize_file(str(src_j), meta_j, cfg_j)

        assert res_k["success"] and res_j["success"]
        # 兩者都產 stem-poster.jpg 和 stem-fanart.jpg（不同 stem 但格式相同）
        assert Path(res_k["fanart_path"]).name.endswith("-fanart.jpg")
        assert Path(res_k["poster_path"]).name.endswith("-poster.jpg")
        assert Path(res_j["fanart_path"]).name.endswith("-fanart.jpg")
        assert Path(res_j["poster_path"]).name.endswith("-poster.jpg")

        # NFO tag 格式相同（各自 basename）
        nfo_k = Path(res_k["nfo_path"]).read_text(encoding="utf-8")
        nfo_j = Path(res_j["nfo_path"]).read_text(encoding="utf-8")
        assert "-poster.jpg</poster>" in nfo_k
        assert "-fanart.jpg</fanart>" in nfo_k
        assert "-poster.jpg</poster>" in nfo_j
        assert "-fanart.jpg</fanart>" in nfo_j

    def test_kodi_multi_video_no_collision(self, tmp_path):
        """kodi + 同資料夾兩部片 → 各自 stem 命名，無碰撞。"""
        src1 = tmp_path / "SONE-205.mp4"
        src2 = tmp_path / "MIDE-001.mp4"
        src1.write_bytes(b"a")
        src2.write_bytes(b"b")

        cfg = self._make_kodi_config(create_folder=False)

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            r1 = organize_file(str(src1), self._make_kodi_metadata("SONE-205"), cfg)
            r2 = organize_file(str(src2), self._make_kodi_metadata("MIDE-001"), cfg)

        assert r1["success"] and r2["success"]
        assert r1.get("poster_path") is not None, "r1 應產 poster_path"
        assert r2.get("poster_path") is not None, "r2 應產 poster_path"
        # 各有獨立 stem 命名（不同路徑）
        assert r1["poster_path"] != r2["poster_path"], "兩片 poster 路徑不應相同"
        assert Path(r1["poster_path"]).name.endswith("-poster.jpg"), "r1 poster 應帶 stem"
        assert Path(r2["poster_path"]).name.endswith("-poster.jpg"), "r2 poster 應帶 stem"
        # 裸短名不存在
        assert not (tmp_path / "poster.jpg").exists(), "不應有共用裸 poster.jpg"

    def test_O3_jellyfin_unchanged(self, tmp_path):
        """O3：jellyfin + create_folder=False → stem 命名不變（回歸）。"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("jellyfin", create_folder=False)
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True
        assert Path(result["fanart_path"]).name.endswith("-fanart.jpg")
        assert Path(result["poster_path"]).name.endswith("-poster.jpg")

    def test_O3_off_unchanged(self, tmp_path):
        """O3 off：off + create_folder=False → 無 poster/fanart（回歸）。"""
        src = tmp_path / "SONE-205.mp4"
        src.write_bytes(b"fake mp4")

        config = _make_ext_config("off", create_folder=False)
        metadata = _make_ext_metadata()

        with patch("core.organizer.download_image", side_effect=_mock_download_image_write_jpeg):
            result = organize_file(str(src), metadata, config)

        assert result["success"] is True
        assert result.get("fanart_path") is None
        assert result.get("poster_path") is None


# ============ 站1接線測試 (TASK-101a-T2 DoD①④) ============


def _t2_oracle_poster_bytes(fixture_path, focal_xy=MOCK_FOCAL_XY):
    """獨立 oracle：不經過 crop_to_poster / 任何一站的呼叫鏈，直接以「只平移既有窗」
    契約（整數 crop_w + focal 平移 x0）算出「應該要平移到焦點」的期望 bytes。不可用
    「同一站流程呼叫兩次自我比對」——對「呼叫端忘了傳 number/maker」這類 mutation
    結構性瞎眼（gotchas-backend.md #9，101a-T1 已踩過）。

    TASK-102c-T1：改吃 focal_xy 參數（預設 MOCK_FOCAL_XY），不再自己呼叫真
    detect_focal——呼叫端須確保 patch `core.organizer.detect_focal` 用同一個值，
    否則 production 端與 oracle 端會對不上。
    """
    with Image.open(fixture_path) as img:
        w, h = img.size
    r_window = _poster_window_ratio(w, h)
    assert r_window is not None
    focal = focal_xy
    with Image.open(fixture_path) as img:
        # 101a P2-1（Codex PR#110）：oracle 改為「只平移既有窗」的真實契約（見 crop_to_poster）——
        # 不再經 crop_image_position 的 float ratio→px round-trip（±1px 改窗寬、已棄用）。
        crop_w = int(h / 1.5) if (h / w) >= 1.0 else (w - int(w / 1.9))
        x0 = max(min(int(w * focal[0]) - crop_w // 2, w - crop_w), 0)
        expected_cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
    buf = io.BytesIO()
    expected_cropped.save(buf, "JPEG", quality=95, subsampling=0)
    return buf.getvalue()


class TestOrganizeFileStationWiring:
    """DoD①：站1（core/organizer.py organize_file）接線——真跑 organize_file()，
    fixture A（番號驅動）+ fixture B（maker-only 驅動）各一次，poster 依焦點裁，
    斷言輸出 bytes 等於獨立 oracle（不可自我比對）。

    DoD④ 的站1 number/maker 軸 mutation 皆對這兩個測試單獨驗證（見 TASK card）。
    """

    _FIXTURE_A = {"number": "FC2-1234567", "maker": "S1 NO.1 STYLE"}  # 番號驅動，maker 非白名單
    _FIXTURE_B = {"number": "SSIS-001", "maker": "10musume"}  # maker-only 驅動，白名單原樣照抄

    @staticmethod
    def _mock_download_fixture_face(url, save_path, referer=''):
        src = _FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg"
        Path(save_path).write_bytes(src.read_bytes())
        return True

    def _run_station1(self, tmp_path, tag, fixture):
        src = tmp_path / f"{fixture['number']}_{tag}.mp4"
        src.write_bytes(b"fake mp4")
        config = _make_jellyfin_config(jellyfin_mode=True)
        metadata = {
            "number": fixture["number"],
            "title": "Test Title",
            "actors": [],
            "tags": [],
            "maker": fixture["maker"],
            "date": "2024-01-15",
            "cover": "http://fake/cover.jpg",
            "url": "",
        }
        with patch("core.organizer.download_image", side_effect=self._mock_download_fixture_face), \
             patch("core.organizer.detect_focal", return_value=MOCK_FOCAL_XY):
            result = organize_file(str(src), metadata, config)
        assert result["success"] is True, f"organize 失敗: {result.get('error')}"
        assert result.get("poster_path") is not None, "station1 應產生 poster_path"
        poster_bytes = Path(result["poster_path"]).read_bytes()
        expected = _t2_oracle_poster_bytes(_FOCAL_FIXTURES_DIR / "wide_offcenter_face.jpg", MOCK_FOCAL_XY)
        assert poster_bytes == expected, "station1 poster 應對準焦點（獨立 oracle 比對）"

    def test_station1_fixture_a(self, tmp_path):
        self._run_station1(tmp_path, "a", self._FIXTURE_A)

    def test_station1_fixture_b(self, tmp_path):
        self._run_station1(tmp_path, "b", self._FIXTURE_B)
