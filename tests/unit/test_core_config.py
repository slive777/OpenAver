"""
tests/unit/test_core_config.py — core.config migration 邏輯 unit tests

直接測試 core.config.load_config 的各段 migration 邏輯，
以及 save_config / AppConfig 的基本行為。
"""

import json
import os
import stat
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
        assert result["gallery"]["directories"] == [{"path": "/videos", "readonly": False, "output_path": ""}]


# ============ test_migration_translate_flat_to_nested ============


# ============ test_migration_folder_format_to_folder_layers ============

class TestMigrationFolderFormatToFolderLayers:
    """folder_format → folder_layers"""

    @pytest.mark.parametrize("folder_format,expected_layers", [
        ("{actor}\\{maker}", ["{actor}", "{maker}"]),  # Windows 風格反斜線
    ])
    def test_single_layer(self, tmp_path, monkeypatch, folder_format, expected_layers):
        """單層／斜線多層／反斜線多層 folder_format 皆轉成 folder_layers"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"folder_format": folder_format}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["folder_layers"] == expected_layers

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


class TestNoSeedConfigBeforeLayoutFinalized:
    """BE-DATA-13：資料根未定版時，load_config 不得在資料根自動建 config.json。"""

    def test_unfinalized_data_root_does_not_write_config(self, tmp_path, monkeypatch):
        """CONFIG_PATH 在乾淨資料根下、無 .layout.json → 回傳可用設定且不落盤。"""
        from core.data_root import LAYOUT_MARKER_NAME

        root = tmp_path / "data_root"
        root.mkdir()
        config_path = root / "config.json"
        default_path = tmp_path / "config.default.json"
        _write_config(default_path, {"general": {"theme": "dark"}, "gallery": {"output_dir": ""}})

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr(core_config, "get_data_root", lambda: root)

        assert not (root / LAYOUT_MARKER_NAME).exists()
        assert not config_path.exists()

        result = load_config()

        assert isinstance(result, dict) and result
        assert result.get("general", {}).get("theme") == "dark"
        assert not config_path.exists(), (
            "資料根未定版時 load_config 不得寫出 config.json（BE-DATA-13）；"
            "否則下次 bootstrap 會判定 root≠legacy 衝突而永久阻斷啟動"
        )


class TestMigrationGalleryOutputDirSentinel:
    """gallery.output_dir 字面 'output' → ''（跟著資料根走）；其餘既有值不動。"""

    def test_literal_output_migrates_to_empty_string(self, tmp_path, monkeypatch):
        from core.data_root import resolve_gallery_output_path

        config_path = tmp_path / "config.json"
        _write_config(config_path, {"gallery": {"output_dir": "output"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        # migration 前：字面 "output" 解析位置
        before_resolved = str(resolve_gallery_output_path("output"))

        # 既有 HTML 放在解析後的位置，遷移不得搬動它
        html_path = Path(before_resolved) / "gallery_output.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = b"<html>pre-migration marker</html>"
        html_path.write_bytes(html_content)

        result = load_config()

        assert result["gallery"]["output_dir"] == ""
        after_resolved = str(resolve_gallery_output_path(""))
        assert after_resolved == before_resolved
        assert html_path.read_bytes() == html_content
        # 落盤也寫成空字串
        assert _read_config(config_path)["gallery"]["output_dir"] == ""

    def test_non_sentinel_custom_value_untouched(self, tmp_path, monkeypatch):
        """既有值不是恰為 'output'（例如已落在程式區的舊自訂值）→ 逐字不動。"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"gallery": {"output_dir": "app/custom"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["gallery"]["output_dir"] == "app/custom"
        assert _read_config(config_path)["gallery"]["output_dir"] == "app/custom"


# ============ test_migration_external_manager ============

