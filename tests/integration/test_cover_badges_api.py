"""TASK-121a-T5: GET /api/cover-badges/manifest 端點契約。

策略：TDD-lite。消費 core.cover_attributes.manifest_payload()，證明端點
沒有自己再硬編一份短名表。
"""


MANIFEST_PATH = "/api/cover-badges/manifest"
EXPECTED_KEYS = {
    "id",
    "canonical_tag",
    "display_name",
    "match_aliases",
    "display_order",
    "i18n_key",
    "supersedes",
}
EXPECTED_IDS = {"subtitle", "cracked", "ltx", "leaked", "4k", "vr"}
EXPECTED_DISPLAY_ORDER = {
    "subtitle": 1,  # 中字
    "cracked": 2,  # AI
    "ltx": 2,  # LTX
    "leaked": 2,  # LEAK
    "vr": 3,  # VR
    "4k": 4,  # 4K
}


class TestCoverBadgesManifest:
    """GET /api/cover-badges/manifest"""


    def test_display_name_and_match_aliases_literal_contract(self, client):
        """邊界 5b（BE-TEST-01）：寫死字面，對兩邊同時改錯仍敏感。"""
        data = client.get(MANIFEST_PATH).json()
        by_id = {item["id"]: item for item in data}
        assert by_id["cracked"]["display_name"] == "AI"
        assert by_id["leaked"]["display_name"] == "LEAK"
        assert "克破" in by_id["cracked"]["match_aliases"]
        assert by_id["subtitle"]["display_name"] == "中字"
        assert by_id["4k"]["display_name"] == "4K"
        assert by_id["vr"]["display_name"] == "VR"
        for item in data:
            assert item["match_aliases"][0] == item["canonical_tag"]
            assert isinstance(item["match_aliases"], list)

    def test_manifest_ltx_row_and_supersedes_contract(self, client):
        from core.cover_attributes import manifest_payload

        data = client.get(MANIFEST_PATH).json()
        assert {item["id"] for item in data} == EXPECTED_IDS
        assert len(data) == 6
        for item in data:
            assert item["display_order"] == EXPECTED_DISPLAY_ORDER[item["id"]]
        ids = [item["id"] for item in data]
        by_id = {item["id"]: item for item in data}
        ltx = by_id["ltx"]
        assert ltx["display_name"] == "LTX"
        assert ltx["match_aliases"][0] == "LTX"
        assert ltx["supersedes"] == ["cracked"]
        for item in data:
            if item["id"] != "ltx":
                assert item["supersedes"] == []
        assert ids.index("ltx") > ids.index("cracked")
        assert ids.index("ltx") < ids.index("leaked")
        assert data == manifest_payload()
