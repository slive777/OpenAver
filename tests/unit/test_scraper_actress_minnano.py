"""
Unit tests for core.scrapers.actress.minnano_av

All tests are pure — no network IO.  Live fixtures are loaded from
tests/fixtures/actress/minnano_av_*.html (captured once at T1 time).

Test coverage:
1. All 5 fixtures parse successfully (name_ja, birth, BWH basics)
2. Alias tag-pollution regression — (着エロ) / (ハード) / (コスプレ) stripped
3. 302 redirect follow — mock Session.get with history stub
4. Title-match hit verification — miss returns None
5. Not-found (empty/garbage HTML) returns None, no exception
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.scrapers.actress.minnano_av import _parse_minnano_html, scrape_minnano_av

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "actress"

# Actress name → known fixture values for smoke-level assertions
FIXTURE_EXPECTATIONS = {
    "明里つむぎ": {"birth": "1998-03-31", "hometown": "神奈川県", "bust": "80cm"},
    "希島あいり": {"birth": "1988-12-24", "hometown": "東京都", "bust": "77cm"},
    "天馬ゆい":   {"birth": "1997-12-03", "hometown": "青森県",  "bust": "83cm"},
    "桃乃木かな": {"birth": "1994-10-20", "hometown": "東京都",  "bust": "86cm"},
    "涼森れむ":   {"birth": "1997-12-03", "hometown": "三重県",  "bust": "87cm"},
}

# HTML fixtures are not committed (tests/fixtures/actress/*.html is in .gitignore).
# To capture locally for fixture-based tests, run from repo root:
#   source venv/bin/activate && python -c "
#   import requests, urllib.parse
#   from pathlib import Path
#   HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
#   for n in ['明里つむぎ','希島あいり','天馬ゆい','桃乃木かな','涼森れむ']:
#       url = f'https://www.minnano-av.com/search_result.php?search_scope=actress&search_word={urllib.parse.quote(n)}'
#       r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
#       Path(f'tests/fixtures/actress/minnano_av_{n}.html').write_text(r.text, encoding='utf-8')
#   "
_FIXTURES_AVAILABLE = all(
    (FIXTURE_DIR / f"minnano_av_{name}.html").exists()
    for name in FIXTURE_EXPECTATIONS
)


# ===========================================================================
# 1. All 5 fixtures parse successfully
# ===========================================================================

@pytest.mark.skipif(
    not _FIXTURES_AVAILABLE,
    reason="HTML fixtures not captured (see capture one-liner in module docstring)",
)
class TestFixtureParsing:
    """Each fixture must parse without error and return expected core fields."""

    @pytest.mark.parametrize("name,expected", FIXTURE_EXPECTATIONS.items())
    def test_fixture_parses_ok(self, name, expected):
        fixture = FIXTURE_DIR / f"minnano_av_{name}.html"
        assert fixture.exists(), f"Fixture missing: {fixture}"

        html = fixture.read_text(encoding="utf-8")
        result = _parse_minnano_html(html, name)

        assert result is not None, f"parse returned None for {name}"
        assert result["name_ja"] == name, f"name_ja mismatch for {name}"
        assert result["birth"] == expected["birth"], f"birth mismatch for {name}"
        assert result["hometown"] == expected["hometown"], f"hometown mismatch for {name}"
        assert result["bust"] == expected["bust"], f"bust mismatch for {name}"

    def test_all_fixtures_have_photo_url(self):
        for name in FIXTURE_EXPECTATIONS:
            fixture = FIXTURE_DIR / f"minnano_av_{name}.html"
            html = fixture.read_text(encoding="utf-8")
            result = _parse_minnano_html(html, name)
            assert result is not None
            assert result["photo_url"], f"photo_url empty for {name}"

    def test_tenma_yui_has_9_aliases(self):
        """天馬ゆい has 9 documented aliases."""
        name = "天馬ゆい"
        html = (FIXTURE_DIR / f"minnano_av_{name}.html").read_text(encoding="utf-8")
        result = _parse_minnano_html(html, name)
        assert result is not None
        assert len(result["aliases"]) == 9, f"expected 9 aliases, got {len(result['aliases'])}"

    def test_tenma_yui_alias_names_clean(self):
        """Alias ja names must not contain tag suffixes like 着エロ."""
        name = "天馬ゆい"
        html = (FIXTURE_DIR / f"minnano_av_{name}.html").read_text(encoding="utf-8")
        result = _parse_minnano_html(html, name)
        assert result is not None
        for alias in result["aliases"]:
            assert "着エロ" not in alias["ja"], f"tag leaked into ja: {alias}"
            assert "ハード" not in alias["ja"], f"tag leaked into ja: {alias}"
            # hiragana must be clean hiragana (no tag text leaking)
            assert "着エロ" not in alias["hiragana"], f"tag leaked into hiragana: {alias}"

    def test_tags_are_list(self):
        """tags field must be a list of strings."""
        name = "天馬ゆい"
        html = (FIXTURE_DIR / f"minnano_av_{name}.html").read_text(encoding="utf-8")
        result = _parse_minnano_html(html, name)
        assert result is not None
        assert isinstance(result["tags"], list)
        assert len(result["tags"]) > 0


# ===========================================================================
# 2. Alias tag pollution regression
# ===========================================================================

class TestAliasTagPollutionRegression:
    """Synthetic HTML with (着エロ) / (ハード) / (コスプレ) scene-tag suffixes."""

    # Use distinct alias names that do NOT contain the tag strings themselves.
    # "田中あ(着エロ)" → ja="田中あ",  "鈴木べ(ハード)" → ja="鈴木べ", etc.
    SYNTHETIC_HTML = """\
