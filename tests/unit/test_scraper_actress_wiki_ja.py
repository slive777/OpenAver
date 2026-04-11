"""
Unit tests for core.scrapers.actress.wiki_ja

Covers:
  1. All 5 HTML fixtures parse without crashing, return non-None with non-empty name_ja
  2. Inch trap regression — スリーサイズ cm row wins over in row
  3. Flag icon regression — 25×17 flag image skipped, real portrait selected
  4. Commons thumb → raw URL (pure string, no network)
  5. photo_needs_resize: True flag present
  6. Not found / empty / non-infobox HTML returns None (or empty result)
  7. Non-AV actress graceful fallback (希島あいり has singer/talent tags but still parses)
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.scrapers.actress.wiki_ja import (
    _commons_thumb_to_raw,
    _parse_wiki_ja_html,
    scrape_wiki_ja,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "actress"

# HTML fixtures are not committed (tests/fixtures/actress/*.html is in .gitignore).
# To capture locally for fixture-based tests, run from repo root:
#   source venv/bin/activate && python -c "
#   import requests, urllib.parse
#   from pathlib import Path
#   HEADERS = {'User-Agent': 'OpenAver-research/1.0', 'Accept-Language': 'ja,en;q=0.8'}
#   for n in ['明里つむぎ','希島あいり','天馬ゆい','桃乃木かな','涼森れむ']:
#       r = requests.get(f'https://ja.wikipedia.org/wiki/{urllib.parse.quote(n)}', headers=HEADERS, timeout=20)
#       if r.status_code == 200:
#           Path(f'tests/fixtures/actress/wiki_ja_{n}.html').write_text(r.text, encoding='utf-8')
#   "
# Without fixtures: parametrized tests below generate 0 cases (pytest handles empty list);
# individual fixture tests use inline pytest.skip guards.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> str:
    return FIXTURE_DIR.joinpath(f"wiki_ja_{name}.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. All fixtures parse
# ---------------------------------------------------------------------------

FIXTURE_NAMES = [
    p.stem.replace("wiki_ja_", "")
    for p in sorted(FIXTURE_DIR.glob("wiki_ja_*.html"))
]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_parses(name):
    """Every captured fixture must return a non-None dict with non-empty name_ja."""
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None, f"expected non-None result for {name}"
    assert result.get("name_ja") == name, f"name_ja mismatch for {name}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_has_birth(name):
    """Every fixture should yield a parseable birth date (YYYY-MM-DD)."""
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    birth = result.get("birth", "")
    assert birth, f"empty birth for {name}"
    # Rough format check
    parts = birth.split("-")
    assert len(parts) == 3 and len(parts[0]) == 4, f"bad birth format {birth!r}"


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_photo_needs_resize_flag(name):
    """photo_needs_resize must be True in all fixture results (C3 constraint)."""
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    assert result.get("photo_needs_resize") is True, (
        f"photo_needs_resize should be True for {name}"
    )


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_photo_license(name):
    """photo_license must be 'Commons'."""
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    assert result.get("photo_license") == "Commons"


# ---------------------------------------------------------------------------
# 2. Inch trap regression
# ---------------------------------------------------------------------------

_INCH_TRAP_HTML = """
<html><body>
<table class="infobox biography">
  <tr><th>スリーサイズ</th><td>80 - 58 - 83 cm</td></tr>
  <tr><th>スリーサイズ</th><td>31 - 23 - 33 in</td></tr>
