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
