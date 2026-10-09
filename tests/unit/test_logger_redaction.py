"""debug.log 不得洩漏 proxy URL 內的帳密（163 Codex F1）。走真正的 setup_logging handler。"""
import io
import logging
import sys

import pytest
import requests

import core.logger as core_logger

BADS = ["http://demo:secret@127.0.0.1:70000", "http://demo:sec'ret@127.0.0.1:70000",
        "http://demo:sec/ret@127.0.0.1:70000"]


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    root = logging.getLogger("OpenAver")
    saved = (list(root.handlers), core_logger._initialized, core_logger._log_dir, root.level)
    root.handlers.clear()
    core_logger._initialized = False
    # StringIO 沒有 .buffer → setup_logging 走 fallback，不會包住真 stdout
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    core_logger.setup_logging(tmp_path)
    yield tmp_path / "debug.log"
    for h in list(root.handlers):
        h.close()
    root.handlers[:] = saved[0]
    core_logger._initialized, core_logger._log_dir = saved[1], saved[2]
    root.setLevel(saved[3])


def _read(path):
    for h in logging.getLogger("OpenAver").handlers:
        h.flush()
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("bad", BADS)
def test_message_userinfo_redacted(log_file, bad):
    core_logger.get_logger("t").info("proxy failed: %s", bad)
    text = _read(log_file)
    assert "ret@" not in text
    assert "http://***@127.0.0.1:70000" in text


@pytest.mark.parametrize("bad", BADS)
def test_traceback_userinfo_redacted(log_file, bad):
    logger = core_logger.get_logger("t")
    try:
        requests.get("http://example.invalid/", proxies={"http": bad, "https": bad}, timeout=1)
    except Exception:
        logger.exception("request failed")
    text = _read(log_file)
    assert "request failed" in text and "Traceback" in text
    assert "ret@" not in text


def test_url_without_userinfo_unchanged(log_file):
    url = "https://www.dmm.co.jp/digital/videoa/-/detail/=/cid=abc00123/"
    core_logger.get_logger("t").info("get %s", url)
    assert url in _read(log_file)


def test_two_urls_redacted_independently(log_file):
    core_logger.get_logger("t").info("a http://u:p@h:1 b https://x/y")
    assert "a http://***@h:1 b https://x/y" in _read(log_file)
