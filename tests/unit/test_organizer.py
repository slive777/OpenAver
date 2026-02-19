"""
T1e Tests — Fix-1 版本標記測試
測試 core/organizer.py 的 _detect_suffixes(), format_string(), organize_file()
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from core.organizer import _detect_suffixes, format_string, organize_file


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
