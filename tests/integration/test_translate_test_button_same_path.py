"""測試鈕與真翻譯走同一條路（TASK-171-T4）：同金鑰／模型／locale 下，
測試端點與 translate_single 外送的 url／headers／json 必須相等（不比 timeout）。

表驅動：T5／T7 往 ROWS 尾端補列即可。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from core.translate_service import (
    ClaudeTranslateService,
    GeminiTranslateService,
    OllamaTranslateService,
    OpenAICompatibleTranslateService,
)
from web.app import app

client = TestClient(app)

KEY = "PARITY-KEY-aaaa"
TITLE = "新人女優デビュー"
BASE = "https://api.example.com/v1"
OLLAMA_URL = "http://ollama.test:11434"


@dataclass(frozen=True)
class Row:
    id: str
    make_service: Callable[[str, str], Any]  # (model, locale) -> service
    endpoint: str
    config_target: str  # load_config 的 patch 位置
    config: Callable[[], dict]
    model: str
    success_body: dict
    extra_body: dict = field(default_factory=dict)  # 端點額外要的 body 欄位
    compare_headers: bool = True  # Ollama 不送 headers


ROWS = [
    Row(
        id="gemini",
        make_service=lambda m, loc: GeminiTranslateService({"api_key": KEY, "model": m}, loc),
        endpoint="/api/gemini/test-translate",
        config_target="web.routers.gemini.load_config",
        config=lambda: {"general": {"locale": "zh-TW"}, "translate": {"gemini": {"api_key": KEY}}},
        model="gemini-flash-lite-latest",
        success_body={"candidates": [{"content": {"parts": [{"text": "新人女優出道"}]}}]},
    ),
    Row(
        id="claude",
        make_service=lambda m, loc: ClaudeTranslateService({"api_key": KEY, "model": m}, loc),
        endpoint="/api/claude/test",
        config_target="web.routers.claude_translate.load_config",
        config=lambda: {"general": {"locale": "zh-TW"}, "translate": {"claude": {"api_key": KEY}}},
        model="claude-haiku-5-5",
        success_body={"content": [{"type": "text", "text": "新人女優出道"}], "stop_reason": "end_turn"},
    ),
    Row(
        id="openai",
        make_service=lambda m, loc: OpenAICompatibleTranslateService(
            {"base_url": BASE, "api_key": KEY, "model": m}, loc
        ),
        endpoint="/api/openai/test",
        config_target="web.routers.openai_translate.load_config",
        config=lambda: {"general": {"locale": "zh-TW"}, "translate": {"openai": {"api_key": KEY}}},
        model="gpt-4o-mini",
        success_body={"choices": [{"message": {"content": "新人女優出道"}, "finish_reason": "stop"}]},
        extra_body={"base_url": BASE},
    ),
    Row(
        id="ollama",
        make_service=lambda m, loc: OllamaTranslateService({"url": OLLAMA_URL, "model": m}, loc),
        endpoint="/api/ollama/test",
        config_target="web.routers.config.load_config",
        config=lambda: {"general": {"locale": "zh-TW"}},
        model="qwen3:8b",
        success_body={"message": {"content": "新人女優出道"}},
        extra_body={"url": OLLAMA_URL},
        compare_headers=False,
    ),
    Row(
        id="openai_official",
        make_service=lambda m, loc: OpenAICompatibleTranslateService(
            {"base_url": "https://api.openai.com/v1", "api_key": KEY, "model": m}, loc
        ),
        endpoint="/api/openai/official/test",
        config_target="web.routers.openai_translate.load_config",
        config=lambda: {
            "general": {"locale": "zh-TW"},
            "translate": {"openai_official": {"api_key": KEY}},
        },
        model="gpt-4o-mini",
        success_body={"choices": [{"message": {"content": "新人女優出道"}, "finish_reason": "stop"}]},
    ),
]


def _mock_client(body: dict):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json = MagicMock(return_value=body)
    resp.raise_for_status = MagicMock(return_value=None)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, mock_client


def _sent(mock_post, compare_headers: bool = True) -> tuple:
    c = mock_post.call_args_list[-1]
    headers = dict(c.kwargs["headers"]) if compare_headers else None
    return c.args[0], headers, c.kwargs["json"]


@pytest.mark.parametrize("row", ROWS, ids=[r.id for r in ROWS])
async def test_test_button_matches_translate_single(row: Row):
    cm, mock_client = _mock_client(row.success_body)
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm), \
         patch(row.config_target, return_value=row.config()):
        service = row.make_service(row.model, "zh-TW")
        result = await service.translate_single(TITLE)
        assert result, "引擎應回譯文"
        assert mock_client.post.call_count == 1
        engine_sent = _sent(mock_client.post, row.compare_headers)

        # TestClient 為同步，放到執行緒避免卡 event loop
        import asyncio
        resp = await asyncio.to_thread(
            client.post, row.endpoint, json={"api_key": KEY, "model": row.model, **row.extra_body}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True, resp.json()
        assert mock_client.post.call_count == 2
        button_sent = _sent(mock_client.post, row.compare_headers)

    assert button_sent[0] == engine_sent[0]
    assert button_sent[1] == engine_sent[1]
    assert button_sent[2] == engine_sent[2]
    if row.id == "gemini":
        assert "safetySettings" in button_sent[2]
        assert "generationConfig" not in button_sent[2]
    if row.id == "openai":
        assert set(button_sent[2].keys()) == {"model", "messages"}


