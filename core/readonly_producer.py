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
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from core import thumbnail_cache
from core.config import _STEM_IMAGE_MODES, iter_gallery_sources
from core.database import Video, get_db_path
from core.enrich_contract import EnrichResult, effective_original_title
from core.focal import requires_face_detection
from core.focal_trigger import maybe_submit_video_focal
from core.gallery_scanner import IMAGE_EXTENSIONS, VideoScanner, fast_scan_directory
from core.logger import get_logger
from core.nfo_updater import parse_nfo
from core.organizer import (
    _detect_suffixes,
    _detect_vr_cluster,
    _strip_num_prefixes,
    crop_to_poster,
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
    uri_to_local_fs_path,
)
from core.readonly_source import _canonical_source_prefix
from core.scraper import extract_number, search_jav, search_jav_single_source
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
    fs_dir = uri_to_fs_path(source_path)  # uri-no-reverse: native config path (DirectoryConfig.path), no DB-mapped namespace
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
    fs_path = uri_to_fs_path(source_path)  # uri-no-reverse: native config path (DirectoryConfig.path), no DB-mapped namespace
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


def resolve_owning_output_root(canonical_uri: str, config: dict) -> Optional[tuple]:
    """Find the innermost readonly gallery source that owns ``canonical_uri`` and
    resolve its effective output root (CD-104-5).

    Returns ``(source, output_root, output_uri)`` where ``source`` is the
    ``DirectoryConfig`` (needed downstream by ``_produce_one``), ``output_root``
    is a native FS path string (``normalize_path()``-d), and ``output_uri`` is
    its ``file:///`` form. Returns ``None`` when no readonly source owns the
    path — the router's signal to fall through to its existing (non-readonly)
    sidecar-write code path unchanged.

    Longest-canonical-prefix-wins, mirroring ``is_path_readonly``'s nested-
    source semantics (readonly_source.py) exactly — but resolving to the WHICH
    source (an object), not just a boolean:
    - Enumerate readonly sources (``iter_gallery_sources`` + ``.readonly``),
      canonicalize each with ``_canonical_source_prefix`` (same mapped
      namespace as DB rows), keep the longest prefix that contains
      ``canonical_uri``.
    - No readonly source contains it → ``None`` (not readonly at all).
    - A writable source's prefix ALSO contains it and is >= as long (ties go to
      writable, matching ``is_path_readonly``'s ``best_ro > best_wr`` — a
      strictly-longer readonly prefix wins) → ``None`` (a nested writable
      override; the file is actually writable, not readonly — do not route).
    - Otherwise resolve via ``resolve_output_root(source, config)``. An empty
      result (media-server flavour with no configured ``output_path``) is
      returned as ``(source, '', '')`` rather than ``None`` — the caller still
      knows WHICH source owns the file (for its own "未設定輸出路徑" error
      message) but has to reject the write itself, since an empty root cannot
      be normalize_path()'d/to_file_uri()'d meaningfully.

    Malformed source paths (``_canonical_source_prefix`` raising ``ValueError``,
    e.g. bad UNC forms) are skipped for that one source (mirrors
    ``readonly_source_prefixes``/``writable_source_prefixes``'s own per-entry
    ``except ValueError: continue`` — one dirty config entry must not sink the
    whole resolution).
    """
    gallery = config.get("gallery", {})
    path_mappings = gallery.get("path_mappings", {})

    best_source = None
    best_ro_len = -1
    for src in iter_gallery_sources(gallery):
        if not src.readonly or not src.path:
            continue
        try:
            prefix = _canonical_source_prefix(src.path, path_mappings)
        except ValueError:
            continue
        if is_path_under_dir(canonical_uri, prefix) and len(prefix) > best_ro_len:
            best_ro_len = len(prefix)
            best_source = src

    if best_source is None:
        return None

    best_wr_len = -1
    for src in iter_gallery_sources(gallery):
        if src.readonly or not src.path:
            continue
        try:
            prefix = _canonical_source_prefix(src.path, path_mappings)
        except ValueError:
            continue
        if is_path_under_dir(canonical_uri, prefix) and len(prefix) > best_wr_len:
            best_wr_len = len(prefix)

    if best_wr_len >= best_ro_len:
        return None  # writable override (or a tie — config self-contradiction, favor writable)

    effective = resolve_output_root(best_source, config)
    if not (effective or "").strip():
        return (best_source, '', '')

    output_root = normalize_path(effective)
    output_uri = to_file_uri(output_root, path_mappings)
    return (best_source, output_root, output_uri)


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
        movie_dir_fs = uri_to_fs_path(movie_dir_uri)  # uri-no-reverse: already paired with reverse_path_mapping on next line
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
    has_strm: bool = False,
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
    when has_poster, `<old_base>-fanart.*` only when has_fanart, `<old_base>.strm`
    only when has_strm (TASK-90a-T3, media-server flavour). A transient
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
    # strm is a media-server flavour extra (TASK-90a-T3): exact filename, no glob
    # (literal join like nfo/cover, no glob.escape needed). Only cleaned when this
    # run actually re-wrote the strm (has_strm) — a transient strm write failure
    # keeps the old <old_base>.strm rather than orphaning it, symmetric with
    # has_cover/has_poster/has_fanart gating. Prevents a title-drift double
    # library entry in Emby/Jellyfin (<old>.strm + <new>.strm side by side).
    if has_strm:
        targets.append(d / f"{old_base}.strm")
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
# TASK-90a-T3: media-server .strm sidecar (CD-90a-2 / CD-90a-6)
# ---------------------------------------------------------------------------

