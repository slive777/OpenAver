"""
test_javbus_scraper.py - JavBus 爬蟲單元測試（BC-1 ~ BC-13）

測試策略：
- 全 mock，不連網
- Mock requests.Session.get 回傳 inline HTML fixture
- rate_limit 也 mock 掉（避免 sleep）
"""

import pytest
from unittest.mock import patch, MagicMock
import requests

# ============================================================
# HTML Fixtures
# ============================================================

ZH_TW_HTML = """\
<html><body>
<h3>SNOS-143 美人OLは絶倫上司に何度も中出しされ孕まされる</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143 美人OL..." src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">導演:</span> <a href="/director/xxx">イナバール</a></p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">發行商:</span> <a href="/label/xxx">エスワン ナンバーワンスタイル</a></p>
  <p><span class="header">類別:</span></p>
  <p>
    <a href="/genre/1">姐妹</a>
    <a href="/genre/2">口交</a>
    <a href="/genre/3">出軌</a>
  </p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
<div id="sample-waterfall">
  <a href="/pics/sample/snos143-1.jpg"><img src="thumb1.jpg"></a>
  <a href="/pics/sample/snos143-2.jpg"><img src="thumb2.jpg"></a>
</div>
</body></html>
"""

JA_HTML = """\
<html><body>
<h3>SNOS-143 美人OLは絶倫上司に何度も中出しされ孕まされる</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143 美人OL..." src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">品番:</span> <a href="/ja/SNOS-143">SNOS-143</a></p>
  <p><span class="header">発売日:</span> 2025-03-20</p>
  <p><span class="header">収録時間:</span> 120分</p>
  <p><span class="header">監督:</span> <a href="/ja/director/xxx">イナバール</a></p>
  <p><span class="header">メーカー:</span> <a href="/ja/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">レーベル:</span> <a href="/ja/label/xxx">エスワン ナンバーワンスタイル</a></p>
  <p><span class="header">ジャンル:</span></p>
  <p>
    <a href="/ja/genre/1">フェラ</a>
    <a href="/ja/genre/2">寝取り</a>
    <a href="/ja/genre/3">中出し</a>
  </p>
  <p><span class="header">出演者:</span>
    <a href="/ja/star/abc">渚あいり</a>
  </p>
</div>
<div id="sample-waterfall">
  <a href="/pics/sample/snos143-1.jpg"><img src="thumb1.jpg"></a>
</div>
</body></html>
"""

EN_HTML = """\
<html><body>
<h3>SNOS-143 Beautiful Office Lady</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143 Beautiful Office Lady" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">ID:</span> <a href="/en/SNOS-143">SNOS-143</a></p>
  <p><span class="header">Release Date:</span> 2025-03-20</p>
  <p><span class="header">Length:</span> 120 min(s)</p>
  <p><span class="header">Director:</span> <a href="/en/director/xxx">Inabar</a></p>
  <p><span class="header">Studio:</span> <a href="/en/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">Label:</span> <a href="/en/label/xxx">S1 NO.1 STYLE Label</a></p>
  <p><span class="header">Genre:</span></p>
  <p>
    <a href="/en/genre/1">Blowjob</a>
    <a href="/en/genre/2">Cheating Wife</a>
    <a href="/en/genre/3">Creampie</a>
  </p>
  <p><span class="header">JAV Idols:</span>
    <a href="/en/star/abc">Airi Nagisa</a>
  </p>
</div>
<div id="sample-waterfall">
  <a href="/pics/sample/snos143-1.jpg"><img src="thumb1.jpg"></a>
</div>
</body></html>
"""

# HTML without director
NO_DIRECTOR_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">類別:</span></p>
  <p>
    <a href="/genre/1">姐妹</a>
  </p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
</body></html>
"""

# HTML with series
WITH_SERIES_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">系列:</span> <a href="/series/xxx">美人OLシリーズ</a></p>
  <p><span class="header">類別:</span></p>
  <p>
    <a href="/genre/1">姐妹</a>
  </p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
</body></html>
"""

