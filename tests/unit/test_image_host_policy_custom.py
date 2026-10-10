"""T14：proxy_verdict Branch 3 — routable 自訂來源宣告的站台（真 gate／真 state／tmp config）。

來源 single-og 的 hosts 基底為 single-og.example。
"""
import hashlib
import shutil

import pytest

import core.config as core_config
from core.config import load_config, save_config
from core.custom_source import state
from core.image_host_policy import proxy_verdict
from tests.unit._custom_source_pages import FIXTURE_DIR

SID = "single-og"
BASE = "single-og.example"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "custom_sources").mkdir(parents=True)
    (tmp_path / "cfg").mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(core_config, "CONFIG_PATH", tmp_path / "cfg" / "config.json")
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "none.json")
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    save_config(load_config())
    load_config()
    return root / "custom_sources"


def _install(d, *, passed=True, enable=True):
    path = d / f"{SID}.yaml"
    shutil.copy(FIXTURE_DIR / f"{SID}.yaml", path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if passed:
        assert state.record_result(
            SID, sha, "passed", {"total": 1, "failed": 0, "cases": []}, state.get_gen(SID)
        )
        assert state.set_enabled(SID, bool(enable), sha)  # 通過即啟用（165-T16），未啟用要明確關閉
    return path, sha


def test_routable_custom_host_and_subdomain_allowed(env):
    _install(env)
    for url in (
        f"https://{BASE}/c.jpg",
        f"https://www.{BASE}/c.jpg",
        f"https://cdn.{BASE}/c.jpg",
        f"http://{BASE}/c.jpg",
        f"https://{BASE}:443/c.jpg",
    ):
        v = proxy_verdict(url)
        assert (v.allowed, v.reason) == (True, None), url


def test_foreign_and_lookalike_hosts_403(env):
    _install(env)
    for url in (
        f"https://evil{BASE}/c.jpg",
        f"https://{BASE}.evil.com/c.jpg",
        "https://other.example/c.jpg",
    ):
        v = proxy_verdict(url)
        assert (v.allowed, v.reason) == (False, "host 不在名單"), url


def test_unrouted_source_host_still_403(env):
    _install(env, passed=True, enable=False)  # 通過但未啟用
    v = proxy_verdict(f"https://{BASE}/c.jpg")
    assert (v.allowed, v.reason) == (False, "host 不在名單")


def test_unverified_source_host_403(env):
    _install(env, passed=False)
    assert proxy_verdict(f"https://{BASE}/c.jpg").allowed is False


def test_sha_mismatch_host_403(env):
    path, _ = _install(env)
    path.write_text(path.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    assert proxy_verdict(f"https://{BASE}/c.jpg").allowed is False


def test_no_custom_sources_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path / "empty"))
    assert proxy_verdict(f"https://{BASE}/c.jpg").reason == "host 不在名單"
    assert proxy_verdict("https://pics.dmm.co.jp/a.jpg").allowed is True


def test_malformed_port_and_odd_scheme_and_port_fail_closed(env):
    _install(env)
    assert proxy_verdict(f"https://{BASE}:99999/c.jpg").allowed is False
    assert proxy_verdict(f"https://{BASE}:8443/c.jpg").allowed is False
    assert proxy_verdict(f"http://{BASE}:443/c.jpg").allowed is False
    assert proxy_verdict(f"ftp://{BASE}/c.jpg").allowed is False


def test_custom_host_resolving_to_private_denied(env, monkeypatch):
    _install(env)
    for ip in ("127.0.0.1", "192.168.1.5"):
        monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host, ip=ip: [ip])
        v = proxy_verdict(f"https://lan.{BASE}/c.jpg")
        assert (v.allowed, v.reason) == (False, "自訂來源圖片 host 非公網"), ip
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    assert proxy_verdict(f"https://lan.{BASE}/c.jpg").allowed is True


def test_custom_verdict_flag_only_on_branch3(env):
    _install(env)
    assert proxy_verdict(f"https://{BASE}/c.jpg").custom_source is True
    assert proxy_verdict("https://pics.dmm.co.jp/a.jpg").custom_source is False
