"""
OpenAI 相容 chat/completions 請求／解析／錯誤分類（OpenAI 翻譯唯一來源）。

不 import web.*、不 import core.translate_service。
失敗一律拋 TranslateError；log 只經 build_error。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from core.cloud_translate import (
    TranslateError,
    build_error,
    cloud_request,
    finalize_translation,
)

TAG = "OpenAI"

OPENAI_OFFICIAL_BASE_URL = "https://api.openai.com/v1"
OPENAI_NON_CHAT_TOKENS = (
    "embedding",
    "tts",
    "whisper",
    "audio",
    "transcribe",
    "realtime",
    "image",
    "dall-e",
    "moderation",
    "search",
    "codex",
)
_DATE_SUFFIX_RE = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")


def pick_official_models(models: list[tuple[str, int | None]]) -> list[str]:
    """過濾 luna／terra／mini（不含 nano）、剔除非聊天類型、去重日期快照後排序。"""
    candidates: list[tuple[str, int | None]] = []
    for mid_raw, created in models:
        mid = (mid_raw or "").lower()
        if not (any(k in mid for k in ("luna", "terra", "mini")) and "nano" not in mid):
            continue
        if any(tok in mid for tok in OPENAI_NON_CHAT_TOKENS):
            continue
        candidates.append((mid_raw, created))

    ids_lower = {m.lower() for m, _ in candidates}
    filtered: list[tuple[str, int | None]] = []
    for mid_raw, created in candidates:
        mid = mid_raw.lower()
        m = _DATE_SUFFIX_RE.search(mid)
        if m is not None and mid[: m.start()] in ids_lower:
            continue
        filtered.append((mid_raw, created))

    filtered.sort(key=lambda item: (item[1] is None, -(item[1] or 0), item[0].lower()))
    return [mid for mid, _ in filtered]


def default_official_model(models: list[str]) -> str:
    """第一個含 luna 的，否則第一個含 mini 的，否則空字串。"""
    for mid in models:
        if "luna" in mid.lower():
            return mid
    for mid in models:
        if "mini" in mid.lower():
            return mid
    return ""


def build_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def build_translate_payload(model: str, prompt: str) -> dict[str, Any]:
    # 刻意不送任何生成參數（上限／溫度／思考）
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }


def extract_text(data: dict) -> str:
    """判定順序見 CD-171-4（先中先贏）；成功回非空譯文，失敗拋 TranslateError。"""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise build_error(TAG, "api_error", None, "", "response missing choices")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        message = {}

    finish_reason = choice.get("finish_reason")
    if finish_reason in ("content_filter", "refusal"):
        raise build_error(TAG, "blocked", None, str(finish_reason), f"finish_reason={finish_reason}")
    if message.get("refusal"):
        raise build_error(TAG, "blocked", None, "refusal", "message.refusal present")
    if finish_reason == "length":
        raise build_error(TAG, "truncated", None, "length", "finish_reason=length")
    if finish_reason not in (None, "", "stop"):
        # fail-closed：未知終止原因（error／insufficient_system_resource…）帶部分內容不得當成功
        raise build_error(TAG, "truncated", None, str(finish_reason), f"finish_reason={finish_reason}")

    content = message.get("content")
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        raise build_error(TAG, "empty_response", None, "", "empty text content")
    return finalize_translation(TAG, text)


def classify_http_error(resp: httpx.Response) -> TranslateError:
    """依狀態碼與 error 欄位分類；非 JSON 本體仍回 TranslateError。"""
    status = resp.status_code
    err_type = ""
    message = ""
    has_reasons = False
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            err_type = str(err.get("type") or "")
            message = str(err.get("message") or "")
            meta = err.get("metadata")
            has_reasons = isinstance(meta, dict) and "reasons" in meta
    except Exception:
        err_type = ""
        message = getattr(resp, "reason_phrase", "") or ""

    if status == 401:
        return build_error(TAG, "auth_failed", status, err_type, message)
    if status == 403:
        lowered = message.lower()
        if has_reasons or "moderation" in lowered or "flagged" in lowered:
            return build_error(TAG, "blocked", status, err_type, message)
        return build_error(TAG, "forbidden", status, err_type, message)
    if status == 404:
        return build_error(TAG, "not_found", status, err_type, message)
    if status in (429, 402):
        return build_error(TAG, "rate_limited", status, err_type, message)
    return build_error(TAG, "http_error", status, err_type, message)


async def request_translation(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    *,
    timeout: float,
) -> str:
    """POST <base_url>/chat/completions；成功回非空 str，失敗拋 TranslateError。"""
    resp = await cloud_request(
        TAG,
        "POST",
        base_url.rstrip("/") + "/chat/completions",
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
