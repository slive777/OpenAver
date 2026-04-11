"""
Integration tests for core/scrapers/actress/orchestrator.py — Phase 42b T4.1

Tests the 4-route parallel orchestrator with all scrapers mocked via source-module paths.
Covers: C1 text cascade, C3 photo cascade, C4 return shape, TD-1 age fix,
        cache TTL, legacy flat↔nested consistency.

Patch targets (source-module paths):
    core.scrapers.actress.minnano_av.scrape_minnano_av
    core.scrapers.actress.wiki_ja.scrape_wiki_ja
    core.scrapers.actress.graphis.scrape_graphis_photo
    core.scrapers.actress.gfriends.lookup_gfriends
"""

import time
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from core.scrapers.actress.orchestrator import get_actress_profile, _cache, _CACHE_TTL, _compute_age_from_birth

# ---------------------------------------------------------------------------
# Patch target constants
# ---------------------------------------------------------------------------
_PATCH_MINNANO  = 'core.scrapers.actress.minnano_av.scrape_minnano_av'
_PATCH_WIKI     = 'core.scrapers.actress.wiki_ja.scrape_wiki_ja'
_PATCH_GRAPHIS  = 'core.scrapers.actress.graphis.scrape_graphis_photo'
_PATCH_GFRIENDS = 'core.scrapers.actress.gfriends.lookup_gfriends'

_ACTRESS_NAME = "明里つむぎ"


# ---------------------------------------------------------------------------
# Mock data factories
# ---------------------------------------------------------------------------

def _make_minnano(name="明里つむぎ", birth="1998-03-31", **kwargs):
    return {
        "name_ja": name,
        "name_hiragana": "あかりつむぎ",
        "name_romaji": "Akari Tsumugi",
        "aliases": [],
        "birth": birth,
        "hometown": "神奈川県",
        "height": "157cm",
        "bust": "80cm",
        "waist": "58cm",
        "hip": "83cm",
        "cup": "B",
        "blood": "O",
        "agency": "S1",
        "hobby": "スポーツ",
        "debut_work": "...",
        "blog_url": "",
        "official_url": "",
        "tags": [],
        "photo_url": "https://www.minnano-av.com/p_actress_125_125/016/273627.jpg",
        **kwargs,
    }


def _make_wiki(name="明里つむぎ", birth="1998-03-31", **kwargs):
    return {
        "name_ja": name,
        "nickname": "つむぎ",
        "birth": birth,
        "hometown": "神奈川県",
        "height": "157cm",
        "bust": "80cm",
        "waist": "58cm",
        "hip": "83cm",
        "cup": "B",
        "blood": "O",
        "exclusive_makers": "",
        "debut_year": "2017",
        "photo_url": "https://upload.wikimedia.org/wikipedia/commons/sample.jpg",
        "photo_needs_resize": True,
        "photo_license": "Commons",
        **kwargs,
    }


def _make_graphis(name_en="Akari Tsumugi", **kwargs):
    return {
        "name": "",
        "prof_url": "https://graphis.ne.jp/photos/akari_tsumugi_prof.jpg",
        "backdrop_url": "https://graphis.ne.jp/photos/akari_tsumugi_back.jpg",
        "name_en": name_en,
        "age": 999,   # intentionally stale — TD-1 must ignore this
        "height": "157cm",
        "cup": "B",
        "bust": "80cm",
        "waist": "58cm",
        "hip": "83cm",
        "hobby": "写真",
        **kwargs,
    }


def _make_gfriends_url():
    return "https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/Content/9-AVDBS/明里つむぎ.jpg"


# ---------------------------------------------------------------------------
# Autouse fixture: clear cache before and after every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


# ---------------------------------------------------------------------------
# datetime freeze helper
# ---------------------------------------------------------------------------

class _FrozenDatetime(datetime):
    """Subclass of datetime that overrides now() to return a frozen instant.
    strptime is inherited and works normally."""
    _frozen: datetime = None

    @classmethod
    def now(cls, tz=None):
        return cls._frozen