</table>
</body></html>
"""


def test_inch_trap_prefers_cm():
    """Parser must use the cm row and NOT the inch row for BWH."""
    result = _parse_wiki_ja_html(_INCH_TRAP_HTML, "テスト")
    assert result is not None
    assert result["bust"] == "80cm", f"expected 80cm, got {result['bust']!r}"
    assert result["waist"] == "58cm", f"expected 58cm, got {result['waist']!r}"
    assert result["hip"] == "83cm", f"expected 83cm, got {result['hip']!r}"


def test_inch_trap_no_inch_values():
    """Inch values (31/23/33) must NOT appear as bust/waist/hip."""
    result = _parse_wiki_ja_html(_INCH_TRAP_HTML, "テスト")
    assert result is not None
    for field in ("bust", "waist", "hip"):
        val = result.get(field, "")
        assert "31" not in val or "cm" in val, (
            f"{field}={val!r} looks like an inch value"
        )
    # Specifically: bust should be 80cm, not 31cm
    assert result["bust"] != "31cm"


# ---------------------------------------------------------------------------
# 3. Flag icon regression
# ---------------------------------------------------------------------------

_FLAG_ICON_HTML = """
<html><body>
<table class="infobox biography">
  <tr>
    <th>出身地</th>
    <td>
      <img src="//upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Flag_of_Japan.svg/40px-Flag_of_Japan.svg.png"
           width="25" height="17" alt="日本" />
      日本 ・ 神奈川県
    </td>
  </tr>
  <tr>
    <th>写真</th>
    <td>
      <img src="//upload.wikimedia.org/wikipedia/commons/thumb/a/ab/ActressPhoto.jpg/220px-ActressPhoto.jpg"
           width="220" height="300" alt="女優写真" />
    </td>
  </tr>
</table>
</body></html>
"""


def test_flag_icon_skipped():
    """The 25×17 flag icon must not be selected as the photo."""
    result = _parse_wiki_ja_html(_FLAG_ICON_HTML, "テスト")
    assert result is not None
    assert result["photo_url"], "expected a photo_url"
    assert "Flag_of_Japan" not in result["photo_url"], (
        f"flag icon was incorrectly selected: {result['photo_url']!r}"
    )


def test_flag_icon_real_photo_selected():
    """The 220×300 portrait should be selected, not the flag."""
    result = _parse_wiki_ja_html(_FLAG_ICON_HTML, "テスト")
    assert result is not None
    assert "ActressPhoto.jpg" in result["photo_url"], (
        f"real portrait not selected: {result['photo_url']!r}"
    )


# ---------------------------------------------------------------------------
# 4. Commons thumb → raw URL (pure string, no network)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("thumb, expected_raw", [
    (
        "//upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Foo.jpg/220px-Foo.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.jpg",
    ),
    (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Fresh_Fes_2024.jpg/220px-Fresh_Fes_2024.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/8/85/Fresh_Fes_2024.jpg",
    ),
    (
        "//upload.wikimedia.org/wikipedia/commons/thumb/d/d7/SomeActress.jpg/180px-SomeActress.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/d/d7/SomeActress.jpg",
    ),
])
def test_commons_thumb_to_raw_string_only(thumb, expected_raw):
    """URL transformation must produce the correct raw URL purely by string ops."""
    result = _commons_thumb_to_raw(thumb)
    assert result == expected_raw, f"expected {expected_raw!r}, got {result!r}"


def test_commons_thumb_to_raw_no_network():
    """_commons_thumb_to_raw must not make any HTTP calls."""
    thumb = "//upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Foo.jpg/220px-Foo.jpg"
    with patch("requests.get", side_effect=RuntimeError("no network allowed")):
        # Should NOT raise — pure string operation
        result = _commons_thumb_to_raw(thumb)
    assert result == "https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.jpg"


def test_commons_thumb_to_raw_passthrough():
    """Non-thumb URLs are returned unchanged."""
    url = "https://example.com/image.jpg"
    assert _commons_thumb_to_raw(url) == url


# ---------------------------------------------------------------------------
# 5. photo_needs_resize: True (covered by parametrized fixture tests above,
#    but add an explicit standalone test for the flag)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not FIXTURE_NAMES, reason="HTML fixtures not captured")
def test_photo_needs_resize_present_in_parsed_fixture():
    """At least one real fixture must have photo_needs_resize=True."""
    found = False
    for name in FIXTURE_NAMES:
        html = _load_fixture(name)
        result = _parse_wiki_ja_html(html, name)
        if result and result.get("photo_needs_resize") is True:
            found = True
            break
    assert found, "photo_needs_resize=True not found in any fixture"


# ---------------------------------------------------------------------------
# 6. Not found / empty / non-infobox HTML → None or graceful
# ---------------------------------------------------------------------------

def test_empty_html_returns_none():
    """Empty HTML string should return None (no infobox)."""
    result = _parse_wiki_ja_html("", "テスト")
    assert result is None


def test_no_infobox_returns_none():
    """HTML with no infobox table should return None."""
    html = "<html><body><p>No infobox here</p></body></html>"
    result = _parse_wiki_ja_html(html, "テスト")
    assert result is None


def test_scrape_wiki_ja_404_returns_none():
    """scrape_wiki_ja should return None on HTTP 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        result = scrape_wiki_ja("存在しない女優")
    assert result is None


