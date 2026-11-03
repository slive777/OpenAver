"""
雲端翻譯共用層（Claude／Gemini／OpenAI 共用）。

不 import web.*、不 import core.translate_service。
提供：TranslateError、build_error、failure_category、settings_error_key、
finalize_translation（清思考標記）、cloud_request（金鑰安全的 httpx 呼叫）。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from core.logger import get_logger

logger = get_logger(__name__)

CLOUD_TRANSLATE_TIMEOUT = 60
_ILLEGAL_KEY_MESSAGE = "API Key contains illegal characters (whitespace/newline/non-ascii)"
_MESSAGE_LIMIT = 300
_MAX_CLEAN_PASSES = 10

_THINK_BLOCK_RE = re.compile(r"<(think|thought)>.*?</\1>", re.DOTALL | re.IGNORECASE)
_STRAY_MARKER_RE = re.compile(r"</?(?:think|thought)>", re.IGNORECASE)

# Gateway / proxy may echo credentials in error.message — redact before log.
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_AIZA_KEY_RE = re.compile(r"\bAIza[A-Za-z0-9_-]{10,}\b")
_BEARER_RE = re.compile(r"(?i)\b(Bearer\s+)([A-Za-z0-9._\-+=/]+)")
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")


def _mask_keep4(value: str) -> str:
    return f"{value[:4]}***" if len(value) > 4 else "***"


def redact_secrets(text: str) -> str:
    """Replace credential-shaped fragments; keep surrounding prose readable.

    Public so anthropic_client (and other cloud clients) can share one redact
    path without importing a private name (ruff PLC2701).
    """
    out = _SK_KEY_RE.sub(lambda m: _mask_keep4(m.group(0)), text)
    out = _AIZA_KEY_RE.sub(lambda m: _mask_keep4(m.group(0)), out)
    out = _BEARER_RE.sub(lambda m: m.group(1) + _mask_keep4(m.group(2)), out)
    out = _LONG_TOKEN_RE.sub(lambda m: _mask_keep4(m.group(0)), out)
    return out

SETTINGS_ERROR_KEY = {
    "auth_failed": "auth_failed",
    "forbidden": "forbidden",
    "not_found": "not_found",
    "rate_limited": "rate_limited",
    "connection_timeout": "connection_timeout",
    "connection_failed": "connection_failed",
    "http_error": "http_error",
    "blocked": "blocked",
    "refused": "blocked",
    "truncated": "translate_failed",
    "empty_response": "translate_failed",
    "api_error": "translate_failed",
}


class TranslateError(Exception):
    """雲端翻譯失敗（HTTP／連線／回應判定）。"""

    def __init__(
        self,
        kind: str,
        status: int | None,
        error_type: str,
        message: str,
    ) -> None:
        self.kind = kind
        self.status = status
        self.error_type = error_type
        self.message = message
        super().__init__(message)


def build_error(
    tag: str,
    kind: str,
    status: int | None,
    error_type: str,
    message: str,
) -> TranslateError:
    """記 warning（不含 headers／body）並回 TranslateError；message 截 300 字。"""
    msg = redact_secrets((message or "")[:_MESSAGE_LIMIT])
    logger.warning("[%s] %s status=%s type=%s msg=%s", tag, kind, status, error_type, msg)
    return TranslateError(kind, status, error_type, msg)


def failure_category(kind: str) -> str:
    """blocked／rate_limited／other 三類（供使用者提示分流）。"""
    if kind in ("blocked", "refused"):
        return "blocked"
    if kind == "rate_limited":
        return "rate_limited"
    return "other"


def settings_error_key(kind: str) -> str:
    return SETTINGS_ERROR_KEY.get(kind, "translate_failed")


def finalize_translation(tag: str, text: str) -> str:
    """清掉 think／thought 區塊；標記不成對或清完為空 → empty_response。"""
    for _ in range(_MAX_CLEAN_PASSES):
        cleaned = _THINK_BLOCK_RE.sub("", text)
        if cleaned == text:
            break
        text = cleaned
    text = text.strip()
    if _STRAY_MARKER_RE.search(text):
        raise build_error(tag, "empty_response", None, "", "unpaired thinking marker")
    if not text:
        raise build_error(tag, "empty_response", None, "", "empty text after cleaning")
    return text


async def cloud_request(
    tag: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    json: Any = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """送出請求並回未檢查狀態的 Response；HTTP 4xx/5xx 由呼叫端判斷。

    method 只接受 "post"／"get"（不分大小寫），其他值拋 ValueError。
    """
    verb = method.lower()
    if verb not in ("post", "get"):
        raise ValueError(f"unsupported method: {method}")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if verb == "post":
                return await client.post(url, headers=headers, json=json)
            return await client.get(url, headers=headers, params=params)
    except httpx.TimeoutException as e:
        raise build_error(tag, "connection_timeout", None, "", str(e)) from e
    except (httpx.LocalProtocolError, UnicodeEncodeError):
        # 金鑰含空白／換行／非 ASCII → h11／httpx 拒送；str(e) 內含金鑰，絕不可進 message／log
        raise build_error(
            tag, "auth_failed", None, "invalid_api_key_format", _ILLEGAL_KEY_MESSAGE
        ) from None
    except (httpx.HTTPError, OSError) as e:
        raise build_error(tag, "connection_failed", None, "", str(e)) from e
