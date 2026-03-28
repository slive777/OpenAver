"""
test_maker_mapping.py - core/maker_mapping.py 單元測試

測試範圍：
- load_name_mapping(): 新格式/舊格式/不存在/損毀
- load_prefix_mapping(): 新格式/舊格式/不存在/損毀，不含 _meta 等 key
- normalize_maker_name(): 查表命中/無對照/空字串/None
- save_prefix_entry(): 寫入後 reload 含新值，name 層未被污染，IOError 靜默
- get_maker_by_prefix(): prefix hit 不呼叫 JavDB，無字母前綴回傳空字串
- Video.to_legacy_dict(): maker 欄位套用 normalize_maker_name()
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ============ Fixtures ============

NEW_FORMAT_JSON = {
    "_meta": {"format": "hybrid", "updated": "2026-03-28"},
    "name_mapping": {
        "エスワン ナンバーワンスタイル": "S1",
        "S1 NO.1 STYLE": "S1",
        "ムーディーズ": "Moodyz",
        "MOODYZ": "Moodyz",
    },
    "prefix_mapping": {
        "MIAA": "Moodyz",
        "SNIS": "S1",
        "ABF": "Prestige",
    },
}

OLD_FORMAT_JSON = {
    "MIAA": "Moodyz",
    "SNIS": "S1",
    "ABF": "Prestige",
}


@pytest.fixture
def new_format_file(tmp_path):
    """新格式 maker_mapping.json"""
    p = tmp_path / "maker_mapping.json"
    p.write_text(json.dumps(NEW_FORMAT_JSON, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def old_format_file(tmp_path):
    """舊格式 maker_mapping.json（純平坦 dict）"""
    p = tmp_path / "maker_mapping.json"
    p.write_text(json.dumps(OLD_FORMAT_JSON, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def nonexistent_file(tmp_path):
    """不存在的路徑"""
    return tmp_path / "no_such_file.json"


@pytest.fixture
def corrupted_file(tmp_path):
    """損毀的 JSON 檔"""
    p = tmp_path / "maker_mapping.json"
    p.write_text("{invalid json", encoding="utf-8")
    return p


# ============ load_name_mapping ============

class TestLoadNameMapping:
    def test_new_format_returns_name_mapping(self, new_format_file, monkeypatch):
        """新格式：load_name_mapping() 回傳 name_mapping 層的正確 dict（含片假名 key）"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_name_mapping()
        assert result["エスワン ナンバーワンスタイル"] == "S1"
        assert result["ムーディーズ"] == "Moodyz"

    def test_new_format_no_meta_key(self, new_format_file, monkeypatch):
        """新格式：load_name_mapping() 不含 _meta key"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_name_mapping()
        assert "_meta" not in result

    def test_old_format_returns_empty(self, old_format_file, monkeypatch):
        """舊格式（純平坦）：load_name_mapping() 回傳空 dict"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", old_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_name_mapping()
        assert result == {}

    def test_file_not_found_returns_empty(self, nonexistent_file, monkeypatch):
        """檔案不存在：load_name_mapping() 回傳空 dict"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", nonexistent_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_name_mapping()
        assert result == {}

    def test_corrupted_json_returns_empty(self, corrupted_file, monkeypatch):
        """JSON 損毀：load_name_mapping() 回傳空 dict"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", corrupted_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_name_mapping()
        assert result == {}


# ============ load_prefix_mapping ============

class TestLoadPrefixMapping:
    def test_new_format_returns_prefix_mapping(self, new_format_file, monkeypatch):
        """新格式：load_prefix_mapping() 回傳 prefix_mapping 層（含前綴 key）"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert result["MIAA"] == "Moodyz"
        assert result["SNIS"] == "S1"
        assert result["ABF"] == "Prestige"

    def test_new_format_no_meta_key(self, new_format_file, monkeypatch):
        """新格式：load_prefix_mapping() 不含 _meta key"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert "_meta" not in result

    def test_new_format_no_layer_keys(self, new_format_file, monkeypatch):
        """新格式：load_prefix_mapping() 不含 name_mapping / prefix_mapping 這些 key"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert "name_mapping" not in result
        assert "prefix_mapping" not in result

    def test_old_format_returns_whole_dict(self, old_format_file, monkeypatch):
        """舊格式（純平坦）：load_prefix_mapping() 回傳整個 dict（向下相容）"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", old_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert result["MIAA"] == "Moodyz"
        assert result["ABF"] == "Prestige"

    def test_file_not_found_returns_empty(self, nonexistent_file, monkeypatch):
        """檔案不存在：load_prefix_mapping() 回傳空 dict"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", nonexistent_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert result == {}

    def test_corrupted_json_returns_empty(self, corrupted_file, monkeypatch):
        """JSON 損毀：load_prefix_mapping() 回傳空 dict"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", corrupted_file)
        monkeypatch.setattr(mm, "_cache", None)
        result = mm.load_prefix_mapping()
        assert result == {}


