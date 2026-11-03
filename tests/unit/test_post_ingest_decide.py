"""post_ingest 決策核心＋入口（189a-T4a）。"""
from __future__ import annotations

import logging
import threading

import pytest

from core.ai_services import post_ingest
from core.database import Video

ALL_OFF = {
    "translate": {"enabled": False},
    "ai_services": {"image_similar": {"enabled": False}, "tags": {"enabled": False}},
}


def _cfg(**overrides):
    cfg = {
        "translate": {"enabled": True},
        "ai_services": {"image_similar": {"enabled": True}, "tags": {"enabled": True}},
        "general": {"locale": "zh-TW"},
    }
    if "translate_enabled" in overrides:
        cfg["translate"]["enabled"] = overrides["translate_enabled"]
    if "similar_enabled" in overrides:
        cfg["ai_services"]["image_similar"]["enabled"] = overrides["similar_enabled"]
    if "tags_enabled" in overrides:
        cfg["ai_services"]["tags"]["enabled"] = overrides["tags_enabled"]
    if "locale" in overrides:
        cfg["general"]["locale"] = overrides["locale"]
    return cfg


def _row(**kw):
    base = dict(
        path="file:///videos/SSIS-001.mp4",
        number="SSIS-001",
        title="中文標題",
        original_title="",
        cover_path="",
        nfo_mtime=1.0,
        maker="S1",
    )
    base.update(kw)
    return Video(**base)


_CASES = [
    ("tr_off", _cfg(translate_enabled=False),
     _row(title="これはテスト", original_title="orig"),
     False, True, True, "translate", "off"),
    ("tr_zh", _cfg(), _row(title="中文標題", nfo_mtime=2.0),
     False, True, True, "translate", "title_in_target_language"),
    ("tr_run", _cfg(),
     _row(title="これはテスト", original_title="orig", nfo_mtime=3.0),
     False, True, True, "translate", "run"),
    ("tr_nfo0", _cfg(),
     _row(title="カタカナ", original_title="x", nfo_mtime=0),
     False, True, True, "translate", "title_in_target_language"),
    ("tr_ja", _cfg(locale="ja"),
     _row(title="ひらがな", original_title="x", nfo_mtime=4.0),
     False, True, True, "translate", "title_in_target_language"),
    ("sim_off", _cfg(similar_enabled=False), _row(cover_path="file:///c.jpg"),
     False, True, True, "similar", "off"),
    ("sim_nocover", _cfg(), _row(cover_path=""),
     False, True, True, "similar", "no_cover"),
    ("sim_idx", _cfg(), _row(cover_path="file:///c.jpg"),
     False, False, True, "similar", "index_not_ready"),
    ("sim_run", _cfg(), _row(cover_path="file:///c.jpg"),
     False, True, True, "similar", "run"),
    ("fa_own", _cfg(),
     _row(number="FC2-PPV-1234567", cover_path="file:///c.jpg"),
     True, True, True, "faces", "own_trigger"),
    ("fa_cens", _cfg(),
     _row(number="SSIS-001", maker="S1", cover_path="file:///c.jpg"),
     False, True, True, "faces", "not_uncensored"),
    ("fa_nocover", _cfg(), _row(number="FC2-PPV-1234567", cover_path="file:///c.jpg"),
     False, True, False, "faces", "no_cover"),
    ("fa_run", _cfg(),
     _row(number="FC2-PPV-1234567", cover_path="file:///c.jpg"),
     False, True, True, "faces", "run"),
    ("tg_off", _cfg(tags_enabled=False), _row(cover_path="file:///c.jpg"),
     False, True, True, "tags", "off"),
    ("tg_nocover", _cfg(), _row(cover_path=""),
     False, True, True, "tags", "no_cover"),
    ("tg_run", _cfg(), _row(cover_path="file:///c.jpg"),
     False, True, True, "tags", "run"),
]


@pytest.mark.parametrize(
    "case,cfg,row,skip_faces,index_ready,cover_exists,item,expect",
    _CASES,
    ids=[c[0] for c in _CASES],
)
def test_decide_table(case, cfg, row, skip_faces, index_ready, cover_exists, item, expect):
    plan = post_ingest.decide(
        cfg, row, skip_faces=skip_faces, index_ready=index_ready, cover_exists=cover_exists,
    )
    v = getattr(plan, item)
    if expect == "run":
        assert v == post_ingest.Verdict(True)
    else:
        assert v == post_ingest.Verdict(False, expect)
    if case != "tr_run":
        return
    mixed_row = _row(
        title="これはテスト", original_title="orig", nfo_mtime=3.0,
        cover_path="", number="FC2-PPV-1234567",
    )
    mixed = post_ingest.decide(
        _cfg(), mixed_row, skip_faces=True, index_ready=True, cover_exists=False,
    )
    assert post_ingest.format_log("organize", mixed_row, mixed) == (
        "[post_ingest] route=organize video=FC2-PPV-1234567 "
        "translate=run similar=skip(no_cover) "
        "faces=skip(own_trigger) tags=skip(no_cover)"
    )


