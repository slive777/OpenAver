import json

import pytest


def test_update_config(client, temp_config_path):
    """測試更新設定"""
    # 先獲取當前設定
    response = client.get("/api/config")
    current_config = response.json()["data"]
    
    # 修改設定
    current_config["gallery"]["output_dir"] = "../openaver_test_output"
    current_config["gallery"]["output_filename"] = "test.html"
    current_config["general"]["theme"] = "dark"
    
    # PUT 更新
    response = client.put("/api/config", json=current_config)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 再次獲取驗證
    response = client.get("/api/config")
    new_config = response.json()["data"]
    assert new_config["gallery"]["output_dir"] == "../openaver_test_output"
    assert new_config["gallery"]["output_filename"] == "test.html"
    assert new_config["general"]["theme"] == "dark"


def test_full_put_with_stale_snapshot_preserves_toggle_endpoint_write(client, temp_config_path):
    """oracle (b)／BE-CONFIG-05 重演（TASK-D3）：先讀 /api/config 拿到 toggle 前快照
    → 打專用端點把 disabled 切成別的值 → 用第一份快照打全量 PUT /api/config
    → 磁碟上的 focal_device 仍是端點寫入的新值，不被舊快照回捲。

    與 test_update_config_preserves_newer_focal_device_against_stale_full_save 互補：
    那支是手動 seed；本支真的走新端點，驗證「端點寫入＋全量 PUT 保留」串起來仍正確。
    """
    # 讀「toggle 之前」的快照（前端長駐 this.config 的模擬）
    snap_resp = client.get("/api/config")
    assert snap_resp.status_code == 200
    stale_snapshot = snap_resp.json()["data"]
    assert stale_snapshot["focal_device"]["disabled"] is False

    # 專用端點把 disabled 切成 true（並設 set_by_user）
    toggle_resp = client.put("/api/config/focal-device/disabled", json={"value": True})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["success"] is True

    with open(temp_config_path, 'r', encoding='utf-8') as f:
        after_toggle = json.load(f)
    assert after_toggle["focal_device"]["disabled"] is True
    assert after_toggle["focal_device"]["set_by_user"] is True

    # 用不相關欄位證明全量 PUT 本身有寫入（排除「整份存檔沒生效」假陽性）
    stale_snapshot = json.loads(json.dumps(stale_snapshot))
    stale_snapshot["gallery"]["output_dir"] = "../openaver_oracle_b_stale_save"

    put_resp = client.put("/api/config", json=stale_snapshot)
    assert put_resp.status_code == 200
    assert put_resp.json()["success"] is True

    with open(temp_config_path, 'r', encoding='utf-8') as f:
        persisted = json.load(f)

    # 端點寫入的新值存活，未被舊快照回捲
    assert persisted["focal_device"]["disabled"] is True
    assert persisted["focal_device"]["set_by_user"] is True
    assert persisted["gallery"]["output_dir"] == "../openaver_oracle_b_stale_save"


# ============ 路由改名向後兼容測試 ============


class TestTranslateConfigRoundTrip:
    """測試 translate 設定 round-trip（GET → PUT → GET）"""


    @pytest.mark.usefixtures("isolate_secret_store")
    def test_openai_config_roundtrip(self, client, temp_config_path):
        """translate.openai 設定在 round-trip 後應完整保留"""
        response = client.get("/api/config")
        assert response.status_code == 200
        config_data = response.json()["data"]

        config_data["translate"]["provider"] = "openai"
        config_data["translate"]["openai"] = {
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-roundtrip",
            "model": "gpt-4o"
        }

        response = client.put("/api/config", json=config_data)
        assert response.status_code == 200
        assert response.json()["success"] is True

        response = client.get("/api/config")
        assert response.status_code == 200
        updated = response.json()["data"]

        assert updated["translate"]["provider"] == "openai"
        openai_cfg = updated["translate"]["openai"]
        assert openai_cfg["base_url"] == "https://api.openai.com/v1"
        # CD-114c-8: API 層改斷言遮罩形狀；round-trip 保存性質下移到 load_config 函式層
        from core.secret_fields import mask_secret
        from core.config import load_config as _load_config
        assert openai_cfg["api_key"] == mask_secret("sk-test-roundtrip")
        assert _load_config()["translate"]["openai"]["api_key"] == "sk-test-roundtrip"
        assert openai_cfg["model"] == "gpt-4o"
