"""共用 fixtures — unit 測試層"""
import pytest
import tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from fastapi.testclient import TestClient

from core.database import init_db, VideoRepository, Video


@pytest.fixture
def client():
    """FastAPI Test Client（unit 層使用）"""
    from web.app import app
    return TestClient(app)


@pytest.fixture
def make_mock_search_jav():
    """Helper fixture to create a mock search_jav function based on a results_map."""
    def _make(results_map):
        def mock_fn(num, source='javbus'):
            return results_map.get(num)
        return mock_fn
    return _make

@pytest.fixture
def temp_db():
    """建立臨時資料庫"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path

@pytest.fixture
def make_client(monkeypatch):
    """Factory fixture: 建立 TestClient 並 mock 指定模組的 get_db_path 或 load_config。"""
    def _make(mock_targets: list[str], mock_db_path=None, config_override: dict = None):
        if not mock_targets:
            raise ValueError("mock_targets cannot be empty")
        config = config_override or {
            "database": {"path": ":memory:"},
            "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
            "gallery": {"min_size_mb": 1, "thumbnail_width": 400},
            "translate": {"provider": "ollama", "ollama_model": "llama3"}
        }
        for target in mock_targets:
            if target.endswith("get_db_path") and mock_db_path is not None:
                monkeypatch.setattr(target, lambda: mock_db_path)
            else:
                monkeypatch.setattr(target, lambda: config)
        from web.app import app
        return TestClient(app)
    return _make

@pytest.fixture
def make_populated_db(temp_db):
    """Factory: 建立含指定 video 資料的臨時 DB，返回 db 的 Path。"""
    def _make(videos: list[Video]) -> Path:
        repo = VideoRepository(temp_db)
        repo.upsert_batch(videos)
        return temp_db
    return _make

