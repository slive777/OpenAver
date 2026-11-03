"""
Anthropic Messages API 請求／解析／錯誤分類（Claude 翻譯唯一來源）。

不 import web.*、不 import core.translate_service。
失敗一律拋 AnthropicError；設定頁測試鈕與真翻譯走同一條路。
"""

from __future__ import annotations

from typing import Any

import httpx

from core.cloud_translate import TranslateError, finalize_translation
from core.logger import get_logger

logger = get_logger(__name__)

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_CLAUDE_MODEL = "claude-haiku-5-5"
MAX_TOKENS = 1024
_ILLEGAL_KEY_MESSAGE = "API Key contains illegal characters (whitespace/newline)"


class AnthropicError(TranslateError):
    """Anthropic API 失敗（HTTP／連線／回應判定）。"""


def _log_and_build_error(
    kind: str,
    status: int | None,
    error_type: str,
    message: str,
) -> AnthropicError:
    msg = (message or "")[:300]
    logger.warning(
        "[Claude] %s status=%s type=%s msg=%s",
        kind,
        status,
        error_type,
        msg,
    )
    return AnthropicError(kind, status, error_type, msg)


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key.strip(),
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def build_translate_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": "low"},
    }


def extract_text(data: dict) -> str:
    """從 Messages 回應取出 text；refusal／max_tokens／空文字拋 AnthropicError。"""
    if data.get("stop_reason") == "refusal":
        raise _log_and_build_error("refused", None, "refusal", "stop_reason=refusal")
    if data.get("stop_reason") == "max_tokens":
        raise _log_and_build_error("truncated", None, "max_tokens", "stop_reason=max_tokens")

    content = data.get("content")
    if not isinstance(content, list):
        raise _log_and_build_error(
            "api_error",
            None,
            "",
            "response missing content list",
        )

    parts = [b.get("text", "") for b in content if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise _log_and_build_error("empty_response", None, "", "empty text content")
    try:
        return finalize_translation("Claude", text)
    except TranslateError as e:
        raise AnthropicError(e.kind, e.status, e.error_type, e.message) from None


def classify_http_error(resp: httpx.Response) -> AnthropicError:
    """依狀態碼與 error.type 分類；非 JSON 本體仍回 AnthropicError。"""
    status = resp.status_code
    err_type = ""
    message = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            err_type = str(err.get("type") or "")
            message = str(err.get("message") or "")
    except Exception:
        err_type = ""
        message = getattr(resp, "reason_phrase", "") or ""

    if status == 401 or err_type == "authentication_error":
        return _log_and_build_error("auth_failed", status, err_type, message)
    if status == 403 or err_type == "permission_error":
        return _log_and_build_error("forbidden", status, err_type, message)
    if status == 404 or err_type == "not_found_error":
        return _log_and_build_error("not_found", status, err_type, message)
    if (
        status in (429, 402)
        or err_type in ("rate_limit_error", "billing_error")
    ):
        return _log_and_build_error("rate_limited", status, err_type, message)
    if status == 400 and "credit balance" in message.lower():
        return _log_and_build_error("rate_limited", status, err_type, message)
    return _log_and_build_error("http_error", status, err_type, message)


def _supports_effort(item: dict) -> bool:
    """capabilities.effort.supported 明確為 False 才排除；欄位缺或形狀不明 → 保留（fail-open）。"""
    caps = item.get("capabilities")
    effort = caps.get("effort") if isinstance(caps, dict) else None
    supported = effort.get("supported") if isinstance(effort, dict) else None
    return supported is not False


def pick_translate_models(data: dict) -> list[str]:
    """過濾 haiku／sonnet，依 created_at 新到舊排，回傳 id 陣列。"""
    raw = data.get("data") or []
    items: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").lower()
        if ("haiku" in mid or "sonnet" in mid) and _supports_effort(m):
            items.append(m)
    items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return [str(m["id"]) for m in items]


async def request_translation(
    api_key: str,
    model: str,
    prompt: str,
    *,
    timeout: float,
) -> str:
    """POST /v1/messages；成功回非空 str，失敗拋 AnthropicError。"""
    headers = build_headers(api_key)
    payload = build_translate_payload(model, prompt)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/v1/messages",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as e:
        raise _log_and_build_error(
            "connection_timeout",
            None,
            "",
            str(e),
        ) from e
    except httpx.LocalProtocolError:
        # 金鑰含空白／換行 → h11 拒送；str(e) 內含金鑰，絕不可進 message／log
        raise _log_and_build_error(
            "auth_failed",
            None,
            "invalid_api_key_format",
            _ILLEGAL_KEY_MESSAGE,
        ) from None
    except (httpx.HTTPError, OSError) as e:
        raise _log_and_build_error(
            "connection_failed",
            None,
            "",
            str(e),
        ) from e

    if resp.status_code >= 400:
        raise classify_http_error(resp)

    try:
        data = resp.json()
    except Exception as e:
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            f"invalid JSON: {e}",
        ) from e

    if not isinstance(data, dict):
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            "response is not a JSON object",
        )

    return extract_text(data)


