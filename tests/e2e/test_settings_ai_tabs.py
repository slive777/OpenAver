"""E2E：設定頁 AI 功能卡分頁切換與 localStorage 記憶（TASK-186-T2）。"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

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
