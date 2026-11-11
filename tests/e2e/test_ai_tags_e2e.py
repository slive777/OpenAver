"""E2E：設定頁 AI 標籤連線區／狀態列＋燈箱 AI 鈕（TASK-188c-T14）。不儲存、不打真模型。"""
from __future__ import annotations

import json
import re
from contextlib import suppress

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e
ROOT = '[x-data="showcase"]'
CARD = ".av-card-preview[data-flip-id]"
IDLE = {
    "running": False, "job_kind": None, "done": 0, "skipped": 0, "slow": False,
    "waiting": False, "stop_reason": None, "outcome": None, "pending": 83,
    "total": 120, "tagged": 37, "resumable": False, "unreachable": False,
    "last_success_at": None,
}
def _fake_settings(page: Page, tags: dict, status: dict, forbidden: list) -> None:
    def cfg(route):
        if route.request.method != "GET":
            forbidden.append(route.request.url)
            route.abort()
            return
        # GET /api/config 形狀＝{success, data}；假設定寫進 data
        envelope = route.fetch().json()
        c = envelope["data"] if isinstance(envelope, dict) and "data" in envelope else envelope
        t = c.setdefault("translate", {})
        t["provider"], t["enabled"] = "ollama", False
        for n in ("gemini", "claude", "openai", "openai_official"):
            b = t.setdefault(n, {})
            b["api_key"] = b["base_url"] = ""
        c.setdefault("ai_services", {})["tags"] = dict(tags)
        route.fulfill(json=envelope)
    def block_tags_post(route):
        # POST backfill／rebuild／stop／test／videos：記錄並 abort，不到真後端
        if route.request.method == "POST":
            forbidden.append(route.request.url)
            route.abort()
            return
        route.fallback()
    page.on(
        "request",
        lambda r: forbidden.append(r.url)
        if r.method == "PUT" and r.url.rstrip("/").endswith("/api/config")
        else None,
    )
    page.route(re.compile(r"/api/config$"), cfg)
    page.route(re.compile(r"/api/(gemini|claude|openai|ollama)/"), lambda r: r.abort())
    page.route(re.compile(r"/api/ai/tags/"), block_tags_post)
    # 後註冊先匹配：GET status 走假回應，不受上列 POST abort 影響
    page.route("**/api/ai/tags/backfill/status", lambda r: r.fulfill(json=status))
