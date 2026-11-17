"""進階編輯瀏覽器接線；攔截寫入，避免重用的 server 寫入使用者資料庫。"""
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, expect

pytestmark = pytest.mark.e2e
ALPINE_ROOT_SELECTOR = '[x-data="showcase"]'
VIDEO_CARD_SELECTOR = ".av-card-preview[data-flip-id]"
E2E_VIEWPORT = {"width": 1280, "height": 720}
MAX_CANDIDATES = 8
LB_FULL_TIMEOUT_MS = 15_000


def _fetch_cover_videos(page: Page, base_url: str) -> list:
    resp = page.request.get(f"{base_url}/api/showcase/videos")
    if not resp.ok:
        return []
    by_path = {v["path"]: v for v in resp.json().get("videos", [])}
    page.goto(f"{base_url}/showcase")
    try:
        page.wait_for_selector(VIDEO_CARD_SELECTOR, state="visible", timeout=LB_FULL_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return []
    paths = page.eval_on_selector_all(
        VIDEO_CARD_SELECTOR, "els => els.map(e => e.getAttribute('data-flip-id'))"
    )
    return [by_path[p] for p in paths if p in by_path and by_path[p].get("has_cover")]


def _open_lightbox_for(page: Page, base_url: str, video_path: str) -> bool:
    page.set_viewport_size(E2E_VIEWPORT)
    page.goto(f"{base_url}/showcase")
    try:
        page.wait_for_selector(VIDEO_CARD_SELECTOR, state="visible", timeout=LB_FULL_TIMEOUT_MS)
        card = page.locator(VIDEO_CARD_SELECTOR).all()
        match = next((item for item in card if item.get_attribute("data-flip-id") == video_path), None)
        if match is None:
            return False
        match.click()
        page.wait_for_function(
            """() => {
                const root = document.querySelector('%s');
                const data = window.Alpine && Alpine.$data(root);
                return !!(data && data._lbFullLoaded);
            }""" % ALPINE_ROOT_SELECTOR,
            timeout=LB_FULL_TIMEOUT_MS,
        )
        page.wait_for_selector(".lbx-more-btn", state="visible", timeout=5_000)
        return True
    except PlaywrightTimeoutError:
        return False


def _replace_path(value, old, new):
    if isinstance(value, dict):
        return {key: _replace_path(item, old, new) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_path(item, old, new) for item in value]
    return new if value == old else value


def test_adv_edit_repath_and_update_end_state(page: Page, base_url: str):
    page.set_viewport_size(E2E_VIEWPORT)
    state = {"old": None, "new": None, "renamed": False}
    repaths, refreshes, files, unexpected_writes, page_errors = [], [], [], [], []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def fallback(route, request):
        if request.method != "GET":
            unexpected_writes.append((request.method, request.url))
            route.abort()
        else:
            route.continue_()

    def repath(route, request):
        repaths.append(request.post_data_json)
        state["renamed"] = True
        route.fulfill(json={"success": True, "path": state["new"], "name_changed": False})

    def refresh(route, request):
        refreshes.append(request.post_data_json)
        route.fulfill(json={"success": True, "media_status": "ok"})

    def videos(route, request):
        if not state["renamed"]:
            route.continue_()
            return
        headers = {k: v for k, v in request.headers.items() if k.lower() != "if-none-match"}
        response = route.fetch(headers=headers)
        body = _replace_path(response.json(), state["old"], state["new"])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def video_files(route, request):
        parts = urlsplit(request.url)
        query = parse_qs(parts.query)
        files.append(query.get("path", [""])[0])
        if state["renamed"] and query.get("path", [""])[0] == state["new"]:
            query["path"] = [state["old"]]
            url = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
            route.fulfill(response=route.fetch(url=url))
        else:
            route.continue_()

    page.route("**/api/showcase/video/**", fallback)
    page.route("**/api/showcase/video/repath", repath)
    page.route("**/api/showcase/video/refresh", refresh)
    page.route("**/api/showcase/videos*", videos)
    page.route("**/api/showcase/video/files?*", video_files)

    candidates = _fetch_cover_videos(page, base_url)
    selected = False
    for video in candidates[:MAX_CANDIDATES]:
        if _open_lightbox_for(page, base_url, video["path"]):
            page.locator(".lbx-more-btn").click()
            menu = page.locator(".lbx-menu-item--advedit")
            try:
                menu.wait_for(state="visible", timeout=3000)
            except PlaywrightTimeoutError:
                page.keyboard.press("Escape")
                page.keyboard.press("Escape")
                continue
            if menu.is_visible():
                assert not menu.inner_text().strip().startswith("[")
                menu.click()
                dialog = page.locator(".adv-edit-dialog")
                expect(dialog).to_have_class(re.compile("modal-open"))
                page.wait_for_function(
                    """() => {
                        const d = window.Alpine.$data(document.querySelector('%s'));
                        return !d.advEditLoading && (!d.advEditInfo ||
                            document.querySelector('.adv-edit-pv-item'));
                    }""" % ALPINE_ROOT_SELECTOR
                )
                previews = dialog.locator(".adv-edit-sec--files .adv-edit-pv-item")
                info_state = page.evaluate(
                    """() => window.Alpine.$data(document.querySelector('%s')).advEditInfo?.state"""
                    % ALPINE_ROOT_SELECTOR
                )
                if (
                    info_state == "ok"
                    and previews.count() == 3
                    and previews.first.is_visible()
                    and not dialog.locator(".adv-edit-notice:visible").count()
                    and dialog.locator(".adv-edit-path-edit").is_visible()
                ):
                    selected = True
                    break
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")
    if not selected:
        pytest.skip("沒有可用候選：需要非唯讀、state=ok 的影片")

    old_uri = page.evaluate(
        """() => window.Alpine.$data(document.querySelector('%s')).currentLightboxVideo.path"""
        % ALPINE_ROOT_SELECTOR
    )
    extension = ".mkv" if old_uri.lower().endswith(".mp4") else ".mp4"
    state["old"], state["new"] = old_uri, old_uri.rsplit(".", 1)[0] + extension
    cards_before = page.locator(VIDEO_CARD_SELECTOR).count()
    page.locator(".adv-edit-path-edit").click()
    field = page.locator(".adv-edit-path-input")
    expect(field).to_be_visible()
    typed = field.input_value().rsplit(".", 1)[0] + extension
    field.fill(typed)
    field.press("Enter")
    page.wait_for_function(
        """([selector, path]) => {
            const d = window.Alpine.$data(document.querySelector(selector));
            return d.lightboxOpen && d.advEditOpen && !d._advEditCell &&
                !d._advEditBusy && d.currentLightboxVideo?.path === path;
        }""",
        arg=[ALPINE_ROOT_SELECTOR, state["new"]],
    )
    assert repaths == [{"path": old_uri, "new_path": typed, "confirm_name_change": False}]
    assert page.locator(VIDEO_CARD_SELECTOR).count() == cards_before
    expect(page.locator(".adv-edit-dialog")).to_have_class(re.compile("modal-open"))
    files_before = len(files)
    page.locator(".adv-edit-update").click()
    page.wait_for_function(
        """([selector, path]) => {
            const d = window.Alpine.$data(document.querySelector(selector));
            return d.lightboxOpen && d.currentLightboxVideo?.path === path && !d._advEditBusy;
        }""",
        arg=[ALPINE_ROOT_SELECTOR, state["new"]],
    )
    expect(page.locator(".adv-edit-update")).to_be_enabled()
    assert refreshes == [{"path": state["new"]}]
    assert len(files) > files_before and state["new"] in files[files_before:]
    assert page.locator(VIDEO_CARD_SELECTOR).count() == cards_before
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.keyboard.press("Escape")
    page.wait_for_function(
        """selector => {
            const d = window.Alpine.$data(document.querySelector(selector));
            return !d.advEditOpen && d.lightboxOpen;
        }""",
        arg=ALPINE_ROOT_SELECTOR,
    )
    assert not unexpected_writes
    assert not page_errors
