"""自訂來源狀態層：持久化（真 tmp config.json）、五態推導、截斷、操作世代、單飛行、鎖可追蹤。"""

import json
import shutil
import threading

import pytest

import core.config as core_config
from core.config import AppConfig, load_config, mutate_config, save_config
from core.custom_source import gate, registry, state, views
from tests.unit._custom_source_pages import FIXTURE_DIR

SID = "single-og"
SHA_A = "a" * 64


@pytest.fixture
def env(tmp_path, monkeypatch):
    """資料根與 config.json 分開放（避免 ConfigRootNotFinalizedError）；走真檔案 I/O。"""
    root = tmp_path / "root"
    root.mkdir()
    cfg_path = tmp_path / "cfg" / "config.json"
    cfg_path.parent.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    monkeypatch.setattr(core_config, "CONFIG_PATH", cfg_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "none.json")
    monkeypatch.setattr(state, "_gens", {})
    monkeypatch.setattr(state, "_running_id", None)
    save_config(load_config())  # 先跑過 migration 到不動點（兩趟），之後的 bytes 比對才乾淨
    load_config()
    return root, cfg_path


def _put(root, names=(SID,)):
    d = root / "custom_sources"
    d.mkdir(exist_ok=True)
    for n in names:
        shutil.copy(FIXTURE_DIR / f"{n}.yaml", d / f"{n}.yaml")
    return d


def _cases(n, mismatches=0, value="x"):
    return [
        {
            "index": i, "number": f"N-{i}", "passed": mismatches == 0,
            "mismatches": [
                {"key": f"k{j}", "expected": value, "actual": value, "url": value}
                for j in range(mismatches)
            ],
        }
        for i in range(n)
    ]


def _result(cases=None, total=None, failed=0):
    cases = _cases(1) if cases is None else cases
    return {"total": len(cases) if total is None else total, "failed": failed, "cases": cases}


def _record(source_id, sha, status="passed", result=None):
    return state.record_result(source_id, sha, status, result or _result(), state.get_gen(source_id))


def _loaded(root):
    _put(root)
    return registry.load_one(SID)


def test_absent_key_is_byte_identical_and_creates_no_dir(env):
    root, cfg_path = env
    before = cfg_path.read_bytes()
    assert "custom_sources" not in json.loads(before)
    loaded = _loaded(root)
    shutil.rmtree(root / "custom_sources")
    assert state.read_entry(SID) is None
    assert state.read_all() == {}
    assert state.derive_status(loaded, None, None) == "unverified"
    assert views.custom_source_configs() == []
    assert gate.check_usable(SID).reason == "not_loaded"  # 目錄不存在
    (root / "custom_sources").mkdir()
    assert gate.check_usable(SID).reason == "not_loaded"  # 目錄為空
    shutil.rmtree(root / "custom_sources")
    assert views.custom_source_configs() == []
    assert not (root / "custom_sources").exists()
    assert cfg_path.read_bytes() == before


def test_stale_snapshot_put_does_not_roll_back_custom_sources(env):
    root, cfg_path = env
    stale_payload = AppConfig().model_dump()  # 前端長駐的舊快照，在寫入之前取得
    assert _record(SID, SHA_A)
    written = load_config()["custom_sources"]
    assert written[SID]["status"] == "passed"
    mutate_config(lambda cfg: cfg.update(stale_payload))  # 同 web/routers/config.py 的整包寫回
    assert load_config()["custom_sources"] == written
    assert json.loads(cfg_path.read_text(encoding="utf-8"))["custom_sources"] == written


def test_record_result_persists_to_disk(env):
    root, cfg_path = env
    assert _record(SID, SHA_A, "passed", _result(_cases(2), total=2))
    entry = json.loads(cfg_path.read_text(encoding="utf-8"))["custom_sources"][SID]
    assert entry["sha256"] == SHA_A and entry["status"] == "passed"
    assert entry["enabled"] is False
    assert isinstance(entry["verified_at"], int)
    assert entry["last_result"]["total"] == 2