# HTML with relative cover URL
RELATIVE_COVER_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">類別:</span></p>
  <p><a href="/genre/1">姐妹</a></p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
</body></html>
"""

# HTML without sample images
NO_SAMPLES_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">類別:</span></p>
  <p><a href="/genre/1">姐妹</a></p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
</body></html>
"""

# HTML with duplicate actresses
DUPLICATE_ACTRESS_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">類別:</span></p>
  <p><a href="/genre/1">姐妹</a></p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
    <a href="/star/abc">渚あいり</a>
    <a href="/star/def">桃乃木かな</a>
  </p>
</div>
</body></html>
"""

# HTML with no duration
NO_DURATION_HTML = """\
<html><body>
<h3>SNOS-143 タイトル</h3>
<a class="bigImage" href="https://pics.javbus.com/cover/snos143pl.jpg">
  <img title="SNOS-143" src="thumb.jpg">
</a>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> <a href="/SNOS-143">SNOS-143</a></p>
  <p><span class="header">發行日期:</span> 2025-03-20</p>
  <p><span class="header">製作商:</span> <a href="/studio/xxx">S1 NO.1 STYLE</a></p>
  <p><span class="header">類別:</span></p>
  <p><a href="/genre/1">姐妹</a></p>
  <p><span class="header">演員:</span>
    <a href="/star/abc">渚あいり</a>
  </p>