def _frozen_dt_class(frozen: datetime):
    """Return a FrozenDatetime subclass frozen at the given instant."""
    class _Cls(_FrozenDatetime):
        _frozen = frozen
    return _Cls


# ---------------------------------------------------------------------------
# TestHappyPath — all 4 routes return data
# ---------------------------------------------------------------------------

class TestHappyPath:

    def test_all_four_routes_not_none(self):
        minnano = _make_minnano()
        wiki    = _make_wiki()
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is not None

    def test_primary_text_source_minnano(self):
        minnano = _make_minnano()
        wiki    = _make_wiki()
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["primary_text_source"] == "minnano"
        assert result["text"] == minnano

    def test_photo_cascade_graphis_wins(self):
        minnano = _make_minnano()
        wiki    = _make_wiki()
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["photo_source"] == "graphis"
        assert result["photo_url"] == graphis["prof_url"]
        assert result["backdrop_url"] == graphis["backdrop_url"]

    def test_all_sources_dict(self):
        minnano = _make_minnano()
        wiki    = _make_wiki()
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["all_sources"]["minnano"] == minnano
        assert result["all_sources"]["wiki"] == wiki
        assert result["all_sources"]["graphis"] == graphis
        assert result["all_sources"]["gfriends"] == gfurl

    def test_legacy_flat_name_and_img(self):
        minnano = _make_minnano()
        graphis = _make_graphis()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["name"] == minnano["name_ja"]
        assert result["img"] == result["photo_url"]


# ---------------------------------------------------------------------------
# TestC1Cascade — text primary source fallback
# ---------------------------------------------------------------------------

class TestC1Cascade:

    def test_minnano_none_wiki_wins(self):
        wiki    = _make_wiki()
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["primary_text_source"] == "wiki"
        assert result["text"] == wiki
        assert result["name"] == wiki["name_ja"]
        # Photo cascade: Graphis still wins because it has prof_url
        assert result["photo_source"] == "graphis"

    def test_minnano_wiki_none_graphis_wins(self):
        graphis = _make_graphis()
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["primary_text_source"] == "graphis"
        assert result["text"] == graphis
        # Bug 2 fix: name falls back to queried name (text.name is "" in _make_graphis,
        # so the final fallback is the queried `name` arg)
        assert result["name"] == _ACTRESS_NAME  # queried name fallback via text.name or name arg
        # Graphis has name_en
        assert result["name_en"] == graphis["name_en"]
        # Graphis has no birth key
        assert result["birth"] is None

    def test_all_four_none_returns_none(self):
        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is None


# ---------------------------------------------------------------------------
# TestPhotoCascade — photo source fallback chain
# ---------------------------------------------------------------------------

class TestPhotoCascade:

    def test_graphis_no_prof_url_gfriends_wins(self):
        minnano = _make_minnano()
        # Graphis present but prof_url missing/empty
        graphis = _make_graphis(prof_url="")
        gfurl   = _make_gfriends_url()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=gfurl):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["photo_source"] == "gfriends"
        assert result["photo_url"] == gfurl
        assert result["img"] == gfurl

    def test_graphis_none_gfriends_none_wiki_wins(self):
        wiki = _make_wiki()

        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["photo_source"] == "wiki"
        assert result["photo_url"] == wiki["photo_url"]

    def test_only_minnano_has_photo(self):
        minnano = _make_minnano()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["photo_source"] == "minnano"
        assert result["photo_url"] == minnano["photo_url"]


# ---------------------------------------------------------------------------
# TestTD1Age — current_age computed from birth, never from source
# ---------------------------------------------------------------------------

