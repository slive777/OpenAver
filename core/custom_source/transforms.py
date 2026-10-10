"""自訂來源的五種欄位變換。

每個變換吃一個字串、回字串／字串 list／None（None＝丟棄該元素）。
名稱到函式的對應是字面表，不做動態查找。
"""
import math
import re
from urllib.parse import urljoin


def round_half_up(number):
    """四捨五入（.5 一律進位；內建 round 是銀行家捨入）。"""
    return math.floor(number + 0.5)


def _regex(value, arg, base_url):
    match = re.search(arg, value)
    return match.group(1) if match else None


def _strip_label(value, arg, base_url):
    text = value.strip()
    if text.startswith(arg):
        return text[len(arg):].strip()
    return text


def _split(value, arg, base_url):
    return [part.strip() for part in value.split(arg) if part.strip()]


def _urljoin(value, arg, base_url):
    try:
        return urljoin(base_url, value)
    except ValueError:
        return None


def _div(value, arg, base_url):
    try:
        return str(round_half_up(float(value) / arg))
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


_DISPATCH = {
    "regex": _regex,
    "strip_label": _strip_label,
    "split": _split,
    "urljoin": _urljoin,
    "div": _div,
}


def apply_transforms(values, transforms, base_url):
    """逐變換、逐元素作用；None 丟棄、list 結果展開、元素一律轉 str。"""
    current = [str(v) for v in values]
    for transform in transforms:
        func = _DISPATCH[transform.name]
        nxt = []
        for value in current:
            result = func(value, transform.arg, base_url)
            if result is None:
                continue
            items = result if isinstance(result, list) else [result]
            nxt.extend(str(item) for item in items)
        current = nxt
    return current
