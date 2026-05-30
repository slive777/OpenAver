"""測試 GET /api/capabilities"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


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
    "showcase_videos",
    "showcase_video",
    "favorite_actress",
    "get_actress",
    "unfavorite_actress",
    "list_actresses",
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

    def test_tools_count_is_39(self, client):
        data = client.get("/api/capabilities").json()
        assert len(data["tools"]) == 39

    def test_all_tool_names_present(self, client):
        data = client.get("/api/capabilities").json()
        names = {t["name"] for t in data["tools"]}
        assert names == EXPECTED_TOOL_NAMES

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
