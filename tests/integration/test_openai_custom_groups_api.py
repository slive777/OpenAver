"""Custom group validation and vault lifecycle through the config API."""

import hashlib
import json

import pytest

from core import config as core_config
from core import secret_store
from core.config import load_config, save_config
from core.secret_fields import mask_secret


@pytest.fixture(autouse=True)
def env(isolate_secret_store):
    save_config(load_config())
    return isolate_secret_store


def group(name, key=""):
    return {"name": name, "base_url": "", "model": "", "use_custom_model": False, "api_key": key}


@pytest.mark.parametrize(
    ("groups", "reason"),
    [
        ({f"oc{i:08x}": group(str(i)) for i in range(6)}, "too_many"),
        ({"oc01234567\n": group("name")}, "invalid_group_id"),
        ({"oc0123abcd": group("   ")}, "empty"),
        ({"oc0123abcd": group("𠀀" * 31)}, "too_long"),
        ({"oc0123abcd": group(" 預設 ")}, "reserved"),
        ({"oc0123abcd": group("OpenRouter"), "oc89abcdef": group(" openrouter ")}, "duplicate"),
        ({f"oc{i:08x}": group("  " + ("𠀀" * 30 if i == 0 else str(i)) + "  ")
          for i in range(5)}, None),
    ],
)
def test_group_rules_reject_bad_input(client, groups, reason):
    data = client.get("/api/config").json()["data"]
    data["translate"]["openai_custom"] = groups
    before = hashlib.sha256(core_config.CONFIG_PATH.read_bytes()).digest()
    result = client.put("/api/config", json=data).json()
    if reason is None:
        assert result["success"] is True
        assert client.get("/api/config").json()["data"]["translate"]["openai_custom"] == groups
    else:
        assert result["success"] is False
        assert result["reason"] == reason
        assert hashlib.sha256(core_config.CONFIG_PATH.read_bytes()).digest() == before
    if reason == "invalid_group_id":
        for gid in ("oc0123.bcd", "OC0123ABCD", "oc0123abc", "oc0123abcde", "", "../x"):
            data["translate"]["openai_custom"] = {gid: group("name")}
            result = client.put("/api/config", json=data).json()
            assert result["success"] is False
            assert result["reason"] == "invalid_group_id"
            assert hashlib.sha256(core_config.CONFIG_PATH.read_bytes()).digest() == before
    if reason == "empty":
        data["translate"]["openai_custom"] = {"oc0123abcd": group("")}
        result = client.put("/api/config", json=data).json()
        assert result["reason"] == "empty"
        assert hashlib.sha256(core_config.CONFIG_PATH.read_bytes()).digest() == before


def test_delete_group_resets_providers_and_vault(client):
    data = client.get("/api/config").json()["data"]
    data["translate"]["openai"]["api_key"] = "fake-key-default"
    data["translate"]["gemini"]["api_key"] = "fake-key-other"
    data["translate"]["openai_custom"] = {
        "oc0123abcd": group("first", "fake-key-aaaa"),
        "oc89abcdef": group("second", "fake-key-bbbb"),
    }
    data["translate"]["provider"] = "openai:oc0123abcd"
    data["ai_services"]["tags"]["provider"] = "openai:oc0123abcd"
    data["ai_services"]["tags"]["model"] = "fake-model"
    assert client.put("/api/config", json=data).json()["success"] is True
    response = client.get("/api/config")
    data = response.json()["data"]
    assert data["translate"]["openai_custom"]["oc0123abcd"]["api_key"] == mask_secret("fake-key-aaaa")
    assert "fake-key-aaaa" not in response.text
    first = "translate.openai_custom.oc0123abcd.api_key"
    second = "translate.openai_custom.oc89abcdef.api_key"
    default = "translate.openai.api_key"
    other = "translate.gemini.api_key"
    assert all(path in secret_store.snapshot() for path in (first, second, default, other))
    del data["translate"]["openai_custom"]["oc0123abcd"]
    assert client.put("/api/config", json=data).json()["success"] is True
    data = client.get("/api/config").json()["data"]
    assert data["translate"]["provider"] == "openai"
    assert data["ai_services"]["tags"]["provider"] == "openai"
    assert data["ai_services"]["tags"]["model"] == "fake-model"
    assert first not in secret_store.snapshot()
    assert all(path in secret_store.snapshot() for path in (second, default, other))
    data["translate"]["provider"] = "openai:oc89abcdef"
    data["ai_services"]["tags"]["provider"] = "openai:zzz"
    assert client.put("/api/config", json=data).json()["success"] is True
    data = client.get("/api/config").json()["data"]
    assert data["translate"]["provider"] == "openai:oc89abcdef"
    assert data["ai_services"]["tags"]["provider"] == "openai"
    data["translate"]["openai_custom"] = {}
    assert client.put("/api/config", json=data).json()["success"] is True
    assert client.get("/api/config").json()["data"]["translate"]["provider"] == "openai"
    assert second not in secret_store.snapshot()
    assert all(path in secret_store.snapshot() for path in (default, other))


def test_legacy_config_untouched(client):
    cfg = load_config()
    cfg["translate"].pop("openai_custom", None)
    cfg["translate"]["provider"] = "openai"
    cfg["translate"]["openai"]["api_key"] = "fake-key-legacy"
    save_config(cfg)
    assert "openai_custom" not in json.loads(core_config.CONFIG_PATH.read_text())["translate"]
    data = client.get("/api/config").json()["data"]
    before = data["translate"]["openai"].copy()
    assert client.put("/api/config", json=data).json()["success"] is True
    after = client.get("/api/config").json()["data"]
    assert after["translate"]["provider"] == "openai"
    assert after["translate"]["openai"] == before
    assert bool(secret_store.snapshot().get("translate.openai.api_key"))