class _FakeRepo:
    def __init__(self, row=None):
        self.row = row
        self.call_count = 0

    def get_by_path(self, _path):
        self.call_count += 1
        return self.row


class _Counter:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_hook_off_reads_nothing(monkeypatch):
    repo = _FakeRepo(_row(number="SSIS-001"))
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: repo)
    monkeypatch.setattr(post_ingest, "load_config", lambda: ALL_OFF)
    submit = _Counter()
    run_item = _Counter()
    monkeypatch.setattr(post_ingest, "_submit", submit)
    monkeypatch.setattr(post_ingest, "_run_item", run_item)

    before = {t.name for t in threading.enumerate()}
    post_ingest.run_after_ingest("file:///videos/a.mp4", route="organize", skip_faces=True)
    assert repo.call_count == 0
    assert len(submit.calls) == 0 and len(run_item.calls) == 0
    assert before == {t.name for t in threading.enumerate()}

    repo.call_count = 0
    submit.calls.clear()
    run_item.calls.clear()
    post_ingest.run_after_ingest("file:///videos/a.mp4", route="organize", skip_faces=False)
    assert repo.call_count <= 1
    assert len(submit.calls) == 0 and len(run_item.calls) == 0


def test_entry_never_raises_and_items_independent(monkeypatch, caplog):
    orig_decide = post_ingest.decide
    row = _row(
        title="これはテスト", original_title="orig", nfo_mtime=5.0,
        cover_path="file:///c.jpg", number="FC2-PPV-1234567",
    )
    repo = _FakeRepo(row)
    monkeypatch.setattr(post_ingest, "VideoRepository", lambda: repo)
    monkeypatch.setattr(post_ingest, "load_config", lambda: _cfg())
    monkeypatch.setattr(post_ingest, "_index_ready", lambda: True)
    monkeypatch.setattr(post_ingest, "_cover_exists", lambda _r, _c: True)

    def boom_decide(*_a, **_k):
        raise RuntimeError("decide-boom")

    monkeypatch.setattr(post_ingest, "decide", boom_decide)
    with caplog.at_level(logging.INFO, logger=post_ingest.logger.name):
        post_ingest.run_after_ingest(row.path, route="scrape", skip_faces=False, notify=True)
    assert any(
        "[post_ingest]" in rec.getMessage() and rec.exc_info
        for rec in caplog.records
    )

    monkeypatch.setattr(post_ingest, "decide", orig_decide)

    class BoomSubmit(_Counter):
        def __call__(self, item, job):
            self.calls.append((item, job))
            if item == "translate":
                raise RuntimeError("submit-translate-boom")

    submit = BoomSubmit()
    run_item = _Counter()
    monkeypatch.setattr(post_ingest, "_submit", submit)
    monkeypatch.setattr(post_ingest, "_run_item", run_item)
    # skip_faces=True → faces 不跑；translate／similar／tags 皆 run
    post_ingest.run_after_ingest(row.path, route="scrape", skip_faces=True, notify=False)
    submitted = [c[0] for c in submit.calls]
    assert "similar" in submitted and "tags" in submitted

    submit.calls.clear()
    run_item.calls.clear()
    # faces 邊界：無碼＋封面在 → _run_item("faces")；_submit 不含 faces
    post_ingest.run_after_ingest(row.path, route="scrape", skip_faces=False, notify=False)
    assert any(c[0][0] == "faces" for c in run_item.calls)
    assert "faces" not in [c[0] for c in submit.calls]


@pytest.mark.parametrize("source,translated,expect_bad", [
    ("美人妻教師", " 美人妻教師 ", True),
    ("これはテスト", "這是テスト", True),
    ("これはテスト", "這是\n測試", True),
    ("あいうえお", "測" * 46, True),
    ("これはテスト", "抱歉，我無法翻譯這個標題", True),
    ("これはテスト", "I can’t translate this", True),
    ("これはテスト", "這是測試", False),
    ("美しい人妻の秘密", "美麗人妻的秘密", False),
])
def test_bad_translation_never_written_back(monkeypatch, source, translated, expect_bad):
    assert post_ingest._bad_translation(source, translated) is expect_bad
    class _Svc:
        async def translate_or_raise(self, _title, _ctx=None):
            return translated
    calls = []
    def _fake_writeback(*a, **k):
        calls.append((a, k))
        return {"success": True}
    monkeypatch.setattr(post_ingest, "create_translate_service", lambda *_a, **_k: _Svc())
    monkeypatch.setattr(post_ingest, "apply_title_writeback", _fake_writeback)
    monkeypatch.setattr(
        post_ingest, "VideoRepository",
        lambda: type("R", (), {"get_by_path": lambda _s, _p: _row(title=source)})(),
    )
    ctx = post_ingest.IngestContext(video_uri="file:///videos/SSIS-001.mp4", route="scrape", notify=False, cfg={"general": {"locale": "zh-TW"}, "translate": {}}, row=_row(title=source))
    assert post_ingest._job_translate(ctx) == ("bad_translation" if expect_bad else None)
    assert len(calls) == (0 if expect_bad else 1)
