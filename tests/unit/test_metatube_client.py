"""
test_metatube_client.py — Unit tests for MetatubeHttpClient + pick_movie_result.

Test strategy: TDD-lite + mock HTTP (monkeypatch on client._session.get).
No real network calls. No requests-mock dependency.
House style: unittest.mock (MagicMock), plain assert, pytest fixtures.
"""

import json
import pytest
import requests
from unittest.mock import MagicMock

from core.metatube.errors import (
    MetatubeUnavailable,
    MetatubeNotFound,
    MetatubeAuthError,
    MetatubeClientError,
    MetatubeProtocolError,
)
from core.metatube.client import MetatubeHttpClient, pick_movie_result


# ============================================================
# Helpers
# ============================================================

def make_json_response(body: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response that returns JSON."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def make_bad_json_response(status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response that raises JSONDecodeError on .json()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)
    return resp


def make_client(base_url: str = "http://localhost:8900", token=None) -> MetatubeHttpClient:
    return MetatubeHttpClient(base_url, token=token)


# ============================================================
# TC-1: exception mapping (using get_info as representative method)
# ============================================================

class TestExceptionMapping:
    """10 boundary cases for status-code → exception mapping."""

    def test_timeout_raises_unavailable(self):
        client = make_client()
        client._session.get = MagicMock(side_effect=requests.Timeout("timed out"))
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_connection_error_raises_unavailable(self):
        client = make_client()
        client._session.get = MagicMock(side_effect=requests.ConnectionError("no conn"))
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_invalid_url_raises_unavailable_not_raw(self):
        """requests.InvalidURL (a RequestException subclass) must be caught and
        re-raised as MetatubeUnavailable — must NOT escape as InvalidURL (FIX 1b)."""
        client = make_client()
        client._session.get = MagicMock(
            side_effect=requests.exceptions.InvalidURL("Invalid URL")
        )
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_ssl_error_raises_unavailable(self):
        """requests.SSLError must also be caught as MetatubeUnavailable (FIX 1b)."""
        client = make_client()
        client._session.get = MagicMock(
            side_effect=requests.exceptions.SSLError("SSL handshake failed")
        )
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_too_many_redirects_raises_unavailable(self):
        """requests.TooManyRedirects must be caught as MetatubeUnavailable (FIX 1b)."""
        client = make_client()
        client._session.get = MagicMock(
            side_effect=requests.exceptions.TooManyRedirects("Too many redirects")
        )
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_200_valid_json_with_data_returns_data(self):
        client = make_client()
        data = {"number": "SSIS-001", "title": "Test Title"}
        client._session.get = MagicMock(
            return_value=make_json_response({"data": data})
        )
        result = client.get_info("FANZA", "1stars00141")
        assert result == data

    def test_200_data_null_returns_none(self):
        """data=null is a legitimate empty response — must NOT raise."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": None})
        )
        result = client.get_info("FANZA", "1stars00141")
        assert result is None

    def test_200_no_data_key_raises_protocol_error(self):
        """200 with valid JSON but missing 'data' key → ProtocolError."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"error": {"code": 0, "message": "ok"}})
        )
        with pytest.raises(MetatubeProtocolError):
            client.get_info("FANZA", "1stars00141")

    def test_200_bad_json_raises_protocol_error(self):
        """200 but response body is not valid JSON → ProtocolError."""
        client = make_client()
        client._session.get = MagicMock(return_value=make_bad_json_response(200))
        with pytest.raises(MetatubeProtocolError):
            client.get_info("FANZA", "1stars00141")

    def test_401_raises_auth_error(self):
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"error": {"code": 401, "message": "unauthorized"}}, 401
            )
        )
        with pytest.raises(MetatubeAuthError):
            client.get_info("FANZA", "1stars00141")

    def test_404_raises_not_found(self):
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"error": {"code": 404, "message": "not found"}}, 404
            )
        )
        with pytest.raises(MetatubeNotFound):
            client.get_info("FANZA", "1stars00141")

    def test_422_raises_client_error(self):
        """Other 4xx errors (not 401/404) → ClientError."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"error": {"code": 422, "message": "unprocessable"}}, 422
            )
        )
        with pytest.raises(MetatubeClientError):
            client.get_info("FANZA", "1stars00141")

    def test_500_raises_unavailable(self):
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"error": {"code": 500, "message": "internal server error"}}, 500
            )
        )
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_500_html_error_page_raises_unavailable_not_protocol_error(self):
        """5xx 回 HTML 錯誤頁（.json() 拋 JSONDecodeError）時，status-code 分類
        必須先於 json 解析 → MetatubeUnavailable，不可被誤判為 MetatubeProtocolError。
        鎖定 CD-63a-6 的 ordering 保證（最易回歸點）。"""
        client = make_client()
        client._session.get = MagicMock(return_value=make_bad_json_response(500))
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")

    def test_503_raises_unavailable(self):
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"error": {"code": 503, "message": "service unavailable"}}, 503
            )
        )
        with pytest.raises(MetatubeUnavailable):
            client.get_info("FANZA", "1stars00141")


# ============================================================
# TC-2: list_providers special cases
# ============================================================

class TestListProviders:

    def test_returns_movie_providers_only(self):
        """actor_providers must be discarded."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({
                "data": {
                    "movie_providers": {"FANZA": "https://dmm.co.jp", "JavBus": "https://javbus.com"},
                    "actor_providers": {"SomeActorProvider": "https://example.com"},
                }
            })
        )
        result = client.list_providers()
        assert result == {"FANZA": "https://dmm.co.jp", "JavBus": "https://javbus.com"}
        assert "SomeActorProvider" not in result

    def test_data_null_returns_empty_dict(self):
        """data=null for list_providers → return {} (safe fallback)."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": None})
        )
        result = client.list_providers()
        assert result == {}

    def test_list_providers_also_raises_on_5xx(self):
        """Same exception mapping applies to list_providers."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"error": {}}, 500)
        )
        with pytest.raises(MetatubeUnavailable):
            client.list_providers()


