"""Faces endpoint activation predicate (CD-187a-3). Stdlib-only."""

from __future__ import annotations


def active_in(cfg: dict) -> bool:
    """True iff ``ai_services.faces.enabled`` and ``url.strip()`` are both set."""
    faces = (cfg or {}).get("ai_services", {}).get("faces") or {}
    if not faces.get("enabled"):
        return False
    return bool((faces.get("url") or "").strip())
