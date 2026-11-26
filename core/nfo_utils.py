"""
NFO 檔案工具函數。

提供底層工具函式供 gallery_scanner 和 nfo_updater 共用，
主要包含 sanitize_nfo_bytes（修正 NFO 中不合規的裸露 & 字元以通過 XML 解析）
及相關正則 pattern。
"""

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


# NFO-CTRL-01（PR #191 CodeRabbit F1/加固；BE-GUARD-01：閘門寫在 sink，不寫在上游白名單）：
# XML 1.0 合法字元只有 \t(0x09) \n(0x0A) \r(0x0D) 與 0x20 以上（另排除 surrogate 區段
# 0xD800–0xDFFF 與 0xFFFE/0xFFFF）。含裸控制字元（\x07/\x0b/\x0c/\x1b/\x00 等）的欄位值
# 目前會讓 generate_nfo() 寫出成功（回 True）但整份 XML 解析失敗——ET.parse 與
# core.nfo_updater.parse_nfo 都讀不到任何欄位，Jellyfin/Kodi/OpenAver 自己全部看不到。
# 這是既有病（core/enricher.py:528 批次補完／進階重刮早就會把 _summary 寫進 <plot>），
# 本次一併在唯一 sink（generate_nfo）收斂，不分兩處補。
_ILLEGAL_XML_CHARS_RE = re.compile(
    '[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]'
)


def strip_illegal_xml_chars(value):
    """剝除字串裡 XML 1.0 不合法的字元，保留 \\t/\\n/\\r（簡介換行不可被吃掉）。

    **非字串一律先收斂成字串**（`None` → `''`，其餘 → `str(value)`）。理由與
    147c-T2 的 `<rating>` 型別防護同一條（BE-GUARD-01：閘門寫在 sink）：
    `POST /api/scrape-single` 對 `metadata` **零驗證**（`web/routers/scraper.py:222`，
    與 `enrich_single` 的嚴格白名單不對稱），AI 送 `{"_summary": null}` 進來時
    `metadata.get('_summary', '')` 會回 `None`（key 存在，default 不生效），
    而 `generate_nfo()` 在 `atomic_move()` **之後**才跑 —— `html.escape(None)` 拋
    `AttributeError` 會讓畫面顯示「整理失敗」，但影片檔其實已經改名搬走了。
    CodeRabbit PR #191 的 P2 提對了這條鏈，只是把觸發前提歸給 scraper 端
    （`Video.summary` 是 `str = Field(default='')` 且 frozen，那半確實不可能）。
    """
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    return _ILLEGAL_XML_CHARS_RE.sub('', value)