# ============================================================
# TC-3: search — provider param & data=null
# ============================================================

class TestSearch:

    def test_search_always_sends_provider_param(self):
        """params must contain 'provider' to avoid triggering SearchMovieAll broadcast."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": []})
        )
        client.search("FANZA", "ssis-001")
        call_kwargs = client._session.get.call_args
        # params can be positional or keyword
        if call_kwargs.kwargs.get("params"):
            params = call_kwargs.kwargs["params"]
        else:
            # find params in args
            params = call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
            params = call_kwargs.kwargs.get("params", params)
        assert "provider" in params
        assert params["provider"] == "FANZA"

    def test_search_sends_fallback_false(self):
        """params must contain fallback=false to enforce source isolation (Codex P2):
        upstream metatube defaults Fallback=true, so a no-match provider-scoped search
        would otherwise return a foreign provider's hit, corrupting US8 / auto fan-out."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": []})
        )
        client.search("SOD", "ssis-001")
        params = client._session.get.call_args.kwargs.get("params") or {}
        assert params.get("fallback") == "false"
        # must be the lowercase string, not Python bool False (requests → "False")
        assert isinstance(params.get("fallback"), str)

    def test_search_data_null_returns_empty_list(self):
        """data=null on search → return [] not raise."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": None})
        )
        result = client.search("FANZA", "ssis-001")
        assert result == []

    def test_search_returns_list(self):
        client = make_client()
        items = [{"id": "ssis00001", "number": "SSIS-001"}]
        client._session.get = MagicMock(
            return_value=make_json_response({"data": items})
        )
        result = client.search("FANZA", "ssis-001")
        assert result == items


# ============================================================
# TC-4: token header (have / none / empty string)
# ============================================================

class TestTokenHeader:

    def test_token_none_no_authorization_header(self):
        client = MetatubeHttpClient("http://localhost:8900", token=None)
        assert "Authorization" not in client._session.headers

    def test_token_set_has_bearer_header(self):
        client = MetatubeHttpClient("http://localhost:8900", token="secret")
        assert client._session.headers.get("Authorization") == "Bearer secret"

    def test_token_empty_string_no_authorization_header(self):
        """Empty string is falsy — must not send Authorization header."""
        client = MetatubeHttpClient("http://localhost:8900", token="")
        assert "Authorization" not in client._session.headers


# ============================================================
# TC-5: pick_movie_result — 5 boundary cases
# ============================================================

class TestPickMovieResult:

    def test_empty_list_returns_none(self):
        assert pick_movie_result([]) is None

    def test_picks_video_dmm_homepage_over_first(self):
        """3 results: second has video.dmm.co.jp homepage — should be picked."""
        results = [
            {"id": "a", "homepage": "https://www.dmm.co.jp/mono/dvd/"},
            {"id": "b", "homepage": "https://video.dmm.co.jp/product/detail/1stars00141/"},
            {"id": "c", "homepage": "https://www.dmm.co.jp/digital/"},
        ]
        picked = pick_movie_result(results)
        assert picked is not None
        assert picked["id"] == "b"

    def test_no_video_dmm_returns_first(self):
        """3 results, none with video.dmm.co.jp → return results[0]."""
        results = [
            {"id": "first", "homepage": "https://other.example.com/"},
            {"id": "second", "homepage": "https://another.example.com/"},
            {"id": "third"},
        ]
        picked = pick_movie_result(results)
        assert picked["id"] == "first"

    def test_single_result_with_video_dmm_returns_it(self):
        """1 result with video.dmm.co.jp homepage → return it (overlap of rule 1 and first)."""
        results = [{"id": "only", "homepage": "https://video.dmm.co.jp/product/detail/x/"}]
        picked = pick_movie_result(results)
        assert picked["id"] == "only"

    def test_single_result_no_homepage_key_returns_it(self):
        """1 result without homepage key → r.get('homepage', '') is safe → returns results[0]."""
        results = [{"id": "nopage", "title": "Some Title"}]
        picked = pick_movie_result(results)
        assert picked["id"] == "nopage"


# ============================================================
# TC-6: movie_id URL quoting in get_info
# ============================================================

# ============================================================
# TC-7: Fix 3 (P2) — 200 but JSON body non-dict → MetatubeProtocolError
# ============================================================

class TestNonDictBodyProtocolError:

    def test_get_data_non_dict_body_raises_protocol_error(self):
        """200 + resp.json() 回 []（list）→ MetatubeProtocolError（via get_info）"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response([], status_code=200)
        )
        with pytest.raises(MetatubeProtocolError):
            client.get_info("FANZA", "1stars00141")

    def test_list_providers_data_is_list_raises_protocol_error(self):
        """200 + {"data": ["FANZA"]}（data 為 list）→ MetatubeProtocolError"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": ["FANZA"]}, status_code=200)
        )
        with pytest.raises(MetatubeProtocolError):
            client.list_providers()

    def test_list_providers_movie_providers_is_list_raises_protocol_error(self):
        """200 + {"data": {"movie_providers": []}}（movie_providers 非 dict）
        → MetatubeProtocolError（per-method inner-shape guard, Codex P2 follow-up）"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response(
                {"data": {"movie_providers": []}}, status_code=200
            )
        )
        with pytest.raises(MetatubeProtocolError):
            client.list_providers()

    def test_list_providers_missing_movie_providers_key_raises_protocol_error(self):
        """200 + {"data": {}}（data 是 dict 但缺 movie_providers key）→ MetatubeProtocolError
        （不可靜默回 {} 假裝「connected, 0 providers」；spec：/v1/providers 畸形應 fail connect）"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {}}, status_code=200)
        )
        with pytest.raises(MetatubeProtocolError):
            client.list_providers()

    def test_get_info_data_is_list_raises_protocol_error(self):
        """200 + {"data": []}（get_info data 非 dict/None）→ MetatubeProtocolError"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": []}, status_code=200)
        )
        with pytest.raises(MetatubeProtocolError):
            client.get_info("FANZA", "1stars00141")

    def test_search_data_is_dict_raises_protocol_error(self):
        """200 + {"data": {"x": 1}}（search data 非 list/None）→ MetatubeProtocolError"""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {"x": 1}}, status_code=200)
        )
        with pytest.raises(MetatubeProtocolError):
            client.search("FANZA", "ssis-001")


