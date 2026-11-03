"""Builtin tag-alias seed (TASK-188b-T4 / CD-188b-7)."""

from __future__ import annotations

from core.logger import get_logger

logger = get_logger(__name__)

SEED_VERSION = 1
SOURCE = "builtin-188"
_META_KEY = "ai_tags.alias_seed_version"


def _read_marker(repo) -> int:
    from core.database.connection import get_connection

    conn = get_connection(repo.db_path)
    try:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = ?", (_META_KEY,)
        ).fetchone()
        if row is None:
            return 0
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0
    finally:
        conn.close()


def _write_marker(repo) -> None:
    from core.database.connection import get_connection

    conn = get_connection(repo.db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            (_META_KEY, str(SEED_VERSION)),
        )
        conn.commit()
    finally:
        conn.close()


def _occupied(repo, name: str) -> bool:
    return (
        repo.get_by_primary(name) is not None
        or repo.find_by_alias(name) is not None
    )


def _top_up(repo, owner, item) -> int:
    n = 0
    for a in item.aliases:
        if a in owner.aliases or _occupied(repo, a):
            continue
        ok, _msg = repo.add_alias(owner.primary_name, a)
        if ok:
            n += 1
            owner.aliases = list(owner.aliases) + [a]
    return n


def _seed_one(repo, item, top_up_only: bool) -> tuple[int, int]:
    owner = repo.get_by_primary(item.name) or repo.find_by_alias(item.name)
    if owner is not None:
        if owner.source != SOURCE or owner.primary_name != item.name:
            return 0, 0
        return 0, _top_up(repo, owner, item)
    if top_up_only:
        return 0, 0
    free = [a for a in item.aliases if not _occupied(repo, a)]
    if not free:
        return 0, 0
    try:
        repo.add(item.name, free, source=SOURCE)
    except ValueError:
        logger.warning(
            "seed_builtin_aliases: skip %r after ValueError", item.name
        )
        return 0, 0
    return 1, 0


def seed_builtin_aliases(repo=None) -> dict:
    from core.database import TagAliasRepository
    from core.ai_services.tagging_vocab import load_builtin
    from core.similar.ranker_cache import SimilarRankerCache

    if repo is None:
        repo = TagAliasRepository()
    if _read_marker(repo) >= SEED_VERSION:
        return {"skipped": True, "created": 0, "topped_up": 0}
    top_up_only = _read_marker(repo) > 0
    created = 0
    topped_up = 0
    for item in load_builtin():
        if not item.aliases:
            continue
        c, t = _seed_one(repo, item, top_up_only)
        created += c
        topped_up += t
    if created or topped_up:
        from core.similar import canonicalize

        canonicalize._invalidate_cache()
        try:
            SimilarRankerCache.invalidate()
        except Exception:
            logger.warning(
                "seed_builtin_aliases: SimilarRankerCache.invalidate failed",
                exc_info=True,
            )
    _write_marker(repo)
    return {"skipped": False, "created": created, "topped_up": topped_up}
