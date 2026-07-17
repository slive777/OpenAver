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
from core.focal import requires_face_detection
from core.focal_trigger import maybe_submit_video_focal
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
    uri_to_local_fs_path,
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

def _write_movie_assets(
    movie_dir: str,
    meta: dict,
    format_data: dict,
    source_fs_path: str,
    config: dict,
    old_base: str = '',
    strm_mappings_getter=None,
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
    imgs = generate_jellyfin_images(
        cover_fs, base_stem, number=meta['number'], maker=meta.get('maker', '')
    ) if has_cover else {}
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
    external_manager = config.get('external_manager', 'off')
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
        external_manager=external_manager,
    )
    if not nfo_ok:
        raise RuntimeError(f"NFO write failed: {nfo_fs}")

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
            # PR #93 五審四次 P2 (option C)：media-server 模式下，每片用注入的 getter 重讀 fresh
            # strm_path_mappings（非 generate 起始凍結值）。封死斷線尾巴殘留——watcher 偵測到斷線
            # 即清 generate token，但 producer 每片 checkpoint 才看 should_abort，會多做完當下這片；
            # 此時另一分頁可能已存新映射（gate 見不到在飛 generate 而放行），該片若用凍結舊映射落檔則
            # 永久 stale。傳 getter callable（非此刻 snapshot）往下，讓 _write_movie_assets 在
            # _write_strm 前一刻才求值（五審五次 Codex：snapshot 在此求值後、封面/NFO 等寫檔仍需時間，
            # 期間存的新映射會被漏掉）。getter=None（既有呼叫/測試）→ 回退凍結 config、零重讀、行為不變。
            assets = _write_movie_assets(
                str(movie_dir), meta, fd, fi["path"], scraper_cfg,
                old_base=old_base, strm_mappings_getter=strm_mappings_getter,
            )
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