def _apply_path_mapping(source_fs_path: str, mappings: dict) -> str:
    """Rewrite a source FS-path prefix to the playback-side namespace.

    strm files are consumed by an external media server (Emby/Jellyfin/Kodi) that
    may see the same physical storage under a DIFFERENT mount path than OpenAver's
    host (e.g. OpenAver on Windows sees ``Z:\\115\\x.mp4`` while the media server
    on the NAS sees ``/volume1/movie/x.mp4``). mappings maps ``local_prefix ->
    remote_prefix``; the matched prefix is swapped and the remainder appended.

    Matching is done in ``file:///`` URI space: both source and each local_prefix
    are converged via ``to_file_uri`` (host-independent, never raises, no
    percent-encoding in this codebase). This fixes two Codex findings:

    - P1 (cross-namespace silent miss): a Windows-display prefix ``C:\\115`` in
      config now matches a WSL-native source ``/mnt/c/115/x.mp4`` (both converge
      to ``file:///C:/115``). Raw-string compare would have silently missed and
      emitted the un-mapped source path.
    - P2 (trailing separator): a local_prefix with a trailing separator
      (``/mnt/z/115/``) no longer misses — the URI form is rstrip'd of ``/``.

    A rule matches when the source URI equals the (trailing-slash-stripped) local
    URI OR the char immediately after it is ``/`` (URIs always use forward-slash,
    so no OS branch). This stops ``file:///Z:/1150/a`` from wrongly matching a
    ``file:///Z:/115`` rule. When several rules match, the LONGEST local URI wins
    (deterministic, independent of dict insertion order). Empty mappings or no
    match returns source_fs_path unchanged (v1 backward compat).

    CD-90a-6: only source/local_prefix are converged (for MATCHING). The remote
    result is written VERBATIM and is NEVER normalized — it is a foreign playback
    namespace (a bare Unix ``/volume1/...`` fed to to_windows_path on a Windows
    host raises). We only rstrip trailing separators off remote_prefix for join
    hygiene; the appended remainder is taken from the URI (always forward-slash).
    """
    if not mappings:
        return source_fs_path
    su = to_file_uri(source_fs_path)  # converge source → file:/// URI (host-independent, no raise)
    matched = []
    for local_prefix, remote_prefix in mappings.items():
        # remote 空的半填規則 skip（PR #93 P2 縱深防禦）：remote='' 會讓下方
        # `remote.rstrip() + su[len(lu):]` 把 local 前綴剝掉只剩後綴（如 /movie.mp4）、
        # 破壞 strm 內容。前端已過濾不存半填規則，此處防手改 config.json。只擋空字串；
        # 非字串 remote 仍照舊流到 rstrip 拋 TypeError → _write_strm best-effort 接（契約不變）。
        if isinstance(remote_prefix, str) and not remote_prefix.strip():
            continue
        lu = to_file_uri(local_prefix).rstrip('/')  # converge + strip trailing sep (P2); URI is always '/'
        if su == lu or (su.startswith(lu) and su[len(lu):len(lu) + 1] == '/'):
            matched.append((lu, remote_prefix))
    if not matched:
        return source_fs_path
    lu, remote_prefix = max(matched, key=lambda kv: len(kv[0]))
    # path-contract-ok: remote 為播放端命名空間、verbatim 寫入不 normalize；僅去尾分隔符做
    # join 衛生（remainder 由 URI 取、恆前導 '/'）。source/local 收斂到 file:/// URI 供比對修
    # Codex P1（跨命名空間 C:\ ↔ /mnt/c/ 靜默失效）+ P2（尾分隔符）。
    return remote_prefix.rstrip('/\\') + su[len(lu):]


def _write_strm(base_stem: str, source_fs_path: str, config: dict, strm_mappings: dict = None) -> bool:
    """Write a single-line ``<base_stem>.strm`` pointing at the source video (best-effort).

    Content = _apply_path_mapping(source_fs_path, mappings) written as one UTF-8
    line, no BOM. The REMOTE side is written verbatim / never normalized; matching
    converges source+local_prefix to file:/// URI space (see _apply_path_mapping /
    CD-90a-6).

    config is the scraper section (produce_source passes scraper_cfg at call site);
    the mapping table defaults to a SAME-LEVEL read — ``config.get('strm_path_mappings', {})``,
    NOT via a nested ``config.get('scraper', ...)`` (that would always yield {} and
    silently disable mappings). This mirrors line ~580's same-level
    ``config.get('external_manager', 'off')`` read.

    strm_mappings (PR #93 五審四次 P2, option C): when provided (not None), it OVERRIDES
    ``config['strm_path_mappings']`` — produce_source passes a FRESH per-file read so the
    generate path uses the current mapping, not the run-start frozen snapshot. This closes
    the disconnect-tail residual: the SSE watcher clears the generate token the instant it
    detects a disconnect, but the producer thread only checks should_abort at each per-file
    checkpoint, so it can finish ONE more file's _write_strm after the token is gone → in that
    window another tab's settings save could land a new mapping (the strm-mapping gate no
    longer sees an in-flight generate) and that last file would otherwise write with the STALE
    frozen mapping and never self-heal. A fresh read makes even that last file use the current
    mapping. None preserves the legacy read (rewrite_strm + unit tests pass config verbatim).

    Best-effort (spec-90 §90a.2.2): strm is an EXTRA product for external media
    servers, not an OpenAver-required asset. A write failure logs a warning and
    returns False — it never raises, never marks the whole movie failed (unlike
    NFO, which is OpenAver's own required metadata). Returns True on success; the
    bool also feeds _clean_stale_singletons' has_strm gating.
    """
    strm_fs = base_stem + '.strm'
    try:
        # mapping + write both inside try: raw config is NOT model_validated on the
        # read path (_load_config_unlocked returns raw dict), so a hand-edited
        # config.json with non-str mapping values could make _apply_path_mapping
        # TypeError. best-effort's promise (§90a.2.2: strm never fails the movie)
        # must hold even then — catch broadly, warn, return False. Any masked bug
        # still surfaces via the warning log.
        mappings = strm_mappings if strm_mappings is not None else config.get('strm_path_mappings', {})
        mapped = _apply_path_mapping(source_fs_path, mappings)
        with open(strm_fs, 'w', encoding='utf-8') as f:
            f.write(mapped)
        return True
    except Exception as e:  # noqa: BLE001 — best-effort auxiliary artifact, must never propagate
        logger.warning("[readonly_producer] strm 寫入失敗（略過，best-effort）: %s (%s)", strm_fs, e)
        return False


# ---------------------------------------------------------------------------
# T-3: write off-flavor assets + DB upsert (plan §5.2 / §6)
# ---------------------------------------------------------------------------

def _write_media_images(
    cover_fs: str, base_stem: str, meta: dict, source_media: Optional[dict]
) -> tuple[bool, bool]:
    """Write ``-poster``/``-fanart`` images for one movie. Returns
    ``(has_poster, has_fanart)``.

    ``source_media is None`` (scrape/rescrape, or ingest with no detected
    curator sidecars): delegates to ``generate_jellyfin_images`` EXACTLY as
    before this fix — the ONE source of truth for the "generate from cover"
    path (fanart = copy2(cover); poster = crop_to_poster(cover)) — byte-
    identical for every caller that doesn't carry a 3rd cover_strategy
    element (CD scrape/rescrape byte-identity guarantee).

    ``source_media`` is a dict (ingest, curator sidecars detected — see
    ``resolve_ingest_plan``'s cover-axis docstring): each slot is handled
    independently.
      - A detected sidecar (``source_media['poster']`` / ``['fanart']`` not
        None) is copied VERBATIM via ``shutil.copy2`` — byte-identical to the
        source, no crop/focal. An ``OSError`` (source vanished mid-run) falls
        back to the SAME generate step the slot would have used had no
        sidecar been detected at all.
      - A missing slot (``None``) always falls back to that generate step —
        this is the pre-fix behaviour for that slot, unchanged.
    """
    number = meta['number']
    maker = meta.get('maker', '')

    if source_media is None:
        imgs = generate_jellyfin_images(cover_fs, base_stem, number=number, maker=maker)
        return imgs.get('poster', False), imgs.get('fanart', False)

    fanart_path = base_stem + '-fanart.jpg'
    poster_path = base_stem + '-poster.jpg'

    # fanart: verbatim copy of curator sidecar, else generate (copy2 of cover
    # — matches generate_jellyfin_images's own fanart step byte-for-byte).
    src_fanart = source_media.get('fanart')
    has_fanart = False
    if src_fanart:
        try:
            shutil.copy2(src_fanart, fanart_path)
            has_fanart = True
        except Exception as e:  # noqa: BLE001 — mirror generate_jellyfin_images' broad catch; any copy failure falls through to generate
            logger.warning(f"[!] ingest fanart 原樣複製失敗，改由封面生成: {e}")
            src_fanart = None  # fall through to generate below
    if not src_fanart:
        try:
            shutil.copy2(cover_fs, fanart_path)
            has_fanart = True
        except Exception as e:
            logger.warning(f"[!] generate_jellyfin_images fanart 複製失敗: {e}")
            has_fanart = False

    # poster: verbatim copy of curator sidecar, else generate (crop_to_poster
    # of cover — matches generate_jellyfin_images's own poster step).
    src_poster = source_media.get('poster')
    has_poster = False
    if src_poster:
        try:
            shutil.copy2(src_poster, poster_path)
            has_poster = True
        except Exception as e:  # noqa: BLE001 — mirror generate path's broad catch; any copy failure falls through to crop_to_poster
            logger.warning(f"[!] ingest poster 原樣複製失敗，改由封面裁生: {e}")
            src_poster = None  # fall through to generate below
    if not src_poster:
        has_poster = crop_to_poster(cover_fs, poster_path, number=number, maker=maker)

    return has_poster, has_fanart


