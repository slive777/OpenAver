"""Integration：自訂來源分支放行的 /api/proxy-image 只轉送 image/*（T14 第 2 輪）。

放行判準本身由 tests/unit/test_image_host_policy_custom.py 守；這裡只測 200 分支的內容型別閘。
"""
from unittest.mock import MagicMock, patch

from core.image_host_policy import ProxyVerdict

URL = "https://site.example/c.jpg"


def _resp(content_type, content=b"bytes"):
    r = MagicMock()
    r.status_code = 200
    r.content = content
    r.headers = {"Content-Type": content_type}
    return r


def _get(client, ctype, custom=True):
    verdict = ProxyVerdict(True, "site.example", "https", None, custom)
    with patch("web.routers.search.proxy_verdict", return_value=verdict), \
         patch("web.routers.search.requests.get", return_value=_resp(ctype)):
        return client.get("/api/proxy-image", params={"url": URL})


def test_custom_source_html_response_not_forwarded(client):
    r = _get(client, "text/html; charset=utf-8")
    assert r.status_code == 403
    assert r.content == b""


def test_custom_source_svg_not_forwarded(client):
    assert _get(client, "image/svg+xml").status_code == 403


def test_custom_source_type_params_and_case_tolerated(client):
    assert _get(client, "Image/JPEG; charset=binary").status_code == 200


def test_custom_source_missing_content_type_not_forwarded(client):
    assert _get(client, "").status_code == 403


def test_custom_source_image_forwarded_with_upstream_type(client):
    r = _get(client, "image/webp")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content == b"bytes"


def test_non_custom_html_behaviour_unchanged(client):
    r = _get(client, "text/html", custom=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