<html><head><title>テスト女優（てすとじょゆう）AV女優プロフィール - みんなのAV.com</title></head>
<body>
<table>
  <tr><td>テスト女優 （てすとじょゆう / Test Joyuu）</td></tr>
  <tr><td>別名 田中あ(着エロ) （たなかあ / Tanaka A）</td></tr>
  <tr><td>別名 鈴木べ(ハード) （すずきべ / Suzuki B）</td></tr>
  <tr><td>別名 佐藤し(コスプレ) （さとうし / Sato C）</td></tr>
  <tr><td>別名 清潔名前 （よみがなd / Romaji D）</td></tr>
  <tr><td>生年月日 1990年01月15日 （現在 35歳 ）やぎ座</td></tr>
  <tr><td>サイズ T165 / B90( Gカップ ) / W60 / H88</td></tr>
  <tr><td>タグ 巨乳 美人</td></tr>
</table>
</body></html>"""

    def test_tag_suffixes_not_in_alias_ja(self):
        """Parenthetical scene-tags must be stripped from ja field.
        e.g. "田中あ(着エロ)" → ja="田中あ" (parenthetical suffix stripped)
        """
        result = _parse_minnano_html(self.SYNTHETIC_HTML, "テスト女優")
        assert result is not None
        for alias in result["aliases"]:
            # The parenthetical form (tag) must not be present in ja
            assert "(着エロ)" not in alias["ja"]
            assert "(ハード)" not in alias["ja"]
            assert "(コスプレ)" not in alias["ja"]
            assert "着エロ" not in alias["ja"]
            assert "ハード" not in alias["ja"]
            assert "コスプレ" not in alias["ja"]

    def test_tag_suffixes_not_in_hiragana(self):
        result = _parse_minnano_html(self.SYNTHETIC_HTML, "テスト女優")
        assert result is not None
        for alias in result["aliases"]:
            assert "着エロ" not in alias["hiragana"]
            assert "ハード" not in alias["hiragana"]
            assert "コスプレ" not in alias["hiragana"]

    def test_clean_alias_still_parsed(self):
        """Alias without tag suffix should parse correctly."""
        result = _parse_minnano_html(self.SYNTHETIC_HTML, "テスト女優")
        assert result is not None
        clean = next((a for a in result["aliases"] if a["ja"] == "清潔名前"), None)
        assert clean is not None, "clean alias not found"
        assert clean["hiragana"] == "よみがなd"
        assert clean["romaji"] == "Romaji D"

    def test_polluted_aliases_have_correct_ja_name(self):
        """Tag-polluted aliases should have clean ja name (suffix stripped)."""
        result = _parse_minnano_html(self.SYNTHETIC_HTML, "テスト女優")
        assert result is not None
        alias_jas = [a["ja"] for a in result["aliases"]]
        assert "田中あ" in alias_jas
        assert "鈴木べ" in alias_jas
        assert "佐藤し" in alias_jas

    def test_no_current_age_on_page_field(self):
        """current_age_on_page must NOT be in the result dict (TD-1 fix)."""
        result = _parse_minnano_html(self.SYNTHETIC_HTML, "テスト女優")
        assert result is not None
        assert "current_age_on_page" not in result, (
            "current_age_on_page field should be absent (TD-1: use birth instead)"
        )


# ===========================================================================
# 3. 302 redirect follow
# ===========================================================================

class TestRedirectFollow:
    """scrape_minnano_av must follow 302 redirects transparently."""

    MOCK_HTML = """\
