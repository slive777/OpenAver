"""Unit tests for core.source_merger.merge_results (TASK-61a-6 / TASK-65b-2).

Contract: epic §5.1.1 (CD-61-9):
- text/meta: 整包贏 — first source in user_order present in candidates wins the
  whole text block (title/actresses/tags/series/maker/director) + meta
  (date/duration/rating/votes); empty fields fall back to later user_order sources.
- cover_url / sample_images: follow user_order — each field resolved independently
  (first non-empty source per field, may come from different sources).
- empty candidates → defensive (caller never calls with empty; return safe).
"""
import pytest

from core.scrapers.models import Video, Actress
from core.source_merger import merge_results


def _v(source, **kw):
    """Build a minimal Video for `source`."""
    return Video(number=kw.pop("number", "TEST-001"), source=source, **kw)


# ---------------------------------------------------------------------------
# Text/meta: user_order 整包贏
# ---------------------------------------------------------------------------

def test_text_fields_follow_user_order_whole_block():
    """Two sources with full text; user_order=[jav321, javbus] → jav321 wins ALL text."""
    javbus = _v(
        "javbus",
        title="JavBus Title",
        actresses=[Actress(name="JB Actress")],
        tags=["jb-tag"],
        series="JB Series",
        maker="JB Maker",
        director="JB Director",
    )
    jav321 = _v(
        "jav321",
        title="Jav321 Title",
        actresses=[Actress(name="J321 Actress")],
        tags=["j321-tag"],
        series="J321 Series",
        maker="J321 Maker",
        director="J321 Director",
    )
    merged = merge_results({"javbus": javbus, "jav321": jav321},
                           user_order=["jav321", "javbus"])

    assert merged.title == "Jav321 Title"
    assert [a.name for a in merged.actresses] == ["J321 Actress"]
    assert merged.tags == ["j321-tag"]
    assert merged.series == "J321 Series"
    assert merged.maker == "J321 Maker"
    assert merged.director == "J321 Director"
    assert merged.source == "jav321"


def test_text_source_empty_field_falls_back():
    """text_source has empty title → fall back to next user_order source's title."""
    primary = _v("jav321", title="", maker="J321 Maker")
    backup = _v("javbus", title="Backup Title", maker="JB Maker")
    merged = merge_results({"jav321": primary, "javbus": backup},
                           user_order=["jav321", "javbus"])

    # whole block from jav321 EXCEPT empty title falls back
    assert merged.title == "Backup Title"
    assert merged.maker == "J321 Maker"
    assert merged.source == "jav321"


def test_label_backfills_from_later_source():
    """label parity (61a-6 review B1): text_source empty label → backfill from later source.

    OLD merge block backfilled `label`; the field-list refactor must keep parity since
    `label` feeds NFO writing.
    """
    primary = _v("jav321", title="J321 Title", label="")
    backup = _v("javbus", title="JB Title", label="JB Label")
    merged = merge_results({"jav321": primary, "javbus": backup},
                           user_order=["jav321", "javbus"])

    assert merged.title == "J321 Title"   # whole block still from jav321
    assert merged.label == "JB Label"     # empty label backfilled
    assert merged.source == "jav321"


def test_label_kept_from_text_source_when_present():
    """text_source has a non-empty label → keep it, no backfill."""
    primary = _v("jav321", label="J321 Label")
    backup = _v("javbus", label="JB Label")
    merged = merge_results({"jav321": primary, "javbus": backup},
                           user_order=["jav321", "javbus"])
    assert merged.label == "J321 Label"


def test_meta_fields_from_text_source():
    """date/duration/rating/votes come from text_source (整包贏)."""
    primary = _v("jav321", date="2024-01-01", duration=120, rating=4.5, votes=10)
    backup = _v("javbus", date="2099-12-31", duration=999, rating=1.0, votes=999)
    merged = merge_results({"jav321": primary, "javbus": backup},
                           user_order=["jav321", "javbus"])

    assert merged.date == "2024-01-01"
    assert merged.duration == 120
    assert merged.rating == 4.5
    assert merged.votes == 10


