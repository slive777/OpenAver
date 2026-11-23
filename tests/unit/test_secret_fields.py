"""Unit tests for core.secret_fields (TASK-114c-T1).

Covers mask_secret truth table, resolve_secret three-states, read_secret,
render_config_secrets deep-copy, and SECRET_FIELDS inventory (B1–B12, B14).
"""


import json
from pathlib import Path

import pytest

from core.secret_fields import (
    inject_secrets,
    mask_secret,
    render_config_secrets,
    secret_paths,
)

BULLET = "\u2022"
MASK4 = BULLET * 4

# Shared with web/static/js/shared/__tests__/secret-mask.test.mjs (BE-TEST-14).
_VECTOR_FILE = Path(__file__).resolve().parent.parent / "data" / "secret_mask_vectors.json"
_VECTORS = json.loads(_VECTOR_FILE.read_text(encoding="utf-8"))["vectors"]
assert len(_VECTORS) >= 12


@pytest.mark.parametrize("vec", _VECTORS, ids=[repr(v["input"]) for v in _VECTORS])
def test_mask_secret_vectors(vec):
    assert mask_secret(vec["input"]) == vec["expected"]


# ============ B1–B5: mask_secret truth table ============

class TestMaskSecret:

    def test_len_le_4_fully_masked(self):
        """B2: length ≤ 4 → fully masked, no length leak."""
        assert mask_secret("ab") == MASK4
        assert mask_secret("abcd") == MASK4


    def test_canonical_roundtrip_example(self):
        """B4: product canonical example."""
        assert mask_secret("sk-test-roundtrip") == "sk-t" + MASK4 + "trip"


# ============ 206a-T2: dynamic paths + vault injection ============

STATIC_PATHS = (
    "translate.gemini.api_key",
    "translate.openai.api_key",
    "translate.claude.api_key",
    "translate.openai_official.api_key",
    "metatube.token",
    "ai_services.image_similar.api_key",
    "ai_services.faces.api_key",
)


def _dynamic_cfg() -> dict:
    return {
        "translate": {
            "gemini": {"api_key": "file-gemini-plain-0001"},
            "openai": {"api_key": "file-openai-plain-0002"},
            "claude": {"api_key": "file-claude-plain-0003"},
            "openai_custom": {
                "grp-a": {"api_key": "file-custom-a-plain-0004"},
                "grp-b": {"api_key": ""},
            },
        },
        "metatube": {"url": "http://example.invalid:8080"},
        "ai_services": {
            "image_similar": {"api_key": "file-similar-plain-0006"},
            "faces": {"api_key": "file-faces-plain-0007"},
        },
    }


