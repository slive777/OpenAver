"""共用 fixtures — integration 測試層"""
import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from web.app import app
from core import config as core_config


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """自動隔離所有 integration 測試的 config — 防止寫入真實 web/config.json"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "test_config.json"
    default_file = config_dir / "test_config.default.json"

    default_config = core_config.AppConfig().model_dump()
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(default_config, f)

    monkeypatch.setattr(core_config, "CONFIG_PATH", config_file)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_file)


@pytest.fixture
def client():
    """共用 integration 層的 TestClient"""
    return TestClient(app)

@pytest.fixture
def parse_sse_events():
    """Helper: 解析 SSE response text，返回所有 event data 的列表。"""
    def _parse(response_text: str) -> list:
        events = []
        for line in response_text.strip().split('\n'):
            if line.startswith('data: '):
                try:
                    event_data = json.loads(line[6:])
                    events.append(event_data)
                except json.JSONDecodeError:
                    pass
        return events
    return _parse
