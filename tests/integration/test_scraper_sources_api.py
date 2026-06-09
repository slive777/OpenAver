"""TASK-61c-5 / 63c-2: GET /api/scraper-sources 端點測試。

過濾 = Rule 3：enabled=True AND is_beta=False AND manual_only=False AND
available=True。複用 get_enabled_source_ids（含 manual_only + available gate），
端點額外排除 is_beta。

63c-2：availability_map 由 metatube_state.availability_map() 注入（不再 None）。
斷線 → 回 {} → enabled metatube 被 gate 排除；連線 + provider available → 出現。
builtin bypass gate，始終出現。

注入自訂 sources 用 PUT /api/config → GET /api/scraper-sources 斷言過濾結果。
"""
import pytest

from core.metatube.state import metatube_state


@pytest.fixture(autouse=True)
def _reset_metatube_state():
    """metatube_state 是 process-global singleton；每個 test 前後 disconnect，
    避免跨 test 殘留連線狀態污染 availability gate（DoD risk (a)）。"""
    metatube_state.disconnect()
    yield
    metatube_state.disconnect()


def _base_config(client):
    return client.get("/api/config").json()["data"]


SOURCE_FIELDS = {"id", "display_name", "type", "enabled", "order", "is_censored"}


def test_200_and_schema(client, temp_config_path):
    """200 + response schema：sources list 每筆含 6 欄位 + total_enabled int。"""
    resp = client.get("/api/scraper-sources")
    assert resp.status_code == 200
    data = resp.json()

    assert "sources" in data and isinstance(data["sources"], list)
    assert "total_enabled" in data and isinstance(data["total_enabled"], int)
    for s in data["sources"]:
        assert set(s.keys()) == SOURCE_FIELDS
        assert isinstance(s["id"], str)
        assert isinstance(s["display_name"], str)
        assert isinstance(s["type"], str)
        assert isinstance(s["enabled"], bool)
        assert isinstance(s["order"], int)
        assert isinstance(s["is_censored"], bool)


def test_default_config_all_eight_builtin(client, temp_config_path):
    """B1 availability_map=None → 8 個預設 builtin（全 enabled、非 beta、非 manual）皆現。"""
    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert len(ids) == 8
    assert data["total_enabled"] == 8
    # builtin 全 enabled
    assert all(s["enabled"] is True for s in data["sources"])
    # 依 order 升冪
    orders = [s["order"] for s in data["sources"]]
    assert orders == sorted(orders)


def test_disabled_source_not_in_response(client, temp_config_path):
    """enabled=false 的 source 不出現。"""
    cfg = _base_config(client)
    target_id = cfg["sources"][0]["id"]
    cfg["sources"][0]["enabled"] = False
    assert client.put("/api/config", json=cfg).status_code == 200

    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert target_id not in ids
    assert data["total_enabled"] == 7


def test_beta_source_not_in_response(client, temp_config_path):
    """is_beta=true 的 source 不出現（即使 enabled=true）。"""
    cfg = _base_config(client)
    cfg["sources"].append(
        {
            "id": "mt_beta",
            "type": "metatube",
            "display_name_key": "",
            "display_name_raw": "Beta Source",
            "enabled": True,
            "order": len(cfg["sources"]),
            "config": {"censored_type": "censored"},
            "is_beta": True,
            "manual_only": False,
        }
    )
    assert client.put("/api/config", json=cfg).status_code == 200

    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert "mt_beta" not in ids
    # 8 builtin 仍在
    assert data["total_enabled"] == 8


def test_manual_only_source_not_in_response(client, temp_config_path):
    """manual_only=true 的 source 不出現（B4 預埋；B1 用構造 config 驗證）。"""
    cfg = _base_config(client)
    cfg["sources"].append(
        {
            "id": "mt_manual",
            "type": "metatube",
            "display_name_key": "",
            "display_name_raw": "Manual Only Source",
            "enabled": True,
            "order": len(cfg["sources"]),
            "config": {"censored_type": "censored"},
            "is_beta": False,
            "manual_only": True,
        }
    )
    assert client.put("/api/config", json=cfg).status_code == 200

    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert "mt_manual" not in ids
    assert data["total_enabled"] == 8


