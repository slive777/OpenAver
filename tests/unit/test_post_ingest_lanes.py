"""post_ingest lane／job／NFO 單寫者／通知的不變式（189a-T4b）。"""
from __future__ import annotations

import logging
import threading
import time

import pytest

from core.ai_services import post_ingest, similar_index, similar_state, tags_state
from core.ai_services.tagging import TaggingFailure
from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from core.user_tags_write import hold_nfo_write

URI = "file:///videos/FC2-PPV-1234567.mp4"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(post_ingest, "_LANES", {})
    for name, val in (("notified", False), ("hook_notified", False), ("unreachable", False),
                      ("notification_sink", None)):
        monkeypatch.setattr(tags_state._STATE, name, val)
    for name, val in (("hook_notified", False), ("unreachable", False)):
        monkeypatch.setattr(similar_state._STATE, name, val)
    for name, val in (("last_error_kind", None), ("last_error_check", None)):
        monkeypatch.setattr(similar_state, name, val)
    monkeypatch.setattr(similar_index, "_notification_sink", None)
    yield
    lanes = list(post_ingest._LANES.values())
    for lane in lanes:
        lane.queue.put(None)
    for lane in lanes:
        lane.thread.join(5)
        if lane.thread.is_alive():
            pytest.fail(f"lane thread {lane.item} did not stop")


class _Repo:
    def __init__(self, row):
        self.row = row

    def get_by_path(self, _path):
        return self.row


def _cfg(translate=True, similar=True, tags=True):
    return {
        "translate": {"enabled": translate},
        "ai_services": {"image_similar": {"enabled": similar}, "tags": {"enabled": tags}},
        "general": {"locale": "zh-TW"},
    }


def _setup(monkeypatch, row, cfg):
    monkeypatch.setattr(post_ingest, "load_config", lambda: cfg)
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: _Repo(row))
    monkeypatch.setattr(post_ingest, "_index_ready", lambda: True)
    monkeypatch.setattr(post_ingest, "_cover_exists", lambda _r, _c: True)


def _jp_row(number="FC2-PPV-1234567"):
    return Video(path=URI, number=number, title="これはテスト", original_title="o",
                 cover_path="file:///c.jpg", nfo_mtime=1.0, maker="")


def _wait(event, what, timeout=3):
    if not event.wait(timeout):
        pytest.fail(f"timeout waiting for {what}")


