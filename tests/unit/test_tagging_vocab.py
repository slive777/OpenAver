"""T3: tagging vocab loader + custom store (budgeted + data-preservation tests)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.ai_services.tagging_vocab import (
    VocabError,
    add_custom,
    load_builtin,
    merged,
    remove_custom,
)
from core.similar.canonicalize import _HARDCODED_ALIAS_MAP, _STOPWORDS  # noqa: PLC2701
from tests.unit._custom_source_fake import finalize_root  # noqa: PLC2701


def prepare_root(tmp_path, monkeypatch, *, finalize: bool = True):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    if finalize:
        finalize_root(root)
    return root


@pytest.fixture
def env(tmp_path, monkeypatch):
    return prepare_root(tmp_path, monkeypatch, finalize=True)


def test_shipped_vocab_is_self_consistent():
    items = load_builtin()
    assert len(items) == 29
    display_names = [item.name for item in items]
    model_names = [item.model_name for item in items]
    assert len(set(display_names)) == 29
    assert len(set(model_names)) == 29

    all_aliases: list[str] = []
    for item in items:
        for alias in item.aliases:
            assert alias not in display_names  # ①
            for other in items:
                if other is item:
                    continue
                assert alias != other.model_name  # ② own model_name allowed
            all_aliases.append(alias)
    assert len(all_aliases) == len(set(all_aliases))  # ③

    vocab_words = set(display_names) | set(model_names) | set(all_aliases)
    hard_keys = set(_HARDCODED_ALIAS_MAP)
    hard_vals = set(_HARDCODED_ALIAS_MAP.values())
    assert vocab_words.isdisjoint(hard_keys)  # ④
    assert vocab_words.isdisjoint(hard_vals)
    assert vocab_words.isdisjoint(_STOPWORDS)


@pytest.mark.parametrize(
    "case,setup,name,definition,reason",
    [
        ("empty", "ready", "   ", "", "name_empty"),
        ("too_long", "ready", "字" * 21, "", "name_too_long"),
        ("newline", "ready", "壞\n名", "", "name_invalid"),
        ("builtin_display", "ready", "校服", "", "name_conflict_builtin"),
        ("builtin_model", "ready", "コスプレ", "", "name_conflict_builtin"),
        ("duplicate", "dup", "JK", "", "name_exists"),
        ("not_finalized", "raw", "JK", "", "data_root_not_ready"),
    ],
)
def test_add_custom_rejects_invalid_names(
    tmp_path, monkeypatch, case, setup, name, definition, reason
):
    finalize = setup != "raw"
    root = prepare_root(tmp_path, monkeypatch, finalize=finalize)
    custom_path = root / "ai_tag_vocab.json"
    before = None
    if setup == "dup":
        add_custom("JK", "女高中生")
        before = custom_path.read_bytes()

    with pytest.raises(VocabError) as excinfo:
        add_custom(name, definition)
    assert excinfo.value.reason == reason

    if before is None:
        assert not custom_path.exists()
    else:
        assert custom_path.read_bytes() == before


def test_added_custom_word_is_in_next_merged_without_restart(env):
    item = add_custom("JK", "女高中生")
    assert item.name == "JK"
    assert item.definition == "女高中生"
    names = {v.name: v for v in merged()}
    assert "JK" in names
    assert names["JK"].definition == "女高中生"

    remove_custom("JK")
    assert all(v.name != "JK" for v in merged())

    with pytest.raises(VocabError) as excinfo:
        remove_custom("JK")
    assert excinfo.value.reason == "not_found"


def test_corrupt_custom_file_degrades_to_builtin_only(env):
    root = env
    path = root / "ai_tag_vocab.json"

    path.write_text("{not json", encoding="utf-8")
    assert len(merged()) == 29

    path.write_text('{"items": 5}', encoding="utf-8")
    assert len(merged()) == 29

    path.write_text(
        json.dumps(
            {"version": 1, "items": [5, {"name": ""}, {"name": "好字"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = merged()
    assert len(result) == 30
    customs = [v for v in result if v.source == "custom"]
    assert len(customs) == 1
    assert customs[0].name == "好字"


@pytest.mark.parametrize("case", ["bad_json", "os_error"])
def test_add_custom_refuses_when_existing_custom_file_unreadable(
    env, monkeypatch, case
):
    """Existing custom words must not be wiped when the file is temporarily unreadable."""
    path = env / "ai_tag_vocab.json"
    add_custom("舊字一", "說明一")
    add_custom("舊字二", "說明二")
    before = path.read_bytes()

    if case == "bad_json":
        path.write_bytes(b"{not json")
        before = path.read_bytes()
    else:
        real_read_text = Path.read_text

        def boom(self, *args, **kwargs):
            if self == path:
                raise OSError("simulated lock")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", boom)

    with pytest.raises(VocabError) as excinfo:
        add_custom("新字", "不該寫入")
    assert excinfo.value.reason == "custom_unreadable"
    assert path.read_bytes() == before
