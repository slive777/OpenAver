"""readonly_producer — T-1 skeleton: dataclasses + listing + incremental skip.

Pure backend module. NO API, NO UI, NO frontend. (feature/88b)

Canonical Decisions enforced here:
  CD-88b-1: listing via fast_scan_directory only (CD-88b-1).
  CD-88b-2 (superseded by TASK-89b-T3): the original incremental-skip design
             read a bulk cover-path index and checked cover-file existence on
             disk. TASK-89b-T3 replaced that with a pure DB signal —
             VideoRepository.get_attempted_index() feeding _should_skip below
             (see CD-89b-3) — with no shape change to get_mtime_index().
"""

from __future__ import annotations

import glob
import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core import thumbnail_cache
from core.config import _STEM_IMAGE_MODES
from core.database import Video, get_db_path
from core.gallery_scanner import fast_scan_directory
from core.logger import get_logger
from core.organizer import (
    _detect_suffixes,
    _detect_vr_cluster,
    _strip_num_prefixes,
    download_image,
    format_string,
    generate_jellyfin_images,
    generate_nfo,
    sanitize_filename,
    truncate_title,
    truncate_to_chars,
)
from core.path_utils import (
    CURRENT_ENV,
    is_path_under_dir,
    normalize_path,
    reverse_path_mapping,
    to_file_uri,
    uri_to_fs_path,
)
from core.scraper import extract_number, search_jav
from core.video_extensions import get_video_extensions

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses (§1.1)
# ---------------------------------------------------------------------------

@dataclass
class ProduceOutcome:
    """Single-video result."""
    source_uri: str
    status: str           # "created" | "skipped" | "failed" | "no_scrape"
    movie_dir: str = ""   # generated per-movie directory (FS path); empty on skip/fail
    number: str = ""
    error: str = ""


@dataclass
class ProduceResult:
    """Aggregate result for one source (used by 88c to build SSE summary)."""
    source_path: str
    output_path: str
    created: int = 0
    skipped: int = 0
    failed: int = 0
    no_scrape: int = 0
    aborted_reason: str = ""
    outcomes: list = field(default_factory=list)  # List[ProduceOutcome]
    skipped_paths: list = field(default_factory=list)  # TASK-89b-T5: paths dropped by fast_scan_directory on_skip
    pruned: int = 0  # TASK-89b-T6: DB rows deleted by the DB-row-only prune below


# ---------------------------------------------------------------------------
# Internal helpers (all independently unit-testable)
# ---------------------------------------------------------------------------

def _min_size_bytes(gallery_config: dict) -> int:
    """Convert gallery.min_size_mb → bytes. Mirrors scanner.py:221."""
    return int(gallery_config.get("min_size_mb", 0)) * 1024 * 1024


def _list_source_videos(
    source_path: str, extensions: set, min_size_bytes: int,
    on_skip: Optional[Callable[[str, Exception], None]] = None,
) -> list[dict]:
    """List video files under source_path. Delegates to fast_scan_directory (CD-88b-1).

    Returns a list of dicts with keys: path, mtime, size, nfo_mtime.
    nfo_mtime is ignored by this module (guard G1: no source-NFO reads).

    source_path may be a native FS path OR a ``file:///`` URI (DirectoryConfig.path
    accepts both per core/config.py schema). uri_to_fs_path is idempotent on FS-path
    input and converts URI form to an FS path, so scanning works for both without a
    hand-rolled ``startswith('file:///')`` check (path-contract compliant).

    on_skip (TASK-89b-T5): forwarded verbatim to fast_scan_directory — invoked
    (path, exception) for entries/subdirectories dropped due to OSError/PermissionError.
    """
    fs_dir = uri_to_fs_path(source_path)
    return fast_scan_directory(fs_dir, extensions, min_size_bytes, on_skip=on_skip)


