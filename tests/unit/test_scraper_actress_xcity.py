from unittest.mock import Mock, patch

import pytest
import requests

from core.scrapers.actress.xcity import (
    _find_exact_match,
    _parse_xcity_detail_html,
    scrape_xcity,
)


# 搜尋結果頁的最小合成頁：只放 _find_exact_match 會讀的 <a href title>，
# 含部分相符的姓名與非詳情頁連結，驗的是「只挑完全同名」這條我們自己的規則。
SEARCH_TSUBOMI = (
    '<a href="/idol/detail/21862/" title="望月つぼみ">望月つぼみ</a>'
    '<a href="/idol/?q=つぼみ" title="つぼみ">次のページ</a>'
    '<a href="/idol/detail/1419/" title="つぼみ">つぼみ</a>'
    '<a href="/idol/detail/11788/" title="鮎川つぼみ">鮎川つぼみ</a>'
)


def _detail(*rows):
    return (
        '<div id="avidolDetails"><h1>試験女優</h1><dl class="profile">'
        + "".join(f'<dd><span class="koumoku">{label}</span>{value}</dd>' for label, value in rows)
        + "</dl></div>"
    )


def _detail_with_photo(photo_src, *rows):
    dd_html = "".join(f'<dd><span class="koumoku">{label}</span>{value}</dd>' for label, value in rows)
    return (
        '<div id="avidolDetails"><h1>試験女優</h1>'
        f'<img class="actressThumb" src="{photo_src}">'
        f'<dl class="profile">{dd_html}</dl></div>'
    )


@pytest.mark.parametrize("html", [
    "<html><body><p>not found</p></body></html>",
    '<div id="avidolDetails"><h1>  </h1></div>',
], ids=["missing_details", "empty_heading"])
def test_parse_xcity_detail_returns_none_when_delisted(html):
    assert _parse_xcity_detail_html(html, "試験女優") is None


def test_parse_xcity_detail_noimage_only_returns_none():
    """TASK-157-F1: idol 11000（白玉あん）實測 — 頁面存在但全部欄位空白，
    僅有共用的 noimage.gif 佔位圖。過濾佔位圖後 name_ja 以外一無所有，
    視同沒找到，讓 orchestrator 的 any(sources.values()) 判斷不被這種
    空殼字典擋住，add_favorite 的本地封面裁圖 fallback（TASK-122-T10）才跑得到。"""
    html = _detail_with_photo("//faws.xcity.jp/actress/large/image/noimage.gif", ("出身地", ""))
    assert _parse_xcity_detail_html(html, "白玉あん") is None


def test_parse_xcity_detail_noimage_with_one_real_field_keeps_dict_without_photo():
    """有真實文字欄位時不算空殼——保留該欄位，但 noimage.gif 仍不當成 photo_url。"""
    html = _detail_with_photo(
        "//faws.xcity.jp/actress/large/image/noimage.gif",
        ("出身地", "東京都"),
    )
    result = _parse_xcity_detail_html(html, "試験女優")
    assert result is not None
    assert result["hometown"] == "東京都"
    assert "photo_url" not in result


def test_parse_xcity_detail_real_photo_is_kept_when_not_placeholder():
    """非 noimage 的真實照片不受過濾影響。"""
    html = _detail_with_photo(
        "//faws.xcity.jp/actress/large/image/person/11000.jpg",
        ("出身地", "東京都"),
    )
    result = _parse_xcity_detail_html(html, "試験女優")
    assert result is not None
    assert result["photo_url"] == "https://faws.xcity.jp/actress/large/image/person/11000.jpg"


def test_parse_xcity_detail_real_photo_no_text_fields_still_kept():
    """TASK-157-F1 follow-up: 一張真實照片、完全沒有文字欄位——不算空殼。
    「空殼」的判準是 len(result) <= 1（只剩 name_ja），真實 photo_url 會讓
    dict 長度變成 2，所以即使沒有任何文字欄位也不該被新規則收斂成 None；
    這條測試把 None 規則故意改成「需要至少一個文字欄位」會讓它變紅，鎖住
    「photo-only 也算數」這個界線（見下方變更後的手動 RED 驗證）。"""
    html = _detail_with_photo(
        "//faws.xcity.jp/actress/large/image/person/11000.jpg",
    )
    result = _parse_xcity_detail_html(html, "試験女優")
    assert result is not None
    assert result["photo_url"] == "https://faws.xcity.jp/actress/large/image/person/11000.jpg"
    assert set(result) == {"name_ja", "photo_url"}