def _write_movie_assets(
    movie_dir: str,
    meta: dict,
    format_data: dict,
    source_fs_path: str,
    config: dict,
    cover_strategy,
    assets_mode: str = 'full',
    old_base: str = '',
    strm_mappings_getter=None,
) -> dict:
    """Write nfo + cover + -poster/-fanart + extrafanart to movie_dir.

    full mode (default) returns {'cover_fs': str, 'sample_fs': list[str],
    'nfo_mtime': float}. cover_fs is '' when the cover step produces no file (see
    cover_strategy below). nfo_mtime (TASK-104-T1 / CD-104-4) is the real
    os.stat().st_mtime of the NFO just written — generate_nfo has already raised
    on failure by the time this is read, so the file is guaranteed to exist.

    Codex PR#113 round-3 (2026-07-21) added a `write_nfo` gate here that let a
    readonly produce skip the NFO write. REVERTED (owner-confirmed, round-3
    review): that gate was a P1 data-loss — a title-changing rescrape with
    write_nfo=False would skip writing `<new_base>.nfo` while
    `_clean_stale_singletons` still unlinked the OLD `<old_base>.nfo`, losing
    the NFO entirely while the DB kept a stale nfo_mtime claiming it exists.
    Readonly produce is a HOLISTIC operation (a library entry always has an
    NFO) — the router now rejects write_nfo=false for readonly up front (see
    `_READONLY_NO_NFO_ERROR_MSG` in web/routers/scraper.py) instead of
    threading a skip flag down here. The NFO is therefore always written,
    unconditionally, exactly like every other produce caller.

    samples_only mode (TASK-104-T1 / CD-104-1) returns ONLY {'sample_fs':
    list[str]} — downloads meta['sample_images'] into movie_dir/extrafanart
    UNCONDITIONALLY (NOT gated on config['download_sample_images']: an explicit
    supplemental-fetch call means "yes, get samples") and touches NOTHING else —
    no nfo/cover/poster/fanart/strm, no _clean_stale_extrafanart, no
    _clean_stale_singletons. Keeps a "fetch more samples" action from ever
    clobbering metadata/cover it wasn't asked to touch (Codex P1-c).

    cover_strategy (TASK-104-T1 / CD-104-2) replaces the old binary
    "None=download" rule with an explicit 3-state tuple:
      ('copy', local_fs_path) — copy a LOCAL file already on disk into cover_fs
        (ingest, T2: zero network). Copy failure (missing/unreadable source) →
        has_cover=False, same graceful-failure semantics as a failed download —
        never raises.
      ('none',) — do not write a cover at all (ingest has a .nfo but no cover
        image; must NOT silently fall back to downloading).
      ('download', remote_url) — has_cover = bool(remote_url) and
        download_image(remote_url, cover_fs); byte-identical to the pre-T1
        unconditional-download branch (scrape / gear rescrape, C6).
    poster/fanart: generate_jellyfin_images(...) runs whenever has_cover is
    True AND cover_strategy carries no 3rd element (scrape/rescrape, or ingest
    with no detected curator sidecars) — byte-identical to the pre-fix
    behaviour. When cover_strategy is the 3-tuple ingest-copy form (see
    resolve_ingest_plan docstring), each detected `{stem}-poster`/`{stem}
    -fanart` sidecar is copied VERBATIM into the output slot instead of being
    regenerated from the cover; a slot with no detected sidecar still falls
    back to the generate step. See `_write_media_images` below.

    old_base (TASK-89a-T4, Codex #3; T5 follow-up, Codex PR review P2): when
    non-empty, this movie's own stale assets from the PREVIOUS run (different
    title → different basename) are deleted — but only AFTER the corresponding
    new asset has been written successfully, and only when old_base differs
    from this run's basename. The singleton assets (nfo/cover/poster/fanart)
    are cleaned only once generate_nfo has already succeeded, and only the
    ones whose new write actually succeeded this run — so a write that fails
    partway (cover download false, generate_nfo raising) leaves the previous
    run's assets on disk instead of deleting them up front and then failing
    to produce replacements. (samples_only never reaches this cleanup — see
    above.)

    Extrafanart is now managed EXCLUSIVELY by the samples_only (補劇照) path
    (P1 grok-review, pre-merge 2026-07-21): full mode only cleans+rewrites the
    extrafanart dir when THIS run itself carries new sample_images to write
    (``old_base and meta.get('sample_images')``) — full-mode ingest/rescrape
    callers always pass ``meta['sample_images'] == []`` (CD-104-3), so on a
    FULL-mode re-entry of an already-produced video (gear rescrape / 放大鏡
    ingest / batch-enrich) this branch is skipped and previously-fetched
    samples on disk survive untouched. A bare ``if old_base:`` would delete
    the extrafanart dir on every full-mode re-entry even though full mode
    never repopulates it, silently wiping 補劇照 output for any video that
    gets re-produced. Any hypothetical future caller that DOES pass full-mode
    samples still gets correct clean+rewrite semantics.
    """
    os.makedirs(movie_dir, exist_ok=True)

    if assets_mode == 'samples_only':
        ef_dir = Path(movie_dir) / 'extrafanart'
        os.makedirs(ef_dir, exist_ok=True)
        sample_fs: list = []
        for i, url in enumerate(meta.get('sample_images', []), 1):
            dest = str(ef_dir / f'fanart{i}.jpg')
            if download_image(url, dest):
                sample_fs.append(dest)
        return {'sample_fs': sample_fs}

    new_base = base = _build_basename(format_data, source_fs_path, config)
    base_stem = str(Path(movie_dir) / base)

    # 1) Cover: 3-state strategy (CD-104-2) — see docstring above.
    cover_fs = base_stem + '.jpg'
    strategy_kind = cover_strategy[0]
    if strategy_kind == 'copy':
        try:
            shutil.copyfile(cover_strategy[1], cover_fs)
            has_cover = True
        except OSError:
            has_cover = False
    elif strategy_kind == 'none':
        has_cover = False
    else:  # 'download' — byte-identical to the pre-T1 unconditional branch (C6)
        remote_url = cover_strategy[1]
        has_cover = bool(remote_url) and download_image(remote_url, cover_fs)

    # 2) poster/fanart (off mode also produces these — Acceptance #6)
    if has_cover:
        raw_source_media = (
            cover_strategy[2]
            if strategy_kind == 'copy' and len(cover_strategy) > 2
            else None
        )
        # An ingest source with neither a -poster nor a -fanart sidecar detected
        # (both slots None) is treated identically to "no 3rd element at all" —
        # falls through to the single generate_jellyfin_images source of truth
        # below, keeping that path (and every test that mocks
        # generate_jellyfin_images directly, e.g. TestIngestFourMatrix) byte-
        # /call-identical to before this fix.
        source_media = (
            raw_source_media
            if raw_source_media and (raw_source_media.get('poster') or raw_source_media.get('fanart'))
            else None
        )
        has_poster, has_fanart = _write_media_images(cover_fs, base_stem, meta, source_media)
    else:
        has_poster = has_fanart = False

    # 3) extrafanart — gated only on config key; per-movie dir already exists (no create_folder).
    # Stale samples from the previous run are cleaned first (whenever old_base is
    # non-empty) regardless of this run's download_sample_images setting, so a
    # re-scrape with samples toggled off still shrinks the old set to zero.
    # P1 grok-review (pre-merge 2026-07-21): gated additionally on
    # meta.get('sample_images') — see docstring's "Extrafanart is now managed
    # EXCLUSIVELY by samples_only" note. Without this, a full-mode RE-ENTRY of
    # an already-produced video (old_base non-empty) with meta['sample_images']
    # always [] (ingest/rescrape, CD-104-3) would delete extrafanart/ and never
    # repopulate it — destroying samples fetched by an earlier 補劇照 call.
    if old_base and meta.get('sample_images'):
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
    # Always written (P1 revert, round-3 review 2026-07-21) — see the
    # write_nfo paragraph in this function's docstring for why a skip-NFO
    # gate is never reintroduced here.
    external_manager = config.get('external_manager', 'off')
    nfo_fs = base_stem + '.nfo'
    nfo_ok = generate_nfo(
        number=meta['number'],
        title=meta['title'],
        original_title=meta.get('original_title', ''),
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
        external_manager=external_manager,
    )
    if not nfo_ok:
        raise RuntimeError(f"NFO write failed: {nfo_fs}")
    # CD-104-4 (TASK-104-T1): real write mtime, not a hardcoded 0.0 — nfo_ok is
    # True here so the file is guaranteed to exist (generate_nfo already raised
    # above otherwise). MUTATION LOCK: replacing this stat with a hardcoded 0.0
    # is caught by test_readonly_producer.py::TestUpsertDbAssetsMode's
    # nfo_mtime-positive test (see that file for the mutation-lock comment).
    nfo_mtime = os.stat(nfo_fs).st_mtime

    # 5) strm sidecar — media-server flavours only (TASK-90a-T3). off / non
    # media-server → no strm. best-effort: a write failure returns False and
    # feeds has_strm gating below (transient failure keeps the old strm).
    # strm_mappings_getter 在此（_write_strm 前一刻、封面/NFO 都寫完後）才求值，讓斷線尾巴那片
    # 用「真正落 .strm 那一刻」的映射而非片處理開頭的 snapshot（五審五次 Codex）。短路：只在
    # media-server 分支求值（off 不寫 strm），getter=None → None → _write_strm 回退凍結 config。
    has_strm = (
        _write_strm(
            base_stem, source_fs_path, config,
            strm_mappings=(strm_mappings_getter() if strm_mappings_getter is not None else None),
        )
        if external_manager in ('jellyfin', 'emby', 'kodi')
        else False
    )

    # Singleton stale-cleanup runs LAST, only after the new NFO write is confirmed
    # (T5 follow-up, Codex PR review P2) — see docstring above for why this is
    # post-write rather than pre-write.
    _clean_stale_singletons(movie_dir, old_base, new_base, has_cover, has_poster, has_fanart, has_strm)
    return {'cover_fs': cover_fs if has_cover else '', 'sample_fs': sample_fs, 'nfo_mtime': nfo_mtime}