def _should_skip(source_uri: str, attempted_index: dict, force: bool = False) -> bool:
    """TASK-89b-T3: single attempted-index skip predicate (replaces the B3/P2a
    three-condition cover-on-disk check).

    Returns True (skip) when this source has already been attempted at least
    once (attempted_index.get(source_uri, 0) > 0) and force is not set.
    force=True unconditionally returns False (never skip), regardless of
    attempted_index contents — the manual re-scrape escape hatch.

    This trades the old cover-file self-heal behaviour (deleting a produced
    cover on disk used to trigger an automatic rebuild on the next run) for a
    pure cost-avoidance signal driven by scrape_attempted_at (CD-89b-3): once
    a source has been attempted, it is never re-attempted automatically,
    regardless of what happens to its output files on disk.
    """
    if force:
        return False
    return attempted_index.get(source_uri, 0) > 0


# ---------------------------------------------------------------------------
# TASK-89a-T2: output-root resolution (CD-89a-7)
# ---------------------------------------------------------------------------

def _derive_source_name(source_path: str) -> str:
    """Derive an App-managed output-folder name for a readonly source (pure, no I/O).

    basename = sanitize_filename(Path(...).name) — folder-name semantics, `.name`
    not `.stem` (a source folder called "Movies.Archive" must not be truncated to
    "Movies").

    A deterministic short code (sha1[:6] of the canonicalized source path) is
    ALWAYS appended (CD-89a-7 — Opus-pinned Option B, 2026-07-03): the folder name
    depends ONLY on this source's own path, never on sibling sources, so adding or
    removing an unrelated source can never flip an existing source's effective
    output root (that flip would orphan every row already written under it — the
    exact churn 89a exists to eliminate). Two different sources sharing the same
    basename therefore never collide; the same source resolves to the same name on
    every call (stability lock).

    Falls back to ``src-<shortcode>`` when sanitize_filename strips the basename to
    an empty string (e.g. source path is a drive root ``D:\\`` or a UNC share root)
    so an empty folder name is never produced.
    """
    # uri_to_fs_path already normalizes internally (strip URI prefix → unquote →
    # normalize_path with a try/except fallback) — do NOT re-run normalize_path
    # again before handing the result to to_file_uri(). Stacking those two calls
    # is a banned lint idiom (see test_no_normalize_before_to_file_uri) because a
    # standalone normalize_path() raises ValueError on foreign-platform path
    # strings (e.g. a Windows path fed to a Linux CI run), which uri_to_fs_path
    # already guards against via its own try/except.
    fs_path = uri_to_fs_path(source_path)
    canonical = to_file_uri(fs_path)
    shortcode = hashlib.sha1(canonical.encode()).hexdigest()[:6]
    basename = sanitize_filename(Path(fs_path).name)
    if not basename:
        return f"src-{shortcode}"
    return f"{basename}-{shortcode}"


def resolve_output_root(source, config: dict) -> str:
    """Resolve the effective output root for a readonly source (CD-89a-7).

    Reads the GLOBAL flavour (config['scraper']['external_manager']), not a
    per-source field (CD-89a-2: flavour is global).

    - off (or any value not in _STEM_IMAGE_MODES) → fixed App-managed folder
      ``output/lib/<derived-source-name>`` (native FS path string, NOT passed
      through to_file_uri — callers normalize_path()/to_file_uri() it themselves,
      matching the existing ``source.output_path`` convention so call sites need
      minimal changes). Structurally guarantees a non-empty output root so off
      sources never abort with zero videos produced.
    - jellyfin/emby/kodi → source.output_path verbatim (may be empty — media-server
      flavours still require the user to configure it; callers keep their existing
      empty-string guards unchanged).
    """
    external_manager = config.get("scraper", {}).get("external_manager", "off")
    if external_manager not in _STEM_IMAGE_MODES:
        name = _derive_source_name(source.path)
        return str(get_db_path().parent / "lib" / name)
    return source.output_path


# ---------------------------------------------------------------------------
# T-2: naming helpers (pure functions). Movie-dir resolution itself
#       (_resolve_movie_dir, TASK-89a-T3) lives further below since it depends
#       on _folder_parts defined here.
# ---------------------------------------------------------------------------