@pytest.mark.parametrize("case", ["load_failed", "verifying", "unverified", "passed", "failed"])
def test_derive_status_five_states(env, case):
    root, _ = env
    d = _put(root)
    loaded = registry.load_one(SID)
    entry = {"sha256": loaded.sha256, "status": "passed", "enabled": True}
    running = None
    if case == "load_failed":
        (d / "bad.yaml").write_text("id: [unclosed", encoding="utf-8")
        loaded = registry.load_one("bad")
        entry = {"sha256": loaded.sha256, "status": "passed"}
    elif case == "verifying":
        running = SID
    elif case == "unverified":
        entry = None
    elif case == "failed":
        entry["status"] = "failed"
    assert state.derive_status(loaded, entry, running) == case


def test_derive_status_verifying_beats_unverified(env):
    root, _ = env
    loaded = _loaded(root)
    assert state.derive_status(loaded, None, SID) == "verifying"
    assert state.derive_status(loaded, None, "other") == "unverified"


def test_derive_status_hash_mismatch_is_unverified(env):
    root, _ = env
    d = _put(root)
    loaded = registry.load_one(SID)
    entry = {"sha256": loaded.sha256, "status": "passed", "enabled": True}
    assert state.derive_status(loaded, entry, None) == "passed"
    assert state.effective_enabled(entry, "passed") is True
    path = d / f"{SID}.yaml"
    path.write_bytes(path.read_bytes() + b"# edited\n")  # 手動覆蓋：現檔雜湊改變
    changed = registry.load_one(SID)
    assert changed.sha256 != entry["sha256"]
    status = state.derive_status(changed, entry, None)
    assert status == "unverified"
    assert state.effective_enabled(entry, status) is False


@pytest.mark.parametrize("bad", ["str", ["x"], 3, {"status": "passed"}, {"sha256": "SHA", "status": "bogus"}])
def test_derive_status_broken_entry_is_unverified(env, bad):
    root, _ = env
    loaded = _loaded(root)
    if isinstance(bad, dict) and bad.get("sha256") == "SHA":
        bad = {**bad, "sha256": loaded.sha256}
    assert state.derive_status(loaded, bad, None) == "unverified"


def test_effective_enabled_requires_passed():
    assert state.effective_enabled({"enabled": True, "status": "passed"}, "passed") is True
    assert state.effective_enabled({"enabled": True, "status": "failed"}, "failed") is False
    assert state.effective_enabled({"enabled": True}, "unverified") is False
    assert state.effective_enabled({"enabled": False}, "passed") is False
    assert state.effective_enabled(None, "passed") is False


def test_truncation_cases_mismatches_and_value_length(env):
    _record(SID, SHA_A, "failed", _result(_cases(25, mismatches=0), total=25, failed=7))
    last = load_config()["custom_sources"][SID]["last_result"]
    assert len(last["cases"]) == state.MAX_CASES == 20
    assert last["total"] == 25 and last["failed"] == 7
    _record(SID, SHA_A, "failed", _result(_cases(1, mismatches=5)))
    assert len(load_config()["custom_sources"][SID]["last_result"]["cases"][0]["mismatches"]) == 3
    case = {"index": 0, "number": "N-1", "passed": False, "mismatches": [
        {"key": "title", "expected": ["a", "b"], "actual": "z" * 300, "url": "u" * 500}]}
    _record(SID, SHA_A, "failed", _result([case]))
    m = load_config()["custom_sources"][SID]["last_result"]["cases"][0]["mismatches"][0]
    assert len(m["actual"]) == 120 and len(m["url"]) == 120
    assert m["expected"] == str(["a", "b"])


