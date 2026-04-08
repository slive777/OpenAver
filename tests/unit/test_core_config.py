"""
tests/unit/test_core_config.py — core.config migration 邏輯 unit tests

直接測試 core.config.load_config 的各段 migration 邏輯，
以及 save_config / AppConfig 的基本行為。
"""

import json
import pytest
from pathlib import Path

import core.config as core_config
from core.config import AppConfig, load_config, save_config


# ============ helpers ============

def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False))


def _read_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ============ test_load_config_empty_file ============

class TestLoadConfigEmptyFile:
    """首次啟動：config.json 不存在，config.default.json 也不存在 → 返回 AppConfig 預設值"""

    def test_returns_default_when_no_files(self, tmp_path, monkeypatch):
        non_existent = tmp_path / "config.json"
        non_existent_default = tmp_path / "config.default.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", non_existent)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", non_existent_default)

        result = load_config()

        assert result == AppConfig().model_dump()
        assert not non_existent.exists(), "不應自動建立 config.json（無 default 可複製）"

    def test_copies_default_when_default_exists(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        default_data = {"general": {"theme": "dark"}}
        _write_config(default_path, default_data)

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_path)

        result = load_config()

        assert config_path.exists(), "應從 default 複製建立 config.json"
        assert result.get("general", {}).get("theme") == "dark"


# ============ test_migration_avlist_to_gallery ============

