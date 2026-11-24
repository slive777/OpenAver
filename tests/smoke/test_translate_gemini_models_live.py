"""
test_translate_gemini_models_live.py - Gemini 模型翻譯 Smoke 金絲雀

只用於本地手動測試，不進 CI（需要真實 Gemini API Key 與外網）

執行方式：
    GEMINI_API_KEY=<KEY> pytest tests/smoke/test_translate_gemini_models_live.py -v -s

前提條件：
- 環境變數 GEMINI_API_KEY（唯一金鑰來源；沒有則整檔 skip）
- 可連 generativelanguage.googleapis.com（連不上／429 限流／5xx 伺服器暫時不可用 skip，不算紅）

走服務層真實路徑（與搜尋頁同一條），對各系列模型各翻一次無害片名，
確認譯文非空、且不夾思考標記（Gemma 4 的 <think>／<thought>）。
"""

import os
import time

import pytest

from core.cloud_translate import TranslateError
from core.translate_service import GeminiTranslateService
from core.gemini_client import list_models, pick_gemini_models

# 金鑰只留在環境變數；測試內以 os.environ[...] 直接當參數傳入，不綁區域變數
# （避免 --showlocals 的 traceback 印出金鑰）。
pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="未設定 GEMINI_API_KEY，跳過 Gemini 活 API 金絲雀",
    ),
]

TITLE = "大型新人 二階堂麗 AVデビュー"
_SERVER_ERROR_STATUSES = (500, 502, 503, 504)
_SKIP_KINDS = ("rate_limited", "connection_timeout", "connection_failed")


def _handle(model: str, kind: str, status) -> None:
    """限流／連線類 skip，其餘（含 blocked）fail；訊息只含 model／kind／status。"""
    if kind == "http_error" and status in _SERVER_ERROR_STATUSES:
        pytest.skip(f"Gemini 伺服器端暫時不可用 status={status}")
    if kind in _SKIP_KINDS:
        pytest.skip(f"{model} 暫不可用（kind={kind}）")
    pytest.fail(f"{model} 翻譯失敗 kind={kind} status={status}", pytrace=False)


@pytest.mark.parametrize("series", ["flash-lite", "flash", "gemma"])
async def test_gemini_model_translates_clean(series):
    models = pick_gemini_models(await list_models(os.environ["GEMINI_API_KEY"], timeout=30.0))
    def matches(name):
        name = name.lower()
        if series == "gemma":
            return name.removeprefix("models/").startswith("gemma-")
        if series == "flash-lite":
            return "flash-lite" in name
        return "flash" in name and "flash-lite" not in name

    model = next((m["name"].removeprefix("models/") for m in models if matches(m["name"])), None)
    assert model, f"找不到 {series} 模型"
    svc = GeminiTranslateService(
        {"api_key": os.environ["GEMINI_API_KEY"], "model": model}, "zh-TW"
    )
    start = time.perf_counter()
    try:
        result = await svc.translate_or_raise(TITLE)
    except TranslateError as e:
        _handle(model, e.kind, e.status)
    elapsed = time.perf_counter() - start
    print(f"[{model}] {elapsed:.1f}s -> {len(result)} chars")  # noqa: T201

    assert result.strip(), f"{model} 回空譯文"
    low = result.lower()
    assert "<think>" not in low, f"{model} 譯文夾帶 <think> 思考標記"
    assert "<thought>" not in low, f"{model} 譯文夾帶 <thought> 思考標記"