def test_failed_result_forces_disabled_and_passed_keeps_only_same_sha(env):
    _record(SID, SHA_A, "passed")
    assert state.set_enabled(SID, True, SHA_A) is True
    _record(SID, SHA_A, "passed")  # 同雜湊重驗：保留 enabled
    assert load_config()["custom_sources"][SID]["enabled"] is True
    _record(SID, "b" * 64, "passed")  # 不同雜湊：關閉
    assert load_config()["custom_sources"][SID]["enabled"] is False
    state.set_enabled(SID, True, "b" * 64)
    _record(SID, "b" * 64, "failed")  # 失敗：必關
    assert load_config()["custom_sources"][SID]["enabled"] is False


def test_set_enabled_requires_passed_and_same_sha(env):
    root, cfg_path = env
    before = cfg_path.read_bytes()
    assert state.set_enabled(SID, True, SHA_A) is False  # 無紀錄
    assert cfg_path.read_bytes() == before
    _record(SID, SHA_A, "failed")
    assert state.set_enabled(SID, True, SHA_A) is False  # failed
    _record(SID, SHA_A, "passed")
    assert state.set_enabled(SID, True, "c" * 64) is False  # 雜湊不符
    assert load_config()["custom_sources"][SID]["enabled"] is False
    assert state.set_enabled(SID, True, SHA_A) is True
    assert load_config()["custom_sources"][SID]["enabled"] is True


@pytest.mark.parametrize("case", ["failed_record", "sha_mismatch"])
def test_set_enabled_rejection_leaves_config_bytes_unchanged(env, case):
    _, cfg_path = env
    _record(SID, SHA_A, "failed" if case == "failed_record" else "passed")
    before = cfg_path.read_bytes()
    asked = SHA_A if case == "failed_record" else "c" * 64
    assert state.set_enabled(SID, True, asked) is False
    assert cfg_path.read_bytes() == before


def test_clear_removes_only_that_record(env):
    _record(SID, SHA_A)
    _record("other", SHA_A)
    assert state.clear(SID) is True
    assert set(load_config()["custom_sources"]) == {"other"}
    assert state.clear(SID) is False


def test_record_result_drops_stale_gen(env):
    _, cfg_path = env
    seen = state.get_gen(SID)
    state.bump_gen(SID)
    before = cfg_path.read_bytes()
    assert state.record_result(SID, SHA_A, "passed", _result(), seen) is False
    assert cfg_path.read_bytes() == before
    assert state.record_result(SID, SHA_A, "passed", _result(), state.get_gen(SID)) is True


def test_gen_has_no_none_bypass(env):
    _, cfg_path = env
    before = cfg_path.read_bytes()
    assert state.record_result(SID, SHA_A, "passed", _result(), None) is False
    assert cfg_path.read_bytes() == before


def test_single_flight_across_ids(env):
    assert state.try_begin_verify("a") is True
    assert state.try_begin_verify("b") is False
    assert state.try_begin_verify("a") is False
    assert state.get_running_id() == "a"
    state.end_verify("b")  # 非持有者不能結束
    assert state.try_begin_verify("b") is False
    state.end_verify("a")
    assert state.try_begin_verify("b") is True


class _TrackedLock:
    def __init__(self):
        self._real = threading.RLock()
        self.acquired = 0
        self.in_callback = False
        self.violations = 0

    def acquire(self, *a, **k):
        self.acquired += 1
        if self.in_callback:
            self.violations += 1
        return self._real.acquire(*a, **k)

    def release(self):
        self._real.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def test_lock_is_read_at_call_time_and_not_taken_in_mutate_callback(env, monkeypatch):
    tracker = _TrackedLock()
    monkeypatch.setattr(state, "LOCK", tracker)
    real = state.mutate_config

    def wrapped(mutator):
        def inner(cfg):
            tracker.in_callback = True
            try:
                mutator(cfg)
            finally:
                tracker.in_callback = False
        return real(inner)

    monkeypatch.setattr(state, "mutate_config", wrapped)
    n = tracker.acquired
    state.bump_gen(SID)
    assert tracker.acquired > n
    n = tracker.acquired
    assert _record(SID, SHA_A)
    assert tracker.acquired > n
    assert state.set_enabled(SID, True, SHA_A)
    assert state.clear(SID)
    assert tracker.violations == 0
