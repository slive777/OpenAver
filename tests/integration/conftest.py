"""共用 fixtures — integration 測試層"""
import pytest
import json
from fastapi.testclient import TestClient
from web.app import app

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
