"""TASK-187b-T4 — core.plot_writeback.rewrite_nfo_plot 單元測試。"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from core.plot_writeback import rewrite_nfo_plot

JP_PLOT = "日本語の劇情\n第二行"
ZH_PLOT = "翻譯後的中文簡介"
ZH_PLOT2 = "再翻一次的簡介"

# 種子：<plot> 後還有其他元素（含 &amp;、多個 actor），供逐元素比對
NFO_SEED = f"""<?xml version='1.0' encoding='utf-8'?>
<movie>
  <title>[ABC-123]タイトル</title>
  <num>ABC-123</num>
  <plot>{JP_PLOT}</plot>
  <rating>7.5</rating>
  <website>https://example.invalid/a&amp;b=1</website>
  <actor><name>女優A</name></actor>
  <actor><name>女優B</name></actor>
</movie>
"""

PLOT_TAGS = {"plot", "originalplot"}


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "ABC-123.nfo"
    p.write_text(text, encoding="utf-8")
    return p


def _canon(e: ET.Element):
    return (
        e.tag,
        e.text,
        tuple(sorted(e.attrib.items())),
        tuple(_canon(c) for c in list(e)),
    )


def _children(root: ET.Element):
    return list(root)


def _text(root: ET.Element, tag: str):
    e = root.find(tag)
    return None if e is None else e.text


def test_rewrite_nfo_plot_states(tmp_path):
    """表驅動：首次／重翻／復原清除／其他元素逐字不變（含 originalplot 緊接 plot）。"""
    p = _write(tmp_path, NFO_SEED)
    before_root = ET.fromstring(NFO_SEED.encode("utf-8"))
    before_others = [_canon(c) for c in before_root if c.tag not in PLOT_TAGS]

    # ── 首次翻譯：plot→譯文、originalplot＝原文且緊接 plot ──
    rewrite_nfo_plot(str(p), new_plot=ZH_PLOT, new_original=JP_PLOT)
    root = ET.fromstring(p.read_bytes())
    assert _text(root, "plot") == ZH_PLOT
    assert _text(root, "originalplot") == JP_PLOT
    kids = _children(root)
    plot_i = next(i for i, c in enumerate(kids) if c.tag == "plot")
    assert kids[plot_i + 1].tag == "originalplot"
    assert [_canon(c) for c in kids if c.tag not in PLOT_TAGS] == before_others

    # ── 重翻：只換 plot，originalplot 不動（new_original=None）──
    rewrite_nfo_plot(str(p), new_plot=ZH_PLOT2, new_original=None)
    root = ET.fromstring(p.read_bytes())
    assert _text(root, "plot") == ZH_PLOT2
    assert _text(root, "originalplot") == JP_PLOT
    kids = _children(root)
    plot_i = next(i for i, c in enumerate(kids) if c.tag == "plot")
    assert kids[plot_i + 1].tag == "originalplot"

    # ── 復原清除：originalplot 元素不存在 ──
    rewrite_nfo_plot(str(p), new_plot=JP_PLOT, new_original="")
    root = ET.fromstring(p.read_bytes())
    assert _text(root, "plot") == JP_PLOT
    assert root.find("originalplot") is None
    assert [_canon(c) for c in root if c.tag not in PLOT_TAGS] == before_others
