"""自動翻譯譯文品質判定：純函式，無 I/O、無 DB。"""
REFUSAL_MARKERS = ("無法翻譯", "無法提供", "抱歉", "i can't", "i cannot", "i'm sorry", "sorry")


def is_bad_translation(source: str, translated: str) -> bool:
    s, t = source.strip(), translated.strip()
    if not t: return True
    t = t.replace("’", "'")
    if t == s or "\n" in t:
        return True
    if len(t) > max(2 * len(s), len(s) + 40):
        return True
    return any(m in t.lower() for m in REFUSAL_MARKERS)
