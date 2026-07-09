"""
test_fc2_scraper.py - FC2 爬蟲單元測試（TASK-36-T9）

測試策略：
- 全 mock，不連網
- Mock scraper._session.get 回傳 inline HTML fixture
- rate_limit 也 mock 掉（避免 sleep）
"""

import pytest
from unittest.mock import patch, MagicMock


# ============================================================
# HTML Fixtures
# ============================================================

SEARCH_HTML = """\
<html><body>
<a href="/id1723984">FC2-PPV-1723984</a>
</body></html>
"""

# Detail page with extrafanart
FULL_FIELDS_HTML = """\
<html><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<div style="padding: 0">
  <a href="//pics.example.com/gallery/001.jpg"><img src="//pics.example.com/gallery/001s.jpg"></a>
  <a href="//pics.example.com/gallery/002.jpg"><img src="//pics.example.com/gallery/002s.jpg"></a>
</div>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
</body></html>
"""

# Detail page without extrafanart
NO_GALLERY_HTML = """\
<html><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
</body></html>
"""

# Detail page with outline (col des) + JSON-LD aggregateRating (dict form)
OUTLINE_RATING_HTML = """\
<html><head><meta charset="utf-8"></head><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<div class="col des">これはFC2の説明文です。</div>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
<script type="application/ld+json">{"@type":"Movie","aggregateRating":{"@type":"AggregateRating","ratingValue":"4.5","bestRating":"5"}}</script>
</body></html>
"""

# Detail page with JSON-LD as a list / @graph array form
GRAPH_RATING_HTML = """\
<html><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<div class="col des">グラフ形式の説明文。</div>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
<script type="application/ld+json">[{"@type":"WebSite"},{"@type":"Movie","aggregateRating":{"@type":"AggregateRating","ratingValue":3.0,"bestRating":"5"}}]</script>
</body></html>
"""

# Detail page with broken JSON-LD
BROKEN_JSONLD_HTML = """\
<html><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
<script type="application/ld+json">{ this is not valid json </script>
</body></html>
"""

# Detail page with JSON-LD present but no aggregateRating
NO_AGGREGATE_JSONLD_HTML = """\
<html><body>
<h1>FC2-1723984</h1>
<h1>テストタイトル</h1>
<div class="col-8">テスト賣家</div>
<a data-fancybox="gallery" href="//pics.example.com/cover.jpg">
  <img src="//pics.example.com/thumb.jpg">
</a>
<p class="card-text">
  <a href="/tag/amateur">アマチュア</a>
</p>
<script type="application/ld+json">{"@type":"Movie","name":"タイトル"}</script>
</body></html>
"""


# ============================================================
# Helpers
# ============================================================

def make_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.content = html.encode("utf-8")
    return resp


def run_search(scraper, detail_html: str, number: str = "FC2-PPV-1723984"):
    """
    Mock _search_url to bypass search page, then mock detail GET.
    """
    detail_resp = make_response(detail_html)
    with patch.object(scraper, "_search_url", return_value="https://javten.com/id1723984"):
        scraper._session.get = MagicMock(return_value=detail_resp)
        return scraper.search(number)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def scraper():
    from core.scrapers.fc2 import FC2Scraper
    with patch("core.scrapers.fc2.rate_limit"):
        s = FC2Scraper()
        yield s


# ============================================================
# Tests
# ============================================================

class TestFullFields:
    """happy path: sample_images 有 URL（list[str]）"""

    def test_sample_images_present(self, scraper):
        video = run_search(scraper, FULL_FIELDS_HTML)
        assert video is not None
        assert len(video.sample_images) == 2

    def test_sample_images_absolute_url(self, scraper):
        video = run_search(scraper, FULL_FIELDS_HTML)
        assert video is not None
        for url in video.sample_images:
            assert url.startswith("https://")


class TestNoGallery:
    """無 extrafanart → sample_images=[]"""

    def test_no_extrafanart_empty_list(self, scraper):
        video = run_search(scraper, NO_GALLERY_HTML)
        assert video is not None
        assert video.sample_images == []


class TestOutline:
    """簡介接線（col des → Video.summary）"""

    def test_summary_present(self, scraper):
        video = run_search(scraper, OUTLINE_RATING_HTML)
        assert video is not None
        assert video.summary == "これはFC2の説明文です。"
        assert video.summary != ""

    def test_summary_empty_when_no_col_des(self, scraper):
        video = run_search(scraper, FULL_FIELDS_HTML)
        assert video is not None
        assert video.summary == ""


class TestRating:
    """評分解析（JSON-LD aggregateRating.ratingValue → Video.rating）"""

    def test_rating_from_dict_jsonld(self, scraper):
        video = run_search(scraper, OUTLINE_RATING_HTML)
        assert video is not None
        assert video.rating == 4.5

    def test_rating_from_graph_list_jsonld(self, scraper):
        video = run_search(scraper, GRAPH_RATING_HTML)
        assert video is not None
        assert video.rating == 3.0

    def test_rating_none_when_no_jsonld(self, scraper):
        video = run_search(scraper, FULL_FIELDS_HTML)
        assert video is not None
        assert video.rating is None

    def test_rating_none_when_broken_jsonld(self, scraper):
        video = run_search(scraper, BROKEN_JSONLD_HTML)
        assert video is not None
        assert video.rating is None

    def test_rating_none_when_no_aggregate(self, scraper):
        video = run_search(scraper, NO_AGGREGATE_JSONLD_HTML)
        assert video is not None
        assert video.rating is None
