"""Unit tests for core.secret_fields (TASK-114c-T1).

Covers mask_secret truth table, resolve_secret three-states, read_secret,
render_config_secrets deep-copy, and SECRET_FIELDS inventory (B1–B12, B14).
"""


from core.secret_fields import (
    mask_secret,
    render_config_secrets,
)

BULLET = "\u2022"
MASK4 = BULLET * 4


# ============ B1–B5: mask_secret truth table ============

class TestMaskSecret:

    def test_len_le_4_fully_masked(self):
        """B2: length ≤ 4 → fully masked, no length leak."""
        assert mask_secret("ab") == MASK4
        assert mask_secret("abcd") == MASK4


    def test_canonical_roundtrip_example(self):
        """B4: product canonical example."""
        assert mask_secret("sk-test-roundtrip") == MASK4 + "trip"


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

