"""
test_anthropic_client.py — Anthropic Messages API 請求／解析層單元測試

mock 一律 patch 使用端 core.anthropic_client.httpx.AsyncClient；
回應為內嵌合成 dict，不連真 API。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.anthropic_client import (
    ANTHROPIC_BASE_URL,
    DEFAULT_CLAUDE_MODEL,
    AnthropicError,
    build_headers,
    extract_text,
    list_models,
    pick_translate_models,
    request_translation,
)


FAKE_KEY = "sk-ant-test-fake-key-not-real"


def _mock_response(*, status_code=200, json_data=None, reason_phrase="OK", json_side_effect=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = reason_phrase
    if json_side_effect is not None:
        resp.json.side_effect = json_side_effect
    else:
        resp.json.return_value = json_data if json_data is not None else {}
    return resp


def _mock_async_client(post_return=None, get_return=None, post_side_effect=None, get_side_effect=None):
    client = MagicMock()
    if post_side_effect is not None:
        client.post = AsyncMock(side_effect=post_side_effect)
    else:
        client.post = AsyncMock(return_value=post_return)
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(return_value=get_return)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ============ payload / headers (I2 oracle) ============


@pytest.mark.asyncio
async def test_request_translation_i2_oracle_via_post():
    """request_translation 實際 post 的 json／headers 符合 I2"""
    ok = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "譯文"}],
    }
    client = _mock_async_client(post_return=_mock_response(json_data=ok))
    with patch("core.anthropic_client.httpx.AsyncClient", return_value=client):
        result = await request_translation(FAKE_KEY, DEFAULT_CLAUDE_MODEL, "prompt", timeout=30)

    assert result == "譯文"
    kwargs = client.post.call_args.kwargs
    assert set(kwargs["json"].keys()) == {"model", "max_tokens", "messages", "output_config"}
    assert kwargs["json"]["max_tokens"] == 1024
    assert kwargs["json"]["output_config"] == {"effort": "low"}
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["headers"]["x-api-key"] == FAKE_KEY
    assert "Authorization" not in kwargs["headers"]
    assert client.post.call_args.args[0] == f"{ANTHROPIC_BASE_URL}/v1/messages"


# ============ extract_text 區塊判定 ============


def test_extract_text_skips_thinking_block():
    """content=[thinking, text] → 只回 text；跳過 thinking"""
    data = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": "先想一下…"},
            {"type": "text", "text": "  繁中譯文  "},
        ],
    }
    assert extract_text(data) == "繁中譯文"


def test_extract_text_thinking_only_is_empty_response():
    """content=[thinking] 單獨 → empty_response"""
    data = {
        "stop_reason": "end_turn",
        "content": [{"type": "thinking", "thinking": "只有思考"}],
    }
    with pytest.raises(AnthropicError) as ei:
        extract_text(data)
    assert ei.value.kind == "empty_response"


def test_extract_text_max_tokens_is_failure():
    """stop_reason=max_tokens 即使有 text 仍拋 truncated"""
    data = {
        "stop_reason": "max_tokens",
        "content": [{"type": "text", "text": "半句譯文"}],
    }
    with pytest.raises(AnthropicError) as ei:
        extract_text(data)
    assert ei.value.kind == "truncated"


def test_extract_text_refusal_is_failure():
    """stop_reason=refusal 即使有 text 仍拋 refused"""
    data = {
        "stop_reason": "refusal",
        "content": [{"type": "text", "text": "我無法翻譯這個"}],
    }
    with pytest.raises(AnthropicError) as ei:
        extract_text(data)
    assert ei.value.kind == "refused"


# ============ classify_http_error ============


# ============ pick_translate_models ============


# ============ 金鑰含空白／換行（Codex P1：不得洩漏進 log／message）============

_ILLEGAL_MSG = "Illegal header value b'sk-ant-FAKE-abc123\\n'"


def test_build_headers_strips_key_whitespace():
    assert build_headers("  sk-ant-x \n")["x-api-key"] == "sk-ant-x"


@pytest.mark.asyncio
async def test_request_translation_illegal_key_header_no_leak(caplog):
    import logging
    client = _mock_async_client(post_side_effect=httpx.LocalProtocolError(_ILLEGAL_MSG))
    with caplog.at_level(logging.DEBUG):
        with patch("core.anthropic_client.httpx.AsyncClient", return_value=client):
            with pytest.raises(AnthropicError) as ei:
                await request_translation(FAKE_KEY, DEFAULT_CLAUDE_MODEL, "p", timeout=1)
    assert ei.value.kind == "auth_failed"
    assert ei.value.error_type == "invalid_api_key_format"
    assert "sk-ant-FAKE" not in ei.value.message
    assert "sk-ant-FAKE" not in caplog.text


@pytest.mark.asyncio
async def test_list_models_illegal_key_header_no_leak(caplog):
    import logging
    client = _mock_async_client(get_side_effect=httpx.LocalProtocolError(_ILLEGAL_MSG))
    with caplog.at_level(logging.DEBUG):
        with patch("core.anthropic_client.httpx.AsyncClient", return_value=client):
            with pytest.raises(AnthropicError) as ei:
                await list_models(FAKE_KEY, timeout=1)
    assert ei.value.kind == "auth_failed"
    assert ei.value.error_type == "invalid_api_key_format"
    assert "sk-ant-FAKE" not in ei.value.message
    assert "sk-ant-FAKE" not in caplog.text


def test_pick_models_excludes_effort_unsupported():
    data = {"data": [
        {"id": "claude-haiku-5-5", "created_at": "2026-09-01T00:00:00Z",
         "capabilities": {"effort": {"supported": True}}},
        {"id": "claude-haiku-4-5-20251001", "created_at": "2025-10-01T00:00:00Z",
         "capabilities": {"effort": {"supported": False}}},
        {"id": "claude-haiku-legacy-nocaps", "created_at": "2025-01-01T00:00:00Z"},
        {"id": "claude-opus-5", "created_at": "2026-09-02T00:00:00Z",
         "capabilities": {"effort": {"supported": True}}},
    ]}
    assert pick_translate_models(data) == ["claude-haiku-5-5", "claude-haiku-legacy-nocaps"]


@pytest.mark.parametrize("token", ["preview", "exp"])
def test_pick_models_caps_per_family_and_excludes_experimental(token):
    rows = [{"id": f"claude-{family}-{i}", "created_at": f"2026-01-{i:02d}"}
            for family, count in (("sonnet", 5), ("haiku", 4)) for i in range(1, count + 1)]
    rows += [{"id": "claude-opus-1", "created_at": "2026-01-09"},
             {"id": f"claude-haiku-{token}", "created_at": "2026-01-10"}]
    got = pick_translate_models({"data": rows})
    assert got == ["claude-sonnet-5", "claude-sonnet-4", "claude-haiku-4",
                   "claude-sonnet-3", "claude-haiku-3", "claude-haiku-2"]
    assert next(mid for mid in got if "haiku" in mid) == "claude-haiku-4"
