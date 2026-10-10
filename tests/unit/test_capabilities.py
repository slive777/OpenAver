"""測試 GET /api/capabilities"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

import core.access_auth as access_auth


@pytest.fixture(autouse=True)
def auth_db(tmp_path, monkeypatch):
    """GET /api/capabilities 冷啟動時會呼叫 load_snapshot()（core/access_auth.py），
    未 mock 前連上 output/openaver.db。同手法見
    tests/integration/test_capabilities_auth.py 的 auth_db fixture。"""
    db_path = tmp_path / "access.db"
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: db_path)
    access_auth.ensure_schema()
    access_auth.reset_state_for_tests()
    yield db_path
    access_auth.reset_state_for_tests()


@pytest.fixture
def client():
    from web.app import app
    return TestClient(app)


REQUIRED_TOP_LEVEL_FIELDS = [
    "schema_version",
    "name",
    "version",
    "base_url",
    "description",
    "skill_setup",
    "quick_check",
    "network",
    "agent_instructions",
    "image_display",
    "error_format",
    "tools",
    "examples",
    "notes",
]

EXPECTED_TOOL_NAMES = {
    "search",
    "batch_search",
    "scrape_single",
    "generate_gallery",
    "local_status",
    "parse_filename",
    "enrich_single",
    "batch_enrich",
    "collection_sql",
    "collection_analysis",
    "collection_analysis_groups",
    "fix_numbers_preview",
    "fix_numbers_apply",
    "proxy_image",
    "jellyfin_check",
    "user_tags",
    "get_user_tags",
    "user_rating",
    "showcase_videos",
    "showcase_video",
    "favorite_actress",
    "get_actress",
    "unfavorite_actress",
    "custom_source_upload",
    "custom_source_verify",
    "custom_sources_list",
    "custom_source_remove",
    "list_actresses",
    "list_library_actresses",
    "alias_crud_read",
    "alias_crud_write",
    "alias_search_online",
    "fetch_samples",
    "list_actress_photo_candidates",
    "set_actress_photo",
    "get_notifications",
    "mark_notifications_read",
    "clear_notifications",
    "similar_covers_by_number",
    "similar_covers",
    "tag_alias_crud_read",
    "tag_alias_crud_write",
    "tags_top",
    "scraper_sources_list",
    "video_rescrape_with_source",
    "preview_actress_sources",
    "submit_actress",
    "upload_actress_photo",
}

REQUIRED_TOOL_FIELDS = [
    "name",
    "description",
    "method",
    "path",
    "input_schema",
    "output_schema",
    "example",
]


class TestCapabilitiesEndpoint:

    def test_http_200(self, client):
        response = client.get("/api/capabilities")
        assert response.status_code == 200

    def test_top_level_fields_exist(self, client):
        data = client.get("/api/capabilities").json()
        for field in REQUIRED_TOP_LEVEL_FIELDS:
            assert field in data, f"Missing top-level field: {field}"

    def test_version_matches_core_version(self, client):
        from core.version import __version__
        data = client.get("/api/capabilities").json()
        assert data["version"] == __version__

    def test_base_url_no_trailing_slash(self, client):
        data = client.get("/api/capabilities").json()
        assert not data["base_url"].endswith("/"), "base_url must not have trailing slash"

    def test_agent_instructions_fetch_method_curl(self, client):
        data = client.get("/api/capabilities").json()
        assert data["agent_instructions"]["fetch_method"] == "curl"

    def test_error_format_http_codes_exist(self, client):
        data = client.get("/api/capabilities").json()
        assert "http_codes" in data["error_format"]
        assert isinstance(data["error_format"]["http_codes"], dict)

    def test_error_format_retry_hint_exist(self, client):
        data = client.get("/api/capabilities").json()
        assert "retry_hint" in data["error_format"]

    def test_tools_count_is_40(self, client):
        data = client.get("/api/capabilities").json()
        assert len(data["tools"]) == 48

    def test_all_tool_names_present(self, client):
        data = client.get("/api/capabilities").json()
        names = {t["name"] for t in data["tools"]}
        assert names == EXPECTED_TOOL_NAMES

    def test_list_library_actresses_read_only_no_confirmation_key(self, client):
        """AC-7.2：唯讀端點不需要 confirmation_required。"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "list_library_actresses")
        assert tool.get("side_effect") is False
        assert "confirmation_required" not in tool

    def test_favorite_actress_description_mentions_concurrency_limit(self, client):
        """AC-7.4：收藏端點的 capability 說明必須寫明序列呼叫或併發上限 2。"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "favorite_actress")
        assert "併發 2" in tool["description"] or "序列呼叫" in tool["description"]

    def test_submit_actress_and_upload_confirmation_required_true(self, client):
        """submit_actress／upload_actress_photo 皆是覆蓋性寫入，AI 呼叫前必須先取得使用者確認。"""
        data = client.get("/api/capabilities").json()
        tools = {t["name"]: t for t in data["tools"]}
        for name in ("submit_actress", "upload_actress_photo"):
            assert tools[name].get("confirmation_required") is True, name
        assert "upload_actress_photo" in tools["submit_actress"]["description"]
        assert "10MB" in tools["upload_actress_photo"]["description"]
        assert "50M" in tools["upload_actress_photo"]["description"]

    def test_no_server_mode_toggle_exposed(self, client):
        """AC-A7（TASK-80a-T5）：LAN 伺服器模式翻轉**不得**揭露給 AI agent。

        server_mode 沿用既有 config 端點、本就無新 capability 條目；本守衛是回歸保險：
        若日後有人把 server_mode 翻轉做成 agent tool（或揭露 config/general 寫入路徑），
        agent 可能把機器切成對外開放 → 整份 capabilities 回應不得觸及 server_mode 或
        config/general 寫入端點。整串序列化比對（涵蓋 tools / instructions / 任何欄位）。
        """
        import json
        blob = json.dumps(client.get("/api/capabilities").json(), ensure_ascii=False).lower()
        assert "server_mode" not in blob, "capabilities 不得揭露 server_mode 翻轉"
        assert "/api/config/general" not in blob, "capabilities 不得揭露 config/general 寫入端點"

    def test_no_auto_organize_control_exposed(self, client):
        """spec-144（TASK-144 pre-merge）：自動整理的**控制面**不得揭露給 AI agent。

        本 branch 新增四支端點（`auto-organize/config` / `run-now` /
        `use-resolved-folder` / `status`），過 `capabilities.md`「揭露判斷四問」後
        **四支全部不揭露**，理由與 `test_no_server_mode_toggle_exposed` 同一條：

        - `config` 是一個**持續性的設定翻轉**——打開之後每 12 小時無人值守地
          對使用者的最愛資料夾**搬檔改名**。那是人的決定，不是 agent 的。
        - `run-now` 是同一件事的立即版，一次可能動到整個資料夾（owner 的測試資料夾
          就有 1965 個影片檔），而且 agent 對個別檔案**沒有任何取捨餘地**。
        - agent 想達成同樣結果，既有的 `POST /api/scrape-single`（已揭露、已標
          `confirmation_required`）本來就做得到，而且是**逐片、可審**的——
          揭露 `run-now` 只會讓它失去控制權，不會讓它更快更準（四問的第 2 問答「沒有優勢」）。
        - `status` 純讀，但沒有任何 agent 可據以行動的價值。

        這支守衛是回歸保險：整串序列化比對，涵蓋 tools／instructions／任何欄位。
        """
        import json
        blob = json.dumps(client.get("/api/capabilities").json(), ensure_ascii=False).lower()
        assert "auto-organize" not in blob, "capabilities 不得揭露自動整理的控制端點"
        assert "auto_organize" not in blob, "capabilities 不得揭露自動整理的控制端點"

    def test_each_tool_has_required_fields(self, client):
        data = client.get("/api/capabilities").json()
        for tool in data["tools"]:
            for field in REQUIRED_TOOL_FIELDS:
                assert field in tool, f"Tool '{tool.get('name')}' missing field: {field}"

    def test_each_tool_input_schema_type_object(self, client):
        data = client.get("/api/capabilities").json()
        for tool in data["tools"]:
            schema = tool["input_schema"]
            assert schema.get("type") == "object", (
                f"Tool '{tool['name']}' input_schema.type must be 'object', got {schema.get('type')}"
            )
            assert "properties" in schema, (
                f"Tool '{tool['name']}' input_schema must have 'properties'"
            )

    def test_scrape_single_side_effect_flags(self, client):
        data = client.get("/api/capabilities").json()
        scrape = next(t for t in data["tools"] if t["name"] == "scrape_single")
        assert scrape.get("side_effect") is True
        assert scrape.get("confirmation_required") is True
        assert scrape.get("idempotent") is False
        assert scrape.get("retry_safe") is False

    def test_tool_example_url_not_hardcoded_localhost(self, client):
        """example URL 必須用 TestClient base_url，不含 hardcoded localhost:38741"""
        data = client.get("/api/capabilities").json()
        for tool in data["tools"]:
            assert "localhost:38741" not in tool["example"], (
                f"Tool '{tool['name']}' example contains hardcoded localhost:38741"
            )

    def test_tool_example_url_contains_base_url(self, client):
        """example URL 必須含動態 base_url"""
        data = client.get("/api/capabilities").json()
        base_url = data["base_url"]
        for tool in data["tools"]:
            assert base_url in tool["example"] or tool["example"].startswith("curl"), (
                f"Tool '{tool['name']}' example does not reference base_url"
            )

    def test_agent_instructions_example_uses_base_url(self, client):
        """agent_instructions.example 使用 request.base_url"""
        data = client.get("/api/capabilities").json()
        example = data["agent_instructions"]["example"]
        base_url = data["base_url"]
        assert base_url in example, \
            "agent_instructions.example 應包含 request.base_url"

    def test_integration_notes_exist(self, client):
        data = client.get("/api/capabilities").json()
        assert "integration_notes" in data

    def test_notes_is_list(self, client):
        data = client.get("/api/capabilities").json()
        assert isinstance(data["notes"], list)
        assert len(data["notes"]) > 0

    def test_examples_is_list(self, client):
        data = client.get("/api/capabilities").json()
        assert isinstance(data["examples"], list)
        assert len(data["examples"]) > 0

    def test_schema_version_is_v1(self, client):
        data = client.get("/api/capabilities").json()
        assert data["schema_version"] == "v1"

    def test_name_is_openaver(self, client):
        data = client.get("/api/capabilities").json()
        assert data["name"] == "OpenAver"

    def test_enrich_single_has_side_effect_flags(self, client):
        """enrich_single 有正確的 side_effect 旗標"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        assert tool.get("side_effect") is True
        assert tool.get("idempotent") is True
        assert tool.get("retry_safe") is True
        assert tool.get("confirmation_required") is False

    def test_enrich_single_input_schema(self, client):
        """enrich_single input_schema 含必要欄位"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        props = tool["input_schema"]["properties"]
        for key in ["file_path", "number", "mode", "write_nfo", "write_cover",
                    "write_extrafanart", "overwrite_existing"]:
            assert key in props, f"enrich_single missing input property: {key}"
        assert "file_path" in tool["input_schema"]["required"]

    def test_collection_sql_has_database_schema(self, client):
        """collection_sql 含 database_schema 且有 videos 表"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "collection_sql")
        assert "database_schema" in tool, "collection_sql 缺少 database_schema"
        assert "videos" in tool["database_schema"], "database_schema 缺少 videos 表"

    def test_collection_sql_has_sql_examples(self, client):
        """collection_sql 含 sql_examples 且至少 4 個"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "collection_sql")
        assert "sql_examples" in tool, "collection_sql 缺少 sql_examples"
        assert len(tool["sql_examples"]) >= 4, (
            f"sql_examples 至少需要 4 個，目前只有 {len(tool['sql_examples'])} 個"
        )

    def test_examples_count_at_least_8(self, client):
        """examples 陣列至少 8 個 scenario"""
        data = client.get("/api/capabilities").json()
        assert len(data["examples"]) >= 8, (
            f"examples 至少需要 8 個，目前只有 {len(data['examples'])} 個"
        )

    def test_translate_not_in_tools(self, client):
        """translate 不揭露"""
        data = client.get("/api/capabilities").json()
        names = {t["name"] for t in data["tools"]}
        assert "translate" not in names

    def test_clip_lifecycle_endpoints_not_in_tools(self, client):
        """CLIP enable/disable/status/test-inference 為 UI flow，不揭露給 AI agent。"""
        resp = client.get("/api/capabilities")
        names = {t["name"] for t in resp.json()["tools"]}
        for forbidden in ("clip_enable", "clip_disable", "clip_status", "clip_test_inference"):
            assert forbidden not in names

    def test_enrich_single_example_contains_number(self, client):
        """F5: enrich_single example curl body 必須含 number 欄位（required 欄位）"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        example = tool.get("example", "")
        assert "number" in example, (
            f"enrich_single example 缺少 'number' 欄位（required），example: {example}"
        )

    def test_user_tags_tool(self, client):
        """user_tags tool 有正確的 side_effect 旗標"""
        data = client.get("/api/capabilities").json()
        tool = next((t for t in data["tools"] if t["name"] == "user_tags"), None)
        assert tool is not None, "user_tags tool 不存在"
        assert tool.get("side_effect") is True
        assert tool.get("confirmation_required") is False
        assert tool.get("retry_safe") is True

    def test_user_rating_tool(self, client):
        """user_rating tool（TASK-123-T2）：批次精選端點，confirmation_required 必為 True，
        description 須含風險說明，且與 user_tags 的 ★ 標籤區分開來。"""
        data = client.get("/api/capabilities").json()
        tool = next((t for t in data["tools"] if t["name"] == "user_rating"), None)
        assert tool is not None, "user_rating tool 不存在"
        assert tool["method"] == "POST"
        assert tool["path"] == "/api/user-rating"
        assert tool.get("side_effect") is True
        assert tool.get("confirmation_required") is True
        assert tool.get("retry_safe") is True
        assert "批次" in tool["description"] or "一鍵復原" in tool["description"] or "取消" in tool["description"]
        assert "user_tags" in tool["description"] or "★" in tool["description"]
        assert "showcase/videos" in tool.get("also_see", "")

    def test_set_actress_photo_side_effect_flags(self, client):
        """set_actress_photo 有正確的 side_effect / confirmation_required 旗標"""
        data = client.get("/api/capabilities").json()
        tools = {t["name"]: t for t in data["tools"]}
        tool = tools.get("set_actress_photo")
        assert tool is not None, "set_actress_photo tool 不存在"
        assert tool.get("side_effect") is True
        assert tool.get("confirmation_required") is True
        assert "可逆" in tool["description"] or "覆蓋" in tool["description"]

    def test_video_rescrape_side_effect_flags(self, client):
        """video_rescrape_with_source 重刮覆蓋面：side_effect + confirmation_required + 不可逆風險描述"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "video_rescrape_with_source")
        assert tool.get("side_effect") is True
        assert tool.get("confirmation_required") is True
        assert tool.get("idempotent") is False
        assert tool.get("retry_safe") is False
        assert tool["path"] == "/api/enrich-single"
        assert "不可逆" in tool["description"] or "覆蓋" in tool["description"]
        props = tool["input_schema"]["properties"]
        for key in ["file_path", "number", "source", "mode",
                    "overwrite_existing", "write_nfo", "write_cover"]:
            assert key in props, f"missing input property: {key}"
        assert props["overwrite_existing"]["default"] is True
        # Codex P1：mode/overwrite_existing 必須 required，否則最小合法呼叫會落回端點預設
        # （fill_missing / overwrite=false）而非重刮覆蓋語意，silently 不覆蓋。
        required = tool["input_schema"]["required"]
        assert "mode" in required and "overwrite_existing" in required


class TestCapabilitiesDescriptionHonesty:
    """TASK-147d-T2：scrape_single / enrich_single 來源選擇語意誠實度文字"""

    def test_scrape_single_description_explains_no_metadata_source_selection(self, client):
        data = client.get("/api/capabilities").json()
        scrape = next(t for t in data["tools"] if t["name"] == "scrape_single")
        desc = scrape["description"]
        assert "完整番號格式" in desc
        assert "不是完整番號格式" in desc
        assert "不跨站合併" in desc
        assert "無碼模式開啟時例外" in desc

    def test_enrich_single_source_description_explains_auto_default_consequence(self, client):
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        desc = tool["input_schema"]["properties"]["source"]["description"]
        assert "每個欄位各自取第一個有值的來源" in desc
        assert "不是「整包用第一家的資料」" in desc

    def test_enrich_single_metadata_description_does_not_deny_fuzzy_carriers(self, client):
        """pre-merge Opus branch review P2-1：147c 新寫的文案宣稱「關鍵字／模糊搜尋與
        javlibrary 多版本清單不會帶 _summary／_rating」，但 search_partial／search_prefix／
        _javbus_keyword_search 全部經 core.scraper.search_jav（internal_nfo_carriers 無條件
        注入），實際上會帶。守住「文案不再宣稱模糊/關鍵字搜尋不帶 carrier」這個否定宣稱不
        再出現，而不是逐字鎖新句子（會變成下一次改寫的絆腳石）。"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        desc = tool["input_schema"]["properties"]["metadata"]["description"]
        # 舊的假否定宣稱：不可再出現
        assert "關鍵字／模糊搜尋與 javlibrary 多版本清單不會帶" not in desc
        assert "有條件地帶" not in desc
        # 正確事實：判準是「有沒有經過 search_jav」，不是搜尋模式名稱
        assert "search_jav" in desc


