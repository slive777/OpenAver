"""
test_javdb_scraper.py - JavDB 爬蟲單元測試（TASK-73c-T3）

測試策略：
- 全 mock，不連網，不需 curl_cffi
- patch scraper._get_html 回傳 HTML fixture 或 inline HTML
- rate_limit 也 mock 掉（避免 sleep）

fixture 實際解析值（73b T2 落檔）：
  search fixture: SONE-103 → /v/Ww9zN8
  detail fixture:
    cover src = https://c0.jdbstatic.com/covers/ww/Ww9zN8.jpg（非 ps.jpg）
    女優: つばさ舞  (sibling classes: ['symbol', 'female'])
    男優: 結城結弦  (sibling classes: ['symbol', 'male'])  → 應被過濾
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ============================================================
# Fixture HTML 載入（file-based fixtures）
# ============================================================

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "scrapers"

SEARCH_HTML = (_FIXTURE_DIR / "javdb_SONE-103_search.html").read_text(encoding="utf-8")
DETAIL_HTML = (_FIXTURE_DIR / "javdb_SONE-103.html").read_text(encoding="utf-8")

# ============================================================
# Inline HTML — no-match search（用一個不匹配的番號結果頁）
# ============================================================

NO_MATCH_SEARCH_HTML = """\
<html><body>
<div class="movie-list">
  <div class="item">
    <div class="video-title"><strong>FONE-103</strong></div>
    <a href="/v/qbgGP"></a>
  </div>
</div>
</body></html>
"""

# ============================================================
# Inline HTML — cover 含 ps.jpg（觸發 ps→pl 升級）
# ============================================================

PS_COVER_SEARCH_HTML = """\
<html><body>
<div class="movie-list">
  <div class="item">
    <div class="video-title"><strong>SONE-103</strong></div>
    <a href="/v/Ww9zN8"></a>
  </div>
</div>
</body></html>
"""

PS_COVER_DETAIL_HTML = """\
<html><body>
<div class="video-cover">
  <img src="https://pics.example.com/covers/ps.jpg">
</div>
<div class="panel-block">
  <strong>演員:</strong>
  <div class="value">
    <a href="/actors/1">テスト女優</a>
    <span class="symbol female">♀</span>
  </div>
</div>
</body></html>
"""

# ============================================================
# Inline HTML — 評分 panel（TASK-93-T7）
# ============================================================

RATING_SEARCH_HTML = """\
<html><body>
<div class="movie-list">
  <div class="item">
    <div class="video-title"><strong>SONE-103</strong></div>
    <a href="/v/Ww9zN8"></a>
  </div>
</div>
</body></html>
"""

RATING_DETAIL_HTML = """\
<html><body>
<h2 class="title is-4">SONE-103 テストタイトル</h2>
<div class="video-cover">
  <img src="https://pics.example.com/covers/rating.jpg">
</div>
<div class="panel-block">
  <strong>評分:</strong>
  <div class="value">4.46分, 由2124人評価</div>
