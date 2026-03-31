"""
TDD-lite 測試 — help_page() context 注入 base_url
Phase 38b T3b / BUG2 修正
"""
import pytest
from fastapi.testclient import TestClient


def _make_client():
    from web.app import app
    return TestClient(app, raise_server_exceptions=True)


class TestHelpPageContext:
    """help_page() 必須注入 base_url 到 template context"""

    def test_help_page_has_curl_command(self):
        """help 頁含 SSR 渲染的 curl 指令"""
        client = _make_client()
        response = client.get("/help")
        assert response.status_code == 200
        html = response.text
        assert "curl -s" in html, \
            "help.html 應含有 SSR 渲染的 curl 指令"
        assert "/api/capabilities" in html, \
            "help.html 應含有 /api/capabilities 端點"

    def test_help_page_base_url_from_request(self):
        """base_url 來自 request，TestClient 預設為 http://testserver"""
        client = _make_client()
        response = client.get("/help")
        assert response.status_code == 200
        html = response.text
        # TestClient 的 base_url 是 http://testserver
        assert "http://testserver/api/capabilities" in html, \
            "base_url 應從 request.base_url 取得並渲染到 curl 指令中"

    def test_help_page_no_lan_ip_reference(self):
        """確認 _get_lan_ip 已移除，HTML 不含 socket 探測的 IP"""
        client = _make_client()
        response = client.get("/help")
        assert response.status_code == 200
        # 確認不再有 _get_lan_ip 相關的 context
        html = response.text
        assert "lan_ip" not in html, \
            "help.html 不應含有 lan_ip template 變數"