def _format_data(meta: dict, source_fs_path: str, config: dict) -> dict:
    """Build format_data dict from scraped meta (off-mode flavour).

    Replicates organizer.py:859-877 (off branch):
    - strip number prefixes from title
    - truncate title to max_title_length
    - detect suffix once (off: unfiltered suffix_keywords)

    The same truncated title feeds both _folder_parts and _build_basename
    so the two never drift (CD-88b-3 / Codex P2).
    """
    number = meta['number']
    title = _strip_num_prefixes(meta.get('title', ''), number)
    title = truncate_title(title, config.get('max_title_length', 50))
    fd: dict = {
        'number': number,
        'title': title,
        'actors': meta.get('actors', []),
        'maker': meta.get('maker', ''),
        'date': meta.get('date', ''),
    }
    fd['suffix'] = _detect_suffixes(
        os.path.basename(source_fs_path),
        config.get('suffix_keywords', []),
    )
    return fd


def _folder_parts(format_data: dict, config: dict) -> list:
    """Return folder layer strings (max 3) replicating organizer.py:915-933."""
    layers = config.get('folder_layers') or [
        p.strip()
        for p in config.get('folder_format', '{num}').replace('\\', '/').split('/')
        if p.strip()
    ]
    max_chars = min(config.get('max_filename_length', 60), 120)
    parts = []
    for layer in layers[:3]:
        part = truncate_to_chars(format_string(layer, format_data, use_fallback=True), max_chars)
        if part:
            parts.append(part)
    return parts


def _build_basename(format_data: dict, source_fs_path: str, config: dict) -> str:
    """Build filename stem (no extension) replicating organizer off-mode filename block.

    Replicates organizer.py:936-971 (off branch):
    - suffix taken from format_data['suffix'] (not recomputed)
    - {suffix} two-pass protection when token present in template
    - vr_tail appended last
    - final cap to max_chars
    - NO multipart / part_tail (off is no-op, CD-88b-3)
    """
    original_filename = os.path.basename(source_fs_path)
    original_ext = os.path.splitext(source_fs_path)[1]

    vr_cluster = _detect_vr_cluster(original_filename)
    vr_tail = f'_{vr_cluster}' if vr_cluster else ''

    # off mode: part_tail always ''
    reserve = len(vr_tail)

    max_filename_chars = min(config.get('max_filename_length', 60), 120)
    max_chars = max_filename_chars - len(original_ext)

    filename_template = config.get('filename_format', '{num} {title}')
    suffix = format_data.get('suffix', '')

    if suffix and '{suffix}' in filename_template:
        no_suffix_data = dict(format_data, suffix='')
        base_without_suffix = format_string(filename_template, no_suffix_data)
        base_budget = max(0, max_chars - len(suffix) - reserve)
        if base_budget == 0:
            filename_base = truncate_to_chars(suffix, max(0, max_chars - reserve))
        else:
            base_without_suffix = truncate_to_chars(base_without_suffix, base_budget)
            filename_base = base_without_suffix + suffix
    else:
        filename_base = format_string(filename_template, format_data)
        filename_base = truncate_to_chars(filename_base, max(0, max_chars - reserve))

    filename_base = filename_base + vr_tail
    filename_base = truncate_to_chars(filename_base, max_chars)
    return filename_base


# ---------------------------------------------------------------------------
# TASK-89a-T3 (CD-89a-3): movie-dir resolution — read DB stored value & reuse
# in place when still valid, else allocate via sanitize_filename(number) +
# increment. Replaces the old owners/_movie_leaf_base/_movie_dir cover-index
# reconstruction model.
# ---------------------------------------------------------------------------

_MAX_INCREMENT = 1000  # guard against a theoretical infinite loop (TASK-89a-T3)


