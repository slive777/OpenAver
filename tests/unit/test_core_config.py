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
    """primary_source strip migration（65d-2：欄位已廢棄，load_config 清除舊 config.json 的殘留 key）"""

    def test_existing_primary_source_gets_stripped(self, tmp_path, monkeypatch):
        """config.json 有 primary_source → load_config 後 key 不存在"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"search": {"proxy_url": "", "primary_source": "javbus"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "primary_source" not in result.get("search", {})

    def test_strip_triggers_save(self, tmp_path, monkeypatch):
        """config.json 有 primary_source → migration 觸發 save（磁碟寫回後 key 不存在）"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"search": {"proxy_url": "", "primary_source": "dmm"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        load_config()

        saved = _read_config(config_path)
        assert "primary_source" not in saved.get("search", {})

    def test_no_primary_source_is_noop(self, tmp_path, monkeypatch):
        """config.json 無 primary_source → strip 分支 no-op，search section 完整保留、無 primary_source key"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"search": {"proxy_url": ""}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "primary_source" not in result.get("search", {})
        assert "search" in result

    def test_search_section_missing(self, tmp_path, monkeypatch):
        """search section 不存在 → 建立空 search section，不崩潰，無 primary_source"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert "search" in result
        assert "primary_source" not in result["search"]


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

    def test_openai_config_has_use_custom_model_field(self):
        """OpenAIConfig 應有 use_custom_model 欄位，預設為 False，重載後能還原 custom/select 模式"""
        from core.config import OpenAIConfig
        config = OpenAIConfig()
        assert hasattr(config, "use_custom_model"), \
            "OpenAIConfig 應有 use_custom_model 欄位，否則重載後無法還原 custom 模式"
        assert config.use_custom_model is False, \
            "OpenAIConfig.use_custom_model 預設值應為 False"

    def test_openai_use_custom_model_roundtrip(self, tmp_path, monkeypatch):
        """use_custom_model=True 存入 config → load_config 後能正確讀回"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "enabled": True,
                "provider": "openai",
                "openai": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "",
                    "model": "my-private-model",
                    "use_custom_model": True
                }
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        openai = result["translate"]["openai"]
        assert openai["use_custom_model"] is True, \
            "use_custom_model=True 應能從 config 正確讀回，否則重載後 custom 模式丟失"


# ============ test_migration_sources ============

class TestMigrationSources:
    """sources 段 migration（TASK-61a-2）：缺段生成 / 升級保留 / 冪等 / uncensored 轉換 / 損壞 fallback"""

    def _enabled_map(self, sources: list) -> dict:
        return {s["id"]: s["enabled"] for s in sources}

    def test_fresh_config_gets_8_builtin_all_enabled(self, tmp_path, monkeypatch):
        """config.json 無 sources key → load_config() 後補入 8 個 builtin 全 enabled=true"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"general": {"theme": "light"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        sources = result["sources"]
        assert isinstance(sources, list)
        assert len(sources) == 8
        assert all(s["enabled"] is True for s in sources)
        ids = [s["id"] for s in sources]
        assert ids == ["dmm", "javbus", "jav321", "javdb", "d2pass", "heyzo", "fc2", "avsox"]

    def test_upgrade_preserves_existing_keys(self, tmp_path, monkeypatch):
        """既有完整 config 但無 sources → 補 8 builtin 且所有既有 key/value 字面保留"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini"},
            },
            "scraper": {
                "create_folder": True,
                "folder_layers": ["{actor}"],
                "folder_format": "{actor}",
                "suffix_keywords": ["-cd1"],
                "jellyfin_mode": False,
                "download_sample_images": False,
            },
            "source_links": {
                "dmm": True, "d2pass": True, "heyzo": True, "fc2": True,
                "javbus": False, "jav321": False, "javdb": False, "avsox": False,
            },
            "general": {"theme": "dark", "locale": "ja"},
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        # sources 補齊
        assert len(result["sources"]) == 8
        assert all(s["enabled"] is True for s in result["sources"])
        # 既有 key 字面保留
        assert result["general"]["theme"] == "dark"
        assert result["general"]["locale"] == "ja"
        assert result["translate"]["enabled"] is False
        assert result["scraper"]["suffix_keywords"] == ["-cd1"]
        # source_links 的 False 值不被改動
        assert result["source_links"]["javbus"] is False
        assert result["source_links"]["javdb"] is False
        assert result["source_links"]["dmm"] is True

    def test_idempotent_valid_sources_unchanged(self, tmp_path, monkeypatch):
        """已存在合法 sources（javbus disabled）→ 不重生、不覆寫"""
        config_path = tmp_path / "config.json"
        existing = [
            {"id": "dmm", "type": "builtin", "display_name_key": "DMM", "enabled": True, "order": 0},
            {"id": "javbus", "type": "builtin", "display_name_key": "JavBus", "enabled": False, "order": 1},
            {"id": "jav321", "type": "builtin", "display_name_key": "Jav321", "enabled": True, "order": 2},
        ]
        _write_config(config_path, {"sources": existing})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert len(result["sources"]) == 3
        emap = self._enabled_map(result["sources"])
        assert emap["javbus"] is False
        assert emap["dmm"] is True

    def test_uncensored_mode_conversion_disables_censored(self, tmp_path, monkeypatch):
        """uncensored_mode_enabled=true 升級無 sources → 4 有碼 disabled，4 無碼（含 d2pass）enabled"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "search": {"uncensored_mode_enabled": True},
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        emap = self._enabled_map(result["sources"])
        # 4 有碼 disabled
        assert emap["dmm"] is False
        assert emap["javbus"] is False
        assert emap["jav321"] is False
        assert emap["javdb"] is False
        # 4 無碼 enabled（d2pass 顯式斷言：是無碼不是有碼）
        assert emap["d2pass"] is True
        assert emap["heyzo"] is True
        assert emap["fc2"] is True
        assert emap["avsox"] is True

    def test_uncensored_mode_does_not_convert_existing_sources(self, tmp_path, monkeypatch):
        """uncensored_mode_enabled=true 但 sources 段已存在 → 冪等優先，不觸發轉換"""
        config_path = tmp_path / "config.json"
        existing = [
            {"id": "dmm", "type": "builtin", "display_name_key": "DMM", "enabled": True, "order": 0},
        ]
        _write_config(config_path, {
            "search": {"uncensored_mode_enabled": True},
            "sources": existing,
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert len(result["sources"]) == 1
        assert result["sources"][0]["enabled"] is True

    def test_corrupt_sources_string_fallback(self, tmp_path, monkeypatch):
        """sources 是字串（損壞）→ fallback 8 builtin 全 enabled + sources_bak 持有原值"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"sources": "broken"})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert isinstance(result["sources"], list)
        assert len(result["sources"]) == 8
        assert all(s["enabled"] is True for s in result["sources"])
        assert result["sources_bak"] == "broken"

    def test_corrupt_sources_missing_id_fallback(self, tmp_path, monkeypatch, caplog):
        """sources 元素缺 id（損壞）→ fallback 8 builtin + sources_bak + warning"""
        config_path = tmp_path / "config.json"
        bad = [{"no_id": 1, "enabled": True}]
        _write_config(config_path, {"sources": bad})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        import logging
        with caplog.at_level(logging.WARNING):
            result = load_config()

        assert len(result["sources"]) == 8
        assert all(s["enabled"] is True for s in result["sources"])
        assert result["sources_bak"] == bad

    def test_corrupt_then_valid_keeps_first_bak(self, tmp_path, monkeypatch):
        """損壞修復後第二次啟動：sources 已合法 → sources_bak 保留不動"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"sources": "broken"})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        first = load_config()
        assert first["sources_bak"] == "broken"
        # config.json 已被 save_config 寫回合法 sources + sources_bak

        second = load_config()
        assert len(second["sources"]) == 8
        assert second["sources_bak"] == "broken"  # 不被合法 sources 清掉


# ============ config.default.json schema parity（Codex PR#45 P2 drift guard）============

class TestConfigDefaultSchemaParity:
    """config.default.json（fresh install 複製來源）必須與 AppConfig schema 對齊。

    load_config() 對 fresh install 直接回傳複製來的 raw dict（不經 AppConfig 重建），
    故 default 檔漏的欄位 / 來源漏的 is_censored 會直接出現在 /api/config，導致：
      - 缺 top-level 欄位 → GET 契約不完整（如 advanced_search_enabled）
      - sources 漏 is_censored → 前端 isUncensored() 把有碼來源誤判無碼（§2.4 配色）
    此守衛防止 default 檔再次漂移出 AppConfig schema。
    """

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "web" / "config.default.json"
    CENSORED = {"dmm", "javbus", "jav321", "javdb"}

    def _default(self) -> dict:
        return json.loads(self.DEFAULT_PATH.read_text(encoding="utf-8"))

    def test_default_has_all_appconfig_toplevel_fields(self):
        default = self._default()
        schema = AppConfig().model_dump()
        missing = set(schema) - set(default)
        assert not missing, f"config.default.json 缺 top-level 欄位（fresh install /api/config 會漏）: {sorted(missing)}"

    def test_default_advanced_search_enabled_present_and_false(self):
        default = self._default()
        assert default.get("advanced_search_enabled") is False

    def test_default_sources_carry_is_censored(self):
        default = self._default()
        for s in default.get("sources", []):
            assert "is_censored" in s, f"source {s.get('id')} 缺 is_censored（前端會誤判無碼）"

    def test_default_sources_is_censored_values_correct(self):
        default = self._default()
        censored = {s["id"] for s in default["sources"] if s.get("is_censored")}
        assert censored == self.CENSORED, f"config.default.json censored 集合錯誤: {sorted(censored)}"

    def test_default_sources_match_appconfig_model_dump(self):
        """default sources 與 get_builtin_sources() model_dump 完全一致（含 is_censored）。"""
        default = self._default()
        schema_sources = AppConfig().model_dump()["sources"]
        assert default["sources"] == schema_sources


# ============ TASK-66b-T1：寫入序列化 + 原子寫 + mutate_config ============

class TestMutateConfigAndAtomicWrite:
    """CD-66b-1：_config_write_lock 序列化 + 原子寫 + mutate_config RMW（確定性，非真 race）。"""

    def _patch_paths(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
        return config_path

    def test_mutate_config_no_lost_update(self, tmp_path, monkeypatch):
        """兩次序列 mutate_config（不同欄位）→ 兩者皆持久化（RMW 在單一 critical section）。"""
        config_path = self._patch_paths(tmp_path, monkeypatch)
        save_config({"general": {}})

        core_config.mutate_config(
            lambda cfg: cfg.setdefault("general", {}).__setitem__("theme", "dark")
        )
        core_config.mutate_config(
            lambda cfg: cfg.setdefault("general", {}).__setitem__("font_size", "lg")
        )

        result = load_config()
        assert result["general"]["theme"] == "dark"
        assert result["general"]["font_size"] == "lg"

    def test_save_config_atomic_no_temp_leftover(self, tmp_path, monkeypatch):
        """json.dump 拋例外 → _save_config_unlocked re-raise 且不留 *.tmp 殘檔。"""
        config_path = self._patch_paths(tmp_path, monkeypatch)

        def _boom(*args, **kwargs):
            raise RuntimeError("dump failed")

        monkeypatch.setattr(core_config.json, "dump", _boom)

        with pytest.raises(RuntimeError, match="dump failed"):
            core_config._save_config_unlocked({"general": {}})

        leftover = list(config_path.parent.glob("*.tmp"))
        assert leftover == [], f"原子寫失敗後不應殘留 temp: {leftover}"
        assert not config_path.exists(), "寫入失敗不應產生 config.json"

    def test_mutate_config_holds_lock(self, tmp_path, monkeypatch):
        """mutator 執行時 _config_write_lock 必須持有（確定性斷言，CD-66b-6）。"""
        self._patch_paths(tmp_path, monkeypatch)
        save_config({"general": {}})

        seen = []

        def _mut(cfg):
            seen.append(core_config._config_write_lock.locked())
            cfg.setdefault("general", {})["theme"] = "dark"

        core_config.mutate_config(_mut)
        assert seen == [True], "mutator 執行時 _config_write_lock 必須為 locked"

    def test_reset_config_file(self, tmp_path, monkeypatch):
        """存在 → 刪除；不存在 → no-op 不拋（無 TOCTOU）。"""
        config_path = self._patch_paths(tmp_path, monkeypatch)
        save_config({"general": {}})
        assert config_path.exists()

        core_config.reset_config_file()
        assert not config_path.exists()

        # 再次呼叫不應拋例外
        core_config.reset_config_file()
        assert not config_path.exists()

    def test_load_config_migration_no_deadlock(self, tmp_path, monkeypatch):
        """觸發 migration（primary_source strip）→ load_config() 不死鎖且寫回。

        migration save 走 _save_config_unlocked（已持鎖），若誤用 save_config 會
        二次 acquire 同一 threading.Lock → 永久死鎖。此測試在無 hang 下完成即證明。
        """
        config_path = self._patch_paths(tmp_path, monkeypatch)
        _write_config(config_path, {"search": {"primary_source": "javdb"}})

        result = load_config()  # 不得 hang

        assert "primary_source" not in result.get("search", {})
        # migration 已持久化（檔案內也無 primary_source）
        persisted = _read_config(config_path)
        assert "primary_source" not in persisted.get("search", {})
        # 鎖已釋放（load_config 結束後不應仍持有）
        assert core_config._config_write_lock.locked() is False