# ============ normalize_maker_name ============

class TestNormalizeMakerName:
    def test_known_katakana_name(self, new_format_file, monkeypatch):
        """片假名 key 命中 → 回傳 canonical 短名"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.normalize_maker_name("エスワン ナンバーワンスタイル") == "S1"

    def test_known_en_name(self, new_format_file, monkeypatch):
        """英文長名命中 → 回傳 canonical 短名"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.normalize_maker_name("S1 NO.1 STYLE") == "S1"

    def test_unknown_maker_returns_original(self, new_format_file, monkeypatch):
        """無對照 → 回傳原值"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.normalize_maker_name("未知片商") == "未知片商"

    def test_empty_string_returns_empty(self, new_format_file, monkeypatch):
        """空字串 → 回傳空字串"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.normalize_maker_name("") == ""

    def test_none_returns_empty(self, new_format_file, monkeypatch):
        """None 輸入 → 回傳空字串（防禦）"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.normalize_maker_name(None) == ""


# ============ save_prefix_entry ============

class TestSavePrefixEntry:
    def test_save_then_reload_contains_new_entry(self, new_format_file, monkeypatch):
        """save_prefix_entry 後 load_prefix_mapping() 應含新 entry"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        mm.save_prefix_entry("TESTX", "TestCo")
        result = mm.load_prefix_mapping()
        assert result.get("TESTX") == "TestCo"

    def test_save_does_not_pollute_name_mapping(self, new_format_file, monkeypatch):
        """save_prefix_entry 後 load_name_mapping() 不含新 prefix key"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        mm.save_prefix_entry("TESTX", "TestCo")
        name_map = mm.load_name_mapping()
        assert "TESTX" not in name_map

    def test_save_preserves_existing_entries(self, new_format_file, monkeypatch):
        """save_prefix_entry 後既有 prefix entry 仍存在"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        mm.save_prefix_entry("NEWPFX", "NewMaker")
        result = mm.load_prefix_mapping()
        assert result.get("MIAA") == "Moodyz"
        assert result.get("NEWPFX") == "NewMaker"

    def test_save_ioerror_is_silent(self, tmp_path, monkeypatch):
        """save_prefix_entry 寫檔失敗 → 靜默，不拋出 exception"""
        import core.maker_mapping as mm
        # 指向不可寫入的路徑（目錄，非檔案）
        bad_path = tmp_path / "not_a_file"
        bad_path.mkdir()
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", bad_path)
        monkeypatch.setattr(mm, "_cache", None)
        # 不應拋出任何 exception
        mm.save_prefix_entry("XYZ", "SomeMaker")

    def test_save_cache_invalidated(self, new_format_file, monkeypatch):
        """save_prefix_entry 後 _cache 被失效，下次 load 重讀"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        # 先 load 以填充 cache
        mm.load_prefix_mapping()
        assert mm._cache is not None
        mm.save_prefix_entry("ZZTEST", "ZZMaker")
        # cache 應被重置
        assert mm._cache is None


# ============ get_maker_by_prefix ============

class TestGetMakerByPrefix:
    def test_prefix_hit_returns_maker_no_javdb(self, new_format_file, monkeypatch):
        """prefix 在 prefix_mapping 中存在 → 直接回傳，不呼叫 JavDB"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)

        mock_javdb = MagicMock()
        with patch("core.scrapers.JavDBScraper", mock_javdb):
            result = mm.get_maker_by_prefix("MIAA-123")

        assert result == "Moodyz"
        mock_javdb.assert_not_called()

    def test_no_alpha_prefix_returns_empty(self, new_format_file, monkeypatch):
        """純數字番號 → 回傳空字串"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.get_maker_by_prefix("123") == ""

    def test_empty_string_returns_empty(self, new_format_file, monkeypatch):
        """空字串 → 回傳空字串"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)
        assert mm.get_maker_by_prefix("") == ""

    def test_prefix_miss_calls_javdb_fallback(self, new_format_file, monkeypatch):
        """prefix miss → 呼叫 JavDB fallback，找到後回傳並儲存"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)

        mock_video = MagicMock()
        mock_video.maker = "NewMakerFromJavDB"

        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = mock_video

        mock_javdb_cls = MagicMock(return_value=mock_scraper_instance)

        with patch("core.scrapers.JavDBScraper", mock_javdb_cls):
            result = mm.get_maker_by_prefix("ZZUNKNOWN-001")

        assert result == "NewMakerFromJavDB"

    def test_prefix_miss_javdb_no_result_returns_empty(self, new_format_file, monkeypatch):
        """prefix miss + JavDB 無結果 → 回傳空字串"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)

        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = None

        mock_javdb_cls = MagicMock(return_value=mock_scraper_instance)

        with patch("core.scrapers.JavDBScraper", mock_javdb_cls):
            result = mm.get_maker_by_prefix("ZZUNKNOWN-001")

        assert result == ""

    def test_javdb_fallback_saves_normalized_name(self, new_format_file, monkeypatch):
        """JavDB fallback 寫入 prefix_mapping 的值必須經過 normalize_maker_name()

        模擬 JavDB 回傳片假名長名（如 "エスワン ナンバーワンスタイル"），
        name_mapping 有對應的 canonical 短名（如 "S1"）。
        驗證 save_prefix_entry 存入的是 canonical 短名，
        且 get_maker_by_prefix 回傳 canonical 短名。
        """
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "MAKER_MAPPING_FILE", new_format_file)
        monkeypatch.setattr(mm, "_cache", None)

        # new_format_file 的 name_mapping 中 "エスワン ナンバーワンスタイル" → "S1"
        mock_video = MagicMock()
        mock_video.maker = "エスワン ナンバーワンスタイル"  # 片假名長名（JavDB 原始值）

        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = mock_video

        mock_javdb_cls = MagicMock(return_value=mock_scraper_instance)

        with patch("core.scrapers.JavDBScraper", mock_javdb_cls):
            result = mm.get_maker_by_prefix("SONE-001")

        # 回傳值應是 canonical 短名，而非片假名長名
        assert result == "S1"

        # 重新載入 prefix_mapping，確認寫入的也是 canonical 短名
        mm._cache = None
        prefix_map = mm.load_prefix_mapping()
        assert prefix_map.get("SONE") == "S1", (
            "save_prefix_entry 應存 canonical 短名 'S1'，"
            f"實際存了 '{prefix_map.get('SONE')}'"
        )