<html><head><title>明里つむぎ（あかりつむぎ）AV女優プロフィール - みんなのAV.com</title></head>
<body>
<table>
  <tr><td>明里つむぎ （あかりつむぎ / Akari Tsumugi）</td></tr>
  <tr><td>生年月日 1998年03月31日 （現在 28歳 ）おひつじ座</td></tr>
  <tr><td>サイズ T157 / B80( Bカップ ) / W58 / H83</td></tr>
  <tr><td>血液型 O型</td></tr>
  <tr><td>出身地 神奈川県</td></tr>
</table>
<meta property="og:image" content="https://www.minnano-av.com/p_actress_125_125/016/273627.jpg?new"/>
</body></html>"""

    def test_redirect_followed_returns_result(self):
        """Session.get with a redirect history (302→200) should parse correctly."""
        # Build a mock response that looks like it came via redirect
        redirect_resp = MagicMock()
        redirect_resp.status_code = 302
        redirect_resp.url = "https://www.minnano-av.com/search_result.php?search_scope=actress&search_word=%E6%98%8E%E9%87%8C%E3%81%A4%E3%82%80%E3%81%8E"

        final_resp = MagicMock()
        final_resp.status_code = 200
        final_resp.text = self.MOCK_HTML
        final_resp.url = "https://www.minnano-av.com/actress273627.html"
        final_resp.history = [redirect_resp]
        final_resp.raise_for_status.return_value = None

        with patch("core.scrapers.actress.minnano_av.requests.Session") as MockSession:
            mock_session = MagicMock()
            MockSession.return_value = mock_session
            mock_session.get.return_value = final_resp

            result = scrape_minnano_av("明里つむぎ")

        assert result is not None
        assert result["name_ja"] == "明里つむぎ"
        assert result["birth"] == "1998-03-31"
        # Confirm a redirect was recorded in the fake response
        assert len(final_resp.history) == 1
        assert final_resp.history[0].status_code == 302


# ===========================================================================
# 4. Title match hit verification
# ===========================================================================

class TestTitleMatchVerification:
    """When title does not contain queried name, _parse_minnano_html returns None."""

    WRONG_TITLE_HTML = """\
<html><head><title>別の女優（べつのじょゆう）AV女優プロフィール - みんなのAV.com</title></head>
<body>
<table>
  <tr><td>別の女優 （べつのじょゆう / Betsu No Joyuu）</td></tr>
  <tr><td>生年月日 1990年05月01日 （現在 35歳 ）おうし座</td></tr>
</table>
</body></html>"""

    def test_miss_when_name_not_in_title(self):
        """Queried name is not in page title → return None (miss signal)."""
        result = _parse_minnano_html(self.WRONG_TITLE_HTML, "探している女優")
        assert result is None

    def test_hit_when_name_in_title(self):
        """Queried name is in page title → return parsed dict."""
        result = _parse_minnano_html(self.WRONG_TITLE_HTML, "別の女優")
        assert result is not None
        assert result["name_ja"] == "別の女優"


# ===========================================================================
# 5. Not found / garbage HTML returns None, no exception
# ===========================================================================

class TestNotFoundBehavior:
    """Edge cases: empty HTML, garbage, missing table."""

    def test_empty_string_returns_none(self):
        assert _parse_minnano_html("", "誰でも") is None

    def test_none_like_blank_returns_none(self):
        assert _parse_minnano_html("   ", "誰でも") is None

    def test_garbage_html_returns_none(self):
        result = _parse_minnano_html(
            "<html><head><title>404 Not Found</title></head><body>page not found</body></html>",
            "誰でも",
        )
        assert result is None

    def test_title_present_but_no_profile_table(self):
        """Title matches but no 生年月日 table — parser must return None gracefully."""
        html = """\
<html><head><title>誰でも（だれでも）AV女優プロフィール - みんなのAV.com</title></head>
<body><p>no profile table here</p></body></html>"""
        result = _parse_minnano_html(html, "誰でも")
        assert result is None

    def test_no_exception_on_malformed_html(self):
        """Malformed/truncated HTML must not raise — just return None or partial dict."""
        malformed = "<html><head><title>誰でも（だれでも）"
        try:
            result = _parse_minnano_html(malformed, "誰でも")
            # either None or a dict with empty fields is acceptable
            if result is not None:
                assert isinstance(result, dict)
        except Exception as exc:
            pytest.fail(f"Exception raised on malformed HTML: {exc}")
