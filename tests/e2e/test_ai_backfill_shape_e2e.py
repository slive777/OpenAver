"""E2E：設定頁 AI 三分頁補跑列形狀一致、停止→繼續不重來（TASK-189a-T13）。只攔自家端點、不改真設定。"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e
TS = 1_700_000_000
SUF = ("ProgressLine", "StopBtn", "RunBtn", "RebuildBtn", "PendingLine")


def _snaps(base: dict, key: str, extra: dict) -> dict:
    """四個快照：idle(4/10,待6)、running(5/10)、stopped(5/10)、done(10/10)。"""
    mk = lambda n, **kw: {**base, key: n, "pending": 10 - n, **kw}  # noqa: E731
    return {
        "idle": mk(4, **extra.get("idle", {})), "running": mk(5, running=True, **extra.get("running", {})),
        "stopped": mk(5, **extra.get("stopped", {})), "done": mk(10, **extra.get("done", {})),
    }


_SIM = {"total": 10, "unreadable": 0, "model": "m", "model_changed": False, "unreachable": False,
        "running": False, "complete": False, "last_success_at": None}
_FACE = {"total": 10, "unreadable": 0, "target_model": "m", "rebuild_count": 10, "stopped_reason": None,
         "kind": None, "check": None, "running": False}
_TAGS = {"total": 10, "running": False, "job_kind": None, "done": 0, "skipped": 0, "slow": False,
         "waiting": False, "stop_reason": None, "outcome": None, "resumable": False,
         "unreachable": False, "last_success_at": None}
# idle／stopped 的主鈕 data-action 以 T10 對映表為準：只有「中途停下」(resumable) 才是 continue
TABS = {
    "aiSimilar": {
        "btn": "#aiTabSimilar", "cfg": "image_similar", "ui": {"url": "http://embed.test", "api_key": "", "model": ""},
        "api": {"status": "/api/ai/similar/status", "start": "/api/ai/similar/index",
                "stop": "/api/ai/similar/index/stop", "rebuild": "/api/ai/similar/index/rebuild"},
        "snap": _snaps(_SIM, "indexed", {"running": {"last_success_at": TS}, "done": {"complete": True}}),
        "act": {"idle": "continue", "stopped": "continue"},
    },
    "aiFaces": {
        "btn": "#aiTabFaces", "cfg": "faces", "ui": {"url": "http://faces.test", "api_key": "", "model": ""},
        "api": {"status": "/api/ai/faces/status", "start": "/api/ai/faces/recompute",
                "stop": "/api/ai/faces/recompute/stop", "rebuild": "/api/ai/faces/rebuild"},
        "snap": _snaps(_FACE, "processed", {"stopped": {"stopped_reason": "unreachable"}}),
        "act": {"idle": "start", "stopped": "continue"},
    },
    "aiTags": {
        "btn": "#aiTabTags", "cfg": "tags", "ui": {"provider": "gemini", "model": "gemini-flash-lite-latest"},
        "api": {"status": "/api/ai/tags/backfill/status", "start": "/api/ai/tags/backfill",
                "stop": "/api/ai/tags/backfill/stop", "rebuild": "/api/ai/tags/backfill/rebuild"},
        "snap": _snaps(_TAGS, "tagged", {"running": {"job_kind": "build", "last_success_at": TS},
                                          "stopped": {"resumable": True}}),
        "act": {"idle": "start", "stopped": "continue"},
    },
}


class Harness:
    """假後端：每分頁一份狀態；POST start/stop 切狀態並記進 posts；其餘非 GET 一律 forbidden＋abort。"""

    def __init__(self, page: Page) -> None:
        self.page, self.forbidden, self.posts, self.gets, self.bad, self.dialogs = page, [], [], [], [], []
        self.st = {k: dict(t["snap"]["idle"]) for k, t in TABS.items()}
        self.hit = {t["api"][a]: (k, a) for k, t in TABS.items() for a in t["api"]}
        page.on("console", self._console)
        page.on("pageerror", lambda e: self.bad.append(f"pageerror: {e}"))
        page.on("dialog", lambda d: (self.dialogs.append(d.message), d.dismiss()))
        page.on("request", lambda r: self.forbidden.append(r.url)
                if r.method == "PUT" and r.url.rstrip("/").endswith("/api/config") else None)
        page.route(re.compile(r"/api/config$"), self._config)
        # 連線測試／模型清單一律回空 200（abort 會讓瀏覽器自己印 ERR_FAILED，污染 console 斷言）
        page.route(re.compile(r"/api/(gemini|claude|openai|ollama)/"), lambda r: r.fulfill(json={"models": []}))
        page.route("**/api/ai/**", self._guard)  # 先註冊＝後匹配
        page.route("**/api/ai/**", self._fake)

    def _console(self, m) -> None:
        txt = m.text
        if m.type == "error" or (m.type == "warning" and ("Alpine Expression Error" in txt or "is not defined" in txt)):
            self.bad.append(f"console.{m.type}: {txt}")

    def _config(self, route) -> None:
        if route.request.method != "GET":
            self.forbidden.append(route.request.url)
            return route.abort()
        env = route.fetch().json()
        c = env["data"] if isinstance(env, dict) and "data" in env else env
        tr = c.setdefault("translate", {})
        tr["provider"], tr["enabled"] = "ollama", False
        for n in ("gemini", "claude", "openai", "openai_official"):
            b = tr.setdefault(n, {})
            b["api_key"] = b["base_url"] = ""
        for t in TABS.values():
            c.setdefault("ai_services", {})[t["cfg"]] = {"enabled": True, **t["ui"]}
        route.fulfill(json=env)

    def _guard(self, route) -> None:
        if route.request.method != "GET":
            self.forbidden.append(f"{route.request.method} {route.request.url}")
            return route.abort()
        route.fallback()

    def _fake(self, route) -> None:
        hit = self.hit.get(urlparse(route.request.url).path)
        if not hit:
            return route.fallback()
        k, act = hit
        # status 只收 GET、其餘只收 POST；方法不對交給 _guard 記入 forbidden
        if route.request.method != ("GET" if act == "status" else "POST"):
            return route.fallback()
        if act == "status":
            self.gets.append(k)
            return route.fulfill(json=self.st[k])
        self.posts.append(f"{k}:{act}")
        if act in ("start", "stop"):
            self.st[k] = dict(TABS[k]["snap"]["running" if act == "start" else "stopped"])
        route.fulfill(json={"ok": True, "status": "started"})

    def load(self, base_url: str) -> None:
        p = self.page
        p.goto(f"{base_url}/settings#ai", wait_until="domcontentloaded")
        p.wait_for_function("() => { const d = window.Alpine && Alpine.$data(document.getElementById("
                            "'settings-components')); return !!(d && d._configLoading === false && d.savedState); }")
        assert p.evaluate("() => Alpine.$data(document.getElementById('settings-components')).isDirty") is False

    def visit(self, k: str, fresh: bool = False) -> None:
        """進分頁並等一次 status；fresh=True 先切到翻譯分頁再回來，逼 bfRefresh 重抓。"""
        if fresh:
            self.page.locator("#aiTabTranslate").click()
            expect(self.page.locator("#aiPanelTranslate")).to_be_visible()
        with self.page.expect_response(f"**{TABS[k]['api']['status']}"):
            self.page.locator(TABS[k]["btn"]).click()

    def t(self, key: str, **params) -> str:
        s = self.page.evaluate("([k, p]) => window.t(k, p)", [key, params])
        assert not s.startswith("["), f"missing i18n key {key}"
        return s

    def el(self, k: str, suf: str):
        return self.page.locator(f"#{k}{suf}")

    def settle(self) -> None:
        """往返一趟，確保已送出的請求事件都進了計數。"""
        self.page.evaluate("() => new Promise(r => setTimeout(r, 0))")


_ORDER_JS = """([k, sufs]) => {
  const els = sufs.map(s => document.getElementById(k + s));
  const run = els[2], row = run.parentElement;
  return {
    order: sufs.slice().sort((a, b) => (document.getElementById(k + a).compareDocumentPosition(
      document.getElementById(k + b)) & 4 ? -1 : 1)),
    sameRow: [els[1], els[2], els[3], els[4]].every(e => e.parentElement === row),
    progressBeforeRow: els[0].nextElementSibling === row,
    retryBetween: !!(document.getElementById(k + 'RetryBtn')
      && run.nextElementSibling === document.getElementById(k + 'RetryBtn')
      && document.getElementById(k + 'RetryBtn').nextElementSibling === els[3]),
  };
}"""
# 位置以「所在按鈕列」為原點：跑時進度列會出現在按鈕列上方、把整列往下推（見 DEVIATIONS），列內槽位才是這裡守的
_REL_JS = """(id) => { const e = document.getElementById(id), p = e.parentElement.getBoundingClientRect(),
  r = e.getBoundingClientRect(); return {x: r.left - p.left, y: r.top - p.top, right: r.right}; }"""


def test_backfill_row_same_shape_on_three_tabs(page: Page, base_url: str) -> None:
    """三分頁補跑列鈕位置／順序不同、跑時停止鈕換地方、窄螢幕按鈕被裁掉，使用者要學三套。"""
    h = Harness(page)
    h.load(base_url)
    vp = page.viewport_size
    for k, tab in TABS.items():
        h.visit(k)
        shape = page.evaluate(_ORDER_JS, [k, list(SUF)])
        assert shape["order"] == list(SUF) and shape["sameRow"] and shape["progressBeforeRow"], (k, shape)
        assert shape["retryBetween"] == (k == "aiSimilar"), (k, shape)
        run = h.el(k, "RunBtn")
        expect(run).to_be_visible()
        expect(run).to_be_enabled()
        expect(run).to_have_attribute("data-action", tab["act"]["idle"])
        expect(h.el(k, "StopBtn")).to_be_hidden()
        expect(h.el(k, "ProgressLine")).to_be_hidden()
        expect(h.el(k, "RebuildBtn")).to_be_visible()
        expect(h.el(k, "PendingLine")).to_be_visible()
        expect(h.el(k, "PendingLine")).to_have_text(re.compile("^" + re.escape(h.t("settings.ai.backfill.pending_line", n=6))))
        expect(page.locator(".ai-similar-save-first:visible, .ai-tags-save-first:visible")).to_have_count(0)
        run_pos = page.evaluate(_REL_JS, f"{k}RunBtn")
        # 390 寬：主鈕與重建鈕右緣不被裁
        page.set_viewport_size({"width": 390, "height": 844})
        for suf in ("RunBtn", "RebuildBtn"):
            assert page.evaluate(_REL_JS, f"{k}{suf}")["right"] <= 390, (k, suf)
        page.set_viewport_size(vp)
        # running：停止鈕站在主鈕位置，主鈕與「還有 N 部」消失，進度列出現
        h.st[k] = dict(tab["snap"]["running"])
        h.visit(k, fresh=True)
        expect(h.el(k, "StopBtn")).to_be_visible()
        expect(run).to_be_hidden()
        expect(h.el(k, "PendingLine")).to_be_hidden()
        expect(h.el(k, "RebuildBtn")).to_be_hidden()
        expect(h.el(k, "ProgressLine")).to_be_visible()
        expect(h.el(k, "ProgressLine")).to_contain_text(h.t("settings.ai.backfill.progress_running", n=5, m=10))
        stop_pos = page.evaluate(_REL_JS, f"{k}StopBtn")
        assert abs(stop_pos["x"] - run_pos["x"]) <= 2 and abs(stop_pos["y"] - run_pos["y"]) <= 2, (k, run_pos, stop_pos)
        # done：輪詢帶回完成狀態 → 主鈕／停止／進度／待補全消失，重建仍在
        h.st[k] = dict(tab["snap"]["done"])
        expect(h.el(k, "StopBtn")).to_be_hidden()
        for suf in ("RunBtn", "ProgressLine", "PendingLine"):
            expect(h.el(k, suf)).to_be_hidden()
        expect(h.el(k, "RebuildBtn")).to_be_visible()
    assert h.forbidden == [] and h.bad == [], (h.forbidden, h.bad)


def test_stop_then_continue_posts_start_not_rebuild(page: Page, base_url: str) -> None:
    """按「停止」後再按「繼續」卻重來（走全部重建、跳刪除確認、進度歸零）或停止鈕沒停。"""
    h = Harness(page)
    h.load(base_url)
    for k, tab in TABS.items():
        h.visit(k)
        h.posts.clear()
        prog = h.el(k, "ProgressLine")
        want = h.t("settings.ai.backfill.progress_running", n=5, m=10)
        expect(h.el(k, "RunBtn")).to_have_attribute("data-action", tab["act"]["idle"])
        h.el(k, "RunBtn").click()
        expect(h.el(k, "StopBtn")).to_be_visible()
        expect(prog).to_be_visible()
        expect(prog).to_contain_text(want)
        h.el(k, "StopBtn").click()
        expect(h.el(k, "RunBtn")).to_be_visible()
        expect(h.el(k, "RunBtn")).to_have_attribute("data-action", tab["act"]["stopped"])
        expect(h.el(k, "PendingLine")).to_be_visible()
        expect(h.el(k, "PendingLine")).to_have_text(re.compile("^" + re.escape(h.t("settings.ai.backfill.pending_line", n=5))))
        h.el(k, "RunBtn").click()
        expect(h.el(k, "StopBtn")).to_be_visible()
        expect(prog).to_be_visible()
        expect(prog).to_contain_text(want)  # 繼續後進度沒歸零
        assert h.posts == [f"{k}:start", f"{k}:stop", f"{k}:start"], (k, h.posts)
        assert h.dialogs == [], (k, h.dialogs)
        # 離開分頁：背景不再打 status（輪詢週期 1 秒，等兩個週期）
        page.locator("#aiTabTranslate").click()
        expect(page.locator("#aiPanelTranslate")).to_be_visible()
        h.settle()
        base = h.gets.count(k)  # 基準取在「已離開、請求事件已落地」之後
        page.wait_for_timeout(2500)
        assert h.gets.count(k) == base, (k, base, h.gets.count(k))
        # 回分頁：立刻重抓、仍在 running；之後被帶到 done 時待補消失、重建仍在
        h.visit(k)
        assert h.gets.count(k) > base
        expect(h.el(k, "StopBtn")).to_be_visible()
        h.st[k] = dict(tab["snap"]["done"])
        expect(h.el(k, "RunBtn")).to_be_hidden()
        expect(h.el(k, "PendingLine")).to_be_hidden()
        expect(h.el(k, "RebuildBtn")).to_be_visible()
    assert h.forbidden == [] and h.bad == [], (h.forbidden, h.bad)


_LINE = {"aiSimilar": "aiSimilarStatusLine", "aiFaces": "aiFacesRecomputeLine", "aiTags": "aiTagsStatusLine"}


def test_running_shows_one_progress_line_and_idle_one_pending(page: Page, base_url: str) -> None:
    """補跑中「已處理」出現兩次（進度行＋舊狀態行）、閒置時待處理數字出現兩次，使用者看到重複的同一件事。"""
    h = Harness(page)
    h.load(base_url)
    for k, tab in TABS.items():
        h.st[k] = dict(tab["snap"]["running"])
        h.visit(k, fresh=True)
        expect(h.el(k, "ProgressLine")).to_be_visible()
        expect(h.el(k, "ProgressLine")).to_contain_text(h.t("settings.ai.backfill.progress_running", n=5, m=10))
        expect(page.locator(f"#{_LINE[k]}")).to_be_hidden()
        assert page.locator("text=已處理 >> visible=true").count() == 1, k
        assert page.locator("text=重新對焦中 >> visible=true").count() == 0, k
    h.visit("aiFaces", fresh=True)
    expect(page.locator("#aiFacesStatusLine")).to_be_visible()  # 「目前使用…」非重述，仍在
    for k, tab in TABS.items():
        h.st[k] = dict(tab["snap"]["idle"])
        h.visit(k, fresh=True)
        expect(h.el(k, "PendingLine")).to_be_visible()
        expect(h.el(k, "PendingLine")).to_have_text(re.compile("^" + re.escape(h.t("settings.ai.backfill.pending_line", n=6))))
        assert page.locator("text=待處理 >> visible=true").count() == 0, k
    assert h.forbidden == [] and h.bad == [], (h.forbidden, h.bad)


def test_non_restating_sentences_still_rendered(page: Page, base_url: str) -> None:
    """標籤放慢／額度用完／連不上、相似封面讀不到、人臉端點停了，併入單行後畫面不說原因，使用者以為卡住。"""
    h = Harness(page)
    h.load(base_url)
    idle = lambda k, **kw: {**TABS[k]["snap"]["idle"], **kw}  # noqa: E731
    running = lambda k, **kw: {**TABS[k]["snap"]["running"], **kw}  # noqa: E731
    cases = [
        ("aiTags", running("aiTags", slow=True), "ProgressLine", "服務要求放慢"),
        ("aiTags", running("aiTags", waiting=True), "ProgressLine", "等待中"),
        ("aiTags", running("aiTags", skipped=2), "ProgressLine", "沒標成"),
        ("aiTags", idle("aiTags", stop_reason="quota"), "StatusLine", "服務額度用完"),
        ("aiTags", idle("aiTags", stop_reason="auth"), "StatusLine", "金鑰被拒"),
        ("aiTags", idle("aiTags", unreachable=True), "StatusLine", "目前連不上"),
        ("aiSimilar", idle("aiSimilar", unreadable=3), "StatusLine", "封面讀不到"),
        ("aiFaces", idle("aiFaces", stopped_reason="unreachable"), "RecomputeLine", "重新對焦已停止：端點連不上"),
        ("aiFaces", idle("aiFaces", stopped_reason="contract"), "RecomputeLine", "不符契約"),
    ]
    for k, snap, where, text in cases:
        h.st[k] = snap
        h.visit(k, fresh=True)
        loc = h.el(k, where) if where == "ProgressLine" else page.locator(f"#{k}{where}")
        expect(loc).to_be_visible()
        expect(loc).to_contain_text(text)
    assert h.forbidden == [] and h.bad == [], (h.forbidden, h.bad)