def _append_metatube_source(cfg, *, id="mt_active", name="Active Metatube",
                            censored_type="uncensored"):
    cfg["sources"].append(
        {
            "id": id,
            "type": "metatube",
            "display_name_key": "",
            "display_name_raw": name,
            "enabled": True,
            "order": len(cfg["sources"]),
            "config": {"censored_type": censored_type},
            "is_beta": False,
            "manual_only": False,
        }
    )
    return cfg


def test_disconnected_metatube_gated_out(client, temp_config_path):
    """63c-2：metatube 斷線（availability_map()=={}）→ enabled metatube source
    被 gate 排除（與 B1 不 gate 的舊行為相反）。builtin 8 個不受影響。"""
    cfg = _append_metatube_source(_base_config(client))
    assert client.put("/api/config", json=cfg).status_code == 200
    # autouse fixture 已 disconnect → availability_map() == {}

    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert "mt_active" not in ids
    assert data["total_enabled"] == 8  # 僅 8 builtin


def test_connected_available_metatube_appears(client, temp_config_path, monkeypatch):
    """63c-2：metatube 連線且 provider available → 出現在揭露清單。"""
    cfg = _append_metatube_source(_base_config(client))
    assert client.put("/api/config", json=cfg).status_code == 200
    monkeypatch.setattr(
        metatube_state, "availability_map", lambda: {"mt_active": True}
    )

    data = client.get("/api/scraper-sources").json()
    by_id = {s["id"]: s for s in data["sources"]}
    assert "mt_active" in by_id
    assert by_id["mt_active"]["display_name"] == "Active Metatube"  # render_name → display_name_raw
    assert by_id["mt_active"]["is_censored"] is False  # derive from config censored_type
    assert data["total_enabled"] == 9


def test_connected_but_unavailable_metatube_gated_out(client, temp_config_path, monkeypatch):
    """63c-2：metatube 連線但該 provider probe-failed（map 值 False）→ gate 排除。"""
    cfg = _append_metatube_source(_base_config(client))
    assert client.put("/api/config", json=cfg).status_code == 200
    monkeypatch.setattr(
        metatube_state, "availability_map", lambda: {"mt_active": False}
    )

    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert "mt_active" not in ids
    assert data["total_enabled"] == 8


def test_builtin_unaffected_by_availability_map(client, temp_config_path, monkeypatch):
    """63c-2：builtin 來源 bypass availability gate — 即使 map 為空也始終出現。"""
    monkeypatch.setattr(metatube_state, "availability_map", lambda: {})
    data = client.get("/api/scraper-sources").json()
    assert data["total_enabled"] == 8
    assert all(s["type"] != "metatube" for s in data["sources"])


def test_capability_count_unchanged_no_new_capability():
    """63c-2：零新增 capability（US6 / spec §5.6）— capabilities.py 無 metatube_status 等新名稱。"""
    import web.routers.capabilities as cap_mod
    src = __import__("inspect").getsource(cap_mod)
    # 不得新增 metatube 連線健康度 capability（spec US6 取消）
    assert "metatube_status" not in src
    assert "metatube_health" not in src


def test_javlibrary_excluded_from_scraper_sources(client):
    """T3 收尾(a)：javlibrary is_beta=True + manual_only=True，
    is_beta gate（scraper_sources.py:L58）自動排除 → 不出現在 /api/scraper-sources。"""
    data = client.get("/api/scraper-sources").json()
    ids = [s["id"] for s in data["sources"]]
    assert "javlibrary" not in ids
    assert data["total_enabled"] == 8  # 8 builtin 不受影響