def _resolve_movie_dir(
    repo,
    source_uri: str,
    existing,                    # Optional[Video] — caller already ran repo.get_by_path(source_uri)
    output_root: str,            # fs path (produce_source's existing output_root)
    output_uri: str,             # to_file_uri(output_root, path_mappings)
    format_data: dict,           # feeds _folder_parts (parent layers) + format_data['number'] (leaf)
    config: dict,                # scraper_cfg
    allocated_this_run: set,     # URIs already handed out THIS produce_source call
    path_mappings: dict,
) -> tuple[Path, str]:
    """Resolve the per-movie directory: read-and-reuse, else allocate + increment.

    Returns (movie_dir_fs_path, output_dir_uri_to_store) (TASK-89a-T3 / CD-89a-3).

    Read-and-reuse: if the DB already has a row for this source whose stored
    output_dir still falls under the CURRENT output root, keep using that exact
    directory (idempotent re-scrape, no re-allocation, no orphaning).
    Otherwise (first time, or the effective output root moved) allocate a new
    slot: leaf = sanitize_filename(number), incrementing a numeric suffix until
    a candidate is free in the DB, on disk, and within this run's own
    allocations.
    """
    if existing and existing.output_dir and is_path_under_dir(existing.output_dir, output_uri):
        movie_dir_uri = existing.output_dir
        # TASK-89a-T5 (CD-89a-6): mapped-output 定位。uri_to_fs_path 本身不反解
        # path_mappings，WSL+UNC mapped 輸出根下會定位到錯誤的本機路徑，故在此
        # targeted 反解。只反解回傳給呼叫端的 fs Path，不反解存回 DB 的 URI
        # （movie_dir_uri 維持 existing.output_dir 原值），否則下一輪
        # is_path_under_dir(existing.output_dir, output_uri) 比對會失準。
        movie_dir_fs = uri_to_fs_path(movie_dir_uri)
        if CURRENT_ENV == 'wsl' and path_mappings:
            movie_dir_fs = reverse_path_mapping(movie_dir_fs, path_mappings) or movie_dir_fs
        return Path(movie_dir_fs), movie_dir_uri

    parts = _folder_parts(format_data, config)
    base_leaf = sanitize_filename(format_data['number'])
    n = 1
    while True:
        leaf = base_leaf if n == 1 else f"{base_leaf}-{n}"
        candidate_fs = Path(output_root, *parts, leaf)
        candidate_uri = to_file_uri(str(candidate_fs), path_mappings)
        taken = (
            candidate_uri in allocated_this_run
            or repo.is_output_dir_taken(candidate_uri, exclude_path=source_uri)
            or candidate_fs.exists()
        )
        if not taken:
            break
        n += 1
        if n > _MAX_INCREMENT:
            raise RuntimeError(f"movie_dir increment 超過上限: {base_leaf}")

    allocated_this_run.add(candidate_uri)
    return candidate_fs, candidate_uri


# ---------------------------------------------------------------------------
# TASK-89a-T4 (Codex #3): stale-asset cleanup — reconstruct the previous run's
# basename from the DB row, then wipe that movie's own old singleton/extrafanart
# files, so re-scraping with a corrected title overwrites in place instead of
# piling up `<old>.* + <new>.*` side by side.
#
# T5 follow-up (Codex PR review P2): cleanup runs AFTER the corresponding new
# asset has been written successfully, not before. Singletons (nfo/cover/
# poster/fanart) are cleaned only once `generate_nfo` has already returned
# True, and only the assets whose new write actually succeeded (has_cover/
# has_poster/has_fanart) — so a partial failure (cover download false, or
# generate_nfo raising) leaves the OLD assets on disk instead of deleting them
# up front and then failing to produce replacements. Extrafanart is the
# exception: it's non-critical and each run rewrites the whole set, so it is
# still cleaned before its own download loop.
# ---------------------------------------------------------------------------

