"""共用 fixtures — unit 測試層"""
import pytest
import tempfile
from pathlib import Path

from core.database import init_db


@pytest.fixture
def temp_db():
    """建立臨時資料庫"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path
