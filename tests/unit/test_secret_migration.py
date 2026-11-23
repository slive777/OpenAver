"""tests/unit/test_secret_migration.py — TASK-206a-T3 行為測試。

只用自編假金鑰；不印任何值。
"""

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import core.config as core_config
from core.secret_fields import SECRET_FIELDS


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


_FAKE_KEYS = {
    "translate.gemini.api_key": "FAKE-TEST-KEY-gemini-0001-xyzzy-plugh-AA",
    "translate.openai.api_key": "FAKE-TEST-KEY-openai-0002-xyzzy-plugh-BB",
    "translate.claude.api_key": "FAKE-TEST-KEY-claude-0003-xyzzy-plugh-CC",
    "translate.openai_official.api_key": "FAKE-TEST-KEY-official-0004-xyzzy-plugh-DD",
    "metatube.token": "FAKE-TEST-KEY-metatube-0005-xyzzy-plugh-EE",
    "ai_services.image_similar.api_key": "FAKE-TEST-KEY-similar-0006-xyzzy-plugh-FF",
    "ai_services.faces.api_key": "FAKE-TEST-KEY-faces-0007-xyzzy-plugh-GG",
}
_FAKE_NEW = {
    "translate.gemini.api_key": "FAKE-TEST-KEY-gemini-1001-xyzzy-plugh-QQ",
    "translate.openai.api_key": "FAKE-TEST-KEY-openai-1002-xyzzy-plugh-RR",
    "translate.claude.api_key": "FAKE-TEST-KEY-claude-1003-xyzzy-plugh-SS",
    "translate.openai_official.api_key": "FAKE-TEST-KEY-official-1004-xyzzy-plugh-TT",
    "metatube.token": "FAKE-TEST-KEY-metatube-1005-xyzzy-plugh-UU",
    "ai_services.image_similar.api_key": "FAKE-TEST-KEY-similar-1006-xyzzy-plugh-VV",
    "ai_services.faces.api_key": "FAKE-TEST-KEY-faces-1007-xyzzy-plugh-WW",
}
_FAKE_ROTATE_ONE = "FAKE-TEST-KEY-rotate-2001-xyzzy-plugh-ZZ"
_FAKE_D_NEW = "FAKE-TEST-KEY-d-new-3001-xyzzy-plugh-XX"
assert all(len(v) >= 20 for v in list(_FAKE_KEYS.values()) + list(_FAKE_NEW.values()) + [_FAKE_ROTATE_ONE, _FAKE_D_NEW])
assert len(set(list(_FAKE_KEYS.values()) + list(_FAKE_NEW.values()) + [_FAKE_ROTATE_ONE, _FAKE_D_NEW])) == 16


def _set_dotted(cfg, dotted, value):
    parts = dotted.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _get_dotted(cfg, dotted):
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _base_config_with(keys):
    cfg = core_config.AppConfig().model_dump()
    for path, value in keys.items():
        _set_dotted(cfg, path, value)
    return cfg


def _setup_isolated_config(isolate_secret_store, monkeypatch, keys):
    from core import secret_store as _ss

    root = isolate_secret_store
    config_path = root / "config.json"
    default_path = root / "config.default.json"
    default_path.write_text(json.dumps(core_config.AppConfig().model_dump()), encoding="utf-8")
    config_path.write_text(json.dumps(_base_config_with(keys)), encoding="utf-8")
    monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", default_path)
    return root, config_path


def _count_file_hits(root, values):
    hits = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            for fake in values:
                if fake.encode("utf-8") in data:
                    hits += 1
    return hits