def _build_old_base(existing, source_fs_path: str, config: dict) -> str:
    """Reconstruct the basename `_write_movie_assets` used on the PREVIOUS run.

    existing is the Video row already read by produce_source (T3, repo.get_by_path).
    Returns '' (skip cleanup) when there is nothing to clean up:
      - existing is None (first generation for this source file)
      - existing.title is empty (defensive; T3/_upsert_db always writes meta['title'])
      - existing.number is empty (defensive; search_jav/_upsert_db always writes a
        non-empty number, but _format_data has no .get for 'number' — guard here
        rather than let a KeyError/empty leaf surface deep in _build_basename)

    Otherwise, maps the OLD DB fields back onto the same meta-dict shape
    `_format_data` expects (DB → meta key names differ: actresses→actors,
    release_date→date) and replays `_format_data` + `_build_basename` against the
    SAME source_fs_path/config used this run — source_fs_path is the same physical
    source file both times, so suffix/vr_tail/ext are identical across runs and
    only the meta-driven parts (title/number/actors/maker/date) can differ.

    existing.title is the RAW scraped title as stored by _upsert_db (meta['title'],
    not the already-truncated format_data['title']) — running it back through
    _format_data reapplies the same strip/truncate transform that produced the
    original basename, so old_base equals what was actually written last time.
    """
    if existing is None or not existing.title or not existing.number:
        return ''
    old_meta = {
        'number': existing.number,
        'title': existing.title,
        'actors': existing.actresses,
        'maker': existing.maker,
        'date': existing.release_date,
    }
    old_format_data = _format_data(old_meta, source_fs_path, config)
    return _build_basename(old_format_data, source_fs_path, config)


def _clean_stale_extrafanart(movie_dir: str) -> None:
    """Delete this movie's own previous-run extrafanart samples (`fanart*.jpg`).

    Called from `_write_movie_assets` BEFORE the extrafanart download loop,
    whenever old_base is non-empty (caller's responsibility to gate — first
    generation has nothing to clean). No old_base parameter is needed: the glob
    is scoped to the fixed `extrafanart/` subdir and the `fanart*.jpg` pattern,
    independent of basename. Safe to run pre-write because extrafanart is
    non-critical (a missing sample degrades silently) and each run rewrites the
    whole set from scratch — unlike the singleton assets below, there is no
    "old cover/NFO now missing" failure mode to worry about here.

    Never a bare `*.jpg`/`*.*` glob, never rmtree — both would delete files the
    user placed in the same directory themselves. Missing files are a no-op
    (unlink(missing_ok=True)); this must never raise.
    """
    ef_dir = Path(movie_dir) / 'extrafanart'
    if not ef_dir.is_dir():
        return
    for f in ef_dir.glob('fanart*.jpg'):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            logger.warning("[readonly_producer] stale extrafanart 清除失敗（略過）: %s", f)


def _clean_stale_singletons(
    movie_dir: str,
    old_base: str,
    new_base: str,
    has_cover: bool,
    has_poster: bool,
    has_fanart: bool,
) -> None:
    """Delete this movie's own previous-run singleton assets (nfo/cover/poster/
    fanart), anchored strictly on old_base.

    Called from `_write_movie_assets` AFTER `generate_nfo` has already returned
    True — i.e. only once the new NFO write actually succeeded. This is
    deliberately post-write, not pre-write (T5 follow-up, Codex PR review P2):
    cleaning before writing would delete the OLD assets even when the new write
    fails partway (cover download false, or generate_nfo raising), leaving
    neither the old nor the new assets on disk. Running it after means a failed
    write always leaves the previous run's assets intact.

    No-op when old_base is '' (first generation — nothing to clean) or
    old_base == new_base (title unchanged — the new write already overwrote the
    same-named file in place; deleting here would clobber what generate_nfo /
    download_image / generate_jellyfin_images just wrote, since this runs after
    the write completes).

    Each asset is deleted only when this run's corresponding write actually
    succeeded: `<old_base>.jpg` only when has_cover, `<old_base>-poster.*` only
    when has_poster, `<old_base>-fanart.*` only when has_fanart. A transient
    download/generation failure this run keeps the matching old file on disk
    rather than leaving a hole. `<old_base>.nfo` is unconditional — this
    function is only ever called once nfo_ok is already True.

    Deliberately narrow: exact filenames for the singletons (extension glob
    only for poster/fanart, defensive against a future non-.jpg format). Never
    a bare `*.jpg`/`*.*` glob, never rmtree — both would delete files the user
    placed in the same directory themselves. Missing files are a no-op
    (unlink(missing_ok=True)); this must never raise.
    """
    if not old_base or old_base == new_base:
        return
    d = Path(movie_dir)
    # old_base comes from the scraped title and can legally contain glob
    # metacharacters (sanitize_filename keeps '[' ']' — common in language/sub
    # tags like "[Chinese Sub]"). Escape before globbing the poster/fanart
    # extension patterns, else Path.glob treats '[...]' as a char class and
    # silently misses the file (residual junk survives — a narrow Codex #3
    # recurrence). The nfo/cover singletons use literal joins, no escape needed.
    esc = glob.escape(old_base)
    targets = [d / f"{old_base}.nfo"]
    if has_cover:
        targets.append(d / f"{old_base}.jpg")
    if has_poster:
        targets.extend(d.glob(f"{esc}-poster.*"))
    if has_fanart:
        targets.extend(d.glob(f"{esc}-fanart.*"))
    for target in targets:
        try:
            Path(target).unlink(missing_ok=True)
        except OSError:
            logger.warning("[readonly_producer] stale asset 清除失敗（略過）: %s", target)


