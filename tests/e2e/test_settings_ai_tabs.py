"""E2E：設定頁 AI 功能卡分頁切換與 localStorage 記憶（TASK-186-T2）。"""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_ai_tab_similar_persists_after_reload(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")

    page.locator("#aiTabSimilar").click()
    page.wait_for_function(
        "() => document.getElementById('aiPanelSimilar') "
        "&& getComputedStyle(document.getElementById('aiPanelSimilar')).display !== 'none'"
    )

    assert page.locator("#aiPanelTranslate").is_hidden()
    assert page.locator("#aiPanelSimilar").is_visible()
    assert page.evaluate("() => localStorage.getItem('settings_ai_tab')") == "similar"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")
    page.wait_for_function(
        "() => document.getElementById('aiPanelSimilar') "
        "&& getComputedStyle(document.getElementById('aiPanelSimilar')).display !== 'none'"
    )

    assert page.locator("#aiPanelTranslate").is_hidden()
    assert page.locator("#aiPanelSimilar").is_visible()


def test_ai_tab_faces_persists_after_reload(page: Page, base_url: str) -> None:
    """第三分頁 settle 後可見＋localStorage 記憶（TASK-187a-T5）。"""
    page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")

    page.locator("#aiTabFaces").click()
    page.wait_for_function(
        "() => document.getElementById('aiPanelFaces') "
        "&& getComputedStyle(document.getElementById('aiPanelFaces')).display !== 'none'"
    )

    assert page.locator("#aiPanelTranslate").is_hidden()
    assert page.locator("#aiPanelFaces").is_visible()
    assert page.evaluate("() => localStorage.getItem('settings_ai_tab')") == "faces"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")
    page.wait_for_function(
        "() => document.getElementById('aiPanelFaces') "
        "&& getComputedStyle(document.getElementById('aiPanelFaces')).display !== 'none'"
    )

    assert page.locator("#aiPanelTranslate").is_hidden()
    assert page.locator("#aiPanelFaces").is_visible()


def test_connection_area_shows_only_selected_provider(page: Page, base_url: str) -> None:
    """連線區只顯示目前翻譯服務那一家（TASK-186-T9）。不儲存。"""
    with page.expect_response(
        lambda r: r.url.rstrip("/").endswith("/api/config") and r.request.method == "GET"
    ):
        page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")

    page.locator("#aiTabTranslate").click()
    page.locator("#translateEnabled").check()

    providers = ("ollama", "gemini", "claude", "openai_official", "openai")
    alert_providers = {"gemini", "claude", "openai_official"}
    for provider in providers:
        page.locator("#translateProvider").select_option(provider)
        visible = page.locator("[data-ai-conn]:visible")
        expect(visible).to_have_count(1)
        expect(visible).to_have_attribute("data-ai-conn", provider)
        expect(page.locator("[data-ai-conn]")).to_have_count(5)
        expect(page.locator("#aiConnections .api-key-alert:visible")).to_have_count(
            1 if provider in alert_providers else 0
        )


def _open_settings(page: Page, base_url: str) -> None:
    with page.expect_response(
        lambda r: r.url.rstrip("/").endswith("/api/config") and r.request.method == "GET"
    ):
        page.goto(f"{base_url}/settings", wait_until="domcontentloaded")
    page.wait_for_selector("#aiServicesCard")


def test_connection_inputs_locked_when_translate_off(page: Page, base_url: str) -> None:
    """翻譯關閉時，連線區每家的輸入框與按鈕全部鎖住（TASK-186-T9）。不儲存。"""
    _open_settings(page, base_url)
    page.locator("#aiTabTranslate").click()
    for provider in ("ollama", "gemini", "claude", "openai_official", "openai"):
        page.locator("#translateEnabled").check()
        page.locator("#translateProvider").select_option(provider)
        page.locator("#translateEnabled").uncheck()
        visible = page.locator("[data-ai-conn]:visible")
        expect(visible).to_have_count(1)
        expect(visible).to_have_attribute("data-ai-conn", provider)
        controls = visible.locator("input, button").all()
        assert len(controls) >= 2, provider
        for el in controls:
            expect(el).to_be_disabled()
        expect(page.locator("#aiConnections")).to_have_class(re.compile(r"\bopacity-50\b"))


def test_connection_area_hidden_on_similar_tab(page: Page, base_url: str) -> None:
    """切到圖片相似分頁後，翻譯的連線區（含金鑰欄）整個不出現（TASK-186-T9）。不儲存。"""
    _open_settings(page, base_url)
    page.locator("#aiTabTranslate").click()
    page.locator("#translateEnabled").check()
    page.locator("#translateProvider").select_option("gemini")
    expect(page.locator("#geminiApiKey")).to_be_visible()

    page.locator("#aiTabSimilar").click()
    expect(page.locator("#aiConnections")).to_be_hidden()
    expect(page.locator("#aiConnections input:visible, #aiConnections button:visible")).to_have_count(0)

    page.locator("#aiTabTranslate").click()
    expect(page.locator("#geminiApiKey")).to_be_visible()


def test_similar_tab_hides_fields_when_switch_off(page: Page, base_url: str) -> None:
    """圖片相似開關關著時只有開關與兩顆鈕，網址／金鑰／模型名不出現（TASK-186-T9）。不儲存。"""
    _open_settings(page, base_url)
    page.locator("#aiTabSimilar").click()
    page.locator("#aiSimilarEnabled").uncheck()
    expect(page.locator("#aiSimilarEnabled")).not_to_be_checked()
    expect(page.locator("#aiSimilarUrl, #aiSimilarApiKey, #aiSimilarModel")).to_have_count(3)
    expect(page.locator("#aiSimilarUrl, #aiSimilarApiKey, #aiSimilarModel >> visible=true")).to_have_count(0)
    expect(page.locator("#aiSimilarAssistantBtn")).to_be_visible()

    page.locator("#aiSimilarEnabled").check()
    expect(page.locator("#aiSimilarUrl")).to_be_visible()


def test_rebuild_button_confirm_gate(page: Page, base_url: str) -> None:
    """「刪除並重建索引」：確認框按取消不送請求、接受才送一次；工作在跑時鈕不出現（TASK-186-T10）。不儲存。"""
    status = {"running": False, "indexed": 7, "unreadable": 0, "total": 7, "pending": 0,
              "model": "m", "complete": True, "model_changed": False, "unreachable": False}
    posts: list[str] = []

    def fake_config(route):
        cfg = route.fetch().json()
        cfg.setdefault("ai_services", {})["image_similar"] = {
            "enabled": True, "url": "http://embed.test", "api_key": "", "model": ""}
        route.fulfill(json=cfg)

    def fake_rebuild(route):
        posts.append(route.request.url)
        route.fulfill(json={"ok": True, "status": "started"})

    page.route(re.compile(r"/api/config$"), lambda r: fake_config(r) if r.request.method == "GET" else r.continue_())
    page.route("**/api/ai/similar/status", lambda r: r.fulfill(json=status))
    page.route("**/api/ai/similar/index/rebuild", fake_rebuild)
    _open_settings(page, base_url)
    page.locator("#aiTabSimilar").click()
    btn = page.locator("#aiSimilarRebuildBtn")
    expect(btn).to_be_visible()
    expect(btn).to_be_enabled()

    messages: list[str] = []

    def on_dialog(accept: bool):
        def handler(d):
            messages.append(d.message)
            d.accept() if accept else d.dismiss()
        return handler

    page.once("dialog", on_dialog(False))
    btn.click()
    expect(btn).to_be_enabled()  # settle：取消後沒有進入處理中
    assert len(messages) == 1 and "7" in messages[0] and posts == []

    page.once("dialog", on_dialog(True))
    with page.expect_request("**/api/ai/similar/index/rebuild"):
        btn.click()
    expect(btn).to_be_enabled()  # settle：請求已走完（route handler 已記錄）
    assert len(messages) == 2 and "7" in messages[1] and len(posts) == 1

    status["running"] = True  # 下一輪輪詢／切回分頁刷新 → 工作在跑
    page.locator("#aiTabTranslate").click()
    page.locator("#aiTabSimilar").click()
    expect(btn).to_be_hidden()