# ============ Video.to_legacy_dict() maker normalize ============

class TestVideoToLegacyDictMaker:
    """Video.to_legacy_dict() 的 maker 欄位應套用 normalize_maker_name()"""

    # name_mapping 供 mock 使用
    MOCK_NAME_MAPPING = {
        "エスワン ナンバーワンスタイル": "S1",
        "S1 NO.1 STYLE": "S1",
        "ムーディーズ": "Moodyz",
    }

    @pytest.fixture(autouse=True)
    def patch_name_mapping(self, monkeypatch):
        """mock load_name_mapping 回傳固定 dict，不讀真實檔案"""
        import core.maker_mapping as mm
        monkeypatch.setattr(mm, "_cache", None)
        monkeypatch.setattr(
            mm, "load_name_mapping",
            lambda: self.MOCK_NAME_MAPPING,
        )

    def _make_video(self, maker):
        from core.scrapers.models import Video
        return Video(number="SONE-001", maker=maker)

    def test_katakana_maker_is_normalized(self):
        """maker = 片假名長名 → to_legacy_dict()['maker'] 為 canonical 短名"""
        v = self._make_video("エスワン ナンバーワンスタイル")
        assert v.to_legacy_dict()["maker"] == "S1"

    def test_english_long_name_is_normalized(self):
        """maker = 英文長名 → to_legacy_dict()['maker'] 為 canonical 短名"""
        v = self._make_video("S1 NO.1 STYLE")
        assert v.to_legacy_dict()["maker"] == "S1"

    def test_unknown_maker_returns_original(self):
        """maker 無對照 → to_legacy_dict()['maker'] 保留原值"""
        v = self._make_video("本中")
        assert v.to_legacy_dict()["maker"] == "本中"

    def test_empty_maker_returns_empty(self):
        """maker = '' → to_legacy_dict()['maker'] 為 ''"""
        v = self._make_video("")
        assert v.to_legacy_dict()["maker"] == ""

    def test_none_maker_returns_empty(self):
        """maker = None → to_legacy_dict()['maker'] 為 ''（型別防禦）"""
        from core.scrapers.models import Video
        # Video.maker 有 default=""，需用 model_construct 繞過 validation
        v = Video.model_construct(number="SONE-001", maker=None,
                                  title="", actresses=[], date="",
                                  cover_url="", tags=[], source="",
                                  detail_url="", director="", duration=None,
                                  label="", series="", sample_images=[])
        assert v.to_legacy_dict()["maker"] == ""

    def test_already_canonical_maker_unchanged(self):
        """maker 已是 canonical（如 'S1'）→ 無對照時保留原值"""
        v = self._make_video("S1")
        assert v.to_legacy_dict()["maker"] == "S1"