def _upsert_db(
    repo,
    source_uri: str,
    file_info: dict,
    meta: dict,
    assets: dict,
    path_mappings: dict,
    output_dir: str,
    assets_mode: str = 'full',
    existing=None,
) -> None:
    """Manually construct Video and upsert to repo (CD-88b-7).

    full mode (default): path = source_uri (streaming key). cover_path /
    sample_images = local output URIs (via to_file_uri). user_tags intentionally
    omitted → upsert preserves existing DB value. output_dir MUST be a non-empty
    file:/// URI (TASK-89a-T1's upsert CASE-WHEN treats '' as "leave existing
    value alone" — passing '' here would make the very first write for a video
    look like a no-op and silently keep it ''). nfo_mtime (TASK-104-T1 /
    CD-104-4) is the real write mtime threaded in via assets['nfo_mtime'] —
    _write_movie_assets only returns that key in full mode, matching this branch.

    existing (P1/P2 grok-review, pre-merge 2026-07-21): the caller's own
    ``repo.get_by_path(source_uri)`` result (``_produce_one`` already reads this
    once and threads it through — same object T4's old_base reconstruction
    uses). Mirrors ``core.enricher._db_upsert``'s PRESERVATION PATTERN
    (enricher.py:~627-646) for full mode:
      - cover_path: when THIS run produced no cover (``assets['cover_fs']``
        empty — cover_strategy ``('none',)`` or a failed download), fall back
        to ``existing.cover_path`` instead of clobbering the DB to ''. Full
        mode only WRITES a new cover_fs when it actually has one to write
        (see _write_movie_assets); an empty cover_fs is not evidence the old
        cover is gone from disk.
      - sample_images: full-mode ingest/rescrape callers always pass
        ``meta['sample_images'] == []`` (CD-104-3) so ``assets['sample_fs']``
        is always ``[]`` too — on a RE-ENTRY of an already-produced video
        (gear rescrape / 放大鏡 ingest / batch-enrich), this must NOT wipe
        sample_images fetched by an earlier 補劇照 (samples_only) call.
        ``existing`` is None for a brand-new video, so the no-existing-row
        matrix still gets ``sample_images=[]`` (no regression).
    Both preservations only apply in ``full`` mode — ``samples_only`` already
    has its own symmetric skip-when-empty guard below. (A Codex PR#113 round-3
    `write_nfo` skip-gate briefly made ``assets['nfo_mtime']`` optional too and
    added a matching fallback here — REVERTED, round-3 review: the gate itself
    was a P1 data-loss and readonly produce always writes the NFO now, so
    ``assets['nfo_mtime']`` is unconditionally present.)

    samples_only mode (TASK-104-T1 / CD-104-1): does NOT construct/upsert a full
    Video row — a supplemental-samples fetch must never touch cover_path/
    nfo_mtime/metadata (Codex P1-c symmetry with _write_movie_assets). Only
    sample_images is updated, via the dedicated repo.update_sample_images (same
    DB path the existing fetch-samples feature already uses).

    P2 review (2026-07-21): `repo.update_sample_images` is skipped entirely when
    `assets['sample_fs']` is empty — matching `core.enricher.fetch_samples_only`'s
    OWN zero-download behaviour byte for byte (that function only calls its
    `_db_upsert_samples_only` `if written_uris:`, leaving any existing DB
    `sample_images` untouched when nothing was actually downloaded, regardless of
    whether zero downloads happened because the scraper returned no sample URLs
    at all or because every download attempt failed). Previously this branch
    called `update_sample_images(source_uri, [])` unconditionally, which cleared
    a video's existing sample_images to `[]` on a total download failure —
    silently destroying data the caller never asked to touch. Do NOT revert to
    the unconditional call: that is the exact bug this task fixes, not a
    simplification.
    """
    if assets_mode == 'samples_only':
        if assets['sample_fs']:
            repo.update_sample_images(
                source_uri, [to_file_uri(p, path_mappings) for p in assets['sample_fs']]
            )
        # FIX P2-B (P2 parity closeout): a samples-only supplemental fetch must
        # still record output_dir on a row that doesn't have one yet — otherwise
        # a later full ingest can't rely on it being set. Idempotent: never
        # clobbers an already-non-empty output_dir (set_output_dir_if_empty's
        # WHERE clause).
        if output_dir:
            repo.set_output_dir_if_empty(source_uri, output_dir)
        return

    if assets['sample_fs']:
        sample_imgs = [to_file_uri(p, path_mappings) for p in assets['sample_fs']]
    else:
        sample_imgs = existing.sample_images if existing else []

    if assets['cover_fs']:
        cover_uri = to_file_uri(assets['cover_fs'], path_mappings)
    else:
        cover_uri = existing.cover_path if existing else ''

    v = Video(
        path=source_uri,
        number=meta['number'],
        title=meta['title'],
        original_title=effective_original_title(meta, existing),
        actresses=meta.get('actors', []),
        maker=meta.get('maker', ''),
        director=meta.get('director', ''),
        series=meta.get('series') or None,
        label=meta.get('label', ''),
        tags=meta.get('tags', []),
        sample_images=sample_imgs,
        duration=meta.get('duration'),
        size_bytes=file_info['size'],
        cover_path=cover_uri,
        output_dir=output_dir,
        release_date=meta.get('date', ''),
        mtime=file_info['mtime'],
        nfo_mtime=assets['nfo_mtime'],
        scrape_attempted_at=time.time(),
    )
    repo.upsert(v)


