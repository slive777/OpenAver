"""Custom OpenAI provider identifiers (CD-206-18)."""

import pytest

from core.openai_groups import custom_key_path, is_valid_group_id, parse_openai_provider


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai", None), ("ollama", None), ("", None),
        ("openai:oc0123abcd", "oc0123abcd"), ("openai:", None),
        ("openai:OC0123ABCD", None), ("openai:oc0123abc", None),
        ("openai:oc0123abcde", None), ("openai:oc0123abcd\n", None),
        ("openai:oc0123.bcd", None), ("openai:oc0123abcd:x", None),
    ],
)
def test_group_id_vectors(provider, expected):
    assert parse_openai_provider(provider) == expected
    assert parse_openai_provider(None) is None
    assert is_valid_group_id("oc0123abcd")
    assert custom_key_path("oc0123abcd") == "translate.openai_custom.oc0123abcd.api_key"
    for gid in ("oc01234567\n", "oc0123.bcd", "OC0123ABCD", "oc0123abc",
                "oc0123abcde", "", "../x", None):
        assert not is_valid_group_id(gid)
        with pytest.raises(ValueError):
            custom_key_path(gid)
