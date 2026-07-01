"""readonly_producer — T-1 skeleton: dataclasses + listing + incremental skip.

Pure backend module. NO API, NO UI, NO frontend. (feature/88b)

Canonical Decisions enforced here:
  CD-88b-1: listing via fast_scan_directory only (CD-88b-1).
  CD-88b-2: get_cover_index() is the additive read-only bulk query added to
             VideoRepository; no shape change to get_mtime_index().
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from core.database import Video
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
from core.path_utils import is_path_under_dir, normalize_path, to_file_uri, uri_to_fs_path
from core.scraper import extract_number, normalize_number, search_jav
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


# ---------------------------------------------------------------------------
# Internal helpers (all independently unit-testable)
# ---------------------------------------------------------------------------

def _min_size_bytes(gallery_config: dict) -> int:
    """Convert gallery.min_size_mb → bytes. Mirrors scanner.py:221."""
    return int(gallery_config.get("min_size_mb", 0)) * 1024 * 1024


def _list_source_videos(source_path: str, extensions: set, min_size_bytes: int) -> list[dict]:
    """List video files under source_path. Delegates to fast_scan_directory (CD-88b-1).

    Returns a list of dicts with keys: path, mtime, size, nfo_mtime.
    nfo_mtime is ignored by this module (guard G1: no source-NFO reads).

    source_path may be a native FS path OR a ``file:///`` URI (DirectoryConfig.path
    accepts both per core/config.py schema). uri_to_fs_path is idempotent on FS-path
    input and converts URI form to an FS path, so scanning works for both without a
    hand-rolled ``startswith('file:///')`` check (path-contract compliant).
    """
    fs_dir = uri_to_fs_path(source_path)
    return fast_scan_directory(fs_dir, extensions, min_size_bytes)


def _build_cover_index(repo, output_uri: str) -> dict:
    """Return {source_uri: cover_path} filtered to rows where cover falls under output_uri.

    Calls repo.get_cover_index() (bulk, avoids N+1).
    Empty / None cover entries are excluded here; _should_skip has a redundant guard.
    """
    full = repo.get_cover_index()  # {path: cover_path}
    return {
        p: c
        for p, c in full.items()
        if c and is_path_under_dir(c, output_uri)
    }


def _should_skip(source_uri: str, output_uri: str, cover_index: dict) -> bool:
    """B3/P2a three-condition skip predicate.

    Returns True (skip) only when ALL of:
      1. DB has a row for source_uri with a non-empty cover_path
      2. cover_path falls under output_uri
      3. The cover file actually exists on disk
    Any condition missing → return False (rebuild).
    """
    cover = cover_index.get(source_uri)
    if not cover:
        return False                                        # no row / no cover → rebuild
    if not is_path_under_dir(cover, output_uri):           # double-guard (cover_index already filtered)
        return False
    return Path(uri_to_fs_path(cover)).exists()            # physical file must exist


# ---------------------------------------------------------------------------
# T-2: naming + collision-avoidance helpers (pure functions, no I/O except
#       Path.exists for orphan detection in _movie_dir)
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


def _build_owners(cover_index: dict) -> dict:
    """Build owners map {movie_dir_str: source_uri} from cover_index.

    cover_index is {source_uri: cover_uri}. The parent of the cover file
    is the movie_dir owned by that source. (plan §4.2)
    """
    owners: dict = {}
    for src, cover in cover_index.items():
        if cover:
            movie_dir = str(Path(uri_to_fs_path(cover)).parent)
            owners[movie_dir] = src
    return owners


def _movie_leaf_base(number: str, source_uri: str) -> str:
    """Return the leaf directory name for a single movie. (plan §4.2 / card §5)

    Four branches:
    1. no stem          → number
    2. stem IS number   → number   (normalised comparison)
    3. stem CONTAINS number (case-insensitive) → stem   (already includes disambiguator)
    4. otherwise        → "{number}-{stem}"
    """
    stem = sanitize_filename(Path(uri_to_fs_path(source_uri)).stem)
    if not stem:
        return number
    if normalize_number(stem) == number:
        return number
    if number and number.upper() in stem.upper():
        return stem
    return f"{number}-{stem}"


def _movie_dir(
    output_root: str,
    format_data: dict,
    source_uri: str,
    config: dict,
    owners: dict,
) -> Path:
    """Return the per-movie directory Path, registering source_uri in owners.

    Collision avoidance (CD-88b-4 / P2b):
    - If candidate is already owned by a DIFFERENT source → append SHA-1 hash suffix.
    - If candidate exists on disk but is not in owners → treat as foreign, hash.
    - Idempotent: same source_uri → same dir (owner == source_uri → no hash).
    - owners is mutated in-place; callers pass a persistent dict across calls.
    """
    parts = _folder_parts(format_data, config)
    leaf = _movie_leaf_base(format_data['number'], source_uri)
    candidate = Path(output_root, *parts, leaf)

    owner = owners.get(str(candidate))
    if owner is None and candidate.exists():
        owner = "<foreign>"        # disk-orphan: not in owners but exists on disk

    if owner not in (None, source_uri):
        h = hashlib.sha1(source_uri.encode()).hexdigest()[:8]
        leaf = f"{leaf}-{h}"
        candidate = Path(output_root, *parts, leaf)

    owners[str(candidate)] = source_uri
    return candidate


# ---------------------------------------------------------------------------
# T-3: write off-flavor assets + DB upsert (plan §5.2 / §6)
# ---------------------------------------------------------------------------

def _write_movie_assets(
    movie_dir: str,
    meta: dict,
    format_data: dict,
    source_fs_path: str,
    config: dict,
) -> dict:
    """Write nfo + cover + -poster/-fanart + extrafanart to movie_dir.

    Returns {'cover_fs': str, 'sample_fs': list[str]}.
    cover_fs is '' when cover download fails or meta['cover'] is empty.
    """
    os.makedirs(movie_dir, exist_ok=True)
    base = _build_basename(format_data, source_fs_path, config)
    base_stem = str(Path(movie_dir) / base)

    # 1) Cover: download from remote URL (C6 — always re-scrape, never read source image)
    cover_fs = base_stem + '.jpg'
    has_cover = bool(meta.get('cover')) and download_image(meta['cover'], cover_fs)

    # 2) poster/fanart (off mode also produces these — Acceptance #6)
    imgs = generate_jellyfin_images(cover_fs, base_stem) if has_cover else {}
    has_poster = imgs.get('poster', False)
    has_fanart = imgs.get('fanart', False)

    # 3) extrafanart — gated only on config key; per-movie dir already exists (no create_folder)
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
    return {'cover_fs': cover_fs if has_cover else '', 'sample_fs': sample_fs}


def _upsert_db(
    repo,
    source_uri: str,
    file_info: dict,
    meta: dict,
    assets: dict,
    path_mappings: dict,
) -> None:
    """Manually construct Video and upsert to repo (CD-88b-7).

    path = source_uri (streaming key).
    cover_path / sample_images = local output URIs (via to_file_uri).
    user_tags intentionally omitted → upsert preserves existing DB value.
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
        release_date=meta.get('date', ''),
        mtime=file_info['mtime'],
        nfo_mtime=0.0,
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