class TestMigrationAvlistToGallery:
    """avlist → gallery key rename"""

    def test_avlist_renamed_to_gallery(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"avlist": {"directories": ["/videos"]}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "gallery" in result
        assert "avlist" not in result
        assert result["gallery"]["directories"] == ["/videos"]

    def test_avlist_not_renamed_when_gallery_exists(self, tmp_path, monkeypatch):
        """若 gallery 已存在，不覆蓋"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "avlist": {"directories": ["/old"]},
            "gallery": {"directories": ["/new"]},
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["gallery"]["directories"] == ["/new"]
        assert "avlist" in result  # 保留未搬移的 avlist


# ============ test_migration_translate_flat_to_nested ============

class TestMigrationTranslateFlatToNested:
    """translate 扁平結構 → 嵌套結構"""

    def test_ollama_url_migrated_to_nested(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "enabled": True,
                "ollama_url": "http://192.168.1.100:11434",
                "ollama_model": "llama3:8b",
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        t = result["translate"]
        assert t["ollama"]["url"] == "http://192.168.1.100:11434"
        assert t["ollama"]["model"] == "llama3:8b"
        assert "ollama_url" not in t
        assert "ollama_model" not in t

    def test_deprecated_progressive_fields_removed(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "auto_progressive": True,
                "progressive_first": 5,
                "progressive_range": 10,
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        t = result["translate"]
        assert "auto_progressive" not in t
        assert "progressive_first" not in t
        assert "progressive_range" not in t

    def test_batch_model_removed_from_ollama(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "ollama": {
                    "url": "http://localhost:11434",
                    "model": "qwen3:8b",
                    "batch_model": "qwen3:14b",
                }
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "batch_model" not in result["translate"]["ollama"]

    def test_gemini_nested_added_when_missing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {"enabled": False, "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"}}
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "gemini" in result["translate"]
        assert result["translate"]["gemini"]["model"] == "gemini-flash-lite-latest"

    def test_batch_size_added_when_missing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {"enabled": False}
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["translate"]["batch_size"] == 10


# ============ test_migration_folder_format_to_folder_layers ============

class TestMigrationFolderFormatToFolderLayers:
    """folder_format → folder_layers"""

    def test_single_layer(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"folder_format": "{actor}"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["folder_layers"] == ["{actor}"]

    def test_multi_layer_slash(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"folder_format": "{actor}/{maker}"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["folder_layers"] == ["{actor}", "{maker}"]

    def test_multi_layer_backslash(self, tmp_path, monkeypatch):
        """Windows 風格反斜線路徑"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"folder_format": "{actor}\\{maker}"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["folder_layers"] == ["{actor}", "{maker}"]

    def test_not_overwrite_existing_folder_layers(self, tmp_path, monkeypatch):
        """folder_layers 已存在時不應覆蓋"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "scraper": {
                "folder_format": "{actor}",
                "folder_layers": ["{maker}", "{actor}"],
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["folder_layers"] == ["{maker}", "{actor}"]


# ============ test_migration_suffix_keywords ============

class TestMigrationSuffixKeywords:
    """suffix_keywords 補齊（Fix-1 版本標記）"""

    def test_suffix_keywords_added_when_missing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"create_folder": True}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["suffix_keywords"] == ["-cd1", "-cd2", "-4k", "-uc"]

    def test_suffix_keywords_not_overwrite_existing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"suffix_keywords": ["-4k"]}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["suffix_keywords"] == ["-4k"]


# ============ test_migration_min_size_kb_to_mb ============

class TestMigrationMinSizeKbToMb:
    """min_size_kb → min_size_mb (KB 轉 MB)"""

    def test_kb_converted_to_mb(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"gallery": {"min_size_kb": 2048}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["gallery"]["min_size_mb"] == 2
        assert "min_size_kb" not in result["gallery"]

    def test_zero_kb_converts_to_zero_mb(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"gallery": {"min_size_kb": 0}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["gallery"]["min_size_mb"] == 0


# ============ test_migration_jellyfin_mode ============

class TestMigrationJellyfinMode:
    """jellyfin_mode 補齊（Fix-6）"""

    def test_jellyfin_mode_added_when_missing(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"create_folder": True}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["jellyfin_mode"] is False


# ============ test_migration_download_sample_images ============

class TestMigrationDownloadSampleImages:
    """download_sample_images 補齊（Task 38e）"""

    def test_download_sample_images_added_when_missing(self, tmp_path, monkeypatch):
        """舊 config 沒有 download_sample_images → migration 自動補 False"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"create_folder": True, "jellyfin_mode": False}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "download_sample_images" in result["scraper"]
        assert result["scraper"]["download_sample_images"] is False

    def test_download_sample_images_not_overwrite_existing(self, tmp_path, monkeypatch):
        """已存在的 download_sample_images=True 不被覆蓋"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"download_sample_images": True}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["download_sample_images"] is True


# ============ test_save_config_roundtrip ============

class TestSaveConfigRoundtrip:
    """save_config / load_config round-trip"""

    def test_roundtrip_preserves_data(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        original = AppConfig().model_dump()
        original["general"]["theme"] = "dark"
        original["gallery"]["min_size_mb"] = 5

        save_config(original)
        reloaded = load_config()

        assert reloaded["general"]["theme"] == "dark"
        assert reloaded["gallery"]["min_size_mb"] == 5

    def test_save_uses_utf8_encoding(self, tmp_path, monkeypatch):
        """確保 JSON 儲存為 UTF-8，非 ASCII 字元不轉義"""
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)

        save_config({"gallery": {"directories": ["/影片/動作"]}})

        raw_text = config_path.read_text(encoding="utf-8")
        assert "影片" in raw_text, "非 ASCII 字元應直接寫入，不應 unicode-escape"

    def test_save_creates_file_if_not_exists(self, tmp_path, monkeypatch):
        config_path = tmp_path / "subdir" / "config.json"
        config_path.parent.mkdir(parents=True)
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)

        save_config({"scraper": {"create_folder": False}})

        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["scraper"]["create_folder"] is False


# ============ test_migration_source_links ============

class TestMigrationSourceLinks:
    """source_links 區段新增 + 深層合併保證"""

    def test_missing_source_links_section_gets_defaults(self, tmp_path, monkeypatch):
        """config.json 無 source_links key → load_config() 後補入全部 8 個預設值"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"general": {"theme": "light"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        sl = result["source_links"]
        assert sl["dmm"] is True
        assert sl["d2pass"] is True
        assert sl["heyzo"] is True
        assert sl["fc2"] is True
        assert sl["javbus"] is False
        assert sl["jav321"] is False
        assert sl["javdb"] is False
        assert sl["avsox"] is False

    def test_existing_source_links_preserved(self, tmp_path, monkeypatch):
        """config.json 有完整 source_links 且用戶已覆寫 javdb: true → 保持不動"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "source_links": {
                "dmm": True,
                "d2pass": True,
                "heyzo": True,
                "fc2": True,
                "javbus": False,
                "jav321": False,
                "javdb": True,   # user override
                "avsox": False,
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["source_links"]["javdb"] is True

    def test_partial_source_links_filled(self, tmp_path, monkeypatch):
        """config.json 的 source_links 只有 {"dmm": true} → 補齊其餘 7 個 key，dmm 保持 true"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"source_links": {"dmm": True}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        sl = result["source_links"]
        assert sl["dmm"] is True          # preserved
        assert sl["d2pass"] is True       # filled from defaults
        assert sl["heyzo"] is True        # filled from defaults
        assert sl["fc2"] is True          # filled from defaults
        assert sl["javbus"] is False      # filled from defaults
        assert sl["jav321"] is False      # filled from defaults
        assert sl["javdb"] is False       # filled from defaults
        assert sl["avsox"] is False       # filled from defaults

    def test_non_dict_source_links_replaced(self, tmp_path, monkeypatch):
        """config.json 有 source_links: null → 整個替換為預設 dict"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"source_links": None})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        sl = result["source_links"]
        assert isinstance(sl, dict)
        assert sl["dmm"] is True
        assert sl["javdb"] is False


# ============ test_migration_primary_source ============

class TestMigrationPrimarySource:
    """primary_source 補齊 migration"""

    def test_missing_primary_source_gets_default(self, tmp_path, monkeypatch):
        """primary_source 不存在 → 補齊為 javbus"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"search": {"proxy_url": ""}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["search"]["primary_source"] == "javbus"

    def test_existing_primary_source_preserved(self, tmp_path, monkeypatch):
        """primary_source 已為 dmm → 不覆蓋"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"search": {"proxy_url": "", "primary_source": "dmm"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["search"]["primary_source"] == "dmm"

    def test_search_section_missing(self, tmp_path, monkeypatch):
        """search section 不存在 → 建立並補齊"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["search"]["primary_source"] == "javbus"


# ============ test_migration_openai ============

class TestMigrationOpenAI:
    """openai 嵌套補齊 migration（Task T2）"""

    def test_translate_openai_migration(self, tmp_path, monkeypatch):
        """舊設定無 openai 區段 → migration 後自動補齊預設值"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "enabled": False,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "openai" in result["translate"]
        openai = result["translate"]["openai"]
        assert openai["base_url"] == ""
        assert openai["api_key"] == ""
        assert openai["model"] == "gpt-4o-mini"

    def test_translate_openai_not_overwrite_existing(self, tmp_path, monkeypatch):
        """openai 嵌套已存在 → 不覆蓋用戶設定"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "enabled": True,
                "provider": "openai",
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "model": "gpt-4o"
                }
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        openai = result["translate"]["openai"]
        assert openai["base_url"] == "https://api.openai.com/v1"
        assert openai["api_key"] == "sk-test"
        assert openai["model"] == "gpt-4o"