class TestTD1Age:

    def _call_with_frozen_now(self, frozen_now: datetime, minnano_birth):
        minnano = _make_minnano(birth=minnano_birth)
        FrozenDT = _frozen_dt_class(frozen_now)

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None), \
             patch('core.scrapers.actress.orchestrator.datetime', FrozenDT):
            return get_actress_profile(_ACTRESS_NAME)

    def test_age_before_birthday_in_year(self):
        # Birth 1998-03-31, frozen 2026-01-01 → hasn't reached birthday → age 27
        result = self._call_with_frozen_now(datetime(2026, 1, 1), "1998-03-31")
        assert result["current_age"] == 27
        assert result["age"] == 27

    def test_age_after_birthday_in_year(self):
        # Birth 1998-03-31, frozen 2026-04-01 → past birthday → age 28
        result = self._call_with_frozen_now(datetime(2026, 4, 1), "1998-03-31")
        assert result["current_age"] == 28
        assert result["age"] == 28

    def test_age_none_when_birth_none(self):
        minnano = _make_minnano(birth=None)
        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["current_age"] is None
        assert result["age"] is None

    def test_age_none_when_birth_invalid(self):
        minnano = _make_minnano(birth="invalid-format")
        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["current_age"] is None
        assert result["age"] is None

    def test_age_not_read_from_graphis_stale_field(self):
        # Graphis has age=999; orchestrator must compute from birth, not read 999
        minnano = _make_minnano(birth="1998-03-31")
        graphis = _make_graphis()  # age=999 is baked in by factory
        FrozenDT = _frozen_dt_class(datetime(2026, 1, 1))

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None), \
             patch('core.scrapers.actress.orchestrator.datetime', FrozenDT):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["age"] != 999
        assert result["age"] == 27  # computed, not from graphis

    def test_age_consistency_age_equals_current_age(self):
        minnano = _make_minnano(birth="1995-06-15")
        FrozenDT = _frozen_dt_class(datetime(2026, 7, 1))

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None), \
             patch('core.scrapers.actress.orchestrator.datetime', FrozenDT):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result["age"] == result["current_age"]


# ---------------------------------------------------------------------------
# TestComputeAgeUnit — unit tests for _compute_age_from_birth directly
# ---------------------------------------------------------------------------

class TestComputeAgeUnit:

    def test_compute_age_before_birthday(self):
        FrozenDT = _frozen_dt_class(datetime(2026, 1, 1))
        with patch('core.scrapers.actress.orchestrator.datetime', FrozenDT):
            assert _compute_age_from_birth("1998-03-31") == 27

    def test_compute_age_after_birthday(self):
        FrozenDT = _frozen_dt_class(datetime(2026, 4, 1))
        with patch('core.scrapers.actress.orchestrator.datetime', FrozenDT):
            assert _compute_age_from_birth("1998-03-31") == 28

    def test_compute_age_none_birth(self):
        assert _compute_age_from_birth(None) is None

    def test_compute_age_invalid_birth(self):
        assert _compute_age_from_birth("not-a-date") is None


# ---------------------------------------------------------------------------
# TestLegacyFlatConsistency — nested↔flat key parity
# ---------------------------------------------------------------------------