</div>
</body></html>
"""


# ============================================================
# Helper: build a mock response
# ============================================================

def make_response(html: str, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    return resp


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def scraper_zh():
    """zh-tw lang scraper with rate_limit mocked."""
    from core.scrapers.javbus import JavBusScraper
    with patch("core.scrapers.javbus.rate_limit"):
        scraper = JavBusScraper(lang="zh-tw")
        yield scraper


@pytest.fixture
def scraper_ja():
    from core.scrapers.javbus import JavBusScraper
    with patch("core.scrapers.javbus.rate_limit"):
        scraper = JavBusScraper(lang="ja")
        yield scraper


@pytest.fixture
def scraper_en():
    from core.scrapers.javbus import JavBusScraper
    with patch("core.scrapers.javbus.rate_limit"):
        scraper = JavBusScraper(lang="en")
        yield scraper


# ============================================================
# BC-1: 三語言 tags 不同
# ============================================================

class TestBC1Tags:
    """BC-1: tags 在各語言下正確解析"""

    def test_parse_zh_tw_tags(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert "姐妹" in video.tags
        assert "口交" in video.tags
        assert "出軌" in video.tags

    def test_parse_ja_tags(self, scraper_ja):
        scraper_ja._session.get = MagicMock(return_value=make_response(JA_HTML))
        video = scraper_ja.search("SNOS-143")
        assert video is not None
        assert "フェラ" in video.tags
        assert "寝取り" in video.tags
        assert "中出し" in video.tags

    def test_parse_en_tags(self, scraper_en):
        scraper_en._session.get = MagicMock(return_value=make_response(EN_HTML))
        video = scraper_en.search("SNOS-143")
        assert video is not None
        assert "Blowjob" in video.tags
        assert "Cheating Wife" in video.tags
        assert "Creampie" in video.tags


# ============================================================
# BC-2: maker 非空
# ============================================================

class TestBC2Maker:
    def test_maker_not_empty(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.maker == "S1 NO.1 STYLE"


# ============================================================
# BC-3: director 有/無
# ============================================================

class TestBC3Director:
    def test_director_present(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.director == "イナバール"

    def test_director_absent(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(NO_DIRECTOR_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.director == ""


# ============================================================
# BC-4: duration 解析
# ============================================================

class TestBC4Duration:
    def test_duration_parsed_as_int(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert isinstance(video.duration, int)
        assert video.duration == 120

    def test_duration_missing(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(NO_DURATION_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.duration is None


# ============================================================
# BC-5: series Optional
# ============================================================

class TestBC5Series:
    def test_series_present(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(WITH_SERIES_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.series == "美人OLシリーズ"

    def test_series_absent(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.series == ""


# ============================================================
# BC-6: cover URL 相對/絕對路徑
# ============================================================

class TestBC6CoverUrl:
    def test_cover_url_absolute_path(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.cover_url == "https://pics.javbus.com/cover/snos143pl.jpg"

    def test_cover_url_relative_path(self, scraper_zh):
        """相對路徑應自動加上 BASE_URL"""
        scraper_zh._session.get = MagicMock(return_value=make_response(RELATIVE_COVER_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.cover_url.startswith("https://www.javbus.com")
        assert "/cover/snos143pl.jpg" in video.cover_url


# ============================================================
# BC-7: sample_images 空
# ============================================================

class TestBC7SampleImages:
    def test_sample_images_populated(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert len(video.sample_images) == 2

    def test_sample_images_empty(self, scraper_zh):
        """沒有 sample-waterfall 時回傳空 list"""
        scraper_zh._session.get = MagicMock(return_value=make_response(NO_SAMPLES_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        assert video.sample_images == []


# ============================================================
# BC-8: HTTP 404 → None
# ============================================================

class TestBC8Http404:
    def test_search_404_returns_none(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response("", status_code=404))
        result = scraper_zh.search("SNOS-143")
        assert result is None


# ============================================================
# BC-9: timeout → TimeoutError
# ============================================================

class TestBC9Timeout:
    def test_search_timeout(self, scraper_zh):
        scraper_zh._session.get = MagicMock(side_effect=requests.Timeout())
        with pytest.raises(TimeoutError):
            scraper_zh.search("SNOS-143")


# ============================================================
# BC-10: invalid number → ValueError
# ============================================================

class TestBC10InvalidNumber:
    def test_search_invalid_number(self, scraper_zh):
        with pytest.raises(ValueError):
            scraper_zh.search("not-a-valid-number-!!!")


# ============================================================
# BC-11: 演員去重
# ============================================================

class TestBC11ActressDedup:
    def test_actresses_dedup(self, scraper_zh):
        scraper_zh._session.get = MagicMock(return_value=make_response(DUPLICATE_ACTRESS_HTML))
        video = scraper_zh.search("SNOS-143")
        assert video is not None
        names = [a.name for a in video.actresses]
        # 渚あいり 出現兩次但只應保留一個
        assert names.count("渚あいり") == 1
        assert "桃乃木かな" in names
        assert len(names) == 2


# ============================================================
# BC-12: 英文演員名（en scraper 正常解析）
# ============================================================

class TestBC12EnActress:
    def test_en_actress_name(self, scraper_en):
        scraper_en._session.get = MagicMock(return_value=make_response(EN_HTML))
        video = scraper_en.search("SNOS-143")
        assert video is not None
        names = [a.name for a in video.actresses]
        assert "Airi Nagisa" in names


# ============================================================
# BC-13: 未知 lang fallback 到 zh-tw
# ============================================================

class TestBC13UnknownLang:
    def test_unknown_lang_fallback(self):
        """未知 lang 應 fallback 到 zh-tw labels，不應拋例外"""
        from core.scrapers.javbus import JavBusScraper
        with patch("core.scrapers.javbus.rate_limit"):
            scraper = JavBusScraper(lang="fr")  # 不支援的語言
            scraper._session.get = MagicMock(return_value=make_response(ZH_TW_HTML))
            # 應 fallback 到 zh-tw labels，能正確解析
            video = scraper.search("SNOS-143")
            # 不應拋例外，也能解析出 maker（zh-tw labels）
            assert video is not None
            assert video.maker == "S1 NO.1 STYLE"


# ============================================================
# search_by_keyword: 永遠回傳空 list
# ============================================================

class TestSearchByKeyword:
    def test_search_by_keyword_returns_empty_list(self, scraper_zh):
        result = scraper_zh.search_by_keyword("渚あいり")
        assert result == []

    def test_search_by_keyword_with_limit(self, scraper_zh):
        result = scraper_zh.search_by_keyword("test", limit=10)
        assert isinstance(result, list)
        assert len(result) == 0


# ============================================================
# source name
# ============================================================

class TestSourceName:
    def test_source_name(self, scraper_zh):
        assert scraper_zh.source_name == "javbus"