# ============================================================
# TC-6: movie_id URL quoting in get_info
# ============================================================

class TestMovieIdQuoting:

    def _get_called_url(self, client: MetatubeHttpClient) -> str:
        """Extract the URL from the last session.get call."""
        call = client._session.get.call_args
        if call.args:
            return call.args[0]
        return call.kwargs.get("url", "")

    def test_underscore_id_not_mangled(self):
        """020125_001 — underscore is valid URL char; path must contain it unchanged."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {"number": "020125_001"}})
        )
        client.get_info("1Pondo", "020125_001")
        url = self._get_called_url(client)
        assert "020125_001" in url

    def test_alphanumeric_id_not_mangled(self):
        """156785614478ab480db — pure alphanum, path unchanged."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {"number": "156785614478ab480db"}})
        )
        client.get_info("Pcolle", "156785614478ab480db")
        url = self._get_called_url(client)
        assert "156785614478ab480db" in url

    def test_lowercase_id_not_mangled(self):
        """1stars00141 — all lower-case alphanum, path unchanged."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {"number": "1stars00141"}})
        )
        client.get_info("FANZA", "1stars00141")
        url = self._get_called_url(client)
        assert "1stars00141" in url

    def test_no_double_slash_in_url(self):
        """base_url with trailing slash must not produce double slashes."""
        client = MetatubeHttpClient("http://localhost:8900/", token=None)
        client._session.get = MagicMock(
            return_value=make_json_response({"data": {}})
        )
        client.get_info("FANZA", "1stars00141")
        url = self._get_called_url(client)
        # After the scheme+host, path should start with single /v1
        assert "//v1" not in url.replace("http://", "").replace("https://", "")


# ============================================================
# TC-9: SSRF redirect guard (Codex P1) — 3xx must NOT be followed
# A validated public host could 30x-redirect to loopback / internal;
# validate_metatube_url() only checks the original URL, so the client
# must refuse redirects (allow_redirects=False) and reject any 3xx.
# ============================================================

class TestRedirectBlocking:
    # Two cases are enough: pin the allow_redirects=False contract, and confirm
    # a 3xx surfaces as MetatubeProtocolError (not followed). The redirect block
    # lives in the shared _get_data path, so per-method / per-target-IP matrices
    # add no coverage — they were enterprise-SSRF audit padding (A2 trim).

    def test_session_get_called_with_allow_redirects_false(self):
        """Pin the contract: allow_redirects=False must be passed (regression guard)."""
        client = make_client()
        client._session.get = MagicMock(
            return_value=make_json_response({"data": None}, status_code=200)
        )
        client.get_info("FANZA", "1stars00141")
        assert client._session.get.call_args.kwargs.get("allow_redirects") is False, (
            "MetatubeHttpClient must pass allow_redirects=False to prevent SSRF via redirects"
        )

    def test_3xx_redirect_raises_protocol_error(self):
        """A 3xx response → MetatubeProtocolError, not followed."""
        client = make_client()
        resp = make_json_response({}, status_code=302)
        resp.headers = {"Location": "http://127.0.0.1:8080/admin"}
        client._session.get = MagicMock(return_value=resp)
        with pytest.raises(MetatubeProtocolError):
            client.get_info("FANZA", "1stars00141")
