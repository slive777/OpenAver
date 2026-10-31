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