class TestLegacyFlatConsistency:

    def _assert_consistency(self, result):
        assert result["img"] == result["photo_url"]
        assert result["backdrop"] == result["backdrop_url"]
        assert result["age"] == result["current_age"]
        text = result.get("text")
        if text is not None:
            # name cascades: text.name_ja → text.name → queried name arg
            expected_name = text.get("name_ja") or text.get("name") or _ACTRESS_NAME
            assert result["name"] == expected_name
            assert result["birth"] == text.get("birth")

    def test_consistency_full_happy_path(self):
        minnano = _make_minnano()
        graphis = _make_graphis()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        self._assert_consistency(result)

    def test_consistency_wiki_as_text_source(self):
        wiki    = _make_wiki()
        graphis = _make_graphis()

        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        self._assert_consistency(result)

    def test_consistency_only_minnano(self):
        minnano = _make_minnano()

        with patch(_PATCH_MINNANO, return_value=minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        self._assert_consistency(result)


# ---------------------------------------------------------------------------
# TestCacheTTL — cache hit/miss/expiry behaviour
# ---------------------------------------------------------------------------

class TestCacheTTL:

    def test_cache_hit_returns_stale_result(self):
        """Second call within TTL returns cached result; scrapers called only once."""
        minnano_first  = _make_minnano(name="初回結果")
        minnano_second = _make_minnano(name="二回目結果")

        mock_minnano = MagicMock(side_effect=[minnano_first, minnano_second])

        with patch(_PATCH_MINNANO, mock_minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result1 = get_actress_profile(_ACTRESS_NAME)
            result2 = get_actress_profile(_ACTRESS_NAME)

        # Scraper should have been called exactly once (cache hit on second call)
        assert mock_minnano.call_count == 1
        # Both results should be identical (from cache)
        assert result1["name"] == result2["name"] == "初回結果"

    def test_cache_expired_fetches_fresh(self):
        """Stale cache entry (older than TTL) causes fresh scraper call."""
        from core.scrapers.actress.orchestrator import _cache, _CACHE_TTL

        stale_result = {"__stale__": True, "name": "stale"}
        cache_key = "明里つむぎ"   # _normalize_name of _ACTRESS_NAME
        _cache[cache_key] = {
            "data": stale_result,
            "timestamp": time.time() - _CACHE_TTL - 10,  # expired
        }

        minnano = _make_minnano(name="fresh")
        mock_minnano = MagicMock(return_value=minnano)

        with patch(_PATCH_MINNANO, mock_minnano), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        # Fresh scraper should have been called
        assert mock_minnano.call_count == 1
        assert result["name"] == "fresh"


# ---------------------------------------------------------------------------
# TestMeaningfulTextFilter — Bug 1 regression: shell source must not suppress richer fallback
# ---------------------------------------------------------------------------

class TestMeaningfulTextFilter:
    """Bug 1 regression: shell/empty text source must not suppress richer fallback."""

    def test_wiki_shell_does_not_suppress_graphis(self):
        """Wiki returning shell dict (name_ja only, no text fields) must not
        win C1 cascade over a Graphis source with actual data."""
        wiki_shell = {
            "name_ja": _ACTRESS_NAME,
            "nickname": "",
            "birth": "",
            "hometown": "",
            "height": "",
            "bust": "", "waist": "", "hip": "",
            "cup": "",
            "blood": "",
            "exclusive_makers": "",
            "debut_year": "",
            "photo_url": "https://upload.wikimedia.org/shell.jpg",
            "photo_needs_resize": True,
            "photo_license": "Commons",
        }
        graphis = _make_graphis()  # has birth, height, BWH, etc.

        with patch(_PATCH_MINNANO, return_value=None), \
             patch(_PATCH_WIKI, return_value=wiki_shell), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is not None
        # Graphis (with real data) must win C1, not the wiki shell
        assert result["primary_text_source"] == "graphis"
        assert result["text"] == graphis
        # But wiki dict is still stored in all_sources for reference
        assert result["all_sources"]["wiki"] == wiki_shell

    def test_minnano_shell_does_not_suppress_wiki(self):
        """Parallel safety: if minnano returns a shell (no meaningful text), wiki wins."""
        minnano_shell = {
            "name_ja": _ACTRESS_NAME,
            "name_hiragana": "",
            "name_romaji": "",
            "aliases": [],
            "birth": "",
            "hometown": "",
            "height": "",
            "bust": "", "waist": "", "hip": "",
            "cup": "",
            "blood": "",
            "agency": "",
            "hobby": "",
            "debut_work": "",
            "blog_url": "",
            "official_url": "",
            "tags": [],
            "photo_url": "https://www.minnano-av.com/shell.jpg",
        }
        wiki = _make_wiki()

        with patch(_PATCH_MINNANO, return_value=minnano_shell), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is not None
        assert result["primary_text_source"] == "wiki"

    def test_all_shells_no_text_source(self):
        """All text sources return shells (no meaningful text) → primary_text_source None.
        minnano_shell/wiki_shell are truthy dicts, so orchestrator edge-case guard
        (not any([...])) does NOT fire early-return None. Result is non-None but
        primary_text_source=None and text=None; name falls back to queried arg."""
        minnano_shell = {"name_ja": _ACTRESS_NAME}
        wiki_shell = {"name_ja": _ACTRESS_NAME}

        with patch(_PATCH_MINNANO, return_value=minnano_shell), \
             patch(_PATCH_WIKI, return_value=wiki_shell), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        # minnano_shell is truthy → not any([...]) guard does not fire
        # but neither shell has meaningful text, so cascade picks no text source
        assert result is not None
        assert result["primary_text_source"] is None
        assert result["text"] is None
        assert result["current_age"] is None
        # Bug 2 fix: name falls back to queried arg when text is None
        assert result["name"] == _ACTRESS_NAME

    def test_minnano_aliases_only_wins_c1_over_wiki(self):
        """Codex 2nd review: Minnano's C1 primary value is aliases/agency/debut_work/
        tags/blog_url/official_url — not just birth/BWH. A Minnano result that has
        ONLY aliases (no birth/size) must still win C1 cascade over a richer Wiki.

        Regression for the Codex review where _MEANINGFUL_TEXT_FIELDS was missing
        Minnano-only fields, causing valid Minnano results to be treated as shells."""
        minnano_aliases_only = {
            "name_ja": _ACTRESS_NAME,
            "name_hiragana": "あかりつむぎ",
            "name_romaji": "Akari Tsumugi",
            "aliases": [  # 9 known aliases — classic Phase 43 auto-populate target
                {"ja": "別名1", "hiragana": "べつめい1", "romaji": "Betsumei 1"},
                {"ja": "別名2", "hiragana": "べつめい2", "romaji": "Betsumei 2"},
            ],
            "birth": "",         # intentionally empty — Minnano parser failed to grab
            "hometown": "",
            "height": "", "bust": "", "waist": "", "hip": "", "cup": "", "blood": "",
            "agency": "",        # also empty
            "hobby": "",
            "debut_work": "",
            "blog_url": "", "official_url": "",
            "tags": [],
            "photo_url": "",
        }
        wiki = _make_wiki()  # has birth, height, BWH — "richer" in the Wiki sense

        with patch(_PATCH_MINNANO, return_value=minnano_aliases_only), \
             patch(_PATCH_WIKI, return_value=wiki), \
             patch(_PATCH_GRAPHIS, return_value=None), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is not None
        # C1 cascade: Minnano wins because aliases is non-empty (C1 primary value proposition)
        assert result["primary_text_source"] == "minnano"
        assert result["text"] == minnano_aliases_only
        # Phase 43 auto-populate consumers reach aliases via all_sources.minnano.aliases
        assert len(result["all_sources"]["minnano"]["aliases"]) == 2
        # Wiki is still stored for reference but not the text source
        assert result["all_sources"]["wiki"] == wiki

    def test_minnano_agency_only_wins_c1(self):
        """Same logic as above but with only agency field populated — proves the
        whole Minnano-specific field set is honored, not just aliases."""
        minnano_agency_only = {
            "name_ja": _ACTRESS_NAME,
            "name_hiragana": "", "name_romaji": "",
            "aliases": [],
            "birth": "", "hometown": "",
            "height": "", "bust": "", "waist": "", "hip": "", "cup": "", "blood": "",
            "agency": "プレステージ",  # only this
            "hobby": "", "debut_work": "",
            "blog_url": "", "official_url": "",
            "tags": [],
            "photo_url": "",
        }
        graphis = _make_graphis()

        with patch(_PATCH_MINNANO, return_value=minnano_agency_only), \
             patch(_PATCH_WIKI, return_value=None), \
             patch(_PATCH_GRAPHIS, return_value=graphis), \
             patch(_PATCH_GFRIENDS, return_value=None):
            result = get_actress_profile(_ACTRESS_NAME)

        assert result is not None
        assert result["primary_text_source"] == "minnano"
        assert result["text"]["agency"] == "プレステージ"
