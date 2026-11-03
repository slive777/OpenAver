"""
Gemini generateContent 請求／解析／錯誤分類（Gemini 翻譯唯一來源）。

不 import web.*、不 import core.translate_service。
失敗一律拋 TranslateError；log 只經 build_error。
"""

from __future__ import annotations

from typing import Any

import httpx

from core.cloud_translate import (
    TranslateError,
    build_error,
    cloud_request,
    finalize_translation,
)

TAG = "Gemini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

SAFETY_SETTINGS = (
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
)
BLOCKED_FINISH_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"})


def build_headers(api_key: str) -> dict[str, str]:
    return {"x-goog-api-key": api_key.strip()}


def build_translate_payload(model: str, prompt: str) -> dict[str, Any]:
    # model 在 URL 內，payload 不帶；刻意不送任何生成參數（上限／溫度／思考）
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [dict(s) for s in SAFETY_SETTINGS],
    }


def extract_text(data: dict) -> str:
    """判定順序見 CD-171-4（先中先贏）；成功回非空譯文，失敗拋 TranslateError。"""
    feedback = data.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise build_error(TAG, "blocked", None, str(feedback["blockReason"]), "prompt blocked")

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise build_error(TAG, "api_error", None, "", "response missing candidates")
    cand = candidates[0]

    finish_reason = cand.get("finishReason")
    if finish_reason in BLOCKED_FINISH_REASONS:
        raise build_error(TAG, "blocked", None, str(finish_reason), f"finishReason={finish_reason}")
    if finish_reason == "MAX_TOKENS":
        raise build_error(TAG, "truncated", None, "MAX_TOKENS", "finishReason=MAX_TOKENS")
    if finish_reason not in (None, "", "STOP"):
        # fail-closed：未知終止原因（RECITATION／OTHER…）帶部分文字不得當成功
        raise build_error(TAG, "truncated", None, str(finish_reason), f"finishReason={finish_reason}")

    content = cand.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        parts = []
    texts = [p.get("text") or "" for p in parts if isinstance(p, dict) and not p.get("thought")]
    text = "".join(texts).strip()
    if not text:
        raise build_error(TAG, "empty_response", None, "", "empty text content")
    return finalize_translation(TAG, text)


def classify_http_error(resp: httpx.Response) -> TranslateError:
    """依狀態碼與 error.status／details 分類；非 JSON 本體仍回 TranslateError。"""
    status = resp.status_code
    err_status = ""
    message = ""
    api_key_invalid = False
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            err_status = str(err.get("status") or "")
            message = str(err.get("message") or "")
            details = err.get("details")
            if isinstance(details, list):
                api_key_invalid = any(
                    isinstance(d, dict) and d.get("reason") == "API_KEY_INVALID" for d in details
                )
    except Exception:
        err_status = ""
        message = getattr(resp, "reason_phrase", "") or ""

    if status == 401:
        return build_error(TAG, "auth_failed", status, err_status, message)
    if status == 400 and (api_key_invalid or "API key not valid" in message):
        return build_error(TAG, "auth_failed", status, err_status, message)
    if status == 403:
        return build_error(TAG, "forbidden", status, err_status, message)
    if status == 404:
        return build_error(TAG, "not_found", status, err_status, message)
    if status in (429, 402) or err_status == "RESOURCE_EXHAUSTED":
        return build_error(TAG, "rate_limited", status, err_status, message)
    return build_error(TAG, "http_error", status, err_status, message)


async def request_translation(
    api_key: str,
    model: str,
    prompt: str,
    *,
    timeout: float,
) -> str:
    """POST :generateContent；成功回非空 str，失敗拋 TranslateError。"""
    resp = await cloud_request(
        TAG,
        "POST",
        f"{GEMINI_BASE_URL}/models/{model}:generateContent",
        headers=build_headers(api_key),
        timeout=timeout,
        json=build_translate_payload(model, prompt),
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise classify_http_error(e.response) from None

    try:
        data = resp.json()
    except Exception as e:
        raise build_error(TAG, "api_error", None, "", f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise build_error(TAG, "api_error", None, "", "response is not a JSON object")
    return extract_text(data)


def _strip_vision_data_uri(uri: str) -> str:
    return uri.split(",", 1)[1]


def build_vision_payload(
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
) -> dict[str, Any]:
    # model 在 URL 內，payload 不帶；刻意不送 generationConfig
    return {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": _strip_vision_data_uri(image_data_uri),
                        }
                    },
                    {"text": user_text},
                ]
            }
        ],
        "system_instruction": {"parts": [{"text": system}]},
        "safetySettings": [dict(s) for s in SAFETY_SETTINGS],
    }


async def request_vision(
    api_key: str,
    model: str,
    system: str,
    user_text: str,
    image_data_uri: str,
    *,
    timeout: float,
) -> str:
    """POST :generateContent with image；成功回非空 str，失敗拋 TranslateError。"""
    resp = await cloud_request(
        TAG,
        "POST",
        f"{GEMINI_BASE_URL}/models/{model}:generateContent",
        headers=build_headers(api_key),
        timeout=timeout,
        json=build_vision_payload(model, system, user_text, image_data_uri),
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise classify_http_error(e.response) from None

    try:
        data = resp.json()
    except Exception as e:
        raise build_error(TAG, "api_error", None, "", f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise build_error(TAG, "api_error", None, "", "response is not a JSON object")
    return extract_text(data)