@pytest.mark.parametrize("name,expected", [
    ("つぼみ", "1419"),
    ("望月つぼみ", "21862"),
    ("鮎川つぼみ", "11788"),
    ("存在しない女優", None),
])
def test_find_exact_match_returns_exact_candidate_only(name, expected):
    assert _find_exact_match(SEARCH_TSUBOMI, name) == expected


def test_find_exact_match_no_candidates():
    assert _find_exact_match("<html><body></body></html>", "つぼみ") is None


def test_parse_xcity_detail_parser_error_returns_none():
    with patch("core.scrapers.actress.xcity.BeautifulSoup", side_effect=ValueError("bad html")):
        assert _parse_xcity_detail_html("<html>", "試験女優") is None


@pytest.mark.parametrize("value,expected", [
    ("-型", None),
    ("-", None),
    ("AB型", "AB型"),
])
def test_parse_xcity_blood(value, expected):
    # TASK-157-F1: 加一個錨定欄位（出身地），避免「血液型」被過濾後整份變成
    # name_ja-only 的空殼字典而被新規則判成 None——本測試要驗的是 blood 欄位
    # 自身的過濾邏輯，不是「空殼視同沒找到」那條規則。
    result = _parse_xcity_detail_html(_detail(("血液型", value), ("出身地", "東京都")), "試験女優")
    assert result is not None
    assert result.get("blood") == expected
    assert ("blood" in result) == (expected is not None)


@pytest.mark.parametrize("value,expected", [
    ("B83 W58 H85", {"bust": "83cm", "waist": "58cm", "hip": "85cm"}),
    ("B83 W58", {"bust": "83cm", "waist": "58cm"}),
    ("W58 H85", {"waist": "58cm", "hip": "85cm"}),
])
def test_parse_xcity_size_without_cup_or_missing_measurement(value, expected):
    result = _parse_xcity_detail_html(_detail(("サイズ", value)), "試験女優")
    assert result is not None
    assert {key: result[key] for key in ("bust", "waist", "hip") if key in result} == expected
    assert "cup" not in result


@pytest.mark.parametrize("rows,expected", [
    ([("趣味", "ショッピング"), ("特技", "")], "ショッピング"),
    ([("趣味", ""), ("特技", "車庫入れ")], "車庫入れ"),
    ([("趣味", ""), ("特技", "")], None),
])
def test_parse_xcity_hobby_ignores_empty_parts_and_other(rows, expected):
    # TASK-157-F1: 加一個錨定欄位（出身地），理由同 test_parse_xcity_blood ——
    # 全空的「趣味/特技」案例若不加錨定欄位，整份會變成 name_ja-only 的空殼
    # 字典而被新規則判成 None，測不到 hobby 過濾邏輯本身。
    result = _parse_xcity_detail_html(
        _detail(*rows, ("出身地", "東京都"), ("その他", "長い自由記述")), "試験女優"
    )
    assert result is not None
    assert result.get("hobby") == expected
    assert "長い自由記述" not in str(result)


@pytest.mark.parametrize("failure", [requests.Timeout("timeout"), requests.RequestException("network")])
def test_scrape_xcity_search_request_failure_returns_none(failure):
    with patch("core.scrapers.actress.xcity.requests.get", side_effect=failure):
        assert scrape_xcity("つぼみ") is None


@pytest.mark.parametrize("failure", [requests.Timeout("timeout"), requests.RequestException("network")])
def test_scrape_xcity_detail_request_failure_returns_none(failure):
    search = Mock(status_code=200, text=SEARCH_TSUBOMI)
    with patch("core.scrapers.actress.xcity.requests.get", side_effect=[search, failure]):
        assert scrape_xcity("つぼみ") is None


def test_scrape_xcity_search_miss_skips_detail_request():
    search = Mock(status_code=200, text="<html></html>")
    with patch("core.scrapers.actress.xcity.requests.get", return_value=search) as get:
        assert scrape_xcity("つぼみ") is None
        get.assert_called_once()


def test_scrape_xcity_fetches_exact_candidate_detail():
    search = Mock(status_code=200, text=SEARCH_TSUBOMI)
    detail = Mock(status_code=200, text=_detail(("身長", "160cm")))
    with patch("core.scrapers.actress.xcity.requests.get", side_effect=[search, detail]) as get:
        assert scrape_xcity("つぼみ")["height"] == "160cm"
        assert get.call_args_list[0].args[0] == "https://xcity.jp/idol/?genre=%2Fidol%2F&q=%E3%81%A4%E3%81%BC%E3%81%BF&sg=idol"
        assert get.call_args_list[1].args[0] == "https://xcity.jp/idol/detail/1419/"