# ---------------------------------------------------------------------------
# TASK-104-T2 (CD-104-3 / CD-104-3a / CD-104-3b): NFO → producer-meta adapter +
# resolve_ingest_plan (the metadata/cover two-axis decision the ingest/rescrape
# gear needs). Both are pure functions — no I/O beyond the caller-supplied
# root / src_fs_path — so the per-file produce_source loop below can call them
# directly without adding a new resource-lifecycle concern.
# ---------------------------------------------------------------------------

def _nfo_to_producer_meta(root: ET.Element, fallback_number: str) -> dict:
    """Reverse-map a parsed NFO `<movie>` root into producer-meta shape (CD-104-3b).

    Mirrors VideoScanner.parse_nfo's (gallery_scanner.py:303) tag-extraction
    robustness — multi-tag date fallback, genre/tag merge-with-dedup, set/name
    — but OUTPUTS producer-meta keys (number/title/actors/tags/date/maker/
    director/series/label/duration/url/_summary/_rating/cover/sample_images),
    matching what `_write_movie_assets`/`generate_nfo`/`_upsert_db` already
    consume (this module, :625/:790). Do NOT reuse `core.enricher._nfo_to_meta`
    — its actresses/release_date/cover_url shape silently drops fields at the
    writer/upsert boundary (card note).

    Two round-trip edges reversing `generate_nfo` (core/organizer.py:597):
      - title: generate_nfo writes `[number]display` — strip that prefix back
        off via `_strip_num_prefixes`, else re-generating double-wraps to
        `[num][num]…`.
      - _rating: `<rating>` is written as raw×2 (organizer.py:674) — divide
        back by 2 here; empty/non-numeric/<=0 → None (never resurrects a
        rating that generate_nfo never actually wrote).

    `number` falls back to `fallback_number` (caller's `extract_number
    (basename)`) when the NFO has neither a non-empty `<num>` nor `<uniqueid>`.
    `cover`/`sample_images` are always '' / [] here — ingest cover is decided
    by `resolve_ingest_plan`'s own cover axis (cover_strategy), not this meta
    dict; samples are never bulk-fetched (see `resolve_ingest_plan` docstring).
    """
    def _text(tag: str) -> str:
        elem = root.find(tag)
        return (elem.text or '').strip() if elem is not None else ''

    # number/maker/date fallback chains mirror VideoScanner.parse_nfo
    # (gallery_scanner.py:323/330/337) EXACTLY so ingest reads a third-party
    # NFO identically to OpenAver's incumbent scan reader (no ingest-vs-scan
    # date/maker drift). `uniqueid` kept as an extra tail fallback (generate_nfo
    # always writes it; harmless for OpenAver NFOs where <num> already wins).
    number = ''
    for tag in ('num', 'id', 'uniqueid'):
        elem = root.find(tag)
        if elem is not None and elem.text and elem.text.strip():
            number = elem.text.strip()
            break
    if not number:
        number = fallback_number or ''

    raw_title = _text('title')
    title = _strip_num_prefixes(raw_title, number) if raw_title else raw_title
    original_title = _text('originaltitle')

    # any-depth `.//actor/name` — mirrors VideoScanner.parse_nfo (gallery_scanner.py:345)
    # EXACTLY. A direct-children-only `root.findall('actor')` would silently return []
    # for a third-party NFO shaped `<movie><actors><actor><name>X</name></actor></actors></movie>`
    # (actors nested one level deeper than OpenAver's own flat `<movie><actor>` shape) —
    # VideoScanner would still read the actor via the scan path, but ingest would clear it
    # (P1 finding, 2026-07-21 review). MUTATION LOCK: reverting to `root.findall('actor')`
    # must turn test_nested_actors_element_any_depth RED (test_readonly_producer.py).
    actors = [
        (elem.text or '').strip()
        for elem in root.findall('.//actor/name')
        if elem.text
    ]

    # genre/tag merge-with-dedup, mirroring VideoScanner.parse_nfo:350-358
    # (genre first, then any <tag> not already present).
    tags: list = []
    for genre_elem in root.findall('genre'):
        if genre_elem.text:
            t = genre_elem.text.strip()
            if t not in tags:
                tags.append(t)
    for tag_elem in root.findall('tag'):
        if tag_elem.text:
            t = tag_elem.text.strip()
            if t not in tags:
                tags.append(t)

    date = _text('release') or _text('premiered') or _text('year')

    set_elem = root.find('set')
    series = ''
    if set_elem is not None:
        n_elem = set_elem.find('name')
        series = (n_elem.text or '').strip() if n_elem is not None else ''

    runtime_text = _text('runtime')
    duration: Optional[int] = None
    if runtime_text:
        try:
            duration = int(runtime_text)
        except ValueError:
            duration = None

    rating_text = _text('rating')
    rating_val: Optional[float] = None
    if rating_text:
        try:
            r = float(rating_text)
            if r > 0:
                rating_val = r / 2
        except ValueError:
            rating_val = None

    return {
        'number': number,
        'title': title,
        'original_title': original_title,
        'actors': actors,
        'tags': tags,
        'date': date,
        'maker': _text('maker') or _text('studio'),
        'director': _text('director'),
        'series': series,
        'label': _text('label'),
        'duration': duration,
        'url': _text('website'),
        '_summary': _text('plot'),
        '_rating': rating_val,
        'cover': '',
        'sample_images': [],
    }


