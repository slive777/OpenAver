"""測試 GET /api/capabilities"""
import re

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
    "ai_sample_embeddings",
    "ai_similar_test",
    "ai_similar_status",
    "ai_similar_index",
    "tag_alias_crud_read",
    "tag_alias_crud_write",
    "tags_top",
    "scraper_sources_list",
    "video_rescrape_with_source",
    "preview_actress_sources",
    "submit_actress",
    "upload_actress_photo",
    "video_title_writeback",
    "wishlist_add",
    "wishlist_membership",
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


    def test_top_level_fields_exist(self, client):
        data = client.get("/api/capabilities").json()
        for field in REQUIRED_TOP_LEVEL_FIELDS:
            assert field in data, f"Missing top-level field: {field}"


    def test_all_tool_names_present(self, client):
        data = client.get("/api/capabilities").json()
        names = {t["name"] for t in data["tools"]}
        assert names == EXPECTED_TOOL_NAMES


    def test_submit_actress_and_upload_confirmation_required_true(self, client):
        """submit_actress／upload_actress_photo 皆是覆蓋性寫入，AI 呼叫前必須先取得使用者確認。"""
        data = client.get("/api/capabilities").json()
        tools = {t["name"]: t for t in data["tools"]}
        for name in ("submit_actress", "upload_actress_photo"):
            assert tools[name].get("confirmation_required") is True, name
        assert "upload_actress_photo" in tools["submit_actress"]["description"]
        assert "10MB" in tools["upload_actress_photo"]["description"]
        assert "50M" in tools["upload_actress_photo"]["description"]

    def test_ai_index_tool_requires_confirmation(self, client):
        """建立索引會對使用者的外部端點發出約等於封面數的請求、換模型時覆蓋向量：AI 助理必須先問使用者。"""
        data = client.get("/api/capabilities").json()
        tools = {t["name"]: t for t in data["tools"]}
        assert tools["ai_similar_index"]["side_effect"] is True
        assert tools["ai_similar_index"]["confirmation_required"] is True


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


    def test_scrape_single_side_effect_flags(self, client):
        data = client.get("/api/capabilities").json()
        scrape = next(t for t in data["tools"] if t["name"] == "scrape_single")
        assert scrape.get("side_effect") is True
        assert scrape.get("confirmation_required") is True
        assert scrape.get("idempotent") is False
        assert scrape.get("retry_safe") is False


    def test_enrich_single_input_schema(self, client):
        """enrich_single input_schema 含必要欄位"""
        data = client.get("/api/capabilities").json()
        tool = next(t for t in data["tools"] if t["name"] == "enrich_single")
        props = tool["input_schema"]["properties"]
        for key in ["file_path", "number", "mode", "write_nfo", "write_cover",
                    "write_extrafanart", "overwrite_existing"]:
            assert key in props, f"enrich_single missing input property: {key}"
        assert "file_path" in tool["input_schema"]["required"]


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


class TestPreviewActressSourcesContract:
    """174-T6：preview_actress_sources 的 sources 說明鍵集合 == 預覽實際回傳鍵集合。"""

    def test_preview_actress_sources_schema_keys_match_orchestrator(self, client):
        tool = next(
            t for t in client.get("/api/capabilities").json()["tools"]
            if t["name"] == "preview_actress_sources"
        )
        m = re.match(r"\{([^}]*)\}", tool["output_schema"]["sources"])
        assert m, "output_schema.sources 開頭必須是 {鍵清單}"
        schema_keys = {k.strip() for k in m.group(1).split(",") if k.strip()}
        assert schema_keys

        with patch("core.scrapers.actress.xcity.scrape_xcity", return_value=None), \
                patch("core.scrapers.actress.wiki_ja.scrape_wiki_ja", return_value=None), \
                patch("core.scrapers.actress.graphis.scrape_graphis_photo", return_value=None), \
                patch("core.scrapers.actress.gfriends.lookup_gfriends", return_value=None), \
                patch("core.scrapers.actress.avbase.scrape_avbase", return_value=None):
            from core.scrapers.actress.orchestrator import get_actress_profile_preview
            actual_keys = set(get_actress_profile_preview("契約測試用名")["sources"])

        assert schema_keys == actual_keys, (
            f"schema={sorted(schema_keys)} actual={sorted(actual_keys)}"
        )


class TestTranslateTitleTools:
    """172-T7：標題寫回／書籤 tool 揭露與 needs_translate 文件。"""

    @staticmethod
    def _tools(client):
        return {t["name"]: t for t in client.get("/api/capabilities").json()["tools"]}


    def test_new_tools_match_registered_routes(self, client):
        registered = set()
        for r in client.app.routes:
            for m in getattr(r, "methods", None) or ():
                registered.add((m, getattr(r, "path", None)))
        tools = self._tools(client)
        for name in ("video_title_writeback", "wishlist_add", "wishlist_membership"):
            t = tools[name]
            assert (t["method"], t["path"]) in registered, name


