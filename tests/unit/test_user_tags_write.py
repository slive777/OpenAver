"""test_user_tags_write.py — core.user_tags_write.apply_user_tags 的鎖／鎖內過濾／NFO 失敗語意（188b-T2b）

時序類 oracle：三支測試要 tmp DB＋真 NFO＋thread，行數超過一般單元測試屬預期。
"""

from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET

from core import user_tags_write
from core.database import Video, VideoRepository, init_db
from core.path_utils import to_file_uri
from core.user_tags_write import apply_user_tags

_MINIMAL_NFO = """<?xml version='1.0' encoding='utf-8'?>
<movie><title>t</title></movie>
"""

_CONFIG = {"gallery": {"path_mappings": {}}}


def _make_env(tmp_path):
    """tmp DB 一列 user_tags=["★4"]＋真 mp4＋同名真 .nfo。回 (repo, file_uri, mp4, nfo, config)。"""
    db_path = tmp_path / "test_user_tags_write.db"
    init_db(db_path)

    mp4 = tmp_path / "AI-001.mp4"
    mp4.write_bytes(b"fake-video")
    nfo = mp4.with_suffix(".nfo")
    nfo.write_text(_MINIMAL_NFO, encoding="utf-8")

    file_uri = to_file_uri(str(mp4))
    repo = VideoRepository(db_path)
    repo.upsert(Video(path=file_uri, number="AI-001", title="AI-001", user_tags=["★4"]))
    return repo, file_uri, mp4, nfo, _CONFIG


def _nfo_user_tags(nfo) -> set:
    root = ET.parse(str(nfo)).getroot()
    return {e.text for e in root.findall("user_tag")}


def test_concurrent_writes_both_survive_in_db_and_nfo(tmp_path, monkeypatch):
    """背景 AI 與使用者同時對同一部片加字 → 兩邊的字都在，DB 與 NFO 一致。"""
    repo, file_uri, mp4, nfo, config = _make_env(tmp_path)

    original = repo.update_user_tags

    def slow(*args, **kwargs):
        time.sleep(0.05)  # 讀 DB 之後、寫 DB 之前，強迫交錯
        return original(*args, **kwargs)

    monkeypatch.setattr(repo, "update_user_tags", slow)

    def run(tag):
        apply_user_tags(repo, file_uri, str(mp4), config, add=[tag], remove=[])

    threads = [threading.Thread(target=run, args=(t,)) for t in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db_tags = set(repo.get_by_path(file_uri).user_tags)
    assert {"★4", "A", "B"} <= db_tags
    assert _nfo_user_tags(nfo) == db_tags


def test_add_filter_sees_user_tags_written_while_waiting_for_lock(tmp_path):
    """AI 等鎖時使用者加了「待看」→ 過濾看得到它，只新增 X，「待看」不重複。"""
    repo, file_uri, mp4, nfo, config = _make_env(tmp_path)

    seen: list = []
    out: dict = {}

    def f(video):
        seen.extend(video.user_tags)
        return ["待看", "X"]

    def run():
        out["result"] = apply_user_tags(
            repo, file_uri, str(mp4), config, add=[], remove=[], add_filter=f,
        )

    user_tags_write._LOCK.acquire()
    try:
        t = threading.Thread(target=run)
        t.start()
        time.sleep(0.2)  # 讓那條 thread 確實卡在鎖外
        repo.update_user_tags(file_uri, ["★4", "待看"])
    finally:
        user_tags_write._LOCK.release()
    t.join()

    result = out["result"]
    assert "待看" in seen
    assert result.added == ["X"]
    assert repo.get_by_path(file_uri).user_tags.count("待看") == 1


def test_nfo_write_failure_keeps_db_and_records_ran_without_raising(tmp_path):
    """NAS 上 NFO 被占用寫不進去 → 標籤與「跑過」仍留在 DB，不丟例外。"""
    repo, file_uri, mp4, nfo, config = _make_env(tmp_path)
    assert nfo.exists()

    def boom(path, tags):
        raise OSError("locked")

    result = apply_user_tags(
        repo, file_uri, str(mp4), config,
        add=["X"], remove=[], ai_tagged=True, nfo_writer=boom,
    )

    assert result.ok is True
    assert "X" in repo.get_by_path(file_uri).user_tags
    assert repo.get_ai_tagged_at(file_uri) is not None
    assert result.nfo_updated is False
    assert result.nfo_write_blocked is True
    assert result.readonly_no_output is False
