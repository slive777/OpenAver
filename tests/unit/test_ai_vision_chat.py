"""vision_chat 請求形狀／金鑰不外洩／Ollama 連線錯誤分類（TASK-188b-T6）。

一律 patch httpx.AsyncClient；回應為內嵌合成 dict，不連真 API。
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.cloud_translate import TranslateError
from core.ai_services.vision_chat import VisionConn, vision_chat


SYS = "SYS-PROMPT"
USER = "請標這張海報。"
B64 = "QUJD"
DATA_URI = "data:image/jpeg;base64,QUJD"
FAKE_SECRET = "sk-FAKE-abc123"


def _ok_resp(data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


_ANTHROPIC_OK = _ok_resp(
    {"content": [{"type": "text", "text": "x"}], "stop_reason": "end_turn"}
)
_GEMINI_OK = _ok_resp(
    {
        "candidates": [
            {"content": {"parts": [{"text": "x"}]}, "finishReason": "STOP"}
        ]
    }
)
_OPENAI_OK = _ok_resp(
    {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}
)
_OLLAMA_OK = _ok_resp(
    {
        "message": {"role": "assistant", "content": "x"},
        "done": True,
        "done_reason": "stop",
    }
)


def _default_post(url, headers=None, json=None, **kwargs):
    if str(url).endswith("/v1/messages") or "/v1/messages" in str(url):
        return _ANTHROPIC_OK
    if "generateContent" in str(url):
        return _GEMINI_OK
    if "chat/completions" in str(url):
        return _OPENAI_OK
    if "/api/chat" in str(url):
        return _OLLAMA_OK
    return _ANTHROPIC_OK


def _FakeAsyncClient(*args, **kwargs):
    client = MagicMock()
    client.post = AsyncMock(side_effect=_default_post)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _fake_with_side_effect(side_effect):
    client = MagicMock()
    client.post = AsyncMock(side_effect=side_effect)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["anthropic", "gemini", "openai", "ollama"],
)
async def test_vision_request_carries_image_in_provider_shape(case):
    """使用者選某家連線按標記 → 圖進對的欄位、Claude 不帶 temperature。"""
    client = _FakeAsyncClient()
    with patch("httpx.AsyncClient", return_value=client):
        if case == "anthropic":
            conn = VisionConn(
                provider="claude",
                model="claude-haiku-5-5",
                api_key=f"  {FAKE_SECRET}  ",
            )
            await vision_chat(conn, SYS, USER, DATA_URI)
            url = client.post.call_args.args[0]
            headers = client.post.call_args.kwargs["headers"]
            body = client.post.call_args.kwargs["json"]
            assert url.endswith("/v1/messages")
            assert body["system"] == SYS
            assert body["messages"][0]["content"] == [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": B64,
                    },
                },
                {"type": "text", "text": USER},
            ]
            assert "temperature" not in body
            assert "output_config" not in body
            assert body["max_tokens"] >= 4000
            assert headers["x-api-key"] == FAKE_SECRET

        elif case == "gemini":
            conn = VisionConn(
                provider="gemini",
                model="gemini-2.0-flash",
                api_key=FAKE_SECRET,
            )
            await vision_chat(conn, SYS, USER, DATA_URI)
            url = client.post.call_args.args[0]
            body = client.post.call_args.kwargs["json"]
            assert f"models/{conn.model}:generateContent" in url
            assert body["contents"][0]["parts"] == [
                {"inline_data": {"mime_type": "image/jpeg", "data": B64}},
                {"text": USER},
            ]
            assert body["system_instruction"] == {"parts": [{"text": SYS}]}
            assert "generationConfig" not in body

        elif case == "openai":
            conn = VisionConn(
                provider="openai",
                model="gpt-4o",
                base_url="http://llm.local/v1/",
                api_key=FAKE_SECRET,
            )
            await vision_chat(conn, SYS, USER, DATA_URI)
            url = client.post.call_args.args[0]
            body = client.post.call_args.kwargs["json"]
            assert url == "http://llm.local/v1/chat/completions"
            assert body["messages"][0] == {"role": "system", "content": SYS}
            assert body["messages"][1]["content"] == [
                {"type": "text", "text": USER},
                {"type": "image_url", "image_url": {"url": DATA_URI}},
            ]
            assert "temperature" not in body

        else:
            conn = VisionConn(
                provider="ollama",
                model="llava",
                base_url="http://ollama.local:11434/",
            )
            await vision_chat(conn, SYS, USER, DATA_URI)
            url = client.post.call_args.args[0]
            body = client.post.call_args.kwargs["json"]
            assert url == "http://ollama.local:11434/api/chat"
            assert "//" not in url[url.find("://") + 3 :]
            assert body["stream"] is False
            assert body["messages"][0] == {"role": "system", "content": SYS}
            assert body["messages"][1]["images"] == [B64]
            assert body["messages"][1]["content"] == USER
            assert "think" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,exc",
    [
        (
            "anthropic_local",
            httpx.LocalProtocolError(f"Illegal header value b'{FAKE_SECRET}\\n'"),
        ),
        (
            "anthropic_unicode",
            UnicodeEncodeError("ascii", FAKE_SECRET, 0, 1, "ordinal not in range"),
        ),
        (
            "ollama_local",
            httpx.LocalProtocolError(f"Illegal header value b'{FAKE_SECRET}\\n'"),
        ),
    ],
)
async def test_vision_errors_never_leak_secret(case, exc, caplog):
    """使用者貼的金鑰尾端多一個空白 → 金鑰不得進例外訊息與 log。"""
    client = _fake_with_side_effect(exc)
    with caplog.at_level(logging.DEBUG):
        with patch("httpx.AsyncClient", return_value=client):
            with pytest.raises(TranslateError) as ei:
                if case.startswith("anthropic"):
                    conn = VisionConn(
                        provider="claude",
                        model="claude-haiku-5-5",
                        api_key=FAKE_SECRET,
                    )
                else:
                    conn = VisionConn(
                        provider="ollama",
                        model="llava",
                        base_url="http://ollama.local:11434/",
                    )
                await vision_chat(conn, SYS, USER, DATA_URI)
    e = ei.value
    assert FAKE_SECRET not in e.message
    assert FAKE_SECRET not in str(e)
    assert FAKE_SECRET not in caplog.text
    if case.startswith("anthropic"):
        assert e.kind == "auth_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,kind",
    [
        (httpx.ReadTimeout("t"), "connection_timeout"),
        (httpx.ConnectError("c"), "connection_failed"),
    ],
)
async def test_vision_ollama_transport_errors_are_classified(exc, kind):
    """本機模型沒開 → 分類成連線錯誤，不是「模型看不懂圖」。"""
    client = _fake_with_side_effect(exc)
    with patch("httpx.AsyncClient", return_value=client):
        with pytest.raises(TranslateError) as ei:
            conn = VisionConn(
                provider="ollama",
                model="llava",
                base_url="http://ollama.local:11434/",
            )
            await vision_chat(conn, SYS, USER, DATA_URI)
    assert ei.value.kind == kind
