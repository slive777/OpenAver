import pytest
import json

class TestConfigAPI:
    """測試 web/routers/config.py 的 API 端點"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH 和 CONFIG_DEFAULT_PATH 避免影響真實設定檔"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        
        # 建立預設設定檔作為基底
        default_data = {
            "general": {"tutorial_completed": False}
        }
        default_path.write_text(json.dumps(default_data))
        
        # Mock module variables（core.config は load_config/save_config が参照する実体）
        # web.routers.config は _core_config.CONFIG_PATH で動態参照するため、
        # core.config.CONFIG_PATH を差し替えるだけで DELETE /api/config も正しく動く
        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        
        # Mock reset_translate_service dependency to do nothing
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        
        return config_path

    def test_delete_config_success(self, client, mock_config_path):
        """測試成功刪除 config.json (恢復原廠設定)"""
        # 手動建立 config_path
        mock_config_path.write_text('{"some": "data"}')
        assert mock_config_path.exists()
        
        response = client.delete("/api/config")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "恢復預設" in data["message"]
        assert not mock_config_path.exists()

        # 不會報錯，一樣回傳成功


class TestLocaleChangeResetsTranslateService:
    """locale 變更應觸發 translate service reset（auto 模式依賴 locale）"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH，初始化含 general.locale 的 config"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
            "translate": {"enabled": False, "provider": "ollama",
                          "batch_size": 10,
                          "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                          "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"}},
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)

        return config_path

    def test_locale_change_calls_reset_translate_service(self, client, mock_config_path, monkeypatch):
        """PUT /api/config/general/locale 成功後呼叫 _reset_translate_service()"""
        reset_called = []

        def fake_reset():
            reset_called.append(True)

        monkeypatch.setattr("web.routers.config._reset_translate_service", fake_reset)

        resp = client.put("/api/config/general/locale", json={"value": "en"})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(reset_called) == 1, "locale 變更後應呼叫一次 _reset_translate_service()"

    def test_korean_locale_is_accepted(self, client, mock_config_path):
        resp = client.put("/api/config/general/locale", json={"value": "ko"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestServerModeEndpoint:
    """PUT /api/config/general/server_mode 端點測試（TASK-80a-T1）"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """Mock CONFIG_PATH，初始化含 general 的 config。
        同時 mock lan_listener.start/stop 避免真實 uvicorn 啟動（T6b 起 server_mode true
        觸發 lan_listener.start()，測試環境未 wire → 需 mock）。"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        # T6b: server_mode toggle 呼叫 lan_listener.start()/stop() — mock 避免真實啟動
        monkeypatch.setattr("web.lan_listener.lan_listener.start", lambda *a, **k: 49200)
        monkeypatch.setattr("web.lan_listener.lan_listener.stop", lambda *a, **k: None)

        return config_path


    def test_server_mode_true_persisted(self, client, mock_config_path):
        """PUT server_mode {value: true} → config.json 寫入 general.server_mode=True"""
        client.put("/api/config/general/server_mode", json={"value": True})

        saved = json.loads(mock_config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True


    def test_server_mode_string_false_returns_400_not_stored(self, client, mock_config_path):
        """安全性關鍵：字串 "false" 是 truthy，必須 400 且不得寫入 config
        （否則 middleware bool("false")=True 會誤開對外）。"""
        resp = client.put("/api/config/general/server_mode", json={"value": "false"})

        assert resp.status_code == 400
        saved = json.loads(mock_config_path.read_text())
        assert "server_mode" not in saved.get("general", {})


class TestAutoCheckUpdateEndpoint:
    """PUT /api/config/general/auto_check_update 端點測試（Codex P2：布林語意欄位擋字串反轉）

    auto_check_update 是布林語意欄位，下游 lifespan(_startup_update_check) 與 help.html
    data-attr 都當布林讀。字串 "false" 是 truthy，若落盤會被當「開啟」→ 語意反轉。
    比照 server_mode，非 bool 一律 400。"""

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_string_false_returns_400_not_stored(self, client, mock_config_path):
        """安全性關鍵：字串 "false" 是 truthy，必須 400 且不得寫入 config
        （否則 lifespan `not "false"` = False → gate 誤過、help data-attr 誤算 true）。"""
        resp = client.put("/api/config/general/auto_check_update", json={"value": "false"})

        assert resp.status_code == 400
        saved = json.loads(mock_config_path.read_text())
        assert "auto_check_update" not in saved.get("general", {})

    def test_bool_false_returns_200_persisted_as_bool(self, client, mock_config_path):
        """PUT {value: false} 真 bool → 200 且落盤為 bool False（非字串 "false"）"""
        resp = client.put("/api/config/general/auto_check_update", json={"value": False})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        saved = json.loads(mock_config_path.read_text())
        stored = saved.get("general", {}).get("auto_check_update")
        assert stored is False  # 嚴格：bool False，非 truthy 字串 "false"


class TestFocalDeviceDisabledEndpoint:
    """PUT /api/config/focal-device/disabled（TASK-D3 / CD-152d-4）

    專用 toggle 端點：value 必須是 StrictBool；真寫磁碟（disabled + set_by_user）。
    非 bool（整數 1）→ schema 層 422，磁碟零改動。
    """

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {"locale": "zh-TW", "theme": "light", "sidebar_collapsed": False,
                        "tutorial_completed": False, "font_size": "md", "default_page": "search"},
            "focal_device": {
                "disabled": False,
                "consecutive_timeout_count": 0,
                "judged_at_version": "",
                "set_by_user": False,
            },
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_focal_device_disabled_endpoint_persists_to_disk(self, client, mock_config_path):
        """oracle (a)：PUT {value: true} → 200 且磁碟 focal_device.disabled/set_by_user 真的改變"""
        before = json.loads(mock_config_path.read_text())
        assert before["focal_device"]["disabled"] is False
        assert before["focal_device"]["set_by_user"] is False

        resp = client.put("/api/config/focal-device/disabled", json={"value": True})

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        saved = json.loads(mock_config_path.read_text())
        assert saved["focal_device"]["disabled"] is True
        assert saved["focal_device"]["set_by_user"] is True

        # 再開回來：value false → disabled=False，set_by_user 仍 True
        resp2 = client.put("/api/config/focal-device/disabled", json={"value": False})
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True
        saved2 = json.loads(mock_config_path.read_text())
        assert saved2["focal_device"]["disabled"] is False
        assert saved2["focal_device"]["set_by_user"] is True


class TestFullConfigSavePreservesServerMode:
    """P2-1: PUT /api/config（全量儲存）不得改寫 server_mode（toggle-lifecycle 所有權）

    Divergence path（confirmed):
      PUT /api/config accepts AppConfig body → Pydantic model_validates the incoming
      general section.  If the payload's general.server_mode is False (Pydantic default
      when the key is absent) or explicitly False, the old save_config() call would write
      that value over a persisted True — leaving the LAN listener running but
      general.server_mode=false in config.json (diverged).

    Fix: update_config() now runs mutate_config(_write_preserving_server_owned) which
    reads the currently-persisted server_mode under the write lock and forces it into the
    payload before writing, regardless of what the incoming body says.
    """

    @pytest.fixture
    def mock_config_path_with_server_mode_true(self, tmp_path, monkeypatch):
        """Config pre-seeded with general.server_mode=true (listener "running")."""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {
            "general": {
                "locale": "zh-TW",
                "theme": "light",
                "sidebar_collapsed": False,
                "tutorial_completed": False,
                "font_size": "md",
                "default_page": "search",
                "server_mode": True,  # persisted True — listener is "running"
            },
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "thumbnail_cache_enabled": False,
        }
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_full_save_omitting_server_mode_preserves_true(
        self, client, mock_config_path_with_server_mode_true
    ):
        """PUT /api/config whose general body OMITS server_mode must NOT reset it to False.

        Simulates the frontend saveConfig() behaviour: it sends a full AppConfig body but
        the general section only sets known form fields (default_page, theme) and does NOT
        include server_mode.  The Pydantic default for missing server_mode is False —
        without the preservation guard this would silently overwrite the persisted True
        and diverge from lan_listener.is_running (still True).
        """
        config_path = mock_config_path_with_server_mode_true

        # Build a minimal valid AppConfig payload.  general.server_mode is deliberately
        # absent — Pydantic will default it to False.
        payload = {
            "general": {
                "default_page": "search",
                "theme": "dark",
                # server_mode intentionally omitted → Pydantic default False
            },
            "scraper": {},
            "search": {},
            "source_links": {},
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "gallery": {},
            "showcase": {},
            "sources": [],
            "thumbnail_cache_enabled": False,
            "metatube": {},
        }

        resp = client.put("/api/config", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        saved = json.loads(config_path.read_text())
        assert saved.get("general", {}).get("server_mode") is True, (
            "PUT /api/config must preserve the persisted server_mode=true; "
            "omitting the field in the payload must not reset it to False "
            "(would diverge from running LAN listener)"
        )


class TestDeleteConfigStopsLanListener:
    """P2-4: DELETE /api/config (reset) は LAN listener を停止しなければならない

    reset_config_file() は server_mode を含む config を削除する → defaults では
    server_mode が存在しない（= false）。しかし listener は停止しないと
    runtime（listener 起動中）≠ persisted（server_mode absent）が分離し、
    0.0.0.0 socket が 403 を返し続けてしまう。
    """

    @pytest.fixture
    def mock_config_path(self, tmp_path, monkeypatch):
        """DELETE /api/config 用 fixture — lan_listener.stop() も mock する"""
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"

        config_data = {"general": {"server_mode": True}}
        config_path.write_text(json.dumps(config_data))
        default_path.write_text(json.dumps(config_data))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        return config_path

    def test_delete_config_calls_lan_listener_stop(self, client, mock_config_path, monkeypatch):
        """DELETE /api/config → lan_listener.stop() は必ず 1 回呼ばれる

        reset は server_mode を消去する（defaults = false）ため、listener の
        runtime↔persisted を一致させるために stop() を呼ぶ必要がある。
        stop() は idempotent なので listener が起動していなくても安全。
        """
        stop_called = []

        monkeypatch.setattr(
            "web.lan_listener.lan_listener.stop",
            lambda *a, **k: stop_called.append(True),
        )

        resp = client.delete("/api/config")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert len(stop_called) == 1, (
            "DELETE /api/config must call lan_listener.stop() once to keep "
            "runtime↔persisted consistent after config reset clears server_mode"
        )


class TestSwitchExternalManagerEndpoint:
    """POST /api/config/switch-external-manager 端點測試（TASK-90c-T4）

    破壞性重設：切換全域 external_manager 時原子刪除離線（唯讀）來源的 DB 卡 +
    移除離線 config 條目 + 設新 external_manager。零檔案系統刪除。含可自癒失敗契約。

    測試以真 config.json（CONFIG_PATH monkeypatch）讓 mutate_config 真的 RMW，
    DB 側 mock（呼叫處 binding web.routers.config.VideoRepository），縮圖 spy。
    """

    class _FakeRepo:
        """有狀態的假 VideoRepository：delete 真的從內部清單移除，供收斂測試。"""
        def __init__(self, paths):
            self._paths = list(paths)
            self.delete_calls = []

        def get_all(self):
            import types
            return [types.SimpleNamespace(path=p) for p in self._paths]

        def delete_by_paths(self, paths):
            self.delete_calls.append(list(paths))
            if not paths:  # 對齊真實 delete_by_paths :669 早退
                return 0
            deleted = [p for p in paths if p in self._paths]
            for p in deleted:
                self._paths.remove(p)
            return len(deleted)

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        import types
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        default_path.write_text(json.dumps({"general": {}}))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)

        # DB 依賴：避免碰真實 DB（get_db_path/init_db no-op），VideoRepository 回共享 fake
        monkeypatch.setattr("web.routers.config.get_db_path", lambda: tmp_path / "videos.db")
        monkeypatch.setattr("web.routers.config.init_db", lambda *a, **k: None)

        holder = types.SimpleNamespace(repo=None, invalidated=[], config_path=config_path)
        monkeypatch.setattr("web.routers.config.VideoRepository", lambda *a, **k: holder.repo)

        # 縮圖 spy（best-effort）
        fake_tc = types.SimpleNamespace(invalidate=lambda p: holder.invalidated.append(p))
        monkeypatch.setattr("web.routers.config.thumbnail_cache", fake_tc)

        def write_config(directories, external_manager="off", path_mappings=None):
            gallery = {"directories": directories}
            if path_mappings:
                gallery["path_mappings"] = path_mappings
            config_path.write_text(json.dumps({
                "gallery": gallery,
                "scraper": {"external_manager": external_manager},
            }))

        def set_videos(paths):
            holder.repo = TestSwitchExternalManagerEndpoint._FakeRepo(paths)

        holder.write_config = write_config
        holder.set_videos = set_videos
        holder.read_config = lambda: json.loads(config_path.read_text())
        return holder

    def test_mixed_only_offline_deleted(self, client, env):
        """混合可寫 + 離線：只刪離線卡，可寫 config 條目 + 卡零影響。"""
        env.write_config([
            {"path": "file:///D:/writable_src", "readonly": False},
            {"path": "file:///D:/ro_src", "readonly": True},
        ], external_manager="off")
        env.set_videos([
            "file:///D:/writable_src/A/A.strm",
            "file:///D:/ro_src/B/B.strm",
        ])

        resp = client.post("/api/config/switch-external-manager",
                           json={"external_manager": "jellyfin"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["removed_sources"] == 1
        assert body["deleted_cards"] == 1
        assert body["external_manager"] == "jellyfin"

        # delete_by_paths 只收到離線來源下的卡
        assert env.repo.delete_calls == [["file:///D:/ro_src/B/B.strm"]]
        # 縮圖只對離線卡失效
        assert env.invalidated == ["file:///D:/ro_src/B/B.strm"]

        cfg = env.read_config()
        dirs = cfg["gallery"]["directories"]
        assert len(dirs) == 1
        assert dirs[0]["path"] == "file:///D:/writable_src"
        assert cfg["scraper"]["external_manager"] == "jellyfin"

    def test_nested_writable_under_readonly_not_deleted(self, client, env):
        """可寫來源夾在唯讀來源之下：可寫卡不得被誤刪（spec §90b(iv)-1 保證）。

        唯讀 file:///D:/media 之下巢狀一個可寫 file:///D:/media/local。唯讀卡（僅落
        唯讀前綴）該刪；可寫卡（同時落唯讀+可寫前綴）由可寫來源主張、零刪除。
        """
        env.write_config([
            {"path": "file:///D:/media", "readonly": True},
            {"path": "file:///D:/media/local", "readonly": False},
        ], external_manager="off")
        env.set_videos([
            "file:///D:/media/X/X.strm",          # 僅唯讀前綴 → 刪
            "file:///D:/media/local/Y/Y.strm",    # 同時落可寫前綴 → 保留
        ])

        resp = client.post("/api/config/switch-external-manager",
                           json={"external_manager": "jellyfin"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # 只刪唯讀-only 卡，可寫巢狀卡零刪除
        assert env.repo.delete_calls == [["file:///D:/media/X/X.strm"]]
        assert body["deleted_cards"] == 1
        assert env.invalidated == ["file:///D:/media/X/X.strm"]

        # config：唯讀條目移除、可寫巢狀條目保留
        cfg = env.read_config()
        paths = [d["path"] for d in cfg["gallery"]["directories"]]
        assert paths == ["file:///D:/media/local"]
        assert cfg["scraper"]["external_manager"] == "jellyfin"


    def test_refuses_when_generate_in_progress(self, client, env, monkeypatch):
        """Finding 2：generate 進行中切換 → success:False + reason，零 DB/config 變更。

        PR #93 P1：改用雙向互斥 try_begin_switch（generate 在飛時回 False = 拒絕切換）。
        """
        env.write_config([
            {"path": "file:///D:/ro_src", "readonly": True},
        ], external_manager="off")
        env.set_videos(["file:///D:/ro_src/B/B.strm"])
        # 產生進行中 → try_begin_switch 回 'generate_in_progress'（generate token 已登記）
        monkeypatch.setattr("web.routers.config.try_begin_switch", lambda: "generate_in_progress")

        resp = client.post("/api/config/switch-external-manager",
                           json={"external_manager": "jellyfin"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["reason"] == "generate_in_progress"
        # 早退：零 DB 刪除、config 未變（external_manager 仍 off、離線來源仍在）
        assert env.repo.delete_calls == []
        cfg = env.read_config()
        assert cfg["scraper"]["external_manager"] == "off"
        assert len(cfg["gallery"]["directories"]) == 1


    def test_unc_prefix_boundary_no_valueerror(self, client, env):
        """UNC 前綴邊界（唯讀主場景）：離線來源 \\\\nas\\media，卡落其下命中且不拋 ValueError。"""
        from core.path_utils import coerce_to_file_uri
        card = coerce_to_file_uri(r"\\nas\media\ABC-001\ABC-001.strm")
        env.write_config([
            {"path": r"\\nas\media", "readonly": True},
        ], external_manager="off")
        env.set_videos([card])

        resp = client.post("/api/config/switch-external-manager",
                           json={"external_manager": "jellyfin"})

        assert resp.status_code == 200  # 無 ValueError
        assert resp.json()["deleted_cards"] == 1
        assert env.repo.delete_calls == [[card]]


class TestRewriteStrmEndpoint:
    """POST /api/config/rewrite-strm 端點測試（TASK-90c-T6）

    改路徑規則 → 就地改寫使用者媒體庫既有 .strm（依當前 strm_path_mappings 重套播放端
    路徑）。只覆寫一行純文字，不刪檔、不動 nfo/封面、不改 DB path、不重刮。

    真 config.json（CONFIG_PATH monkeypatch）供端點讀當前 scraper 設定；DB 側 mock
    （呼叫處 binding web.routers.config.VideoRepository）；.strm/.nfo/封面 為真 temp 檔
    （不 mock _write_strm，讀回檔案斷言單行/無 BOM/映射正確）。
    """

    class _FakeRepo:
        """假 VideoRepository：get_all 回設定的片；upsert 為 spy（斷言不被呼叫）。"""
        def __init__(self, videos):
            self._videos = list(videos)
            self.upsert_calls = []

        def get_all(self):
            return list(self._videos)

        def upsert(self, v):
            self.upsert_calls.append(v)

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        import types
        from core.path_utils import to_file_uri

        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        default_path.write_text(json.dumps({"general": {}}))

        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        monkeypatch.setattr("web.routers.config.get_db_path", lambda: tmp_path / "videos.db")
        monkeypatch.setattr("web.routers.config.init_db", lambda *a, **k: None)

        src_root = tmp_path / "src"      # 映射本機前綴
        lib_root = tmp_path / "library"  # 輸出媒體庫
        src_root.mkdir()
        lib_root.mkdir()
        remote_prefix = "/volume1/movies"

        holder = types.SimpleNamespace(
            repo=None, config_path=config_path,
            src_root=src_root, remote_prefix=remote_prefix,
        )
        monkeypatch.setattr("web.routers.config.VideoRepository", lambda *a, **k: holder.repo)

        def write_config(external_manager="jellyfin", with_mapping=True, filename_format="{num}"):
            mappings = {str(src_root): remote_prefix} if with_mapping else {}
            config_path.write_text(json.dumps({
                "scraper": {
                    "external_manager": external_manager,
                    "strm_path_mappings": mappings,
                    "filename_format": filename_format,
                },
            }))

        def make_movie(name, strm_stem=None, strm_content="OLD-CONTENT",
                       with_nfo=False, with_cover=False):
            """建一個單片夾，內含既有 .strm（可選 nfo/封面）。回 (video_ns, movie_dir)。"""
            movie_dir = lib_root / name
            movie_dir.mkdir()
            source_fs = src_root / name / f"{name}.mp4"
            extras = {}
            if strm_stem is None:
                strm_stem = name
            strm = movie_dir / f"{strm_stem}.strm"
            strm.write_text(strm_content, encoding="utf-8")
            extras["strm"] = strm
            if with_nfo:
                nfo = movie_dir / f"{name}.nfo"
                nfo.write_text("<movie>original</movie>", encoding="utf-8")
                extras["nfo"] = nfo
            if with_cover:
                cover = movie_dir / f"{name}.jpg"
                cover.write_bytes(b"\xff\xd8\xff-fake-jpeg")
                extras["cover"] = cover
            v = types.SimpleNamespace(
                path=to_file_uri(str(source_fs)),
                output_dir=to_file_uri(str(movie_dir)),
            )
            return v, movie_dir, extras

        def make_empty_movie(name):
            """已產出（output_dir 非空）但夾內無 .strm。"""
            movie_dir = lib_root / name
            movie_dir.mkdir()
            source_fs = src_root / name / f"{name}.mp4"
            v = types.SimpleNamespace(
                path=to_file_uri(str(source_fs)),
                output_dir=to_file_uri(str(movie_dir)),
            )
            return v, movie_dir

        def make_unproduced(name):
            """未產出骨架 row：output_dir 空。"""
            source_fs = src_root / name / f"{name}.mp4"
            return types.SimpleNamespace(path=to_file_uri(str(source_fs)), output_dir="")

        def set_videos(videos):
            holder.repo = TestRewriteStrmEndpoint._FakeRepo(videos)

        holder.write_config = write_config
        holder.make_movie = make_movie
        holder.make_empty_movie = make_empty_movie
        holder.make_unproduced = make_unproduced
        holder.set_videos = set_videos
        holder.expected_mapped = lambda name: f"{remote_prefix}/{name}/{name}.mp4"
        return holder

    def test_multi_video_rewrite_correct(self, client, env):
        """多片改寫：各自 .strm 內容為新映射路徑、單行、無 BOM、rewritten 計數正確。"""
        env.write_config(external_manager="jellyfin", with_mapping=True)
        v1, _, e1 = env.make_movie("ABC-001")
        v2, _, e2 = env.make_movie("XYZ-999")
        env.set_videos([v1, v2])

        resp = client.post("/api/config/rewrite-strm")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["rewritten"] == 2
        for name, extras in [("ABC-001", e1), ("XYZ-999", e2)]:
            raw = extras["strm"].read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf")   # 無 BOM
            text = raw.decode("utf-8")
            assert "\n" not in text                       # 單行
            assert text == env.expected_mapped(name)      # 正確映射後路徑


    def test_codex_p1_filename_format_and_mapping_both_changed(self, client, env):
        """Codex P1：同次改 strm_path_mappings + filename_format → 仍 glob 命中磁碟既有
        .strm（不依當前 filename_format 重建）→ 改寫該既有檔、不新增第二份、不 miss。"""
        # 磁碟上的既有 strm stem 與當前 filename_format 完全不符（模擬舊 config 產生）
        env.write_config(external_manager="jellyfin", with_mapping=True,
                         filename_format="{num}-{title}-{actor}")
        v1, movie_dir, e1 = env.make_movie("ABC-001", strm_stem="LEGACY-OLD-NAME")
        env.set_videos([v1])

        resp = client.post("/api/config/rewrite-strm")

        assert resp.json()["rewritten"] == 1
        strms = list(movie_dir.glob("*.strm"))
        assert len(strms) == 1                              # 仍只有一個 .strm（不新增第二份）
        assert strms[0].name == "LEGACY-OLD-NAME.strm"      # 改寫的是既有檔
        assert strms[0].read_text(encoding="utf-8") == env.expected_mapped("ABC-001")


    def test_dry_run_counts_and_writes_nothing(self, client, env):
        """dry_run=true → 回精確 count、零檔案寫入（.strm 內容不變）。"""
        env.write_config(external_manager="jellyfin", with_mapping=True)
        v1, _, e1 = env.make_movie("ABC-001", strm_content="UNTOUCHED-DRY")
        v2, _, e2 = env.make_movie("XYZ-999", strm_content="UNTOUCHED-DRY2")
        env.set_videos([v1, v2])

        resp = client.post("/api/config/rewrite-strm?dry_run=true")

        body = resp.json()
        assert body == {"success": True, "count": 2}
        assert e1["strm"].read_text(encoding="utf-8") == "UNTOUCHED-DRY"
        assert e2["strm"].read_text(encoding="utf-8") == "UNTOUCHED-DRY2"


    def test_mapped_output_dir_reverse_mapped_before_glob(self, tmp_path, monkeypatch):
        """PR#93 Codex P2：WSL+UNC mapped 輸出根 → output_dir 存映射端 URI，
        _collect_strm_targets 需 reverse-map 回本機實際掛載點才 glob 得到 .strm。

        無此反解時（舊 bug）：uri_to_fs_path 直解到映射端 //NAS/... glob 落空 → count 0 →
        改映射後既有 strm 永不改寫。直接測 module 函式，精準鎖住反解邏輯。
        """
        import types
        import core.path_utils as path_utils_module
        from core.path_utils import to_file_uri
        from web.routers import config as config_module

        # 環境無關關鍵：to_file_uri() 的 mapping 分支、_collect_strm_targets 的
        # reverse-map guard 都各自讀自己模組的 CURRENT_ENV 全域（import 時值拷貝，
        # 非同一個 binding）。兩處都要釘成 'wsl' 才能在純 Linux CI 上重現「WSL+UNC
        # mapped 輸出根」情境；只 patch 其中一個在本機 WSL 剛好巧合過（core.path_utils.
        # CURRENT_ENV 本來就是 'wsl'），但在 Linux runner 上 to_file_uri 會退回
        # fallback 分支、URI 裡不含 "NAS"，前置斷言就先炸。
        monkeypatch.setattr(path_utils_module, "CURRENT_ENV", "wsl")
        monkeypatch.setattr(config_module, "CURRENT_ENV", "wsl")

        # 本機實際寫檔位置（producer 真正落地處）
        lib = tmp_path / "library"
        movie = lib / "ABC-001"
        movie.mkdir(parents=True)
        (movie / "ABC-001.strm").write_text("x", encoding="utf-8")

        # gallery.path_mappings：本機 lib → 遠端 UNC（WSL↔本機 FS 映射）
        mappings = {str(lib): "//NAS/share/lib"}
        # output_dir 存映射端 URI（比照 producer output_uri = to_file_uri(root, mappings)）
        mapped_output_uri = to_file_uri(str(movie), mappings)
        assert "NAS" in mapped_output_uri  # 前置：真的映射到遠端了

        v = types.SimpleNamespace(
            path=to_file_uri(str(tmp_path / "src" / "ABC-001.mp4")),
            output_dir=mapped_output_uri,
        )
        repo = TestRewriteStrmEndpoint._FakeRepo([v])

        # 有映射 → 反解回本機、glob 命中
        assert len(config_module._collect_strm_targets(repo, mappings)) == 1
        # 無映射 → 直解到映射端 //NAS/... glob 落空（重現舊 bug、證明修法必要）
        repo2 = TestRewriteStrmEndpoint._FakeRepo([v])
        assert len(config_module._collect_strm_targets(repo2, {})) == 0

    def test_mapped_source_path_reverse_mapped_for_rewrite(self, tmp_path, monkeypatch):
        """PR#93 二審 P2：source path（v.path）在 WSL+gallery.path_mappings 下也存映射端 URI，
        _collect_strm_targets 須把它反解回原掃描路徑再傳 _write_strm——否則改寫拿映射端 UNC
        去比對 strm_path_mappings（本機前綴=原掃描路徑）對不上 → 改寫內容 ≠ 初次生成內容。
        """
        import types
        import core.path_utils as path_utils_module
        from core.path_utils import to_file_uri
        from web.routers import config as config_module

        monkeypatch.setattr(path_utils_module, "CURRENT_ENV", "wsl")
        monkeypatch.setattr(config_module, "CURRENT_ENV", "wsl")

        lib = tmp_path / "library"
        movie = lib / "ABC-001"
        movie.mkdir(parents=True)
        (movie / "ABC-001.strm").write_text("x", encoding="utf-8")

        src_root = tmp_path / "nas-mount"          # 原始掃描根（本機）
        src_fs = src_root / "ABC-001" / "ABC-001.mp4"
        # gallery.path_mappings：本機 lib + src_root 各映射遠端 UNC（producer 存 v.path/output_dir 用）
        mappings = {str(lib): "//NAS/share/lib", str(src_root): "//NAS/share/src"}
        v = types.SimpleNamespace(
            path=to_file_uri(str(src_fs), mappings),        # 映射端 URI（producer src_uri 存法）
            output_dir=to_file_uri(str(movie), mappings),
        )
        assert "NAS" in v.path  # 前置：v.path 真的存成映射端

        targets = config_module._collect_strm_targets(
            TestRewriteStrmEndpoint._FakeRepo([v]), mappings)
        assert len(targets) == 1
        _, source_fs_path = targets[0]
        # 關鍵：source path 反解回原掃描本機路徑（供 strm_path_mappings 比對），非映射端 UNC
        assert source_fs_path == str(src_fs)
        assert "NAS" not in source_fs_path


class TestGalleryOutputDirProgramAreaGuard:
    """TASK-153b-T3：gallery.output_dir 程式區守衛 + resolved response-only。"""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        seed = {
            "general": {"locale": "zh-TW", "theme": "light", "default_page": "search"},
            "gallery": {"output_dir": "", "output_filename": "gallery_output.html"},
            "scraper": {},
            "search": {},
            "source_links": {},
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "showcase": {},
            "sources": [],
            "thumbnail_cache_enabled": False,
            "metatube": {},
        }
        config_path.write_text(json.dumps(seed), encoding="utf-8")
        default_path.write_text(json.dumps(seed), encoding="utf-8")
        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        return {"config_path": config_path, "seed": seed}

    def _payload(self, seed, output_dir):
        body = json.loads(json.dumps(seed))
        body.setdefault("gallery", {})["output_dir"] = output_dir
        return body

    def test_relative_dot_output_rejected(self, client, env):
        """./output → 落在程式區 → 拒絕。"""
        resp = client.put("/api/config", json=self._payload(env["seed"], "./output"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["reason"] == "gallery_output_in_program_area"
        assert isinstance(body.get("error"), str) and body["error"].strip()


    def test_absolute_outside_accepted(self, client, env, tmp_path):
        outside = str(tmp_path / "external_gallery")
        resp = client.put("/api/config", json=self._payload(env["seed"], outside))
        body = resp.json()
        assert body["success"] is True
        saved = json.loads(env["config_path"].read_text(encoding="utf-8"))
        assert saved["gallery"]["output_dir"] == outside


    def test_get_resolved_gallery_output_path_empty_follows_data_root(self, client, env):
        from core.data_root import get_data_root
        resp = client.get("/api/config")
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["gallery"]["output_dir"] == ""
        assert "resolved" in body
        assert body["resolved"]["gallery_output_path"] == str(get_data_root())
        # resolved 不在 data 裡
        assert "resolved" not in body["data"]
        assert "gallery_output_path" not in (body["data"].get("gallery") or {})


class TestNfoTitleFormatConfigGuard:
    """TASK-154b-T5：PUT /api/config 驗證 NFO 標題格式。"""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        default_path = tmp_path / "config.default.json"
        seed = {
            "general": {"locale": "zh-TW", "theme": "light", "default_page": "search"},
            "gallery": {"output_dir": "", "output_filename": "gallery_output.html"},
            "scraper": {},
            "search": {},
            "source_links": {},
            "translate": {
                "enabled": False,
                "provider": "ollama",
                "batch_size": 10,
                "ollama": {"url": "http://localhost:11434", "model": "qwen3:8b"},
                "gemini": {"api_key": "", "model": "gemini-flash-lite-latest"},
                "openai": {"base_url": "", "api_key": "", "model": "gpt-4o-mini",
                           "use_custom_model": False},
            },
            "showcase": {},
            "sources": [],
            "thumbnail_cache_enabled": False,
            "metatube": {},
        }
        config_path.write_text(json.dumps(seed), encoding="utf-8")
        default_path.write_text(json.dumps(seed), encoding="utf-8")
        monkeypatch.setattr("core.config.CONFIG_PATH", config_path)
        monkeypatch.setattr("core.config.CONFIG_DEFAULT_PATH", default_path)
        monkeypatch.setattr("web.routers.config._reset_translate_service", lambda: None)
        return {"config_path": config_path, "seed": seed}

    def _payload(self, seed, nfo_title_format):
        body = json.loads(json.dumps(seed))
        body.setdefault("scraper", {})["nfo_title_format"] = nfo_title_format
        return body

    def test_put_config_rejects_invalid_nfo_title_format(self, client, env):
        """缺 {num} → 驗證拒絕、返回 reason 與 error，且設定未落地。"""
        resp = client.put("/api/config", json=self._payload(env["seed"], "{title}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["reason"] == "nfo_title_format_invalid"
        assert body["error"] == "格式必須包含恰好一個 {num}"

        # 重新 GET 確認設定未落地
        get_resp = client.get("/api/config")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["scraper"]["nfo_title_format"] != "{title}"


    def test_put_config_accepts_reordered_custom_nfo_title_format(self, client, env):
        """合法格式（順序互換＋含額外變數）→ 存檔成功並可讀回。"""
        custom_fmt = "{title}-{num}-{actor}-{maker}-{date}"
        resp = client.put("/api/config", json=self._payload(env["seed"], custom_fmt))
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        get_resp = client.get("/api/config")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["scraper"]["nfo_title_format"] == custom_fmt
