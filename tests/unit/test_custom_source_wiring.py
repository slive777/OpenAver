"""165-T7a：custom:<id> 進 search_jav 的接線——gate 才放行、快照一致、auto 不碰、錯誤分類上拋。"""

import shutil

import pytest

import core.config as core_config
import core.scraper as scraper_mod
from core.config import load_config, save_config
from core.custom_source import gate, registry, state
from core.scrapers.errors import CustomSourceRefused, SourceParseEmpty
from core.scrapers.models import Video
from tests.unit._custom_source_fake import FakeTransport, finalize_root, page
from tests.unit._custom_source_pages import FIXTURE_DIR, PAGES

NUMBER = "SONE-205"
OG_URL = "https://single-og.example/sone-205"
TS_SEARCH = "https://two-step.example/search/SONE-205"
TS_UC = "https://two-step.example/video/sone-205uc/"
TS_C = "https://two-step.example/video/sone-205c/"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr("core.custom_source.fetch.rate_limit", lambda delay=0: None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(core_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "none.json")
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    finalize_root(root)
    save_config(load_config())
    load_config()
    return root


def _wire(monkeypatch, routes):
    transport = FakeTransport(routes)
    monkeypatch.setattr("core.custom_source.interpret.make_transport", lambda *a, **k: transport)
    return transport


def _put(root, name, text=None):
    d = root / "custom_sources"
    d.mkdir(exist_ok=True)
    if text is None:
        shutil.copy(FIXTURE_DIR / f"{name}.yaml", d / f"{name}.yaml")
    else:
        (d / f"{name}.yaml").write_text(text, encoding="utf-8")
    return d / f"{name}.yaml"


def _pass(sid, enabled=True):
    loaded = registry.load_one(sid)
    result = {"total": 1, "failed": 0, "cases": [{"index": 0, "number": NUMBER, "passed": True, "mismatches": []}]}
    assert state.record_result(sid, loaded.sha256, "passed", result, state.get_gen(sid))
    if enabled:
        assert state.set_enabled(sid, True, loaded.sha256)


def _ready_og(env, monkeypatch, routes=None):
    _put(env, "single-og")
    _pass("single-og")
    return _wire(monkeypatch, routes or {OG_URL: page(PAGES["single-og"])})


# ---- gate 四種拒絕：各用不同來源狀態（BE-TEST-23），不 stub check_usable ----

def _s_unverified(env):
    _put(env, "single-og")
    return "single-og", NUMBER


def _s_disabled(env):
    _put(env, "single-og")
    _pass("single-og", enabled=False)
    return "single-og", NUMBER


def _s_pattern(env):
    _put(env, "single-og")
    _pass("single-og")
    return "single-og", "FC2-123456"


def _s_load_failed(env):
    _put(env, "broken", "id: [unclosed\n")
    return "broken", NUMBER


@pytest.mark.parametrize("setup,reason", [
    (_s_unverified, "unverified"), (_s_disabled, "disabled"),
    (_s_pattern, "pattern_mismatch"), (_s_load_failed, "load_failed"),
])
def test_gate_refusals_raise_and_never_send(env, monkeypatch, setup, reason):
    sid, number = setup(env)
    transport = _wire(monkeypatch, {OG_URL: page(PAGES["single-og"])})
    calls = []
    real = gate.check_usable
    monkeypatch.setattr(gate, "check_usable", lambda *a, **k: calls.append(a) or real(*a, **k))
    with pytest.raises(CustomSourceRefused) as ei:
        scraper_mod.search_jav(number, source=f"custom:{sid}", surface_access_errors=True)
    assert ei.value.reason == reason
    assert scraper_mod.search_jav(number, source=f"custom:{sid}", surface_access_errors=False) is None
    assert calls, "真 gate 必須被呼叫"
    assert transport.calls == []


def test_not_loaded_is_refused_too(env, monkeypatch):
    transport = _wire(monkeypatch, {})
    with pytest.raises(CustomSourceRefused) as ei:
        scraper_mod.search_jav(NUMBER, source="custom:ghost", surface_access_errors=True)
    assert ei.value.reason == "not_loaded" and transport.calls == []


def test_passing_gate_sends_and_returns_dict(env, monkeypatch):
    transport = _ready_og(env, monkeypatch)
    result = scraper_mod.search_jav(NUMBER, source="custom:single-og", surface_access_errors=True)
    assert transport.calls == [OG_URL]
    assert result["_source"] == "custom:single-og"


@pytest.mark.parametrize("bad", ["custom:../x", "custom:", "custom:A"])
def test_malformed_ids_return_none_without_raise(env, monkeypatch, bad):
    transport = _wire(monkeypatch, {})
    assert scraper_mod.search_jav(NUMBER, source=bad, surface_access_errors=True) is None
    assert transport.calls == []


def test_gate_snapshot_survives_file_replacement(env, monkeypatch):
    path = _put(env, "single-og")
    _pass("single-og")
    swapped = "https://swapped.example/sone-205"
    transport = _wire(monkeypatch, {OG_URL: page(PAGES["single-og"]), swapped: page("<html>NEW</html>")})
    original = path.read_text(encoding="utf-8")
    real = gate.check_usable
    hits = []

    def spy(*a, **k):
        r = real(*a, **k)
        hits.append(r.ok)
        path.write_text(original.replace("single-og.example", "swapped.example"), encoding="utf-8")
        return r

    monkeypatch.setattr(gate, "check_usable", spy)
    result = scraper_mod.search_jav(NUMBER, source="custom:single-og", surface_access_errors=True)
    assert hits == [True]
    assert transport.calls == [OG_URL]
    assert result["_source"] == "custom:single-og"


def test_parse_empty_surfaces_only_when_requested(env, monkeypatch):
    _ready_og(env, monkeypatch, {OG_URL: page("<html><body>redesigned</body></html>")})
    with pytest.raises(SourceParseEmpty):
        scraper_mod.search_jav(NUMBER, source="custom:single-og", surface_access_errors=True)
    assert scraper_mod.search_jav(NUMBER, source="custom:single-og", surface_access_errors=False) is None


# ---- auto 路徑不碰 custom ----

def _fake_builtins(monkeypatch, record):
    for name in ("DMMScraper", "JavBusScraper", "JAV321Scraper", "JavDBScraper", "D2PassScraper",
                 "HEYZOScraper", "FC2OfficialScraper", "AVSOXScraper", "JavLibraryScraper", "FC2JavtenScraper"):
        def make(n):
            class Fake:
                def __init__(self, *a, **k):
                    record.append(("new", n))

                def search(self, number):
                    record.append(("search", n))
                    return None
            return Fake
        monkeypatch.setattr(f"core.scraper.{name}", make(name))


def _auto_record(monkeypatch):
    record = []
    _fake_builtins(monkeypatch, record)
    assert scraper_mod.search_jav(NUMBER, source="auto") is None
    return record


def test_auto_ignores_custom_files(env, monkeypatch):
    transport = _wire(monkeypatch, {})
    baseline = _auto_record(monkeypatch)
    assert len([r for r in baseline if r[0] == "search"]) >= 2
    _put(env, "single-og")
    _pass("single-og")
    assert _auto_record(monkeypatch) == baseline
    assert transport.calls == []


def test_broken_custom_does_not_spread(env, monkeypatch):
    transport = _wire(monkeypatch, {})
    baseline = _auto_record(monkeypatch)
    _put(env, "broken", "id: [unclosed\n")
    _put(env, "single-og")
    _pass("single-og")
    _put(env, "text")  # 未驗收
    assert _auto_record(monkeypatch) == baseline
    # 抓取丟例外的 custom 只影響自己
    monkeypatch.setattr("core.custom_source.interpret.make_transport",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert _auto_record(monkeypatch) == baseline
    assert transport.calls == []


# ---- 兩個 wrapper ----

def _two_step_ready(env, monkeypatch):
    _put(env, "two-step")
    _pass("two-step")
    return _wire(monkeypatch, {
        TS_SEARCH: page(PAGES["two-step-search"]),
        TS_UC: page(PAGES["two-step-detail-a"]), TS_C: page(PAGES["two-step-detail-b"]),
    })


def test_search_custom_versions_returns_two_legacy_dicts(env, monkeypatch):
    _two_step_ready(env, monkeypatch)
    versions = scraper_mod.search_custom_versions("custom:two-step", NUMBER)
    assert len(versions) == 2
    assert all(isinstance(v, dict) and v.get("number") for v in versions)


def test_fetch_custom_by_detail_url_same_site_and_cross_domain(env, monkeypatch):
    transport = _two_step_ready(env, monkeypatch)
    video = scraper_mod.fetch_custom_by_detail_url("custom:two-step", TS_UC, NUMBER)
    assert isinstance(video, Video) and video.source == "custom:two-step"
    transport.calls.clear()
    evil = "https://evil.example/video/x/"
    with pytest.raises(RuntimeError) as ei:
        scraper_mod.fetch_custom_by_detail_url("custom:two-step", evil, NUMBER)
    assert "blocked_target" in str(ei.value)
    assert transport.calls == []


@pytest.mark.parametrize("call", [
    lambda: scraper_mod.search_custom_versions("custom:single-og", NUMBER),
    lambda: scraper_mod.fetch_custom_by_detail_url("custom:single-og", OG_URL, NUMBER),
])
def test_wrappers_refuse_unverified(env, monkeypatch, call):
    _put(env, "single-og")
    transport = _wire(monkeypatch, {OG_URL: page(PAGES["single-og"])})
    with pytest.raises(CustomSourceRefused) as ei:
        call()
    assert ei.value.reason == "unverified" and transport.calls == []


# ---- access_error_info 顯示名 ----

def test_access_error_info_uses_yaml_name(env):
    _put(env, "single-og")
    info = scraper_mod.access_error_info(RuntimeError("x"), "custom:single-og")
    assert "Single OG" in info["message"] and info["source"] == "custom:single-og"


@pytest.mark.parametrize("src", ["custom:../x", "custom:", "custom:ghost", "custom:broken"])
def test_access_error_info_never_raises(env, src):
    _put(env, "broken", "id: [unclosed\n")
    info = scraper_mod.access_error_info(RuntimeError("x"), src)
    assert src in info["message"] and info["source"] == src