def produce_source(source, config, repo, *, proxy_url="", on_progress=None, should_abort=None) -> ProduceResult:
    """Orchestrate per-source readonly generation: guard → list → skip → scrape → write → upsert.

    Pure service layer. NO FastAPI, NO SSE, NO router. (CD-88b-8, §1.1)
    Caller (88c) injects on_progress/should_abort for SSE streaming.
    """
    result = ProduceResult(source_path=source.path, output_path=source.output_path or "")

    # G8/D7 guards (CD-88b-6 / Acceptance #11)
    if not source.readonly:
        result.aborted_reason = "not_readonly"
        return result
    if not (source.output_path or "").strip():
        result.aborted_reason = "no_output_path"
        return result

    gallery = config.get("gallery", {})
    scraper_cfg = config.get("scraper", {})
    path_mappings = gallery.get("path_mappings", {})

    output_root = normalize_path(source.output_path)
    output_uri = to_file_uri(output_root, path_mappings)

    cover_index = _build_cover_index(repo, output_uri)
    owners = _build_owners(cover_index)

    files = _list_source_videos(source.path, get_video_extensions(config), _min_size_bytes(gallery))

    for fi in files:
        if should_abort is not None and should_abort():
            break

        src_uri = to_file_uri(fi["path"], path_mappings)

        if _should_skip(src_uri, output_uri, cover_index):
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
            result.no_scrape += 1
            _emit(on_progress, result, src_uri, "no_scrape")
            continue

        try:
            fd = _format_data(meta, fi["path"], scraper_cfg)
            movie_dir = _movie_dir(output_root, fd, src_uri, scraper_cfg, owners)
            assets = _write_movie_assets(str(movie_dir), meta, fd, fi["path"], scraper_cfg)
            _upsert_db(repo, src_uri, fi, meta, assets, path_mappings)
            result.created += 1
            _emit(on_progress, result, src_uri, "created", str(movie_dir), number)
        except Exception:
            result.failed += 1
            # Full detail + traceback to the log (error level, diagnosable);
            # ProduceOutcome.error is the 88c SSE-bound field — use a fixed message
            # (repo error policy) so raw exception text (paths, errno) never leaks.
            logger.exception("[readonly_producer] 生成失敗: %s", src_uri)
            _emit(on_progress, result, src_uri, "failed", number=number, error="生成失敗")

    return result
