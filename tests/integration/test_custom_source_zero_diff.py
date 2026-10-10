"""CD-165-2 零自訂來源 oracle：SSR 合成只在讀取邊界做；沒用過自訂來源的人拿到的與升級前（35a9cb70）逐位元組相同。全離線。"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

import core.access_auth as access_auth
from core import config as core_config
from core.config import load_config, save_config
from core.custom_source import registry, state
from core.metatube.state import metatube_state
from tests.unit._custom_source_fake import finalize_root, put_source
from tests.unit._custom_source_pages import FIXTURE_DIR

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "custom_sources"
GOLDEN = FIXTURES / "zero_diff_golden.json"
REGEN = FIXTURES / "regen_zero_diff_golden.py"
SINGLE = (FIXTURE_DIR / "single-og.yaml").read_text(encoding="utf-8")
PAGES = ["/search", "/showcase"]  # 有注入 __ADVANCED_SEARCH__ 的頁面
RENDER_PAGES = ["/settings", *PAGES]
REGEN_SCRIPT = "/home/peace/OpenAver/tests/fixtures/custom_sources/regen_zero_diff_golden.py"
REGEN_STEPS = (
    "重產 golden 的步驟：git clone --local /home/peace/OpenAver \"$HOME/.cache/openaver-golden-35a9cb70\"（必須在 $HOME 下，不是 /tmp）"
    " → git -C 該目錄 checkout 35a9cb70 → cd 該目錄 → PYTHONPATH=$PWD <venv>/bin/python "
    + REGEN_SCRIPT + " /home/peace/OpenAver/tests/fixtures/custom_sources/zero_diff_golden.json"
    "（腳本用本 repo 的絕對路徑，clone 內不需要有它）"
)


def _load_regen():
    spec = importlib.util.spec_from_file_location("regen_zero_diff_golden", REGEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _capture(client):
    return _load_regen().capture(client)


@pytest.fixture(autouse=True)
def _isolated_access_auth(tmp_path, monkeypatch):
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access_auth_zero_diff.db")
    access_auth.reset_state_for_tests()
    access_auth.ensure_schema()
    yield
    access_auth.reset_state_for_tests()


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    save_config(load_config())
    save_config(load_config())  # 不動點：migration 不會讓之後的 bytes 變動
    finalize_root(root)
    return root


@pytest.fixture(params=["absent", "empty"])
def zero_env(request, env):
    if request.param == "empty":
        (env / "custom_sources").mkdir()
    return env


def _ready(env, sid, text, enable=True):
    put_source(env, sid, text)
    sha = registry.load_one(sid).sha256
    assert state.record_result(sid, sha, "passed", {"total": 1, "failed": 0, "cases": []}, state.get_gen(sid))
    if enable:
        assert state.set_enabled(sid, True, sha)


def _yaml(text, sid):
    return text.replace("id: single-og", f"id: {sid}", 1)


def _ssr_sources(client, path="/search"):
    resp = client.get(path)
    assert resp.status_code == 200, path
    m = re.search(r"sources: (.*?),\n\s+cf_transport_available", resp.text, re.S)
    assert m, f"{path} 缺 __ADVANCED_SEARCH__.sources"
    return json.loads(m.group(1))


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _legacy_sources():
    """165 之前的暫態欄位迴圈（4 行重現）。"""
    cfg = load_config()
    avail, connected = metatube_state.availability_map(), metatube_state.is_connected
    for s in cfg.get("sources") or []:
        mt = isinstance(s.get("id"), str) and s["id"].startswith("metatube:")
        s["routable"] = connected if mt else True
        s["available"] = avail.get(s["id"], False) if mt else True
    return cfg.get("sources")


def _config_bytes():
    return core_config.CONFIG_PATH.read_bytes()


def _customs(sources):
    return [s for s in sources if s.get("type") == "custom"]


# ---------- 零自訂：①②③ ----------

def test_zero_custom_ssr_matches_legacy_loop(client, zero_env):
    legacy = _dump(_legacy_sources())
    for path in PAGES:
        sources = _ssr_sources(client, path)
        assert _customs(sources) == []
        assert _dump(sources) == legacy, path


def test_zero_custom_api_matches_golden(client, zero_env):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["baseline_commit"] == "35a9cb70"
    for _ in range(2):  # 渲染頁面前後各比一次
        got = _capture(client)
        for key in ("search_sources", "scraper_sources", "config_sources", "capabilities_source_enums"):
            assert got[key] == golden[key], f"{key} 與升級前不同。{REGEN_STEPS}"
        client.get("/settings")


def test_zero_custom_leaves_config_bytes_unchanged(client, zero_env):
    before = _config_bytes()
    for path in RENDER_PAGES:
        assert client.get(path).status_code == 200
    _capture(client)
    assert _config_bytes() == before
    assert "custom_sources" not in json.loads(before)
    assert "custom_sources" not in json.loads(_config_bytes())


def test_zero_custom_creates_no_directory(client, zero_env):
    d = zero_env / "custom_sources"
    existed = d.exists()
    for path in RENDER_PAGES:
        assert client.get(path).status_code == 200
    _capture(client)
    assert d.exists() == existed
    if existed:
        assert list(d.iterdir()) == []


# ---------- ⓪ 持久化不被汙染 ----------

@pytest.mark.parametrize("blank_locale", [False, True])
def test_render_never_pollutes_persisted_sources(client, env, blank_locale):
    _ready(env, "single-og", SINGLE)
    if blank_locale:  # 走首次偵測 locale 的 mutate_config 寫入路徑
        raw = json.loads(_config_bytes())
        raw["general"]["locale"] = ""
        core_config.CONFIG_PATH.write_text(json.dumps(raw), encoding="utf-8")
    assert client.get("/settings").status_code == 200
    for path in PAGES:
        sources = _ssr_sources(client, path)
        assert [s["id"] for s in _customs(sources)] == ["custom:single-og"]  # 同一次 render 看得到
        assert _customs(load_config()["sources"]) == []
        assert "custom" not in {s.get("type") for s in json.loads(_config_bytes())["sources"]}
    if blank_locale:
        assert json.loads(_config_bytes())["general"]["locale"]  # 確認寫入路徑真的跑過
    # 再渲染一次：不累加
    assert len(_customs(_ssr_sources(client))) == 1


# ---------- 有自訂來源 ----------

def test_ssr_lists_usable_custom_source(client, env):
    baseline = _dump(_legacy_sources())
    _ready(env, "single-og", SINGLE)
    for path in PAGES:
        sources = _ssr_sources(client, path)
        customs = _customs(sources)
        assert len(customs) == 1
        c = customs[0]
        assert c["id"] == "custom:single-og"
        assert c["routable"] is True and c["available"] is True
        assert c["is_censored"] is True and c["manual_only"] is True
        assert c["custom_status"] == "passed"
        assert _dump([s for s in sources if s.get("type") != "custom"]) == baseline


def test_unverified_custom_listed_but_not_routable(client, env):
    _ready(env, "good-one", _yaml(SINGLE, "good-one"))
    put_source(env, "raw-one", _yaml(SINGLE, "raw-one"))  # 放檔、無紀錄
    by_id = {s["id"]: s for s in _customs(_ssr_sources(client))}
    assert set(by_id) == {"custom:good-one", "custom:raw-one"}
    assert by_id["custom:raw-one"]["routable"] is False
    assert by_id["custom:raw-one"]["custom_status"] == "unverified"
    assert by_id["custom:good-one"]["routable"] is True


# ---------- BE-CONFIG-05 ----------

def test_old_snapshot_put_keeps_custom_state(client, env):
    snapshot = client.get("/api/config").json()["data"]
    _ready(env, "single-og", SINGLE)  # 後端之後才寫 custom_sources
    assert "single-og" in json.loads(_config_bytes())["custom_sources"]
    resp = client.put("/api/config", json=snapshot)
    assert resp.status_code == 200
    raw = json.loads(_config_bytes())
    assert "single-og" in raw["custom_sources"]
    assert _customs(raw["sources"]) == []
    assert [s["id"] for s in _customs(_ssr_sources(client))] == ["custom:single-og"]


def test_golden_mismatch_message_has_regen_steps():
    assert "git clone --local" in REGEN_STEPS and "35a9cb70" in REGEN_STEPS
    assert REGEN_SCRIPT in REGEN_STEPS and Path(REGEN_SCRIPT).name == REGEN.name
    assert "clone 內不需要有它" in REGEN_STEPS
