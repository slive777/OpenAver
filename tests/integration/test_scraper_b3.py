"""
Integration tests for POST /api/scraper/fetch-samples (b5)

spec-48b §b3 — multi-video folder gate + fetch_samples_only() integration
"""
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import asdict
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from web.app import app
    return TestClient(app)


def _make_enrich_result(success=True, extrafanart_written=2, error=None):
    """Helper: build a minimal EnrichResult-like object (dataclass)."""
    from core.enricher import EnrichResult
    return EnrichResult(
        success=success,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=extrafanart_written,
        fields_filled=[],
        source_used="javbus",
        error=error,
    )


class TestFetchSamplesEndpoint:
    """spec-48b §b3 — POST /api/scraper/fetch-samples

    邊界條件：
    - 單片資料夾 → 呼叫 fetch_samples_only()，回傳 EnrichResult dict
    - 多片資料夾（count>1）→ success=False，error=multi_video_folder，不呼叫 fetch_samples_only()
    - 空資料夾（count=0）→ 視為單片，放行
    - 缺少必填欄位 → 422
    - capabilities 揭露 fetch_samples 含 confirmation_required: true
    """

    def test_single_video_folder_calls_fetch_samples(self, client):
        """count=1：gate 不觸發，呼叫 fetch_samples_only()，回傳其 EnrichResult"""
        mock_result = _make_enrich_result(success=True, extrafanart_written=3)

        with patch("web.routers.scraper.VideoRepository") as mock_repo_cls, \
             patch("web.routers.scraper.fetch_samples_only", return_value=mock_result) as mock_fetch:
            mock_repo = MagicMock()
            mock_repo.count_videos_in_folder.return_value = 1
            mock_repo_cls.return_value = mock_repo

            resp = client.post("/api/scraper/fetch-samples", json={
                "file_path": "file:///home/user/movies/SONE-205/SONE-205.mp4",
                "number": "SONE-205",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["extrafanart_written"] == 3
        assert data["nfo_written"] is False
        mock_fetch.assert_called_once()
        # 確認傳入參數
        call_kwargs = mock_fetch.call_args
        assert call_kwargs.kwargs.get("file_path") or call_kwargs.args[0]  # file_path 有值

    def test_multi_video_folder_returns_gate_response(self, client):
        """count=3：gate 觸發，不呼叫 fetch_samples_only()，回傳 multi_video_folder 錯誤"""
        with patch("web.routers.scraper.VideoRepository") as mock_repo_cls, \
             patch("web.routers.scraper.fetch_samples_only") as mock_fetch:
            mock_repo = MagicMock()
            mock_repo.count_videos_in_folder.return_value = 3
            mock_repo_cls.return_value = mock_repo

            resp = client.post("/api/scraper/fetch-samples", json={
                "file_path": "file:///home/user/movies/mixed_folder/SONE-205.mp4",
                "number": "SONE-205",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] == "multi_video_folder"
        assert data["count"] == 3
        assert data["extrafanart_written"] == 0
        mock_fetch.assert_not_called()

    def test_empty_folder_count_zero_proceeds_to_fetch(self, client):
        """count=0（DB 尚未掃描）：視為非多片，放行到 fetch_samples_only()"""
        mock_result = _make_enrich_result(success=True, extrafanart_written=0)

        with patch("web.routers.scraper.VideoRepository") as mock_repo_cls, \
             patch("web.routers.scraper.fetch_samples_only", return_value=mock_result) as mock_fetch:
            mock_repo = MagicMock()
            mock_repo.count_videos_in_folder.return_value = 0
            mock_repo_cls.return_value = mock_repo

            resp = client.post("/api/scraper/fetch-samples", json={
                "file_path": "/home/user/movies/SONE-205/SONE-205.mp4",
                "number": "SONE-205",
            })

        assert resp.status_code == 200
        mock_fetch.assert_called_once()

    def test_missing_file_path_returns_422(self, client):
        """缺少必填欄位 file_path → 422"""
        resp = client.post("/api/scraper/fetch-samples", json={"number": "SONE-205"})
        assert resp.status_code == 422

    def test_missing_number_returns_422(self, client):
        """缺少必填欄位 number → 422"""
        resp = client.post("/api/scraper/fetch-samples", json={
            "file_path": "file:///home/user/movies/SONE-205/SONE-205.mp4",
        })
        assert resp.status_code == 422

    def test_capabilities_exposes_fetch_samples(self, client):
        """GET /api/capabilities → tools 陣列含 fetch_samples，且 confirmation_required=True"""
        resp = client.get("/api/capabilities")
        assert resp.status_code == 200
        tools = {t["name"]: t for t in resp.json().get("tools", [])}
        assert "fetch_samples" in tools, "fetch_samples tool 未在 capabilities 中揭露"
        tool = tools["fetch_samples"]
        assert tool.get("confirmation_required") is True
        assert tool.get("side_effect") is True
        assert tool.get("method") == "POST"
        assert "/api/scraper/fetch-samples" in tool.get("path", "")
