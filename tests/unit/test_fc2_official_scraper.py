"""test_fc2_official_scraper.py - FC2 官方站爬蟲單元測試（TASK-118-T2）

測試策略：
- 全 mock，不連網；mock scraper._session.get 回傳真 fixture bytes
- rate_limit 也 mock 掉（避免 sleep）
- 全部 parse 測試餵 tests/fixtures/scrapers/fc2official_*.html 真檔，零手搭 HTML
  （feedback_scraper_real_fixtures.md）
- 需要製造變體時用「真 fixture 字串手術」（heyzo 測試的 _remove_* helper 風格）

本檔只驗證 FC2OfficialScraper 本體行為；dispatch 接線（core/scraper.py /
core/scrapers/__init__.py）由 tests/unit/test_fc2_dispatch_single_point.py 守。
"""

import os

import pytest
import requests
from unittest.mock import MagicMock, patch


FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "scrapers"
)


def load_fixture_bytes(name: str) -> bytes:
    with open(os.path.join(FIXTURES_DIR, name), "rb") as f:
        return f.read()


FIX_4938582 = load_fixture_bytes("fc2official_4938582.html")
FIX_1723984 = load_fixture_bytes("fc2official_1723984.html")
FIX_4938576 = load_fixture_bytes("fc2official_4938576.html")
FIX_NOTFOUND = load_fixture_bytes("fc2official_1723985_notfound.html")


# ============================================================
# Fixture surgery helpers（真 fixture 為底做針對性字串置換）
# ============================================================

def _replace_tag_with_uncensored_marker(html_bytes: bytes) -> bytes:
    """把 4938582 fixture 中「個撮」這個標籤的顯示文字換成「無修正」
    （模擬站方標籤字面剛好是無修正標記，過濾邏輯應該把它濾掉）。"""
    old = ">個撮</a>".encode("utf-8")
    assert html_bytes.count(old) == 1
    new = ">無修正</a>".encode("utf-8")
    return html_bytes.replace(old, new, 1)


def _html_str(html_bytes: bytes) -> str:
    return html_bytes.decode("utf-8")


def _remove_json_ld(html_bytes: bytes) -> bytes:
    """整段移除 <script type="application/ld+json">…</script>（og:url fallback 邊界）。"""
    html = _html_str(html_bytes)
    start_marker = '<script type="application/ld+json">'
    start = html.index(start_marker)
    end = html.index("</script>", start) + len("</script>")
    return (html[:start] + html[end:]).encode("utf-8")


def _replace_og_url(html_bytes: bytes, new_url: str) -> bytes:
    html = _html_str(html_bytes)
    old = 'property="og:url" content="https://adult.contents.fc2.com/article/4938582/"'
    new = f'property="og:url" content="{new_url}"'
    assert html.count(old) == 1
    return html.replace(old, new, 1).encode("utf-8")


def _remove_seller_box(html: str) -> str:
    start_marker = '<section class="items_comment_sellerBox"'
    start = html.index(start_marker)
    end = html.index("</section>", start) + len("</section>")
    return html[:start] + html[end:]


def _remove_sample_images_area(html: str) -> str:
    start_marker = '<ul class="items_article_SampleImagesArea"'
    start = html.index(start_marker)
    end = html.index("</ul>", start) + len("</ul>")
    return html[:start] + html[end:]


def _remove_sale_date_block(html: str) -> str:
    idx = html.index("販売日")
    start = html.rindex('<div class="items_article_softDevice">', 0, idx)
    end = html.index("</div>", idx) + len("</div>")
    return html[:start] + html[end:]


def _remove_aggregate_rating(html: str) -> str:
    old = (
        ',"aggregateRating":{"ratingValue":0,"bestRating":5,'
        '"worstRating":1,"reviewCount":0,"@type":"AggregateRating"}'
    )
    assert html.count(old) == 1
    return html.replace(old, "", 1)


def _strip_optional_field_blocks(html_bytes: bytes) -> bytes:
    """同時拿掉賣家／劇照／販売日／aggregateRating（卡片本 task 特有邊界 3–6）。"""
    html = _html_str(html_bytes)
    html = _remove_seller_box(html)
    html = _remove_sample_images_area(html)
    html = _remove_sale_date_block(html)
    html = _remove_aggregate_rating(html)
    return html.encode("utf-8")


# ============================================================
# Helpers
# ============================================================