</div>
</body></html>
"""


# ============================================================
# Helper
# ============================================================

def run_search(scraper, search_html: str, detail_html: str, number: str = "SONE-103"):
    """
    patch _get_html: first call returns search_html, second returns detail_html.
    """
    with patch.object(
        scraper,
        "_get_html",
        side_effect=[search_html, detail_html],
    ):
        return scraper.search(number)


# ============================================================
# pytest Fixture
# ============================================================

@pytest.fixture
def scraper():
    from core.scrapers.javdb import JavDBScraper
    with patch("core.scrapers.javdb.rate_limit"):
        s = JavDBScraper()
        yield s


# ============================================================
# Tests
# ============================================================

class TestJavdbNumberMatch:
    """番號比對：match / no-match"""

    def test_match_returns_video_with_number(self, scraper):
        """search+detail fixture → 非 None，video.number == 'SONE-103'"""
        video = run_search(scraper, SEARCH_HTML, DETAIL_HTML)
        assert video is not None
        assert video.number == "SONE-103"

    def test_no_match_returns_none(self, scraper):
        """搜尋結果僅 FONE-103（不匹配） → 回 None（比對迴圈走完無 match）"""
        video = run_search(scraper, NO_MATCH_SEARCH_HTML, DETAIL_HTML)
        assert video is None


class TestJavdbGenderFilter:
    """性別過濾：男優 sibling class 包含 'male' 且不含 'female' → 排除"""

    def test_actress_only_female(self, scraper):
        """
        fixture 演員 panel 含：
          つばさ舞  sibling=['symbol','female'] → 保留
          結城結弦  sibling=['symbol','male']   → 過濾
        → video.actresses 只有 つばさ舞
        """
        video = run_search(scraper, SEARCH_HTML, DETAIL_HTML)
        assert video is not None
        actress_names = [a.name for a in video.actresses]
        assert "つばさ舞" in actress_names
        assert "結城結弦" not in actress_names


class TestJavdbCoverUpgrade:
    """ps.jpg → pl.jpg 升級"""

    def test_ps_cover_upgraded_to_pl(self, scraper):
        """inline detail HTML cover src 含 ps.jpg → video.cover_url 含 pl.jpg"""
        video = run_search(scraper, PS_COVER_SEARCH_HTML, PS_COVER_DETAIL_HTML)
        assert video is not None
        assert "pl.jpg" in video.cover_url
        assert "ps.jpg" not in video.cover_url


class TestJavdbValidateGuard:
    """validate_number 失敗 → ValueError"""

    def test_invalid_number_raises(self, scraper):
        """'invalid!!!' → ValueError（不進網路）"""
        with pytest.raises(ValueError):
            scraper.search("invalid!!!")


class TestJavdbGetHtmlNone:
    """_get_html 回 None → search 回 None（空 HTML guard）"""

    def test_get_html_none_returns_none(self, scraper):
        """_get_html side_effect=[None] → search 短路回 None"""
        with patch.object(scraper, "_get_html", side_effect=[None]):
            result = scraper.search("SONE-103")
        assert result is None


class TestJavdbTags:
    """tags 解析：從 fixture SONE-103 detail 頁驗證 video.tags"""

    def test_javdb_tags_from_fixture(self, scraper):
        """
        用 SEARCH_HTML + DETAIL_HTML（javdb_SONE-103.html）餵 run_search，
        驗證 video.tags 為非空 list[str] 且含穩定錨點 tag「戲劇」。

        fixture 行 373–375 含 7 個 tag：戲劇、乳交、巨乳、單體作品、苗條、按摩、妹妹
        只斷言型別 + 非空 + 一個穩定 tag，不斷言完整 list 或順序。
        """
        video = run_search(scraper, SEARCH_HTML, DETAIL_HTML)
        assert video is not None

        # 層 1：型別 + 非空
        assert isinstance(video.tags, list) and len(video.tags) > 0

        # 層 2：每個元素都是 str
        assert all(isinstance(t, str) for t in video.tags)

        # 層 3：含穩定錨點 tag
        assert "戲劇" in video.tags


class TestJavdbRating:
    """評分解析（TASK-93-T7 / D8）：`([0-9.]+)\\s*分` 由 `分` 錨定"""

    def test_rating_parsed_from_panel(self, scraper):
        """
        評分 panel `.value` = `4.46分, 由2124人評価` → video.rating == 4.46。
        關鍵：`分` 錨定，`由2124人` 的 2124 後接 `人` 不誤命中。
        """
        video = run_search(scraper, RATING_SEARCH_HTML, RATING_DETAIL_HTML)
        assert video is not None
        assert video.rating == 4.46
        # 明確驗證未誤抓 2124（人數而非評分）
        assert video.rating != 2124

    def test_rating_none_when_no_panel(self, scraper):
        """
        無評分 panel 的 detail（PS_COVER_DETAIL_HTML）→ video.rating is None，不 raise。
        （既有 javdb_SONE-103.html fixture 本身含真實評分 panel，故另用 inline 無評分頁。）
        """
        video = run_search(scraper, PS_COVER_SEARCH_HTML, PS_COVER_DETAIL_HTML)
        assert video is not None
        assert video.rating is None

    def test_rating_from_real_fixture(self, scraper):
        """真實 javdb_SONE-103.html fixture 含 `4.46分, 由2105人評價` → rating == 4.46（非 2105）"""
        video = run_search(scraper, SEARCH_HTML, DETAIL_HTML)
        assert video is not None
        assert video.rating == 4.46
        assert video.rating != 2105


# ============================================================
# curl_cffi 缺失 / 非 200 診斷 log（spec-97 T5，G-3）
# ============================================================


class TestJavdbCurlCffiDiagnostics:
    """javdb 兩條靜默失敗路徑補 log（零行為變更，只加可觀測性）。

    patch target 一律 core.scrapers.javdb.*（旗標/錯誤物件/_warned 定義端＝使用端
    同模組）；每測例重置 module-level _warned 避免測試間洩漏。
    """

    def test_curl_cffi_unavailable_warns_once_with_error(self, caplog, monkeypatch):
        """curl_cffi 不可用（帶原始例外）→ _get_html 首次呼叫 log 一次 warning 含例外
        訊息；連呼兩次只 log 一次；仍 return None（行為不變）。"""
        import logging
        from core.scrapers import javdb

        fake_exc = ImportError("No package metadata was found for curl_cffi")
        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", False)
        monkeypatch.setattr(javdb, "CURL_CFFI_IMPORT_ERROR", fake_exc)
        monkeypatch.setattr(javdb, "_warned", False)

        s = javdb.JavDBScraper()
        with caplog.at_level(logging.WARNING, logger="OpenAver.core.scrapers.javdb"):
            r1 = s._get_html("https://javdb.com/search?q=SONE-103")
            r2 = s._get_html("https://javdb.com/search?q=SONE-103")

        assert r1 is None and r2 is None  # 行為不變
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, f"應只 warn 一次，實得 {len(warnings)}"
        msg = warnings[0].getMessage()
        assert "curl_cffi" in msg
        assert "No package metadata was found for curl_cffi" in msg  # 含原始例外

    def test_curl_cffi_unavailable_error_none_no_nameerror(self, caplog, monkeypatch):
        """單獨 patch CURL_CFFI_AVAILABLE=False、CURL_CFFI_IMPORT_ERROR 維持 None →
        不 NameError（Codex P2：頂層先初始化），warning 仍發（None 容錯路徑）。"""
        import logging
        from core.scrapers import javdb

        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", False)
        monkeypatch.setattr(javdb, "CURL_CFFI_IMPORT_ERROR", None)
        monkeypatch.setattr(javdb, "_warned", False)

        s = javdb.JavDBScraper()
        with caplog.at_level(logging.WARNING, logger="OpenAver.core.scrapers.javdb"):
            result = s._get_html("https://javdb.com/search?q=SONE-103")

        assert result is None  # 不炸 NameError
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "curl_cffi" in warnings[0].getMessage()

    def test_non_200_logs_status_code(self, caplog, monkeypatch):
        """非 200 response → debug log 含 url + status code；仍 return None。"""
        import logging
        from unittest.mock import MagicMock

        # 本測 patch javdb.curl_requests.get，該屬性僅在 curl_cffi 可 import 時存在
        # （dev venv / CI 為硬依賴恆有）；真缺 curl_cffi 的環境 skip 而非 AttributeError。
        pytest.importorskip("curl_cffi")
        from core.scrapers import javdb

        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", True)
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        monkeypatch.setattr(javdb.curl_requests, "get", lambda *a, **k: mock_resp)

        s = javdb.JavDBScraper()
        with caplog.at_level(logging.DEBUG, logger="OpenAver.core.scrapers.javdb"):
            result = s._get_html("https://javdb.com/v/Ww9zN8")

        assert result is None
        debug_msgs = [r.getMessage() for r in caplog.records]
        assert any("403" in m for m in debug_msgs), f"應 log status code，實得 {debug_msgs}"
