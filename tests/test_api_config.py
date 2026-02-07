import json
from web.routers.config import AppConfig

def test_get_config(client, temp_config_path):
    """測試獲取設定"""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "scraper" in data["data"]
    assert "gallery" in data["data"]
    
    # 驗證 Phase 3.2 新增的欄位
    gallery = data["data"]["gallery"]
    assert "output_dir" in gallery
    assert "output_filename" in gallery

def test_update_config(client, temp_config_path):
    """測試更新設定"""
    # 先獲取當前設定
    response = client.get("/api/config")
    current_config = response.json()["data"]
    
    # 修改設定
    current_config["gallery"]["output_dir"] = "test_output"
    current_config["gallery"]["output_filename"] = "test.html"
    current_config["general"]["theme"] = "dark"
    
    # PUT 更新
    response = client.put("/api/config", json=current_config)
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # 再次獲取驗證
    response = client.get("/api/config")
    new_config = response.json()["data"]
    assert new_config["gallery"]["output_dir"] == "test_output"
    assert new_config["gallery"]["output_filename"] == "test.html"
    assert new_config["general"]["theme"] == "dark"

def test_config_persistence(client, temp_config_path):
    """測試設定持久化（寫入檔案）"""
    # 修改設定
    response = client.get("/api/config")
    cfg = response.json()["data"]
    cfg["scraper"]["max_title_length"] = 99
    
    client.put("/api/config", json=cfg)
    
    # 直接讀取檔案驗證
    with open(temp_config_path, 'r', encoding='utf-8') as f:
        saved_data = json.load(f)
        
    assert saved_data["scraper"]["max_title_length"] == 99


# ============ 路由改名向後兼容測試 ============

def test_gallery_legacy_redirect(client):
    """GET /gallery 應 302 轉址到 /scanner"""
    response = client.get("/gallery", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/scanner"


def test_scanner_route_ok(client):
    """GET /scanner 應正常回應 200"""
    response = client.get("/scanner")
    assert response.status_code == 200