def _read_raw(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_upgrade_moves_plaintext_out_of_config_and_into_vault(
    isolate_secret_store, tmp_path, monkeypatch
):
    from core import secret_store as _ss

    root, config_path = _setup_isolated_config(isolate_secret_store, monkeypatch, _FAKE_KEYS)
    assert _ss.snapshot() == {}
    core_config.migrate_config_secrets()
    raw = _read_raw(config_path)
    for path in SECRET_FIELDS:
        assert _get_dotted(raw, path) == ""
    assert _ss.snapshot() == dict(_FAKE_KEYS)
    assert _ss.verify_from_disk(dict(_FAKE_KEYS)) is True
    assert _count_file_hits(root, list(_FAKE_KEYS.values())) == 0
    sha_before = hashlib.sha256(config_path.read_bytes()).hexdigest()
    core_config.migrate_config_secrets()
    sha_after = hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert sha_before == sha_after
    assert _ss.snapshot() == dict(_FAKE_KEYS)
    core_config.reset_config_file()
    assert not config_path.exists()
    assert _ss.snapshot() == {}
    assert _ss.verify_from_disk({}) is True


def test_hand_written_plaintext_after_upgrade_replaces_vault_value(
    isolate_secret_store, tmp_path, monkeypatch
):
    from core import secret_store as _ss

    root, config_path = _setup_isolated_config(isolate_secret_store, monkeypatch, _FAKE_KEYS)
    core_config.migrate_config_secrets()
    assert _ss.snapshot() == dict(_FAKE_KEYS)
    raw = _read_raw(config_path)
    for path, value in _FAKE_NEW.items():
        _set_dotted(raw, path, value)
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    core_config.migrate_config_secrets()
    assert _ss.snapshot() == dict(_FAKE_NEW)
    raw2 = _read_raw(config_path)
    for path in SECRET_FIELDS:
        assert _get_dotted(raw2, path) == ""
    assert _count_file_hits(root, list(_FAKE_NEW.values())) == 0


def test_failed_readback_keeps_plaintext_and_cache_unpublished(
    isolate_secret_store, tmp_path, monkeypatch, caplog
):
    from core import secret_store as _ss

    root, config_path = _setup_isolated_config(isolate_secret_store, monkeypatch, _FAKE_KEYS)
    sha_before = hashlib.sha256(config_path.read_bytes()).hexdigest()
    orig_verify = core_config.secret_store.verify_from_disk
    monkeypatch.setattr(
        core_config.secret_store, "verify_from_disk", lambda expected: False
    )
    with caplog.at_level("WARNING"):
        core_config.migrate_config_secrets()
    sha_after = hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert sha_before == sha_after
    assert _ss.snapshot() == {}
    for fake in _FAKE_KEYS.values():
        assert fake not in caplog.text
    raw = _read_raw(config_path)
    for path, value in _FAKE_KEYS.items():
        assert _get_dotted(raw, path) == value
    monkeypatch.setattr(core_config.secret_store, "verify_from_disk", orig_verify)
    core_config.migrate_config_secrets()
    assert _ss.snapshot() == dict(_FAKE_KEYS)
    raw2 = _read_raw(config_path)
    for path in SECRET_FIELDS:
        assert _get_dotted(raw2, path) == ""


def test_vault_values_reach_config_readers_and_survive_restart(
    isolate_secret_store, tmp_path, monkeypatch
):
    from core import secret_store as _ss

    root, config_path = _setup_isolated_config(isolate_secret_store, monkeypatch, _FAKE_KEYS)
    core_config.migrate_config_secrets()
    assert _ss.snapshot() == dict(_FAKE_KEYS)
    _ss.reset_state_for_tests()
    assert _ss.snapshot() == {}
    orig_connect = sqlite3.connect
    calls = []
    def _counting(*args, **kwargs):
        calls.append(1)
        return orig_connect(*args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", _counting)
    cfg_unprimed = core_config.load_config()
    assert _get_dotted(cfg_unprimed, "translate.gemini.api_key") == ""
    assert len(calls) == 0
    monkeypatch.setattr(sqlite3, "connect", orig_connect)
    _ss.prime()
    cfg = core_config.load_config()
    for path, value in _FAKE_KEYS.items():
        assert _get_dotted(cfg, path) == value
    seen = {}
    def _mutator(inner):
        for path in SECRET_FIELDS:
            seen[path] = _get_dotted(inner, path)
    core_config.mutate_config(_mutator)
    for path, value in _FAKE_KEYS.items():
        assert seen[path] == value
    holder = {}
    def _rotator(inner):
        holder["before"] = _get_dotted(inner, "translate.gemini.api_key")
        _set_dotted(inner, "translate.gemini.api_key", _FAKE_D_NEW)
        _set_dotted(inner, "translate.claude.api_key", "")
        holder["caller_dict"] = copy.deepcopy(inner)
    core_config.mutate_config(_rotator)
    assert holder["before"] == _FAKE_KEYS["translate.gemini.api_key"]
    snap = _ss.snapshot()
    assert snap.get("translate.gemini.api_key") == _FAKE_D_NEW
    assert "translate.claude.api_key" not in snap
    assert _get_dotted(holder["caller_dict"], "translate.gemini.api_key") == _FAKE_D_NEW
    raw = _read_raw(config_path)
    assert _FAKE_D_NEW not in config_path.read_text(encoding="utf-8")
    for tmp_file in config_path.parent.glob("*.tmp"):
        assert _FAKE_D_NEW not in tmp_file.read_text(encoding="utf-8")
    assert _get_dotted(raw, "translate.gemini.api_key") == ""
    env = dict(os.environ)
    env["OPENAVER_DATA_DIR"] = str(root)
    code = (
        "from core import secret_store as s;"
        "s.prime();"
        "import json;"
        "ok = all(s.snapshot().get(k) == v for k, v in json.loads(%r).items());"
        "print(bool(ok));"
    ) % json.dumps({k: v for k, v in snap.items()})
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip().splitlines()[-1] == "True"
    assert _FAKE_D_NEW not in config_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "case", ["same_key_mutate", "legacy_migration_writeback", "partial_dict_save"]
)
def test_writes_without_secret_changes_never_touch_the_vault(
    isolate_secret_store, tmp_path, monkeypatch, case
):
    from core import secret_store as _ss

    root, config_path = _setup_isolated_config(isolate_secret_store, monkeypatch, _FAKE_KEYS)
    core_config.migrate_config_secrets()
    before = dict(_ss.snapshot())
    assert before == dict(_FAKE_KEYS)
    orig_connect = sqlite3.connect
    calls = []
    def _counting(*args, **kwargs):
        calls.append(1)
        return orig_connect(*args, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", _counting)
    if case == "same_key_mutate":
        def _mutator(inner):
            inner.setdefault("general", {})["last_notified_update_version"] = "v9.9.9-test"
        core_config.mutate_config(_mutator)
    elif case == "legacy_migration_writeback":
        raw = _read_raw(config_path)
        raw["avlist"] = {"directories": ["/videos"]}
        for path, value in _FAKE_KEYS.items():
            _set_dotted(raw, path, value)
        config_path.write_text(json.dumps(raw), encoding="utf-8")
        loaded = core_config.load_config()
        assert "gallery" in loaded
        on_disk = _read_raw(config_path)
        for path, value in _FAKE_KEYS.items():
            assert _get_dotted(on_disk, path) == value
    else:
        core_config.save_config({"general": {"theme": "dark"}})
    assert len(calls) == 0
    assert _ss.snapshot() == before
