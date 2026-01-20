"""
/api/parse-filename API 整合測試
"""
import pytest
from fastapi.testclient import TestClient
from web.app import app


client = TestClient(app)


class TestParseFilename:
    """parse-filename API 測試"""

    def test_single_file(self):
        """測試單個檔案解析"""
        response = client.post("/api/parse-filename", json={
            "filenames": ["SONE-205.mp4"]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["parsed"] == 1
        assert data["results"][0]["number"] == "SONE-205"
        assert data["results"][0]["has_subtitle"] is False

    def test_multiple_files(self):
        """測試多個檔案批次解析"""
        response = client.post("/api/parse-filename", json={
            "filenames": [
                "SONE-205.mp4",
                "[中文字幕] ABC-123.mkv",
                "FC2-PPV-1234567.mp4"
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["parsed"] == 3
        assert data["results"][0]["number"] == "SONE-205"
        assert data["results"][1]["number"] == "ABC-123"
        assert data["results"][1]["has_subtitle"] is True
        assert data["results"][2]["number"] == "FC2-PPV-1234567"

    def test_with_subtitle_markers(self):
        """測試字幕標記偵測"""
        response = client.post("/api/parse-filename", json={
            "filenames": [
                "ABC-123-C.mp4",        # -C 標記
                "DEF-456_C.mkv",        # _C 標記
                "[中文字幕] GHI-789.mp4",  # 中文字幕
                "JKL-012 字幕.mp4",     # 字幕
                "MNO-345.mp4"           # 無字幕
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["results"][0]["has_subtitle"] is True   # -C
        assert data["results"][1]["has_subtitle"] is True   # _C
        assert data["results"][2]["has_subtitle"] is True   # 中文字幕
        assert data["results"][3]["has_subtitle"] is True   # 字幕
        assert data["results"][4]["has_subtitle"] is False  # 無

    def test_unparseable_filename(self):
        """測試無法解析的檔名"""
        response = client.post("/api/parse-filename", json={
            "filenames": ["random_movie.mp4", "another.avi"]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["parsed"] == 0
        assert data["results"][0]["number"] is None
        assert data["results"][1]["number"] is None

    def test_empty_list(self):
        """測試空列表"""
        response = client.post("/api/parse-filename", json={
            "filenames": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["parsed"] == 0
        assert data["results"] == []

    def test_mixed_parseable(self):
        """測試混合可解析和不可解析"""
        response = client.post("/api/parse-filename", json={
            "filenames": [
                "SONE-205.mp4",
                "random.mp4",
                "ABC-123.mkv"
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["parsed"] == 2  # 只有 2 個可解析