# ---------------------------------------------------------------------------
# T-3: write off-flavor assets + DB upsert (plan §5.2 / §6)
# ---------------------------------------------------------------------------

def _write_movie_assets(
    movie_dir: str,
    meta: dict,
    format_data: dict,
    source_fs_path: str,
    config: dict,
    old_base: str = '',
) -> dict:
    """Write nfo + cover + -poster/-fanart + extrafanart to movie_dir.

    Returns {'cover_fs': str, 'sample_fs': list[str]}.
    cover_fs is '' when cover download fails or meta['cover'] is empty.

    old_base (TASK-89a-T4, Codex #3; T5 follow-up, Codex PR review P2): when
    non-empty, this movie's own stale assets from the PREVIOUS run (different
    title → different basename) are deleted — but only AFTER the corresponding
    new asset has been written successfully, and only when old_base differs
    from this run's basename. Extrafanart (non-critical, whole set rewritten
    every run) is cleaned before its own download loop. The singleton assets
    (nfo/cover/poster/fanart) are cleaned only once generate_nfo has already
    succeeded, and only the ones whose new write actually succeeded this run —
    so a write that fails partway (cover download false, generate_nfo raising)
    leaves the previous run's assets on disk instead of deleting them up front
    and then failing to produce replacements.
    """
    os.makedirs(movie_dir, exist_ok=True)
    new_base = base = _build_basename(format_data, source_fs_path, config)
    base_stem = str(Path(movie_dir) / base)

    # 1) Cover: download from remote URL (C6 — always re-scrape, never read source image)
    cover_fs = base_stem + '.jpg'
    has_cover = bool(meta.get('cover')) and download_image(meta['cover'], cover_fs)

    # 2) poster/fanart (off mode also produces these — Acceptance #6)
    imgs = generate_jellyfin_images(cover_fs, base_stem) if has_cover else {}
    has_poster = imgs.get('poster', False)
    has_fanart = imgs.get('fanart', False)

    # 3) extrafanart — gated only on config key; per-movie dir already exists (no create_folder).
    # Stale samples from the previous run are cleaned first (whenever old_base is
    # non-empty) regardless of this run's download_sample_images setting, so a
    # re-scrape with samples toggled off still shrinks the old set to zero.
    if old_base:
        _clean_stale_extrafanart(movie_dir)
    sample_fs: list = []
    if config.get('download_sample_images'):
        ef_dir = Path(movie_dir) / 'extrafanart'
        os.makedirs(ef_dir, exist_ok=True)
        for i, url in enumerate(meta.get('sample_images', []), 1):
            dest = str(ef_dir / f'fanart{i}.jpg')
            if download_image(url, dest):
                sample_fs.append(dest)

    # 4) NFO — title/fields use full meta (not truncated format_data).
    # NFO is a REQUIRED off-complete output: a write failure must NOT be silently
    # treated as success (generate_nfo swallows its own I/O error and returns False).
    # Raise so produce_source counts the item as failed and skips _upsert_db — DB never
    # claims a movie was generated when the NFO is missing ("每片成功生成後寫一筆").
    # Cover/poster/fanart stay best-effort: a missing cover is acceptable per C6
    # (cold title with no image) and self-heals on the next incremental run.
    nfo_fs = base_stem + '.nfo'
    nfo_ok = generate_nfo(
        number=meta['number'],
        title=meta['title'],
        actors=meta.get('actors', []),
        tags=meta.get('tags', []),
        date=meta.get('date', ''),
        maker=meta.get('maker', ''),
        url=meta.get('url', ''),
        output_path=nfo_fs,
        has_poster=has_poster,
        has_fanart=has_fanart,
        director=meta.get('director', ''),
        duration=meta.get('duration'),
        series=meta.get('series', ''),
        label=meta.get('label', ''),
        summary=meta.get('_summary', ''),
        rating=meta.get('_rating'),
        external_manager=config.get('external_manager', 'off'),
    )
    if not nfo_ok:
        raise RuntimeError(f"NFO write failed: {nfo_fs}")

    # Singleton stale-cleanup runs LAST, only after the new NFO write is confirmed
    # (T5 follow-up, Codex PR review P2) — see docstring above for why this is
    # post-write rather than pre-write.
    _clean_stale_singletons(movie_dir, old_base, new_base, has_cover, has_poster, has_fanart)
    return {'cover_fs': cover_fs if has_cover else '', 'sample_fs': sample_fs}


