"""Opaque credential inventory, masking, and resolve helpers (TASK-114c-T1).

All public symbols are pure functions / constants — zero I/O, zero import of web.
Consumers load config themselves and pass dicts in.
"""

from __future__ import annotations

import copy
from typing import Any

# CD-114c-1: four opaque secrets. Single inventory for render_config_secrets.
SECRET_FIELDS: tuple[str, ...] = (
    "translate.gemini.api_key",
    "translate.openai.api_key",
    "translate.claude.api_key",
    "translate.openai_official.api_key",
    "metatube.token",
    "ai_services.image_similar.api_key",
    "ai_services.faces.api_key",
)

# CD-114c-2: U+2022 BULLET × 4 (not ASCII *, not U+25CF).
_BULLET = "\u2022"
_MASK4 = _BULLET * 4


def mask_secret(value: str) -> str:
    """Project a secret for GET responses and input previews (CD-206-7).

    - empty → empty (UI must distinguish unset vs set)
    - shorter than 16 code points → full mask (short tokens never leak a tail)
    - 16+ code points → first 4 + mask + last 4 (user can recognise which key)
    """
    if not value:
        return ""
    if len(value) < 16:
        return _MASK4
    return value[:4] + _MASK4 + value[-4:]


def resolve_secret(incoming: str, stored: str) -> str:
    """Browser may re-submit mask_secret(stored) when the user did not edit.

    Three-state pure function (wiring to PUT/connect/test endpoints is T2):
    - sentinel (incoming == mask(stored)) → keep stored
    - new plaintext → adopt incoming
    - empty string → clear (mask of non-empty is never "")
    """
    return stored if incoming == mask_secret(stored) else incoming


def read_secret(cfg: dict, dotted: str) -> str:
    """Read a dotted-path secret from a config dict.

    Missing intermediate / terminal keys, or a non-str value → \"\".
    Answers only \"what is the value\" — no masking, no validation.
    """
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return ""
        node = node[part]
    if not isinstance(node, str):
        return ""
    return node


def secret_paths(cfg: dict) -> tuple[str, ...]:
    """Static secret paths plus one path per custom OpenAI-compatible group.

    Custom groups live under ``translate.openai_custom.<id>.api_key`` and keep
    dict order after the seven static fields. Missing nests or non-dict values
    fall back to the static fields only.
    """
    paths = list(SECRET_FIELDS)
    translate = cfg.get("translate") if isinstance(cfg, dict) else None
    custom = translate.get("openai_custom") if isinstance(translate, dict) else None
    if isinstance(custom, dict):
        for group_id in custom:
            if isinstance(group_id, str):
                paths.append(f"translate.openai_custom.{group_id}.api_key")
    return tuple(paths)


def inject_secrets(cfg: dict, snapshot: dict) -> dict:
    """Merge cached vault values into cfg in place and return the same dict.

    Only paths from secret_paths(cfg) are visited, so snapshot entries for
    removed custom groups are ignored. A truthy snapshot value overwrites the
    leaf (creating the leaf key when its parent dict exists); a missing or
    falsy value keeps whatever cfg already holds, including on-disk plaintext.
    Missing parent dicts are never created.
    """
    for path in secret_paths(cfg):
        cached = snapshot.get(path)
        if not cached:
            continue
        parts = path.split(".")
        node: Any = cfg
        for part in parts[:-1]:
            if not isinstance(node, dict):
                node = None
                break
            child = node.get(part)
            if not isinstance(child, dict):
                node = None
                break
            node = child
        if not isinstance(node, dict):
            continue
        node[parts[-1]] = cached
    return cfg


def render_config_secrets(cfg: dict) -> dict:
    """Deep-copy cfg and mask every path in secret_paths(cfg).

    Does not mutate the input. Missing paths are skipped (no empty nests created).
    """
    out = copy.deepcopy(cfg)
    for dotted in secret_paths(cfg):
        parts = dotted.split(".")
        node: Any = out
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if not isinstance(node, dict):
            continue
        leaf = parts[-1]
        if leaf not in node:
            continue
        value = node[leaf]
        if isinstance(value, str):
            node[leaf] = mask_secret(value)
    return out
