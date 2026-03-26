"""
test_jav321_scraper.py - JAV321 爬蟲單元測試

測試策略：
- 全 mock，不連網
- Mock core.scrapers.jav321.post_html / get_html（因為 jav321.py 用 from .utils import）
- rate_limit 也 mock 掉（避免 sleep）
"""

import pytest
from unittest.mock import patch, MagicMock

# ============================================================
# HTML Fixtures
# ============================================================

FULL_FIELDS_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: <a href="/company/Fitch/1">Fitch</a><br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>収録時間</b>: 147 minutes<br>
      <b>シリーズ</b>: <a href="/series/xxx">究極の爆乳密写シコシコサポート</a><br>
    </div>
  </div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/0"><img src="http://pics.dmm.co.jp//digital/video/jufd00851/jufd00851pl.jpg"></a></p></div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/1"><img src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851jp-1.jpg"></a></p></div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/2"><img src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851jp-2.jpg"></a></p></div>
</div>
</body></html>
"""

NO_SERIES_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: <a href="/company/Fitch/1">Fitch</a><br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>収録時間</b>: 147 minutes<br>
    </div>
  </div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/1"><img src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851jp-1.jpg"></a></p></div>
</div>
</body></html>
"""

NO_DURATION_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: <a href="/company/Fitch/1">Fitch</a><br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>シリーズ</b>: <a href="/series/xxx">究極の爆乳密写シコシコサポート</a><br>
    </div>
  </div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/1"><img src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851jp-1.jpg"></a></p></div>
</div>
</body></html>
"""

NO_SNAPSHOT_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: <a href="/company/Fitch/1">Fitch</a><br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>収録時間</b>: 147 minutes<br>
      <b>シリーズ</b>: <a href="/series/xxx">究極の爆乳密写シコシコサポート</a><br>
    </div>
  </div>
</div>
</body></html>
"""

# HTML where snapshot index 0 is the cover and should be skipped
SNAPSHOT_WITH_COVER_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: <a href="/company/Fitch/1">Fitch</a><br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>収録時間</b>: 147 minutes<br>
    </div>
  </div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/0"><img src="http://pics.dmm.co.jp//digital/video/jufd00851/jufd00851pl.jpg"></a></p></div>
</div>
</body></html>
"""

# HTML without .col-md-9 — new fields should use defaults
NO_COL_MD_9_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル</h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
  </div>
</div>
</body></html>
"""

# HTML where maker is plain text (no <a>), but series has <a>
# Verifies that _find_next_a_before_next_b does NOT cross into the series field
MAKER_PLAIN_TEXT_HTML = """\
<html><body>
<a href="/video/jufd-851">JUFD-851</a>
<h3>JUFD-851 タイトル <small>jufd-851</small></h3>
<div class="panel-body">
  <div class="row">
    <div class="col-md-3"><img class="img-responsive" src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851ps.jpg"></div>
    <div class="col-md-9">
      <b>出演者</b>: <a href="/star/123/1">テスト女優</a> &nbsp; <br>
      <b>メーカー</b>: Fitch<br>
      <b>品番</b>: jufd-851<br>
      <b>配信開始日</b>: 2018-01-13<br>
      <b>収録時間</b>: 147 minutes<br>
      <b>シリーズ</b>: <a href="/series/xxx">究極の爆乳密写シコシコサポート</a><br>
    </div>
  </div>
  <div class="col-xs-12 col-md-12"><p><a href="/snapshot/jufd00851/1/1"><img src="http://pics.dmm.co.jp/digital/video/jufd00851/jufd00851jp-1.jpg"></a></p></div>
</div>
</body></html>
"""

# Full fields HTML — used for verifying existing fields are unchanged
EXISTING_FIELDS_HTML = FULL_FIELDS_HTML


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def scraper():
    """JAV321Scraper with rate_limit mocked."""
    from core.scrapers.jav321 import JAV321Scraper
    with patch("core.scrapers.jav321.rate_limit"):
        yield JAV321Scraper()


# ============================================================
# Helper
# ============================================================

def run_search(scraper, html: str, number: str = "JUFD-851"):
    """
    Patch post_html to return HTML that looks like a direct detail page
    (contains /video/ and <h3>), so search() uses it directly without
    calling get_html.
    """
    with patch("core.scrapers.jav321.post_html", return_value=html):
        return scraper.search(number)


# ============================================================
# Tests
# ============================================================

class TestFullFields:
    """happy path: all new fields present"""

    def test_search_full_fields(self, scraper):
        video = run_search(scraper, FULL_FIELDS_HTML)
        assert video is not None
        assert video.maker == "Fitch"
        assert video.duration == 147
        assert video.series == "究極の爆乳密写シコシコサポート"
        assert len(video.sample_images) == 2
        assert "jufd00851jp-1.jpg" in video.sample_images[0]
        assert "jufd00851jp-2.jpg" in video.sample_images[1]


class TestNoSeries:
    """シリーズ 欄位缺失 → series = ''"""

    def test_search_no_series(self, scraper):
        video = run_search(scraper, NO_SERIES_HTML)
        assert video is not None
        assert video.series == ""


class TestNoDuration:
    """収録時間 欄位缺失 → duration = None"""

    def test_search_no_duration(self, scraper):
        video = run_search(scraper, NO_DURATION_HTML)
        assert video is not None
        assert video.duration is None


class TestNoSnapshot:
    """snapshot 全缺失 → sample_images = []"""

    def test_search_no_snapshot(self, scraper):
        video = run_search(scraper, NO_SNAPSHOT_HTML)
        assert video is not None
        assert video.sample_images == []


class TestSnapshotSkipsCover:
    """snapshot index 0（封面）href 結尾 /0 → 跳過，不加入 sample_images"""

    def test_search_snapshot_skips_cover(self, scraper):
        video = run_search(scraper, SNAPSHOT_WITH_COVER_HTML)
        assert video is not None
        # Cover image (index 0) must not appear in sample_images
        assert video.sample_images == []


class TestNoColMd9:
    """.col-md-9 缺失 → 新欄位使用預設值"""

    def test_search_no_col_md_9(self, scraper):
        video = run_search(scraper, NO_COL_MD_9_HTML)
        assert video is not None
        assert video.maker == ""
        assert video.duration is None
        assert video.series == ""
        assert video.sample_images == []


class TestMakerPlainText:
    """maker が純テキスト（<a> なし）で、次の欄位 シリーズ が <a> を持つ場合、
    maker は '' になり（<a> なし）、series は正しく取得される（跨欄位誤抓しない）"""

    def test_maker_plain_text_no_cross_field(self, scraper):
        video = run_search(scraper, MAKER_PLAIN_TEXT_HTML)
        assert video is not None
        # maker has no <a> tag — should be empty string, NOT "究極の爆乳密写シコシコサポート"
        assert video.maker == ""
        # series <a> is still correctly parsed
        assert video.series == "究極の爆乳密写シコシコサポート"


class TestExistingFieldsUnchanged:
    """確認 actresses、tags、date、title、cover_url 行為不變"""

    def test_search_existing_fields_unchanged(self, scraper):
        video = run_search(scraper, EXISTING_FIELDS_HTML)
        assert video is not None
        # title — number prefix removed
        assert "JUFD-851" not in video.title
        assert "タイトル" in video.title
        # cover_url — ps.jpg → pl.jpg
        assert video.cover_url.endswith("pl.jpg")
        assert "ps.jpg" not in video.cover_url
        # actresses
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "テスト女優"
        # date
        assert video.date == "2018-01-13"
        # source
        assert video.source == "jav321"
        # director and label use model defaults
        assert video.director == ""
        assert video.label == ""