def make_response(content: bytes, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    return resp


@pytest.fixture
def scraper():
    from core.scrapers.fc2_official import FC2OfficialScraper
    with patch("core.scrapers.fc2_official.rate_limit"):
        s = FC2OfficialScraper()
        yield s


# ============================================================
# 1. 4938582 全欄位快照
# ============================================================

class TestFullSnapshot4938582:
    def test_full_fields(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_4938582))
        video = scraper.search("4938582")

        assert video is not None
        assert video.title == (
            "【個人撮影/数量限定】一見お淑やかなおねえさん系人妻、"
            "実は名器の締め付けが凄まじい肉食獣。"
            "玩具を駆使した激しいピストンの末、"
            "可愛いお顔へ大量に撃ち込まれた至高の個人撮影データ。"
        )
        assert video.date == "2026-07-13"
        assert video.maker == "古い絵の具"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "古い絵の具"
        assert video.tags == [
            "人妻", "ハメ撮り", "素人", "美乳", "個人撮影",
            "巨乳", "美人", "かわいい", "下着", "個撮",
        ]
        assert video.cover_url == (
            "https://storage201000.contents.fc2.com/file/384/38370907/1783944765.71.jpg"
        )
        assert len(video.sample_images) == 2
        for url in video.sample_images:
            assert url.startswith("https://contents-thumbnail2.fc2.com/w1280/")
        assert video.number == "FC2-4938582"
        assert video.source == "fc2"
        assert video.detail_url == "https://adult.contents.fc2.com/article/4938582/"
        assert video.summary == ""
        assert video.rating is None


# ============================================================
# 2. 1723984：rating / date / 10 張劇照 / cover https（非 LD 的 http）
# ============================================================

class TestRatingAndHttpsCover1723984:
    def test_rating_date_images_https_cover(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_1723984))
        video = scraper.search("1723984")

        assert video is not None
        assert video.rating == 5.0
        assert video.date == "2021-03-12"
        assert len(video.sample_images) == 10
        assert video.cover_url.startswith("https://")
        assert not video.cover_url.startswith("http://")


# ============================================================
# 3. 4938576：標題為 LD name 逐字，不含番號前綴（mutation #1 的可證偽點）
# ============================================================

class TestTitleFromJsonLdName4938576:
    def test_title_matches_ld_name_no_number_prefix(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_4938576))
        video = scraper.search("4938576")

        assert video is not None
        assert len(video.title) == 85
        assert not video.title.startswith("FC2-PPV")


# ============================================================
# 4. 軟 404 → None
# ============================================================

class TestSoftNotFound:
    def test_soft_404_returns_none(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_NOTFOUND))
        video = scraper.search("1723985")

        assert video is None


# ============================================================
# 5. id 不符（拿到別片）→ None
# ============================================================

class TestIdMismatch:
    def test_mismatched_id_returns_none(self, scraper):
        # 4938582 的 fixture，當作請求 4938433 的回應
        scraper._session.get = MagicMock(return_value=make_response(FIX_4938582))
        video = scraper.search("4938433")

        assert video is None


# ============================================================
# 6. ?lang=ja URL 完整字串
# ============================================================

class TestRequestUrl:
    def test_url_includes_lang_ja(self, scraper):
        mock_get = MagicMock(return_value=make_response(FIX_1723984))
        scraper._session.get = mock_get
        scraper.search("1723984")

        called_url = mock_get.call_args[0][0]
        assert called_url == "https://adult.contents.fc2.com/article/1723984/?lang=ja"


# ============================================================
# 7. summary 恆空
# ============================================================

class TestSummaryAlwaysEmpty:
    def test_summary_is_empty_even_though_ld_has_description(self, scraper):
        assert b'"description"' in FIX_4938582  # fixture 確實有 description
        scraper._session.get = MagicMock(return_value=make_response(FIX_4938582))
        video = scraper.search("4938582")

        assert video is not None
        assert video.summary == ""
        assert "…" not in video.summary


# ============================================================
# 8. 標籤過濾：字串手術把「個撮」換成「無修正」
# ============================================================

class TestTagFiltering:
    def test_uncensored_marker_tag_filtered_out(self, scraper):
        surgically_modified = _replace_tag_with_uncensored_marker(FIX_4938582)
        scraper._session.get = MagicMock(return_value=make_response(surgically_modified))
        video = scraper.search("4938582")

        assert video is not None
        assert len(video.tags) == 9  # 原本 10 個，「個撮」→「無修正」被濾掉
        assert "無修正" not in video.tags
        assert "個撮" not in video.tags


# ============================================================
# 9. _get_tags 直接對軟 404 fixture 呼叫 → []（mutation #2 的唯一可證偽點）
# ============================================================