def _upsert_db(
    repo,
    source_uri: str,
    file_info: dict,
    meta: dict,
    assets: dict,
    path_mappings: dict,
    output_dir: str,
) -> None:
    """Manually construct Video and upsert to repo (CD-88b-7).

    path = source_uri (streaming key).
    cover_path / sample_images = local output URIs (via to_file_uri).
    user_tags intentionally omitted → upsert preserves existing DB value.
    output_dir MUST be a non-empty file:/// URI (TASK-89a-T1's upsert CASE-WHEN
    treats '' as "leave existing value alone" — passing '' here would make the
    very first write for a video look like a no-op and silently keep it '').
    """
    v = Video(
        path=source_uri,
        number=meta['number'],
        title=meta['title'],
        actresses=meta.get('actors', []),
        maker=meta.get('maker', ''),
        director=meta.get('director', ''),
        series=meta.get('series') or None,
        label=meta.get('label', ''),
        tags=meta.get('tags', []),
        sample_images=[to_file_uri(p, path_mappings) for p in assets['sample_fs']],
        duration=meta.get('duration'),
        size_bytes=file_info['size'],
        cover_path=to_file_uri(assets['cover_fs'], path_mappings) if assets['cover_fs'] else '',
        output_dir=output_dir,
        release_date=meta.get('date', ''),
        mtime=file_info['mtime'],
        nfo_mtime=0.0,
        scrape_attempted_at=time.time(),
    )
    repo.upsert(v)


# ---------------------------------------------------------------------------
# T-4: _emit helper + produce_source orchestrator (plan §7)
# ---------------------------------------------------------------------------

def _emit(on_progress, result, source_uri, status, movie_dir="", number="", error=""):
    """Append a ProduceOutcome to result.outcomes and fire on_progress callback."""
    outcome = ProduceOutcome(
        source_uri=source_uri,
        status=status,
        movie_dir=movie_dir,
        number=number,
        error=error,
    )
    result.outcomes.append(outcome)
    if on_progress is not None:
        on_progress(outcome)