def resolve_ingest_plan(
    src_fs_path: str,
    number: Optional[str],
    config: dict,
    *,
    action: str = 'ingest',
    proxy_url: str = '',
    scraper_data: Optional[dict] = None,
    source: Optional[str] = None,
    javbus_lang: Optional[str] = None,
) -> tuple:
    """Metadata + cover two-axis decision for one source file (CD-104-3a).

    `config` is scraper_cfg (matches produce_source's own call-site
    convention). Returns `(meta, cover_strategy)`; `meta` is None when nothing
    usable was found — the caller falls to its own no_scrape stub, matching
    the pre-T2 "search_jav returns None" contract byte for byte.

    action='ingest' (bulk loop / 放大鏡): metadata prefers a valid sidecar NFO
    (zero network, via `_nfo_to_producer_meta`) over `search_jav`; cover
    prefers a LOCAL file (`VideoScanner.find_cover_image`, with the NFO's
    `<thumb>` threaded in as `nfo_thumb` when the NFO is valid) over a remote
    download — local-first, ingest intent (CD-104-10: nfo_thumb must be
    threaded or L3 silently degrades). When there is no usable NFO, the
    scrape-fallback (P2 fix, round-3 review 2026-07-21) honors the caller's own
    `source`/`javbus_lang` instead of hardcoding `source="auto"` — mirrors the
    rescrape branch's own dispatch just below: a concrete `source` (not
    None/'auto') routes through `search_jav_single_source`; otherwise falls
    back to `search_jav(source='auto', ...)`. Both dispatch cases thread
    `javbus_lang` through.

    action='rescrape' (gear; T3 wires the caller): metadata and cover are
    ALWAYS remote — a re-scrape means "get the current upstream truth", never
    reusing whatever's already on disk (a stale local cover must not survive a
    deliberate re-scrape). `scraper_data` (TASK-104-T3), when given, is used
    verbatim as the metadata (already-fetched detail_url/candidate-version
    payload from the router's javlibrary confirm flow — matches
    `to_legacy_dict()` + `internal_nfo_carriers()` shape) and no network call is
    made here. Without `scraper_data`: a concrete `source` (not None/'auto')
    routes through `search_jav_single_source` (explicit source pick, mirrors
    `rescrape_preview_endpoint`'s own branching); otherwise falls back to
    `search_jav(source='auto', ...)`.

    A `parse_nfo()` failure (bad XML → root=None) is treated as "no usable
    NFO": `nfo_thumb=None`, metadata falls to `search_jav`, and the cover
    `('none',)` branch below keys on `valid_nfo` (root is not None) — NEVER on
    the bare `nfo_path.exists()` check. Keying on file-exists alone would let
    a malformed sidecar both withhold metadata AND lock the cover into
    `('none',)` with no download fallback (card's 特有邊界 #1).

    Common (both actions): before returning, `sample_images` is always forced
    to `[]` — neither ingest nor rescrape bulk-fetches sample images (spec
    §3-A / Non-Goals; samples are on-demand only, via the separate case-C
    `assets_mode='samples_only'` path). When `meta` is None, the computed
    cover_strategy is discarded and `('none',)` is returned instead — nothing
    to copy/download without any metadata to attach it to.

    Curated -poster/-fanart passthrough (owner-approved fix, 2026-07-21):
    action='ingest' only, when the cover strategy resolves to the local-copy
    form (`('copy', cover_fs)`), the 3rd element is appended as
    `('copy', cover_fs, {'poster': poster_fs, 'fanart': fanart_fs})` — the
    source directory's OWN `{stem}-poster.*` / `{stem}-fanart.*` sidecars
    (curated Jellyfin/Emby libraries ship both, distinct portrait/landscape
    images), each `None` when absent. `_write_movie_assets` copies these
    VERBATIM into the output `-poster`/`-fanart` slots instead of regenerating
    them from whichever single image `find_cover_image` picked as the cover
    (which previously discarded the curator's real poster — see plan-104
    cover axis notes). `('none',)` is left untouched (no local cover at all →
    nothing to copy). `action='rescrape'` never adds this 3rd element —
    cover_strategy stays a 2-tuple there, so the scrape/rescrape write path
    (`source_media is None` in `_write_movie_assets`) stays byte-identical to
    before this fix.
    """
    nfo_path = Path(src_fs_path).with_suffix('.nfo')
    root = None
    if nfo_path.exists():
        _, root = parse_nfo(str(nfo_path))
    valid_nfo = root is not None

    if action == 'ingest':
        if valid_nfo:
            meta = _nfo_to_producer_meta(root, fallback_number=number)
            # Codex PR#113 one-pass alignment (2026-07-21): _nfo_to_producer_meta
            # carries no 'source' key at all — the readonly endpoints derive
            # EnrichResult.source_used from meta.get('source', ''), so an NFO-
            # sourced ingest must explicitly mark itself 'nfo' (mirrors
            # core.enricher's own source_used='nfo' for its NFO-read branch)
            # or it would silently report '' instead.
            meta['source'] = 'nfo'
        elif not number:
            meta = None
        # P2 fix (round-3 review 2026-07-21): honor the caller's own source/
        # javbus_lang instead of hardcoding source="auto" — mirrors the
        # rescrape branch's dispatch below.
        elif source and source not in (None, 'auto'):
            meta = search_jav_single_source(number, source, proxy_url, javbus_lang=javbus_lang)
        else:
            meta = search_jav(number, source="auto", proxy_url=proxy_url, javbus_lang=javbus_lang)

        nfo_thumb = root.findtext('thumb') if valid_nfo else None
        cover_fs = VideoScanner().find_cover_image(src_fs_path, nfo_thumb=nfo_thumb)
        if cover_fs:
            src_dir = Path(src_fs_path).parent
            stem = Path(src_fs_path).stem
            poster_fs = next(
                (str(p) for ext in IMAGE_EXTENSIONS
                 if (p := src_dir / f"{stem}-poster{ext}").exists()),
                None,
            )
            fanart_fs = next(
                (str(p) for ext in IMAGE_EXTENSIONS
                 if (p := src_dir / f"{stem}-fanart{ext}").exists()),
                None,
            )
            cover_strategy = ('copy', cover_fs, {'poster': poster_fs, 'fanart': fanart_fs})
        elif valid_nfo:
            cover_strategy = ('none',)
        else:
            cover_strategy = ('download', meta['cover']) if meta and meta.get('cover') else ('none',)
    else:  # 'rescrape'
        if scraper_data:
            meta = scraper_data
        elif source and source not in (None, 'auto'):
            meta = search_jav_single_source(number, source, proxy_url, javbus_lang=javbus_lang) if number else None
        else:
            meta = search_jav(number, source="auto", proxy_url=proxy_url, javbus_lang=javbus_lang) if number else None
        cover_strategy = ('download', meta['cover']) if meta and meta.get('cover') else ('none',)

    if meta is None:
        return None, ('none',)
    meta['sample_images'] = []
    return meta, cover_strategy