def test_scrape_wiki_ja_timeout_returns_none():
    """scrape_wiki_ja should return None on timeout."""
    import requests as req_module
    with patch("requests.get", side_effect=req_module.exceptions.Timeout()):
        result = scrape_wiki_ja("タイムアウト")
    assert result is None


# ---------------------------------------------------------------------------
# 7. Non-AV actress graceful fallback (希島あいり)
# ---------------------------------------------------------------------------

def test_kijima_airi_graceful_fallback():
    """希島あいり has singer/talent tags but her infobox is still parseable.
    Must not crash and should yield partial fields."""
    name = "希島あいり"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip(f"fixture not found: {fixture_path}")

    html = fixture_path.read_text(encoding="utf-8")
    result = _parse_wiki_ja_html(html, name)

    # Must not crash → result should be a dict (not None)
    assert result is not None, "希島あいり parse crashed (returned None)"

    # Should parse birth date correctly
    assert result.get("birth") == "1988-12-24", (
        f"unexpected birth for 希島あいり: {result.get('birth')!r}"
    )

    # No photo (she has no infobox portrait on ja.wikipedia.org)
    # photo_url may be empty — that's fine, should not raise
    assert "photo_url" in result, "photo_url key missing"


# ---------------------------------------------------------------------------
# 8. Bug 1 fix — parser returns None when infobox has no meaningful text fields
# ---------------------------------------------------------------------------

def test_parse_wiki_ja_html_no_meaningful_fields_returns_none():
    """Parser must return None when infobox has no text fields (fix for Bug 1).
    Labels 職業 and 所属 are not in the elif chain, so no meaningful field is set."""
    html = """
    <html><body>
    <table class="infobox biography">
      <tr><th>職業</th><td>歌手</td></tr>
      <tr><th>所属</th><td>フリー</td></tr>
    </table>
    </body></html>
    """
    result = _parse_wiki_ja_html(html, "テスト女優")
    assert result is None, \
        "parser must return None when no text fields (birth/height/BWH/hometown/etc.) extracted"


def test_parse_wiki_ja_html_photo_only_returns_none():
    """Infobox with only a photo (no text fields) must return None.
    photo_url alone is not sufficient — it could be a wrong-person image."""
    html = """
    <html><body>
    <table class="infobox biography">
      <tr>
        <td>
          <img src="//upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Photo.jpg/220px-Photo.jpg"
               width="220" height="300" />
        </td>
      </tr>
    </table>
    </body></html>
    """
    result = _parse_wiki_ja_html(html, "テスト女優")
    assert result is None, \
        "parser must return None when only photo is found (no text profile fields)"


# ---------------------------------------------------------------------------
# 9. Bug 3 fix — standalone 身長 row (without 体重) still yields height
# ---------------------------------------------------------------------------

_STANDALONE_HEIGHT_HTML = """
<html><body>
<table class="infobox biography">
  <tr><th>身長</th><td>160 cm</td></tr>
  <tr><th>生年月日</th><td>1998年3月31日</td></tr>
</table>
</body></html>
"""


def test_standalone_shincho_row_parses_height():
    """Bug 3: standalone 身長 row (without 体重) must still yield height."""
    result = _parse_wiki_ja_html(_STANDALONE_HEIGHT_HTML, "テスト女優")
    assert result is not None, "expected non-None result for standalone 身長 row"
    assert result["height"] == "160cm", \
        f"expected '160cm' from standalone 身長 row, got {result.get('height')!r}"
    assert result["birth"] == "1998-03-31"


