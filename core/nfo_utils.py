"""NFO 檔案工具函數"""

import re

# CDATA 區塊 pattern（用於先拆出 CDATA 再對非 CDATA 部分 sanitize）
_CDATA_RE = re.compile(rb'<!\[CDATA\[.*?\]\]>', re.DOTALL)
# bare & pattern：只保留 XML 規範允許的 5 個 predefined entity + numeric reference
_BARE_AMP_RE = re.compile(rb'&(?!(?:amp|lt|gt|quot|apos);|#(?:\d+|x[0-9a-fA-F]+);)')


def sanitize_nfo_bytes(raw: bytes) -> bytes:
    """
    修正非法 bare '&'，讓 malformed XML 可被解析。
    在 bytes 層級操作，不破壞原始編碼。

    只對 CDATA 以外的區域做替換：
    - 保留：&amp; &lt; &gt; &quot; &apos; &#123; &#xAB;
    - 保留：CDATA 區塊內容原封不動（CDATA 內的 & 是合法的）
    - 替換：其餘 bare &（&t=、&nbsp;、&hellip; 等）→ &amp;
    """
    # 無 CDATA 的快速路徑（NFO 幾乎不會有 CDATA）
    if b'<![CDATA[' not in raw:
        return _BARE_AMP_RE.sub(b'&amp;', raw)

    # 有 CDATA：逐段處理，CDATA 區塊原封不動
    result = []
    last_end = 0
    for m in _CDATA_RE.finditer(raw):
        # CDATA 前的普通區域：sanitize
        result.append(_BARE_AMP_RE.sub(b'&amp;', raw[last_end:m.start()]))
        # CDATA 區塊：原封不動
        result.append(m.group())
        last_end = m.end()
    # 最後一段普通區域
    result.append(_BARE_AMP_RE.sub(b'&amp;', raw[last_end:]))
    return b''.join(result)