# ---------------------------------------------------------------------------
# TASK-104-T1 (CD-104-1): single-file produce primitive — extracted from
# produce_source's per-file try-block so ingest/rescrape/samples-only callers
# (T2/T3: readonly gear/放大鏡/補劇照 endpoints) can reuse the SAME
# resolve→write→upsert pipeline instead of a second, driftable copy. Landing
# in the SAME movie_dir every time (via _resolve_movie_dir's read-and-reuse) is
# what keeps every one of those callers from ever orphaning/overwriting a
# sibling's assets.
#
# Deliberately excludes: _emit / the try-except wrapper / result counters
# (orchestrator bookkeeping) and the skip check / extract_number / search_jav
# (scrape-decision concerns) — all of those stay in produce_source's loop (and,
# later, the readonly endpoints' own orchestration).
# ---------------------------------------------------------------------------

def _produce_one(
    repo,
    source,
    config,
    *,
    file_info: dict,
    meta: dict,
    cover_strategy,
    assets_mode: str = 'full',
    existing,
    output_root: str,
    output_uri: str,
    allocated_this_run: set,
    path_mappings: dict,
    strm_mappings_getter=None,
) -> tuple[Path, dict]:
    """Resolve movie_dir, write assets, upsert DB for ONE file. Returns
    ``(movie_dir, assets)`` (contract change, P2 review 2026-07-21 — was a
    bare ``movie_dir`` Path; every caller must now unpack the tuple).

    ``assets`` is the dict `_write_movie_assets` returned (``{'cover_fs',
    'sample_fs', 'nfo_mtime'}`` in full mode / ``{'sample_fs'}`` in
    samples_only mode) — the shared enabler for two router-level bugs:
      - fetch-samples was reporting the REQUESTED sample count instead of the
        ACTUALLY-downloaded one (`len(assets['sample_fs'])` is ground truth;
        `_write_movie_assets` only appends successfully-downloaded files to
        `sample_fs`, so a partial/total download failure no longer over-reports).
      - batch/enrich-single readonly success responses carried no
        nfo_written/cover_written for the frontend — callers can now derive
        `cover_written = bool(assets.get('cover_fs'))` (nfo_written is
        unconditionally True on a successful return in full mode:
        `_write_movie_assets` raises before returning if the NFO write itself
        fails, so reaching here always means the NFO was written).

    config here is scraper_cfg — the same section _resolve_movie_dir /
    _write_movie_assets already take (matches produce_source's call site).
    existing is the caller's own repo.get_by_path(source_uri) result (read ONCE
    by the caller, not here) — T4's old_base reconstruction and T3's
    read-and-reuse movie-dir logic both consume it, and it is now also passed
    through to ``_upsert_db`` (P2 grok-review) so a full-mode RE-ENTRY of an
    already-produced video preserves existing cover_path/sample_images instead
    of clobbering them when this run's assets are empty.

    source is accepted (not currently read in this body) for parity with the
    CD-104-1 contract and for T2/T3 callers that will need it (e.g. resolving
    ingest vs. rescrape intent upstream of this primitive).

    A Codex PR#113 round-3 `write_nfo` param that threaded a skip-NFO flag
    down to `_write_movie_assets` was REVERTED (P1 data-loss, round-3 review
    2026-07-21) — every caller, including the readonly router endpoints,
    always writes the NFO now.
    """
    src_uri = to_file_uri(file_info["path"], path_mappings)
    fd = _format_data(meta, file_info["path"], config)
    movie_dir, output_dir_uri = _resolve_movie_dir(
        repo, src_uri, existing, output_root, output_uri,
        fd, config, allocated_this_run, path_mappings,
    )
    old_base = _build_old_base(existing, file_info["path"], config)  # '' when no prior row/title/number
    # FIX P1 (Codex PR#113 round-6, 2026-07-21; feature/105 T3: extracted to
    # effective_original_title helper): synthesize the EFFECTIVE original_title
    # ONCE, before writing any asset, so the output NFO
    # (_write_movie_assets→generate_nfo) and the DB row (_upsert_db) consume the
    # SAME value. A re-scrape whose source returns an empty original_title must
    # NOT clobber the on-disk NFO's <originaltitle> to '' while the DB keeps the
    # old value — that split (preserve in _upsert_db only) was on-disk data loss
    # + NFO/DB drift. Mirrors the cover_path/sample_images preserve-if-empty
    # contract. Full-mode only in effect (samples_only writes no NFO), but the
    # mutation is harmless there. _upsert_db calls the same helper as a defensive
    # net for any direct caller, but after this line meta already carries the truth.
    meta['original_title'] = effective_original_title(meta, existing)
    # PR #93 五審四次 P2 (option C): media-server 模式下用注入的 getter 讓
    # _write_movie_assets 在真正落 .strm 那一刻才重讀 fresh strm_path_mappings
    # （見 _write_movie_assets 內部該段落的完整解釋）。strm_mappings_getter=None
    # （既有呼叫）→ 回退凍結 config、零重讀、行為不變。
    assets = _write_movie_assets(
        str(movie_dir), meta, fd, file_info["path"], config,
        cover_strategy=cover_strategy, assets_mode=assets_mode,
        old_base=old_base, strm_mappings_getter=strm_mappings_getter,
    )
    _upsert_db(
        repo, src_uri, file_info, meta, assets, path_mappings, output_dir_uri,
        assets_mode=assets_mode, existing=existing,
    )
    return movie_dir, assets


# ---------------------------------------------------------------------------
# TASK-105-T5 (T2-a/T2-b): readonly-only Tier-2 convergence helpers
# ---------------------------------------------------------------------------

def _readonly_stub_not_found(repo, uri: str, number, fs_path: str) -> None:
    """唯讀 not-found 樁列（順序不可反）：先 insert_if_ignore 建樁 row、
    再 update_scrape_attempted_at 記帳。update_scrape_attempted_at 是 bare
    UPDATE...WHERE path=?，無 row 靜默 no-op，故必須先建樁（見 video.py:1144-1167）。

    repo 由呼叫端傳（各站來源不同：S1/S2 現場新建、S3 呼叫端傳入共用實例）；
    `if number:` guard（若有）留呼叫端 — helper body 無條件執行兩步。
    """
    repo.insert_if_ignore(Video(path=uri, number=number, title=os.path.basename(fs_path)))
    repo.update_scrape_attempted_at(uri, time.time())


def _readonly_enrich_failure(error, reason=None) -> EnrichResult:
    """唯讀失敗回報固定形狀：success/nfo/cover 全 False、extrafanart=0、
    fields_filled=[]、source_used=''；只 error/reason 由呼叫端定。

    reason 預設 None（對齊 fetch-samples 路徑「無 top-level exception boundary」
    的刻意語意）；需 'error'/'not_found' 的站顯式傳 reason=。
    """
    return EnrichResult(
        success=False, nfo_written=False, cover_written=False,
        extrafanart_written=0, fields_filled=[], source_used='',
        error=error, reason=reason,
    )


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


