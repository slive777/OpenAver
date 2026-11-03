"""core.cloud_translate 共用層（171-T1）：清理 oracle、錯誤分類、cloud_request 例外映射。"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.anthropic_client import classify_http_error, extract_text
from core.cloud_translate import (
    TranslateError,
    build_error,
    cloud_request,
    failure_category,
    finalize_translation,
)

FAKE_KEY = "FAKEKEY-xyz"

# Credential-shaped fixtures for build_error log redaction (gateway may echo keys).
_SK_ANT = "sk-ant-abcdefghijklmnopqrstuvwxyz012345"
_SK_PROJ = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"
_AIZA = "AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz0123456"
_BEARER_TOKEN = "tok_abcdefghijklmnopqrstuvwxyz0123456789"
_LONG_TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_extra"


def _mock_client(post=None, get=None):
    client = MagicMock()
    client.post = post or AsyncMock()
    client.get = get or AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def _resp(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=payload if payload is not None else {})
    return r


# ---- finalize_translation ----

@pytest.mark.parametrize("raw,expected", [
    ("<thought>先想</thought>譯", "譯"),
])
def test_finalize_cleans_thinking(raw, expected):
    assert finalize_translation("T", raw) == expected


def test_finalize_unpaired_marker_fails(caplog):
    with pytest.raises(TranslateError) as ei:
        finalize_translation("Claude", "<thought>只有思考")
    assert ei.value.kind == "empty_response"
    assert "Claude" in caplog.text and "empty_response" in caplog.text


# ---- 錯誤分類 ----

@pytest.mark.parametrize("kind,expected", [
    ("blocked", "blocked"),
    ("refused", "blocked"),
    ("rate_limited", "rate_limited"),
    ("auth_failed", "other"),
    ("whatever", "other"),
])
def test_failure_category_table(kind, expected):
    assert failure_category(kind) == expected


# ---- build_error log redaction ----

@pytest.mark.parametrize(
    "secret,raw",
    [
        # sk-ant- echoed by a self-hosted gateway
        (_SK_ANT, f"Incorrect API key provided: {_SK_ANT}"),
        # sk-proj-
        (_SK_PROJ, f"Incorrect API key provided: {_SK_PROJ}"),
        # Google AIza
        (_AIZA, f"API key not valid. Please pass a valid API key. key={_AIZA}"),
        # Bearer <token>
        (_BEARER_TOKEN, f"Unauthorized Bearer {_BEARER_TOKEN}"),
        # ≥32 continuous credential-shaped fragment
        (_LONG_TOKEN, f"upstream rejected token={_LONG_TOKEN}"),
    ],
    ids=["sk-ant", "sk-proj", "AIza", "Bearer", "long32"],
)
def test_build_error_redacts_credential_fragments_in_log(caplog, secret, raw):
    """Gateway 在 error.message 回顯金鑰 → debug.log 不得留下明文。"""
    with caplog.at_level(logging.WARNING, logger="OpenAver.core.cloud_translate"):
        err = build_error("T", "auth_failed", 401, "invalid_request", raw)
    assert secret not in caplog.text
    assert secret not in err.message
    # 一般錯誤描述仍可讀
    assert "Incorrect API key" in caplog.text or "API key" in caplog.text or "Unauthorized" in caplog.text or "upstream rejected" in caplog.text


def test_anthropic_log_and_build_error_redacts_sk_ant_in_log(caplog):
    """Claude 路徑（_log_and_build_error）同樣不得把回顯的 sk-ant 金鑰寫進 log。"""
    resp = MagicMock()
    resp.status_code = 401
    resp.json = MagicMock(
        return_value={
            "error": {
                "type": "authentication_error",
                "message": f"Incorrect API key provided: {_SK_ANT}",
            }
        }
    )
    with caplog.at_level(logging.WARNING, logger="OpenAver.core.anthropic_client"):
        err = classify_http_error(resp)
    assert _SK_ANT not in caplog.text
    assert _SK_ANT not in err.message
    assert "Incorrect API key" in caplog.text
    assert err.kind == "auth_failed"


# ---- cloud_request ----

@pytest.mark.asyncio
async def test_cloud_request_illegal_key_no_leak(caplog):
    post = AsyncMock(side_effect=httpx.LocalProtocolError(
        f"Illegal header value b'{FAKE_KEY}\\n'"))
    cm, _ = _mock_client(post=post)
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        with pytest.raises(TranslateError) as ei:
            await cloud_request("T", "post", "https://x", headers={}, timeout=1, json={})
    e = ei.value
    assert e.kind == "auth_failed"
    assert e.error_type == "invalid_api_key_format"
    assert "FAKEKEY" not in e.message
    assert "FAKEKEY" not in caplog.text
    assert e.__suppress_context__ and e.__cause__ is None


@pytest.mark.asyncio
async def test_cloud_request_non_ascii_key_is_auth_failed(caplog):
    """使用者貼進全形字金鑰 → 歸「認證失敗」而非例外穿出；金鑰不進訊息／log。"""
    post = AsyncMock(side_effect=UnicodeEncodeError("ascii", "ＡKEY", 0, 1, "ordinal not in range"))
    cm, _ = _mock_client(post=post)
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        with pytest.raises(TranslateError) as ei:
            await cloud_request("T", "post", "https://x", headers={}, timeout=1, json={})
    e = ei.value
    assert e.kind == "auth_failed"
    assert "ＡKEY" not in e.message
    assert "ＡKEY" not in caplog.text


# ---- Claude 對齊 ----

def test_claude_extract_text_strips_thought():
    data = {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": "<thought>想</thought>譯"}]}
    assert extract_text(data) == "譯"