def test_standalone_shincho_combined_row_still_works():
    """Existing combined 身長 / 体重 row must still parse height correctly."""
    html = """
    <html><body>
    <table class="infobox biography">
      <tr><th>身長 / 体重</th><td>157 cm / 45 kg</td></tr>
      <tr><th>生年月日</th><td>1998年3月31日</td></tr>
    </table>
    </body></html>
    """
    result = _parse_wiki_ja_html(html, "テスト女優")
    assert result is not None
    assert result["height"] == "157cm", \
        f"expected '157cm' from combined 身長/体重 row, got {result.get('height')!r}"


# ---------------------------------------------------------------------------
# 10. C3 — no photo HTTP in the scraper module
# ---------------------------------------------------------------------------

def test_scrape_wiki_ja_no_photo_download():
    """
    When scrape_wiki_ja is called with valid HTML, it must NOT call requests.get
    with the photo_url.  Photo handling is string-only (C3 constraint).
    """
    name = "明里つむぎ"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip("fixture not available")

    html = fixture_path.read_text(encoding="utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html

    call_urls = []

    def fake_get(url, **kwargs):
        call_urls.append(url)
        return mock_resp

    with patch("requests.get", side_effect=fake_get):
        result = scrape_wiki_ja(name)

    assert result is not None
    photo_url = result.get("photo_url", "")
    # Ensure requests.get was only called once (for the Wikipedia page itself),
    # never for the photo URL.
    assert len(call_urls) == 1, f"expected 1 HTTP call, got {len(call_urls)}: {call_urls}"
    if photo_url:
        assert photo_url not in call_urls, (
            f"photo_url was fetched (C3 violation): {photo_url}"
        )


# ---------------------------------------------------------------------------
# 11. T7.2 — 別名 field + photo alt guard (Finding A + B from T6-wiki-ja.md)
# ---------------------------------------------------------------------------

def test_parses_bieimei_row_momonogi_kana():
    """Finding A: 桃乃木かな 別名 = 松嶋真麻（單名）"""
    name = "桃乃木かな"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip(f"fixture not found: {fixture_path}")
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    assert result.get("other_names") == ["松嶋真麻"], (
        f"expected ['松嶋真麻'], got {result.get('other_names')!r}"
    )


def test_parses_bieimei_row_kijima_airi_multiple():
    """Finding A/E: 希島あいり 別名 = '希岛爱理 、希島愛理(中華圏名)'
    Japanese comma 分隔、不清洗 (中華圏名) 括號"""
    name = "希島あいり"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip(f"fixture not found: {fixture_path}")
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    other = result.get("other_names")
    assert isinstance(other, list)
    assert len(other) >= 2, f"expected >=2 names, got {other!r}"
    assert "希岛爱理" in other, f"missing 希岛爱理 in {other!r}"
    # 括號說明不清洗 — 第二個元素仍含 (中華圏名)
    assert any("希島愛理" in s for s in other), f"missing 希島愛理 in {other!r}"


def test_no_bieimei_row_returns_empty_list():
    """明里つむぎ 無 別名 row → other_names == []"""
    name = "明里つむぎ"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip(f"fixture not found: {fixture_path}")
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    assert result.get("other_names") == [], (
        f"expected [], got {result.get('other_names')!r}"
    )


def test_photo_alt_guard_prefers_human_photo_suzumori_remu():
    """Finding B: 涼森れむ infobox 有 [220 alt='(2025年5月撮影)' 人像]
    + [180 alt='' Remu_sign.jpg]，加 alt guard 後仍選人像"""
    name = "涼森れむ"
    fixture_path = FIXTURE_DIR / f"wiki_ja_{name}.html"
    if not fixture_path.exists():
        pytest.skip(f"fixture not found: {fixture_path}")
    html = _load_fixture(name)
    result = _parse_wiki_ja_html(html, name)
    assert result is not None
    photo_url = result.get("photo_url", "")
    assert photo_url, "expected a photo_url"
    # 不是簽名
    assert "Remu_sign" not in photo_url, f"signature selected: {photo_url!r}"
    assert "sign" not in photo_url.lower(), f"signature-like URL: {photo_url!r}"
    # 是人像
    assert "Trend_Girls" in photo_url, f"human photo not selected: {photo_url!r}"