def test_inject_secrets_and_dynamic_paths():
    """Dynamic settings groups join the secret inventory; vault wins, file plaintext survives."""
    # ---- secret_paths: static-only shapes vs two custom groups ----
    assert secret_paths({}) == STATIC_PATHS
    assert secret_paths({"translate": {"gemini": {"api_key": ""}}}) == STATIC_PATHS
    assert secret_paths({"translate": {"openai_custom": []}}) == STATIC_PATHS

    two_groups = _dynamic_cfg()
    assert secret_paths(two_groups) == STATIC_PATHS + (
        "translate.openai_custom.grp-a.api_key",
        "translate.openai_custom.grp-b.api_key",
    )
    assert len(secret_paths(two_groups)) == 9

    # ---- inject_secrets ----
    cfg = _dynamic_cfg()
    snapshot = {
        # truthy → overwrite a different plaintext already on disk
        "translate.gemini.api_key": "vault-gemini-1111",
        # falsy → keep the file plaintext
        "translate.openai.api_key": "",
        # two custom groups: overwrite / fill
        "translate.openai_custom.grp-a.api_key": "vault-custom-a-3333",
        "translate.openai_custom.grp-b.api_key": "vault-custom-b-2222",
        # parent nest absent in cfg → do not create it
        "translate.openai_official.api_key": "vault-official-4444",
        # leaf key absent but parent exists → write the leaf
        "metatube.token": "vault-metatube-5555",
        "ai_services.image_similar.api_key": "vault-similar-6666",
        "ai_services.faces.api_key": "",
        # orphan name (group gone from cfg) → never injected
        "translate.openai_custom.gone-group.api_key": "vault-orphan-7777",
    }

    returned = inject_secrets(cfg, snapshot)

    assert returned is cfg
    assert cfg["translate"]["gemini"]["api_key"] == "vault-gemini-1111"
    assert cfg["translate"]["openai"]["api_key"] == "file-openai-plain-0002"
    assert cfg["translate"]["claude"]["api_key"] == "file-claude-plain-0003"
    assert cfg["metatube"]["token"] == "vault-metatube-5555"
    assert cfg["translate"]["openai_custom"]["grp-a"]["api_key"] == "vault-custom-a-3333"
    assert cfg["translate"]["openai_custom"]["grp-b"]["api_key"] == "vault-custom-b-2222"
    assert "gone-group" not in cfg["translate"]["openai_custom"]
    assert "openai_official" not in cfg["translate"]
    assert cfg["ai_services"]["image_similar"]["api_key"] == "vault-similar-6666"
    assert cfg["ai_services"]["faces"]["api_key"] == "file-faces-plain-0007"

    # ---- render_config_secrets: custom group paths masked, input untouched ----
    cfg = _dynamic_cfg()
    rendered = render_config_secrets(cfg)

    assert cfg["translate"]["openai_custom"]["grp-a"]["api_key"] == "file-custom-a-plain-0004"
    assert cfg["translate"]["openai_custom"]["grp-b"]["api_key"] == ""
    assert cfg["translate"]["gemini"]["api_key"] == "file-gemini-plain-0001"
    assert rendered["translate"]["openai_custom"]["grp-a"]["api_key"] == "file" + MASK4 + "0004"
    assert rendered["translate"]["openai_custom"]["grp-b"]["api_key"] == ""
    assert rendered["translate"]["gemini"]["api_key"] == "file" + MASK4 + "0001"


# ============ B6–B9: resolve_secret three-states ============


# ============ B10: read_secret ============


# ============ B11–B12: render_config_secrets ============

def _sample_cfg() -> dict:
    return {
        "translate": {
            "enabled": True,
            "provider": "openai",
            "gemini": {"api_key": "sk-test-roundtrip", "model": "gemini-flash-lite-latest"},
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test-roundtrip",
                "model": "gpt-4o",
            },
            "claude": {
                "api_key": "sk-test-roundtrip",
                "model": "claude-haiku-5-5",
            },
            "openai_official": {
                "api_key": "sk-test-roundtrip",
                "model": "",
            },
        },
        "metatube": {
            "enabled": True,
            "url": "http://user:pass@192.168.1.177:8080",
            "token": "mt-secret-token-xyz",
            "allow_lan": False,
        },
        "search": {
            "proxy_url": "http://proxy-user:proxy-pass@proxy.example:8080",
        },
        "general": {"theme": "dark"},
        "gallery": {"directories": []},
    }


class TestRenderConfigSecrets:
    def test_does_not_mutate_input(self):
        """B11: deep-copy — original dict remains plaintext after call."""
        cfg = _sample_cfg()
        original_openai = cfg["translate"]["openai"]["api_key"]
        original_gemini = cfg["translate"]["gemini"]["api_key"]
        original_claude = cfg["translate"]["claude"]["api_key"]
        original_official = cfg["translate"]["openai_official"]["api_key"]
        original_token = cfg["metatube"]["token"]
        cfg_id = id(cfg)

        rendered = render_config_secrets(cfg)

        assert id(rendered) != cfg_id
        assert cfg["translate"]["openai"]["api_key"] == original_openai
        assert cfg["translate"]["gemini"]["api_key"] == original_gemini
        assert cfg["translate"]["claude"]["api_key"] == original_claude
        assert cfg["translate"]["openai_official"]["api_key"] == original_official
        assert cfg["metatube"]["token"] == original_token
        assert cfg["translate"]["openai"]["api_key"] == "sk-test-roundtrip"
        assert rendered["translate"]["openai_official"]["api_key"] == mask_secret(
            "sk-test-roundtrip"
        )


# ============ B14: SECRET_FIELDS inventory ============

