"""E2E：以圖查番號的接線（193-T12）。全 mock、零真站，只驗結束狀態。

mock 的輸入全是自家協定（/api/image-search 信封、/api/search 的 {success,data}、SSE result 事件）。
逐部查詢的 /api/search?q= 先「收著不回」，測試在需要的時刻才放行（等抵達 → 放行），
所以順序是承重的，不靠固定等待湊時序。cover／thumb_url 一律空字串，真 server 不會去代理真站圖片。
"""
import base64
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

NUMS = ["TST-101", "TST-102", "TST-103"]
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
CTA = json.loads((Path(__file__).parents[2] / "locales" / "zh_TW.json").read_text("utf-8"))[
    "search"]["image"]["not_found"]["search_cta"]
CANCEL = ".search-actions-right button:not(#btnClear):has(.bi-x-lg)"
TOGGLE = ".search-actions-right button:has(i.bi-grid-3x3), .search-actions-right button:has(i.bi-list-ul)"
FONTS = re.compile(r"https://fonts\.(googleapis|gstatic)\.com/")
CARDS = ".search-grid .av-card-preview:not(.hero-card)"


def _candidate(rank: int, number: str) -> dict:
    match = {"kind": "cover", "cover_part": "full", "time_seconds": None, "time_text": None, "thumb_url": ""}
    return {"rank": rank, "code": number, "number": number, "searchable": True,
            "similarity": 93.4 - rank, "match": match, "in_library": False}


def _result_event(number: str) -> str:
    video = {"number": number, "title": "T-" + number, "cover": "", "actors": []}
    event = {"type": "result", "success": True, "data": [video], "has_more": False, "mode": "exact"}
    return "data: " + json.dumps(event) + "\n\n"


class Harness:
    """三條 route ＋ 外部請求收集。streams 依文字搜尋呼叫次序：None＝掛住不回，字串＝SSE 內容。"""

    def __init__(self, page: Page, base_url: str, streams: list | None = None):
        self.page, self.base, self.urls, self.held = page, base_url, [], {}
        self.streams, self.stream_calls, self.image_calls = list(streams or []), 0, 0
        page.on("request", lambda r: self.urls.append(r.url))
        page.route("**/api/image-search", self._image)
        page.route(re.compile(r"/api/search\?q="), self._lookup)
        page.route("**/api/search/stream*", self._stream)
        page.route(FONTS, lambda r: r.fulfill(body="", content_type="text/css"))  # 站內頁面固有的 Google Fonts，不放行出網

    def _image(self, route):
        self.image_calls += 1
        route.fulfill(json={"success": True, "source": "avscan", "clear_hit": True, "lead": 9.0,
                            "candidates": [_candidate(i + 1, n) for i, n in enumerate(NUMS)]})

    def _lookup(self, route):
        self.held[parse_qs(urlparse(route.request.url).query)["q"][0]] = route

    def _stream(self, route):
        body = self.streams[self.stream_calls] if self.stream_calls < len(self.streams) else None
        self.stream_calls += 1
        if body is not None:
            route.fulfill(content_type="text/event-stream", body=body)

    def arrive(self, number: str, timeout_ms: int = 10_000) -> None:
        waited = 0
        while number not in self.held:
            if waited >= timeout_ms:
                pytest.fail(f"{number} 的查詢沒有抵達；已收到 {list(self.held)}")
            self.page.wait_for_timeout(50)
            waited += 50

    def release(self, number: str) -> None:
        video = {"number": number, "title": "T-" + number, "cover": "", "actors": []}
        self.held.pop(number).fulfill(json={"success": True, "data": [video]})

    def open_and_pick(self) -> None:
        self.page.set_viewport_size({"width": 1280, "height": 900})
        self.page.goto(f"{self.base}/search")
        self.page.bring_to_front()
        with self.page.expect_file_chooser() as chooser:
            self.page.click("#btnImageSearch")
        chooser.value.set_files({"name": "shot.png", "mimeType": "image/png", "buffer": PNG})
        expect(self.page.locator(".search-grid")).to_be_visible()

    def assert_clean(self) -> None:
        outside = [u for u in self.urls if not (u.startswith((self.base, "blob:", "data:")) or FONTS.match(u))]
        assert outside == [], f"出現外部請求：{outside}"
        assert [u for u in self.urls if "/api/proxy-image" in u] == []
        assert self.image_calls == 1


def _text_search(page: Page, query: str) -> None:
    page.fill("#searchQuery", query)
    page.click("#btnSubmit")