class TestMigrationExternalManager:
    """external_manager 三態補齊與 jellyfin_mode 遷移（Fix-72b）"""

    @pytest.mark.parametrize("scraper_section,expected_manager", [
        ({"jellyfin_mode": True}, "jellyfin"),
        ({"create_folder": True}, "off"),  # 完全沒有 jellyfin_mode
    ])
    def test_legacy_jellyfin_mode_true_maps_to_jellyfin(
        self, tmp_path, monkeypatch, scraper_section, expected_manager
    ):
        """舊 config 無 external_manager：jellyfin_mode true→jellyfin；false／缺席→off"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": scraper_section})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["external_manager"] == expected_manager


    def test_legacy_jellyfin_emby_migrates_to_jellyfin(self, tmp_path, monkeypatch):
        """舊存檔有 external_manager='jellyfin_emby' → load_config() 後讀到 'jellyfin'"""
        import core.config as core_config
        from core.config import load_config
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"scraper": {"external_manager": "jellyfin_emby"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["external_manager"] == "jellyfin"


# ============ test_migration_download_sample_images ============


# ============ test_migration_thumbnail_cache_enabled ============

class TestMigrationThumbnailCacheEnabled:
    """thumbnail_cache_enabled 補齊（feature/71 T2，top-level flag）"""


    def test_existing_v098_user_gets_thumbnail_cache_enabled_false(self, tmp_path, monkeypatch, mocker):
        """v0.9.8 升級用戶（config.json 存在但無 thumbnail_cache_enabled key）→ migration 補 False（OFF）。

        保護現有用戶不被意外開啟快取（磁碟空間影響）；
        migration 寫 False 且持久化到 config.json。
        """
        config_path = tmp_path / "config.json"
        # 模擬 v0.9.8 config（有 scraper/gallery 等但沒有 thumbnail_cache_enabled）
        _write_config(config_path, {
            "scraper": {"create_folder": True},
            "gallery": {"directories": ["/videos"]},
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        spy = mocker.spy(core_config, "_save_config_unlocked")

        result = load_config()

        assert result.get("thumbnail_cache_enabled") is False, (
            "既有 v0.9.8 用戶 migration 應補 False（OFF），避免不知情開啟快取"
        )
        # migration 必須已將 False 寫回磁碟
        assert spy.call_count >= 1, "migration 命中 → 必須呼叫 _save_config_unlocked 寫回"
        written = json.loads(config_path.read_text(encoding="utf-8"))
        assert written.get("thumbnail_cache_enabled") is False, (
            "migration 寫回的 config.json 中 thumbnail_cache_enabled 必須為 False"
        )


# ============ test_migration_proxy_scope ============

_REAL_DEFAULT = Path(__file__).resolve().parents[2] / "web" / "config.default.json"


def _dmm_enabled(cfg: dict):
    return {s["id"]: s["enabled"] for s in cfg["sources"]}["dmm"]


def _legacy_proxy_config(proxy_url, dmm_enabled: bool, **extra) -> dict:
    """舊式設定檔：search 段無 proxy_scope、sources 為完整 builtin（DMM enabled 可指定）。"""
    from core.source_config import get_builtin_sources
    sources = [s.model_dump() for s in get_builtin_sources()]
    for s in sources:
        if s["id"] == "dmm":
            s["enabled"] = dmm_enabled
    cfg = {"search": {"proxy_url": proxy_url}, "sources": sources}
    cfg.update(extra)
    return cfg


class TestMigrationProxyScope:
    """search.proxy_scope 欄位 + 升級遷移（feature/163a T2，CD-163a-5/8/9）"""

    @staticmethod
    def _setup(tmp_path, monkeypatch, data=None, default_path=None):
        config_path = tmp_path / "config.json"
        if data is not None:
            _write_config(config_path, data)
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_path or tmp_path / "config.default.json")
        return config_path

    @pytest.mark.parametrize("proxy_url, dmm_before, url_after, dmm_after", [
        ("http://192.168.1.177:8888", True, "http://192.168.1.177:8888", True),
        ("direct", True, "", True),
        ("", True, "", False),          # 空白 + DMM on → off
    ])
    def test_migration_table(self, tmp_path, monkeypatch, proxy_url, dmm_before, url_after, dmm_after):
        config_path = self._setup(tmp_path, monkeypatch, _legacy_proxy_config(proxy_url, dmm_before))
        load_config()
        disk = _read_config(config_path)
        assert disk["search"]["proxy_scope"] == "dmm"
        assert disk["search"]["proxy_url"] == url_after
        assert _dmm_enabled(disk) is dmm_after


    @pytest.mark.parametrize("proxy_url", [""])
    def test_sources_missing_regenerated(self, tmp_path, monkeypatch, proxy_url):
        """sources 缺 → 重生為全開 → 空白 proxy 關 DMM；填了維持開"""
        config_path = self._setup(tmp_path, monkeypatch, {"search": {"proxy_url": proxy_url}})
        load_config()
        assert _dmm_enabled(_read_config(config_path)) is bool(proxy_url)


    def test_migration_runs_once_user_reenabled_dmm_stays_on(self, tmp_path, monkeypatch):
        """I-2：遷移後使用者自己把 DMM 打開 → 下次載入不再被關掉"""
        config_path = self._setup(tmp_path, monkeypatch, _legacy_proxy_config("", True))
        load_config()
        disk = _read_config(config_path)
        assert _dmm_enabled(disk) is False
        for s in disk["sources"]:
            if s["id"] == "dmm":
                s["enabled"] = True
        _write_config(config_path, disk)
        result = load_config()
        assert _dmm_enabled(result) is True
        assert _dmm_enabled(_read_config(config_path)) is True


    def test_new_install_dmm_on_and_not_migrated(self, tmp_path, monkeypatch, mocker):
        config_path = self._setup(tmp_path, monkeypatch, default_path=_REAL_DEFAULT)
        assert not config_path.exists()
        result = load_config()
        assert result["search"]["proxy_scope"] == "dmm"
        assert result["search"]["proxy_url"] == ""
        assert _dmm_enabled(result) is True
        assert _dmm_enabled(_read_config(config_path)) is True
        # 遷移函式對新安裝 raw config 回 False（不進遷移）
        assert core_config._migrate_proxy_scope(json.loads(config_path.read_text(encoding="utf-8"))) is False

# ============ test_migration_focal_device_state ============


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


# ============ test_migration_source_links ============


# ============ test_migration_openai ============

class TestMigrationOpenAI:
    """openai 嵌套補齊 migration（Task T2）"""

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


# ============ test_migration_claude ============


# ============ test_migration_sources ============

class TestMigrationSources:
    """sources 段 migration（TASK-61a-2）：缺段生成 / 升級保留 / 冪等 / uncensored 轉換 / 損壞 fallback"""

    def _enabled_map(self, sources: list) -> dict:
        return {s["id"]: s["enabled"] for s in sources}

    def test_fresh_config_gets_8_builtin_all_enabled(self, tmp_path, monkeypatch):
        """config.json 無 sources key → load_config() 後補入 8 個 builtin 全 enabled=true
        （T3 後：additive migration 再追加 javlibrary manual_only，共 9 條）"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"general": {"theme": "light"}, "search": {"proxy_scope": "dmm"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        sources = result["sources"]
        assert isinstance(sources, list)
        # T3 後：8 builtin + 1 javlibrary manual_only（additive migration）
        builtin_sources = [s for s in sources if not s.get("manual_only")]
        assert len(builtin_sources) == 8
        assert all(s["enabled"] is True for s in builtin_sources)
        ids = [s["id"] for s in builtin_sources]
        assert ids == ["dmm", "javbus", "jav321", "javdb", "d2pass", "heyzo", "fc2", "avsox"]
        # javlibrary 也存在，manual_only=True
        jl_sources = [s for s in sources if s.get("id") == "javlibrary"]
        assert len(jl_sources) == 1
        assert jl_sources[0]["manual_only"] is True


    def test_idempotent_valid_sources_unchanged(self, tmp_path, monkeypatch):
        """已存在合法 sources（javbus disabled）→ 不重生、不覆寫
        （T3 後：additive migration 追加 javlibrary，共 4 條）"""
        config_path = tmp_path / "config.json"
        existing = [
            {"id": "dmm", "type": "builtin", "display_name_key": "DMM", "enabled": True, "order": 0},
            {"id": "javbus", "type": "builtin", "display_name_key": "JavBus", "enabled": False, "order": 1},
            {"id": "jav321", "type": "builtin", "display_name_key": "Jav321", "enabled": True, "order": 2},
        ]
        _write_config(config_path, {"sources": existing, "search": {"proxy_scope": "dmm"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        # T3 後：3 既有 + 1 javlibrary（additive migration）= 4
        builtin_sources = [s for s in result["sources"] if not s.get("manual_only")]
        assert len(builtin_sources) == 3
        emap = self._enabled_map(builtin_sources)
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


    def test_migration_backfills_fc_javten_when_javlibrary_already_present(
        self, tmp_path, monkeypatch
    ):
        """CD-118a-9：已有 javlibrary、沒有 fc-javten 的舊 config → load 後補上 fc-javten。"""
        from core.source_config import get_manual_only_sources

        config_path = tmp_path / "config.json"
        existing = AppConfig().model_dump()
        existing["sources"].append(get_manual_only_sources()[0].model_dump())
        _write_config(config_path, existing)
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        ids = [s.get("id") for s in result["sources"]]
        assert "fc-javten" in ids
        fc = next(s for s in result["sources"] if s.get("id") == "fc-javten")
        assert fc["order"] == 100
        assert fc["manual_only"] is True
        assert fc["is_beta"] is True
        assert fc["enabled"] is False

    def test_corrupt_then_valid_keeps_first_bak(self, tmp_path, monkeypatch):
        """損壞修復後第二次啟動：sources 已合法 → sources_bak 保留不動
        （T3 後：第二次 load 的 sources 含 javlibrary，共 9 條）"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"sources": "broken"})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        first = load_config()
        assert first["sources_bak"] == "broken"
        # config.json 已被 save_config 寫回合法 sources + sources_bak

        second = load_config()
        # T3 後：8 builtin + 1 javlibrary（additive migration）= 9；javlibrary 冪等不重複
        builtin_sources = [s for s in second["sources"] if not s.get("manual_only")]
        assert len(builtin_sources) == 8
        assert second["sources_bak"] == "broken"  # 不被合法 sources 清掉


# ============ config.default.json schema parity（Codex PR#45 P2 drift guard）============

class TestConfigDefaultSchemaParity:
    """config.default.json（fresh install 複製來源）必須與 AppConfig schema 對齊。

    load_config() 對 fresh install 直接回傳複製來的 raw dict（不經 AppConfig 重建），
    故 default 檔漏的欄位 / 來源漏的 is_censored 會直接出現在 /api/config，導致：
      - 缺 top-level 欄位 → GET 契約不完整（如 thumbnail_cache_enabled）
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
        self._patch_paths(tmp_path, monkeypatch)
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


# ============ T3：javlibrary migration additive step ============

class TestJavlibraryMigration:
    """T3：config migration additive step 測試。"""

    def _patch(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
        return config_path

    # a) 8-builtin 既有 config → load 後 sources 含 javlibrary（order=99, manual_only=True）

    # c) 已有 javlibrary 且用戶自訂 order=50 → 不被改動


# ============ TASK-80a-T1：GeneralConfig.server_mode schema ============

class TestGeneralConfigServerMode:
    """server_mode: bool = False 欄位 schema 測試（TASK-80a-T1）"""

    def test_appconfig_server_mode_default_false(self):
        """AppConfig().general.server_mode 預設 False"""
        cfg = AppConfig()
        assert cfg.general.server_mode is False


# ============ TASK-82-T4：GeneralConfig.close_action schema ============


# ============ TASK-82-T4：additive migration general.close_action ============

class TestMigrationCloseAction:
    """general.close_action additive migration（feature/82 T4）"""

    def test_close_action_added_when_missing(self, tmp_path, monkeypatch):
        """舊 config 缺 general.close_action → migration 自動補 'ask'"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"general": {"theme": "dark", "locale": "zh-TW"}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result.get("general", {}).get("close_action") == "ask"
        # migration 命中 → 已寫回 config.json
        written = json.loads(config_path.read_text(encoding="utf-8"))
        assert written.get("general", {}).get("close_action") == "ask"


# ============ TASK-107-P1-T1：GeneralConfig.auto_check_update schema ============


# ============ TASK-107-P1-T1：additive migration general.auto_check_update ============

class TestMigrationAutoCheckUpdate:
    """general.auto_check_update additive migration（feature/107 P1-T1）"""


    def test_auto_check_update_not_overwritten_when_false(self, tmp_path, monkeypatch):
        """既存 auto_check_update=False（使用者曾關閉）不被覆寫（用 not in 判斷）"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"general": {"auto_check_update": False}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result.get("general", {}).get("auto_check_update") is False
        # 回讀檔案仍為 False
        written = _read_config(config_path)
        assert written.get("general", {}).get("auto_check_update") is False


# ============ TASK-88a-T3：gallery.directories str → DirectoryConfig object migration ============

class TestMigrationDirectoriesToObject:
    """gallery.directories 純字串清單 → DirectoryConfig 物件遷移（TASK-88a-T3）"""


    def test_mixed_list_preserved(self, tmp_path, monkeypatch):
        """混合清單：str 升級；dict 的 readonly/output_path 值保留"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "gallery": {
                "directories": [
                    "/a",
                    {"path": "/b", "readonly": True, "output_path": "/out"},
                ]
            }
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        dirs = result["gallery"]["directories"]
        assert dirs[0] == {"path": "/a", "readonly": False, "output_path": ""}
        assert dirs[1] == {"path": "/b", "readonly": True, "output_path": "/out"}


# ============ TASK-90a-T2：scraper.strm_path_mappings schema + additive migration ============

class TestScraperStrmPathMappings:
    """ScraperConfig.strm_path_mappings: Dict[str,str] = {} + load_config additive migration（TASK-90a-T2）"""

    def test_migration_not_overwrite_existing(self, tmp_path, monkeypatch):
        """已含 strm_path_mappings 有值 → migration 不覆寫，保留原值"""
        config_path = tmp_path / "config.json"
        _write_config(config_path, {
            "scraper": {"strm_path_mappings": {"Z:\\115\\": "/vol/"}}
        })
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["scraper"]["strm_path_mappings"] == {"Z:\\115\\": "/vol/"}


# ============ CD-114c-9: config.json mode bits (POSIX only) ============

class TestConfigPathMode:
    """CD-114c-9: config.json must be 0600 after first-init copy2 and after save.

    B19 / B20 — function-layer tests (same monkeypatch style as
    test_copies_default_when_default_exists). Windows skips (NTFS ACLs).
    """

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits; NTFS ACL 不吃 0600")
    def test_first_init_copy_yields_0600(self, tmp_path, monkeypatch):
        """B19 ①: no config.json → load_config() copy2 from default → mode 0o600.

        Default content is migration-complete so first-init does **not** trigger a
        migration rewrite (atomic_write would hide copy2's 0644). That makes this
        assertion pin the post-copy2 chmod itself (CD-114c-9 DoD: red at 0644
        before chmod lands, green after).
        """
        # Produce a fully migrated blob, then use it as 0644 default.
        seed_path = tmp_path / "seed.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", seed_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "unused.default.json")
        save_config(AppConfig().model_dump())
        complete = load_config()

        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        _write_config(default_path, complete)
        default_path.chmod(0o644)
        assert not config_path.exists()

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_path)

        load_config()

        assert config_path.exists(), "應從 default 複製建立 config.json"
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600, f"first-init config.json mode must be 0o600, got {oct(mode)}"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits; NTFS ACL 不吃 0600")
    def test_save_config_yields_0600(self, tmp_path, monkeypatch):
        """B20 ②: save_config() leaves config.json at 0o600."""
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        cfg = AppConfig().model_dump()
        save_config(cfg)

        assert config_path.exists()
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600, f"after save_config mode must be 0o600, got {oct(mode)}"


# ============ TASK-121c-T4：gallery.cover_badges 預設值 + default.json parity ============


# ============ TASK-133b-T1：gallery.show_table_list 預設值 + default.json parity ============


# ============ TASK-153b-T3fix1：資料根未定版時禁止寫入 config.json（BE-DATA-13） ============

class TestSaveConfigBlockedBeforeLayoutFinalized:
    """BE-DATA-13 / TASK-153b-T3fix1：資料根未定版時，禁止呼叫 save_config / mutate_config 落盤。"""

    def test_save_config_raises_when_root_not_finalized(self, tmp_path, monkeypatch):
        """資料根未定版時 save_config 必須 raise ConfigRootNotFinalizedError 且磁碟零寫入。"""
        from core.data_root import LAYOUT_MARKER_NAME

        root = tmp_path / "data_root"
        root.mkdir()
        config_path = root / "config.json"

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "get_data_root", lambda: root)

        assert not (root / LAYOUT_MARKER_NAME).exists()
        before_entries = list(root.iterdir())

        with pytest.raises(core_config.ConfigRootNotFinalizedError):
            core_config.save_config({"hello": "world"})

        assert not config_path.exists()
        assert list(root.iterdir()) == before_entries

    def test_save_config_succeeds_when_root_finalized(self, tmp_path, monkeypatch):
        """資料根已定版時 save_config 正常寫入，行為不變。"""
        from core.data_root import LAYOUT_MARKER_NAME

        root = tmp_path / "data_root"
        root.mkdir()
        config_path = root / "config.json"
        (root / LAYOUT_MARKER_NAME).write_text(
            json.dumps({"version": 1, "complete": True}),
            encoding="utf-8",
        )

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "get_data_root", lambda: root)

        core_config.save_config({"hello": "world"})

        assert config_path.exists()
        assert _read_config(config_path) == {"hello": "world"}


    def test_save_config_raises_when_marker_corrupt_json(self, tmp_path, monkeypatch):
        """F2：marker JSON 損壞 → save_config raise 且零寫入。"""
        from core.data_root import LAYOUT_MARKER_NAME

        root = tmp_path / "data_root"
        root.mkdir()
        config_path = root / "config.json"
        (root / LAYOUT_MARKER_NAME).write_text("{not json", encoding="utf-8")

        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "get_data_root", lambda: root)

        before_entries = list(root.iterdir())

        with pytest.raises(core_config.ConfigRootNotFinalizedError):
            core_config.save_config({"hello": "world"})

        assert not config_path.exists()
        assert list(root.iterdir()) == before_entries


# ============ test_nfo_title_format ============


# ============ test_migration_ai_tags_config ============

class TestMigrationAITagsConfig:
    """ai_services.tags 缺才補（TASK-188b-T8，CD-188b-14）"""

    def test_legacy_ai_services_without_tags_gets_default_tags(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"ai_services": {"image_similar": {"enabled": False, "url": "", "api_key": "", "model": ""}, "faces": {"enabled": True, "url": "http://faces.invalid", "api_key": "", "model": "m"}}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["ai_services"]["tags"] == {"enabled": False, "provider": "", "model": ""}
        assert result["ai_services"]["faces"]["enabled"] is True
        assert _read_config(config_path)["ai_services"]["tags"] == {"enabled": False, "provider": "", "model": ""}


# ============ TASK-195-T3：gallery.hide_unreachable_sources additive migration ============

class TestHideUnreachableSourcesMigration:
    """舊 config 缺 hide_unreachable_sources → 補 False 並寫回磁碟（TASK-195-T3）"""

    def test_hide_unreachable_defaults_off_for_legacy_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        _write_config(config_path, {"gallery": {"items_per_page": 60}})
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

        result = load_config()

        assert result["gallery"]["hide_unreachable_sources"] is False
        assert result["gallery"]["items_per_page"] == 60
        disk = _read_config(config_path)
        assert disk["gallery"]["hide_unreachable_sources"] is False
        assert disk["gallery"]["items_per_page"] == 60