def test_duration_zero_is_present():
    """duration=0 is a value (is None check), not falsy → not overwritten."""
    primary = _v("jav321", duration=0)
    backup = _v("javbus", duration=120)
    merged = merge_results({"jav321": primary, "javbus": backup},
                           user_order=["jav321", "javbus"])
    assert merged.duration == 0


# ---------------------------------------------------------------------------
# Cover: user_order with independent fields
# ---------------------------------------------------------------------------

def test_cover_follows_user_order():
    """cover_url follows user_order — jav321 first → cover from jav321, NOT javbus.

    KEY behavioral proof (TASK-65b-2): javbus ordered LAST → cover must NOT be javbus's.
    """
    javbus = _v("javbus", title="JB", cover_url="http://javbus/cover.jpg",
                sample_images=["http://javbus/s1.jpg"])
    jav321 = _v("jav321", title="J321", cover_url="http://jav321/cover.jpg",
                sample_images=["http://jav321/s1.jpg"])
    merged = merge_results({"javbus": javbus, "jav321": jav321},
                           user_order=["jav321", "javbus"])

    # text from jav321 (first in user_order)
    assert merged.title == "J321"
    assert merged.source == "jav321"
    # cover from jav321 (first in user_order) — NOT javbus
    assert merged.cover_url == "http://jav321/cover.jpg"
    assert merged.sample_images == ["http://jav321/s1.jpg"]
    assert merged.cover_url != "http://javbus/cover.jpg"


def test_cover_and_sample_images_resolved_independently():
    """cover_url and sample_images may come from different sources."""
    # javbus has cover but no samples; jav321 has samples but no cover
    javbus = _v("javbus", cover_url="http://javbus/cover.jpg", sample_images=[])
    jav321 = _v("jav321", cover_url="", sample_images=["http://jav321/s.jpg"])
    merged = merge_results({"javbus": javbus, "jav321": jav321},
                           user_order=["javbus", "jav321"])

    assert merged.cover_url == "http://javbus/cover.jpg"
    assert merged.sample_images == ["http://jav321/s.jpg"]


def test_cover_user_order_direct():
    """user_order directly selects cover source — any source in user_order wins."""
    # avsox is the only source; user_order=['avsox'] → avsox cover wins directly
    avsox = _v("avsox", title="AV", cover_url="http://avsox/cover.jpg")
    merged = merge_results({"avsox": avsox},
                           user_order=["avsox"])
    assert merged.cover_url == "http://avsox/cover.jpg"


def test_cover_skips_empty_source_in_user_order():
    """user_order source with empty cover → skip to next qualifying source in user_order."""
    # user_order=['javbus','jav321']; javbus has empty cover → jav321 wins
    javbus = _v("javbus", cover_url="")
    jav321 = _v("jav321", cover_url="http://jav321/cover.jpg")
    merged = merge_results({"javbus": javbus, "jav321": jav321},
                           user_order=["javbus", "jav321"])
    assert merged.cover_url == "http://jav321/cover.jpg"



# ---------------------------------------------------------------------------
# Fallbacks / edge cases
# ---------------------------------------------------------------------------

def test_single_source_passthrough():
    """single candidate → that source's data verbatim."""
    only = _v("javbus", title="Only Title", cover_url="http://c.jpg",
              maker="M", actresses=[Actress(name="A")])
    merged = merge_results({"javbus": only}, user_order=["javbus"])
    assert merged.title == "Only Title"
    assert merged.cover_url == "http://c.jpg"
    assert merged.maker == "M"
    assert merged.source == "javbus"


def test_text_source_keys_not_in_user_order_falls_back_to_insertion_order():
    """candidates whose keys are not in user_order → use insertion-order first."""
    a = _v("avsox", title="AVSOX Title")
    b = _v("fc2", title="FC2 Title")
    merged = merge_results({"avsox": a, "fc2": b}, user_order=["javbus", "jav321"])
    # neither in user_order → insertion-order first = avsox
    assert merged.source == "avsox"
    assert merged.title == "AVSOX Title"


def test_empty_candidates_returns_none():
    """defensive: empty candidates → None (caller guards before merge)."""
    assert merge_results({}, user_order=["javbus"]) is None