def test_first_candidate_auto_switches_to_detail(page: Page, base_url: str):
    """丟圖 → 先看到格狀（第一格是自己的圖）；第一名補上自動轉詳細且比對列在。"""
    h = Harness(page, base_url)
    h.open_and_pick()
    grid = page.locator(".search-grid")
    first = page.locator(".search-grid .hero-card.av-card-user-image")
    expect(first).to_be_visible()
    expect(first.locator('img[src^="blob:"]')).to_have_count(1)
    expect(page.locator(CARDS)).to_have_count(3)
    expect(page.locator(".search-grid .av-card-preview.skeleton")).to_have_count(3)
    expect(grid).not_to_contain_text("avscan")
    h.arrive(NUMS[0])
    h.release(NUMS[0])
    expect(page.locator(".av-card-full")).to_be_visible()
    expect(page.locator("#resultNumber")).to_have_text(NUMS[0])
    expect(page.locator(".img-match-row")).to_be_visible()
    expect(page.locator(".img-match-row .imr-score")).to_contain_text("%")
    expect(grid).not_to_be_visible()
    h.assert_clean()


def test_user_toggled_view_is_not_moved_away(page: Page, base_url: str):
    """自己切過檢視（來回兩次）→ 第一名資料到了仍留在格狀，不被轉走。"""
    h = Harness(page, base_url)
    h.open_and_pick()
    page.click(TOGGLE)
    expect(page.locator(".av-card-full")).to_be_visible()
    page.click(TOGGLE)
    expect(page.locator(".search-grid")).to_be_visible()
    h.arrive(NUMS[0])
    h.release(NUMS[0])
    h.arrive(NUMS[1])  # 第二筆已發出 ＝ 第一名「要不要轉」的決定必已做完
    h.release(NUMS[1])
    expect(page.locator(CARDS).nth(1)).not_to_have_class(re.compile("skeleton"))
    expect(page.locator(".search-grid")).to_be_visible()
    expect(page.locator(".av-card-full")).not_to_be_visible()
    expect(page.locator(".img-match-row")).to_have_count(0)
    h.assert_clean()


def test_cancel_after_first_keeps_numbers_for_the_rest(page: Page, base_url: str):
    """番號到後按取消 → 已出現的留著、沒查完的看得到番號，沒有骨架殘留。"""
    h = Harness(page, base_url)
    h.open_and_pick()
    h.arrive(NUMS[0])
    h.release(NUMS[0])
    expect(page.locator(".av-card-full")).to_be_visible()
    h.arrive(NUMS[1])  # 迴圈在飛；這筆之後會被取消，不放行
    page.click(CANCEL)
    expect(page.locator(CANCEL)).to_be_hidden()
    expect(page.locator("#btnClear")).to_be_visible()
    page.click(TOGGLE)
    expect(page.locator(".search-grid")).to_be_visible()
    cards = page.locator(CARDS)
    expect(cards).to_have_count(3)
    expect(page.locator(".search-grid .av-card-preview.skeleton")).to_have_count(0)
    expect(cards.nth(0)).not_to_have_class(re.compile("is-notfound"))
    expect(cards.nth(0).locator(".av-num")).to_have_text(NUMS[0])
    for i in (1, 2):
        expect(cards.nth(i)).to_have_class(re.compile("is-notfound"))
        expect(cards.nth(i).locator(".av-num")).to_have_text(NUMS[i])
    h.assert_clean()


def test_stop_text_search_returns_to_image_candidates(page: Page, base_url: str):
    """候選沒補完就改打字搜尋再取消 → 一次就停、回圖片候選、無骨架；文字結果取代後比對列消失。"""
    h = Harness(page, base_url, streams=[None, _result_event("TXT-004")])
    h.open_and_pick()
    h.arrive(NUMS[0])
    h.release(NUMS[0])
    expect(page.locator(".av-card-full")).to_be_visible()
    h.arrive(NUMS[1])  # 候選還有骨架
    _text_search(page, "TXT-003")
    expect(page.locator(CANCEL)).to_be_visible()
    page.click(CANCEL)
    expect(page.locator(CANCEL)).to_be_hidden()
    expect(page.locator(".img-match-row")).to_be_visible()
    expect(page.locator("#resultNumber")).to_have_text(NUMS[0])
    expect(page.locator(".av-card-preview.skeleton")).to_have_count(0)
    expect(page.locator(".search-grid .skeleton-cover.shimmer:visible")).to_have_count(0)
    for number in NUMS[1:]:
        page.keyboard.press("ArrowRight")
        panel = page.locator(".notfound-panel")
        expect(panel).to_be_visible()
        expect(panel.locator(".notfound-number")).to_have_text(number)
        expect(panel).to_contain_text(CTA)
        expect(page.locator(".img-match-row")).to_be_visible()
    _text_search(page, "TXT-004")
    expect(page.locator("#resultNumber")).to_have_text("TXT-004")
    expect(page.locator(".img-match-row")).to_have_count(0)
    h.assert_clean()
