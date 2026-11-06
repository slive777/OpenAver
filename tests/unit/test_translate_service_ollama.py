"""171-T7：OllamaTranslateService.translate_or_raise 失敗 kind 與 translate_single 包裝。"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.cloud_translate import TranslateError
from core.translate_service import OllamaTranslateService

URL = "http://ollama.test:11434"


def _cm(post_side_effect=None, status=200, content="翻譯結果"):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json = MagicMock(return_value={"message": {"content": content}})
    inst = MagicMock()
    if post_side_effect is not None:
        inst.post = AsyncMock(side_effect=post_side_effect)
    else:
        inst.post = AsyncMock(return_value=resp)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=inst)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, inst


def _svc(lang="zh-TW"):
    return OllamaTranslateService({"url": URL, "model": "qwen3:8b"}, lang)


FAILURES = [
    ("connection_failed", dict(post_side_effect=httpx.ConnectError("c"))),
]


@pytest.mark.asyncio
async def test_ollama_translate_or_raise_success():
    cm, inst = _cm()
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        assert await _svc().translate_or_raise("テスト") == "翻譯結果"
    assert inst.post.call_count == 1


@pytest.mark.asyncio
async def test_ollama_korean_locale_sends_korean_translation_prompt():
    cm, inst = _cm(content="한국어 번역")
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        assert await _svc("ko").translate_or_raise("日本語タイトル") == "한국어 번역"

    messages = inst.post.await_args.kwargs["json"]["messages"]
    assert "한국어" in messages[0]["content"]
    assert "日本語タイトル" in messages[1]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,kw", FAILURES, ids=[k for k, _ in FAILURES])
async def test_ollama_translate_or_raise_kinds(kind, kw):
    cm, _ = _cm(**kw)
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        with pytest.raises(TranslateError) as ei:
            await _svc().translate_or_raise("テスト")
    assert ei.value.kind == kind


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,kw", FAILURES, ids=[k for k, _ in FAILURES])
async def test_ollama_translate_single_swallows_translate_error(kind, kw):
    cm, inst = _cm(**kw)
    with patch("core.cloud_translate.httpx.AsyncClient", return_value=cm):
        assert await _svc().translate_single("テスト") == ""
    assert inst.post.call_count == 1


@pytest.mark.asyncio
async def test_ollama_translate_or_raise_ja_short_circuit():
    with patch("core.cloud_translate.httpx.AsyncClient") as ac:
        assert await _svc("ja").translate_or_raise("原題") == "原題"
    assert ac.call_count == 0
