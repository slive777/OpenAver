"""T7a: tagging pure functions (parse / vocab map / classify / resolve)."""

from __future__ import annotations

import pytest

from core.ai_services.tagging import (
    TaggingFailure,
    build_system_prompt,
    classify_failure,
    parse_tags,
    resolve_vision_conn,
    to_display_names,
)
from core.ai_services.tagging_vocab import VocabItem
from core.ai_services.vision_chat import VisionConn
from core.cloud_translate import TranslateError
from core.openai_client import OPENAI_OFFICIAL_BASE_URL


def test_parse_tags_three_way_boundary():
    cases = [
        ('{"tags":[]}}', "ok", []),
        (
            '前言\n```json\n{"tags":[{"tag":"制服","confidence":"mid"}]}\n```\n後語',
            "ok",
            ["制服"],
        ),
        ('{"tags":["制服","水着"]}', "ok", ["制服", "水着"]),
        ('{"foo":1}', "bad", []),
        ("{not json", "bad", []),
        ("この画像では適切なタグが見つかりません。", "refused", []),
        ("這張海報看不清楚，無法標註。", "refused", []),
    ]
    for text, status, tags in cases:
        got = parse_tags(text)
        assert got.status == status, text
        if status == "ok":
            assert got.tags == tags, text


def test_vocab_names_map_to_display_names_and_drop_unknown():
    vocab = [
        VocabItem(
            name="校服",
            source="builtin",
            group="服裝",
            definition="學生制服",
            model_name="制服",
        ),
        VocabItem(
            name="泳裝",
            source="builtin",
            group="服裝",
            definition="一般泳裝",
            model_name="水着",
        ),
        VocabItem(
            name="我的標籤",
            source="custom",
            group="自訂",
            definition="自訂說明",
            model_name="我的標籤",
        ),
    ]
    raw = ["制服", "泳裝", "制服", "校服", "詞表外的字", "我的標籤", 123, None]
    assert to_display_names(raw, vocab) == ["校服", "泳裝", "我的標籤"]

    prompt = build_system_prompt(vocab)
    assert "【自訂】" in prompt
    assert "我的標籤" in prompt
    assert '- 「我的標籤」 ＝ 自訂說明' in prompt

    bare = [
        VocabItem(
            name="無說明字",
            source="custom",
            group="自訂",
            definition="",
            model_name="無說明字",
        )
    ]
    bare_prompt = build_system_prompt(bare)
    assert '- 「無說明字」' in bare_prompt
    assert '- 「無說明字」 ＝' not in bare_prompt


def test_resolve_vision_conn_table():
    def cfg(provider, model, **translate_bits):
        base = {
            "ai_services": {"tags": {"provider": provider, "model": model}},
            "translate": {
                "claude": {"api_key": "", "model": "Y"},
                "gemini": {"api_key": "", "model": "Y"},
                "openai": {"api_key": "", "base_url": "", "model": "Y"},
                "openai_official": {"api_key": "", "model": "Y"},
                "ollama": {"url": "", "model": "Y"},
            },
        }
        for path, value in translate_bits.items():
            parts = path.split(".")
            node = base["translate"]
            for p in parts[:-1]:
                node = node[p]
            node[parts[-1]] = value
        return base

    ok_cases = [
        (
            cfg("ollama", "llava", **{"ollama.url": "http://ollama.local:11434"}),
            VisionConn("ollama", "llava", "http://ollama.local:11434", ""),
        ),
        (
            cfg("gemini", "gemini-2.0-flash", **{"gemini.api_key": "gk-1"}),
            VisionConn("gemini", "gemini-2.0-flash", "", "gk-1"),
        ),
        (
            cfg("claude", "claude-haiku-5-5", **{"claude.api_key": "ck-1"}),
            VisionConn("claude", "claude-haiku-5-5", "", "ck-1"),
        ),
        (
            cfg(
                "openai",
                "gpt-4o",
                **{"openai.base_url": "http://llm.local/v1", "openai.api_key": "ok-1"},
            ),
            VisionConn("openai", "gpt-4o", "http://llm.local/v1", "ok-1"),
        ),
        (
            cfg("openai_official", "gpt-4o-mini", **{"openai_official.api_key": "ok-off"}),
            VisionConn(
                "openai_official", "gpt-4o-mini", OPENAI_OFFICIAL_BASE_URL, "ok-off"
            ),
        ),
    ]
    seen = set()
    for config, expected in ok_cases:
        got = resolve_vision_conn(config)
        assert got == expected
        seen.add((got.provider, got.model, got.base_url, got.api_key))
    assert len(seen) == 5

    # ollama 缺 url → 預設
    got = resolve_vision_conn(cfg("ollama", "llava"))
    assert got.base_url == "http://localhost:11434"

    # tags.model 優先於 translate.<p>.model
    got = resolve_vision_conn(
        cfg("claude", "X", **{"claude.api_key": "ck-2", "claude.model": "Y"})
    )
    assert got.model == "X"

    bad_cases = [
        cfg("", "m"),
        cfg("claude", ""),
        cfg("gemini", "m"),  # 缺金鑰
        cfg("openai", "m"),  # 缺 base_url
        cfg("openai_official", "m"),  # 缺金鑰
        cfg("unknown", "m"),
    ]
    for config in bad_cases:
        with pytest.raises(TaggingFailure) as ei:
            resolve_vision_conn(config)
        assert ei.value.reason == "not_configured"


def test_classify_failure_table():
    cases = [
        ("blocked", None, None),
        ("refused", None, None),
        ("connection_failed", None, "unreachable"),
        ("not_found", 404, "unreachable"),
        ("http_error", 422, "model_unsupported"),
        ("http_error", 503, "unreachable"),
        ("truncated", None, "bad_response"),
    ]
    for kind, status, expect in cases:
        exc = TranslateError(kind, status, "", "msg")
        got = classify_failure(exc)
        if expect is None:
            assert got is None
        else:
            assert isinstance(got, TaggingFailure)
            assert got.reason == expect
            assert got.detail == kind
