"""TASK-186-T1：官方 OpenAI 過濾／遷移／factory（離線，不連網）。"""

from __future__ import annotations

import json
from pathlib import Path

import core.config as core_config
from core.config import load_config
from core.translate_service import (
    OpenAICompatibleTranslateService,
    create_translate_service,
)


def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) pick_official_models + default_official_model 表驅動
# ---------------------------------------------------------------------------

# 類型排除：每個 token 一列，id 同時含 mini（或 luna／terra）以免被關鍵字閘擋掉。
_EXCL_IDS = {
    "embedding": "text-embedding-3-mini",
    "tts": "gpt-4o-mini-tts",
    "whisper": "gpt-4o-mini-whisper",
    "audio": "gpt-4o-mini-audio-preview",
    "transcribe": "gpt-4o-mini-transcribe",
    "realtime": "gpt-4o-mini-realtime-preview",
    "image": "gpt-4o-mini-image",
    "dall-e": "dall-e-mini",
    "moderation": "gpt-4o-mini-moderation",
    "search": "gpt-4o-mini-search-preview",
    "codex": "codex-mini-latest",
}

# 每列一個失敗原因（類型排除列由上表展開）。
_PICK_CASES: list[tuple[str, list[tuple[str, int | None]], list[str], str]] = [
    ("nano_with_mini_dropped",
     [("gpt-4o-mini-nano", 2), ("gpt-4o-mini", 1)], ["gpt-4o-mini"], "gpt-4o-mini"),
    *[
        (f"excl_{tok.replace('-', '_')}",
         [(mid, 9), ("gpt-4o-mini", 1)], ["gpt-4o-mini"], "gpt-4o-mini")
        for tok, mid in _EXCL_IDS.items()
    ],
    ("snapshot_only_dated_kept",
     [("gpt-4o-mini-2024-07-18", 1)], ["gpt-4o-mini-2024-07-18"], "gpt-4o-mini-2024-07-18"),
    ("snapshot_both_keep_undated",
     [("gpt-4o-mini", 2), ("gpt-4o-mini-2024-07-18", 1)], ["gpt-4o-mini"], "gpt-4o-mini"),
    ("snapshot_yyyymmdd_both",
     [("gpt-4o-mini", 2), ("gpt-4o-mini-20240718", 1)], ["gpt-4o-mini"], "gpt-4o-mini"),
    ("sort_created_none_alpha",
     [("b-mini", 100), ("a-mini", 100), ("c-mini", None), ("d-mini", 200)],
     ["d-mini", "a-mini", "b-mini", "c-mini"], "d-mini"),
    ("keyword_keep_luna_terra",
     [("gpt-luna-1", 3), ("gpt-terra-1", 2), ("gpt-other", 9)],
     ["gpt-luna-1", "gpt-terra-1"], "gpt-luna-1"),
    ("default_prefers_luna_over_mini",
     [("gpt-4o-mini", 9), ("chatgpt-luna", 1)],
     ["gpt-4o-mini", "chatgpt-luna"], "chatgpt-luna"),
    ("default_mini_when_no_luna",
     [("gpt-terra-1", 2), ("gpt-4o-mini", 1)], ["gpt-terra-1", "gpt-4o-mini"], "gpt-4o-mini"),
    ("default_empty_when_only_terra", [("gpt-terra-1", 1)], ["gpt-terra-1"], ""),
    ("default_empty_list", [], [], ""),
]


def test_pick_official_models():
    from core.openai_client import (
        OPENAI_NON_CHAT_TOKENS,
        default_official_model,
        pick_official_models,
    )

    assert tuple(_EXCL_IDS) == OPENAI_NON_CHAT_TOKENS
    for name, models, expected_ids, expected_default in _PICK_CASES:
        got = pick_official_models(models)
        assert got == expected_ids, f"{name}: pick got {got!r}"
        assert default_official_model(got) == expected_default, (
            f"{name}: default got {default_official_model(got)!r}"
        )


# ---------------------------------------------------------------------------
# (b) 遷移：補巢且不改 provider；巢已存在不覆蓋
# ---------------------------------------------------------------------------

def test_translate_migration_adds_official_nest(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {
        "translate": {
            "enabled": True,
            "provider": "openai",
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-compat",
                "model": "gpt-4o",
            },
        }
    })
    monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")

    result = load_config()
    t = result["translate"]
    assert t["provider"] == "openai"
    assert t["openai_official"] == {"api_key": "", "model": ""}

    # 巢已存在含金鑰 → 不被覆蓋（同一支測試函式）
    _write_config(config_path, {
        "translate": {
            "enabled": True,
            "provider": "openai",
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-compat",
                "model": "gpt-4o",
            },
            "openai_official": {
                "api_key": "sk-keep-me",
                "model": "chatgpt-luna",
            },
        }
    })
    result2 = load_config()
    t2 = result2["translate"]
    assert t2["provider"] == "openai"
    assert t2["openai_official"]["api_key"] == "sk-keep-me"
    assert t2["openai_official"]["model"] == "chatgpt-luna"


# ---------------------------------------------------------------------------
# (c) factory openai_official → 官方 base_url
# ---------------------------------------------------------------------------

def test_factory_openai_official():
    service = create_translate_service({
        "provider": "openai_official",
        "openai_official": {"api_key": "k", "model": "m"},
    })
    from core.openai_client import OPENAI_OFFICIAL_BASE_URL

    assert isinstance(service, OpenAICompatibleTranslateService)
    assert service.base_url == OPENAI_OFFICIAL_BASE_URL
    assert service.api_key == "k"
    assert service.model == "m"
