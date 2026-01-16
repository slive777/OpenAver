import pytest
from pathlib import Path
import json
from fastapi.testclient import TestClient
from web.app import app
from web.routers import config

@pytest.fixture
def client():
    """FastAPI Test Client"""
    return TestClient(app)

@pytest.fixture
def temp_config_path(tmp_path, monkeypatch):
    """
    Mock config path to use a temporary file.
    Avoids modifying the real config.json during tests.
    """
    # Create a temp config file
    d = tmp_path / "config"
    d.mkdir()
    p = d / "test_config.json"
    
    # Write default config
    default_config = config.AppConfig().model_dump()
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(default_config, f)
        
    # Monkeypatch the global CONFIG_PATH variable in the module
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    
    return p


# ============ 跨平台環境 Fixtures ============

@pytest.fixture
def mock_wsl_env(monkeypatch):
    """模擬 WSL 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')


@pytest.fixture
def mock_windows_env(monkeypatch):
    """模擬 Windows 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')


@pytest.fixture
def mock_linux_env(monkeypatch):
    """模擬 Linux 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')


@pytest.fixture
def mock_mac_env(monkeypatch):
    """模擬 macOS 環境"""
    import core.path_utils as path_utils
    monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'mac')


# ============ Samples 目錄 Fixtures ============

@pytest.fixture
def samples_dir():
    """取得 samples 測試目錄"""
    from pathlib import Path
    return Path(__file__).parent.parent / 'samples'