def produce_source(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None, force: bool = False, reachable: bool = True) -> ProduceResult:
    """Orchestrate per-source readonly generation: guard → list → skip → scrape → write → upsert.

    Pure service layer. NO FastAPI, NO SSE, NO router. (CD-88b-8, §1.1)
    Caller (88c) injects on_progress/should_abort for SSE streaming.
    """
    result = ProduceResult(source_path=source.path, output_path=source.output_path or "")

    # G8/D7 guards (CD-88b-6 / Acceptance #11)
    if not source.readonly:
        result.aborted_reason = "not_readonly"
        return result

    # CD-89a-7: off flavour resolves to a fixed App-managed folder (always non-empty);
    # media-server flavours (jellyfin/emby/kodi) still require source.output_path.
    effective_output = resolve_output_root(source, config)
    if not (effective_output or "").strip():
        result.aborted_reason = "no_output_path"
        return result

    gallery = config.get("gallery", {})
    scraper_cfg = config.get("scraper", {})
    path_mappings = gallery.get("path_mappings", {})

    output_root = normalize_path(effective_output)
    output_uri = to_file_uri(output_root, path_mappings)

    # TASK-89b-T5 / CD-89b-5: reachability guard — computed by caller (scanner.py
    # readonly dispatch point), not by produce_source itself (see TASK-89b-T5 §5.1).
    # Must precede repo.get_attempted_index() — no DB/IO before this guard.
    if not reachable:
        result.aborted_reason = "unreachable"
        return result

    attempted_index = repo.get_attempted_index()
    allocated_this_run: set = set()

    files = _list_source_videos(
        source.path, get_video_extensions(config), _min_size_bytes(gallery),
        on_skip=lambda p, _e: result.skipped_paths.append(p),  # noqa: B023 — result consumed synchronously, same call stack
    )

    for fi in files:
        if should_abort is not None and should_abort():
            break

        src_uri = to_file_uri(fi["path"], path_mappings)

        if _should_skip(src_uri, attempted_index, force):
            result.skipped += 1
            _emit(on_progress, result, src_uri, "skipped")
            continue

        number = extract_number(os.path.basename(fi["path"]))  # Optional[str]
        if not number:  # None guard (Codex P2b): search_jav(None) crashes
            result.no_scrape += 1
            _emit(on_progress, result, src_uri, "no_scrape")
            continue

        meta = search_jav(number, source="auto", proxy_url=proxy_url)
        if not meta:
            repo.insert_if_ignore(Video(path=src_uri, number=number, title=os.path.basename(fi["path"])))
            repo.update_scrape_attempted_at(src_uri, time.time())
            result.no_scrape += 1
            _emit(on_progress, result, src_uri, "no_scrape")
            continue

        try:
            fd = _format_data(meta, fi["path"], scraper_cfg)
            existing = repo.get_by_path(src_uri)  # T3: read once; T4 reuses title/actresses/maker/release_date
            movie_dir, output_dir_uri = _resolve_movie_dir(
                repo, src_uri, existing, output_root, output_uri,
                fd, scraper_cfg, allocated_this_run, path_mappings,
            )
            old_base = _build_old_base(existing, fi["path"], scraper_cfg)  # T4: '' when no prior row/title/number
            assets = _write_movie_assets(str(movie_dir), meta, fd, fi["path"], scraper_cfg, old_base=old_base)
            _upsert_db(repo, src_uri, fi, meta, assets, path_mappings, output_dir_uri)
            result.created += 1
            _emit(on_progress, result, src_uri, "created", str(movie_dir), number)
        except Exception:
            result.failed += 1
            # Full detail + traceback to the log (error level, diagnosable);
            # ProduceOutcome.error is the 88c SSE-bound field — use a fixed message
            # (repo error policy) so raw exception text (paths, errno) never leaks.
            logger.exception("[readonly_producer] 生成失敗: %s", src_uri)
            _emit(on_progress, result, src_uri, "failed", number=number, error="生成失敗")

    # TASK-89b-T6 (CD-89b-6): DB-row-only prune. Gate = reachable AND this-run
    # list non-empty AND no skipped_paths. reachable is implicitly True here —
    # the "unreachable" guard above already returned before this point, so any
    # execution path reaching here has aborted_reason == "" (empty).
    if files and not result.skipped_paths:
        source_root_fs = uri_to_fs_path(source.path)
        source_root_uri = to_file_uri(source_root_fs, path_mappings)
        this_run_uris = {to_file_uri(fi["path"], path_mappings) for fi in files}
        candidates = [
            v.path for v in repo.get_all()
            if is_path_under_dir(v.path, source_root_uri)
            and (v.scrape_attempted_at > 0 or v.output_dir)
            and v.path not in this_run_uris
        ]
        if candidates:
            result.pruned = repo.delete_by_paths(candidates)
            # thumbnail cache parity with the non-readonly branch (scanner.py
            # :441-442) — see TASK-89b-T6 技術要點 6.5.
            for p in candidates:
                thumbnail_cache.invalidate(p)

    return result
