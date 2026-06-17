"""Per-source reachability probe for the live canary (TASK-73b-T3).

`_probe_reachable(source, number, scraper) -> bool` distinguishes state-1 (site
down / unreachable) from state-2 (200 but parser empty) for Group A sources.
Used only when `search()` returns None — a True probe + None search means the
site responded but parsing failed (state-2 fail); a False probe means the site
is unreachable (skip).

CONTRACT: this function MUST NEVER raise. Any exception (connection error,
timeout, proxy failure, missing attribute) -> return False (= unreachable ->
skip). probe false-positives (e.g. javbus soft-404 returning 200 for a delisted
number) are absorbed by quorum (>=1 pass wins).

Zero production scraper changes: reuses existing scraper URLs/helpers/session.
"""
import requests


def _probe_reachable(source: str, number: str, scraper) -> bool:
    """Return True if `source` looks reachable for `number`, else False.

    Group A only (javbus / heyzo / d2pass / jav321 / dmm). Group B and unknown
    sources return False (-> classify_one row 6 skip, never a false state-2 fail).
    """
    try:
        if source == "javbus":
            # Same URL as search() (javbus.py:95-96), including the lang prefix so
            # the probe stays faithful if the scraper is ever built non-default-lang
            # (default zh-tw prefix is ""). Reuse session headers for a browser-y
            # User-Agent (some edges 403 a bare requests UA).
            prefix = scraper._get_lang_prefix() if hasattr(scraper, "_get_lang_prefix") else ""
            headers = dict(getattr(scraper._session, "headers", {}))
            resp = requests.get(
                f"{scraper.BASE_URL}{prefix}/{number}", headers=headers, timeout=10
            )
            return resp.status_code == 200

        if source == "heyzo":
            num = scraper._extract_heyzo_num(number)
            if not num:
                return False
            resp = requests.get(
                f"https://en.heyzo.com/moviepages/{num}/index.html", timeout=10
            )
            return resp.status_code == 200

        if source == "d2pass":
            # Use the scraper's own JSON fetch: non-None = HTTP 200 + valid JSON.
            site = scraper._detect_site_order(number)[0]
            movie_id = scraper.normalize_number(number)
            return scraper._fetch_json(site, movie_id) is not None

        if source == "jav321":
            # Low-confidence: guessed detail URL (jav321.py:177). Real search is a
            # POST flow, so a 200 here may be a false-positive -> absorbed by quorum.
            resp = requests.get(
                f"https://www.jav321.com/video/{number.lower()}", timeout=10
            )
            return resp.status_code == 200

        if source == "dmm":
            # Proxy-reachability: a bare GET to the GraphQL API through the proxied
            # session. The endpoint may reject a GET (400/404/405) but ANY HTTP
            # response proves proxy + host are reachable. Only connection/proxy
            # errors (caught below) -> False.
            scraper._session.get(scraper.API_URL, timeout=10)
            return True

        # Group B (javdb / fc2 / avsox) or unknown source.
        return False
    except Exception:
        # NEVER raise — any failure means "treat as unreachable" -> skip.
        return False
