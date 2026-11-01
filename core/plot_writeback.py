"""plot_writeback.py — 就地改寫 NFO 的 <plot>／<originalplot>（TASK-187b-T4，CD-187b-7）。

只改這兩個元素，其餘原樣保留。NfoNotFoundError／NfoParseError／strip_illegal_xml_chars
直接重用 core.title_writeback 的公開別名。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple, Union

from core.nfo_updater import set_element_text
from core.nfo_utils import sanitize_nfo_bytes
from core.title_writeback import (
    NfoNotFoundError,
    NfoParseError,
    strip_illegal_xml_chars,
)


class PlotEmptyError(Exception):
    """NFO 無 <plot> 或內容為空。"""


def read_nfo_plots(nfo_path: Union[str, Path]) -> Tuple[str, str]:
    """讀取 NFO 的 (plot, original_plot)。

    只剝頭尾空白、保留內部換行；無 <originalplot> → ""；無／空 <plot> 仍回 ""
    （呼叫端判 plot_empty）。檔不存在 → NfoNotFoundError；無法解析 → NfoParseError。
    """
    path = Path(nfo_path)
    if not path.exists():
        raise NfoNotFoundError(str(nfo_path))
    raw = path.read_bytes()
    raw = sanitize_nfo_bytes(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise NfoParseError(str(e)) from e
    plot_elem = root.find("plot")
    plot = (plot_elem.text or "").strip() if plot_elem is not None else ""
    orig_elem = root.find("originalplot")
    original = (orig_elem.text or "").strip() if orig_elem is not None else ""
    return plot, original


def rewrite_nfo_plot(
    nfo_path,
    *,
    new_plot: str,
    new_original: Optional[str],
) -> bytes:
    """改寫 NFO 的 <plot>／<originalplot> 並回傳寫出的 bytes。

    new_original 三態（端點解算後傳入）：
      None ＝不動 <originalplot>
      ""   ＝移除 <originalplot> 元素
      非空 ＝設定（after_tag='plot'）

    NFO 不存在 → NfoNotFoundError；無法解析 → NfoParseError；
    無 <plot> → PlotEmptyError；new==old → 不寫檔、回傳現有 bytes。
    """
    path = Path(nfo_path)
    if not path.exists():
        raise NfoNotFoundError(str(nfo_path))

    new_plot = strip_illegal_xml_chars(new_plot)
    if new_original is not None:
        new_original = strip_illegal_xml_chars(new_original)

    raw = path.read_bytes()
    raw = sanitize_nfo_bytes(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise NfoParseError(str(e)) from e

    plot_elem = root.find("plot")
    if plot_elem is None:
        raise PlotEmptyError(str(nfo_path))

    old_plot = plot_elem.text or ""
    old_orig_elem = root.find("originalplot")
    old_original = (old_orig_elem.text or "") if old_orig_elem is not None else None

    # 雙保險：new==old 不寫檔
    plot_same = old_plot == new_plot
    if new_original is None:
        orig_same = True
    elif new_original == "":
        orig_same = old_orig_elem is None
    else:
        orig_same = old_orig_elem is not None and old_original == new_original
    if plot_same and orig_same:
        return bytes(raw)

    set_element_text(root, "plot", new_plot)

    if new_original is None:
        pass
    elif new_original == "":
        existing = root.find("originalplot")
        if existing is not None:
            root.remove(existing)
    else:
        set_element_text(root, "originalplot", new_original, after_tag="plot")

    out = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(out)
    return out
