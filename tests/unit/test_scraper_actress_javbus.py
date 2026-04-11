"""
_search_star_on_javbus 邊界條件單元測試（全 mock，不打外部）

覆蓋：
1. 成功：找到 .avatar-box.text-center，回傳 (star_id, star_name)
2. 女優不存在：無 .avatar-box.text-center，回傳 None
3. HTTP 非 200：回傳 None
4. Timeout：回傳 None
5. href 格式異常（不含 "star/"）：回傳 None
"""

import pytest
import requests
from unittest.mock import patch, MagicMock


# ============================================================================
# 共用 HTML 片段
# ============================================================================

_SEARCH_STAR_FOUND_HTML = """
<html>
<body>
  <div class="avatar-box text-center">
    <a href="https://www.javbus.com/star/okq">
      <div class="photo-frame">
        <img src="/pics/actress/okq_a.jpg" title="桜空もも" />
      </div>
      <div class="photo-info"><span>桜空もも</span></div>
    </a>
  </div>
</body>
</html>
"""

_SEARCH_STAR_MULTIPLE_HTML = """
<html>
<body>
  <div class="avatar-box text-center">
    <a href="https://www.javbus.com/star/abc">
      <div class="photo-frame">
        <img src="/pics/actress/abc_a.jpg" title="同名女優A" />
      </div>
    </a>
  </div>
  <div class="avatar-box text-center">
    <a href="https://www.javbus.com/star/def">
      <div class="photo-frame">
        <img src="/pics/actress/def_a.jpg" title="同名女優B" />
      </div>
    </a>
  </div>
</body>
</html>
"""

_SEARCH_STAR_NOT_FOUND_HTML = """
<html>
<body>
  <p>No results found.</p>
</body>
</html>
"""

_SEARCH_STAR_BAD_HREF_HTML = """
<html>
<body>
  <div class="avatar-box text-center">
    <a href="https://www.javbus.com/actress/okq">
      <div class="photo-frame">
        <img src="/pics/actress/okq_a.jpg" title="桜空もも" />
      </div>
    </a>
  </div>
</body>
</html>
"""


# ============================================================================
# 測試：成功找到女優
# ============================================================================

def test_search_star_on_javbus_success():
    """成功：mock HTML 包含 .avatar-box.text-center，回傳 (star_id, star_name)"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SEARCH_STAR_FOUND_HTML

    with patch('requests.get', return_value=mock_resp) as mock_get:
        result = _search_star_on_javbus("桜空もも")

    assert result is not None
    star_id, star_name = result
    assert star_id == "okq"
    assert star_name == "桜空もも"
    # 確認 URL 有包含 name
    call_args = mock_get.call_args
    assert "searchstar" in call_args[0][0]


# ============================================================================
# 測試：女優不存在
# ============================================================================

def test_search_star_on_javbus_not_found():
    """女優不存在：mock HTML 無 .avatar-box，回傳 None"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SEARCH_STAR_NOT_FOUND_HTML

    with patch('requests.get', return_value=mock_resp):
        result = _search_star_on_javbus("不存在的女優")

    assert result is None


# ============================================================================
# 測試：HTTP 非 200
# ============================================================================

def test_search_star_on_javbus_http_error():
    """HTTP 非 200：回傳 None"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "<html></html>"

    with patch('requests.get', return_value=mock_resp):
        result = _search_star_on_javbus("桜空もも")

    assert result is None


def test_search_star_on_javbus_http_500():
    """HTTP 500：回傳 None"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "<html>Server Error</html>"

    with patch('requests.get', return_value=mock_resp):
        result = _search_star_on_javbus("桜空もも")

    assert result is None


# ============================================================================
# 測試：Timeout
# ============================================================================

def test_search_star_on_javbus_timeout():
    """Timeout：mock requests.get 拋 Timeout，回傳 None（fail-open）"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    with patch('requests.get', side_effect=requests.exceptions.Timeout("timeout")):
        result = _search_star_on_javbus("桜空もも")

    assert result is None


# ============================================================================
# 測試：href 格式異常（不含 "star/"）
# ============================================================================

def test_search_star_on_javbus_bad_href():
    """解析失敗：href 不含 'star/'，回傳 None"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SEARCH_STAR_BAD_HREF_HTML

    with patch('requests.get', return_value=mock_resp):
        result = _search_star_on_javbus("桜空もも")

    assert result is None


# ============================================================================
# 測試：多個結果取第一個
# ============================================================================

def test_search_star_on_javbus_multiple_results_takes_first():
    """多個 .avatar-box 結果：回傳第一個"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SEARCH_STAR_MULTIPLE_HTML

    with patch('requests.get', return_value=mock_resp):
        result = _search_star_on_javbus("同名女優")

    assert result is not None
    star_id, star_name = result
    assert star_id == "abc"
    assert star_name == "同名女優A"


# ============================================================================
# 測試：網路錯誤（RequestException）
# ============================================================================

def test_search_star_on_javbus_request_exception():
    """網路錯誤：mock requests.get 拋 RequestException，回傳 None"""
    from core.scrapers.actress.javbus import _search_star_on_javbus

    with patch('requests.get', side_effect=requests.exceptions.ConnectionError("conn refused")):
        result = _search_star_on_javbus("桜空もも")

    assert result is None


# ============================================================
# Accept-Encoding guard — br 不應出現（無 Brotli 解碼器）
# ============================================================

def test_javbus_headers_no_brotli():
    """_JAVBUS_HEADERS 不應宣告 br（專案無 brotli 依賴）"""
    from core.scrapers.actress.javbus import _JAVBUS_HEADERS
    ae = _JAVBUS_HEADERS.get('Accept-Encoding', '')
    assert 'br' not in ae, f"Accept-Encoding 不應含 br: {ae!r}"
    assert 'gzip' in ae, f"Accept-Encoding 應含 gzip: {ae!r}"
