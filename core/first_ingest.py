"""首次入庫判定：純函式，無 I/O、無 DB。"""
from dataclasses import dataclass
from typing import Callable

from core.organizer import _strip_num_prefixes, pick_filename_title


@dataclass(frozen=True)
class FirstIngest:
    scraper_cfg: dict
    on_done: Callable[[str], None]


def is_first_ingest_readonly(meta_source: str, existing_nfo_mtime) -> bool:
    return meta_source != 'nfo' and not (existing_nfo_mtime or 0) > 0


def is_first_ingest_sidecar(nfo_existed: bool, source_used: str, title_from_site) -> bool:
    return not nfo_existed and source_used not in ('db', 'nfo', '') and bool(title_from_site)


def pick_title(
    site_title: str,
    filename: str,
    number: str,
    actors: list,
    maker: str,
    scraper_cfg: dict,
) -> tuple:
    picked = pick_filename_title(filename, number, actors, {'maker': maker}, scraper_cfg)
    if picked:
        return _strip_num_prefixes(picked, number), site_title
    return site_title, ''