def _wait_idle(timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(lane.queue.unfinished_tasks == 0 for lane in list(post_ingest._LANES.values())):
            return
        time.sleep(0.01)
    pytest.fail("lanes not idle")


def test_hook_returns_before_lane_work_finishes(monkeypatch):
    _setup(monkeypatch, _jp_row(), _cfg())
    gate, started, finished = threading.Event(), threading.Event(), threading.Event()

    def slow_translate(_ctx):
        started.set()
        gate.wait(10)
        finished.set()

    focal = []
    monkeypatch.setattr(post_ingest, "_job_translate", slow_translate)
    monkeypatch.setattr(post_ingest, "_job_similar", lambda _c: None)
    monkeypatch.setattr(post_ingest, "_job_tags", lambda _c: None)
    monkeypatch.setattr(post_ingest, "maybe_submit_video_focal", lambda *a, **k: focal.append(k))
    watchdog = threading.Thread(
        target=lambda: post_ingest.run_after_ingest(URI, route="scrape"), daemon=True)
    try:
        watchdog.start()
        watchdog.join(2)
        assert not watchdog.is_alive(), "run_after_ingest blocked on lane work"
        assert not finished.is_set()
        assert len(focal) == 1
        post_ingest.run_after_ingest(URI, route="scrape", skip_faces=True)
        assert len(focal) == 1
    finally:
        gate.set()
        watchdog.join(5)
        assert not watchdog.is_alive()
    _wait(finished, "translate job")
    _wait_idle()


def test_slow_translation_does_not_hold_up_tags_or_similar(monkeypatch):
    _setup(monkeypatch, _jp_row(number="SSIS-001"), _cfg())
    gate, tr_done = threading.Event(), threading.Event()
    tags_done, sim_done = threading.Event(), threading.Event()

    def slow_translate(_ctx):
        gate.wait(10)
        tr_done.set()

    monkeypatch.setattr(post_ingest, "_job_translate", slow_translate)
    monkeypatch.setattr(post_ingest, "_job_tags", lambda _c: tags_done.set())
    monkeypatch.setattr(post_ingest, "_job_similar", lambda _c: sim_done.set())
    try:
        post_ingest.run_after_ingest(URI, route="scrape")
        _wait(tags_done, "tags while translate is held")
        _wait(sim_done, "similar while translate is held")
        assert not tr_done.is_set()
    finally:
        gate.set()
    _wait(tr_done, "translate job")
    _wait_idle()


def test_job_failures_never_escape_and_lane_survives(monkeypatch, caplog):
    _setup(monkeypatch, _jp_row(number="SSIS-001"), _cfg(translate=False))
    tag_calls = []

    def bad_tags(*_a, **_k):
        tag_calls.append(1)
        raise RuntimeError("SECRET-XYZ")

    monkeypatch.setattr(post_ingest, "tag_video_sync", bad_tags)
    monkeypatch.setattr(post_ingest.similar_index, "index_one", lambda _u: "error")
    with caplog.at_level(logging.INFO, logger=post_ingest.logger.name):
        post_ingest.run_after_ingest(URI, route="scrape", notify=False)
        _wait_idle()
        monkeypatch.setattr(post_ingest, "tag_video_sync", lambda *a, **k: tag_calls.append(2))
        post_ingest.run_after_ingest(URI, route="scrape", notify=False)
        _wait_idle()
    assert "[post_ingest] tags failed reason=RuntimeError" in caplog.text
    assert "similar failed reason=error" in caplog.text
    assert "SECRET-XYZ" not in caplog.text
    assert tag_calls == [1, 2]


def test_translate_and_tags_never_overwrite_each_other(monkeypatch, tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    mp4 = tmp_path / "AI-001.mp4"
    mp4.write_bytes(b"x")
    nfo = mp4.with_suffix(".nfo")
    nfo.write_text("<movie><title>あいう</title><num>AI-001</num></movie>", encoding="utf-8")
    uri = to_file_uri(str(mp4))
    repo = VideoRepository(db)
    repo.upsert(Video(path=uri, number="AI-001", title="あいう", original_title="o", nfo_mtime=1.0))
    cfg = {"translate": {"enabled": True}, "general": {"locale": "zh-TW"},
           "gallery": {}, "ai_services": {}}
    monkeypatch.setattr(post_ingest, "load_config", lambda: cfg)
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: repo)
    translated = threading.Event()

    class _Svc:
        async def translate_or_raise(self, _title, _ctx=None):
            translated.set()
            return "新翻譯標題"

    monkeypatch.setattr(post_ingest, "create_translate_service", lambda *_a: _Svc())
    entry = threading.Thread(
        target=lambda: post_ingest.run_after_ingest(uri, route="scrape", skip_faces=True),
        daemon=True)
    try:
        with hold_nfo_write():
            old = nfo.read_text(encoding="utf-8")
            entry.start()
            _wait(translated, "fake translation")
            time.sleep(0.3)
            assert "あいう" in nfo.read_text(encoding="utf-8")
            nfo.write_text(old.replace("</movie>", "<user_tag>X</user_tag></movie>"), encoding="utf-8")
    finally:
        if entry.ident is not None:
            entry.join(5)
            assert not entry.is_alive()
    _wait_idle()
    final = nfo.read_text(encoding="utf-8")
    assert "新翻譯標題" in final and "<user_tag>X</user_tag>" in final
    assert repo.get_by_path(uri).title == "新翻譯標題"


def test_stale_row_is_not_overwritten_by_queued_translation(monkeypatch, tmp_path, caplog):
    db = tmp_path / "t.db"
    init_db(db)
    mp4 = tmp_path / "AI-001.mp4"
    mp4.write_bytes(b"x")
    nfo = mp4.with_suffix(".nfo")
    nfo.write_text("<movie><title>あいう</title><num>AI-001</num></movie>", encoding="utf-8")
    uri, repo = to_file_uri(str(mp4)), VideoRepository(db)
    repo.upsert(Video(path=uri, number="AI-001", title="あいう", original_title="o", nfo_mtime=1.0))
    cfg = {"translate": {"enabled": True}, "general": {"locale": "zh-TW"},
           "gallery": {}, "ai_services": {}}
    monkeypatch.setattr(post_ingest, "load_config", lambda: cfg)
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: repo)

    class _Svc:  # 排隊期間使用者在燈箱手動改了標題
        async def translate_or_raise(self, _title, _ctx=None):
            repo.update_titles(uri, "手動標題", "o", 1.0)
            return "舊的機器翻譯"

    monkeypatch.setattr(post_ingest, "create_translate_service", lambda *_a: _Svc())
    before = nfo.read_text(encoding="utf-8")
    with caplog.at_level(logging.INFO, logger=post_ingest.logger.name):
        post_ingest.run_after_ingest(uri, route="scrape", skip_faces=True)
        _wait_idle()
    assert "translate failed reason=stale_row" in caplog.text
    assert nfo.read_text(encoding="utf-8") == before
    assert repo.get_by_path(uri).title == "手動標題"


def test_unreachable_notifies_once_per_round(monkeypatch):
    _setup(monkeypatch, _jp_row(number="SSIS-001"), _cfg(translate=False))
    tag_keys, sim_keys = [], []
    tags_state.set_notification_sink(lambda _lv, key, **_k: tag_keys.append(key))
    monkeypatch.setattr(similar_index, "_notification_sink",
                        lambda _lv, key, **_k: sim_keys.append(key))
    failure = [TaggingFailure("unreachable", "connect")]
    outcome = ["unreachable"]

    def tags(*_a, **_k):
        raise failure[0]

    def sim(_uri):
        similar_state.observe_failure("unreachable", "x")
        return outcome[0]

    monkeypatch.setattr(post_ingest, "tag_video_sync", tags)
    monkeypatch.setattr(post_ingest.similar_index, "index_one", sim)

    def burst(n, notify=True):
        for _ in range(n):
            post_ingest.run_after_ingest(URI, route="scrape", skip_faces=True, notify=notify)
        _wait_idle()

    burst(5)
    assert tag_keys == ["notif.ai_tags_unreachable"]
    assert sim_keys == ["notif.ai_similar_unreachable"]
    tags_state.job_begin("build")  # 補完全庫開工不得讓掛勾同輪再發
    burst(2)
    assert len(tag_keys) == 1 and len(sim_keys) == 1
    assert tags_state.note_failure() is True  # 掛勾通知沒耗掉補完全庫的旗標
    post_ingest.begin_round()
    burst(1)
    assert len(tag_keys) == 2 and len(sim_keys) == 2
    burst(3, notify=False)
    post_ingest.begin_round()
    burst(3, notify=False)
    assert len(tag_keys) == 2 and len(sim_keys) == 2
    outcome[0] = "error"  # 舊狀態 unreachable、本次只是別的錯 → 不通知
    for failure[0] in (TaggingFailure("unreachable", "rate_limited"), TaggingFailure("disabled")):
        post_ingest.begin_round()
        burst(1)
    assert len(tag_keys) == 2 and len(sim_keys) == 2