class TestGetTagsDirectOnNotFound:
    def test_get_tags_empty_on_soft_404_fixture(self, scraper):
        from lxml import etree
        html = etree.fromstring(FIX_NOTFOUND, etree.HTMLParser())

        tags = scraper._get_tags(html)

        assert tags == []


# ============================================================
# 10. 番號正規化四形狀
# ============================================================

class TestNormalizeNumber:
    def test_four_shapes_normalize_equally(self, scraper):
        for raw in ("FC2-PPV-1723984", "FC2PPV1723984", "FC2-1723984", "1723984"):
            assert scraper._normalize_fc2_number(raw) == "1723984"


# ============================================================
# 11-13. 傳輸層失敗：非 200 / Timeout / ConnectionError → 靜默回 None
# ============================================================

class TestTransportFailureReturnsNone:
    def test_non_200_returns_none(self, scraper):
        # body 刻意餵**可解析成功的真商品頁**（不是 b""）：若餵空 body，就算把
        # `if resp.status_code != 200` 整段拿掉，etree 也會對空文件拋例外並被外層
        # `except Exception` 吞成 None——測試照樣綠，等於沒守住它宣稱的那條早退。
        # 餵真 fixture 後，拿掉 status 早退會解析成功回一個 Video → 本斷言轉紅。
        scraper._session.get = MagicMock(return_value=make_response(FIX_1723984, status_code=403))

        assert scraper.search("1723984") is None

    def test_timeout_returns_none(self, scraper):
        scraper._session.get = MagicMock(side_effect=requests.Timeout("boom"))

        assert scraper.search("1723984") is None

    def test_connection_error_returns_none(self, scraper):
        scraper._session.get = MagicMock(side_effect=requests.ConnectionError("boom"))

        assert scraper.search("1723984") is None


# ============================================================
# search_by_keyword：比照 fc2_javten.py（0.13.13 前為 fc2.py），包成 list
# ============================================================

class TestSearchByKeyword:
    def test_search_by_keyword_wraps_result_in_list(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_4938582))
        results = scraper.search_by_keyword("4938582")

        assert len(results) == 1
        assert results[0].number == "FC2-4938582"

    def test_search_by_keyword_empty_list_when_not_found(self, scraper):
        scraper._session.get = MagicMock(return_value=make_response(FIX_NOTFOUND))
        results = scraper.search_by_keyword("1723985")

        assert results == []


# ============================================================
# _get_source_name
# ============================================================

class TestSourceName:
    def test_source_name_is_fc2(self, scraper):
        assert scraper._get_source_name() == "fc2"


# ============================================================
# Review fix 1：無 JSON-LD 時 og:url / og:title fallback 必須可達
# ============================================================

EXPECTED_TITLE_4938582 = (
    "【個人撮影/数量限定】一見お淑やかなおねえさん系人妻、"
    "実は名器の締め付けが凄まじい肉食獣。"
    "玩具を駆使した激しいピストンの末、"
    "可愛いお顔へ大量に撃ち込まれた至高の個人撮影データ。"
)


class TestOgUrlFallbackWithoutJsonLd:
    def test_og_url_fallback_still_returns_video(self, scraper):
        surgically_modified = _remove_json_ld(FIX_4938582)
        scraper._session.get = MagicMock(return_value=make_response(surgically_modified))
        video = scraper.search("FC2-PPV-4938582")

        assert video is not None
        assert video.title == EXPECTED_TITLE_4938582
        assert video.rating is None
        assert video.date == "2026-07-13"
        assert video.maker == "古い絵の具"

    def test_og_url_pointing_to_other_article_returns_none(self, scraper):
        surgically_modified = _replace_og_url(
            _remove_json_ld(FIX_4938582),
            "https://adult.contents.fc2.com/article/9999999/",
        )
        scraper._session.get = MagicMock(return_value=make_response(surgically_modified))
        video = scraper.search("FC2-PPV-4938582")

        assert video is None


# ============================================================
# Review fix 2：欄位缺席不得整筆回 None（賣家空字串尤其不可炸 pydantic）
# ============================================================

class TestMissingOptionalFields:
    def test_absent_optional_blocks_still_return_video(self, scraper):
        surgically_modified = _strip_optional_field_blocks(FIX_4938582)
        scraper._session.get = MagicMock(return_value=make_response(surgically_modified))
        video = scraper.search("4938582")

        assert video is not None
        assert video.maker == ""
        assert video.actresses == []
        assert video.date == ""
        assert video.sample_images == []
        assert video.rating is None
        assert video.title == EXPECTED_TITLE_4938582