class TestCapabilitiesSourceEnum:
    """TASK-61a-4：4 處 source enum 由 get_source_enum() 生成（無硬編碼）"""

    def _tools_by_name(self, client):
        data = client.get("/api/capabilities").json()
        return {t["name"]: t for t in data["tools"]}

    def test_search_source_enum_matches_helper_without_auto(self, client):
        """search 端點 source enum == get_source_enum(False)，且不含 auto"""
        from core.source_config import get_source_enum
        tool = self._tools_by_name(client)["search"]
        enum = tool["input_schema"]["properties"]["source"]["enum"]
        assert enum == get_source_enum(include_auto=False)
        assert "auto" not in enum

    def test_enrich_single_source_enum_matches_helper_with_auto(self, client):
        """enrich_single source enum == get_source_enum(True)，且含 auto"""
        from core.source_config import get_source_enum
        tool = self._tools_by_name(client)["enrich_single"]
        enum = tool["input_schema"]["properties"]["source"]["enum"]
        assert enum == get_source_enum(include_auto=True)
        assert "auto" in enum

    def test_batch_enrich_default_source_enum_matches_helper_with_auto(self, client):
        """batch_enrich 預設 source enum == get_source_enum(True)"""
        from core.source_config import get_source_enum
        tool = self._tools_by_name(client)["batch_enrich"]
        enum = tool["input_schema"]["properties"]["source"]["enum"]
        assert enum == get_source_enum(include_auto=True)
        assert "auto" in enum

    def test_batch_enrich_per_item_source_enum_matches_helper_with_auto(self, client):
        """batch_enrich per-item source enum == get_source_enum(True)"""
        from core.source_config import get_source_enum
        tool = self._tools_by_name(client)["batch_enrich"]
        item_props = tool["input_schema"]["properties"]["items"]["items"]["properties"]
        enum = item_props["source"]["enum"]
        assert enum == get_source_enum(include_auto=True)
        assert "auto" in enum
