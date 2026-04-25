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
    "rescrape_actress",
    "list_actresses",
    "alias_crud_read",
    "alias_crud_write",
    "alias_search_online",
    "fetch_samples",
    "list_actress_photo_candidates",
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

    def test_tools_count_is_29(self, client):
        data = client.get("/api/capabilities").json()
        assert len(data["tools"]) == 29

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
