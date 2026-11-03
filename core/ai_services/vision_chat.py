"""Vision chat：依連線分派 Claude／Gemini／OpenAI／Ollama 看圖請求。

不 import web.*。翻譯路徑（translate_service／cloud_translate）零改動。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from core import anthropic_client, gemini_client, openai_client
from core.cloud_translate import build_error, finalize_translation

VISION_TIMEOUT_S = 90
_OLLAMA_ILLEGAL_KEY_MESSAGE = (
    "API Key contains illegal characters (whitespace/newline/non-ascii)"
)


@dataclass(frozen=True)
class VisionConn:
    provider: str
    model: str
    base_url: str = ""
    api_key: str = ""


def _strip_data_uri_prefix(uri: str) -> str:
    return uri.split(",", 1)[1]


def _build_ollama_payload(
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
) -> dict:
    return {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": user_text,
                "images": [_strip_data_uri_prefix(image_data_uri)],
            },
        ],
    }


def _ollama_parse_response(resp: httpx.Response) -> str:
    if resp.status_code >= 400:
        kind = "not_found" if resp.status_code == 404 else "http_error"
        raise build_error("Ollama", kind, resp.status_code, "", "")
    try:
        data = resp.json()
    except Exception as e:
        raise build_error("Ollama", "api_error", None, "", f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise build_error("Ollama", "api_error", None, "", "response is not a JSON object")
    if data.get("done_reason") == "length":
        raise build_error("Ollama", "truncated", None, "length", "done_reason=length")
    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        raise build_error("Ollama", "empty_response", None, "", "empty text content")
    return finalize_translation("Ollama", text)


async def ollama_vision(
    url: str,
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
    *,
    timeout: float,
) -> str:
    """POST {url}/api/chat with image；成功回非空 str，失敗拋 TranslateError。"""
    endpoint = url.rstrip("/") + "/api/chat"
    payload = _build_ollama_payload(model, system, user_text, image_data_uri)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(endpoint, json=payload)
    except httpx.TimeoutException:
        raise build_error(
            "Ollama", "connection_timeout", None, "", "request timed out"
        ) from None
    except (httpx.LocalProtocolError, UnicodeEncodeError):
        raise build_error(
            "Ollama",
            "auth_failed",
            None,
            "invalid_api_key_format",
            _OLLAMA_ILLEGAL_KEY_MESSAGE,
        ) from None
    except (httpx.HTTPError, OSError):
        raise build_error(
            "Ollama", "connection_failed", None, "", "cannot connect"
        ) from None
    return _ollama_parse_response(resp)


async def vision_chat(
    conn: VisionConn,
    system: str,
    user_text: str,
    image_data_uri: str,
) -> str:
    """依 conn.provider 分派看圖請求；回原始文字。"""
    t = VISION_TIMEOUT_S
    p, m, k, u = conn.provider, conn.model, conn.api_key, conn.base_url
    if p == "claude":
        return await anthropic_client.request_vision(
            k, m, system, user_text, image_data_uri, timeout=t
        )
    if p == "gemini":
        return await gemini_client.request_vision(
            k, m, system, user_text, image_data_uri, timeout=t
        )
    if p in ("openai", "openai_official"):
        base = (
            openai_client.OPENAI_OFFICIAL_BASE_URL
            if p == "openai_official"
            else u
        )
        return await openai_client.request_vision(
            base, k, m, system, user_text, image_data_uri, timeout=t
        )
    if p == "ollama":
        return await ollama_vision(u, m, system, user_text, image_data_uri, timeout=t)
    raise ValueError(f"unsupported vision provider: {p}")