def produce_source(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None, force: bool = False, reachable: bool = True, strm_mappings_getter=None) -> ProduceResult:
    """Orchestrate per-source readonly generation: guard → list → skip → scrape → write → upsert.

    Pure service layer. NO FastAPI, NO SSE, NO router. (CD-88b-8, §1.1)
    Caller (88c) injects on_progress/should_abort for SSE streaming.

    strm_mappings_getter (PR #93 五審四次 P2, option C): optional 0-arg callable returning the
    CURRENT strm_path_mappings dict, read fresh per file. The SSE generate path injects one that
    re-reads config from disk so the strm sidecar uses the live mapping, not the run-start frozen
    snapshot — closing the disconnect-tail residual (watcher clears the generate token the instant
    it detects a disconnect, but the producer only checks should_abort at each per-file checkpoint,
    so it can finish one more file's _write_strm after the token is gone; in that window another tab
    could land a new mapping and this last file would otherwise write with the stale frozen value,
    never self-healing). None (default) → the frozen config mapping is used, so every existing
    caller/test is behaviourally unchanged and no config re-read happens. Only consulted for
    media-server flavours (off writes no strm).
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

        # Codex PR#113 P2 #1: the old `if not number: continue` bailed BEFORE
        # resolve_ingest_plan ever got a chance to read an adjacent NFO's
        # <num>/<id>/<uniqueid> — a curated file whose FILENAME has no
        # extractable number but whose sidecar NFO does was wrongly no_scrape'd.
        # resolve_ingest_plan already guards this: its scrape branch is
        # `search_jav(number, ...) if number else None`, so number=None never
        # reaches search_jav — safe to always call it.
        #
        # CD-104-3a (TASK-104-T2): metadata + cover two-axis decision — .nfo
        # sidecar (zero network) / local cover file win over search_jav /
        # download when present (ingest intent, local-first). Falls straight
        # to the pre-T2 scrape-everything behavior when neither sidecar nor
        # local cover exists (CD-104-2's 3-state cover_strategy tuple lives
        # inside resolve_ingest_plan now, not inline here).
        meta, cover_strategy = resolve_ingest_plan(
            fi["path"], number, scraper_cfg, action='ingest', proxy_url=proxy_url,
        )
        if not meta or not meta.get('number'):
            # Only stub+record-attempt when a filename number exists (matches
            # the old `if not number` branch's behavior byte-for-byte for the
            # no-number-no-NFO case — no DB row for a file we can't identify
            # at all).
            if number:
                _readonly_stub_not_found(repo, src_uri, number, fi["path"])
            result.no_scrape += 1
            _emit(on_progress, result, src_uri, "no_scrape")
            continue

        try:
            existing = repo.get_by_path(src_uri)  # T3: read once; T4 reuses title/actresses/maker/release_date
            movie_dir, _assets = _produce_one(  # _produce_one now returns (movie_dir, assets) — this loop only needs movie_dir
                repo, source, scraper_cfg,
                file_info=fi, meta=meta, cover_strategy=cover_strategy, assets_mode='full',
                existing=existing, output_root=output_root, output_uri=output_uri,
                allocated_this_run=allocated_this_run, path_mappings=path_mappings,
                strm_mappings_getter=strm_mappings_getter,
            )
            result.created += 1
            _emit(on_progress, result, src_uri, "created", str(movie_dir), number)
        except Exception:
            result.failed += 1
            # Full detail + traceback to the log (error level, diagnosable);
            # ProduceOutcome.error is the 88c SSE-bound field — use a fixed message
            # (repo error policy) so raw exception text (paths, errno) never leaks.
            logger.exception("[readonly_producer] 生成失敗: %s", src_uri)
            _emit(on_progress, result, src_uri, "failed", number=number, error="生成失敗")

    # TASK-99b-T1 (CD-99b-1/2/7/8, spec §3.10)：post-loop bulk focal pass。落在
    # per-file 迴圈之後——此時本次產出的產物封面已落盤，提前呼叫會讓
    # maybe_submit_video_focal 內的 os.path.exists(cover_fs) 早退、靜默不報錯
    # （HANDOFF §4「順序陷阱」）。bulk gate（非 per-item hook，CD-99b-2）：
    # _should_skip（:846）讓已產過的片直接 continue，走不到 _upsert_db；per-item
    # hook 只涵蓋本次新產者，0.12 既有唯讀庫（全數零焦點）永遠補不到。候選來自
    # DB（get_empty_focal_candidates），天然涵蓋 skipped 片。
    #
    # CD-99b-8：should_abort 已中止 → 完全跳過本段（fresh 查一次，非迴圈起始
    # snapshot、非迴圈內累積的 break 狀態）。worker 是單執行緒 FIFO、每 job
    # ~3s，候選可達數千片，中止後仍照排＝取消後仍吃 CPU 數十分鐘，且把使用者
    # 正在等的手動 focal 塞在其後。只 gate 本段，絕不 `return`——下方 prune
    # 區塊必須照跑（其判準來自完整 files 列表，非本次處理進度，abort 後跑
    # prune 是既有且安全的語意）。
    focal_aborted = should_abort is not None and should_abort()
    if not focal_aborted:
        try:
            # 各自現場算（不可複用下方 prune 的 this_run_uris，:902 之前——那個
            # 被 `if files and not result.skipped_paths` gate 住，focal 不該因
            # 為 partial-scan 就整批不排）。與 _upsert_db 寫入同一套推導式
            # （to_file_uri(fi["path"], path_mappings)），不疊 normalize_path。
            focal_this_run_uris = [to_file_uri(fi["path"], path_mappings) for fi in files]
            if focal_this_run_uris:
                for c_path, c_number, c_maker, c_cover_path in repo.get_empty_focal_candidates(focal_this_run_uris):
                    # Codex P1（CD-99b-8 二次修）：入口 gate（:912）只擋「取消已在
                    # 迴圈開始前發生」；候選數可達數千、每圈一次 os.path.exists，
                    # 迴圈本身可能跑到秒級，取消也可能落在迴圈中途。此處每圈
                    # fresh 查一次，與入口 gate 防同一種傷害、只是取消落點不同。
                    if should_abort is not None and should_abort():
                        break
                    if requires_face_detection(c_number, c_maker):
                        cover_fs = uri_to_local_fs_path(c_cover_path, path_mappings)
                        maybe_submit_video_focal(c_number, c_maker, c_path, cover_fs, db_path=repo.db_path, cover_path_uri=c_cover_path)
        except Exception:
            logger.warning("[readonly_producer] focal trigger 批次排程失敗（不影響生成結果）", exc_info=True)

    # TASK-89b-T6 (CD-89b-6): DB-row-only prune. Gate = reachable AND this-run
    # list non-empty AND no skipped_paths. reachable is implicitly True here —
    # the "unreachable" guard above already returned before this point, so any
    # execution path reaching here has aborted_reason == "" (empty).
    if files and not result.skipped_paths:
        source_root_fs = uri_to_fs_path(source.path)  # uri-no-reverse: native config path (SourceConfig.path), comparison-only
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