def _settle_settings(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/settings#ai", wait_until="domcontentloaded")
    page.wait_for_function(
        "() => { const d = window.Alpine && Alpine.$data("
        "document.getElementById('settings-components'));"
        "return !!(d && d._configLoading === false && d.savedState); }"
    )
def _flag(page: Page, enabled: bool, provider: str = "") -> None:
    v = json.dumps({"enabled": enabled, "provider": provider})
    page.add_init_script(
        f"Object.defineProperty(window,'__SHOWCASE_AI_TAGS__',"
        f"{{configurable:true,get(){{return {v};}},set(){{}}}});"
    )
def _cover_a(page: Page, base_url: str) -> str | None:
    """回 A.path；片庫封面不足 → None（caller skip）；頁面／卡片載入失敗 → 拋錯 fail。"""
    resp = page.request.get(f"{base_url}/api/showcase/videos")
    assert resp.ok, f"GET /api/showcase/videos HTTP {resp.status}"
    videos = resp.json().get("videos", [])
    by = {v["path"]: v for v in videos}
    if sum(1 for v in videos if v.get("has_cover")) < 2:
        return None
    page.goto(f"{base_url}/showcase", wait_until="domcontentloaded")
    page.wait_for_selector(CARD, state="visible", timeout=15_000)
    paths = page.eval_on_selector_all(
        CARD, "els => els.slice(0,5).map(e => e.getAttribute('data-flip-id'))"
    )
    covers = [p for p in paths if by.get(p, {}).get("has_cover")]
    if len(covers) < 2:
        return None
    a = covers[0]
    return a if paths.index(a) + 1 < len(paths) else None
def _open_lb(page: Page, path: str) -> None:
    page.locator(f'.av-card-preview[data-flip-id="{path}"]').first.click()
    _wait_lb(page, path)
def _wait_lb(page: Page, path: str) -> None:
    """等 path＋_lbFullLoaded，且 .lb-title 標題文字對上該片（換片畫面更新完成）。"""
    page.wait_for_function(
        f"""() => {{
            const d = window.Alpine && Alpine.$data(document.querySelector('{ROOT}'));
            if (!(d && d.lightboxOpen && d._lbFullLoaded && d.currentLightboxVideo
                  && d.currentLightboxVideo.path === {json.dumps(path)})) return false;
            const want = d.currentLightboxVideo.title || '';
            const el = document.querySelector('.lb-title span');
            return !!(el && el.textContent === (want || el.textContent));
        }}""",
        timeout=15_000,
    )
def _path(page: Page) -> str:
    return page.evaluate(
        f"() => {{ const d = Alpine.$data(document.querySelector('{ROOT}'));"
        f"return (d.currentLightboxVideo && d.currentLightboxVideo.path) || ''; }}"
    )
def _tags(page: Page) -> list[str]:
    return page.locator(".lbx-tag-right a.lbx-utag-link span").all_inner_texts()
def _open_tag_input(page: Page) -> None:
    """按「＋」展開輸入區（AI 判斷鈕藏在展開區裡）。"""
    page.locator(".lbx-tag-plus").click()
    expect(page.locator(".lbx-tag-input")).to_be_visible()
def test_tags_conn_area_shows_only_tags_provider_editable(page: Page, base_url: str) -> None:
    """翻譯關、只開 AI 標籤選 Gemini → 標籤分頁卡底只剩 Gemini 一家且可打字（翻譯選的 Ollama 不列）。"""
    bad: list[str] = []
    _fake_settings(page, {"enabled": False, "provider": "", "model": ""}, dict(IDLE), bad)
    _settle_settings(page, base_url)
    page.locator("#aiTabTags").click()
    page.wait_for_selector("#aiPanelTags", state="visible")
    page.locator("#aiTagsEnabled").check()
    expect(page.locator("#aiTagsProvider")).to_have_value("ollama")
    page.locator("#aiTagsProvider").select_option("gemini")
    vis = page.locator("[data-ai-conn]:visible")
    expect(vis).to_have_count(1)
    expect(vis).to_have_attribute("data-ai-conn", "gemini")
    for el in page.locator('[data-ai-conn="gemini"] input, [data-ai-conn="gemini"] button').all():
        expect(el).to_be_enabled()
    page.locator("#geminiApiKey").fill("e2e-gemini-key")
    expect(page.locator("#geminiApiKey")).to_have_value("e2e-gemini-key")
    expect(page.locator('[data-ai-conn="ollama"]')).to_be_hidden()
    expect(page.locator("#aiConnections")).not_to_have_class(re.compile(r"\bopacity-50\b"))
    assert bad == []
def test_tags_settings_loaded_not_dirty(page: Page, base_url: str) -> None:
    """已開 AI 標籤載入後 isDirty 乾淨、補完全庫可按、無「先儲存」。"""
    bad: list[str] = []
    tags = {"enabled": True, "provider": "gemini", "model": "gemini-flash-lite-latest"}
    _fake_settings(page, tags, dict(IDLE), bad)
    _settle_settings(page, base_url)
    with page.expect_response("**/api/ai/tags/backfill/status"):
        page.locator("#aiTabTags").click()
    expect(page.locator("#aiTagsRunBtn")).to_be_visible()
    expect(page.locator("#aiTagsRunBtn")).to_be_enabled()
    expect(page.locator(".ai-tags-save-first")).to_be_hidden()
    assert page.evaluate(
        "() => Alpine.$data(document.getElementById('settings-components')).isDirty"
    ) is False
    assert bad == []
def test_tags_progress_line_and_first_run_hint_share_pending(page: Page, base_url: str) -> None:
    """跑中只留進度行（37／120）；跑完後「還有 83 部沒跑」與開關旁句子同一個 N，並接費用半句；舊費用行已不存在。"""
    bad: list[str] = []
    st = {**IDLE, "running": True, "job_kind": "build", "done": 5}
    tags = {"enabled": True, "provider": "gemini", "model": "gemini-flash-lite-latest"}
    _fake_settings(page, tags, st, bad)
    _settle_settings(page, base_url)
    page.locator("#aiTabTags").click()
    page.wait_for_selector("#aiPanelTags", state="visible")
    expect(page.locator("#aiTagsProgressLine")).to_contain_text("37")
    expect(page.locator("#aiTagsProgressLine")).to_contain_text("120")
    expect(page.locator("#aiTagsStatusLine")).to_be_hidden()
    expect(page.locator("#aiTagsFirstRunHint")).to_contain_text("83")
    expect(page.locator("#aiTagsStopBtn")).to_be_visible()
    st["running"] = False
    pending = page.locator("#aiTagsPendingLine")
    expect(pending).to_have_text(re.compile(r"^還有 83 部沒跑"))
    expect(pending).to_contain_text("USD")
    expect(page.locator("#aiTagsRunBtn")).to_be_visible()
    expect(page.locator("#aiTagsRunBtn")).to_be_enabled()
    assert page.locator("#aiPanelTags >> text=USD >> visible=true").count() == 1  # 費用只在這一行
    h = re.search(r"\d+", page.locator("#aiTagsFirstRunHint").inner_text())
    p = re.search(r"\d+", pending.inner_text())
    assert h and p and h.group() == p.group() == "83"
    assert bad == []


def _tags_rebuild_dialog(page: Page, base_url: str, tags: dict, status: dict) -> str:
    """進 AI 標籤分頁、按「全部重建」，取確認視窗字後取消（不送請求）。"""
    bad: list[str] = []
    _fake_settings(page, tags, status, bad)
    _settle_settings(page, base_url)
    page.locator("#aiTabTags").click()
    page.wait_for_selector("#aiPanelTags", state="visible")
    msgs: list[str] = []
    page.once("dialog", lambda d: (msgs.append(d.message), d.dismiss()))
    page.locator("#aiTagsRebuildBtn").click()
    expect(page.locator("#aiTagsRebuildBtn")).to_be_enabled()
    assert len(msgs) == 1 and bad == [], (msgs, bad)
    return msgs[0]


def test_tags_cost_one_line_and_rebuild_confirm_amount(page: Page, base_url: str) -> None:
    """有費用規則的連線家：確認視窗寫「會對 120 部…大約 USD」，金額＝120 部的（不是 83 部的）；0 部沒跑整頁無 USD。"""
    tags = {"enabled": True, "provider": "gemini", "model": "gemini-flash-lite-latest"}
    msg = _tags_rebuild_dialog(page, base_url, tags, dict(IDLE))
    assert "會對 120 部再請 AI 看一次，大約 USD $0.09" in msg, msg  # 0.72 * 120 / 1000
    assert "USD $0.06" in page.locator("#aiTagsPendingLine").inner_text()  # 83 部 ≈ 0.0598


def test_tags_cost_hidden_without_pending_or_rule(page: Page, base_url: str) -> None:
    """沒有待補、或連線家不屬費用規則（ollama）時：畫面與確認視窗都沒有 USD／NaN，確認視窗用原文。"""
    ctx = page.context
    p0 = ctx.new_page()
    tags = {"enabled": True, "provider": "gemini", "model": "gemini-flash-lite-latest"}
    msg0 = _tags_rebuild_dialog(p0, base_url, tags, {**IDLE, "pending": 0, "tagged": 120})
    assert "USD" in msg0  # 重建仍有金額；待補為 0 時整頁（含「還有 N 部」那行）不出現 USD
    expect(p0.locator("#aiTagsPendingLine")).to_be_hidden()
    assert p0.locator("text=USD >> visible=true").count() == 0
    p0.close()
    p1 = ctx.new_page()
    msg1 = _tags_rebuild_dialog(p1, base_url, {"enabled": True, "provider": "ollama", "model": "llava"}, dict(IDLE))
    assert "120" in msg1 and "USD" not in msg1 and "NaN" not in msg1, msg1
    pending = p1.locator("#aiTagsPendingLine")
    expect(pending).to_have_text("還有 83 部沒跑")
    p1.close()


def test_lightbox_ai_button_follows_flag_beside_plus(page: Page, base_url: str) -> None:
    """旗標關無 AI 鈕；旗標開展開前看不到、展開後恰一顆且在輸入框右側同一列。"""
    ctx = page.context
    path_a = _cover_a(page, base_url)
    if not path_a:
        pytest.skip("片庫封面片不足 2（API／DOM 前 5 張確認）")
    off = ctx.new_page()
    _flag(off, False)
    off.goto(f"{base_url}/showcase", wait_until="domcontentloaded")
    off.wait_for_selector(CARD, state="visible", timeout=15_000)
    _open_lb(off, path_a)
    expect(off.locator(".lb-tag-ai-btn:visible")).to_have_count(0)
    off.close()
    on = ctx.new_page()
    _flag(on, True, "gemini")
    on.goto(f"{base_url}/showcase", wait_until="domcontentloaded")
    on.wait_for_selector(CARD, state="visible", timeout=15_000)
    _open_lb(on, path_a)
    expect(on.locator(".lb-tag-ai-btn:visible")).to_have_count(0)
    _open_tag_input(on)
    ai, inp = on.locator(".lb-tag-ai-btn:visible"), on.locator(".lbx-tag-input:visible")
    expect(ai).to_have_count(1)
    ab, ib = ai.bounding_box(), inp.bounding_box()
    assert ab and ib and ab["x"] > ib["x"] and abs(ab["y"] - ib["y"]) < 24
    on.close()
def test_lightbox_ai_result_lands_on_original_video(page: Page, base_url: str) -> None:
    """按下 AI 鈕後換片：結果寫回 A，B 不被蓋；toast 含 3。"""
    ctx = page.context
    path_a = _cover_a(page, base_url)
    if not path_a:
        pytest.skip("片庫封面片不足 2（API／DOM 前 5 張確認）")
    p = ctx.new_page()
    _flag(p, True, "gemini")
    held: list = []
    # 後註冊先匹配：本測試持有 POST videos；其餘 tags POST 仍由設定頁慣例 abort 不適用於此頁
    p.route(
        "**/api/ai/tags/videos",
        lambda r: held.append(r) if r.request.method == "POST" else r.fallback(),
    )
    added = ["E2E-AI-alpha", "E2E-AI-beta", "E2E-AI-gamma"]
    body = {
        "success": True, "added": added, "refused": False, "user_tags": added,
        "nfo_updated": False, "readonly_no_output": False, "nfo_write_blocked": False,
    }
    done = False
    try:
        p.goto(f"{base_url}/showcase", wait_until="domcontentloaded")
        p.wait_for_selector(CARD, state="visible", timeout=15_000)
        _open_lb(p, path_a)
        _open_tag_input(p)
        btn = p.locator(".lb-tag-ai-btn")
        expect(btn).to_be_visible()
        btn.click()
        expect(btn).to_be_disabled()
        expect(btn).to_have_attribute("aria-busy", "true")
        expect(p.locator(".lb-tag-ai-btn .spin")).to_be_visible()
        p.keyboard.press("ArrowRight")
        p.wait_for_function(
            f"() => {{ const d = Alpine.$data(document.querySelector('{ROOT}'));"
            f"return !!(d && d.currentLightboxVideo &&"
            f" d.currentLightboxVideo.path !== {json.dumps(path_a)}); }}",
            timeout=15_000,
        )
        path_b = _path(p)
        assert path_b and path_b != path_a
        _wait_lb(p, path_b)
        expect(p.locator(".lb-tag-ai-btn")).to_be_enabled()
        snap = _tags(p)
        assert len(held) == 1
        held[0].fulfill(json=body)
        done = True
        expect(p.locator(".fluent-toast:visible")).to_contain_text("3")
        assert _tags(p) == snap and _path(p) == path_b
        p.keyboard.press("ArrowLeft")
        _wait_lb(p, path_a)
        expect(p.locator(".lbx-tag-right a.lbx-utag-link span")).to_have_text(added)
        assert json.loads(held[0].request.post_data or "{}").get("file_path") == path_a
        assert len(held) == 1
    finally:
        if held and not done:
            with suppress(Exception):
                held[0].fulfill(json=body)
        p.close()