async def list_models(api_key: str, *, timeout: float) -> dict:
    """GET /v1/models?limit=1000；回原始 dict；has_more 只 warning 不翻頁。"""
    headers = build_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{ANTHROPIC_BASE_URL}/v1/models",
                headers=headers,
                params={"limit": 1000},
            )
    except httpx.TimeoutException as e:
        raise _log_and_build_error(
            "connection_timeout",
            None,
            "",
            str(e),
        ) from e
    except httpx.LocalProtocolError:
        # 金鑰含空白／換行 → h11 拒送；str(e) 內含金鑰，絕不可進 message／log
        raise _log_and_build_error(
            "auth_failed",
            None,
            "invalid_api_key_format",
            _ILLEGAL_KEY_MESSAGE,
        ) from None
    except (httpx.HTTPError, OSError) as e:
        raise _log_and_build_error(
            "connection_failed",
            None,
            "",
            str(e),
        ) from e

    if resp.status_code >= 400:
        raise classify_http_error(resp)

    try:
        data = resp.json()
    except Exception as e:
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            f"invalid JSON: {e}",
        ) from e

    if not isinstance(data, dict):
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            "response is not a JSON object",
        )

    if data.get("has_more"):
        logger.warning("[Claude] models has_more=True; not paginating (limit=1000)")

    return data


VISION_MAX_TOKENS = 6000


def _strip_vision_data_uri(uri: str) -> str:
    return uri.split(",", 1)[1]


def build_vision_payload(
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": VISION_MAX_TOKENS,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": _strip_vision_data_uri(image_data_uri),
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    }


def _parse_messages_response(resp: httpx.Response) -> dict:
    if resp.status_code >= 400:
        raise classify_http_error(resp)
    try:
        data = resp.json()
    except Exception as e:
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            f"invalid JSON: {e}",
        ) from e
    if not isinstance(data, dict):
        raise _log_and_build_error(
            "api_error",
            resp.status_code,
            "",
            "response is not a JSON object",
        )
    return data


async def _post_messages(api_key: str, payload: dict, *, timeout: float) -> dict:
    headers = build_headers(api_key)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/v1/messages",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as e:
        raise _log_and_build_error(
            "connection_timeout",
            None,
            "",
            str(e),
        ) from e
    except (httpx.LocalProtocolError, UnicodeEncodeError):
        # 金鑰含空白／換行／非 ASCII → 拒送；str(e) 內含金鑰，絕不可進 message／log
        raise _log_and_build_error(
            "auth_failed",
            None,
            "invalid_api_key_format",
            _ILLEGAL_KEY_MESSAGE,
        ) from None
    except (httpx.HTTPError, OSError) as e:
        raise _log_and_build_error(
            "connection_failed",
            None,
            "",
            str(e),
        ) from e
    return _parse_messages_response(resp)


async def request_vision(
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
    *,
    timeout: float,
) -> str:
    """POST /v1/messages with image；成功回非空 str，失敗拋 AnthropicError。"""
    payload = build_vision_payload(model, system, user_text, image_data_uri)
    data = await _post_messages(api_key, payload, timeout=timeout)
    return extract_text(data)
